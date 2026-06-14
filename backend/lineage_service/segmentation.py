"""Chain segmentation & archival framework — read-only metadata (D-24/D-25; §15).

Segmentation is a **label over one continuous chain** (D-25): `emit` stamps each record's
`segment_id` and the `prev_marker` linkage is unbroken across boundaries, so the chain stays
verifiable end to end (continuity = `closing_marker(N) == opening_prev_marker(N+1)`). This
module derives read-only segment summaries (first/last seq, opening/closing markers, count)
and an `ArchivePrepared` signal — making the chain **archival-ready** without moving data
(archival jobs are deferred per R1). No writes, no deletes: append-only is absolute (A/F).
"""

from __future__ import annotations

from typing import Optional

from shared.audit import OperationalAudit, OperationalAuditEvent
from shared.context import RequestContext
from shared.session import LineageReadSession, LineageReadSessionProvider

from .models import LINEAGE_TABLE, SegmentInfo

_COUNT_PAGE = 1000


class Segmentation:
    def __init__(self, provider: LineageReadSessionProvider, *, audit: Optional[OperationalAudit] = None) -> None:
        self._provider = provider
        self._audit = audit

    def current_segment(self, ctx: RequestContext) -> Optional[SegmentInfo]:
        """Summary of the open (highest-seq) segment, or None if no lineage exists."""
        session = self._open(ctx)
        try:
            head = session.page(LINEAGE_TABLE, {}, order_by="seq", descending=True, limit=1)
            if not head:
                return None
            segment_id = int(head[0].get("segment_id", 1) or 1)
            return self._summary(session, segment_id)
        finally:
            session.close()

    def segment_summary(self, ctx: RequestContext, segment_id: int) -> Optional[SegmentInfo]:
        session = self._open(ctx)
        try:
            return self._summary(session, segment_id)
        finally:
            session.close()

    def prepare_archive(self, ctx: RequestContext, segment_id: int) -> Optional[SegmentInfo]:
        """Produce a verifiable, archive-ready summary and emit `ArchivePrepared` (audited)."""
        info = self.segment_summary(ctx, segment_id)
        if info is not None:
            self._audit_archive(ctx, info)
        return info

    @staticmethod
    def verify_continuity(prior: SegmentInfo, nxt: SegmentInfo) -> bool:
        """Cross-segment chain continuity: the next segment opens on the prior's closing marker."""
        return nxt.opening_prev_marker == prior.closing_marker

    # -- internals -------------------------------------------------------------
    def _summary(self, session: LineageReadSession, segment_id: int) -> Optional[SegmentInfo]:
        where = {"segment_id": segment_id}
        first = session.page(LINEAGE_TABLE, where, order_by="seq", descending=False, limit=1)
        if not first:
            return None
        last = session.page(LINEAGE_TABLE, where, order_by="seq", descending=True, limit=1)
        return SegmentInfo(
            segment_id=segment_id,
            first_seq=int(first[0]["seq"]),
            last_seq=int(last[0]["seq"]),
            opening_prev_marker=first[0].get("prev_marker", "") or "",
            closing_marker=last[0]["integrity_marker"],
            count=self._count(session, segment_id),
        )

    def _count(self, session: LineageReadSession, segment_id: int) -> int:
        where = {"segment_id": segment_id}
        total = 0
        after: Optional[int] = None
        while True:
            rows = session.page(LINEAGE_TABLE, where, order_by="seq", descending=False, after=after, limit=_COUNT_PAGE)
            if not rows:
                break
            total += len(rows)
            after = int(rows[-1]["seq"])
            if len(rows) < _COUNT_PAGE:
                break
        return total

    def _audit_archive(self, ctx: RequestContext, info: SegmentInfo) -> None:
        if self._audit is None:
            return
        self._audit.initiate(
            OperationalAuditEvent(
                actor_ref=ctx.principal_ref or "<system>",
                action="ArchivePrepared",
                correlation_id=ctx.correlation_id,
                outcome="segment:%d:%d-%d" % (info.segment_id, info.first_seq, info.last_seq),
                target_ref=ctx.active_tenant_id,
            )
        )

    def _open(self, ctx: RequestContext) -> LineageReadSession:
        return self._provider.open_read_session(
            tenant_id=ctx.active_tenant_id or "",
            correlation_id=ctx.correlation_id,
            principal_ref=ctx.principal_ref,
        )
