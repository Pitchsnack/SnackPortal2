"""PRD 07B / PRD 07B.1 — tenant schema-application wiring, end-to-end on live PostgreSQL (standalone-only).

Proves the onboarding lifecycle now reaches Ready on a REAL physically-distinct tenant database
because onboarding Step 2b applies the tenant schema before verification:

    register -> provision physical DB (CREATE DATABASE) -> APPLY SCHEMA (Step 2b: 6 bootstrap +
    7 tenant templates + System Primary seed, ONE transaction) -> associate ->
    verify (probe reads schema_version; Physical Distinctness VERIFIED) -> Ready.

It composes the REAL adapters directly (PostgresProvisioningOperator, PostgresTenantSchemaApplicator,
PostgresTenantProbe, PostgresDistinctnessEvidenceProvider) against scratch databases on one ephemeral
cluster — the same standalone pattern as the sibling requires_pg harnesses. The Database Router serving
path (routing a live request through the gateway to the tenant DB) is intentionally OUT OF SCOPE here
(the authorized 07B lifecycle ends at Ready; live router serving is a later deployment phase). B5-BLK-4
remains OPEN; the Physical Multi-Database MVP remains mandatory.

CHECKS:
  C1  onboard -> provision -> apply schema -> verify VERIFIED -> Ready; schema actually present in the
      tenant DB (schema_version='1', lineage, dv_sentinel.marker, sp2_provisioner/lineage_writer/reader).
  C3  a second tenant reaches Ready on its own distinct physical DB (cross-tenant distinctness).
  C4  atomic rollback: a failing DDL mid-apply rolls the WHOLE transaction back (no partial schema) and
      raises TenantSchemaApplicationError.
  C5  idempotent re-apply: applying twice is a no-op (schema_version stays one row; lineage intact).
  C6  secret hygiene (D-14): the DSN never appears in the operational audit records.
  C7  blob pins: the SIX 07B bootstrap templates equal their reviewed git blobs (drift FAILs — do not fix
      DDL here). The seven 07C tenant files are pinned by 07C's OWN guard/harness (C7 Option 2): this
      harness asserts their MEMBERSHIP and ORDER against 07C's TENANT_DDL_APPLY_ORDER authority only —
      it deliberately duplicates no tenant pins and introduces no _REVIEWED_* names (b7c1r2 stays clean).
  C8  NON-VACUITY: with a no-op applicator (no Step 2b effect) the real tenant DB has no schema_version, so
      verify fails closed and the tenant is NOT Ready; with the real applicator it reaches Ready.
PRD 07B.1 CHECKS (composed Step-2b + System Primary seed):
  C9  the composed Step-2b applied 13 files (6 bootstrap first, then the 7 tenant files in
      TENANT_DDL_APPLY_ORDER) — full 14-table tenant business schema present after Ready.
  C10 a freshly provisioned tenant DB has EXACTLY ONE system_primary Agent (before any human exists).
  C11 the seeded row is agent_kind='system_primary', agent_status='active', supervised_by_agent_id NULL.
  C12 idempotent full-set re-apply leaves exactly one system_primary row.
  C13 a duplicate direct system_primary INSERT fails on the 07C singleton constraint.
  C14 system_primary DELETE and kind-flip UPDATE remain blocked by the 07C trigger after bootstrap.
  C15 no human Agent is required for Ready (zero humans in the fresh tenant).
  C16 no queue-manager / reservation / claim table exists.
  C17 no tenant_id column exists in the tenant business tables (tenancy is PHYSICAL).
  C18 the Control-DB reference holds no tenant operational tables.
  C19 SEED RACE (07C-AT-5): a TRUE two-connection race on the seed path — the loser (driven through the
      applicator seam) is classified fail-closed as TenantSchemaApplicationError; exactly one SP remains.
      Reachability caveat: the normal path cannot race two same-DB Step-2b applies (CREATE DATABASE
      precludes it), so the race is isolated at the seed seam per the exec-auth package §14 allowance.
  C20 LATE FAILURE (07C-AT-2): (a) a failure AFTER all 13 composed files rolls back the ENTIRE
      transaction (no bootstrap schema, no tenant schema, no SP row persists); (b) a seed-time failure
      likewise rolls back all 13 applied files (fail-closed, no partial schema).

DRIVER CONTAINMENT. This file imports NO database driver statically and does NOT import the postgres
adapters at module top level (psycopg is reached only via importlib.import_module after a DSN check; the
real adapters are imported lazily inside the composer, which runs only when the harness runs) — so the
default-suite tests/architecture/test_vendor_and_db_containment.py (AST scan for static driver imports)
is not tripped and the file clean-imports without psycopg.

DEFAULT SUITE. IGNORED by the default run (pyproject addopts --ignore=tests/control_plane/requires_pg).
Run it by setting SNACKPORTAL_TEST_DSN to a NON-PRODUCTION admin DSN (CREATE/DROP DATABASE + CREATE/DROP
ROLE; the ephemeral CI postgres service runs as the postgres superuser under trust auth) and invoking:
  python backend/tests/control_plane/requires_pg/test_pg_onboarding_e2e_schema_application.py
With SNACKPORTAL_TEST_DSN unset (or psycopg absent) it clean-skips (exit 0).

SECRET HYGIENE (D-14). SNACKPORTAL_TEST_DSN is used by NAME only; its value is never printed. No row
written here holds a DSN/secret. All scratch databases and the cluster roles are dropped in `finally`.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import os
import pathlib
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402  (standalone live-PG runner: SNACKPORTAL_TEST_DSN, available()/run()/swap_db)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

from control_plane import events  # noqa: E402
from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.adapters.providers.in_memory_tenant_schema_applicator import (  # noqa: E402
    InMemoryTenantSchemaApplicator,
)
from control_plane.audit import ControlPlaneAudit  # noqa: E402
from control_plane.distinctness import DistinctnessResult  # noqa: E402
from control_plane.onboarding import OnboardingOrchestrator  # noqa: E402
from control_plane.provisioning import (  # noqa: E402
    ProvisioningVerificationService,
    TenantSchemaApplicationError,
    tenant_database_name,
)
from control_plane.records import TenantLifecycleState  # noqa: E402
from control_plane.registry import TenantRegistry  # noqa: E402
from shared.secrets import SecretRef, SecretStore, SecretValue  # noqa: E402

# --- reviewed DDL templates + git-blob pins (applied bytes MUST equal these; drift STOPs) ---------
_DB = pathlib.Path(__file__).resolve().parents[4] / "infrastructure" / "db"
_DDL_BLOBS = [
    (_DB / "provisioning" / "001_tenant_database.sql", "d3073e82a6b9b5dc3bc9774201c6932c956a6897"),
    (_DB / "provisioning" / "002_distinctness_sentinel.sql", "04b1401de262320e140d79f5133051f41ff92693"),
    (_DB / "provisioning" / "003_provisioning_role.sql", "2564826cc2d00b63b2edf0c7f88fc2c88bcc853b"),
    (_DB / "lineage" / "001_lineage_schema.sql", "5891b5dbce621bffda2ca15ac29cf6621d1dd725"),
    (_DB / "lineage" / "002_append_only.sql", "e32be83c37ac37c3f3a96a3b008bd1b1b1dc0521"),
    (_DB / "lineage" / "003_roles.sql", "b962d4ca2b0cbfbb9ac1ce0b11e2bdfa4cab6a33"),
]

_CTL_DB = "sp2_b7b_e2e_ctl"  # scratch Control-DB reference (distinct from any tenant DB)
_CLUSTER_ROLES = ("sp2_provisioner", "lineage_writer", "lineage_reader")  # cluster-scoped; created by 003 templates
_ORG, _FED = "org_ref_x", "fed_ref_x"

# PRD 07C V5's full tenant business table census (the 07B.1 composed apply must produce exactly these
# ON TOP of the bootstrap objects; census mirrors the 07C harness).
_TENANT_BUSINESS_TABLES = (
    "agents",
    "ai_agents",
    "startups",
    "investors",
    "deals",
    "startup_ownership",
    "investor_ownership",
    "deal_ownership",
    "startup_ai_ownership",
    "investor_ai_ownership",
    "deal_ai_ownership",
    "startup_contacts",
    "investor_contacts",
    "startup_investors",
)


def _tenant_apply_order_from_guard() -> list:
    """TENANT_DDL_APPLY_ORDER parsed from 07C's machine-readable guard authority (AST literal —
    no import, no side effects). C7 Option 2: this harness asserts membership/order against the
    07C-owned list; it deliberately duplicates NO tenant blob pins and names NO _REVIEWED_* pin
    (the b7c1r2 meta-guard scans this directory for _REVIEWED_* — tenant pins are 07C's)."""
    guard = pathlib.Path(__file__).resolve().parents[2] / "architecture" / "test_tenant_ddl_blob_drift.py"
    for node in ast.parse(guard.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "TENANT_DDL_APPLY_ORDER" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("TENANT_DDL_APPLY_ORDER not found in the 07C tenant blob-drift guard")


# --- helpers (stdlib only; driver reached solely via importlib.import_module) ---------------------
def _psycopg():
    """The database driver, located at call time (no static import — Driver Containment Standard)."""
    return importlib.import_module("psycopg")


def _git_blob_sha1(path: pathlib.Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")  # autocrlf normalization (the git blob is LF)
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _assert_blobs() -> None:
    for path, expected in _DDL_BLOBS:
        actual = _git_blob_sha1(path)
        assert actual == expected, f"{path.name} blob {actual} != reviewed {expected} — STOP (do not fix DDL here)"


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
    """Best-effort cluster-role drop (the role's per-DB grants vanish with the dropped tenant DBs)."""
    try:
        conn = psycopg.connect(admin_dsn, autocommit=True)
        try:
            conn.execute(f'DROP ROLE IF EXISTS "{name}"')
        finally:
            conn.close()
    except Exception:
        pass


def _cleanup(psycopg, admin_dsn: str, tenant_ids) -> None:
    for tid in tenant_ids:
        _drop_db(psycopg, admin_dsn, tenant_database_name(tid))
    _drop_db(psycopg, admin_dsn, _CTL_DB)
    for role in _CLUSTER_ROLES:
        _drop_role(psycopg, admin_dsn, role)


class _HarnessSecretStore(SecretStore):
    """Test-only D-14 secret store: a SecretRef whose store_ref is a database name resolves to the
    admin DSN with that database substituted. Material is built in-memory at resolve() time only."""

    def __init__(self, admin_dsn: str) -> None:
        self._admin = admin_dsn

    def resolve(self, ref: SecretRef) -> SecretValue:
        return SecretValue(material=_pg.swap_db(self._admin, ref.store_ref))

    def current_version(self, store_ref: str) -> str:
        return "1"


def _build(psycopg, admin_dsn: str, *, real_applicator: bool):
    """Compose the onboarding orchestrator with the REAL postgres adapters (operator/probe/evidence)
    and either the real or a no-op schema applicator. Creates a scratch Control-DB reference and
    gathers its real distinctness evidence. Returns (orchestrator, store). (Adapters imported lazily:
    they pull psycopg, so importing them only happens when the harness actually runs.)"""
    from control_plane.adapters.providers.postgres_distinctness import PostgresDistinctnessEvidenceProvider
    from control_plane.adapters.providers.postgres_probe import PostgresTenantProbe
    from control_plane.adapters.providers.postgres_provisioning_operator import PostgresProvisioningOperator
    from control_plane.adapters.providers.postgres_tenant_schema_applicator import PostgresTenantSchemaApplicator

    secret_store = _HarnessSecretStore(admin_dsn)
    store = InMemoryControlStore()
    audit = ControlPlaneAudit(store)
    registry = TenantRegistry(store, audit)
    operator = PostgresProvisioningOperator(admin_dsn)
    evidence_provider = PostgresDistinctnessEvidenceProvider(secret_store)
    probe = PostgresTenantProbe(secret_store)
    applicator = PostgresTenantSchemaApplicator(secret_store) if real_applicator else InMemoryTenantSchemaApplicator()

    # Control-DB reference: a scratch database whose REAL distinctness evidence the verifier compares
    # every tenant against (a tenant must be physically distinct from it).
    _drop_db(psycopg, admin_dsn, _CTL_DB)
    operator.provision("ctl", target=_CTL_DB)
    control_db_evidence = evidence_provider.gather(
        SecretRef(store_ref=_CTL_DB, version="1"), sentinel_token="ctl_tok", sentinel_namespace="ctl_ns"
    )
    assert control_db_evidence is not None, "control-DB distinctness evidence must be gatherable — NOT READY (environment)"

    gate = ProvisioningVerificationService(store, audit, probe, evidence_provider, control_db_evidence, supported_schema_versions=["1"])
    return OnboardingOrchestrator(registry, operator, gate, audit, applicator), store


def _onboard(orch: OnboardingOrchestrator, tenant_id: str, correlation_id: str):
    return orch.onboard(tenant_id, organization_ref=_ORG, federation_config_ref=_FED, actor="ops_ref", correlation_id=correlation_id)


# --- the exercise --------------------------------------------------------------------------------
def test_e2e_onboard_applies_schema_and_reaches_ready(admin_dsn: str) -> None:
    """C1 + C3 + C6 + C7: full lifecycle to Ready, schema physically present, two tenants distinct."""
    psycopg = _psycopg()
    _assert_blobs()
    print("PASS: C7 blob pins (6 DDL templates == reviewed git blobs)")

    tids = ["b7be2ea", "b7be2eb"]
    orch, store = _build(psycopg, admin_dsn, real_applicator=True)
    try:
        for tid in tids:
            _drop_db(psycopg, admin_dsn, tenant_database_name(tid))

        out_a = _onboard(orch, tids[0], "c-a")
        assert out_a.result is DistinctnessResult.VERIFIED, out_a.reason
        rec_a = store.get_tenant(tids[0])
        assert rec_a is not None and rec_a.lifecycle_state is TenantLifecycleState.READY
        print("PASS: C1 tenant A — provision -> apply schema -> verify VERIFIED -> READY")

        ta = psycopg.connect(_pg.swap_db(admin_dsn, tenant_database_name(tids[0])))
        try:
            with ta.cursor() as cur:
                assert _one(cur, "SELECT to_regclass('schema_version')") is not None, "schema_version must exist"
                assert str(_one(cur, "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1")) == "1"
                assert _one(cur, "SELECT to_regclass('lineage')") is not None, "lineage must exist"
                assert _one(cur, "SELECT to_regclass('lineage_segment')") is not None, "lineage_segment must exist"
                assert _one(cur, "SELECT to_regclass('dv_sentinel.marker')") is not None, "dv_sentinel.marker must exist"
                for role in _CLUSTER_ROLES:
                    assert _one(cur, "SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)) is not None, f"{role} must exist"
        finally:
            ta.close()
        print("PASS: C1 tenant A physical schema present (schema_version=1, lineage(+segment), dv_sentinel.marker, 3 roles)")

        # ---- PRD 07B.1: composed Step-2b + System Primary probes (autocommit: error probes are own txns)
        from control_plane.adapters.providers.postgres_tenant_schema_applicator import (
            default_tenant_schema_ddl_paths,
        )

        pa = psycopg.connect(_pg.swap_db(admin_dsn, tenant_database_name(tids[0])))
        pa.autocommit = True
        try:
            with pa.cursor() as cur:
                # C9 — the composed transaction applied the full tenant business schema, and the
                # applicator's composed order is 6 bootstrap files then 07C's TENANT_DDL_APPLY_ORDER
                # (membership/order asserted against the 07C authority — C7 Option 2, no pin duplication).
                for table in _TENANT_BUSINESS_TABLES:
                    assert _one(cur, "SELECT to_regclass(%s)", (table,)) is not None, f"{table} must exist after Ready"
                names = [p.name for p in default_tenant_schema_ddl_paths()]
                assert len(names) == 13, f"composed Step-2b path count must be 13: {names}"
                assert names[:6] == [p.name for p, _sha in _DDL_BLOBS], "the six 07B bootstrap templates must come first"
                assert names[6:] == _tenant_apply_order_from_guard(), (
                    f"appended tenant files {names[6:]} must equal 07C's TENANT_DDL_APPLY_ORDER"
                )
                print("PASS: C9 composed Step-2b applied 13 files (6 bootstrap + 7 tenant in 07C order); full tenant schema present")

                # C10 + C11 + C15 — exactly one seeded System Primary; correct shape; zero humans needed.
                assert _one(cur, "SELECT count(*) FROM agents WHERE agent_kind = 'system_primary'") == 1
                assert _one(cur, "SELECT count(*) FROM agents") == 1, "the SP seed must be the ONLY agents row"
                cur.execute("SELECT agent_status, supervised_by_agent_id FROM agents WHERE agent_kind = 'system_primary'")
                status, supervisor = cur.fetchone()
                assert status == "active" and supervisor is None, (status, supervisor)
                assert _one(cur, "SELECT count(*) FROM agents WHERE agent_kind = 'human'") == 0
                print("PASS: C10/C11/C15 exactly one system_primary (active, unsupervised); zero humans required for Ready")

                # C13 — duplicate direct SP insert rejected by the 07C singleton (own txn under autocommit).
                dup_raised = False
                try:
                    cur.execute(
                        "INSERT INTO agents (agent_kind, agent_status, supervised_by_agent_id) VALUES ('system_primary', 'active', NULL)"
                    )
                except Exception:
                    dup_raised = True
                assert dup_raised, "a second system_primary row must be rejected by ux_agents_single_system_primary"
                print("PASS: C13 duplicate system_primary insert rejected (07C singleton)")

                # C14 — the 07C protective trigger still blocks DELETE and kind-flip after bootstrap.
                del_raised = False
                try:
                    cur.execute("DELETE FROM agents WHERE agent_kind = 'system_primary'")
                except Exception:
                    del_raised = True
                assert del_raised, "system_primary DELETE must be rejected by trg_agents_protect_system_primary"
                flip_raised = False
                try:
                    cur.execute("UPDATE agents SET agent_kind = 'human' WHERE agent_kind = 'system_primary'")
                except Exception:
                    flip_raised = True
                assert flip_raised, "system_primary kind-flip must be rejected by trg_agents_protect_system_primary"
                assert _one(cur, "SELECT count(*) FROM agents WHERE agent_kind = 'system_primary'") == 1
                print("PASS: C14 system_primary DELETE and kind-flip remain blocked by the 07C trigger after bootstrap")

                # C16 — no queue-manager / reservation / claim structures (name check Python-side:
                # a literal % in SQL would collide with the driver's placeholder parsing).
                cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                names_in_db = [r[0] for r in cur.fetchall()]
                offenders = [t for t in names_in_db if any(tok in t for tok in ("queue", "reservation", "claim"))]
                assert not offenders, f"no queue/reservation/claim table may exist: {offenders}"
                print("PASS: C16 no queue-manager / reservation / claim table exists")

                # C17 — tenancy is PHYSICAL: no TENANT BUSINESS table carries a tenant_id column
                # (the 07C V5 §13 invariant, scoped exactly as 07C's own guard scopes it). The
                # bootstrap `import_job` table's tenant_id (lineage/001, blob-pinned since Phase 6)
                # is the PRE-EXISTING IC-003 import-provenance field — not shared-DB tenancy.
                cur.execute("SELECT table_name FROM information_schema.columns WHERE table_schema = 'public' AND column_name = 'tenant_id'")
                tid_tables = {r[0] for r in cur.fetchall()}
                business_offenders = tid_tables & set(_TENANT_BUSINESS_TABLES)
                assert not business_offenders, f"no tenant business table may carry tenant_id: {sorted(business_offenders)}"
                assert tid_tables <= {"import_job"}, f"unexpected tenant_id column beyond IC-003 import_job: {sorted(tid_tables)}"
                print("PASS: C17 no tenant_id column in the tenant business tables (physical multi-DB; import_job's is IC-003)")
        finally:
            pa.close()

        # C18 — the Control-DB reference holds NO tenant operational tables.
        ctl = psycopg.connect(_pg.swap_db(admin_dsn, _CTL_DB))
        try:
            with ctl.cursor() as cur:
                for table in ("agents", "startups", "investors", "deals"):
                    assert _one(cur, "SELECT to_regclass(%s)", (table,)) is None, (
                        f"tenant operational table {table} must NOT exist in the Control DB"
                    )
        finally:
            ctl.close()
        print("PASS: C18 Control-DB reference holds no tenant operational tables")

        out_b = _onboard(orch, tids[1], "c-b")
        assert out_b.result is DistinctnessResult.VERIFIED, out_b.reason
        rec_b = store.get_tenant(tids[1])
        assert rec_b is not None and rec_b.lifecycle_state is TenantLifecycleState.READY
        print("PASS: C3 tenant B onboarded to its own distinct physical DB -> VERIFIED (cross-tenant distinctness)")

        for r in store.list_audit():
            assert admin_dsn not in repr(r), "C6 secret hygiene: a DSN must never appear in audit records (D-14)"
        assert events.TENANT_SCHEMA_APPLICATION_SUCCEEDED in [r.action for r in store.list_audit()]
        print("PASS: C6 secret hygiene (no DSN in audit records) + schema-application audited")
    finally:
        _cleanup(psycopg, admin_dsn, tids)


def test_non_vacuity_without_step2b_verify_fails(admin_dsn: str) -> None:
    """C8: with a no-op applicator the real tenant DB has no schema -> verify fails closed (NOT Ready);
    with the real applicator the SAME flow reaches Ready. Proves Step 2b is load-bearing (not vacuous)."""
    psycopg = _psycopg()
    tid = "b7benv"

    orch_noop, store_noop = _build(psycopg, admin_dsn, real_applicator=False)
    try:
        _drop_db(psycopg, admin_dsn, tenant_database_name(tid))
        out = _onboard(orch_noop, tid, "c-nv1")
        assert out.result is not DistinctnessResult.VERIFIED, "without Step 2b the tenant must NOT reach VERIFIED"
        rec = store_noop.get_tenant(tid)
        assert rec is not None and rec.lifecycle_state is not TenantLifecycleState.READY
        print("PASS: C8 non-vacuity NEGATIVE (no Step 2b effect -> schema_version absent -> verify fails closed -> NOT Ready)")
    finally:
        _cleanup(psycopg, admin_dsn, [tid])

    orch_real, store_real = _build(psycopg, admin_dsn, real_applicator=True)
    try:
        _drop_db(psycopg, admin_dsn, tenant_database_name(tid))
        out2 = _onboard(orch_real, tid, "c-nv2")
        assert out2.result is DistinctnessResult.VERIFIED, out2.reason
        rec2 = store_real.get_tenant(tid)
        assert rec2 is not None and rec2.lifecycle_state is TenantLifecycleState.READY
        print("PASS: C8 non-vacuity POSITIVE (with Step 2b -> schema applied -> VERIFIED -> READY)")
    finally:
        _cleanup(psycopg, admin_dsn, [tid])


def test_schema_application_atomic_rollback(admin_dsn: str) -> None:
    """C4: a failing statement mid-apply rolls the WHOLE transaction back (no partial schema) and raises."""
    psycopg = _psycopg()
    from control_plane.adapters.providers.postgres_provisioning_operator import PostgresProvisioningOperator
    from control_plane.adapters.providers.postgres_tenant_schema_applicator import PostgresTenantSchemaApplicator

    tid = "b7bero"
    target = tenant_database_name(tid)
    secret_store = _HarnessSecretStore(admin_dsn)
    operator = PostgresProvisioningOperator(admin_dsn)

    fd, bad_name = tempfile.mkstemp(suffix=".sql")
    os.close(fd)
    bad_path = pathlib.Path(bad_name)
    # A second template that errors AFTER 001 created schema_version (same transaction) -> rollback.
    bad_path.write_text("SELECT * FROM __sp2_nonexistent_table_for_rollback__;\n", encoding="utf-8")
    applicator = PostgresTenantSchemaApplicator(secret_store, ddl_paths=[_DDL_BLOBS[0][0], bad_path])
    try:
        _drop_db(psycopg, admin_dsn, target)
        operator.provision(tid, target=target)
        raised = False
        try:
            applicator.apply_schema(tid, target=target, association_ref=SecretRef(store_ref=target, version="1"))
        except TenantSchemaApplicationError:
            raised = True
        assert raised, "a failing DDL statement must raise TenantSchemaApplicationError (fail-closed)"

        t = psycopg.connect(_pg.swap_db(admin_dsn, target))
        try:
            with t.cursor() as cur:
                assert _one(cur, "SELECT to_regclass('schema_version')") is None, (
                    "atomic rollback violated: schema_version was committed despite a later failure"
                )
        finally:
            t.close()
        print("PASS: C4 atomic rollback (failing DDL -> TenantSchemaApplicationError -> NO partial schema committed)")
    finally:
        _drop_db(psycopg, admin_dsn, target)
        for role in _CLUSTER_ROLES:
            _drop_role(psycopg, admin_dsn, role)
        try:
            bad_path.unlink()
        except Exception:
            pass


def test_schema_application_idempotent_reapply(admin_dsn: str) -> None:
    """C5: applying the real schema twice is a no-op (schema_version stays one row; lineage intact)."""
    psycopg = _psycopg()
    from control_plane.adapters.providers.postgres_provisioning_operator import PostgresProvisioningOperator
    from control_plane.adapters.providers.postgres_tenant_schema_applicator import PostgresTenantSchemaApplicator

    tid = "b7beidem"
    target = tenant_database_name(tid)
    secret_store = _HarnessSecretStore(admin_dsn)
    operator = PostgresProvisioningOperator(admin_dsn)
    applicator = PostgresTenantSchemaApplicator(secret_store)
    ref = SecretRef(store_ref=target, version="1")
    try:
        _drop_db(psycopg, admin_dsn, target)
        operator.provision(tid, target=target)
        applicator.apply_schema(tid, target=target, association_ref=ref)
        applicator.apply_schema(tid, target=target, association_ref=ref)  # second apply: no error
        t = psycopg.connect(_pg.swap_db(admin_dsn, target))
        try:
            with t.cursor() as cur:
                assert _one(cur, "SELECT count(*) FROM schema_version") == 1, "re-apply must not re-seed (idempotent)"
                assert _one(cur, "SELECT to_regclass('lineage')") is not None, "lineage must remain present"
                # C12 (PRD 07B.1): the full-set re-apply (13 files + seed, twice) leaves EXACTLY ONE
                # System Primary — the WHERE NOT EXISTS seed and the DROP-TRIGGER-recreate are both no-ops.
                assert _one(cur, "SELECT count(*) FROM agents WHERE agent_kind = 'system_primary'") == 1, (
                    "full-set idempotent retry must preserve exactly one system_primary row"
                )
                assert _one(cur, "SELECT count(*) FROM agents") == 1, "re-apply must not add agents rows"
        finally:
            t.close()
        print("PASS: C5 idempotent re-apply (no error; schema_version=1 row; lineage present)")
        print("PASS: C12 full-set idempotent retry preserves exactly one system_primary row")
    finally:
        _drop_db(psycopg, admin_dsn, target)
        for role in _CLUSTER_ROLES:
            _drop_role(psycopg, admin_dsn, role)


def test_composed_late_failure_and_seed_failure_rollback(admin_dsn: str) -> None:
    """C20 (07C-AT-2): rollback proofs for the COMPOSED 13-file Step-2b transaction.
    (a) a failing statement AFTER all 13 composed files rolls the ENTIRE transaction back — no
    bootstrap schema, no tenant schema, no System Primary row persists; (b) a seed-time failure
    (the module seed SQL patched to hit a nonexistent table — test-only, restored in finally)
    likewise rolls back all 13 applied files. Fail-closed both ways: TenantSchemaApplicationError."""
    psycopg = _psycopg()
    from control_plane.adapters.providers import postgres_tenant_schema_applicator as applicator_mod
    from control_plane.adapters.providers.postgres_provisioning_operator import PostgresProvisioningOperator

    tid = "b7b1late"
    target = tenant_database_name(tid)
    secret_store = _HarnessSecretStore(admin_dsn)
    operator = PostgresProvisioningOperator(admin_dsn)
    ref = SecretRef(store_ref=target, version="1")

    fd, bad_name = tempfile.mkstemp(suffix=".sql")
    os.close(fd)
    bad_path = pathlib.Path(bad_name)
    bad_path.write_text("SELECT * FROM __sp2_late_failure_after_composed_tenant_ddl__;\n", encoding="utf-8")
    try:
        _drop_db(psycopg, admin_dsn, target)
        operator.provision(tid, target=target)

        # (a) LATE failure: all 13 real templates apply, then a failing 14th path -> whole txn back.
        late = applicator_mod.PostgresTenantSchemaApplicator(
            secret_store, ddl_paths=[*applicator_mod.default_tenant_schema_ddl_paths(), bad_path]
        )
        raised = False
        try:
            late.apply_schema(tid, target=target, association_ref=ref)
        except TenantSchemaApplicationError:
            raised = True
        assert raised, "a late failure after the 13 composed files must raise TenantSchemaApplicationError"
        t = psycopg.connect(_pg.swap_db(admin_dsn, target))
        try:
            with t.cursor() as cur:
                assert _one(cur, "SELECT to_regclass('schema_version')") is None, "bootstrap schema must roll back"
                assert _one(cur, "SELECT to_regclass('agents')") is None, "tenant schema must roll back"
                assert _one(cur, "SELECT to_regclass('deals')") is None, "tenant schema must roll back entirely"
        finally:
            t.close()
        print("PASS: C20a late failure after the 13 composed files -> ENTIRE transaction rolled back (no partial schema, no SP)")

        # (b) SEED-time failure: the seed itself fails -> all 13 applied DDL files roll back.
        original_seed = applicator_mod._SYSTEM_PRIMARY_SEED_SQL
        applicator_mod._SYSTEM_PRIMARY_SEED_SQL = "INSERT INTO __sp2_seed_failure_probe__ VALUES (1)"
        try:
            real = applicator_mod.PostgresTenantSchemaApplicator(secret_store)
            raised2 = False
            try:
                real.apply_schema(tid, target=target, association_ref=ref)
            except TenantSchemaApplicationError:
                raised2 = True
            assert raised2, "a seed-time failure must raise TenantSchemaApplicationError"
        finally:
            applicator_mod._SYSTEM_PRIMARY_SEED_SQL = original_seed
        t2 = psycopg.connect(_pg.swap_db(admin_dsn, target))
        try:
            with t2.cursor() as cur:
                assert _one(cur, "SELECT to_regclass('schema_version')") is None, "seed failure must roll back bootstrap DDL"
                assert _one(cur, "SELECT to_regclass('agents')") is None, "seed failure must roll back tenant DDL"
        finally:
            t2.close()
        print("PASS: C20b seed-time failure -> all 13 applied DDL files rolled back (fail-closed, no partial schema)")

        # sanity: with the REAL seed restored, the same tenant DB then bootstraps cleanly end-to-end.
        applicator_mod.PostgresTenantSchemaApplicator(secret_store).apply_schema(tid, target=target, association_ref=ref)
        t3 = psycopg.connect(_pg.swap_db(admin_dsn, target))
        try:
            with t3.cursor() as cur:
                assert _one(cur, "SELECT count(*) FROM agents WHERE agent_kind = 'system_primary'") == 1
        finally:
            t3.close()
        print("PASS: C20 recovery — after the rollbacks the real composed apply still succeeds with one SP")
    finally:
        _drop_db(psycopg, admin_dsn, target)
        for role in _CLUSTER_ROLES:
            _drop_role(psycopg, admin_dsn, role)
        try:
            bad_path.unlink()
        except Exception:
            pass


def test_seed_race_two_connection_classification(admin_dsn: str) -> None:
    """C19 (07C-AT-5): TRUE two-connection System Primary seed race, classified fail-closed.

    Two independent connections run the SEED PATH with deterministic overlap: connection W executes
    the seed and holds it UNCOMMITTED; the loser — the REAL applicator with ddl_paths=[] (isolating
    exactly the in-transaction seed seam) — passes WHERE NOT EXISTS (no committed SP visible),
    INSERTs, and blocks on the 07C singleton index; once W commits, the loser's raw UniqueViolation
    is classified by apply_schema as TenantSchemaApplicationError (never a raw driver exception past
    the boundary), its transaction rolls back, and exactly one System Primary row remains.

    REACHABILITY CAVEAT (exec-auth package §14): the normal onboarding path cannot naturally race
    two same-DB Step-2b applies (provision's CREATE DATABASE serializes/precludes it), so the race
    is isolated at the Step-2b seed seam after schema creation, as the package explicitly allows."""
    psycopg = _psycopg()
    from control_plane.adapters.providers import postgres_tenant_schema_applicator as applicator_mod
    from control_plane.adapters.providers.postgres_provisioning_operator import PostgresProvisioningOperator

    tid = "b7b1race"
    target = tenant_database_name(tid)
    secret_store = _HarnessSecretStore(admin_dsn)
    operator = PostgresProvisioningOperator(admin_dsn)

    w = None
    try:
        _drop_db(psycopg, admin_dsn, target)
        operator.provision(tid, target=target)
        # Schema WITHOUT a seed (the applicator always seeds): apply the 13 read-only templates
        # directly so the agents table exists with ZERO rows, leaving the seed race fully open.
        setup = psycopg.connect(_pg.swap_db(admin_dsn, target))
        try:
            with setup.cursor() as cur:
                for path in applicator_mod.default_tenant_schema_ddl_paths():
                    cur.execute(path.read_text(encoding="utf-8"))
            setup.commit()
        finally:
            setup.close()

        # Connection W: the WINNING seed — executed and held UNCOMMITTED (overlap window open).
        w = psycopg.connect(_pg.swap_db(admin_dsn, target))
        w.execute(applicator_mod._SYSTEM_PRIMARY_SEED_SQL)

        # The LOSER: the real applicator seed seam in a second connection, on its own thread
        # (its INSERT will block on the singleton index until W's transaction resolves).
        outcome: dict = {}

        def _loser() -> None:
            try:
                loser = applicator_mod.PostgresTenantSchemaApplicator(secret_store, ddl_paths=[])
                loser.apply_schema(tid, target=target, association_ref=SecretRef(store_ref=target, version="1"))
                outcome["result"] = "no-error"
            except TenantSchemaApplicationError:
                outcome["result"] = "classified"  # fail-closed, wrapped — NOT a raw driver exception
            except Exception as exc:  # a raw driver exception leaking past the boundary = FAIL
                outcome["result"] = f"raw:{type(exc).__name__}"

        loser_thread = threading.Thread(target=_loser)
        loser_thread.start()

        # Deterministic overlap proof: wait until the loser is visibly LOCK-blocked on W's txn.
        mon = psycopg.connect(admin_dsn, autocommit=True)
        try:
            deadline = time.time() + 30
            blocked = False
            while time.time() < deadline:
                with mon.cursor() as cur:
                    n = _one(
                        cur,
                        "SELECT count(*) FROM pg_stat_activity WHERE datname = %s AND wait_event_type = 'Lock'",
                        (target,),
                    )
                if n and n >= 1:
                    blocked = True
                    break
                time.sleep(0.05)
            assert blocked, "the losing seed never blocked on the singleton — two-connection overlap not established"
        finally:
            mon.close()
        print("PASS: C19 overlap established (loser LOCK-blocked on the singleton while winner uncommitted)")

        w.commit()  # winner commits -> loser's INSERT raises the singleton UniqueViolation
        loser_thread.join(timeout=30)
        assert not loser_thread.is_alive(), "loser thread must finish after the winner commits"
        assert outcome.get("result") == "classified", (
            f"the losing concurrent seed must be classified as TenantSchemaApplicationError, got: {outcome.get('result')}"
        )

        check = psycopg.connect(_pg.swap_db(admin_dsn, target))
        try:
            with check.cursor() as cur:
                assert _one(cur, "SELECT count(*) FROM agents WHERE agent_kind = 'system_primary'") == 1
                assert _one(cur, "SELECT count(*) FROM agents") == 1, "the loser must leave NO second row (rolled back)"
        finally:
            check.close()
        print("PASS: C19 two-connection seed race — one SP committed; loser classified fail-closed (TenantSchemaApplicationError)")
    finally:
        if w is not None:
            try:
                w.close()  # close BEFORE the drop so an aborted winner txn cannot block it
            except Exception:
                pass
        _drop_db(psycopg, admin_dsn, target)
        for role in _CLUSTER_ROLES:
            _drop_role(psycopg, admin_dsn, role)


if __name__ == "__main__":
    _pg.run(
        [
            test_e2e_onboard_applies_schema_and_reaches_ready,
            test_non_vacuity_without_step2b_verify_fails,
            test_schema_application_atomic_rollback,
            test_schema_application_idempotent_reapply,
            test_composed_late_failure_and_seed_failure_rollback,
            test_seed_race_two_connection_classification,
        ]
    )
