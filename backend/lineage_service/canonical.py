"""Canonical lineage content + integrity marker — single source of truth (PRD-P6-R2 C).

The marker is a per-tenant keyed HMAC over a fixed, ordered serialization of a lineage
record plus the prior record's marker (D-23 hash-chain). **Emit, verification, and tests
MUST all compute the marker through this module** — no field-order is re-implemented
anywhere else (closes P6-OBS-3; a Phase-6 architecture guard enforces it).

Versioned (`marker_version`): **v1 is frozen** and byte-identical to the Build Phase 5
emit, so the existing chain stays verifiable. A future field/algorithm change adds a new
version; verification selects the canonicalizer by each record's stored `marker_version`
(backward compatible). `correlation_id`, `segment_id`, the markers themselves, and
`marker_version` are deliberately **excluded** from the digest (segmentation is a label,
not tamper-evidence ordering — D-25; correlation is request metadata).

No payloads, PII, or secrets are serialized — references and codes only (D-22). The keyed
hash key is a D-14 reference resolved by the caller and never stored in lineage.
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Any, Mapping

MARKER_VERSION_V1 = 1
CURRENT_MARKER_VERSION = MARKER_VERSION_V1

_SEP = "\x1f"  # unit separator

# Frozen v1 field order (matches Build Phase 5 emit byte-for-byte).
_V1_FIELDS = (
    "lineage_id", "seq", "event_type", "occurred_at", "actor_ref", "source_ref",
    "target_ref", "operation", "schema_version", "derivation_ref", "parent_lineage_ref",
)


class UnknownMarkerVersion(ValueError):
    """A lineage record carries a marker_version this build cannot canonicalize."""


def canonical_content(record: Mapping[str, Any], prev_marker: str, *,
                      marker_version: int = CURRENT_MARKER_VERSION) -> bytes:
    """Deterministic bytes for `record` chained on `prev_marker`. References/codes only."""
    if marker_version == MARKER_VERSION_V1:
        parts = [prev_marker]
        for field in _V1_FIELDS:
            value = record.get(field)
            parts.append("" if value is None else str(value))
        return _SEP.join(parts).encode("utf-8")
    raise UnknownMarkerVersion(marker_version)


def compute_marker(key: str, content: bytes) -> str:
    """Keyed HMAC-SHA256 hexdigest over canonical `content` (D-23). `key` is resolved from a
    D-14 SecretRef by the caller and never stored in lineage."""
    return hmac.new(key.encode("utf-8"), content, hashlib.sha256).hexdigest()


def marker_for(key: str, record: Mapping[str, Any], prev_marker: str, *,
               marker_version: int = CURRENT_MARKER_VERSION) -> str:
    """Convenience: canonicalize then HMAC. The single way a marker is produced."""
    return compute_marker(key, canonical_content(record, prev_marker, marker_version=marker_version))
