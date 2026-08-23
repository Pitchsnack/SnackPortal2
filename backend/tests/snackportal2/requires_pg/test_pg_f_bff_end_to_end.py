"""Stage 4F — the mandatory real BFF-to-PostgreSQL end-to-end path.

Eleven services run as real uvicorn processes. Nothing is mocked and nothing is substituted:

    BFF -> Authentication -> RequestContext -> Access Control -> Database Router
        -> tenant-resident domain service -> real tenant PostgreSQL
        -> response -> Audit Service -> real Control PostgreSQL

The Access Control Service reads membership from the Control Plane over real HTTP, and the
Control Plane reads it from the real Control database — so an authorization decision in this
module genuinely depends on a row in PostgreSQL. Every production HTTP client the BFF composes
(``HttpAuthentication``, ``HttpAccessControl``, ``HttpTenantRouting``, ``HttpControlRead``,
``HttpDomainService``, ``HttpAudit``) executes here for the first time.

Stage 4E's physical-isolation proof lives here too, because the same fleet is what makes it
meaningful: the denials are measured at the databases with ``pg_stat_database.sessions``, so
"no tenant database was reached" is PostgreSQL's own count rather than an inference.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import httpx
import pytest

from snackportal2.services.bff.carrier import NON_CARRIER_HEADERS, TENANT_HEADER
from snackportal2.services.bff.dtos import compose_display_ref
from snackportal2.services.control_plane.models import SecretReference, TenantDescriptor
from snackportal2.services.control_plane.store import ENV_CONTROL_DSN, build_store
from snackportal2.services.database_router.resolver import EnvironmentTenantSecretStore
from snackportal2.shared.lineage_keys import EnvironmentLineageKeyResolver
from snackportal2.shared.types import PlatformRole, TenantLifecycleState

from . import _stage4_pg as pg
from . import _stage4_servers as srv

pytestmark = pytest.mark.skipif(not pg.configured(), reason=pg.SKIP_REASON)

BASE_DOMAIN = "snackportal2.example"

BFF_CREDENTIAL = "internal-bff-credential"
ROUTER_CREDENTIAL = "internal-router-credential"
ACCESS_CONTROL_CREDENTIAL = "internal-access-control-credential"
GRANT_CREDENTIALS = {
    "startups": "grant-startups",
    "investors": "grant-investors",
    "deals": "grant-deals",
    "lineage": "grant-lineage",
    "import_service": "grant-import",
}

#: A global directory record this module alone imports. Dedicated on purpose: the Stage 4D
#: module also imports ``gs-1`` into the same tenant databases, and a shared source would make
#: this module's "created" assertion depend on which module happened to run first.
E2E_SOURCE = "gs-ingress-import"

#: Per-tenant D-23 chain keys for the Import Service, so an import through the ingress writes
#: a real lineage row rather than being refused. Distinct per tenant; test material only.
LINEAGE_KEYS = {
    EnvironmentLineageKeyResolver.variable_name(tenant): "stage5-e2e-chain-key-" + tenant + "-" + ("0" * 16)
    for tenant in pg.TENANTS
}

#: Development-posture principals. The Authentication Service selects this verifier only on
#: explicit configuration; it is never reachable by omission.
PRINCIPALS = {
    "token-acme": {"principal_ref": "p-acme", "role": PlatformRole.TENANT_AGENT.value, "active_tenant": "acme"},
    "token-zeta": {"principal_ref": "p-zeta", "role": PlatformRole.TENANT_AGENT.value, "active_tenant": "zeta"},
    "token-nova": {"principal_ref": "p-nova", "role": PlatformRole.TENANT_AGENT.value, "active_tenant": "nova"},
    "token-stranger": {"principal_ref": "p-stranger", "role": PlatformRole.TENANT_AGENT.value, "active_tenant": "acme"},
    "token-offline": {"principal_ref": "p-offline", "role": PlatformRole.TENANT_AGENT.value, "active_tenant": "offline"},
    "token-ghost": {"principal_ref": "p-ghost", "role": PlatformRole.TENANT_AGENT.value, "active_tenant": "ghost"},
    "token-control": {"principal_ref": "p-control", "role": PlatformRole.CONTROL.value, "active_tenant": None},
}

AUDIT_CREDENTIALS = {
    BFF_CREDENTIAL: {"emitter_ref": "bff", "scopes": ["audit:write"]},
    "audit-reader": {"emitter_ref": "auditor", "scopes": ["audit:read:all"]},
}


def _dsn_variable(store_ref: str) -> str:
    return EnvironmentTenantSecretStore.variable_name(store_ref, "1")


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[srv.ServiceFleet]:
    pg.provision()

    store = build_store(env={ENV_CONTROL_DSN: pg.dsn("control")})
    for tenant in list(pg.TENANTS) + ["offline"]:
        store.put_tenant(
            TenantDescriptor(
                tenant_ref=tenant,
                organization_ref="org-" + tenant,
                lifecycle_state=TenantLifecycleState.ACTIVE,
                expected_schema_version="1",
                database_association_ref=SecretReference(store_ref="assoc/" + tenant, version="1"),
            )
        )
    # Membership lives in the Control database and is what Access Control actually reads.
    # ``p-stranger`` deliberately holds none, so its denial is a real database answer.
    store.put_membership("p-acme", "acme", PlatformRole.TENANT_AGENT)
    store.put_membership("p-zeta", "zeta", PlatformRole.TENANT_AGENT)
    store.put_membership("p-nova", "nova", PlatformRole.TENANT_AGENT)
    store.put_membership("p-offline", "offline", PlatformRole.TENANT_AGENT)

    for record_ref, name in (("gs-1", "Alpha Corp"), ("gs-2", "Beta Systems"), (E2E_SOURCE, "Ingress Import Corp")):
        pg.execute(
            pg.dsn("control"),
            "INSERT INTO control_directory (directory, record_id, display_name, attributes) "
            "VALUES ('GlobalStartupDirectory', %s, %s, '{}'::jsonb) ON CONFLICT DO NOTHING",
            (record_ref, name),
        )
    pg.execute(
        pg.dsn("control"),
        "INSERT INTO control_directory (directory, record_id, display_name, attributes) "
        "VALUES ('GlobalInvestorDirectory', 'gi-1', 'Northwind Capital', '{}'::jsonb) ON CONFLICT DO NOTHING",
    )

    log_dir: Path = tmp_path_factory.mktemp("stage4f-logs")
    running = srv.ServiceFleet(log_dir)
    try:
        control = running.start("control_plane", {"SP2_CONTROL_PLANE_DSN": pg.dsn("control")})
        authentication = running.start(
            "authentication", {"SP2_AUTHENTICATION_STATIC_PRINCIPALS": json.dumps(PRINCIPALS)}
        )
        access_control = running.start(
            "access_control",
            {
                "SP2_ACCESS_CONTROL_CONTROL_PLANE_URL": control.base_url,
                "SP2_ACCESS_CONTROL_SERVICE_CREDENTIAL": ACCESS_CONTROL_CREDENTIAL,
            },
        )
        audit = running.start(
            "audit", {"SP2_AUDIT_DSN": pg.dsn("control"), "SP2_AUDIT_CREDENTIALS": json.dumps(AUDIT_CREDENTIALS)}
        )

        unreachable = "postgresql://absent@127.0.0.1:" + str(srv.free_port()) + "/sp2_offline"
        router = running.start(
            "database_router",
            {
                "SP2_DATABASE_ROUTER_CONTROL_PLANE_URL": control.base_url,
                "SP2_DATABASE_ROUTER_SERVICE_CREDENTIAL": ROUTER_CREDENTIAL,
                # The BFF's own credential is deliberately NOT here (D-48 C-1).
                "SP2_DATABASE_ROUTER_GRANTEES": json.dumps(
                    {credential: service for service, credential in GRANT_CREDENTIALS.items()}
                ),
                **{_dsn_variable("assoc/" + tenant): pg.dsn(tenant) for tenant in pg.TENANTS},
                _dsn_variable("assoc/offline"): unreachable,
            },
        )

        domain_urls: Dict[str, str] = {}
        for service in ("startups", "investors", "deals", "lineage"):
            process = running.start(
                service,
                {
                    "SP2_" + service.upper() + "_STORAGE": "postgres",
                    "SP2_" + service.upper() + "_DATABASE_ROUTER_URL": router.base_url,
                    "SP2_" + service.upper() + "_SERVICE_CREDENTIAL": GRANT_CREDENTIALS[service],
                },
            )
            domain_urls[service] = process.base_url
        import_process = running.start(
            "import_service",
            {
                "SP2_IMPORT_SERVICE_CONTROL_PLANE_URL": control.base_url,
                "SP2_IMPORT_SERVICE_SERVICE_CREDENTIAL": GRANT_CREDENTIALS["import_service"],
                "SP2_IMPORT_SERVICE_STORAGE": "postgres",
                "SP2_IMPORT_SERVICE_DATABASE_ROUTER_URL": router.base_url,
                **LINEAGE_KEYS,
            },
        )

        running.start(
            "bff",
            {
                "SP2_BFF_AUTHENTICATION_URL": authentication.base_url,
                "SP2_BFF_ACCESS_CONTROL_URL": access_control.base_url,
                "SP2_BFF_DATABASE_ROUTER_URL": router.base_url,
                "SP2_BFF_CONTROL_PLANE_URL": control.base_url,
                "SP2_BFF_AUDIT_URL": audit.base_url,
                "SP2_BFF_SERVICE_CREDENTIAL": BFF_CREDENTIAL,
                "SP2_BFF_BASE_DOMAIN": BASE_DOMAIN,
                "SP2_BFF_STARTUPS_URL": domain_urls["startups"],
                "SP2_BFF_INVESTORS_URL": domain_urls["investors"],
                "SP2_BFF_DEALS_URL": domain_urls["deals"],
                "SP2_BFF_LINEAGE_URL": domain_urls["lineage"],
                "SP2_BFF_IMPORT_SERVICE_URL": import_process.base_url,
            },
        )
        yield running
    finally:
        running.stop()


def _as(token: Optional[str], carrier: Optional[str] = None, host: Optional[str] = None) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    if carrier is not None:
        # ``X-Tenant-Id`` is the one recognized header carrier (IC-013 §5).
        headers[TENANT_HEADER] = carrier
    if host is not None:
        headers["Host"] = host
    return headers


def _get(stack: srv.ServiceFleet, path: str, token: Optional[str], **kwargs: Any) -> httpx.Response:
    headers = _as(token, kwargs.pop("carrier", None), kwargs.pop("host", None))
    headers.update(kwargs.pop("extra_headers", {}))
    return httpx.get(stack.url("bff") + path, headers=headers, timeout=30.0, **kwargs)


def _post(stack: srv.ServiceFleet, path: str, token: Optional[str], body: Any = None, **kwargs: Any) -> httpx.Response:
    headers = _as(token, kwargs.pop("carrier", None), kwargs.pop("host", None))
    headers.update(kwargs.pop("extra_headers", {}))
    return httpx.post(stack.url("bff") + path, headers=headers, json=body, timeout=30.0, **kwargs)


def _audit_events(stack: srv.ServiceFleet, **params: Any) -> List[Dict[str, Any]]:
    response = httpx.get(
        stack.url("audit") + "/audit/events",
        headers={"Authorization": "Bearer audit-reader"},
        params={"limit": 500, **params},
        timeout=30.0,
    )
    assert response.status_code == 200, response.text
    return list(response.json()["events"])


# --- the happy path, every hop real -------------------------------------------------------


def test_a_complete_tenant_write_and_read_traverses_every_stage_to_postgresql(stack: srv.ServiceFleet) -> None:
    created = _post(
        stack, "/tenant/startups", "token-acme", {"display_name": "Endgame Robotics", "short_description": "Pickers."}
    )
    assert created.status_code == 201, created.text
    record_ref = created.json()["record_ref"]
    assert record_ref.startswith("ref:acme:startups:")

    # The row is physically in the ACME database, and in no other.
    assert pg.scalar(pg.dsn("acme"), "SELECT count(*) FROM startups WHERE company_name = 'Endgame Robotics'") == 1
    for other in ("zeta", "nova"):
        assert pg.scalar(pg.dsn(other), "SELECT count(*) FROM startups WHERE company_name = 'Endgame Robotics'") == 0

    read = _get(stack, "/tenant/startups/" + record_ref, "token-acme")
    assert read.status_code == 200, read.text
    body = read.json()
    assert set(body) == {
        "record_ref",
        "display_name",
        "short_description",
        "investment_stage",
        "record_origin",
        "record_residency",
        "record_type",
        "lineage_reference",
    }, "the BFF returned something other than the contract-pinned shape"
    assert body["display_name"] == "Endgame Robotics"
    assert body["record_origin"] == "tenant"


def test_the_success_read_is_audited_into_the_real_control_database(stack: srv.ServiceFleet) -> None:
    created = _post(stack, "/tenant/startups", "token-acme", {"display_name": "Audited Co"})
    record_ref = created.json()["record_ref"]
    before = pg.scalar(pg.dsn("control"), "SELECT count(*) FROM control_ingress_audit")

    assert _get(stack, "/tenant/startups/" + record_ref, "token-acme").status_code == 200

    after = pg.scalar(pg.dsn("control"), "SELECT count(*) FROM control_ingress_audit")
    assert after == before + 1, "the successful read emitted no audit event"

    stored = pg.rows(
        pg.dsn("control"),
        "SELECT source_service, action, outcome, actor_ref, tenant_ref, record_ref FROM control_ingress_audit "
        "WHERE record_ref = %s ORDER BY id DESC LIMIT 1",
        (record_ref,),
    )
    assert stored == [("bff", "tenant_startup_read", "allowed", "p-acme", "acme", record_ref)]


def test_the_update_operation_writes_through_to_postgresql_and_is_audited(stack: srv.ServiceFleet) -> None:
    created = _post(stack, "/tenant/startups", "token-acme", {"display_name": "Patchable Ltd"})
    record_ref = created.json()["record_ref"]

    patched = httpx.patch(
        stack.url("bff") + "/tenant/startups/" + record_ref,
        headers=_as("token-acme"),
        json={"short_description": "revised"},
        timeout=30.0,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["short_description"] == "revised"
    assert pg.scalar(pg.dsn("acme"), "SELECT short_description FROM startups WHERE company_name = 'Patchable Ltd'") == "revised"

    actions = [event["action"] for event in _audit_events(stack, tenant_ref="acme")]
    assert "tenant_startup_update" in actions


def test_a_control_domain_read_serves_from_the_control_database(stack: srv.ServiceFleet) -> None:
    response = _get(stack, "/memberships", "token-acme")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "memberships": [{"tenant_id": "acme", "role": "TENANT_AGENT", "display_ref": compose_display_ref("acme")}]
    }

    directory = _get(stack, "/directories/startups", "token-control")
    assert directory.status_code == 200, directory.text
    records = [entry["record_ref"] for entry in directory.json()["records"]]

    # Containment plus order, not equality: the Stage 4D module seeds its own records into the
    # same Control directory, so the exact contents depend on which modules ran. What must hold
    # regardless is that every record this module seeded is served, and that the BFF passes the
    # Control Plane's ``ORDER BY record_id`` through without re-sorting it.
    assert {"gs-1", "gs-2", E2E_SOURCE} <= set(records), records
    assert records == sorted(records), "the BFF re-ordered the Control Plane's directory listing"


def test_investors_and_deals_traverse_the_same_path_to_the_same_tenant_database(stack: srv.ServiceFleet) -> None:
    investor = _post(
        stack,
        "/tenant/investors",
        "token-nova",
        {"display_name": "Nova Capital", "industry_focus": ["robotics"], "investment_stage_focus": ["seed"]},
    )
    assert investor.status_code == 201, investor.text
    startup = _post(stack, "/tenant/startups", "token-nova", {"display_name": "Nova Target"})
    assert startup.status_code == 201, startup.text

    deal = _post(
        stack,
        "/tenant/deals",
        "token-nova",
        {
            "deal_name": "Nova Round",
            "startup_ref": startup.json()["record_ref"],
            "investor_ref": investor.json()["record_ref"],
            "stage": "term_sheet",
            "amount": "2500000",
            "currency": "USD",
        },
    )
    assert deal.status_code == 201, deal.text
    assert pg.scalar(pg.dsn("nova"), "SELECT count(*) FROM deals WHERE deal_name = 'Nova Round'") == 1
    assert pg.rows(pg.dsn("nova"), "SELECT investment_stage_focus FROM investors WHERE investor_name = 'Nova Capital'") == [
        (["seed"],)
    ]

    listed = _get(stack, "/tenant/deals", "token-nova")
    assert listed.status_code == 200
    assert "Nova Round" in [record["deal_name"] for record in listed.json()["records"]]


# --- §8 fail-closed cases, measured at the databases --------------------------------------


def _tenant_sessions_unchanged(watch: pg.SessionWatch, baseline: Dict[str, int]) -> None:
    delta = watch.delta_since(baseline)
    tenant_delta = {name: count for name, count in delta.items() if name != "control"}
    assert all(count == 0 for count in tenant_delta.values()), "a denied request opened a tenant session: " + repr(tenant_delta)


def test_an_invalid_credential_is_401_and_reaches_no_tenant_database(stack: srv.ServiceFleet) -> None:
    with pg.SessionWatch(["control", *pg.TENANTS]) as watch:
        baseline = watch.snapshot()
        for headers in (
            {},  # no credential at all
            {"Authorization": "Bearer token-forged"},  # a credential no principal maps to
            {"Authorization": "Basic dXNlcjpwYXNz"},  # a scheme this ingress does not accept
            {"Authorization": "token-acme"},  # a valid token presented without a scheme
        ):
            response = _get(stack, "/tenant/startups", None, extra_headers=headers)
            assert response.status_code == 401, repr(headers) + " -> " + response.text
            assert response.json() == {"status": 401, "code": "unauthenticated"}
        _tenant_sessions_unchanged(watch, baseline)


def test_an_authorization_denial_is_403_and_reaches_no_tenant_database(stack: srv.ServiceFleet) -> None:
    """``p-stranger`` authenticates into ACME but holds no membership row in Control.

    Access Control reads that absence out of PostgreSQL, so this denial genuinely depends on
    the database — and it happens before routing, which is why no tenant session appears.
    """
    with pg.SessionWatch(["control", *pg.TENANTS]) as watch:
        baseline = watch.snapshot()
        response = _get(stack, "/tenant/startups", "token-stranger")
        assert response.status_code == 403, response.text
        assert response.json() == {"status": 403, "code": "access_denied"}
        _tenant_sessions_unchanged(watch, baseline)

    denials = [event for event in _audit_events(stack) if event["action"] == "RouteDenied"]
    assert any(event["actor_ref"] == "p-stranger" for event in denials), "the denial was not audited"


def test_a_control_principal_is_denied_every_tenant_operation(stack: srv.ServiceFleet) -> None:
    """CONTROL holds a tenantless token and no tenant-record permission at all (IC-009 §C)."""
    with pg.SessionWatch(["control", *pg.TENANTS]) as watch:
        baseline = watch.snapshot()
        for path in ("/tenant/startups", "/tenant/investors", "/tenant/deals"):
            response = _get(stack, path, "token-control")
            assert response.status_code == 403, path + " -> " + response.text
        _tenant_sessions_unchanged(watch, baseline)


def test_a_mismatched_tenant_carrier_is_denied_before_routing(stack: srv.ServiceFleet) -> None:
    """The carrier is validated pre-context and pre-routing (IC-013 §5)."""
    with pg.SessionWatch(["control", *pg.TENANTS]) as watch:
        baseline = watch.snapshot()
        response = _get(stack, "/tenant/startups", "token-acme", carrier="zeta")
        assert response.status_code == 403, response.text
        assert response.json() == {"status": 403, "code": "carrier_mismatch"}
        _tenant_sessions_unchanged(watch, baseline)

    mismatches = [event for event in _audit_events(stack) if event["action"] == "CarrierMismatch"]
    assert mismatches, "the carrier mismatch was not audited"
    assert all(event["outcome"] == "denied" for event in mismatches)


def test_a_matching_tenant_carrier_is_accepted(stack: srv.ServiceFleet) -> None:
    assert _get(stack, "/tenant/startups", "token-acme", carrier="acme").status_code == 200


def test_a_subdomain_carrier_is_recognized_and_a_disagreeing_pair_is_a_conflict(stack: srv.ServiceFleet) -> None:
    """The second recognized carrier is the tenant subdomain, under the configured base domain."""
    assert _get(stack, "/tenant/startups", "token-acme", host="acme." + BASE_DOMAIN).status_code == 200

    wrong_subdomain = _get(stack, "/tenant/startups", "token-acme", host="zeta." + BASE_DOMAIN)
    assert wrong_subdomain.status_code == 403
    assert wrong_subdomain.json()["code"] == "carrier_mismatch"

    # Two recognized carriers that disagree is a conflict, resolved by neither.
    conflicting = _get(stack, "/tenant/startups", "token-acme", carrier="acme", host="zeta." + BASE_DOMAIN)
    assert conflicting.status_code == 403
    assert conflicting.json()["code"] == "carrier_mismatch"


def test_a_tenant_shaped_header_that_is_not_a_carrier_is_ignored(stack: srv.ServiceFleet) -> None:
    """The prohibited channels are ignored, not honoured and not rejected (IC-013 §5).

    If any of these were read as a carrier, ``zeta`` against an ACME claim would produce a
    mismatch. A 200 is the proof that none of them is a routing authority.
    """
    for header in NON_CARRIER_HEADERS:
        if header.casefold() == TENANT_HEADER.casefold():
            continue
        response = _get(stack, "/tenant/startups", "token-acme", extra_headers={header: "zeta"})
        assert response.status_code == 200, header + " was treated as a tenant carrier"


def test_an_unknown_tenant_claim_fails_closed_without_disclosing_whether_it_exists(
    stack: srv.ServiceFleet,
) -> None:
    with pg.SessionWatch(["control", *pg.TENANTS]) as watch:
        baseline = watch.snapshot()
        response = _get(stack, "/tenant/startups", "token-ghost")
        assert response.status_code in (403, 404), response.text
        assert set(response.json()) == {"status", "code"}
        _tenant_sessions_unchanged(watch, baseline)


def test_an_unavailable_tenant_database_answers_canonically_and_never_falls_back_to_control(
    stack: srv.ServiceFleet,
) -> None:
    """The single most important failure in the whole architecture.

    ``offline`` is ACTIVE, its principal is a member, and its association resolves — to a
    database that is not there. The correct answer is 503 for *that* tenant, and under no
    circumstances a read served from the Control database.
    """
    control_startups_exist = "startups" in pg.table_names(pg.dsn("control"))
    assert not control_startups_exist, "the Control database holds a tenant business table"

    with pg.SessionWatch(["control", *pg.TENANTS]) as watch:
        baseline = watch.snapshot()
        response = _get(stack, "/tenant/startups", "token-offline")
        assert response.status_code == 503, response.text
        assert response.json() == {"status": 503, "code": "tenant_unavailable"}
        # No *other* tenant was served in its place either.
        _tenant_sessions_unchanged(watch, baseline)


def test_a_cross_tenant_record_read_is_not_visible_through_the_ingress(stack: srv.ServiceFleet) -> None:
    zeta_record = _post(stack, "/tenant/startups", "token-zeta", {"display_name": "Zeta Confidential"})
    assert zeta_record.status_code == 201, zeta_record.text
    record_ref = zeta_record.json()["record_ref"]

    stolen = _get(stack, "/tenant/startups/" + record_ref, "token-acme")
    assert stolen.status_code == 404, stolen.text
    assert "Zeta Confidential" not in stolen.text

    # Physical absence, not merely a filtered answer.
    assert pg.scalar(pg.dsn("acme"), "SELECT count(*) FROM startups WHERE company_name = 'Zeta Confidential'") == 0
    assert pg.scalar(pg.dsn("zeta"), "SELECT count(*) FROM startups WHERE company_name = 'Zeta Confidential'") == 1


def test_a_cross_tenant_deal_is_refused_at_the_owning_service(stack: srv.ServiceFleet) -> None:
    acme_startup = _post(stack, "/tenant/startups", "token-acme", {"display_name": "Acme Crossing"})
    response = _post(
        stack,
        "/tenant/deals",
        "token-zeta",
        {"deal_name": "Illegal Crossing", "startup_ref": acme_startup.json()["record_ref"]},
    )
    assert response.status_code == 422, response.text
    for tenant in pg.TENANTS:
        assert pg.scalar(pg.dsn(tenant), "SELECT count(*) FROM deals WHERE deal_name = 'Illegal Crossing'") == 0


# --- Stage 4E: physical isolation, measured ------------------------------------------------


def test_each_tenants_request_opens_a_session_only_on_its_own_database(stack: srv.ServiceFleet) -> None:
    """§7's central claim, observed from inside each cluster.

    Three requests, one per tenant, each measured separately. The tenant whose request it is
    gains sessions; the other two gain none. This is the difference between a service that
    filters correctly and a system that is physically isolated.
    """
    for tenant, token in (("acme", "token-acme"), ("zeta", "token-zeta"), ("nova", "token-nova")):
        with pg.SessionWatch(["control", *pg.TENANTS]) as watch:
            baseline = watch.snapshot()
            response = _get(stack, "/tenant/startups", token)
            assert response.status_code == 200, response.text
            delta = watch.delta_since(baseline)

        assert delta[tenant] > 0, tenant + " request opened no session on its own database"
        for other in pg.TENANTS:
            if other != tenant:
                assert delta[other] == 0, tenant + " request opened a session on " + other


def test_seeded_records_are_physically_absent_from_every_other_tenant_database(stack: srv.ServiceFleet) -> None:
    markers = {"acme": "ISO-ACME", "zeta": "ISO-ZETA", "nova": "ISO-NOVA"}
    tokens = {"acme": "token-acme", "zeta": "token-zeta", "nova": "token-nova"}

    for tenant, marker in markers.items():
        assert _post(stack, "/tenant/startups", tokens[tenant], {"display_name": marker}).status_code == 201

    for tenant, marker in markers.items():
        for database in pg.TENANTS:
            expected = 1 if database == tenant else 0
            found = pg.scalar(pg.dsn(database), "SELECT count(*) FROM startups WHERE company_name = %s", (marker,))
            assert found == expected, marker + " appears " + str(found) + " time(s) in " + database

    # And no tenant marker reached the Control database, which has no such table to hold it.
    assert "startups" not in pg.table_names(pg.dsn("control"))


def test_a_tenant_listing_returns_only_its_own_records(stack: srv.ServiceFleet) -> None:
    names = {}
    for tenant, token in (("acme", "token-acme"), ("zeta", "token-zeta"), ("nova", "token-nova")):
        response = _get(stack, "/tenant/startups", token, params={"limit": 500})
        assert response.status_code == 200, response.text
        names[tenant] = {record["display_name"] for record in response.json()["records"]}

    assert "ISO-ACME" in names["acme"] and "ISO-ACME" not in names["zeta"] and "ISO-ACME" not in names["nova"]
    assert "ISO-ZETA" in names["zeta"] and "ISO-ZETA" not in names["acme"]
    assert "ISO-NOVA" in names["nova"] and "ISO-NOVA" not in names["acme"]


# --- Import through the ingress, into real tenant PostgreSQL (Stage 5) ----------------------


def test_an_import_through_the_ingress_writes_the_copy_and_its_lineage_to_the_tenant_database(
    stack: srv.ServiceFleet,
) -> None:
    """The whole path, end to end, with nothing substituted.

        client token -> BFF -> Authentication -> Access Control -> Import Service
                     -> Database Router grant -> ACME PostgreSQL (copy + lineage + idempotency)

    Before Stage 5 this request answered 201 and wrote nothing at all.
    """
    with pg.SessionWatch(pg.TENANTS) as watch:
        baseline = watch.snapshot()
        response = _post(stack, "/import/startups/" + E2E_SOURCE, "token-acme")
        delta = watch.delta_since(baseline)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["outcome"] == "created"
    assert body["source_ref"] == E2E_SOURCE

    copy = pg.rows(
        pg.dsn("acme"),
        "SELECT id, company_name FROM startups WHERE global_startup_id = %s",
        (E2E_SOURCE,),
    )
    assert len(copy) == 1, "the ingress import wrote no tenant row"
    assert copy[0][1] == "Ingress Import Corp"
    assert body["tenant_record_ref"] == "ref:acme:startups:" + str(copy[0][0])

    chain = pg.rows(
        pg.dsn("acme"),
        "SELECT lineage_id, event_type, actor_ref, target_ref, length(integrity_marker) FROM lineage "
        "WHERE source_ref = %s",
        (E2E_SOURCE,),
    )
    assert len(chain) == 1, "the ingress import wrote no lineage row"
    assert chain[0][1] == "import"
    assert chain[0][2] == "p-acme", "the lineage row did not record the authenticated principal"
    assert chain[0][3] == body["tenant_record_ref"]
    assert chain[0][4] == 64, "the lineage row carries no real D-23 marker"
    assert body["lineage_ref"] == "ref:acme:lineage:" + str(chain[0][0])

    # Written into exactly one tenant database, and no other.
    assert delta["acme"] > 0
    assert delta["zeta"] == 0 and delta["nova"] == 0, delta
    for other in ("zeta", "nova"):
        assert pg.scalar(pg.dsn(other), "SELECT count(*) FROM startups WHERE global_startup_id = %s", (E2E_SOURCE,)) == 0
        assert pg.scalar(pg.dsn(other), "SELECT count(*) FROM lineage WHERE source_ref = %s", (E2E_SOURCE,)) == 0


def test_a_repeated_ingress_import_replays_and_writes_no_second_row(stack: srv.ServiceFleet) -> None:
    counted = "SELECT count(*) FROM startups WHERE global_startup_id = %s"
    chained = "SELECT count(*) FROM lineage WHERE source_ref = %s"
    before = (pg.scalar(pg.dsn("acme"), counted, (E2E_SOURCE,)), pg.scalar(pg.dsn("acme"), chained, (E2E_SOURCE,)))

    response = _post(stack, "/import/startups/" + E2E_SOURCE, "token-acme")
    assert response.status_code == 201, response.text
    assert response.json()["outcome"] == "replayed"
    assert (pg.scalar(pg.dsn("acme"), counted, (E2E_SOURCE,)), pg.scalar(pg.dsn("acme"), chained, (E2E_SOURCE,))) == before


def test_the_same_global_record_imported_by_two_tenants_stays_physically_separate(
    stack: srv.ServiceFleet,
) -> None:
    acme = _post(stack, "/import/startups/gs-2", "token-acme")
    zeta = _post(stack, "/import/startups/gs-2", "token-zeta")
    assert acme.status_code == 201 and zeta.status_code == 201, (acme.text, zeta.text)
    assert acme.json()["import_id"] != zeta.json()["import_id"]

    for tenant in ("acme", "zeta"):
        assert pg.scalar(pg.dsn(tenant), "SELECT count(*) FROM startups WHERE global_startup_id = 'gs-2'") == 1
    assert pg.scalar(pg.dsn("nova"), "SELECT count(*) FROM startups WHERE global_startup_id = 'gs-2'") == 0

    # The two lineage rows are genuinely different rows in genuinely different databases.
    acme_id = pg.scalar(pg.dsn("acme"), "SELECT lineage_id FROM lineage WHERE source_ref = 'gs-2'")
    assert pg.scalar(pg.dsn("zeta"), "SELECT count(*) FROM lineage WHERE lineage_id = %s", (acme_id,)) == 0


def test_an_import_by_a_principal_without_membership_is_denied_before_any_write(
    stack: srv.ServiceFleet,
) -> None:
    """Access Control runs before tenant routing, so a denial reaches no tenant database."""
    with pg.SessionWatch(pg.TENANTS) as watch:
        baseline = watch.snapshot()
        response = _post(stack, "/import/startups/gs-2", "token-stranger")
        _tenant_sessions_unchanged(watch, baseline)
    assert response.status_code == 403, response.text
    assert response.json() == {"status": 403, "code": "access_denied"}
    assert pg.scalar(pg.dsn("acme"), "SELECT count(*) FROM import_idempotency WHERE status = 'failed'") == 0


def test_no_ingress_import_response_discloses_a_chain_key(stack: srv.ServiceFleet) -> None:
    bodies = [
        _post(stack, "/import/startups/" + E2E_SOURCE, "token-acme").text,
        _post(stack, "/import/startups/gs-absent", "token-acme").text,
        _post(stack, "/import/startups/gs-2", "token-stranger").text,
    ]
    logs = stack.all_logs()
    for key_value in LINEAGE_KEYS.values():
        for body in bodies:
            assert key_value not in body, "an import response disclosed a chain key"
        for name, text in logs.items():
            assert key_value not in text, name + " logged a chain key"


# --- D-48 at the ingress -------------------------------------------------------------------


def test_the_bff_credential_cannot_obtain_a_tenant_connection_grant(stack: srv.ServiceFleet) -> None:
    """D-48 C-1 from the ingress's own position, using the credential it really holds."""
    response = httpx.post(
        stack.url("database_router") + "/internal/routing/bind",
        headers={"Authorization": "Bearer " + BFF_CREDENTIAL},
        json={"tenant_ref": "acme"},
        timeout=30.0,
    )
    assert response.status_code == 403, response.text

    grantees = httpx.get(
        stack.url("database_router") + "/internal/routing/grantees",
        headers={"Authorization": "Bearer " + ROUTER_CREDENTIAL},
        timeout=30.0,
    ).json()["grantees"]
    listed = {entry["service_ref"] for entry in grantees}
    assert "bff" not in listed and "access_control" not in listed
    assert listed == set(GRANT_CREDENTIALS)


def test_the_access_control_credential_cannot_obtain_a_tenant_connection_grant(stack: srv.ServiceFleet) -> None:
    response = httpx.post(
        stack.url("database_router") + "/internal/routing/bind",
        headers={"Authorization": "Bearer " + ACCESS_CONTROL_CREDENTIAL},
        json={"tenant_ref": "acme"},
        timeout=30.0,
    )
    assert response.status_code == 403, response.text


def test_the_ingress_opens_no_database_session_of_its_own(stack: srv.ServiceFleet) -> None:
    """The BFF holds no connection: a Control-domain read touches Control through a service.

    Measured on the *tenant* clusters, where the BFF has no business at all — a Control-domain
    operation must produce no tenant session anywhere.
    """
    with pg.SessionWatch(list(pg.TENANTS)) as watch:
        baseline = watch.snapshot()
        assert _get(stack, "/memberships", "token-acme").status_code == 200
        assert _get(stack, "/directories/startups", "token-control").status_code == 200
        delta = watch.delta_since(baseline)
    assert all(count == 0 for count in delta.values()), "a Control-domain operation opened a tenant session: " + repr(delta)


# --- disclosure ------------------------------------------------------------------------------


def test_no_ingress_response_or_service_log_discloses_a_connection_string(stack: srv.ServiceFleet) -> None:
    fragments = srv.dsn_secret_fragments()
    assert fragments

    bodies = [
        _get(stack, "/tenant/startups", "token-acme").text,
        _get(stack, "/tenant/startups", "token-offline").text,
        _get(stack, "/tenant/startups", "token-stranger").text,
        _get(stack, "/memberships", "token-acme").text,
        _get(stack, "/health", None).text,
        _get(stack, "/readiness", None).text,
        httpx.get(stack.url("bff") + "/openapi.json", timeout=30.0).text,
        json.dumps(_audit_events(stack)),
    ]
    for body in bodies:
        for fragment in fragments:
            assert fragment not in body, "an ingress response disclosed a DSN fragment"

    for key, text in stack.all_logs().items():
        for fragment in fragments:
            assert fragment not in text, key + " logged a DSN fragment"


def test_no_ingress_response_discloses_a_service_credential(stack: srv.ServiceFleet) -> None:
    secrets = [BFF_CREDENTIAL, ROUTER_CREDENTIAL, ACCESS_CONTROL_CREDENTIAL, *GRANT_CREDENTIALS.values(), *PRINCIPALS]
    bodies = [
        _get(stack, "/tenant/startups", "token-acme").text,
        _get(stack, "/tenant/startups", "token-forged").text,
        httpx.get(stack.url("bff") + "/openapi.json", timeout=30.0).text,
        json.dumps(_audit_events(stack)),
    ]
    for body in bodies:
        for secret in secrets:
            assert secret not in body, "a credential appeared in an ingress response"


def test_the_audit_trail_carries_references_only(stack: srv.ServiceFleet) -> None:
    """Every stored audit row must be references, codes and timestamps — never content."""
    _post(stack, "/tenant/startups", "token-acme", {"display_name": "Audit Content Probe"})
    text = json.dumps(_audit_events(stack))
    assert "Audit Content Probe" not in text, "an audit record carried business field content"
    for event in _audit_events(stack):
        assert set(event) == {
            "event_id",
            "occurred_at",
            "source_service",
            "action",
            "outcome",
            "correlation_id",
            "actor_ref",
            "subject_ref",
            "tenant_ref",
            "record_ref",
            "carrier_ref",
        }
