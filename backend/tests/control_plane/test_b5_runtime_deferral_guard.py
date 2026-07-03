"""PRD 06 B-5 / PRD 07D-1 — runtime composition-activation LOCK (controlled non-production; no live resources).

HISTORY. This file began as the B-5 runtime-deferral regression lock: main.py kept the durable/real adapters
DEFERRED and any non-in_memory selection failed closed with NotImplementedError. Its own charter said a future,
separately-authorized runtime-activation phase "owns updating it" — PRD 07D-1 (composition activation +
canonical tenant secret references) is that phase, and this update is the self-authorized flip.

WHAT IT PINS NOW (the 07D-1 activation contract):
  - the DEFAULT composition (all selectors unset) remains fully in-memory and constructs with NO I/O;
  - SP2_CP_PROVISIONING_ADAPTER / SP2_CP_TENANT_SCHEMA_APPLICATOR / SP2_CP_DISTINCTNESS_LEDGER = 'postgres'
    now SELECT the real adapters (PostgresProvisioningOperator / PostgresTenantSchemaApplicator /
    PostgresDistinctnessLedger) — construction is LAZY and performs ZERO database I/O (B-7B pattern; the
    driver connect is patched with a recorder to prove it);
  - every UNKNOWN selector value still fails closed (ValueError; never a silent fallback, never I/O).

Driver containment: no database-driver import here — the recorder patches the driver module attribute
REACHED THROUGH the adapter module (the test_distinctness_ledger_b2 precedent); the postgres adapter classes
are imported for isinstance checks only (import-only, the b7b default-suite precedent). Construction performs
no I/O, so no live PostgreSQL/Docker/cloud/secrets are required. Standalone-runnable:
  python tests/control_plane/test_b5_runtime_deferral_guard.py
"""

from __future__ import annotations

import os
import pathlib
import sys
from typing import Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))  # backend on path

from control_plane import main as cp_main  # noqa: E402
from control_plane.adapters.providers import postgres_distinctness_ledger as ledger_mod  # noqa: E402
from control_plane.adapters.providers.postgres_provisioning_operator import PostgresProvisioningOperator  # noqa: E402
from control_plane.adapters.providers.postgres_tenant_schema_applicator import PostgresTenantSchemaApplicator  # noqa: E402
from control_plane.distinctness import InMemoryDistinctnessLedger  # noqa: E402
from control_plane.provisioning import InMemoryProvisioningOperator  # noqa: E402

_SELECTOR_ENVS = (
    cp_main.PROVISIONING_ADAPTER_ENV,
    cp_main.TENANT_SCHEMA_APPLICATOR_ENV,
    cp_main.DISTINCTNESS_LEDGER_ENV,
)


def _with_env(name: str, value: Optional[str]):
    """Set/clear an env var (value=None -> unset); return a restore() callable."""
    saved = os.environ.get(name)
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value

    def restore() -> None:
        if saved is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = saved

    return restore


def _patch_connect(recorder):
    """Swap the shared driver module's connect via the adapter module attribute (no driver import
    here — the psycopg module object is shared by every postgres adapter). Returns restore()."""
    orig = ledger_mod.psycopg.connect
    ledger_mod.psycopg.connect = recorder

    def restore() -> None:
        ledger_mod.psycopg.connect = orig

    return restore


def test_default_composition_is_in_memory_no_io() -> None:
    # All selectors unset -> in-memory composition; construction performs no I/O (the default).
    restores = [_with_env(name, None) for name in _SELECTOR_ENVS]
    calls: list = []
    restore_c = _patch_connect(lambda *a, **k: calls.append((a, k)))
    try:
        cp = cp_main.ControlPlane()
        assert isinstance(cp.operator, InMemoryProvisioningOperator)
        assert isinstance(cp.provisioning._ledger, InMemoryDistinctnessLedger)
        assert calls == [], "default construction must perform no live DB connection"
    finally:
        restore_c()
        for restore in reversed(restores):
            restore()


def test_postgres_selection_composes_real_adapters_lazily() -> None:
    # PRD 07D-1 (D-B): the activation trio 'postgres' selects the REAL adapters through
    # ControlPlane() composition — and construction is LAZY (zero database I/O; B-7B pattern).
    restores = [_with_env(name, "postgres") for name in _SELECTOR_ENVS]
    calls: list = []
    restore_c = _patch_connect(lambda *a, **k: calls.append((a, k)))
    try:
        cp = cp_main.ControlPlane()
        assert isinstance(cp.operator, PostgresProvisioningOperator), "postgres must select the real operator"
        assert isinstance(cp.schema_applicator, PostgresTenantSchemaApplicator), "postgres must select the real applicator"
        assert isinstance(cp.provisioning._ledger, ledger_mod.PostgresDistinctnessLedger), "postgres must select the durable ledger"
        assert calls == [], "postgres-selected construction must perform ZERO database I/O (lazy-connect)"
    finally:
        restore_c()
        for restore in reversed(restores):
            restore()


def test_unknown_selector_values_fail_closed() -> None:
    # Fail-closed is PRESERVED: any unknown selector value raises (ValueError) with zero I/O —
    # never a silent fallback to in-memory, never a half-wired composition.
    calls: list = []
    restore_c = _patch_connect(lambda *a, **k: calls.append((a, k)))
    try:
        for env_name in _SELECTOR_ENVS:
            for value in ("durable", "true", "x", "POSTGRES!"):
                restore = _with_env(env_name, value)
                try:
                    raised = False
                    try:
                        cp_main.ControlPlane()
                    except ValueError:
                        raised = True
                    assert raised, f"{env_name}={value!r} must fail closed (ValueError)"
                finally:
                    restore()
        assert calls == [], "a rejected selector value must not open any connection before raising"
    finally:
        restore_c()


if __name__ == "__main__":
    test_default_composition_is_in_memory_no_io()
    test_postgres_selection_composes_real_adapters_lazily()
    test_unknown_selector_values_fail_closed()
    print("ALL PASSED")
