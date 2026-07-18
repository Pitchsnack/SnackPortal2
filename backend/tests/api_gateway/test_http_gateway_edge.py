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
from typing import Dict, Iterator, Optional, Tuple

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
from api_gateway.main import build_gateway  # noqa: E402
from api_gateway.models import AuditAction  # noqa: E402
from api_gateway.portal import MembershipEntryDTO  # noqa: E402

_CTL_TOKEN = "tok-ctl"
_TENANT_TOKEN = "tok-t1"
_MEMBERSHIP = MembershipEntryDTO(tenant_id="t1", role="TENANT_AGENT", display_ref="ref:tenant/t1/display")


class _CountingGateway:
    """Wraps a composed Gateway and counts ``handle`` calls (proves exactly-once / never)."""

    def __init__(self, inner: object) -> None:
        self._inner = inner
        self.calls = 0

    def handle(self, request: object) -> object:
        self.calls += 1
        return self._inner.handle(request)  # type: ignore[attr-defined]


@contextlib.contextmanager
def _serve(control_read: object, *, allowed_origins: Tuple[str, ...] = ()) -> Iterator[Tuple[str, _CountingGateway, RecordingAuditEmitter]]:
    authn = StubAuthenticator()
    # The stub keys tokens by the verbatim Authorization value the edge forwards (the core does not
    # strip "Bearer " — the real IC-005 authenticator does; the stub stands in for it), so register
    # the full header value.
    authn.add_token("Bearer " + _CTL_TOKEN, principal="ops", tenant=None, role="CONTROL")
    authn.add_token("Bearer " + _TENANT_TOKEN, principal="p1", tenant="t1", role="TENANT_AGENT")
    router = StubRouterDispatch()
    audit = RecordingAuditEmitter()
    gateway = build_gateway(authenticator=authn, router=router, control_read=control_read, audit=audit)
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
        ]
    )
