"""End-to-end control-plane flow: bootstrap -> register -> membership/directory -> readiness.

Exercises the composition root (control_plane.main.create_app) and confirms the
frameworks interoperate while honoring the Phase-2 invariants (no tenant Ready;
operational audit recorded; readiness disclosure-safe).
"""

from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from control_plane.main import create_app, liveness  # noqa: E402
from control_plane.records import DirectoryKind, Role, TenantLifecycleState  # noqa: E402
from shared.health import GlobalReadiness  # noqa: E402
from shared.secrets import SecretRef  # noqa: E402


def test_bootstrap_to_ready_control_plane() -> None:
    os.environ["SNACKPORTAL_SECRET_BOOTSTRAP_TRUST_ANCHOR_V1"] = "demo-anchor"
    cp = create_app()

    # Bootstrap Phase 0 (DB-free) -> Phase 1 (gated).
    assert cp.bootstrap.verify_system_identity("demo-anchor") is True
    state = cp.schema.check(cp.store.schema_version())
    assert state.name == "PASS"
    cp.bootstrap.enter_phase1(cp.store, schema_compatible=True)
    assert cp.bootstrap.phase.value == "BootstrapPhase1"
    assert cp.bootstrap.phase0_closed is True
    assert cp.bootstrap.break_glass_enabled is False

    # Registry: tenant is Registered, never Ready in Phase 2.
    t = cp.registry.register_tenant(
        tenant_id="t1",
        organization_ref="org1",
        expected_schema_version="1",
        database_association_ref=SecretRef("tenant/t1/db", "1"),
        federation_config_ref="fed1",
        actor="op",
        correlation_id="r1",
    )
    assert t.lifecycle_state is TenantLifecycleState.REGISTERED
    assert cp.store.get_tenant("t1").lifecycle_state is not TenantLifecycleState.READY

    # Membership + directory.
    cp.membership.add_membership(principal_ref="ma", tenant_id="t1", role=Role.MASTER_AGENT)
    cp.directory.add(directory=DirectoryKind.STARTUP, record_id="g-1", display_name="Acme")
    assert len(cp.directory.list(DirectoryKind.STARTUP)) == 1

    # Global readiness is READY once Phase 1 is active.
    rep = cp.readiness.evaluate(phase1_active=True, control_store_reachable=cp.store.is_reachable(), schema_pass=True)
    assert rep.state is GlobalReadiness.READY

    # Operational audit captured the registration.
    assert "RegisterTenant" in [e.action for e in cp.audit.events()]
    assert liveness()["build_phase"] == "2"


if __name__ == "__main__":
    _h.run([test_bootstrap_to_ready_control_plane])
