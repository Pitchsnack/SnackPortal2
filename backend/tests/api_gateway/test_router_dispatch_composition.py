"""Behavioral tests for the 07E-3d config-selectable router-dispatch seam.

Proves ``build_router_dispatch_from_env`` (api_gateway/main.py): unset/empty env keeps the
existing injected composition (returns ``None``), a structurally valid internal ``http``
base URL selects the production-shaped D-15-T1b ``HttpRouterDispatch`` transport client
bound to exactly that URL, and any malformed/off-scheme value fails closed with
``ValueError`` — never a silent fallback (the same selector posture as the 07E-3c auth
seam). Also proves the helper performs no network I/O at construction (lazy transport), and
that ``build_gateway`` required-injection behavior and the existing stub composition path
are byte-unchanged. This seam does NOT create a runnable production gateway — the Database
Router still requires production composition over physical tenant databases (B5 scope).
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Iterator, List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _gateway_doubles as G  # noqa: E402
import _h  # noqa: E402

from api_gateway.adapters.providers.http_router_dispatch import HttpRouterDispatch  # noqa: E402
from api_gateway.main import GW_DB_ROUTER_BASE_URL_ENV, build_gateway, build_router_dispatch_from_env  # noqa: E402
from api_gateway.models import DatabaseDomain, DispatchCategory, DispatchDecision, RouteOutcome  # noqa: E402
from shared.context import RequestContext  # noqa: E402

_SUCCESS_BODY = b'{"status": 200, "public_code": "ok", "dispatched": true}'
_CTX = RequestContext(correlation_id="cid", request_id="cid", active_tenant_id="t1", principal_ref="u1", role="TENANT_AGENT")
_DECISION = DispatchDecision(category=DispatchCategory.TENANT_OPERATION, domain=DatabaseDomain.TENANT, target_tenant_id="t1")


@contextlib.contextmanager
def _env(value: Optional[str]) -> Iterator[None]:
    """Set/unset SP2_GW_DB_ROUTER_BASE_URL for one test and always restore the prior value."""
    prior = os.environ.get(GW_DB_ROUTER_BASE_URL_ENV)
    try:
        if value is None:
            os.environ.pop(GW_DB_ROUTER_BASE_URL_ENV, None)
        else:
            os.environ[GW_DB_ROUTER_BASE_URL_ENV] = value
        yield
    finally:
        if prior is None:
            os.environ.pop(GW_DB_ROUTER_BASE_URL_ENV, None)
        else:
            os.environ[GW_DB_ROUTER_BASE_URL_ENV] = prior


def _host_minimal_dispatch_server() -> tuple:
    """A minimal loopback responder returning the fixed references-only dispatch body; records paths."""
    paths: List[str] = []

    class _H(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            paths.append(self.path)
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(_SUCCESS_BODY)))
            self.end_headers()
            self.wfile.write(_SUCCESS_BODY)

        def log_message(self, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), _H)
    host, port = server.server_address[0], server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://{host}:{port}", paths


def _closed_loopback_port() -> int:
    """An ephemeral loopback port with nothing listening (bind, read the port, close)."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])
    finally:
        probe.close()


def _expect_value_error(value: str) -> None:
    with _env(value):
        try:
            build_router_dispatch_from_env()
        except ValueError:
            return
        raise AssertionError(f"{value!r} must fail closed with ValueError (never a silent fallback)")


# --- selection behavior -----------------------------------------------------------------------------
def test_env_unset_returns_none() -> None:
    with _env(None):
        assert build_router_dispatch_from_env() is None, "unset env must preserve the injected (stub) composition"


def test_env_empty_or_whitespace_returns_none() -> None:
    for value in ("", "   ", "\t"):
        with _env(value):
            assert build_router_dispatch_from_env() is None, f"empty/whitespace {value!r} must behave as unset"


def test_valid_http_url_selects_http_router_dispatch() -> None:
    with _env("http://127.0.0.1:8082"):
        router = build_router_dispatch_from_env()
    assert isinstance(router, HttpRouterDispatch), "a valid internal http URL must select the transport client"


def test_selected_router_calls_the_configured_base_url() -> None:
    server, base_url, paths = _host_minimal_dispatch_server()
    try:
        with _env(base_url):
            router = build_router_dispatch_from_env()
        assert router is not None
        outcome = router.dispatch(_CTX, _DECISION)
        assert isinstance(outcome, RouteOutcome) and (outcome.status, outcome.public_code, outcome.dispatched) == (200, "ok", True)
        assert paths == ["/internal/dispatch/route"], "the client must call the configured base URL's internal dispatch path"
    finally:
        server.shutdown()
        server.server_close()


# --- fail-closed configuration boundary --------------------------------------------------------------
def test_malformed_url_raises_value_error() -> None:
    for value in ("not a url", "127.0.0.1:8082", "ftp://127.0.0.1:8082", "http//missing-colon"):
        _expect_value_error(value)


def test_https_scheme_raises_value_error() -> None:
    # The seam pins scheme http: this is the INTERNAL loopback transport (TLS termination is
    # deployment scope). A configured https value must fail closed, not silently degrade.
    _expect_value_error("https://127.0.0.1:8443")


def test_missing_netloc_raises_value_error() -> None:
    for value in ("http://", "http:///internal/dispatch/route", "http:relative"):
        _expect_value_error(value)


# --- lazy transport: no network I/O at construction --------------------------------------------------
def test_construction_performs_no_network_io() -> None:
    port = _closed_loopback_port()
    with _env(f"http://127.0.0.1:{port}"):
        router = build_router_dispatch_from_env()  # must not raise: construction opens no connection
    assert isinstance(router, HttpRouterDispatch)
    # A dead base URL fails closed at CALL time to the single references-only fail-closed outcome.
    outcome = router.dispatch(_CTX, _DECISION)
    assert (outcome.status, outcome.public_code, outcome.dispatched) == (503, "unavailable", False)


# --- build_gateway required-injection path unchanged --------------------------------------------------
def test_build_gateway_required_injection_unchanged() -> None:
    try:
        build_gateway(authenticator=G.StubAuthenticator())  # type: ignore[call-arg]
        raise AssertionError("build_gateway must still REQUIRE the router port (no default)")
    except TypeError:
        pass
    try:
        build_gateway(router=G.StubRouterDispatch())  # type: ignore[call-arg]
        raise AssertionError("build_gateway must still REQUIRE the authenticator port (no default)")
    except TypeError:
        pass


def test_build_gateway_still_composes_with_stubs() -> None:
    with _env(None):
        gateway, _authn, router, _audit = G.tenant_setup()
        response = gateway.handle(G.req("GET", "/tenant/deals", headers={"X-Tenant-Id": "t1"}, authorization="tok-t1"))
    assert (response.status, response.public_code, response.dispatched) == (200, "ok", True)
    assert len(router.handoffs) == 1, "the existing stub composition path must be byte-unchanged"


if __name__ == "__main__":
    _h.run(
        [
            test_env_unset_returns_none,
            test_env_empty_or_whitespace_returns_none,
            test_valid_http_url_selects_http_router_dispatch,
            test_selected_router_calls_the_configured_base_url,
            test_malformed_url_raises_value_error,
            test_https_scheme_raises_value_error,
            test_missing_netloc_raises_value_error,
            test_construction_performs_no_network_io,
            test_build_gateway_required_injection_unchanged,
            test_build_gateway_still_composes_with_stubs,
        ]
    )
