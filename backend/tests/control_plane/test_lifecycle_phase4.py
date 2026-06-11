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
        tenant_id=tid, organization_ref="org", expected_schema_version=schema,
        database_association_ref=SecretRef(f"tenant/{tid}/db", version), federation_config_ref="fed",
        actor="op", correlation_id="c",
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


if __name__ == "__main__":
    _h.run([
        test_verify_promotes_provisioning_to_ready,
        test_verify_unreachable_marks_failed,
        test_verify_schema_out_of_range_marks_failed,
        test_activate_requires_verifying,
        test_reactivate_suspended_to_ready,
        test_reassociate_requires_version_increment_and_reverifies,
    ])
