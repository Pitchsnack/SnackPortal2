"""Lineage search — tenant-scoped, paginated, filterable reads (PRD-P6-R2 D; §13).

Equality-filtered, keyset-paginated search over the per-tenant lineage chain (record /
import / verification-oriented filters). Read-only; tenant scope intrinsic to the routed
session (no cross-tenant search expressible). All filters are parameterized by the read
session provider (injection-safe). Distinct entry point from `LineageQuery` for the §13
search surface; both share the same read seam.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from shared.context import RequestContext
from shared.session import LineageReadSession, LineageReadSessionProvider

from .models import LINEAGE_TABLE, LineageRecordView, Page


class LineageSearch:
    def __init__(self, provider: LineageReadSessionProvider, *, page_limit_max: int = 200) -> None:
        self._provider = provider
        self._page_limit_max = page_limit_max

    def search(
        self,
        ctx: RequestContext,
        *,
        event_type: Optional[str] = None,
        operation: Optional[str] = None,
        derivation_ref: Optional[str] = None,
        actor_ref: Optional[str] = None,
        after: Optional[int] = None,
        limit: int = 50,
    ) -> Page:
        """Search by any combination of equality filters; newest-first, keyset-paginated."""
        where: Dict[str, Any] = {}
        if event_type is not None:
            where["event_type"] = event_type
        if operation is not None:
            where["operation"] = operation
        if derivation_ref is not None:
            where["derivation_ref"] = derivation_ref
        if actor_ref is not None:
            where["actor_ref"] = actor_ref

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
