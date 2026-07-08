"""DB-free end-to-end gateway auth + router transport smoke (07E-3d, Option A).

Composes BOTH env-selected production-shaped transports through the REAL gateway pipeline,
DB-free: an ``InboundRequest`` enters ``Gateway.handle`` (``build_gateway`` with BOTH
``build_authenticator_from_env()`` and ``build_router_dispatch_from_env()`` selected);
authentication crosses the wire — ``HttpAuthenticator`` → loopback ``build_authenticate_server``
(REAL ``Authenticator`` over the auth_router stdlib doubles: no PyJWT, no control plane, no
PostgreSQL) — and the 4-field ``AuthResult`` builds the gateway ``RequestContext`` through the
existing exclusive path; dispatch then crosses the wire — ``HttpRouterDispatch`` → a
hand-rolled FAKE dispatch server returning the references-only ``{status, public_code,
dispatched}`` envelope (Option A: NO ``DatabaseRouter``, no ``_db_doubles``, no PostgreSQL —
the Database Router production composition + physical tenant DBs remain B5-BLK-4 / Physical
Multi-Database MVP scope, explicitly out of this slice).

This is production-shaped, NOT a runnable production gateway. Invariants preserved:
Authentication ≠ Routing ≠ Authorization ≠ Database Access; One Request → One Active Tenant →
One Database; CONTROL derived from ``active_tenant_id is None`` (never a field); references
only on both wires. Placed under ``tests/api_gateway`` (not ``tests/integration``): the
package-imported test tree would need a ``tests/integration/__init__.py`` outside the
authorized surface.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Iterator, List, Optional, Tuple

_HERE = pathlib.Path(__file__).resolve().parent
# Insert auth_router's test dir first, then api_gateway's LAST so it wins position 0: the shared
# ``_h``/``_gateway_doubles`` names resolve to api_gateway; ``_auth_doubles`` is unique to auth_router.
sys.path.insert(0, str(_HERE.parent / "auth_router"))
sys.path.insert(0, str(_HERE))
import _auth_doubles as D  # noqa: E402
import _gateway_doubles as G  # noqa: E402
import _h  # noqa: E402

from api_gateway.adapters.providers.http_router_dispatch import HttpRouterDispatch  # noqa: E402
from api_gateway.main import (  # noqa: E402
    GW_AUTH_ROUTER_BASE_URL_ENV,
    GW_DB_ROUTER_BASE_URL_ENV,
    build_authenticator_from_env,
    build_gateway,
    build_router_dispatch_from_env,
)
from api_gateway.models import DatabaseDomain, DispatchCategory, DispatchDecision  # noqa: E402
from auth_router.adapters.providers.http_authenticate_api import build_authenticate_server  # noqa: E402
from auth_router.main import build_authenticator  # noqa: E402
from auth_router.models import Role  # noqa: E402
from shared.context import RequestContext  # noqa: E402

_ISS = "https://platform.snackportal"
_SECRET = b"07e3d-smoke-secret"
_DISPATCH_OK = b'{"status": 200, "public_code": "ok", "dispatched": true}'


def _compose_loopback_auth_router() -> Tuple[HTTPServer, str]:
    """Host the REAL auth stack in-process: doubles-composed Authenticator behind the REAL
    single-threaded loopback transport server (test-owned daemon thread)."""
    read = D.FakeControlPlaneRead()
    read.set_tenant("t1", ready=True)
    read.add_member("u1", "t1", Role.TENANT_AGENT)
    authenticator = build_authenticator(verifier=D.HmacTestVerifier(), read=read, issuers={_ISS: D.issuer_cfg(issuer=_ISS, secret=_SECRET)})
    server, base_url = build_authenticate_server(authenticator, "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, base_url


class _FakeDispatchState:
    def __init__(self) -> None:
        self.status = 200
        self.body: bytes = _DISPATCH_OK
        self.calls = 0
        self.paths: List[str] = []


def _host_fake_dispatch_server(state: _FakeDispatchState) -> Tuple[HTTPServer, str]:
    """A hand-rolled FAKE dispatch server (Option A): returns the configured references-only
    body — NO DatabaseRouter, no DB. Mirrors tests/api_gateway/test_http_router_dispatch.py."""

    class _H(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            state.calls += 1
            state.paths.append(self.path)
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self.send_response(state.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(state.body)))
            self.end_headers()
            self.wfile.write(state.body)

        def log_message(self, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), _H)
    host, port = server.server_address[0], server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://{host}:{port}"


def _tenant_token(sub: str = "u1", tenant: Optional[str] = "t1") -> str:
    return D.make_hs256_jwt(D.claims(sub=sub, iss=_ISS, tenant=tenant), secret=_SECRET)


@contextlib.contextmanager
def _both_env(*, auth_url: str, db_router_url: str) -> Iterator[None]:
    """Set BOTH transport selectors for one test and always restore the prior values."""
    keys = {GW_AUTH_ROUTER_BASE_URL_ENV: auth_url, GW_DB_ROUTER_BASE_URL_ENV: db_router_url}
    prior = {k: os.environ.get(k) for k in keys}
    try:
        for k, v in keys.items():
            os.environ[k] = v
        yield
    finally:
        for k, v in prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@contextlib.contextmanager
def _both_transports(*, dispatch_status: int = 200, dispatch_body: bytes = _DISPATCH_OK) -> Iterator[Tuple[object, _FakeDispatchState]]:
    """Compose a gateway wired with BOTH env-SELECTED real transports (auth loopback server +
    dispatch client → fake dispatch server). Yields (gateway, dispatch_state)."""
    auth_server, auth_url = _compose_loopback_auth_router()
    state = _FakeDispatchState()
    state.status = dispatch_status
    state.body = dispatch_body
    dispatch_server, dispatch_url = _host_fake_dispatch_server(state)
    try:
        with _both_env(auth_url=auth_url, db_router_url=dispatch_url):
            authenticator = build_authenticator_from_env()
            router = build_router_dispatch_from_env()
        assert authenticator is not None and router is not None, "both seams must select real transports"
        yield build_gateway(authenticator=authenticator, router=router), state
    finally:
        auth_server.shutdown()
        auth_server.server_close()
        dispatch_server.shutdown()
        dispatch_server.server_close()


def test_smoke_success_dispatches_once_references_only() -> None:
    with _both_transports() as (gateway, state):
        response = gateway.handle(
            G.req(
                "GET",
                "/tenant/deals",
                headers={"X-Tenant-Id": "t1"},
                authorization="Bearer " + _tenant_token(),
                correlation_id="smoke-cid-1",
            )
        )
    # Full chain across BOTH real wires: auth → 4-field AuthResult → RequestContext → dispatch
    # client → fake dispatch server → references-only RouteOutcome.
    assert (response.status, response.public_code, response.dispatched) == (200, "ok", True)
    assert response.category is DispatchCategory.TENANT_OPERATION
    assert state.calls == 1 and state.paths == ["/internal/dispatch/route"], "dispatch must be reached exactly once"
    # The dispatch request envelope carries references only ({v, context, category}) — never a DB
    # handle, DSN, credential, or business payload (verified structurally by the wire itself).


def test_smoke_bad_token_maps_401_and_never_dispatches() -> None:
    with _both_transports() as (gateway, state):
        response = gateway.handle(
            G.req("GET", "/tenant/deals", headers={"X-Tenant-Id": "t1"}, authorization="Bearer opaque-invalid-credential")
        )
    assert (response.status, response.public_code) == (401, "unauthenticated")
    assert state.calls == 0, "auth failure must fail closed BEFORE any dispatch (fail closed)"


def test_smoke_carrier_mismatch_maps_403_and_never_dispatches() -> None:
    with _both_transports() as (gateway, state):
        # Carrier asserts t2 while the signed claim is t1 → IC-005 match-or-reject across the wire.
        response = gateway.handle(G.req("GET", "/tenant/deals", headers={"X-Tenant-Id": "t2"}, authorization="Bearer " + _tenant_token()))
    assert (response.status, response.public_code) == (403, "carrier_mismatch")
    assert state.calls == 0, "carrier mismatch must fail closed BEFORE any dispatch"


def test_smoke_malformed_dispatch_response_fails_closed() -> None:
    # Auth succeeds; the fake dispatch server returns a malformed body → the dispatch client
    # collapses fail-closed to RouteOutcome(503, "unavailable", False) (IC-010 §L).
    with _both_transports(dispatch_body=b"not a valid dispatch envelope") as (gateway, state):
        response = gateway.handle(G.req("GET", "/tenant/deals", headers={"X-Tenant-Id": "t1"}, authorization="Bearer " + _tenant_token()))
    assert (response.status, response.public_code, response.dispatched) == (503, "unavailable", False)
    assert state.calls == 1, "the malformed response is only reachable after auth succeeds and dispatch is attempted"


def test_smoke_dispatch_request_is_references_only() -> None:
    # Capture the dispatch request body and assert it is exactly the {v, context, category}
    # references-only envelope — no DB handle/DSN/credential/business payload crosses the wire.
    captured: List[bytes] = []

    class _CapturingHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            captured.append(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            self.send_response(200)
            self.send_header("Content-Length", str(len(_DISPATCH_OK)))
            self.end_headers()
            self.wfile.write(_DISPATCH_OK)

        def log_message(self, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), _CapturingHandler)
    host, port = server.server_address[0], server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        ctx = RequestContext(correlation_id="cid", request_id="cid", active_tenant_id="t1", principal_ref="u1", role="TENANT_AGENT")
        decision = DispatchDecision(category=DispatchCategory.TENANT_OPERATION, domain=DatabaseDomain.TENANT, target_tenant_id="t1")
        HttpRouterDispatch(f"http://{host}:{port}").dispatch(ctx, decision)
    finally:
        server.shutdown()
        server.server_close()

    assert len(captured) == 1
    envelope = json.loads(captured[0].decode("utf-8"))
    assert set(envelope.keys()) == {"v", "context", "category"}, "dispatch wire must be exactly {v, context, category}"
    assert set(envelope["context"].keys()) == {"correlation_id", "request_id", "active_tenant_id", "principal_ref", "role"}
    # target_tenant_id / domain (gateway-computed) MUST NOT cross the wire — the router binds from the claim.
    assert "target_tenant_id" not in envelope and "domain" not in envelope, "DispatchDecision internals must never cross the wire"


if __name__ == "__main__":
    _h.run(
        [
            test_smoke_success_dispatches_once_references_only,
            test_smoke_bad_token_maps_401_and_never_dispatches,
            test_smoke_carrier_mismatch_maps_403_and_never_dispatches,
            test_smoke_malformed_dispatch_response_fails_closed,
            test_smoke_dispatch_request_is_references_only,
        ]
    )
