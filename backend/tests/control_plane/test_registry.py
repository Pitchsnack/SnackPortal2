"""Tenant registry: references-only, idempotent register, lifecycle gating (no Ready in P2)."""

from __future__ import annotations

import pathlib
import sys
from dataclasses import replace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.audit import ControlPlaneAudit  # noqa: E402
from control_plane.records import TenantLifecycleState  # noqa: E402
from control_plane.registry import PhaseFourDeferred, RegistryError, TenantRegistry  # noqa: E402
from shared.secrets import SecretRef  # noqa: E402


class _PutCountingStore(InMemoryControlStore):
    """Store double counting put_tenant writes — proves the A1 same-target no-op is
    non-mutating (PRD 07D-2d §6.1: no store write side effect on a no-op)."""

    def __init__(self) -> None:
        super().__init__()
        self.put_calls = 0

    def put_tenant(self, record):
        self.put_calls += 1
        return super().put_tenant(record)


def _registry(store=None):
    store = store or InMemoryControlStore()
    return TenantRegistry(store, ControlPlaneAudit(store)), store


def _seed_ready(reg, store, tid="t1"):
    """Register then seed READY directly in the store — the registry can never set READY in
    Phase 2 (the Phase-4 fence guards _transition's to_state, not the test fixture)."""
    _register(reg, tid)
    ready = replace(store.get_tenant(tid), lifecycle_state=TenantLifecycleState.READY)
    store.put_tenant(ready)
    return ready


def _register(reg, tid="t1"):
    return reg.register_tenant(
        tenant_id=tid,
        organization_ref="org",
        expected_schema_version="1",
        database_association_ref=SecretRef(f"tenant/{tid}/db", "1"),
        federation_config_ref="fed",
        actor="op",
        correlation_id="c",
    )


def test_register_yields_registered_and_is_idempotent() -> None:
    reg, _ = _registry()
    rec = _register(reg)
    assert rec.lifecycle_state is TenantLifecycleState.REGISTERED
    again = reg.register_tenant(
        tenant_id="t1",
        organization_ref="changed",
        expected_schema_version="9",
        database_association_ref=SecretRef("z", "9"),
        federation_config_ref="z",
        actor="op",
        correlation_id="c2",
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
    # PRD 07D-2d (DD-2c-2 = B2): Provisioning -> Suspended is no longer legal, so the Phase-2
    # chain under test is Registered -> Provisioning -> Decommissioned; suspend now requires
    # READY and is covered by the dedicated 07D-2d suspend tests below.
    reg, store = _registry()
    _register(reg)
    reg.mark_provisioning("t1", actor="op", correlation_id="c")
    assert store.get_tenant("t1").lifecycle_state is TenantLifecycleState.PROVISIONING
    reg.decommission_tenant("t1", actor="op", correlation_id="c")
    assert store.get_tenant("t1").lifecycle_state is TenantLifecycleState.DECOMMISSIONED


# --- PRD 07D-2d (DD-2c-1 = A1 same-target idempotency; DD-2c-2 = B2 READY-only suspend) -------
def test_2d_suspend_ready_only() -> None:
    # B2 (MD-3/MD-4 kill sites): allowed_from is narrowed to {READY} — IC-002 lists
    # `Ready -> Suspended` only. READY suspends; REGISTERED and PROVISIONING now refuse.
    reg, store = _registry()
    _seed_ready(reg, store)
    rec = reg.suspend_tenant("t1", actor="op", correlation_id="c-s")
    assert rec.lifecycle_state is TenantLifecycleState.SUSPENDED
    _register(reg, "t_reg")  # REGISTERED
    _register(reg, "t_prov")
    reg.mark_provisioning("t_prov", actor="op", correlation_id="c-p")  # PROVISIONING
    for tid in ("t_reg", "t_prov"):
        raised = False
        try:
            reg.suspend_tenant(tid, actor="op", correlation_id="c-x")
        except RegistryError:
            raised = True
        assert raised, f"{tid}: non-READY suspend must refuse (B2)"
        assert store.get_tenant(tid).lifecycle_state is not TenantLifecycleState.SUSPENDED


def test_2d_same_target_reissue_is_idempotent_noop() -> None:
    # A1 (MD-1/MD-5 kill sites): a same-target lifecycle re-issue returns the EXISTING record
    # as a non-mutating no-op — no put_tenant write, no audit record, no event — for every
    # reachable state (Provisioning / Suspended / Quarantined / Decommissioned).
    store = _PutCountingStore()
    reg, _ = _registry(store)
    _register(reg, "t_p")
    reg.mark_provisioning("t_p", actor="op", correlation_id="c0")
    _seed_ready(reg, store, "t_s")
    reg.suspend_tenant("t_s", actor="op", correlation_id="c1")
    _register(reg, "t_q")
    reg.mark_provisioning("t_q", actor="op", correlation_id="c2")
    reg.quarantine_tenant("t_q", actor="op", correlation_id="c3")
    _register(reg, "t_d")
    reg.decommission_tenant("t_d", actor="op", correlation_id="c4")
    reissues = (
        ("t_p", reg.mark_provisioning, TenantLifecycleState.PROVISIONING),
        ("t_s", reg.suspend_tenant, TenantLifecycleState.SUSPENDED),
        ("t_q", reg.quarantine_tenant, TenantLifecycleState.QUARANTINED),
        ("t_d", reg.decommission_tenant, TenantLifecycleState.DECOMMISSIONED),
    )
    for tid, op, state in reissues:
        rec_before = store.get_tenant(tid)
        audit_before = store.list_audit()
        puts_before = store.put_calls
        out = op(tid, actor="op", correlation_id="c-noop")
        assert out == rec_before, f"{tid}: the no-op must return the existing record unmutated"
        assert out.lifecycle_state is state
        assert store.get_tenant(tid) == rec_before, f"{tid}: the stored record must stay field-identical"
        assert store.list_audit() == audit_before, f"{tid}: no audit record may be written on a no-op"
        assert store.put_calls == puts_before, f"{tid}: no put_tenant write may occur on a no-op"


def test_2d_unknown_and_illegal_transitions_still_fail_closed() -> None:
    # A1 must not weaken fail-closed behavior: unknown tenants still refuse, and every
    # non-same-target illegal transition still raises with ZERO mutation.
    store = _PutCountingStore()
    reg, _ = _registry(store)
    raised = False
    try:
        reg.suspend_tenant("ghost", actor="op", correlation_id="c")
    except RegistryError:
        raised = True
    assert raised, "unknown tenant must still refuse"
    _register(reg, "t1")  # REGISTERED — neither suspend (B2) nor quarantine allows it
    audit_before = store.list_audit()
    puts_before = store.put_calls
    for op in (reg.suspend_tenant, reg.quarantine_tenant):
        raised = False
        try:
            op("t1", actor="op", correlation_id="c-bad")
        except RegistryError:
            raised = True
        assert raised, "illegal non-same-target transition must still raise"
    assert store.get_tenant("t1").lifecycle_state is TenantLifecycleState.REGISTERED
    assert store.list_audit() == audit_before and store.put_calls == puts_before


def test_2d_suspended_to_suspended_noops_under_narrowed_set() -> None:
    # §6.3 composition proof (MD-2 kill site): with allowed_from == {READY} (B2), re-suspending
    # an already-SUSPENDED tenant must no-op via A1 — NOT raise — precisely because the
    # same-target check precedes the allowed_from guard.
    store = _PutCountingStore()
    reg, _ = _registry(store)
    _seed_ready(reg, store)
    first = reg.suspend_tenant("t1", actor="op", correlation_id="c-s1")
    assert first.lifecycle_state is TenantLifecycleState.SUSPENDED
    audit_before = store.list_audit()
    puts_before = store.put_calls
    again = reg.suspend_tenant("t1", actor="op", correlation_id="c-s2")
    assert again == first, "re-suspend must return the existing SUSPENDED record without raising"
    assert store.list_audit() == audit_before, "no duplicate SuspendTenant record on the no-op"
    assert store.put_calls == puts_before, "no store write on the composed no-op"


if __name__ == "__main__":
    _h.run(
        [
            test_register_yields_registered_and_is_idempotent,
            test_registry_stores_references_only,
            test_phase2_cannot_reach_ready_or_verify,
            test_phase2_lifecycle_transitions,
            test_2d_suspend_ready_only,
            test_2d_same_target_reissue_is_idempotent_noop,
            test_2d_unknown_and_illegal_transitions_still_fail_closed,
            test_2d_suspended_to_suspended_noops_under_narrowed_set,
        ]
    )
