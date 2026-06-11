"""Lineage query — tenant-scoped, read-only lookups (IC-004; PRD-P6-R2 D; §10).

Consumes a `LineageReadSessionProvider` (implemented by the Database Router; injected) and
opens a short-lived tenant-bound read session per call — never imports `database_router`
(DAG). Reads are keyset-paginated by `seq` (expand-only) and parameter-filtered; rows map
to `LineageRecordView` (references only). Tenant scope is intrinsic: the routed session is
bound to exactly one tenant DB (D-04/D-30), so no cross-tenant query is expressible here.

Authorization (`lineage:read`) is decided by the caller/auth layer (§16) — this service
implements no authN/authZ; it consumes the resolved `RequestContext` and trusts its scope.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from shared.context import RequestContext
from shared.session import LineageReadSession, LineageReadSessionProvider

from .models import LINEAGE_TABLE, LineageRecordView, Page

READ_PERMISSION = "lineage:read"  # declared for traceability; enforced upstream (§16)


class LineageQuery:
    def __init__(self, provider: LineageReadSessionProvider, *, page_limit_max: int = 200) -> None:
        self._provider = provider
        self._page_limit_max = page_limit_max

    def get(self, ctx: RequestContext, lineage_id: str) -> Optional[LineageRecordView]:
        """Lookup a single record by id (G1)."""
        session = self._open(ctx)
        try:
            rows = session.page(LINEAGE_TABLE, {"lineage_id": lineage_id}, order_by="seq", limit=1)
        finally:
            session.close()
        return LineageRecordView.from_row(rows[0]) if rows else None

    def for_record(self, ctx: RequestContext, target_ref: str, *,
                   after: Optional[int] = None, limit: int = 50) -> Page:
        """Lineage of one tenant record (G1)."""
        return self._page(ctx, {"target_ref": target_ref}, after, limit)

    def for_import(self, ctx: RequestContext, derivation_ref: str, *,
                   after: Optional[int] = None, limit: int = 50) -> Page:
        """Import history by job reference (G2)."""
        return self._page(ctx, {"derivation_ref": derivation_ref}, after, limit)

    def events(self, ctx: RequestContext, *, event_type: Optional[str] = None,
               after: Optional[int] = None, limit: int = 50) -> Page:
        """Recent events, optionally filtered by type (G2)."""
        where: Dict[str, Any] = {"event_type": event_type} if event_type else {}
        return self._page(ctx, where, after, limit)

    # -- internals -------------------------------------------------------------
    def _page(self, ctx: RequestContext, where: Dict[str, Any],
              after: Optional[int], limit: int) -> Page:
        n = max(1, min(int(limit), self._page_limit_max))
        session = self._open(ctx)
        try:
            rows = session.page(LINEAGE_TABLE, where, order_by="seq",
                                descending=True, after=after, limit=n)
        finally:
            session.close()
        items = [LineageRecordView.from_row(r) for r in rows]
        next_cursor = items[-1].seq if len(items) == n and items else None
        return Page(items=items, next_cursor=next_cursor)

    def _open(self, ctx: RequestContext) -> LineageReadSession:
        return self._provider.open_read_session(
            tenant_id=ctx.active_tenant_id, correlation_id=ctx.correlation_id,
            principal_ref=ctx.principal_ref,
        )
