"""PRD 07D-2b.2b — recovery compensation, orphan scan, and ownership-proof units (in-memory, no I/O).

Covers the recovery-core safety layer introduced by the first governed DROP DATABASE caller:

* the EXACT R1-3 bootstrap-only census (empty / bootstrap_only / non_empty; sentinel artifacts
  bootstrap-compatible; ANY extra table or business row => evidence, never dropped);
* the ownership-proof quintuple + explicit-only DeprovisionTenantDatabase (§7/§8): eligible
  positive paths (empty, bootstrap-only, Quarantined; absent-target idempotent no-op), every
  refusal leg (unknown tenant, ineligible state, non-canonical ref, non-empty content, ledger
  collision, fingerprint mismatch, Control-DB target, unavailable inspection/control identity,
  operator failure), the Requested/Completed/Failed event pairing, and the R1-5 quarantine
  eligibility rule ({Provisioning, Failed} only; already-Quarantined STAYS);
* the §7.1 TOCTOU pre-DROP re-validation (R1-9 — the MR-13 kill site);
* the read-only ScanForOrphans classification table (§9) — zero events, zero state change,
  credential-free deterministic report; fail-closed inventory/identity legs;
* the composition + mixed-posture facade (R1-2): cp.recovery / cp.orphan_scan exposed
  un-wrapped on MATCHED postures, denied pre-effect (zero events) in BOTH mix directions;
  the gate and the recovery services share ONE ledger instance; NO new env selector and no
  new ControlPlane.__init__ parameter are exercised anywhere here.

Pure stdlib; no driver connection; no live PostgreSQL (that is the requires_pg 07D harness).
Standalone-runnable: `python tests/control_plane/test_recovery_compensation.py`.
"""

from __future__ import annotations

import inspect as _inspect
import os
import pathlib
import sys
from dataclasses import replace
from typing import List, Optional, Set

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))  # backend on path

from control_plane import events  # noqa: E402
from control_plane import main as cp_main  # noqa: E402
from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.audit import ControlPlaneAudit  # noqa: E402
from control_plane.distinctness import DistinctnessEvidence, InMemoryDistinctnessLedger  # noqa: E402
from control_plane.onboarding import tenant_dsn_ref  # noqa: E402
from control_plane.provisioning import (  # noqa: E402
    InMemoryProvisioningOperator,
    ProvisioningError,
    tenant_database_name,
)
from control_plane.records import TenantLifecycleState, TenantRecord  # noqa: E402
from control_plane.recovery import (  # noqa: E402
    BOOTSTRAP_TABLE_SET,
    CLASS_ACTIVE_TENANT,
    CLASS_CONTROL_DB_TARGET,
    CLASS_ELIGIBLE_BOOTSTRAP_ONLY,
    CLASS_ELIGIBLE_EMPTY,
    CLASS_FINGERPRINT_MISMATCH,
    CLASS_LEDGER_COLLISION,
    CLASS_NO_REGISTRY_RECORD,
    CLASS_NON_EMPTY_EVIDENCE,
    CLASS_REGISTRY_NO_DATABASE,
    CLASS_UNINSPECTABLE,
    CONTENT_BOOTSTRAP_ONLY,
    CONTENT_EMPTY,
    CONTENT_NON_EMPTY,
    REASON_ABSENT_NOOP,
    REASON_CONTENT_NOT_EMPTY,
    REASON_CONTROL_TARGET,
    REASON_CONTROL_UNAVAILABLE,
    REASON_DEPROVISION_FAILED,
    REASON_DEPROVISIONED,
    REASON_FINGERPRINT_MISMATCH,
    REASON_INELIGIBLE_STATE,
    REASON_INSPECTION_UNAVAILABLE,
    REASON_LEDGER_COLLISION,
    REASON_NON_CANONICAL_REF,
    REASON_UNKNOWN_TENANT,
    DatabaseInspection,
    InMemoryRecoveryInspection,
    OrphanScanService,
    RecoveryCompensationService,
    RecoveryError,
    classify_content,
)
from control_plane.registry import TenantRegistry  # noqa: E402
from shared.secrets import SecretRef  # noqa: E402

_ORG, _FED = "org_ref_x", "fed_ref_x"
_CONTROL_NAME = "sp2_control"


class _SpyOperator(InMemoryProvisioningOperator):
    """In-memory operator that records deprovision calls (and can be made to fail)."""

    def __init__(self, *, fail: bool = False) -> None:
        super().__init__()
        self.fail = fail
        self.deprovision_calls: List[str] = []

    def deprovision(self, *, target: str) -> None:
        self.deprovision_calls.append(target)
        if self.fail:
            raise RuntimeError("deprovision failed")
        super().deprovision(target=target)


def _record(tenant_id: str, state: TenantLifecycleState, *, store_ref: Optional[str] = None) -> TenantRecord:
    return TenantRecord(
        tenant_id=tenant_id,
        organization_ref=_ORG,
        lifecycle_state=state,
        expected_schema_version="1",
        database_association_ref=SecretRef(store_ref=store_ref or tenant_dsn_ref(tenant_id), version="1"),
        federation_config_ref=_FED,
        created_at="t0",
        updated_at="t0",
    )


def _bootstrap_inspection(target: str, *, sentinel_rows: int = 3) -> DatabaseInspection:
    """A fully bootstrapped tenant database: every applicator table, the System Primary seed,
    the platform schema_version row, and sentinel artifacts (bootstrap-compatible)."""
    tables = {name: 0 for name in BOOTSTRAP_TABLE_SET}
    tables["public.agents"] = 1
    tables["public.schema_version"] = 1
    tables["dv_sentinel.marker"] = sentinel_rows
    return DatabaseInspection(
        database_name=target,
        system_identifier="cluster_a",
        database_identity=f"{target}:101",
        user_tables=tables,
        agents_total=1,
        agents_system_primary=1,
        schema_versions=("1",),
    )


def _plane(
    *,
    state: Optional[TenantLifecycleState] = TenantLifecycleState.PROVISIONING,
    tenant_id: str = "t1",
    store_ref: Optional[str] = None,
    operator: Optional[_SpyOperator] = None,
):
    """A minimal recovery plane: store/audit/registry + spy operator + inspection double."""
    store = InMemoryControlStore()
    audit = ControlPlaneAudit(store)
    registry = TenantRegistry(store, audit)
    op = operator or _SpyOperator()
    ledger = InMemoryDistinctnessLedger()
    inspection = InMemoryRecoveryInspection(
        control_database_name=_CONTROL_NAME,
        provisioned_view=lambda: set(op.provisioned),
    )
    if state is not None:
        store.put_tenant(_record(tenant_id, state, store_ref=store_ref))
    service = RecoveryCompensationService(registry, op, audit, inspection, ledger, supported_schema_versions=["1"])
    scan = OrphanScanService(store, inspection, ledger, supported_schema_versions=["1"])
    return store, audit, registry, op, ledger, inspection, service, scan


def _deprovision(service: RecoveryCompensationService, tenant_id: str = "t1", correlation_id: str = "c-dep"):
    return service.deprovision_tenant_database(tenant_id, actor="ops_ref", correlation_id=correlation_id)


def _actions(store: InMemoryControlStore) -> List[str]:
    return [r.action for r in store.list_audit()]


def _pairing(store: InMemoryControlStore) -> tuple:
    acts = _actions(store)
    return (
        acts.count(events.TENANT_DEPROVISION_REQUESTED),
        acts.count(events.TENANT_DEPROVISION_COMPLETED),
        acts.count(events.TENANT_DEPROVISION_FAILED),
    )


# --- the EXACT R1-3 census -------------------------------------------------------------------
def test_census_empty_database() -> None:
    insp = DatabaseInspection(database_name="sp2_tenant_t1", system_identifier="c", database_identity="d")
    assert classify_content(insp, supported_schema_versions=["1"]) == CONTENT_EMPTY


def test_census_bootstrap_only_full_schema_with_sentinel_rows() -> None:
    # Seed + platform schema_version row + UNRESTRICTED sentinel rows are bootstrap-compatible.
    insp = _bootstrap_inspection("sp2_tenant_t1", sentinel_rows=7)
    assert classify_content(insp, supported_schema_versions=["1"]) == CONTENT_BOOTSTRAP_ONLY


def test_census_sentinel_only_database_is_bootstrap_only() -> None:
    # A verification-artifact-only database (Readiness §23 R-3): sentinel table alone.
    insp = DatabaseInspection(
        database_name="sp2_tenant_t1",
        system_identifier="c",
        database_identity="d",
        user_tables={"dv_sentinel.marker": 4},
    )
    assert classify_content(insp, supported_schema_versions=["1"]) == CONTENT_BOOTSTRAP_ONLY


def test_census_extra_table_is_evidence() -> None:
    insp = _bootstrap_inspection("sp2_tenant_t1")
    tables = dict(insp.user_tables)
    tables["public.evil_extra"] = 0  # even an EMPTY extra table is evidence (R1-3)
    assert classify_content(replace(insp, user_tables=tables), supported_schema_versions=["1"]) == CONTENT_NON_EMPTY


def test_census_business_row_is_evidence() -> None:
    insp = _bootstrap_inspection("sp2_tenant_t1")
    tables = dict(insp.user_tables)
    tables["public.startups"] = 1
    assert classify_content(replace(insp, user_tables=tables), supported_schema_versions=["1"]) == CONTENT_NON_EMPTY


def test_census_agents_seed_rules() -> None:
    base = _bootstrap_inspection("sp2_tenant_t1")
    # two agents rows -> evidence
    two = dict(base.user_tables)
    two["public.agents"] = 2
    assert classify_content(replace(base, user_tables=two, agents_total=2), supported_schema_versions=["1"]) == CONTENT_NON_EMPTY
    # one row that is NOT the system_primary seed -> evidence
    assert classify_content(replace(base, agents_system_primary=0), supported_schema_versions=["1"]) == CONTENT_NON_EMPTY


def test_census_schema_version_rules() -> None:
    base = _bootstrap_inspection("sp2_tenant_t1")
    # a non-platform version row -> evidence
    assert classify_content(replace(base, schema_versions=("1", "999")), supported_schema_versions=["1"]) == CONTENT_NON_EMPTY


def test_census_unknown_row_count_fails_closed() -> None:
    base = _bootstrap_inspection("sp2_tenant_t1")
    tables = dict(base.user_tables)
    tables["public.deals"] = -1  # the adapter could not count -> never droppable
    assert classify_content(replace(base, user_tables=tables), supported_schema_versions=["1"]) == CONTENT_NON_EMPTY


def test_census_surfaced_matview_and_large_object_entries_are_evidence() -> None:
    # AT-PMV46-1 (PR #46 pre-merge V-1): the adapter surfaces materialized views / foreign
    # tables as census names with count -1 and large-object presence as a synthetic
    # pg_catalog entry — every such entry is outside the bootstrap set (or violates its
    # count rule) => non_empty => evidence, never dropped.
    base = _bootstrap_inspection("sp2_tenant_t1")
    snap = dict(base.user_tables)
    snap["public.evidence_snapshot"] = -1  # a surfaced materialized view (uncounted)
    assert classify_content(replace(base, user_tables=snap), supported_schema_versions=["1"]) == CONTENT_NON_EMPTY
    lo = dict(base.user_tables)
    lo["pg_catalog.pg_largeobject"] = 3  # the synthetic large-object presence entry
    assert classify_content(replace(base, user_tables=lo), supported_schema_versions=["1"]) == CONTENT_NON_EMPTY
    shadow = dict(base.user_tables)
    shadow["public.deals"] = -1  # a matview SHADOWING an allowed bootstrap name (relkind != 'r')
    assert classify_content(replace(base, user_tables=shadow), supported_schema_versions=["1"]) == CONTENT_NON_EMPTY
    assert "pg_catalog.pg_largeobject" not in BOOTSTRAP_TABLE_SET, "the synthetic entry must never be bootstrap-compatible"


# --- DeprovisionTenantDatabase: positive paths ------------------------------------------------
def test_deprovision_empty_database_succeeds_and_retains_registry_record() -> None:
    store, audit, registry, op, ledger, inspection, service, _ = _plane()
    target = tenant_database_name("t1")
    op.provision("t1", target=target)  # an EMPTY provisioned database
    out = _deprovision(service)
    assert out.dropped and out.completed and out.reason == REASON_DEPROVISIONED
    assert out.target == target
    assert op.deprovision_calls == [target], "the operator must be called exactly once"
    assert target not in op.provisioned
    assert _pairing(store) == (1, 1, 0), "Requested -> Completed exactly once each"
    rec = store.get_tenant("t1")
    assert rec is not None, "the registry record is RETAINED (never deleted)"
    assert rec.lifecycle_state is TenantLifecycleState.PROVISIONING, "deprovision changes no lifecycle state"


def test_deprovision_bootstrap_only_database_succeeds() -> None:
    store, audit, registry, op, ledger, inspection, service, _ = _plane(state=TenantLifecycleState.FAILED)
    inspection.set_database(_bootstrap_inspection(tenant_database_name("t1")))
    out = _deprovision(service)
    assert out.dropped and out.reason == REASON_DEPROVISIONED
    assert _pairing(store) == (1, 1, 0)
    rec = store.get_tenant("t1")
    assert rec is not None and rec.lifecycle_state is TenantLifecycleState.FAILED


def test_deprovision_quarantined_tenant_is_eligible() -> None:
    store, audit, registry, op, ledger, inspection, service, _ = _plane(state=TenantLifecycleState.QUARANTINED)
    inspection.set_database(_bootstrap_inspection(tenant_database_name("t1")))
    out = _deprovision(service)
    assert out.dropped and out.reason == REASON_DEPROVISIONED
    rec = store.get_tenant("t1")
    assert rec is not None and rec.lifecycle_state is TenantLifecycleState.QUARANTINED, "state unchanged"


def test_deprovision_absent_target_is_safe_noop_completed() -> None:
    store, audit, registry, op, ledger, inspection, service, _ = _plane()
    out = _deprovision(service)  # eligible tenant, target never provisioned -> absent
    assert not out.dropped and out.completed and out.reason == REASON_ABSENT_NOOP
    assert op.deprovision_calls == [], "an absent target must never reach the operator"
    assert _pairing(store) == (1, 1, 0), "idempotency is by OUTCOME (§8.3): a safe no-op Completed"


# --- DeprovisionTenantDatabase: refusal legs --------------------------------------------------
def test_deprovision_unknown_tenant_refused() -> None:
    store, audit, registry, op, ledger, inspection, service, _ = _plane(state=None)
    out = _deprovision(service, "ghost")
    assert not out.completed and out.reason == REASON_UNKNOWN_TENANT
    assert op.deprovision_calls == []
    assert _pairing(store) == (1, 0, 1), "explicitly requested -> Requested/Failed trail"


def test_deprovision_ineligible_states_refused_with_no_state_change() -> None:
    for state in (
        TenantLifecycleState.REGISTERED,
        TenantLifecycleState.VERIFYING,
        TenantLifecycleState.READY,
        TenantLifecycleState.SUSPENDED,
        TenantLifecycleState.DECOMMISSIONED,
    ):
        store, audit, registry, op, ledger, inspection, service, _ = _plane(state=state)
        op.provision("t1", target=tenant_database_name("t1"))
        out = _deprovision(service)
        assert not out.completed and out.reason == REASON_INELIGIBLE_STATE, state
        assert op.deprovision_calls == [], f"{state}: the operator must never be reached"
        rec = store.get_tenant("t1")
        assert rec is not None and rec.lifecycle_state is state, "zero state change (R1-5)"
        assert _pairing(store) == (1, 0, 1)


def test_deprovision_non_canonical_association_ref_refused() -> None:
    # An old-style raw-target ref cannot prove the canonical tenant<->database relationship.
    store, audit, registry, op, ledger, inspection, service, _ = _plane(store_ref="sp2_tenant_t1")
    op.provision("t1", target=tenant_database_name("t1"))
    out = _deprovision(service)
    assert not out.completed and out.reason == REASON_NON_CANONICAL_REF
    assert op.deprovision_calls == []
    rec = store.get_tenant("t1")
    assert rec is not None and rec.lifecycle_state is TenantLifecycleState.QUARANTINED, (
        "an integrity-class proof failure quarantines an eligible (Provisioning) tenant (R1-5)"
    )
    assert events.TENANT_QUARANTINED in _actions(store)


def test_deprovision_non_empty_database_never_dropped_and_quarantines() -> None:
    store, audit, registry, op, ledger, inspection, service, _ = _plane(state=TenantLifecycleState.FAILED)
    target = tenant_database_name("t1")
    insp = _bootstrap_inspection(target)
    tables = dict(insp.user_tables)
    tables["public.startups"] = 2  # business rows = evidence
    inspection.set_database(replace(insp, user_tables=tables))
    out = _deprovision(service)
    assert not out.completed and out.reason == REASON_CONTENT_NOT_EMPTY
    assert op.deprovision_calls == [], "MR-6 kill site: a non-empty database must NEVER be dropped"
    assert inspection.database_exists(target) is True, "the database is preserved as evidence"
    rec = store.get_tenant("t1")
    assert rec is not None and rec.lifecycle_state is TenantLifecycleState.QUARANTINED
    acts = _actions(store)
    assert "QuarantineTenant" in acts and events.TENANT_QUARANTINED in acts
    assert _pairing(store) == (1, 0, 1)


def test_deprovision_already_quarantined_stays_on_proof_failure() -> None:
    # R1-5: an already-QUARANTINED tenant STAYS (a re-quarantine would raise) — Failed only.
    store, audit, registry, op, ledger, inspection, service, _ = _plane(state=TenantLifecycleState.QUARANTINED)
    target = tenant_database_name("t1")
    insp = _bootstrap_inspection(target)
    tables = dict(insp.user_tables)
    tables["public.deals"] = 1
    inspection.set_database(replace(insp, user_tables=tables))
    out = _deprovision(service)
    assert not out.completed and out.reason == REASON_CONTENT_NOT_EMPTY
    rec = store.get_tenant("t1")
    assert rec is not None and rec.lifecycle_state is TenantLifecycleState.QUARANTINED
    acts = _actions(store)
    assert "QuarantineTenant" not in acts, "no re-quarantine transition may be attempted"
    assert _pairing(store) == (1, 0, 1)


def test_deprovision_ledger_collision_refused() -> None:
    # MR-7 kill site: another tenant's distinctness evidence names the same physical database.
    store, audit, registry, op, ledger, inspection, service, _ = _plane(state=TenantLifecycleState.FAILED)
    target = tenant_database_name("t1")
    inspection.set_database(_bootstrap_inspection(target))
    ledger.record_evidence(
        "other_tenant",
        DistinctnessEvidence(
            system_identifier="cluster_a",
            database_identity=f"{target}:101",
            observed_target=target,
            secret_ref_key="tenant/other_tenant/dsn",
            sentinel_namespace="dv_sentinel_other_tenant",
            sentinel_token="tok",
            sentinel_written=True,
        ),
    )
    out = _deprovision(service)
    assert not out.completed and out.reason == REASON_LEDGER_COLLISION
    assert op.deprovision_calls == []
    rec = store.get_tenant("t1")
    assert rec is not None and rec.lifecycle_state is TenantLifecycleState.QUARANTINED


def test_deprovision_own_fingerprint_mismatch_refused() -> None:
    # The tenant's OWN recorded identity disagrees with the observed database (swap/restore).
    store, audit, registry, op, ledger, inspection, service, _ = _plane(state=TenantLifecycleState.FAILED)
    target = tenant_database_name("t1")
    inspection.set_database(_bootstrap_inspection(target))
    ledger.record_evidence(
        "t1",
        DistinctnessEvidence(
            system_identifier="cluster_B",  # different cluster identity than the observed one
            database_identity=f"{target}:999",
            observed_target=target,
            secret_ref_key=tenant_dsn_ref("t1"),
            sentinel_namespace="dv_sentinel_t1",
            sentinel_token="tok",
            sentinel_written=True,
        ),
    )
    out = _deprovision(service)
    assert not out.completed and out.reason == REASON_FINGERPRINT_MISMATCH
    assert op.deprovision_calls == []
    rec = store.get_tenant("t1")
    assert rec is not None and rec.lifecycle_state is TenantLifecycleState.QUARANTINED


def test_deprovision_control_database_target_refused_before_operator() -> None:
    # MR-8 kill site: anything resolving to the Control database fails BEFORE the operator.
    store, audit, registry, op, ledger, inspection, service, _ = _plane()
    inspection._control_name = tenant_database_name("t1")  # the recomputed target IS the Control DB
    op.provision("t1", target=tenant_database_name("t1"))
    out = _deprovision(service)
    assert not out.completed and out.reason == REASON_CONTROL_TARGET
    assert op.deprovision_calls == [], "the Control database is never droppable"
    assert _pairing(store) == (1, 0, 1)


def test_deprovision_control_identity_unavailable_fails_closed() -> None:
    # Transient/environmental: refuse with NO quarantine transition and zero state change.
    store, audit, registry, op, ledger, inspection, service, _ = _plane()
    op.provision("t1", target=tenant_database_name("t1"))
    inspection.fail_control_name = True
    out = _deprovision(service)
    assert not out.completed and out.reason == REASON_CONTROL_UNAVAILABLE
    assert op.deprovision_calls == []
    rec = store.get_tenant("t1")
    assert rec is not None and rec.lifecycle_state is TenantLifecycleState.PROVISIONING


def test_deprovision_inspection_unavailable_fails_closed() -> None:
    for switch in ("fail_exists", "fail_inspect"):
        store, audit, registry, op, ledger, inspection, service, _ = _plane()
        op.provision("t1", target=tenant_database_name("t1"))
        setattr(inspection, switch, True)
        out = _deprovision(service)
        assert not out.completed and out.reason == REASON_INSPECTION_UNAVAILABLE, switch
        assert op.deprovision_calls == [], f"{switch}: a partial census is never treated as safe"
        rec = store.get_tenant("t1")
        assert rec is not None and rec.lifecycle_state is TenantLifecycleState.PROVISIONING


def test_deprovision_operator_failure_is_terminal_failed_without_quarantine() -> None:
    op = _SpyOperator(fail=True)
    store, audit, registry, op, ledger, inspection, service, _ = _plane(operator=op)
    op.provision("t1", target=tenant_database_name("t1"))
    out = _deprovision(service)
    assert not out.completed and out.reason == REASON_DEPROVISION_FAILED
    assert op.deprovision_calls == [tenant_database_name("t1")]
    assert _pairing(store) == (1, 0, 1), "MR-9 kill site: the failure trail must be recorded"
    rec = store.get_tenant("t1")
    assert rec is not None and rec.lifecycle_state is TenantLifecycleState.PROVISIONING, "operational failure: no quarantine"


def test_deprovision_accepts_no_database_name_input() -> None:
    # §7.2 pin: the compensation API takes tenant_id + actor/correlation context ONLY —
    # no parameter can carry a database name, DSN, or connection string to drop.
    params = list(_inspect.signature(RecoveryCompensationService.deprovision_tenant_database).parameters)
    assert params == ["self", "tenant_id", "actor", "correlation_id"], params


# --- §7.1 TOCTOU pre-DROP re-validation (R1-9; MR-13 kill site) --------------------------------
def test_toctou_revalidation_refuses_concurrent_state_change() -> None:
    store, audit, registry, op, ledger, inspection, service, _ = _plane()
    target = tenant_database_name("t1")
    op.provision("t1", target=target)

    def flip_state(_: str) -> None:
        # Concurrent transition DURING the content inspection: the tenant becomes READY
        # between the first ownership proof and the destructive step.
        rec = store.get_tenant("t1")
        assert rec is not None
        store.put_tenant(replace(rec, lifecycle_state=TenantLifecycleState.READY))

    inspection.on_inspect = flip_state
    out = _deprovision(service)
    assert not out.completed and out.reason == REASON_INELIGIBLE_STATE
    assert op.deprovision_calls == [], "MR-13 kill site: the pre-DROP re-validation must refuse"
    assert target in op.provisioned, "no DROP happened"
    assert _pairing(store) == (1, 0, 1)


def test_toctou_revalidation_refuses_concurrent_ledger_claim() -> None:
    store, audit, registry, op, ledger, inspection, service, _ = _plane()
    target = tenant_database_name("t1")
    op.provision("t1", target=target)

    def claim_ledger(_: str) -> None:
        # Another tenant's evidence lands DURING inspection (e.g. a concurrent verification).
        ledger.record_evidence(
            "other_tenant",
            DistinctnessEvidence(
                system_identifier="",
                database_identity=f"{target}:db",
                observed_target=target,
                secret_ref_key="tenant/other_tenant/dsn",
                sentinel_namespace="dv_sentinel_other_tenant",
                sentinel_token="tok",
                sentinel_written=True,
            ),
        )

    inspection.on_inspect = claim_ledger
    out = _deprovision(service)
    assert not out.completed and out.reason == REASON_LEDGER_COLLISION
    assert op.deprovision_calls == [] and target in op.provisioned


def test_final_proof_re_proves_own_evidence_leg() -> None:
    # AT-PMV46-2 (PR #46 pre-merge V-2 / refuter R7): the §7.1 final proof ITSELF refuses
    # when the tenant's OWN recorded evidence disagrees with the observed fingerprint — the
    # own leg is inside the re-validated subset, not only the pre-census check (the
    # other-tenant loop excludes the own row, so this leg needs its own re-proof).
    store, audit, registry, op, ledger, inspection, service, _ = _plane()
    target = tenant_database_name("t1")
    op.provision("t1", target=target)
    observed_fingerprint = f"::{target}:db"  # the in-memory double's identity for the target
    # No own evidence -> the non-content proof passes with the fingerprint leg engaged.
    assert service._non_content_proof("t1", target, fingerprint=observed_fingerprint) is None
    # MISMATCHED own evidence -> the final proof refuses (fingerprint_mismatch), fail closed.
    ledger.record_evidence(
        "t1",
        DistinctnessEvidence(
            system_identifier="cluster_SWAP",
            database_identity=f"{target}:777",
            observed_target=target,
            secret_ref_key=tenant_dsn_ref("t1"),
            sentinel_namespace="dv_sentinel_t1",
            sentinel_token="tok",
            sentinel_written=True,
        ),
    )
    assert service._non_content_proof("t1", target, fingerprint=observed_fingerprint) == REASON_FINGERPRINT_MISMATCH
    # MATCHING own evidence passes (a healthy previously-verified identity is not a refusal).
    ledger.record_evidence(
        "t1",
        DistinctnessEvidence(
            system_identifier="",
            database_identity=f"{target}:db",
            observed_target=target,
            secret_ref_key=tenant_dsn_ref("t1"),
            sentinel_namespace="dv_sentinel_t1",
            sentinel_token="tok",
            sentinel_written=True,
        ),
    )
    assert service._non_content_proof("t1", target, fingerprint=observed_fingerprint) is None


# --- AT-PMV46-11 — own-evidence target-mismatch differentials (fingerprint MATCHES) ------------
def test_own_target_mismatch_differential_pre_census_leg() -> None:
    # PRD 07D-2c (AT-PMV46-11; MC-4 kill site): own evidence whose FINGERPRINT MATCHES the
    # observed database but whose observed_target DIFFERS must refuse at the PRE-CENSUS
    # own-evidence check with fingerprint_mismatch. The census content is deliberately
    # NON-EMPTY: if the observed_target disjunct were deleted, the flow would fall through to
    # the census and report content_not_empty — so the asserted reason isolates the disjunct.
    store, audit, registry, op, ledger, inspection, service, _ = _plane(state=TenantLifecycleState.FAILED)
    target = tenant_database_name("t1")
    insp = _bootstrap_inspection(target)
    tables = dict(insp.user_tables)
    tables["public.startups"] = 2  # non-empty: the fall-through reason would differ
    inspection.set_database(replace(insp, user_tables=tables))
    ledger.record_evidence(
        "t1",
        DistinctnessEvidence(
            system_identifier="cluster_a",  # fingerprint MATCHES the observed inspection
            database_identity=f"{target}:101",
            observed_target=tenant_database_name("elsewhere"),  # recorded target DIFFERS
            secret_ref_key=tenant_dsn_ref("t1"),
            sentinel_namespace="dv_sentinel_t1",
            sentinel_token="tok",
            sentinel_written=True,
        ),
    )
    out = _deprovision(service)
    assert out.reason == REASON_FINGERPRINT_MISMATCH, f"the observed_target disjunct must refuse: {out}"
    assert not out.completed and op.deprovision_calls == []


def test_own_target_mismatch_differential_final_proof_leg() -> None:
    # PRD 07D-2c (AT-PMV46-11): the §7.1 final-proof own-evidence leg refuses on an
    # observed_target mismatch even when the fingerprint matches (the re-proof disjunct,
    # exercised directly — the sibling of the AT-PMV46-2 fingerprint-differing case).
    store, audit, registry, op, ledger, inspection, service, _ = _plane()
    target = tenant_database_name("t1")
    op.provision("t1", target=target)
    observed_fingerprint = f"::{target}:db"  # the in-memory double's identity for the target
    ledger.record_evidence(
        "t1",
        DistinctnessEvidence(
            system_identifier="",
            database_identity=f"{target}:db",  # fingerprint MATCHES
            observed_target=tenant_database_name("elsewhere"),  # recorded target DIFFERS
            secret_ref_key=tenant_dsn_ref("t1"),
            sentinel_namespace="dv_sentinel_t1",
            sentinel_token="tok",
            sentinel_written=True,
        ),
    )
    assert service._non_content_proof("t1", target, fingerprint=observed_fingerprint) == REASON_FINGERPRINT_MISMATCH


def test_own_target_mismatch_differential_scan_leg() -> None:
    # PRD 07D-2c (AT-PMV46-11): the scan's own-tenant leg flags fingerprint_mismatch when the
    # recorded observed_target differs from the database name while the fingerprint matches.
    store, audit, registry, op, ledger, inspection, service, scan = _plane(state=TenantLifecycleState.FAILED)
    target = tenant_database_name("t1")
    inspection.set_database(_bootstrap_inspection(target))
    ledger.record_evidence(
        "t1",
        DistinctnessEvidence(
            system_identifier="cluster_a",
            database_identity=f"{target}:101",  # fingerprint MATCHES the observed database
            observed_target=tenant_database_name("elsewhere"),  # recorded target DIFFERS
            secret_ref_key=tenant_dsn_ref("t1"),
            sentinel_namespace="dv_sentinel_t1",
            sentinel_token="tok",
            sentinel_written=True,
        ),
    )
    entry = next(e for e in scan.scan_for_orphans() if e.database_name == target)
    assert entry.fingerprint_mismatch and entry.classification == CLASS_FINGERPRINT_MISMATCH
    assert not entry.safe_to_deprovision


# --- O-1 emit-once terminal latch (PRD 07D-2c D-8) ----------------------------------------------
class _RaisingReadLedger(InMemoryDistinctnessLedger):
    """Durable-ledger stand-in whose inventory READ raises — the port O-1 protects against
    (the durable adapter's evidence_excluding propagates by design)."""

    def evidence_excluding(self, tenant_id):
        raise RuntimeError("durable ledger read failed")


class _ActionRaisingAudit(ControlPlaneAudit):
    """Audit sink that raises on ONE configured action (raising-port double for the latch)."""

    def __init__(self, store, *, raise_on: str) -> None:
        super().__init__(store)
        self._raise_on = raise_on

    def record(self, *, actor, tenant_id, action, from_state, to_state, correlation_id):
        if action == self._raise_on:
            raise RuntimeError(f"audit sink unavailable for {action}")
        return super().record(
            actor=actor,
            tenant_id=tenant_id,
            action=action,
            from_state=from_state,
            to_state=to_state,
            correlation_id=correlation_id,
        )


class _VanishingRegistry(TenantRegistry):
    """Registry whose get_tenant_status serves N reads, then None (a concurrent delete)."""

    def __init__(self, store, audit, *, present_reads: int) -> None:
        super().__init__(store, audit)
        self._reads_left = present_reads

    def get_tenant_status(self, tenant_id):
        if self._reads_left <= 0:
            return None
        self._reads_left -= 1
        return super().get_tenant_status(tenant_id)


class _QuarantineRaisingRegistry(TenantRegistry):
    """Registry whose quarantine_tenant raises (the quarantine-port raising double)."""

    def quarantine_tenant(self, tenant_id, *, actor, correlation_id):
        raise RuntimeError("registry quarantine port down")


def _custom_plane(*, state=TenantLifecycleState.PROVISIONING, make_audit=None, make_registry=None, ledger=None):
    """A recovery plane with swappable audit/registry/ledger doubles (O-1 latch tests)."""
    store = InMemoryControlStore()
    audit = make_audit(store) if make_audit else ControlPlaneAudit(store)
    registry = make_registry(store, audit) if make_registry else TenantRegistry(store, audit)
    op = _SpyOperator()
    led = ledger or InMemoryDistinctnessLedger()
    inspection = InMemoryRecoveryInspection(
        control_database_name=_CONTROL_NAME,
        provisioned_view=lambda: set(op.provisioned),
    )
    store.put_tenant(_record("t1", state))
    service = RecoveryCompensationService(registry, op, audit, inspection, led, supported_schema_versions=["1"])
    return store, op, inspection, service


def test_o1_ledger_read_raise_yields_single_failed_terminal_and_reraises() -> None:
    # D-8 (O-1): the durable ledger read is the production-plausible raiser — a raise after
    # Requested must record EXACTLY ONE Failed terminal (best-effort, NOT via _fail) and
    # RE-RAISE the original error; pairing (1,0,1); zero state change; no quarantine attempt.
    store, op, inspection, service = _custom_plane(ledger=_RaisingReadLedger())
    op.provision("t1", target=tenant_database_name("t1"))
    raised = False
    try:
        _deprovision(service)
    except RuntimeError:
        raised = True
    assert raised, "the original port error must re-raise (never swallowed into a quiet outcome)"
    assert _pairing(store) == (1, 0, 1), "exactly one Failed terminal after the raise"
    assert op.deprovision_calls == [], "no DROP under a raising proof port"
    rec = store.get_tenant("t1")
    assert rec is not None and rec.lifecycle_state is TenantLifecycleState.PROVISIONING, "zero state change"
    assert events.TENANT_QUARANTINED not in _actions(store), "best-effort terminal only — no quarantine path"


def test_o1_post_drop_completed_emit_raise_honors_latch_no_second_terminal() -> None:
    # D-8 pins (a)+(b): the DROP succeeded and the COMPLETED terminal emit itself raises — the
    # latch was already attempted, so the handler must NOT add a Failed terminal after a genuine
    # completion (no double terminal; no false Failed after a successful drop); error re-raises.
    store, op, inspection, service = _custom_plane(
        make_audit=lambda s: _ActionRaisingAudit(s, raise_on=events.TENANT_DEPROVISION_COMPLETED),
    )
    op.provision("t1", target=tenant_database_name("t1"))
    raised = False
    try:
        _deprovision(service)
    except RuntimeError:
        raised = True
    assert raised
    assert op.deprovision_calls == [tenant_database_name("t1")], "the DROP ran before the sink failed"
    assert _pairing(store) == (1, 0, 0), "sink down mid-COMPLETED: no terminal recorded, and NO second terminal added"
    assert events.TENANT_DEPROVISION_FAILED not in _actions(store), "a successful drop must never gain a Failed terminal"


def test_o1_failed_terminal_emit_raise_never_doubles_the_terminal() -> None:
    # D-8 pin (a): once the Failed terminal emit is ATTEMPTED, a sink raise mid-emit must not
    # produce a second attempt from the outer handler (quarantine transition already recorded).
    store, op, inspection, service = _custom_plane(
        state=TenantLifecycleState.FAILED,
        make_audit=lambda s: _ActionRaisingAudit(s, raise_on=events.TENANT_DEPROVISION_FAILED),
    )
    target = tenant_database_name("t1")
    insp = _bootstrap_inspection(target)
    tables = dict(insp.user_tables)
    tables["public.startups"] = 2  # evidence content -> anomaly-class refusal
    inspection.set_database(replace(insp, user_tables=tables))
    raised = False
    try:
        _deprovision(service)
    except RuntimeError:
        raised = True
    assert raised
    assert _pairing(store) == (1, 0, 0), "the Failed emit failed at the sink; the handler must not retry it"
    assert _actions(store).count(events.TENANT_QUARANTINED) == 1, "the quarantine marker recorded once"
    rec = store.get_tenant("t1")
    assert rec is not None and rec.lifecycle_state is TenantLifecycleState.QUARANTINED


def test_o1_quarantine_marker_raise_still_yields_failed_terminal() -> None:
    # D-8 pin (c): TenantQuarantined is a registry-side marker and must NOT satisfy the latch.
    # If its emit raises AFTER the quarantine transition but BEFORE the Failed terminal is
    # attempted, the handler must still record the best-effort Failed terminal — (1,0,1).
    store, op, inspection, service = _custom_plane(
        state=TenantLifecycleState.FAILED,
        make_audit=lambda s: _ActionRaisingAudit(s, raise_on=events.TENANT_QUARANTINED),
    )
    target = tenant_database_name("t1")
    insp = _bootstrap_inspection(target)
    tables = dict(insp.user_tables)
    tables["public.startups"] = 2
    inspection.set_database(replace(insp, user_tables=tables))
    raised = False
    try:
        _deprovision(service)
    except RuntimeError:
        raised = True
    assert raised
    assert _pairing(store) == (1, 0, 1), "the terminal Failed must still be recorded (TenantQuarantined never latches)"
    assert events.TENANT_QUARANTINED not in _actions(store), "the marker emit itself failed at the sink"


def test_o1_quarantine_port_raise_still_yields_failed_terminal() -> None:
    # D-8: a raising registry quarantine port must not strand the trail at Requested — the
    # best-effort Failed terminal is recorded, the original error re-raises, (1,0,1) holds.
    store, op, inspection, service = _custom_plane(
        state=TenantLifecycleState.FAILED,
        make_registry=lambda s, a: _QuarantineRaisingRegistry(s, a),
    )
    target = tenant_database_name("t1")
    insp = _bootstrap_inspection(target)
    tables = dict(insp.user_tables)
    tables["public.deals"] = 1
    inspection.set_database(replace(insp, user_tables=tables))
    raised = False
    try:
        _deprovision(service)
    except RuntimeError:
        raised = True
    assert raised
    assert _pairing(store) == (1, 0, 1)
    assert events.TENANT_QUARANTINED not in _actions(store), "the quarantine port failed before its marker"
    rec = store.get_tenant("t1")
    assert rec is not None and rec.lifecycle_state is TenantLifecycleState.FAILED, "no state change recorded"


def test_o1_registry_record_vanishing_mid_flight_routes_to_failed_path() -> None:
    # D-8 pin (d): the former bare assert is now an explicit None-check routed to the terminal
    # Failed path — a record vanishing between element 1 and element 3 yields a clean
    # unknown_tenant refusal (1,0,1), never an AssertionError that strands the audit trail.
    store, op, inspection, service = _custom_plane(
        make_registry=lambda s, a: _VanishingRegistry(s, a, present_reads=1),
    )
    op.provision("t1", target=tenant_database_name("t1"))
    out = _deprovision(service)
    assert not out.completed and out.reason == REASON_UNKNOWN_TENANT
    assert _pairing(store) == (1, 0, 1)
    assert op.deprovision_calls == []


# --- ScanForOrphans (§9): read-only classification --------------------------------------------
def test_scan_is_read_only_zero_events_and_never_calls_deprovision() -> None:
    store, audit, registry, op, ledger, inspection, service, scan = _plane()
    op.provision("t1", target=tenant_database_name("t1"))
    audit_before = store.list_audit()
    rec_before = store.get_tenant("t1")
    entries = scan.scan_for_orphans()
    assert entries, "the scan must report the candidate database"
    assert store.list_audit() == audit_before, "ZERO audit events (read-only)"
    assert store.get_tenant("t1") == rec_before, "zero state change"
    assert op.deprovision_calls == [], "the scan never calls deprovision"
    assert op.provisioned == {tenant_database_name("t1")}, "no DROP"


def test_scan_classifies_eligible_and_active_rows() -> None:
    store, audit, registry, op, ledger, inspection, service, scan = _plane()
    op.provision("t1", target=tenant_database_name("t1"))  # PROVISIONING + empty -> eligible
    store.put_tenant(_record("t2", TenantLifecycleState.READY))
    inspection.set_database(_bootstrap_inspection(tenant_database_name("t2")))  # READY -> active
    store.put_tenant(_record("t3", TenantLifecycleState.FAILED))
    inspection.set_database(_bootstrap_inspection(tenant_database_name("t3")))  # FAILED + bootstrap -> eligible
    by_name = {e.database_name: e for e in scan.scan_for_orphans()}
    e1 = by_name[tenant_database_name("t1")]
    assert e1.classification == CLASS_ELIGIBLE_EMPTY and e1.safe_to_deprovision and e1.content_class == CONTENT_EMPTY
    e2 = by_name[tenant_database_name("t2")]
    assert e2.classification == CLASS_ACTIVE_TENANT and not e2.safe_to_deprovision
    assert e2.registry_state == "Ready"
    e3 = by_name[tenant_database_name("t3")]
    assert e3.classification == CLASS_ELIGIBLE_BOOTSTRAP_ONLY and e3.safe_to_deprovision
    assert e3.content_class == CONTENT_BOOTSTRAP_ONLY


def test_scan_reports_database_without_registry_record() -> None:
    store, audit, registry, op, ledger, inspection, service, scan = _plane(state=None)
    inspection.set_database(
        DatabaseInspection(database_name="sp2_tenant_ghost", system_identifier="c", database_identity="sp2_tenant_ghost:7")
    )
    audit_before = store.list_audit()  # AT-PMV46-6: direction (a) is report-only
    entries = scan.scan_for_orphans()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.classification == CLASS_NO_REGISTRY_RECORD
    assert entry.tenant_id is None and not entry.safe_to_deprovision
    assert entry.recommended_action == "manual_review"
    assert store.list_audit() == audit_before, "ghost-DB row: ZERO audit events (AT-PMV46-6)"
    assert store.list_tenant_ids() == [], "ghost-DB row: ZERO registry writes (record invariance)"


def test_scan_reports_registry_record_without_database() -> None:
    store, audit, registry, op, ledger, inspection, service, scan = _plane()  # t1 PROVISIONING, no DB
    audit_before = store.list_audit()  # AT-PMV46-6: direction (a) is report-only
    rec_before = store.get_tenant("t1")
    entries = scan.scan_for_orphans()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.classification == CLASS_REGISTRY_NO_DATABASE
    assert entry.tenant_id == "t1" and entry.database_name == tenant_database_name("t1")
    assert entry.content_class is None and not entry.safe_to_deprovision
    assert store.list_audit() == audit_before, "registry-sweep row: ZERO audit events (AT-PMV46-6)"
    assert store.get_tenant("t1") == rec_before, "registry-sweep row: record byte-invariant"


def test_scan_flags_control_db_target() -> None:
    store, audit, registry, op, ledger, inspection, service, scan = _plane()
    inspection._control_name = tenant_database_name("t1")
    op.provision("t1", target=tenant_database_name("t1"))
    entries = [e for e in scan.scan_for_orphans() if e.database_name == tenant_database_name("t1")]
    assert entries and entries[0].classification == CLASS_CONTROL_DB_TARGET
    assert entries[0].control_db_target and not entries[0].safe_to_deprovision


def test_scan_flags_ledger_collision_and_fingerprint_mismatch() -> None:
    store, audit, registry, op, ledger, inspection, service, scan = _plane(state=TenantLifecycleState.FAILED)
    target = tenant_database_name("t1")
    inspection.set_database(_bootstrap_inspection(target))
    # (a) another tenant's evidence names t1's database -> collision
    ledger.record_evidence(
        "intruder",
        DistinctnessEvidence(
            system_identifier="cluster_a",
            database_identity=f"{target}:101",
            observed_target=target,
            secret_ref_key="tenant/intruder/dsn",
            sentinel_namespace="dv_sentinel_intruder",
            sentinel_token="tok",
            sentinel_written=True,
        ),
    )
    entry = next(e for e in scan.scan_for_orphans() if e.database_name == target)
    assert entry.classification == CLASS_LEDGER_COLLISION and entry.ledger_conflict and not entry.safe_to_deprovision
    ledger.remove("intruder")
    # (b) the tenant's OWN evidence disagrees with the observed identity -> mismatch
    ledger.record_evidence(
        "t1",
        DistinctnessEvidence(
            system_identifier="cluster_OTHER",
            database_identity=f"{target}:999",
            observed_target=target,
            secret_ref_key=tenant_dsn_ref("t1"),
            sentinel_namespace="dv_sentinel_t1",
            sentinel_token="tok",
            sentinel_written=True,
        ),
    )
    entry = next(e for e in scan.scan_for_orphans() if e.database_name == target)
    assert entry.classification == CLASS_FINGERPRINT_MISMATCH and entry.fingerprint_mismatch and not entry.safe_to_deprovision


def test_scan_uninspectable_database_fails_closed() -> None:
    store, audit, registry, op, ledger, inspection, service, scan = _plane()
    op.provision("t1", target=tenant_database_name("t1"))
    inspection.fail_inspect = True
    entry = next(e for e in scan.scan_for_orphans() if e.database_name == tenant_database_name("t1"))
    assert entry.classification == CLASS_UNINSPECTABLE and not entry.safe_to_deprovision


def test_scan_non_empty_database_is_preserved_evidence() -> None:
    store, audit, registry, op, ledger, inspection, service, scan = _plane(state=TenantLifecycleState.FAILED)
    target = tenant_database_name("t1")
    insp = _bootstrap_inspection(target)
    tables = dict(insp.user_tables)
    tables["public.investors"] = 3
    inspection.set_database(replace(insp, user_tables=tables))
    entry = next(e for e in scan.scan_for_orphans() if e.database_name == target)
    assert entry.classification == CLASS_NON_EMPTY_EVIDENCE
    assert entry.content_class == CONTENT_NON_EMPTY and not entry.safe_to_deprovision
    assert entry.recommended_action == "preserve_evidence"


def test_scan_inventory_or_control_failure_raises_fail_closed() -> None:
    for switch in ("fail_inventory", "fail_control_name"):
        store, audit, registry, op, ledger, inspection, service, scan = _plane()
        setattr(inspection, switch, True)
        raised = False
        try:
            scan.scan_for_orphans()
        except RecoveryError:
            raised = True
        assert raised, f"{switch}: a partial report is never returned (fail closed)"


def test_scan_report_is_deterministic_and_credential_free() -> None:
    store, audit, registry, op, ledger, inspection, service, scan = _plane()
    op.provision("t1", target=tenant_database_name("t1"))
    store.put_tenant(_record("a0", TenantLifecycleState.REGISTERED))
    first = scan.scan_for_orphans()
    second = scan.scan_for_orphans()
    assert first == second, "the report must be deterministic"
    assert [e.database_name for e in first] == sorted(e.database_name for e in first)
    for entry in first:
        for value in (entry.reason, entry.classification, entry.recommended_action, entry.association_ref_status):
            assert "://" not in value and "password" not in value.lower(), "credential-free report (D-14)"


# --- composition + mixed-posture facade (R1-2) -------------------------------------------------
_ALL_SELECTOR_ENVS = (
    cp_main.CONTROL_STORE_ENV,
    cp_main.PROVISIONING_ADAPTER_ENV,
    cp_main.TENANT_SCHEMA_APPLICATOR_ENV,
    cp_main.DISTINCTNESS_LEDGER_ENV,
)


def _with_selector_env(values: dict):
    saved = {name: os.environ.get(name) for name in _ALL_SELECTOR_ENVS}
    for name in _ALL_SELECTOR_ENVS:
        os.environ.pop(name, None)
    for name, value in values.items():
        if value is not None:
            os.environ[name] = value

    def restore() -> None:
        for name, old in saved.items():
            if old is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old

    return restore


def _assert_recovery_denied(cp: "cp_main.ControlPlane") -> None:
    """BOTH new entry points must raise ProvisioningError pre-effect under a MIXED posture."""
    for op_name in ("deprovision_tenant_database", "scan_for_orphans"):
        raised = False
        try:
            if op_name == "deprovision_tenant_database":
                cp.recovery.deprovision_tenant_database("guard_t1", actor="ops_ref", correlation_id="c-rg1")
            else:
                cp.orphan_scan.scan_for_orphans()
        except ProvisioningError:
            raised = True
        assert raised, f"{op_name}() must fail closed (ProvisioningError) under a MIXED effective posture"


def test_default_composition_exposes_recovery_and_shares_one_ledger() -> None:
    restore = _with_selector_env({})
    try:
        cp = cp_main.ControlPlane()
        assert isinstance(cp.recovery, RecoveryCompensationService), "matched posture must expose the real service"
        assert isinstance(cp.orphan_scan, OrphanScanService)
        # ONE ledger instance shared by the gate and the recovery services — a second
        # in-memory ledger would make the element-5 collision proof vacuous.
        assert cp.provisioning._ledger is cp._ledger
        assert cp.recovery._ledger is cp._ledger
        assert cp.orphan_scan._ledger is cp._ledger
    finally:
        restore()


def test_default_composition_deprovision_end_to_end() -> None:
    restore = _with_selector_env({})
    try:
        cp = cp_main.ControlPlane()
        cp.registry.register_tenant(
            tenant_id="t_dep",
            organization_ref=_ORG,
            expected_schema_version="1",
            database_association_ref=SecretRef(store_ref=tenant_dsn_ref("t_dep"), version="1"),
            federation_config_ref=_FED,
            actor="ops_ref",
            correlation_id="c-e2e-0",
        )
        cp.registry.mark_provisioning("t_dep", actor="ops_ref", correlation_id="c-e2e-1")
        assert isinstance(cp.operator, InMemoryProvisioningOperator)
        cp.operator.provision("t_dep", target=tenant_database_name("t_dep"))
        assert isinstance(cp.recovery, RecoveryCompensationService)
        out = cp.recovery.deprovision_tenant_database("t_dep", actor="ops_ref", correlation_id="c-e2e-2")
        assert out.dropped and out.reason == REASON_DEPROVISIONED
        assert tenant_database_name("t_dep") not in cp.operator.provisioned
        rec = cp.store.get_tenant("t_dep")
        assert rec is not None, "registry record retained"
    finally:
        restore()


def test_recovery_guard_blocks_durable_store_with_in_memory_live() -> None:
    # Mix direction (a): durable/postgres control store standalone, live trio in-memory.
    restore = _with_selector_env({cp_main.CONTROL_STORE_ENV: "postgres"})
    try:
        cp = cp_main.ControlPlane()  # construction stays allowed (B-7B posture)
        _assert_recovery_denied(cp)
    finally:
        restore()


def test_recovery_guard_blocks_reverse_mix_with_zero_events() -> None:
    # Mix direction (b): explicit in-memory store under the all-postgres env composition.
    restore = _with_selector_env({name: "postgres" for name in _ALL_SELECTOR_ENVS})
    try:
        store = InMemoryControlStore()
        cp = cp_main.ControlPlane(store=store)
        _assert_recovery_denied(cp)
        assert store.list_audit() == [], "the deny is PRE-EFFECT: zero audit events"
        assert store.get_tenant("guard_t1") is None, "zero registry writes"
    finally:
        restore()


def test_recovery_guard_allows_matched_postgres_posture() -> None:
    restore = _with_selector_env({name: "postgres" for name in _ALL_SELECTOR_ENVS})
    try:
        cp = cp_main.ControlPlane()  # lazy; constructs with no I/O
        assert isinstance(cp.recovery, RecoveryCompensationService), "all-postgres posture must not be wrapped"
        assert isinstance(cp.orphan_scan, OrphanScanService)
    finally:
        restore()


def test_in_memory_inspection_tracks_operator_provisioned_view() -> None:
    op = InMemoryProvisioningOperator()
    view_source: Set[str] = op.provisioned
    inspection = InMemoryRecoveryInspection(control_database_name=_CONTROL_NAME, provisioned_view=lambda: set(view_source))
    assert inspection.list_candidate_databases() == []
    op.provision("t1", target=tenant_database_name("t1"))
    assert inspection.list_candidate_databases() == [tenant_database_name("t1")]
    assert inspection.database_exists(tenant_database_name("t1")) is True
    insp = inspection.inspect_database(tenant_database_name("t1"))
    assert insp is not None and classify_content(insp, supported_schema_versions=["1"]) == CONTENT_EMPTY


_TESTS = [
    test_census_empty_database,
    test_census_bootstrap_only_full_schema_with_sentinel_rows,
    test_census_sentinel_only_database_is_bootstrap_only,
    test_census_extra_table_is_evidence,
    test_census_business_row_is_evidence,
    test_census_agents_seed_rules,
    test_census_schema_version_rules,
    test_census_unknown_row_count_fails_closed,
    test_census_surfaced_matview_and_large_object_entries_are_evidence,
    test_deprovision_empty_database_succeeds_and_retains_registry_record,
    test_deprovision_bootstrap_only_database_succeeds,
    test_deprovision_quarantined_tenant_is_eligible,
    test_deprovision_absent_target_is_safe_noop_completed,
    test_deprovision_unknown_tenant_refused,
    test_deprovision_ineligible_states_refused_with_no_state_change,
    test_deprovision_non_canonical_association_ref_refused,
    test_deprovision_non_empty_database_never_dropped_and_quarantines,
    test_deprovision_already_quarantined_stays_on_proof_failure,
    test_deprovision_ledger_collision_refused,
    test_deprovision_own_fingerprint_mismatch_refused,
    test_deprovision_control_database_target_refused_before_operator,
    test_deprovision_control_identity_unavailable_fails_closed,
    test_deprovision_inspection_unavailable_fails_closed,
    test_deprovision_operator_failure_is_terminal_failed_without_quarantine,
    test_deprovision_accepts_no_database_name_input,
    test_toctou_revalidation_refuses_concurrent_state_change,
    test_toctou_revalidation_refuses_concurrent_ledger_claim,
    test_final_proof_re_proves_own_evidence_leg,
    test_own_target_mismatch_differential_pre_census_leg,
    test_own_target_mismatch_differential_final_proof_leg,
    test_own_target_mismatch_differential_scan_leg,
    test_o1_ledger_read_raise_yields_single_failed_terminal_and_reraises,
    test_o1_post_drop_completed_emit_raise_honors_latch_no_second_terminal,
    test_o1_failed_terminal_emit_raise_never_doubles_the_terminal,
    test_o1_quarantine_marker_raise_still_yields_failed_terminal,
    test_o1_quarantine_port_raise_still_yields_failed_terminal,
    test_o1_registry_record_vanishing_mid_flight_routes_to_failed_path,
    test_scan_is_read_only_zero_events_and_never_calls_deprovision,
    test_scan_classifies_eligible_and_active_rows,
    test_scan_reports_database_without_registry_record,
    test_scan_reports_registry_record_without_database,
    test_scan_flags_control_db_target,
    test_scan_flags_ledger_collision_and_fingerprint_mismatch,
    test_scan_uninspectable_database_fails_closed,
    test_scan_non_empty_database_is_preserved_evidence,
    test_scan_inventory_or_control_failure_raises_fail_closed,
    test_scan_report_is_deterministic_and_credential_free,
    test_default_composition_exposes_recovery_and_shares_one_ledger,
    test_default_composition_deprovision_end_to_end,
    test_recovery_guard_blocks_durable_store_with_in_memory_live,
    test_recovery_guard_blocks_reverse_mix_with_zero_events,
    test_recovery_guard_allows_matched_postgres_posture,
    test_in_memory_inspection_tracks_operator_provisioned_view,
]

if __name__ == "__main__":
    for _t in _TESTS:
        _t()
        print("PASS:", _t.__name__)
    print("ALL PASSED")
