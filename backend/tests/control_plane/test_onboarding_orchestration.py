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
from control_plane.onboarding import OnboardingError, OnboardingOrchestrator, tenant_dsn_ref, tenant_id_from_dsn_ref  # noqa: E402
from control_plane.provisioning import (  # noqa: E402
    InMemoryProvisioningOperator,
    ProvisioningError,
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
# PRD 07D-2b.2a (IC-002 recovery-core amendment): + Quarantined; + the 7 recovery/compensation
# event names (exact spellings frozen — the {Started} vs {Requested} asymmetry is intentional;
# TenantDeprovision* are vocabulary-only until 07D-2b.2b). Kept in LOCKSTEP with the copies in
# tests/control_plane/test_distinctness_ledger_b2.py.
EXPECTED_STATES = {
    "Registered",
    "Provisioning",
    "Verifying",
    "Ready",
    "Suspended",
    "Failed",
    "Quarantined",
    "Decommissioned",
}
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
    "TenantQuarantined",
    "OnboardingRecoveryStarted",
    "OnboardingRecoveryCompleted",
    "OnboardingRecoveryFailed",
    "TenantDeprovisionRequested",
    "TenantDeprovisionCompleted",
    "TenantDeprovisionFailed",
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


def test_isolation_anomaly_quarantines_at_classification_time() -> None:
    # PRD 07D-2b.2a (IC-002 Failure Behavior; was test_isolation_anomaly_fails_closed): an
    # isolation-class anomaly now lands in QUARANTINED (the automatic Verifying→Quarantined
    # edge), not FAILED — so Failed is by construction non-anomalous. TenantQuarantined marks
    # the hold; the IsolationAnomaly incident event is preserved. MR-1 kill site.
    store = InMemoryControlStore()
    out = _onboard(_orchestrator(store, evidence=_AnomalyEvidenceProvider(nonprod_control_db_evidence())))
    assert out.result is DistinctnessResult.ISOLATION_ANOMALY
    assert _state(store) is TenantLifecycleState.QUARANTINED
    acts = _actions(store)
    assert events.TENANT_QUARANTINED in acts
    assert events.ISOLATION_ANOMALY in acts


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


_ALL_SELECTOR_ENVS = (
    cp_main.CONTROL_STORE_ENV,
    cp_main.PROVISIONING_ADAPTER_ENV,
    cp_main.TENANT_SCHEMA_APPLICATOR_ENV,
    cp_main.DISTINCTNESS_LEDGER_ENV,
)


def test_postgres_adapter_selectable_lazily() -> None:
    # PRD 07D-1 (was: deferred to B-4), under the 07D-2a coherence matrix: the real operator is
    # selected via the ALL-FOUR-postgres composition (RULE 3 — provisioning-alone is now a
    # forbidden mix, RULE 1); construction stays lazy (no I/O — the operator resolves the admin
    # DSN reference per-operation only). The unknown-value fail-closed check is below.
    saved = {name: os.environ.get(name) for name in _ALL_SELECTOR_ENVS}
    for name in _ALL_SELECTOR_ENVS:
        os.environ[name] = "postgres"
    try:
        cp = cp_main.ControlPlane()
        assert isinstance(cp.operator, PostgresProvisioningOperator), "postgres must select the real operator"
    finally:
        for name, old in saved.items():
            if old is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old


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


# --- PRD 07D-2a: tenant-id admission guardrail (AT-07D1-11) ---------------------------------------
_BAD_TENANT_IDS = (
    "",
    "control",
    "Control",
    "CONTROL",
    "a-b",
    "a/b",
    "a\\b",
    "a.b",
    "A_b",
    "a b",
    "té",
    # PRD 07D-2b.1 (AT-07D2A2-1): with `.match` Python's `$` also matches before ONE trailing
    # newline, so these were admitted pre-fullmatch and would alias "t1_"/"control_"/"tenant_1_"
    # through the '\n'->'_' env-key flattening. fullmatch rejects them.
    "t1\n",
    "control\n",
    "tenant_1\n",
)
_GOOD_TENANT_IDS = ("a", "t1", "tenant_1", "acme", "zeta", "nova")


def test_tenant_id_admission_rejects_bad_ids_with_zero_effects() -> None:
    # PRD 07D-2a (AT-07D1-11): a bad tenant id is rejected BEFORE any effect — no store write, no
    # audit record, no provision() call, no lifecycle transition, no PERSISTED secret reference.
    # (onboard() constructs an in-memory SecretRef string first — side-effect-free by design.)
    from control_plane.registry import RegistryError

    for bad in _BAD_TENANT_IDS:
        store = InMemoryControlStore()
        operator = InMemoryProvisioningOperator()
        orch = _orchestrator(store, operator=operator)
        raised = False
        try:
            orch.onboard(bad, organization_ref=_ORG, federation_config_ref=_FED, actor="ops_ref", correlation_id="c-adm")
        except RegistryError:
            raised = True
        assert raised, f"bad tenant id {bad!r} must be rejected with RegistryError"
        assert store.get_tenant(bad) is None, f"{bad!r}: no registry row may be written"
        assert store.list_audit() == [], f"{bad!r}: no audit record may be written"
        assert operator.provisioned == set(), f"{bad!r}: provision() must never be called"


def test_tenant_id_admission_accepts_representative_ids() -> None:
    # Representative safe ids (incl. the shapes every existing suite/harness id uses) still pass
    # registration; a full onboard still reaches READY for a canonical example.
    store = InMemoryControlStore()
    orch = _orchestrator(store)
    for good in _GOOD_TENANT_IDS:
        rec = orch._registry.register_tenant(
            tenant_id=good,
            organization_ref=_ORG,
            expected_schema_version="1",
            database_association_ref=SecretRef(store_ref=tenant_dsn_ref(good), version="1"),
            federation_config_ref=_FED,
            actor="ops_ref",
            correlation_id="c-adm-ok",
        )
        assert rec.tenant_id == good
    # end-to-end: a fresh orchestrator onboards a valid id to READY (admission does not regress).
    store2 = InMemoryControlStore()
    assert _onboard(_orchestrator(store2), tenant_id="t1").result is DistinctnessResult.VERIFIED


# --- PRD 07D-2b.2a: recovery vocabulary, resume, and quarantine integrity --------------------------
def _register(reg: TenantRegistry, tenant_id: str, correlation_id: str = "c-2b2a-reg") -> None:
    reg.register_tenant(
        tenant_id=tenant_id,
        organization_ref=_ORG,
        expected_schema_version="1",
        database_association_ref=SecretRef(store_ref=tenant_dsn_ref(tenant_id), version="1"),
        federation_config_ref=_FED,
        actor="ops_ref",
        correlation_id=correlation_id,
    )


def test_resume_from_provisioning_reaches_ready() -> None:
    # IC-002 Retry-resume eligibility (07D2B2-1 unit shape): a tenant stranded in PROVISIONING
    # auto-resumes through the fence dispatch and converges to READY, wrapped in the
    # OnboardingRecovery start/terminal pair (the resumed provision is attributable).
    store = InMemoryControlStore()
    out1 = _onboard(_orchestrator(store, operator=_FailingOperator()))
    assert out1.reason == "provision_failed"
    assert _state(store) is TenantLifecycleState.PROVISIONING
    out2 = _onboard(_orchestrator(store), correlation_id="c-resume")  # cause fixed (same store)
    assert out2.result is DistinctnessResult.VERIFIED
    assert _state(store) is TenantLifecycleState.READY
    acts = _actions(store)
    assert events.ONBOARDING_RECOVERY_STARTED in acts
    assert events.ONBOARDING_RECOVERY_COMPLETED in acts
    assert acts.count(events.DATABASE_PROVISION_REQUESTED) == 2, "the resume must re-drive provision"


def test_resume_failure_keeps_started_terminal_pairing() -> None:
    # MR-2 kill site (IC-002 Audit Requirements): every OnboardingRecoveryStarted pairs with
    # EXACTLY one terminal record; a resume that fails again stays PROVISIONING (fail closed).
    store = InMemoryControlStore()
    orch_fail = _orchestrator(store, operator=_FailingOperator())
    assert _onboard(orch_fail).reason == "provision_failed"
    out = _onboard(orch_fail, correlation_id="c-resume-fail")  # resume, cause NOT fixed
    assert out.result is not DistinctnessResult.VERIFIED
    assert _state(store) is TenantLifecycleState.PROVISIONING
    acts = _actions(store)
    started = acts.count(events.ONBOARDING_RECOVERY_STARTED)
    terminal = acts.count(events.ONBOARDING_RECOVERY_COMPLETED) + acts.count(events.ONBOARDING_RECOVERY_FAILED)
    assert started == terminal == 1, f"start/terminal must pair exactly (got {started}/{terminal})"
    assert events.ONBOARDING_RECOVERY_FAILED in acts


def test_failed_tenant_requires_explicit_recover() -> None:
    # Fence dispatch: FAILED is terminal via onboard() — reason 'recover_required', zero side
    # effects, no auto-resume, no re-provision (MR-3/MR-4 kill family).
    store = InMemoryControlStore()
    orch = _orchestrator(store, probe=InMemoryTenantDatabaseProbe(reachable=False))
    assert _onboard(orch).result is not DistinctnessResult.VERIFIED
    assert _state(store) is TenantLifecycleState.FAILED
    before = store.list_audit()
    out = _onboard(orch, correlation_id="c-failed-retry")
    assert out.result is DistinctnessResult.VERIFICATION_INCOMPLETE
    assert out.reason == "recover_required"
    assert _state(store) is TenantLifecycleState.FAILED
    assert store.list_audit() == before, "the terminal fence path must have zero side effects"


def test_recover_transient_failed_reaches_ready_only_via_gate() -> None:
    # R1-5 unit shape (live 07D2B2-2 mirrors this on PostgreSQL): a transient FAILED tenant
    # recovers explicitly once the cause is fixed — and reaches Ready ONLY through
    # Verifying/the gate (recovery never sets Ready directly; sole-readiness-writer).
    store = InMemoryControlStore()
    orch_broken = _orchestrator(store, probe=InMemoryTenantDatabaseProbe(reachable=False))
    assert _onboard(orch_broken).result is not DistinctnessResult.VERIFIED
    assert _state(store) is TenantLifecycleState.FAILED
    orch = _orchestrator(store)  # probe healthy again (same store)
    out = orch.recover("t1", actor="ops_ref", correlation_id="c-recover")
    assert out.result is DistinctnessResult.VERIFIED
    assert _state(store) is TenantLifecycleState.READY
    recs = store.list_audit()
    acts = [r.action for r in recs]
    assert events.ONBOARDING_RECOVERY_STARTED in acts
    assert events.ONBOARDING_RECOVERY_COMPLETED in acts
    ready_writes = [(r.from_state, r.to_state) for r in recs if r.to_state == "Ready"]
    assert ready_writes == [("Verifying", "Ready")], "Ready must be written ONLY by the gate transition"


def test_recover_refuses_ineligible_states_pre_effect() -> None:
    # Only FAILED is recover-eligible (IC-002 Retry-resume eligibility); every other state —
    # including QUARANTINED (MR-3 kill site) — refuses fail-closed with ZERO side effects.
    store = InMemoryControlStore()
    orch = _orchestrator(store)
    assert _onboard(orch).result is DistinctnessResult.VERIFIED  # t1 -> READY
    reg = orch._registry
    _register(reg, "t_reg")
    _register(reg, "t_prov")
    reg.mark_provisioning("t_prov", actor="ops_ref", correlation_id="c-2b2a-p")
    _register(reg, "t_susp")
    reg.suspend_tenant("t_susp", actor="ops_ref", correlation_id="c-2b2a-s")
    _register(reg, "t_dec")
    reg.decommission_tenant("t_dec", actor="ops_ref", correlation_id="c-2b2a-d")
    _register(reg, "t_q")
    reg.mark_provisioning("t_q", actor="ops_ref", correlation_id="c-2b2a-q0")
    reg.quarantine_tenant("t_q", actor="ops_ref", correlation_id="c-2b2a-q")
    for tid in ("t1", "t_reg", "t_prov", "t_susp", "t_dec", "t_q", "absent_tenant"):
        state_before = None if tid == "absent_tenant" else _state(store, tid)
        audit_before = store.list_audit()
        raised = False
        try:
            orch.recover(tid, actor="ops_ref", correlation_id="c-recover-bad")
        except OnboardingError:
            raised = True
        assert raised, f"recover() must refuse {tid!r} (state {state_before})"
        assert store.list_audit() == audit_before, f"{tid!r}: refusal must have zero side effects"
        if state_before is not None:
            assert _state(store, tid) is state_before


def test_recover_anomaly_history_routes_to_quarantined() -> None:
    # IC-002 defence in depth: a FAILED record whose trail carries IsolationAnomaly (predating
    # the automatic-quarantine rule) is re-classified by recover() and routed to QUARANTINED —
    # never resumed toward Verifying/Ready (MR-3 kill site).
    store = InMemoryControlStore()
    orch_broken = _orchestrator(store, probe=InMemoryTenantDatabaseProbe(reachable=False))
    assert _onboard(orch_broken).result is not DistinctnessResult.VERIFIED
    assert _state(store) is TenantLifecycleState.FAILED
    # Simulate the pre-2b.2a history: an anomaly record for a tenant resting in Failed.
    ControlPlaneAudit(store).record(
        actor="ops_ref", tenant_id="t1", action=events.ISOLATION_ANOMALY, from_state=None, to_state=None, correlation_id="c-hist"
    )
    orch = _orchestrator(store)
    verifies_before = _actions(store).count(events.DISTINCTNESS_VERIFICATION_STARTED)
    out = orch.recover("t1", actor="ops_ref", correlation_id="c-recover-anom")
    assert out.result is DistinctnessResult.ISOLATION_ANOMALY
    assert out.reason == "anomaly_history"
    assert _state(store) is TenantLifecycleState.QUARANTINED
    acts = _actions(store)
    assert acts.count(events.DISTINCTNESS_VERIFICATION_STARTED) == verifies_before, "must NOT re-enter Verifying"
    assert "QuarantineTenant" in acts
    assert events.TENANT_QUARANTINED in acts
    assert events.ONBOARDING_RECOVERY_STARTED in acts
    assert events.ONBOARDING_RECOVERY_FAILED in acts


def test_verify_refuses_quarantined_pre_transition() -> None:
    # R1-1 / C-1 (MR-Q1 kill site): the gate itself refuses a QUARANTINED tenant BEFORE any
    # transition — a direct verify() must never walk Quarantined -> Verifying -> Ready.
    store = InMemoryControlStore()
    orch = _orchestrator(store, evidence=_AnomalyEvidenceProvider(nonprod_control_db_evidence()))
    assert _onboard(orch).result is DistinctnessResult.ISOLATION_ANOMALY
    assert _state(store) is TenantLifecycleState.QUARANTINED
    before = store.list_audit()
    raised = False
    try:
        orch._provisioning.verify("t1", actor="ops_ref", correlation_id="c-q-verify")
    except ProvisioningError:
        raised = True
    assert raised, "verify() must refuse a QUARANTINED tenant (fail closed, pre-transition)"
    assert _state(store) is TenantLifecycleState.QUARANTINED
    assert store.list_audit() == before, "zero side effects (no Verifying transition, no audit write)"


def test_quarantined_tenant_all_entry_points_refuse() -> None:
    # AC-2B2A-14 (extended reading; live 07D2B2-3/-4 mirror this): Quarantined cannot onboard,
    # recover, reassociate, OR direct-verify toward Ready. onboard() returns the terminal
    # non-routable shape; the other three raise pre-effect (record byte-unchanged).
    store = InMemoryControlStore()
    orch = _orchestrator(store, evidence=_AnomalyEvidenceProvider(nonprod_control_db_evidence()))
    assert _onboard(orch).result is DistinctnessResult.ISOLATION_ANOMALY
    rec_before = store.get_tenant("t1")
    assert rec_before is not None and rec_before.lifecycle_state is TenantLifecycleState.QUARANTINED
    out = _onboard(orch, correlation_id="c-q-onboard")
    assert out.result is DistinctnessResult.VERIFICATION_INCOMPLETE
    assert out.reason == "quarantined"
    for op in ("recover", "reassociate", "verify"):
        raised = False
        try:
            if op == "recover":
                orch.recover("t1", actor="ops_ref", correlation_id="c-q-r")
            elif op == "reassociate":
                orch.reassociate(
                    "t1",
                    new_association_ref=SecretRef(store_ref=tenant_dsn_ref("t1"), version="2"),
                    actor="ops_ref",
                    correlation_id="c-q-ra",
                )
            else:
                orch._provisioning.verify("t1", actor="ops_ref", correlation_id="c-q-v")
        except (OnboardingError, ProvisioningError):
            raised = True
        assert raised, f"{op}() must refuse a QUARANTINED tenant"
    rec_after = store.get_tenant("t1")
    assert rec_after == rec_before, "no state or association overwrite (all refusals pre-effect)"


def test_reassociate_refused_for_decommissioned_pre_effect() -> None:
    # IC-002 Re-association guard: refused for Decommissioned too, before any state overwrite.
    store = InMemoryControlStore()
    orch = _orchestrator(store)
    _register(orch._registry, "t_dec")
    orch._registry.decommission_tenant("t_dec", actor="ops_ref", correlation_id="c-dec")
    rec_before = store.get_tenant("t_dec")
    audit_before = store.list_audit()
    raised = False
    try:
        orch.reassociate(
            "t_dec",
            new_association_ref=SecretRef(store_ref=tenant_dsn_ref("t_dec"), version="2"),
            actor="ops_ref",
            correlation_id="c-dec-ra",
        )
    except ProvisioningError:
        raised = True
    assert raised, "reassociate() must refuse a DECOMMISSIONED tenant"
    assert store.get_tenant("t_dec") == rec_before
    assert store.list_audit() == audit_before


def test_reassociate_emits_secret_reference_registered() -> None:
    # AT-07D1-7: re-association registers a NEW association reference — the reference-only
    # SecretReferenceRegistered marker must appear (previously only first onboarding emitted it).
    store = InMemoryControlStore()
    orch = _orchestrator(store)
    assert _onboard(orch).result is DistinctnessResult.VERIFIED
    before = _actions(store).count(events.SECRET_REFERENCE_REGISTERED)
    out = orch.reassociate(
        "t1",
        new_association_ref=SecretRef(store_ref=tenant_database_name("t1"), version="2"),
        actor="ops_ref",
        correlation_id="c-ra",
    )
    assert out.result is DistinctnessResult.VERIFIED
    assert _actions(store).count(events.SECRET_REFERENCE_REGISTERED) == before + 1


def test_suspend_allows_ready_and_decommission_catchup() -> None:
    # R1-2 / C-2 (AC-2B2A-42): READY can now be suspended (Suspended is Ready's ONLY egress
    # under the amended IC-002 — suspend-first is executable) and decommission's allowed_from
    # gained Failed + Quarantined (state catch-up ONLY; nothing is deprovisioned). Ready-direct
    # decommission stays disallowed. The {REGISTERED, PROVISIONING} suspend wideness is a
    # documented residual for the post-2b.2 reconcile (not asserted away here).
    from control_plane.registry import RegistryError

    store = InMemoryControlStore()
    orch = _orchestrator(store)
    assert _onboard(orch).result is DistinctnessResult.VERIFIED
    reg = orch._registry
    raised = False
    try:
        reg.decommission_tenant("t1", actor="ops_ref", correlation_id="c-dec-ready")
    except RegistryError:
        raised = True
    assert raised, "Ready-direct decommission must remain disallowed (suspend-first)"
    rec = reg.suspend_tenant("t1", actor="ops_ref", correlation_id="c-susp")
    assert rec.lifecycle_state is TenantLifecycleState.SUSPENDED
    suspends = [r for r in store.list_audit() if r.action == "SuspendTenant"]
    assert suspends and suspends[-1].from_state == "Ready" and suspends[-1].to_state == "Suspended"
    # Failed -> Decommissioned (catch-up)
    store2 = InMemoryControlStore()
    orch2 = _orchestrator(store2, probe=InMemoryTenantDatabaseProbe(reachable=False))
    assert _onboard(orch2).result is not DistinctnessResult.VERIFIED
    assert _state(store2) is TenantLifecycleState.FAILED
    rec2 = orch2._registry.decommission_tenant("t1", actor="ops_ref", correlation_id="c-dec-f")
    assert rec2.lifecycle_state is TenantLifecycleState.DECOMMISSIONED
    # Quarantined -> Decommissioned (the SOLE Quarantined egress)
    store3 = InMemoryControlStore()
    orch3 = _orchestrator(store3, evidence=_AnomalyEvidenceProvider(nonprod_control_db_evidence()))
    assert _onboard(orch3).result is DistinctnessResult.ISOLATION_ANOMALY
    rec3 = orch3._registry.decommission_tenant("t1", actor="ops_ref", correlation_id="c-dec-q")
    assert rec3.lifecycle_state is TenantLifecycleState.DECOMMISSIONED


def test_quarantine_tenant_registry_operation() -> None:
    # IC-002 QuarantineTenant: explicit, audited quarantine from Provisioning and Failed
    # (audit-first ordering rides the guarded _transition); refused from other states.
    from control_plane.registry import RegistryError

    store = InMemoryControlStore()
    orch = _orchestrator(store)
    reg = orch._registry
    _register(reg, "t_p")
    reg.mark_provisioning("t_p", actor="ops_ref", correlation_id="c-qp0")
    rec = reg.quarantine_tenant("t_p", actor="ops_ref", correlation_id="c-qp")
    assert rec.lifecycle_state is TenantLifecycleState.QUARANTINED
    q_recs = [r for r in store.list_audit() if r.action == "QuarantineTenant"]
    assert q_recs and q_recs[-1].from_state == "Provisioning" and q_recs[-1].to_state == "Quarantined"
    # from Failed (the recover() re-classification edge)
    store2 = InMemoryControlStore()
    orch2 = _orchestrator(store2, probe=InMemoryTenantDatabaseProbe(reachable=False))
    assert _onboard(orch2).result is not DistinctnessResult.VERIFIED
    assert orch2._registry.quarantine_tenant("t1", actor="ops_ref", correlation_id="c-qf").lifecycle_state is (
        TenantLifecycleState.QUARANTINED
    )
    # refused from Registered (fail closed)
    _register(reg, "t_r")
    raised = False
    try:
        reg.quarantine_tenant("t_r", actor="ops_ref", correlation_id="c-qr")
    except RegistryError:
        raised = True
    assert raised, "quarantine_tenant must refuse a Registered tenant"


# --- PRD 07D-2b.1: symmetric effective-posture onboard-time guard (AC-4..8) ------------------------
def _with_selector_env(values: dict):
    """Set/clear the four selector env vars (only the given keys set); return a restore() callable."""
    saved = {name: os.environ.get(name) for name in _ALL_SELECTOR_ENVS}
    for name in _ALL_SELECTOR_ENVS:
        os.environ.pop(name, None)
    for name, value in values.items():
        if value is not None:
            os.environ[name] = value

    def restore() -> None:
        for name, old in saved.items():
            if old is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old

    return restore


def _assert_onboarding_guarded(cp: "cp_main.ControlPlane") -> None:
    """All guarded entry points — incl. the PRD 07D-2b.2a recovery entry point — must raise
    ProvisioningError pre-effect (the facade deny, never an accidental AttributeError)."""
    for op in ("onboard", "reassociate", "recover"):
        raised = False
        try:
            if op == "onboard":
                cp.onboarding.onboard("guard_t1", organization_ref=_ORG, federation_config_ref=_FED, actor="ops_ref", correlation_id="c-g1")
            elif op == "reassociate":
                cp.onboarding.reassociate(
                    "guard_t1",
                    new_association_ref=SecretRef(store_ref=tenant_dsn_ref("guard_t1"), version="1"),
                    actor="ops_ref",
                    correlation_id="c-g2",
                )
            else:
                cp.onboarding.recover("guard_t1", actor="ops_ref", correlation_id="c-g2r")
        except ProvisioningError:
            raised = True
        assert raised, f"{op}() must fail closed (ProvisioningError) under a MIXED effective posture"


def test_onboard_guard_blocks_durable_store_with_in_memory_live() -> None:
    # Hazard posture (a) — the documented B-7B residual: durable/postgres control store standalone,
    # live trio in-memory. Construction stays allowed (B-7B); onboard()/reassociate() fail closed
    # BEFORE any side effect (the guard raises before any delegation reaches the orchestrator).
    restore = _with_selector_env({cp_main.CONTROL_STORE_ENV: "postgres"})
    try:
        cp = cp_main.ControlPlane()  # constructs lazily (RULE 2) — never blocked
        _assert_onboarding_guarded(cp)
    finally:
        restore()


def test_onboard_guard_blocks_reverse_mix_explicit_store_bypass() -> None:
    # Hazard posture (b) — the REVERSE explicit-constructor bypass: an in-memory store passed via
    # store= under the all-postgres env composition (the 07D-2a matrix reads env only). Real
    # physical DBs on a volatile registry would be orphans-on-restart; the guard fails both entry
    # points closed with PROVEN zero effects (the in-memory store is directly readable).
    restore = _with_selector_env({name: "postgres" for name in _ALL_SELECTOR_ENVS})
    try:
        store = InMemoryControlStore()
        cp = cp_main.ControlPlane(store=store)  # lazy; no I/O at construction
        _assert_onboarding_guarded(cp)
        assert store.get_tenant("guard_t1") is None, "guard must fire before any registry write"
        assert store.list_audit() == [], "guard must fire before any audit record"
    finally:
        restore()


def test_onboard_guard_allows_matched_postures() -> None:
    # MATCHED postures pass through unchanged: the all-in-memory default onboards to READY via the
    # composed plane, and the all-postgres composition exposes the REAL orchestrator (its onboard
    # behavior is proven in the live 07D harness; construction here stays lazy/zero-I/O).
    restore = _with_selector_env({})
    try:
        cp = cp_main.ControlPlane()
        assert isinstance(cp.onboarding, OnboardingOrchestrator), "matched posture must not be wrapped"
        out = cp.onboarding.onboard("guard_ok", organization_ref=_ORG, federation_config_ref=_FED, actor="ops_ref", correlation_id="c-g3")
        assert out.result is DistinctnessResult.VERIFIED, "all-in-memory onboarding must still reach READY"
        # PRD 07D-2b.2a: on a MATCHED posture the recovery entry point reaches the ORCHESTRATOR
        # (its own OnboardingError refusal for an unknown tenant), never the facade deny.
        recover_reached_orchestrator = False
        try:
            cp.onboarding.recover("guard_absent", actor="ops_ref", correlation_id="c-g4")
        except OnboardingError:
            recover_reached_orchestrator = True
        assert recover_reached_orchestrator, "matched posture must expose the real recover()"
    finally:
        restore()
    restore = _with_selector_env({name: "postgres" for name in _ALL_SELECTOR_ENVS})
    try:
        cp = cp_main.ControlPlane()
        assert isinstance(cp.onboarding, OnboardingOrchestrator), "all-postgres posture must not be wrapped"
    finally:
        restore()


# --- PRD 07D-2a: secret precedence / version pins (AT-07D1-10; Q4 = pin current behavior) ----------
def test_tenant_dsn_provider_env_wins_over_file_when_both_set() -> None:
    # BOTH forms set -> the ENV value is returned and the file is silently ignored (the current
    # deterministic behavior on BOTH sides of the replicated convention — pinned, not changed).
    ref = SecretRef(store_ref=tenant_dsn_ref("t7"), version="1")
    key = EnvTenantDsnSecretStore._env_key(ref.store_ref, ref.version)
    saved = os.environ.get(key)
    with tempfile.TemporaryDirectory() as tmp:
        secret_file = pathlib.Path(tmp) / f"{ref.store_ref}@{ref.version}"
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        secret_file.write_text("file-material\n", encoding="utf-8")
        os.environ[key] = "env-material"
        try:
            provider = EnvTenantDsnSecretStore(secret_dir=tmp)
            assert provider.resolve(ref).material == "env-material", "env must win over file (pinned behavior)"
        finally:
            if saved is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = saved


def test_tenant_dsn_provider_version_2_via_both_forms() -> None:
    # Version "2" resolves via the env form AND the file form (nothing pins version "1" only).
    ref_v2 = SecretRef(store_ref=tenant_dsn_ref("t8"), version="2")
    key = EnvTenantDsnSecretStore._env_key(ref_v2.store_ref, ref_v2.version)
    assert key.endswith("_V2"), key
    saved = os.environ.get(key)
    os.environ[key] = "env-material-v2"
    try:
        assert EnvTenantDsnSecretStore().resolve(ref_v2).material == "env-material-v2"
    finally:
        if saved is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = saved
    with tempfile.TemporaryDirectory() as tmp:
        secret_file = pathlib.Path(tmp) / f"{ref_v2.store_ref}@2"
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        secret_file.write_text("file-material-v2\n", encoding="utf-8")
        assert EnvTenantDsnSecretStore(secret_dir=tmp).resolve(ref_v2).material == "file-material-v2"


def test_tenant_dsn_provider_current_version_token_pinned() -> None:
    # current_version uses the literal LOWERCASE 'current' token (…_Vcurrent; only the store_ref
    # is uppercased) and defaults to "1" when unpinned — identical on the router side (pinned).
    store_ref = tenant_dsn_ref("t7")
    key = EnvTenantDsnSecretStore._env_key(store_ref, "current")
    assert key == "SNACKPORTAL_TENANT_SECRET_TENANT_T7_DSN_Vcurrent", key
    saved = os.environ.get(key)
    provider = EnvTenantDsnSecretStore(secret_dir=None)
    try:
        os.environ.pop(key, None)
        assert provider.current_version(store_ref) == "1", "unpinned current_version must default to '1'"
        os.environ[key] = "3"
        assert provider.current_version(store_ref) == "3"
    finally:
        if saved is None:
            os.environ.pop(key, None)
        else:
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
    test_isolation_anomaly_quarantines_at_classification_time,
    test_idempotent_onboard_does_not_reverify,
    test_reassociate_reverifies,
    test_disable_routing,
    test_resume_from_provisioning_reaches_ready,
    test_resume_failure_keeps_started_terminal_pairing,
    test_failed_tenant_requires_explicit_recover,
    test_recover_transient_failed_reaches_ready_only_via_gate,
    test_recover_refuses_ineligible_states_pre_effect,
    test_recover_anomaly_history_routes_to_quarantined,
    test_verify_refuses_quarantined_pre_transition,
    test_quarantined_tenant_all_entry_points_refuse,
    test_reassociate_refused_for_decommissioned_pre_effect,
    test_reassociate_emits_secret_reference_registered,
    test_suspend_allows_ready_and_decommission_catchup,
    test_quarantine_tenant_registry_operation,
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
    test_tenant_id_admission_rejects_bad_ids_with_zero_effects,
    test_tenant_id_admission_accepts_representative_ids,
    test_onboard_guard_blocks_durable_store_with_in_memory_live,
    test_onboard_guard_blocks_reverse_mix_explicit_store_bypass,
    test_onboard_guard_allows_matched_postures,
    test_tenant_dsn_provider_env_wins_over_file_when_both_set,
    test_tenant_dsn_provider_version_2_via_both_forms,
    test_tenant_dsn_provider_current_version_token_pinned,
]

if __name__ == "__main__":
    for _t in _TESTS:
        _t()
        print("PASS:", _t.__name__)
    print("ALL PASSED")
