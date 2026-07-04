"""PRD 06 B-5 / PRD 07D-1 / PRD 07D-2a — runtime composition-activation + coherence LOCK (no live resources).

HISTORY. This file began as the B-5 runtime-deferral regression lock (its charter authorized the
activating phase to update it); PRD 07D-1 flipped it to the composition-activation contract; PRD
07D-2a extends it with the SELECTOR-COHERENCE MATRIX (AT-07D1-9) and the control-evidence
sentinel-proof rule (AT-07D1-8).

WHAT IT PINS NOW:
  - the DEFAULT composition (all four selectors unset) remains fully in-memory, constructs with NO I/O;
  - the ALL-POSTGRES composition (all FOUR selectors 'postgres') constructs lazily with ZERO database
    I/O (07D-1 behavior, now under the 07D-2a matrix RULE 3);
  - RULE 1 (07D-2a): 'postgres' on ANY live-side selector (provisioning / schema applicator /
    distinctness ledger) without ALL FOUR selectors 'postgres' fails closed with ValueError at
    construction — half-live compositions manufacture orphans or record fabricated evidence;
  - RULE 2 (07D-2a): control-store-standalone 'postgres' remains ALLOWED — the live-proven B-7B
    durable audit/registry posture (pinned here so a future matrix change cannot silently break the
    off-limits B-7B tests/harness);
  - UNKNOWN selector values still fail closed (ValueError; never a silent fallback, never I/O);
  - control evidence with an UNPROVEN sentinel is rejected (_proven_control_evidence -> None; the
    lazy gate then fails closed) — AT-07D1-8.

RUNTIME_ACTIVATION_ENABLED=false and the b5 activation-gate semantics are CI-enforced by the existing
architecture guard (test_b5_runtime_activation_gate_contract.py) — not duplicated here (07D-2a R1-7).

Driver containment: no database-driver import here — the recorder patches the driver module attribute
REACHED THROUGH the adapter module (the test_distinctness_ledger_b2 precedent); the postgres adapter
classes are imported for isinstance checks only (import-only, the b7b default-suite precedent).
Construction performs no I/O, so no live PostgreSQL/Docker/cloud/secrets are required.
Standalone-runnable:
  python tests/control_plane/test_b5_runtime_deferral_guard.py
"""

from __future__ import annotations

import os
import pathlib
import sys
from typing import Dict, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))  # backend on path

from control_plane import main as cp_main  # noqa: E402
from control_plane.adapters.providers import postgres_distinctness_ledger as ledger_mod  # noqa: E402
from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.adapters.providers.postgres_provisioning_operator import PostgresProvisioningOperator  # noqa: E402
from control_plane.adapters.providers.postgres_store import PostgresControlStore  # noqa: E402
from control_plane.adapters.providers.postgres_tenant_schema_applicator import PostgresTenantSchemaApplicator  # noqa: E402
from control_plane.distinctness import DistinctnessEvidence, InMemoryDistinctnessLedger  # noqa: E402
from control_plane.provisioning import InMemoryProvisioningOperator  # noqa: E402

# ALL FOUR selectors (07D-2a: the coherence matrix spans the control store + the live-side trio).
_SELECTOR_ENVS = (
    cp_main.CONTROL_STORE_ENV,
    cp_main.PROVISIONING_ADAPTER_ENV,
    cp_main.TENANT_SCHEMA_APPLICATOR_ENV,
    cp_main.DISTINCTNESS_LEDGER_ENV,
)


def _with_env_map(values: Dict[str, Optional[str]]):
    """Set/clear a map of env vars (None -> unset); return one restore() callable."""
    saved = {name: os.environ.get(name) for name in values}
    for name, value in values.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

    def restore() -> None:
        for name, old in saved.items():
            if old is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old

    return restore


def _all(value: Optional[str]) -> Dict[str, Optional[str]]:
    return {name: value for name in _SELECTOR_ENVS}


def _patch_connect(recorder):
    """Swap the shared driver module's connect via the adapter module attribute (no driver import
    here — the psycopg module object is shared by every postgres adapter). Returns restore()."""
    orig = ledger_mod.psycopg.connect
    ledger_mod.psycopg.connect = recorder

    def restore() -> None:
        ledger_mod.psycopg.connect = orig

    return restore


def test_default_composition_is_in_memory_no_io() -> None:
    # All four selectors unset -> in-memory composition; construction performs no I/O (RULE 3).
    calls: list = []
    restore_c = _patch_connect(lambda *a, **k: calls.append((a, k)))
    restore_e = _with_env_map(_all(None))
    try:
        cp = cp_main.ControlPlane()
        assert isinstance(cp.store, InMemoryControlStore)
        assert isinstance(cp.operator, InMemoryProvisioningOperator)
        assert isinstance(cp.provisioning._ledger, InMemoryDistinctnessLedger)
        assert calls == [], "default construction must perform no live DB connection"
    finally:
        restore_e()
        restore_c()


def test_all_postgres_selection_composes_real_adapters_lazily() -> None:
    # PRD 07D-1 (D-B) under 07D-2a RULE 3: ALL FOUR selectors 'postgres' compose the real adapters
    # through ControlPlane() — construction stays LAZY (zero database I/O; B-7B pattern).
    calls: list = []
    restore_c = _patch_connect(lambda *a, **k: calls.append((a, k)))
    restore_e = _with_env_map(_all("postgres"))
    try:
        cp = cp_main.ControlPlane()
        assert isinstance(cp.store, PostgresControlStore), "postgres must select the durable store"
        assert isinstance(cp.operator, PostgresProvisioningOperator), "postgres must select the real operator"
        assert isinstance(cp.schema_applicator, PostgresTenantSchemaApplicator), "postgres must select the real applicator"
        assert isinstance(cp.provisioning._ledger, ledger_mod.PostgresDistinctnessLedger), "postgres must select the durable ledger"
        assert calls == [], "all-postgres construction must perform ZERO database I/O (lazy-connect)"
    finally:
        restore_e()
        restore_c()


def test_forbidden_selector_mixes_fail_closed() -> None:
    # PRD 07D-2a RULE 1: any live-side 'postgres' without ALL FOUR 'postgres' -> ValueError at
    # construction, with zero I/O. Covers (at minimum) the five hazard minima from the package.
    forbidden = [
        # provisioning-only postgres (orphans-on-restart hazard — the largest orphan source)
        {cp_main.PROVISIONING_ADAPTER_ENV: "postgres"},
        # applicator-only postgres (real DDL against an un-provisioned/arbitrary target)
        {cp_main.TENANT_SCHEMA_APPLICATOR_ENV: "postgres"},
        # ledger-only postgres (fabricated evidence durably recorded — fail-open)
        {cp_main.DISTINCTNESS_LEDGER_ENV: "postgres"},
        # three live-side postgres WITHOUT the control store (the pre-07D-2a b5 test shape)
        {
            cp_main.PROVISIONING_ADAPTER_ENV: "postgres",
            cp_main.TENANT_SCHEMA_APPLICATOR_ENV: "postgres",
            cp_main.DISTINCTNESS_LEDGER_ENV: "postgres",
        },
        # control store + ledger postgres WITHOUT provisioning (fabricated-evidence combo, R1-3)
        {cp_main.CONTROL_STORE_ENV: "postgres", cp_main.DISTINCTNESS_LEDGER_ENV: "postgres"},
    ]
    calls: list = []
    restore_c = _patch_connect(lambda *a, **k: calls.append((a, k)))
    try:
        for mix in forbidden:
            env = _all(None)
            env.update(mix)
            restore_e = _with_env_map(env)
            try:
                raised = False
                try:
                    cp_main.ControlPlane()
                except ValueError:
                    raised = True
                assert raised, f"forbidden selector mix must fail closed (ValueError): {mix}"
            finally:
                restore_e()
        assert calls == [], "a rejected selector mix must not open any connection before raising"
    finally:
        restore_c()


def test_control_store_standalone_postgres_remains_allowed() -> None:
    # PRD 07D-2a RULE 2: control-store-standalone 'postgres' is the live-proven B-7B durable
    # audit/registry posture and MUST keep constructing (lazily) — this pin protects the
    # off-limits B-7B selector tests/harness from a future matrix regression.
    calls: list = []
    restore_c = _patch_connect(lambda *a, **k: calls.append((a, k)))
    env = _all(None)
    env[cp_main.CONTROL_STORE_ENV] = "postgres"
    restore_e = _with_env_map(env)
    try:
        cp = cp_main.ControlPlane()
        assert isinstance(cp.store, PostgresControlStore), "RULE 2: durable store must be selected"
        assert isinstance(cp.operator, InMemoryProvisioningOperator), "live side stays in-memory"
        assert calls == [], "RULE 2 construction must perform no I/O (lazy-connect)"
    finally:
        restore_e()
        restore_c()


def test_unknown_selector_values_fail_closed() -> None:
    # Fail-closed preserved: any unknown selector value raises (ValueError) with zero I/O —
    # never a silent fallback, never a half-wired composition. (Whether the coherence check or
    # the per-selector builder raises first is immaterial — the outcome is ValueError.)
    calls: list = []
    restore_c = _patch_connect(lambda *a, **k: calls.append((a, k)))
    try:
        for env_name in _SELECTOR_ENVS:
            for value in ("durable", "true", "x", "POSTGRES!"):
                env = _all(None)
                env[env_name] = value
                restore_e = _with_env_map(env)
                try:
                    raised = False
                    try:
                        cp_main.ControlPlane()
                    except ValueError:
                        raised = True
                    assert raised, f"{env_name}={value!r} must fail closed (ValueError)"
                finally:
                    restore_e()
        assert calls == [], "a rejected selector value must not open any connection before raising"
    finally:
        restore_c()


def _evidence(*, written: bool, token: str | None) -> DistinctnessEvidence:
    return DistinctnessEvidence(
        system_identifier="sysX",
        database_identity="ctl:1",
        observed_target="sp2_ctl",
        secret_ref_key="control/control-store-dsn",
        sentinel_namespace="dv_sentinel_control",
        sentinel_token=token,
        sentinel_written=written,
    )


def test_unproven_control_evidence_is_rejected() -> None:
    # PRD 07D-2a (AT-07D1-8): control evidence without a PROVEN write-sentinel must NOT count as
    # resolved — _proven_control_evidence returns None (the lazy gate then fails closed with
    # ProvisioningError). Proven evidence passes through unchanged.
    assert cp_main._proven_control_evidence(None) is None
    assert cp_main._proven_control_evidence(_evidence(written=False, token="tok")) is None
    assert cp_main._proven_control_evidence(_evidence(written=True, token=None)) is None
    assert cp_main._proven_control_evidence(_evidence(written=False, token=None)) is None
    proven = _evidence(written=True, token="tok")
    assert cp_main._proven_control_evidence(proven) is proven, "proven evidence must pass through unchanged"


if __name__ == "__main__":
    test_default_composition_is_in_memory_no_io()
    test_all_postgres_selection_composes_real_adapters_lazily()
    test_forbidden_selector_mixes_fail_closed()
    test_control_store_standalone_postgres_remains_allowed()
    test_unknown_selector_values_fail_closed()
    test_unproven_control_evidence_is_rejected()
    print("ALL PASSED")
