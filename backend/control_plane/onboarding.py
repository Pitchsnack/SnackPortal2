"""Tenant-onboarding orchestration — D-15 orchestration wiring (sub-phase B-1).

Composes the already-merged D-15 components into one controlled-non-production onboarding
flow — Register → Provision → Associate → Verify → Ready/Failed — WITHOUT changing any of
their behavior. It owns no state transition of its own: the ``TenantRegistry`` sets
Registered/Provisioning (IC-002, Phase 2) and the ``ProvisioningVerificationService`` gate
owns Verifying → Ready/Failed (the sole readiness authority — IC-005/D-07: the Database
Router remains the sole database selector). The orchestrator only sequences these
operations and emits the existing reference-only provisioning audit events
(``control_plane.events``; D15-ARCH-SPEC-01 §14.3).

Guarantees:
* Fail-closed — any step that fails leaves the tenant not-Ready (only Ready is routable).
* Idempotent — onboarding a tenant that is not in Registered does not re-provision/re-verify.
* No new lifecycle state, no new audit event, no IC-010 §P change (additive composition).
"""

from __future__ import annotations

from shared.secrets import SecretRef

from . import events
from .audit import ControlPlaneAudit
from .distinctness import DistinctnessOutcome, DistinctnessResult
from .provisioning import (
    ProvisioningOperator,
    ProvisioningVerificationService,
    tenant_database_name,
)
from .records import TenantLifecycleState
from .registry import TenantRegistry


class OnboardingError(Exception):
    """Non-sensitive onboarding error (mapped to a defined denial at the edge)."""


class OnboardingOrchestrator:
    """Sequences Register → Provision → Associate → Verify for one tenant (non-prod)."""

    def __init__(
        self,
        registry: TenantRegistry,
        operator: ProvisioningOperator,
        provisioning: ProvisioningVerificationService,
        audit: ControlPlaneAudit,
    ) -> None:
        self._registry = registry
        self._operator = operator
        self._provisioning = provisioning
        self._audit = audit

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
        Ready. If the tenant already exists and is not in ``Registered``, onboarding is a
        no-op that returns a non-routable outcome (idempotency guard) — it does NOT
        re-provision or re-verify.
        """
        # Association reference (D-14): in controlled non-production the secret-store
        # reference is the provisioned target name; the registry stays authoritative (D-07).
        target = tenant_database_name(tenant_id)
        association_ref = SecretRef(store_ref=target, version="1")

        # Idempotency guard (SAFETY-A3): never re-provision/re-verify an already-progressed tenant.
        existing = self._registry.get_tenant_status(tenant_id)
        if existing is not None and existing.lifecycle_state is not TenantLifecycleState.REGISTERED:
            already_ready = existing.lifecycle_state is TenantLifecycleState.READY
            return DistinctnessOutcome(
                DistinctnessResult.VERIFIED if already_ready else DistinctnessResult.VERIFICATION_INCOMPLETE,
                "already_onboarded",
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

        # 2) Provisioning (registry owns Registered → Provisioning).
        self._registry.mark_provisioning(tenant_id, actor=actor, correlation_id=correlation_id)
        self._emit(tenant_id, events.DATABASE_PROVISION_REQUESTED, actor, correlation_id)
        try:
            self._operator.provision(tenant_id, target=target)
        except Exception:
            # Fail-closed: provisioning failed → leave not-Ready (not routable); do not verify.
            self._emit(tenant_id, events.DATABASE_PROVISION_FAILED, actor, correlation_id)
            return DistinctnessOutcome(DistinctnessResult.VERIFICATION_INCOMPLETE, "provision_failed")
        self._emit(tenant_id, events.DATABASE_PROVISION_SUCCEEDED, actor, correlation_id)

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
        """Reference-only operational-audit event (existing ``events`` vocabulary; no new action)."""
        self._audit.record(
            actor=actor,
            tenant_id=tenant_id,
            action=action,
            from_state=None,
            to_state=None,
            correlation_id=correlation_id,
        )
