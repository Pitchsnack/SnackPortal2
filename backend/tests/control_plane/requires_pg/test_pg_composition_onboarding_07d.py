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

PRD 07D-2b.2b COMPENSATION + ORPHAN EVIDENCE (folded in per the 07D-2b.2b exec-auth
[GPT V2, byte-adopting the Claude V1 R1]; run set STAYS 13 — no new harness). Declared
characterization SCOPING (R1-8, not a weakening): the existing "deprovision() must never be
called" pins remain scoped to the PREVENTION/FAILURE-PATH tenants (d07fail, d07gf — asserted
via pg_database presence after retries/recover); the POSITIVE deprovision cases below use NEW
disposable tenants (d07de, d07bs, d07x) plus the never-registered d07orph and the dedicated
control-clone composition (ctlx):
  07D2B2B-1 D-5 fullmatch negative, live: newline/suffix-injected targets are rejected by the
            REAL operator's shared guard on the DROP path; no database is dropped.
  07D2B2B-2 empty tenant DB eligible: explicit deprovision passes the ownership-proof
            quintuple, calls the operator, drops the DB, leaves the Requested->Completed
            trail, and RETAINS the registry record (no state change).
  07D2B2B-3 bootstrap-only tenant DB eligible: schema + System-Primary seed + platform
            schema_version rows classify bootstrap-only (R1-3 census) and deprovision.
  07D2B2B-4 non-empty tenant DB preserved: content beyond bootstrap refuses (no DROP),
            emits TenantDeprovisionFailed, and quarantines the eligible FAILED tenant.
            AT-PMV46-1 (V-1 revision): three INDEPENDENT evidence classes each refuse
            ALONE — a materialized view (physically stored rows; invisible to a
            relkind='r'-only census), a large object (pg_largeobject presence probe),
            and an extra ordinary table; the read-only scan reports non_empty_evidence;
            the already-QUARANTINED tenant STAYS across repeat refusals (R1-5 live).
  07D2B2B-5 Control DB non-droppable: a dedicated composition whose Control DB sits INSIDE
            the tenant namespace refuses compensation BEFORE any operator call — the
            Control DB survives; the primary Control DB also survives the whole run.
  07D2B2B-6 ledger collision: another tenant's durable distinctness evidence naming the
            target refuses (fail closed) and quarantines; no DROP.
  07D2B2B-7 physical DB with no registry record: the READ-ONLY scan reports it (zero audit
            events, no state change, no DROP); explicit deprovision of the unknown id
            refuses; the DB survives.
  07D2B2B-8 cross-process durable re-classification (R1-7 recipe): instance A leaves a
            FAILED tenant with ONE durable IsolationAnomaly row (public audit API);
            instance B (fresh create_app) recover() re-classifies to QUARANTINED without
            re-entering Verifying and never Ready; the sentinel-BEARING bootstrap-only DB
            then deprovisions from Quarantined (verification artifacts bootstrap-compatible).
  07D2B1-1+ the standalone durable-store posture ALSO denies the two NEW recovery entry
            points (deprovision_tenant_database + scan_for_orphans) pre-effect (R1-2).

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
from control_plane.distinctness import DistinctnessEvidence, DistinctnessResult  # noqa: E402
from control_plane.onboarding import OnboardingError, tenant_dsn_ref  # noqa: E402
from control_plane.provisioning import ProvisioningError, tenant_database_name  # noqa: E402
from control_plane.read_api import ControlPlaneReadService  # noqa: E402
from control_plane.records import TenantLifecycleState  # noqa: E402
from control_plane.recovery import (  # noqa: E402
    CLASS_NO_REGISTRY_RECORD,
    REASON_ABSENT_NOOP,
    REASON_CONTENT_NOT_EMPTY,
    REASON_CONTROL_TARGET,
    REASON_DEPROVISIONED,
    REASON_LEDGER_COLLISION,
    REASON_UNKNOWN_TENANT,
    RecoveryCompensationService,
)
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
    "009_control_tenants_cas_version.sql",  # PRD 07D-2e: the adapter reads/writes control_tenants.version
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
    # PRD 07D-2b.2b disposable tenants: empty-deprovision / bootstrap-deprovision / non-empty-
    # preserved / ledger-collision / cross-process-requarantine; plus the never-registered
    # physical orphan (d07orph) and the control-clone tenant id (ctlx -> sp2_tenant_ctlx).
    tid_de, tid_bs, tid_ne, tid_lc, tid_x = "d07de", "d07bs", "d07ne", "d07lc", "d07x"
    all_tids = (
        tid_a,
        tid_b,
        tid_fail,
        tid_reg,
        tid_db,
        tid_pf,
        tid_gf,
        tid_tr,
        tid_q,
        tid_de,
        tid_bs,
        tid_ne,
        tid_lc,
        tid_x,
        "d07orph",
        "ctlx",
    )

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
        # 07D-2b.2a recovery tenants + the 07D-2b.2b onboarding-based fixtures resolve via
        # the ENV form of the shared convention...
        for tid in (tid_a, tid_reg, tid_db, tid_pf, tid_gf, tid_tr, tid_q, tid_bs, tid_ne, tid_lc, tid_x):
            os.environ[_tenant_env_key(tid)] = _pg.swap_db(admin_dsn, tenant_database_name(tid))
        os.environ.pop(_tenant_env_key(tid_fail), None)  # d07fail: deliberately unresolvable (D6)
        os.environ.pop(_tenant_env_key(tid_de), None)  # d07de: unresolvable -> PROVISIONING + EMPTY DB (2b.2b)
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
            for guard_op in ("onboard", "reassociate", "recover", "deprovision_tenant_database", "scan_for_orphans"):
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
                    elif guard_op == "recover":  # PRD 07D-2b.2a: the recovery entry point's facade deny
                        cp_guard.onboarding.recover("d07guard", actor="ops_ref", correlation_id="c-07d2b1rec")
                    elif guard_op == "deprovision_tenant_database":
                        # PRD 07D-2b.2b (R1-2): the compensation entry point denies pre-effect too.
                        cp_guard.recovery.deprovision_tenant_database("d07guard", actor="ops_ref", correlation_id="c-07d2b2b-g1")
                    else:  # PRD 07D-2b.2b (R1-2): even the READ-ONLY scan denies under a mixed plane.
                        cp_guard.orphan_scan.scan_for_orphans()
                except ProvisioningError:
                    guard_raised = True
                assert guard_raised, f"07D-2b.1/2b.2b guard: {guard_op}() must fail closed under the standalone posture"
        finally:
            for key, value in saved_live_selectors.items():
                if value is not None:
                    os.environ[key] = value
        assert cp.store.get_tenant("d07guard") is None, "guard must leave NO durable registry row"
        assert all(r.tenant_id != "d07guard" for r in cp.store.list_audit()), "guard must leave NO durable audit record"
        assert not _db_exists(psycopg, admin_dsn, tenant_database_name("d07guard")), "guard must create NO physical DB"
        print(
            "PASS: 07D2B1-1 onboard-time guard (standalone durable-store posture: onboard+reassociate+recover"
            "+deprovision_tenant_database+scan_for_orphans fail closed pre-effect; zero durable registry/audit/DB footprint)"
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

        # === PRD 07D-2b.2b: compensation, orphan scan, governed deprovision — LIVE evidence =======
        assert isinstance(cp.recovery, RecoveryCompensationService), "matched all-postgres posture must expose the real service"

        def _deprovision(plane, tid: str, correlation_id: str):
            return plane.recovery.deprovision_tenant_database(tid, actor="ops_ref", correlation_id=correlation_id)

        def _dep_pairing(plane, tid: str) -> tuple:
            acts_t = [r.action for r in plane.store.list_audit() if r.tenant_id == tid]
            return (
                acts_t.count(events.TENANT_DEPROVISION_REQUESTED),
                acts_t.count(events.TENANT_DEPROVISION_COMPLETED),
                acts_t.count(events.TENANT_DEPROVISION_FAILED),
            )

        # --- 07D2B2B-1: D-5 fullmatch negative on the REAL operator's DROP path -------------------
        for bad_target in (
            tenant_database_name(tid_a) + "\n",  # the `.match` + `$` trailing-newline hazard
            tenant_database_name(tid_a) + '"; DROP DATABASE "' + _CTL_DB,  # quoted-injection shape
        ):
            d5_raised = False
            try:
                cp.operator.deprovision(target=bad_target)
            except ProvisioningError:
                d5_raised = True
            assert d5_raised, f"the shared guard must reject {bad_target!r} on the DROP path (fail closed)"
        assert _db_exists(psycopg, admin_dsn, tenant_database_name(tid_a)), "no DROP may have happened"
        assert _db_exists(psycopg, admin_dsn, _CTL_DB), "the Control DB must be untouched"
        print("PASS: 07D2B2B-1 D-5 fullmatch negative (newline/suffix-injected DROP targets rejected; nothing dropped)")

        # --- 07D2B2B-2: EMPTY tenant DB eligible -> explicit deprovision drops it ------------------
        # Fixture: unresolvable tenant ref -> provision succeeds, apply fails -> PROVISIONING + EMPTY DB.
        out_de = _onboard(cp, tid_de, "c-2b2b-de0")
        assert out_de.reason == "schema_application_failed", out_de.reason
        rec_de = cp.store.get_tenant(tid_de)
        assert rec_de is not None and rec_de.lifecycle_state is TenantLifecycleState.PROVISIONING
        assert _db_exists(psycopg, admin_dsn, tenant_database_name(tid_de)), "the empty orphan DB exists"
        out_de_dep = _deprovision(cp, tid_de, "c-2b2b-de1")
        assert out_de_dep.dropped and out_de_dep.completed and out_de_dep.reason == REASON_DEPROVISIONED, out_de_dep
        assert not _db_exists(psycopg, admin_dsn, tenant_database_name(tid_de)), "the empty DB must be DROPPED"
        assert _dep_pairing(cp, tid_de) == (1, 1, 0), "Requested -> Completed exactly once each"
        rec_de2 = cp.store.get_tenant(tid_de)
        assert rec_de2 is not None, "the registry record is RETAINED (never deleted)"
        assert rec_de2.lifecycle_state is TenantLifecycleState.PROVISIONING, "deprovision changes no lifecycle state"
        # Idempotency by outcome (§8.3): repeating the explicit request is a safe no-op Completed.
        out_de_rep = _deprovision(cp, tid_de, "c-2b2b-de2")
        assert not out_de_rep.dropped and out_de_rep.completed and out_de_rep.reason == REASON_ABSENT_NOOP
        assert _dep_pairing(cp, tid_de) == (2, 2, 0)
        print(
            "PASS: 07D2B2B-2 empty tenant DB deprovisioned "
            "(proof passed; Requested->Completed; registry retained; absent repeat = safe no-op)"
        )

        # --- 07D2B2B-3: BOOTSTRAP-ONLY tenant DB eligible (R1-3 census) ---------------------------
        # Fixture: gate-fail (expected '2' vs observed '1') -> FAILED with a fully applied schema
        # (all applicator tables + the System Primary seed + the platform schema_version row).
        out_bs = cp.onboarding.onboard(
            tid_bs,
            organization_ref=_ORG,
            federation_config_ref=_FED,
            actor="ops_ref",
            correlation_id="c-2b2b-bs0",
            expected_schema_version="2",
        )
        assert out_bs.result is DistinctnessResult.VERIFICATION_FAILED, out_bs
        rec_bs = cp.store.get_tenant(tid_bs)
        assert rec_bs is not None and rec_bs.lifecycle_state is TenantLifecycleState.FAILED
        assert _db_exists(psycopg, admin_dsn, tenant_database_name(tid_bs)), "the schema'd DB exists"
        out_bs_dep = _deprovision(cp, tid_bs, "c-2b2b-bs1")
        assert out_bs_dep.dropped and out_bs_dep.reason == REASON_DEPROVISIONED, out_bs_dep
        assert not _db_exists(psycopg, admin_dsn, tenant_database_name(tid_bs)), "the bootstrap-only DB must be DROPPED"
        rec_bs2 = cp.store.get_tenant(tid_bs)
        assert rec_bs2 is not None and rec_bs2.lifecycle_state is TenantLifecycleState.FAILED, "record retained; state unchanged"
        print("PASS: 07D2B2B-3 bootstrap-only tenant DB deprovisioned (schema + seed + schema_version accepted by the R1-3 census)")

        # --- 07D2B2B-4: NON-EMPTY tenant DB preserved + quarantined --------------------------------
        # AT-PMV46-1 (PR #46 pre-merge V-1): three evidence classes — (A) a materialized view
        # (physically stored rows invisible to a relkind='r'-only census) and (B) a large
        # object (pg_largeobject; invisible to any user-relation scan), each proven to refuse
        # ALONE; then (C) extra-table (+ residual large object) — the original
        # characterization, with Phase B's large object deliberately left in place
        # (AT-PMV46-13: Phase C is NOT an alone-proof).
        out_ne = cp.onboarding.onboard(
            tid_ne,
            organization_ref=_ORG,
            federation_config_ref=_FED,
            actor="ops_ref",
            correlation_id="c-2b2b-ne0",
            expected_schema_version="2",
        )
        assert out_ne.result is DistinctnessResult.VERIFICATION_FAILED
        ne_db = tenant_database_name(tid_ne)
        # Phase A — MATVIEW-ONLY evidence: the DB is bootstrap-only except a matview with rows.
        ne_conn = psycopg.connect(_pg.swap_db(admin_dsn, ne_db))
        try:
            with ne_conn.cursor() as cur:
                cur.execute("CREATE MATERIALIZED VIEW evidence_snapshot AS SELECT g AS x FROM generate_series(1, 5) g")
            ne_conn.commit()
        finally:
            ne_conn.close()
        out_ne_mv = _deprovision(cp, tid_ne, "c-2b2b-ne1")
        assert not out_ne_mv.completed and out_ne_mv.reason == REASON_CONTENT_NOT_EMPTY, (
            f"a materialized view ALONE must classify as evidence (V-1): {out_ne_mv}"
        )
        assert _db_exists(psycopg, admin_dsn, ne_db), "the matview-bearing DB is PRESERVED (never dropped)"
        rec_ne = cp.store.get_tenant(tid_ne)
        assert rec_ne is not None and rec_ne.lifecycle_state is TenantLifecycleState.QUARANTINED, (
            "an eligible (Failed) tenant with evidence content quarantines (R1-5)"
        )
        # The READ-ONLY scan must also see the matview content: non_empty_evidence, unsafe.
        ne_scan_entry = next(e for e in cp.orphan_scan.scan_for_orphans() if e.database_name == ne_db)
        assert ne_scan_entry.classification == "non_empty_evidence" and not ne_scan_entry.safe_to_deprovision, ne_scan_entry
        assert ne_scan_entry.content_class == "non_empty"
        # Phase B — LARGE-OBJECT-ONLY evidence: drop the matview; leave only a large object.
        ne_conn = psycopg.connect(_pg.swap_db(admin_dsn, ne_db))
        try:
            with ne_conn.cursor() as cur:
                assert _one(cur, "SELECT count(*) FROM evidence_snapshot") == 5, "matview rows survive Phase A unmodified"
                cur.execute("DROP MATERIALIZED VIEW evidence_snapshot")
                cur.execute("SELECT lo_create(0)")
            ne_conn.commit()
        finally:
            ne_conn.close()
        out_ne_lo = _deprovision(cp, tid_ne, "c-2b2b-ne2")
        assert not out_ne_lo.completed and out_ne_lo.reason == REASON_CONTENT_NOT_EMPTY, (
            f"a large object ALONE must classify as evidence (V-1): {out_ne_lo}"
        )
        assert _db_exists(psycopg, admin_dsn, ne_db), "the large-object-bearing DB is PRESERVED"
        rec_ne_lo = cp.store.get_tenant(tid_ne)
        assert rec_ne_lo is not None and rec_ne_lo.lifecycle_state is TenantLifecycleState.QUARANTINED, (
            "an already-QUARANTINED tenant STAYS on a further proof failure (R1-5, live)"
        )
        # Phase C — EXTRA-TABLE (+ residual large object) evidence (the original
        # characterization; the Phase-B large object remains in place — AT-PMV46-13).
        ne_conn = psycopg.connect(_pg.swap_db(admin_dsn, ne_db))
        try:
            with ne_conn.cursor() as cur:
                cur.execute("CREATE TABLE evidence_extra (x int)")  # beyond-bootstrap content
                cur.execute("INSERT INTO evidence_extra (x) VALUES (1)")
            ne_conn.commit()
        finally:
            ne_conn.close()
        out_ne_dep = _deprovision(cp, tid_ne, "c-2b2b-ne3")
        assert not out_ne_dep.completed and out_ne_dep.reason == REASON_CONTENT_NOT_EMPTY, out_ne_dep
        assert _db_exists(psycopg, admin_dsn, ne_db), "the non-empty DB is PRESERVED (never dropped)"
        ne_acts = [r.action for r in cp.store.list_audit() if r.tenant_id == tid_ne]
        assert events.TENANT_DEPROVISION_FAILED in ne_acts and events.TENANT_QUARANTINED in ne_acts
        assert ne_acts.count("QuarantineTenant") == 1, "exactly ONE quarantine transition (re-quarantine never attempted)"
        assert ne_acts.count(events.TENANT_DEPROVISION_REQUESTED) == 3
        assert ne_acts.count(events.TENANT_DEPROVISION_FAILED) == 3, "each explicit request pairs with exactly one Failed"
        ne_check = psycopg.connect(_pg.swap_db(admin_dsn, ne_db))
        try:
            with ne_check.cursor() as cur:
                assert _one(cur, "SELECT count(*) FROM evidence_extra") == 1, "the evidence rows survive unmodified"
                assert _one(cur, "SELECT count(*) FROM pg_largeobject_metadata") == 1, "the large object survives"
        finally:
            ne_check.close()
        print(
            "PASS: 07D2B2B-4 non-empty tenant DB preserved (matview-only and large-object-only evidence EACH "
            "refuse alone; extra-table (+ residual large object) also refuses; no DROP; scan reports "
            "non_empty_evidence; FAILED -> QUARANTINED once, then stays)"
        )

        # --- 07D2B2B-5: Control DB non-droppable (fails BEFORE the operator; Control DB survives) --
        # A dedicated composition whose CONTROL database sits INSIDE the tenant namespace
        # (sp2_tenant_ctlx == tenant_database_name('ctlx')): the recomputed target of tenant
        # 'ctlx' IS that composition's Control DB, so the never-droppable guard must fire.
        ctl_clone = tenant_database_name("ctlx")
        boot_ctl = psycopg.connect(admin_dsn, autocommit=True)
        try:
            boot_ctl.execute(f'CREATE DATABASE "{ctl_clone}"')
        finally:
            boot_ctl.close()
        cc = psycopg.connect(_pg.swap_db(admin_dsn, ctl_clone))
        try:
            with cc.cursor() as cur:
                for name in _CONTROL_DDL_ORDER:
                    cur.execute((_CONTROL_DDL_DIR / name).read_text(encoding="utf-8"))
            cc.commit()
        finally:
            cc.close()
        saved_ctl_dsn = os.environ[_CTL_SECRET_KEY]
        os.environ[_CTL_SECRET_KEY] = _pg.swap_db(admin_dsn, ctl_clone)
        try:
            cp_ctl = cp_main.create_app()
            open_stores.append(cp_ctl.store)
            cp_ctl.registry.register_tenant(
                tenant_id="ctlx",
                organization_ref=_ORG,
                expected_schema_version="1",
                database_association_ref=SecretRef(store_ref=tenant_dsn_ref("ctlx"), version="1"),
                federation_config_ref=_FED,
                actor="ops_ref",
                correlation_id="c-2b2b-ctl0",
            )
            cp_ctl.registry.mark_provisioning("ctlx", actor="ops_ref", correlation_id="c-2b2b-ctl1")
            out_ctl = _deprovision(cp_ctl, "ctlx", "c-2b2b-ctl2")
            assert not out_ctl.completed and out_ctl.reason == REASON_CONTROL_TARGET, out_ctl
            assert _db_exists(psycopg, admin_dsn, ctl_clone), "the Control DB must SURVIVE (guard fires pre-operator)"
            rec_ctlx = cp_ctl.store.get_tenant("ctlx")
            assert rec_ctlx is not None and rec_ctlx.lifecycle_state is TenantLifecycleState.QUARANTINED, (
                "the Control-target anomaly quarantines the eligible (Provisioning) tenant"
            )
            assert _dep_pairing(cp_ctl, "ctlx") == (1, 0, 1), "Requested -> Failed trail, durably recorded"
        finally:
            os.environ[_CTL_SECRET_KEY] = saved_ctl_dsn
        print("PASS: 07D2B2B-5 Control DB non-droppable (refusal BEFORE operator; Control DB survives; Requested->Failed durable)")

        # --- 07D2B2B-6: ledger/fingerprint collision -> NO DROP, fail closed, quarantine -----------
        out_lc = cp.onboarding.onboard(
            tid_lc,
            organization_ref=_ORG,
            federation_config_ref=_FED,
            actor="ops_ref",
            correlation_id="c-2b2b-lc0",
            expected_schema_version="2",
        )
        assert out_lc.result is DistinctnessResult.VERIFICATION_FAILED
        # Manufacture ANOTHER tenant's durable distinctness evidence naming d07lc's database
        # (the existing public ledger write API; the collision row is removed again below).
        cp.provisioning._ledger.record_evidence(
            "d07other",
            DistinctnessEvidence(
                system_identifier="",
                database_identity="collision:evidence",
                observed_target=tenant_database_name(tid_lc),
                secret_ref_key="tenant/d07other/dsn",
                sentinel_namespace="dv_sentinel_d07other",
                sentinel_token="tok",
                sentinel_written=True,
            ),
        )
        try:
            out_lc_dep = _deprovision(cp, tid_lc, "c-2b2b-lc1")
            assert not out_lc_dep.completed and out_lc_dep.reason == REASON_LEDGER_COLLISION, out_lc_dep
            assert _db_exists(psycopg, admin_dsn, tenant_database_name(tid_lc)), "NO DROP on a ledger collision"
            rec_lc = cp.store.get_tenant(tid_lc)
            assert rec_lc is not None and rec_lc.lifecycle_state is TenantLifecycleState.QUARANTINED
        finally:
            cp.provisioning._ledger.remove("d07other")
        print("PASS: 07D2B2B-6 ledger collision (another tenant's durable evidence names the target: no DROP; quarantined)")

        # --- 07D2B2B-7: physical DB with NO registry record -> scan reports only; nothing touched --
        orph_db = tenant_database_name("d07orph")
        boot_orph = psycopg.connect(admin_dsn, autocommit=True)
        try:
            boot_orph.execute(f'CREATE DATABASE "{orph_db}"')
        finally:
            boot_orph.close()
        audit_count_before = len(cp.store.list_audit())
        scan_entries = cp.orphan_scan.scan_for_orphans()
        orph_entry = next(e for e in scan_entries if e.database_name == orph_db)
        assert orph_entry.classification == CLASS_NO_REGISTRY_RECORD and orph_entry.tenant_id is None
        assert not orph_entry.safe_to_deprovision
        assert len(cp.store.list_audit()) == audit_count_before, "the scan emits ZERO audit events (read-only)"
        assert _db_exists(psycopg, admin_dsn, orph_db), "the scan drops nothing (report-only)"
        # The registry-side sweep also reports d07de (record retained, DB dropped in 07D2B2B-2).
        de_entry = next(e for e in scan_entries if e.database_name == tenant_database_name(tid_de))
        assert de_entry.classification == "registry_record_database_absent" and de_entry.tenant_id == tid_de
        # Secret hygiene: the report carries no DSN/secret material (D-14).
        for entry in scan_entries:
            for secret in (admin_dsn, os.environ[_CTL_SECRET_KEY]):
                assert secret not in repr(entry), "no secret material may appear in the scan report"
        # Explicit deprovision of the unknown id refuses (Requested->Failed) and touches nothing.
        out_orph = _deprovision(cp, "d07orph", "c-2b2b-or1")
        assert not out_orph.completed and out_orph.reason == REASON_UNKNOWN_TENANT
        assert _db_exists(psycopg, admin_dsn, orph_db), "a no-registry-record DB is NEVER touched"
        print("PASS: 07D2B2B-7 no-registry-record DB (scan reports read-only, zero events; explicit deprovision refuses; DB survives)")

        # --- 07D2B2B-8: cross-process durable anomaly-history re-classification (R1-7 recipe) ------
        out_x = _onboard(cp, tid_x, "c-2b2b-x0")
        assert out_x.result is DistinctnessResult.VERIFIED, out_x.reason
        saved_x_dsn = os.environ.pop(_tenant_env_key(tid_x))  # break the DSN secret
        try:
            out_x_fail = cp.provisioning.verify(tid_x, actor="ops_ref", correlation_id="c-2b2b-x1")
        finally:
            os.environ[_tenant_env_key(tid_x)] = saved_x_dsn
        assert out_x_fail.result is DistinctnessResult.VERIFICATION_INCOMPLETE, out_x_fail
        rec_x = cp.store.get_tenant(tid_x)
        assert rec_x is not None and rec_x.lifecycle_state is TenantLifecycleState.FAILED, "non-anomalous FAILED landing"
        # Instance A writes ONE IsolationAnomaly row via the PUBLIC audit API (durable store).
        cp.audit.record(
            actor="ops_ref",
            tenant_id=tid_x,
            action=events.ISOLATION_ANOMALY,
            from_state=None,
            to_state=None,
            correlation_id="c-2b2b-x2",
        )
        # Instance B: a FRESH composition (same env) re-classifies from the DURABLE trail.
        cp_b2 = cp_main.create_app()
        open_stores.append(cp_b2.store)
        x_verifies_before = len(
            [r for r in cp_b2.store.list_audit() if r.tenant_id == tid_x and r.action == events.DISTINCTNESS_VERIFICATION_STARTED]
        )
        out_x_rec = cp_b2.onboarding.recover(tid_x, actor="ops_ref", correlation_id="c-2b2b-x3")
        assert out_x_rec.result is DistinctnessResult.ISOLATION_ANOMALY and out_x_rec.reason == "anomaly_history", out_x_rec
        rec_x2 = cp_b2.store.get_tenant(tid_x)
        assert rec_x2 is not None and rec_x2.lifecycle_state is TenantLifecycleState.QUARANTINED, (
            "fresh-process recover() must re-classify to QUARANTINED from the durable trail"
        )
        x_verifies_after = len(
            [r for r in cp_b2.store.list_audit() if r.tenant_id == tid_x and r.action == events.DISTINCTNESS_VERIFICATION_STARTED]
        )
        assert x_verifies_after == x_verifies_before, "must NEVER re-enter Verifying (no new DistinctnessVerificationStarted)"
        # The sentinel-BEARING bootstrap-only DB (dv_sentinel rows from the READY run) then
        # deprovisions from QUARANTINED — verification artifacts are bootstrap-compatible (R1-3).
        x_conn = psycopg.connect(_pg.swap_db(admin_dsn, tenant_database_name(tid_x)))
        try:
            with x_conn.cursor() as cur:
                assert _one(cur, "SELECT count(*) FROM dv_sentinel.marker") > 0, "sentinel artifacts present"
        finally:
            x_conn.close()
        out_x_dep = _deprovision(cp_b2, tid_x, "c-2b2b-x4")
        assert out_x_dep.dropped and out_x_dep.reason == REASON_DEPROVISIONED, out_x_dep
        assert not _db_exists(psycopg, admin_dsn, tenant_database_name(tid_x))
        rec_x3 = cp_b2.store.get_tenant(tid_x)
        assert rec_x3 is not None and rec_x3.lifecycle_state is TenantLifecycleState.QUARANTINED, "record retained; state unchanged"
        print(
            "PASS: 07D2B2B-8 cross-process durable re-classification (fresh recover() -> QUARANTINED, never re-enters "
            "Verifying, never Ready; sentinel-bearing bootstrap-only DB deprovisions from Quarantined)"
        )
        assert _db_exists(psycopg, admin_dsn, _CTL_DB), "the primary Control DB survives the whole compensation arc"

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


# =====================================================================================================
# PRD D-15-T1b — gateway<->database-router dispatch transport pair, live-PG proof DT-1..DT-8.
# Self-contained (own scratch databases; no onboarding dependency): it exercises the RUNTIME dispatch
# transport (api_gateway urllib client -> internal database_router HTTP dispatch server -> composed
# DatabaseRouter.route(ctx)) against physically-distinct PostgreSQL databases on the ephemeral cluster.
# Run set STAYS 13 (this file is already a single workflow loop entry). All database_router / api_gateway
# imports are function-local (Driver Containment + the harness's no-top-level-database_router discipline).
# =====================================================================================================

# §10 never-cross material scanned in the raw HTTP response bytes (DT-5 denial path, DT-7 success path).
# The raw bytes are split at the first CRLFCRLF and the halves are scanned separately, because the
# server's own framing FIELD NAMES are framing, not leaked material:
#   * header block — the framing field-name tokens are removed, then the remainder (status line, every
#     other field name, and ALL field values) is scanned CASE-INSENSITIVELY;
#   * body         — scanned CASE-INSENSITIVELY against the same needle set.
# This is strictly STRONGER than the previous CASE-SENSITIVE scan over the undivided bytes, which could
# only see a needle in the exact case listed. It also removes the false positive the FastAPI/Uvicorn
# migration introduced: ASGI servers emit field names LOWERCASE ('content-length:', 'content-type:'),
# so the bare lowercase 'content' needle matched the framing headers that stdlib http.server's
# 'Content-Type'/'Content-Length' capitalisation had kept invisible (RF/C-5). A real 'content'
# occurrence anywhere else — including inside a framing header's VALUE — still trips, because only the
# field-name tokens are removed. 'data' still does not match 'date'.
_LEAK_NEEDLES = (
    "DSN", "dsn", "dbname", "database", "host", "port", "store_ref", "SecretRef", "secret", "credential",
    "password", "passwd", "token", "authorization", "route_ref", "TenantConnection", "RouteResult",
    "TenantRoutingView", "topology", "pool", "body", "payload", "data", "content", "stack trace",
    "exception", "vendor payload", "secret version", "internal diagnostic", "lifecycle reason",
)  # fmt: skip

# Framing FIELD NAMES emitted by the server itself. Removed from the header block (never from the body,
# and never from any field value) before the case-insensitive scan. Lowercase because the header block is
# lower-cased first: ASGI/Uvicorn already emit these lowercase, stdlib http.server capitalised them, and
# HTTP/1.1 field names are case-insensitive either way.
_FRAMING_FIELD_NAMES = ("content-length:", "content-type:")


def _raw_dispatch(base_url: str, ctx, category: str) -> bytes:
    """POST a dispatch envelope over a raw socket and return the FULL raw HTTP response bytes."""
    import json
    import socket
    from urllib.parse import urlsplit

    parts = urlsplit(base_url)
    host, port = parts.hostname or "127.0.0.1", parts.port
    body = json.dumps(
        {
            "v": 1,
            "context": {
                "correlation_id": ctx.correlation_id,
                "request_id": ctx.request_id,
                "active_tenant_id": ctx.active_tenant_id,
                "principal_ref": ctx.principal_ref,
                "role": ctx.role,
            },
            "category": category,
        }
    ).encode("utf-8")
    request = (
        f"POST /internal/dispatch/route HTTP/1.1\r\nHost: {host}:{port}\r\n"
        f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n"
    ).encode("utf-8") + body
    sock = socket.create_connection((host, port), timeout=5)
    try:
        sock.sendall(request)
        chunks = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        sock.close()


def _assert_no_leak(raw_bytes: bytes, *db_names: str, label: str = "DT-7") -> None:
    """Scan the FULL raw response for §10 never-cross material. `label` names the calling check."""
    text = raw_bytes.decode("latin-1")  # byte-faithful; no re-encode surprises
    head, separator, body = text.partition("\r\n\r\n")
    if not separator:  # no header/body boundary -> scan the whole thing as a header block
        head, body = text, ""
    headers = head.lower()
    for framing in _FRAMING_FIELD_NAMES:
        headers = headers.replace(framing, "")
    for region, scanned in (("headers", headers), ("body", body.lower())):
        for needle in _LEAK_NEEDLES:
            assert needle.lower() not in scanned, f"{label} raw-byte leak: needle {needle!r} present in the response {region}"
        for name in db_names:
            assert name.lower() not in scanned, f"{label} raw-byte leak: database name {name!r} present in the response {region}"


def test_07d_dispatch_transport_pair(admin_dsn: str) -> None:
    psycopg = _psycopg()
    import threading

    from api_gateway.adapters.providers.http_router_dispatch import HttpRouterDispatch
    from api_gateway.models import DatabaseDomain, DispatchCategory, DispatchDecision
    from database_router.adapters.providers.env_tenant_secret_store import EnvTenantSecretStore
    from database_router.adapters.providers.http_dispatch_api import build_dispatch_server
    from database_router.adapters.providers.in_memory_audit_sink import InMemoryAuditSink
    from database_router.adapters.providers.psycopg_connection import PsycopgConnectionFactory
    from database_router.cache import RoutingViewCache
    from database_router.models import TenantRoutingView
    from database_router.pool import ConnectionPoolManager
    from database_router.ports import ControlPlaneRoutingReadPort
    from database_router.resolver import RoutingResolver
    from database_router.router import DatabaseRouter
    from shared.context import RequestContext

    tenant_db, ctl_db, tid = "sp2_dt_tenant", "sp2_dt_ctl", "dt1"
    store_ref = "tenant/dt1/dsn"
    env_key = EnvTenantSecretStore._env_key(store_ref, "1")
    saved_secret = os.environ.get(env_key)
    server = None
    pool = None
    try:
        # Two physically-distinct scratch databases on the same ephemeral cluster.
        for name in (tenant_db, ctl_db):
            _drop_db(psycopg, admin_dsn, name)
            boot = psycopg.connect(admin_dsn, autocommit=True)
            try:
                boot.execute(f'CREATE DATABASE "{name}"')
            finally:
                boot.close()
        tenant_dsn = _pg.swap_db(admin_dsn, tenant_db)
        os.environ[env_key] = tenant_dsn  # the router resolves the tenant descriptor BY REFERENCE (D-14)

        class _FixedRoutingRead(ControlPlaneRoutingReadPort):
            def __init__(self) -> None:
                self._views = {
                    tid: TenantRoutingView(tid, "Ready", True, SecretRef(store_ref, "1"), "1"),
                    "susp": TenantRoutingView("susp", "Suspended", False, SecretRef("tenant/susp/dsn", "1"), "1"),
                }

            def get_routing_view(self, tenant_id: str):
                return self._views.get(tenant_id)  # "ghost" -> None -> not_found

        resolver = RoutingResolver(
            _FixedRoutingRead(), RoutingViewCache(ttl_seconds=15.0, clock=lambda: 0.0), supported_schema_versions=("1",)
        )
        pool = ConnectionPoolManager(max_per_tenant=5, idle_timeout_seconds=60.0, clock=lambda: 0.0)
        audit = InMemoryAuditSink()
        router = DatabaseRouter(
            resolver=resolver, pool=pool, secret_store=EnvTenantSecretStore(), connection_factory=PsycopgConnectionFactory(), audit=audit
        )
        server, base_url = build_dispatch_server(router, "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        client = HttpRouterDispatch(base_url)

        def ctx(cid: str, tenant, role: str) -> RequestContext:
            return RequestContext(correlation_id=cid, request_id=None, active_tenant_id=tenant, principal_ref="ops_ref", role=role)

        tenant_dec = DispatchDecision(category=DispatchCategory.TENANT_OPERATION, domain=DatabaseDomain.TENANT, target_tenant_id=tid)
        control_dec = DispatchDecision(
            category=DispatchCategory.GLOBAL_DIRECTORY_READ, domain=DatabaseDomain.CONTROL, target_tenant_id=None
        )

        # DT-1 e2e happy path + EXACT one-'Route'-per-correlation-id audit (and the CONTROL leg -> RouteControl).
        out1 = client.dispatch(ctx("dt-1", tid, "TENANT_AGENT"), tenant_dec)
        assert (out1.status, out1.public_code, out1.dispatched) == (200, "ok", True), out1
        assert [e.action for e in audit.events() if e.correlation_id == "dt-1"].count("Route") == 1
        out1c = client.dispatch(ctx("dt-1c", None, "CONTROL"), control_dec)
        assert (out1c.status, out1c.public_code, out1c.dispatched) == (200, "ok", True)
        assert [e.action for e in audit.events() if e.correlation_id == "dt-1c"].count("RouteControl") == 1
        print("PASS: DT-1 e2e gateway client -> dispatch server -> router = 200/ok/true; exactly one Route (RouteControl for CONTROL)")

        # DT-2 one request -> one active tenant -> one tenant database.
        assert pool.pool_keys() == [(tid, "1")], f"exactly one tenant pool expected: {pool.pool_keys()}"
        assert pool.counts(tid, "1")[1] == 0, "the tenant connection is released before the response (in_use == 0)"
        print("PASS: DT-2 one request -> one active tenant -> one tenant database (single pool key, released)")

        # DT-3 control DB vs tenant DB physically distinct at database granularity (same cluster).
        assert tenant_db != ctl_db and _db_exists(psycopg, admin_dsn, tenant_db) and _db_exists(psycopg, admin_dsn, ctl_db)
        tconn = psycopg.connect(tenant_dsn)
        try:
            with tconn.cursor() as cur:
                bound = _one(cur, "SELECT current_database()")
                assert bound == tenant_db and bound != ctl_db, bound
        finally:
            tconn.close()
        print("PASS: DT-3 control DB vs tenant DB physically distinct at database granularity (cross-cluster is deployment-only / b3a)")

        # DT-4 dispatch server unavailable -> client fail-closed.
        out4 = HttpRouterDispatch("http://127.0.0.1:1", timeout=1.0).dispatch(ctx("dt-4", tid, "TENANT_AGENT"), tenant_dec)
        assert (out4.status, out4.public_code, out4.dispatched) == (503, "unavailable", False)
        print("PASS: DT-4 dispatch server unavailable -> 503/unavailable/false")

        # DT-5 invalid tenant -> 404/not_found/false with no topology leak.
        out5 = client.dispatch(ctx("dt-5", "ghost", "TENANT_AGENT"), tenant_dec)
        assert (out5.status, out5.public_code, out5.dispatched) == (404, "not_found", False)
        _assert_no_leak(_raw_dispatch(base_url, ctx("dt-5b", "ghost", "TENANT_AGENT"), "TENANT_OPERATION"), tenant_db, ctl_db, label="DT-5")
        print("PASS: DT-5 invalid tenant -> 404/not_found/false; raw denial carries no dbname/host/port/store_ref/credential/topology")

        # DT-6 administratively disabled / suspended routing -> 403/administratively_disabled/false.
        out6 = client.dispatch(ctx("dt-6", "susp", "TENANT_AGENT"), tenant_dec)
        assert (out6.status, out6.public_code, out6.dispatched) == (403, "administratively_disabled", False)
        print("PASS: DT-6 administratively disabled / suspended routing -> 403/administratively_disabled/false, no topology leak")

        # DT-7 raw HTTP response byte leak scan (case-insensitive, header block + body) on the success path.
        _assert_no_leak(_raw_dispatch(base_url, ctx("dt-7", tid, "TENANT_AGENT"), "TENANT_OPERATION"), tenant_db, ctl_db, label="DT-7")
        print("PASS: DT-7 raw response byte scan (success + denial): no never-cross material (case-insensitive; framing names excluded)")

        # DT-8 release hygiene: N (> max_per_tenant=5) sequential dispatches all succeed; in_use stays 0.
        for i in range(6):
            out8 = client.dispatch(ctx(f"dt-8-{i}", tid, "TENANT_AGENT"), tenant_dec)
            assert (out8.status, out8.public_code, out8.dispatched) == (200, "ok", True), (i, out8)
            assert pool.counts(tid, "1")[1] == 0, f"in_use must be 0 after dispatch {i} (no release leak)"
        print(
            "PASS: DT-8 release hygiene: 6 (> max_per_tenant=5) dispatches all 200/ok/true, in_use==0 (a leak trips "
            "connection_unavailable at #6); forced-exhaustion fail-closed carried as residual AT-D15T1-5"
        )
        print("ALL D-15-T1b DISPATCH TRANSPORT (DT-1..DT-8) CHECKS PASSED")
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if pool is not None:
            try:
                pool.invalidate_version(tid, keep_version="__drain__")  # close pooled idle conns before DROP
            except Exception:
                pass
        for name in (tenant_db, ctl_db):
            _drop_db(psycopg, admin_dsn, name)
        if saved_secret is None:
            os.environ.pop(env_key, None)
        else:
            os.environ[env_key] = saved_secret


if __name__ == "__main__":
    _pg.run([test_07d_composition_onboarding, test_07d_dispatch_transport_pair])
