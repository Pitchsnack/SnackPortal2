"""OnboardingOrchestrator — D-15 orchestration wiring (B-1) end-to-end (in-memory, no I/O).

Drives Register -> Provision -> Associate -> Verify -> Ready/Failed via the merged D-15
components; asserts the fail-closed branches, re-association, suspension routing-disable,
the idempotency guard, and the controlled-non-prod baselines (no new lifecycle state, no
new audit vocabulary, default composition is in-memory). PRD 07D-1 additions: onboarding
mints the CANONICAL tenant DSN refs (`tenant/<tenant_id>/dsn`, D-A — the old raw
`sp2_tenant_<id>` style is no longer minted), the 'postgres' provisioning selector is now
SELECTABLE (lazy; unknown values fail closed with ValueError), and the control-plane
tenant-DSN provider (adapters/providers/env_tenant_dsn_secret_store.py) is unit-covered
here (folded in per the 07D-1 exec-auth §12.9 — no new default-suite test file). Pure
stdlib; no driver connection; no live PostgreSQL (that is the requires_pg harnesses).
Standalone-runnable: `python tests/control_plane/test_onboarding_orchestration.py`.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
from dataclasses import replace
from typing import List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))  # backend on path

from control_plane import events  # noqa: E402
from control_plane import main as cp_main  # noqa: E402
from control_plane.adapters.providers.env_tenant_dsn_secret_store import EnvTenantDsnSecretStore  # noqa: E402
from control_plane.adapters.providers.in_memory_distinctness import (  # noqa: E402
    nonprod_control_db_evidence,
)
from control_plane.adapters.providers.in_memory_probe import InMemoryTenantDatabaseProbe  # noqa: E402
from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.adapters.providers.in_memory_tenant_schema_applicator import (  # noqa: E402
    InMemoryTenantSchemaApplicator,
)
from control_plane.adapters.providers.postgres_provisioning_operator import PostgresProvisioningOperator  # noqa: E402
from control_plane.audit import ControlPlaneAudit  # noqa: E402
from control_plane.distinctness import (  # noqa: E402
    DistinctnessEvidence,
    DistinctnessEvidenceProvider,
    DistinctnessOutcome,
    DistinctnessResult,
)
from control_plane.onboarding import OnboardingOrchestrator, tenant_dsn_ref, tenant_id_from_dsn_ref  # noqa: E402
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
        # Observed target matches the INTENDED target (so this is NOT a misroute): since 07D-1 the
        # association carries the canonical `tenant/<id>/dsn` ref (D-A), so the intended target is
        # derived from it; a non-canonical ref falls back to the raw store_ref (pre-07D-1 shape).
        tenant_id = tenant_id_from_dsn_ref(association_ref.store_ref)
        intended = tenant_database_name(tenant_id) if tenant_id is not None else association_ref.store_ref
        return replace(
            self._control,  # keeps the Control-DB fingerprint -> ISOLATION_ANOMALY (control collision)
            observed_target=intended,  # matches intended target (not a misroute)
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
        # 07D-1: the composition root's canonical-ref-aware in-memory evidence (the association
        # carries `tenant/<id>/dsn`, not the target name — the base provider alone would misroute).
        evidence or cp_main.CanonicalTenantRefInMemoryEvidence(),
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


def test_onboard_mints_canonical_tenant_ref() -> None:
    # PRD 07D-1 (D-A / AC-13 / AC-14): onboarding mints the canonical `tenant/<tenant_id>/dsn`
    # secret reference — never the old raw-target-name style (`sp2_tenant_<id>`).
    store = InMemoryControlStore()
    assert _onboard(_orchestrator(store)).result is DistinctnessResult.VERIFIED
    rec = store.get_tenant("t1")
    assert rec is not None
    assert rec.database_association_ref.store_ref == tenant_dsn_ref("t1") == "tenant/t1/dsn"
    assert rec.database_association_ref.version == "1"
    assert not rec.database_association_ref.store_ref.startswith("sp2_tenant_"), "old-style refs must no longer be minted"
    # the canonical shape round-trips (the control-plane and router sides parse the same form)
    assert tenant_id_from_dsn_ref(rec.database_association_ref.store_ref) == "t1"
    assert tenant_id_from_dsn_ref("sp2_tenant_t1") is None  # non-canonical -> opaque (no parse)


def test_postgres_adapter_selectable_lazily() -> None:
    # PRD 07D-1 (was: deferred to B-4): 'postgres' now SELECTS the real operator through
    # ControlPlane() composition; construction stays lazy (no I/O — the operator resolves the
    # admin DSN reference per-operation only). The unknown-value fail-closed check is below.
    saved = os.environ.get(cp_main.PROVISIONING_ADAPTER_ENV)
    os.environ[cp_main.PROVISIONING_ADAPTER_ENV] = "postgres"
    try:
        cp = cp_main.ControlPlane()
        assert isinstance(cp.operator, PostgresProvisioningOperator), "postgres must select the real operator"
    finally:
        if saved is None:
            os.environ.pop(cp_main.PROVISIONING_ADAPTER_ENV, None)
        else:
            os.environ[cp_main.PROVISIONING_ADAPTER_ENV] = saved


def test_provisioning_adapter_unknown_value_fails_closed() -> None:
    # Fail-closed preserved (AC-8): an unknown selector value raises ValueError — never a silent
    # fallback to in-memory, never a half-wired composition.
    saved = os.environ.get(cp_main.PROVISIONING_ADAPTER_ENV)
    try:
        for value in ("durable", "true", "x"):
            os.environ[cp_main.PROVISIONING_ADAPTER_ENV] = value
            raised = False
            try:
                cp_main.ControlPlane()
            except ValueError:
                raised = True
            assert raised, f"{value!r} must fail closed (ValueError)"
    finally:
        if saved is None:
            os.environ.pop(cp_main.PROVISIONING_ADAPTER_ENV, None)
        else:
            os.environ[cp_main.PROVISIONING_ADAPTER_ENV] = saved


# --- PRD 07D-1: control-plane tenant-DSN provider unit coverage (exec-auth §12.9 — folded in) -----
_BACKEND = pathlib.Path(__file__).resolve().parents[2]
_ROUTER_PROVIDER_SRC = _BACKEND / "database_router" / "adapters" / "providers" / "env_tenant_secret_store.py"
_CP_PROVIDER_SRC = _BACKEND / "control_plane" / "adapters" / "providers" / "env_tenant_dsn_secret_store.py"
# The REPLICATED env-key mapping (env_tenant_secret_store.py:31-33) — pinned verbatim in both files.
_SHARED_ENV_KEY_MAPPING = '"".join(c.upper() if c.isalnum() else "_" for c in store_ref)'


def test_tenant_dsn_provider_prefix_guard_fails_closed() -> None:
    # Least privilege: only `tenant/...` references resolve; anything else is PermissionError —
    # this provider can never read the trust-anchor or control-store secrets.
    provider = EnvTenantDsnSecretStore()
    for bad_ref in ("bootstrap/trust-anchor", "control/control-store-dsn", "sp2_tenant_t1", ""):
        for op in (lambda r=bad_ref: provider.resolve(SecretRef(store_ref=r, version="1")), lambda r=bad_ref: provider.current_version(r)):
            raised = False
            try:
                op()
            except PermissionError:
                raised = True
            assert raised, f"non-tenant ref {bad_ref!r} must fail closed (PermissionError)"


def test_tenant_dsn_provider_env_resolution_and_exact_key() -> None:
    # D3 (EN-1/EN-2): the canonical ref computes the EXACT replicated env key — one materialized
    # env var serves both the control-plane side (this provider) and the router side (same
    # convention). The mapping for 'tenant/t1/dsn' is pinned literally.
    ref = SecretRef(store_ref=tenant_dsn_ref("t1"), version="1")
    key = EnvTenantDsnSecretStore._env_key(ref.store_ref, ref.version)
    assert key == "SNACKPORTAL_TENANT_SECRET_TENANT_T1_DSN_V1", key
    saved = os.environ.get(key)
    os.environ[key] = "descriptor-by-ref-only"
    try:
        value = EnvTenantDsnSecretStore().resolve(ref)
        assert value.material == "descriptor-by-ref-only"
        assert "descriptor-by-ref-only" not in repr(value), "SecretValue repr must hide the material (D-14)"
    finally:
        if saved is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = saved


def test_tenant_dsn_provider_file_resolution() -> None:
    # The file form (`$SNACKPORTAL_TENANT_SECRET_DIR/<store_ref>@<version>`) — same convention as
    # the router side; the canonical ref's '/'s nest directories under the secret dir.
    ref = SecretRef(store_ref=tenant_dsn_ref("t9"), version="1")
    with tempfile.TemporaryDirectory() as tmp:
        secret_file = pathlib.Path(tmp) / f"{ref.store_ref}@{ref.version}"
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        secret_file.write_text("file-descriptor-by-ref-only\n", encoding="utf-8")
        provider = EnvTenantDsnSecretStore(secret_dir=tmp)
        assert provider.resolve(ref).material == "file-descriptor-by-ref-only"


def test_tenant_dsn_provider_unresolved_fails_closed() -> None:
    provider = EnvTenantDsnSecretStore(secret_dir=None)
    ref = SecretRef(store_ref=tenant_dsn_ref("absent_tenant_xyz"), version="1")
    key = EnvTenantDsnSecretStore._env_key(ref.store_ref, ref.version)
    saved = os.environ.pop(key, None)
    try:
        raised = False
        try:
            provider.resolve(ref)
        except LookupError:
            raised = True
        assert raised, "an unresolved tenant ref must fail closed (LookupError)"
        assert provider.current_version(ref.store_ref) == "1"  # default version when unpinned
    finally:
        if saved is not None:
            os.environ[key] = saved


def test_tenant_dsn_provider_replicates_router_convention() -> None:
    # D3 alignment WITHOUT importing database_router (AC-15/AC-84): both provider SOURCES carry the
    # IDENTICAL env-key mapping expression, the same env prefix, the same 'tenant/' prefix guard,
    # and the same file convention — so a silent divergence on either side fails this test.
    cp_src = _CP_PROVIDER_SRC.read_text(encoding="utf-8")
    router_src = _ROUTER_PROVIDER_SRC.read_text(encoding="utf-8")
    for fragment in (
        _SHARED_ENV_KEY_MAPPING,
        'f"SNACKPORTAL_TENANT_SECRET_{base}_V{version}"',
        'TENANT_PREFIX = "tenant/"',
        'f"{ref.store_ref}@{ref.version}"',
        '"SNACKPORTAL_TENANT_SECRET_DIR"',
    ):
        assert fragment in cp_src, f"control-plane provider lost the replicated convention fragment: {fragment!r}"
        assert fragment in router_src, f"router-side provider no longer carries the replicated fragment: {fragment!r}"
    # replication, not import (AC-84): the provider may CITE the router-side file in prose, but it
    # must never import the database_router service (services stay mutually independent).
    assert "import database_router" not in cp_src and "from database_router" not in cp_src, (
        "the control-plane provider must not import database_router"
    )


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
    test_onboard_mints_canonical_tenant_ref,
    test_postgres_adapter_selectable_lazily,
    test_provisioning_adapter_unknown_value_fails_closed,
    test_tenant_dsn_provider_prefix_guard_fails_closed,
    test_tenant_dsn_provider_env_resolution_and_exact_key,
    test_tenant_dsn_provider_file_resolution,
    test_tenant_dsn_provider_unresolved_fails_closed,
    test_tenant_dsn_provider_replicates_router_convention,
]

if __name__ == "__main__":
    for _t in _TESTS:
        _t()
        print("PASS:", _t.__name__)
    print("ALL PASSED")
