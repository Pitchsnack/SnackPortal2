"""Stage 4C — the Database Router against real Control-DB routing metadata.

Both services run as **real uvicorn processes**. The router is configured only through the
environment, so it composes ``HttpControlPlaneRegistry`` and ``EnvironmentTenantSecretStore``
itself and reads its registry over real HTTP from a Control Plane backed by the real Control
database. Grants are fetched with the production ``RouterGrantProvider`` — the same class a
domain service uses — and the connection it authorizes is really opened.

Every case in the brief's §5 table is here, plus D-48 C-1 through C-4. The two negative
allowlist cases are asserted at *configuration* time: a router told to grant to the BFF or to
Access Control must fail to start, because a check that only fires per request leaves a window
in which the process is running with an unlawful allowlist.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Iterator, List

import httpx
import pytest

from snackportal2.services.control_plane.models import SecretReference, TenantDescriptor
from snackportal2.services.control_plane.store import ENV_CONTROL_DSN, build_store
from snackportal2.services.database_router import grants as router_grants
from snackportal2.services.database_router import resolver as router_resolver
from snackportal2.shared.errors import AppError
from snackportal2.shared.security import AuthContext, RequestContext
from snackportal2.shared.tenant_data import (
    NoGrantProvider,
    RouterGrantProvider,
    TenantConnectionGrant,
    build_grant_provider,
    open_tenant_connection,
)
from snackportal2.shared.types import PlatformRole, TenantLifecycleState

from . import _stage4_pg as pg
from . import _stage4_servers as srv

pytestmark = pytest.mark.skipif(not pg.configured(), reason=pg.SKIP_REASON)

SERVICE_CREDENTIAL = "internal-router-credential"
STARTUPS_CREDENTIAL = "grant-credential-startups"
BFF_CREDENTIAL = "internal-bff-credential"
ACCESS_CONTROL_CREDENTIAL = "internal-access-control-credential"

#: Registry entries seeded into the real Control database, one per failure mode.
SEEDED = {
    "acme": (TenantLifecycleState.ACTIVE, "assoc/acme"),
    "zeta": (TenantLifecycleState.ACTIVE, "assoc/zeta"),
    "nova": (TenantLifecycleState.ACTIVE, "assoc/nova"),
    "dormant": (TenantLifecycleState.DISABLED, "assoc/dormant"),
    "provisioning": (TenantLifecycleState.PROVISIONING, "assoc/provisioning"),
    "orphan": (TenantLifecycleState.ACTIVE, "assoc/orphan"),
    "malformed": (TenantLifecycleState.ACTIVE, "assoc/malformed"),
    "offline": (TenantLifecycleState.ACTIVE, "assoc/offline"),
}


def _dsn_variable(store_ref: str) -> str:
    return router_resolver.EnvironmentTenantSecretStore.variable_name(store_ref, "1")


def _seed_registry() -> None:
    store = build_store(env={ENV_CONTROL_DSN: pg.dsn("control")})
    for tenant_ref, (lifecycle, association) in SEEDED.items():
        store.put_tenant(
            TenantDescriptor(
                tenant_ref=tenant_ref,
                organization_ref="org-" + tenant_ref,
                lifecycle_state=lifecycle,
                expected_schema_version="1",
                database_association_ref=SecretReference(store_ref=association, version="1"),
            )
        )


def _seed_sentinels() -> Dict[str, str]:
    """One distinguishable row per tenant database, so a grant can be proven to bind one.

    Comparing database *names* would mean handling a DSN in an assertion. A sentinel row
    proves the same thing by observation and keeps every credential out of the test body.
    """
    sentinels = {tenant: "SENTINEL-" + tenant.upper() for tenant in pg.TENANTS}
    for tenant, marker in sentinels.items():
        pg.execute(
            pg.dsn(tenant),
            "INSERT INTO startups (company_name, global_startup_id) VALUES (%s, %s) "
            "ON CONFLICT (global_startup_id) DO UPDATE SET company_name = EXCLUDED.company_name",
            (marker, "sentinel/" + tenant),
        )
    return sentinels


@pytest.fixture(scope="module")
def fleet(tmp_path_factory: pytest.TempPathFactory) -> Iterator[srv.ServiceFleet]:
    pg.provision()
    _seed_registry()
    _seed_sentinels()

    log_dir: Path = tmp_path_factory.mktemp("stage4c-logs")
    running = srv.ServiceFleet(log_dir)
    try:
        control = running.start("control_plane", {"SP2_CONTROL_PLANE_DSN": pg.dsn("control")})

        # A closed loopback port: the "tenant database is unavailable" case, expressed as
        # configuration rather than by stopping a container mid-run.
        closed_port = srv.free_port()
        offline_dsn = "postgresql://unreachable@127.0.0.1:" + str(closed_port) + "/sp2_offline"

        running.start(
            "database_router",
            {
                "SP2_DATABASE_ROUTER_CONTROL_PLANE_URL": control.base_url,
                "SP2_DATABASE_ROUTER_SERVICE_CREDENTIAL": SERVICE_CREDENTIAL,
                "SP2_DATABASE_ROUTER_GRANTEES": json.dumps({STARTUPS_CREDENTIAL: "startups"}),
                _dsn_variable("assoc/acme"): pg.dsn("acme"),
                _dsn_variable("assoc/zeta"): pg.dsn("zeta"),
                _dsn_variable("assoc/nova"): pg.dsn("nova"),
                _dsn_variable("assoc/dormant"): pg.dsn("acme"),
                _dsn_variable("assoc/provisioning"): pg.dsn("acme"),
                # assoc/orphan is deliberately absent -> missing association.
                _dsn_variable("assoc/malformed"): "this-is-not-a-connection-string",
                _dsn_variable("assoc/offline"): offline_dsn,
            },
        )
        yield running
    finally:
        running.stop()


def _context(tenant_ref: object) -> dict:
    """Build the wire context the way the BFF does — through the one lawful constructor.

    Hand-writing the JSON would let this file drift from ``RequestContext`` and turn a real
    contract change into a 422 in the tests rather than a caught regression.
    """
    auth = AuthContext(
        correlation_id="c-stage4c",
        principal_ref="p-agent",
        role=PlatformRole.TENANT_AGENT,
        active_tenant_ref=tenant_ref,  # type: ignore[arg-type]
    )
    return RequestContext.from_auth_context(auth).model_dump(mode="json")


def _resolve(fleet: srv.ServiceFleet, tenant_ref: object, credential: str = SERVICE_CREDENTIAL) -> httpx.Response:
    return httpx.post(
        fleet.url("database_router") + "/internal/routing/resolve",
        headers={"Authorization": "Bearer " + credential},
        json={"context": _context(tenant_ref)},
        timeout=10.0,
    )


def _bind(fleet: srv.ServiceFleet, tenant_ref: str, credential: str) -> httpx.Response:
    return httpx.post(
        fleet.url("database_router") + "/internal/routing/bind",
        headers={"Authorization": "Bearer " + credential},
        json={"tenant_ref": tenant_ref},
        timeout=10.0,
    )


# --- the six resolution cases ------------------------------------------------------------


def test_a_known_active_tenant_resolves_to_exactly_one_database(fleet: srv.ServiceFleet) -> None:
    for tenant in pg.TENANTS:
        response = _resolve(fleet, tenant)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["tenant_ref"] == tenant
        assert body["target_ref"] == "ref:tenant/" + tenant + "/database"
        assert body["expected_schema_version"] == "1"
        # A resolution is a reference. It is not, and must never become, a way to connect.
        assert set(body) == {"tenant_ref", "target_ref", "expected_schema_version"}


def test_an_unknown_tenant_fails_closed_with_the_consistent_denial(fleet: srv.ServiceFleet) -> None:
    response = _resolve(fleet, "no-such-tenant")
    assert response.status_code == 404
    assert response.json() == {"status": 404, "code": "tenant_not_found"}


def test_a_tenantless_context_fails_closed_identically_to_an_unknown_tenant(fleet: srv.ServiceFleet) -> None:
    """There is no default tenant, so "no tenant" and "no such tenant" answer the same way."""
    assert _resolve(fleet, None).json() == _resolve(fleet, "no-such-tenant").json()


@pytest.mark.parametrize("tenant", ["dormant", "provisioning"])
def test_an_inactive_tenant_fails_closed_as_not_ready(fleet: srv.ServiceFleet, tenant: str) -> None:
    response = _resolve(fleet, tenant)
    assert response.status_code == 409
    assert response.json() == {"status": 409, "code": "tenant_not_ready"}


def test_a_missing_database_association_fails_closed_as_unavailable(fleet: srv.ServiceFleet) -> None:
    response = _resolve(fleet, "orphan")
    assert response.status_code == 503
    assert response.json() == {"status": 503, "code": "tenant_unavailable"}


def test_a_malformed_database_association_never_yields_a_usable_connection(fleet: srv.ServiceFleet) -> None:
    """The router does not connect, so it cannot pre-validate a DSN — the failure lands here.

    What matters is the observable outcome: the caller gets the canonical unavailable denial
    and no connection to any other database. A grant is issued for a value the router cannot
    tell is broken; opening it fails closed, which is the behaviour the isolation rule needs.
    """
    granted = _bind(fleet, "malformed", STARTUPS_CREDENTIAL)
    assert granted.status_code == 200, granted.text
    grant = TenantConnectionGrant(**granted.json())
    with pytest.raises(AppError) as raised:
        open_tenant_connection(grant)
    assert raised.value.status == 503
    assert raised.value.code.value == "tenant_unavailable"


def test_an_unavailable_tenant_database_fails_closed_and_reaches_nothing_else(fleet: srv.ServiceFleet) -> None:
    granted = _bind(fleet, "offline", STARTUPS_CREDENTIAL)
    assert granted.status_code == 200
    grant = TenantConnectionGrant(**granted.json())
    with pytest.raises(AppError) as raised:
        open_tenant_connection(grant)
    assert raised.value.code.value == "tenant_unavailable"


def test_an_unavailable_tenant_database_fails_closed_promptly(fleet: srv.ServiceFleet) -> None:
    """Stage 4 defect F-2: fail-closed has to mean *fast*, not merely eventual.

    Measured, because the difference is invisible in source and enormous in operation: with no
    connect timeout the driver took ~130 seconds to give up. The BFF abandons a downstream call
    after 5, so the caller was already answered while the callee stayed blocked — one tenant's
    outage becoming every tenant's latency on the same service.
    """
    from snackportal2.shared.config import db_connect_timeout

    grant = TenantConnectionGrant(**_bind(fleet, "offline", STARTUPS_CREDENTIAL).json())
    started = time.monotonic()
    with pytest.raises(AppError):
        open_tenant_connection(grant)
    elapsed = time.monotonic() - started
    assert elapsed < db_connect_timeout() + 10, "opening an unreachable tenant database took " + str(round(elapsed, 1)) + "s"


def test_the_connect_timeout_takes_a_secure_default_and_ignores_a_broken_override() -> None:
    """A typo in configuration must not silently restore the unbounded behaviour."""
    from snackportal2.shared.config import (
        DEFAULT_DB_CONNECT_TIMEOUT_SECONDS,
        ENV_DB_CONNECT_TIMEOUT,
        db_connect_timeout,
    )

    assert db_connect_timeout(env={}) == DEFAULT_DB_CONNECT_TIMEOUT_SECONDS
    assert db_connect_timeout(env={ENV_DB_CONNECT_TIMEOUT: "12"}) == 12
    for broken in ("", "   ", "abc", "0", "-5", "3.5"):
        assert db_connect_timeout(env={ENV_DB_CONNECT_TIMEOUT: broken}) == DEFAULT_DB_CONNECT_TIMEOUT_SECONDS, broken


# --- never the Control database ----------------------------------------------------------


def test_no_routing_failure_ever_returns_the_control_database(fleet: srv.ServiceFleet) -> None:
    """The property that makes physical isolation survive an outage (IC-013 §11, D-48 C-4).

    Checked two ways: nothing in any failure response resembles a Control target, and the
    Control database gains no row while every failure mode is exercised.
    """
    control = pg.dsn("control")
    tables = pg.table_names(control)
    before = {table: pg.scalar(control, "SELECT count(*) FROM " + table) for table in tables}

    # ``malformed`` is deliberately absent: the router resolves it (the registry names an
    # association the secret store *can* produce), and the failure lands where the socket is
    # actually opened. That case is covered by its own test.
    for tenant in ("no-such-tenant", "dormant", "provisioning", "orphan"):
        response = _resolve(fleet, tenant)
        assert response.status_code >= 400
        text = response.text.casefold()
        assert "control" not in text, tenant + " failure mentioned Control: " + response.text
        assert set(response.json()) == {"status", "code"}

    after = {table: pg.scalar(control, "SELECT count(*) FROM " + table) for table in tables}
    assert after == before, "routing failures wrote to the Control database"


def test_the_resolver_has_no_branch_that_can_answer_control(fleet: srv.ServiceFleet) -> None:
    """A structural companion to the behavioural test above.

    ``TenantResolver.resolve`` returns a ``ResolvedTarget`` whose ``target_ref`` is built from
    the tenant reference alone, so no reachable input produces a Control target. Exercised
    here with the live registry rather than asserted from source.
    """
    seen = set()
    for tenant in pg.TENANTS:
        seen.add(_resolve(fleet, tenant).json()["target_ref"])
    assert seen == {"ref:tenant/" + tenant + "/database" for tenant in pg.TENANTS}


# --- D-48 C-1: the allowlist -------------------------------------------------------------


def test_an_allowlisted_domain_service_receives_a_grant_that_binds_its_one_tenant(fleet: srv.ServiceFleet) -> None:
    """D-48 C-2 and the "allowed domain service" row, proven by opening the connection.

    The grant is fetched with the production ``RouterGrantProvider``, and the sentinel row
    read back proves *which* physical database bound — without a name or a DSN entering the
    assertion.
    """
    provider = RouterGrantProvider(fleet.url("database_router"), STARTUPS_CREDENTIAL)
    for tenant in pg.TENANTS:
        grant = provider.grant_for(tenant)
        assert grant.tenant_ref == tenant
        assert grant.target_ref == "ref:tenant/" + tenant + "/database"
        assert grant.expires_at

        with open_tenant_connection(grant) as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute("SELECT company_name FROM startups WHERE global_startup_id LIKE 'sentinel/%'")
                found = sorted(str(row[0]) for row in cursor.fetchall())
        assert found == ["SENTINEL-" + tenant.upper()], tenant + " grant opened the wrong database: " + repr(found)


def test_a_credential_not_on_the_allowlist_is_refused_even_though_it_is_valid(fleet: srv.ServiceFleet) -> None:
    """D-48 C-1: the BFF's and Access Control's own credentials buy nothing here."""
    for credential in (BFF_CREDENTIAL, ACCESS_CONTROL_CREDENTIAL, SERVICE_CREDENTIAL):
        response = _bind(fleet, "acme", credential)
        assert response.status_code == 403, credential + " received " + str(response.status_code)
        assert response.json() == {"status": 403, "code": "access_denied"}


def test_an_unallowlisted_caller_cannot_use_bind_to_probe_which_tenants_exist(fleet: srv.ServiceFleet) -> None:
    """Refusal precedes resolution, so a known and an unknown tenant answer identically."""
    known = _bind(fleet, "acme", BFF_CREDENTIAL)
    unknown = _bind(fleet, "no-such-tenant", BFF_CREDENTIAL)
    assert known.status_code == unknown.status_code == 403
    assert known.json() == unknown.json()


def test_the_grantee_listing_returns_service_references_and_never_credentials(fleet: srv.ServiceFleet) -> None:
    response = httpx.get(
        fleet.url("database_router") + "/internal/routing/grantees",
        headers={"Authorization": "Bearer " + SERVICE_CREDENTIAL},
        timeout=10.0,
    )
    assert response.status_code == 200
    assert response.json() == {"grantees": [{"service_ref": "startups"}]}
    assert STARTUPS_CREDENTIAL not in response.text


@pytest.mark.parametrize("excluded", ["bff", "access_control"])
def test_a_router_configured_to_grant_to_an_excluded_service_refuses_to_start(
    tmp_path_factory: pytest.TempPathFactory, excluded: str
) -> None:
    """D-48 C-1 is enforced at configuration time, not per request.

    A per-request check would leave a process running with an unlawful allowlist between boot
    and the first call. Here the process must never reach a serving state at all.
    """
    running = srv.ServiceFleet(tmp_path_factory.mktemp("stage4c-excluded-" + excluded))
    try:
        with pytest.raises(RuntimeError) as raised:
            running.start(
                "database_router",
                {
                    "SP2_DATABASE_ROUTER_GRANTEES": json.dumps({"some-credential": excluded}),
                },
            )
        message = str(raised.value)
        assert "exited during startup" in message
        assert "may never receive a tenant connection grant" in message, message[-2000:]
    finally:
        running.stop()


def test_no_service_outside_the_tenant_resident_set_can_be_configured_as_a_grantee() -> None:
    """The allowlist is a *positive* census, which is what makes it complete.

    ``PERMANENTLY_EXCLUDED`` and ``TENANT_RESIDENT_SERVICES`` do not partition the fourteen
    services — ``database_router`` and ``ai_agents`` are in neither — and that is not a hole,
    because the constructor's second check requires membership of the tenant-resident set. A
    deny-list alone would have left exactly those two configurable; the positive check is why
    every one of the fourteen is refused unless it is deliberately tenant-resident.
    """
    from snackportal2.shared.config import SERVICE_REGISTRY

    assert not (router_grants.PERMANENTLY_EXCLUDED & router_grants.TENANT_RESIDENT_SERVICES)
    assert {"bff", "access_control"} <= router_grants.PERMANENTLY_EXCLUDED

    for service_key in SERVICE_REGISTRY:
        if service_key in router_grants.TENANT_RESIDENT_SERVICES:
            router_grants.GrantAllowlist({"credential": service_key})
            continue
        with pytest.raises(ValueError):
            router_grants.GrantAllowlist({"credential": service_key})


# --- D-48 C-3: no credential is ever disclosed -------------------------------------------


def test_no_router_or_control_plane_response_discloses_a_connection_string(fleet: srv.ServiceFleet) -> None:
    fragments: List[str] = srv.dsn_secret_fragments()
    assert fragments, "the leakage check needs configured DSNs to look for"

    bodies = [_resolve(fleet, tenant).text for tenant in list(pg.TENANTS) + ["orphan", "dormant", "no-such-tenant"]]
    bodies.append(httpx.get(fleet.url("database_router") + "/health", timeout=10.0).text)
    bodies.append(httpx.get(fleet.url("database_router") + "/readiness", timeout=10.0).text)
    bodies.append(
        httpx.get(
            fleet.url("database_router") + "/internal/routing/grantees",
            headers={"Authorization": "Bearer " + SERVICE_CREDENTIAL},
            timeout=10.0,
        ).text
    )
    bodies.append(httpx.get(fleet.url("database_router") + "/openapi.json", timeout=10.0).text)

    for body in bodies:
        for fragment in fragments:
            assert fragment not in body, "a response disclosed a DSN fragment"


def test_no_service_process_log_contains_a_connection_string(fleet: srv.ServiceFleet) -> None:
    """§5 names logs explicitly, so this reads the real process output rather than the source."""
    fragments = srv.dsn_secret_fragments()
    for key, text in fleet.all_logs().items():
        for fragment in fragments:
            assert fragment not in text, key + " logged a DSN fragment"


def test_a_grant_object_redacts_its_connection_string_in_repr_and_str() -> None:
    """C-3 includes exception traces, and a traceback renders objects with ``repr``."""
    grant = TenantConnectionGrant(
        tenant_ref="acme",
        target_ref="ref:tenant/acme/database",
        expected_schema_version="1",
        dsn="postgresql://user:secret@host:5432/db",
        expires_at="2026-08-23T00:01:00+00:00",
    )
    assert "secret" not in repr(grant)
    assert "secret" not in str(grant)
    assert "<redacted>" in repr(grant)
    assert "secret" not in "{}".format(grant)
    assert "secret" not in f"{grant}"


def test_an_exception_raised_while_opening_a_grant_carries_no_connection_string() -> None:
    closed = srv.free_port()
    grant = TenantConnectionGrant(
        tenant_ref="acme",
        target_ref="ref:tenant/acme/database",
        expected_schema_version="1",
        dsn="postgresql://user:secret@127.0.0.1:" + str(closed) + "/db",
        expires_at="2026-08-23T00:01:00+00:00",
    )
    with pytest.raises(AppError) as raised:
        open_tenant_connection(grant)
    rendered = repr(raised.value) + str(raised.value) + repr(raised.value.__cause__)
    assert "secret" not in rendered
    assert raised.value.__cause__ is None, "the driver error must not be chained onto the denial"


# --- fail-closed by omission --------------------------------------------------------------


def test_a_service_with_no_router_configured_can_reach_no_tenant_database() -> None:
    provider = build_grant_provider("startups", env={})
    assert isinstance(provider, NoGrantProvider)
    with pytest.raises(AppError) as raised:
        provider.grant_for("acme")
    assert raised.value.code.value == "tenant_unavailable"


def test_a_router_url_without_a_credential_is_not_a_configured_router(fleet: srv.ServiceFleet) -> None:
    provider = build_grant_provider("startups", env={"SP2_STARTUPS_DATABASE_ROUTER_URL": fleet.url("database_router")})
    assert isinstance(provider, NoGrantProvider)


def test_a_configured_router_url_and_credential_select_the_real_grant_provider(fleet: srv.ServiceFleet) -> None:
    provider = build_grant_provider(
        "startups",
        env={
            "SP2_STARTUPS_DATABASE_ROUTER_URL": fleet.url("database_router"),
            "SP2_STARTUPS_SERVICE_CREDENTIAL": STARTUPS_CREDENTIAL,
        },
    )
    assert isinstance(provider, RouterGrantProvider)
    assert provider.grant_for("acme").tenant_ref == "acme"


def test_a_grant_request_for_a_tenantless_context_is_refused_before_any_call() -> None:
    provider = RouterGrantProvider("http://127.0.0.1:1", "unused")
    with pytest.raises(AppError) as raised:
        provider.grant_for(None)
    assert raised.value.code.value == "tenant_unavailable"


def test_the_router_denial_propagates_unchanged_through_the_grant_provider(fleet: srv.ServiceFleet) -> None:
    """ "Not ready" must not become "not found" on the way back (D-48 C-4)."""
    provider = RouterGrantProvider(fleet.url("database_router"), STARTUPS_CREDENTIAL)
    for tenant, status, code in (
        ("no-such-tenant", 404, "tenant_not_found"),
        ("dormant", 409, "tenant_not_ready"),
        ("orphan", 503, "tenant_unavailable"),
    ):
        with pytest.raises(AppError) as raised:
            provider.grant_for(tenant)
        assert (raised.value.status, raised.value.code.value) == (status, code), tenant
