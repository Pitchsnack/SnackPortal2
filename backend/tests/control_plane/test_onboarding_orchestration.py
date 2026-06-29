"""OnboardingOrchestrator — D-15 orchestration wiring (B-1) end-to-end (in-memory, no I/O).

Drives Register -> Provision -> Associate -> Verify -> Ready/Failed via the merged D-15
components; asserts the fail-closed branches, re-association, suspension routing-disable,
the idempotency guard, and the controlled-non-prod baselines (no new lifecycle state, no
new audit vocabulary, default composition is in-memory). Pure stdlib; no driver; no live
PostgreSQL (that is B-4). Standalone-runnable:
`python tests/control_plane/test_onboarding_orchestration.py`.
"""

from __future__ import annotations

import os
import pathlib
import sys
from dataclasses import replace
from typing import List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))  # backend on path

from control_plane import events  # noqa: E402
from control_plane import main as cp_main  # noqa: E402
from control_plane.adapters.providers.in_memory_distinctness import (  # noqa: E402
    InMemoryDistinctnessEvidenceProvider,
    nonprod_control_db_evidence,
)
from control_plane.adapters.providers.in_memory_probe import InMemoryTenantDatabaseProbe  # noqa: E402
from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.adapters.providers.in_memory_tenant_schema_applicator import (  # noqa: E402
    InMemoryTenantSchemaApplicator,
)
from control_plane.audit import ControlPlaneAudit  # noqa: E402
from control_plane.distinctness import (  # noqa: E402
    DistinctnessEvidence,
    DistinctnessEvidenceProvider,
    DistinctnessOutcome,
    DistinctnessResult,
)
from control_plane.onboarding import OnboardingOrchestrator  # noqa: E402
from control_plane.provisioning import (  # noqa: E402
    InMemoryProvisioningOperator,
    ProvisioningOperator,
    ProvisioningVerificationService,
    ProvisionResult,
    tenant_database_name,
)
from control_plane.records import TenantLifecycleState  # noqa: E402
from control_plane.registry import TenantRegistry  # noqa: E402
from control_plane.verification import TenantDatabaseProbe  # noqa: E402
from shared.secrets import SecretRef  # noqa: E402

# The IC-002 lifecycle states and the D-15 audit vocabulary as merged @ baseline — the
# baseline guards (no-new-state / no-new-vocab) compare against these exact sets.
EXPECTED_STATES = {"Registered", "Provisioning", "Verifying", "Ready", "Suspended", "Failed", "Decommissioned"}
EXPECTED_EVENT_ACTIONS = {
    "TenantRegistered",
    "DatabaseProvisionRequested",
    "DatabaseProvisionSucceeded",
    "DatabaseProvisionFailed",
    "DatabaseAssociated",
    "SecretReferenceRegistered",
    "TenantSchemaApplicationStarted",
    "TenantSchemaApplicationSucceeded",
    "TenantSchemaApplicationFailed",
    "DistinctnessVerificationStarted",
    "DistinctnessVerificationPassed",
    "DistinctnessVerificationFailed",
    "VerificationIncomplete",
    "IsolationAnomaly",
    "RoutingEnabled",
    "RoutingDisabled",
    "RouterCacheInvalidated",
    "RegistryMappingChanged",
    "TenantSuspended",
    "TenantReactivated",
    "TenantDecommissionStarted",
    "TenantDecommissionCompleted",
}

_ORG = "org_ref_x"
_FED = "fed_ref_x"


class _FailingOperator(ProvisioningOperator):
    """Operator whose provision step fails (to exercise the fail-closed branch)."""

    def provision(self, tenant_id: str, *, target: str) -> ProvisionResult:
        raise RuntimeError("provision failed")

    def deprovision(self, *, target: str) -> None:
        pass


class _AnomalyEvidenceProvider(DistinctnessEvidenceProvider):
    """Returns evidence whose physical fingerprint collides with the Control DB -> anomaly."""

    def __init__(self, control: DistinctnessEvidence) -> None:
        self._control = control

    def gather(self, association_ref: SecretRef, *, sentinel_token: str, sentinel_namespace: str) -> Optional[DistinctnessEvidence]:
        return replace(
            self._control,  # keeps the Control-DB fingerprint -> ISOLATION_ANOMALY (control collision)
            observed_target=association_ref.store_ref,  # matches intended target (not a misroute)
            secret_ref_key=association_ref.store_ref,
            sentinel_namespace=sentinel_namespace,
            sentinel_token=sentinel_token,
            sentinel_written=True,
        )


def _orchestrator(
    store: InMemoryControlStore,
    *,
    operator: Optional[ProvisioningOperator] = None,
    probe: Optional[TenantDatabaseProbe] = None,
    evidence: Optional[DistinctnessEvidenceProvider] = None,
) -> OnboardingOrchestrator:
    audit = ControlPlaneAudit(store)
    registry = TenantRegistry(store, audit)
    gate = ProvisioningVerificationService(
        store,
        audit,
        probe or InMemoryTenantDatabaseProbe(schema_version="1"),
        evidence or InMemoryDistinctnessEvidenceProvider(),
        nonprod_control_db_evidence(),
        supported_schema_versions=["1"],
    )
    return OnboardingOrchestrator(registry, operator or InMemoryProvisioningOperator(), gate, audit, InMemoryTenantSchemaApplicator())


def _actions(store: InMemoryControlStore) -> List[str]:
    return [r.action for r in store.list_audit()]


def _state(store: InMemoryControlStore, tenant_id: str = "t1") -> TenantLifecycleState:
    rec = store.get_tenant(tenant_id)
    assert rec is not None
    return rec.lifecycle_state


def _onboard(orch: OnboardingOrchestrator, tenant_id: str = "t1", correlation_id: str = "c1") -> DistinctnessOutcome:
    return orch.onboard(
        tenant_id,
        organization_ref=_ORG,
        federation_config_ref=_FED,
        actor="ops_ref",
        correlation_id=correlation_id,
    )


def test_onboard_reaches_ready() -> None:
    store = InMemoryControlStore()
    out = _onboard(_orchestrator(store))
    assert out.result is DistinctnessResult.VERIFIED, out.reason
    assert _state(store) is TenantLifecycleState.READY
    acts = _actions(store)
    for action in (
        events.DATABASE_PROVISION_REQUESTED,
        events.DATABASE_PROVISION_SUCCEEDED,
        events.DATABASE_ASSOCIATED,
        events.DISTINCTNESS_VERIFICATION_PASSED,
        events.ROUTING_ENABLED,
    ):
        assert action in acts, action


def test_provision_failure_fails_closed() -> None:
    store = InMemoryControlStore()
    out = _onboard(_orchestrator(store, operator=_FailingOperator()))
    assert out.result is not DistinctnessResult.VERIFIED
    assert _state(store) is not TenantLifecycleState.READY
    acts = _actions(store)
    assert events.DATABASE_PROVISION_FAILED in acts
    assert events.DISTINCTNESS_VERIFICATION_STARTED not in acts  # never reached the gate


def test_unreachable_fails_closed() -> None:
    store = InMemoryControlStore()
    out = _onboard(_orchestrator(store, probe=InMemoryTenantDatabaseProbe(reachable=False)))
    assert out.result is not DistinctnessResult.VERIFIED
    assert _state(store) is TenantLifecycleState.FAILED


def test_schema_mismatch_fails_closed() -> None:
    store = InMemoryControlStore()
    out = _onboard(_orchestrator(store, probe=InMemoryTenantDatabaseProbe(schema_version="2")))
    assert out.result is not DistinctnessResult.VERIFIED
    assert _state(store) is TenantLifecycleState.FAILED


def test_isolation_anomaly_fails_closed() -> None:
    store = InMemoryControlStore()
    out = _onboard(_orchestrator(store, evidence=_AnomalyEvidenceProvider(nonprod_control_db_evidence())))
    assert out.result is DistinctnessResult.ISOLATION_ANOMALY
    assert _state(store) is TenantLifecycleState.FAILED
    assert events.ISOLATION_ANOMALY in _actions(store)


def test_idempotent_onboard_does_not_reverify() -> None:
    store = InMemoryControlStore()
    orch = _orchestrator(store)
    assert _onboard(orch).result is DistinctnessResult.VERIFIED
    before = _actions(store).count(events.DISTINCTNESS_VERIFICATION_STARTED)
    out2 = _onboard(orch, correlation_id="c2")  # second onboard on an already-Ready tenant
    after = _actions(store).count(events.DISTINCTNESS_VERIFICATION_STARTED)
    assert before == after == 1  # no re-verify
    assert _state(store) is TenantLifecycleState.READY
    assert out2.reason == "already_onboarded"


def test_reassociate_reverifies() -> None:
    store = InMemoryControlStore()
    orch = _orchestrator(store)
    assert _onboard(orch).result is DistinctnessResult.VERIFIED
    out = orch.reassociate(
        "t1",
        new_association_ref=SecretRef(store_ref=tenant_database_name("t1"), version="2"),
        actor="ops_ref",
        correlation_id="c3",
    )
    assert out.result is DistinctnessResult.VERIFIED
    acts = _actions(store)
    assert events.REGISTRY_MAPPING_CHANGED in acts
    assert events.ROUTER_CACHE_INVALIDATED in acts


def test_disable_routing() -> None:
    store = InMemoryControlStore()
    orch = _orchestrator(store)
    assert _onboard(orch).result is DistinctnessResult.VERIFIED
    orch.disable_routing("t1", actor="ops_ref", correlation_id="c4")
    acts = _actions(store)
    assert events.ROUTING_DISABLED in acts
    assert events.ROUTER_CACHE_INVALIDATED in acts


def test_no_new_lifecycle_states() -> None:
    # Baseline guard (GUARDS-001): catches a state added to records.py even if unused.
    assert {s.value for s in TenantLifecycleState} == EXPECTED_STATES


def test_no_new_audit_vocabulary() -> None:
    # Baseline guard (GUARDS-001): catches an event added to events.py even if unused.
    actions = {v for k, v in vars(events).items() if k.isupper() and isinstance(v, str)}
    assert actions == EXPECTED_EVENT_ACTIONS


def test_default_composition_is_in_memory() -> None:
    # OB-1 / GUARDS-002: env unset -> in-memory composition, reaching Ready with no I/O.
    saved = os.environ.pop(cp_main.PROVISIONING_ADAPTER_ENV, None)
    try:
        cp = cp_main.ControlPlane()
        assert isinstance(cp.operator, InMemoryProvisioningOperator)
        out = cp.onboarding.onboard("t9", organization_ref=_ORG, federation_config_ref=_FED, actor="ops_ref", correlation_id="c9")
        assert out.result is DistinctnessResult.VERIFIED
        assert _state(cp.store, "t9") is TenantLifecycleState.READY
    finally:
        if saved is not None:
            os.environ[cp_main.PROVISIONING_ADAPTER_ENV] = saved


def test_postgres_adapter_deferred_to_b4() -> None:
    # OB-2: selecting a non-default adapter defers to B-4 (no live-PG in B-1).
    saved = os.environ.get(cp_main.PROVISIONING_ADAPTER_ENV)
    os.environ[cp_main.PROVISIONING_ADAPTER_ENV] = "postgres"
    try:
        raised = False
        try:
            cp_main.ControlPlane()
        except NotImplementedError:
            raised = True
        assert raised, "postgres adapter selection must defer to B-4"
    finally:
        if saved is None:
            os.environ.pop(cp_main.PROVISIONING_ADAPTER_ENV, None)
        else:
            os.environ[cp_main.PROVISIONING_ADAPTER_ENV] = saved


_TESTS = [
    test_onboard_reaches_ready,
    test_provision_failure_fails_closed,
    test_unreachable_fails_closed,
    test_schema_mismatch_fails_closed,
    test_isolation_anomaly_fails_closed,
    test_idempotent_onboard_does_not_reverify,
    test_reassociate_reverifies,
    test_disable_routing,
    test_no_new_lifecycle_states,
    test_no_new_audit_vocabulary,
    test_default_composition_is_in_memory,
    test_postgres_adapter_deferred_to_b4,
]

if __name__ == "__main__":
    for _t in _TESTS:
        _t()
        print("PASS:", _t.__name__)
    print("ALL PASSED")
