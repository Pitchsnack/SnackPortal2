"""AW-1 Tier-A — disposable least-privilege privilege rehearsal (MANUAL_ONLY; standalone only).

Proves, on **disposable** infrastructure and before any Gate-B mutation, that the byte-frozen AW-1
§5.4 payload produces exactly the intended privilege surface — that `sp2_gateway_audit_writer` can
`INSERT` and `SELECT` on `public.control_gateway_audit` and can do **nothing else anywhere**.

WHY THIS RUNS ON DISPOSABLE INFRASTRUCTURE. `CREATE ROLE` is **cluster-scoped**: the rehearsal roles
land wherever the rehearsal runs. Running this against the standing control cluster would create the
Gate-B roles ahead of Gate B. `SNACKPORTAL_TEST_DSN` must never point at the standing Control
database (the standing runbook rule), and this harness additionally refuses to proceed if the
disposable database name is already taken.

TWO EXECUTABILITY PRECONDITIONS THAT MAKE OR BREAK THE PROOF:

* **The database must be named exactly `snackportal2_control_local`.** The frozen payload contains
  `GRANT CONNECT ON DATABASE snackportal2_control_local`, and the block is byte-frozen — it must
  execute verbatim, with zero deviation. The name is asserted ABSENT on the rehearsal instance first.
* **Control DDL 001–009 must be applied, then blob-pinned 012, then 013.** Without the sibling
  tables, every V-7 negative probe raises `undefined_table` (42P01) instead of permission-denied — a
  vacuous pass for the wrong reason. Without 012 the payload's table grants fail outright. 010/011
  and 014/015 stay **absent**, matching the standing baseline.

EVERY "DENIED" ASSERTION PINS SQLSTATE **42501** (`insufficient_privilege`). A denial arriving with
any other SQLSTATE is a FAILURE, not a pass — a bare `except Exception` would let a typo, a missing
table, or a syntax error read as a security proof.

TEARDOWN, GUARANTEED IN `finally`, IN THIS ORDER: `DROP DATABASE` first (removing every
database-local ACL reference and the database's own `datacl` CONNECT entry), then
`DROP ROLE sp2_gateway_audit_ingest`, then `DROP ROLE sp2_gateway_audit_writer`. A role still
referenced by any ACL cannot be dropped, which is why the database goes first.

MANUAL_ONLY and deliberately **NOT** loop-enrolled: it needs a disposable cluster it may create
roles on, and enrolling it would move a lockstep that must not move (see the AW-1 boundary guard's
`test_the_hosted_loop_lockstep_is_deliberately_untouched`).

    python tests/control_plane/requires_pg/test_pg_aw1_gateway_audit_writer_rehearsal.py
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import pathlib
import sys
from typing import Any, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_CONTROL_DDL_DIR = _REPO_ROOT / "infrastructure" / "db" / "control"

# 001-009 is the governed standing apply order; 012/013 are added because the writer's grants target
# control_gateway_audit and V-8a needs the append-only triggers. 010/011 and 014/015 stay ABSENT.
_BASE_DDL: Tuple[str, ...] = (
    "001_distinctness_ledger.sql",
    "002_provisioning_audit.sql",
    "003_provisioning_audit_append_only.sql",
    "004_control_tenants.sql",
    "005_control_memberships.sql",
    "006_control_federation.sql",
    "007_control_directory.sql",
    "008_distinctness_fingerprint_unique.sql",
    "009_control_tenants_cas_version.sql",
)
_DDL_012 = _CONTROL_DDL_DIR / "012_gateway_operational_audit.sql"
_DDL_013 = _CONTROL_DDL_DIR / "013_gateway_operational_audit_append_only.sql"

# Reviewed LF-normalized git-blob SHA-1 pins. A mismatch STOPS the rehearsal BEFORE any connection is
# opened and before any SQL is applied. Moved in lockstep with the four Python pin sites and the two
# runbook literals whenever the DDL changes.
_REHEARSAL_BLOB_012 = "d2c70bab2a1c00d836b428d0c04a3bf61f4df1ae"
_REHEARSAL_BLOB_013 = "4377ec309cc7640cf36b35491c63168ef05d60f4"

_INSUFFICIENT_PRIVILEGE = "42501"


def _tool() -> Any:
    """The operator tool under rehearsal — the SAME frozen payload the Gate-B apply executes."""
    spec = importlib.util.spec_from_file_location(
        "aw1_gateway_audit_writer", pathlib.Path(__file__).resolve().parent / "aw1_gateway_audit_writer.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git_blob_sha1(path: pathlib.Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _verify_blobs() -> None:
    b012, b013 = _git_blob_sha1(_DDL_012), _git_blob_sha1(_DDL_013)
    assert b012 == _REHEARSAL_BLOB_012, f"012 blob {b012} != pinned {_REHEARSAL_BLOB_012} — STOP before connect/apply"
    assert b013 == _REHEARSAL_BLOB_013, f"013 blob {b013} != pinned {_REHEARSAL_BLOB_013} — STOP before connect/apply"
    print(f"PASS: AW1-0 reviewed DDL blob pins verified BEFORE any connection (012={b012[:12]}…, 013={b013[:12]}…)")


def _sqlstate(exc: BaseException) -> Optional[str]:
    return getattr(exc, "sqlstate", None)


def _denied_42501(conn: Any, sql: str, label: str) -> None:
    """Assert `sql` is refused with SQLSTATE 42501 — never a bare 'it raised'."""
    try:
        conn.execute(sql)
    except Exception as exc:  # noqa: BLE001 — the SQLSTATE is inspected, not swallowed
        state = _sqlstate(exc)
        assert state == _INSUFFICIENT_PRIVILEGE, (
            f"{label}: DENIED with SQLSTATE {state!r}, expected {_INSUFFICIENT_PRIVILEGE} (insufficient_privilege). "
            "Any other SQLSTATE is a FAILURE — a wrong-reason refusal is not a security proof."
        )
        return
    raise AssertionError(f"{label}: the statement SUCCEEDED; it must be denied with SQLSTATE {_INSUFFICIENT_PRIVILEGE}")


def rehearse(admin_dsn: str) -> None:
    psycopg = importlib.import_module("psycopg")
    tool = _tool()
    _verify_blobs()

    db = tool.CONTROL_DATABASE
    writer, ingest = tool.WRITER_ROLE, tool.INGEST_ROLE
    rehearsal_password = tool._mint_password()  # never printed; local to this process

    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        # ---- preconditions -----------------------------------------------------------------
        version = int(admin.execute("SELECT current_setting('server_version_num')::int").fetchone()[0])
        assert version >= tool.MIN_SERVER_VERSION_NUM, (
            f"server_version_num {version} < {tool.MIN_SERVER_VERSION_NUM}: on PG < 15 the CREATE-in-public probe "
            "passes for the wrong reason (the PUBLIC schema-CREATE default) and the rehearsal is vacuous"
        )
        major = version // 10000
        if major != tool.STANDING_SERVER_MAJOR:
            print(f"WARN: rehearsal major {major} != standing major {tool.STANDING_SERVER_MAJOR}; record this in evidence")
        print(f"PASS: AW1-1 server version accepted (server_version_num={version}, major={major})")

        exists = admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db,)).fetchone()
        assert not exists, (
            f"database {db!r} ALREADY EXISTS on this instance. SNACKPORTAL_TEST_DSN must never point at the standing "
            "Control database, and this rehearsal creates and drops that exact name — refusing to proceed."
        )
        for role in (writer, ingest):
            assert not admin.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone(), (
                f"role {role!r} already exists on this cluster. CREATE ROLE is cluster-scoped; a pre-existing role "
                "means this is not a clean disposable instance."
            )
        print(f"PASS: AW1-2 disposable target clean ({db} absent; neither AW-1 role present on this cluster)")

        admin.execute(f'CREATE DATABASE "{db}"')
    except BaseException:
        admin.close()
        raise

    proof_dsn = _pg.swap_db(admin_dsn, db)
    conn = None
    try:
        conn = psycopg.connect(proof_dsn, autocommit=True)

        # ---- content: 001-009, then 012, then 013 ------------------------------------------
        for name in _BASE_DDL:
            conn.execute((_CONTROL_DDL_DIR / name).read_text(encoding="utf-8"))
        conn.execute(_DDL_012.read_text(encoding="utf-8"))
        conn.execute(_DDL_013.read_text(encoding="utf-8"))
        present = {
            row[0] for row in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename").fetchall()
        }
        for table in tool.UNRELATED_TABLES:
            assert table in present, f"{table} missing — every V-7 negative would be vacuous (undefined_table, not denied)"
        assert "control_gateway_audit" in present
        assert "control_routing_audit" not in present and "control_import_audit" not in present, (
            "010/011 and 014/015 must stay ABSENT so the rehearsal matches the standing baseline"
        )
        print(f"PASS: AW1-3 rehearsal content applied (001-009 + 012 + 013; {len(present)} public tables; 010/011/014/015 absent)")

        # ---- the frozen payload, VERBATIM ---------------------------------------------------
        conn.execute(tool.FROZEN_ROLE_GRANT_SQL)
        print("PASS: AW1-4 the byte-frozen §5.4 payload executed verbatim against the disposable database")

        # ---- V-6: complete role-state census, BOTH roles ------------------------------------
        state = tool.observe_role_state(conn)
        for role in (writer, ingest):
            assert state["roles"][role]["attributes"] == tool.EXPECTED_ATTRIBUTES[role], (
                f"V-6(a) {role} attribute vector {state['roles'][role]['attributes']} != {tool.EXPECTED_ATTRIBUTES[role]}"
            )
            assert state["roles"][role]["inherit"] == tool.EXPECTED_INHERIT[role], f"V-6(a) {role} rolinherit"
            assert state["comments"][role] == tool.EXPECTED_COMMENTS[role], f"V-6 {role} COMMENT ON ROLE text"
            assert state["owned_objects"][role] == 0, f"V-6(f) {role} must own zero objects"
        assert state["memberships"] == [(writer, ingest, False)], (
            f"V-6(b..e) membership roster {state['memberships']} != exactly one PLAIN grant of {writer} to {ingest}"
        )
        print("PASS: AW1-5 (V-6) role-state census: attribute vectors, inherit, comments, zero ownership, one plain membership")

        # ---- V-1: NOLOGIN writer, LOGIN ingest ----------------------------------------------
        conn.execute(f'ALTER ROLE "{ingest}" PASSWORD %s', (rehearsal_password,))
        ingest_dsn = _writer_dsn(proof_dsn, ingest, rehearsal_password)
        writer_dsn = _writer_dsn(proof_dsn, writer, rehearsal_password)
        with psycopg.connect(ingest_dsn, autocommit=True) as probe:
            who = probe.execute("SELECT current_user, session_user").fetchone()
            assert who == (ingest, ingest), f"V-1 connected identity {who} != ({ingest!r}, {ingest!r})"
        try:
            psycopg.connect(writer_dsn, connect_timeout=5).close()
            raise AssertionError(f"V-1 {writer} is NOLOGIN and MUST NOT be able to connect")
        except AssertionError:
            raise
        except Exception:  # noqa: BLE001 — a refused login is the expected outcome
            pass
        print(f"PASS: AW1-6 (V-1) {ingest} connects; {writer} is NOLOGIN and cannot")

        # ---- V-2/V-3/V-4: positive surface at the writer identity ---------------------------
        with psycopg.connect(ingest_dsn, autocommit=True) as w:
            before = int(w.execute("SELECT count(*) FROM control_gateway_audit").fetchone()[0])
            inserted = w.execute(
                "INSERT INTO control_gateway_audit (audit_id, event_version, occurred_at, correlation_id, action,"
                " outcome, source_service) VALUES (%s, 1, now(), %s, 'workspace_memberships_read', 'success',"
                " 'api_gateway') ON CONFLICT (audit_id) DO NOTHING RETURNING id",
                ("aw1rehearsal0000000000000000000a", "aw1-rehearsal-correlation"),
            ).fetchone()
            assert inserted is not None, "V-2 the writer's INSERT must succeed and RETURNING must yield the DB-assigned id"
            assert int(w.execute("SELECT count(*) FROM control_gateway_audit").fetchone()[0]) == before + 1
            print("PASS: AW1-7 (V-2/V-3) INSERT succeeded at the writer identity with ZERO sequence grants; RETURNING id works")

            replay = w.execute(
                "INSERT INTO control_gateway_audit (audit_id, event_version, occurred_at, correlation_id, action,"
                " outcome, source_service) VALUES (%s, 1, now(), %s, 'workspace_memberships_read', 'success',"
                " 'api_gateway') ON CONFLICT (audit_id) DO NOTHING RETURNING id",
                ("aw1rehearsal0000000000000000000a", "aw1-rehearsal-correlation"),
            ).fetchone()
            assert replay is None, "V-4 an exact replay must be suppressed by ON CONFLICT DO NOTHING"
            stored = w.execute(
                "SELECT audit_id, action FROM control_gateway_audit WHERE audit_id = %s",
                ("aw1rehearsal0000000000000000000a",),
            ).fetchone()
            assert stored is not None, "V-4 the replay comparison SELECT is load-bearing and must be permitted"
            print("PASS: AW1-8 (V-4) replay suppressed and the replay-comparison SELECT permitted (SELECT is load-bearing)")

            # ---- V-5: negative privilege probes, each DENIED with 42501 ---------------------
            _denied_42501(w, "UPDATE control_gateway_audit SET outcome = 'x'", "V-5 UPDATE")
            _denied_42501(w, "DELETE FROM control_gateway_audit", "V-5 DELETE")
            _denied_42501(w, "TRUNCATE control_gateway_audit", "V-5 TRUNCATE")
            _denied_42501(w, "CREATE TABLE aw1_probe (x int)", "V-5 CREATE TABLE in public")
            _denied_42501(w, "ALTER TABLE control_gateway_audit ADD COLUMN aw1_probe int", "V-5 ALTER TABLE")
            _denied_42501(w, "DROP TABLE control_gateway_audit", "V-5 DROP TABLE")
            _denied_42501(w, "CREATE ROLE aw1_probe_role", "V-5 CREATE ROLE")
            _denied_42501(w, "SET ROLE sp2_local", "V-5 SET ROLE sp2_local")
            print("PASS: AW1-9 (V-5) eight negative privilege probes, each DENIED with SQLSTATE 42501")

            # ---- V-7: unrelated Control-DB tables, each DENIED with 42501 ------------------
            for table in tool.UNRELATED_TABLES:
                _denied_42501(w, f"SELECT 1 FROM {table} LIMIT 1", f"V-7 SELECT on {table}")
            print(f"PASS: AW1-10 (V-7) {len(tool.UNRELATED_TABLES)} unrelated Control-DB tables unreadable, each DENIED with 42501")

        # ---- V-8a: the 013 triggers are a backstop even ABOVE the privilege layer -----------
        for statement, label in (
            ("UPDATE control_gateway_audit SET outcome = 'x'", "V-8a owner UPDATE"),
            ("DELETE FROM control_gateway_audit", "V-8a owner DELETE"),
            ("TRUNCATE control_gateway_audit", "V-8a owner TRUNCATE"),
        ):
            try:
                conn.execute(statement)
            except Exception as exc:  # noqa: BLE001
                assert "append-only" in str(exc), f"{label}: rejected, but not by the 013 append-only trigger ({exc})"
            else:
                raise AssertionError(f"{label}: SUCCEEDED as the owner; the 013 trigger backstop is not working")
        print("PASS: AW1-11 (V-8a) the 013 append-only triggers reject owner-identity UPDATE/DELETE/TRUNCATE")

        # ---- V-9a: structural cluster-scoping ------------------------------------------------
        elsewhere = admin.execute("SELECT count(*) FROM pg_roles WHERE rolname = ANY(%s)", ([writer, ingest],)).fetchone()[0]
        assert int(elsewhere) == 2, "V-9a both roles must exist on the rehearsal cluster (and, by cluster scoping, only there)"
        print("PASS: AW1-12 (V-9a) roles exist on the rehearsal cluster only — CREATE ROLE is cluster-scoped by construction")

    finally:
        # Order is load-bearing: a role still referenced by any ACL cannot be dropped, and the
        # database's own datacl carries the writer's CONNECT grant. Database first, then ingest
        # (the member), then writer.
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
        errors: List[str] = []
        for statement in (f'DROP DATABASE IF EXISTS "{db}"', f'DROP ROLE IF EXISTS "{ingest}"', f'DROP ROLE IF EXISTS "{writer}"'):
            try:
                admin.execute(statement)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{statement}: {exc}")
        admin.close()
        if errors:
            print("TEARDOWN INCOMPLETE — resolve manually before re-running:")
            for error in errors:
                print(f"    - {error}")
        else:
            print(f"PASS: AW1-13 teardown complete in order (DROP DATABASE {db} -> DROP ROLE {ingest} -> DROP ROLE {writer})")


def _writer_dsn(base_dsn: str, role: str, password: str) -> str:
    """Compose a rehearsal DSN for `role`. Local to this process; never printed, never persisted."""
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(base_dsn)
    host = parts.hostname or "127.0.0.1"
    port = f":{parts.port}" if parts.port else ""
    return urlunsplit((parts.scheme, f"{role}:{password}@{host}{port}", parts.path, parts.query, parts.fragment))


def test_aw1_tier_a_disposable_privilege_rehearsal(admin_dsn: str) -> None:
    rehearse(admin_dsn)


if __name__ == "__main__":
    _pg.run([test_aw1_tier_a_disposable_privilege_rehearsal])
