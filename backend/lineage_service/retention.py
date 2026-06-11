"""Retention framework — architecture only (IC-004 D-24/D-08; PRD-P6-R2 E/F; §14).

Build Phase 6 ships the retention **mechanism** and a **safe default**: with no approved
D-08 values, every tenant evaluates to **retain-all** (nothing eligible for expiry). Expiry,
deletion, and crypto-erase are **disabled** here and raise `RetentionDisabled` — they may be
enabled only once the standing D-08 business/legal values are named (a Control-DB policy
write, audited; never a code change). Per-tenant policy lives in the Control-DB registry by
reference; this module never deletes lineage rows (append-only is absolute — A/F).

Erasure model (when later enabled): act on the **referent** (tenant data / its key), append
a tombstone lineage entry, and never mutate or delete a lineage row — so the chain is never
broken by retention (F3). Every evaluation emits `RetentionEvaluated` (operational audit).
"""
from __future__ import annotations

from typing import Optional

from shared.audit import OperationalAudit, OperationalAuditEvent
from shared.context import RequestContext

from .models import RetentionDecision, RetentionPolicy


class RetentionDisabled(RuntimeError):
    """Expiry/deletion/crypto-erase is not permitted until approved D-08 values exist."""


class RetentionFramework:
    def __init__(self, *, audit: Optional[OperationalAudit] = None) -> None:
        self._audit = audit

    def evaluate(self, ctx: RequestContext, policy: Optional[RetentionPolicy] = None) -> RetentionDecision:
        """Evaluate retention eligibility. Safe default = retain-all (eligible_count = 0)."""
        configured = policy is not None and policy.retention_floor_days is not None
        detail = ("retain (expiry disabled in Build Phase 6)" if configured
                  else "retain-all (D-08 retention values pending)")
        decision = RetentionDecision(
            tenant_id=ctx.active_tenant_id or "", action="retain",
            policy_configured=configured, eligible_count=0, detail=detail,
        )
        self._audit_evaluated(ctx, decision)
        return decision

    def expire(self, *args: object, **kwargs: object) -> None:
        """Disabled in Build Phase 6 — requires approved D-08 values (§14)."""
        raise RetentionDisabled(
            "expiry/deletion/crypto-erase disabled until approved D-08 retention values"
        )

    # archival/crypto-erase share the same gate
    crypto_erase = expire
    delete = expire

    def _audit_evaluated(self, ctx: RequestContext, decision: RetentionDecision) -> None:
        if self._audit is None:
            return
        self._audit.initiate(OperationalAuditEvent(
            actor_ref=ctx.principal_ref or "<system>", action="RetentionEvaluated",
            correlation_id=ctx.correlation_id,
            outcome="retain:configured" if decision.policy_configured else "retain:default",
            target_ref=decision.tenant_id,
        ))
