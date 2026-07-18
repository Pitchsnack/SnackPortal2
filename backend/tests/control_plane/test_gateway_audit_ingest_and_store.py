"""Gateway Audit V1a — Control-Plane ingest edge + durable store behavioral contract (DB-free; no driver I/O).

Two halves, both stdlib-only and driver-free (the Driver Containment Standard: this test never imports
``psycopg``; it reaches the store adapter only through its module, with a recording fake connection):

* **Store** (``PostgresGatewayAuditStore`` behind ``GatewayAuditStorePort``): exact SQL parameter
  mapping, store-assigned ``recorded_at``/``id`` (never caller-bound), idempotent ``INSERTED`` /
  ``DUPLICATE_MATCH`` semantics, same-ID/different-payload conflict rejection (fail closed),
  commit-only-on-new-row transactions, rollback-and-re-raise on failure, the bounded pre-insert
  validation, the closed record field set, and the append-only port surface (exactly one write
  method; no read/update/delete).
* **Ingest** (``build_gateway_audit_server`` over ``127.0.0.1`` on a test-owned daemon thread — the
  established loopback precedent; production stays thread-free, AT-D15T1-10): strict envelope
  acceptance/rejection for ``POST /internal/gateway-audit/events``, the exact two-key response
  envelope for INSERTED / DUPLICATE_MATCH / INVALID / CONFLICT / UNAVAILABLE, 404/405 empty-body
  refusals, forbidden-name and secret-shaped-value defenses, the V1a success-only action/outcome/
  version pins, and the no-leak guarantee. The store behind the edge is a local test double.

Pure stdlib; standalone-runnable: ``python tests/control_plane/test_gateway_audit_ingest_and_store.py``.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import pathlib
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402,F401  (backend + architecture helpers on path)

from control_plane.adapters.providers.http_gateway_audit_api import (  # noqa: E402
    _INGEST_PATH,
    build_gateway_audit_server,
)
from control_plane.adapters.providers.postgres_store import (  # noqa: E402
    _GATEWAY_AUDIT_COLUMNS,
    _GATEWAY_AUDIT_SELECT,
    PostgresGatewayAuditStore,
    _same_instant,
)
from control_plane.gateway_audit import (  # noqa: E402
    GATEWAY_AUDIT_STORE_ACTIONS,
    GatewayAuditAppendResult,
    GatewayAuditConflictError,
    GatewayAuditInvalidError,
    GatewayAuditRecord,
    GatewayAuditStorePort,
)
from control_plane.ports import ControlStore  # noqa: E402

_AUDIT_ID = "0123456789abcdef0123456789abcdef"
_OCCURRED_AT = "2026-07-18T10:00:00+00:00"


# ===========================================================================
# STORE HALF — recording fake connection (no driver, no socket, no database)
# ===========================================================================
class _FakeCursor:
    def __init__(self, conn: "_FakeConn") -> None:
        self._conn = conn

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, sql: str, params: Sequence[object] = ()) -> None:
        if self._conn.execute_error is not None:
            raise self._conn.execute_error
        self._conn.executed.append((sql, tuple(params)))

    def fetchone(self) -> Optional[Tuple[Any, ...]]:
        return self._conn.script.pop(0) if self._conn.script else None


class _FakeConn:
    """Scripted connection double: `script` holds sequential fetchone() results."""

    def __init__(self, script: Sequence[Optional[Tuple[Any, ...]]] = ()) -> None:
        self.script: List[Optional[Tuple[Any, ...]]] = list(script)
        self.executed: List[Tuple[str, Tuple[object, ...]]] = []
        self.commits = 0
        self.rollbacks = 0
        self.execute_error: Optional[BaseException] = None

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _store(conn: _FakeConn) -> PostgresGatewayAuditStore:
    store = PostgresGatewayAuditStore(dsn="test-double-descriptor")  # lazy: never connects
    store._conn_cache = conn  # inject the fake into the lazy slot (no I/O anywhere)
    return store


def _record(**overrides: object) -> GatewayAuditRecord:
    base: dict[str, object] = dict(
        audit_id=_AUDIT_ID,
        event_version=1,
        occurred_at=_OCCURRED_AT,
        correlation_id="corr-1",
        action="workspace_memberships_read",
        outcome="success",
        source_service="api_gateway",
        actor_ref="principal:ops",
        subject_ref="principal:ops",
        tenant_ref=None,
        carrier_ref=None,
    )
    base.update(overrides)
    return GatewayAuditRecord(**base)  # type: ignore[arg-type]


def _stored_row(record: GatewayAuditRecord, **overrides: object) -> Tuple[Any, ...]:
    """A stored row in _GATEWAY_AUDIT_COLUMNS order, with the timestamptz as a driver datetime."""
    values: dict[str, object] = {
        "audit_id": record.audit_id,
        "event_version": record.event_version,
        "occurred_at": datetime(2026, 7, 18, 10, 0, 0, tzinfo=timezone.utc),
        "correlation_id": record.correlation_id,
        "action": record.action,
        "outcome": record.outcome,
        "source_service": record.source_service,
        "actor_ref": record.actor_ref,
        "subject_ref": record.subject_ref,
        "tenant_ref": record.tenant_ref,
        "carrier_ref": record.carrier_ref,
    }
    values.update(overrides)
    return tuple(values[name] for name in _GATEWAY_AUDIT_COLUMNS)


def test_store01_valid_event_maps_to_exact_sql_parameters() -> None:
    conn = _FakeConn(script=[(1,)])
    record = _record()
    _store(conn).append_gateway_audit(record)
    sql, params = conn.executed[0]
    assert "INSERT INTO control_gateway_audit (" + ", ".join(_GATEWAY_AUDIT_COLUMNS) + ")" in sql
    assert "ON CONFLICT (audit_id) DO NOTHING RETURNING id" in sql
    assert params == (
        _AUDIT_ID,
        1,
        _OCCURRED_AT,
        "corr-1",
        "workspace_memberships_read",
        "success",
        "api_gateway",
        "principal:ops",
        "principal:ops",
        None,  # tenant_ref
        None,  # carrier_ref
    )


def test_store02_recorded_at_and_id_are_never_caller_bound() -> None:
    conn = _FakeConn(script=[(1,)])
    _store(conn).append_gateway_audit(_record())
    sql, params = conn.executed[0]
    assert "recorded_at" not in sql, "recorded_at is DB-assigned (DEFAULT now()) — never in the INSERT column list"
    assert len(params) == len(_GATEWAY_AUDIT_COLUMNS) == 11
    assert _GATEWAY_AUDIT_COLUMNS[0] == "audit_id" and "id" not in _GATEWAY_AUDIT_COLUMNS
    assert "recorded_at" not in _GATEWAY_AUDIT_COLUMNS
    assert "source_service" in _GATEWAY_AUDIT_COLUMNS  # producer constant is store-bound, not a wire field


def test_store03_new_event_returns_inserted_and_commits_once() -> None:
    conn = _FakeConn(script=[(7,)])  # RETURNING id produced a row -> newly inserted
    result = _store(conn).append_gateway_audit(_record())
    assert result is GatewayAuditAppendResult.INSERTED
    assert conn.commits == 1 and conn.rollbacks == 0


def test_store04_exact_duplicate_returns_duplicate_match_without_commit() -> None:
    record = _record()
    conn = _FakeConn(script=[None, _stored_row(record)])  # conflict -> verify-select returns the equal row
    result = _store(conn).append_gateway_audit(record)
    assert result is GatewayAuditAppendResult.DUPLICATE_MATCH
    assert conn.commits == 0, "a replay persists nothing — commit happens ONLY on a newly inserted row"
    assert conn.rollbacks == 1
    select_sql, select_params = conn.executed[1]
    assert select_sql == _GATEWAY_AUDIT_SELECT and select_params == (record.audit_id,)


def test_store05_same_id_with_changed_field_raises_conflict() -> None:
    record = _record()
    for drifted in (
        _stored_row(record, outcome="denied:forbidden"),
        _stored_row(record, actor_ref="principal:mallory"),
        _stored_row(record, subject_ref="principal:mallory"),
        _stored_row(record, correlation_id="corr-2"),
        _stored_row(record, occurred_at=datetime(2026, 7, 18, 10, 0, 1, tzinfo=timezone.utc)),
    ):
        conn = _FakeConn(script=[None, drifted])
        try:
            _store(conn).append_gateway_audit(record)
            raise AssertionError("same-ID/different-payload replay must fail closed")
        except GatewayAuditConflictError:
            pass
        assert conn.commits == 0 and conn.rollbacks == 1


def test_store06_transaction_commits_only_on_valid_insert() -> None:
    conn = _FakeConn()
    try:
        _store(conn).append_gateway_audit(_record(action="Publish"))
        raise AssertionError("invalid action must be rejected before any SQL")
    except GatewayAuditInvalidError:
        pass
    assert conn.executed == [] and conn.commits == 0


def test_store07_failure_rolls_back_and_reraises_unchanged() -> None:
    conn = _FakeConn()
    boom = RuntimeError("driver-detail-that-must-not-be-wrapped")
    conn.execute_error = boom
    try:
        _store(conn).append_gateway_audit(_record())
        raise AssertionError("store failure must propagate")
    except RuntimeError as exc:
        assert exc is boom, "the original error is the signal — re-raised unchanged (fail closed)"
    assert conn.rollbacks == 1 and conn.commits == 0


def test_store08_validation_enforced_before_any_sql() -> None:
    assert GATEWAY_AUDIT_STORE_ACTIONS == (
        "CarrierMismatch",
        "CarrierOnControlAnomaly",
        "RouteDenied",
        "IsolationAnomaly",
        "workspace_memberships_read",
    )
    for bad in ("Publish", "workspace_memberships", "route", "DispatchCompleted", ""):
        conn = _FakeConn()
        try:
            _store(conn).append_gateway_audit(_record(action=bad))
            raise AssertionError(f"action {bad!r} must be rejected")
        except GatewayAuditInvalidError:
            pass
        assert conn.executed == []
    for bad_version in (0, -1):
        conn = _FakeConn()
        try:
            _store(conn).append_gateway_audit(_record(event_version=bad_version))
            raise AssertionError("non-positive event_version must be rejected")
        except GatewayAuditInvalidError:
            pass
    conn = _FakeConn()
    try:
        _store(conn).append_gateway_audit(_record(source_service="database_router"))
        raise AssertionError("non-gateway source_service must be rejected (DDL CHECK mirror)")
    except GatewayAuditInvalidError:
        pass


def test_store09_optional_references_map_to_nullable_columns() -> None:
    conn = _FakeConn(script=[(1,)])
    record = _record(actor_ref=None, subject_ref=None, tenant_ref=None, carrier_ref=None)
    _store(conn).append_gateway_audit(record)
    _sql, params = conn.executed[0]
    for column in ("actor_ref", "subject_ref", "tenant_ref", "carrier_ref"):
        assert params[_GATEWAY_AUDIT_COLUMNS.index(column)] is None, column


def test_store10_forbidden_model_fields_do_not_exist() -> None:
    names = {f.name for f in dataclasses.fields(GatewayAuditRecord)}
    assert names == {
        "audit_id",
        "event_version",
        "occurred_at",
        "correlation_id",
        "action",
        "outcome",
        "source_service",
        "actor_ref",
        "subject_ref",
        "tenant_ref",
        "carrier_ref",
    }, "the record field set is CLOSED (11 fields)"
    for forbidden in ("recorded_at", "id", "dsn", "password", "token", "jwt", "request_body", "memberships", "payload", "hash_chain"):
        assert forbidden not in names, forbidden
    record = _record()
    try:
        record.outcome = "denied:forbidden"  # type: ignore[misc]
        raise AssertionError("GatewayAuditRecord must be frozen")
    except dataclasses.FrozenInstanceError:
        pass


def test_store11_no_read_update_delete_method_exists() -> None:
    assert GatewayAuditStorePort.__abstractmethods__ == frozenset({"append_gateway_audit"}), (
        "the store port is append-only write: exactly ONE abstract method"
    )
    public = {n for n in dir(PostgresGatewayAuditStore) if not n.startswith("_")}
    assert public == {"append_gateway_audit", "release"}, f"append-only adapter surface violated: {sorted(public)}"
    for verb in ("list", "get", "read", "query", "export", "purge", "update", "delete"):
        assert not any(n.startswith(verb) for n in public), verb
    assert "append_gateway_audit" not in ControlStore.__abstractmethods__  # frozen ControlStore not widened


def test_store12_construction_requires_exactly_one_source_and_never_connects() -> None:
    for bad in (
        lambda: PostgresGatewayAuditStore(),
        lambda: PostgresGatewayAuditStore(dsn="x", ref=object()),
        lambda: PostgresGatewayAuditStore(ref=object()),
    ):  # type: ignore[arg-type]
        try:
            bad()
            raise AssertionError("invalid construction must be rejected")
        except (ValueError, TypeError):
            pass
    store = PostgresGatewayAuditStore(dsn="test-double-descriptor")
    assert store._conn_cache is None, "lazy-connect: construction performs no I/O"
    store.release()  # idempotent on a never-opened store
    assert _same_instant(datetime(2026, 7, 18, 10, 0, 0, tzinfo=timezone.utc), _OCCURRED_AT)  # shared helper reused


# ===========================================================================
# INGEST HALF — loopback HTTP over a test-owned daemon thread
# ===========================================================================
class _FakeStore(GatewayAuditStorePort):
    """Scripted store double: behavior in {insert, duplicate, conflict, invalid, boom}."""

    def __init__(self, behavior: str = "insert") -> None:
        self.behavior = behavior
        self.records: List[GatewayAuditRecord] = []

    def append_gateway_audit(self, record: GatewayAuditRecord) -> GatewayAuditAppendResult:
        self.records.append(record)
        if self.behavior == "insert":
            return GatewayAuditAppendResult.INSERTED
        if self.behavior == "duplicate":
            return GatewayAuditAppendResult.DUPLICATE_MATCH
        if self.behavior == "conflict":
            raise GatewayAuditConflictError("replayed audit_id with a different payload")
        if self.behavior == "invalid":
            raise GatewayAuditInvalidError("record rejected")
        raise RuntimeError("internal-store-detail-that-must-never-leak")


@contextlib.contextmanager
def _serving(store: GatewayAuditStorePort) -> Iterator[str]:
    server, base_url = build_gateway_audit_server(store)  # 127.0.0.1, ephemeral port
    thread = threading.Thread(target=server.serve_forever, daemon=True)  # test-owned hosting thread only
    thread.start()
    try:
        yield base_url
    finally:
        server.shutdown()
        server.server_close()


def _request(base: str, body: bytes, path: str = _INGEST_PATH, method: str = "POST") -> Tuple[int, bytes]:
    req = urllib.request.Request(base + path, data=body, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return int(resp.status), resp.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read()


# A single-threaded stdlib HTTP/1.0 server closes the connection immediately after a bodiless
# 404/405 refusal, which on Windows loopback intermittently surfaces client-side as
# ConnectionAbortedError/ConnectionResetError. Bounded retry, SOLELY for the side-effect-free
# refusal probes (they never reach the store); every other exception propagates unchanged.
_REFUSAL_PROBE_ATTEMPTS = 5


def _refusal_probe(base: str, body: bytes, path: str = _INGEST_PATH, method: str = "POST") -> Tuple[int, bytes]:
    last: BaseException = AssertionError("unreachable")
    for _attempt in range(_REFUSAL_PROBE_ATTEMPTS):
        try:
            return _request(base, body, path=path, method=method)
        except (ConnectionAbortedError, ConnectionResetError) as exc:
            last = exc
        except urllib.error.URLError as exc:
            if not isinstance(exc.reason, (ConnectionAbortedError, ConnectionResetError)):
                raise
            last = exc
    raise last


def _event(**overrides: object) -> Dict[str, object]:
    base: Dict[str, object] = {
        "audit_id": _AUDIT_ID,
        "event_version": 1,
        "occurred_at": _OCCURRED_AT,
        "correlation_id": "corr-1",
        "action": "workspace_memberships_read",
        "outcome": "success",
        "actor_ref": "principal:ops",
        "subject_ref": "principal:ops",
        "tenant_ref": None,
        "carrier_ref": None,
    }
    base.update(overrides)
    return base


def _envelope(event: Optional[Dict[str, object]] = None, **top: object) -> bytes:
    payload: Dict[str, object] = {"version": 1, "event": event if event is not None else _event()}
    payload.update(top)
    return json.dumps(payload).encode("utf-8")


def _expect(base: str, body: bytes, status: int, result: str) -> bytes:
    got_status, raw = _request(base, body)
    assert got_status == status, f"expected {status}, got {got_status}: {raw!r}"
    parsed = json.loads(raw.decode("utf-8"))
    assert parsed == {"version": 1, "result": result}, parsed
    return raw


def test_ingest01_valid_insert_envelope_accepted() -> None:
    store = _FakeStore("insert")
    with _serving(store) as base:
        _expect(base, _envelope(), 200, "INSERTED")
    (record,) = store.records
    assert record.audit_id == _AUDIT_ID and record.action == "workspace_memberships_read"
    assert record.source_service == "api_gateway"  # store-side producer constant, not from the wire
    assert record.actor_ref == record.subject_ref == "principal:ops"
    assert record.tenant_ref is None and record.carrier_ref is None


def test_ingest02_exact_duplicate_accepted_idempotently() -> None:
    with _serving(_FakeStore("duplicate")) as base:
        _expect(base, _envelope(), 200, "DUPLICATE_MATCH")


def test_ingest03_same_id_different_payload_conflict_rejected() -> None:
    with _serving(_FakeStore("conflict")) as base:
        _expect(base, _envelope(), 409, "CONFLICT")


def test_ingest04_store_failure_collapses_to_unavailable_no_leak() -> None:
    with _serving(_FakeStore("boom")) as base:
        raw = _expect(base, _envelope(), 503, "UNAVAILABLE")
    assert b"internal-store-detail" not in raw, "no internal store detail may leak through the edge"


def test_ingest05_wrong_path_rejected_404_empty() -> None:
    with _serving(_FakeStore("insert")) as base:
        status, raw = _refusal_probe(base, _envelope(), path="/nope")
    assert status == 404 and raw == b""


def test_ingest06_wrong_method_rejected_405_empty() -> None:
    with _serving(_FakeStore("insert")) as base:
        for method in ("GET", "PUT", "DELETE", "PATCH"):
            status, raw = _refusal_probe(base, b"", method=method)
            assert status == 405 and raw == b"", method


def test_ingest07_malformed_and_non_object_json_rejected() -> None:
    with _serving(_FakeStore("insert")) as base:
        for body in (b"not json", b"[1,2,3]", b"", json.dumps("string").encode()):
            _expect(base, body, 400, "INVALID")


def test_ingest08_missing_or_extra_keys_rejected() -> None:
    with _serving(_FakeStore("insert")) as base:
        _expect(base, json.dumps({"event": _event()}).encode(), 400, "INVALID")  # missing version
        _expect(base, json.dumps({"version": 1}).encode(), 400, "INVALID")  # missing event
        _expect(base, _envelope(extra="x"), 400, "INVALID")  # extra top-level key
        missing = _event()
        del missing["actor_ref"]
        _expect(base, _envelope(missing), 400, "INVALID")  # missing event key
        _expect(base, _envelope(_event(extra_key="x")), 400, "INVALID")  # extra event key


def test_ingest09_unsupported_version_rejected() -> None:
    with _serving(_FakeStore("insert")) as base:
        for version in (0, 2, "1", True, None):
            _expect(base, _envelope(version=version), 400, "INVALID")
        _expect(base, _envelope(_event(event_version=2)), 400, "INVALID")
        _expect(base, _envelope(_event(event_version=True)), 400, "INVALID")
        _expect(base, _envelope(_event(event_version="1")), 400, "INVALID")


def test_ingest10_wrong_field_types_rejected() -> None:
    with _serving(_FakeStore("insert")) as base:
        _expect(base, _envelope(_event(actor_ref=7)), 400, "INVALID")
        _expect(base, _envelope(_event(correlation_id=None)), 400, "INVALID")
        _expect(base, _envelope(_event(audit_id="")), 400, "INVALID")
        _expect(base, _envelope(_event(subject_ref=None)), 400, "INVALID")
        _expect(base, json.dumps({"version": 1, "event": [1]}).encode(), 400, "INVALID")


def test_ingest11_v1a_action_outcome_version_pins_enforced() -> None:
    # V1a wires ONLY the workspace_memberships_read success event: the four denial/anomaly actions
    # are refused at the edge, and outcome must be exactly "success".
    with _serving(_FakeStore("insert")) as base:
        for action in ("CarrierMismatch", "CarrierOnControlAnomaly", "RouteDenied", "IsolationAnomaly", "Hacked"):
            _expect(base, _envelope(_event(action=action)), 400, "INVALID")
        _expect(base, _envelope(_event(outcome="rejected")), 400, "INVALID")
        _expect(base, _envelope(_event(outcome="denied:forbidden")), 400, "INVALID")


def test_ingest12_forbidden_names_and_secret_shapes_rejected() -> None:
    with _serving(_FakeStore("insert")) as base:
        for forbidden in ("id", "recorded_at", "source_service", "dsn", "token", "password", "memberships", "connection"):
            _expect(base, _envelope(_event(**{forbidden: "x"})), 400, "INVALID")
        for shaped in ("eyJhbGciOi", "postgresql://u:p@h/db", "-----BEGIN KEY-----", "ghp_secrettoken"):
            _expect(base, _envelope(_event(actor_ref=shaped)), 400, "INVALID")


if __name__ == "__main__":
    _h.run(
        [
            test_store01_valid_event_maps_to_exact_sql_parameters,
            test_store02_recorded_at_and_id_are_never_caller_bound,
            test_store03_new_event_returns_inserted_and_commits_once,
            test_store04_exact_duplicate_returns_duplicate_match_without_commit,
            test_store05_same_id_with_changed_field_raises_conflict,
            test_store06_transaction_commits_only_on_valid_insert,
            test_store07_failure_rolls_back_and_reraises_unchanged,
            test_store08_validation_enforced_before_any_sql,
            test_store09_optional_references_map_to_nullable_columns,
            test_store10_forbidden_model_fields_do_not_exist,
            test_store11_no_read_update_delete_method_exists,
            test_store12_construction_requires_exactly_one_source_and_never_connects,
            test_ingest01_valid_insert_envelope_accepted,
            test_ingest02_exact_duplicate_accepted_idempotently,
            test_ingest03_same_id_different_payload_conflict_rejected,
            test_ingest04_store_failure_collapses_to_unavailable_no_leak,
            test_ingest05_wrong_path_rejected_404_empty,
            test_ingest06_wrong_method_rejected_405_empty,
            test_ingest07_malformed_and_non_object_json_rejected,
            test_ingest08_missing_or_extra_keys_rejected,
            test_ingest09_unsupported_version_rejected,
            test_ingest10_wrong_field_types_rejected,
            test_ingest11_v1a_action_outcome_version_pins_enforced,
            test_ingest12_forbidden_names_and_secret_shapes_rejected,
        ]
    )
