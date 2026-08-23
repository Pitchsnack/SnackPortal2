"""Day 3.6 — the end-to-end smoke path, and the fail-closed cases around it.

These are **integration** tests, not mocked ones. Every hop below runs the real service
application over ASGI: the BFF calls the real Authentication Service, which runs the real
verifier; the real Access Control Service, which runs the real policy engine; the real Database
Router, which runs the real resolver; the real domain services; and the real Audit Service. The
only thing substituted is storage, which is each service's in-memory adapter.

That matters because the failures worth catching here are *wiring* failures — a stage skipped, a
denial that does not propagate, an audit event emitted at the wrong moment. A test suite of
doubles cannot see any of them.

    Frontend/BFF request
      -> Authentication -> Request Context -> Access Control -> Database Router
      -> Tenant Service -> Tenant DB -> Response
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi.testclient import TestClient

from snackportal2.services.access_control import main as ac_main
from snackportal2.services.access_control.membership import StaticMemberships
from snackportal2.services.audit import main as audit_main
from snackportal2.services.audit.identity import CredentialDirectory
from snackportal2.services.audit.sink import InMemoryAuditSink
from snackportal2.services.authentication import main as auth_main
from snackportal2.services.authentication.service import AuthenticationService
from snackportal2.services.authentication.verifier import StaticTokenVerifier
from snackportal2.services.bff.operations import build_router
from snackportal2.services.bff.pipeline import IngressPipeline
from snackportal2.services.bff.ports import AuthenticationResult, AuthorizationResult, CarrierVerdict, RoutedTenant
from snackportal2.services.control_plane import main as cp_main
from snackportal2.services.control_plane.models import (
    DirectoryKind,
    DirectoryRecord,
    SecretReference,
    TenantDescriptor,
)
from snackportal2.services.control_plane.store import InMemoryControlStore
from snackportal2.services.database_router import main as dbr_main
from snackportal2.services.database_router.grants import GrantAllowlist
from snackportal2.services.database_router.resolver import (
    EnvironmentTenantSecretStore,
    StaticTenantRegistry,
    TenantRegistryEntry,
    TenantResolver,
)
from snackportal2.services.deals import main as deals_main
from snackportal2.services.deals.repository import InMemoryDealRepository
from snackportal2.services.import_service import main as import_main
from snackportal2.services.import_service import service as import_service
from snackportal2.services.investors import main as investors_main
from snackportal2.services.investors.repository import InMemoryInvestorRepository
from snackportal2.services.lineage import main as lineage_main
from snackportal2.services.startups import main as startups_main
from snackportal2.services.startups.repository import InMemoryStartupRepository
from snackportal2.shared.errors import AppError, ErrorCode, tenant_unavailable
from snackportal2.shared.security import AuthContext, RequestContext
from snackportal2.shared.service import build_app
from snackportal2.shared.types import DatabaseDomain, PlatformRole, TenantLifecycleState

SERVICE_HEADERS = {"Authorization": "Bearer internal"}

TOKENS = {
    "acme-agent": {"principal_ref": "p-agent", "role": "TENANT_AGENT", "active_tenant": "acme"},
    "zeta-agent": {"principal_ref": "p-zeta", "role": "TENANT_AGENT", "active_tenant": "zeta"},
    "stranger": {"principal_ref": "p-stranger", "role": "TENANT_AGENT", "active_tenant": "acme"},
    "nova-agent": {"principal_ref": "p-nova", "role": "TENANT_AGENT", "active_tenant": "nova"},
    "control": {"principal_ref": "p-control", "role": "CONTROL", "active_tenant": None},
}

_ACME_DSN_VAR = EnvironmentTenantSecretStore.variable_name("assoc/acme", "1")
_ZETA_DSN_VAR = EnvironmentTenantSecretStore.variable_name("assoc/zeta", "1")


# --- In-process adapters: the real apps, reached over ASGI ------------------------------------

class _Authentication:
    def __init__(self, client: TestClient) -> None:
        self._client = client

    def authenticate(self, credential: str, carrier: Optional[str], correlation_id: str) -> Optional[AuthenticationResult]:
        response = self._client.post(
            "/authenticate", headers=SERVICE_HEADERS, json={"credential": credential, "tenant_carrier": carrier}
        )
        if response.status_code != 200:
            return None
        body = response.json()
        return AuthenticationResult(
            auth_context=AuthContext(
                correlation_id=correlation_id or "c-e2e",
                principal_ref=body["principal_ref"],
                role=PlatformRole(body["role"]),
                active_tenant_ref=body.get("active_tenant_ref"),
            ),
            carrier_verdict=CarrierVerdict(body["carrier_check"]),
        )


class _AccessControl:
    def __init__(self, client: TestClient) -> None:
        self._client = client

    def decide(self, context: RequestContext, operation: Any, record_ref: Optional[str] = None) -> AuthorizationResult:
        response = self._client.post(
            "/decisions",
            headers=SERVICE_HEADERS,
            json={"context": context.model_dump(mode="json"), "operation": operation.value, "record_ref": record_ref},
        )
        if response.status_code != 200:
            return AuthorizationResult(allowed=False, denial_code="access_denied", resolved_domain=None)
        body = response.json()
        if body["decision"] != "allowed":
            return AuthorizationResult(allowed=False, denial_code=body.get("denial_code"), resolved_domain=None)
        domain = body.get("resolved_domain")
        return AuthorizationResult(True, None, DatabaseDomain(domain) if domain else None)


class _Routing:
    def __init__(self, client: TestClient) -> None:
        self._client = client
        self.resolutions: List[str] = []

    def resolve(self, context: RequestContext) -> RoutedTenant:
        self.resolutions.append(context.tenant_context or "<tenantless>")
        response = self._client.post(
            "/internal/routing/resolve", headers=SERVICE_HEADERS, json={"context": context.model_dump(mode="json")}
        )
        if response.status_code >= 400:
            body = response.json()
            raise AppError(response.status_code, ErrorCode(body["code"]))
        body = response.json()
        return RoutedTenant(tenant_ref=body["tenant_ref"], target_ref=body["target_ref"])


class _ControlRead:
    def __init__(self, client: TestClient) -> None:
        self._client = client

    def _get(self, path: str) -> Any:
        response = self._client.get(path, headers=SERVICE_HEADERS)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise tenant_unavailable()
        return response.json()

    def list_memberships(self, principal_ref: str) -> List[Dict[str, str]]:
        body = self._get("/internal/memberships/" + principal_ref)
        return [] if body is None else list(body["memberships"])

    def list_directory(self, directory: str) -> List[Dict[str, str]]:
        body = self._get("/internal/directories/" + directory + "/records")
        return [] if body is None else list(body["records"])

    def get_directory_record(self, directory: str, record_ref: str) -> Optional[Dict[str, str]]:
        return self._get("/internal/directories/" + directory + "/records/" + record_ref)


class _Domain:
    def __init__(self, client: TestClient) -> None:
        self._client = client

    def call(self, path: str, payload: Dict[str, Any]) -> Any:
        response = self._client.post(path, headers=SERVICE_HEADERS, json=payload)
        if response.status_code >= 400:
            body = response.json()
            raise AppError(response.status_code, ErrorCode(body["code"]))
        return response.json()


class _Audit:
    def __init__(self, client: TestClient) -> None:
        self._client = client
        self.emitted: List[Dict[str, Any]] = []

    def emit(self, **event: Any) -> None:
        self.emitted.append(event)
        self._client.post(
            "/audit/events",
            headers={"Authorization": "Bearer bff-audit-key"},
            json={
                "action": event["action"],
                "outcome": event["outcome"],
                "correlation_id": event["correlation_id"],
                "actor_ref": event["actor_ref"],
                "subject_ref": event.get("subject_ref"),
                "tenant_ref": event.get("tenant_ref"),
                "record_ref": event.get("record_ref"),
                "carrier_ref": event.get("carrier_ref"),
            },
        )


class Topology:
    """The whole backend, wired in one process, with real apps and in-memory storage."""

    def __init__(self) -> None:
        # Authentication — the real verifier over a fixed principal map.
        auth_main._service = AuthenticationService(StaticTokenVerifier.from_json(json.dumps(TOKENS)))  # type: ignore[attr-defined]

        # Access Control — the real policy engine over a fixed membership map. `p-stranger`
        # deliberately holds no membership anywhere.
        ac_main._memberships = StaticMemberships({"p-agent": {"acme"}, "p-zeta": {"zeta"}, "p-nova": {"nova"}})  # type: ignore[attr-defined]

        # Control Plane — seeded registry, memberships and directories.
        control_store = InMemoryControlStore()
        for tenant in ("acme", "zeta", "nova"):
            control_store.put_tenant(
                TenantDescriptor(
                    tenant_ref=tenant,
                    organization_ref="org-" + tenant,
                    lifecycle_state=TenantLifecycleState.ACTIVE,
                    expected_schema_version="1",
                    database_association_ref=SecretReference(store_ref="assoc/" + tenant, version="1"),
                )
            )
        control_store.put_membership("p-agent", "acme", PlatformRole.TENANT_AGENT)
        control_store.put_membership("p-zeta", "zeta", PlatformRole.TENANT_AGENT)
        control_store.put_directory_record(
            DirectoryKind.GLOBAL_STARTUP, DirectoryRecord(record_ref="gs-1", display_name="Alpha Corp")
        )
        control_store.put_directory_record(
            DirectoryKind.GLOBAL_INVESTOR, DirectoryRecord(record_ref="gi-1", display_name="Northwind Capital")
        )
        cp_main._store = control_store  # type: ignore[attr-defined]

        # Database Router — acme and zeta resolvable; nova is registered but its association
        # cannot be produced, which is the "missing mapping" case.
        # The enum, not the string. TenantRegistryEntry is a dataclass and does not coerce, and
        # the resolver compares with `is` — so a plain "ACTIVE" would silently read as not-ACTIVE
        # and every tenant would answer not-ready.
        active = TenantLifecycleState.ACTIVE
        registry = StaticTenantRegistry(
            {
                "acme": TenantRegistryEntry("acme", active, "1", "assoc/acme", "1"),
                "zeta": TenantRegistryEntry("zeta", active, "1", "assoc/zeta", "1"),
                "nova": TenantRegistryEntry("nova", active, "1", "assoc/nova", "1"),
            }
        )
        secrets = EnvironmentTenantSecretStore(
            env={_ACME_DSN_VAR: "postgresql://localhost/acme", _ZETA_DSN_VAR: "postgresql://localhost/zeta"}
        )
        dbr_main._resolver = TenantResolver(registry, secrets)  # type: ignore[attr-defined]
        dbr_main._allowlist = GrantAllowlist({"startups-key": "startups"})  # type: ignore[attr-defined]

        # Domain services — in-memory storage, tenant-partitioned.
        startups_main._repository = InMemoryStartupRepository()  # type: ignore[attr-defined]
        investors_main._repository = InMemoryInvestorRepository()  # type: ignore[attr-defined]
        deals_main._repository = InMemoryDealRepository()  # type: ignore[attr-defined]

        import_store = import_service.InMemoryImportStore()
        directory = import_service.StaticGlobalDirectory(
            {"gs-1": import_service.GlobalSourceRecord("gs-1", "Alpha Corp", {"industry": "robotics"})}
        )
        import_main._store = import_store  # type: ignore[attr-defined]
        import_main._service = import_service.ImportService(directory, import_store)  # type: ignore[attr-defined]

        # Lineage reads the same tenant partition the import wrote to, which is what it would
        # do in a real deployment: both are rows in one tenant database.
        lineage_main._repository = lineage_main.LineageRepository(import_store.lineage)  # type: ignore[attr-defined]

        # Audit.
        audit_main._credentials = CredentialDirectory.from_json(  # type: ignore[attr-defined]
            json.dumps({"bff-audit-key": {"emitter_ref": "bff", "scopes": ["audit:write"]},
                        "auditor-key": {"emitter_ref": "auditor", "scopes": ["audit:read:all"]}})
        )
        audit_main._sink = InMemoryAuditSink()  # type: ignore[attr-defined]

        def client(app: Any) -> TestClient:
            return TestClient(app, raise_server_exceptions=False)

        self.audit_client = client(audit_main.app)
        self.routing = _Routing(client(dbr_main.app))
        self.audit = _Audit(self.audit_client)

        self.pipeline = IngressPipeline(
            authentication=_Authentication(client(auth_main.app)),
            access_control=_AccessControl(client(ac_main.app)),
            routing=self.routing,
            audit=self.audit,
            base_domain="example.com",
        )
        self.control_read = _ControlRead(client(cp_main.app))
        self.domains = {
            "startups": _Domain(client(startups_main.app)),
            "investors": _Domain(client(investors_main.app)),
            "deals": _Domain(client(deals_main.app)),
            "import_service": _Domain(client(import_main.app)),
            "lineage": _Domain(client(lineage_main.app)),
        }

        bff = build_app("bff", description="end-to-end topology")
        bff.include_router(build_router(self.pipeline, self.control_read, self.domains))  # type: ignore[arg-type]
        self.bff = TestClient(bff, raise_server_exceptions=False)

    def as_(self, token: str) -> Dict[str, str]:
        return {"Authorization": "Bearer " + token}

    def audit_actions(self) -> List[str]:
        return [event["action"] for event in self.audit.emitted]


# --- The happy path ---------------------------------------------------------------------------

def test_a_complete_tenant_request_traverses_every_stage() -> None:
    topology = Topology()

    created = topology.bff.post(
        "/tenant/startups", headers=topology.as_("acme-agent"), json={"display_name": "Acme Robotics"}
    )
    assert created.status_code == 201, created.text
    record_ref = created.json()["record_ref"]
    assert record_ref.startswith("ref:acme:startups:")

    read = topology.bff.get("/tenant/startups/" + record_ref, headers=topology.as_("acme-agent"))
    assert read.status_code == 200
    body = read.json()

    # Exactly the eight contract-pinned fields, and nothing else.
    assert set(body) == {
        "record_ref",
        "display_name",
        "short_description",
        "investment_stage",
        "record_origin",
        "record_residency",
        "record_type",
        "lineage_reference",
    }
    assert body["display_name"] == "Acme Robotics"
    assert body["record_residency"] == "tenant"

    # The router was consulted for every tenant operation, and only ever for acme.
    assert topology.routing.resolutions == ["acme", "acme"]
    assert "tenant_startup_read" in topology.audit_actions()


def test_the_bounded_update_flows_end_to_end_and_emits_its_audit_class() -> None:
    topology = Topology()
    created = topology.bff.post("/tenant/startups", headers=topology.as_("acme-agent"), json={"display_name": "Acme"})
    record_ref = created.json()["record_ref"]

    updated = topology.bff.patch(
        "/tenant/startups/" + record_ref,
        headers=topology.as_("acme-agent"),
        json={"short_description": "Industrial robotics."},
    )
    assert updated.status_code == 200
    assert updated.json()["short_description"] == "Industrial robotics."
    assert "tenant_startup_update" in topology.audit_actions()


def test_memberships_emit_exactly_one_event_even_when_empty() -> None:
    """The event records the operation, not how many records it returned (IC-013 §10)."""
    topology = Topology()

    held = topology.bff.get("/memberships", headers=topology.as_("acme-agent"))
    assert held.status_code == 200
    assert held.json()["memberships"] == [
        {"tenant_id": "acme", "role": "TENANT_AGENT", "display_ref": "ref:tenant/acme/display"}
    ]

    topology.audit.emitted.clear()
    empty = topology.bff.get("/memberships", headers=topology.as_("nova-agent"))
    assert empty.status_code == 200
    assert empty.json()["memberships"] == []
    assert topology.audit_actions() == ["workspace_memberships_read"], "an empty enumeration is still an enumeration"


def test_the_global_directory_read_is_tenant_anonymous() -> None:
    topology = Topology()
    response = topology.bff.get("/directories/startups", headers=topology.as_("acme-agent"))
    assert response.status_code == 200
    body = response.json()
    assert body["record_residency"] == "global"
    assert body["records"] == [{"record_ref": "gs-1", "display_name": "Alpha Corp"}]
    for forbidden in ("tenant_id", "tenant_ref", "tenant_name", "lineage_reference", "acme"):
        assert forbidden not in response.text


def test_an_import_produces_a_tenant_copy_whose_lineage_is_readable_end_to_end() -> None:
    topology = Topology()
    imported = topology.bff.post("/import/startups/gs-1", headers=topology.as_("acme-agent"))
    assert imported.status_code == 201, imported.text
    body = imported.json()
    assert body["outcome"] == "created"
    assert body["target_tenant_ref"] == "acme"

    lineage = topology.bff.get("/tenant/records/" + body["tenant_record_ref"] + "/lineage", headers=topology.as_("acme-agent"))
    assert lineage.status_code == 200
    assert lineage.json()["source_references"] == ["gs-1"]

    replay = topology.bff.post("/import/startups/gs-1", headers=topology.as_("acme-agent"))
    assert replay.json()["outcome"] == "replayed"
    assert replay.json()["tenant_record_ref"] == body["tenant_record_ref"]


def test_a_deal_links_two_records_of_the_same_tenant() -> None:
    topology = Topology()
    startup = topology.bff.post("/tenant/startups", headers=topology.as_("acme-agent"), json={"display_name": "Acme"})
    investor = topology.bff.post(
        "/tenant/investors", headers=topology.as_("acme-agent"), json={"display_name": "Northwind"}
    )
    deal = topology.bff.post(
        "/tenant/deals",
        headers=topology.as_("acme-agent"),
        json={
            "deal_name": "Series A",
            "startup_ref": startup.json()["record_ref"],
            "investor_ref": investor.json()["record_ref"],
        },
    )
    assert deal.status_code == 201, deal.text
    assert deal.json()["startup_ref"] == startup.json()["record_ref"]


# --- The fail-closed cases (plan §3.6) -----------------------------------------------------------

def test_invalid_authentication_is_a_canonical_401_and_reaches_no_router() -> None:
    topology = Topology()
    response = topology.bff.get("/tenant/startups", headers=topology.as_("not-a-real-token"))
    assert response.status_code == 401
    assert response.json() == {"status": 401, "code": "unauthenticated"}
    assert topology.routing.resolutions == []


def test_a_missing_credential_is_a_canonical_401() -> None:
    topology = Topology()
    response = topology.bff.get("/tenant/startups")
    assert response.status_code == 401
    assert topology.routing.resolutions == []


def test_a_denied_authorization_never_reaches_the_router_and_is_audited() -> None:
    """`p-stranger` authenticates into acme but holds no membership anywhere."""
    topology = Topology()
    response = topology.bff.get("/tenant/startups", headers=topology.as_("stranger"))
    assert response.status_code == 403
    assert response.json() == {"status": 403, "code": "access_denied"}
    assert topology.routing.resolutions == [], "the router was contacted after a denial"
    assert topology.audit_actions() == ["RouteDenied"]


def test_a_wrong_tenant_carrier_is_rejected_before_any_routing() -> None:
    topology = Topology()
    response = topology.bff.get(
        "/tenant/startups", headers={**topology.as_("acme-agent"), "X-Tenant-Id": "zeta"}
    )
    assert response.status_code == 403
    assert response.json() == {"status": 403, "code": "carrier_mismatch"}
    assert topology.routing.resolutions == []
    assert topology.audit_actions() == ["CarrierMismatch"]


def test_a_matching_carrier_passes() -> None:
    topology = Topology()
    response = topology.bff.get("/tenant/startups", headers={**topology.as_("acme-agent"), "X-Tenant-Id": "acme"})
    assert response.status_code == 200


def test_a_carrier_on_a_control_principal_is_an_anomaly_and_the_carrier_is_ignored() -> None:
    topology = Topology()
    response = topology.bff.get("/memberships", headers={**topology.as_("control"), "X-Tenant-Id": "acme"})
    assert response.status_code == 200
    assert "CarrierOnControlAnomaly" in topology.audit_actions()
    # The carrier did not become the active tenant: a CONTROL principal has none, so the read
    # is self-scoped to a principal with no memberships.
    assert response.json()["memberships"] == []


def test_a_tenantless_control_principal_cannot_reach_a_tenant_operation() -> None:
    topology = Topology()
    response = topology.bff.get("/tenant/startups", headers=topology.as_("control"))
    assert response.status_code == 403
    assert topology.routing.resolutions == [], "a tenantless request reached the router"


def test_a_tenant_whose_association_cannot_be_produced_is_unavailable_not_redirected() -> None:
    """nova is ACTIVE and its principal is a member, but its association resolves to nothing.

    The request must fail as an outage of nova — never silently serve a different tenant, and
    never fall back to the Control database.
    """
    topology = Topology()
    response = topology.bff.get("/tenant/startups", headers=topology.as_("nova-agent"))
    assert response.status_code == 503
    assert response.json() == {"status": 503, "code": "tenant_unavailable"}


def test_one_principal_cannot_read_another_tenants_record() -> None:
    topology = Topology()
    created = topology.bff.post("/tenant/startups", headers=topology.as_("acme-agent"), json={"display_name": "Acme"})
    acme_ref = created.json()["record_ref"]

    # zeta-agent is a legitimate principal with a legitimate tenant. The record reference is
    # simply not theirs, and it is not found rather than refused in a way that confirms it exists.
    response = topology.bff.get("/tenant/startups/" + acme_ref, headers=topology.as_("zeta-agent"))
    assert response.status_code == 404


def test_two_tenants_records_never_appear_in_one_anothers_lists() -> None:
    topology = Topology()
    topology.bff.post("/tenant/startups", headers=topology.as_("acme-agent"), json={"display_name": "Acme Robotics"})
    topology.bff.post("/tenant/startups", headers=topology.as_("zeta-agent"), json={"display_name": "Zeta Systems"})

    acme = topology.bff.get("/tenant/startups", headers=topology.as_("acme-agent")).json()
    zeta = topology.bff.get("/tenant/startups", headers=topology.as_("zeta-agent")).json()

    assert [record["display_name"] for record in acme["records"]] == ["Acme Robotics"]
    assert [record["display_name"] for record in zeta["records"]] == ["Zeta Systems"]


def test_a_deal_cannot_be_created_across_tenants_end_to_end() -> None:
    topology = Topology()
    acme_startup = topology.bff.post(
        "/tenant/startups", headers=topology.as_("acme-agent"), json={"display_name": "Acme"}
    ).json()["record_ref"]

    response = topology.bff.post(
        "/tenant/deals",
        headers=topology.as_("zeta-agent"),
        json={"deal_name": "Cross-tenant", "startup_ref": acme_startup},
    )
    assert response.status_code == 422


# --- Audit lands durably ---------------------------------------------------------------------------

def test_ingress_audit_reaches_the_audit_service_with_a_server_derived_emitter() -> None:
    topology = Topology()
    topology.bff.get("/tenant/startups", headers=topology.as_("stranger"))

    stored = topology.audit_client.get("/audit/events", headers={"Authorization": "Bearer auditor-key"}).json()
    assert stored["events"], "the denial did not reach the audit sink"
    event = stored["events"][-1]
    assert event["action"] == "RouteDenied"
    assert event["source_service"] == "bff", "the emitter was not server-derived"
    assert event["actor_ref"] == "p-stranger"


def test_no_audit_record_carries_a_credential_or_a_connection_string() -> None:
    topology = Topology()
    topology.bff.get("/tenant/startups", headers={**topology.as_("acme-agent"), "X-Tenant-Id": "zeta"})
    topology.bff.get("/tenant/startups", headers=topology.as_("stranger"))

    raw = topology.audit_client.get("/audit/events", headers={"Authorization": "Bearer auditor-key"}).text
    for forbidden in ("postgresql://", "acme-agent", "stranger-token", "Bearer", "password", "assoc/"):
        assert forbidden not in raw, "an audit record disclosed " + forbidden
