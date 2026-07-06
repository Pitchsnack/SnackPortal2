"""Operational audit (lifecycle events, no secrets) + Global Discovery Platform."""

from __future__ import annotations

import pathlib
import sys
from dataclasses import replace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.audit import ControlPlaneAudit  # noqa: E402
from control_plane.directory import GlobalDirectory  # noqa: E402
from control_plane.records import DirectoryKind, TenantLifecycleState  # noqa: E402
from control_plane.registry import TenantRegistry  # noqa: E402
from shared.secrets import SecretRef  # noqa: E402


def test_lifecycle_events_are_audited_with_required_fields() -> None:
    store = InMemoryControlStore()
    audit = ControlPlaneAudit(store)
    reg = TenantRegistry(store, audit)
    reg.register_tenant(
        tenant_id="t1",
        organization_ref="o",
        expected_schema_version="1",
        database_association_ref=SecretRef("a", "1"),
        federation_config_ref="f",
        actor="op",
        correlation_id="c1",
    )
    # PRD 07D-2d (B2): suspend requires READY — seed the READY state directly in the store
    # (the Phase-4 fence guards registry transitions, not the test fixture) so the audited
    # SuspendTenant lifecycle event under test is emitted from a legal source state.
    store.put_tenant(replace(store.get_tenant("t1"), lifecycle_state=TenantLifecycleState.READY))
    reg.suspend_tenant("t1", actor="op", correlation_id="c2")
    actions = [e.action for e in audit.events()]
    assert "RegisterTenant" in actions and "SuspendTenant" in actions
    for e in audit.events():
        assert e.actor and e.action and e.correlation_id and e.timestamp


def test_audit_records_have_no_secret_fields() -> None:
    audit = ControlPlaneAudit(InMemoryControlStore())
    rec = audit.record(actor="op", tenant_id="t1", action="RegisterTenant", from_state=None, to_state="Registered", correlation_id="c")
    for bad in ("secret", "credential", "password", "material", "token"):
        assert not hasattr(rec, bad)


def test_global_directory_stable_ids_and_separation() -> None:
    d = GlobalDirectory(InMemoryControlStore())
    s = d.add(directory=DirectoryKind.STARTUP, record_id="g-100", display_name="Acme")
    assert s.record_id == "g-100"  # stable id for future IC-003/IC-004 source_ref
    assert d.get(DirectoryKind.STARTUP, "g-100").display_name == "Acme"
    d.add(directory=DirectoryKind.INVESTOR, record_id="i-1", display_name="VC")
    assert len(d.list(DirectoryKind.STARTUP)) == 1
    assert len(d.list(DirectoryKind.INVESTOR)) == 1


if __name__ == "__main__":
    _h.run(
        [
            test_lifecycle_events_are_audited_with_required_fields,
            test_audit_records_have_no_secret_fields,
            test_global_directory_stable_ids_and_separation,
        ]
    )
