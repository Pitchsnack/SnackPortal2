"""Provenance graph — per-tenant, read-only traversal (IC-004 D-25; PRD-P6-R2 G; §12).

Walks `parent_lineage_ref` self-references within one tenant DB via the read session's
bounded `traverse` (recursive CTE — no external graph DB; F5). The chain is acyclic by
construction (a child only references a prior record), and traversal is additionally
depth- and node-bounded (cycle/runaway guard; G3). Read-only and tenant-scoped: the routed
session is bound to one tenant, so the graph never crosses tenants (D-25/D-30).
"""

from __future__ import annotations

from shared.context import RequestContext
from shared.session import LineageReadSession, LineageReadSessionProvider

from .models import LINEAGE_TABLE, ProvenanceGraphResult, ProvenanceNode


class ProvenanceGraph:
    def __init__(self, provider: LineageReadSessionProvider, *, max_depth: int = 64, max_nodes: int = 1000) -> None:
        self._provider = provider
        self._max_depth = max_depth
        self._max_nodes = max_nodes

    def ancestors(self, ctx: RequestContext, lineage_id: str) -> ProvenanceGraphResult:
        """Trace a record back through its inputs to its import root(s)."""
        return self._walk(ctx, lineage_id, descendants=False)

    def descendants(self, ctx: RequestContext, lineage_id: str) -> ProvenanceGraphResult:
        """Trace forward to records derived from this one."""
        return self._walk(ctx, lineage_id, descendants=True)

    # -- internals -------------------------------------------------------------
    def _walk(self, ctx: RequestContext, lineage_id: str, *, descendants: bool) -> ProvenanceGraphResult:
        session = self._open(ctx)
        try:
            rows = session.traverse(
                LINEAGE_TABLE,
                lineage_id,
                id_col="lineage_id",
                parent_col="parent_lineage_ref",
                max_depth=self._max_depth,
                descendants=descendants,
            )
        finally:
            session.close()

        truncated = len(rows) > self._max_nodes
        rows = rows[: self._max_nodes]
        nodes = [
            ProvenanceNode(
                lineage_id=str(r["lineage_id"]),
                seq=int(r["seq"]),
                event_type=r["event_type"],
                target_ref=r["target_ref"],
                operation=r["operation"],
                parent_lineage_ref=r.get("parent_lineage_ref"),
            )
            for r in rows
        ]
        return ProvenanceGraphResult(
            root_lineage_id=str(lineage_id),
            direction="descendants" if descendants else "ancestors",
            nodes=nodes,
            truncated=truncated,
        )

    def _open(self, ctx: RequestContext) -> LineageReadSession:
        return self._provider.open_read_session(
            tenant_id=ctx.active_tenant_id,
            correlation_id=ctx.correlation_id,
            principal_ref=ctx.principal_ref,
        )
