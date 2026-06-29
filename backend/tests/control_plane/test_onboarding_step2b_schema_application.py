"""PRD 07B — onboarding Step 2b (tenant schema application) wiring (in-memory; no I/O).

Pins the schema-application step the onboarding orchestrator runs between database provision and
verification: ordering, fail-closed semantics, the idempotency guard, the in-memory applicator port
contract, and the controlled-non-prod composition (default in-memory; the live applicator is
composed directly by the requires_pg harness, so composition-level selection defers). Pure stdlib;
no driver; no live PostgreSQL (that is the requires_pg harness). Standalone-runnable:
`python tests/control_plane/test_onboarding_step2b_schema_application.py`.

The deeper "no tenant reaches Ready on live PG without Step 2b" non-vacuity is proven by
`requires_pg/test_pg_onboarding_e2e_schema_application.py`; here the load-bearing-ness is shown at
unit level (a failing applicator fails closed and never reaches the gate).
"""

from __future__ import annotations

import os
import pathlib
import sys
from typing import List, Optional, Tuple

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
from control_plane.distinctness import DistinctnessResult  # noqa: E402
from control_plane.onboarding import OnboardingOrchestrator  # noqa: E402
from control_plane.provisioning import (  # noqa: E402
    InMemoryProvisioningOperator,
    ProvisioningVerificationService,
    TenantSchemaApplicationError,
    TenantSchemaApplicator,
    tenant_database_name,
)
from control_plane.records import TenantLifecycleState  # noqa: E402
from control_plane.registry import TenantRegistry  # noqa: E402
from shared.secrets import SecretRef  # noqa: E402

_ORG = "org_ref_x"
_FED = "fed_ref_x"


class _RecordingApplicator(TenantSchemaApplicator):
    """Records each apply_schema call (tenant_id, target, association_ref); applies nothing."""

    def __init__(self) -> None:
        self.calls: List[Tuple[str, str, SecretRef]] = []

    def apply_schema(self, tenant_id: str, *, target: str, association_ref: SecretRef) -> None:
        self.calls.append((tenant_id, target, association_ref))


class _FailingApplicator(TenantSchemaApplicator):
    """Applicator whose schema-application step fails (fail-closed branch exercise)."""

    def apply_schema(self, tenant_id: str, *, target: str, association_ref: SecretRef) -> None:
        raise TenantSchemaApplicationError("forced failure")


def _orchestrator(store: InMemoryControlStore, *, applicator: Optional[TenantSchemaApplicator] = None) -> OnboardingOrchestrator:
    audit = ControlPlaneAudit(store)
    registry = TenantRegistry(store, audit)
    gate = ProvisioningVerificationService(
        store,
        audit,
        InMemoryTenantDatabaseProbe(schema_version="1"),
        InMemoryDistinctnessEvidenceProvider(),
        nonprod_control_db_evidence(),
        supported_schema_versions=["1"],
    )
    return OnboardingOrchestrator(registry, InMemoryProvisioningOperator(), gate, audit, applicator or InMemoryTenantSchemaApplicator())


def _onboard(orch: OnboardingOrchestrator, tenant_id: str = "t1", correlation_id: str = "c1") -> DistinctnessResult:
    return orch.onboard(tenant_id, organization_ref=_ORG, federation_config_ref=_FED, actor="ops_ref", correlation_id=correlation_id).result


def _actions(store: InMemoryControlStore) -> List[str]:
    return [r.action for r in store.list_audit()]


def _state(store: InMemoryControlStore, tenant_id: str = "t1") -> TenantLifecycleState:
    rec = store.get_tenant(tenant_id)
    assert rec is not None
    return rec.lifecycle_state


def test_step2b_emitted_between_provision_and_verify() -> None:
    store = InMemoryControlStore()
    assert _onboard(_orchestrator(store)) is DistinctnessResult.VERIFIED
    acts = _actions(store)
    # Step 2b is bracketed by PROVISION_SUCCEEDED before and DISTINCTNESS_VERIFICATION_STARTED after.
    i_prov = acts.index(events.DATABASE_PROVISION_SUCCEEDED)
    i_started = acts.index(events.TENANT_SCHEMA_APPLICATION_STARTED)
    i_ok = acts.index(events.TENANT_SCHEMA_APPLICATION_SUCCEEDED)
    i_verify = acts.index(events.DISTINCTNESS_VERIFICATION_STARTED)
    assert i_prov < i_started < i_ok < i_verify, acts


def test_step2b_failure_fails_closed_and_skips_verify() -> None:
    store = InMemoryControlStore()
    result = _onboard(_orchestrator(store, applicator=_FailingApplicator()))
    assert result is not DistinctnessResult.VERIFIED
    assert _state(store) is not TenantLifecycleState.READY
    acts = _actions(store)
    assert events.TENANT_SCHEMA_APPLICATION_FAILED in acts
    assert events.TENANT_SCHEMA_APPLICATION_SUCCEEDED not in acts
    assert events.DISTINCTNESS_VERIFICATION_STARTED not in acts  # never reached the gate (fail-closed)


def test_step2b_success_reaches_ready() -> None:
    store = InMemoryControlStore()
    assert _onboard(_orchestrator(store)) is DistinctnessResult.VERIFIED
    assert _state(store) is TenantLifecycleState.READY
    acts = _actions(store)
    assert events.TENANT_SCHEMA_APPLICATION_SUCCEEDED in acts


def test_step2b_invoked_with_tenant_association() -> None:
    store = InMemoryControlStore()
    rec = _RecordingApplicator()
    assert _onboard(_orchestrator(store, applicator=rec)) is DistinctnessResult.VERIFIED
    assert len(rec.calls) == 1, rec.calls
    tenant_id, target, association_ref = rec.calls[0]
    assert tenant_id == "t1"
    assert target == tenant_database_name("t1")
    # The association passed to the applicator references the tenant target (D-14: by reference only).
    assert association_ref.store_ref == tenant_database_name("t1")


def test_in_memory_applicator_records_and_never_fails() -> None:
    app = InMemoryTenantSchemaApplicator()
    app.apply_schema("t1", target="sp2_tenant_t1", association_ref=SecretRef(store_ref="sp2_tenant_t1", version="1"))
    assert app.applied == [("t1", "sp2_tenant_t1")]


def test_idempotent_onboard_does_not_reapply() -> None:
    store = InMemoryControlStore()
    rec = _RecordingApplicator()
    orch = _orchestrator(store, applicator=rec)
    assert _onboard(orch) is DistinctnessResult.VERIFIED
    assert len(rec.calls) == 1
    # A second onboard on an already-Ready tenant is a no-op (idempotency guard) — no re-apply.
    orch.onboard("t1", organization_ref=_ORG, federation_config_ref=_FED, actor="ops_ref", correlation_id="c2")
    assert len(rec.calls) == 1, "Step 2b must not re-apply on an already-onboarded tenant"


def test_non_vacuity_step2b_is_load_bearing() -> None:
    # Same in-memory verify path: a SUCCEEDING applicator reaches Ready and DID invoke apply_schema;
    # a FAILING applicator does NOT reach Ready and never starts verify. The differing outcomes prove
    # Step 2b is on the load-bearing path (not a vacuous no-op).
    ok_store, rec = InMemoryControlStore(), _RecordingApplicator()
    assert _onboard(_orchestrator(ok_store, applicator=rec)) is DistinctnessResult.VERIFIED
    assert len(rec.calls) == 1 and _state(ok_store) is TenantLifecycleState.READY

    bad_store = InMemoryControlStore()
    assert _onboard(_orchestrator(bad_store, applicator=_FailingApplicator())) is not DistinctnessResult.VERIFIED
    assert _state(bad_store) is not TenantLifecycleState.READY


def test_schema_applicator_default_in_memory() -> None:
    # PRD 07B / OB-1 parity: env unset -> in-memory applicator; onboarding reaches Ready with no I/O.
    saved = os.environ.pop(cp_main.TENANT_SCHEMA_APPLICATOR_ENV, None)
    try:
        cp = cp_main.ControlPlane()
        assert isinstance(cp.schema_applicator, InMemoryTenantSchemaApplicator)
        out = cp.onboarding.onboard("t9", organization_ref=_ORG, federation_config_ref=_FED, actor="ops_ref", correlation_id="c9")
        assert out.result is DistinctnessResult.VERIFIED
        assert _state(cp.store, "t9") is TenantLifecycleState.READY
    finally:
        if saved is not None:
            os.environ[cp_main.TENANT_SCHEMA_APPLICATOR_ENV] = saved


def test_schema_applicator_postgres_deferred() -> None:
    # The live applicator is composed directly by the requires_pg harness; composition-level
    # selection defers (fail closed), mirroring the SP2_CP_PROVISIONING_ADAPTER deferral.
    saved = os.environ.get(cp_main.TENANT_SCHEMA_APPLICATOR_ENV)
    os.environ[cp_main.TENANT_SCHEMA_APPLICATOR_ENV] = "postgres"
    try:
        raised = False
        try:
            cp_main.ControlPlane()
        except NotImplementedError:
            raised = True
        assert raised, "postgres schema-applicator selection must defer (composed directly by the harness)"
    finally:
        if saved is None:
            os.environ.pop(cp_main.TENANT_SCHEMA_APPLICATOR_ENV, None)
        else:
            os.environ[cp_main.TENANT_SCHEMA_APPLICATOR_ENV] = saved


_TESTS = [
    test_step2b_emitted_between_provision_and_verify,
    test_step2b_failure_fails_closed_and_skips_verify,
    test_step2b_success_reaches_ready,
    test_step2b_invoked_with_tenant_association,
    test_in_memory_applicator_records_and_never_fails,
    test_idempotent_onboard_does_not_reapply,
    test_non_vacuity_step2b_is_load_bearing,
    test_schema_applicator_default_in_memory,
    test_schema_applicator_postgres_deferred,
]

if __name__ == "__main__":
    for _t in _TESTS:
        _t()
        print("PASS:", _t.__name__)
    print("ALL PASSED")
