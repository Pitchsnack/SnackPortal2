"""PRD 07B — tenant schema-application wiring, end-to-end on live PostgreSQL (standalone-only).

Proves the onboarding lifecycle now reaches Ready on a REAL physically-distinct tenant database
because onboarding Step 2b applies the tenant schema before verification:

    register -> provision physical DB (CREATE DATABASE) -> APPLY SCHEMA (Step 2b) -> associate ->
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
  C7  blob pins: the six applied DDL templates equal their reviewed git blobs (drift FAILs — do not fix DDL here).
  C8  NON-VACUITY: with a no-op applicator (no Step 2b effect) the real tenant DB has no schema_version, so
      verify fails closed and the tenant is NOT Ready; with the real applicator it reaches Ready.

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

import hashlib
import importlib
import os
import pathlib
import sys
import tempfile

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
        finally:
            t.close()
        print("PASS: C5 idempotent re-apply (no error; schema_version=1 row; lineage present)")
    finally:
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
        ]
    )
