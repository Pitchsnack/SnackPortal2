"""control_audit durable-store — live-PostgreSQL exercise (standalone-only; SNACKPORTAL_TEST_DSN).

The B-7A live exercise for the PRD 06 B-7 created-not-applied Control-Plane audit DDL
(infrastructure/db/control/002_provisioning_audit.sql + 003_provisioning_audit_append_only.sql).
Against a real non-production PostgreSQL it pins the reviewed DDL by git blob, applies it inside a
throwaway scratch SCHEMA, and proves the live behavioral complement to B-7's STATIC contract tests:
DB-generated id, nullable/required columns, ts timestamptz acceptance of now_iso(), append-only
UPDATE/DELETE/TRUNCATE rejection, cross-instance durability, no-partial-commit, fail-closed, and
idempotency. This is the control-plane analogue of the B-4 distinctness-ledger live exercise
(test_pg_distinctness_ledger.py) and mirrors its DDL-blob-pin + adapter-confined-driver discipline.

ISOLATION & SAFETY. Everything runs in a uniquely-named scratch schema
`sp2_b7a_control_audit_scratch` created at start and DROP SCHEMA ... CASCADE'd in a finally — it
never touches `public` or any real table, and never CREATE/DROP DATABASE. The DDL files in the repo
are never modified (read + blob-pinned only). control_audit is created ONLY inside the scratch
schema (search_path is set to the scratch schema alone, so a missing table fails closed rather than
falling back to public).

DRIVER CONTAINMENT. This file imports NO database driver. It reaches PostgreSQL only through the
control-plane adapter `PostgresControlStore` (whose psycopg import lives in the sanctioned provider
zone) via `store._conn` — so backend/tests/architecture/test_vendor_and_db_containment.py is not
tripped. Expected-error cases use AUTOCOMMIT isolation (each statement is its own transaction; a
rejected statement leaves the connection immediately usable), per PRD 06 B-7A R3 §16.13.

SECRET HYGIENE (D-14). SNACKPORTAL_TEST_DSN is used by NAME only; its value (and the in-memory
unreachable DSN derived from it) is never printed, logged, or written. Stored rows are asserted to
contain no DSN/password substring.

DEFAULT SUITE. IGNORED by the default test run (pyproject addopts
`--ignore=tests/control_plane/requires_pg`); B-7A runs no live PostgreSQL by default. Run it for the
B-7A exercise by populating SNACKPORTAL_TEST_DSN (a non-production admin DSN permitted to
CREATE/DROP SCHEMA) in the environment and invoking:
  python backend/tests/control_plane/requires_pg/test_pg_control_audit_ddl.py
With SNACKPORTAL_TEST_DSN unset (or psycopg absent) it clean-skips (exit 0).

FORWARD DEFECT (recorded in B-7A; RESOLVED in B-7B): append_audit binds a now_iso() *string* into
the ts timestamptz column. B-7A asserted only that the str->timestamptz write is accepted and the
stored value round-trips timezone-aware; it did NOT assert timestamp string round-trip fidelity.
PRD 06 B-7B resolved the asymmetry — postgres_store.list_audit now normalizes the driver datetime to
a UTC ISO-8601 *string* on read, so ControlAuditRecord.timestamp is a `str` for both adapters — and
made PostgresControlStore lazy-connect (the connection now opens on first store operation, not at
construction). This harness still reaches the driver only via the adapter and stays valid under both.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402  (standalone live-PG runner: SNACKPORTAL_TEST_DSN, available()/run())

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

from control_plane._util import now_iso  # noqa: E402
from control_plane.adapters.providers.postgres_store import PostgresControlStore  # noqa: E402
from control_plane.records import ControlAuditRecord  # noqa: E402

_SCHEMA = "sp2_b7a_control_audit_scratch"

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_CONTROL = _REPO_ROOT / "infrastructure" / "db" / "control"
_DDL_002 = _CONTROL / "002_provisioning_audit.sql"
_DDL_003 = _CONTROL / "003_provisioning_audit_append_only.sql"

# Reviewed B-7 DDL blobs (full LF-normalized git-blob SHA-1; PRD 06 B-7A R3 §10). The applied bytes
# MUST equal these reviewed-and-merged blobs; a mismatch STOPs the exercise (do not "fix" DDL here).
_REVIEWED_002_BLOB = "887d0cbce636b7a4610272b584ad0aea61eb2294"
_REVIEWED_003_BLOB = "c787c5372c511dc1975d337cdfe871d2d849a2c4"

_EXPECTED_COLS = ["id", "actor", "tenant_id", "action", "from_state", "to_state", "ts", "correlation_id"]
_NULLABLE = {"tenant_id", "from_state", "to_state"}
_NOT_NULL = {"actor", "action", "ts", "correlation_id"}


# --- helpers (stdlib only; driver reached solely via PostgresControlStore._conn) -----------------
def _git_blob_sha1(path: pathlib.Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")  # autocrlf normalization (the git blob is LF)
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _derive_unreachable_dsn(dsn: str) -> str:
    """Derive an unreachable DSN IN MEMORY from `dsn` (port -> 1, short connect-timeout). Never
    printed/written (PRD 06 B-7A R3 §4.3). Keeps userinfo so no separate secret handling is needed."""
    p = urlsplit(dsn)
    auth = ""
    if p.username:
        auth = p.username + ((":" + p.password) if p.password else "") + "@"
    netloc = f"{auth}{p.hostname or 'localhost'}:1"  # port 1 -> connection refused (fast, deterministic)
    query = (p.query + "&" if p.query else "") + "connect_timeout=2"
    return urlunsplit((p.scheme, netloc, p.path, query, p.fragment))


def _store(dsn: str, *, autocommit: bool = False) -> PostgresControlStore:
    """A control-plane store whose session search_path is the scratch schema ONLY (so a missing
    control_audit fails closed instead of resolving public)."""
    s = PostgresControlStore(dsn)
    if autocommit:
        s._conn.autocommit = True
    with s._conn.cursor() as cur:
        cur.execute(f"SET search_path TO {_SCHEMA}")
    if not autocommit:
        s._conn.commit()
    return s


def _raises(conn, sql: str, params=()) -> bool:
    """True iff `sql` raised. Autocommit isolation: a rejected statement is its own aborted
    single-statement transaction, so the connection stays usable for the next statement."""
    try:
        conn.execute(sql, params)
        return False
    except Exception:
        return True


def _scalar(conn, sql: str, params=()):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


# --- the exercise -------------------------------------------------------------------------------
def test_b7a_live_pg_control_audit_ddl(admin_dsn: str) -> None:
    # check 1 — PostgreSQL version gate (>= 11): 003's PL/pgSQL triggers + 002's IDENTITY (R3 §16.1)
    boot = _store(admin_dsn, autocommit=True)  # connects to the DSN's database (search_path set to scratch by _store after CREATE below)
    conn = boot._conn
    server_num = int(_scalar(conn, "SELECT current_setting('server_version_num')"))
    assert server_num >= 110000, f"PostgreSQL >= 11 required (server_version_num={server_num}) — NOT READY (environment)"
    print(f"PASS: 16.1 version gate (server_version_num={server_num} >= 110000)")

    # fresh scratch schema (drop any leftover from a prior crashed run — scratch-only reset, R3 §16.2/§16.15)
    with conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE")
        cur.execute(f"CREATE SCHEMA {_SCHEMA}")
        cur.execute(f"SET search_path TO {_SCHEMA}")
    try:
        # check 2 — table-absent precondition (R3 §16.2)
        assert _scalar(conn, "SELECT to_regclass('control_audit')") is None, "control_audit must be ABSENT before apply"
        print("PASS: 16.2 table-absent precondition (control_audit IS NULL in scratch schema)")

        # check 3 — DDL blob pin (R3 §10/§16.3): applied bytes == reviewed B-7 blobs
        b002, b003 = _git_blob_sha1(_DDL_002), _git_blob_sha1(_DDL_003)
        assert b002 == _REVIEWED_002_BLOB, f"002 blob {b002} != reviewed {_REVIEWED_002_BLOB} — STOP (do not fix DDL in B-7A)"
        assert b003 == _REVIEWED_003_BLOB, f"003 blob {b003} != reviewed {_REVIEWED_003_BLOB} — STOP (do not fix DDL in B-7A)"
        print(f"PASS: 16.3a DDL blob pin (002={b002[:12]}…, 003={b003[:12]}…)")

        # check 3b/4 — apply 002 -> 003 (read from the repo files; never modified)
        with conn.cursor() as cur:
            cur.execute(_DDL_002.read_text(encoding="utf-8"))
            cur.execute(_DDL_003.read_text(encoding="utf-8"))
        assert _scalar(conn, "SELECT to_regclass('control_audit')") is not None, "control_audit must exist after apply"
        print("PASS: 16.3 DDL apply (002 then 003 applied cleanly)")

        # check 5 — table shape (R3 §16.5): exact columns/order, id GENERATED ALWAYS, nullability, no CHECK
        cols = conn.execute(
            "SELECT column_name, data_type, is_nullable, is_identity, identity_generation, column_default "
            "FROM information_schema.columns WHERE table_schema=%s AND table_name='control_audit' ORDER BY ordinal_position",
            (_SCHEMA,),
        ).fetchall()
        names = [c[0] for c in cols]
        assert names == _EXPECTED_COLS, f"column order {names} != {_EXPECTED_COLS}"
        meta = {c[0]: c for c in cols}
        idc = meta["id"]
        assert idc[1] == "bigint" and idc[3] == "YES" and idc[4] == "ALWAYS" and idc[5] is None, (
            f"id must be bigint GENERATED ALWAYS AS IDENTITY (default NULL); got {idc}"
        )
        for c in _NULLABLE:
            assert meta[c][2] == "YES", f"{c} must be NULLABLE"
        for c in _NOT_NULL:
            assert meta[c][2] == "NO", f"{c} must be NOT NULL"
        assert meta["ts"][1] == "timestamp with time zone", f"ts must be timestamptz; got {meta['ts'][1]}"
        pk = conn.execute(
            "SELECT kcu.column_name FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name "
            "AND tc.table_schema=kcu.table_schema WHERE tc.table_schema=%s AND tc.table_name='control_audit' "
            "AND tc.constraint_type='PRIMARY KEY'",
            (_SCHEMA,),
        ).fetchall()
        assert [r[0] for r in pk] == ["id"], f"PRIMARY KEY must be (id); got {pk}"
        checks = _scalar(
            conn,
            "SELECT count(*) FROM pg_constraint WHERE conrelid = %s::regclass AND contype='c'",
            (f"{_SCHEMA}.control_audit",),
        )
        assert checks == 0, f"control_audit must have NO CHECK constraint (events.py is the vocab authority); got {checks}"
        print("PASS: 16.5 table shape (cols/order, id GENERATED ALWAYS, nullability, timestamptz, PK(id), no CHECK)")

        # check 6 — adapter-shape insert + DB-generated id (R3 §16.6); ts bound from an ACTUAL now_iso()
        ts_main = now_iso()
        new_id = _scalar(
            conn,
            "INSERT INTO control_audit (actor, tenant_id, action, from_state, to_state, ts, correlation_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            ("b7a-test-actor", None, "b7a.test.action", None, None, ts_main, "b7a-correlation-001"),
        )
        assert isinstance(new_id, int) and new_id > 0, f"id must be DB-generated; got {new_id!r}"
        row = conn.execute(
            "SELECT actor, tenant_id, action, from_state, to_state, correlation_id FROM control_audit WHERE id=%s",
            (new_id,),
        ).fetchone()
        assert row == ("b7a-test-actor", None, "b7a.test.action", None, None, "b7a-correlation-001"), f"row mismatch: {row}"
        print(f"PASS: 16.6 adapter-shape insert (DB-generated id={new_id}; NULL tenant_id/from_state/to_state accepted)")

        # check 8 — timestamp compatibility (R3 §16.12): now_iso() with and without fractional seconds; tz-aware round-trip
        ts_nofrac = datetime.now(timezone.utc).replace(microsecond=0).isoformat()  # the no-fraction now_iso() form
        id_nofrac = _scalar(
            conn,
            "INSERT INTO control_audit (actor, action, ts, correlation_id) VALUES (%s,%s,%s,%s) RETURNING id",
            ("b7a-ts-actor", "b7a.ts", ts_nofrac, "b7a-correlation-ts-nofrac"),
        )
        stored_main = _scalar(conn, "SELECT ts FROM control_audit WHERE id=%s", (new_id,))
        stored_nofrac = _scalar(conn, "SELECT ts FROM control_audit WHERE id=%s", (id_nofrac,))
        assert getattr(stored_main, "tzinfo", None) is not None, "stored ts (fractional now_iso) must be timezone-aware"
        assert getattr(stored_nofrac, "tzinfo", None) is not None, "stored ts (no-fraction now_iso) must be timezone-aware"
        # NOTE: no assertion on fractional-digit presence; both now_iso() forms are valid (R3 §16.12).
        print("PASS: 16.12 timestamp compatibility (now_iso with/without fraction accepted; round-trip tz-aware)")

        # check 7 — read-path ordering ORDER BY id ASC (R3 §16.8): >=2 rows, strictly increasing ids
        ordered = conn.execute("SELECT id, correlation_id FROM control_audit ORDER BY id ASC").fetchall()
        ids = [r[0] for r in ordered]
        assert len(ids) >= 2 and ids == sorted(ids) and len(set(ids)) == len(ids), f"ORDER BY id ASC not strictly increasing: {ids}"
        assert ordered[0][1] == "b7a-correlation-001", "first appended row must sort first under ORDER BY id ASC"
        print(f"PASS: 16.8 read-path ordering (ORDER BY id ASC; {len(ids)} rows, strictly increasing id)")

        # check 9 — reference-only stored row (R3 §16.9 / D-14): no DSN/password substring in any cell
        p = urlsplit(admin_dsn)
        leak = [s for s in (admin_dsn, p.password or "") if s]
        allrows = conn.execute("SELECT actor, tenant_id, action, from_state, to_state, correlation_id FROM control_audit").fetchall()
        for r in allrows:
            for cell in r:
                for secret in leak:
                    assert secret not in str(cell), "stored cell must not contain the DSN/password (references-only)"
        print(f"PASS: 16.9 reference-only stored row ({len(allrows)} rows; no DSN/secret in any cell)")

        # check 10 — required-field rejection + no-partial-commit (R3 §16.10/§16.11)
        count0 = _scalar(conn, "SELECT count(*) FROM control_audit")
        for field in ("actor", "action", "ts", "correlation_id"):
            vals = {"actor": "b7a-neg", "action": "b7a.neg", "ts": now_iso(), "correlation_id": f"b7a-neg-{field}"}
            vals[field] = None
            assert _raises(
                conn,
                "INSERT INTO control_audit (actor, action, ts, correlation_id) VALUES (%s,%s,%s,%s)",
                (vals["actor"], vals["action"], vals["ts"], vals["correlation_id"]),
            ), f"NULL {field} must be rejected (NOT NULL)"
            assert _scalar(conn, "SELECT count(*) FROM control_audit") == count0, (
                f"NULL-{field} insert must leave NO row (no partial commit)"
            )
        assert _scalar(conn, "SELECT 1") == 1, "connection must remain usable after rejected inserts (autocommit isolation)"
        print("PASS: 16.10/16.11 required-field rejection (actor/action/ts/correlation_id) + no-partial-commit")

        # check 11 — append-only rejection (R3 §16.13): row present; UPDATE/DELETE/TRUNCATE each raise; row unchanged; no SQLSTATE assertion
        before = _scalar(conn, "SELECT action FROM control_audit WHERE id=%s", (new_id,))
        n_before = _scalar(conn, "SELECT count(*) FROM control_audit")
        assert _raises(conn, "UPDATE control_audit SET action='mutated' WHERE id=%s", (new_id,)), "UPDATE must be rejected (append-only)"
        assert _raises(conn, "DELETE FROM control_audit WHERE id=%s", (new_id,)), "DELETE must be rejected (append-only)"
        assert _raises(conn, "TRUNCATE control_audit"), "TRUNCATE must be rejected (append-only)"
        assert _scalar(conn, "SELECT action FROM control_audit WHERE id=%s", (new_id,)) == before, "row unchanged after rejected UPDATE"
        assert _scalar(conn, "SELECT count(*) FROM control_audit") == n_before, "row count must be unchanged after rejected DELETE/TRUNCATE"
        print("PASS: 16.13 append-only rejection (UPDATE/DELETE/TRUNCATE each raised; row/table unchanged)")

        # check 12 — idempotency PROVEN (R3 §16.4): re-apply 002 preserves rows; re-apply 003 keeps triggers enforcing
        with conn.cursor() as cur:
            cur.execute(_DDL_002.read_text(encoding="utf-8"))  # CREATE TABLE IF NOT EXISTS — must not error
        assert _scalar(conn, "SELECT count(*) FROM control_audit") == n_before, "re-applying 002 must preserve existing rows"
        with conn.cursor() as cur:
            cur.execute(_DDL_003.read_text(encoding="utf-8"))  # CREATE OR REPLACE FUNCTION + DROP/CREATE TRIGGER
        assert _raises(conn, "UPDATE control_audit SET action='x' WHERE id=%s", (new_id,)), "after 003 re-apply, UPDATE still rejected"
        print("PASS: 16.4 idempotency PROVEN (re-apply 002 preserves rows; re-apply 003 keeps append-only enforcing)")

        # check 13 — cross-instance durability (R3 §16.7): append via store A, read via fresh store B
        writer = _store(admin_dsn)  # real adapter (non-autocommit; append_audit commits)
        writer.append_audit(
            ControlAuditRecord(
                actor="b7a-durable-actor",
                tenant_id=None,
                action="b7a.durable",
                from_state=None,
                to_state=None,
                timestamp=now_iso(),
                correlation_id="b7a-correlation-durable",
            )
        )
        writer._conn.close()  # discard instance A
        reader = _store(admin_dsn)  # wholly independent instance B
        durable = [r for r in reader.list_audit() if r.correlation_id == "b7a-correlation-durable"]
        reader._conn.close()
        assert len(durable) == 1, "a fresh PostgresControlStore.list_audit() must read the committed row (durability)"
        assert durable[0].actor == "b7a-durable-actor" and durable[0].action == "b7a.durable", "type-stable fields must round-trip"
        print("PASS: 16.7 cross-instance durability (write via store A; read via fresh store B; type-stable fields match)")

        # check 14a — fail-closed: unreachable DSN must RAISE on first operation (derived in memory;
        # never printed) (R3 §16.14). PRD 06 B-7B made PostgresControlStore lazy-connect, so the
        # connection — and its failure — now occurs on first use, not at construction.
        unreachable_raised = False
        try:
            PostgresControlStore(_derive_unreachable_dsn(admin_dsn)).list_audit()
        except Exception:
            unreachable_raised = True
        assert unreachable_raised, "an unreachable DSN must fail closed (raise on first op), never connect silently"
        print("PASS: 16.14a fail-closed unreachable DSN (first-op connect raised; DSN never printed)")

        # check 14b — fail-closed: missing table -> list_audit() RAISES, never returns [] (must be LAST table check)
        with conn.cursor() as cur:
            cur.execute("DROP TABLE control_audit")  # scratch-only; append-only triggers do not block DROP (DDL)
        missing = _store(admin_dsn)
        missing_raised, got_empty = False, False
        try:
            got_empty = missing.list_audit() == []
        except Exception:
            missing_raised = True
        missing._conn.close()
        assert missing_raised and not got_empty, "list_audit() against a MISSING control_audit must RAISE, never return [] (fail-open)"
        print("PASS: 16.14b fail-closed missing table (list_audit raised; did not return [])")

        print("ALL B-7A CHECKS PASSED")
    finally:
        # check 15 — cleanup (R3 §16.15): DROP SCHEMA CASCADE (never DELETE/TRUNCATE); scratch-only
        with conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE")
        conn.close()


if __name__ == "__main__":
    _pg.run([test_b7a_live_pg_control_audit_ddl])
