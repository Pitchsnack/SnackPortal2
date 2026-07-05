"""Build Phase 4 tenant lifecycle (IC-002): Verify/Activate/Reactivate/Reassociate.

Uses a stdlib fake verification probe (no tenant DB, no driver). Confirms the
Phase-4 states (Verifying/Ready/Failed) are reached, transitions are audited, and the
service never touches database_router (Standard G).
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.audit import ControlPlaneAudit  # noqa: E402
from control_plane.lifecycle import LifecycleError, TenantLifecycleService  # noqa: E402
from control_plane.records import TenantLifecycleState  # noqa: E402
from control_plane.registry import TenantRegistry  # noqa: E402
from control_plane.verification import ProbeResult, TenantDatabaseProbe  # noqa: E402
from shared.secrets import SecretRef  # noqa: E402


class FakeProbe(TenantDatabaseProbe):
    def __init__(self, reachable: bool = True, observed: str = "1") -> None:
        self.reachable = reachable
        self.observed = observed
        self.calls = []

    def probe(self, association_ref: SecretRef) -> ProbeResult:
        self.calls.append(association_ref)
        return ProbeResult(reachable=self.reachable, observed_schema_version=self.observed)


def _wire(probe=None):
    store = InMemoryControlStore()
    audit = ControlPlaneAudit(store)
    reg = TenantRegistry(store, audit)
    svc = TenantLifecycleService(store, audit, probe or FakeProbe(), supported_schema_versions=("1",))
    return store, audit, reg, svc


def _register(reg, tid="t1", version="1", schema="1"):
    return reg.register_tenant(
        tenant_id=tid,
        organization_ref="org",
        expected_schema_version=schema,
        database_association_ref=SecretRef(f"tenant/{tid}/db", version),
        federation_config_ref="fed",
        actor="op",
        correlation_id="c",
    )


def _actions(audit):
    return [e.action for e in audit.events()]


def test_verify_promotes_provisioning_to_ready() -> None:
    store, audit, reg, svc = _wire()
    _register(reg)
    reg.mark_provisioning("t1", actor="op", correlation_id="c")
    rec = svc.verify_tenant("t1", actor="op", correlation_id="c")
    assert rec.lifecycle_state is TenantLifecycleState.READY
    assert "VerifyTenant:ready" in _actions(audit)


def test_verify_unreachable_marks_failed() -> None:
    store, audit, reg, svc = _wire(FakeProbe(reachable=False, observed=None))
    _register(reg)
    rec = svc.verify_tenant("t1", actor="op", correlation_id="c")
    assert rec.lifecycle_state is TenantLifecycleState.FAILED
    assert "VerifyTenant:unreachable" in _actions(audit)


def test_verify_schema_out_of_range_marks_failed() -> None:
    store, audit, reg, svc = _wire(FakeProbe(reachable=True, observed="2"))
    _register(reg)  # expected schema "1"; observed "2"
    rec = svc.verify_tenant("t1", actor="op", correlation_id="c")
    assert rec.lifecycle_state is TenantLifecycleState.FAILED
    assert "VerifyTenant:schema" in _actions(audit)


def test_activate_requires_verifying() -> None:
    store, audit, reg, svc = _wire()
    _register(reg)
    # Reach Verifying via re-association, then activate.
    svc.reassociate_database("t1", new_association_ref=SecretRef("tenant/t1/db", "2"), actor="op", correlation_id="c")
    assert store.get_tenant("t1").lifecycle_state is TenantLifecycleState.VERIFYING
    rec = svc.activate_tenant("t1", actor="op", correlation_id="c")
    assert rec.lifecycle_state is TenantLifecycleState.READY
    # Activating a non-Verifying tenant is rejected.
    try:
        svc.activate_tenant("t1", actor="op", correlation_id="c")
        assert False, "activate must require Verifying"
    except LifecycleError:
        pass


def test_reactivate_suspended_to_ready() -> None:
    store, audit, reg, svc = _wire()
    _register(reg)
    reg.suspend_tenant("t1", actor="op", correlation_id="c")
    assert store.get_tenant("t1").lifecycle_state is TenantLifecycleState.SUSPENDED
    rec = svc.reactivate_tenant("t1", actor="op", correlation_id="c")
    assert rec.lifecycle_state is TenantLifecycleState.READY
    assert "ReactivateTenant" in _actions(audit)


def test_reassociate_requires_version_increment_and_reverifies() -> None:
    store, audit, reg, svc = _wire()
    _register(reg, version="1")
    # Same/lower version is rejected.
    try:
        svc.reassociate_database("t1", new_association_ref=SecretRef("tenant/t1/db", "1"), actor="op", correlation_id="c")
        assert False, "re-association requires an incremented version"
    except LifecycleError:
        pass
    rec = svc.reassociate_database("t1", new_association_ref=SecretRef("tenant/t1/db2", "2"), actor="op", correlation_id="c")
    assert rec.lifecycle_state is TenantLifecycleState.VERIFYING
    assert rec.database_association_ref == SecretRef("tenant/t1/db2", "2")  # reference only
    assert "ReassociateDatabase" in _actions(audit)
    # Re-verify promotes to Ready.
    rec2 = svc.verify_tenant("t1", actor="op", correlation_id="c")
    assert rec2.lifecycle_state is TenantLifecycleState.READY


# --- PRD 07D-2b.2b §11 HARDEN (R1-6; MR-12 kill sites) ---------------------------------------
# This service remains DORMANT (uncomposed — the b7c1 composition-root exclusion pin), but if
# it were ever wired these tests close its two Quarantined escape hatches.
def _quarantine(store, reg, tid="t1"):
    reg.mark_provisioning(tid, actor="op", correlation_id="c-q0")
    reg.quarantine_tenant(tid, actor="op", correlation_id="c-q1")
    rec = store.get_tenant(tid)
    assert rec is not None and rec.lifecycle_state is TenantLifecycleState.QUARANTINED
    return rec


def test_verify_tenant_refuses_quarantined_pre_transition() -> None:
    # MR-12 kill site (verification leg): verify_tenant must never walk a QUARANTINED tenant
    # toward Verifying/Ready — refusal is PRE-transition with zero side effects.
    store, audit, reg, svc = _wire()
    _register(reg)
    rec_before = _quarantine(store, reg)
    audit_before = list(audit.events())
    try:
        svc.verify_tenant("t1", actor="op", correlation_id="c-q2")
        assert False, "verify_tenant must refuse a QUARANTINED tenant"
    except LifecycleError:
        pass
    assert store.get_tenant("t1") == rec_before, "zero state change (no Verifying overwrite)"
    assert audit.events() == audit_before, "zero audit writes (pre-transition refusal)"


def test_reassociate_refuses_quarantined_and_decommissioned_pre_effect() -> None:
    # MR-12 kill site (re-association leg): the current-state pre-check runs BEFORE any other
    # check or write — no association overwrite, no Verifying transition, no audit record.
    store, audit, reg, svc = _wire()
    _register(reg)
    rec_q = _quarantine(store, reg)
    audit_before = list(audit.events())
    try:
        svc.reassociate_database("t1", new_association_ref=SecretRef("tenant/t1/db2", "2"), actor="op", correlation_id="c-q3")
        assert False, "reassociate_database must refuse a QUARANTINED tenant"
    except LifecycleError:
        pass
    assert store.get_tenant("t1") == rec_q, "record byte-unchanged (association + state)"
    assert audit.events() == audit_before
    # Decommissioned is terminal for re-association too.
    _register(reg, tid="t2")
    reg.decommission_tenant("t2", actor="op", correlation_id="c-d0")
    rec_d = store.get_tenant("t2")
    audit_before = list(audit.events())
    try:
        svc.reassociate_database("t2", new_association_ref=SecretRef("tenant/t2/db2", "2"), actor="op", correlation_id="c-d1")
        assert False, "reassociate_database must refuse a DECOMMISSIONED tenant"
    except LifecycleError:
        pass
    assert store.get_tenant("t2") == rec_d
    assert audit.events() == audit_before
    # The pre-check runs FIRST: even a same-version (otherwise version-refused) request on a
    # QUARANTINED tenant reports the state refusal, proving the guard precedes the version check.
    try:
        svc.reassociate_database("t1", new_association_ref=SecretRef("tenant/t1/db", "1"), actor="op", correlation_id="c-q4")
        assert False
    except LifecycleError as exc:
        assert "illegal lifecycle transition" in str(exc), "the state guard must run before the version check"


if __name__ == "__main__":
    _h.run(
        [
            test_verify_promotes_provisioning_to_ready,
            test_verify_unreachable_marks_failed,
            test_verify_schema_out_of_range_marks_failed,
            test_activate_requires_verifying,
            test_reactivate_suspended_to_ready,
            test_reassociate_requires_version_increment_and_reverifies,
            test_verify_tenant_refuses_quarantined_pre_transition,
            test_reassociate_refuses_quarantined_and_decommissioned_pre_effect,
        ]
    )
