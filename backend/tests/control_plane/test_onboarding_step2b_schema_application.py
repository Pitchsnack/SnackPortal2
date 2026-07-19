"""PRD 07B / PRD 07B.1 — onboarding Step 2b (tenant schema application) wiring (no live PG).

Pins the schema-application step the onboarding orchestrator runs between database provision and
verification: ordering, fail-closed semantics, the idempotency guard, the in-memory applicator port
contract, and the controlled-non-prod composition (default in-memory; since PRD 07D-1 the
'postgres' value SELECTS the real applicator lazily, and unknown values fail closed). No live
PostgreSQL (that is the requires_pg harness); the PRD 07B.1 tests import the postgres applicator
module (the psycopg dependency is import-only here — the b7b default-suite precedent) and exercise
it against a RECORDING fake connection, never a real one. Standalone-runnable:
`python tests/control_plane/test_onboarding_step2b_schema_application.py`.

PRD 07B.1 additions pin the composed Step-2b surface: `default_tenant_schema_ddl_paths()` returns
the six 07B bootstrap templates FIRST then the seven 07C tenant business files in the 07C-owned
machine-readable TENANT_DDL_APPLY_ORDER (asserted against the guard's AST — C7 Option 2: no
duplicated tenant pins); the System Primary seed is in-applicator, in-transaction, executed after
the DDL loop and before the single commit; a seed failure is wrapped fail-closed as
`TenantSchemaApplicationError` with rollback; 07B.1 authors no DDL and introduces no
queue-manager / reservation / claim-lock construct.

The deeper "no tenant reaches Ready on live PG without Step 2b" non-vacuity is proven by
`requires_pg/test_pg_onboarding_e2e_schema_application.py`; here the load-bearing-ness is shown at
unit level (a failing applicator fails closed and never reaches the gate).
"""

from __future__ import annotations

import ast
import os
import pathlib
import sys
from types import SimpleNamespace
from typing import Any, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))  # backend on path

from control_plane import events  # noqa: E402
from control_plane import main as cp_main  # noqa: E402
from control_plane.adapters.providers import postgres_tenant_schema_applicator as applicator_mod  # noqa: E402
from control_plane.adapters.providers.in_memory_distinctness import (  # noqa: E402
    nonprod_control_db_evidence,
)
from control_plane.adapters.providers.in_memory_probe import InMemoryTenantDatabaseProbe  # noqa: E402
from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.adapters.providers.in_memory_tenant_schema_applicator import (  # noqa: E402
    InMemoryTenantSchemaApplicator,
)
from control_plane.audit import ControlPlaneAudit  # noqa: E402
from control_plane.distinctness import DistinctnessResult  # noqa: E402
from control_plane.onboarding import OnboardingOrchestrator, tenant_dsn_ref  # noqa: E402
from control_plane.provisioning import (  # noqa: E402
    InMemoryProvisioningOperator,
    ProvisioningVerificationService,
    TenantSchemaApplicationError,
    TenantSchemaApplicator,
    tenant_database_name,
)
from control_plane.records import TenantLifecycleState  # noqa: E402
from control_plane.registry import TenantRegistry  # noqa: E402
from shared.secrets import SecretRef, SecretStore, SecretValue  # noqa: E402

_ORG = "org_ref_x"
_FED = "fed_ref_x"

# The six 07B bootstrap templates (provisioning then lineage), the head of the composed order.
_BOOTSTRAP_SIX = [
    "001_tenant_database.sql",
    "002_distinctness_sentinel.sql",
    "003_provisioning_role.sql",
    "001_lineage_schema.sql",
    "002_append_only.sql",
    "003_roles.sql",
]


def _tenant_apply_order_from_guard() -> List[str]:
    """TENANT_DDL_APPLY_ORDER parsed from 07C's machine-readable guard authority.

    AST literal extraction — no import, no side effects. C7 Option 2: 07B.1 asserts against the
    07C-owned order; it does not restate an independent order or duplicate blob pins."""
    guard = pathlib.Path(__file__).resolve().parents[1] / "architecture" / "test_tenant_ddl_blob_drift.py"
    for node in ast.parse(guard.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "TENANT_DDL_APPLY_ORDER" for t in node.targets):
            order = ast.literal_eval(node.value)
            assert isinstance(order, list) and order, "TENANT_DDL_APPLY_ORDER must be a non-empty list"
            return order
    raise AssertionError("TENANT_DDL_APPLY_ORDER not found in the 07C tenant blob-drift guard")


class _StaticSecretStore(SecretStore):
    """Test-only D-14 store: resolves any ref to an opaque non-DSN marker (never connected to)."""

    def resolve(self, ref: SecretRef) -> SecretValue:
        return SecretValue(material="resolved-descriptor-by-ref-only")

    def current_version(self, store_ref: str) -> str:
        return "1"


class _RecordingCursor:
    def __init__(self, conn: "_RecordingConn") -> None:
        self._conn = conn

    def __enter__(self) -> "_RecordingCursor":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        # EXACT-equality failure hook (Governed CI Live-PG Bundle, AT-07B1-1): a substring hook would
        # false-fire on 001_agents.sql's header COMMENT (it quotes the seed SQL verbatim), making a
        # "seed failure" fire at DDL file #7 and never reach the seed statement.
        if self._conn.fail_on_exact is not None and sql == self._conn.fail_on_exact:
            raise RuntimeError("forced statement failure")
        self._conn.executed.append(sql)


class _RecordingConn:
    """Recording fake connection: captures executed SQL and commit/rollback POSITION; no I/O.

    Commit/rollback append "COMMIT"/"ROLLBACK" markers into the executed stream (AT-07B1-2) so ordering
    asserts can pin seed-BEFORE-commit — a commit-before-seed mutant is indistinguishable by counters."""

    def __init__(self, fail_on_exact: Optional[str] = None) -> None:
        self.executed: List[str] = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.fail_on_exact = fail_on_exact

    def cursor(self) -> _RecordingCursor:
        return _RecordingCursor(self)

    def commit(self) -> None:
        self.commits += 1
        self.executed.append("COMMIT")

    def rollback(self) -> None:
        self.rollbacks += 1
        self.executed.append("ROLLBACK")

    def close(self) -> None:
        self.closed = True


def _apply_with_fake_conn(conn: _RecordingConn) -> None:
    """Run the REAL postgres applicator against the recording fake (module psycopg swapped and
    restored — no pytest fixture, so the file stays standalone-runnable)."""
    saved = applicator_mod.psycopg
    applicator_mod.psycopg = SimpleNamespace(connect=lambda *a, **k: conn)  # type: ignore[assignment]
    try:
        app = applicator_mod.PostgresTenantSchemaApplicator(_StaticSecretStore())
        app.apply_schema("t1", target=tenant_database_name("t1"), association_ref=SecretRef(store_ref="sp2_tenant_t1", version="1"))
    finally:
        applicator_mod.psycopg = saved


class _RecordingApplicator(TenantSchemaApplicator):
    """Records each apply_schema call (tenant_id, target, association_ref); applies nothing."""

    def __init__(self) -> None:
        self.calls: List[Tuple[str, str, SecretRef]] = []

    def apply_schema(self, tenant_id: str, *, target: str, association_ref: SecretRef) -> None:
        self.calls.append((tenant_id, target, association_ref))


class _FailingApplicator(TenantSchemaApplicator):
    """Applicator whose schema-application step fails (fail-closed branch exercise)."""

    def apply_schema(self, tenant_id: str, *, target: str, association_ref: SecretRef) -> None:
        raise TenantSchemaApplicationError("forced failure")


def _orchestrator(store: InMemoryControlStore, *, applicator: Optional[TenantSchemaApplicator] = None) -> OnboardingOrchestrator:
    audit = ControlPlaneAudit(store)
    registry = TenantRegistry(store, audit)
    gate = ProvisioningVerificationService(
        store,
        audit,
        InMemoryTenantDatabaseProbe(schema_version="1"),
        # 07D-1: the composition root's canonical-ref-aware in-memory evidence (the association
        # carries `tenant/<id>/dsn`, not the target name — the base provider alone would misroute).
        cp_main.CanonicalTenantRefInMemoryEvidence(),
        nonprod_control_db_evidence(),
        supported_schema_versions=["1"],
    )
    return OnboardingOrchestrator(registry, InMemoryProvisioningOperator(), gate, audit, applicator or InMemoryTenantSchemaApplicator())


def _onboard(orch: OnboardingOrchestrator, tenant_id: str = "t1", correlation_id: str = "c1") -> DistinctnessResult:
    return orch.onboard(tenant_id, organization_ref=_ORG, federation_config_ref=_FED, actor="ops_ref", correlation_id=correlation_id).result


def _actions(store: InMemoryControlStore) -> List[str]:
    return [r.action for r in store.list_audit()]


def _state(store: InMemoryControlStore, tenant_id: str = "t1") -> TenantLifecycleState:
    rec = store.get_tenant(tenant_id)
    assert rec is not None
    return rec.lifecycle_state


def test_step2b_emitted_between_provision_and_verify() -> None:
    store = InMemoryControlStore()
    assert _onboard(_orchestrator(store)) is DistinctnessResult.VERIFIED
    acts = _actions(store)
    # Step 2b is bracketed by PROVISION_SUCCEEDED before and DISTINCTNESS_VERIFICATION_STARTED after.
    i_prov = acts.index(events.DATABASE_PROVISION_SUCCEEDED)
    i_started = acts.index(events.TENANT_SCHEMA_APPLICATION_STARTED)
    i_ok = acts.index(events.TENANT_SCHEMA_APPLICATION_SUCCEEDED)
    i_verify = acts.index(events.DISTINCTNESS_VERIFICATION_STARTED)
    assert i_prov < i_started < i_ok < i_verify, acts


def test_step2b_failure_fails_closed_and_skips_verify() -> None:
    store = InMemoryControlStore()
    result = _onboard(_orchestrator(store, applicator=_FailingApplicator()))
    assert result is not DistinctnessResult.VERIFIED
    assert _state(store) is not TenantLifecycleState.READY
    acts = _actions(store)
    assert events.TENANT_SCHEMA_APPLICATION_FAILED in acts
    assert events.TENANT_SCHEMA_APPLICATION_SUCCEEDED not in acts
    assert events.DISTINCTNESS_VERIFICATION_STARTED not in acts  # never reached the gate (fail-closed)


def test_step2b_success_reaches_ready() -> None:
    store = InMemoryControlStore()
    assert _onboard(_orchestrator(store)) is DistinctnessResult.VERIFIED
    assert _state(store) is TenantLifecycleState.READY
    acts = _actions(store)
    assert events.TENANT_SCHEMA_APPLICATION_SUCCEEDED in acts


def test_step2b_invoked_with_tenant_association() -> None:
    store = InMemoryControlStore()
    rec = _RecordingApplicator()
    assert _onboard(_orchestrator(store, applicator=rec)) is DistinctnessResult.VERIFIED
    assert len(rec.calls) == 1, rec.calls
    tenant_id, target, association_ref = rec.calls[0]
    assert tenant_id == "t1"
    assert target == tenant_database_name("t1")
    # The association passed to the applicator is the CANONICAL tenant DSN reference (PRD 07D-1
    # D-A; D-14: by reference only) — the provisioned target name travels separately (above).
    assert association_ref.store_ref == tenant_dsn_ref("t1") == "tenant/t1/dsn"
    assert association_ref.store_ref != tenant_database_name("t1"), "the ref is a secret location, not the target name"


def test_in_memory_applicator_records_and_never_fails() -> None:
    app = InMemoryTenantSchemaApplicator()
    app.apply_schema("t1", target="sp2_tenant_t1", association_ref=SecretRef(store_ref="sp2_tenant_t1", version="1"))
    assert app.applied == [("t1", "sp2_tenant_t1")]


def test_idempotent_onboard_does_not_reapply() -> None:
    store = InMemoryControlStore()
    rec = _RecordingApplicator()
    orch = _orchestrator(store, applicator=rec)
    assert _onboard(orch) is DistinctnessResult.VERIFIED
    assert len(rec.calls) == 1
    # A second onboard on an already-Ready tenant is a no-op (idempotency guard) — no re-apply.
    orch.onboard("t1", organization_ref=_ORG, federation_config_ref=_FED, actor="ops_ref", correlation_id="c2")
    assert len(rec.calls) == 1, "Step 2b must not re-apply on an already-onboarded tenant"


def test_non_vacuity_step2b_is_load_bearing() -> None:
    # Same in-memory verify path: a SUCCEEDING applicator reaches Ready and DID invoke apply_schema;
    # a FAILING applicator does NOT reach Ready and never starts verify. The differing outcomes prove
    # Step 2b is on the load-bearing path (not a vacuous no-op).
    ok_store, rec = InMemoryControlStore(), _RecordingApplicator()
    assert _onboard(_orchestrator(ok_store, applicator=rec)) is DistinctnessResult.VERIFIED
    assert len(rec.calls) == 1 and _state(ok_store) is TenantLifecycleState.READY

    bad_store = InMemoryControlStore()
    assert _onboard(_orchestrator(bad_store, applicator=_FailingApplicator())) is not DistinctnessResult.VERIFIED
    assert _state(bad_store) is not TenantLifecycleState.READY


def test_schema_applicator_default_in_memory() -> None:
    # PRD 07B / OB-1 parity: env unset -> in-memory applicator; onboarding reaches Ready with no I/O.
    saved = os.environ.pop(cp_main.TENANT_SCHEMA_APPLICATOR_ENV, None)
    try:
        cp = cp_main.ControlPlane()
        assert isinstance(cp.schema_applicator, InMemoryTenantSchemaApplicator)
        out = cp.onboarding.onboard("t9", organization_ref=_ORG, federation_config_ref=_FED, actor="ops_ref", correlation_id="c9")
        assert out.result is DistinctnessResult.VERIFIED
        assert _state(cp.store, "t9") is TenantLifecycleState.READY
    finally:
        if saved is not None:
            os.environ[cp_main.TENANT_SCHEMA_APPLICATOR_ENV] = saved


def test_schema_applicator_postgres_selectable_and_unknown_fails_closed() -> None:
    # PRD 07D-1 (was: deferred), under the PRD 07D-2a coherence matrix: applicator-ALONE=postgres
    # is now a FORBIDDEN mix (RULE 1 — real DDL against an un-provisioned/arbitrary target); the
    # real applicator is selected via the ALL-FOUR-postgres composition (lazy — construction
    # applies nothing and opens no connection); any unknown value still fails closed (ValueError).
    all_envs = (
        cp_main.CONTROL_STORE_ENV,
        cp_main.PROVISIONING_ADAPTER_ENV,
        cp_main.TENANT_SCHEMA_APPLICATOR_ENV,
        cp_main.DISTINCTNESS_LEDGER_ENV,
    )
    saved = {name: os.environ.get(name) for name in all_envs}
    try:
        # applicator-alone -> forbidden mix (fail closed at construction).
        for name in all_envs:
            os.environ.pop(name, None)
        os.environ[cp_main.TENANT_SCHEMA_APPLICATOR_ENV] = "postgres"
        raised = False
        try:
            cp_main.ControlPlane()
        except ValueError:
            raised = True
        assert raised, "applicator-alone=postgres must fail closed (07D-2a RULE 1 forbidden mix)"
        # all-four postgres -> the real applicator is selected (lazy).
        for name in all_envs:
            os.environ[name] = "postgres"
        cp = cp_main.ControlPlane()
        assert isinstance(cp.schema_applicator, applicator_mod.PostgresTenantSchemaApplicator), (
            "all-four postgres must select the real schema applicator"
        )
        # unknown applicator values still fail closed (with the other selectors unset).
        for name in all_envs:
            os.environ.pop(name, None)
        for value in ("durable", "true", "x"):
            os.environ[cp_main.TENANT_SCHEMA_APPLICATOR_ENV] = value
            raised = False
            try:
                cp_main.ControlPlane()
            except ValueError:
                raised = True
            assert raised, f"{value!r} must fail closed (ValueError)"
    finally:
        for name, old in saved.items():
            if old is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old


# --- PRD 07B.1: composed 13-file sequencing + in-transaction System Primary seed ------------------
def test_07b1_default_paths_compose_14_files_bootstrap_then_tenant() -> None:
    paths = applicator_mod.default_tenant_schema_ddl_paths()
    names = [p.name for p in paths]
    assert len(names) == 14, f"composed Step-2b DDL path count must be 14, got {len(names)}: {names}"
    assert names[:6] == _BOOTSTRAP_SIX, f"the six 07B bootstrap templates must come FIRST: {names[:6]}"
    families = [p.parent.name for p in paths]
    assert families == ["provisioning"] * 3 + ["lineage"] * 3 + ["tenant"] * 8, families
    missing = [str(p) for p in paths if not p.is_file()]
    assert not missing, f"referenced (read-only) DDL templates must exist: {missing}"


def test_07b1_tenant_order_matches_07c_authority() -> None:
    # C7 Option 2: the appended eight MUST equal 07C's machine-readable TENANT_DDL_APPLY_ORDER,
    # read from the guard itself (07C owns the order and the blob pins; 07B.1 duplicates neither).
    names = [p.name for p in applicator_mod.default_tenant_schema_ddl_paths()]
    assert names[6:] == _tenant_apply_order_from_guard(), (
        f"appended tenant files {names[6:]} must equal the 07C TENANT_DDL_APPLY_ORDER authority"
    )


def test_07b1_seed_sql_shape() -> None:
    seed = applicator_mod._SYSTEM_PRIMARY_SEED_SQL
    assert "INSERT INTO agents (agent_kind, agent_status, supervised_by_agent_id)" in seed
    assert "SELECT 'system_primary', 'active', NULL" in seed
    # exact idempotency predicate pinned by PRD 07B.1 §10:
    assert "WHERE NOT EXISTS (SELECT 1 FROM agents WHERE agent_kind = 'system_primary')" in seed
    seed_columns = [c.strip() for c in seed.split("(", 1)[1].split(")", 1)[0].split(",")]
    assert seed_columns == ["agent_kind", "agent_status", "supervised_by_agent_id"], seed_columns
    assert "id" not in seed_columns, "seed must omit id (GENERATED ALWAYS)"
    assert "queue" not in seed.lower() and "is_queue_manager" not in seed.lower()


def test_07b1_seed_executes_after_ddl_loop_before_commit() -> None:
    conn = _RecordingConn()
    _apply_with_fake_conn(conn)
    seed = applicator_mod._SYSTEM_PRIMARY_SEED_SQL
    expected_ddl = [p.read_text(encoding="utf-8") for p in applicator_mod.default_tenant_schema_ddl_paths()]
    assert conn.executed[:14] == expected_ddl, "all 14 templates must execute first, in order"
    assert conn.executed[14] == seed, "the seed must execute immediately AFTER the DDL loop"
    # position-pinned commit (AT-07B1-2): the seed strictly precedes the single COMMIT marker —
    # a commit-before-seed mutant fails here (counters alone cannot see ordering).
    assert conn.executed.count("COMMIT") == 1 and conn.executed.count("ROLLBACK") == 0
    assert conn.executed.index(seed) < conn.executed.index("COMMIT"), "seed must run BEFORE the commit"
    assert conn.executed[-1] == "COMMIT", "the single commit must be the FINAL action"
    assert conn.commits == 1 and conn.rollbacks == 0, "single commit AFTER the seed; no rollback"
    assert conn.closed, "connection must be closed"


def test_07b1_seed_failure_wrapped_fail_closed() -> None:
    # a failing SEED (the exact statement — not a DDL template) must roll the WHOLE transaction back
    # and surface as TenantSchemaApplicationError. The exact-equality hook cannot fire on 001_agents.sql's
    # header comment, so the failure provably occurs AT the seed, after all 14 templates executed.
    seed = applicator_mod._SYSTEM_PRIMARY_SEED_SQL
    conn = _RecordingConn(fail_on_exact=seed)
    raised = False
    try:
        _apply_with_fake_conn(conn)
    except TenantSchemaApplicationError:
        raised = True
    assert raised, "a seed failure must be classified as TenantSchemaApplicationError (fail-closed)"
    expected_ddl = [p.read_text(encoding="utf-8") for p in applicator_mod.default_tenant_schema_ddl_paths()]
    assert conn.executed[:14] == expected_ddl, "ALL 14 templates must have executed BEFORE the seed failed"
    assert seed not in conn.executed, "the seed raised before recording — it was the FAILING statement"
    assert conn.executed[-1] == "ROLLBACK" and conn.executed.count("COMMIT") == 0, "seed failure: rollback recorded, never a commit"
    assert conn.commits == 0 and conn.rollbacks == 1, "seed failure: rollback, never commit"
    assert conn.closed, "connection must be closed even on failure"


def test_07b1_applicator_authors_no_ddl_and_no_forbidden_terms() -> None:
    src = pathlib.Path(applicator_mod.__file__).read_text(encoding="utf-8")
    lowered = src.lower()
    # case-insensitive (AT-07B1-3): a lowercase "create table" is valid SQL and must not evade the check
    assert "create table" not in lowered, "07B.1 must not author DDL in runtime source (07C owns the agents table)"
    for term in ("queue_manager", "is_queue_manager", "reservation", "claim_lock"):
        assert term not in lowered, f"forbidden construct in the applicator source: {term}"


_TESTS = [
    test_step2b_emitted_between_provision_and_verify,
    test_step2b_failure_fails_closed_and_skips_verify,
    test_step2b_success_reaches_ready,
    test_step2b_invoked_with_tenant_association,
    test_in_memory_applicator_records_and_never_fails,
    test_idempotent_onboard_does_not_reapply,
    test_non_vacuity_step2b_is_load_bearing,
    test_schema_applicator_default_in_memory,
    test_schema_applicator_postgres_selectable_and_unknown_fails_closed,
    test_07b1_default_paths_compose_14_files_bootstrap_then_tenant,
    test_07b1_tenant_order_matches_07c_authority,
    test_07b1_seed_sql_shape,
    test_07b1_seed_executes_after_ddl_loop_before_commit,
    test_07b1_seed_failure_wrapped_fail_closed,
    test_07b1_applicator_authors_no_ddl_and_no_forbidden_terms,
]

if __name__ == "__main__":
    for _t in _TESTS:
        _t()
        print("PASS:", _t.__name__)
    print("ALL PASSED")
