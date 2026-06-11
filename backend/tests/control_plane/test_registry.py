"""Tenant registry: references-only, idempotent register, lifecycle gating (no Ready in P2)."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.audit import ControlPlaneAudit  # noqa: E402
from control_plane.records import TenantLifecycleState  # noqa: E402
from control_plane.registry import PhaseFourDeferred, TenantRegistry  # noqa: E402
from shared.secrets import SecretRef  # noqa: E402


def _registry():
    store = InMemoryControlStore()
    return TenantRegistry(store, ControlPlaneAudit(store)), store


def _register(reg, tid="t1"):
    return reg.register_tenant(
        tenant_id=tid, organization_ref="org", expected_schema_version="1",
        database_association_ref=SecretRef(f"tenant/{tid}/db", "1"), federation_config_ref="fed",
        actor="op", correlation_id="c",
    )


def test_register_yields_registered_and_is_idempotent() -> None:
    reg, _ = _registry()
    rec = _register(reg)
    assert rec.lifecycle_state is TenantLifecycleState.REGISTERED
    again = reg.register_tenant(
        tenant_id="t1", organization_ref="changed", expected_schema_version="9",
        database_association_ref=SecretRef("z", "9"), federation_config_ref="z",
        actor="op", correlation_id="c2",
    )
    assert again.created_at == rec.created_at  # idempotent by tenant_id


def test_registry_stores_references_only() -> None:
    reg, _ = _registry()
    rec = _register(reg)
    assert isinstance(rec.database_association_ref, SecretRef)
    for bad in ("password", "credentials", "secret", "dsn"):
        assert not hasattr(rec, bad)


def test_phase2_cannot_reach_ready_or_verify() -> None:
    reg, store = _registry()
    _register(reg)
    for op in (reg.verify_tenant, reg.activate_tenant, reg.reactivate_tenant, reg.reassociate_database):
        try:
            op("t1")
            assert False, "Phase 4 operation must be deferred"
        except PhaseFourDeferred:
            pass
    assert store.get_tenant("t1").lifecycle_state is not TenantLifecycleState.READY


def test_phase2_lifecycle_transitions() -> None:
    reg, store = _registry()
    _register(reg)
    reg.mark_provisioning("t1", actor="op", correlation_id="c")
    assert store.get_tenant("t1").lifecycle_state is TenantLifecycleState.PROVISIONING
    reg.suspend_tenant("t1", actor="op", correlation_id="c")
    assert store.get_tenant("t1").lifecycle_state is TenantLifecycleState.SUSPENDED
    reg.decommission_tenant("t1", actor="op", correlation_id="c")
    assert store.get_tenant("t1").lifecycle_state is TenantLifecycleState.DECOMMISSIONED


if __name__ == "__main__":
    _h.run([
        test_register_yields_registered_and_is_idempotent,
        test_registry_stores_references_only,
        test_phase2_cannot_reach_ready_or_verify,
        test_phase2_lifecycle_transitions,
    ])
