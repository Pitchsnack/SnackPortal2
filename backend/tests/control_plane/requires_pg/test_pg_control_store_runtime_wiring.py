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
import threading
import time
from dataclasses import replace
from datetime import datetime
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402  (standalone live-PG runner: SNACKPORTAL_TEST_DSN, available()/run())

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

from control_plane import events  # noqa: E402
from control_plane._util import now_iso  # noqa: E402
from control_plane.adapters.providers.in_memory_distinctness import nonprod_control_db_evidence  # noqa: E402
from control_plane.adapters.providers.in_memory_probe import InMemoryTenantDatabaseProbe  # noqa: E402
from control_plane.adapters.providers.postgres_store import PostgresControlStore  # noqa: E402
from control_plane.audit import ControlPlaneAudit  # noqa: E402
from control_plane.distinctness import DistinctnessResult  # noqa: E402
from control_plane.main import (  # noqa: E402
    CONTROL_STORE_DSN_REF_ENV,
    CONTROL_STORE_ENV,
    DEFAULT_CONTROL_STORE_DSN_REF,
    CanonicalTenantRefInMemoryEvidence,
    create_app,
)
from control_plane.ports import ControlStoreConcurrencyError  # noqa: E402
from control_plane.provisioning import REASON_CONCURRENT_LIFECYCLE_WINNER, ProvisioningVerificationService  # noqa: E402
from control_plane.records import ControlAuditRecord, TenantLifecycleState, TenantRecord  # noqa: E402
from control_plane.registry import RegistryError, TenantRegistry  # noqa: E402
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


# --- PRD 07D-2e — lifecycle CAS live proofs (R-2c-LWW closure) ------------------------------------
# Folded into this ALREADY-ENROLLED harness (D-2e-6: no workflow edit, no new requires_pg file).
# The 009 DDL blob is byte-pinned in test_pg_control_schema_mcc.py + the default-suite blob guard
# (single source of truth); this function applies the repo bytes into its own scratch schema —
# the same unpinned-apply precedent as the composition harness.
_CAS_SCHEMA = "sp2_2e_cas_scratch"
_DDL_004 = _CONTROL / "004_control_tenants.sql"
_DDL_009 = _CONTROL / "009_control_tenants_cas_version.sql"


def _cas_store(admin_dsn: str, *, autocommit: bool = False) -> PostgresControlStore:
    """A store whose session search_path is the 2e CAS scratch schema ONLY."""
    s = PostgresControlStore(admin_dsn)
    if autocommit:
        s._conn.autocommit = True
    with s._conn.cursor() as cur:
        cur.execute(f"SET search_path TO {_CAS_SCHEMA}")
    if not autocommit:
        s._conn.commit()
    return s


def _cas_tenant(tid: str, state: TenantLifecycleState) -> TenantRecord:
    return TenantRecord(
        tenant_id=tid,
        organization_ref="org-2e",
        lifecycle_state=state,
        expected_schema_version="1",
        database_association_ref=SecretRef(f"tenant/{tid}/dsn", "1"),
        federation_config_ref="fed-2e",
        created_at=now_iso(),
        updated_at=now_iso(),
    )


def test_2e_cas_lifecycle_live(admin_dsn: str) -> None:
    boot = _cas_store(admin_dsn, autocommit=True)
    conn = boot._conn
    with conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {_CAS_SCHEMA} CASCADE")
        cur.execute(f"CREATE SCHEMA {_CAS_SCHEMA}")
        cur.execute(f"SET search_path TO {_CAS_SCHEMA}")
    opened: list = []
    try:
        # apply 002+003 (control_audit + append-only), 004 (control_tenants), 009 (CAS version)
        for ddl in (_DDL_002, _DDL_003, _DDL_004, _DDL_009):
            with conn.cursor() as cur:
                cur.execute(ddl.read_text(encoding="utf-8"))

        # 2E-1 — 009 applied: version bigint NOT NULL DEFAULT 0 (idempotent re-apply clean)
        row = conn.execute(
            "SELECT data_type, is_nullable, column_default FROM information_schema.columns "
            "WHERE table_schema=%s AND table_name='control_tenants' AND column_name='version'",
            (_CAS_SCHEMA,),
        ).fetchone()
        assert row is not None, "control_tenants.version must exist after 009"
        assert row[0] == "bigint" and row[1] == "NO" and "0" in (row[2] or ""), f"version shape wrong: {row}"
        with conn.cursor() as cur:
            cur.execute(_DDL_009.read_text(encoding="utf-8"))  # idempotent re-apply — must not error
        print("PASS: 2E-1 009 applied (version bigint NOT NULL DEFAULT 0; re-apply idempotent)")

        # 2E-2 — CAS success increments version; durable exactly with its committing audit append
        store = _cas_store(admin_dsn)
        opened.append(store)
        store.put_tenant(_cas_tenant("t_cas", TenantLifecycleState.REGISTERED))  # create/seed path, version 0
        out = store.compare_and_swap_tenant(
            replace(store.get_tenant("t_cas"), lifecycle_state=TenantLifecycleState.PROVISIONING, updated_at=now_iso()),
            expected_version=0,
        )
        assert out.version == 1
        uncommitted = conn.execute("SELECT lifecycle_state, version FROM control_tenants WHERE tenant_id='t_cas'").fetchone()
        assert uncommitted == ("Registered", 0), f"the CAS write must be INVISIBLE before its audit commits: {uncommitted}"
        store.append_audit(
            ControlAuditRecord(
                actor="op-2e",
                tenant_id="t_cas",
                action="MarkProvisioning",
                from_state="Registered",
                to_state="Provisioning",
                timestamp=now_iso(),
                correlation_id="c-2e-cas1",
            )
        )
        committed = conn.execute("SELECT lifecycle_state, version FROM control_tenants WHERE tenant_id='t_cas'").fetchone()
        assert committed == ("Provisioning", 1), f"audit commit must make the CAS durable: {committed}"
        print("PASS: 2E-2 CAS success increments version; durable in ONE transaction with its audit append")

        # 2E-3 — stale expected_version raises the typed error and leaves the row unchanged
        raised = False
        try:
            store.compare_and_swap_tenant(
                replace(store.get_tenant("t_cas"), lifecycle_state=TenantLifecycleState.SUSPENDED), expected_version=0
            )
        except ControlStoreConcurrencyError:
            raised = True
        assert raised, "a stale expected_version must raise ControlStoreConcurrencyError"
        unchanged = conn.execute("SELECT lifecycle_state, version FROM control_tenants WHERE tenant_id='t_cas'").fetchone()
        assert unchanged == ("Provisioning", 1), f"a refused CAS must leave the row unchanged: {unchanged}"
        print("PASS: 2E-3 stale CAS refused (typed error; row byte-unchanged)")

        # 2E-4 — transactional audit+CAS rollback: a failed audit append discards the CAS work
        audits_before = conn.execute("SELECT count(*) FROM control_audit").fetchone()[0]
        store4 = _cas_store(admin_dsn)
        opened.append(store4)
        store4.compare_and_swap_tenant(
            replace(store4.get_tenant("t_cas"), lifecycle_state=TenantLifecycleState.SUSPENDED, updated_at=now_iso()),
            expected_version=1,
        )
        bad_audit_raised = False
        try:  # ts is timestamptz: an unparseable timestamp fails server-side inside the SAME txn
            store4.append_audit(
                ControlAuditRecord(
                    actor="op-2e",
                    tenant_id="t_cas",
                    action="SuspendTenant",
                    from_state="Provisioning",
                    to_state="Suspended",
                    timestamp="not-a-timestamp",
                    correlation_id="c-2e-rb",
                )
            )
        except Exception:
            bad_audit_raised = True
        assert bad_audit_raised, "the failed audit append must propagate (fail closed)"
        after_rb = conn.execute("SELECT lifecycle_state, version FROM control_tenants WHERE tenant_id='t_cas'").fetchone()
        assert after_rb == ("Provisioning", 1), f"the failed audit must roll the CAS back (no partial state): {after_rb}"
        assert conn.execute("SELECT count(*) FROM control_audit").fetchone()[0] == audits_before, "no orphan audit row"
        print("PASS: 2E-4 transactional rollback (failed audit append discards the CAS; no orphan audit)")

        # 2E-5 — R-2c-LWW TWO-WRITER PROOF: a suspend committing inside verify()'s window WINS
        store.put_tenant(_cas_tenant("t_lww", TenantLifecycleState.READY))  # seed READY, version 0
        store_a = _cas_store(admin_dsn)
        opened.append(store_a)
        svc = ProvisioningVerificationService(
            store_a,
            ControlPlaneAudit(store_a),
            InMemoryTenantDatabaseProbe(schema_version="1"),
            CanonicalTenantRefInMemoryEvidence(),
            nonprod_control_db_evidence(),
            supported_schema_versions=["1"],
        )
        store_b = _cas_store(admin_dsn)
        opened.append(store_b)
        rec_b = store_b.get_tenant("t_lww")
        assert rec_b is not None and rec_b.version == 0
        # Writer B: the suspend CAS, executed and held UNCOMMITTED (row lock held; the window open)
        store_b.compare_and_swap_tenant(
            replace(rec_b, lifecycle_state=TenantLifecycleState.SUSPENDED, updated_at=now_iso()), expected_version=0
        )
        outcome: dict = {}

        def _verifier() -> None:
            try:
                outcome["result"] = svc.verify("t_lww", actor="op-2e", correlation_id="c-2e-lww")
            except Exception as exc:  # a raw escape = FAIL (asserted below)
                outcome["error"] = type(exc).__name__

        verifier_thread = threading.Thread(target=_verifier)
        verifier_thread.start()
        # Deterministic overlap: A's VERIFYING CAS blocks on B's row lock (observed), then B commits.
        deadline = time.time() + 30
        blocked = False
        while time.time() < deadline:
            n = conn.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND wait_event_type = 'Lock'"
            ).fetchone()[0]
            if n and n >= 1:
                blocked = True
                break
            time.sleep(0.05)
        assert blocked, "the verifier never LOCK-blocked on the uncommitted suspend — overlap not established"
        print("PASS: 2E-5a overlap established (verifier LOCK-blocked while the suspend is uncommitted)")
        store_b.append_audit(  # B commits: suspend + its audit become durable in one transaction
            ControlAuditRecord(
                actor="op-2e",
                tenant_id="t_lww",
                action="SuspendTenant",
                from_state="Ready",
                to_state="Suspended",
                timestamp=now_iso(),
                correlation_id="c-2e-lww-b",
            )
        )
        verifier_thread.join(timeout=30)
        assert not verifier_thread.is_alive(), "verifier thread must finish after the winner commits"
        assert "error" not in outcome, f"verify() must YIELD, not raise: {outcome.get('error')}"
        result = outcome["result"]
        assert result.result is DistinctnessResult.VERIFICATION_INCOMPLETE, f"must yield non-routable: {result}"
        assert result.reason == REASON_CONCURRENT_LIFECYCLE_WINNER, result.reason
        final = conn.execute("SELECT lifecycle_state, version FROM control_tenants WHERE tenant_id='t_lww'").fetchone()
        assert final == ("Suspended", 1), f"the legitimate winner must be preserved: {final}"
        lww_acts = [r[0] for r in conn.execute("SELECT action FROM control_audit WHERE tenant_id='t_lww'").fetchall()]
        assert events.ROUTING_ENABLED not in lww_acts, "routing must NEVER be enabled over a concurrent suspend"
        assert events.DISTINCTNESS_VERIFICATION_STARTED not in lww_acts, "the loser's started event rolled back with its CAS"
        assert events.TENANT_QUARANTINED not in lww_acts, "the legitimate winner must not be auto-quarantined"
        print("PASS: 2E-5 R-2c-LWW two-writer proof (suspend wins; verify yields VERIFICATION_INCOMPLETE; no routing)")

        # 2E-6 — parallel same-target transitions converge safely
        store.put_tenant(_cas_tenant("t_conv", TenantLifecycleState.READY))
        store_a2 = _cas_store(admin_dsn)
        opened.append(store_a2)
        reg_a = TenantRegistry(store_a2, ControlPlaneAudit(store_a2))
        store_b2 = _cas_store(admin_dsn)
        opened.append(store_b2)
        rec_conv = store_b2.get_tenant("t_conv")
        store_b2.compare_and_swap_tenant(
            replace(rec_conv, lifecycle_state=TenantLifecycleState.SUSPENDED, updated_at=now_iso()), expected_version=0
        )
        conv: dict = {}

        def _suspender() -> None:
            try:
                conv["result"] = reg_a.suspend_tenant("t_conv", actor="op-2e", correlation_id="c-2e-conv-a")
            except ControlStoreConcurrencyError:
                conv["result"] = "typed-conflict"
            except Exception as exc:
                conv["result"] = f"raw:{type(exc).__name__}"

        s_thread = threading.Thread(target=_suspender)
        s_thread.start()
        deadline = time.time() + 30
        blocked = False
        while time.time() < deadline:
            n = conn.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND wait_event_type = 'Lock'"
            ).fetchone()[0]
            if n and n >= 1:
                blocked = True
                break
            time.sleep(0.05)
        assert blocked, "the racing suspend never LOCK-blocked — overlap not established"
        store_b2.append_audit(
            ControlAuditRecord(
                actor="op-2e",
                tenant_id="t_conv",
                action="SuspendTenant",
                from_state="Ready",
                to_state="Suspended",
                timestamp=now_iso(),
                correlation_id="c-2e-conv-b",
            )
        )
        s_thread.join(timeout=30)
        assert not s_thread.is_alive()
        assert conv.get("result") == "typed-conflict", f"the losing same-target writer must surface the typed error: {conv}"
        noop = reg_a.suspend_tenant("t_conv", actor="op-2e", correlation_id="c-2e-conv-a2")  # re-read -> A1 no-op
        assert noop.lifecycle_state is TenantLifecycleState.SUSPENDED and noop.version == 1
        conv_row = conn.execute("SELECT lifecycle_state, version FROM control_tenants WHERE tenant_id='t_conv'").fetchone()
        assert conv_row == ("Suspended", 1), f"parallel same-target transitions must converge: {conv_row}"
        n_susp = conn.execute("SELECT count(*) FROM control_audit WHERE tenant_id='t_conv' AND action='SuspendTenant'").fetchone()[0]
        assert n_susp == 1, f"exactly ONE SuspendTenant audit row after convergence: {n_susp}"
        print("PASS: 2E-6 parallel same-target transitions converge (one winner, typed loser, A1 re-issue no-op)")

        # 2E-7 — A1 no-op durable proof: no update, version/updated_at unchanged, no audit row
        before = conn.execute("SELECT lifecycle_state, version, updated_at FROM control_tenants WHERE tenant_id='t_conv'").fetchone()
        audits_before = conn.execute("SELECT count(*) FROM control_audit WHERE tenant_id='t_conv'").fetchone()[0]
        again = reg_a.suspend_tenant("t_conv", actor="op-2e", correlation_id="c-2e-noop")
        assert again.version == 1
        after = conn.execute("SELECT lifecycle_state, version, updated_at FROM control_tenants WHERE tenant_id='t_conv'").fetchone()
        assert after == before, f"the A1 no-op must leave the durable row byte-unchanged: {after} != {before}"
        assert conn.execute("SELECT count(*) FROM control_audit WHERE tenant_id='t_conv'").fetchone()[0] == audits_before, (
            "the A1 no-op must write no durable audit row"
        )
        print("PASS: 2E-7 A1 same-target no-op durable proof (row + version + updated_at + audit all unchanged)")

        # 2E-8 — B2 READY-only durable proof: non-READY suspends refuse and change nothing
        store.put_tenant(_cas_tenant("t_reg", TenantLifecycleState.REGISTERED))
        store.put_tenant(_cas_tenant("t_prov", TenantLifecycleState.PROVISIONING))
        for tid in ("t_reg", "t_prov"):
            row_before = conn.execute("SELECT lifecycle_state, version FROM control_tenants WHERE tenant_id=%s", (tid,)).fetchone()
            refused = False
            try:
                reg_a.suspend_tenant(tid, actor="op-2e", correlation_id=f"c-2e-b2-{tid}")
            except RegistryError:
                refused = True
            assert refused, f"{tid}: non-READY suspend must refuse (B2)"
            row_after = conn.execute("SELECT lifecycle_state, version FROM control_tenants WHERE tenant_id=%s", (tid,)).fetchone()
            assert row_after == row_before, f"{tid}: a refused suspend must change nothing: {row_after}"
        print("PASS: 2E-8 B2 READY-only durable proof (READY->SUSPENDED proven in 2E-6; non-READY refused, rows unchanged)")

        print("ALL 2E CAS LIFECYCLE CHECKS PASSED")
    finally:
        for s in opened:
            try:
                if s._conn_cache is not None:
                    s._conn_cache.close()
            except Exception:
                pass
        with conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {_CAS_SCHEMA} CASCADE")
        conn.close()


# --- PRD 07D-3a — Tier-1 two-INSTANCE CAS convergence (multi-instance readiness, LP-1) -----------
# Folded into this ALREADY-ENROLLED harness (D-3-3/D-3-4: no workflow edit, run-set stays 13).
# 2E-5/2E-6 raced a raw store CAS against the wired services on ONE plane's stores; this proof
# frames the same durable boundary as TWO INDEPENDENT PostgresControlStore INSTANCES (one
# connection each — the separate-process/multi-instance shape of D-3-5 Tier-1): both instances
# read the same pre-image, race the same tenant transition with a deterministic lock-block
# overlap, and exactly one durable CAS survives; the losing INSTANCE gets the typed refusal,
# leaves NO orphan audit, never routes over the winner, and recovers a fresh consistent view
# on its own connection. Tier-2 (concurrent requests SHARING one instance) remains OPEN
# (AT-PMV46-4 / PRD 07D-3b) and is fenced statically, not proven here.
_MI_SCHEMA = "sp2_3a_tier1_scratch"


def _mi_store(admin_dsn: str, *, autocommit: bool = False) -> PostgresControlStore:
    """A store whose session search_path is the 07D-3a Tier-1 scratch schema ONLY."""
    s = PostgresControlStore(admin_dsn)
    if autocommit:
        s._conn.autocommit = True
    with s._conn.cursor() as cur:
        cur.execute(f"SET search_path TO {_MI_SCHEMA}")
    if not autocommit:
        s._conn.commit()
    return s


def _mi_tenant(tid: str, state: TenantLifecycleState) -> TenantRecord:
    return TenantRecord(
        tenant_id=tid,
        organization_ref="org-3a",
        lifecycle_state=state,
        expected_schema_version="1",
        database_association_ref=SecretRef(f"tenant/{tid}/dsn", "1"),
        federation_config_ref="fed-3a",
        created_at=now_iso(),
        updated_at=now_iso(),
    )


def test_3a_tier1_two_instance_cas_convergence(admin_dsn: str) -> None:
    boot = _mi_store(admin_dsn, autocommit=True)
    conn = boot._conn
    with conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {_MI_SCHEMA} CASCADE")
        cur.execute(f"CREATE SCHEMA {_MI_SCHEMA}")
        cur.execute(f"SET search_path TO {_MI_SCHEMA}")
    opened: list = []
    try:
        for ddl in (_DDL_002, _DDL_003, _DDL_004, _DDL_009):
            with conn.cursor() as cur:
                cur.execute(ddl.read_text(encoding="utf-8"))

        # Two INDEPENDENT store instances — one Control-DB connection each (the multi-instance shape).
        store_x = _mi_store(admin_dsn)
        opened.append(store_x)
        store_y = _mi_store(admin_dsn)
        opened.append(store_y)
        assert store_x._conn is not store_y._conn, "the two instances must hold separate connections"

        # 3A-1 — non-vacuity pre-image: BOTH instances read the same record at version 0.
        store_x.put_tenant(_mi_tenant("t_mi", TenantLifecycleState.READY))
        rx = store_x.get_tenant("t_mi")
        ry = store_y.get_tenant("t_mi")
        assert rx is not None and ry is not None and rx.version == 0 and ry.version == 0, (
            f"both instances must observe the same pre-image (x={rx}, y={ry})"
        )
        print("PASS: 3A-1 two independent instances share the same durable pre-image (version 0)")

        # 3A-2 — the race: X's suspend CAS held UNCOMMITTED (row lock; window open); Y's CAS,
        # off the SAME pre-image version, lock-blocks (observed via pg_stat_activity), then X
        # commits atomically with its audit and Y must surface the typed refusal.
        store_x.compare_and_swap_tenant(
            replace(rx, lifecycle_state=TenantLifecycleState.SUSPENDED, updated_at=now_iso()), expected_version=0
        )
        outcome: dict = {}

        def _loser() -> None:
            try:
                store_y.compare_and_swap_tenant(
                    replace(ry, lifecycle_state=TenantLifecycleState.SUSPENDED, updated_at=now_iso()),
                    expected_version=0,
                )
                outcome["result"] = "won"  # must be unreachable
            except ControlStoreConcurrencyError:
                outcome["result"] = "typed-conflict"
            except Exception as exc:
                outcome["result"] = f"raw:{type(exc).__name__}"

        loser_thread = threading.Thread(target=_loser)
        loser_thread.start()
        deadline = time.time() + 30
        blocked = False
        while time.time() < deadline:
            n = conn.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND wait_event_type = 'Lock'"
            ).fetchone()[0]
            if n and n >= 1:
                blocked = True
                break
            time.sleep(0.05)
        assert blocked, "instance Y never LOCK-blocked on X's uncommitted CAS — overlap not established"
        print("PASS: 3A-2a overlap established (instance Y LOCK-blocked on instance X's uncommitted CAS)")
        store_x.append_audit(  # X commits: CAS + audit durable in ONE transaction
            ControlAuditRecord(
                actor="op-3a-x",
                tenant_id="t_mi",
                action="SuspendTenant",
                from_state="Ready",
                to_state="Suspended",
                timestamp=now_iso(),
                correlation_id="c-3a-x",
            )
        )
        loser_thread.join(timeout=30)
        assert not loser_thread.is_alive(), "the losing instance must finish after the winner commits"
        assert outcome.get("result") == "typed-conflict", f"the losing instance must surface ControlStoreConcurrencyError: {outcome}"
        print("PASS: 3A-2 exactly one CAS wins across instances (loser typed-refused)")

        # 3A-3 — exactly ONE durable transition; the loser left NO orphan audit; no routing
        # was enabled over the winner.
        row = conn.execute("SELECT lifecycle_state, version FROM control_tenants WHERE tenant_id='t_mi'").fetchone()
        assert row == ("Suspended", 1), f"the winner's single transition must be the durable state: {row}"
        acts = conn.execute("SELECT action, correlation_id FROM control_audit WHERE tenant_id='t_mi'").fetchall()
        assert acts == [("SuspendTenant", "c-3a-x")], f"exactly the winner's ONE audit row may exist (loser rolled back, no orphan): {acts}"
        assert events.ROUTING_ENABLED not in [a for a, _ in acts], "routing must NEVER be enabled over the winner"
        print("PASS: 3A-3 one durable transition + winner's single audit row (no orphan; no routing)")

        # 3A-4 — the losing INSTANCE recovers: its typed refusal rolled its transaction back,
        # and a fresh read on ITS OWN connection observes the winner's committed state.
        fresh = store_y.get_tenant("t_mi")
        assert fresh is not None and fresh.lifecycle_state is TenantLifecycleState.SUSPENDED and fresh.version == 1, (
            f"the losing instance must observe the winner on re-read: {fresh}"
        )
        print("PASS: 3A-4 losing instance recovers a fresh consistent view on its own connection")

        # 3A-5 — non-vacuity control: with a FRESH (correct) expected version the second
        # instance's CAS succeeds and commits with its audit — the refusal above was the
        # version predicate at work, not a broken instance.
        store_y.put_tenant(_mi_tenant("t_mi2", TenantLifecycleState.READY))
        r2 = store_y.get_tenant("t_mi2")
        assert r2 is not None and r2.version == 0
        store_y.compare_and_swap_tenant(
            replace(r2, lifecycle_state=TenantLifecycleState.SUSPENDED, updated_at=now_iso()), expected_version=0
        )
        store_y.append_audit(
            ControlAuditRecord(
                actor="op-3a-y",
                tenant_id="t_mi2",
                action="SuspendTenant",
                from_state="Ready",
                to_state="Suspended",
                timestamp=now_iso(),
                correlation_id="c-3a-y",
            )
        )
        row2 = conn.execute("SELECT lifecycle_state, version FROM control_tenants WHERE tenant_id='t_mi2'").fetchone()
        assert row2 == ("Suspended", 1), f"a correct-version CAS from the second instance must succeed: {row2}"
        print("PASS: 3A-5 non-vacuity control (fresh-version CAS from the second instance succeeds)")

        print("ALL 3A TIER-1 TWO-INSTANCE CHECKS PASSED")
    finally:
        for s in opened:
            try:
                if s._conn_cache is not None:
                    s._conn_cache.close()
            except Exception:
                pass
        with conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {_MI_SCHEMA} CASCADE")
        conn.close()


if __name__ == "__main__":
    _pg.run([test_b7b_live_pg_runtime_wiring, test_2e_cas_lifecycle_live, test_3a_tier1_two_instance_cas_convergence])
