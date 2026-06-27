"""PRD 06 B-7B — audit timestamp normalization (B7B-D7; the headline forward-defect fix).

B-7A recorded an asymmetry: the in-memory adapter returns ``timestamp`` as the written
``now_iso()`` *str*, while the postgres adapter returned the driver *datetime* for the
``ts timestamptz`` column — yet ``ControlAuditRecord.timestamp`` is typed ``str``. B-7B
normalizes on read in ``postgres_store.list_audit`` so BOTH adapters return ``str``
representing the same instant, without retyping ``records.py``.

This exercises the REAL ``list_audit`` code path with a fake driver connection (no live DB,
mutation-form: identity-passthrough of the datetime would fail ``isinstance(str)``) plus the
in-memory round-trip and the ``_ts_to_iso`` normalizer directly. The live same-instant
round-trip against a real PostgreSQL is in
``requires_pg/test_pg_control_store_runtime_wiring.py``. Pure stdlib; pytest- or standalone-run:
  python tests/control_plane/test_b7b_audit_timestamp_normalization.py
"""

from __future__ import annotations

import pathlib
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, List, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from control_plane._util import now_iso  # noqa: E402
from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.adapters.providers.postgres_store import PostgresControlStore, _ts_to_iso  # noqa: E402
from control_plane.records import ControlAuditRecord  # noqa: E402

_Row = Tuple[Any, Any, Any, Any, Any, Any, Any]


class _FakeCursor:
    def __init__(self, rows: List[_Row]) -> None:
        self._rows = rows

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *_a: object) -> bool:
        return False

    def execute(self, _sql: str, _params: Tuple[Any, ...] = ()) -> "_FakeCursor":
        return self

    def fetchall(self) -> List[_Row]:
        return list(self._rows)


class _FakeConn:
    """Minimal psycopg-shaped stand-in so list_audit runs without a live DB."""

    def __init__(self, rows: List[_Row]) -> None:
        self._rows = rows

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._rows)


def _pg_with_rows(rows: List[_Row]) -> PostgresControlStore:
    store = PostgresControlStore(dsn="postgresql://unused")  # lazy: __init__ opens no connection
    store._conn_cache = _FakeConn(rows)  # inject a fake driver connection (no I/O)
    return store


def test_postgres_list_audit_returns_str_same_instant() -> None:
    dt = datetime(2026, 6, 27, 12, 0, 0, 123456, tzinfo=timezone(timedelta(hours=5)))
    store = _pg_with_rows([("actor", None, "act", None, None, dt, "corr-1")])
    rec = store.list_audit()[0]
    # mutation form: before the fix list_audit returned the raw datetime -> this fails
    assert isinstance(rec.timestamp, str), "postgres list_audit must return a str timestamp"
    assert rec.timestamp.endswith("+00:00"), "timestamp must be normalized to UTC"
    assert datetime.fromisoformat(rec.timestamp) == dt, "same instant must be preserved"


def test_in_memory_list_audit_returns_str_as_written() -> None:
    store = InMemoryControlStore()
    ts = now_iso()
    store.append_audit(
        ControlAuditRecord(actor="a", tenant_id=None, action="act", from_state=None, to_state=None, timestamp=ts, correlation_id="c1")
    )
    rec = store.list_audit()[0]
    assert isinstance(rec.timestamp, str) and rec.timestamp == ts


def test_both_adapters_type_stable_same_instant() -> None:
    instant = datetime(2026, 3, 4, 5, 6, 7, tzinfo=timezone.utc)
    pg_ts = _pg_with_rows([("a", None, "act", None, None, instant, "c1")]).list_audit()[0].timestamp
    mem = InMemoryControlStore()
    mem.append_audit(
        ControlAuditRecord(
            actor="a", tenant_id=None, action="act", from_state=None, to_state=None, timestamp=instant.isoformat(), correlation_id="c1"
        )
    )
    mem_ts = mem.list_audit()[0].timestamp
    assert isinstance(pg_ts, str) and isinstance(mem_ts, str)
    assert datetime.fromisoformat(pg_ts) == datetime.fromisoformat(mem_ts)


def test_ts_to_iso_normalizer() -> None:
    # tz-aware UTC -> unchanged ISO
    assert _ts_to_iso(datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)) == "2026-01-02T03:04:05+00:00"
    # naive -> assumed UTC
    assert _ts_to_iso(datetime(2026, 1, 2, 3, 4, 5)) == "2026-01-02T03:04:05+00:00"
    # non-UTC aware -> normalized to UTC, same instant
    assert _ts_to_iso(datetime(2026, 1, 2, 8, 4, 5, tzinfo=timezone(timedelta(hours=5)))) == "2026-01-02T03:04:05+00:00"
    # str passthrough (defensive)
    assert _ts_to_iso("2026-01-02T03:04:05+00:00") == "2026-01-02T03:04:05+00:00"
    # type stability: always str
    for v in (datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 1), "x"):
        assert isinstance(_ts_to_iso(v), str)


if __name__ == "__main__":
    _h.run(
        [
            test_postgres_list_audit_returns_str_same_instant,
            test_in_memory_list_audit_returns_str_as_written,
            test_both_adapters_type_stable_same_instant,
            test_ts_to_iso_normalizer,
        ]
    )
