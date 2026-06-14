"""Lineage verification — chain/hash/tamper/continuity (IC-004 D-23; PRD-P6-R2 E; §11).

Recomputes each record's integrity marker via the single-source `canonical` module
(version-aware), checks `prev_marker` linkage and `seq` contiguity across the per-tenant
chain (segments are a label on one continuous chain, so the linkage check covers segment
boundaries — D-25), and emits a non-sensitive `VerificationReport` (hashes/seq/ids only —
E4). Tenant-scoped, read-only, service-independent (no import_service / control_plane /
database_router import — E1/E2/E3). A detected break is alarmed via the shared operational
audit (`ChainBroken`; IC-002), distinct from lineage.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from shared.audit import OperationalAudit, OperationalAuditEvent
from shared.context import RequestContext
from shared.secrets import SecretRef, SecretStore
from shared.session import LineageReadSession, LineageReadSessionProvider

from . import canonical
from .models import LINEAGE_TABLE, VerificationFinding, VerificationReport

VERIFY_PERMISSION = "lineage:verify"  # declared for traceability; enforced upstream (§16)


class LineageVerifier:
    def __init__(
        self,
        provider: LineageReadSessionProvider,
        secret_store: SecretStore,
        *,
        key_prefix: str = "lineage",
        audit: Optional[OperationalAudit] = None,
        scan_page: int = 500,
    ) -> None:
        self._provider = provider
        self._secrets = secret_store
        self._key_prefix = key_prefix
        self._audit = audit
        self._scan_page = scan_page

    def verify(self, ctx: RequestContext, *, max_records: Optional[int] = None) -> VerificationReport:
        session = self._open(ctx)
        try:
            tenant_id = session.tenant_id
            key = self._chain_key(tenant_id)
            rows = self._scan_ascending(session, max_records)
        finally:
            session.close()

        findings: List[VerificationFinding] = []
        prev_marker = ""
        prev_seq: Optional[int] = None
        first_seq: Optional[int] = None
        last_seq: Optional[int] = None

        for r in rows:
            seq = int(r["seq"])
            first_seq = seq if first_seq is None else first_seq
            last_seq = seq
            stored_prev = r.get("prev_marker", "") or ""
            marker_version = int(r.get("marker_version", 1) or 1)

            try:
                expected = canonical.marker_for(key, r, stored_prev, marker_version=marker_version)
            except canonical.UnknownMarkerVersion:
                findings.append(VerificationFinding("marker_mismatch", seq, r.get("lineage_id"), "unknown marker_version"))
                expected = None
            if expected is not None and expected != r.get("integrity_marker"):
                findings.append(
                    VerificationFinding("marker_mismatch", seq, r.get("lineage_id"), "recomputed marker != stored (tamper-evident)")
                )
            if stored_prev != prev_marker:
                findings.append(
                    VerificationFinding("broken_link", seq, r.get("lineage_id"), "prev_marker != prior record integrity_marker")
                )
            if prev_seq is not None and seq != prev_seq + 1:
                findings.append(VerificationFinding("seq_gap", seq, r.get("lineage_id"), "non-contiguous seq"))

            prev_marker = r.get("integrity_marker", "")
            prev_seq = seq

        report = VerificationReport(
            tenant_id=tenant_id,
            scanned=len(rows),
            ok=not findings,
            first_seq=first_seq,
            last_seq=last_seq,
            findings=findings,
        )
        self._audit_result(ctx, report)
        return report

    # -- internals -------------------------------------------------------------
    def _scan_ascending(self, session: LineageReadSession, max_records: Optional[int]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        after: Optional[int] = None
        while True:
            rows = session.page(LINEAGE_TABLE, {}, order_by="seq", descending=False, after=after, limit=self._scan_page)
            if not rows:
                break
            out.extend(rows)
            after = int(rows[-1]["seq"])
            if max_records is not None and len(out) >= max_records:
                return out[:max_records]
            if len(rows) < self._scan_page:
                break
        return out

    def _chain_key(self, tenant_id: str) -> str:
        store_ref = f"{self._key_prefix}/{tenant_id}/chainkey"
        version: str = self._secrets.current_version(store_ref)
        return self._secrets.resolve(SecretRef(store_ref=store_ref, version=version)).material

    def _audit_result(self, ctx: RequestContext, report: VerificationReport) -> None:
        if self._audit is None:
            return
        action = "LineageVerified" if report.ok else "ChainBroken"
        outcome = "verified:%d" % report.scanned if report.ok else "broken:%d" % len(report.findings)
        self._audit.initiate(
            OperationalAuditEvent(
                actor_ref=ctx.principal_ref or "<unknown>",
                action=action,
                correlation_id=ctx.correlation_id,
                outcome=outcome,
                target_ref=report.tenant_id,
            )
        )

    def _open(self, ctx: RequestContext) -> LineageReadSession:
        return self._provider.open_read_session(
            tenant_id=ctx.active_tenant_id or "",
            correlation_id=ctx.correlation_id,
            principal_ref=ctx.principal_ref,
        )
