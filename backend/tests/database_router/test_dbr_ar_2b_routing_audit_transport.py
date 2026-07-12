"""DBR-AR-2B — router-side routing-audit transport client behavioral contract (loopback HTTP; DB-free).

Exercises `HttpRoutingAudit` (the uncomposed `RoutingAuditPort` client) against a
scripted loopback stdlib server (test-owned daemon hosting thread — the established
precedent; production stays thread-free): exact seventeen-key wire serialization with
``target_ref`` travelling as ``tenant_ref`` and no ``id``/``store_id``/``recorded_at``/
``trace_ref`` key; INSERTED and DUPLICATE_MATCH both succeed; conflict/invalid/
unavailable answers, malformed or mis-shaped response envelopes, wrong statuses, and
refused connections all raise the bounded `RoutingAuditTransportError` (fixed message,
``kind`` in {invalid, conflict, unavailable}, chained from None); exactly ONE request per
initiate (no retry); no in-memory fallback; and end-to-end interop with the REAL
Control-Plane ingest edge over a store double (structural `RoutingAuditPort`
satisfaction). No database, no external network. Pure stdlib; standalone-runnable:
`python tests/database_router/test_dbr_ar_2b_routing_audit_transport.py`.
"""

from __future__ import annotations

import contextlib
import json
import pathlib
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Iterator, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402,F401  (backend + architecture helpers on path)

from control_plane.adapters.providers.http_routing_audit_api import build_routing_audit_server  # noqa: E402
from control_plane.routing_audit import (  # noqa: E402
    RoutingAuditAppendResult,
    RoutingAuditRecord,
    RoutingAuditStorePort,
)
from database_router.adapters.providers.http_routing_audit import (  # noqa: E402
    HttpRoutingAudit,
    RoutingAuditTransportError,
)
from database_router.adapters.providers.in_memory_audit_sink import InMemoryAuditSink  # noqa: E402
from database_router.models import (  # noqa: E402
    ROUTING_AUDIT_EVENT_VERSION,
    ROUTING_AUDIT_SOURCE_SERVICE,
    ROUTING_AUDIT_SOURCE_VERSION,
    RoutingAuditEvent,
)
from database_router.ports import RoutingAuditPort  # noqa: E402

# ---------------------------------------------------------------------------
# Scripted fake ingest server (records requests; answers from a script)
# ---------------------------------------------------------------------------


class _ServerState:
    def __init__(self, responses: List[Tuple[int, Optional[Dict[str, object]]]]) -> None:
        self.responses = list(responses)
        self.requests: List[Tuple[str, str, bytes]] = []  # (method, path, body)
        self.raw_responses: List[bytes] = []


def _fake_handler(state: _ServerState) -> "type[BaseHTTPRequestHandler]":
    class _H(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length > 0 else b""
            state.requests.append(("POST", self.path, body))
            status, payload = state.responses.pop(0) if state.responses else (200, {"version": 1, "result": "INSERTED"})
            raw = json.dumps(payload).encode("utf-8") if payload is not None else b"this is not json {"
            state.raw_responses.append(raw)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args: object) -> None:
            return

    return _H


@contextlib.contextmanager
def _fake_server(responses: List[Tuple[int, Optional[Dict[str, object]]]]) -> Iterator[Tuple[_ServerState, str]]:
    state = _ServerState(responses)
    server = HTTPServer(("127.0.0.1", 0), _fake_handler(state))
    base = f"http://{server.server_address[0]}:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)  # test-owned hosting thread only
    thread.start()
    try:
        yield state, base
    finally:
        server.shutdown()
        server.server_close()


_OK = {"version": 1, "result": "INSERTED"}
_DUP = {"version": 1, "result": "DUPLICATE_MATCH"}

_EXPECTED_WIRE_KEYS = {
    "event_id",
    "event_version",
    "occurred_at",
    "correlation_id",
    "actor_ref",
    "action",
    "outcome",
    "source_service",
    "source_version",
    "request_ref",
    "tenant_ref",
    "resolved_tenant_ref",
    "public_code",
    "error_class",
    "association_store_ref",
    "association_version",
    "lane",
}


def _event(**overrides: object) -> RoutingAuditEvent:
    base: Dict[str, object] = dict(
        actor_ref="principal:alice",
        action="Route",
        correlation_id="corr-1",
        outcome="success",
        target_ref="tenant-alpha",
        event_id="1f0e6b1a-9b2c-4d3e-8f4a-5b6c7d8e9f0a",
        event_version=ROUTING_AUDIT_EVENT_VERSION,
        occurred_at="2026-07-13T10:00:00+00:00",
        source_service=ROUTING_AUDIT_SOURCE_SERVICE,
        source_version=ROUTING_AUDIT_SOURCE_VERSION,
        request_ref="req-1",
        resolved_tenant_ref="tenant-alpha",
        association_store_ref="tenant/alpha-db",
        association_version="1",
        lane="interactive",
    )
    base.update(overrides)
    return RoutingAuditEvent(**base)  # type: ignore[arg-type]


def _expect_error(client: HttpRoutingAudit, event: RoutingAuditEvent, kind: str) -> RoutingAuditTransportError:
    try:
        client.initiate(event)
    except RoutingAuditTransportError as exc:
        assert exc.kind == kind, f"expected kind {kind!r}, got {exc.kind!r}"
        assert str(exc) == f"routing-audit transport failure ({kind})", "the message is fixed and non-leaking"
        assert exc.__cause__ is None and exc.__suppress_context__, "must be raised `from None` (no chained internals)"
        return exc
    raise AssertionError(f"expected RoutingAuditTransportError({kind!r})")


# ---------------------------------------------------------------------------
# Cases 29-31 — exact serialization
# ---------------------------------------------------------------------------
def test_case29_exact_event_serialization() -> None:
    event = _event()
    with _fake_server([(200, _OK)]) as (state, base):
        HttpRoutingAudit(base).initiate(event)
    method, path, body = state.requests[0]
    assert (method, path) == ("POST", "/internal/routing-audit/events")
    envelope = json.loads(body.decode("utf-8"))
    assert set(envelope.keys()) == {"version", "event"} and envelope["version"] == 1
    wire = envelope["event"]
    assert set(wire.keys()) == _EXPECTED_WIRE_KEYS, "exactly the seventeen approved wire keys"
    assert wire["event_id"] == event.event_id and wire["event_version"] == 1
    assert wire["occurred_at"] == event.occurred_at and wire["correlation_id"] == "corr-1"
    assert wire["actor_ref"] == "principal:alice" and wire["action"] == "Route" and wire["outcome"] == "success"
    assert wire["source_service"] == "database_router" and wire["source_version"] == "4"
    assert wire["request_ref"] == "req-1" and wire["resolved_tenant_ref"] == "tenant-alpha"
    assert wire["public_code"] is None and wire["error_class"] is None
    assert wire["association_store_ref"] == "tenant/alpha-db" and wire["association_version"] == "1"
    assert wire["lane"] == "interactive"


def test_case30_target_ref_serialized_as_tenant_ref() -> None:
    with _fake_server([(200, _OK)]) as (state, base):
        HttpRoutingAudit(base).initiate(_event(target_ref="tenant-beta"))
    wire = json.loads(state.requests[0][2].decode("utf-8"))["event"]
    assert wire["tenant_ref"] == "tenant-beta"
    assert "target_ref" not in wire, "the inherited field travels ONLY under its durable name tenant_ref"


def test_case31_no_recorded_at_or_store_assigned_key_sent() -> None:
    with _fake_server([(200, _OK)]) as (state, base):
        HttpRoutingAudit(base).initiate(_event())
    wire = json.loads(state.requests[0][2].decode("utf-8"))["event"]
    for absent in ("recorded_at", "store_id", "id", "trace_ref"):
        assert absent not in wire, absent


# ---------------------------------------------------------------------------
# Cases 32-35 — success pair; bounded conflict/unavailable
# ---------------------------------------------------------------------------
def test_case32_inserted_response_succeeds() -> None:
    with _fake_server([(200, _OK)]) as (_state, base):
        assert HttpRoutingAudit(base).initiate(_event()) is None


def test_case33_duplicate_match_response_succeeds() -> None:
    with _fake_server([(200, _DUP)]) as (_state, base):
        assert HttpRoutingAudit(base).initiate(_event()) is None, "an idempotent replay is success, not an error"


def test_case34_conflict_raises_bounded_client_error() -> None:
    with _fake_server([(409, {"version": 1, "result": "CONFLICT"})]) as (_state, base):
        _expect_error(HttpRoutingAudit(base), _event(), "conflict")


def test_case35_unavailable_raises_bounded_client_error() -> None:
    with _fake_server([(503, {"version": 1, "result": "UNAVAILABLE"})]) as (_state, base):
        _expect_error(HttpRoutingAudit(base), _event(), "unavailable")
    with _fake_server([(400, {"version": 1, "result": "INVALID"})]) as (_state, base):
        _expect_error(HttpRoutingAudit(base), _event(), "invalid")


# ---------------------------------------------------------------------------
# Cases 36-38 — strict response parsing; refused connection
# ---------------------------------------------------------------------------
def test_case36_malformed_extra_missing_response_fields_fail_closed() -> None:
    bad_bodies: List[Optional[Dict[str, object]]] = [
        None,  # not JSON at all
        {"version": 1},  # missing result
        {"result": "INSERTED"},  # missing version
        {"version": 1, "result": "INSERTED", "extra": "x"},  # extra key
        {"version": 1, "result": "ok"},  # unknown result
        {"version": 1, "result": "CONFLICT"},  # error result on a 200 status line
    ]
    for body in bad_bodies:
        with _fake_server([(200, body)]) as (_state, base):
            _expect_error(HttpRoutingAudit(base), _event(), "invalid")


def test_case37_wrong_status_type_or_version_fails_closed() -> None:
    with _fake_server([(201, _OK)]) as (_state, base):
        _expect_error(HttpRoutingAudit(base), _event(), "invalid")
    with _fake_server([(200, {"version": 2, "result": "INSERTED"})]) as (_state, base):
        _expect_error(HttpRoutingAudit(base), _event(), "invalid")
    with _fake_server([(200, {"version": True, "result": "INSERTED"})]) as (_state, base):
        _expect_error(HttpRoutingAudit(base), _event(), "invalid")
    with _fake_server([(500, {"version": 1, "result": "UNAVAILABLE"})]) as (_state, base):
        _expect_error(HttpRoutingAudit(base), _event(), "invalid")  # unmapped status: protocol violation


def test_case38_connection_refusal_fails_closed_unavailable() -> None:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    host, port = probe.getsockname()
    probe.close()  # nothing is bound here anymore -> connection refused
    client = HttpRoutingAudit(f"http://{host}:{port}", timeout=0.5)
    _expect_error(client, _event(), "unavailable")


# ---------------------------------------------------------------------------
# Cases 39-41 — no retry; no fallback; structural port satisfaction
# ---------------------------------------------------------------------------
def test_case39_no_retry_occurs() -> None:
    for responses, kind in (
        ([(503, {"version": 1, "result": "UNAVAILABLE"})], "unavailable"),
        ([(409, {"version": 1, "result": "CONFLICT"})], "conflict"),
        ([(200, {"version": 1})], "invalid"),
    ):
        with _fake_server(list(responses)) as (state, base):
            _expect_error(HttpRoutingAudit(base), _event(), kind)
            assert len(state.requests) == 1, "exactly ONE request per initiate — no retry loop (DBR-AR-2C owns retry)"


def test_case40_no_in_memory_fallback_occurs() -> None:
    # Behavioral: a failed initiate raises — it never silently succeeds into any sink.
    with _fake_server([(503, {"version": 1, "result": "UNAVAILABLE"})]) as (_state, base):
        client = HttpRoutingAudit(base)
        _expect_error(client, _event(), "unavailable")
        assert not hasattr(client, "events"), "the client is a transport, not a sink"
        assert not isinstance(client, InMemoryAuditSink)
    # Structural: the client module never references the in-memory sink.
    module_path = pathlib.Path(sys.modules[HttpRoutingAudit.__module__].__file__ or "")
    source = module_path.read_text(encoding="utf-8")
    assert "in_memory" not in source and "InMemoryAuditSink" not in source, "no fallback wiring may exist"


def test_case41_client_structurally_satisfies_routing_audit_port() -> None:
    # Compile-time: the annotated assignment below is the mypy-visible structural check.
    port: RoutingAuditPort = HttpRoutingAudit("http://127.0.0.1:9")
    assert hasattr(port, "initiate")

    # End-to-end over the REAL Control-Plane ingest edge with a store double: the pair interoperates.
    class _RecordingStore(RoutingAuditStorePort):
        def __init__(self) -> None:
            self.records: List[RoutingAuditRecord] = []

        def append_routing_audit(self, record: RoutingAuditRecord) -> RoutingAuditAppendResult:
            self.records.append(record)
            return RoutingAuditAppendResult.INSERTED if len(self.records) == 1 else RoutingAuditAppendResult.DUPLICATE_MATCH

    store = _RecordingStore()
    server, base = build_routing_audit_server(store)
    thread = threading.Thread(target=server.serve_forever, daemon=True)  # test-owned hosting thread only
    thread.start()
    try:
        live_port: RoutingAuditPort = HttpRoutingAudit(base)
        event = _event(target_ref="tenant-gamma")
        assert live_port.initiate(event) is None
        assert live_port.initiate(event) is None, "an idempotent replay (DUPLICATE_MATCH) is success end-to-end"
    finally:
        server.shutdown()
        server.server_close()
    assert len(store.records) == 2
    stored = store.records[0]
    assert stored.tenant_ref == "tenant-gamma" and stored.event_id == event.event_id
    assert stored.trace_ref is None and stored.action == "Route"


if __name__ == "__main__":
    _h.run(
        [
            test_case29_exact_event_serialization,
            test_case30_target_ref_serialized_as_tenant_ref,
            test_case31_no_recorded_at_or_store_assigned_key_sent,
            test_case32_inserted_response_succeeds,
            test_case33_duplicate_match_response_succeeds,
            test_case34_conflict_raises_bounded_client_error,
            test_case35_unavailable_raises_bounded_client_error,
            test_case36_malformed_extra_missing_response_fields_fail_closed,
            test_case37_wrong_status_type_or_version_fails_closed,
            test_case38_connection_refusal_fails_closed_unavailable,
            test_case39_no_retry_occurs,
            test_case40_no_in_memory_fallback_occurs,
            test_case41_client_structurally_satisfies_routing_audit_port,
        ]
    )
