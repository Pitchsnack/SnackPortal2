"""Control Plane composition root (Build Phase 2).

Wires the control-plane frameworks against the ControlStore port (default in-memory
adapter) and the vendor-neutral env/file SecretStore provider for Bootstrap Phase 0.
No tenant-database access on the default path, no routing, no runtime authentication.
PRD 07D-1 adds env-selected composition of the REAL physical provisioning path
(controlled non-production; lazy-connect; references only).
"""

from __future__ import annotations

import os
import uuid
from dataclasses import replace
from typing import Callable, ContextManager, Dict, Iterable, List, NoReturn, Optional, Set, Tuple

from shared.adapters.providers.env_reference_secret_store import DEFAULT_ALLOWED, EnvReferenceSecretStore
from shared.secrets import SecretRef

from .adapters.providers.control_store_factory import (  # driver-free at import (PRD 07D-3b)
    PostgresControlStoreFactory,
    SharedControlStoreFactory,
)
from .adapters.providers.env_tenant_dsn_secret_store import EnvTenantDsnSecretStore
from .adapters.providers.in_memory_distinctness import (
    NONPROD_CONTROL_SENTINEL_NAMESPACE,
    NONPROD_CONTROL_TARGET,
    InMemoryDistinctnessEvidenceProvider,
    nonprod_control_db_evidence,
)
from .adapters.providers.in_memory_probe import InMemoryTenantDatabaseProbe
from .adapters.providers.in_memory_store import InMemoryControlStore
from .adapters.providers.in_memory_tenant_schema_applicator import InMemoryTenantSchemaApplicator
from .audit import ControlPlaneAudit
from .bootstrap import BootstrapController
from .directory import GlobalDirectory
from .distinctness import (
    DistinctnessEvidence,
    DistinctnessEvidenceProvider,
    DistinctnessLedger,
    DistinctnessOutcome,
    InMemoryDistinctnessLedger,
)
from .federation import FederationStore
from .membership import MembershipRegistry
from .onboarding import OnboardingOrchestrator, tenant_id_from_dsn_ref
from .ports import ControlStore
from .provisioning import (
    InMemoryProvisioningOperator,
    ProvisioningError,
    ProvisioningOperator,
    ProvisioningVerificationService,
    TenantSchemaApplicator,
    tenant_database_name,
)
from .readiness import ReadinessFramework
from .recovery import (
    DeprovisionOutcome,
    InMemoryRecoveryInspection,
    OrphanScanEntry,
    OrphanScanService,
    RecoveryCompensationService,
    RecoveryInspectionPort,
)
from .registry import TenantRegistry
from .schema_compat import SchemaCompatibilityChecker
from .verification import TenantDatabaseProbe

SERVICE = "control_plane"
SUPPORTED_SCHEMA_MIN = 1
SUPPORTED_SCHEMA_MAX = 1

# D-15 orchestration adapter selection (OB-1). Unset/empty -> in-memory (controlled
# non-production default; construction performs no I/O). 'postgres' (PRD 07D-1 composition
# activation) selects the REAL physical provisioning path — PostgresProvisioningOperator with the
# admin DSN by SecretRef (PROVISIONING_ADMIN_DSN_REF), the real Postgres probe + tenant
# distinctness evidence provider (tenant DSNs resolved by the control-plane EnvTenantDsnSecretStore
# via the canonical `tenant/<tenant_id>/dsn` refs), and REAL Control-DB evidence resolved lazily on
# first verification (D-C). All lazy-connect (B-7B pattern): construction performs no I/O; refs
# resolve per-operation and fail closed. Any other value raises ValueError (fail closed).
PROVISIONING_ADAPTER_ENV = "SP2_CP_PROVISIONING_ADAPTER"

# D-15 distinctness-ledger selection (PRD 06 B-2). Unset/empty -> in-memory (controlled
# non-production default; the per-instance distinctness-evidence inventory). 'postgres'
# (PRD 07D-1 composition activation) selects the durable Control-DB-backed ledger
# (PostgresDistinctnessLedger over the control-store DSN reference — the same B-7B secret binding
# as the durable ControlStore). The durable adapter is lazy-connect (no I/O at construction; each
# operation resolves the reference, connects short-lived, and fails closed on error). Any other
# value raises ValueError (fail closed) — never a silent fallback.
DISTINCTNESS_LEDGER_ENV = "SP2_CP_DISTINCTNESS_LEDGER"

# Control-Store selection (PRD 06 B-7B; controlled non-production runtime audit-sink wiring).
# Unset/empty -> in-memory (the default persistence — construction performs no I/O). The value
# 'postgres' selects the durable Control-DB-backed ControlStore (the operational audit sink is
# ONE consumer of this store — B-7B selects a durable ControlStore, not a separate audit sink);
# it is lazy-connect (no I/O at construction; connects and fails closed on first store
# operation). Any other value raises (fail closed), mirroring the SP2_CP_PROVISIONING_ADAPTER /
# SP2_CP_DISTINCTNESS_LEDGER selectors. No production activation, no runtime DDL.
CONTROL_STORE_ENV = "SP2_CP_CONTROL_STORE"

# Name of the secret-store REFERENCE (SecretRef.store_ref) for the durable Control-Store DSN
# (D-14). The composition root resolves the DSN through the SecretStore by this reference and
# holds NO DSN literal; SNACKPORTAL_TEST_DSN is never reused as runtime config.
CONTROL_STORE_DSN_REF_ENV = "SP2_CP_CONTROL_STORE_DSN_REF"
DEFAULT_CONTROL_STORE_DSN_REF = "control/control-store-dsn"

# Tenant schema-applicator selection (PRD 07B; D15-ARCH-SPEC-01 §8 Step 2b). Unset/empty ->
# in-memory (controlled non-production default; construction performs no I/O). 'postgres'
# (PRD 07D-1 composition activation) selects the REAL applicator — it applies the existing
# 14-file tenant DDL set + the System Primary seed in one atomic, fail-closed transaction — wired
# against the control-plane tenant-DSN provider (EnvTenantDsnSecretStore) that resolves the
# canonical `tenant/<tenant_id>/dsn` refs minted by onboarding. Lazy: construction performs no
# I/O; the credential is resolved in-memory per apply and never retained. Any other value raises
# ValueError (fail closed).
TENANT_SCHEMA_APPLICATOR_ENV = "SP2_CP_TENANT_SCHEMA_APPLICATOR"

# PRD 07D-1 (D-14): the admin/provisioning DSN secret REFERENCE for the postgres provisioning
# path. Resolved through a SEPARATE widened-allow-list EnvReferenceSecretStore (the B-7B
# control-store widening pattern); the composition root holds NO DSN literal.
PROVISIONING_ADMIN_DSN_REF = "control/provisioning-admin-dsn"

# PRD 07D-2a (AT-07D1-9): the LIVE-side selector family for the coherence matrix. If ANY of these
# selects 'postgres', ALL FOUR selectors (these three + SP2_CP_CONTROL_STORE) must be 'postgres'
# (RULE 1) — otherwise construction fails closed. Hazards each mix would open (source-verified):
# provisioning=postgres + in-memory control store -> real physical databases recorded only in
# volatile memory (orphans on every restart — the largest orphan source); applicator=postgres +
# in-memory provisioning -> real DDL applied to an un-provisioned/arbitrary target; ledger=postgres
# without the full postgres path -> FABRICATED in-memory evidence durably recorded in the real
# control_distinctness_ledger plus durable fake READY rows (fail-open). Control-store-standalone
# 'postgres' (RULE 2) remains ALLOWED — the established, live-proven B-7B durable audit/registry
# posture (it creates nothing physical). All-in_memory and all-postgres are the two sanctioned
# compositions (RULE 3).
_LIVE_SELECTOR_ENVS: Tuple[str, str, str] = (
    PROVISIONING_ADAPTER_ENV,
    TENANT_SCHEMA_APPLICATOR_ENV,
    DISTINCTNESS_LEDGER_ENV,
)


def _proven_control_evidence(evidence: Optional[DistinctnessEvidence]) -> Optional[DistinctnessEvidence]:
    """PRD 07D-2a (AT-07D1-8): accept Control-DB evidence ONLY with a PROVEN write-sentinel.

    A gather whose sentinel was not written AND read back (``sentinel_written=False`` or a missing
    token) must not count as resolved Control-DB evidence — one of the gate's five DV-C7A
    comparison legs (token equality) would be silently inert. Returning None routes the lazy gate
    into its existing fail-closed branch (``ProvisioningError``; no tenant reaches Ready)."""
    if evidence is None or not evidence.sentinel_written or not evidence.sentinel_token:
        return None
    return evidence


class CanonicalTenantRefInMemoryEvidence(InMemoryDistinctnessEvidenceProvider):
    """In-memory distinctness evidence aware of the canonical tenant refs minted since 07D-1.

    The base in-memory provider derives the observed provisioning target from the association
    store reference — correct while onboarding minted the raw target name (`sp2_tenant_<id>`,
    pre-07D-1), but the canonical ref `tenant/<tenant_id>/dsn` (D-A) is a secret-store LOCATION,
    not the target name. For canonical refs this derives the intended controlled-non-prod target
    (`tenant_database_name`) so the default in-memory composition still verifies
    (observed target == intended target); non-canonical refs (e.g. caller-supplied raw refs via
    `reassociate`) are delegated to the base provider unchanged. Composition-level glue only:
    no I/O, no new evidence model, and `secret_ref_key` stays the association store_ref (as the
    real provider binds it), so the gate's secret-reference collision checks are unweakened.
    """

    def gather(
        self,
        association_ref: SecretRef,
        *,
        sentinel_token: str,
        sentinel_namespace: str,
    ) -> Optional[DistinctnessEvidence]:
        evidence = super().gather(association_ref, sentinel_token=sentinel_token, sentinel_namespace=sentinel_namespace)
        tenant_id = tenant_id_from_dsn_ref(association_ref.store_ref)
        if evidence is None or tenant_id is None:
            return evidence
        target = tenant_database_name(tenant_id)
        return replace(evidence, database_identity=f"{target}:db", observed_target=target)


class _LazyControlEvidenceGate(ProvisioningVerificationService):
    """The readiness gate with LAZILY resolved REAL Control-DB distinctness evidence (07D-1 D-C).

    The gate's constructor takes Control-DB evidence as a VALUE, but gathering the REAL evidence
    (PostgresDistinctnessEvidenceProvider against the control-store DB reference) is live I/O —
    forbidden at composition time (lazy-construction invariant; the deferral-lock tests construct
    the postgres selection without a live database). This subclass therefore resolves the real
    evidence on the FIRST verification and caches it; a failed/incomplete gather fails closed
    (ProvisioningError) BEFORE any state transition, so no tenant can reach Ready without proven
    tenant-vs-Control-DB distinctness. It adds NO transition logic, NO audit write, and NO second
    Ready writer — the entire gate behavior is inherited unchanged (the sole-readiness-writer
    invariant is preserved).
    """

    def __init__(
        self,
        store: ControlStore,
        audit: ControlPlaneAudit,
        probe: TenantDatabaseProbe,
        evidence_provider: DistinctnessEvidenceProvider,
        control_db_evidence: DistinctnessEvidence,
        *,
        supported_schema_versions: Iterable[str],
        ledger: Optional[DistinctnessLedger] = None,
        control_evidence_factory: Callable[[], Optional[DistinctnessEvidence]],
    ) -> None:
        super().__init__(
            store,
            audit,
            probe,
            evidence_provider,
            control_db_evidence,
            supported_schema_versions=supported_schema_versions,
            ledger=ledger,
        )
        self._control_evidence_factory = control_evidence_factory
        self._control_evidence_resolved = False

    def verify(self, tenant_id: str, *, actor: str, correlation_id: str) -> DistinctnessOutcome:
        if not self._control_evidence_resolved:
            control = self._control_evidence_factory()
            if control is None:
                # Fail closed: without REAL Control-DB evidence, tenant-vs-Control-DB
                # distinctness cannot be proven — no tenant may reach Ready (never a fallback).
                raise ProvisioningError("control database distinctness evidence unavailable")
            self._control = control
            self._control_evidence_resolved = True
        return super().verify(tenant_id, actor=actor, correlation_id=correlation_id)


class _MixedPostureOnboardingGuard:
    """PRD 07D-2b.1: fail-closed onboarding facade for MIXED effective compositions.

    The 07D-2a selector matrix reads ENV VALUES ONLY, so two code-level seams can still compose a
    MIXED plane: (a) the documented B-7B residual — durable control store + in-memory live side —
    where ``onboard()``/``reassociate()`` would commit a DURABLE fake-READY row backed by an
    in-memory fake DB; and (b) the reverse — an explicit in-memory ``store=`` under the
    all-postgres env composition — where they would create REAL physical databases recorded only
    in volatile memory (orphans on restart). Under either mixed posture this facade replaces the
    orchestrator and fails the effectful entry points — ``onboard()``, ``reassociate()``, and
    (PRD 07D-2b.2a) the recovery entry point ``recover()`` — closed with ``ProvisioningError``
    BEFORE any side effect (no registry read/write, no audit record, no provision(), no schema
    apply, no evidence gather, no lifecycle transition). ``disable_routing`` delegates unchanged —
    it drops routing evidence and emits events only (never writes Ready) and remains a safe
    operational companion.
    Construction of the plane itself is NEVER blocked (the B-7B audit/registry posture stays fully
    usable — PRD 06 B-7B tests construct and audit only)."""

    def __init__(self, inner: OnboardingOrchestrator, posture: str) -> None:
        self._inner = inner
        self._posture = posture

    def _deny(self, operation: str) -> NoReturn:
        raise ProvisioningError(
            f"{operation}() is disabled under a MIXED effective composition (PRD 07D-2b.1): "
            f"{self._posture}. The durable-store standalone posture is audit/registry-only "
            "(PRD 06 B-7B); full onboarding requires the matched all-postgres composition "
            "(PRD 07D-1) — fail closed, no side effects were performed."
        )

    def onboard(
        self,
        tenant_id: str,
        *,
        organization_ref: str,
        federation_config_ref: str,
        actor: str,
        correlation_id: str,
        expected_schema_version: str = "1",
    ) -> DistinctnessOutcome:
        self._deny("onboard")

    def reassociate(
        self,
        tenant_id: str,
        *,
        new_association_ref: SecretRef,
        actor: str,
        correlation_id: str,
    ) -> DistinctnessOutcome:
        self._deny("reassociate")

    def recover(self, tenant_id: str, *, actor: str, correlation_id: str) -> DistinctnessOutcome:
        # PRD 07D-2b.2a: the new recovery entry point gets an EXPLICIT mixed-posture deny — a
        # mixed-plane recover() would otherwise fail only by accidental AttributeError (unproven).
        self._deny("recover")

    def disable_routing(self, tenant_id: str, *, actor: str, correlation_id: str) -> None:
        self._inner.disable_routing(tenant_id, actor=actor, correlation_id=correlation_id)


class _MixedPostureRecoveryGuard:
    """PRD 07D-2b.2b (R1-2): fail-closed recovery facade for MIXED effective compositions.

    Denies BOTH new recovery entry points — the ``DeprovisionTenantDatabase`` compensation
    operation AND the read-only ``ScanForOrphans`` — PRE-EFFECT (zero audit events, zero
    reads-with-side-effects), under BOTH mix directions (durable-store standalone AND the
    reverse explicit-store bypass), mirroring the 07D-2b.1 onboarding guard. A mixed plane
    must never reach the first governed ``DROP DATABASE`` caller: the durable-standalone
    posture would proof-check FAKE in-memory content against REAL durable registry rows,
    and the reverse mix would drop REAL physical databases against a volatile registry.
    Matched postures expose the real services un-wrapped."""

    def __init__(self, posture: str) -> None:
        self._posture = posture

    def _deny(self, operation: str) -> NoReturn:
        raise ProvisioningError(
            f"{operation}() is disabled under a MIXED effective composition (PRD 07D-2b.2b): "
            f"{self._posture}. The durable-store standalone posture is audit/registry-only "
            "(PRD 06 B-7B); recovery compensation and the orphan scan require the matched "
            "all-postgres composition (PRD 07D-1) — fail closed, no side effects were performed."
        )

    def deprovision_tenant_database(self, tenant_id: str, *, actor: str, correlation_id: str) -> DeprovisionOutcome:
        self._deny("deprovision_tenant_database")

    def scan_for_orphans(self) -> List[OrphanScanEntry]:
        self._deny("scan_for_orphans")


class ControlPlane:
    """Assembled control plane. Construction performs no I/O and no bootstrap."""

    def __init__(self, store: ControlStore | None = None) -> None:
        # PRD 07D-2a: fail-closed selector coherence BEFORE any builder runs (AT-07D1-9).
        self._check_selector_coherence()
        # An explicit store wins (tests / the B-7A harness). Otherwise the Control-Store is
        # selected by env (B-7B); the default is in-memory and construction performs no I/O.
        self.store = store if store is not None else self._build_store()
        # PRD 07D-3b (AT-PMV46-4): the per-unit-of-work ControlStore boundary. Built ONCE;
        # no transport is wired here (07E). The 07E contract: every request transport MUST
        # acquire a fresh unit of work per request via control_store_unit_of_work() and MUST
        # NOT share it across concurrent requests. self.store remains the single-context
        # store for the existing non-concurrent composition paths (no I/O at construction).
        self.store_factory: "SharedControlStoreFactory | PostgresControlStoreFactory" = self._build_store_factory(
            explicit_store=store is not None
        )
        self.audit = ControlPlaneAudit(self.store)
        self.registry = TenantRegistry(self.store, self.audit)
        self.membership = MembershipRegistry(self.store)
        self.federation = FederationStore(self.store)
        self.directory = GlobalDirectory(self.store)
        self.readiness = ReadinessFramework()
        self.schema = SchemaCompatibilityChecker(SUPPORTED_SCHEMA_MIN, SUPPORTED_SCHEMA_MAX)
        self.secret_store = EnvReferenceSecretStore()
        self.bootstrap = BootstrapController(self.secret_store)
        # D-15 orchestration wiring (B-1 default; PRD 07D-1 postgres path). Adapters selected by
        # env (OB-1); default is in-memory. Construction performs no I/O (lazy-connect).
        # PRD 07D-2b.2b: the ledger is built ONCE and shared by the verification gate and the
        # recovery services — two in-memory instances would give compensation a blind (empty)
        # collision inventory (element 5 of the ownership proof would be vacuous).
        self._ledger: DistinctnessLedger = self._build_ledger()
        self.operator, self.provisioning = self._build_provisioning()
        self.schema_applicator = self._build_schema_applicator()
        # PRD 07D-2b.1: the symmetric effective-posture onboard-time guard wraps the orchestrator
        # LAST, over the objects actually composed (never env values) — see _guarded_onboarding.
        self.onboarding = self._guarded_onboarding(
            OnboardingOrchestrator(self.registry, self.operator, self.provisioning, self.audit, self.schema_applicator)
        )
        # PRD 07D-2b.2b (R1-2): recovery compensation + orphan scan — INTERNAL-only composition
        # (no new env selector, no new constructor parameter). The inspection posture derives
        # from the EXISTING provisioning selector; the same effective-object guard rule that
        # protects onboarding denies BOTH new entry points under a mixed plane.
        supported_versions = [str(v) for v in range(SUPPORTED_SCHEMA_MIN, SUPPORTED_SCHEMA_MAX + 1)]
        inspection = self._build_recovery_inspection()
        self.recovery: "RecoveryCompensationService | _MixedPostureRecoveryGuard"
        self.orphan_scan: "OrphanScanService | _MixedPostureRecoveryGuard"
        self.recovery, self.orphan_scan = self._guarded_recovery(
            RecoveryCompensationService(
                self.registry,
                self.operator,
                self.audit,
                inspection,
                self._ledger,
                supported_schema_versions=supported_versions,
            ),
            OrphanScanService(self.store, inspection, self._ledger, supported_schema_versions=supported_versions),
        )

    def _mixed_effective_posture(self) -> Optional[str]:
        """The symmetric effective-object posture (PRD 07D-2b.1; reused by 07D-2b.2b).

        Computed from the COMPOSED objects, never env values, so both explicit ``store=``
        constructor bypass directions are covered (the 07D-2a matrix reads env only):
        ``store_kind = durable`` iff the effective store is the Postgres ControlStore;
        ``live_kind = postgres`` iff the effective operator is the Postgres provisioning
        operator (``store=`` is this constructor's ONLY explicit parameter, so the live side
        is always env-composed and matrix-coherent — the operator stands for the whole live
        trio). Returns None for MATCHED postures (both in-memory / both postgres) and the
        non-sensitive posture description for MIXED ones. Performs no I/O (isinstance only)."""
        # Function-local imports mirror the builders' driver-containment pattern.
        from .adapters.providers.postgres_provisioning_operator import PostgresProvisioningOperator
        from .adapters.providers.postgres_store import PostgresControlStore

        store_durable = isinstance(self.store, PostgresControlStore)
        live_postgres = isinstance(self.operator, PostgresProvisioningOperator)
        if store_durable == live_postgres:
            return None
        return (
            f"control store={'postgres' if store_durable else 'in_memory'}, "
            f"provisioning operator={'postgres' if live_postgres else 'in_memory'}"
        )

    def _guarded_onboarding(self, inner: OnboardingOrchestrator) -> "OnboardingOrchestrator | _MixedPostureOnboardingGuard":
        """PRD 07D-2b.1 (AC-4..8): symmetric effective-object onboard-time guard.

        MATCHED postures return the orchestrator unchanged; MIXED postures get the
        fail-closed facade (see ``_mixed_effective_posture`` for the posture rule)."""
        posture = self._mixed_effective_posture()
        if posture is None:
            return inner
        return _MixedPostureOnboardingGuard(inner, posture)

    def _guarded_recovery(
        self,
        compensation: RecoveryCompensationService,
        scan: OrphanScanService,
    ) -> Tuple[
        "RecoveryCompensationService | _MixedPostureRecoveryGuard",
        "OrphanScanService | _MixedPostureRecoveryGuard",
    ]:
        """PRD 07D-2b.2b (R1-2): the same effective-object rule guards the recovery surface.

        MATCHED postures expose the real compensation + scan services un-wrapped; MIXED
        postures replace BOTH with the pre-effect deny facade (zero events, both mix
        directions — the first governed DROP DATABASE caller never composes half-live)."""
        posture = self._mixed_effective_posture()
        if posture is None:
            return compensation, scan
        guard = _MixedPostureRecoveryGuard(posture)
        return guard, guard

    def _build_recovery_inspection(self) -> RecoveryInspectionPort:
        """Select the recovery-inspection adapter (PRD 07D-2b.2b R1-1/R1-2).

        NO new env selector: the posture derives from the EXISTING provisioning selector
        (normalized byte-equal to the builders). The postgres path composes the live
        inspection adapter over the EXISTING admin + control-store secret bindings (lazy,
        references only); the default path is the pure-stdlib double bound to the in-memory
        operator's provisioned view and the nonprod Control-DB identity. Unknown selector
        values already failed closed in ``_build_provisioning`` (which runs first)."""
        if self._selector_value(PROVISIONING_ADAPTER_ENV) == "postgres":
            from .adapters.providers.postgres_recovery_inspection import (  # function-local (driver containment)
                PostgresRecoveryInspection,
            )

            admin_secrets = EnvReferenceSecretStore(allowed=frozenset({*DEFAULT_ALLOWED, PROVISIONING_ADMIN_DSN_REF}))
            control_secrets, control_ref = self._control_store_secret_binding()
            return PostgresRecoveryInspection(
                admin_secrets=admin_secrets,
                admin_ref=SecretRef(store_ref=PROVISIONING_ADMIN_DSN_REF, version="1"),
                control_secrets=control_secrets,
                control_ref=control_ref,
            )
        operator = self.operator

        def provisioned_view() -> Set[str]:
            # A LIVE view of the in-memory operator's provisioned targets: each is an EMPTY
            # database in the default plane (the operator records intent; creates nothing).
            return set(operator.provisioned) if isinstance(operator, InMemoryProvisioningOperator) else set()

        return InMemoryRecoveryInspection(control_database_name=NONPROD_CONTROL_TARGET, provisioned_view=provisioned_view)

    @staticmethod
    def _selector_value(env_name: str) -> str:
        """One selector's effective value — normalized BYTE-EQUAL to the builders (07D-2a R1-10).

        A value like ``'  IN_MEMORY  '`` must classify identically here and in ``_build_store`` /
        ``_build_provisioning`` / ``_build_schema_applicator`` / ``_build_ledger``."""
        return (os.environ.get(env_name) or "in_memory").strip().lower()

    def _check_selector_coherence(self) -> None:
        """PRD 07D-2a selector-coherence matrix (AT-07D1-9) — fail closed at construction.

        RULE 1: 'postgres' on ANY live-side selector (provisioning / schema applicator /
        distinctness ledger) requires ALL FOUR selectors (incl. the control store) to be
        'postgres'; any mix raises ValueError. RULE 2: control-store-standalone 'postgres' stays
        ALLOWED (the live-proven B-7B durable audit/registry posture — creates nothing physical;
        see the 07D-2a documented residual). RULE 3: all-in_memory and all-postgres are allowed.
        Reads the four ENV VALUES ONLY (never the effective store object — the explicit ``store=``
        constructor param remains a deliberate bypass used by the B-7B selector tests). Performs
        no I/O; unknown selector tokens are left to the builders' existing per-selector
        fail-closed ValueError (the outcome is ValueError either way)."""
        selectors = (CONTROL_STORE_ENV, *_LIVE_SELECTOR_ENVS)
        values = {name: self._selector_value(name) for name in selectors}
        live = [name for name in _LIVE_SELECTOR_ENVS if values[name] == "postgres"]
        if live and any(values[name] != "postgres" for name in selectors):
            mixed = ", ".join(f"{name}={values[name]!r}" for name in selectors)
            raise ValueError(
                "incoherent selector combination (PRD 07D-2a RULE 1): selecting 'postgres' for "
                "provisioning, the tenant schema applicator, or the distinctness ledger requires "
                f"ALL FOUR selectors to be 'postgres' — got {mixed}. Half-live compositions "
                "manufacture orphans or record fabricated evidence (fail closed)."
            )

    def _build_store(self) -> ControlStore:
        """Select the Control-Store backend (controlled non-production; PRD 06 B-7B).

        Default (env unset/empty) is the in-memory adapter — construction performs no I/O.
        ``postgres`` selects the durable Control-DB-backed store (lazy-connect; the audit sink
        is one consumer). Any other value raises (fail closed), mirroring the fail-closed
        pattern of ``_build_provisioning`` / ``_build_ledger``.
        """
        kind = (os.environ.get(CONTROL_STORE_ENV) or "in_memory").strip().lower()
        if kind in ("", "in_memory"):
            return InMemoryControlStore(schema_version=1)
        if kind == "postgres":
            return self._build_durable_control_store()
        raise ValueError(f"unsupported {CONTROL_STORE_ENV}={kind!r}; expected 'in_memory' or 'postgres'")

    def _build_store_factory(self, *, explicit_store: bool) -> "SharedControlStoreFactory | PostgresControlStoreFactory":
        """Build the per-unit-of-work ControlStore factory (PRD 07D-3b; AT-PMV46-4).

        Env-coherent with ``_build_store``: the in-memory default (and any explicit ``store=``
        injection — tests/harnesses) wraps THE composed store, whose state is the process-local
        instance; ``postgres`` issues a FRESH lazily-connecting durable store per unit of work
        with the SAME secret binding (references only, D-14 — no DSN literal transits here).
        Construction performs no I/O. A request transport (07E, not wired in this slice) must
        acquire one unit of work per request from this factory and never share it."""
        if explicit_store:
            return SharedControlStoreFactory(self.store)
        kind = (os.environ.get(CONTROL_STORE_ENV) or "in_memory").strip().lower()
        if kind in ("", "in_memory"):
            return SharedControlStoreFactory(self.store)
        if kind == "postgres":
            control_store_secrets, ref = self._control_store_secret_binding()
            return PostgresControlStoreFactory(secrets=control_store_secrets, ref=ref)
        raise ValueError(f"unsupported {CONTROL_STORE_ENV}={kind!r}; expected 'in_memory' or 'postgres'")

    def control_store_unit_of_work(self) -> "ContextManager[ControlStore]":
        """Acquire ONE ControlStore unit of work (PRD 07D-3b; AT-PMV46-4).

        The Tier-2 boundary: one logical request → one store → one Control-DB connection,
        held across the request's transitions (CAS + audit commit together on it) and
        released (rollback + close) at exit. NEVER share the yielded store across concurrent
        requests — that is the exact hazard 07D-3b closes. 07E transports must call this
        once per request."""
        return self.store_factory.acquire()

    def _control_store_secret_binding(self) -> Tuple[EnvReferenceSecretStore, SecretRef]:
        """The Control-DB DSN secret binding (D-14; PRD 06 B-7B): resolver + reference, no literal.

        The Control-DB descriptor is a SECRET REFERENCE: the composition root holds
        ``{store_ref, version}``, never a DSN literal, and never reuses ``SNACKPORTAL_TEST_DSN``.
        Resolution uses a SEPARATE ``EnvReferenceSecretStore`` whose allow-list is widened to
        include the control-store ref ONLY — the default trust-anchor-only secret store
        (``self.secret_store``, used by Bootstrap) is preserved unchanged. Shared by the durable
        ControlStore (B-7B), the durable distinctness ledger, and the D-C Control-DB evidence
        acquisition (PRD 07D-1) so all three resolve the SAME Control-DB reference."""
        store_ref = (os.environ.get(CONTROL_STORE_DSN_REF_ENV) or DEFAULT_CONTROL_STORE_DSN_REF).strip()
        ref = SecretRef(store_ref=store_ref, version="1")
        # Widen the allow-list for the control-store ref ONLY (default trust-anchor-only preserved
        # everywhere else). Without this, EnvReferenceSecretStore.resolve() raises PermissionError.
        secrets = EnvReferenceSecretStore(allowed=frozenset({*DEFAULT_ALLOWED, store_ref}))
        return secrets, ref

    def _build_durable_control_store(self) -> ControlStore:
        """Build the durable PostgreSQL ControlStore (lazy-connect; references only — D-14).

        The provider import is function-local so the composition root binds no database driver at
        module load (Driver Containment Standard). Construction opens no connection (lazy); a
        missing/unresolvable ref or an unreachable Control DB fails closed on the first store
        operation. The secret binding is the shared ``_control_store_secret_binding``."""
        from .adapters.providers.postgres_store import PostgresControlStore  # function-local (driver containment)

        control_store_secrets, ref = self._control_store_secret_binding()
        return PostgresControlStore(secrets=control_store_secrets, ref=ref)

    def _build_provisioning(self) -> Tuple[ProvisioningOperator, ProvisioningVerificationService]:
        """Build the D-15 provisioning operator + verification gate (controlled non-prod).

        Default (env unset/empty) is the fully in-memory composition — no I/O on construction.
        ``postgres`` (PRD 07D-1 composition activation) is the REAL physical provisioning path —
        see ``_build_postgres_provisioning``. Any other value raises ValueError (fail closed; no
        silent fallback).
        """
        adapter = (os.environ.get(PROVISIONING_ADAPTER_ENV) or "in_memory").strip().lower()
        supported = [str(v) for v in range(SUPPORTED_SCHEMA_MIN, SUPPORTED_SCHEMA_MAX + 1)]
        if adapter in ("", "in_memory"):
            operator: ProvisioningOperator = InMemoryProvisioningOperator()
            provisioning = ProvisioningVerificationService(
                self.store,
                self.audit,
                InMemoryTenantDatabaseProbe(schema_version=str(SUPPORTED_SCHEMA_MAX)),
                CanonicalTenantRefInMemoryEvidence(),
                nonprod_control_db_evidence(),
                ledger=self._ledger,
                supported_schema_versions=supported,
            )
            return operator, provisioning
        if adapter == "postgres":
            return self._build_postgres_provisioning(supported)
        raise ValueError(f"unsupported {PROVISIONING_ADAPTER_ENV}={adapter!r}; expected 'in_memory' or 'postgres'")

    def _build_postgres_provisioning(self, supported: List[str]) -> Tuple[ProvisioningOperator, ProvisioningVerificationService]:
        """The REAL physical provisioning path (PRD 07D-1; controlled non-production).

        * operator — ``PostgresProvisioningOperator`` constructed with ``secrets=`` + ``ref=``
          (never a raw DSN): the admin descriptor is resolved by the SecretRef
          ``control/provisioning-admin-dsn`` through a widened-allow-list resolver, per
          operation, lazily (D-14).
        * gate — the inherited ``ProvisioningVerificationService`` with the real Postgres probe
          and tenant evidence provider; tenant DSNs resolve through the control-plane
          ``EnvTenantDsnSecretStore`` via the canonical ``tenant/<tenant_id>/dsn`` refs minted by
          onboarding (D-A). REAL Control-DB evidence (D-C) is gathered lazily on first
          verification by ``PostgresDistinctnessEvidenceProvider`` against the control-store DB
          reference — fail-closed if unavailable.

        Provider imports are function-local (Driver Containment Standard): the composition root
        binds no database driver at module load, and construction performs no I/O.
        """
        from .adapters.providers.postgres_distinctness import PostgresDistinctnessEvidenceProvider
        from .adapters.providers.postgres_probe import PostgresTenantProbe
        from .adapters.providers.postgres_provisioning_operator import PostgresProvisioningOperator

        admin_secrets = EnvReferenceSecretStore(allowed=frozenset({*DEFAULT_ALLOWED, PROVISIONING_ADMIN_DSN_REF}))
        operator: ProvisioningOperator = PostgresProvisioningOperator(
            secrets=admin_secrets, ref=SecretRef(store_ref=PROVISIONING_ADMIN_DSN_REF, version="1")
        )
        tenant_secrets = EnvTenantDsnSecretStore()
        control_secrets, control_ref = self._control_store_secret_binding()
        control_evidence_provider = PostgresDistinctnessEvidenceProvider(control_secrets)

        def _control_evidence() -> Optional[DistinctnessEvidence]:
            # D-C: REAL Control-DB evidence — gathered against the control-store DB reference at
            # first verification (lazy). The provider fails closed (returns None) on any error;
            # 07D-2a (AT-07D1-8) additionally requires a PROVEN write-sentinel — an unproven
            # gather is treated as unavailable. The gate then raises rather than verifying
            # against placeholder or unproven evidence.
            return _proven_control_evidence(
                control_evidence_provider.gather(
                    control_ref,
                    sentinel_token=uuid.uuid4().hex,
                    sentinel_namespace=NONPROD_CONTROL_SENTINEL_NAMESPACE,
                )
            )

        gate = _LazyControlEvidenceGate(
            self.store,
            self.audit,
            PostgresTenantProbe(tenant_secrets),
            PostgresDistinctnessEvidenceProvider(tenant_secrets),
            # Constructor placeholder ONLY (the gate requires a value at construction, but real
            # evidence is live I/O): replaced by the REAL Control-DB evidence before ANY
            # verification proceeds (_LazyControlEvidenceGate.verify, fail-closed).
            nonprod_control_db_evidence(),
            ledger=self._ledger,
            supported_schema_versions=supported,
            control_evidence_factory=_control_evidence,
        )
        return operator, gate

    def _build_schema_applicator(self) -> TenantSchemaApplicator:
        """Select the tenant schema applicator (controlled non-prod; PRD 07B; D15 Step 2b).

        Default (env unset/empty) is the in-memory applicator — construction performs no I/O and
        applies no DDL. ``postgres`` (PRD 07D-1 composition activation) is the REAL applicator —
        the existing 14-file tenant DDL set + System Primary seed in one atomic, fail-closed
        transaction (live-proven by the PRD 07B requires_pg harness) — wired against the
        control-plane tenant-DSN provider that resolves the canonical refs minted by onboarding.
        Lazy: no I/O at construction. Any other value raises ValueError (fail closed).
        """
        kind = (os.environ.get(TENANT_SCHEMA_APPLICATOR_ENV) or "in_memory").strip().lower()
        if kind in ("", "in_memory"):
            return InMemoryTenantSchemaApplicator()
        if kind == "postgres":
            from .adapters.providers.postgres_tenant_schema_applicator import (  # function-local (driver containment)
                PostgresTenantSchemaApplicator,
            )

            return PostgresTenantSchemaApplicator(EnvTenantDsnSecretStore())
        raise ValueError(f"unsupported {TENANT_SCHEMA_APPLICATOR_ENV}={kind!r}; expected 'in_memory' or 'postgres'")

    def _build_ledger(self) -> DistinctnessLedger:
        """Select the distinctness-evidence ledger (controlled non-prod; PRD 06 B-2).

        Default (env unset/empty) is the in-memory ledger — construction performs no I/O.
        ``postgres`` (PRD 07D-1 composition activation) selects the durable Control-DB-backed
        ledger over the SAME control-store secret binding as the durable ControlStore (B-7B):
        lazy-connect (no I/O at construction), references only, fail-closed on every operation.
        Any other value raises ValueError (fail closed) — never a silent fallback.
        """
        kind = (os.environ.get(DISTINCTNESS_LEDGER_ENV) or "in_memory").strip().lower()
        if kind in ("", "in_memory"):
            return InMemoryDistinctnessLedger()
        if kind == "postgres":
            from .adapters.providers.postgres_distinctness_ledger import (  # function-local (driver containment)
                PostgresDistinctnessLedger,
            )

            secrets, ref = self._control_store_secret_binding()
            return PostgresDistinctnessLedger(secrets, ref)
        raise ValueError(f"unsupported {DISTINCTNESS_LEDGER_ENV}={kind!r}; expected 'in_memory' or 'postgres'")


def liveness() -> Dict[str, str]:
    # Static, non-disclosing liveness (no tenant/database detail).
    return {"service": SERVICE, "status": "alive", "build_phase": "2"}


def create_app() -> ControlPlane:
    return ControlPlane()


# --- B5-1: control-plane read-edge serve-composition seam -------------------------------------
# A config-selectable, socket-binding, serve-INERT environment-composition seam for the existing
# read-edge server factory (``make_server`` / ``create_app`` in
# ``adapters/providers/http_read_api.py``), mirroring the merged Database Router
# (``build_dispatch_server_from_env``) and Auth Router (``build_authenticate_server_from_env``)
# server seams. It composes a read-edge server OBJECT from environment config; it does NOT serve
# requests, start a thread or service, open a database, run runtime DDL, complete the Physical
# Multi-Database MVP, or make the physical live-topology smoke runnable — one prerequisite among
# several (B5-BLK-4 stays OPEN; the runnable/serve lifecycle is B5-2 scope).
#
# Intentional divergence from the router server seams: the read-edge server side has no upstream
# client-URL selector, so the bind HOST itself is the activation selector. While inactive the seam
# returns ``None`` WITHOUT consulting the port, composing ``create_app()``, importing/calling
# ``make_server``, or binding a socket. ``create_app()``'s own SP2_CP_* selector-coherence rules
# keep the composed app fail-closed.

# The read-edge bind host — the ACTIVATION selector. Non-secret internal config (the loopback/
# internal bind host, never a credential). Unset / empty / whitespace-only → the seam is inactive
# (returns ``None``); a non-empty value (stripped) is the bind host.
SP2_CP_READ_HOST = "SP2_CP_READ_HOST"

# The read-edge bind port. Consulted ONLY when the host selector is active. Unset / empty /
# whitespace → ``0`` (ephemeral); otherwise a base-10 integer in ``[0, 65535]``; anything else →
# ``ValueError`` raised BEFORE ``create_app()`` / ``make_server`` / any socket bind (fail closed —
# never a silent fallback).
SP2_CP_READ_PORT = "SP2_CP_READ_PORT"


def _read_port_from_env() -> int:
    """Parse ``SP2_CP_READ_PORT`` fail-closed: unset/empty/whitespace → ``0`` (ephemeral);
    otherwise a base-10 integer in ``[0, 65535]``, else ``ValueError`` — raised BEFORE any socket
    bind so malformed config never opens a listener."""
    raw = (os.environ.get(SP2_CP_READ_PORT) or "").strip()
    if not raw:
        return 0
    try:
        port = int(raw, 10)
    except ValueError:
        raise ValueError(f"invalid {SP2_CP_READ_PORT}={raw!r}; expected an integer in [0, 65535]") from None
    if not (0 <= port <= 65535):
        raise ValueError(f"invalid {SP2_CP_READ_PORT}={raw!r}; port out of range [0, 65535]")
    return port


def build_read_server_from_env() -> Optional[Tuple[object, str]]:
    """The config-selectable control-plane read-edge server composition seam (B5-1).

    Host-gate-first (the read-edge server side has no upstream client-URL selector, so the bind
    HOST is the activation selector):

    * ``SP2_CP_READ_HOST`` unset, or empty/whitespace after stripping → ``None``: the seam is
      inactive; ``SP2_CP_READ_PORT`` is NOT consulted, ``create_app()`` is NOT composed,
      ``make_server`` is NOT imported or called, and no socket binds.
    * a non-empty ``SP2_CP_READ_HOST`` (stripped) → compose the production app via ``create_app()``
      and construct the read-edge server via the existing ``make_server`` adapter, returning
      ``(server, base_url)``. ``SP2_CP_READ_PORT`` unset/empty → ``0`` (ephemeral); otherwise an
      integer in ``[0, 65535]``; non-integer / negative / out-of-range → ``ValueError`` raised
      BEFORE ``create_app()`` / ``make_server`` so malformed config never binds a socket.

    Side-effect boundary (LOAD-BEARING): this seam is DB-connection-inert, network-read-inert,
    thread-inert, and serve-inert — ``create_app()`` construction opens no database (lazy-connect),
    performs no network read, and the seam starts no serve loop, thread, daemon, or service. But it
    is NOT socket-inert: when active, ``make_server`` constructs an ``HTTPServer`` which binds +
    activates a local listening socket at construction (default ``port=0`` → ephemeral). Callers /
    tests own the socket lifecycle and must close it.

    No overclaim: it composes a read-edge server *object* from config; it does NOT serve requests,
    run a production service, open a physical database, complete the Physical Multi-Database MVP,
    or make the physical live-topology smoke runnable. It is one prerequisite among several.
    """
    host = (os.environ.get(SP2_CP_READ_HOST) or "").strip()
    if not host:
        return None
    port = _read_port_from_env()
    # Lazy relative import keeps control_plane/main.py transport-free at module import (http.server
    # is pulled in via the read adapter only when the seam is active); make_server binds the socket.
    from .adapters.providers.http_read_api import make_server

    return make_server(create_app(), host, port)


# --- DBR-AR-2C: routing-audit ingest-server composition seam -----------------------------------
# The config-selectable, socket-binding, serve-INERT composition seam for the DBR-AR-2B internal
# routing-audit ingest edge (``build_routing_audit_server`` bound to the durable
# ``PostgresRoutingAuditStore``), mirroring the B5-1 read-edge seam: the bind HOST is the
# activation selector; while inactive the seam returns ``None`` WITHOUT consulting the port,
# constructing the store, importing the ingest adapter, or binding a socket. The ingest surface is
# internal-only, so the host is restricted to the loopback vocabulary below (fail closed). The
# store is lazy-connect and reference-only (D-14; the shared control-store secret binding): no raw
# descriptor value, no DDL apply, no serve loop, no thread, no import-time socket, and no DB I/O
# happen here. DBR-AR-2 remains OPEN; live durability proof is DBR-AR-2D scope.

# The routing-audit ingest bind host — the ACTIVATION selector (B5-1 convention). Non-secret
# internal config. Unset / empty / whitespace-only → the seam is inactive (returns ``None``);
# otherwise the stripped value must be one of the internal loopback hosts (IC-010 §R).
SP2_CP_ROUTING_AUDIT_HOST = "SP2_CP_ROUTING_AUDIT_HOST"

# The routing-audit ingest bind port. Consulted ONLY when the host selector is active. Unset /
# empty / whitespace → ``0`` (ephemeral); otherwise a base-10 integer in ``[0, 65535]``; anything
# else → ``ValueError`` raised BEFORE store construction and socket bind (fail closed).
SP2_CP_ROUTING_AUDIT_PORT = "SP2_CP_ROUTING_AUDIT_PORT"

# The internal-only ingest edge binds loopback hosts exclusively (it must never be
# portal-reachable or registered as a public ingress — DBR-AR-2B module contract).
_ROUTING_AUDIT_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def _routing_audit_port_from_env() -> int:
    """Parse ``SP2_CP_ROUTING_AUDIT_PORT`` fail-closed: unset/empty/whitespace → ``0``
    (ephemeral); otherwise a base-10 integer in ``[0, 65535]``, else ``ValueError`` — raised
    BEFORE store construction and any socket bind so malformed config never opens a listener."""
    raw = (os.environ.get(SP2_CP_ROUTING_AUDIT_PORT) or "").strip()
    if not raw:
        return 0
    try:
        port = int(raw, 10)
    except ValueError:
        raise ValueError(f"invalid {SP2_CP_ROUTING_AUDIT_PORT}={raw!r}; expected an integer in [0, 65535]") from None
    if not (0 <= port <= 65535):
        raise ValueError(f"invalid {SP2_CP_ROUTING_AUDIT_PORT}={raw!r}; port out of range [0, 65535]")
    return port


def build_routing_audit_server_from_env() -> Optional[Tuple[object, str]]:
    """The config-selectable routing-audit ingest-server composition seam (DBR-AR-2C).

    Host-gate-first (the B5-1 convention — the bind HOST is the activation selector):

    * ``SP2_CP_ROUTING_AUDIT_HOST`` unset, or empty/whitespace after stripping → ``None``:
      the seam is inactive; the port and secret reference are NOT consulted, no store is
      constructed, no provider module is imported, and no socket binds.
    * an active host must be one of ``127.0.0.1`` / ``localhost`` / ``::1`` — the ingest
      edge is internal-only (DBR-AR-2B); any other host → ``ValueError`` BEFORE store
      construction and socket bind (fail closed).
    * ``SP2_CP_ROUTING_AUDIT_PORT`` unset/empty → ``0`` (ephemeral); otherwise an integer
      in ``[0, 65535]``; anything else → ``ValueError`` BEFORE store construction and
      socket bind.
    * the durable store binds the SAME reference-only control-store secret composition as
      the durable ControlStore (D-14; ``SP2_CP_ROUTING_AUDIT_HOST`` never carries a
      credential and no raw descriptor value transits here): a blank effective
      ``SP2_CP_CONTROL_STORE_DSN_REF`` → ``ValueError`` at composition; an unresolvable
      reference fails closed at FIRST STORE USE (the B-7B lazy pattern), never at import
      or composition.

    Side-effect boundary (LOAD-BEARING): this seam is DB-inert (``PostgresRoutingAuditStore``
    is lazy-connect — construction performs no I/O), serve-inert, and thread-inert; it is
    NOT socket-inert — when active, ``build_routing_audit_server`` constructs the plain
    single-threaded stdlib server which binds + activates a local listening socket at
    construction (default ``port=0`` → ephemeral). Callers/tests own the socket lifecycle
    and must close it. Starting the request loop is NEVER done here.

    No overclaim: it composes the ingest server *object* bound to the durable store; it
    does NOT serve requests, run a production service, apply DDL, open a database, prove
    live durability (DBR-AR-2D scope), close DBR-AR-2, complete the Physical
    Multi-Database MVP, or change the activation gate. It is one prerequisite among
    several.
    """
    host = (os.environ.get(SP2_CP_ROUTING_AUDIT_HOST) or "").strip()
    if not host:
        return None
    if host not in _ROUTING_AUDIT_LOOPBACK_HOSTS:
        raise ValueError(
            f"invalid {SP2_CP_ROUTING_AUDIT_HOST}; the routing-audit ingest edge is internal-only and"
            f" must bind one of {_ROUTING_AUDIT_LOOPBACK_HOSTS} (fail closed — the configured value is"
            " not echoed)"
        )
    port = _routing_audit_port_from_env()
    store_ref = (os.environ.get(CONTROL_STORE_DSN_REF_ENV) or DEFAULT_CONTROL_STORE_DSN_REF).strip()
    if not store_ref:
        raise ValueError(
            f"blank {CONTROL_STORE_DSN_REF_ENV}; the durable routing-audit store requires the"
            " control-store secret REFERENCE (references only — never a raw descriptor value)"
        )
    # The shared reference-only control-store secret binding (D-14): a resolver whose allow-list is
    # widened for the control-store ref ONLY, plus the reference itself — never a resolved value.
    secrets = EnvReferenceSecretStore(allowed=frozenset({*DEFAULT_ALLOWED, store_ref}))
    ref = SecretRef(store_ref=store_ref, version="1")
    # Function-local provider imports (Driver Containment Standard / transport containment): the
    # composition root binds no DB driver and no transport module at module load.
    from .adapters.providers.http_routing_audit_api import build_routing_audit_server
    from .adapters.providers.postgres_store import PostgresRoutingAuditStore

    store = PostgresRoutingAuditStore(secrets=secrets, ref=ref)
    return build_routing_audit_server(store, host=host, port=port)


# --- Gateway Audit V1a: Gateway operational-audit ingest-server composition seam ---------------
# The config-selectable, socket-binding, serve-INERT composition seam for the Gateway Audit V1a
# internal ingest edge (``build_gateway_audit_server`` bound to the durable
# ``PostgresGatewayAuditStore``), mirroring the routing-audit seam above: the bind HOST is the
# activation selector; while inactive the seam returns ``None`` WITHOUT consulting the port,
# constructing the store, importing the ingest adapter, or binding a socket. The ingest surface is
# internal-only, so the host is restricted to the loopback vocabulary below (fail closed). The store
# is lazy-connect and reference-only (D-14; the shared control-store secret binding): no raw
# descriptor value, no DDL apply, no serve loop, no thread, no import-time socket, and no DB I/O
# happen here. The Control Plane remains the sole Control-DB writer.

# The Gateway-audit ingest bind host — the ACTIVATION selector. Non-secret internal config. Unset /
# empty / whitespace-only → the seam is inactive (returns ``None``); otherwise the stripped value
# must be one of the internal loopback hosts (IC-010 §R).
SP2_CP_GATEWAY_AUDIT_HOST = "SP2_CP_GATEWAY_AUDIT_HOST"

# The Gateway-audit ingest bind port. Consulted ONLY when the host selector is active. Unset / empty
# / whitespace → ``0`` (ephemeral); otherwise a base-10 integer in ``[0, 65535]``; anything else →
# ``ValueError`` raised BEFORE store construction and socket bind (fail closed).
SP2_CP_GATEWAY_AUDIT_PORT = "SP2_CP_GATEWAY_AUDIT_PORT"

# The internal-only ingest edge binds loopback hosts exclusively (it must never be portal-reachable
# or registered as a public ingress — the ingest module contract).
_GATEWAY_AUDIT_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def _gateway_audit_port_from_env() -> int:
    """Parse ``SP2_CP_GATEWAY_AUDIT_PORT`` fail-closed: unset/empty/whitespace → ``0`` (ephemeral);
    otherwise a base-10 integer in ``[0, 65535]``, else ``ValueError`` — raised BEFORE store
    construction and any socket bind so malformed config never opens a listener."""
    raw = (os.environ.get(SP2_CP_GATEWAY_AUDIT_PORT) or "").strip()
    if not raw:
        return 0
    try:
        port = int(raw, 10)
    except ValueError:
        raise ValueError(f"invalid {SP2_CP_GATEWAY_AUDIT_PORT}={raw!r}; expected an integer in [0, 65535]") from None
    if not (0 <= port <= 65535):
        raise ValueError(f"invalid {SP2_CP_GATEWAY_AUDIT_PORT}={raw!r}; port out of range [0, 65535]")
    return port


def build_gateway_audit_server_from_env() -> Optional[Tuple[object, str]]:
    """The config-selectable Gateway operational-audit ingest-server composition seam (Gateway Audit V1a).

    Host-gate-first (the routing-audit convention — the bind HOST is the activation selector):

    * ``SP2_CP_GATEWAY_AUDIT_HOST`` unset, or empty/whitespace after stripping → ``None``: the seam
      is inactive; the port and secret reference are NOT consulted, no store is constructed, no
      provider module is imported, and no socket binds.
    * an active host must be one of ``127.0.0.1`` / ``localhost`` / ``::1`` — the ingest edge is
      internal-only; any other host → ``ValueError`` BEFORE store construction and socket bind (fail
      closed).
    * ``SP2_CP_GATEWAY_AUDIT_PORT`` unset/empty → ``0`` (ephemeral); otherwise an integer in
      ``[0, 65535]``; anything else → ``ValueError`` BEFORE store construction and socket bind.
    * the durable store binds the SAME reference-only control-store secret composition as the durable
      ControlStore (D-14; ``SP2_CP_GATEWAY_AUDIT_HOST`` never carries a credential and no raw
      descriptor value transits here): a blank effective ``SP2_CP_CONTROL_STORE_DSN_REF`` →
      ``ValueError`` at composition; an unresolvable reference fails closed at FIRST STORE USE (the
      lazy pattern), never at import or composition.

    Side-effect boundary (LOAD-BEARING): this seam is DB-inert (``PostgresGatewayAuditStore`` is
    lazy-connect — construction performs no I/O), serve-inert, and thread-inert; it is NOT
    socket-inert — when active, ``build_gateway_audit_server`` constructs the plain single-threaded
    stdlib server which binds + activates a local listening socket at construction (default
    ``port=0`` → ephemeral). Callers/tests own the socket lifecycle and must close it. Starting the
    request loop is NEVER done here.

    No overclaim: it composes the ingest server *object* bound to the durable store; it does NOT
    serve requests, run a production service, apply DDL, open a database, prove live durability
    (the MANUAL_ONLY disposable proof scope), close any B5 blocker, or change the activation gate.
    """
    host = (os.environ.get(SP2_CP_GATEWAY_AUDIT_HOST) or "").strip()
    if not host:
        return None
    if host not in _GATEWAY_AUDIT_LOOPBACK_HOSTS:
        raise ValueError(
            f"invalid {SP2_CP_GATEWAY_AUDIT_HOST}; the Gateway-audit ingest edge is internal-only and"
            f" must bind one of {_GATEWAY_AUDIT_LOOPBACK_HOSTS} (fail closed — the configured value is"
            " not echoed)"
        )
    port = _gateway_audit_port_from_env()
    store_ref = (os.environ.get(CONTROL_STORE_DSN_REF_ENV) or DEFAULT_CONTROL_STORE_DSN_REF).strip()
    if not store_ref:
        raise ValueError(
            f"blank {CONTROL_STORE_DSN_REF_ENV}; the durable Gateway-audit store requires the"
            " control-store secret REFERENCE (references only — never a raw descriptor value)"
        )
    # The shared reference-only control-store secret binding (D-14): a resolver whose allow-list is
    # widened for the control-store ref ONLY, plus the reference itself — never a resolved value.
    secrets = EnvReferenceSecretStore(allowed=frozenset({*DEFAULT_ALLOWED, store_ref}))
    ref = SecretRef(store_ref=store_ref, version="1")
    # Function-local provider imports (Driver Containment Standard / transport containment): the
    # composition root binds no DB driver and no transport module at module load.
    from .adapters.providers.http_gateway_audit_api import build_gateway_audit_server
    from .adapters.providers.postgres_store import PostgresGatewayAuditStore

    store = PostgresGatewayAuditStore(secrets=secrets, ref=ref)
    return build_gateway_audit_server(store, host=host, port=port)


# --- W1a: Import operational-audit ingest-server composition seam ------------------------------
# The config-selectable, socket-binding, serve-INERT composition seam for the W1a Import-audit internal
# ingest edge (``build_import_audit_server`` bound to the durable ``PostgresImportAuditStore``), mirroring
# the Gateway-audit seam above: the bind HOST is the activation selector; while inactive the seam returns
# ``None`` WITHOUT consulting the port, constructing the store, importing the ingest adapter, or binding a
# socket. The ingest surface is internal-only, so the host is restricted to the loopback vocabulary below
# (fail closed). The store is lazy-connect and reference-only (D-14; the shared control-store secret binding):
# no raw descriptor value, no DDL apply, no serve loop, no thread, no import-time socket, and no DB I/O happen
# here. The Control Plane remains the sole Control-DB writer.

# The Import-audit ingest bind host — the ACTIVATION selector. Non-secret internal config. Unset / empty /
# whitespace-only → the seam is inactive (returns ``None``); otherwise the stripped value must be one of the
# internal loopback hosts (IC-010 §R).
SP2_CP_IMPORT_AUDIT_HOST = "SP2_CP_IMPORT_AUDIT_HOST"

# The Import-audit ingest bind port. Consulted ONLY when the host selector is active. Unset / empty /
# whitespace → ``0`` (ephemeral); otherwise a base-10 integer in ``[0, 65535]``; anything else → ``ValueError``
# raised BEFORE store construction and socket bind (fail closed).
SP2_CP_IMPORT_AUDIT_PORT = "SP2_CP_IMPORT_AUDIT_PORT"

# The internal-only ingest edge binds loopback hosts exclusively (it must never be portal-reachable or
# registered as a public ingress — the ingest module contract).
_IMPORT_AUDIT_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def _import_audit_port_from_env() -> int:
    """Parse ``SP2_CP_IMPORT_AUDIT_PORT`` fail-closed: unset/empty/whitespace → ``0`` (ephemeral); otherwise a
    base-10 integer in ``[0, 65535]``, else ``ValueError`` — raised BEFORE store construction and any socket
    bind so malformed config never opens a listener."""
    raw = (os.environ.get(SP2_CP_IMPORT_AUDIT_PORT) or "").strip()
    if not raw:
        return 0
    try:
        port = int(raw, 10)
    except ValueError:
        raise ValueError(f"invalid {SP2_CP_IMPORT_AUDIT_PORT}={raw!r}; expected an integer in [0, 65535]") from None
    if not (0 <= port <= 65535):
        raise ValueError(f"invalid {SP2_CP_IMPORT_AUDIT_PORT}={raw!r}; port out of range [0, 65535]")
    return port


def build_import_audit_server_from_env() -> Optional[Tuple[object, str]]:
    """The config-selectable Import operational-audit ingest-server composition seam (W1a).

    Host-gate-first (the Gateway-audit convention — the bind HOST is the activation selector):

    * ``SP2_CP_IMPORT_AUDIT_HOST`` unset, or empty/whitespace after stripping → ``None``: the seam is
      inactive; the port and secret reference are NOT consulted, no store is constructed, no provider module
      is imported, and no socket binds.
    * an active host must be one of ``127.0.0.1`` / ``localhost`` / ``::1`` — the ingest edge is internal-only;
      any other host → ``ValueError`` BEFORE store construction and socket bind (fail closed).
    * ``SP2_CP_IMPORT_AUDIT_PORT`` unset/empty → ``0`` (ephemeral); otherwise an integer in ``[0, 65535]``;
      anything else → ``ValueError`` BEFORE store construction and socket bind.
    * the durable store binds the SAME reference-only control-store secret composition as the durable
      ControlStore (D-14; ``SP2_CP_IMPORT_AUDIT_HOST`` never carries a credential and no raw descriptor value
      transits here): a blank effective ``SP2_CP_CONTROL_STORE_DSN_REF`` → ``ValueError`` at composition; an
      unresolvable reference fails closed at FIRST STORE USE (the lazy pattern), never at import or
      composition.

    Side-effect boundary (LOAD-BEARING): this seam is DB-inert (``PostgresImportAuditStore`` is lazy-connect —
    construction performs no I/O), serve-inert, and thread-inert; it is NOT socket-inert — when active,
    ``build_import_audit_server`` constructs the plain single-threaded stdlib server which binds + activates a
    local listening socket at construction (default ``port=0`` → ephemeral). Callers/tests own the socket
    lifecycle and must close it. Starting the request loop is NEVER done here.

    No overclaim: it composes the ingest server *object* bound to the durable store; it does NOT serve
    requests, run a production service, apply DDL, open a database, prove live durability (the MANUAL_ONLY
    disposable proof scope), close any B5 blocker, or change the activation gate.
    """
    host = (os.environ.get(SP2_CP_IMPORT_AUDIT_HOST) or "").strip()
    if not host:
        return None
    if host not in _IMPORT_AUDIT_LOOPBACK_HOSTS:
        raise ValueError(
            f"invalid {SP2_CP_IMPORT_AUDIT_HOST}; the Import-audit ingest edge is internal-only and"
            f" must bind one of {_IMPORT_AUDIT_LOOPBACK_HOSTS} (fail closed — the configured value is"
            " not echoed)"
        )
    port = _import_audit_port_from_env()
    store_ref = (os.environ.get(CONTROL_STORE_DSN_REF_ENV) or DEFAULT_CONTROL_STORE_DSN_REF).strip()
    if not store_ref:
        raise ValueError(
            f"blank {CONTROL_STORE_DSN_REF_ENV}; the durable Import-audit store requires the"
            " control-store secret REFERENCE (references only — never a raw descriptor value)"
        )
    # The shared reference-only control-store secret binding (D-14): a resolver whose allow-list is widened
    # for the control-store ref ONLY, plus the reference itself — never a resolved value.
    secrets = EnvReferenceSecretStore(allowed=frozenset({*DEFAULT_ALLOWED, store_ref}))
    ref = SecretRef(store_ref=store_ref, version="1")
    # Function-local provider imports (Driver Containment Standard / transport containment): the composition
    # root binds no DB driver and no transport module at module load.
    from .adapters.providers.http_import_audit_api import build_import_audit_server
    from .adapters.providers.postgres_store import PostgresImportAuditStore

    store = PostgresImportAuditStore(secrets=secrets, ref=ref)
    return build_import_audit_server(store, host=host, port=port)
