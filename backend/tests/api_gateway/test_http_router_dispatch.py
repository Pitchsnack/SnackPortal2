"""Behavioral tests for the gateway-side dispatch client (D-15-T1b).

Drives ``HttpRouterDispatch`` against a configurable fake dispatch server hosted on a
test-owned daemon thread. Proves the client half of the T1a wire contract: it serializes
exactly ``{v, context, category}`` (and no other ``DispatchDecision`` field), maps the
references-only response and mirrored 4xx/5xx denials, and collapses every malformed /
wrong-shape / wrong-type / unknown-code / timeout / transport-failure case fail-closed to
``RouteOutcome(503, "unavailable", False)`` — single attempt, no retry loop.
"""

from __future__ import annotations

import json
import pathlib
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from api_gateway.adapters.providers.http_router_dispatch import HttpRouterDispatch  # noqa: E402
from api_gateway.models import DatabaseDomain, DispatchCategory, DispatchDecision  # noqa: E402
from shared.context import RequestContext  # noqa: E402


class _FakeState:
    def __init__(self) -> None:
        self.status = 200
        self.body: Optional[bytes] = b'{"status": 200, "public_code": "ok", "dispatched": true}'
        self.delay = 0.0
        self.calls = 0
        self.last_body: Optional[bytes] = None

    def set(self, status: int, body: Optional[bytes]) -> None:
        self.status = status
        self.body = body


def _fake_handler(state: _FakeState):
    class _H(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            state.calls += 1
            length = int(self.headers.get("Content-Length") or 0)
            state.last_body = self.rfile.read(length) if length else b""
            if state.delay:
                time.sleep(state.delay)
            self.send_response(state.status)
            if state.body is None:
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(state.body)))
            self.end_headers()
            self.wfile.write(state.body)

        def log_message(self, *args: object) -> None:
            return

    return _H


class _QuietHTTPServer(HTTPServer):
    # Suppress the expected aborted-socket traceback when a client times out and closes
    # the connection while a delayed handler is still writing (the timeout test).
    def handle_error(self, request: object, client_address: object) -> None:
        return


def _host(state: _FakeState):
    server = _QuietHTTPServer(("127.0.0.1", 0), _fake_handler(state))
    host, port = server.server_address[0], server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://{host}:{port}"


def _tenant_ctx() -> RequestContext:
    return RequestContext(correlation_id="c1", request_id="r1", active_tenant_id="t1", principal_ref="p1", role="TENANT_AGENT")


def _tenant_decision() -> DispatchDecision:
    return DispatchDecision(category=DispatchCategory.TENANT_OPERATION, domain=DatabaseDomain.TENANT, target_tenant_id="t1")


def test_serializes_exact_request_envelope_and_maps_ok() -> None:
    state = _FakeState()
    server, base_url = _host(state)
    try:
        client = HttpRouterDispatch(base_url)
        outcome = client.dispatch(_tenant_ctx(), _tenant_decision())
        assert (outcome.status, outcome.public_code, outcome.dispatched) == (200, "ok", True)
        sent = json.loads(state.last_body or b"{}")
        assert set(sent.keys()) == {"v", "context", "category"} and sent["v"] == 1
        assert set(sent["context"].keys()) == {"correlation_id", "request_id", "active_tenant_id", "principal_ref", "role"}
        assert sent["context"]["active_tenant_id"] == "t1" and sent["category"] == "TENANT_OPERATION"
        # No DispatchDecision field other than the advisory category crosses the wire.
        raw = (state.last_body or b"").decode("utf-8")
        for forbidden in ("target_tenant_id", "domain", "workspace", "route_ref"):
            assert forbidden not in raw, f"{forbidden} must not be serialized"
    finally:
        server.shutdown()
        server.server_close()


def test_control_null_tenant_serialized_and_ok() -> None:
    state = _FakeState()
    server, base_url = _host(state)
    try:
        client = HttpRouterDispatch(base_url)
        ctx = RequestContext(correlation_id="cc", active_tenant_id=None, role="CONTROL")
        decision = DispatchDecision(category=DispatchCategory.GLOBAL_DIRECTORY_READ, domain=DatabaseDomain.CONTROL, target_tenant_id=None)
        outcome = client.dispatch(ctx, decision)
        assert (outcome.status, outcome.public_code, outcome.dispatched) == (200, "ok", True)
        sent = json.loads(state.last_body or b"{}")
        assert sent["context"]["active_tenant_id"] is None and sent["category"] == "GLOBAL_DIRECTORY_READ"
    finally:
        server.shutdown()
        server.server_close()


def test_maps_success_and_mirrored_denials() -> None:
    state = _FakeState()
    server, base_url = _host(state)
    try:
        client = HttpRouterDispatch(base_url)
        for status, code, dispatched in [
            (200, "ok", True),
            (404, "not_found", False),
            (403, "administratively_disabled", False),
            (503, "connection_unavailable", False),
        ]:
            state.set(status, json.dumps({"status": status, "public_code": code, "dispatched": dispatched}).encode("utf-8"))
            outcome = client.dispatch(_tenant_ctx(), _tenant_decision())
            assert (outcome.status, outcome.public_code, outcome.dispatched) == (status, code, dispatched)
    finally:
        server.shutdown()
        server.server_close()


def test_bad_shapes_collapse_fail_closed() -> None:
    state = _FakeState()
    server, base_url = _host(state)
    try:
        client = HttpRouterDispatch(base_url)
        bad_bodies = [
            b'{"status": 200, "public_code": "ok", "dispatched": true, "extra": 1}',  # extra field
            b'{"status": 200, "public_code": "ok"}',  # missing field
            b'{"status": "200", "public_code": "ok", "dispatched": true}',  # wrong-type status
            b'{"status": 200, "public_code": "ok", "dispatched": "true"}',  # wrong-type dispatched
            b'{"status": 200, "public_code": "weird_code", "dispatched": true}',  # unknown public_code
            b"{not json",  # malformed JSON
            b"[1, 2, 3]",  # non-object JSON
        ]
        for body in bad_bodies:
            state.set(200, body)
            outcome = client.dispatch(_tenant_ctx(), _tenant_decision())
            assert (outcome.status, outcome.public_code, outcome.dispatched) == (503, "unavailable", False), body
    finally:
        server.shutdown()
        server.server_close()


def test_httperror_empty_body_collapses() -> None:
    state = _FakeState()
    server, base_url = _host(state)
    try:
        client = HttpRouterDispatch(base_url)
        state.set(503, None)  # mirrored protocol-failure: 503 with an EMPTY body
        outcome = client.dispatch(_tenant_ctx(), _tenant_decision())
        assert (outcome.status, outcome.public_code, outcome.dispatched) == (503, "unavailable", False)
    finally:
        server.shutdown()
        server.server_close()


def test_timeout_and_connection_refused_collapse() -> None:
    state = _FakeState()
    server, base_url = _host(state)
    try:
        slow = HttpRouterDispatch(base_url, timeout=0.2)
        state.delay = 1.0
        outcome = slow.dispatch(_tenant_ctx(), _tenant_decision())
        assert (outcome.status, outcome.public_code, outcome.dispatched) == (503, "unavailable", False)
    finally:
        server.shutdown()
        server.server_close()
    dead = HttpRouterDispatch("http://127.0.0.1:1", timeout=1.0)
    outcome = dead.dispatch(_tenant_ctx(), _tenant_decision())
    assert (outcome.status, outcome.public_code, outcome.dispatched) == (503, "unavailable", False)


def test_single_attempt_no_retry_loop() -> None:
    state = _FakeState()
    server, base_url = _host(state)
    try:
        client = HttpRouterDispatch(base_url)
        state.set(200, b'{"status": 200, "public_code": "weird_code", "dispatched": true}')
        before = state.calls
        outcome = client.dispatch(_tenant_ctx(), _tenant_decision())
        assert (outcome.status, outcome.public_code) == (503, "unavailable")
        assert state.calls - before == 1, "the client must make exactly one attempt (no retry loop)"
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    _h.run(
        [
            test_serializes_exact_request_envelope_and_maps_ok,
            test_control_null_tenant_serialized_and_ok,
            test_maps_success_and_mirrored_denials,
            test_bad_shapes_collapse_fail_closed,
            test_httperror_empty_body_collapses,
            test_timeout_and_connection_refused_collapse,
            test_single_attempt_no_retry_loop,
        ]
    )
