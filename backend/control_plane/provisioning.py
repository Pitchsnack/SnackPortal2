"""D15 provisioning verification gate (D15-ARCH-SPEC-01 §8 Steps 6-8, §9, §13).

The control-plane-owned service that turns the approved D15 architecture into behavior:

* a `ProvisioningOperator` port (WP-1/WP-2) — provisions a physically distinct tenant
  database (D-15: IaC substrate / automated, audited control-plane workflow); concrete
  operators that touch a real cluster live under `adapters/providers/**` and run in
  controlled non-production only.
* `ProvisioningVerificationService` (WP-3/WP-10/WP-11/WP-12) — runs reachability + schema
  validation AND Physical Distinctness Verification; a tenant reaches Ready (routing-
  eligible) ONLY when ALL pass (fail-closed). It emits reference-only operational audit
  (WP-12) and signals router cache invalidation on association change (WP-11).

Additive by construction: it does not modify the Phase-2 `TenantRegistry` or the Phase-4
`TenantLifecycleService`; it composes the existing probe with the new distinctness
verifier and is the authoritative "declare readiness" gate for D15. The Database Router
remains the sole database selector (IC-005/D-07); this service only sets the routing-
eligibility state (lifecycle == Ready) the router consumes and signals invalidation —
it never resolves a database. Credentials never appear here; associations are references
(D-14).
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import Callable, Iterable, Optional, Set

from shared.secrets import SecretRef

from . import events
from ._util import now_iso
from .audit import ControlPlaneAudit
from .distinctness import (
    REASON_CONTROL_DB_COLLISION,
    REASON_INCOMPLETE_EVIDENCE,
    REASON_TENANT_COLLISION,
    DistinctnessCollisionError,
    DistinctnessEvidence,
    DistinctnessEvidenceProvider,
    DistinctnessLedger,
    DistinctnessOutcome,
    DistinctnessResult,
    InMemoryDistinctnessLedger,
    PhysicalDistinctnessVerifier,
    secret_ref_key,
)
from .ports import ControlStore, ControlStoreConcurrencyError
from .records import TenantLifecycleState, TenantRecord
from .router_signal import NoOpRouterInvalidation, RouterInvalidationPort
from .verification import TenantDatabaseProbe

DEFAULT_TENANT_DB_PREFIX = "sp2_tenant_"
REASON_SCHEMA_MISMATCH = "schema_mismatch"
# PRD 07D-2e (D-2e-5): outcome reason for a verify() that YIELDS to a legitimate concurrent
# lifecycle winner (e.g. a suspend that committed between this gate's read and its write).
# An outcome-category string only — like REASON_SCHEMA_MISMATCH above, it is NOT audit/event
# vocabulary (nothing records it; the frozen events.py action set is unchanged).
REASON_CONCURRENT_LIFECYCLE_WINNER = "concurrent_lifecycle_winner"


class ProvisioningError(Exception):
    """Non-sensitive provisioning error (mapped to a defined denial at the edge)."""


def tenant_database_name(tenant_id: str, *, prefix: str = DEFAULT_TENANT_DB_PREFIX) -> str:
    """Deterministic default tenant-database target name.

    D-07: a naming convention serves only as an *overridable default*; the registry
    remains authoritative. Used as the intended provisioning target for DV-C3."""
    return f"{prefix}{tenant_id}"


@dataclass(frozen=True)
class ProvisionResult:
    target: str
    created: bool


class ProvisioningOperator(ABC):
    """Provisions a physically distinct tenant database (WP-1/WP-2; D-15)."""

    @abstractmethod
    def provision(self, tenant_id: str, *, target: str) -> ProvisionResult: ...
    @abstractmethod
    def deprovision(self, *, target: str) -> None: ...


class InMemoryProvisioningOperator(ProvisioningOperator):
    """Pure-stdlib provisioning operator double — records intent; creates nothing."""

    def __init__(self) -> None:
        self.provisioned: Set[str] = set()

    def provision(self, tenant_id: str, *, target: str) -> ProvisionResult:
        created = target not in self.provisioned
        self.provisioned.add(target)
        return ProvisionResult(target=target, created=created)

    def deprovision(self, *, target: str) -> None:
        self.provisioned.discard(target)


class TenantSchemaApplicationError(Exception):
    """Non-sensitive tenant-schema-application error (fail-closed; mapped to a non-routable outcome)."""


class TenantSchemaApplicator(ABC):
    """Applies a freshly provisioned tenant database's schema before verification (D15 Step 2b).

    The `ProvisioningOperator` only CREATEs the physically distinct database; this applies its
    schema — the existing provisioning + lineage DDL templates — so the readiness probe can observe
    `schema_version`. Concrete adapters that touch a real cluster live under `adapters/providers/**`
    and run in controlled non-production only. Fail-closed: any failure raises
    `TenantSchemaApplicationError` and commits NO partial schema (the concrete adapter applies all
    templates in a single atomic transaction). The per-tenant credential is resolved by reference
    in-memory (D-14) inside the adapter and is never returned or logged. This authors no DDL: it
    applies the already-reviewed templates as-is."""

    @abstractmethod
    def apply_schema(self, tenant_id: str, *, target: str, association_ref: SecretRef) -> None: ...


class ProvisioningVerificationService:
    """The D15 readiness gate: reachability + schema + Physical Distinctness -> Ready."""

    def __init__(
        self,
        store: ControlStore,
        audit: ControlPlaneAudit,
        probe: TenantDatabaseProbe,
        evidence_provider: DistinctnessEvidenceProvider,
        control_db_evidence: DistinctnessEvidence,
        *,
        supported_schema_versions: Iterable[str],
        verifier: Optional[PhysicalDistinctnessVerifier] = None,
        ledger: Optional[DistinctnessLedger] = None,
        router_invalidation: Optional[RouterInvalidationPort] = None,
        token_factory: Optional[Callable[[], str]] = None,
        sentinel_prefix: str = "dv_sentinel_",
    ) -> None:
        self._store = store
        self._audit = audit
        self._probe = probe
        self._evidence = evidence_provider
        self._control = control_db_evidence
        self._supported = frozenset(supported_schema_versions)
        self._verifier = verifier or PhysicalDistinctnessVerifier()
        self._ledger = ledger or InMemoryDistinctnessLedger()
        self._router = router_invalidation or NoOpRouterInvalidation()
        self._token = token_factory or (lambda: uuid.uuid4().hex)
        self._sentinel_prefix = sentinel_prefix

    # -- public operations -----------------------------------------------------
    def verify(self, tenant_id: str, *, actor: str, correlation_id: str) -> DistinctnessOutcome:
        """Run the full D15 verification gate. Returns the verification outcome; only
        VERIFIED reaches Ready. Every other outcome leaves routing disabled (fail-closed)."""
        rec = self._require(tenant_id)
        # PRD 07D-2b.2a (R1-1/C-1): QUARANTINED joins the refusal list — the gate is a composed,
        # publicly reachable entry point (and recover() calls it), so without its own refusal a
        # direct verify() would walk Quarantined → Verifying → potentially Ready, violating
        # IC-002's "NO transition from Quarantined toward Verifying or Ready, ever". Fail closed,
        # PRE-transition, zero side effects.
        if rec.lifecycle_state in (
            TenantLifecycleState.DECOMMISSIONED,
            TenantLifecycleState.SUSPENDED,
            TenantLifecycleState.QUARANTINED,
        ):
            raise ProvisioningError("illegal lifecycle transition")

        # PRD 07D-2e (D-2e-5): the VERIFYING entry write is the CAS arbiter against concurrent
        # lifecycle writers (R-2c-LWW). On a lost race: re-read and YIELD to a legitimate
        # winner (suspend/quarantine/decommission/fail) with the EXISTING non-routable
        # VERIFICATION_INCOMPLETE result and zero side effects (the started event rolled back
        # with the CAS — no started/terminal pairing violation); never auto-quarantine the
        # winner. If the record is still mid-flight (Verifying/Provisioning — e.g. a sibling
        # verifier), allow exactly ONE bounded retry at the fresh version; anything else
        # (e.g. a READY winner) fails closed.
        try:
            rec = self._transition(rec, TenantLifecycleState.VERIFYING, events.DISTINCTNESS_VERIFICATION_STARTED, actor, correlation_id)
        except ControlStoreConcurrencyError:
            fresh = self._require(tenant_id)
            if fresh.lifecycle_state in (
                TenantLifecycleState.SUSPENDED,
                TenantLifecycleState.QUARANTINED,
                TenantLifecycleState.DECOMMISSIONED,
                TenantLifecycleState.FAILED,
            ):
                return DistinctnessOutcome(DistinctnessResult.VERIFICATION_INCOMPLETE, REASON_CONCURRENT_LIFECYCLE_WINNER)
            if fresh.lifecycle_state in (TenantLifecycleState.VERIFYING, TenantLifecycleState.PROVISIONING):
                try:  # one bounded retry with the freshly observed version
                    rec = self._transition(
                        fresh, TenantLifecycleState.VERIFYING, events.DISTINCTNESS_VERIFICATION_STARTED, actor, correlation_id
                    )
                except ControlStoreConcurrencyError as exc:
                    raise ProvisioningError("concurrent lifecycle transition") from exc
            else:
                raise ProvisioningError("concurrent lifecycle transition") from None
        intended_target = tenant_database_name(tenant_id)

        # Registry / lifecycle validation: reachability + version-gated schema (D-17).
        probe = self._probe.probe(rec.database_association_ref)
        if not probe.reachable:
            return self._fail(
                rec,
                DistinctnessResult.VERIFICATION_INCOMPLETE,
                REASON_INCOMPLETE_EVIDENCE,
                events.VERIFICATION_INCOMPLETE,
                actor,
                correlation_id,
            )
        if probe.observed_schema_version not in self._supported or probe.observed_schema_version != rec.expected_schema_version:
            return self._fail(
                rec,
                DistinctnessResult.VERIFICATION_FAILED,
                REASON_SCHEMA_MISMATCH,
                events.DISTINCTNESS_VERIFICATION_FAILED,
                actor,
                correlation_id,
            )

        # Registry-level secret-reference guard (DV-C7A, secret-reference vector): a tenant
        # whose association resolves through the Control DB's secret reference would reach the
        # Control DB. Catch it before connecting.
        if secret_ref_key(rec.database_association_ref) == self._control.secret_ref_key:
            return self._fail(
                rec,
                DistinctnessResult.ISOLATION_ANOMALY,
                REASON_CONTROL_DB_COLLISION,
                events.DISTINCTNESS_VERIFICATION_FAILED,
                actor,
                correlation_id,
                anomaly=True,
            )

        # Physical Distinctness Verification (§9): gather evidence + decide.
        token = self._token()
        namespace = f"{self._sentinel_prefix}{tenant_id}"
        evidence = self._evidence.gather(rec.database_association_ref, sentinel_token=token, sentinel_namespace=namespace)
        outcome = self._verifier.verify(
            tenant_id,
            evidence,
            intended_target=intended_target,
            control_db=self._control,
            inventory=self._ledger.evidence_excluding(tenant_id),
        )

        if outcome.result is DistinctnessResult.VERIFIED and evidence is not None:
            # PRD 07D-2c: the recording write is the atomic arbiter of the §6.1 fingerprint
            # rule. A DistinctnessCollisionError here is a LOST concurrent race — another
            # tenant's evidence landed between this gate's inventory read (the CHECK feeding
            # the verifier above) and this ACT, so the verifier could not see it. Route it to
            # the EXISTING IC-010 §P / IC-002 anomaly path (auto-quarantine via _fail): the
            # loser never reaches Ready/RoutingEnabled, the winner is unaffected, and no new
            # event names are introduced.
            try:
                self._ledger.record_evidence(tenant_id, evidence)
            except DistinctnessCollisionError:
                return self._fail(
                    rec,
                    DistinctnessResult.ISOLATION_ANOMALY,
                    REASON_TENANT_COLLISION,
                    events.DISTINCTNESS_VERIFICATION_FAILED,
                    actor,
                    correlation_id,
                    anomaly=True,
                )
            # PRD 07D-2e: a mid-gate CAS conflict on the READY commit fails closed (routing is
            # never enabled over a concurrent lifecycle write). Under the 07D-2d READY-only
            # suspend a legitimate suspend cannot land on VERIFYING, so a conflict here is a
            # sibling writer (e.g. a concurrent re-verify/reassociate) — an error, not a yield.
            try:
                self._transition(rec, TenantLifecycleState.READY, events.DISTINCTNESS_VERIFICATION_PASSED, actor, correlation_id)
            except ControlStoreConcurrencyError as exc:
                raise ProvisioningError("concurrent lifecycle transition") from exc
            self._event(tenant_id, events.ROUTING_ENABLED, actor, correlation_id)
            return outcome

        # Fail-closed: drop any stale evidence and never reach Ready.
        self._ledger.remove(tenant_id)
        if outcome.is_anomaly:
            self._fail(rec, outcome.result, outcome.reason, events.DISTINCTNESS_VERIFICATION_FAILED, actor, correlation_id, anomaly=True)
        elif outcome.result is DistinctnessResult.VERIFICATION_INCOMPLETE:
            self._fail(rec, outcome.result, outcome.reason, events.VERIFICATION_INCOMPLETE, actor, correlation_id)
        else:
            self._fail(rec, outcome.result, outcome.reason, events.DISTINCTNESS_VERIFICATION_FAILED, actor, correlation_id)
        return outcome

    def reassociate(self, tenant_id: str, *, new_association_ref: SecretRef, actor: str, correlation_id: str) -> DistinctnessOutcome:
        """Re-point a tenant at a restored/relocated DB: update association, invalidate the
        router cache, and re-run the full verification gate before routing can be restored
        (§11.2, §22; WP-11). Routing is withheld until re-verification passes (fail-closed)."""
        rec = self._require(tenant_id)
        # PRD 07D-2b.2a (IC-002 Re-association guard / AT-07D1-7): validate the CURRENT lifecycle
        # state BEFORE any effect. Without this pre-check the association overwrite below would
        # move the tenant to Verifying before verify()'s own refusal runs — an escape hatch from
        # Quarantined toward Ready. Refused for Quarantined and Decommissioned, fail closed,
        # pre-effect (no state overwrite, no audit record, no cache invalidation).
        if rec.lifecycle_state in (TenantLifecycleState.QUARANTINED, TenantLifecycleState.DECOMMISSIONED):
            raise ProvisioningError("illegal lifecycle transition")
        updated = replace(
            rec,
            database_association_ref=new_association_ref,
            lifecycle_state=TenantLifecycleState.VERIFYING,
            updated_at=now_iso(),
        )
        # PRD 07D-2e (D-2e-4): CAS-then-audit — the durable store commits the association
        # overwrite and the required audit record in ONE transaction (conflict → no audit, no
        # overwrite; audit failure → state rolled back). A lost race fails closed: the caller
        # re-reads and re-issues against the winner's state.
        try:
            self._store.compare_and_swap_tenant(updated, expected_version=rec.version)
        except ControlStoreConcurrencyError as exc:
            raise ProvisioningError("concurrent lifecycle transition") from exc
        self._audit.record(
            actor=actor,
            tenant_id=tenant_id,
            action=events.DATABASE_ASSOCIATED,
            from_state=rec.lifecycle_state.value,
            to_state=TenantLifecycleState.VERIFYING.value,
            correlation_id=correlation_id,
        )
        # PRD 07D-2b.2a (AT-07D1-7): the NEW association reference is registered here — emit the
        # same reference-only marker onboarding emits for the initial association (IC-002 §69).
        self._event(tenant_id, events.SECRET_REFERENCE_REGISTERED, actor, correlation_id)
        self._event(tenant_id, events.REGISTRY_MAPPING_CHANGED, actor, correlation_id)
        self._invalidate(tenant_id, actor, correlation_id)
        return self.verify(tenant_id, actor=actor, correlation_id=correlation_id)

    def disable_routing(self, tenant_id: str, *, actor: str, correlation_id: str) -> None:
        """Provisioning-side companion for suspension / decommissioning (§7.3, §16, §17):
        drop the tenant's distinctness evidence, record ROUTING_DISABLED, and invalidate any
        cached routing decision. The IC-002 lifecycle state change itself remains with the
        Phase-2 registry; this is the routing/eligibility side only."""
        self._ledger.remove(tenant_id)
        self._event(tenant_id, events.ROUTING_DISABLED, actor, correlation_id)
        self._invalidate(tenant_id, actor, correlation_id)

    # -- internals -------------------------------------------------------------
    def _require(self, tenant_id: str) -> TenantRecord:
        rec = self._store.get_tenant(tenant_id)
        if rec is None:
            raise ProvisioningError("unknown tenant")
        return rec

    def _transition(
        self,
        rec: TenantRecord,
        to_state: TenantLifecycleState,
        action: str,
        actor: str,
        correlation_id: str,
    ) -> TenantRecord:
        updated = replace(rec, lifecycle_state=to_state, updated_at=now_iso())
        # PRD 07D-2e (D-2e-4): version-predicated CAS first (uncommitted in the durable store),
        # required audit append second — the store commits BOTH in one Control-DB transaction.
        # A lost race raises ControlStoreConcurrencyError with NO audit written (no orphan);
        # a failed required audit write rolls the state change back (the B7B-D5 fail-closed
        # guarantee, now transactional). The typed conflict propagates to the caller's policy
        # (verify()'s yield/retry at entry; fail-closed conversion elsewhere).
        persisted = self._store.compare_and_swap_tenant(updated, expected_version=rec.version)
        self._audit.record(
            actor=actor,
            tenant_id=rec.tenant_id,
            action=action,
            from_state=rec.lifecycle_state.value,
            to_state=to_state.value,
            correlation_id=correlation_id,
        )
        return persisted

    def _event(self, tenant_id: str, action: str, actor: str, correlation_id: str) -> None:
        """Non-transition operational-audit event (reference-only; no state change)."""
        self._audit.record(
            actor=actor,
            tenant_id=tenant_id,
            action=action,
            from_state=None,
            to_state=None,
            correlation_id=correlation_id,
        )

    def _invalidate(self, tenant_id: str, actor: str, correlation_id: str) -> None:
        self._router.invalidate_tenant(tenant_id, correlation_id=correlation_id)
        self._event(tenant_id, events.ROUTER_CACHE_INVALIDATED, actor, correlation_id)

    def _fail(
        self,
        rec: TenantRecord,
        result: DistinctnessResult,
        reason: str,
        event_action: str,
        actor: str,
        correlation_id: str,
        *,
        anomaly: bool = False,
    ) -> DistinctnessOutcome:
        self._ledger.remove(rec.tenant_id)
        # PRD 07D-2e: a CAS conflict on a terminal transition fails closed as a ProvisioningError
        # (a legitimate suspend cannot land on VERIFYING under 07D-2d B2, so a conflict here is a
        # sibling writer; the caller re-issues against the winner's state — never a lost write).
        try:
            if anomaly:
                # PRD 07D-2b.2a (IC-002 Failure Behavior): isolation-class anomalies MUST quarantine
                # automatically at classification time (the automatic `Verifying → Quarantined` edge),
                # so a tenant resting in Failed is by construction non-anomalous. The transition keeps
                # the verification attempt's terminal action (started/terminal pairing unchanged);
                # TenantQuarantined marks the hold and IsolationAnomaly the incident (§23 S7/S8) —
                # evidence-preserving: the record and any physical database are retained unmodified.
                self._transition(rec, TenantLifecycleState.QUARANTINED, event_action, actor, correlation_id)
                self._event(rec.tenant_id, events.TENANT_QUARANTINED, actor, correlation_id)
                self._event(rec.tenant_id, events.ISOLATION_ANOMALY, actor, correlation_id)
            else:
                self._transition(rec, TenantLifecycleState.FAILED, event_action, actor, correlation_id)
        except ControlStoreConcurrencyError as exc:
            raise ProvisioningError("concurrent lifecycle transition") from exc
        return DistinctnessOutcome(result, reason)
