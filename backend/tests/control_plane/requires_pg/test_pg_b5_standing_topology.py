"""PRD B5-4 — standing-topology operator harness, live on PostgreSQL (standalone-only; SNACKPORTAL_TEST_DSN).

Proves the B5-4 operator tool (``b5_standing_topology.py``, same directory) against DISPOSABLE scratch
resources: a scratch Control DB (``sp2_b54_ctl``), the two deterministic B5-4 tenants, a tmp secret
dir, and explicit sentinels — everything created here is dropped/removed in ``finally``. The operator
tool itself establishes the STANDING fixture only when explicitly run (see the runbook
``infrastructure/runbooks/b5_standing_topology.md``); this test never does.

CHECKS (PRD B5-4 §11.1 + the §11.3 mutation legs):
  B54-1  plan is read-only: exit 0, no database created, no control table created, sanitized output.
  B54-2  status BEFORE apply fails closed (control DDL omitted -> non-zero).           [mutation 1]
  B54-3  a repo-contained SNACKPORTAL_TENANT_SECRET_DIR is REFUSED by plan AND apply
         (non-zero; zero mutation).                                                    [mutation 7]
  B54-4  apply: exit 0; control DDL 001-009 applied TWICE inside one apply (re-apply
         proven safe [mutation 2]); both tenants reach Ready through the REAL path
         (gate-written Verifying->Ready audit row — never a direct Ready [mutation 3]);
         two distinct physical DBs; complete schema + System-Primary singleton; secret
         files materialized with the exact tenant DSN content.
  B54-5  second apply is a no-op (exit 0; DATABASE_PROVISION_REQUESTED counts unchanged;
         singleton intact).
  B54-6  status passes ONLY for the complete topology (exit 0), and fails for each induced
         gap, restored between legs: missing database (rename away/back), missing secret
         file, mismatched secret version (@1 -> @2), both refs resolving to ONE database
         [mutation 4/5], and a non-Ready tenant (supported suspend; feeds teardown).
  B54-7  teardown without the explicit flag is REFUSED (non-zero; rows/DBs/files intact). [mutation 9]
  B54-8  teardown --confirm-b5-teardown: rows reconciled to Decommissioned via SUPPORTED
         transitions and RETAINED; exactly the two B5-4 databases dropped; exactly the two
         secret files removed; the sentinel database, sentinel registry row, and sentinel
         secret file ALL SURVIVE.                                                      [mutation 8]
  B54-9  teardown rerun is idempotent (exit 0, no-ops).
  B54-10 post-teardown apply fails closed (Decommissioned is terminal; no DB recreated) —
         the documented full-fixture-reset consequence.
  B54-11 secret hygiene: NO raw DSN/password appears in ANY captured command output.    [mutation 6]
  (mutation 10 — DDL from import/runtime — is pinned structurally by
   tests/architecture/test_b5_standing_topology_boundaries.py and behaviorally by B54-1/B54-2.)

DRIVER CONTAINMENT. No static database-driver import: psycopg is located via importlib after the DSN
check; provider classes are imported lazily inside the live path only.

DEFAULT SUITE. IGNORED by the default run (pyproject addopts --ignore=tests/control_plane/requires_pg).
Run it by setting SNACKPORTAL_TEST_DSN to a NON-PRODUCTION admin DSN (CREATE/DROP DATABASE + CREATE/DROP
ROLE) and invoking:
  python backend/tests/control_plane/requires_pg/test_pg_b5_standing_topology.py
With SNACKPORTAL_TEST_DSN unset (or psycopg absent) it clean-skips (exit 0). NOT enrolled in the
advisory live-PG workflow loop this slice (MANUAL_ONLY exception — enrollment is a .github edit,
out of B5-4 scope; tracked follow-up).

SAFETY. If any B5-4-named database already exists on the target cluster (a REAL standing fixture),
this test REFUSES to run rather than dropping anything it does not own.

SECRET HYGIENE (D-14). SNACKPORTAL_TEST_DSN is used by NAME only; its value (and every DSN derived
from it) is never printed or persisted; the tmp secret dir is removed in ``finally``. B5-BLK-4
remains OPEN; the Physical Multi-Database MVP remains mandatory and is NOT completed by this test.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import os
import pathlib
import shutil
import sys
import tempfile
from typing import Any, List, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402  (standalone live-PG runner: SNACKPORTAL_TEST_DSN, available()/run()/swap_db)
import b5_standing_topology as b5ops  # noqa: E402  (the operator module under test; import is inert)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

_CTL_DB = "sp2_b54_ctl"  # scratch Control DB (dropped in finally)
_SENTINEL_DB = "sp2_tenant_b54_sentinel"  # unrelated database INSIDE the tenant namespace (must survive teardown)
_SENTINEL_TENANT = "b5_sentinel_reg"  # unrelated registry row (must survive teardown)
_CLUSTER_ROLES = ("sp2_provisioner", "lineage_writer", "lineage_reader")  # created by the tenant 003 templates
_ALPHA, _BETA = b5ops.TENANT_IDS


def _psycopg() -> Any:
    return importlib.import_module("psycopg")


def _one(cur: Any, sql: str, params: Tuple[Any, ...] = ()) -> Any:
    cur.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else None


def _db_exists(psycopg: Any, admin_dsn: str, name: str) -> bool:
    conn = psycopg.connect(admin_dsn)
    try:
        with conn.cursor() as cur:
            return _one(cur, "SELECT 1 FROM pg_database WHERE datname = %s", (name,)) is not None
    finally:
        conn.close()


def _drop_db(psycopg: Any, admin_dsn: str, name: str) -> None:
    """Best-effort scratch-database drop (autocommit; DROP DATABASE cannot run in a transaction)."""
    try:
        conn = psycopg.connect(admin_dsn, autocommit=True)
        try:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}"')
        finally:
            conn.close()
    except Exception:
        pass


def _drop_role(psycopg: Any, admin_dsn: str, name: str) -> None:
    try:
        conn = psycopg.connect(admin_dsn, autocommit=True)
        try:
            conn.execute(f'DROP ROLE IF EXISTS "{name}"')
        finally:
            conn.close()
    except Exception:
        pass


def _admin_exec(psycopg: Any, admin_dsn: str, sql: str) -> None:
    conn = psycopg.connect(admin_dsn, autocommit=True)
    try:
        conn.execute(sql)
    finally:
        conn.close()


def _ctl_query(psycopg: Any, admin_dsn: str, sql: str, params: Tuple[Any, ...] = ()) -> Any:
    conn = psycopg.connect(_pg.swap_db(admin_dsn, _CTL_DB))
    try:
        with conn.cursor() as cur:
            return _one(cur, sql, params)
    finally:
        conn.close()


def test_b5_standing_topology_ops(admin_dsn: str) -> None:
    psycopg = _psycopg()
    from control_plane import main as cp_main
    from control_plane.adapters.providers.env_tenant_dsn_secret_store import EnvTenantDsnSecretStore
    from control_plane.onboarding import tenant_dsn_ref
    from control_plane.provisioning import tenant_database_name
    from shared.adapters.providers.env_reference_secret_store import EnvReferenceSecretStore

    targets = {tid: tenant_database_name(tid) for tid in b5ops.TENANT_IDS}

    # SAFETY pre-flight: refuse to run over anything B5-4-shaped that already exists (never drop
    # a database this test did not create — a REAL standing fixture may live on this cluster).
    for name in (*targets.values(), _SENTINEL_DB, _CTL_DB):
        assert not _db_exists(psycopg, admin_dsn, name), (
            f"database {name!r} already exists on this cluster — refusing to run the disposable proof over it "
            "(tear down / point SNACKPORTAL_TEST_DSN at a disposable cluster first)"
        )

    ctl_secret_key = EnvReferenceSecretStore._env_key(cp_main.DEFAULT_CONTROL_STORE_DSN_REF, "1")
    admin_secret_key = EnvReferenceSecretStore._env_key(cp_main.PROVISIONING_ADMIN_DSN_REF, "1")
    tenant_env_keys = [EnvTenantDsnSecretStore._env_key(tenant_dsn_ref(t), "1") for t in (*b5ops.TENANT_IDS, _SENTINEL_TENANT)]
    env_keys = [
        cp_main.CONTROL_STORE_ENV,
        cp_main.PROVISIONING_ADAPTER_ENV,
        cp_main.TENANT_SCHEMA_APPLICATOR_ENV,
        cp_main.DISTINCTNESS_LEDGER_ENV,
        cp_main.CONTROL_STORE_DSN_REF_ENV,
        ctl_secret_key,
        admin_secret_key,
        "SNACKPORTAL_TENANT_SECRET_DIR",
        *tenant_env_keys,
    ]
    saved_env = {k: os.environ.get(k) for k in env_keys}
    secret_dir = tempfile.mkdtemp(prefix="sp2_b54_secrets_")
    open_planes: List[Any] = []
    all_output: List[str] = []

    def run_ops(argv: List[str]) -> Tuple[int, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = b5ops.main(argv)
        out = buf.getvalue()
        all_output.append(out)
        return code, out

    try:
        # --- environment: scratch control DB + reference-resolved secrets (values never printed) --
        _admin_exec(psycopg, admin_dsn, f'CREATE DATABASE "{_CTL_DB}"')
        os.environ.pop(cp_main.CONTROL_STORE_DSN_REF_ENV, None)  # default control-store ref
        os.environ[ctl_secret_key] = _pg.swap_db(admin_dsn, _CTL_DB)
        os.environ[admin_secret_key] = admin_dsn
        os.environ["SNACKPORTAL_TENANT_SECRET_DIR"] = secret_dir
        for key in tenant_env_keys:
            os.environ.pop(key, None)  # the standing convention here is the FILE form only

        # --- B54-1: plan is read-only ---------------------------------------------------------------
        code, out = run_ops(["plan"])
        assert code == 0, f"plan must succeed on a valid config (got {code}):\n{out}"
        assert "PLAN OK" in out
        for tid, target in targets.items():
            assert tid in out and target in out, "plan must name the deterministic ids/targets"
            assert not _db_exists(psycopg, admin_dsn, target), "plan must create NO database"
        assert _ctl_query(psycopg, admin_dsn, "SELECT to_regclass('control_tenants')") is None, "plan must apply NO control DDL"

        # --- B54-2: status before apply fails closed (control DDL omitted) -------------------------
        code, out = run_ops(["status"])
        assert code != 0, "status must fail closed while the control DDL is absent"
        assert "FAIL" in out and "control" in out.lower()
        assert _ctl_query(psycopg, admin_dsn, "SELECT to_regclass('control_tenants')") is None, "status must apply NO control DDL"

        # --- B54-3: repo-contained secret dir is refused (plan AND apply; zero mutation) -----------
        repo_inside = str(pathlib.Path(b5ops._REPO_ROOT) / "infrastructure")
        os.environ["SNACKPORTAL_TENANT_SECRET_DIR"] = repo_inside
        for argv in (["plan"], ["apply"]):
            code, out = run_ops(argv)
            assert code != 0, f"{argv[0]} must refuse a repo-contained secret dir"
            assert "refused" in out.lower() or "ERROR" in out
        for target in targets.values():
            assert not _db_exists(psycopg, admin_dsn, target), "the refusal must be pre-effect (no database)"
        os.environ["SNACKPORTAL_TENANT_SECRET_DIR"] = secret_dir

        # --- B54-4: apply establishes the full topology through the REAL path ----------------------
        code, out = run_ops(["apply"])
        assert code == 0, f"apply must succeed (got {code}):\n{out}"
        assert "pass 2" in out, "apply must prove the second (idempotent) control-DDL pass"
        for tid, target in targets.items():
            assert _db_exists(psycopg, admin_dsn, target), f"physical DB {target} must exist"
            state = _ctl_query(psycopg, admin_dsn, "SELECT lifecycle_state FROM control_tenants WHERE tenant_id = %s", (tid,))
            assert state == "Ready", f"{tid} must be Ready (got {state!r})"
            ref = _ctl_query(psycopg, admin_dsn, "SELECT assoc_store_ref FROM control_tenants WHERE tenant_id = %s", (tid,))
            assert ref == tenant_dsn_ref(tid), f"{tid} must carry the canonical reference (got {ref!r})"
            version = _ctl_query(psycopg, admin_dsn, "SELECT assoc_version FROM control_tenants WHERE tenant_id = %s", (tid,))
            assert version == "1", f"{tid} association version must be '1' (got {version!r})"
            # Ready ONLY through the gate (never a direct write): exactly one Verifying->Ready row.
            gate_ready = _ctl_query(
                psycopg,
                admin_dsn,
                "SELECT count(*) FROM control_audit WHERE tenant_id = %s AND from_state = 'Verifying' AND to_state = 'Ready'",
                (tid,),
            )
            assert gate_ready == 1, f"{tid}: Ready must be gate-written exactly once (got {gate_ready})"
            tconn = psycopg.connect(_pg.swap_db(admin_dsn, target))
            try:
                with tconn.cursor() as cur:
                    for table in ("agents", "ai_agents", "startups", "investors", "deals", "lineage", "schema_version"):
                        assert _one(cur, "SELECT to_regclass(%s)", (table,)) is not None, f"{target}: {table} must exist"
                    assert _one(cur, "SELECT count(*) FROM agents WHERE agent_kind = 'system_primary'") == 1
                    assert _one(cur, "SELECT count(*) FROM agents") == 1, "System Primary must be the only agents row"
            finally:
                tconn.close()
            secret_path = pathlib.Path(secret_dir) / f"{tenant_dsn_ref(tid)}@1"
            assert secret_path.is_file(), f"secret file must exist: {secret_path}"
            assert secret_path.read_text(encoding="utf-8").strip() == _pg.swap_db(admin_dsn, target)
        assert targets[_ALPHA] != targets[_BETA], "the two tenant databases must be distinct"

        # --- B54-5: second apply is a converged no-op ----------------------------------------------
        def provision_requests(tid: str) -> Any:
            return _ctl_query(
                psycopg,
                admin_dsn,
                "SELECT count(*) FROM control_audit WHERE tenant_id = %s AND action = 'DatabaseProvisionRequested'",
                (tid,),
            )

        before = {tid: provision_requests(tid) for tid in b5ops.TENANT_IDS}
        code, out = run_ops(["apply"])
        assert code == 0, f"re-apply must succeed (got {code}):\n{out}"
        for tid in b5ops.TENANT_IDS:
            assert provision_requests(tid) == before[tid], f"{tid}: a Ready tenant's re-apply must not re-provision"

        # --- B54-6: status passes complete; fails per induced gap (restored between legs) ----------
        code, out = run_ops(["status"])
        assert code == 0, f"status must pass on the complete topology (got {code}):\n{out}"
        assert "STATUS OK" in out

        # (a) missing database — rename away and back (schema preserved).
        _admin_exec(psycopg, admin_dsn, f'ALTER DATABASE "{targets[_ALPHA]}" RENAME TO "sp2_b54_hidden"')
        try:
            code, out = run_ops(["status"])
            assert code != 0 and "missing" in out.lower(), "status must fail for a missing physical database"
        finally:
            _admin_exec(psycopg, admin_dsn, f'ALTER DATABASE "sp2_b54_hidden" RENAME TO "{targets[_ALPHA]}"')
        code, _ = run_ops(["status"])
        assert code == 0, "status must recover once the database is back"

        # (b) missing secret file.
        alpha_secret = pathlib.Path(secret_dir) / f"{tenant_dsn_ref(_ALPHA)}@1"
        os.replace(alpha_secret, alpha_secret.parent / "dsn@1.bak")
        try:
            code, out = run_ops(["status"])
            assert code != 0 and "secret" in out.lower(), "status must fail for a missing secret file"
        finally:
            os.replace(alpha_secret.parent / "dsn@1.bak", alpha_secret)

        # (c) mismatched secret version (@1 replaced by @2 — the expected canonical version is absent).
        os.replace(alpha_secret, alpha_secret.parent / "dsn@2")
        try:
            code, out = run_ops(["status"])
            assert code != 0, "status must fail when only a non-canonical secret version exists"
        finally:
            os.replace(alpha_secret.parent / "dsn@2", alpha_secret)

        # (d) both refs resolving to ONE database (beta's file re-pointed at alpha's DSN).
        beta_secret = pathlib.Path(secret_dir) / f"{tenant_dsn_ref(_BETA)}@1"
        beta_original = beta_secret.read_text(encoding="utf-8")
        beta_secret.write_text(_pg.swap_db(admin_dsn, targets[_ALPHA]) + "\n", encoding="utf-8")
        try:
            code, out = run_ops(["status"])
            assert code != 0 and ("own" in out.lower() or "one database" in out.lower()), (
                "status must fail when both secrets resolve to one database"
            )
        finally:
            beta_secret.write_text(beta_original, encoding="utf-8")
        code, _ = run_ops(["status"])
        assert code == 0, "status must recover once beta's secret is restored"

        # --- B54-7: teardown without the explicit confirmation flag is refused ---------------------
        code, out = run_ops(["teardown"])
        assert code != 0 and "REFUSED" in out, "teardown must refuse without --confirm-b5-teardown"
        for tid, target in targets.items():
            assert _db_exists(psycopg, admin_dsn, target), "the refusal must be pre-effect (databases intact)"
            state = _ctl_query(psycopg, admin_dsn, "SELECT lifecycle_state FROM control_tenants WHERE tenant_id = %s", (tid,))
            assert state == "Ready", "the refusal must be pre-effect (rows intact)"

        # --- sentinels: an unrelated database, registry row, and secret file must survive ----------
        _admin_exec(psycopg, admin_dsn, f'CREATE DATABASE "{_SENTINEL_DB}"')
        plane = None
        try:
            for name in (
                cp_main.CONTROL_STORE_ENV,
                cp_main.PROVISIONING_ADAPTER_ENV,
                cp_main.TENANT_SCHEMA_APPLICATOR_ENV,
                cp_main.DISTINCTNESS_LEDGER_ENV,
            ):
                os.environ[name] = "postgres"
            plane = cp_main.create_app()
            open_planes.append(plane)
            from shared.secrets import SecretRef

            plane.registry.register_tenant(
                tenant_id=_SENTINEL_TENANT,
                organization_ref="b5_sentinel_org",
                expected_schema_version="1",
                database_association_ref=SecretRef(store_ref=tenant_dsn_ref(_SENTINEL_TENANT), version="1"),
                federation_config_ref="b5_sentinel_fed",
                actor="b5_sentinel_ops",
                correlation_id="b5-sentinel-reg",
            )
            # --- non-Ready leg (supported suspend) — deliberately NOT restored: it feeds the
            # teardown Suspended path below (beta still covers the Ready path).
            plane.registry.suspend_tenant(_ALPHA, actor="b5_test_ops", correlation_id="b5-suspend-alpha")
        finally:
            if plane is not None:
                try:
                    if plane.store._conn_cache is not None:
                        plane.store._conn_cache.close()
                except Exception:
                    pass
        sentinel_secret = pathlib.Path(secret_dir) / f"{tenant_dsn_ref(_SENTINEL_TENANT)}@1"
        sentinel_secret.parent.mkdir(parents=True, exist_ok=True)
        sentinel_secret.write_text("postgresql://placeholder.invalid/never_used\n", encoding="utf-8")

        code, out = run_ops(["status"])
        assert code != 0 and "not ready" in out.lower(), "status must fail for a non-Ready (Suspended) tenant"

        # --- B54-8: confirmed teardown — bounded, supported semantics, sentinels survive -----------
        code, out = run_ops(["teardown", "--confirm-b5-teardown"])
        assert code == 0, f"confirmed teardown must succeed (got {code}):\n{out}"
        for tid, target in targets.items():
            state = _ctl_query(psycopg, admin_dsn, "SELECT lifecycle_state FROM control_tenants WHERE tenant_id = %s", (tid,))
            assert state == "Decommissioned", f"{tid} must be reconciled to Decommissioned and RETAINED (got {state!r})"
            assert not _db_exists(psycopg, admin_dsn, target), f"{target} must be dropped"
            assert not (pathlib.Path(secret_dir) / f"{tenant_dsn_ref(tid)}@1").is_file(), f"{tid} secret file must be removed"
        assert _db_exists(psycopg, admin_dsn, _SENTINEL_DB), "the unrelated sentinel DATABASE must survive teardown"
        sentinel_state = _ctl_query(
            psycopg, admin_dsn, "SELECT lifecycle_state FROM control_tenants WHERE tenant_id = %s", (_SENTINEL_TENANT,)
        )
        assert sentinel_state == "Registered", "the unrelated sentinel REGISTRY ROW must survive teardown"
        assert sentinel_secret.is_file(), "the unrelated sentinel SECRET FILE must survive teardown"

        # --- B54-9: teardown rerun is idempotent ----------------------------------------------------
        code, out = run_ops(["teardown", "--confirm-b5-teardown"])
        assert code == 0, f"teardown rerun must be a clean no-op (got {code}):\n{out}"

        # --- B54-10: post-teardown apply fails closed (Decommissioned is terminal) -----------------
        code, out = run_ops(["apply"])
        assert code != 0, "apply after teardown must fail closed (Decommissioned is terminal)"
        assert "decommissioned" in out.lower() and "full-fixture reset" in out.lower()
        for target in targets.values():
            assert not _db_exists(psycopg, admin_dsn, target), "the terminal refusal must create NO database"

        # --- B54-11: secret hygiene across ALL captured output -------------------------------------
        joined = "\n".join(all_output)
        from urllib.parse import urlsplit

        secrets_never_printed = [admin_dsn, _pg.swap_db(admin_dsn, _CTL_DB)]
        secrets_never_printed += [_pg.swap_db(admin_dsn, t) for t in targets.values()]
        for secret in secrets_never_printed:
            assert secret not in joined, "no DSN value may appear in any command output (D-14)"
        password = urlsplit(admin_dsn).password
        if password:
            assert password not in joined, "no password may appear in any command output (D-14)"
        print("PASS-DETAIL: B54-1..B54-11 all held (plan/apply/status/teardown lifecycle proven on disposable resources)")
    finally:
        for target in targets.values():
            _drop_db(psycopg, admin_dsn, target)
        _drop_db(psycopg, admin_dsn, "sp2_b54_hidden")
        _drop_db(psycopg, admin_dsn, _SENTINEL_DB)
        _drop_db(psycopg, admin_dsn, _CTL_DB)
        for role in _CLUSTER_ROLES:
            _drop_role(psycopg, admin_dsn, role)
        shutil.rmtree(secret_dir, ignore_errors=True)
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


if __name__ == "__main__":
    _pg.run([test_b5_standing_topology_ops])
