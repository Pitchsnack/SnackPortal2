"""The twenty required adversarial proofs against the Gateway-free MVP architecture.

Every test drives a REAL composed public edge over a REAL loopback socket. The only doubles
are the identity provider and the database (see ``_fakes``); the boundary kernel, the transport
gate, the executor, the DTO composition, and the FastAPI applications are the real runtime.

The isolation oracle throughout is ``provider.opened`` — the list of ``(tenant_id,
principal_ref)`` pairs the routed session provider was asked to open. A status code alone is a
weak oracle: a cross-tenant read that returns ``404`` because the record happens to be missing
looks identical to one that was never attempted. Asserting on the opened sessions distinguishes
them, and it is the assertion a mutation must not be able to satisfy.
"""

from __future__ import annotations

import pathlib
import sys

# APPEND, never insert(0): backend/tests contains packages named after the services
# (tests/database_router/, tests/control_plane/, tests/shared/). Putting it first makes those
# EMPTY stubs win over the production packages, which silently blinds any sys.modules census.
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from gateway_free._fakes import (  # noqa: E402
    ACME,
    ACME_BEARER,
    ACME_PRINCIPAL,
    ACME_REF,
    ACME_SECRET_NAME,
    CONTROL_BEARER,
    STRANGER_BEARER,
    ZETA,
    ZETA_BEARER,
    ZETA_PRINCIPAL,
    ZETA_REF,
    HostedEdge,
    TwoTenantProvider,
    bearer,
    build_boundary,
    decode,
)

from control_plane.adapters.providers.control_membership_reader import ControlStoreMembershipReader  # noqa: E402
from control_plane.adapters.providers.control_store_factory import SharedControlStoreFactory  # noqa: E402
from control_plane.adapters.providers.http_public_workspace_edge import build_public_workspace_edge_server  # noqa: E402
from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.membership import MembershipRegistry  # noqa: E402
from control_plane.records import Role  # noqa: E402
from database_router.adapters.providers.http_public_startup_edge import build_public_startup_edge_server  # noqa: E402
from database_router.adapters.providers.http_tenant_startup_api import build_tenant_startup_server  # noqa: E402
from database_router.tenant_startup_ops import TenantStartupOperations  # noqa: E402
from shared.adapters.providers.edge_audit import EdgeAuditTransportError  # noqa: E402

_ACME_TARGET = "/tenant/startups/" + ACME_REF
_ZETA_TARGET = "/tenant/startups/" + ZETA_REF
_FRONTEND_ORIGIN = "http://localhost:5173"


def _startup_edge(allowed_origins=()):
    """A composed, hosted public tenant Startup edge plus its collaborators."""
    provider = TwoTenantProvider()
    boundary, auth, audit = build_boundary()
    server, base_url = build_public_startup_edge_server(
        TenantStartupOperations(provider),
        boundary,
        host="127.0.0.1",
        port=0,
        allowed_origins=allowed_origins,
    )
    return HostedEdge(server, base_url), provider, auth, audit


def _workspace_edge(memberships=((ACME_PRINCIPAL, ACME, Role.TENANT_AGENT),), allowed_origins=()):
    """A composed, hosted public workspace edge over a REAL in-memory ControlStore.

    The seeding path (``MembershipRegistry``) is deliberately kept OUT of what the edge is
    handed: the store is written here, then only a ``ControlStoreMembershipReader`` over it is
    passed in. That mirrors production exactly — the edge reads Control-DB rows it has no way
    to write — so a test could not accidentally prove the narrowing while the edge still held
    a writer.
    """
    store = InMemoryControlStore()
    registry = MembershipRegistry(store)
    for principal_ref, tenant_id, role in memberships:
        registry.add_membership(principal_ref=principal_ref, tenant_id=tenant_id, role=role)
    boundary, auth, audit = build_boundary()
    server, base_url = build_public_workspace_edge_server(
        ControlStoreMembershipReader(SharedControlStoreFactory(store)),
        boundary,
        host="127.0.0.1",
        port=0,
        allowed_origins=allowed_origins,
    )
    return HostedEdge(server, base_url), auth, audit


# ------------------------------------------------------------------------------------------
# A1 / A2 — anonymous access is denied on both verbs
# ------------------------------------------------------------------------------------------


def test_a1_anonymous_startup_get_is_denied_and_opens_no_database() -> None:
    edge, provider, _auth, _audit = _startup_edge()
    with edge:
        status, body, _headers = edge.request("GET", _ACME_TARGET)
    assert status == 401, "an anonymous Startup GET must be denied 401 unauthenticated"
    assert body == b"", "a denial carries an EMPTY body — never a hint about what exists"
    assert provider.opened == [], "no tenant database may be opened for an unauthenticated caller"


def test_a2_anonymous_startup_patch_is_denied_and_mutates_nothing() -> None:
    edge, provider, _auth, _audit = _startup_edge()
    before = dict(provider.store(ACME)[ACME_REF])
    with edge:
        status, body, _headers = edge.request(
            "PATCH",
            _ACME_TARGET,
            headers={"Content-Type": "application/json"},
            body=b'{"short_description":"written-by-nobody"}',
        )
    assert status == 401, "an anonymous Startup PATCH must be denied 401 unauthenticated"
    assert body == b""
    assert provider.opened == [], "no tenant database may be opened for an unauthenticated caller"
    assert provider.store(ACME)[ACME_REF] == before, "an anonymous PATCH must mutate nothing"


# ------------------------------------------------------------------------------------------
# A3 / A4 — the legitimate journeys still work
# ------------------------------------------------------------------------------------------


def test_a3_valid_acme_principal_reads_acme() -> None:
    edge, provider, _auth, _audit = _startup_edge()
    with edge:
        status, body, _headers = edge.request("GET", _ACME_TARGET, headers=bearer(ACME_BEARER))
    assert status == 200, "a valid ACME principal must be able to read its own tenant record"
    record = decode(body)
    assert record["record_ref"] == ACME_REF
    assert record["display_name"] == ACME_SECRET_NAME
    assert provider.opened == [(ACME, ACME_PRINCIPAL)], "exactly one ACME session, opened for the ACME principal"


def test_a4_valid_acme_principal_writes_acme() -> None:
    edge, provider, _auth, _audit = _startup_edge()
    with edge:
        status, body, _headers = edge.request(
            "PATCH",
            _ACME_TARGET,
            headers={**bearer(ACME_BEARER), "Content-Type": "application/json"},
            body=b'{"short_description":"acme-updated"}',
        )
    assert status == 200, "a valid ACME principal must be able to write its own tenant record"
    assert decode(body)["short_description"] == "acme-updated"
    assert provider.store(ACME)[ACME_REF]["short_description"] == "acme-updated", "the write must have landed in ACME's store"
    assert provider.store(ZETA)[ZETA_REF]["short_description"] == "zeta-private", "ZETA's store must be untouched"


# ------------------------------------------------------------------------------------------
# A5 / A6 — a valid ZETA principal cannot reach ACME, by read or by write
# ------------------------------------------------------------------------------------------


def test_a5_zeta_principal_cannot_read_acme() -> None:
    edge, provider, _auth, _audit = _startup_edge()
    with edge:
        status, body, _headers = edge.request("GET", _ACME_TARGET, headers=bearer(ZETA_BEARER))
    # The URL names a record, never a tenant: the ZETA principal's request binds ZETA, where
    # ACME's record does not exist. The status is the consistent not-found, and — the assertion
    # that actually matters — no ACME session was ever opened.
    assert status == 404, "ACME's record must not be readable by a ZETA principal"
    assert body == b""
    assert provider.opened == [(ZETA, ZETA_PRINCIPAL)], "only ZETA's database may be opened for a ZETA principal"
    assert ACME not in [tenant for tenant, _p in provider.opened], "no ACME session was opened"


def test_a6_zeta_principal_cannot_write_acme() -> None:
    edge, provider, _auth, _audit = _startup_edge()
    with edge:
        status, _body, _headers = edge.request(
            "PATCH",
            _ACME_TARGET,
            headers={**bearer(ZETA_BEARER), "Content-Type": "application/json"},
            body=b'{"short_description":"written-by-zeta"}',
        )
    assert status == 404, "a ZETA principal must not be able to write ACME's record"
    assert provider.opened == [(ZETA, ZETA_PRINCIPAL)], "only ZETA's database may be opened"
    assert provider.store(ACME)[ACME_REF]["short_description"] == "acme-private", "ACME's record must be byte-unchanged"


# ------------------------------------------------------------------------------------------
# A7 / A8 / A9 — client-supplied tenant and actor values are non-authoritative
# ------------------------------------------------------------------------------------------


def test_a7_x_tenant_id_cannot_switch_databases() -> None:
    edge, provider, _auth, audit = _startup_edge()
    with edge:
        status, body, _headers = edge.request(
            "GET",
            _ACME_TARGET,
            headers={**bearer(ZETA_BEARER), "X-Tenant-Id": ACME},
        )
    assert status == 403, "a carrier disagreeing with the signed claim is rejected"
    assert body == b""
    assert provider.opened == [], "a rejected carrier must open NO tenant database at all"
    assert "CarrierMismatch" in audit.actions(), "the carrier mismatch must be audited"


def test_a7b_matching_x_tenant_id_is_accepted_but_still_not_the_authority() -> None:
    # The carrier is only ever fed into the match check. A matching carrier changes nothing
    # about which database is opened — that still comes from the signed claim.
    edge, provider, _auth, _audit = _startup_edge()
    with edge:
        status, _body, _headers = edge.request("GET", _ZETA_TARGET, headers={**bearer(ZETA_BEARER), "X-Tenant-Id": ZETA})
    assert status == 200
    assert provider.opened == [(ZETA, ZETA_PRINCIPAL)]


def test_a8_json_target_tenant_ref_cannot_switch_databases() -> None:
    edge, provider, _auth, _audit = _startup_edge()
    with edge:
        status, body, _headers = edge.request(
            "PATCH",
            _ZETA_TARGET,
            headers={**bearer(ZETA_BEARER), "Content-Type": "application/json"},
            body=b'{"short_description":"x","target_tenant_ref":"' + ACME.encode() + b'"}',
        )
    # `target_tenant_ref` is not merely ignored — it is not in the accepted field set at all,
    # so the body is refused fail-closed before the executor is reached.
    assert status == 403, "a body carrying anything but the one allowlisted field is refused"
    assert body == b""
    assert provider.opened == [], "no tenant database is opened for a refused body"
    assert provider.store(ACME)[ACME_REF]["short_description"] == "acme-private", "ACME must be untouched"


def test_a9_json_actor_ref_cannot_impersonate_another_principal() -> None:
    edge, provider, _auth, _audit = _startup_edge()
    with edge:
        status, _body, _headers = edge.request(
            "PATCH",
            _ZETA_TARGET,
            headers={**bearer(ZETA_BEARER), "Content-Type": "application/json"},
            body=b'{"short_description":"x","actor_ref":"' + ACME_PRINCIPAL.encode() + b'"}',
        )
    assert status == 403, "a body carrying an actor field is refused"
    assert provider.opened == [], "no session, so no actor could have been recorded"


def test_a9b_the_recorded_actor_is_always_the_authenticated_principal() -> None:
    # The positive half of A9: on an ACCEPTED request the recorded actor is the authenticated
    # principal, and there is no request channel that could have supplied a different one.
    edge, provider, _auth, audit = _startup_edge()
    with edge:
        status, _body, _headers = edge.request(
            "PATCH",
            _ZETA_TARGET,
            headers={**bearer(ZETA_BEARER), "Content-Type": "application/json"},
            body=b'{"short_description":"zeta-updated"}',
        )
    assert status == 200
    assert provider.opened == [(ZETA, ZETA_PRINCIPAL)], "the session actor is the authenticated principal"
    updates = [e for e in audit.events if e.action == "tenant_startup_update"]
    assert len(updates) == 1 and updates[0].actor_ref == ZETA_PRINCIPAL, "the audited actor is the authenticated principal"


# ------------------------------------------------------------------------------------------
# A10 — denial consistency: unknown tenant and non-member are indistinguishable
# ------------------------------------------------------------------------------------------


def test_a10_a_non_member_is_denied_with_no_existence_signal() -> None:
    """Scoped honestly to what this suite can prove.

    ``STRANGER_BEARER`` carries a signed ACME claim with NO membership row — the shape of a
    REVOKED membership. What is proven here is that such a caller is denied 403 with an empty
    body and opens no database, carrier or not.

    What is NOT proven here, and must not be read into it: that an *unknown tenant* and a
    non-member are indistinguishable. The real ``TenantContextResolver`` makes two independent
    lookups (``get_tenant_state`` → ``state is None``, and ``is_member``) and only then collapses
    them into one ``forbidden``; this suite's identity double has a single membership check, so
    the two branches are identical BY CONSTRUCTION of the double and a regression that split
    them would be invisible here. That property belongs to ``auth_router`` and is covered by its
    own tests. Nor is a FORGED token proven: forgery fails at Stage 1 with 401, and the double
    has no Stage-1 signature path by design.
    """
    edge, provider, _auth, _audit = _startup_edge()
    with edge:
        no_carrier = edge.request("GET", _ACME_TARGET, headers=bearer(STRANGER_BEARER))
        with_matching_carrier = edge.request("GET", _ACME_TARGET, headers={**bearer(STRANGER_BEARER), "X-Tenant-Id": ACME})
    assert no_carrier[0] == 403 and no_carrier[1] == b"", "a non-member is denied 403 with an empty body"
    assert with_matching_carrier[0] == 403 and with_matching_carrier[1] == b"", "a matching carrier changes nothing"
    assert provider.opened == [], "neither denial opens a tenant database"


def test_a10b_a_control_principal_reaching_a_tenant_route_is_denied() -> None:
    edge, provider, _auth, audit = _startup_edge()
    with edge:
        status, body, _headers = edge.request("GET", _ACME_TARGET, headers=bearer(CONTROL_BEARER))
    assert status == 403, "a tenantless CONTROL principal has no active tenant, so a tenant route is denied"
    assert body == b""
    assert provider.opened == [], "no default tenant is ever substituted"
    assert "RouteDenied" in audit.actions(), "the route denial must be audited"


def test_a10c_carrier_on_a_control_principal_is_ignored_and_audited() -> None:
    edge, provider, _auth, audit = _startup_edge()
    with edge:
        status, _body, _headers = edge.request("GET", _ACME_TARGET, headers={**bearer(CONTROL_BEARER), "X-Tenant-Id": ACME})
    assert status == 403, "the carrier is claim-only and never promotes a CONTROL principal into a tenant"
    assert provider.opened == []
    assert "CarrierOnControlAnomaly" in audit.actions(), "the carrier-on-CONTROL anomaly must be audited"


# ------------------------------------------------------------------------------------------
# A11 — exactly one tenant DB session per accepted request
# ------------------------------------------------------------------------------------------


def test_a11_one_accepted_request_opens_exactly_one_tenant_session() -> None:
    edge, provider, _auth, _audit = _startup_edge()
    with edge:
        assert edge.request("GET", _ACME_TARGET, headers=bearer(ACME_BEARER))[0] == 200
    assert len(provider.opened) == 1, f"exactly one tenant session per accepted request; got {provider.opened}"
    assert provider.opened == [(ACME, ACME_PRINCIPAL)]


def test_a11b_a_comma_joined_carrier_is_a_MISMATCH_not_a_straddle() -> None:
    # Named precisely. A comma-joined value is ONE carrier string, so it reaches the
    # authenticator and is rejected there as a mismatch — the straddle branch is NOT taken.
    # The distinction matters: only the real two-value cases below are rejected pre-auth.
    edge, provider, auth, audit = _startup_edge()
    with edge:
        status, body, _headers = edge.request(
            "GET",
            _ACME_TARGET,
            headers={**bearer(ACME_BEARER), "X-Tenant-Id": ACME + ", " + ZETA},
        )
    assert status == 403
    assert body == b""
    assert provider.opened == [], "a rejected multi-tenant assertion opens no database"
    assert audit.actions() == ["CarrierMismatch"], "it is audited as a mismatch, not an isolation anomaly"
    assert len(auth.calls) == 1, "a single carrier value legitimately reaches the carrier-match check"


def test_a11c_two_x_tenant_id_headers_are_a_STRADDLE_rejected_before_authentication() -> None:
    """The ordinary two-header form of a multi-tenant assertion.

    This is the case the straddle check exists for, and it is the one a mapping-shaped header
    view silently destroys: ``dict(request.headers)`` keeps only the first value, so the second
    tenant disappears before the kernel ever sees it and the request proceeds as an ordinary
    single-carrier one. The edge therefore hands the kernel the RAW ASGI header list.
    """
    edge, provider, auth, audit = _startup_edge()
    with edge:
        status, body, _headers = edge.request_raw(
            "GET",
            _ACME_TARGET,
            pairs=[("Authorization", "Bearer " + ACME_BEARER), ("X-Tenant-Id", ACME), ("X-Tenant-Id", ZETA)],
        )
    assert status == 403, "asserting two tenants in one request must be rejected"
    assert body == b""
    assert audit.actions() == ["IsolationAnomaly"], "it is the straddle class, not a carrier mismatch"
    assert auth.calls == [], "REJECTED BEFORE AUTHENTICATION — the authenticator is never reached"
    assert provider.opened == [], "and no tenant database is opened"


def test_a11d_a_subdomain_disagreeing_with_a_header_is_also_a_straddle() -> None:
    # The second reachable straddle shape: a host-derived carrier plus a disagreeing header.
    edge, provider, auth, audit = _startup_edge()
    with edge:
        status, _body, _headers = edge.request_raw(
            "GET",
            _ACME_TARGET,
            pairs=[("Host", ZETA + ".sp2.example.com"), ("Authorization", "Bearer " + ACME_BEARER), ("X-Tenant-Id", ACME)],
        )
    assert status == 403
    assert audit.actions() == ["IsolationAnomaly"]
    assert auth.calls == [], "rejected before authentication"
    assert provider.opened == []


def test_a11e_duplicate_identical_carriers_collapse_and_are_not_a_straddle() -> None:
    # Two occurrences of the SAME value assert one tenant, not two — it must not false-positive.
    edge, provider, _auth, _audit = _startup_edge()
    with edge:
        status, _body, _headers = edge.request_raw(
            "GET",
            _ACME_TARGET,
            pairs=[("Authorization", "Bearer " + ACME_BEARER), ("X-Tenant-Id", ACME), ("X-Tenant-Id", ACME)],
        )
    assert status == 200, "identical duplicates collapse to one carrier and the request proceeds"
    assert provider.opened == [(ACME, ACME_PRINCIPAL)]


# ------------------------------------------------------------------------------------------
# A12 / A13 — malformed and oversized inputs fail before any tenant DB access
# ------------------------------------------------------------------------------------------


def test_a12_malformed_startup_reference_fails_before_tenant_db_access() -> None:
    edge, provider, auth, _audit = _startup_edge()
    malformed = [
        "/tenant/startups/",  # empty reference
        "/tenant/startups/../../etc/passwd",  # traversal
        "/tenant/startups/%2e%2e%2f%2e%2e",  # percent-encoded traversal
        "/tenant/startups/a/b",  # multi-segment
        "/tenant/startups/" + "z" * 600,  # over the 512-byte bound
        "/tenant/startups/" + ACME_REF + "?tenant=" + ACME,  # query-bearing
        "/tenant/startups/.",  # bare dot
    ]
    with edge:
        results = [edge.request("GET", target, headers=bearer(ACME_BEARER))[0] for target in malformed]
    assert all(status in (404, 413) for status in results), f"every malformed reference must be refused; got {results}"
    assert provider.opened == [], "no malformed reference may reach a tenant database"
    assert auth.calls == [], "a malformed reference is refused BEFORE authentication is even attempted"


def test_a13_oversized_patch_fails_before_mutation() -> None:
    edge, provider, auth, _audit = _startup_edge()
    before = dict(provider.store(ACME)[ACME_REF])
    with edge:
        status, body, _headers = edge.request(
            "PATCH",
            _ACME_TARGET,
            headers={**bearer(ACME_BEARER), "Content-Type": "application/json"},
            body=b'{"short_description":"' + b"y" * 20000 + b'"}',
        )
    assert status == 413, "a body beyond the 16384-byte route budget is refused pre-handler"
    assert body == b""
    assert provider.opened == [], "an oversized body never reaches a tenant database"
    assert auth.calls == [], "an oversized body is refused BEFORE authentication"
    assert provider.store(ACME)[ACME_REF] == before, "nothing was mutated"


def test_a13b_an_over_bound_field_value_is_refused_after_authentication_with_no_write() -> None:
    # Within the transport budget but beyond the 500-character field bound: refused by the
    # owner-resident parser, before the executor, with no partial write.
    edge, provider, _auth, _audit = _startup_edge()
    with edge:
        status, _body, _headers = edge.request(
            "PATCH",
            _ACME_TARGET,
            headers={**bearer(ACME_BEARER), "Content-Type": "application/json"},
            body=b'{"short_description":"' + b"y" * 4000 + b'"}',
        )
    assert status == 403, "an over-bound field value is refused fail-closed"
    assert provider.opened == [], "the executor is never reached"
    assert provider.store(ACME)[ACME_REF]["short_description"] == "acme-private", "no partial write"


# ------------------------------------------------------------------------------------------
# A14 / A15 — missing configuration fails closed
# ------------------------------------------------------------------------------------------


def test_a14_missing_auth_configuration_fails_closed(monkeypatch) -> None:
    import control_plane.main as cp_main
    import database_router.main as dbr_main
    from control_plane.adapters.providers import http_public_workspace_edge as cp_edge
    from database_router.adapters.providers import http_public_startup_edge as dbr_edge

    monkeypatch.delenv(dbr_main.SP2_EDGE_AUTH_ROUTER_BASE_URL, raising=False)
    # RFC 2606 reserved host: structurally valid for the selector, and it can never resolve.
    # Naming a real standing port here would be a latent hazard — if composition ever gained a
    # build-time probe, this test would start dialling a standing edge.
    monkeypatch.setenv(dbr_main.SP2_DBR_ROUTING_READ_BASE_URL, "http://routing.invalid")
    assert dbr_main.build_public_boundary_from_env() is None, "no auth URL -> no boundary"
    assert dbr_main.build_public_startup_edge_deps_from_env() is None, "no boundary -> no public edge composes"
    assert cp_main.build_public_workspace_edge_deps_from_env() is None, "no boundary -> no public edge composes"
    for factory in (dbr_edge.create_app_from_env, cp_edge.create_app_from_env):
        try:
            factory()
        except RuntimeError:
            continue
        raise AssertionError(f"{factory.__module__} must refuse to compose an application without authentication")


def test_a14b_malformed_auth_configuration_raises_before_any_socket(monkeypatch) -> None:
    import database_router.main as dbr_main

    for bad in ("https://auth.example", "not-a-url", "ftp://x", "http://"):
        monkeypatch.setenv(dbr_main.SP2_EDGE_AUTH_ROUTER_BASE_URL, bad)
        try:
            dbr_main.build_public_boundary_from_env()
        except ValueError:
            continue
        raise AssertionError(f"malformed auth base URL {bad!r} must raise, never fall back to a stub")


def test_a15_missing_routing_configuration_fails_closed(monkeypatch) -> None:
    import database_router.main as dbr_main
    from database_router.adapters.providers import http_public_startup_edge as dbr_edge

    monkeypatch.setenv(dbr_main.SP2_EDGE_AUTH_ROUTER_BASE_URL, "http://auth.invalid")  # RFC 2606 reserved; never resolves
    monkeypatch.delenv(dbr_main.SP2_DBR_ROUTING_READ_BASE_URL, raising=False)
    assert dbr_main.build_public_startup_edge_deps_from_env() is None, "no routing association -> no public edge composes"
    assert dbr_main.build_public_startup_edge_server_from_env() is None, "an inactive composition binds no socket"
    try:
        dbr_edge.create_app_from_env()
    except RuntimeError:
        return
    raise AssertionError("the tenant Startup edge must refuse to compose without a routing association")


def test_a15b_a_routing_failure_at_request_time_collapses_to_503_without_detail() -> None:
    edge, provider, _auth, _audit = _startup_edge()
    provider.fail_with = LookupError("association missing for tenant t-acme at 127.0.0.1:5541")
    with edge:
        status, body, _headers = edge.request("GET", _ACME_TARGET, headers=bearer(ACME_BEARER))
    assert status == 503, "an unroutable tenant collapses to a fixed 503"
    assert body == b"", "no exception text, host, port, or tenant identity may leak"


# ------------------------------------------------------------------------------------------
# A16 — CORS admits only the configured origins
# ------------------------------------------------------------------------------------------


def test_a16_cors_permits_only_the_configured_origin() -> None:
    edge, _provider, _auth, _audit = _startup_edge(allowed_origins=(_FRONTEND_ORIGIN,))
    with edge:
        allowed = edge.request("GET", _ACME_TARGET, headers={**bearer(ACME_BEARER), "Origin": _FRONTEND_ORIGIN})
        denied = edge.request("GET", _ACME_TARGET, headers={**bearer(ACME_BEARER), "Origin": "http://evil.example"})
        preflight = edge.request("OPTIONS", _ACME_TARGET, headers={"Origin": _FRONTEND_ORIGIN})
        preflight_denied = edge.request("OPTIONS", _ACME_TARGET, headers={"Origin": "http://evil.example"})
    assert allowed[2].get("access-control-allow-origin") == _FRONTEND_ORIGIN, "the configured origin is echoed exactly"
    assert allowed[2].get("access-control-allow-credentials") == "false", "credentialed CORS is never emitted"
    assert "access-control-allow-origin" not in denied[2], "an unlisted origin receives NO CORS headers"
    assert preflight[0] == 204 and preflight[2].get("access-control-allow-origin") == _FRONTEND_ORIGIN
    assert "access-control-allow-origin" not in preflight_denied[2], "a preflight from an unlisted origin gets no grant"


def test_a16b_an_empty_allowlist_denies_every_origin() -> None:
    edge, _provider, _auth, _audit = _startup_edge(allowed_origins=())
    with edge:
        _status, _body, headers = edge.request("GET", _ACME_TARGET, headers={**bearer(ACME_BEARER), "Origin": _FRONTEND_ORIGIN})
    assert "access-control-allow-origin" not in headers, "an unconfigured edge grants no origin at all"
    assert "*" not in str(headers), "a wildcard origin is never emitted"


# ------------------------------------------------------------------------------------------
# A17 — correlation id is bounded, echoed, and usable
# ------------------------------------------------------------------------------------------


def test_a17_correlation_id_is_bounded_echoed_and_usable() -> None:
    edge, _provider, _auth, audit = _startup_edge()
    with edge:
        good = edge.request("GET", _ACME_TARGET, headers={**bearer(ACME_BEARER), "x-correlation-id": "trace-abc.123"})
        oversized = edge.request("GET", _ACME_TARGET, headers={**bearer(ACME_BEARER), "x-correlation-id": "c" * 400})
        unsafe = edge.request("GET", _ACME_TARGET, headers={**bearer(ACME_BEARER), "x-correlation-id": "bad id\twith space"})
        absent = edge.request("GET", _ACME_TARGET, headers=bearer(ACME_BEARER))
    assert good[2]["x-correlation-id"] == "trace-abc.123", "a bounded, safe id is accepted and echoed"
    assert oversized[2]["x-correlation-id"] != "c" * 400, "an oversized id is replaced by a minted one"
    assert unsafe[2]["x-correlation-id"] not in ("bad id\twith space", ""), "an unsafe id is replaced (anti-log-injection)"
    assert len(absent[2]["x-correlation-id"]) == 32, "an absent id is minted as an opaque 32-hex value"
    assert "trace-abc.123" in {e.correlation_id for e in audit.events}, "the accepted id reaches the audit record — it is usable"


# ------------------------------------------------------------------------------------------
# A18 / A19 — audit evidence and the fail-closed audit policy
# ------------------------------------------------------------------------------------------


def test_a18_minimum_mvp_audit_events_are_emitted_with_references_only() -> None:
    edge, _provider, _auth, audit = _startup_edge()
    with edge:
        assert edge.request("GET", _ACME_TARGET, headers=bearer(ACME_BEARER))[0] == 200
        assert (
            edge.request(
                "PATCH",
                _ACME_TARGET,
                headers={**bearer(ACME_BEARER), "Content-Type": "application/json"},
                body=b'{"short_description":"audited"}',
            )[0]
            == 200
        )
        assert edge.request("GET", _ACME_TARGET, headers=bearer(STRANGER_BEARER))[0] == 403
    actions = audit.actions()
    assert actions.count("tenant_startup_read") == 1, "exactly one read event per successful read"
    assert actions.count("tenant_startup_update") == 1, "exactly one update event per successful update"
    assert "RouteDenied" in actions, "a denial is evidenced"
    for event in audit.events:
        assert event.audit_id and event.occurred_at and event.event_version == 1, "every event carries its identity triple"
        rendered = repr(event)
        for forbidden_fragment in (ACME_SECRET_NAME, "acme-private", "audited", "Bearer", ACME_BEARER):
            assert forbidden_fragment not in rendered, f"audit records are references only; {forbidden_fragment!r} leaked"


def test_a18b_the_workspace_read_emits_exactly_one_event_including_an_empty_enumeration() -> None:
    edge, _auth, audit = _workspace_edge(memberships=())
    with edge:
        status, body, _headers = edge.request("GET", "/memberships", headers=bearer(ACME_BEARER))
    assert status == 200, "a principal with zero memberships is a lawful success"
    assert decode(body) == {"memberships": []}
    assert audit.actions() == ["workspace_memberships_read"], "exactly one event for a successful EMPTY enumeration"
    assert audit.events[0].actor_ref == audit.events[0].subject_ref == ACME_PRINCIPAL, "actor == subject == the authenticated principal"


def test_a19_a_terminal_audit_failure_fails_the_request_closed() -> None:
    # The declared MVP policy is FAIL-CLOSED for the durably homed classes: a success is never
    # handed back unless its evidence was accepted, and a denial is never handed back without
    # its record. This test pins both halves.
    edge, provider, _auth, audit = _startup_edge()
    audit.fail_with = EdgeAuditTransportError("unavailable")
    with edge:
        success_path = edge.request("GET", _ACME_TARGET, headers=bearer(ACME_BEARER))
        denial_path = edge.request("GET", _ACME_TARGET, headers=bearer(STRANGER_BEARER))
    assert success_path[0] == 503, "a success whose evidence cannot be recorded is NOT handed back"
    assert success_path[1] == b"", "and it discloses nothing"
    assert denial_path[0] == 503, "a denial whose record cannot be persisted fails closed too"
    assert provider.opened == [(ACME, ACME_PRINCIPAL)], "the read still happened; only the hand-back was refused"


# ------------------------------------------------------------------------------------------
# A20 — the internal lower-level edge cannot be used to bypass the public boundary
# ------------------------------------------------------------------------------------------


def test_a20_the_public_edge_never_reaches_the_internal_envelope_edge() -> None:
    # The public edge holds the executor in-process, so it neither imports nor constructs the
    # internal envelope edge. Asserted on the AST, not on substrings, and never on a docstring:
    # an earlier version of this test asserted that a docstring contained the word "boundary",
    # which is not a behavioural oracle and passed while the internal edge ran alongside it.
    import ast

    from database_router.adapters.providers import http_public_startup_edge as public_edge

    tree = ast.parse(pathlib.Path(public_edge.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(node.module + "." + alias.name for alias in node.names)
    assert not any("http_tenant_startup_api" in name for name in imported), "the public edge must not import the internal edge"
    called = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    called |= {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert "build_tenant_startup_server" not in called, "the public edge must not construct the internal edge"


def test_a20d_KNOWN_RESIDUAL_the_internal_envelope_edge_still_composes_under_mvp_env(monkeypatch) -> None:
    """A deliberately UNCOMFORTABLE test: it pins what is NOT true, so no one can claim it is.

    The MVP topology does not *launch* the internal envelope edge — but the module, its
    application factory and its serve entrypoint all remain, and its composition gate is the
    SAME variable (``SP2_DBR_ROUTING_READ_BASE_URL``) the public edge itself requires. So under
    exactly the Gateway-free MVP environment it composes perfectly well, and the standing
    launcher still starts it on 8004.

    "The hazard is deleted" would therefore be false; "the hazard is not launched" is true. The
    difference is a topology choice, not a structural guarantee, and closing it for real needs
    the later cleanup PR that deletes the module. This test exists so that distinction cannot
    quietly rot into the stronger claim.
    """
    import database_router.main as dbr_main

    monkeypatch.setenv(dbr_main.SP2_EDGE_AUTH_ROUTER_BASE_URL, "http://auth.invalid")
    monkeypatch.setenv(dbr_main.SP2_DBR_ROUTING_READ_BASE_URL, "http://routing.invalid")
    # Socket-inert on purpose: this proves composability without binding a listener.
    assert dbr_main.build_tenant_startup_ops_from_env() is not None, (
        "KNOWN RESIDUAL: the internal envelope edge's executor composes under the MVP environment"
    )
    assert dbr_main.build_public_startup_edge_deps_from_env() is not None, "and so does the public edge, from the same gate"


def test_a20b_positive_control_the_internal_edge_really_is_unauthenticated() -> None:
    # The positive control that makes A20 non-vacuous: the internal envelope edge, run here in
    # isolation, genuinely answers an ANONYMOUS caller and lets that caller name both the
    # tenant and the recorded actor. That is exactly the hazard the Gateway-free MVP topology
    # removes by not running this edge at all — and exactly why "just expose the internal API"
    # was never a lawful option.
    provider = TwoTenantProvider()
    server, base_url = build_tenant_startup_server(TenantStartupOperations(provider), "127.0.0.1", 0)
    internal = HostedEdge(server, base_url)
    envelope = (
        b'{"v":1,"startup_ref":"'
        + ACME_REF.encode()
        + b'","target_tenant_ref":"'
        + ACME.encode()
        + b'","correlation_id":"corr-anon","actor_ref":"anyone-at-all"}'
    )
    with internal:
        status, body, _headers = internal.request(
            "POST",
            "/internal/tenant/startups/read",
            headers={"Content-Type": "application/json"},
            body=envelope,
        )
    assert status == 200, "the internal edge answers an unauthenticated caller (the pre-existing hazard)"
    assert decode(body)["record"]["display_name"] == ACME_SECRET_NAME
    assert provider.opened == [(ACME, "anyone-at-all")], "the anonymous caller chose BOTH the tenant and the recorded actor"


def test_a20c_the_public_edge_exposes_no_internal_envelope_surface() -> None:
    """Probed with NO body, deliberately.

    An earlier version sent a 2-byte body on every probe. Every non-PATCH route has a body
    budget of zero, so all five probes were refused ``413`` by the transport gate BEFORE
    routing — the same status an EXISTING route returns for a body it will not accept. The
    oracle therefore could not distinguish "route absent" from "route present, body-bounded",
    and it passed unchanged against an application with the internal envelope route registered
    and leaking. Body-less probes reach the router, so ``404``/``405`` now genuinely means the
    surface is not exposed, and the positive control proves the probe shape reaches routes that
    DO exist.
    """
    edge, provider, _auth, _audit = _startup_edge()
    foreign = (
        "/internal/tenant/startups/read",
        "/internal/tenant/startups/update",
        "/memberships",
        "/import/x",
        "/directory/startup",
    )
    with edge:
        results = {path: edge.request("POST", path, headers=bearer(ACME_BEARER))[0] for path in foreign}
        own_route = edge.request("GET", _ACME_TARGET, headers=bearer(ACME_BEARER))[0]
    assert all(status in (404, 405) for status in results.values()), f"no internal or foreign surface is exposed; got {results}"
    assert own_route == 200, "POSITIVE CONTROL: the edge's own route IS served by the same probe shape"
    assert provider.opened == [(ACME, ACME_PRINCIPAL)], "only the positive control reached a tenant database"


# ------------------------------------------------------------------------------------------
# The workspace edge's own boundary (the second route family)
# ------------------------------------------------------------------------------------------


def test_w1_anonymous_memberships_read_is_denied() -> None:
    edge, _auth, _audit = _workspace_edge()
    with edge:
        status, body, _headers = edge.request("GET", "/memberships")
    assert status == 401
    assert body == b""


def test_w2_memberships_are_self_scoped_and_the_query_selector_is_unreachable() -> None:
    # The internal read dispatcher takes its subject from `?p=<principal_ref>`. The public edge
    # never exposes that: any query string at all is refused 404 before a handler runs, and the
    # subject is the authenticated principal in every case.
    edge, _auth, _audit = _workspace_edge(
        memberships=((ACME_PRINCIPAL, ACME, Role.TENANT_AGENT), (ZETA_PRINCIPAL, ZETA, Role.TENANT_AGENT))
    )
    with edge:
        mine = edge.request("GET", "/memberships", headers=bearer(ACME_BEARER))
        impersonation = edge.request("GET", "/memberships?p=" + ZETA_PRINCIPAL, headers=bearer(ACME_BEARER))
    assert mine[0] == 200
    assert decode(mine[1]) == {
        "memberships": [{"tenant_id": ACME, "role": "TENANT_AGENT", "display_ref": "ref:tenant/" + ACME + "/display"}]
    }
    assert impersonation[0] == 404, "a query-bearing target is not an exposed route"
    assert impersonation[1] == b""


def test_w3_a_zeta_principal_sees_only_zeta_memberships() -> None:
    edge, _auth, _audit = _workspace_edge(
        memberships=((ACME_PRINCIPAL, ACME, Role.TENANT_AGENT), (ZETA_PRINCIPAL, ZETA, Role.TENANT_AGENT))
    )
    with edge:
        status, body, _headers = edge.request("GET", "/memberships", headers=bearer(ZETA_BEARER))
    assert status == 200
    tenants = [entry["tenant_id"] for entry in decode(body)["memberships"]]
    assert tenants == [ZETA], f"a ZETA principal must see only its own memberships; got {tenants}"


def test_w4_operational_routes_are_non_disclosing_and_unauthenticated_by_design() -> None:
    edge, _auth, _audit = _workspace_edge()
    with edge:
        health = edge.request("GET", "/health")
        readiness = edge.request("GET", "/readiness")
    assert health[0] == 200 and readiness[0] == 200
    for payload in (decode(health[1]), decode(readiness[1])):
        rendered = str(payload).lower()
        # The edge's own service NAME is lawful operational status; a tenant identity, a database
        # name, a host/port, or any topology detail is not.
        for leak in (ACME, ZETA, "5540", "5541", "postgres", "dsn", "127.0.0.1"):
            assert leak not in rendered, f"readiness must not disclose {leak!r}"
