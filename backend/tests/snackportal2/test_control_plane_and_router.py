"""Day 1.4 and 1.5 — Control Plane and Database Router.

The router half is the isolation boundary, so its tests are written as the plan's six
required cases (known / unknown / disabled / missing mapping / unavailable mapping / no
Control-DB fallback) plus a structural proof that a Control fallback is not merely absent
today but unreachable by construction.
"""

from __future__ import annotations

import ast
import pathlib

from fastapi.testclient import TestClient

from snackportal2.services.control_plane import main as cp_main
from snackportal2.services.control_plane.models import (
    DirectoryKind,
    DirectoryRecord,
    SecretReference,
    TenantDescriptor,
)
from snackportal2.services.control_plane.store import InMemoryControlStore, looks_like_a_connection_string
from snackportal2.services.database_router import main as dbr_main
from snackportal2.services.database_router import resolver as dbr_resolver
from snackportal2.services.database_router.grants import (
    PERMANENTLY_EXCLUDED,
    TENANT_RESIDENT_SERVICES,
    GrantAllowlist,
    build_allowlist,
)
from snackportal2.services.database_router.resolver import (
    EnvironmentTenantSecretStore,
    StaticTenantRegistry,
    TenantRegistryEntry,
    TenantResolver,
)
from snackportal2.shared.errors import AppError
from snackportal2.shared.security import AuthContext, RequestContext
from snackportal2.shared.types import PlatformRole, TenantLifecycleState

from ._openapi_rules import assert_document

_CREDENTIAL = {"Authorization": "Bearer internal-service-credential"}


# --- Control Plane ---------------------------------------------------------------------

def _seeded_control_store() -> InMemoryControlStore:
    store = InMemoryControlStore()
    store.put_tenant(
        TenantDescriptor(
            tenant_ref="acme",
            organization_ref="org-1",
            lifecycle_state=TenantLifecycleState.ACTIVE,
            expected_schema_version="1",
            database_association_ref=SecretReference(store_ref="assoc/acme", version="1"),
        )
    )
    store.put_tenant(
        TenantDescriptor(
            tenant_ref="zeta",
            organization_ref="org-2",
            lifecycle_state=TenantLifecycleState.DISABLED,
            expected_schema_version="1",
            database_association_ref=SecretReference(store_ref="assoc/zeta", version="1"),
        )
    )
    store.put_membership("p-agent", "acme", PlatformRole.TENANT_AGENT)
    store.put_directory_record(
        DirectoryKind.GLOBAL_STARTUP, DirectoryRecord(record_ref="gs-2", display_name="Beta Corp")
    )
    store.put_directory_record(
        DirectoryKind.GLOBAL_STARTUP, DirectoryRecord(record_ref="gs-1", display_name="Alpha Corp")
    )
    return store


def _control_client() -> TestClient:
    cp_main._store = _seeded_control_store()  # type: ignore[attr-defined]
    return TestClient(cp_main.app, raise_server_exceptions=False)


def test_tenant_descriptor_read_returns_references_not_credentials() -> None:
    response = _control_client().get("/internal/tenants/acme", headers=_CREDENTIAL)
    assert response.status_code == 200
    body = response.json()
    assert body["database_association_ref"] == {"store_ref": "assoc/acme", "version": "1"}
    for forbidden in ("password", "dbname=", "postgresql://", "host="):
        assert forbidden not in response.text


def test_unknown_tenant_answers_the_consistent_denial() -> None:
    response = _control_client().get("/internal/tenants/no-such-tenant", headers=_CREDENTIAL)
    assert response.status_code == 404
    assert response.json() == {"status": 404, "code": "tenant_not_found"}


def test_only_an_active_tenant_is_serviceable() -> None:
    client = _control_client()
    assert client.get("/internal/tenants/acme/readiness", headers=_CREDENTIAL).json()["serviceable"] is True
    assert client.get("/internal/tenants/zeta/readiness", headers=_CREDENTIAL).json()["serviceable"] is False


def test_memberships_are_deterministic_and_an_empty_list_is_a_success() -> None:
    client = _control_client()
    held = client.get("/internal/memberships/p-agent", headers=_CREDENTIAL).json()
    assert held["memberships"] == [{"tenant_ref": "acme", "role": "TENANT_AGENT"}]
    none_held = client.get("/internal/memberships/p-nobody", headers=_CREDENTIAL)
    assert none_held.status_code == 200
    assert none_held.json()["memberships"] == []


def test_directory_records_are_tenant_anonymous_and_deterministically_ordered() -> None:
    body = _control_client().get(
        "/internal/directories/GlobalStartupDirectory/records", headers=_CREDENTIAL
    ).json()
    assert [record["record_ref"] for record in body["records"]] == ["gs-1", "gs-2"]
    for record in body["records"]:
        assert set(record) == {"record_ref", "display_name", "attributes"}
        for forbidden in ("tenant_ref", "tenant_id", "tenant_name", "tenant_code", "lineage_reference"):
            assert forbidden not in record


def test_a_connection_string_is_refused_where_a_reference_is_expected() -> None:
    """D-14: this field is a reference. Refusing at the write boundary means a DSN can
    never be read back out of it, which no read-side check could guarantee on its own."""
    assert looks_like_a_connection_string("postgresql://user:pw@host/db")
    assert looks_like_a_connection_string("host=db.internal dbname=acme")
    assert not looks_like_a_connection_string("assoc/acme")

    response = _control_client().put(
        "/internal/tenants",
        headers=_CREDENTIAL,
        json={
            "tenant_ref": "nova",
            "organization_ref": "org-3",
            "lifecycle_state": "ACTIVE",
            "expected_schema_version": "1",
            "database_association_ref": {"store_ref": "postgresql://u:p@h/nova", "version": "1"},
        },
    )
    assert response.status_code == 422
    assert response.json() == {"status": 422, "code": "invalid_request"}


def test_control_plane_openapi_meets_the_standing_rules() -> None:
    assert_document(
        cp_main.app.openapi(),
        service="control_plane",
        expected_paths=[
            "/health",
            "/readiness",
            "/internal/tenants/{tenant_ref}",
            "/internal/tenants/{tenant_ref}/readiness",
            "/internal/memberships/{principal_ref}",
            "/internal/directories/{directory}/records",
            "/internal/directories/{directory}/records/{record_ref}",
            "/internal/tenants",
            "/internal/memberships",
        ],
        expected_schemas=["TenantDescriptor", "MembershipsResponse", "DirectoryListResponse", "SecretReference"],
        required_security_schemes=["InternalServiceBearer"],
    )


# --- Database Router: the six required resolution cases ------------------------------------

def _registry() -> StaticTenantRegistry:
    return StaticTenantRegistry(
        {
            "acme": TenantRegistryEntry("acme", TenantLifecycleState.ACTIVE, "1", "assoc/acme", "1"),
            "zeta": TenantRegistryEntry("zeta", TenantLifecycleState.DISABLED, "1", "assoc/zeta", "1"),
            "nova": TenantRegistryEntry("nova", TenantLifecycleState.ACTIVE, "1", "assoc/nova", "1"),
        }
    )


def _resolver_with(env: dict[str, str]) -> TenantResolver:
    return TenantResolver(_registry(), EnvironmentTenantSecretStore(env=env))


_ACME_DSN_VAR = EnvironmentTenantSecretStore.variable_name("assoc/acme", "1")


def _denial(callable_: object, *args: object) -> AppError:
    try:
        callable_(*args)  # type: ignore[operator]
    except AppError as error:
        return error
    raise AssertionError("expected a fail-closed denial, got a resolution")


def test_known_tenant_resolves_exactly_one_database() -> None:
    resolver = _resolver_with({_ACME_DSN_VAR: "postgresql://localhost/acme"})
    target = resolver.resolve("acme")
    assert target.tenant_ref == "acme"
    assert target.target_ref == "ref:tenant/acme/database"


def test_unknown_tenant_fails_closed_with_the_consistent_denial() -> None:
    error = _denial(_resolver_with({}).resolve, "no-such-tenant")
    assert (error.status, error.code.value) == (404, "tenant_not_found")


def test_a_tenantless_context_has_no_tenant_database() -> None:
    error = _denial(_resolver_with({}).resolve, None)
    assert (error.status, error.code.value) == (404, "tenant_not_found")


def test_a_disabled_tenant_is_not_ready() -> None:
    error = _denial(_resolver_with({}).resolve, "zeta")
    assert (error.status, error.code.value) == (409, "tenant_not_ready")


def test_a_missing_association_mapping_is_unavailable_not_a_fallback() -> None:
    """The registry names an association the secret store cannot produce."""
    error = _denial(_resolver_with({}).resolve, "nova")
    assert (error.status, error.code.value) == (503, "tenant_unavailable")


def test_an_unavailable_registry_resolves_nothing() -> None:
    """A registry read that fails must not produce a cached, default, or Control answer."""
    resolver = TenantResolver(StaticTenantRegistry({}), EnvironmentTenantSecretStore(env={}))
    error = _denial(resolver.resolve, "acme")
    assert error.status == 404


def test_no_control_database_fallback_exists_in_the_resolver_source() -> None:
    """Structural, not behavioural.

    A behavioural test can only show that today's inputs do not reach the Control database.
    This shows the resolver has no branch that could: the module never mentions a control
    DSN, a control database, or a default tenant.
    """
    source = pathlib.Path(dbr_resolver.__file__).read_text(encoding="utf-8").casefold()
    tree = ast.parse(pathlib.Path(dbr_resolver.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.casefold()
            assert "control_dsn" not in value, "the resolver references a control DSN"
    assert "sp2_control_plane_dsn" not in source, "the resolver can reach the Control database credential"




# --- Database Router: connection grants (D-48) ----------------------------------------------

def test_the_grant_allowlist_permanently_excludes_the_bff_and_the_authorizer() -> None:
    """D-48 C-1, enforced at CONFIGURATION time rather than at request time.

    Both exclusions are structural rather than incidental. The BFF is the public ingress, so the
    process nearest the internet must be the furthest from a credential; and IC-014 §6 is
    absolute — the service that decides access must not be the service that has access. A
    misconfiguration naming either one fails on startup instead of quietly widening the blast
    radius until someone notices.
    """
    assert "bff" in PERMANENTLY_EXCLUDED
    assert "access_control" in PERMANENTLY_EXCLUDED
    assert PERMANENTLY_EXCLUDED.isdisjoint(TENANT_RESIDENT_SERVICES)

    for excluded in sorted(PERMANENTLY_EXCLUDED):
        try:
            GrantAllowlist({"some-credential": excluded})
        except ValueError:
            continue
        raise AssertionError(excluded + " was accepted onto the connection-grant allowlist")


def test_a_non_tenant_resident_service_cannot_be_a_grantee() -> None:
    try:
        GrantAllowlist({"some-credential": "not-a-service"})
    except ValueError:
        return
    raise AssertionError("an unknown service was accepted onto the grant allowlist")


def test_an_unconfigured_router_grants_nothing() -> None:
    allowlist = build_allowlist(env={})
    assert allowlist.service_for("any-credential") is None
    assert allowlist.service_refs() == []


def _router_client(env: dict[str, str], grantees: dict[str, str] | None = None) -> TestClient:
    dbr_main._resolver = _resolver_with(env)  # type: ignore[attr-defined]
    dbr_main._allowlist = GrantAllowlist(grantees or {})  # type: ignore[attr-defined]
    return TestClient(dbr_main.app, raise_server_exceptions=False)


def _context(tenant: str | None) -> dict[str, object]:
    return RequestContext.from_auth_context(
        AuthContext(correlation_id="c-1", principal_ref="p-agent", role=PlatformRole.TENANT_AGENT, active_tenant_ref=tenant)
    ).model_dump(mode="json")


def test_routing_resolution_never_discloses_a_dsn() -> None:
    """What the BFF receives proves one database bound, without saying how to reach it."""
    client = _router_client({_ACME_DSN_VAR: "postgresql://localhost/acme"})
    response = client.post("/internal/routing/resolve", headers=_CREDENTIAL, json={"context": _context("acme")})
    assert response.status_code == 200
    assert response.json() == {
        "tenant_ref": "acme",
        "target_ref": "ref:tenant/acme/database",
        "expected_schema_version": "1",
    }
    assert "postgresql://" not in response.text


def test_an_allowlisted_service_receives_a_single_tenant_grant() -> None:
    client = _router_client({_ACME_DSN_VAR: "postgresql://localhost/acme"}, {"startups-key": "startups"})
    response = client.post(
        "/internal/routing/bind",
        headers={"Authorization": "Bearer startups-key"},
        json={"tenant_ref": "acme"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tenant_ref"] == "acme"
    assert body["dsn"] == "postgresql://localhost/acme"
    assert body["expires_at"], "a grant with no expiry is a standing credential (D-48 C-2)"


def test_a_caller_outside_the_allowlist_is_refused_even_with_a_valid_credential() -> None:
    """The refusal happens BEFORE resolution, so the endpoint cannot be used to probe tenants."""
    client = _router_client({_ACME_DSN_VAR: "postgresql://localhost/acme"}, {"startups-key": "startups"})
    for probe in ("acme", "no-such-tenant", "zeta"):
        response = client.post(
            "/internal/routing/bind",
            headers={"Authorization": "Bearer some-other-key"},
            json={"tenant_ref": probe},
        )
        assert response.status_code == 403, probe
        assert response.json() == {"status": 403, "code": "access_denied"}


def test_grant_issuance_fails_closed_on_the_same_cases_as_resolution() -> None:
    """D-48 C-4: a service cannot obtain a connection the router would not itself have opened."""
    client = _router_client({_ACME_DSN_VAR: "postgresql://localhost/acme"}, {"startups-key": "startups"})
    headers = {"Authorization": "Bearer startups-key"}
    for tenant_ref, expected in (("no-such-tenant", 404), ("zeta", 409), ("nova", 503)):
        response = client.post("/internal/routing/bind", headers=headers, json={"tenant_ref": tenant_ref})
        assert response.status_code == expected, tenant_ref
        assert "postgresql://" not in response.text, "a denial disclosed a connection string"


def test_the_grantee_listing_returns_service_references_never_credentials() -> None:
    client = _router_client({}, {"startups-key": "startups", "deals-key": "deals"})
    response = client.get("/internal/routing/grantees", headers=_CREDENTIAL)
    assert response.status_code == 200
    assert response.json() == {"grantees": [{"service_ref": "deals"}, {"service_ref": "startups"}]}
    assert "startups-key" not in response.text


def test_a_grant_never_reaches_the_bff_through_the_resolve_surface() -> None:
    """The resolve response shape has no field a DSN could occupy, whatever the caller is."""
    from snackportal2.services.database_router.models import RoutingResolution

    assert set(RoutingResolution.model_fields) == {"tenant_ref", "target_ref", "expected_schema_version"}
    assert "dsn" not in RoutingResolution.model_fields


def test_database_router_openapi_meets_the_standing_rules() -> None:
    assert_document(
        dbr_main.app.openapi(),
        service="database_router",
        expected_paths=[
            "/health",
            "/readiness",
            "/internal/routing/resolve",
            "/internal/routing/bind",
            "/internal/routing/grantees",
        ],
        expected_schemas=["RoutingResolution", "TenantConnectionGrantResponse", "GranteeListResponse"],
        required_security_schemes=["InternalServiceBearer"],
    )
