"""Bootstrap framework: DB-free Phase 0; gated Phase 1; Phase-0 closure + break-glass."""

from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.bootstrap import BootstrapController, BootstrapError, BootstrapPhase  # noqa: E402
from shared.adapters.providers.env_reference_secret_store import EnvReferenceSecretStore  # noqa: E402


def _controller() -> BootstrapController:
    os.environ["SNACKPORTAL_SECRET_BOOTSTRAP_TRUST_ANCHOR_V1"] = "anchor"
    return BootstrapController(EnvReferenceSecretStore())


def test_phase0_is_db_free_identity_check() -> None:
    b = _controller()
    assert b.phase is BootstrapPhase.PHASE_0
    assert b.verify_system_identity("anchor") is True
    assert b.verify_system_identity("wrong") is False  # no Control DB involved


def test_phase1_requires_identity_store_and_schema() -> None:
    b = _controller()
    store = InMemoryControlStore(schema_version=1, reachable=True)
    try:
        b.enter_phase1(store, schema_compatible=True)
        assert False, "must require verified identity"
    except BootstrapError:
        pass
    b.verify_system_identity("anchor")
    try:
        b.enter_phase1(InMemoryControlStore(reachable=False), schema_compatible=True)
        assert False, "must require reachable Control DB"
    except BootstrapError:
        pass
    try:
        b.enter_phase1(store, schema_compatible=False)
        assert False, "must require compatible schema"
    except BootstrapError:
        pass
    b.enter_phase1(store, schema_compatible=True)
    assert b.phase is BootstrapPhase.PHASE_1


def test_phase0_closed_and_break_glass_disabled_on_transition() -> None:
    b = _controller()
    assert b.break_glass_enabled is True and b.phase0_closed is False
    b.verify_system_identity("anchor")
    b.enter_phase1(InMemoryControlStore(), schema_compatible=True)
    assert b.phase0_closed is True
    assert b.break_glass_enabled is False


if __name__ == "__main__":
    _h.run(
        [
            test_phase0_is_db_free_identity_check,
            test_phase1_requires_identity_store_and_schema,
            test_phase0_closed_and_break_glass_disabled_on_transition,
        ]
    )
