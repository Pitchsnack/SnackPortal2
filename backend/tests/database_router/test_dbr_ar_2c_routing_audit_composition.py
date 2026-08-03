"""Behavioral tests for the Database-Router durable routing-audit composition + failure semantics (DBR-AR-2C).

Proves the C2 opt-in seam in ``build_router_from_env`` (database_router/main.py) and the
bounded per-event-class policy: gate-first (the audit env is NOT consulted while the outer
routing seam is inactive — a deliberately malformed audit value does not raise); selector
unset/empty preserves the prior in-memory composition; a valid internal URL composes
``BoundedRoutingAuditPolicy`` over ``HttpRoutingAudit`` bound to exactly that URL with the
pinned default timeout 2.0 (explicit timeouts pass through; invalid/non-finite/out-of-bounds
fail closed with a ValueError that never echoes the configured URL); credentials/query/
fragment/off-scheme URLs fail closed; once selected, durable mode is never the in-memory
sink. Policy semantics (over the REAL transport-error type): exactly one same-event retry
for ``unavailable`` only; no retry for ``invalid``/``conflict``/non-transport failures;
Route/RouteControl terminal failure re-raises; RouteDenied/IsolationAnomaly terminal
failure preserves the original outcome and increments exactly its fixed counter. Router
integration (stdlib doubles): a failed Route audit discards the acquired connection and
denies ``routing_audit_unavailable`` (503) without recursive audit; a failed RouteControl
audit denies the same way; denial and isolation-anomaly records degrade per condition 3
with the original denial preserved. One wire-level proof drives the COMPOSED policy against
a scripted loopback ingest server (test-owned daemon hosting thread — the established
precedent; production stays thread-free), proving the composed retry over the real wire and
that ``DUPLICATE_MATCH`` stays success. DB-free (no live PostgreSQL); runnable standalone:
  python tests/database_router/test_dbr_ar_2c_routing_audit_composition.py
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402
from _db_doubles import (  # noqa: E402
    FakeConnection,
    FakeConnectionFactory,
    FakeRoutingRead,
    FakeSecretStore,
    make_router,
)

from database_router.adapters.providers.http_routing_audit import RoutingAuditTransportError  # noqa: E402
from database_router.adapters.providers.in_memory_audit_sink import InMemoryAuditSink  # noqa: E402
from database_router.cache import RoutingViewCache  # noqa: E402
from database_router.main import (  # noqa: E402
    SP2_DBR_ROUTING_AUDIT_BASE_URL,
    SP2_DBR_ROUTING_AUDIT_TIMEOUT_SECONDS,
    SP2_DBR_ROUTING_READ_BASE_URL,
    BoundedRoutingAuditPolicy,
    build_router_from_env,
)
from database_router.models import RoutingAuditEvent, RoutingDenied, RoutingTarget  # noqa: E402
from database_router.resolver import RoutingResolver  # noqa: E402
from database_router.router import DatabaseRouter  # noqa: E402
from shared.context import RequestContext  # noqa: E402

_VARS = (SP2_DBR_ROUTING_READ_BASE_URL, SP2_DBR_ROUTING_AUDIT_BASE_URL, SP2_DBR_ROUTING_AUDIT_TIMEOUT_SECONDS)


@contextlib.contextmanager
def _env(read: Optional[str], audit: Optional[str] = None, timeout: Optional[str] = None) -> Iterator[None]:
    """Set the three seam env vars for one test (None => unset); restore all afterward."""
    prior = {k: os.environ.get(k) for k in _VARS}
    try:
        for key, value in zip(_VARS, (read, audit, timeout), strict=False):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key in _VARS:
            if prior[key] is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior[key]


def _ctx(tenant: Optional[str] = "t1", *, role: str = "TENANT_ADMIN") -> RequestContext:
    return RequestContext(correlation_id="cid-2c", request_id="req-2c", active_tenant_id=tenant, principal_ref="principal_2c", role=role)


_OUTCOMES = {"Route": "success", "RouteControl": "success", "RouteDenied": "denied:not_found", "IsolationAnomaly": "anomaly:tenant_binding"}


def _event(action: str = "Route") -> RoutingAuditEvent:
    return RoutingAuditEvent(
        actor_ref="principal_2c",
        action=action,
        correlation_id="cid-2c",
        outcome=_OUTCOMES[action],
        target_ref="t1",
        event_id="00000000-0000-4000-8000-000000000001",
        event_version=1,
        occurred_at="2026-07-14T00:00:00+00:00",
        source_service="database_router",
        source_version="4",
        request_ref="req-2c",
        public_code="not_found" if action == "RouteDenied" else None,
    )


class _ScriptedInner:
    """RoutingAuditPort double: answers each initiate from a script of None (success),
    a transport-error kind string, or an exception instance; records every attempt."""

    def __init__(self, script: Sequence[Any]) -> None:
        self.script: List[Any] = list(script)
        self.calls: List[RoutingAuditEvent] = []

    def initiate(self, event: RoutingAuditEvent) -> None:
        self.calls.append(event)
        step = self.script.pop(0) if self.script else None
        if step is None:
            return
        if isinstance(step, str):
            raise RoutingAuditTransportError(step)
        assert isinstance(step, BaseException)
        raise step  # a non-transport exception instance


def _policy(script: Sequence[Any]) -> Tuple[BoundedRoutingAuditPolicy, _ScriptedInner]:
    inner = _ScriptedInner(script)
    return BoundedRoutingAuditPolicy(inner, transport_error=RoutingAuditTransportError), inner


def _expect_value_error(**env_kw: Optional[str]) -> str:
    with _env(**env_kw):
        try:
            build_router_from_env()
        except ValueError as exc:
            return str(exc)
    raise AssertionError("expected ValueError (fail closed — never a silent fallback)")


# --- C2 selection: gate-first, unset-preserves, valid-composes ---------------------------------
def test_outer_gate_inactive_never_consults_audit_env() -> None:
    # A deliberately MALFORMED audit URL + timeout prove the audit env is not consulted
    # while the outer routing seam is inactive: consulting either would raise ValueError.
    with _env(read=None, audit="ftp://user:pass@evil?x=1#f", timeout="not-a-number"):
        assert build_router_from_env() is None, "an inactive outer seam must return None without reading the audit env"


def test_audit_selector_unset_preserves_in_memory_composition() -> None:
    for audit_value in (None, "", "   ", "\t"):
        with _env(read="http://127.0.0.1:1234", audit=audit_value):
            router = build_router_from_env()
        assert isinstance(router, DatabaseRouter)
        assert isinstance(router._audit, InMemoryAuditSink), (
            "selector unset/empty must preserve the prior in-memory composition byte-for-byte"
        )


def test_valid_audit_url_composes_bounded_policy_over_http_client() -> None:
    with _env(read="http://127.0.0.1:1234", audit="http://127.0.0.1:8125"):
        router = build_router_from_env()
    assert isinstance(router, DatabaseRouter)
    policy = router._audit
    assert isinstance(policy, BoundedRoutingAuditPolicy), "a valid opt-in must compose the bounded per-event-class policy"
    inner: Any = policy._inner
    assert type(inner).__name__ == "HttpRoutingAudit", "the policy must wrap the durable transport client"
    assert inner._base == "http://127.0.0.1:8125", "the client must bind exactly the configured base URL"
    assert inner._timeout == 2.0, "an absent timeout must default to the pinned 2.0 seconds"
    assert not isinstance(policy, InMemoryAuditSink), "durable mode must never be the in-memory sink (no fallback)"


def test_explicit_timeout_passes_through() -> None:
    for raw, expected in (("5.5", 5.5), ("30.0", 30.0), ("  7  ", 7.0), ("0.001", 0.001)):
        with _env(read="http://127.0.0.1:1234", audit="http://127.0.0.1:8125", timeout=raw):
            router = build_router_from_env()
        assert isinstance(router, DatabaseRouter)
        policy = router._audit
        assert isinstance(policy, BoundedRoutingAuditPolicy)
        inner: Any = policy._inner
        assert inner._timeout == expected, f"timeout {raw!r} must pass through as {expected}"


def test_invalid_timeout_fails_closed() -> None:
    for bad in ("abc", "0", "-2", "30.1", "1000", "nan", "inf", "-inf", "1e400"):
        message = _expect_value_error(read="http://127.0.0.1:1234", audit="http://127.0.0.1:8125", timeout=bad)
        assert SP2_DBR_ROUTING_AUDIT_TIMEOUT_SECONDS in message, f"the timeout error must name the knob for {bad!r}"


def test_invalid_audit_url_fails_closed_without_echo() -> None:
    for bad in (
        "not a url",
        "127.0.0.1:8125",
        "ftp://127.0.0.1:8125",
        "https://127.0.0.1:8443",
        "http://",
        "http://user:secretpw@127.0.0.1:8125",
        "http://127.0.0.1:8125?x=1",
        "http://127.0.0.1:8125#frag",
    ):
        message = _expect_value_error(read="http://127.0.0.1:1234", audit=bad)
        assert SP2_DBR_ROUTING_AUDIT_BASE_URL in message, f"the URL error must name the selector for {bad!r}"
        # The distinctive configured material (ports, credentials) must never be echoed.
        assert "secretpw" not in message and "8125" not in message and "8443" not in message, (
            "the bounded URL error must never echo the configured value"
        )


# --- D4: the single bounded retry ---------------------------------------------------------------
def test_success_first_call_no_retry() -> None:
    policy, inner = _policy([None])
    event = _event("Route")
    policy.initiate(event)
    assert inner.calls == [event], "a successful first attempt must be the only transport call"


def test_unavailable_then_success_retries_same_event_once() -> None:
    policy, inner = _policy(["unavailable", None])
    event = _event("Route")
    policy.initiate(event)  # must NOT raise: the single retry succeeded
    assert len(inner.calls) == 2 and inner.calls[0] is event and inner.calls[1] is event, (
        "exactly one immediate retry of the SAME event object (same event_id, same payload)"
    )
    assert policy.degradation_snapshot() == {"route_denied_audit_failures": 0, "isolation_anomaly_audit_failures": 0}


def test_unavailable_twice_route_fails_closed_after_two_calls() -> None:
    policy, inner = _policy(["unavailable", "unavailable"])
    try:
        policy.initiate(_event("Route"))
    except RoutingAuditTransportError as exc:
        assert exc.kind == "unavailable"
    else:
        raise AssertionError("a finally-failed Route write must re-raise (the router fails the route closed)")
    assert len(inner.calls) == 2, "maximum two total transport calls (first attempt + the single retry)"


def test_invalid_and_conflict_never_retry() -> None:
    for kind in ("invalid", "conflict"):
        for action in ("Route", "RouteControl"):
            policy, inner = _policy([kind])
            try:
                policy.initiate(_event(action))
            except RoutingAuditTransportError as exc:
                assert exc.kind == kind
            else:
                raise AssertionError(f"a {kind} failure on {action} must re-raise")
            assert len(inner.calls) == 1, f"{kind} must NEVER be retried"


def test_non_transport_failure_never_retries() -> None:
    policy, inner = _policy([RuntimeError("boom")])
    try:
        policy.initiate(_event("Route"))
    except RuntimeError:
        pass
    else:
        raise AssertionError("a non-transport failure on Route must re-raise (fail closed)")
    assert len(inner.calls) == 1, "only kind == 'unavailable' transport failures are retryable"


# --- D6/D7: denial/anomaly preservation + fixed counters ----------------------------------------
def test_route_denied_terminal_failure_swallowed_and_counted() -> None:
    for script, expected_calls in ((["unavailable", "unavailable"], 2), (["invalid"], 1), ([RuntimeError("boom")], 1)):
        policy, inner = _policy(list(script))
        policy.initiate(_event("RouteDenied"))  # must NOT raise: the original denial is preserved
        assert len(inner.calls) == expected_calls
        assert policy.degradation_snapshot() == {"route_denied_audit_failures": 1, "isolation_anomaly_audit_failures": 0}


def test_isolation_anomaly_terminal_failure_swallowed_and_counted() -> None:
    for script, expected_calls in ((["unavailable", "unavailable"], 2), (["conflict"], 1)):
        policy, inner = _policy(list(script))
        policy.initiate(_event("IsolationAnomaly"))  # must NOT raise: discard + isolation denial preserved
        assert len(inner.calls) == expected_calls
        assert policy.degradation_snapshot() == {"route_denied_audit_failures": 0, "isolation_anomaly_audit_failures": 1}


def test_snapshot_is_exactly_two_integer_keys_and_accumulates() -> None:
    policy, _ = _policy(["invalid", "invalid", "conflict"])
    policy.initiate(_event("RouteDenied"))
    policy.initiate(_event("RouteDenied"))
    policy.initiate(_event("IsolationAnomaly"))
    snapshot = policy.degradation_snapshot()
    assert set(snapshot.keys()) == {"route_denied_audit_failures", "isolation_anomaly_audit_failures"}, (
        "the degradation snapshot must expose EXACTLY the two fixed keys"
    )
    assert snapshot == {"route_denied_audit_failures": 2, "isolation_anomaly_audit_failures": 1}
    assert all(type(v) is int for v in snapshot.values()), "integer counts only — no payload"


# --- D5: router condition-1 behavior (discard + bounded denial; no recursive audit) --------------
def _wired_router(script: List[Optional[object]]):
    read = FakeRoutingRead()
    read.set_view("t1")
    policy, inner = _policy(script)
    factory = FakeConnectionFactory()
    router, _cache, pool, _resolver = make_router(read=read, secret_store=FakeSecretStore(), factory=factory, audit=policy)
    return router, pool, policy, inner


def test_route_success_audit_failure_discards_connection_and_denies() -> None:
    router, pool, policy, inner = _wired_router(["unavailable", "unavailable"])
    try:
        router.route(_ctx())
    except RoutingDenied as denied:
        assert denied.public_code == "routing_audit_unavailable" and denied.http_status == 503, (
            "the allowed route must fail closed with the bounded non-leaking 503-bucket denial"
        )
    else:
        raise AssertionError("an allowed route whose durable audit finally failed must NOT be handed back")
    assert pool.counts("t1", "1") == (0, 0), "the acquired connection must be discarded (not stranded in_use, not idle)"
    assert len(inner.calls) == 2 and all(e.action == "Route" for e in inner.calls), (
        "exactly the Route event was attempted (once + one retry); the routing_audit_unavailable denial is never recursively audited"
    )
    assert policy.degradation_snapshot() == {"route_denied_audit_failures": 0, "isolation_anomaly_audit_failures": 0}


def test_route_control_audit_failure_denies_without_recursive_audit() -> None:
    router, pool, _policy_obj, inner = _wired_router(["invalid"])
    try:
        router.route(_ctx(tenant=None, role="CONTROL"))
    except RoutingDenied as denied:
        assert denied.public_code == "routing_audit_unavailable" and denied.http_status == 503
    else:
        raise AssertionError("an allowed control route whose audit finally failed must NOT be handed back")
    assert len(inner.calls) == 1 and inner.calls[0].action == "RouteControl", "no retry for invalid; no recursive audit"
    assert pool.pool_keys() == [], "the control target never touches a tenant pool"


def test_route_denied_audit_failure_preserves_original_denial() -> None:
    router, _pool, policy, inner = _wired_router(["unavailable", "unavailable"])
    try:
        router.route(_ctx(tenant="ghost"))  # unknown tenant -> not_found at the router edge
    except RoutingDenied as denied:
        assert denied.public_code == "not_found" and denied.http_status == 404, (
            "the ORIGINAL denial must be preserved unchanged (condition 3 — never replaced, never upgraded)"
        )
    else:
        raise AssertionError("the request must stay denied")
    assert len(inner.calls) == 2 and inner.calls[0].action == "RouteDenied"
    assert policy.degradation_snapshot()["route_denied_audit_failures"] == 1, "the lost denial record must be counted"


def test_audit_success_leaves_routing_behavior_unchanged() -> None:
    router, pool, policy, inner = _wired_router([None])
    result = router.route(_ctx())
    assert result.target is RoutingTarget.TENANT and result.tenant_id == "t1" and result.connection is not None
    assert len(inner.calls) == 1 and inner.calls[0].action == "Route"
    assert pool.counts("t1", "1") == (0, 1), "the connection is handed back in_use exactly as before"
    router.release(result)
    assert policy.degradation_snapshot() == {"route_denied_audit_failures": 0, "isolation_anomaly_audit_failures": 0}


class _PassThroughPool:
    """Hands back a preset (deliberately divergent) connection and records discards — the
    real pool's own binding check would intercept a misbound connection before the
    router's D-30 L3 check (the 2A local-double precedent)."""

    def __init__(self, conn: FakeConnection) -> None:
        self._conn = conn
        self.discarded: List[FakeConnection] = []

    def acquire(self, tenant_id: str, association_version: str, open_fn: Any) -> FakeConnection:
        return self._conn

    def release(self, conn: FakeConnection) -> None:
        return None

    def discard(self, conn: FakeConnection) -> None:
        self.discarded.append(conn)
        conn.close()


def test_isolation_anomaly_audit_failure_preserves_discard_and_denial() -> None:
    read = FakeRoutingRead()
    read.set_view("t1")
    policy, inner = _policy(["unavailable", "unavailable"])
    divergent = FakeConnection("evil-other-tenant", "1")
    pool = _PassThroughPool(divergent)
    router = DatabaseRouter(
        resolver=RoutingResolver(read, RoutingViewCache(ttl_seconds=15.0), supported_schema_versions=("1",)),
        pool=pool,  # type: ignore[arg-type]
        secret_store=FakeSecretStore(),
        connection_factory=FakeConnectionFactory(),
        audit=policy,
    )
    try:
        router.route(_ctx())
    except RoutingDenied as denied:
        assert denied.public_code == "routing_isolation_fault" and denied.http_status == 503, (
            "the EXISTING isolation denial must be preserved unchanged (never replaced by an audit-failure denial)"
        )
    else:
        raise AssertionError("a tenant-binding fault must stay denied")
    assert pool.discarded == [divergent], "the existing connection discard must be preserved"
    assert len(inner.calls) == 2 and inner.calls[0].action == "IsolationAnomaly"
    assert policy.degradation_snapshot()["isolation_anomaly_audit_failures"] == 1, "the lost anomaly record must be counted"


# --- wire-level proof: the COMPOSED policy over the real ingest envelope -------------------------
class _WireState:
    def __init__(self, responses: List[Tuple[int, Optional[Dict[str, object]]]]) -> None:
        self.responses = list(responses)
        self.requests: List[Tuple[str, Dict[str, object]]] = []


def _wire_handler(state: _WireState) -> "type[BaseHTTPRequestHandler]":
    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 (http.server API)
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            state.requests.append((self.path, body))
            status, payload = state.responses.pop(0) if state.responses else (200, {"version": 1, "result": "INSERTED"})
            raw = json.dumps(payload).encode("utf-8") if payload is not None else b""
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args: object) -> None:
            return

    return _Handler


@contextlib.contextmanager
def _wire_server(responses: List[Tuple[int, Optional[Dict[str, object]]]]) -> Iterator[Tuple[_WireState, str]]:
    state = _WireState(responses)
    server = HTTPServer(("127.0.0.1", 0), _wire_handler(state))
    base = f"http://{server.server_address[0]}:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)  # test-owned hosting thread only
    thread.start()
    try:
        yield state, base
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_composed_policy_speaks_the_real_wire_with_bounded_retry() -> None:
    # 503 then INSERTED: the COMPOSED policy (built through the env seam) must retry once
    # over the real wire and succeed; DUPLICATE_MATCH replay stays success on one call.
    with _wire_server([(503, {"version": 1, "result": "UNAVAILABLE"}), (200, {"version": 1, "result": "INSERTED"})]) as (state, base):
        with _env(read="http://127.0.0.1:1234", audit=base, timeout="5"):
            router = build_router_from_env()
        assert isinstance(router, DatabaseRouter)
        policy = router._audit
        assert isinstance(policy, BoundedRoutingAuditPolicy)
        policy.initiate(_event("Route"))  # must NOT raise: one bounded retry over the wire
        assert len(state.requests) == 2, "exactly two wire calls: the failed attempt + the single retry"
        assert all(path == "/internal/routing-audit/events" for path, _ in state.requests)
        first, second = state.requests[0][1], state.requests[1][1]
        assert first == second, "the retry must submit the SAME envelope (same event_id, same payload)"
    with _wire_server([(200, {"version": 1, "result": "DUPLICATE_MATCH"})]) as (state, base):
        with _env(read="http://127.0.0.1:1234", audit=base):
            router = build_router_from_env()
        assert isinstance(router, DatabaseRouter)
        router._audit.initiate(_event("Route"))  # DUPLICATE_MATCH is success (idempotent replay)
        assert len(state.requests) == 1, "an idempotent duplicate answer must not trigger a retry"


if __name__ == "__main__":
    _h.run(
        [
            test_outer_gate_inactive_never_consults_audit_env,
            test_audit_selector_unset_preserves_in_memory_composition,
            test_valid_audit_url_composes_bounded_policy_over_http_client,
            test_explicit_timeout_passes_through,
            test_invalid_timeout_fails_closed,
            test_invalid_audit_url_fails_closed_without_echo,
            test_success_first_call_no_retry,
            test_unavailable_then_success_retries_same_event_once,
            test_unavailable_twice_route_fails_closed_after_two_calls,
            test_invalid_and_conflict_never_retry,
            test_non_transport_failure_never_retries,
            test_route_denied_terminal_failure_swallowed_and_counted,
            test_isolation_anomaly_terminal_failure_swallowed_and_counted,
            test_snapshot_is_exactly_two_integer_keys_and_accumulates,
            test_route_success_audit_failure_discards_connection_and_denies,
            test_route_control_audit_failure_denies_without_recursive_audit,
            test_route_denied_audit_failure_preserves_original_denial,
            test_audit_success_leaves_routing_behavior_unchanged,
            test_isolation_anomaly_audit_failure_preserves_discard_and_denial,
            test_composed_policy_speaks_the_real_wire_with_bounded_retry,
        ]
    )
