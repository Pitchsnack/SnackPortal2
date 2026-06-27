"""B-7B runtime audit-sink wiring — live-PostgreSQL exercise (standalone-only; SNACKPORTAL_TEST_DSN).

Proves the controlled non-production B-7B runtime wiring END TO END against a real
non-production PostgreSQL: with `SP2_CP_CONTROL_STORE=postgres` and the control-store DSN
resolved through the REAL D-14 path (EnvReferenceSecretStore + SecretRef, widened allow-list),
`create_app()` selects the durable Control-Store and its operational audit sink
(`ControlPlane.audit`, one consumer of the store) persists to `control_audit` and reads back
type-stable `str` timestamps representing the same instant. It also proves fail-closed:
unreachable DSN, unresolved ref (LookupError), non-allow-listed ref (PermissionError), and a
missing `control_audit` all RAISE on first use (never connect silently / never return []), the
append-only trigger still rejects mutation, construction performs NO I/O (lazy-connect), and a
failed required durable audit write leaves NO partial/committed row.

ISOLATION & SAFETY. Everything runs in a uniquely-named scratch schema
`sp2_b7b_runtime_scratch` created at start and DROP SCHEMA ... CASCADE'd in a finally — it never
touches `public` or any real table, and never CREATE/DROP DATABASE. The reviewed B-7 DDL files
are read + git-blob-pinned only (never modified). The durable runtime store is pinned to the
scratch schema via a libpq `options=-c search_path=...` descriptor (the composition root sets no
search_path itself), so a missing table fails closed rather than resolving `public`.

DRIVER CONTAINMENT. This file imports NO database driver. It reaches PostgreSQL only through the
control-plane adapter `PostgresControlStore` (whose psycopg import lives in the sanctioned
provider zone) via `store._conn`, and through `create_app()`'s durable store.

SECRET HYGIENE (D-14). SNACKPORTAL_TEST_DSN is used by NAME only. The in-process control-store
secret env var (and the scratch/unreachable DSNs derived from it) carry the admin DSN value and
are NEVER printed, logged, or written; stored rows are asserted to contain no DSN/password.

DEFAULT SUITE. IGNORED by the default test run (pyproject addopts
`--ignore=tests/control_plane/requires_pg`). Run it by populating SNACKPORTAL_TEST_DSN (a
non-production admin DSN permitted to CREATE/DROP SCHEMA) and invoking:
  python backend/tests/control_plane/requires_pg/test_pg_control_store_runtime_wiring.py
With SNACKPORTAL_TEST_DSN unset (or psycopg absent) it clean-skips (exit 0).
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import sys
from datetime import datetime
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402  (standalone live-PG runner: SNACKPORTAL_TEST_DSN, available()/run())

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

from control_plane.adapters.providers.postgres_store import PostgresControlStore  # noqa: E402
from control_plane.main import (  # noqa: E402
    CONTROL_STORE_DSN_REF_ENV,
    CONTROL_STORE_ENV,
    DEFAULT_CONTROL_STORE_DSN_REF,
    create_app,
)
from shared.adapters.providers.env_reference_secret_store import EnvReferenceSecretStore  # noqa: E402
from shared.secrets import SecretRef  # noqa: E402

_SCHEMA = "sp2_b7b_runtime_scratch"

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_CONTROL = _REPO_ROOT / "infrastructure" / "db" / "control"
_DDL_002 = _CONTROL / "002_provisioning_audit.sql"
_DDL_003 = _CONTROL / "003_provisioning_audit_append_only.sql"

# Reviewed B-7 DDL blobs (full LF-normalized git-blob SHA-1; same pins as the B-7A harness).
_REVIEWED_002_BLOB = "887d0cbce636b7a4610272b584ad0aea61eb2294"
_REVIEWED_003_BLOB = "c787c5372c511dc1975d337cdfe871d2d849a2c4"

_REF_STORE_REF = DEFAULT_CONTROL_STORE_DSN_REF  # the composition root's default control-store ref


# --- helpers (stdlib only; driver reached solely via PostgresControlStore._conn) -----------------
def _git_blob_sha1(path: pathlib.Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")  # autocrlf normalization (the git blob is LF)
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _secret_env_key() -> str:
    """The env var create_app() resolves the control-store DSN from (D-14; pinned derivation)."""
    return EnvReferenceSecretStore._env_key(_REF_STORE_REF, "1")


def _derive_unreachable_dsn(dsn: str) -> str:
    """Derive an unreachable DSN IN MEMORY (port -> 1, short connect-timeout). Never printed."""
    p = urlsplit(dsn)
    auth = ""
    if p.username:
        auth = p.username + ((":" + p.password) if p.password else "") + "@"
    netloc = f"{auth}{p.hostname or 'localhost'}:1"  # port 1 -> connection refused (fast, deterministic)
    query = (p.query + "&" if p.query else "") + "connect_timeout=2"
    return urlunsplit((p.scheme, netloc, p.path, query, p.fragment))


def _dsn_with_search_path(dsn: str, schema: str) -> str:
    """Pin a URL DSN to a schema via libpq `options=-c search_path=...` (percent-encoded)."""
    p = urlsplit(dsn)
    q = dict(parse_qsl(p.query))
    q["options"] = f"-c search_path={schema}"
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q, quote_via=quote), p.fragment))


def _store(dsn: str, *, autocommit: bool = False) -> PostgresControlStore:
    """A boot/admin control-plane store whose session search_path is the scratch schema ONLY."""
    s = PostgresControlStore(dsn)
    if autocommit:
        s._conn.autocommit = True
    with s._conn.cursor() as cur:
        cur.execute(f"SET search_path TO {_SCHEMA}")
    if not autocommit:
        s._conn.commit()
    return s


def _scalar(conn, sql, params=()):  # type: ignore[no-untyped-def]
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def _raises(conn, sql, params=()) -> bool:  # type: ignore[no-untyped-def]
    try:
        conn.execute(sql, params)
        return False
    except Exception:
        return True


# --- the exercise -------------------------------------------------------------------------------
def test_b7b_live_pg_runtime_wiring(admin_dsn: str) -> None:
    # env we mutate in-process; restored in finally (never printed)
    saved_env = {k: os.environ.get(k) for k in (CONTROL_STORE_ENV, CONTROL_STORE_DSN_REF_ENV, _secret_env_key())}
    scratch_dsn = _dsn_with_search_path(admin_dsn, _SCHEMA)

    boot = _store(admin_dsn, autocommit=True)
    conn = boot._conn
    server_num = int(_scalar(conn, "SELECT current_setting('server_version_num')"))
    assert server_num >= 110000, f"PostgreSQL >= 11 required (server_version_num={server_num}) — NOT READY (environment)"

    with conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE")
        cur.execute(f"CREATE SCHEMA {_SCHEMA}")
        cur.execute(f"SET search_path TO {_SCHEMA}")
    try:
        # 1 — DDL blob pin + apply 002 -> 003 inside the scratch schema (never modify the files)
        b002, b003 = _git_blob_sha1(_DDL_002), _git_blob_sha1(_DDL_003)
        assert b002 == _REVIEWED_002_BLOB, f"002 blob {b002} != reviewed {_REVIEWED_002_BLOB} — STOP"
        assert b003 == _REVIEWED_003_BLOB, f"003 blob {b003} != reviewed {_REVIEWED_003_BLOB} — STOP"
        with conn.cursor() as cur:
            cur.execute(_DDL_002.read_text(encoding="utf-8"))
            cur.execute(_DDL_003.read_text(encoding="utf-8"))
        assert _scalar(conn, "SELECT to_regclass('control_audit')") is not None
        print("PASS: 1 DDL blob pin + apply (002 then 003) in scratch schema")

        # configure the REAL composition-root durable path (secret env populated in-process; never printed)
        os.environ[CONTROL_STORE_ENV] = "postgres"
        os.environ.pop(CONTROL_STORE_DSN_REF_ENV, None)  # use the default ref
        os.environ[_secret_env_key()] = scratch_dsn

        # 2 — no I/O at construction (lazy-connect): create_app() selects durable but does not connect
        cp = create_app()
        assert isinstance(cp.store, PostgresControlStore), "postgres mode must select the durable store"
        assert cp.store._conn_cache is None, "construction must perform NO PostgreSQL I/O (lazy-connect)"
        print("PASS: 2 durable selection + no-I/O construction (lazy-connect)")

        # 3 — durable audit write through the REAL audit consumer -> control_audit (scratch)
        cp.audit.record(
            actor="b7b-runtime-actor",
            tenant_id=None,
            action="b7b.runtime.wiring",
            from_state=None,
            to_state=None,
            correlation_id="b7b-corr-1",
        )
        assert cp.store._conn_cache is not None, "first store op must have opened the connection"
        assert _scalar(conn, "SELECT count(*) FROM control_audit WHERE correlation_id=%s", ("b7b-corr-1",)) == 1
        print("PASS: 3 durable audit write reaches control_audit via create_app() wiring")

        # 4 — read-back type-stable str timestamp, SAME instant (the B-7B headline fix, live)
        stored_dt = _scalar(conn, "SELECT ts FROM control_audit WHERE correlation_id=%s", ("b7b-corr-1",))
        rec = [r for r in cp.audit.events() if r.correlation_id == "b7b-corr-1"][0]
        assert isinstance(rec.timestamp, str), "list_audit timestamp must be str (B7B-D7)"
        assert datetime.fromisoformat(rec.timestamp).tzinfo is not None, "timestamp must be timezone-aware"
        assert datetime.fromisoformat(rec.timestamp) == stored_dt, "list_audit timestamp must be the SAME instant"
        print("PASS: 4 type-stable str timestamp, same instant (forward defect resolved live)")

        # 5 — reference-only stored row (no DSN/password leak)
        p = urlsplit(admin_dsn)
        leak = [s for s in (admin_dsn, p.password or "") if s]
        allrows = conn.execute("SELECT actor, tenant_id, action, from_state, to_state, correlation_id FROM control_audit").fetchall()
        for r in allrows:
            for cell in r:
                for secret in leak:
                    assert secret not in str(cell), "stored cell must not contain the DSN/password (references-only)"
        print("PASS: 5 reference-only stored row (no DSN/secret in any cell)")

        # 6 — cross-instance durability + no-I/O construction on a fresh instance
        cp2 = create_app()
        assert cp2.store._conn_cache is None, "fresh durable store must construct without I/O"
        durable = [r for r in cp2.audit.events() if r.correlation_id == "b7b-corr-1"]
        assert len(durable) == 1 and durable[0].actor == "b7b-runtime-actor"
        if cp2.store._conn_cache is not None:
            cp2.store._conn_cache.close()
        print("PASS: 6 cross-instance durability (fresh create_app reads the committed row)")

        # Release the durable read transactions BEFORE the TRUNCATE check: a non-autocommit
        # SELECT (cp.audit.events) leaves an open ACCESS SHARE lock that would block TRUNCATE.
        if cp.store._conn_cache is not None:
            cp.store._conn_cache.close()

        # 7 — append-only still rejects mutation (via boot adapter conn; autocommit isolation)
        new_id = _scalar(conn, "SELECT id FROM control_audit WHERE correlation_id=%s", ("b7b-corr-1",))
        before = _scalar(conn, "SELECT action FROM control_audit WHERE id=%s", (new_id,))
        assert _raises(conn, "UPDATE control_audit SET action='mutated' WHERE id=%s", (new_id,)), "UPDATE must be rejected"
        assert _raises(conn, "DELETE FROM control_audit WHERE id=%s", (new_id,)), "DELETE must be rejected"
        assert _raises(conn, "TRUNCATE control_audit"), "TRUNCATE must be rejected"
        assert _scalar(conn, "SELECT action FROM control_audit WHERE id=%s", (new_id,)) == before, "row unchanged"
        print("PASS: 7 append-only rejection (UPDATE/DELETE/TRUNCATE) under durable wiring")

        # 8 — fail-closed + NO partial state: an unreachable durable DSN raises and commits NO row
        os.environ[_secret_env_key()] = _derive_unreachable_dsn(scratch_dsn)
        cp_unreach = create_app()
        unreachable_raised = False
        try:
            cp_unreach.audit.record(
                actor="b7b-unreach",
                tenant_id=None,
                action="b7b.unreachable",
                from_state=None,
                to_state=None,
                correlation_id="b7b-corr-unreachable",
            )
        except Exception:
            unreachable_raised = True
        if cp_unreach.store._conn_cache is not None:
            cp_unreach.store._conn_cache.close()
        assert unreachable_raised, "an unreachable durable DSN must fail closed (raise on first use)"
        assert _scalar(conn, "SELECT count(*) FROM control_audit WHERE correlation_id=%s", ("b7b-corr-unreachable",)) == 0, (
            "a failed required durable audit write must leave NO partial/committed row"
        )
        os.environ[_secret_env_key()] = scratch_dsn  # restore the good descriptor
        print("PASS: 8 fail-closed unreachable DSN + no partial state (no orphan row)")

        # 9 — fail-closed: unresolved ref (LookupError) raises on first use
        os.environ.pop(_secret_env_key(), None)
        cp_missing_ref = create_app()
        lookup_raised = False
        try:
            cp_missing_ref.audit.events()
        except LookupError:
            lookup_raised = True
        assert lookup_raised, "an unresolved control-store ref must fail closed (LookupError)"
        os.environ[_secret_env_key()] = scratch_dsn  # restore
        print("PASS: 9 fail-closed unresolved ref (LookupError)")

        # 10 — fail-closed: non-allow-listed ref (PermissionError) raises (adapter-level, default allow-list)
        perm_store = PostgresControlStore(secrets=EnvReferenceSecretStore(), ref=SecretRef(_REF_STORE_REF, "1"))
        perm_raised = False
        try:
            perm_store.list_audit()
        except PermissionError:
            perm_raised = True
        assert perm_raised, "a non-allow-listed control-store ref must fail closed (PermissionError)"
        print("PASS: 10 fail-closed non-allow-listed ref (PermissionError)")

        # 11 — fail-closed: missing control_audit -> list_audit RAISES, never returns [] (LAST table check)
        with conn.cursor() as cur:
            cur.execute("DROP TABLE control_audit")  # scratch-only; triggers do not block DROP (DDL)
        cp_missing_tbl = create_app()
        missing_raised, got_empty = False, False
        try:
            got_empty = cp_missing_tbl.audit.events() == []
        except Exception:
            missing_raised = True
        if cp_missing_tbl.store._conn_cache is not None:
            cp_missing_tbl.store._conn_cache.close()
        assert missing_raised and not got_empty, "list_audit against a MISSING control_audit must RAISE, never return []"
        print("PASS: 11 fail-closed missing table (list_audit raised; did not return [])")

        print("ALL B-7B RUNTIME-WIRING CHECKS PASSED")
    finally:
        with conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE")
        conn.close()
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


if __name__ == "__main__":
    _pg.run([test_b7b_live_pg_runtime_wiring])
