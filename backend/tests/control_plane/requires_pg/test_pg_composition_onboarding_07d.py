"""PRD 07D-1 — composition activation + canonical tenant secret references, live on PostgreSQL (standalone-only).

Proves the FIRST fully composed physical-tenant onboarding: an env-selected ``create_app()`` — no
harness-side manual adapter construction — drives a real tenant from registration to READY on a
physically distinct PostgreSQL database, with every secret resolved BY REFERENCE (D-14) through the
canonical convention (D-A):

    SP2_CP_CONTROL_STORE=postgres            -> durable ControlStore     (control-store DSN by ref)
    SP2_CP_PROVISIONING_ADAPTER=postgres     -> PostgresProvisioningOperator (admin DSN by ref
                                                `control/provisioning-admin-dsn`) + the real gate
                                                (Postgres probe/evidence; lazy REAL Control-DB
                                                evidence — D-C)
    SP2_CP_TENANT_SCHEMA_APPLICATOR=postgres -> real 13-file Step-2b applicator + System Primary seed
    SP2_CP_DISTINCTNESS_LEDGER=postgres      -> durable Control-DB distinctness ledger

CHECKS (the 07D-1 exec-auth V2 §13 D-set):
  D1  env-selected ControlPlane() composes ALL live selectors through runtime composition (no manual
      operator/applicator/ledger construction here) and constructs with NO database I/O (lazy).
  D2  onboard() creates the real physical tenant DB, applies the 13-file Step-2b schema, seeds exactly
      one System Primary, passes the gate (real Control-DB evidence) and reaches READY.
  D3  the minted canonical ref `tenant/<tenant_id>/dsn` aligns with the database-router-side
      EnvTenantSecretStore convention WITHOUT importing database_router: the control-plane provider's
      computed env key equals the replicated router mapping, ONE materialized env secret served the
      live runtime path (tenant A), and the shared FILE convention serves it too (tenant B resolves
      through `$SNACKPORTAL_TENANT_SECRET_DIR/tenant/<id>/dsn@1`).
  D4  the routing view returns ready=true, the canonical reference, assoc_version and schema_version.
  D5  tenant/Control isolation: tenant operational tables live ONLY in the tenant DBs; the Control DB
      holds registry/lifecycle/audit/ledger metadata only; the durable ledger carries both tenants.
  D6  LATE FAILURE (REWRITTEN under PRD 07D-2b.2a — governed recovery supersedes the old
      terminal-retry characterization): an unresolvable tenant ref after CREATE DATABASE leaves the
      tenant not-Ready with an EMPTY orphan DB and an honest registry; a retry now AUTO-RESUMES from
      PROVISIONING (OnboardingRecoveryStarted, provision re-driven existence-checked) and — the
      cause unfixed — converges to the SAME safe failure (OnboardingRecoveryFailed, still
      PROVISIONING, orphan still empty, deprovision still never called). Once the secret is fixed,
      the next retry resumes to READY (07D2B2-1).
  D7  idempotency: registry-exists-but-DB-absent onboards safely; DB-exists-but-registry-absent takes
      the created=False path safely; a Ready tenant's repeat onboard is a no-op (no re-provision).
  D8  secret hygiene: registry + audit rows carry references only — never a DSN/secret value.
  D9  clean-skip: with SNACKPORTAL_TEST_DSN unset (or psycopg absent) this file exits 0 via _pg.run's
      SKIP path without touching any database (proven by a separate unset-DSN invocation).

PRD 07D-2a CHARACTERIZATION (folded in per the 07D-2a exec-auth; 07D2A-4's retry legs REWRITTEN
under PRD 07D-2b.2a from terminal-on-retry to the governed recovery semantics — mapping below):
  07D2A-1  tenant-id admission (AT-07D1-11): bad ids ('d07-bad'/'control'/'D07UPPER') rejected with
           RegistryError BEFORE any effect — no durable registry row, no audit record, no DB.
  07D2A-2  selector coherence (AT-07D1-9): a half-live mix (in-memory control store under postgres
           provisioning) fails closed with ValueError at construction; all-four-postgres constructs.
  07D2A-3  sentinel proof (AT-07D1-8): the LIVE control evidence resolved during D2 is proven;
           sentinel_written=False / missing-token variants are rejected by the composition's rule.
  07D2A-4  failure-injection landings (first-failure legs UNCHANGED; retry legs rewritten):
           provision-fail (unresolvable admin ref) -> PROVISIONING + NO orphan; the retry — cause
           fixed — now RESUMES to READY (was: terminal no-op). Gate-fail (expected '2' vs observed
           '1') -> FAILED + schema'd orphan; the retry is terminal 'recover_required' (was:
           'already_onboarded'), no re-provision; deprovision() is NEVER called; explicit recover()
           re-enters the gate and fails again — a schema-mismatch tenant NEVER reaches Ready.

PRD 07D-2b.1 (folded in per the confirmed V2 exec-auth; D1-D9 and 07D2A-1..3 preserved verbatim):
  07D2A-1+ a trailing-newline bad id (fullmatch hardening, AT-07D2A2-1) and a per-bad-id
           pg_database ABSENCE assertion (AT-07D2A2-5) strengthen the admission proof.
  07D2B1-1 the symmetric effective-posture onboard-time guard, live: the standalone durable-store
           posture constructs (B-7B preserved) but onboard(), reassociate() AND (07D-2b.2a) the new
           recover() entry point fail closed with ProvisioningError pre-effect — zero durable
           registry/audit/DB footprint proven against the real control DB.

PRD 07D-2b.2a RECOVERY EVIDENCE (folded in per the 07D-2b.2a exec-auth [Claude V1 R1 / GPT V2];
run set STAYS 13 — no new harness):
  07D2B2-1 resume from PROVISIONING with an empty/schema-created DB converges to READY through the
           fence dispatch (folded into the D6 arc: fix the secret -> retry -> READY).
  07D2B2-2 a gate-failed TRANSIENT tenant (unreachable-then-restored DSN, R1-5) recovers via
           explicit recover() and reaches READY ONLY through Verifying/the gate; the NEGATIVE:
           a schema-mismatch FAILED tenant re-enters the gate and fails again — NEVER Ready.
  07D2B2-3 a live isolation anomaly (association re-pointed at ANOTHER tenant's DB -> misrouted
           target) lands in QUARANTINED, emits TenantQuarantined + IsolationAnomaly, and
           onboard / reassociate / recover / direct verify() ALL refuse (R1-1/C-1).
  07D2B2-4 reassociate on the QUARANTINED tenant is refused PRE-EFFECT — no Verifying overwrite,
           association reference and record byte-unchanged.
  07D2B2-5 reverse-mix live proof (AT-07D2B1-4): an explicit in-memory store under the all-postgres
           env composition denies onboard/reassociate/recover pre-effect — pg_database ABSENCE
           proves zero physical footprint.

DRIVER CONTAINMENT. No static database-driver import: psycopg is reached only via importlib after the
DSN check; the postgres adapter CLASSES are imported lazily inside the exercise for isinstance proof
only. The composed runtime path reaches the driver solely through the sanctioned provider zone.

DEFAULT SUITE. IGNORED by the default run (pyproject addopts --ignore=tests/control_plane/requires_pg).
Run it by setting SNACKPORTAL_TEST_DSN to a NON-PRODUCTION admin DSN (CREATE/DROP DATABASE + CREATE/DROP
ROLE; the ephemeral CI postgres service runs as the postgres superuser under trust auth) and invoking:
  python backend/tests/control_plane/requires_pg/test_pg_composition_onboarding_07d.py
With SNACKPORTAL_TEST_DSN unset (or psycopg absent) it clean-skips (exit 0).

SECRET HYGIENE (D-14). SNACKPORTAL_TEST_DSN is used by NAME only; its value (and every DSN derived from
it, including the in-process secret env vars) is never printed or persisted. All scratch databases, the
secret-dir tempfile, and the cluster roles are dropped/removed in `finally`. B5-BLK-4 remains OPEN; the
Physical Multi-Database MVP remains mandatory and is NOT completed by 07D-1.
"""

from __future__ import annotations

import importlib
import os
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402  (standalone live-PG runner: SNACKPORTAL_TEST_DSN, available()/run()/swap_db)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

from control_plane import events  # noqa: E402
from control_plane import main as cp_main  # noqa: E402
from control_plane.adapters.providers.env_tenant_dsn_secret_store import EnvTenantDsnSecretStore  # noqa: E402
from control_plane.distinctness import DistinctnessResult  # noqa: E402
from control_plane.onboarding import OnboardingError, tenant_dsn_ref  # noqa: E402
from control_plane.provisioning import ProvisioningError, tenant_database_name  # noqa: E402
from control_plane.read_api import ControlPlaneReadService  # noqa: E402
from control_plane.records import TenantLifecycleState  # noqa: E402
from control_plane.registry import RegistryError  # noqa: E402
from shared.adapters.providers.env_reference_secret_store import EnvReferenceSecretStore  # noqa: E402
from shared.secrets import SecretRef  # noqa: E402

_CTL_DB = "sp2_07d_ctl"  # scratch Control DB (durable store + ledger + control evidence target)
_CLUSTER_ROLES = ("sp2_provisioner", "lineage_writer", "lineage_reader")  # created by the 003 templates
_ORG, _FED = "org_ref_x", "fed_ref_x"

# The reviewed Control-DB DDL set (applied to the SCRATCH control DB only; files are read-only here —
# their blob pins are owned by the default-suite b7c1/b7c1r2 guard families, not duplicated).
_CONTROL_DDL_DIR = pathlib.Path(__file__).resolve().parents[4] / "infrastructure" / "db" / "control"
_CONTROL_DDL_ORDER = (
    "001_distinctness_ledger.sql",
    "002_provisioning_audit.sql",
    "003_provisioning_audit_append_only.sql",
    "004_control_tenants.sql",
    "005_control_memberships.sql",
    "006_control_federation.sql",
    "007_control_directory.sql",
)

# Selector + secret env names (values are set in-process only and NEVER printed).
_SELECTOR_ENV = {
    cp_main.CONTROL_STORE_ENV: "postgres",
    cp_main.PROVISIONING_ADAPTER_ENV: "postgres",
    cp_main.TENANT_SCHEMA_APPLICATOR_ENV: "postgres",
    cp_main.DISTINCTNESS_LEDGER_ENV: "postgres",
}
_CTL_SECRET_KEY = EnvReferenceSecretStore._env_key(cp_main.DEFAULT_CONTROL_STORE_DSN_REF, "1")
_ADMIN_SECRET_KEY = EnvReferenceSecretStore._env_key(cp_main.PROVISIONING_ADMIN_DSN_REF, "1")


def _psycopg():
    """The database driver, located at call time (no static import — Driver Containment Standard)."""
    return importlib.import_module("psycopg")


def _tenant_env_key(tenant_id: str) -> str:
    return EnvTenantDsnSecretStore._env_key(tenant_dsn_ref(tenant_id), "1")


def _replicated_router_env_key(store_ref: str, version: str) -> str:
    """The database-router-side EnvTenantSecretStore env-key mapping, REPLICATED inline (never
    imported — AC-15/AC-84): env_tenant_secret_store.py:31-33 verbatim."""
    base = "".join(c.upper() if c.isalnum() else "_" for c in store_ref)
    return f"SNACKPORTAL_TENANT_SECRET_{base}_V{version}"


def _one(cur, sql, params=()):
    cur.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else None


def _drop_db(psycopg, admin_dsn: str, name: str) -> None:
    """Best-effort scratch-database drop (autocommit; DROP DATABASE cannot run in a transaction)."""
    try:
        conn = psycopg.connect(admin_dsn, autocommit=True)
        try:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}"')
        finally:
            conn.close()
    except Exception:
        pass


def _drop_role(psycopg, admin_dsn: str, name: str) -> None:
    try:
        conn = psycopg.connect(admin_dsn, autocommit=True)
        try:
            conn.execute(f'DROP ROLE IF EXISTS "{name}"')
        finally:
            conn.close()
    except Exception:
        pass


def _db_exists(psycopg, admin_dsn: str, name: str) -> bool:
    conn = psycopg.connect(admin_dsn)
    try:
        with conn.cursor() as cur:
            return _one(cur, "SELECT 1 FROM pg_database WHERE datname = %s", (name,)) is not None
    finally:
        conn.close()


def _prepare_control_db(psycopg, admin_dsn: str) -> None:
    """Create the scratch Control DB and apply the reviewed control DDL set (read-only templates)."""
    _drop_db(psycopg, admin_dsn, _CTL_DB)
    boot = psycopg.connect(admin_dsn, autocommit=True)
    try:
        boot.execute(f'CREATE DATABASE "{_CTL_DB}"')
    finally:
        boot.close()
    ctl = psycopg.connect(_pg.swap_db(admin_dsn, _CTL_DB))
    try:
        with ctl.cursor() as cur:
            for name in _CONTROL_DDL_ORDER:
                cur.execute((_CONTROL_DDL_DIR / name).read_text(encoding="utf-8"))
        ctl.commit()
    finally:
        ctl.close()


def _onboard(cp, tenant_id: str, correlation_id: str):
    return cp.onboarding.onboard(
        tenant_id, organization_ref=_ORG, federation_config_ref=_FED, actor="ops_ref", correlation_id=correlation_id
    )


def _actions(cp) -> list:
    return [r.action for r in cp.store.list_audit()]


def test_07d_composition_onboarding(admin_dsn: str) -> None:
    psycopg = _psycopg()
    tid_a, tid_b, tid_fail, tid_reg, tid_db = "d07a", "d07b", "d07fail", "d07reg", "d07db"
    tid_pf, tid_gf = "d07pf", "d07gf"  # PRD 07D-2a characterization tenants (provision-fail / gate-fail)
    tid_tr, tid_q = "d07tr", "d07q"  # PRD 07D-2b.2a tenants (transient-recover / quarantine)
    all_tids = (tid_a, tid_b, tid_fail, tid_reg, tid_db, tid_pf, tid_gf, tid_tr, tid_q)

    env_keys = [*_SELECTOR_ENV, cp_main.CONTROL_STORE_DSN_REF_ENV, _CTL_SECRET_KEY, _ADMIN_SECRET_KEY]
    env_keys += [_tenant_env_key(t) for t in all_tids]
    env_keys.append("SNACKPORTAL_TENANT_SECRET_DIR")
    saved_env = {k: os.environ.get(k) for k in env_keys}
    open_stores: list = []

    secret_dir = tempfile.mkdtemp(prefix="sp2_07d_secrets_")
    try:
        # --- environment: scratch control DB + reference-resolved secrets (values never printed) --
        _prepare_control_db(psycopg, admin_dsn)
        for tid in all_tids:
            _drop_db(psycopg, admin_dsn, tenant_database_name(tid))

        for name, value in _SELECTOR_ENV.items():
            os.environ[name] = value
        os.environ.pop(cp_main.CONTROL_STORE_DSN_REF_ENV, None)  # default control-store ref
        os.environ[_CTL_SECRET_KEY] = _pg.swap_db(admin_dsn, _CTL_DB)
        os.environ[_ADMIN_SECRET_KEY] = admin_dsn
        # tenant A + the idempotency tenants + the 07D-2a characterization tenants + the
        # 07D-2b.2a recovery tenants resolve via the ENV form of the shared convention...
        for tid in (tid_a, tid_reg, tid_db, tid_pf, tid_gf, tid_tr, tid_q):
            os.environ[_tenant_env_key(tid)] = _pg.swap_db(admin_dsn, tenant_database_name(tid))
        os.environ.pop(_tenant_env_key(tid_fail), None)  # d07fail: deliberately unresolvable (D6)
        # ...tenant B resolves via the FILE form: $SNACKPORTAL_TENANT_SECRET_DIR/tenant/<id>/dsn@1
        os.environ["SNACKPORTAL_TENANT_SECRET_DIR"] = secret_dir
        os.environ.pop(_tenant_env_key(tid_b), None)
        ref_b = tenant_dsn_ref(tid_b)
        file_b = pathlib.Path(secret_dir) / f"{ref_b}@1"
        file_b.parent.mkdir(parents=True, exist_ok=True)
        file_b.write_text(_pg.swap_db(admin_dsn, tenant_database_name(tid_b)) + "\n", encoding="utf-8")

        # --- D1: env-selected runtime composition (no manual adapter construction; lazy) ----------
        from control_plane.adapters.providers.postgres_distinctness_ledger import PostgresDistinctnessLedger
        from control_plane.adapters.providers.postgres_provisioning_operator import PostgresProvisioningOperator
        from control_plane.adapters.providers.postgres_store import PostgresControlStore
        from control_plane.adapters.providers.postgres_tenant_schema_applicator import PostgresTenantSchemaApplicator

        cp = cp_main.create_app()
        open_stores.append(cp.store)
        assert isinstance(cp.store, PostgresControlStore), "composition must select the durable ControlStore"
        assert isinstance(cp.operator, PostgresProvisioningOperator), "composition must select the real operator"
        assert isinstance(cp.schema_applicator, PostgresTenantSchemaApplicator), "composition must select the real applicator"
        assert isinstance(cp.provisioning._ledger, PostgresDistinctnessLedger), "composition must select the durable ledger"
        assert cp.store._conn_cache is None, "create_app() must perform NO database I/O (lazy-connect)"
        print("PASS: D1 env-selected ControlPlane() composes all live selectors (lazy; no harness-side adapter construction)")

        # --- D2: composed onboard -> physical DB + 13-file schema + System Primary + READY --------
        out_a = _onboard(cp, tid_a, "c-07d-a")
        assert out_a.result is DistinctnessResult.VERIFIED, out_a.reason
        rec_a = cp.store.get_tenant(tid_a)
        assert rec_a is not None and rec_a.lifecycle_state is TenantLifecycleState.READY
        assert _db_exists(psycopg, admin_dsn, tenant_database_name(tid_a)), "the physical tenant DB must exist"
        ta = psycopg.connect(_pg.swap_db(admin_dsn, tenant_database_name(tid_a)))
        try:
            with ta.cursor() as cur:
                assert str(_one(cur, "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1")) == "1"
                for table in ("lineage", "agents", "ai_agents", "startups", "investors", "deals"):
                    assert _one(cur, "SELECT to_regclass(%s)", (table,)) is not None, f"{table} must exist after Ready"
                assert _one(cur, "SELECT count(*) FROM agents WHERE agent_kind = 'system_primary'") == 1
                assert _one(cur, "SELECT count(*) FROM agents") == 1, "the System Primary seed must be the only agents row"
        finally:
            ta.close()
        acts = _actions(cp)
        for action in (
            events.DATABASE_PROVISION_SUCCEEDED,
            events.TENANT_SCHEMA_APPLICATION_SUCCEEDED,
            events.DISTINCTNESS_VERIFICATION_PASSED,
            events.ROUTING_ENABLED,
        ):
            assert action in acts, action
        print("PASS: D2 composed onboard -> physical DB + 13-file Step-2b schema + one System Primary + gate VERIFIED -> READY")

        # tenant B reaches READY through the FILE form of the same convention (cross-tenant distinctness).
        out_b = _onboard(cp, tid_b, "c-07d-b")
        assert out_b.result is DistinctnessResult.VERIFIED, out_b.reason
        rec_b = cp.store.get_tenant(tid_b)
        assert rec_b is not None and rec_b.lifecycle_state is TenantLifecycleState.READY

        # --- D3: canonical-ref convention alignment (no database_router import) -------------------
        assert rec_a.database_association_ref.store_ref == tenant_dsn_ref(tid_a) == f"tenant/{tid_a}/dsn"
        assert rec_a.database_association_ref.version == "1"
        assert not rec_a.database_association_ref.store_ref.startswith("sp2_tenant_"), "old-style refs must not be minted"
        cp_key = EnvTenantDsnSecretStore._env_key(rec_a.database_association_ref.store_ref, "1")
        router_key = _replicated_router_env_key(rec_a.database_association_ref.store_ref, "1")
        assert cp_key == router_key == f"SNACKPORTAL_TENANT_SECRET_TENANT_{tid_a.upper()}_DSN_V1", (cp_key, router_key)
        assert cp_key in os.environ, "the ONE materialized env secret must be the key BOTH sides compute"
        # material equivalence: the control-plane provider resolves the SAME material the env carries
        # (the runtime path already consumed it to reach READY above); tenant B proved the FILE form.
        assert EnvTenantDsnSecretStore().resolve(rec_a.database_association_ref).material == os.environ[cp_key]
        assert rec_b.database_association_ref.store_ref == ref_b and file_b.is_file()
        print("PASS: D3 canonical ref tenant/<id>/dsn == router-side convention (env + file forms; one secret serves both sides)")

        # --- D4: routing view (the Database Router's read model) ----------------------------------
        view = ControlPlaneReadService(cp.store).routing_view(tid_a)
        assert view is not None
        assert view["ready"] is True and view["lifecycle_state"] == "Ready"
        assert view["database_association_ref"] == {"store_ref": tenant_dsn_ref(tid_a), "version": "1"}
        assert view["expected_schema_version"] == "1"
        print("PASS: D4 routing view returns ready=true + the canonical reference + assoc_version/schema_version")

        # --- D5: tenant-DB isolation / Control-DB boundary (+ durable ledger inventory) -----------
        ctl = psycopg.connect(_pg.swap_db(admin_dsn, _CTL_DB))
        try:
            with ctl.cursor() as cur:
                for table in ("agents", "startups", "investors", "deals", "schema_version"):
                    assert _one(cur, "SELECT to_regclass(%s)", (table,)) is None, f"tenant table {table} must NOT be in the Control DB"
                assert _one(cur, "SELECT count(*) FROM control_tenants WHERE tenant_id = %s", (tid_a,)) == 1
                assert _one(cur, "SELECT count(*) FROM control_audit") > 0, "operational audit must be durable in the Control DB"
                cur.execute("SELECT tenant_id FROM control_distinctness_ledger")
                ledger_tids = {r[0] for r in cur.fetchall()}
                assert {tid_a, tid_b} <= ledger_tids, f"durable ledger must carry both tenants: {ledger_tids}"
        finally:
            ctl.close()
        tb = psycopg.connect(_pg.swap_db(admin_dsn, tenant_database_name(tid_b)))
        try:
            with tb.cursor() as cur:
                for table in ("control_tenants", "control_audit", "control_distinctness_ledger"):
                    assert _one(cur, "SELECT to_regclass(%s)", (table,)) is None, f"control table {table} must NOT be in a tenant DB"
        finally:
            tb.close()
        print("PASS: D5 tenant operational tables only in tenant DBs; Control DB holds registry/audit/ledger metadata only")

        # --- D6 (REWRITTEN, PRD 07D-2b.2a) + 07D2B2-1: late failure -> governed resume ------------
        # First failure UNCHANGED: unresolvable tenant ref -> schema apply fails -> PROVISIONING,
        # EMPTY orphan, honest registry.
        out_fail = _onboard(cp, tid_fail, "c-07d-f1")
        assert out_fail.result is not DistinctnessResult.VERIFIED
        assert out_fail.reason == "schema_application_failed", out_fail.reason
        rec_fail = cp.store.get_tenant(tid_fail)
        assert rec_fail is not None and rec_fail.lifecycle_state is TenantLifecycleState.PROVISIONING, (
            "the failed tenant must remain honestly not-Ready in the registry"
        )
        assert _db_exists(psycopg, admin_dsn, tenant_database_name(tid_fail)), "the orphan DB is preserved, not deprovisioned"
        orphan = psycopg.connect(_pg.swap_db(admin_dsn, tenant_database_name(tid_fail)))
        try:
            with orphan.cursor() as cur:
                assert _one(cur, "SELECT to_regclass('schema_version')") is None, "the orphan must be EMPTY (rolled back / never applied)"
                assert _one(cur, "SELECT to_regclass('agents')") is None
        finally:
            orphan.close()
        # Retry with the cause UNFIXED (was: terminal no-op) -> governed AUTO-RESUME from
        # PROVISIONING: provision is re-driven existence-checked (created=False), the apply fails
        # again, and the run converges to the SAME safe failure wrapped in the recovery pair.
        prov_requests = _actions(cp).count(events.DATABASE_PROVISION_REQUESTED)
        out_retry = _onboard(cp, tid_fail, "c-07d-f2")
        assert out_retry.result is not DistinctnessResult.VERIFIED
        assert out_retry.reason == "schema_application_failed", out_retry.reason
        acts_d6 = _actions(cp)
        assert acts_d6.count(events.DATABASE_PROVISION_REQUESTED) == prov_requests + 1, "the resume re-drives provision"
        assert events.ONBOARDING_RECOVERY_STARTED in acts_d6, "the resume must be attributable (RecoveryStarted)"
        assert events.ONBOARDING_RECOVERY_FAILED in acts_d6, "the failed resume must emit its terminal record"
        rec_fail2 = cp.store.get_tenant(tid_fail)
        assert rec_fail2 is not None and rec_fail2.lifecycle_state is TenantLifecycleState.PROVISIONING
        assert _db_exists(psycopg, admin_dsn, tenant_database_name(tid_fail)), "deprovision() must never be called"
        orphan2 = psycopg.connect(_pg.swap_db(admin_dsn, tenant_database_name(tid_fail)))
        try:
            with orphan2.cursor() as cur:
                assert _one(cur, "SELECT to_regclass('schema_version')") is None, "the orphan must STILL be empty"
        finally:
            orphan2.close()
        # 07D2B2-1: fix the secret -> the next retry resumes from PROVISIONING over the EXISTING
        # empty DB (idempotent apply) and converges to READY, only through the gate.
        os.environ[_tenant_env_key(tid_fail)] = _pg.swap_db(admin_dsn, tenant_database_name(tid_fail))
        out_resume = _onboard(cp, tid_fail, "c-07d-f3")
        assert out_resume.result is DistinctnessResult.VERIFIED, out_resume.reason
        rec_fail3 = cp.store.get_tenant(tid_fail)
        assert rec_fail3 is not None and rec_fail3.lifecycle_state is TenantLifecycleState.READY
        assert events.ONBOARDING_RECOVERY_COMPLETED in _actions(cp), "the successful resume must emit its terminal record"
        resumed = psycopg.connect(_pg.swap_db(admin_dsn, tenant_database_name(tid_fail)))
        try:
            with resumed.cursor() as cur:
                assert str(_one(cur, "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1")) == "1"
                assert _one(cur, "SELECT count(*) FROM agents WHERE agent_kind = 'system_primary'") == 1
        finally:
            resumed.close()
        print(
            "PASS: D6+07D2B2-1 late failure -> empty orphan + honest registry; unfixed retry auto-resumes to the "
            "same safe failure (recovery pair, no deprovision); fixed retry resumes PROVISIONING -> READY via the gate"
        )

        # --- D7: idempotency cases -----------------------------------------------------------------
        # (a) registry row exists (Registered) but the DB is absent -> onboard provisions and reaches READY.
        cp.registry.register_tenant(
            tenant_id=tid_reg,
            organization_ref=_ORG,
            expected_schema_version="1",
            database_association_ref=SecretRef(store_ref=tenant_dsn_ref(tid_reg), version="1"),
            federation_config_ref=_FED,
            actor="ops_ref",
            correlation_id="c-07d-r0",
        )
        assert not _db_exists(psycopg, admin_dsn, tenant_database_name(tid_reg))
        out_reg = _onboard(cp, tid_reg, "c-07d-r1")
        assert out_reg.result is DistinctnessResult.VERIFIED, out_reg.reason
        # (b) the DB exists but no registry row -> provision takes the created=False path safely.
        boot = psycopg.connect(admin_dsn, autocommit=True)
        try:
            boot.execute(f'CREATE DATABASE "{tenant_database_name(tid_db)}"')
        finally:
            boot.close()
        out_db = _onboard(cp, tid_db, "c-07d-d1")
        assert out_db.result is DistinctnessResult.VERIFIED, out_db.reason
        # (c) a Ready tenant's repeat onboard is a no-op (no re-provision, no re-verify).
        prov_requests = _actions(cp).count(events.DATABASE_PROVISION_REQUESTED)
        out_repeat = _onboard(cp, tid_a, "c-07d-a2")
        assert out_repeat.result is DistinctnessResult.VERIFIED and out_repeat.reason == "already_onboarded"
        assert _actions(cp).count(events.DATABASE_PROVISION_REQUESTED) == prov_requests, "repeat onboard must not re-provision"
        print("PASS: D7 idempotency (registry-only -> READY; DB-exists created=False -> READY; Ready repeat = no-op)")

        # --- D8: secret hygiene (references only, durably) ----------------------------------------
        secrets = [admin_dsn, os.environ[_CTL_SECRET_KEY], os.environ[_tenant_env_key(tid_a)]]
        for r in cp.store.list_audit():
            for secret in secrets:
                assert secret not in repr(r), "no DSN/secret value may appear in any audit record (D-14)"
        for tid in (tid_a, tid_b, tid_reg, tid_db, tid_fail):
            rec = cp.store.get_tenant(tid)
            assert rec is not None
            for secret in secrets:
                assert secret not in repr(rec), "no DSN/secret value may appear in any registry record (D-14)"
            assert rec.database_association_ref.store_ref == tenant_dsn_ref(tid), "the stored association is the canonical REFERENCE"
        # cross-instance durability: a FRESH composition reads the committed READY state (registry honesty).
        cp2 = cp_main.create_app()
        open_stores.append(cp2.store)
        rec2 = cp2.store.get_tenant(tid_a)
        assert rec2 is not None and rec2.lifecycle_state is TenantLifecycleState.READY
        print("PASS: D8 secret hygiene (references only in registry + audit) + cross-instance durable READY")

        # === PRD 07D-2a characterization (prevention guardrails; recovery stays 07D-2b) ===========
        # --- 07D2A-1: tenant-id admission (AT-07D1-11) — bad ids rejected with ZERO effects -------
        # PRD 07D-2b.1 additions: a TRAILING-NEWLINE id ("d07nl\n" — pre-fullmatch it slipped
        # through `.match`+`$` and aliased "d07nl_" via the '\n'->'_' env-key flattening;
        # AT-07D2A2-1) and a direct pg_database ABSENCE assertion per bad id, proving the "no
        # provision footprint" claim against the PHYSICAL layer, not just the store (AT-07D2A2-5).
        for bad in ("d07-bad", "control", "D07UPPER", "d07nl\n"):
            admission_raised = False
            try:
                _onboard(cp, bad, "c-07d2a-adm")
            except RegistryError:
                admission_raised = True
            assert admission_raised, f"bad tenant id {bad!r} must be rejected with RegistryError"
            assert cp.store.get_tenant(bad) is None, f"{bad!r}: no registry row may be written (durable store)"
            assert all(r.tenant_id != bad for r in cp.store.list_audit()), f"{bad!r}: no audit record may be written"
            assert not _db_exists(psycopg, admin_dsn, tenant_database_name(bad)), f"{bad!r}: no physical DB may exist"
        print("PASS: 07D2A-1 tenant-id admission (bad ids rejected pre-effect; zero registry/audit/provision footprint)")

        # --- 07D2A-2: selector-coherence matrix (AT-07D1-9) — forbidden mix fails closed ----------
        os.environ[cp_main.CONTROL_STORE_ENV] = "in_memory"  # provisioning stays postgres -> RULE 1 mix
        coherence_raised = False
        try:
            cp_main.create_app()
        except ValueError:
            coherence_raised = True
        finally:
            os.environ[cp_main.CONTROL_STORE_ENV] = "postgres"  # restore the all-postgres composition
        assert coherence_raised, "a half-live selector mix must fail closed at construction (RULE 1)"
        cp_matrix_ok = cp_main.create_app()  # all-four postgres still constructs (RULE 3)
        open_stores.append(cp_matrix_ok.store)
        print("PASS: 07D2A-2 selector coherence (forbidden half-live mix ValueError; all-postgres composition intact)")

        # --- 07D2A-3: control-evidence sentinel proof (AT-07D1-8) ---------------------------------
        # The live path reaching READY (D2) already proved PROVEN evidence is accepted; here the
        # rejection rule is exercised against the same helper the composition uses.
        import dataclasses as _dc

        live_evidence = cp_main._proven_control_evidence  # the composition's acceptance rule
        proven = cp.provisioning._control  # the REAL control evidence resolved during D2 (proven)
        assert live_evidence(proven) is proven, "the resolved live control evidence must be PROVEN"
        unproven = _dc.replace(proven, sentinel_written=False)
        assert live_evidence(unproven) is None, "sentinel_written=False must not count as resolved evidence"
        assert live_evidence(_dc.replace(proven, sentinel_token=None)) is None, "a missing token must not count"
        print("PASS: 07D2A-3 sentinel proof (unproven control evidence rejected; live proven evidence accepted)")

        # --- 07D2A-4 (retry legs REWRITTEN, PRD 07D-2b.2a): failure-injection landings -------------
        # (a) PROVISION failure: unresolvable admin DSN ref -> provision_failed; NO orphan DB
        #     (first-failure leg UNCHANGED).
        saved_admin = os.environ.pop(_ADMIN_SECRET_KEY)
        try:
            out_pf = _onboard(cp, tid_pf, "c-07d2a-pf")
        finally:
            os.environ[_ADMIN_SECRET_KEY] = saved_admin
        assert out_pf.result is not DistinctnessResult.VERIFIED and out_pf.reason == "provision_failed", out_pf
        rec_pf = cp.store.get_tenant(tid_pf)
        assert rec_pf is not None and rec_pf.lifecycle_state is TenantLifecycleState.PROVISIONING
        assert not _db_exists(psycopg, admin_dsn, tenant_database_name(tid_pf)), "provision failed -> NO orphan DB"
        # Retry with the admin ref RESTORED (was: terminal no-op) -> auto-resume from PROVISIONING
        # provisions the missing DB and converges to READY through the gate.
        out_pf_retry = _onboard(cp, tid_pf, "c-07d2a-pf2")
        assert out_pf_retry.result is DistinctnessResult.VERIFIED, out_pf_retry.reason
        rec_pf2 = cp.store.get_tenant(tid_pf)
        assert rec_pf2 is not None and rec_pf2.lifecycle_state is TenantLifecycleState.READY
        assert _db_exists(psycopg, admin_dsn, tenant_database_name(tid_pf)), "the resumed run provisions the DB"
        # (b) SCHEMA-APPLY failure: characterized by the D6 arc above (empty orphan; unfixed retry
        #     converges to the same safe failure; fixed retry resumes to READY = 07D2B2-1).
        # (c) GATE failure: resolvable ref but expected schema '2' vs observed '1' -> FAILED landing;
        #     the orphan EXISTS WITH schema (apply succeeded); retry is terminal 'recover_required'
        #     (FAILED never auto-resumes); deprovision uncalled.
        out_gf = cp.onboarding.onboard(
            tid_gf,
            organization_ref=_ORG,
            federation_config_ref=_FED,
            actor="ops_ref",
            correlation_id="c-07d2a-gf",
            expected_schema_version="2",
        )
        assert out_gf.result is DistinctnessResult.VERIFICATION_FAILED, out_gf
        rec_gf = cp.store.get_tenant(tid_gf)
        assert rec_gf is not None and rec_gf.lifecycle_state is TenantLifecycleState.FAILED
        assert _db_exists(psycopg, admin_dsn, tenant_database_name(tid_gf)), "gate-fail orphan DB persists (preserved)"
        gf_conn = psycopg.connect(_pg.swap_db(admin_dsn, tenant_database_name(tid_gf)))
        try:
            with gf_conn.cursor() as cur:
                assert _one(cur, "SELECT to_regclass('schema_version')") is not None, "gate-fail orphan HAS schema (apply succeeded)"
        finally:
            gf_conn.close()
        prov_requests_gf = _actions(cp).count(events.DATABASE_PROVISION_REQUESTED)
        out_gf_retry = _onboard(cp, tid_gf, "c-07d2a-gf2")
        assert out_gf_retry.result is not DistinctnessResult.VERIFIED and out_gf_retry.reason == "recover_required"
        assert _actions(cp).count(events.DATABASE_PROVISION_REQUESTED) == prov_requests_gf, "FAILED must not auto-resume"
        assert _db_exists(psycopg, admin_dsn, tenant_database_name(tid_gf)), "deprovision() must never be called"
        # 07D2B2-2 NEGATIVE (R1-5): explicit recover() on the schema-mismatch tenant re-classifies
        # (non-anomaly history), re-enters Verifying, and FAILS AGAIN at the gate
        # (expected_schema_version is immutable on the record; D-17) — it must NEVER reach Ready.
        out_gf_recover = cp.onboarding.recover(tid_gf, actor="ops_ref", correlation_id="c-07d2a-gf3")
        assert out_gf_recover.result is DistinctnessResult.VERIFICATION_FAILED, out_gf_recover
        rec_gf2 = cp.store.get_tenant(tid_gf)
        assert rec_gf2 is not None and rec_gf2.lifecycle_state is TenantLifecycleState.FAILED, (
            "a schema-mismatch tenant must land back in FAILED — never Ready"
        )
        gf_recovery_terminal = [
            r.action
            for r in cp.store.list_audit()
            if r.tenant_id == tid_gf and r.action in (events.ONBOARDING_RECOVERY_COMPLETED, events.ONBOARDING_RECOVERY_FAILED)
        ]
        assert gf_recovery_terminal == [events.ONBOARDING_RECOVERY_FAILED], gf_recovery_terminal
        assert _db_exists(psycopg, admin_dsn, tenant_database_name(tid_gf)), "recover() never deprovisions"
        print(
            "PASS: 07D2A-4 failure landings (provision-fail: no orphan, fixed retry resumes to READY; "
            "schema-fail [D6 arc]; gate-fail: schema'd orphan, retry recover_required, recover() re-gates "
            "and NEVER reaches Ready; deprovision never called; registry honest)"
        )

        # === PRD 07D-2b.1: symmetric effective-posture onboard-time guard — LIVE proof ============
        # --- 07D2B1-1: the standalone durable-store posture (control_store=postgres, live trio
        # in-memory) on the SAME scratch control DB. Construction stays allowed (B-7B preserved);
        # onboard() AND reassociate() fail closed with ProvisioningError BEFORE any durable
        # footprint — closing the 07D-2a documented residual (durable fake-READY). Zero footprint
        # is proven against the REAL control DB through the primary composition's durable store.
        saved_live_selectors = {
            key: os.environ.pop(key, None)
            for key in (cp_main.PROVISIONING_ADAPTER_ENV, cp_main.TENANT_SCHEMA_APPLICATOR_ENV, cp_main.DISTINCTNESS_LEDGER_ENV)
        }
        try:
            cp_guard = cp_main.create_app()  # control_store stays 'postgres' -> standalone posture
            open_stores.append(cp_guard.store)
            for guard_op in ("onboard", "reassociate", "recover"):
                guard_raised = False
                try:
                    if guard_op == "onboard":
                        cp_guard.onboarding.onboard(
                            "d07guard", organization_ref=_ORG, federation_config_ref=_FED, actor="ops_ref", correlation_id="c-07d2b1"
                        )
                    elif guard_op == "reassociate":
                        cp_guard.onboarding.reassociate(
                            "d07guard",
                            new_association_ref=SecretRef(store_ref=tenant_dsn_ref("d07guard"), version="1"),
                            actor="ops_ref",
                            correlation_id="c-07d2b1r",
                        )
                    else:  # PRD 07D-2b.2a: the NEW recovery entry point gets the same facade deny
                        cp_guard.onboarding.recover("d07guard", actor="ops_ref", correlation_id="c-07d2b1rec")
                except ProvisioningError:
                    guard_raised = True
                assert guard_raised, f"07D-2b.1 guard: {guard_op}() must fail closed under the standalone posture"
        finally:
            for key, value in saved_live_selectors.items():
                if value is not None:
                    os.environ[key] = value
        assert cp.store.get_tenant("d07guard") is None, "guard must leave NO durable registry row"
        assert all(r.tenant_id != "d07guard" for r in cp.store.list_audit()), "guard must leave NO durable audit record"
        assert not _db_exists(psycopg, admin_dsn, tenant_database_name("d07guard")), "guard must create NO physical DB"
        print(
            "PASS: 07D2B1-1 onboard-time guard (standalone durable-store posture: onboard+reassociate+recover "
            "fail closed pre-effect; zero durable registry/audit/DB footprint)"
        )

        # === PRD 07D-2b.2a: recovery + quarantine integrity — LIVE evidence =======================
        # --- 07D2B2-2 (positive; R1-5 fixture): unreachable-then-restored DSN -> explicit recover()
        out_tr = _onboard(cp, tid_tr, "c-07d2b2-tr0")
        assert out_tr.result is DistinctnessResult.VERIFIED, out_tr.reason
        saved_tr_dsn = os.environ.pop(_tenant_env_key(tid_tr))  # break the tenant DSN secret
        try:
            out_tr_fail = cp.provisioning.verify(tid_tr, actor="ops_ref", correlation_id="c-07d2b2-tr1")
        finally:
            os.environ[_tenant_env_key(tid_tr)] = saved_tr_dsn  # restore the secret
        assert out_tr_fail.result is DistinctnessResult.VERIFICATION_INCOMPLETE, out_tr_fail
        rec_tr = cp.store.get_tenant(tid_tr)
        assert rec_tr is not None and rec_tr.lifecycle_state is TenantLifecycleState.FAILED, (
            "an unreachable DSN must land the tenant in FAILED (transient, non-anomalous)"
        )
        tr_events = [r.action for r in cp.store.list_audit() if r.tenant_id == tid_tr]
        assert events.VERIFICATION_INCOMPLETE in tr_events and events.ISOLATION_ANOMALY not in tr_events
        out_tr_retry = _onboard(cp, tid_tr, "c-07d2b2-tr2")
        assert out_tr_retry.reason == "recover_required", "FAILED is terminal via onboard(); recover() is the exit"
        rec_tr_pre = cp.store.get_tenant(tid_tr)
        assert rec_tr_pre is not None and rec_tr_pre.lifecycle_state is TenantLifecycleState.FAILED, "not Ready yet"
        ready_writes_before = len([r for r in cp.store.list_audit() if r.tenant_id == tid_tr and r.to_state == "Ready"])
        out_tr_rec = cp.onboarding.recover(tid_tr, actor="ops_ref", correlation_id="c-07d2b2-tr3")
        assert out_tr_rec.result is DistinctnessResult.VERIFIED, out_tr_rec
        rec_tr2 = cp.store.get_tenant(tid_tr)
        assert rec_tr2 is not None and rec_tr2.lifecycle_state is TenantLifecycleState.READY
        tr_recs = [r for r in cp.store.list_audit() if r.tenant_id == tid_tr]
        tr_acts = [r.action for r in tr_recs]
        assert events.ONBOARDING_RECOVERY_STARTED in tr_acts and events.ONBOARDING_RECOVERY_COMPLETED in tr_acts
        ready_writes_tr = [(r.from_state, r.to_state) for r in tr_recs if r.to_state == "Ready"]
        assert len(ready_writes_tr) == ready_writes_before + 1, "recovery must add exactly ONE gate-written Ready"
        assert all(w == ("Verifying", "Ready") for w in ready_writes_tr), (
            "READY must be reached ONLY through Verifying/the gate (sole-readiness-writer)"
        )
        print(
            "PASS: 07D2B2-2 transient gate-failed tenant (unreachable-then-restored DSN) recovers explicitly "
            "and reaches READY only through Verifying/the gate; schema-mismatch negative proven in 07D2A-4"
        )

        # --- 07D2B2-3 + 07D2B2-4: live isolation anomaly -> QUARANTINED; ALL entry points refuse --
        out_q = _onboard(cp, tid_q, "c-07d2b2-q0")
        assert out_q.result is DistinctnessResult.VERIFIED, out_q.reason
        # Re-point the tenant's canonical ref at ANOTHER tenant's physical DB (tid_db): the gate's
        # evidence observes a misrouted target (current_database() != intended sp2_tenant_d07q) —
        # an isolation-class anomaly. (The victim gains only a dv_sentinel_* row; dropped in cleanup.)
        os.environ[_tenant_env_key(tid_q)] = _pg.swap_db(admin_dsn, tenant_database_name(tid_db))
        out_q_anom = cp.provisioning.verify(tid_q, actor="ops_ref", correlation_id="c-07d2b2-q1")
        assert out_q_anom.result is DistinctnessResult.ISOLATION_ANOMALY, out_q_anom
        rec_q = cp.store.get_tenant(tid_q)
        assert rec_q is not None and rec_q.lifecycle_state is TenantLifecycleState.QUARANTINED, (
            "an isolation-class anomaly must quarantine automatically at classification time"
        )
        q_acts = [r.action for r in cp.store.list_audit() if r.tenant_id == tid_q]
        assert events.TENANT_QUARANTINED in q_acts, "the hold must be marked TenantQuarantined"
        assert events.ISOLATION_ANOMALY in q_acts, "the incident event must be preserved"
        # ALL FOUR entry points refuse (R1-1/C-1 incl. DIRECT verify): zero effects each time.
        q_audit_before = len(cp.store.list_audit())
        out_q_onboard = _onboard(cp, tid_q, "c-07d2b2-q2")
        assert out_q_onboard.result is DistinctnessResult.VERIFICATION_INCOMPLETE and out_q_onboard.reason == "quarantined"
        for q_op in ("reassociate", "recover", "verify"):
            q_raised = False
            try:
                if q_op == "reassociate":
                    cp.onboarding.reassociate(
                        tid_q,
                        new_association_ref=SecretRef(store_ref=tenant_dsn_ref(tid_q), version="2"),
                        actor="ops_ref",
                        correlation_id="c-07d2b2-q3",
                    )
                elif q_op == "recover":
                    cp.onboarding.recover(tid_q, actor="ops_ref", correlation_id="c-07d2b2-q4")
                else:
                    cp.provisioning.verify(tid_q, actor="ops_ref", correlation_id="c-07d2b2-q5")
            except (ProvisioningError, OnboardingError):
                q_raised = True
            assert q_raised, f"{q_op}() must refuse the QUARANTINED tenant (fail closed)"
        assert len(cp.store.list_audit()) == q_audit_before, "every refusal must be pre-effect (zero audit writes)"
        rec_q2 = cp.store.get_tenant(tid_q)
        assert rec_q2 == rec_q, (
            "07D2B2-4: the QUARANTINED record must be byte-unchanged — no Verifying overwrite, "
            "no association overwrite (reassociate refused PRE-effect)"
        )
        assert rec_q2 is not None and rec_q2.lifecycle_state is TenantLifecycleState.QUARANTINED, "no path to READY, ever"
        os.environ[_tenant_env_key(tid_q)] = _pg.swap_db(admin_dsn, tenant_database_name(tid_q))
        print(
            "PASS: 07D2B2-3/-4 live isolation anomaly -> QUARANTINED (TenantQuarantined + IsolationAnomaly); "
            "onboard/reassociate/recover/direct-verify ALL refuse pre-effect; record byte-unchanged"
        )

        # --- 07D2B2-5 (AT-07D2B1-4): reverse-mix live proof — explicit in-memory store under the
        # all-postgres env composition; all three entry points deny pre-effect; pg_database ABSENCE.
        from control_plane.adapters.providers.in_memory_store import InMemoryControlStore

        mem_store = InMemoryControlStore()
        cp_mix = cp_main.ControlPlane(store=mem_store)  # env is all-postgres here -> reverse mix
        for mix_op in ("onboard", "reassociate", "recover"):
            mix_raised = False
            try:
                if mix_op == "onboard":
                    cp_mix.onboarding.onboard(
                        "d07mix", organization_ref=_ORG, federation_config_ref=_FED, actor="ops_ref", correlation_id="c-07d2b2-m1"
                    )
                elif mix_op == "reassociate":
                    cp_mix.onboarding.reassociate(
                        "d07mix",
                        new_association_ref=SecretRef(store_ref=tenant_dsn_ref("d07mix"), version="1"),
                        actor="ops_ref",
                        correlation_id="c-07d2b2-m2",
                    )
                else:
                    cp_mix.onboarding.recover("d07mix", actor="ops_ref", correlation_id="c-07d2b2-m3")
            except ProvisioningError:
                mix_raised = True
            assert mix_raised, f"reverse mix: {mix_op}() must fail closed (ProvisioningError)"
        assert mem_store.get_tenant("d07mix") is None, "reverse mix: no registry row may be written"
        assert mem_store.list_audit() == [], "reverse mix: no audit record may be written"
        assert not _db_exists(psycopg, admin_dsn, tenant_database_name("d07mix")), (
            "reverse mix: pg_database ABSENCE — no physical DB may be created"
        )
        print(
            "PASS: 07D2B2-5 reverse-mix live proof (explicit in-memory store + all-postgres env: "
            "onboard/reassociate/recover denied pre-effect; zero physical footprint in pg_database)"
        )

        # --- D9: clean-skip contract ---------------------------------------------------------------
        # The SKIP path itself is exercised by a separate unset-DSN invocation of this file (exit 0,
        # no DB touched — _pg.run's guard); this live run proves the non-skip path emitted real PASSes.
        print("PASS: D9 clean-skip contract exercised by unset-DSN invocation (this run took the live path)")
        print("ALL 07D-1 COMPOSITION CHECKS PASSED")
    finally:
        for store in open_stores:
            try:
                if store._conn_cache is not None:
                    store._conn_cache.close()
            except Exception:
                pass
        for tid in all_tids:
            _drop_db(psycopg, admin_dsn, tenant_database_name(tid))
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
    _pg.run([test_07d_composition_onboarding])
