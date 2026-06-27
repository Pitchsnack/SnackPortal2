"""Tenant Registry (IC-002 + IC-001/D-07/D-11).

Phase 2 implements RegisterTenant, GetTenantStatus, SuspendTenant, DecommissionTenant
and records Provisioning intent. It MUST NOT set Verifying/Ready/Failed (those require
tenant-DB connectivity + schema verification — Build Phase 4). **No tenant may become
Ready during Phase 2.** Verify/Activate/Reactivate/ReassociateDatabase are *defined but
deferred* to Build Phase 4. Stores references only — never credentials (D-14).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from shared.secrets import SecretRef

from ._util import now_iso
from .audit import ControlPlaneAudit
from .ports import ControlStore
from .records import TenantLifecycleState, TenantRecord

# States that require tenant-database verification — never set in Build Phase 2.
PHASE_4_STATES = (
    TenantLifecycleState.VERIFYING,
    TenantLifecycleState.READY,
    TenantLifecycleState.FAILED,
)


class RegistryError(Exception):
    """Non-sensitive registry error (mapped to a defined denial at the edge)."""


class PhaseFourDeferred(NotImplementedError):
    """Operation defined now but introduced in Build Phase 4 (needs tenant-DB access)."""


class TenantRegistry:
    def __init__(self, store: ControlStore, audit: ControlPlaneAudit) -> None:
        self._store = store
        self._audit = audit

    # ---------------- Phase 2 implemented operations ----------------
    def register_tenant(
        self,
        *,
        tenant_id: str,
        organization_ref: str,
        expected_schema_version: str,
        database_association_ref: SecretRef,
        federation_config_ref: str,
        actor: str,
        correlation_id: str,
    ) -> TenantRecord:
        existing = self._store.get_tenant(tenant_id)
        if existing is not None:
            return existing  # idempotent by tenant_id (IC-002)
        ts = now_iso()
        record = TenantRecord(
            tenant_id=tenant_id,
            organization_ref=organization_ref,
            lifecycle_state=TenantLifecycleState.REGISTERED,
            expected_schema_version=expected_schema_version,
            database_association_ref=database_association_ref,
            federation_config_ref=federation_config_ref,
            created_at=ts,
            updated_at=ts,
        )
        # Fail-closed ordering (PRD 06 B-7B / B7B-D5): write the required audit record BEFORE the
        # irreversible state commit, so a failed durable audit write rejects the transition with
        # NO committed partial state. The in-memory default is unaffected (its writes never fail).
        self._audit.record(
            actor=actor,
            tenant_id=tenant_id,
            action="RegisterTenant",
            from_state=None,
            to_state=TenantLifecycleState.REGISTERED.value,
            correlation_id=correlation_id,
        )
        self._store.put_tenant(record)
        return record

    def get_tenant_status(self, tenant_id: str) -> Optional[TenantRecord]:
        return self._store.get_tenant(tenant_id)

    def mark_provisioning(self, tenant_id: str, *, actor: str, correlation_id: str) -> TenantRecord:
        return self._transition(
            tenant_id,
            TenantLifecycleState.PROVISIONING,
            {TenantLifecycleState.REGISTERED},
            "MarkProvisioning",
            actor,
            correlation_id,
        )

    def suspend_tenant(self, tenant_id: str, *, actor: str, correlation_id: str) -> TenantRecord:
        return self._transition(
            tenant_id,
            TenantLifecycleState.SUSPENDED,
            {TenantLifecycleState.REGISTERED, TenantLifecycleState.PROVISIONING},
            "SuspendTenant",
            actor,
            correlation_id,
        )

    def decommission_tenant(self, tenant_id: str, *, actor: str, correlation_id: str) -> TenantRecord:
        return self._transition(
            tenant_id,
            TenantLifecycleState.DECOMMISSIONED,
            {TenantLifecycleState.REGISTERED, TenantLifecycleState.PROVISIONING, TenantLifecycleState.SUSPENDED},
            "DecommissionTenant",
            actor,
            correlation_id,
        )

    # ---------------- Phase 4 deferred operations (defined, not implemented) ----------------
    def verify_tenant(self, *args: object, **kwargs: object) -> None:
        raise PhaseFourDeferred("VerifyTenant requires tenant-DB connectivity (Build Phase 4).")

    def activate_tenant(self, *args: object, **kwargs: object) -> None:
        raise PhaseFourDeferred("ActivateTenant requires verification (Build Phase 4).")

    def reactivate_tenant(self, *args: object, **kwargs: object) -> None:
        raise PhaseFourDeferred("ReactivateTenant requires re-verification (Build Phase 4).")

    def reassociate_database(self, *args: object, **kwargs: object) -> None:
        raise PhaseFourDeferred("ReassociateDatabase requires DB Router + re-verify (Build Phase 4).")

    # ---------------- internal ----------------
    def _transition(
        self,
        tenant_id: str,
        to_state: TenantLifecycleState,
        allowed_from: set[TenantLifecycleState],
        action: str,
        actor: str,
        correlation_id: str,
    ) -> TenantRecord:
        # Critical rule: Phase 2 never sets Verifying/Ready/Failed.
        if to_state in PHASE_4_STATES:
            raise PhaseFourDeferred(f"{to_state.value} is set only in Build Phase 4.")
        record = self._store.get_tenant(tenant_id)
        if record is None:
            raise RegistryError("unknown tenant")
        if record.lifecycle_state not in allowed_from:
            raise RegistryError("illegal lifecycle transition")
        updated = replace(record, lifecycle_state=to_state, updated_at=now_iso())
        # Fail-closed ordering (B7B-D5): required audit write precedes the irreversible put_tenant.
        self._audit.record(
            actor=actor,
            tenant_id=tenant_id,
            action=action,
            from_state=record.lifecycle_state.value,
            to_state=to_state.value,
            correlation_id=correlation_id,
        )
        self._store.put_tenant(updated)
        return updated
