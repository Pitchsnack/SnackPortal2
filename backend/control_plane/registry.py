"""Tenant Registry (IC-002 + IC-001/D-07/D-11).

Phase 2 implements RegisterTenant, GetTenantStatus, SuspendTenant, DecommissionTenant
and records Provisioning intent. It MUST NOT set Verifying/Ready/Failed (those require
tenant-DB connectivity + schema verification — Build Phase 4). **No tenant may become
Ready during Phase 2.** Verify/Activate/Reactivate/ReassociateDatabase are *defined but
deferred* to Build Phase 4. Stores references only — never credentials (D-14).

PRD 07D-2b.2a (IC-002 Recovery & Compensation) adds QuarantineTenant — the explicit,
audited transition into the evidence-preserving isolation hold (`Quarantined` is not a
verification state, so the Phase-4 fence does not apply) — and catches the SuspendTenant /
DecommissionTenant allowed-from sets up to the amended IC-002 transition table.
"""

from __future__ import annotations

import re
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

# PRD 07D-2a tenant-id admission (AT-07D1-11). LOWERCASE-only so two tenant ids can never alias
# through the case-flattening tenant secret env-key convention (`tenant/A_b/dsn` and
# `tenant/a_b/dsn` compute the SAME env key — a silent shared-credential hazard). The charset is
# the lowercase subset of the provisioning operator's _SAFE_IDENTIFIER, so the admission gate and
# the CREATE DATABASE target gate enforce one alphabet (defence in depth: reject at registration,
# before any physical resource, persisted secret reference, sentinel namespace, or lifecycle
# transition exists). 'control' is RESERVED: it would collide with the Control-DB vocabulary and
# the control sentinel namespace (`dv_sentinel_control`).
_TENANT_ID_SHAPE = re.compile(r"^[a-z0-9_]+$")
_RESERVED_TENANT_IDS = frozenset({"control"})


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
        # PRD 07D-2a admission guard (AT-07D1-11): reject BEFORE any effect — no store write, no
        # audit record, no provision(), no lifecycle transition, no persisted secret reference
        # (fail closed). Checked ahead of the idempotent existing-return so an invalid id can
        # never be read back either. The tenant_id is an identifier, never a secret (D-14-safe
        # to echo in the error).
        if tenant_id.lower() in _RESERVED_TENANT_IDS:
            raise RegistryError(f"invalid tenant_id {tenant_id!r}: reserved identifier")
        # fullmatch, not match (PRD 07D-2b.1 / AT-07D2A2-1): with `.match` Python's `$` also
        # matches before ONE trailing newline, so "t1\n" would be admitted and would ALIAS
        # "t1_" through the '\n'->'_' env-key flattening — the exact hazard this guard closes.
        if not _TENANT_ID_SHAPE.fullmatch(tenant_id):
            raise RegistryError(f"invalid tenant_id {tenant_id!r}: must match ^[a-z0-9_]+$")
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
        # PRD 07D-2b.2a (R1-2/C-2): READY joins allowed_from — the amended IC-002 removed the
        # Ready-direct decommission, making Suspended a Ready tenant's ONLY egress; without this
        # the contract's suspend-first rule is inexecutable. The pre-existing {REGISTERED,
        # PROVISIONING} wideness (code-lawful, not contract-listed) is a documented residual for
        # the post-2b.2 docs/contracts reconcile — deliberately NOT removed in this slice.
        return self._transition(
            tenant_id,
            TenantLifecycleState.SUSPENDED,
            {TenantLifecycleState.REGISTERED, TenantLifecycleState.PROVISIONING, TenantLifecycleState.READY},
            "SuspendTenant",
            actor,
            correlation_id,
        )

    def decommission_tenant(self, tenant_id: str, *, actor: str, correlation_id: str) -> TenantRecord:
        # PRD 07D-2b.2a: allowed_from caught up to the amended IC-002 transition table —
        # `Registered | Provisioning | Suspended | Failed | Quarantined → Decommissioned`.
        # Ready-direct decommission stays disallowed (suspend-first); Decommissioned is
        # Quarantined's SOLE egress. Lifecycle-state catch-up only: this slice never calls
        # ProvisioningOperator.deprovision() and drops nothing (compensation is 07D-2b.2b).
        return self._transition(
            tenant_id,
            TenantLifecycleState.DECOMMISSIONED,
            {
                TenantLifecycleState.REGISTERED,
                TenantLifecycleState.PROVISIONING,
                TenantLifecycleState.SUSPENDED,
                TenantLifecycleState.FAILED,
                TenantLifecycleState.QUARANTINED,
            },
            "DecommissionTenant",
            actor,
            correlation_id,
        )

    def quarantine_tenant(self, tenant_id: str, *, actor: str, correlation_id: str) -> TenantRecord:
        # PRD 07D-2b.2a (IC-002 QuarantineTenant): the explicit, audited entry into the
        # evidence-preserving hold — `Provisioning | Failed → Quarantined` (the automatic
        # isolation-anomaly edge `Verifying → Quarantined` is owned by the verification gate at
        # classification time). Routes through _transition, so the B7B-D5 audit-before-commit
        # ordering applies unchanged (AST-guard-enforced).
        return self._transition(
            tenant_id,
            TenantLifecycleState.QUARANTINED,
            {TenantLifecycleState.PROVISIONING, TenantLifecycleState.FAILED},
            "QuarantineTenant",
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
