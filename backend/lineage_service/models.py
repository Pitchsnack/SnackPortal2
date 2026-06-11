"""lineage_service read/verify/graph/retention DTOs (Build Phase 6).

Contract-owned I/O shapes (Governance §E — they live in the service, not in `shared`).
Every field is a **reference, code, count, or hash** — never a payload, PII, or secret
(D-22). `LineageRecordView` is the read projection of the D-22 core plus the integrity /
segmentation columns needed for verification and archival.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

# Tenant-DB logical table names (the lineage chain + its segment summary).
LINEAGE_TABLE = "lineage"
SEGMENT_TABLE = "lineage_segment"


@dataclass(frozen=True)
class LineageRecordView:
    """Read projection of one lineage record (references only)."""
    lineage_id: str
    seq: int
    segment_id: int
    event_type: str
    occurred_at: str
    actor_ref: str
    source_ref: str
    target_ref: str
    operation: str
    schema_version: str
    integrity_marker: str
    prev_marker: str
    marker_version: int
    derivation_ref: Optional[str] = None
    parent_lineage_ref: Optional[str] = None
    correlation_id: Optional[str] = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "LineageRecordView":
        return cls(
            lineage_id=str(row["lineage_id"]),
            seq=int(row["seq"]),
            segment_id=int(row.get("segment_id", 1) or 1),
            event_type=row["event_type"],
            occurred_at=row["occurred_at"],
            actor_ref=row["actor_ref"],
            source_ref=row["source_ref"],
            target_ref=row["target_ref"],
            operation=row["operation"],
            schema_version=str(row["schema_version"]),
            integrity_marker=row["integrity_marker"],
            prev_marker=row.get("prev_marker", "") or "",
            marker_version=int(row.get("marker_version", 1) or 1),
            derivation_ref=row.get("derivation_ref"),
            parent_lineage_ref=row.get("parent_lineage_ref"),
            correlation_id=row.get("correlation_id"),
        )


@dataclass(frozen=True)
class Page:
    """Expand-only keyset page. `next_cursor` is the `seq` to pass as `after` for more."""
    items: List[LineageRecordView]
    next_cursor: Optional[int] = None


@dataclass(frozen=True)
class VerificationFinding:
    """A non-sensitive verification observation, located by reference (hashes/seq/ids)."""
    kind: str          # "ok" | "marker_mismatch" | "broken_link" | "seq_gap"
    seq: Optional[int] = None
    lineage_id: Optional[str] = None
    detail: str = ""   # non-sensitive (no payloads/secrets)


@dataclass(frozen=True)
class VerificationReport:
    """Evidence of a tenant-scoped chain verification (E4 / IC-002 audit input)."""
    tenant_id: str
    scanned: int
    ok: bool
    first_seq: Optional[int] = None
    last_seq: Optional[int] = None
    findings: List[VerificationFinding] = field(default_factory=list)


@dataclass(frozen=True)
class ProvenanceNode:
    """A node in the per-tenant provenance graph (references only)."""
    lineage_id: str
    seq: int
    event_type: str
    target_ref: str
    operation: str
    parent_lineage_ref: Optional[str] = None


@dataclass(frozen=True)
class ProvenanceGraphResult:
    """A bounded, read-only ancestry/descendant view rooted at one record (D-25)."""
    root_lineage_id: str
    direction: str     # "ancestors" | "descendants"
    nodes: List[ProvenanceNode]
    truncated: bool = False   # depth/node limit reached


@dataclass(frozen=True)
class RetentionPolicy:
    """Per-tenant retention policy (held in the Control-DB registry; references only).

    Values derive from the named D-08 regime; **None means unconfigured → retain-all.**
    """
    regime_code: Optional[str] = None
    retention_floor_days: Optional[int] = None
    retention_ceiling_days: Optional[int] = None
    residency: Optional[str] = None
    archival_target_ref: Optional[str] = None


@dataclass(frozen=True)
class RetentionDecision:
    """Outcome of a retention evaluation. In Build Phase 6 the action is always `retain`."""
    tenant_id: str
    action: str                 # "retain" (expiry disabled until D-08 values approved)
    policy_configured: bool
    eligible_count: int = 0     # records eligible for expiry — 0 by safe default
    detail: str = ""


@dataclass(frozen=True)
class SegmentInfo:
    """Read-only summary of one integrity-chain segment (archival-ready; D-24/D-25)."""
    segment_id: int
    first_seq: int
    last_seq: int
    opening_prev_marker: str    # prev_marker of the segment's first record
    closing_marker: str         # integrity_marker of the segment's last record
    count: int
