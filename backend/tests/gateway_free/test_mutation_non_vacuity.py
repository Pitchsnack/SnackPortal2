"""Mutation proofs: each security assertion above is shown to FAIL under a real defect.

A green suite is not evidence. For every load-bearing control in the Gateway-free MVP this
module installs a plausible defect into the LIVE decision function, re-drives the same request
through the same composed edge, and asserts the security property is now violated. A mutation
that survives would mean the corresponding adversarial test proves nothing.

Two rules the mutations follow, both learned from earlier arcs on this codebase:

* the mutation is applied to the executed function, never to a copy of the source, so no
  bytecode cache, import shadow, or stale ``.pyc`` can fake the result;
* detection is asserted on the strongest available oracle — usually ``provider.opened``, the
  record of which physical tenant databases were actually opened — because a status code alone
  can coincide with the safe answer for the wrong reason.
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

import shared.adapters.providers.public_edge_transport as transport  # noqa: E402
import shared.public_edge as kernel  # noqa: E402
from database_router.adapters.providers import http_public_startup_edge as edge_module  # noqa: E402
from database_router.adapters.providers.http_public_startup_edge import build_public_startup_edge_server  # noqa: E402
from database_router.tenant_startup_ops import TenantStartupOperations  # noqa: E402
from shared.adapters.providers.edge_audit import EdgeAuditTransportError  # noqa: E402

_ACME_TARGET = "/tenant/startups/" + ACME_REF
_ZETA_TARGET = "/tenant/startups/" + ZETA_REF
_FRONTEND_ORIGIN = "http://localhost:5173"


def _edge(allowed_origins=()):
    provider = TwoTenantProvider()
    boundary, auth, audit = build_boundary()
    server, base_url = build_public_startup_edge_server(
        TenantStartupOperations(provider), boundary, host="127.0.0.1", port=0, allowed_origins=allowed_origins
    )
    return HostedEdge(server, base_url), provider, auth, audit


# ------------------------------------------------------------------------------------------
# M1 — the tenant authority itself
# ------------------------------------------------------------------------------------------


def test_m1_trusting_the_carrier_instead_of_the_claim_is_DETECTED(monkeypatch) -> None:
    """The single most important control: tenant authority comes from the signed claim.

    The mutation is the exact defect the previous experiment found in the internal edge —
    honour the caller's asserted tenant. Under it a ZETA principal reads ACME.
    """
    original = kernel.PublicBoundary.require_tenant

    def mutated(self, principal):  # noqa: ANN001 — deliberate defect
        return ACME  # "trust whatever the caller asked for"

    edge, provider, _auth, _audit = _edge()
    with edge:
        clean = edge.request("GET", _ACME_TARGET, headers=bearer(ZETA_BEARER))
        clean_opened = list(provider.opened)
        monkeypatch.setattr(kernel.PublicBoundary, "require_tenant", mutated)
        breached = edge.request("GET", _ACME_TARGET, headers=bearer(ZETA_BEARER))
    monkeypatch.setattr(kernel.PublicBoundary, "require_tenant", original)

    assert clean[0] == 404 and clean_opened == [(ZETA, ZETA_PRINCIPAL)], "baseline: the ZETA principal binds ZETA"
    assert breached[0] == 200, "the mutation must actually change behaviour (otherwise it proves nothing)"
    assert decode(breached[1])["display_name"] == ACME_SECRET_NAME, "MUTATED: a ZETA principal read ACME's record"
    assert (ACME, ZETA_PRINCIPAL) in provider.opened, "DETECTOR: an ACME session was opened under a ZETA principal"


def test_m2_defaulting_a_tenantless_principal_is_DETECTED(monkeypatch) -> None:
    """A tenantless CONTROL principal must be denied, never silently defaulted to a tenant."""
    original = kernel.PublicBoundary.require_tenant

    def mutated(self, principal):  # noqa: ANN001 — deliberate defect
        return principal.active_tenant_id or ACME  # "fall back to the first tenant"

    edge, provider, _auth, _audit = _edge()
    with edge:
        clean = edge.request("GET", _ACME_TARGET, headers=bearer(CONTROL_BEARER))
        clean_opened = list(provider.opened)
        monkeypatch.setattr(kernel.PublicBoundary, "require_tenant", mutated)
        breached = edge.request("GET", _ACME_TARGET, headers=bearer(CONTROL_BEARER))
    monkeypatch.setattr(kernel.PublicBoundary, "require_tenant", original)

    assert clean[0] == 403 and clean_opened == [], "baseline: a tenantless principal is denied and opens nothing"
    assert breached[0] == 200, "the mutation must actually change behaviour"
    assert provider.opened == [(ACME, "p-control")], "DETECTOR: a tenantless principal opened a tenant database"


# ------------------------------------------------------------------------------------------
# M3 — authentication itself
# ------------------------------------------------------------------------------------------


def test_m3_skipping_authentication_is_DETECTED(monkeypatch) -> None:
    """If ``admit`` stopped denying, the anonymous-access tests must fail."""
    original = kernel.PublicBoundary.admit

    def mutated(self, request, correlation_id):  # noqa: ANN001 — deliberate defect
        return kernel.TrustedPrincipal(correlation_id=correlation_id, principal_ref="anonymous", active_tenant_id=ACME, role=None)

    edge, provider, _auth, _audit = _edge()
    with edge:
        clean = edge.request("GET", _ACME_TARGET)
        monkeypatch.setattr(kernel.PublicBoundary, "admit", mutated)
        breached = edge.request("GET", _ACME_TARGET)
    monkeypatch.setattr(kernel.PublicBoundary, "admit", original)

    assert clean[0] == 401, "baseline: anonymous is denied"
    assert breached[0] == 200, "the mutation must actually change behaviour"
    assert provider.opened == [(ACME, "anonymous")], "DETECTOR: an anonymous caller opened a tenant database"


def test_m4_ignoring_the_carrier_match_is_DETECTED(monkeypatch) -> None:
    """Dropping the carriers on the way to the authenticator disables the match-or-reject check."""
    original = kernel.recognized_carriers
    monkeypatch.setattr(kernel, "recognized_carriers", lambda request: [])

    edge, provider, _auth, audit = _edge()
    with edge:
        breached = edge.request("GET", _ZETA_TARGET, headers={**bearer(ZETA_BEARER), "X-Tenant-Id": ACME})
    monkeypatch.setattr(kernel, "recognized_carriers", original)

    # Baseline for the same request is 403 carrier_mismatch with nothing opened (test_a7).
    assert breached[0] == 200, "MUTATED: a disagreeing carrier was accepted instead of rejected"
    assert "CarrierMismatch" not in audit.actions(), "DETECTOR: the carrier-mismatch evidence disappeared"
    assert provider.opened == [(ZETA, ZETA_PRINCIPAL)], "the request proceeded despite the disagreeing carrier"


# ------------------------------------------------------------------------------------------
# M5 — the bounded request-target matcher
# ------------------------------------------------------------------------------------------


def test_m5_disabling_the_bounded_matcher_is_DETECTED(monkeypatch) -> None:
    """A permissive matcher lets a reference the charset forbids reach the executor.

    Choosing the probe matters. An OVER-BOUND (>512-byte) reference is re-validated by
    ``TenantStartupOperations`` before it opens a session, so under this mutation it still opens
    no database — a session-based detector alone would miss the defect, and a naive test would
    read that as "the matcher is redundant". The probe here is an UNSAFE-CHARSET reference,
    which the executor does NOT re-validate: with the matcher disabled it reaches a real tenant
    session. Both halves are asserted, so the two independent controls stay distinguishable.
    """
    edge, provider, _auth, _audit = _edge()
    unsafe_target = "/tenant/startups/" + ACME_REF + "';--"
    long_target = "/tenant/startups/" + "z" * 600
    with edge:
        clean_unsafe = edge.request("GET", unsafe_target, headers=bearer(ACME_BEARER))
        clean_long = edge.request("GET", long_target, headers=bearer(ACME_BEARER))
        clean_opened = list(provider.opened)
        monkeypatch.setattr(edge_module, "is_valid_tenant_startup_target", lambda target: True)
        breached_unsafe = edge.request("GET", unsafe_target, headers=bearer(ACME_BEARER))
        unsafe_opened = list(provider.opened)
        breached_long = edge.request("GET", long_target, headers=bearer(ACME_BEARER))

    assert clean_unsafe[0] == 404 and clean_long[0] == 404, "baseline: both malformed references are refused pre-core"
    assert clean_opened == [], "baseline: neither reaches a tenant session"
    assert unsafe_opened == [(ACME, ACME_PRINCIPAL)], "DETECTOR: the unsafe-charset reference reached a real tenant session"
    assert breached_unsafe[0] == 404, "it is then a not-found inside the bound tenant database"
    assert breached_long[0] == 503, "DETECTOR: the over-bound reference now fails in the EXECUTOR (404 -> 503), not at the edge"
    assert provider.opened == unsafe_opened, "the executor's own 512-byte bound still refuses before opening a session"


def _mutated_install(app, policy):  # noqa: ANN001 — the real transport gate minus the query branch
    """The real installer with EXACTLY the query-string rejection removed and nothing else."""

    @app.middleware("http")
    async def _transport(request, call_next):  # noqa: ANN001
        request.state.correlation_id = "fixed-correlation-id"
        request.state.raw_target = transport.raw_request_target(request)
        request.state.preflight = False
        request.state.cors_methods = policy.default_cors_methods
        request.state.cors_headers = policy.default_cors_headers
        return await call_next(request)


def test_m6_removing_the_query_rejection_is_SURVIVED_by_two_independent_controls(monkeypatch) -> None:
    """A NEGATIVE result, recorded because it changes how the control should be classified.

    The query-string rejection was expected to be MVP-essential. It is not. With the branch
    removed from the executed middleware, neither MVP route becomes exploitable, because two
    independent controls already cover it:

    * on the parameterized tenant Startup route, the bounded matcher decides against the RAW
      request target, and ``?`` is outside its charset — so the target is still ``404``;
    * on the static ``/memberships`` route the query IS now reachable, but no handler reads a
      query parameter: the subject is ``TrustedPrincipal.principal_ref`` and nothing else, so
      ``?p=<someone-else>`` returns the CALLER's own memberships.

    That makes the rejection MVP DEFENCE-IN-DEPTH rather than MVP ESSENTIAL, and it is recorded
    here as executed evidence rather than as an assumption. The mutation is applied to the
    composed middleware, so this is not a claim about what the code "would" do.
    """
    from control_plane.adapters.providers import http_public_workspace_edge as ws_module
    from control_plane.adapters.providers.http_public_workspace_edge import build_public_workspace_edge_server
    from control_plane.adapters.providers.in_memory_store import InMemoryControlStore
    from control_plane.main import ControlPlane
    from control_plane.records import Role

    startup_target = _ACME_TARGET + "?p=" + ZETA_PRINCIPAL
    clean_edge, clean_provider, _a, _b = _edge()
    with clean_edge:
        clean_startup = clean_edge.request("GET", startup_target, headers=bearer(ACME_BEARER))
    assert clean_startup[0] == 404 and clean_provider.opened == [], "baseline: a query-bearing target is not exposed"

    # --- the same request, with the query-rejection branch removed from BOTH composed edges ---
    monkeypatch.setattr(edge_module, "install_public_transport", _mutated_install)
    monkeypatch.setattr(ws_module, "install_public_transport", _mutated_install)

    provider = TwoTenantProvider()
    boundary, _auth, _audit = build_boundary()
    server, base_url = build_public_startup_edge_server(TenantStartupOperations(provider), boundary, host="127.0.0.1", port=0)
    with HostedEdge(server, base_url) as mutated_startup_edge:
        startup = mutated_startup_edge.request("GET", startup_target, headers=bearer(ACME_BEARER))

    control_plane = ControlPlane(store=InMemoryControlStore())
    control_plane.membership.add_membership(principal_ref=ACME_PRINCIPAL, tenant_id=ACME, role=Role.TENANT_AGENT)
    control_plane.membership.add_membership(principal_ref=ZETA_PRINCIPAL, tenant_id=ZETA, role=Role.TENANT_AGENT)
    ws_boundary, _auth2, _audit2 = build_boundary()
    ws_server, ws_base = build_public_workspace_edge_server(control_plane, ws_boundary, host="127.0.0.1", port=0)
    with HostedEdge(ws_server, ws_base) as mutated_ws_edge:
        workspace = mutated_ws_edge.request("GET", "/memberships?p=" + ZETA_PRINCIPAL, headers=bearer(ACME_BEARER))

    assert startup[0] == 404, "SURVIVED: the raw-target matcher independently refuses the query-bearing target"
    assert provider.opened == [], "and it still reaches no tenant database"
    assert workspace[0] == 200, "the static route IS now reachable with a query — the rejection really was removed"
    tenants = [entry["tenant_id"] for entry in decode(workspace[1])["memberships"]]
    assert tenants == [ACME], f"SURVIVED: `?p=` is not read; the caller still sees only its own memberships; got {tenants}"


# ------------------------------------------------------------------------------------------
# M7 — the bounded update parser
# ------------------------------------------------------------------------------------------


def test_m7_accepting_extra_body_fields_is_DETECTED(monkeypatch) -> None:
    """A permissive parser re-admits ``target_tenant_ref`` / ``actor_ref`` as request inputs."""
    from database_router.portal import TenantStartupUpdateRequestDTO

    def mutated(raw):  # noqa: ANN001 — deliberate defect
        import json

        body = json.loads(raw.decode("utf-8"))
        return TenantStartupUpdateRequestDTO(short_description=body.get("short_description"))

    edge, provider, _auth, _audit = _edge()
    payload = b'{"short_description":"x","target_tenant_ref":"' + ACME.encode() + b'","actor_ref":"' + ACME_PRINCIPAL.encode() + b'"}'
    headers = {**bearer(ZETA_BEARER), "Content-Type": "application/json"}
    with edge:
        clean = edge.request("PATCH", _ZETA_TARGET, headers=headers, body=payload)
        clean_opened = list(provider.opened)
        monkeypatch.setattr(edge_module, "parse_tenant_startup_update_request", mutated)
        breached = edge.request("PATCH", _ZETA_TARGET, headers=headers, body=payload)

    assert clean[0] == 403 and clean_opened == [], "baseline: an extra field is refused before the executor"
    assert breached[0] == 200, "MUTATED: the body with extra fields was accepted"
    # The mutation re-opens the CHANNEL. The architecture still refuses to READ those fields, so
    # the write stays in ZETA — that separation is itself the finding, and it is why the strict
    # parser is defence-in-depth rather than the primary control.
    assert provider.opened == [(ZETA, ZETA_PRINCIPAL)], "the tenant is still the signed claim, not the body field"
    assert provider.store(ACME)[ACME_REF]["short_description"] == "acme-private", "ACME remains untouched even under M7"


def test_m8_removing_the_field_length_bound_is_DETECTED(monkeypatch) -> None:
    """The 500-character bound is genuinely DEFENCE-IN-DEPTH, and the test says which layer caught it.

    With the edge parser's bound removed, the over-bound value is refused by
    ``TenantStartupOperations`` — before it opens a session, so no database is touched and the
    stored value is unchanged. The detector is therefore the layer transition (403 at the edge
    becomes 503 from the executor), not a write that got through. Recording it this way keeps a
    later reader from concluding either "the bound is redundant" or "the bound is the only thing
    stopping a write"; neither is true.
    """
    from database_router.portal import TenantStartupUpdateRequestDTO

    def mutated(raw):  # noqa: ANN001 — deliberate defect
        import json

        return TenantStartupUpdateRequestDTO(short_description=json.loads(raw.decode("utf-8"))["short_description"])

    edge, provider, _auth, _audit = _edge()
    payload = b'{"short_description":"' + b"y" * 4000 + b'"}'
    headers = {**bearer(ACME_BEARER), "Content-Type": "application/json"}
    with edge:
        clean = edge.request("PATCH", _ACME_TARGET, headers=headers, body=payload)
        clean_opened = list(provider.opened)
        monkeypatch.setattr(edge_module, "parse_tenant_startup_update_request", mutated)
        breached = edge.request("PATCH", _ACME_TARGET, headers=headers, body=payload)

    assert clean[0] == 403 and clean_opened == [], "baseline: the over-bound value is refused by the edge parser"
    assert breached[0] == 503, "DETECTOR: with the edge bound removed the refusal comes from the EXECUTOR (403 -> 503)"
    assert provider.opened == [], "the executor refuses BEFORE opening a session, so no database is touched either way"
    assert provider.store(ACME)[ACME_REF]["short_description"] == "acme-private", "still no write — the bound genuinely survives"


# ------------------------------------------------------------------------------------------
# M9 — the audit posture
# ------------------------------------------------------------------------------------------


def test_m9_making_the_audit_fail_open_is_DETECTED(monkeypatch) -> None:
    """The declared MVP policy is fail-CLOSED. A swallowed sink failure must be detectable."""
    original = kernel.PublicBoundary.emit

    def mutated(self, action, outcome, correlation_id, **kwargs):  # noqa: ANN001 — deliberate defect
        try:
            original(self, action, outcome, correlation_id, **kwargs)
        except Exception:
            return  # "don't let audit break the request"

    edge, provider, _auth, audit = _edge()
    audit.fail_with = EdgeAuditTransportError("unavailable")
    with edge:
        clean = edge.request("GET", _ACME_TARGET, headers=bearer(ACME_BEARER))
        monkeypatch.setattr(kernel.PublicBoundary, "emit", mutated)
        breached = edge.request("GET", _ACME_TARGET, headers=bearer(ACME_BEARER))
    monkeypatch.setattr(kernel.PublicBoundary, "emit", original)

    assert clean[0] == 503, "baseline: a success without recordable evidence is NOT handed back"
    assert breached[0] == 200, "MUTATED: the record was served with no audit evidence at all"
    assert audit.events == [], "DETECTOR: the tenant record was disclosed while the evidence set stayed empty"
    assert provider.opened, "the read did happen in both cases; only the hand-back differed"


# ------------------------------------------------------------------------------------------
# M10 — the browser boundary
# ------------------------------------------------------------------------------------------


def test_m10_widening_cors_to_a_wildcard_is_DETECTED(monkeypatch) -> None:
    edge, _provider, _auth, _audit = _edge(allowed_origins=(_FRONTEND_ORIGIN,))

    def mutated(response, origin, allowed_origins, *, preflight, cors_methods, cors_headers):  # noqa: ANN001 — deliberate defect
        response.headers["Access-Control-Allow-Origin"] = "*"

    with edge:
        clean = edge.request("GET", _ACME_TARGET, headers={**bearer(ACME_BEARER), "Origin": "http://evil.example"})
        monkeypatch.setattr(transport, "_write_cors_headers", mutated)
        breached = edge.request("GET", _ACME_TARGET, headers={**bearer(ACME_BEARER), "Origin": "http://evil.example"})

    assert "access-control-allow-origin" not in clean[2], "baseline: an unlisted origin gets no CORS grant"
    assert breached[2].get("access-control-allow-origin") == "*", "DETECTOR: a wildcard grant reached an unlisted origin"


def test_m11_accepting_an_unbounded_correlation_id_is_DETECTED(monkeypatch) -> None:
    edge, _provider, _auth, _audit = _edge()
    with edge:
        clean = edge.request("GET", _ACME_TARGET, headers={**bearer(ACME_BEARER), "x-correlation-id": "c" * 400})
        monkeypatch.setattr(transport, "_correlation_id", lambda request: request.headers.get("x-correlation-id") or "")
        breached = edge.request("GET", _ACME_TARGET, headers={**bearer(ACME_BEARER), "x-correlation-id": "c" * 400})

    assert clean[2]["x-correlation-id"] != "c" * 400, "baseline: an oversized id is replaced by a minted one"
    assert breached[2]["x-correlation-id"] == "c" * 400, "DETECTOR: the unbounded caller-supplied id was echoed verbatim"


def test_m11b_a_correlation_id_carrying_a_header_injection_payload_is_rejected() -> None:
    """The anti-log-injection half of the same control, driven with a real CRLF payload.

    The previous version of this test asserted on a non-empty local variable that was never
    sent anywhere — unconditionally true, and therefore no coverage at all.
    """
    edge, _provider, _auth, audit = _edge()
    with edge:
        status, _body, headers = edge.request_raw(
            "GET",
            _ACME_TARGET,
            pairs=[("Authorization", "Bearer " + ACME_BEARER), ("x-correlation-id", "ok-prefix\tX-Injected: yes")],
        )
    assert status == 200
    echoed = headers["x-correlation-id"]
    assert "X-Injected" not in echoed and "\t" not in echoed, "an injection payload must never be echoed"
    assert len(echoed) == 32, "it is replaced by a freshly minted opaque id"
    assert all("X-Injected" not in (event.correlation_id or "") for event in audit.events), "nor reach an audit record"


def test_m12_collapsing_headers_into_a_mapping_makes_the_STRADDLE_CHECK_UNREACHABLE(monkeypatch) -> None:
    """The defect an independent review found in this experiment's first implementation.

    The edges originally handed the kernel ``dict(request.headers)``. HTTP allows a header name
    to repeat, and a mapping keeps only the FIRST value — so two ``X-Tenant-Id`` headers, the
    ordinary way a client asserts two tenants in one request, were silently reduced to one and
    the straddle branch could never execute. The request then proceeded as an ordinary
    single-carrier one.

    Nothing was exploitable (authority is the signed claim either way), but an advertised
    control was unreachable by the exact mechanism it exists to catch. This mutation restores
    the old collapsing view and asserts the control goes dark.
    """
    edge, provider, auth, audit = _edge()
    pairs = [("Authorization", "Bearer " + ACME_BEARER), ("X-Tenant-Id", ACME), ("X-Tenant-Id", ZETA)]
    with edge:
        clean = edge.request_raw("GET", _ACME_TARGET, pairs=pairs)
        clean_actions = list(audit.actions())
        clean_auth_calls = list(auth.calls)
        # The mutation: reduce the raw pair list to a first-value-wins mapping, exactly as
        # dict(request.headers) did.
        monkeypatch.setattr(edge_module, "_raw_headers", lambda request: list(dict(request.headers).items()))
        breached = edge.request_raw("GET", _ACME_TARGET, pairs=pairs)

    assert clean[0] == 403 and clean_actions == ["IsolationAnomaly"], "baseline: the straddle is caught"
    assert clean_auth_calls == [], "baseline: and caught BEFORE authentication"
    assert breached[0] == 200, "MUTATED: the second asserted tenant vanished and the request was served"
    assert "IsolationAnomaly" not in audit.actions()[len(clean_actions) :], "DETECTOR: the straddle evidence disappeared"
    assert provider.opened == [(ACME, ACME_PRINCIPAL)], "the request proceeded on the first carrier alone"
