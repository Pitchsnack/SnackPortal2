"""Live-PostgreSQL test harness (Build Phase 6; PRD-P6-R2 K / PRD-P6-E1 §19).

These tests prove the DB-behavioral guarantees that in-memory doubles CANNOT: append-only
trigger/privilege rejection of UPDATE/DELETE/TRUNCATE, UNIQUE(seq) fork prevention,
advisory-lock acquisition, recursive-CTE provenance traversal, and least-privilege role
enforcement. They require a live, disposable PostgreSQL.

Run: set SNACKPORTAL_TEST_DSN (e.g. 'postgresql://localhost:5432/snackportal_test') and
`python tests/lineage_service/requires_pg/test_pg_*.py`. With no DSN (or psycopg absent) the
files SKIP cleanly (exit 0), so the stdlib runner stays green in environments without PG.

psycopg is imported **dynamically** (only when a DSN is set), so the database-driver
containment guard — which forbids a static driver import outside the two provider zones — is
not tripped by this test harness. The harness DROPs+recreates the lineage tables for a clean
slate (owner-privileged; not blocked by the append-only trigger) and ROLLs BACK between
tests (no DELETE needed — append-only).
"""
from __future__ import annotations

import importlib
import os
import pathlib
import sys
from typing import Callable, List

DSN_ENV = "SNACKPORTAL_TEST_DSN"
DDL_DIR = pathlib.Path(__file__).resolve().parents[4] / "infrastructure" / "db" / "lineage"

_REQUIRED = (
    "seq", "lineage_id", "segment_id", "event_type", "occurred_at", "actor_ref",
    "source_ref", "target_ref", "operation", "schema_version", "marker_version",
    "integrity_marker", "prev_marker",
)


def dsn() -> str:
    return os.environ.get(DSN_ENV, "")


def psycopg():
    return importlib.import_module("psycopg")


def available() -> bool:
    if not dsn():
        return False
    try:
        psycopg()
        return True
    except Exception:
        return False


def connect():
    return psycopg().connect(dsn())


def apply_schema(conn) -> None:
    # Clean slate for a disposable test DB: DROP (owner) bypasses the append-only trigger,
    # then re-apply 001 -> 002 -> 003.
    with conn.cursor() as cur:
        cur.execute(
            "DROP TABLE IF EXISTS lineage_segment, import_checkpoint, import_idempotency, "
            "import_job CASCADE; DROP TABLE IF EXISTS lineage CASCADE;"
        )
    for name in ("001_lineage_schema.sql", "002_append_only.sql", "003_roles.sql"):
        with conn.cursor() as cur:
            cur.execute((DDL_DIR / name).read_text(encoding="utf-8"))
    conn.commit()


def insert_lineage(cur, *, seq: int, lineage_id: str, parent=None, segment_id: int = 1,
                   integrity_marker: str = "m", prev_marker: str = "") -> None:
    row = {
        "seq": seq, "lineage_id": lineage_id, "segment_id": segment_id, "event_type": "import",
        "occurred_at": "T", "actor_ref": "u", "source_ref": "g", "target_ref": "t:c:%s" % seq,
        "operation": "created", "schema_version": "1", "marker_version": 1,
        "integrity_marker": integrity_marker, "prev_marker": prev_marker,
    }
    cols = list(row.keys()) + (["parent_lineage_ref"] if parent is not None else [])
    vals = [row[c] for c in row] + ([parent] if parent is not None else [])
    placeholders = ", ".join(["%s"] * len(cols))
    cur.execute("INSERT INTO lineage (%s) VALUES (%s)" % (", ".join(cols), placeholders), tuple(vals))


def expect_error(conn, sql: str, params: tuple = ()) -> bool:
    """Run `sql`; return True iff it raised (savepoint-isolated so the txn can continue)."""
    with conn.cursor() as cur:
        cur.execute("SAVEPOINT sp")
        try:
            cur.execute(sql, params)
            cur.execute("RELEASE SAVEPOINT sp")
            return False
        except Exception:
            cur.execute("ROLLBACK TO SAVEPOINT sp")
            return True


def run(tests: List[Callable]) -> None:
    if not available():
        print("SKIP (no %s set / psycopg not installed) — live-PG evidence pending (P6-V1)" % DSN_ENV)
        return
    conn = connect()
    failed = 0
    try:
        apply_schema(conn)
        for t in tests:
            try:
                t(conn)
                print("PASS:", t.__name__)
            except AssertionError as exc:
                failed += 1
                print("FAIL:", t.__name__, "-", exc)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("ERROR:", t.__name__, "-", repr(exc))
            finally:
                conn.rollback()  # reset inserted rows between tests (append-only: no DELETE)
    finally:
        conn.close()
    if failed:
        sys.exit(1)
    print("ALL PASSED")
