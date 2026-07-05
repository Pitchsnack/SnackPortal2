"""Tenant-onboarding orchestration — D-15 orchestration wiring (sub-phase B-1).

Composes the already-merged D-15 components into one controlled-non-production onboarding
flow — Register → Provision → Associate → Verify → Ready/Failed — WITHOUT changing any of
their behavior. It owns no state transition of its own: the ``TenantRegistry`` sets
Registered/Provisioning (IC-002, Phase 2) and the ``ProvisioningVerificationService`` gate
owns Verifying → Ready/Failed (the sole readiness authority — IC-005/D-07: the Database
Router remains the sole database selector). The orchestrator only sequences these
operations and emits the existing reference-only provisioning audit events
(``control_plane.events``; D15-ARCH-SPEC-01 §14.3).

PRD 07D-2b.2a (IC-002 Recovery & Compensation) replaces the blanket non-Registered terminal
fence with state-specific dispatch: automatic resume is permitted ONLY from ``Provisioning``
(re-driving the proven-idempotent provision → apply → verify tail), ``Failed`` requires the
explicit, audited ``recover()`` operation (which re-classifies from the audit trail first),
and ``Quarantined`` / ``Suspended`` / ``Decommissioned`` remain terminal (fail closed).

Guarantees:
* Fail-closed — any step that fails leaves the tenant not-Ready (only Ready is routable).
* Idempotent — re-onboarding a Ready tenant is a no-op; a resumed run converges without
  duplicating effects (provision is existence-checked; schema application is atomic +
  idempotent).
* No recovery path ever sets Ready directly — recovery re-enters ``Verifying`` and readiness
  is decided solely by the verification gate (the sole-readiness-writer rule).
"""

from __future__ import annotations

from typing import Optional

from shared.secrets import SecretRef

from . import events
from .audit import ControlPlaneAudit
from .distinctness import DistinctnessOutcome, DistinctnessResult
from .provisioning import (
    ProvisioningOperator,
    ProvisioningVerificationService,
    TenantSchemaApplicator,
    tenant_database_name,
)
from .records import TenantLifecycleState, TenantRecord
from .registry import TenantRegistry

# PRD 07D-1 (decision D-A): the CANONICAL tenant DSN secret-reference convention. Onboarding mints
# `tenant/<tenant_id>/dsn`; the reference is resolvable by BOTH the control-plane tenant-DSN
# provider (adapters/providers/env_tenant_dsn_secret_store.py) and — by the same REPLICATED, never
# imported, env/file convention — the database-router-side EnvTenantSecretStore, so one
# materialized secret serves both sides (D3). References only, never a DSN value (D-14).
TENANT_DSN_REF_PREFIX = "tenant/"
TENANT_DSN_REF_SUFFIX = "/dsn"


def tenant_dsn_ref(tenant_id: str) -> str:
    """The canonical tenant DSN secret reference (PRD 07D-1 D-A): ``tenant/<tenant_id>/dsn``."""
    return f"{TENANT_DSN_REF_PREFIX}{tenant_id}{TENANT_DSN_REF_SUFFIX}"


def tenant_id_from_dsn_ref(store_ref: str) -> Optional[str]:
    """Inverse of ``tenant_dsn_ref``: the tenant_id if ``store_ref`` is canonical-shaped, else None.

    Non-canonical references (e.g. caller-supplied raw refs passed to ``reassociate``) return None
    so callers can fall back to treating the reference as an opaque store location."""
    if store_ref.startswith(TENANT_DSN_REF_PREFIX) and store_ref.endswith(TENANT_DSN_REF_SUFFIX):
        inner = store_ref[len(TENANT_DSN_REF_PREFIX) : -len(TENANT_DSN_REF_SUFFIX)]
        if inner and "/" not in inner:
            return inner
    return None


class OnboardingError(Exception):
    """Non-sensitive onboarding error (mapped to a defined denial at the edge)."""


# PRD 07D-2b.2a onboarding-fence dispatch (IC-002 Retry-resume eligibility): the terminal,
# non-routable outcome reasons per resting state. Non-sensitive category strings only. States
# absent here (e.g. an in-flight Verifying) keep the pre-2b.2a "already_onboarded" shape.
_TERMINAL_ONBOARD_REASONS = {
    TenantLifecycleState.FAILED: "recover_required",  # explicit recover() is the governed exit
    TenantLifecycleState.QUARANTINED: "quarantined",  # fail closed; never resumes
    TenantLifecycleState.SUSPENDED: "suspended",  # reactivate path only
    TenantLifecycleState.DECOMMISSIONED: "decommissioned",
}


class OnboardingOrchestrator:
    """Sequences Register → Provision → Associate → Verify for one tenant (non-prod).

    PRD 07D-2b.2a adds the governed recovery surface: automatic resume from ``Provisioning``
    (fence dispatch) and the explicit ``recover()`` operation for ``Failed`` tenants."""

    def __init__(
        self,
        registry: TenantRegistry,
        operator: ProvisioningOperator,
        provisioning: ProvisioningVerificationService,
        audit: ControlPlaneAudit,
        schema_applicator: TenantSchemaApplicator,
    ) -> None:
        self._registry = registry
        self._operator = operator
        self._provisioning = provisioning
        self._audit = audit
        self._schema_applicator = schema_applicator

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
        """Drive a tenant from registration to routing-eligibility (or fail closed).

        Returns the gate's ``DistinctnessOutcome``; only ``VERIFIED`` leaves the tenant
        Ready. The onboarding fence dispatches on the tenant's CURRENT state (PRD 07D-2b.2a;
        IC-002 Retry-resume eligibility): ``Registered``/absent → fresh run; ``Provisioning``
        → automatic resume (the only auto-resume-eligible state); ``Ready`` → idempotent
        no-op; ``Failed`` → terminal here (explicit ``recover()`` required); ``Quarantined``
        / ``Suspended`` / ``Decommissioned`` → terminal, fail closed, zero side effects.
        """
        # Association reference (D-14; PRD 07D-1 D-A): the CANONICAL tenant DSN secret reference
        # `tenant/<tenant_id>/dsn` — a secret-store LOCATION resolvable by the control-plane
        # tenant-DSN provider and (same replicated convention) the database-router side. The
        # provisioned target name is carried separately below; the registry stays authoritative
        # (D-07). The old raw-target-name ref style (`sp2_tenant_<id>`) is no longer minted.
        target = tenant_database_name(tenant_id)
        association_ref = SecretRef(store_ref=tenant_dsn_ref(tenant_id), version="1")

        # Onboarding fence (PRD 07D-2b.2a): state-specific dispatch replaces the blanket
        # non-Registered terminal (SAFETY-A3 idempotency is preserved — nothing here ever
        # re-provisions/re-verifies a Ready tenant or resumes a terminal state).
        existing = self._registry.get_tenant_status(tenant_id)
        if existing is not None and existing.lifecycle_state is not TenantLifecycleState.REGISTERED:
            state = existing.lifecycle_state
            if state is TenantLifecycleState.READY:
                return DistinctnessOutcome(DistinctnessResult.VERIFIED, "already_onboarded")
            if state is TenantLifecycleState.PROVISIONING:
                # Automatic resume — permitted ONLY from Provisioning (IC-002): a resumption
                # within the first transition chain, along proven-idempotent paths.
                return self._resume(existing, target, actor, correlation_id)
            # Failed (explicit recover() required) / Quarantined (never resumes) / Suspended
            # (reactivate path only) / Decommissioned / in-flight Verifying: terminal via
            # onboard() — non-routable outcome, zero side effects.
            return DistinctnessOutcome(
                DistinctnessResult.VERIFICATION_INCOMPLETE,
                _TERMINAL_ONBOARD_REASONS.get(state, "already_onboarded"),
            )

        # 1) Register (Phase-2 registry; idempotent by tenant_id) → Registered.
        self._registry.register_tenant(
            tenant_id=tenant_id,
            organization_ref=organization_ref,
            expected_schema_version=expected_schema_version,
            database_association_ref=association_ref,
            federation_config_ref=federation_config_ref,
            actor=actor,
            correlation_id=correlation_id,
        )

        # 2) Provisioning (registry owns Registered → Provisioning), then the shared tail.
        self._registry.mark_provisioning(tenant_id, actor=actor, correlation_id=correlation_id)
        return self._provision_apply_verify(tenant_id, target, association_ref, actor, correlation_id)

    def recover(self, tenant_id: str, *, actor: str, correlation_id: str) -> DistinctnessOutcome:
        """Explicit RecoverTenant (IC-002 Recovery & Compensation) — ``Failed`` tenants only.

        Re-classifies the failure from the audit trail BEFORE re-entering ``Verifying``
        (defence in depth for Failed records predating the automatic-quarantine rule):
        isolation-class history routes to ``Quarantined`` — never resumed. Otherwise the
        tenant re-enters ``Verifying`` via the gate, which alone decides readiness — this
        operation never sets Ready. Ineligible states (anything but ``Failed``) are refused
        fail-closed, pre-effect, with zero side effects.
        """
        record = self._registry.get_tenant_status(tenant_id)
        if record is None:
            raise OnboardingError("unknown tenant")
        if record.lifecycle_state is not TenantLifecycleState.FAILED:
            # Fail closed, PRE-effect: Quarantined/Suspended/Decommissioned/Ready/Registered/
            # Provisioning/Verifying are not recover-eligible (IC-002 Retry-resume eligibility).
            raise OnboardingError("illegal lifecycle transition")
        self._emit(tenant_id, events.ONBOARDING_RECOVERY_STARTED, actor, correlation_id)
        # Re-classification (IC-002): isolation-class history quarantines instead of resuming.
        anomaly_history = any(r.tenant_id == tenant_id and r.action == events.ISOLATION_ANOMALY for r in self._audit.events())
        if anomaly_history:
            self._registry.quarantine_tenant(tenant_id, actor=actor, correlation_id=correlation_id)
            self._emit(tenant_id, events.TENANT_QUARANTINED, actor, correlation_id)
            self._emit(tenant_id, events.ONBOARDING_RECOVERY_FAILED, actor, correlation_id)
            return DistinctnessOutcome(DistinctnessResult.ISOLATION_ANOMALY, "anomaly_history")
        try:
            outcome = self._provisioning.verify(tenant_id, actor=actor, correlation_id=correlation_id)
        except Exception:
            # Keep the IC-002 start/terminal pairing even when the gate raises (fail closed).
            self._emit(tenant_id, events.ONBOARDING_RECOVERY_FAILED, actor, correlation_id)
            raise
        self._emit(
            tenant_id,
            events.ONBOARDING_RECOVERY_COMPLETED if outcome.result is DistinctnessResult.VERIFIED else events.ONBOARDING_RECOVERY_FAILED,
            actor,
            correlation_id,
        )
        return outcome

    def _resume(self, record: TenantRecord, target: str, actor: str, correlation_id: str) -> DistinctnessOutcome:
        """Automatic resume from ``Provisioning`` (IC-002 Retry-resume eligibility).

        Re-drives the proven-idempotent onboarding tail (provision is existence-checked;
        schema application is atomic + idempotent) using the REGISTRY-AUTHORITATIVE stored
        association reference (D-07), wrapped in the OnboardingRecovery start/terminal pair
        so a resumed run is attributable in the trail (a second DatabaseProvisionRequested
        is otherwise unexplained). Readiness is still decided solely by the gate."""
        tenant_id = record.tenant_id
        self._emit(tenant_id, events.ONBOARDING_RECOVERY_STARTED, actor, correlation_id)
        try:
            outcome = self._provision_apply_verify(tenant_id, target, record.database_association_ref, actor, correlation_id)
        except Exception:
            # Keep the IC-002 start/terminal pairing even when the gate raises (fail closed).
            self._emit(tenant_id, events.ONBOARDING_RECOVERY_FAILED, actor, correlation_id)
            raise
        self._emit(
            tenant_id,
            events.ONBOARDING_RECOVERY_COMPLETED if outcome.result is DistinctnessResult.VERIFIED else events.ONBOARDING_RECOVERY_FAILED,
            actor,
            correlation_id,
        )
        return outcome

    def _provision_apply_verify(
        self,
        tenant_id: str,
        target: str,
        association_ref: SecretRef,
        actor: str,
        correlation_id: str,
    ) -> DistinctnessOutcome:
        """The shared onboarding tail: Provision → Apply schema → Associate → Verify.

        Used by the fresh path (after Register → Provisioning) and by the automatic resume
        from ``Provisioning`` (every step is idempotent/existence-checked; fail-closed)."""
        self._emit(tenant_id, events.DATABASE_PROVISION_REQUESTED, actor, correlation_id)
        try:
            self._operator.provision(tenant_id, target=target)
        except Exception:
            # Fail-closed: provisioning failed → leave not-Ready (not routable); do not verify.
            self._emit(tenant_id, events.DATABASE_PROVISION_FAILED, actor, correlation_id)
            return DistinctnessOutcome(DistinctnessResult.VERIFICATION_INCOMPLETE, "provision_failed")
        self._emit(tenant_id, events.DATABASE_PROVISION_SUCCEEDED, actor, correlation_id)

        # 2b) Apply tenant schema (D15-ARCH-SPEC-01 §8 Step 2b; PRD 07B). A freshly provisioned
        # database has no schema yet; apply the existing provisioning + lineage DDL (idempotent,
        # single atomic transaction, fail-closed) BEFORE verify — whose readiness probe reads
        # schema_version. Fail-closed: a failed apply leaves the tenant not-Ready (never routable)
        # and never reaches the gate (mirrors the provision-failure branch above).
        self._emit(tenant_id, events.TENANT_SCHEMA_APPLICATION_STARTED, actor, correlation_id)
        try:
            self._schema_applicator.apply_schema(tenant_id, target=target, association_ref=association_ref)
        except Exception:
            self._emit(tenant_id, events.TENANT_SCHEMA_APPLICATION_FAILED, actor, correlation_id)
            return DistinctnessOutcome(DistinctnessResult.VERIFICATION_INCOMPLETE, "schema_application_failed")
        self._emit(tenant_id, events.TENANT_SCHEMA_APPLICATION_SUCCEEDED, actor, correlation_id)

        # 3) Associate (the association reference was recorded at registration — IC-002 §69).
        self._emit(tenant_id, events.SECRET_REFERENCE_REGISTERED, actor, correlation_id)
        self._emit(tenant_id, events.DATABASE_ASSOCIATED, actor, correlation_id)

        # 4) Verify (the gate owns Verifying → Ready/Failed; the sole readiness authority).
        return self._provisioning.verify(tenant_id, actor=actor, correlation_id=correlation_id)

    def reassociate(
        self,
        tenant_id: str,
        *,
        new_association_ref: SecretRef,
        actor: str,
        correlation_id: str,
    ) -> DistinctnessOutcome:
        """Re-point a tenant at a restored/relocated DB and re-verify (gate-owned)."""
        return self._provisioning.reassociate(
            tenant_id,
            new_association_ref=new_association_ref,
            actor=actor,
            correlation_id=correlation_id,
        )

    def disable_routing(self, tenant_id: str, *, actor: str, correlation_id: str) -> None:
        """Routing-side companion for suspension / decommissioning (gate-owned)."""
        self._provisioning.disable_routing(tenant_id, actor=actor, correlation_id=correlation_id)

    def _emit(self, tenant_id: str, action: str, actor: str, correlation_id: str) -> None:
        """Reference-only operational-audit event (frozen ``events`` vocabulary — including the
        PRD 07D-2b.2a recovery actions guarded by EXPECTED_EVENT_ACTIONS)."""
        self._audit.record(
            actor=actor,
            tenant_id=tenant_id,
            action=action,
            from_state=None,
            to_state=None,
            correlation_id=correlation_id,
        )
