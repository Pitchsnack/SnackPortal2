"""DBR-AR-2B — Control-Plane routing-audit store behavioral contract (DB-free; no driver I/O).

Covers the dedicated durable routing-audit store (`PostgresRoutingAuditStore` behind
`RoutingAuditStorePort`) with a recording fake connection: exact SQL parameter mapping,
store-assigned `recorded_at` (never caller-bound), idempotent `INSERTED` /
`DUPLICATE_MATCH` semantics, same-ID/different-payload conflict rejection (fail closed),
commit-only-on-new-row transactions, rollback-and-re-raise on failure, the bounded
pre-insert validation, the closed record field set, and the append-only port surface
(exactly one write method; no read/update/delete). The frozen `ControlStore` port is
deliberately NOT widened by DBR-AR-2B — pinned here alongside its existing snapshot in
`test_distinctness_ledger_b2.py`. Per the Driver Containment Standard this test never
imports `psycopg`; it reaches the adapter only through its module. Pure stdlib;
standalone-runnable: `python tests/control_plane/test_dbr_ar_2b_routing_audit_store.py`.
"""

from __future__ import annotations

import dataclasses
import pathlib
import sys
from datetime import datetime, timezone
from typing import Any, List, Optional, Sequence, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402,F401  (backend + architecture helpers on path)

from control_plane.adapters.providers.postgres_store import (  # noqa: E402
    _ROUTING_AUDIT_COLUMNS,
    _ROUTING_AUDIT_SELECT,
    PostgresRoutingAuditStore,
    _same_instant,
)
from control_plane.ports import ControlStore  # noqa: E402
from control_plane.routing_audit import (  # noqa: E402
    ROUTING_AUDIT_STORE_ACTIONS,
    RoutingAuditAppendResult,
    RoutingAuditConflictError,
    RoutingAuditInvalidError,
    RoutingAuditRecord,
    RoutingAuditStorePort,
)

# ---------------------------------------------------------------------------
# Fakes (stdlib only; no driver, no socket, no database)
# ---------------------------------------------------------------------------


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


def _store(conn: _FakeConn) -> PostgresRoutingAuditStore:
    store = PostgresRoutingAuditStore(dsn="test-double-descriptor")  # lazy: never connects
    store._conn_cache = conn  # inject the fake into the lazy slot (no I/O anywhere)
    return store


_OCCURRED_AT = "2026-07-13T10:00:00+00:00"


def _record(**overrides: object) -> RoutingAuditRecord:
    base: dict[str, object] = dict(
        event_id="1f0e6b1a-9b2c-4d3e-8f4a-5b6c7d8e9f0a",
        event_version=1,
        occurred_at=_OCCURRED_AT,
        correlation_id="corr-1",
        actor_ref="principal:alice",
        action="Route",
        outcome="success",
        source_service="database_router",
        source_version="4",
        request_ref="req-1",
        tenant_ref="tenant-alpha",
        resolved_tenant_ref="tenant-alpha",
        association_store_ref="tenant/alpha-db",
        association_version="1",
        lane="interactive",
    )
    base.update(overrides)
    return RoutingAuditRecord(**base)  # type: ignore[arg-type]


def _stored_row(record: RoutingAuditRecord, **overrides: object) -> Tuple[Any, ...]:
    """A stored row in _ROUTING_AUDIT_COLUMNS order, with the timestamptz as a driver datetime."""
    values: dict[str, object] = {
        "event_id": record.event_id,
        "event_version": record.event_version,
        "occurred_at": datetime(2026, 7, 13, 10, 0, 0, tzinfo=timezone.utc),
        "correlation_id": record.correlation_id,
        "actor_ref": record.actor_ref,
        "action": record.action,
        "outcome": record.outcome,
        "source_service": record.source_service,
        "source_version": record.source_version,
        "request_ref": record.request_ref,
        "trace_ref": record.trace_ref,
        "tenant_ref": record.tenant_ref,
        "resolved_tenant_ref": record.resolved_tenant_ref,
        "public_code": record.public_code,
        "error_class": record.error_class,
        "association_store_ref": record.association_store_ref,
        "association_version": record.association_version,
        "lane": record.lane,
    }
    values.update(overrides)
    return tuple(values[name] for name in _ROUTING_AUDIT_COLUMNS)


# ---------------------------------------------------------------------------
# Cases 1-3 — exact SQL parameter mapping; recorded_at/id never caller-bound
# ---------------------------------------------------------------------------
def test_case01_valid_event_maps_to_exact_sql_parameters() -> None:
    conn = _FakeConn(script=[(1,)])
    record = _record()
    _store(conn).append_routing_audit(record)
    sql, params = conn.executed[0]
    assert "INSERT INTO control_routing_audit (" + ", ".join(_ROUTING_AUDIT_COLUMNS) + ")" in sql
    assert "ON CONFLICT (event_id) DO NOTHING RETURNING id" in sql
    assert params == (
        record.event_id,
        1,
        _OCCURRED_AT,
        "corr-1",
        "principal:alice",
        "Route",
        "success",
        "database_router",
        "4",
        "req-1",
        None,  # trace_ref: reserved column, always NULL in DBR-AR-2B
        "tenant-alpha",
        "tenant-alpha",
        None,  # public_code: None on success
        None,  # error_class
        "tenant/alpha-db",
        "1",
        "interactive",
    )


def test_case02_tenant_ref_is_the_durable_column_not_target_ref() -> None:
    conn = _FakeConn(script=[(1,)])
    _store(conn).append_routing_audit(_record(tenant_ref="tenant-beta"))
    sql, params = conn.executed[0]
    assert "tenant_ref" in sql and "target_ref" not in sql, "the durable column is tenant_ref (as-built target_ref)"
    assert params[_ROUTING_AUDIT_COLUMNS.index("tenant_ref")] == "tenant-beta"


def test_case03_recorded_at_and_id_are_never_caller_bound() -> None:
    conn = _FakeConn(script=[(1,)])
    _store(conn).append_routing_audit(_record())
    sql, params = conn.executed[0]
    assert "recorded_at" not in sql, "recorded_at is DB-assigned (DEFAULT now()) — never in the INSERT column list"
    assert len(params) == len(_ROUTING_AUDIT_COLUMNS) == 18
    assert _ROUTING_AUDIT_COLUMNS[0] == "event_id" and "id" not in _ROUTING_AUDIT_COLUMNS
    assert "recorded_at" not in _ROUTING_AUDIT_COLUMNS


# ---------------------------------------------------------------------------
# Cases 4-8 — idempotency, conflict, transactions
# ---------------------------------------------------------------------------
def test_case04_new_event_returns_inserted_and_commits_once() -> None:
    conn = _FakeConn(script=[(7,)])  # RETURNING id produced a row -> newly inserted
    result = _store(conn).append_routing_audit(_record())
    assert result is RoutingAuditAppendResult.INSERTED
    assert conn.commits == 1 and conn.rollbacks == 0


def test_case05_exact_duplicate_returns_duplicate_match_without_commit() -> None:
    record = _record()
    conn = _FakeConn(script=[None, _stored_row(record)])  # conflict -> verify-select returns the equal row
    result = _store(conn).append_routing_audit(record)
    assert result is RoutingAuditAppendResult.DUPLICATE_MATCH
    assert conn.commits == 0, "a replay persists nothing — commit happens ONLY on a newly inserted row"
    assert conn.rollbacks == 1
    select_sql, select_params = conn.executed[1]
    assert select_sql == _ROUTING_AUDIT_SELECT and select_params == (record.event_id,)


def test_case06_same_id_with_changed_field_raises_conflict() -> None:
    record = _record()
    for drifted in (
        _stored_row(record, outcome="denied:not_found"),
        _stored_row(record, actor_ref="principal:mallory"),
        _stored_row(record, association_version="2"),
        _stored_row(record, occurred_at=datetime(2026, 7, 13, 10, 0, 1, tzinfo=timezone.utc)),
    ):
        conn = _FakeConn(script=[None, drifted])
        try:
            _store(conn).append_routing_audit(record)
            raise AssertionError("same-ID/different-payload replay must fail closed")
        except RoutingAuditConflictError:
            pass
        assert conn.commits == 0 and conn.rollbacks == 1


def test_case07_transaction_commits_only_on_valid_insert() -> None:
    # Newly inserted -> exactly one commit (case 4). Replay/conflict paths -> zero commits
    # (cases 5/6). Validation failure -> nothing executed at all.
    conn = _FakeConn()
    try:
        _store(conn).append_routing_audit(_record(action="Publish"))
        raise AssertionError("invalid action must be rejected before any SQL")
    except RoutingAuditInvalidError:
        pass
    assert conn.executed == [] and conn.commits == 0


def test_case08_failure_rolls_back_and_reraises_unchanged() -> None:
    conn = _FakeConn()
    boom = RuntimeError("driver-detail-that-must-not-be-wrapped")
    conn.execute_error = boom
    try:
        _store(conn).append_routing_audit(_record())
        raise AssertionError("store failure must propagate")
    except RuntimeError as exc:
        assert exc is boom, "the original error is the signal — re-raised unchanged (fail closed)"
    assert conn.rollbacks == 1 and conn.commits == 0


# ---------------------------------------------------------------------------
# Cases 9-12 — validation, nullable optionals, closed shapes, append-only port
# ---------------------------------------------------------------------------
def test_case09_action_allowlist_enforced_before_any_sql() -> None:
    assert ROUTING_AUDIT_STORE_ACTIONS == ("Route", "RouteControl", "RouteDenied", "IsolationAnomaly")
    for bad in ("Publish", "route", "DispatchCompleted", "DispatchFailed", "AuditSinkFailed", ""):
        conn = _FakeConn()
        try:
            _store(conn).append_routing_audit(_record(action=bad, outcome="success"))
            raise AssertionError(f"action {bad!r} must be rejected")
        except RoutingAuditInvalidError:
            pass
        assert conn.executed == []
    for bad_version in (0, -1):
        conn = _FakeConn()
        try:
            _store(conn).append_routing_audit(_record(event_version=bad_version))
            raise AssertionError("non-positive event_version must be rejected")
        except RoutingAuditInvalidError:
            pass
    conn = _FakeConn()
    try:
        _store(conn).append_routing_audit(_record(source_service="api_gateway"))
        raise AssertionError("non-router source_service must be rejected (DDL CHECK mirror)")
    except RoutingAuditInvalidError:
        pass


def test_case10_optional_references_map_to_nullable_columns() -> None:
    conn = _FakeConn(script=[(1,)])
    record = _record(
        action="RouteControl",
        tenant_ref=None,
        resolved_tenant_ref=None,
        request_ref=None,
        association_store_ref=None,
        association_version=None,
        lane=None,
    )
    _store(conn).append_routing_audit(record)
    _sql, params = conn.executed[0]
    for column in (
        "request_ref",
        "trace_ref",
        "tenant_ref",
        "resolved_tenant_ref",
        "public_code",
        "error_class",
        "association_store_ref",
        "association_version",
        "lane",
    ):
        assert params[_ROUTING_AUDIT_COLUMNS.index(column)] is None, column


def test_case11_forbidden_model_fields_do_not_exist() -> None:
    names = {f.name for f in dataclasses.fields(RoutingAuditRecord)}
    assert names == {
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
        "trace_ref",
        "tenant_ref",
        "resolved_tenant_ref",
        "public_code",
        "error_class",
        "association_store_ref",
        "association_version",
        "lane",
    }, "the record field set is CLOSED (18 fields; contract §8)"
    for forbidden in (
        "recorded_at",
        "store_id",
        "id",
        "dsn",
        "password",
        "token",
        "jwt",
        "request_body",
        "response_body",
        "hostname",
        "connection",
        "payload",
        "hash_chain",
    ):
        assert forbidden not in names, forbidden
    # Immutable (frozen): field mutation must fail.
    record = _record()
    try:
        record.outcome = "denied:not_found"  # type: ignore[misc]
        raise AssertionError("RoutingAuditRecord must be frozen")
    except dataclasses.FrozenInstanceError:
        pass


def test_case12_no_read_update_delete_method_exists() -> None:
    assert RoutingAuditStorePort.__abstractmethods__ == frozenset({"append_routing_audit"}), (
        "the store port is append-only write: exactly ONE abstract method"
    )
    public = {n for n in dir(PostgresRoutingAuditStore) if not n.startswith("_")}
    assert public == {"append_routing_audit", "release"}, f"append-only adapter surface violated: {sorted(public)}"
    for verb in ("list", "get", "read", "query", "export", "purge", "update", "delete"):
        assert not any(n.startswith(verb) for n in public), verb
    # DBR-AR-2B does NOT widen the frozen ControlStore port (its snapshot pin lives in
    # test_distinctness_ledger_b2.py; re-asserted here for the 2B boundary).
    assert "append_routing_audit" not in ControlStore.__abstractmethods__


# ---------------------------------------------------------------------------
# Construction discipline + timestamp comparison helper
# ---------------------------------------------------------------------------
def test_construction_requires_exactly_one_source_and_never_connects() -> None:
    try:
        PostgresRoutingAuditStore()
        raise AssertionError("neither source must be rejected")
    except ValueError:
        pass
    try:
        PostgresRoutingAuditStore(dsn="x", ref=object())  # type: ignore[arg-type]
        raise AssertionError("both sources must be rejected")
    except ValueError:
        pass
    try:
        PostgresRoutingAuditStore(ref=object())  # type: ignore[arg-type]
        raise AssertionError("ref without secrets must be rejected")
    except ValueError:
        pass
    store = PostgresRoutingAuditStore(dsn="test-double-descriptor")
    assert store._conn_cache is None, "lazy-connect: construction performs no I/O"
    store.release()  # idempotent on a never-opened store


def test_same_instant_tolerates_representation_but_not_drift() -> None:
    aware = datetime(2026, 7, 13, 10, 0, 0, tzinfo=timezone.utc)
    assert _same_instant(aware, _OCCURRED_AT)
    assert _same_instant(_OCCURRED_AT, _OCCURRED_AT)
    assert _same_instant(datetime(2026, 7, 13, 10, 0, 0), _OCCURRED_AT), "naive stored values are assumed UTC"
    assert not _same_instant(datetime(2026, 7, 13, 10, 0, 1, tzinfo=timezone.utc), _OCCURRED_AT)
    assert not _same_instant("not-a-timestamp", _OCCURRED_AT)


if __name__ == "__main__":
    _h.run(
        [
            test_case01_valid_event_maps_to_exact_sql_parameters,
            test_case02_tenant_ref_is_the_durable_column_not_target_ref,
            test_case03_recorded_at_and_id_are_never_caller_bound,
            test_case04_new_event_returns_inserted_and_commits_once,
            test_case05_exact_duplicate_returns_duplicate_match_without_commit,
            test_case06_same_id_with_changed_field_raises_conflict,
            test_case07_transaction_commits_only_on_valid_insert,
            test_case08_failure_rolls_back_and_reraises_unchanged,
            test_case09_action_allowlist_enforced_before_any_sql,
            test_case10_optional_references_map_to_nullable_columns,
            test_case11_forbidden_model_fields_do_not_exist,
            test_case12_no_read_update_delete_method_exists,
            test_construction_requires_exactly_one_source_and_never_connects,
            test_same_instant_tolerates_representation_but_not_drift,
        ]
    )
