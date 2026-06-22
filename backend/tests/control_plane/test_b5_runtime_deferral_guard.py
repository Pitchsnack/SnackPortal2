"""PRD 06 B-5 — runtime-deferral regression LOCK (controlled non-production; no live resources).

Consolidated B-5-named guard that PINS the current runtime deferral *behaviorally*: backend/control_plane/main.py keeps
the durable/real adapters DEFERRED — default env builds the in-memory composition (construction performs no I/O), and
selecting any non-in_memory adapter via SP2_CP_PROVISIONING_ADAPTER or SP2_CP_DISTINCTNESS_LEDGER fails closed with
NotImplementedError. "Runtime activation" = flipping that deferral in main.py; B-5 does NOT do it.

This is a REGRESSION LOCK: if a future, separately-authorized runtime-activation phase flips the deferral, this test is
expected to fail and that phase owns updating it. It COMPLEMENTS (does not duplicate) the existing behavior guards:
  - tests/control_plane/test_onboarding_orchestration.py::test_default_composition_is_in_memory
  - tests/control_plane/test_onboarding_orchestration.py::test_postgres_adapter_deferred_to_b4
  - tests/control_plane/test_distinctness_ledger_b2.py  (B-2 WP-H13)

Driver containment: imports only control_plane app modules (no database-driver import). Construction performs no I/O, so
no live PostgreSQL/Docker/cloud/secrets are required. Standalone-runnable:
  python tests/control_plane/test_b5_runtime_deferral_guard.py
"""

from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))  # backend on path

from control_plane import main as cp_main  # noqa: E402
from control_plane.distinctness import InMemoryDistinctnessLedger  # noqa: E402
from control_plane.provisioning import InMemoryProvisioningOperator  # noqa: E402

_NON_IN_MEMORY = "postgres"


def _with_env(name, value):
    """Set/clear an env var (value=None -> unset); return a restore() callable."""
    saved = os.environ.get(name)
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value

    def restore():
        if saved is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = saved

    return restore


def test_default_composition_is_in_memory_no_io() -> None:
    # Both selectors unset -> in-memory composition; construction performs no I/O (the deferred default).
    restore_prov = _with_env(cp_main.PROVISIONING_ADAPTER_ENV, None)
    restore_led = _with_env(cp_main.DISTINCTNESS_LEDGER_ENV, None)
    try:
        cp = cp_main.ControlPlane()
        assert isinstance(cp.operator, InMemoryProvisioningOperator)
        assert isinstance(cp.provisioning._ledger, InMemoryDistinctnessLedger)
    finally:
        restore_led()
        restore_prov()


def test_provisioning_adapter_non_in_memory_fails_closed() -> None:
    restore = _with_env(cp_main.PROVISIONING_ADAPTER_ENV, _NON_IN_MEMORY)
    try:
        raised = False
        try:
            cp_main.ControlPlane()
        except NotImplementedError:
            raised = True
        assert raised, "SP2_CP_PROVISIONING_ADAPTER non-in_memory must fail closed (NotImplementedError)"
    finally:
        restore()


def test_distinctness_ledger_non_in_memory_fails_closed() -> None:
    restore = _with_env(cp_main.DISTINCTNESS_LEDGER_ENV, _NON_IN_MEMORY)
    try:
        raised = False
        try:
            cp_main.ControlPlane()
        except NotImplementedError:
            raised = True
        assert raised, "SP2_CP_DISTINCTNESS_LEDGER non-in_memory must fail closed (NotImplementedError)"
    finally:
        restore()


if __name__ == "__main__":
    test_default_composition_is_in_memory_no_io()
    test_provisioning_adapter_non_in_memory_fails_closed()
    test_distinctness_ledger_non_in_memory_fails_closed()
    print("ALL PASSED")
