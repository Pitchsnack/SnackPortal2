"""Live-wire behavioral tests for HttpControlPlaneRead (B5-3 LW-1).

Proves the production auth-router read client against a REAL local stdlib HTTP boundary
(single-threaded ``HTTPServer`` on a test-owned daemon thread): a live HTTP 404 maps to
``None`` (consistent denial — parity with the in-memory double and the DBR
``HttpRoutingRead`` twin); every non-404 ``HTTPError`` (400/401/403/500) re-raises as the
ORIGINAL error with its status preserved (callers fail closed); connection refusal keeps
raising ``URLError``; successful 2xx JSON decode and malformed-JSON failure behavior are
unchanged; and the federation client decode (``FederationView``) round-trips over the wire.

Mutation reasoning (wrapper §8.4 items 1-3): removing the 404 catch makes a live 404 raise
``HTTPError`` → ``test_live_404_maps_to_none...`` fails; converting EVERY ``HTTPError`` to
``None`` makes 400/401/403/500 return ``None`` → ``test_non_404_http_errors_reraise...``
fails (it asserts the original exception and code); converting 404 to an empty object
instead of ``None`` is OBSERVATIONALLY EQUIVALENT at the port surface (every port method
truthiness-guards the ``_get`` result), so that mutant is killed by the B5-3 architecture
census instead — ``test_control_plane_read_client_live_wire_guard`` (test_07e3b) requires a
literal ``return None`` inside the 404 handler and fails on the ``{}`` shape.

Stdlib-only; DB-free; bounded daemon-thread hosting with ``server_close`` in ``finally``;
runnable standalone:  python tests/auth_router/test_http_control_plane_read_live_wire.py
"""

from __future__ import annotations

import json
import pathlib
import socket
import sys
import threading
import urllib.error
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from auth_router.adapters.providers.http_control_plane_read import HttpControlPlaneRead  # noqa: E402
from auth_router.models import FederationView, TenantStateView  # noqa: E402

_ISS = "https://issuer.example/realm?x=1&y=2"  # needs URL-encoding on the wire

# The scripted wire: tenant-state responses keyed by tenant id (status, body-json-or-raw).
_SCRIPT: dict[str, Tuple[int, Optional[str]]] = {
    "t-ready": (200, json.dumps({"tenant_id": "t-ready", "lifecycle_state": "Ready", "ready": True})),
    "t-unknown": (404, None),
    "t-400": (400, None),
    "t-401": (401, None),
    "t-403": (403, None),
    "t-500": (500, None),
    "t-badjson": (200, "this is not json {"),
}


def _make_stub_handler() -> "type[BaseHTTPRequestHandler]":
    class _Stub(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            parts = urllib.parse.urlsplit(self.path)
            segments = [s for s in parts.path.split("/") if s]
            # /tenants/{id}/state — scripted per tenant id.
            if len(segments) == 3 and segments[0] == "tenants" and segments[2] == "state":
                status, body = _SCRIPT.get(segments[1], (404, None))
                self._respond(status, body)
                return
            # /federation?issuer= — one known issuer, five-field client-compatible JSON.
            if segments == ["federation"]:
                issuer = (urllib.parse.parse_qs(parts.query).get("issuer") or [""])[0]
                if issuer == _ISS:
                    self._respond(
                        200,
                        json.dumps(
                            {
                                "tenant_id": "t-ready",
                                "oidc_issuer": _ISS,
                                "oidc_audience": "aud",
                                "jwks_ref": "jwks/t-ready",
                                "claim_to_tenant_rule": "tenant",
                            }
                        ),
                    )
                    return
                self._respond(404, None)
                return
            # /membership and /role — 404 for everything (None/False mapping on the client).
            self._respond(404, None)

        def _respond(self, status: int, body: Optional[str]) -> None:
            payload = (body or "").encode("utf-8")
            self.send_response(status)
            if payload:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if payload:
                self.wfile.write(payload)

        def log_message(self, *args: object) -> None:  # silence stderr
            return

    return _Stub


class _StubWire:
    """A REAL local stdlib HTTP server hosted on a bounded test-owned daemon thread."""

    def __enter__(self) -> str:
        self._server = HTTPServer(("127.0.0.1", 0), _make_stub_handler())
        host, port = self._server.server_address[0], self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return f"http://{host}:{port}"

    def __exit__(self, *exc: object) -> None:
        self._server.shutdown()
        self._thread.join(timeout=10.0)
        self._server.server_close()
        assert not self._thread.is_alive(), "stub wire thread must terminate (bounded join)"


def _refused_url() -> str:
    """A loopback URL with a just-released (closed) ephemeral port — connection refused."""
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return f"http://127.0.0.1:{port}"


# --- LW-1: live 404 -> None (consistent denial) ------------------------------------------------------
def test_live_404_maps_to_none_for_every_read() -> None:
    with _StubWire() as base_url:
        read = HttpControlPlaneRead(base_url)
        assert read.get_tenant_state("t-unknown") is None, "a LIVE 404 must map to None (LW-1)"
        assert read.get_role("u1", "t-unknown") is None, "role 404 must map to None"
        assert read.is_member("u1", "t-unknown") is False, "membership 404 must map to False"
        assert read.get_federation_for_issuer("https://nobody.example") is None, "federation 404 must map to None"


# --- non-404 HTTPError: the ORIGINAL exception re-raises (fail closed) -------------------------------
def test_non_404_http_errors_reraise_with_status_preserved() -> None:
    with _StubWire() as base_url:
        read = HttpControlPlaneRead(base_url)
        for tenant, expected in (("t-400", 400), ("t-401", 401), ("t-403", 403), ("t-500", 500)):
            try:
                read.get_tenant_state(tenant)
            except urllib.error.HTTPError as exc:
                assert exc.code == expected, f"non-404 must re-raise the ORIGINAL HTTPError (got {exc.code}, want {expected})"
            else:
                raise AssertionError(f"HTTP {expected} must NOT be converted to None (fail closed)")


# --- transport failure behavior unchanged ------------------------------------------------------------
def test_connection_refused_still_raises_urlerror() -> None:
    read = HttpControlPlaneRead(_refused_url(), timeout=1.0)
    try:
        read.get_tenant_state("t-ready")
    except urllib.error.URLError:
        pass  # includes ConnectionRefusedError wrapped by urllib — callers fail closed
    else:
        raise AssertionError("connection refusal must keep raising URLError (never None)")


# --- success + malformed-JSON decode behavior unchanged ----------------------------------------------
def test_success_decode_unchanged() -> None:
    with _StubWire() as base_url:
        read = HttpControlPlaneRead(base_url)
        state = read.get_tenant_state("t-ready")
        assert state == TenantStateView(tenant_id="t-ready", lifecycle_state="Ready", ready=True)
        # Federation decode over the wire: the five-field JSON round-trips into FederationView,
        # through a URL-encoded issuer (quote() on the client, percent-decode on the stub).
        fed = read.get_federation_for_issuer(_ISS)
        assert fed == FederationView(
            tenant_id="t-ready", oidc_issuer=_ISS, oidc_audience="aud", jwks_ref="jwks/t-ready", claim_to_tenant_rule="tenant"
        )


def test_malformed_json_still_raises() -> None:
    with _StubWire() as base_url:
        read = HttpControlPlaneRead(base_url)
        try:
            read.get_tenant_state("t-badjson")
        except (json.JSONDecodeError, ValueError):
            pass  # existing failure behavior unchanged — callers fail closed
        else:
            raise AssertionError("malformed 200 JSON must keep raising (never a silent None)")


_TESTS = [
    test_live_404_maps_to_none_for_every_read,
    test_non_404_http_errors_reraise_with_status_preserved,
    test_connection_refused_still_raises_urlerror,
    test_success_decode_unchanged,
    test_malformed_json_still_raises,
]

if __name__ == "__main__":
    _h.run(_TESTS)
