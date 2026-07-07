"""Behavioral tests for the gateway-side authentication client (07E-3b).

Drives ``HttpAuthenticator`` against a configurable fake auth server hosted on a test-owned
daemon thread (the D-15-T1b client-test precedent). Proves the client half of the
AUTH-TRANSPORT-SPEC-01 wire contract: it serializes exactly ``{v, authorization,
recognized_carriers, correlation_id}`` (and no forbidden field), maps a references-only 200
body to the exact 4-field ``AuthResult``, maps the mirrored 4xx/5xx denials to the existing
``RequestRejected`` factories, never logs the credential, and collapses every malformed /
wrong-shape / oversized / missing-field / timeout / transport-failure case fail-closed to
``unavailable`` — single attempt, no DB, no dispatch. Stub server only (no ``auth_router``).
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from api_gateway.adapters.providers.http_authenticator import HttpAuthenticator  # noqa: E402
from api_gateway.models import AuthResult, RequestRejected  # noqa: E402

_PATH = "/internal/auth/authenticate"
_TENANT_BODY = b'{"correlation_id": "cid", "principal_ref": "u1", "active_tenant_id": "t1", "role": "TENANT_AGENT"}'
_CONTROL_BODY = b'{"correlation_id": "cid", "principal_ref": "ctl", "active_tenant_id": null, "role": null}'


class _FakeState:
    def __init__(self) -> None:
        self.status = 200
        self.body: Optional[bytes] = _TENANT_BODY
        self.delay = 0.0
        self.calls = 0
        self.last_path: Optional[str] = None
        self.last_body: Optional[bytes] = None

    def set(self, status: int, body: Optional[bytes]) -> None:
        self.status = status
        self.body = body


def _fake_handler(state: _FakeState):
    class _H(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            state.calls += 1
            state.last_path = self.path
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
    # Suppress the expected aborted-socket traceback when the client times out and closes the
    # connection while a delayed handler is still writing (the timeout test).
    def handle_error(self, request: object, client_address: object) -> None:
        return


def _host(state: _FakeState):
    server = _QuietHTTPServer(("127.0.0.1", 0), _fake_handler(state))
    host, port = server.server_address[0], server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://{host}:{port}"


# --- success mapping ------------------------------------------------------------------------------
def test_valid_tenant_success_returns_exact_four_field_authresult() -> None:
    state = _FakeState()
    server, base_url = _host(state)
    try:
        result = HttpAuthenticator(base_url).authenticate("Bearer opaque-credential-1", ["t1"], "cid")
        assert isinstance(result, AuthResult)
        assert (result.correlation_id, result.principal_ref, result.active_tenant_id, result.role) == ("cid", "u1", "t1", "TENANT_AGENT")
    finally:
        server.shutdown()
        server.server_close()


def test_valid_control_success_has_null_active_tenant() -> None:
    state = _FakeState()
    state.set(200, _CONTROL_BODY)
    server, base_url = _host(state)
    try:
        result = HttpAuthenticator(base_url).authenticate("Bearer opaque-credential-1", [], "cid")
        # CONTROL is derived from active_tenant_id is None (never a boolean field).
        assert result.active_tenant_id is None and result.role is None and result.principal_ref == "ctl"
    finally:
        server.shutdown()
        server.server_close()


def test_request_envelope_is_exactly_the_four_spec_fields() -> None:
    state = _FakeState()
    server, base_url = _host(state)
    try:
        HttpAuthenticator(base_url).authenticate("Bearer opaque-credential-1", ["t1"], "cid")
        sent = json.loads(state.last_body or b"{}")
        assert set(sent.keys()) == {"v", "authorization", "recognized_carriers", "correlation_id"}, sent
        assert sent["v"] == 1 and sent["recognized_carriers"] == ["t1"] and sent["correlation_id"] == "cid"
        assert state.last_path == _PATH
        # No never-cross / routing identifier is serialized as a request KEY (the credential
        # VALUE legitimately appears in the authorization field, so this checks keys, not text).
        for forbidden_key in (
            "token",
            "secret",
            "credential",
            "dsn",
            "database_url",
            "dispatchdecision",
            "routeoutcome",
            "role",
            "principal_ref",
        ):
            assert forbidden_key not in sent, f"{forbidden_key} must not be a request key"
    finally:
        server.shutdown()
        server.server_close()


def test_credential_is_sent_on_the_wire_but_never_logged() -> None:
    state = _FakeState()
    server, base_url = _host(state)
    cred = "opaque-credential-DO-NOT-LOG"
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            HttpAuthenticator(base_url).authenticate(f"Bearer {cred}", ["t1"], "cid")
        # The credential crosses the wire (required for validation) ...
        sent = json.loads(state.last_body or b"{}")
        assert sent["authorization"] == f"Bearer {cred}"
        # ... but is never emitted to any client-side log/stdout/stderr.
        assert cred not in buf.getvalue()
    finally:
        server.shutdown()
        server.server_close()


# --- failure mapping (fail-closed) ----------------------------------------------------------------
def test_denial_status_maps_to_fail_closed_rejections() -> None:
    for status, public_code, expected in [
        (401, "unauthenticated", "unauthenticated"),
        (403, "carrier_mismatch", "carrier_mismatch"),
        (403, "forbidden", "forbidden"),
        (503, "unavailable", "unavailable"),
    ]:
        state = _FakeState()
        state.set(status, json.dumps({"status": status, "public_code": public_code}).encode("utf-8"))
        server, base_url = _host(state)
        try:
            raised: Optional[RequestRejected] = None
            try:
                HttpAuthenticator(base_url).authenticate("Bearer opaque-credential-1", ["t1"], "cid")
            except RequestRejected as exc:
                raised = exc
            assert raised is not None and (raised.http_status, raised.public_code) == (status, expected)
        finally:
            server.shutdown()
            server.server_close()


def test_403_without_public_code_defaults_to_forbidden() -> None:
    state = _FakeState()
    state.set(403, b"")  # empty 403 body -> cannot be carrier_mismatch -> forbidden (same status, fail-closed)
    server, base_url = _host(state)
    try:
        raised: Optional[RequestRejected] = None
        try:
            HttpAuthenticator(base_url).authenticate("Bearer opaque-credential-1", ["t1"], "cid")
        except RequestRejected as exc:
            raised = exc
        assert raised is not None and (raised.http_status, raised.public_code) == (403, "forbidden")
    finally:
        server.shutdown()
        server.server_close()


def test_connection_refused_maps_to_unavailable() -> None:
    raised: Optional[RequestRejected] = None
    try:
        HttpAuthenticator("http://127.0.0.1:1", timeout=1.0).authenticate("Bearer opaque-credential-1", ["t1"], "cid")
    except RequestRejected as exc:
        raised = exc
    assert raised is not None and (raised.http_status, raised.public_code) == (503, "unavailable")


def test_timeout_maps_to_unavailable() -> None:
    state = _FakeState()
    state.delay = 1.0
    server, base_url = _host(state)
    try:
        raised: Optional[RequestRejected] = None
        try:
            HttpAuthenticator(base_url, timeout=0.2).authenticate("Bearer opaque-credential-1", ["t1"], "cid")
        except RequestRejected as exc:
            raised = exc
        assert raised is not None and (raised.http_status, raised.public_code) == (503, "unavailable")
    finally:
        server.shutdown()
        server.server_close()


def test_malformed_oversized_and_wrong_shape_bodies_collapse_fail_closed() -> None:
    bad_bodies = [
        b"{not json",  # malformed JSON
        b"[1, 2, 3]",  # non-object JSON
        b'{"correlation_id": "cid", "principal_ref": "u1", "active_tenant_id": "t1", "role": "TENANT_AGENT", "extra": 1}',  # extra field
        b'{"correlation_id": "cid", "principal_ref": "u1", "active_tenant_id": "t1"}',  # missing field (role)
        b'{"correlation_id": 1, "principal_ref": "u1", "active_tenant_id": "t1", "role": "TENANT_AGENT"}',  # wrong-type correlation_id
        b'{"correlation_id": "cid", "principal_ref": "u1", "active_tenant_id": 5, "role": "TENANT_AGENT"}',  # wrong-type active_tenant_id
    ]
    for body in bad_bodies:
        state = _FakeState()
        state.set(200, body)
        server, base_url = _host(state)
        try:
            raised: Optional[RequestRejected] = None
            try:
                HttpAuthenticator(base_url).authenticate("Bearer opaque-credential-1", ["t1"], "cid")
            except RequestRejected as exc:
                raised = exc
            assert raised is not None and (raised.http_status, raised.public_code) == (503, "unavailable"), body
        finally:
            server.shutdown()
            server.server_close()


def test_oversized_success_body_collapses_fail_closed() -> None:
    state = _FakeState()
    server, base_url = _host(state)
    try:
        # A well-formed 200 body that exceeds the client's response-size limit -> unavailable.
        raised: Optional[RequestRejected] = None
        try:
            HttpAuthenticator(base_url, max_response_bytes=16).authenticate("Bearer opaque-credential-1", ["t1"], "cid")
        except RequestRejected as exc:
            raised = exc
        assert raised is not None and (raised.http_status, raised.public_code) == (503, "unavailable")
    finally:
        server.shutdown()
        server.server_close()


def test_single_transport_attempt_and_no_dispatch_on_failure() -> None:
    # No DB connection opened / no dispatch: the client makes exactly ONE transport call to the
    # auth path and, on a denial, raises RequestRejected (the pipeline never proceeds to routing).
    state = _FakeState()
    state.set(401, json.dumps({"status": 401, "public_code": "unauthenticated"}).encode("utf-8"))
    server, base_url = _host(state)
    try:
        before = state.calls
        raised: Optional[RequestRejected] = None
        try:
            HttpAuthenticator(base_url).authenticate("Bearer opaque-credential-1", ["t1"], "cid")
        except RequestRejected as exc:
            raised = exc
        assert raised is not None and raised.http_status == 401
        assert state.calls - before == 1, "the client must make exactly one attempt (no retry, no extra connection)"
        assert state.last_path == _PATH, "the client contacts only the internal auth path (no other/DB connection)"
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    _h.run(
        [
            test_valid_tenant_success_returns_exact_four_field_authresult,
            test_valid_control_success_has_null_active_tenant,
            test_request_envelope_is_exactly_the_four_spec_fields,
            test_credential_is_sent_on_the_wire_but_never_logged,
            test_denial_status_maps_to_fail_closed_rejections,
            test_403_without_public_code_defaults_to_forbidden,
            test_connection_refused_maps_to_unavailable,
            test_timeout_maps_to_unavailable,
            test_malformed_oversized_and_wrong_shape_bodies_collapse_fail_closed,
            test_oversized_success_body_collapses_fail_closed,
            test_single_transport_attempt_and_no_dispatch_on_failure,
        ]
    )
