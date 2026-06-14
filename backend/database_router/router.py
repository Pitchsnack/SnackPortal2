"""Database Router (PRD-P4-E1 §4/§19; IC-005; D-04/D-07/D-13/D-14/D-30).

Consumes the authenticated `RequestContext`, determines the routing target
(control-plane vs exactly one tenant database), resolves the registry-authoritative
association, gates on readiness + schema version, resolves per-tenant credentials at
connect time, and hands back a single tenant-bound connection. Enforces single-tenant
binding and emits routing/isolation audit.

This service performs NO authentication, authorization, import, or lineage. It does
not import auth_router or control_plane (transport ports only). The single active
tenant is taken from the signed claim resolved by Phase 3 — never re-derived.
"""

from __future__ import annotations

from typing import Optional

from shared.audit import OperationalAudit, OperationalAuditEvent
from shared.context import RequestContext
from shared.secrets import SecretRef, SecretStore
from shared.session import Lane

from .models import (
    RouteResult,
    RoutingDenied,
    RoutingTarget,
    forbidden,
    unavailable,
)
from .pool import ConnectionPoolManager
from .ports import ConnectionFactory, TenantConnection
from .resolver import RoutingResolver

CONTROL_ROLE = "CONTROL"


class DatabaseRouter:
    def __init__(
        self,
        *,
        resolver: RoutingResolver,
        pool: ConnectionPoolManager,
        secret_store: SecretStore,
        connection_factory: ConnectionFactory,
        audit: OperationalAudit,
        bulk_pool: Optional[ConnectionPoolManager] = None,
    ) -> None:
        self._resolver = resolver
        self._pool = pool  # interactive lane (Build Phase 4 default)
        self._bulk_pool = bulk_pool  # separate bounded capacity for heavy workloads (D-13)
        self._secrets = secret_store
        self._factory = connection_factory
        self._audit = audit

    # -- public API ------------------------------------------------------------
    def route(self, ctx: RequestContext, *, bootstrap_phase0: bool = False, lane: Lane = Lane.INTERACTIVE) -> RouteResult:
        target = self._determine_target(ctx, bootstrap_phase0)
        if target is RoutingTarget.CONTROL:
            self._ok(ctx, None, "RouteControl")
            return RouteResult(target=RoutingTarget.CONTROL)

        tenant_id = ctx.active_tenant_id  # present by determination
        try:
            view = self._resolver.resolve(tenant_id)  # type: ignore[arg-type]
            conn = self._acquire(view.tenant_id, view.database_association_ref, lane)
        except RoutingDenied as denied:
            self._denied(ctx, tenant_id, denied.public_code)
            raise

        # Defense in depth (D-30 L3): the bound connection must match the active tenant.
        if conn.tenant_id != tenant_id:
            self._anomaly(ctx, tenant_id)
            self._pool_for(lane).discard(conn)
            raise unavailable("routing_isolation_fault")

        self._ok(ctx, tenant_id, "Route")
        return RouteResult(
            target=RoutingTarget.TENANT,
            tenant_id=tenant_id,
            association_version=conn.association_version,
            connection=conn,
            lane=lane,
        )

    def release(self, result: RouteResult) -> None:
        if isinstance(result.connection, TenantConnection):
            self._pool_for(result.lane).release(result.connection)

    def _pool_for(self, lane: Lane) -> ConnectionPoolManager:
        if lane is Lane.BULK and self._bulk_pool is not None:
            return self._bulk_pool
        return self._pool

    def invalidate_tenant(self, tenant_id: str) -> None:
        """Push-invalidate the routing-view cache (e.g. after ReassociateDatabase)."""
        self._resolver.invalidate(tenant_id)

    # -- internals -------------------------------------------------------------
    def _determine_target(self, ctx: RequestContext, bootstrap_phase0: bool) -> RoutingTarget:
        if ctx.active_tenant_id is not None:
            if bootstrap_phase0:
                # Tenant routing is unavailable during Bootstrap Phase 0 (IC-001/D-01).
                raise unavailable("tenant_routing_unavailable")
            return RoutingTarget.TENANT
        # No active tenant: control-plane-scoped only for CONTROL; never a tenant DB.
        if ctx.role == CONTROL_ROLE:
            return RoutingTarget.CONTROL
        raise forbidden("no_active_tenant")

    def _acquire(self, tenant_id: str, association_ref: SecretRef, lane: Lane) -> TenantConnection:
        def open_fn() -> TenantConnection:
            # Resolve the per-tenant credential in memory at connect time only (D-14);
            # the descriptor is never stored, logged, or returned.
            descriptor = self._secrets.resolve(association_ref).material
            return self._factory.open(tenant_id, association_ref.version, descriptor)

        try:
            return self._pool_for(lane).acquire(tenant_id, association_ref.version, open_fn)
        except RoutingDenied:
            raise
        except Exception:
            # Secret-missing / driver / capacity / unreachable — surfaced as a
            # non-leaking 'unavailable' (never reveal or chain secret state / topology).
            raise unavailable("connection_unavailable") from None

    # -- audit (references only; never secrets/credentials) --------------------
    def _ok(self, ctx: RequestContext, tenant_id: Optional[str], action: str) -> None:
        self._audit.initiate(
            OperationalAuditEvent(
                actor_ref=ctx.principal_ref or "<unknown>",
                action=action,
                correlation_id=ctx.correlation_id,
                outcome="success",
                target_ref=tenant_id,
            )
        )

    def _denied(self, ctx: RequestContext, tenant_id: Optional[str], code: str) -> None:
        self._audit.initiate(
            OperationalAuditEvent(
                actor_ref=ctx.principal_ref or "<unknown>",
                action="RouteDenied",
                correlation_id=ctx.correlation_id,
                outcome="denied:" + code,
                target_ref=tenant_id,
            )
        )

    def _anomaly(self, ctx: RequestContext, tenant_id: Optional[str]) -> None:
        # Cross-tenant-adjacent anomaly (D-30 L4) — no secrets, no topology.
        self._audit.initiate(
            OperationalAuditEvent(
                actor_ref=ctx.principal_ref or "<unknown>",
                action="IsolationAnomaly",
                correlation_id=ctx.correlation_id,
                outcome="anomaly:tenant_binding",
                target_ref=tenant_id,
            )
        )
