"""Tenant lifecycle service — Build Phase 4 (IC-002): Verify / Activate / Reactivate /
ReassociateDatabase.

These are the operations Phase 2 deferred (they require tenant-DB connectivity). They
are CONTROL-PLANE operations — they set the Phase-4 states (Verifying/Ready/Failed)
that the Phase-2 registry intentionally refuses. Verification uses the control-plane
TenantDatabaseProbe (Standard PRD-P4-R2 G); this module never imports or calls
database_router. Every transition is audited (IC-002). Credentials never appear here —
the association is a reference (D-14).

This service is additive: the Phase-2 TenantRegistry is unchanged; this is the
Phase-4-authorized writer of Verifying/Ready/Failed.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from shared.secrets import SecretRef

from ._util import now_iso
from .audit import ControlPlaneAudit
from .ports import ControlStore
from .records import TenantLifecycleState, TenantRecord
from .verification import TenantDatabaseProbe


class LifecycleError(Exception):
    """Non-sensitive lifecycle error (mapped to a defined denial at the edge)."""


def _version_gt(new: str, old: str) -> bool:
    """True if `new` is a strictly greater association version than `old`."""
    try:
        return int(new) > int(old)
    except (TypeError, ValueError):
        return new > old


class TenantLifecycleService:
    def __init__(
        self,
        store: ControlStore,
        audit: ControlPlaneAudit,
        probe: TenantDatabaseProbe,
        *,
        supported_schema_versions: Iterable[str],
    ) -> None:
        self._store = store
        self._audit = audit
        self._probe = probe
        self._supported = frozenset(supported_schema_versions)

    # -- operations ------------------------------------------------------------
    def verify_tenant(self, tenant_id: str, *, actor: str, correlation_id: str) -> TenantRecord:
        rec = self._require(tenant_id)
        if rec.lifecycle_state in (
            TenantLifecycleState.DECOMMISSIONED,
            TenantLifecycleState.SUSPENDED,
        ):
            raise LifecycleError("illegal lifecycle transition")
        self._set(rec, TenantLifecycleState.VERIFYING, actor, correlation_id, "VerifyTenant")

        result = self._probe.probe(rec.database_association_ref)
        cur = self._require(tenant_id)
        if not result.reachable:
            return self._set(cur, TenantLifecycleState.FAILED, actor, correlation_id, "VerifyTenant:unreachable")
        observed = result.observed_schema_version
        # Version-gated readiness (D-17): observed must be supported AND match the registry intent.
        if observed not in self._supported or observed != rec.expected_schema_version:
            return self._set(cur, TenantLifecycleState.FAILED, actor, correlation_id, "VerifyTenant:schema")
        return self._set(cur, TenantLifecycleState.READY, actor, correlation_id, "VerifyTenant:ready")

    def activate_tenant(self, tenant_id: str, *, actor: str, correlation_id: str) -> TenantRecord:
        rec = self._require(tenant_id)
        if rec.lifecycle_state is not TenantLifecycleState.VERIFYING:
            raise LifecycleError("ActivateTenant requires Verifying")
        return self._set(rec, TenantLifecycleState.READY, actor, correlation_id, "ActivateTenant")

    def reactivate_tenant(self, tenant_id: str, *, actor: str, correlation_id: str) -> TenantRecord:
        rec = self._require(tenant_id)
        if rec.lifecycle_state is not TenantLifecycleState.SUSPENDED:
            raise LifecycleError("ReactivateTenant requires Suspended")
        # Suspended -> Verifying -> (re-verify) -> Ready/Failed.
        self._set(rec, TenantLifecycleState.VERIFYING, actor, correlation_id, "ReactivateTenant")
        return self.verify_tenant(tenant_id, actor=actor, correlation_id=correlation_id)

    def reassociate_database(
        self,
        tenant_id: str,
        *,
        new_association_ref: SecretRef,
        actor: str,
        correlation_id: str,
    ) -> TenantRecord:
        rec = self._require(tenant_id)
        if not _version_gt(new_association_ref.version, rec.database_association_ref.version):
            raise LifecycleError("ReassociateDatabase requires an incremented association version")
        # Point at the restored/relocated DB and re-enter Verifying (re-verify before Ready).
        updated = replace(
            rec,
            database_association_ref=new_association_ref,
            lifecycle_state=TenantLifecycleState.VERIFYING,
            updated_at=now_iso(),
        )
        self._store.put_tenant(updated)
        self._audit.record(
            actor=actor,
            tenant_id=tenant_id,
            action="ReassociateDatabase",
            from_state=rec.lifecycle_state.value,
            to_state=TenantLifecycleState.VERIFYING.value,
            correlation_id=correlation_id,
        )
        return updated

    # -- internals -------------------------------------------------------------
    def _require(self, tenant_id: str) -> TenantRecord:
        rec = self._store.get_tenant(tenant_id)
        if rec is None:
            raise LifecycleError("unknown tenant")
        return rec

    def _set(
        self,
        rec: TenantRecord,
        to_state: TenantLifecycleState,
        actor: str,
        correlation_id: str,
        action: str,
    ) -> TenantRecord:
        updated = replace(rec, lifecycle_state=to_state, updated_at=now_iso())
        self._store.put_tenant(updated)
        self._audit.record(
            actor=actor,
            tenant_id=rec.tenant_id,
            action=action,
            from_state=rec.lifecycle_state.value,
            to_state=to_state.value,
            correlation_id=correlation_id,
        )
        return updated
