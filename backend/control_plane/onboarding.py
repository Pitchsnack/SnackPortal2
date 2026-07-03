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
from .records import TenantLifecycleState
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


class OnboardingOrchestrator:
    """Sequences Register → Provision → Associate → Verify for one tenant (non-prod)."""

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
        Ready. If the tenant already exists and is not in ``Registered``, onboarding is a
        no-op that returns a non-routable outcome (idempotency guard) — it does NOT
        re-provision or re-verify.
        """
        # Association reference (D-14; PRD 07D-1 D-A): the CANONICAL tenant DSN secret reference
        # `tenant/<tenant_id>/dsn` — a secret-store LOCATION resolvable by the control-plane
        # tenant-DSN provider and (same replicated convention) the database-router side. The
        # provisioned target name is carried separately below; the registry stays authoritative
        # (D-07). The old raw-target-name ref style (`sp2_tenant_<id>`) is no longer minted.
        target = tenant_database_name(tenant_id)
        association_ref = SecretRef(store_ref=tenant_dsn_ref(tenant_id), version="1")

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
        """Reference-only operational-audit event (existing ``events`` vocabulary; no new action)."""
        self._audit.record(
            actor=actor,
            tenant_id=tenant_id,
            action=action,
            from_state=None,
            to_state=None,
            correlation_id=correlation_id,
        )
