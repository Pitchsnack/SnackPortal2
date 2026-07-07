"""Behavioral tests for the router-side dispatch server (D-15-T1b).

Hosts the single-threaded ``build_dispatch_server`` on a test-owned daemon thread (the
requires_pg / read-edge precedent) and drives it over real HTTP with ``http.client``. The
router is composed from the stdlib database_router doubles — no PostgreSQL, no driver, no
network beyond loopback. Proves the T1a wire contract at the server edge: exact envelope
validation, the references-only response, category-is-advisory, null CONTROL routes, the
denial mapping, release-before-respond, and the fail-closed empty-body edges.
"""

from __future__ import annotations

import http.client
import json
import pathlib
import sys
import threading
from typing import Optional, Tuple
from urllib.parse import urlsplit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _db_doubles as D  # noqa: E402
import _h  # noqa: E402

from database_router.adapters.providers.http_dispatch_api import build_dispatch_server  # noqa: E402

_PATH = "/internal/dispatch/route"


def _compose():
    read = D.FakeRoutingRead()
    read.set_view("t1", schema="1")  # a routable Ready tenant
    read.set_view("susp", lifecycle="Suspended", ready=False)  # -> administratively_disabled
    # "ghost" intentionally has no view -> not_found
    factory = D.FakeConnectionFactory()
    secret = D.FakeSecretStore()
    audit = D.FakeAudit()
    router, _cache, pool, _resolver = D.make_router(read=read, secret_store=secret, factory=factory, audit=audit, supported=("1",))
    return router, pool, factory, audit


def _host(router):
    server, base_url = build_dispatch_server(router, "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, base_url


def _do(
    base_url: str,
    *,
    method: str = "POST",
    path: str = _PATH,
    payload: Optional[dict] = None,
    raw_body: Optional[bytes] = None,
) -> Tuple[int, bytes]:
    parts = urlsplit(base_url)
    conn = http.client.HTTPConnection(parts.hostname or "127.0.0.1", parts.port, timeout=5)
    try:
        body: Optional[bytes]
        if raw_body is not None:
            body = raw_body
        elif payload is not None:
            body = json.dumps(payload).encode("utf-8")
        else:
            body = None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


def _env(
    *,
    correlation_id: str = "c1",
    request_id=None,
    active_tenant_id=None,
    principal_ref=None,
    role=None,
    category: str = "TENANT_OPERATION",
    v: int = 1,
) -> dict:
    return {
        "v": v,
        "context": {
            "correlation_id": correlation_id,
            "request_id": request_id,
            "active_tenant_id": active_tenant_id,
            "principal_ref": principal_ref,
            "role": role,
        },
        "category": category,
    }


def test_default_bind_is_loopback() -> None:
    router, _pool, _factory, _audit = _compose()
    server, base_url = _host(router)
    try:
        assert base_url.startswith("http://127.0.0.1:"), base_url
    finally:
        server.shutdown()
        server.server_close()


def test_tenant_dispatch_ok_and_release_before_response() -> None:
    router, pool, factory, audit = _compose()
    server, base_url = _host(router)
    try:
        status, body = _do(base_url, payload=_env(active_tenant_id="t1", role="TENANT_AGENT"))
        assert status == 200
        data = json.loads(body)
        assert set(data.keys()) == {"status", "public_code", "dispatched"}, data
        assert data == {"status": 200, "public_code": "ok", "dispatched": True}
        # one request -> one tenant -> one DB; released before responding (in_use == 0).
        assert len(factory.opens) == 1 and factory.opens[0][0] == "t1"
        assert pool.counts("t1", "1")[1] == 0, "the tenant connection must be released before the response"
        assert "Route" in audit.actions() and "RouteControl" not in audit.actions()
    finally:
        server.shutdown()
        server.server_close()


def test_control_null_tenant_dispatch_ok() -> None:
    router, _pool, factory, audit = _compose()
    server, base_url = _host(router)
    try:
        # RF-1: null active_tenant_id + CONTROL role is a valid CONTROL route (advisory
        # category is a real control-domain value, never a synthetic CONTROL_OPERATION).
        status, body = _do(base_url, payload=_env(correlation_id="cc", role="CONTROL", category="GLOBAL_DIRECTORY_READ"))
        assert status == 200
        assert json.loads(body) == {"status": 200, "public_code": "ok", "dispatched": True}
        assert not factory.opens, "a CONTROL route opens no tenant connection"
        assert "RouteControl" in audit.actions()
    finally:
        server.shutdown()
        server.server_close()


def test_null_role_null_tenant_maps_to_no_active_tenant() -> None:
    router, _pool, _factory, _audit = _compose()
    server, base_url = _host(router)
    try:
        # RF-6: a null-role/null-tenant envelope is transport-VALID; the router denies it.
        status, body = _do(base_url, payload=_env(role=None))
        assert status == 403
        assert json.loads(body) == {"status": 403, "public_code": "no_active_tenant", "dispatched": False}
    finally:
        server.shutdown()
        server.server_close()


def test_category_is_advisory_not_a_selector() -> None:
    router, _pool, factory, _audit = _compose()
    server, base_url = _host(router)
    try:
        # A tenant claim carrying a control-domain advisory category still routes to the
        # tenant (the claim decides, not the category) -> category is not a selector.
        status, body = _do(base_url, payload=_env(active_tenant_id="t1", role="TENANT_AGENT", category="GLOBAL_DIRECTORY_READ"))
        assert status == 200 and json.loads(body)["public_code"] == "ok"
        assert factory.opens and factory.opens[-1][0] == "t1", "routing followed the signed claim, not the category"
    finally:
        server.shutdown()
        server.server_close()


def test_denial_mapping_not_found_and_administratively_disabled() -> None:
    router, _pool, _factory, _audit = _compose()
    server, base_url = _host(router)
    try:
        s1, b1 = _do(base_url, payload=_env(active_tenant_id="ghost", role="TENANT_AGENT"))
        assert s1 == 404 and json.loads(b1) == {"status": 404, "public_code": "not_found", "dispatched": False}
        s2, b2 = _do(base_url, payload=_env(active_tenant_id="susp", role="TENANT_AGENT"))
        assert s2 == 403 and json.loads(b2) == {"status": 403, "public_code": "administratively_disabled", "dispatched": False}
        # No never-cross material in a denial response body.
        assert set(json.loads(b1).keys()) == {"status", "public_code", "dispatched"}
    finally:
        server.shutdown()
        server.server_close()


def test_wrong_method_405_empty_and_wrong_path_404_empty_no_route() -> None:
    router, _pool, factory, audit = _compose()
    server, base_url = _host(router)
    try:
        s_get, b_get = _do(base_url, method="GET")
        assert s_get == 405 and b_get == b"", "non-POST must be 405 empty body"
        s_path, b_path = _do(base_url, path="/nope", payload=_env(active_tenant_id="t1", role="TENANT_AGENT"))
        assert s_path == 404 and b_path == b"", "wrong path must be 404 empty body"
        assert not factory.opens and "Route" not in audit.actions(), "wrong path must not route"
    finally:
        server.shutdown()
        server.server_close()


def test_malformed_and_invalid_envelopes_fail_closed_503_empty() -> None:
    router, _pool, _factory, _audit = _compose()
    server, base_url = _host(router)
    try:
        cases: list = [
            {"raw_body": b"{not json"},  # malformed JSON
            {"raw_body": b"[1,2,3]"},  # non-object JSON
            {"payload": _env(active_tenant_id="t1", role="TENANT_AGENT", v=2)},  # unknown version
            {"payload": {"context": _env()["context"], "category": "TENANT_OPERATION"}},  # missing top-level key (v)
            {"payload": {**_env(active_tenant_id="t1", role="TENANT_AGENT"), "extra": 1}},  # extra top-level key
            {"payload": _env(category="NOPE_CATEGORY")},  # unknown category
        ]
        for case in cases:
            status, body = _do(base_url, **case)
            assert status == 503 and body == b"", f"fail-closed 503 empty expected for {case}"
        # missing/extra context key
        env_missing = _env(active_tenant_id="t1", role="TENANT_AGENT")
        env_missing["context"].pop("role")
        assert _do(base_url, payload=env_missing) == (503, b"")
        env_extra = _env(active_tenant_id="t1", role="TENANT_AGENT")
        env_extra["context"]["oops"] = 1
        assert _do(base_url, payload=env_extra) == (503, b"")
        # wrong field type (active_tenant_id must be str-or-null)
        env_type = _env(role="TENANT_AGENT")
        env_type["context"]["active_tenant_id"] = 123
        assert _do(base_url, payload=env_type) == (503, b"")
    finally:
        server.shutdown()
        server.server_close()


def test_server_exception_fails_closed_503_empty() -> None:
    class _BoomRouter:
        def route(self, ctx):
            raise RuntimeError("boom")

        def release(self, result):  # pragma: no cover - never reached
            return None

    server, base_url = _host(_BoomRouter())
    try:
        status, body = _do(base_url, payload=_env(active_tenant_id="t1", role="TENANT_AGENT"))
        assert status == 503 and body == b"", "an unhandled server exception must fail closed 503 empty (no leak)"
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    _h.run(
        [
            test_default_bind_is_loopback,
            test_tenant_dispatch_ok_and_release_before_response,
            test_control_null_tenant_dispatch_ok,
            test_null_role_null_tenant_maps_to_no_active_tenant,
            test_category_is_advisory_not_a_selector,
            test_denial_mapping_not_found_and_administratively_disabled,
            test_wrong_method_405_empty_and_wrong_path_404_empty_no_route,
            test_malformed_and_invalid_envelopes_fail_closed_503_empty,
            test_server_exception_fails_closed_503_empty,
        ]
    )
