"""Behavioral loopback tests for the served API Gateway Edge (real HTTP round-trips).

Hosts the genuine single-threaded stdlib edge on an ephemeral loopback port in a test-only daemon
thread and exercises it over real HTTP (via ``http.client``, for precise control of the request
target, Host, headers and body). The Gateway core is composed from the accepted api_gateway test
doubles (a stub authenticator + a stub Control-Plane read); no network, no database, no live
PostgreSQL. Proves the §12 behavioral matrix: success + empty success, the fail-closed 401/403/503
denials (empty body, no detail), the pre-core 404/405/413/400 transport rejections, correlation
accept/mint/echo, exact-origin CORS (allowed + denied), the operational health/readiness routes, and
that ``Gateway.handle`` is called exactly once for a valid business request and zero times for any
pre-core rejection or operational route.

Runnable standalone:  python tests/api_gateway/test_http_gateway_edge.py
"""

from __future__ import annotations

import http.client
import json
import pathlib
import sys
import threading
from typing import Dict, Iterator, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import contextlib  # noqa: E402

import _h  # noqa: E402
from _gateway_doubles import (  # noqa: E402
    RecordingAuditEmitter,
    StubAuthenticator,
    StubControlPlaneRead,
    StubRouterDispatch,
)

from api_gateway.adapters.providers.http_gateway_edge import build_gateway_edge_server  # noqa: E402
from api_gateway.main import ClmDurableAuditPartition, build_gateway  # noqa: E402
from api_gateway.models import AuditAction, GatewayAuditEvent  # noqa: E402
from api_gateway.portal import MembershipEntryDTO  # noqa: E402
from api_gateway.ports import AuditEmitterPort, ImportInitiationOutcome, ImportInitiationPort, ImportInitiationRequest  # noqa: E402

_CTL_TOKEN = "tok-ctl"
_TENANT_TOKEN = "tok-t1"
_MEMBERSHIP = MembershipEntryDTO(tenant_id="t1", role="TENANT_AGENT", display_ref="ref:tenant/t1/display")


class _StubImportInitiation(ImportInitiationPort):
    """W1b local references-only ``ImportInitiationPort`` double (stays inside this file — the shared
    ``_gateway_doubles.py`` remains byte-unchanged). Records the request(s) the gateway hands over and
    returns a canned ``ImportInitiationOutcome`` (no network, no database, no real Import Service)."""

    def __init__(self, outcome: ImportInitiationOutcome) -> None:
        self._outcome = outcome
        self.requests: List[ImportInitiationRequest] = []

    def initiate(self, request: ImportInitiationRequest) -> ImportInitiationOutcome:
        self.requests.append(request)
        return self._outcome


def _import_outcome(
    *,
    ok: bool = True,
    state: str = "applied",
    replayed: bool = False,
    applied_count: int = 1,
    noop_count: int = 0,
    import_id: str = "job-1",
) -> ImportInitiationOutcome:
    return ImportInitiationOutcome(
        ok=ok, state=state, replayed=replayed, applied_count=applied_count, noop_count=noop_count, import_id=import_id
    )


class _CountingGateway:
    """Wraps a composed Gateway and counts ``handle`` calls (proves exactly-once / never)."""

    def __init__(self, inner: object) -> None:
        self._inner = inner
        self.calls = 0

    def handle(self, request: object) -> object:
        self.calls += 1
        return self._inner.handle(request)  # type: ignore[attr-defined]


@contextlib.contextmanager
def _serve(
    control_read: object,
    *,
    allowed_origins: Tuple[str, ...] = (),
    import_initiation: Optional[ImportInitiationPort] = None,
) -> Iterator[Tuple[str, _CountingGateway, RecordingAuditEmitter]]:
    authn = StubAuthenticator()
    # The stub keys tokens by the verbatim Authorization value the edge forwards (the core does not
    # strip "Bearer " — the real IC-005 authenticator does; the stub stands in for it), so register
    # the full header value.
    authn.add_token("Bearer " + _CTL_TOKEN, principal="ops", tenant=None, role="CONTROL")
    authn.add_token("Bearer " + _TENANT_TOKEN, principal="p1", tenant="t1", role="TENANT_AGENT")
    router = StubRouterDispatch()
    audit = RecordingAuditEmitter()
    gateway = build_gateway(authenticator=authn, router=router, control_read=control_read, audit=audit, import_initiation=import_initiation)
    counting = _CountingGateway(gateway)
    server, base_url = build_gateway_edge_server(counting, host="127.0.0.1", port=0, allowed_origins=allowed_origins)  # type: ignore[arg-type]
    netloc = base_url.split("://", 1)[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield netloc, counting, audit
    finally:
        server.shutdown()
        thread.join(timeout=10.0)
        server.server_close()


def _request(
    netloc: str,
    path: str,
    *,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[bytes] = None,
    host: str = "example.com",
) -> Tuple[int, Dict[str, str], bytes]:
    """One real HTTP round-trip. ``host`` sets the Host header explicitly (default a subdomain-less
    host so 127.0.0.1 does not spuriously assert a tenant-subdomain carrier)."""
    conn = http.client.HTTPConnection(netloc, timeout=5.0)
    try:
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", host)
        for key, value in (headers or {}).items():
            conn.putheader(key, value)
        if body is not None:
            conn.putheader("Content-Length", str(len(body)))
        conn.endheaders(message_body=body)
        resp = conn.getresponse()
        data = resp.read()
        return resp.status, {k.lower(): v for k, v in resp.getheaders()}, data
    finally:
        conn.close()


def _bearer(token: str) -> Dict[str, str]:
    return {"Authorization": "Bearer " + token}


# --- success paths --------------------------------------------------------------------------------
def test_valid_memberships_returns_200_dto_and_calls_handle_once() -> None:
    cr = StubControlPlaneRead(mode="success", memberships=(_MEMBERSHIP,))
    with _serve(cr) as (netloc, counting, _audit):
        status, hdrs, body = _request(netloc, "/memberships", headers=_bearer(_CTL_TOKEN))
    assert status == 200, f"valid memberships must be 200; got {status}"
    assert hdrs.get("content-type") == "application/json"
    assert hdrs.get("cache-control") == "no-store"
    assert json.loads(body) == {"memberships": [{"tenant_id": "t1", "role": "TENANT_AGENT", "display_ref": "ref:tenant/t1/display"}]}
    assert counting.calls == 1, "Gateway.handle must be called exactly once for a valid business request"


def test_empty_memberships_is_lawful_200() -> None:
    with _serve(StubControlPlaneRead(mode="empty")) as (netloc, _c, _a):
        status, _hdrs, body = _request(netloc, "/memberships", headers=_bearer(_CTL_TOKEN))
    assert status == 200 and json.loads(body) == {"memberships": []}, "an empty membership set is a lawful 200"


# --- fail-closed denials (empty body, no detail) --------------------------------------------------
def test_missing_bearer_is_401() -> None:
    with _serve(StubControlPlaneRead(mode="success")) as (netloc, counting, _a):
        status, _hdrs, body = _request(netloc, "/memberships")
    assert status == 401 and body == b"", "missing bearer must be a 401 with no body"
    assert counting.calls == 1, "the core is invoked once and rejects (auth is core-owned)"


def test_invalid_bearer_is_401() -> None:
    with _serve(StubControlPlaneRead(mode="success")) as (netloc, _c, _a):
        status, _hdrs, _body = _request(netloc, "/memberships", headers=_bearer("nope"))
    assert status == 401, "an unknown bearer must be a 401"


def test_forbidden_is_403() -> None:
    cr = StubControlPlaneRead(mode="success", memberships=(_MEMBERSHIP,))
    authn = StubAuthenticator()
    authn.add_token("Bearer " + _CTL_TOKEN, principal="ops", tenant=None, role="CONTROL")
    authn.set_deny_access()
    router = StubRouterDispatch()
    audit = RecordingAuditEmitter()
    gateway = build_gateway(authenticator=authn, router=router, control_read=cr, audit=audit)
    counting = _CountingGateway(gateway)
    server, base_url = build_gateway_edge_server(counting, host="127.0.0.1", port=0)  # type: ignore[arg-type]
    netloc = base_url.split("://", 1)[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _hdrs, body = _request(netloc, "/memberships", headers=_bearer(_CTL_TOKEN))
    finally:
        server.shutdown()
        thread.join(timeout=10.0)
        server.server_close()
    assert status == 403 and body == b"", "a denied principal must be a 403 with no body"


def test_carrier_mismatch_is_403_with_carrier_audit() -> None:
    # A tenant-scoped token + a DIFFERENT single carrier (X-Tenant-Id) -> carrier_mismatch (403).
    cr = StubControlPlaneRead(mode="success", memberships=(_MEMBERSHIP,))
    with _serve(cr) as (netloc, _c, audit):
        headers = {**_bearer(_TENANT_TOKEN), "X-Tenant-Id": "t2"}
        status, _hdrs, body = _request(netloc, "/memberships", headers=headers, host="example.com")
    assert status == 403 and body == b"", "a carrier mismatch must be a 403 with no body"
    assert any(e.action is AuditAction.CARRIER_MISMATCH for e in audit.events), "carrier mismatch must emit the CarrierMismatch audit"


def test_isolation_anomaly_straddle_is_403() -> None:
    # Two distinct carriers (Host subdomain t1 + X-Tenant-Id t2) -> isolation anomaly (403).
    cr = StubControlPlaneRead(mode="success", memberships=(_MEMBERSHIP,))
    with _serve(cr) as (netloc, _c, audit):
        headers = {**_bearer(_CTL_TOKEN), "X-Tenant-Id": "t2"}
        status, _hdrs, body = _request(netloc, "/memberships", headers=headers, host="t1.example.com")
    assert status == 403 and body == b"", "a carrier straddle must be a 403 with no body"
    assert any(e.action is AuditAction.ISOLATION_ANOMALY for e in audit.events), "a straddle must emit the IsolationAnomaly audit"


def test_forwarded_host_is_not_trusted() -> None:
    # X-Forwarded-Host must never become a tenant selector or security decision: the edge derives
    # the host from the real Host header only. A forwarded subdomain + X-Tenant-Id would straddle
    # (403) IF the forwarded host were trusted; because it is ignored, a CONTROL token yields a
    # lawful 200 (the forwarded value is dropped, not honored).
    with _serve(StubControlPlaneRead(mode="empty")) as (netloc, _c, _a):
        headers = {**_bearer(_CTL_TOKEN), "X-Forwarded-Host": "t1.evil.example", "X-Tenant-Id": "t2"}
        status, _hdrs, _body = _request(netloc, "/memberships", headers=headers, host="example.com")
    assert status == 200, "the edge must ignore X-Forwarded-* (a forwarded host must not create a carrier/straddle)"


def test_control_read_unavailable_is_503() -> None:
    with _serve(StubControlPlaneRead(mode="unavailable")) as (netloc, _c, _a):
        status, _hdrs, body = _request(netloc, "/memberships", headers=_bearer(_CTL_TOKEN))
    assert status == 503 and body == b"", "an unavailable control read must be a 503 with no detail"


def test_malformed_control_response_is_503() -> None:
    with _serve(StubControlPlaneRead(mode="malformed")) as (netloc, _c, _a):
        status, _hdrs, body = _request(netloc, "/memberships", headers=_bearer(_CTL_TOKEN))
    assert status == 503 and body == b"", "a malformed control response must collapse to 503 (no provider body)"


# --- pre-core transport rejections (Gateway.handle never reached) ---------------------------------
def test_post_memberships_is_405_pre_core() -> None:
    with _serve(StubControlPlaneRead(mode="success")) as (netloc, counting, _a):
        status, _hdrs, _body = _request(netloc, "/memberships", method="POST", headers=_bearer(_CTL_TOKEN))
    assert status == 405, "POST on an exposed route must be 405"
    assert counting.calls == 0, "a method rejection must never reach the core"


def test_unknown_and_reserved_routes_are_404_pre_core() -> None:
    with _serve(StubControlPlaneRead(mode="success")) as (netloc, counting, _a):
        for path in ("/directory", "/tenant", "/import", "/nope", "/memberships/extra", "/memberships?p=evil"):
            status, _hdrs, _body = _request(netloc, path, headers=_bearer(_CTL_TOKEN))
            assert status == 404, f"non-exposed route {path} must be 404; got {status}"
    assert counting.calls == 0, "a route rejection must never reach the core"


def test_get_with_body_is_rejected_pre_core() -> None:
    with _serve(StubControlPlaneRead(mode="success")) as (netloc, counting, _a):
        status, _hdrs, _body = _request(netloc, "/memberships", headers=_bearer(_CTL_TOKEN), body=b"x")
    assert status in (400, 413), "a non-empty body on GET must be rejected pre-core"
    assert counting.calls == 0, "a bounds rejection must never reach the core"


def test_oversized_request_target_is_413() -> None:
    with _serve(StubControlPlaneRead(mode="success")) as (netloc, _c, _a):
        status, _hdrs, _body = _request(netloc, "/" + "a" * 3000, headers=_bearer(_CTL_TOKEN))
    assert status == 413, "an oversized request target must be 413"


def test_oversized_header_is_413() -> None:
    with _serve(StubControlPlaneRead(mode="success")) as (netloc, _c, _a):
        headers = {**_bearer(_CTL_TOKEN), "X-Big": "z" * 20000}
        status, _hdrs, _body = _request(netloc, "/memberships", headers=headers)
    assert status == 413, "oversized total header bytes must be 413"


# --- correlation accept / mint / echo -------------------------------------------------------------
def test_valid_correlation_is_echoed() -> None:
    with _serve(StubControlPlaneRead(mode="empty")) as (netloc, _c, _a):
        headers = {**_bearer(_CTL_TOKEN), "X-Correlation-Id": "corr-abc.123"}
        status, hdrs, _body = _request(netloc, "/memberships", headers=headers)
    assert status == 200 and hdrs.get("x-correlation-id") == "corr-abc.123", "a valid correlation id must be echoed verbatim"


def test_missing_correlation_is_minted_and_echoed() -> None:
    with _serve(StubControlPlaneRead(mode="empty")) as (netloc, _c, _a):
        status, hdrs, _body = _request(netloc, "/memberships", headers=_bearer(_CTL_TOKEN))
    echoed = hdrs.get("x-correlation-id")
    assert status == 200 and echoed and len(echoed) >= 8, "a missing correlation id must be minted and echoed"


def test_malformed_correlation_is_replaced_and_echoed() -> None:
    with _serve(StubControlPlaneRead(mode="empty")) as (netloc, _c, _a):
        headers = {**_bearer(_CTL_TOKEN), "X-Correlation-Id": "bad id with spaces!!"}
        status, hdrs, _body = _request(netloc, "/memberships", headers=headers)
    echoed = hdrs.get("x-correlation-id")
    assert status == 200 and echoed and echoed != "bad id with spaces!!", "a malformed correlation id must be replaced with a minted one"


# --- CORS ------------------------------------------------------------------------------------------
def test_allowed_cors_preflight_is_204_with_exact_origin_headers() -> None:
    origin = "https://ok.example"
    with _serve(StubControlPlaneRead(mode="success"), allowed_origins=(origin,)) as (netloc, counting, _a):
        status, hdrs, _body = _request(netloc, "/memberships", method="OPTIONS", headers={"Origin": origin})
    assert status == 204, f"an allowed preflight must be 204; got {status}"
    assert hdrs.get("access-control-allow-origin") == origin, "the exact origin must be echoed"
    assert hdrs.get("access-control-allow-credentials") == "false", "credentialed CORS must never be enabled"
    assert hdrs.get("access-control-allow-methods") == "GET, OPTIONS"
    assert "authorization" in (hdrs.get("access-control-allow-headers") or "").lower()
    assert counting.calls == 0, "a CORS preflight must never reach the core"


def test_denied_cors_origin_gets_no_permissive_headers() -> None:
    with _serve(StubControlPlaneRead(mode="success"), allowed_origins=("https://ok.example",)) as (netloc, _c, _a):
        status, hdrs, _body = _request(netloc, "/memberships", method="OPTIONS", headers={"Origin": "https://evil.example"})
    assert status == 204, "a denied preflight is still answered (204) but carries no permissive headers"
    assert "access-control-allow-origin" not in hdrs, "a denied origin must receive no CORS headers"


def test_success_response_to_denied_origin_carries_no_cors() -> None:
    with _serve(StubControlPlaneRead(mode="empty"), allowed_origins=("https://ok.example",)) as (netloc, _c, _a):
        headers = {**_bearer(_CTL_TOKEN), "Origin": "https://evil.example"}
        status, hdrs, _body = _request(netloc, "/memberships", headers=headers)
    assert status == 200 and "access-control-allow-origin" not in hdrs, "a disallowed origin gets a body but no CORS grant"


# --- operational routes ---------------------------------------------------------------------------
def test_health_is_200_and_core_untouched() -> None:
    with _serve(StubControlPlaneRead(mode="success")) as (netloc, counting, _a):
        status, hdrs, body = _request(netloc, "/health")
    assert status == 200 and json.loads(body).get("status") == "alive"
    assert hdrs.get("x-correlation-id"), "operational routes still echo a correlation id"
    assert counting.calls == 0, "operational routes must never reach the core"


def test_readiness_is_200_without_overclaim() -> None:
    with _serve(StubControlPlaneRead(mode="success")) as (netloc, counting, _a):
        status, _hdrs, body = _request(netloc, "/readiness")
    parsed = json.loads(body)
    assert status == 200 and "state" in parsed, "readiness reports in-process state only (no production-readiness overclaim)"
    assert "database" not in parsed and "tenant" not in parsed, "readiness must disclose no tenant/DB detail"
    assert counting.calls == 0, "readiness must never reach the core"


# --- served import route (W1b): POST /import/<source_ref> --------------------------------------------
# The port-composed import success (200 + ImportResultDTO). A bounded, traversal-safe MULTI-segment
# source_ref is accepted; the core executes exactly once and the edge serializes only the real result.
def test_post_import_multisegment_source_created_returns_200_result_dto_and_calls_handle_once() -> None:
    stub = _StubImportInitiation(_import_outcome(applied_count=1, noop_count=0, import_id="job-9"))
    with _serve(StubControlPlaneRead(mode="success"), import_initiation=stub) as (netloc, counting, _a):
        status, hdrs, body = _request(netloc, "/import/global-startup/rec-9", method="POST", headers=_bearer(_TENANT_TOKEN))
    assert status == 200, f"a created import must be 200; got {status}"
    assert hdrs.get("content-type") == "application/json" and hdrs.get("cache-control") == "no-store"
    payload = json.loads(body)
    assert payload["outcome"] == "created", "an applied import composes the created ImportResultDTO"
    assert payload["source_ref"] == "global-startup/rec-9" and payload["target_tenant_ref"] == "t1"
    assert payload["tenant_record_ref"] == "t1:startups:global-startup/rec-9", "the multi-segment source_ref flows through verbatim"
    assert counting.calls == 1, "Gateway.handle must be called exactly once for a valid import request"
    assert len(stub.requests) == 1 and stub.requests[0].source_ref == "global-startup/rec-9"


def test_post_import_replayed_returns_200() -> None:
    stub = _StubImportInitiation(_import_outcome(replayed=True, applied_count=0, noop_count=1))
    with _serve(StubControlPlaneRead(mode="success"), import_initiation=stub) as (netloc, _c, _a):
        status, _hdrs, body = _request(netloc, "/import/g1", method="POST", headers=_bearer(_TENANT_TOKEN))
    assert status == 200 and json.loads(body)["outcome"] == "replayed", "a replayed import is a lawful 200 ImportResultDTO"


def test_post_import_noop_returns_200() -> None:
    stub = _StubImportInitiation(_import_outcome(replayed=False, applied_count=0, noop_count=1))
    with _serve(StubControlPlaneRead(mode="success"), import_initiation=stub) as (netloc, _c, _a):
        status, _hdrs, body = _request(netloc, "/import/g1", method="POST", headers=_bearer(_TENANT_TOKEN))
    assert status == 200 and json.loads(body)["outcome"] == "noop", "a noop import is a lawful 200 ImportResultDTO"


def test_post_import_zero_record_is_403_no_body() -> None:
    # A zero-record completion (applied=0, noop=0) is the LW-1 consistent denial: 403, no body, no DTO.
    stub = _StubImportInitiation(_import_outcome(applied_count=0, noop_count=0))
    with _serve(StubControlPlaneRead(mode="success"), import_initiation=stub) as (netloc, _c, _a):
        status, _hdrs, body = _request(netloc, "/import/g1", method="POST", headers=_bearer(_TENANT_TOKEN))
    assert status == 403 and body == b"", "a zero-record import must be a 403 with no body"


def test_post_import_engine_failure_is_503_no_body() -> None:
    # A transport/engine failure (ok=False) collapses fail-closed to 503, empty body — no detail.
    stub = _StubImportInitiation(_import_outcome(ok=False, state="", applied_count=0, noop_count=0, import_id=""))
    with _serve(StubControlPlaneRead(mode="success"), import_initiation=stub) as (netloc, _c, _a):
        status, _hdrs, body = _request(netloc, "/import/g1", method="POST", headers=_bearer(_TENANT_TOKEN))
    assert status == 503 and body == b"", "an engine/transport failure must be a 503 with no body"


def test_post_import_missing_bearer_is_401() -> None:
    stub = _StubImportInitiation(_import_outcome())
    with _serve(StubControlPlaneRead(mode="success"), import_initiation=stub) as (netloc, _c, _a):
        status, _hdrs, body = _request(netloc, "/import/g1", method="POST")
    assert status == 401 and body == b"", "a missing bearer on the import route must be a 401 with no body"
    assert stub.requests == [], "an unauthenticated import must never reach the import port"


def test_post_import_control_scope_token_is_403_tenant_context_required() -> None:
    # A tenantless CONTROL token has no signed active tenant -> the import (a TENANT-domain write) is
    # denied pre-port with 403, empty body. Tenant authority is never taken from the path/headers.
    stub = _StubImportInitiation(_import_outcome())
    with _serve(StubControlPlaneRead(mode="success"), import_initiation=stub) as (netloc, _c, _a):
        status, _hdrs, body = _request(netloc, "/import/g1", method="POST", headers=_bearer(_CTL_TOKEN))
    assert status == 403 and body == b"", "a control-scope token (no active tenant) must be a 403 with no body"
    assert stub.requests == [], "a pre-port tenant-context denial must never invoke the import port"


def test_post_import_carrier_mismatch_is_403() -> None:
    # A tenant token (t1) + a DIFFERENT single carrier (X-Tenant-Id t2) -> carrier_mismatch (403).
    stub = _StubImportInitiation(_import_outcome())
    with _serve(StubControlPlaneRead(mode="success"), import_initiation=stub) as (netloc, _c, _a):
        headers = {**_bearer(_TENANT_TOKEN), "X-Tenant-Id": "t2"}
        status, _hdrs, body = _request(netloc, "/import/g1", method="POST", headers=headers, host="example.com")
    assert status == 403 and body == b"", "a carrier mismatch must be a 403 with no body"
    assert stub.requests == [], "a carrier-mismatch denial must never invoke the import port"


def test_post_import_operation_key_is_forwarded() -> None:
    # The optional x-operation-key header is forwarded to the core, which hands it to the import port
    # (operation-level idempotency, D-20). The edge derives no tenant/actor authority from it.
    stub = _StubImportInitiation(_import_outcome())
    with _serve(StubControlPlaneRead(mode="success"), import_initiation=stub) as (netloc, _c, _a):
        headers = {**_bearer(_TENANT_TOKEN), "X-Operation-Key": "op-hdr-123"}
        status, _hdrs, _body = _request(netloc, "/import/g1", method="POST", headers=headers)
    assert status == 200
    assert len(stub.requests) == 1 and stub.requests[0].operation_key == "op-hdr-123", "a client x-operation-key must be forwarded"


def test_post_import_port_absent_envelope_is_failclosed_503() -> None:
    # Port ABSENT (no ImportInitiationPort) + control_read present: the core dispatches and composes the
    # accepted-initiation ImportInitiationDTO envelope (200). The edge must NEVER serve that as success —
    # only a real ImportResultDTO is a served import success — so it fails closed to 503, empty body.
    with _serve(StubControlPlaneRead(mode="success")) as (netloc, counting, _a):
        status, _hdrs, body = _request(netloc, "/import/g1", method="POST", headers=_bearer(_TENANT_TOKEN))
    assert status == 503 and body == b"", "a port-absent ImportInitiationDTO envelope must fail closed to 503, empty body"
    assert counting.calls == 1, "the core is still invoked once; the non-ImportResultDTO envelope is fail-closed at the edge"


def test_get_valid_import_target_is_405_pre_core() -> None:
    with _serve(StubControlPlaneRead(mode="success")) as (netloc, counting, _a):
        status, _hdrs, _body = _request(netloc, "/import/g1", headers=_bearer(_TENANT_TOKEN))  # GET
    assert status == 405, "GET on a valid import target must be 405 (POST/OPTIONS only)"
    assert counting.calls == 0, "a method rejection must never reach the core"


def test_bare_and_empty_import_targets_are_404_pre_core() -> None:
    with _serve(StubControlPlaneRead(mode="success")) as (netloc, counting, _a):
        for path in ("/import", "/import/", "/import//rec-9"):
            status, _hdrs, _body = _request(netloc, path, method="POST", headers=_bearer(_TENANT_TOKEN))
            assert status == 404, f"a bare/empty import target {path!r} must be 404 pre-core; got {status}"
    assert counting.calls == 0, "a route rejection must never reach the core"


def test_malformed_traversal_and_encoded_import_targets_are_404_pre_core() -> None:
    malformed = (
        "/import/../rec-9",  # dot-dot traversal segment
        "/import/global-startup/../rec-9",  # interior dot-dot traversal
        "/import/%2e%2e/rec-9",  # percent-encoded dot-dot
        "/import/global-startup%2Frec-9",  # percent-encoded delimiter
        "/import/global-startup\\rec-9",  # backslash
        "/import/g1?tenant=t1",  # query form (tenant authority is never from the query)
    )
    with _serve(StubControlPlaneRead(mode="success")) as (netloc, counting, _a):
        for path in malformed:
            status, _hdrs, _body = _request(netloc, path, method="POST", headers=_bearer(_TENANT_TOKEN))
            assert status == 404, f"a malformed/encoded import target {path!r} must be 404 pre-core; got {status}"
    assert counting.calls == 0, "a malformed-target rejection must never reach the core"


def test_post_import_with_body_is_413_pre_core() -> None:
    with _serve(StubControlPlaneRead(mode="success")) as (netloc, counting, _a):
        status, _hdrs, _body = _request(netloc, "/import/g1", method="POST", headers=_bearer(_TENANT_TOKEN), body=b"x")
    assert status == 413, "a non-empty body on the body-less import route must be 413 pre-core"
    assert counting.calls == 0, "a bounds rejection must never reach the core"


def test_options_import_preflight_is_204_with_post_methods() -> None:
    origin = "https://ok.example"
    with _serve(StubControlPlaneRead(mode="success"), allowed_origins=(origin,)) as (netloc, counting, _a):
        status, hdrs, _body = _request(netloc, "/import/g1", method="OPTIONS", headers={"Origin": origin})
    assert status == 204, f"an allowed import preflight must be 204; got {status}"
    assert hdrs.get("access-control-allow-origin") == origin, "the exact origin must be echoed"
    assert hdrs.get("access-control-allow-methods") == "POST, OPTIONS", "the import preflight must advertise POST, OPTIONS"
    assert hdrs.get("access-control-allow-credentials") == "false", "credentialed CORS must never be enabled"
    assert "x-operation-key" in (hdrs.get("access-control-allow-headers") or "").lower(), (
        "x-operation-key must be an allowed request header"
    )
    assert counting.calls == 0, "a CORS preflight must never reach the core"


def test_post_import_correlation_id_is_echoed() -> None:
    stub = _StubImportInitiation(_import_outcome())
    with _serve(StubControlPlaneRead(mode="success"), import_initiation=stub) as (netloc, _c, _a):
        headers = {**_bearer(_TENANT_TOKEN), "X-Correlation-Id": "imp-corr.9"}
        status, hdrs, _body = _request(netloc, "/import/g1", method="POST", headers=headers)
    assert status == 200 and hdrs.get("x-correlation-id") == "imp-corr.9", "a valid correlation id must be echoed on the import route"


# --- served tenant Startup routes (TA-1): GET/PATCH /tenant/startups/<startup_ref> -----------------
def test_options_tenant_startup_preflight_grants_tenant_carrier_header() -> None:
    # TA-1: the tenant-startup preflight grants the x-tenant-id match-only carrier (alongside
    # authorization, content-type, x-correlation-id) so the browser may SEND it; the carrier is
    # never authorization. Exact-origin allowlist and credentials-false stay unchanged.
    origin = "https://ok.example"
    with _serve(StubControlPlaneRead(mode="success"), allowed_origins=(origin,)) as (netloc, counting, _a):
        status, hdrs, _body = _request(netloc, "/tenant/startups/stp_1", method="OPTIONS", headers={"Origin": origin})
    assert status == 204, f"an allowed tenant-startup preflight must be 204; got {status}"
    assert hdrs.get("access-control-allow-origin") == origin, "the exact origin must be echoed"
    assert hdrs.get("access-control-allow-methods") == "GET, PATCH, OPTIONS", "the preflight must advertise GET, PATCH, OPTIONS"
    assert hdrs.get("access-control-allow-credentials") == "false", "credentialed CORS must never be enabled"
    allowed_headers = (hdrs.get("access-control-allow-headers") or "").lower()
    for granted in ("authorization", "content-type", "x-correlation-id", "x-tenant-id"):
        assert granted in allowed_headers, f"{granted} must be granted on the tenant-startup preflight"
    assert counting.calls == 0, "a CORS preflight must never reach the core"


class _FailingAuditEmitter(AuditEmitterPort):
    """A durable-sink double whose every emit fails (stands in for an unavailable sink)."""

    def __init__(self) -> None:
        self.calls = 0

    def emit(self, event: GatewayAuditEvent) -> None:
        self.calls += 1
        raise RuntimeError("durable-audit-sink-unavailable-stub")


@contextlib.contextmanager
def _serve_tenant_mismatch(durable: AuditEmitterPort) -> Iterator[Tuple[str, _CountingGateway, RecordingAuditEmitter, StubRouterDispatch]]:
    """The tenant-mismatch serving fixture (D-43): the audit emitter is the REAL CLM durable
    partition over the injected ``durable`` half (a recording in-memory half proves the
    mismatch never lands in-memory), and the router is exposed so no-DB-handoff is provable."""
    authn = StubAuthenticator()
    authn.add_token("Bearer " + _TENANT_TOKEN, principal="p1", tenant="t1", role="TENANT_AGENT")
    router = StubRouterDispatch()
    in_memory = RecordingAuditEmitter()
    gateway = build_gateway(
        authenticator=authn,
        router=router,
        control_read=StubControlPlaneRead(mode="success"),
        audit=ClmDurableAuditPartition(durable, in_memory),
    )
    counting = _CountingGateway(gateway)
    server, base_url = build_gateway_edge_server(counting, host="127.0.0.1", port=0)  # type: ignore[arg-type]
    netloc = base_url.split("://", 1)[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield netloc, counting, in_memory, router
    finally:
        server.shutdown()
        thread.join(timeout=10.0)
        server.server_close()


def test_tenant_startup_cross_tenant_carrier_replay_is_403_empty_before_routing() -> None:
    # TA-1 + D-43: a tenant-A token replayed with a tenant-B X-Tenant-Id carrier on the
    # tenant-startup route remains a fail-closed 403 with an EMPTY body before routing: the
    # CarrierMismatch DURABLE event is emitted exactly once (with the opaque carrier_ref),
    # never to the in-memory half, and no tenant read, update, handoff, or database routing
    # occurs (no tenant Startup read/update audit is emitted; the denial is pre-dispatch
    # inside the core).
    durable = RecordingAuditEmitter()
    with _serve_tenant_mismatch(durable) as (netloc, counting, in_memory, router):
        headers = {**_bearer(_TENANT_TOKEN), "X-Tenant-Id": "t2"}
        status, _hdrs, body = _request(netloc, "/tenant/startups/stp_1", headers=headers, host="example.com")
    assert status == 403 and body == b"", "a cross-tenant carrier replay must be a 403 with no body"
    carrier_events = [e for e in durable.events if e.action is AuditAction.CARRIER_MISMATCH]
    assert len(carrier_events) == 1, "the CarrierMismatch durable event must be emitted exactly once"
    (event,) = carrier_events
    assert event.outcome == "rejected" and event.carrier_ref == "carrier:t2", "the opaque carrier_ref must be present"
    assert event.carrier_ref is not None and event.carrier_ref.startswith("carrier:") and len(event.carrier_ref) <= 64
    assert event.tenant_ref is None and event.record_ref is None, "the pre-routing denial fabricates no tenant/record reference"
    assert not any(e.action is AuditAction.CARRIER_MISMATCH for e in in_memory.events), (
        "the mismatch must never land on the in-memory emitter (D-43 durable homing)"
    )
    assert not any(e.action in (AuditAction.TENANT_STARTUP_READ, AuditAction.TENANT_STARTUP_UPDATE) for e in durable.events), (
        "a carrier-mismatch denial must never produce a tenant Startup read or update"
    )
    assert router.handoffs == [], "no DB handoff: the denial is pre-routing (the router is never dispatched)"
    assert counting.calls == 1, "the core is invoked exactly once and denies before any routing or handoff"


def test_tenant_startup_carrier_mismatch_sink_failure_is_503_no_routing() -> None:
    # D-43: the SAME cross-tenant mismatch with the durable sink unavailable collapses
    # fail-closed to 503 `unavailable` (empty body) — the denial is never handed back
    # without its durable evidence — and still performs no routing and no tenant access.
    durable = _FailingAuditEmitter()
    with _serve_tenant_mismatch(durable) as (netloc, counting, in_memory, router):
        headers = {**_bearer(_TENANT_TOKEN), "X-Tenant-Id": "t2"}
        status, _hdrs, body = _request(netloc, "/tenant/startups/stp_1", headers=headers, host="example.com")
    assert status == 503 and body == b"", "an unavailable durable sink must collapse the mismatch denial to 503 with no body"
    assert durable.calls == 1, "the failed durable emit is attempted exactly once at the gateway edge (per-request dedup)"
    assert in_memory.events == [], "a failed durable denial must never fall back to the in-memory emitter"
    assert router.handoffs == [], "no routing occurs on the sink-failure leg"
    assert counting.calls == 1, "the core is invoked exactly once and fails closed before any routing"


if __name__ == "__main__":
    _h.run(
        [
            test_valid_memberships_returns_200_dto_and_calls_handle_once,
            test_empty_memberships_is_lawful_200,
            test_missing_bearer_is_401,
            test_invalid_bearer_is_401,
            test_forbidden_is_403,
            test_carrier_mismatch_is_403_with_carrier_audit,
            test_isolation_anomaly_straddle_is_403,
            test_forwarded_host_is_not_trusted,
            test_control_read_unavailable_is_503,
            test_malformed_control_response_is_503,
            test_post_memberships_is_405_pre_core,
            test_unknown_and_reserved_routes_are_404_pre_core,
            test_get_with_body_is_rejected_pre_core,
            test_oversized_request_target_is_413,
            test_oversized_header_is_413,
            test_valid_correlation_is_echoed,
            test_missing_correlation_is_minted_and_echoed,
            test_malformed_correlation_is_replaced_and_echoed,
            test_allowed_cors_preflight_is_204_with_exact_origin_headers,
            test_denied_cors_origin_gets_no_permissive_headers,
            test_success_response_to_denied_origin_carries_no_cors,
            test_health_is_200_and_core_untouched,
            test_readiness_is_200_without_overclaim,
            test_post_import_multisegment_source_created_returns_200_result_dto_and_calls_handle_once,
            test_post_import_replayed_returns_200,
            test_post_import_noop_returns_200,
            test_post_import_zero_record_is_403_no_body,
            test_post_import_engine_failure_is_503_no_body,
            test_post_import_missing_bearer_is_401,
            test_post_import_control_scope_token_is_403_tenant_context_required,
            test_post_import_carrier_mismatch_is_403,
            test_post_import_operation_key_is_forwarded,
            test_post_import_port_absent_envelope_is_failclosed_503,
            test_get_valid_import_target_is_405_pre_core,
            test_bare_and_empty_import_targets_are_404_pre_core,
            test_malformed_traversal_and_encoded_import_targets_are_404_pre_core,
            test_post_import_with_body_is_413_pre_core,
            test_options_import_preflight_is_204_with_post_methods,
            test_post_import_correlation_id_is_echoed,
            test_options_tenant_startup_preflight_grants_tenant_carrier_header,
            test_tenant_startup_cross_tenant_carrier_replay_is_403_empty_before_routing,
            test_tenant_startup_carrier_mismatch_sink_failure_is_503_no_routing,
        ]
    )
