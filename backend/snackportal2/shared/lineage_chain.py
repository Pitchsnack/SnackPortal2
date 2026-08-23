"""The D-23 lineage integrity chain — canonical content and keyed marker.

**This is a re-implementation of an accepted algorithm, not a new one.** The rules come from
IC-004 (*Immutability*, D-23) and are implemented in the retired architecture at
``backend/lineage_service/canonical.py``. That package is Phase-0 category D and is
unreachable from here by import-linter contract, so the algorithm is restated — deliberately
byte-for-byte, so a row written by the rebuild and a row written by the accepted emitter
carry the same marker for the same content. ``tests/snackportal2/test_lineage_chain.py``
executes both implementations side by side and asserts they agree; if this file ever drifts,
that test fails rather than the chain quietly becoming unverifiable.

The marker is a **per-tenant keyed HMAC** over a fixed, ordered serialization of a lineage
record plus the prior record's marker. Two properties follow, and both are the point:

* *tamper-evidence* — altering any serialized field of any row breaks every marker after it;
* *per-tenant chains* — the key is resolved per tenant and each tenant's chain lives in that
  tenant's own database, so no chain ever spans two tenants (D-25).

``correlation_id``, ``segment_id``, the markers themselves and ``marker_version`` are
deliberately **excluded** from the digest: segmentation is a label rather than tamper-evidence
ordering, and correlation is request metadata. ``v1`` is frozen. A future field or algorithm
change adds a new version and selects the canonicalizer by each row's stored
``marker_version``; it never edits the ``v1`` field order.

No payload, PII, or secret is serialized — references and codes only (D-22). The key is
resolved through :mod:`snackportal2.shared.lineage_keys` and is never stored in lineage,
never logged, and never published.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any, Mapping, Optional

MARKER_VERSION_V1 = 1
CURRENT_MARKER_VERSION = MARKER_VERSION_V1

#: ASCII unit separator. Chosen because it cannot appear in any reference or code the D-22
#: core admits, so no field value can forge a field boundary.
_SEP = "\x1f"

#: The frozen v1 field order. Identical to the accepted canonicalizer, in the same sequence.
_V1_FIELDS = (
    "lineage_id",
    "seq",
    "event_type",
    "occurred_at",
    "actor_ref",
    "source_ref",
    "target_ref",
    "operation",
    "schema_version",
    "derivation_ref",
    "parent_lineage_ref",
)

#: The first row of a chain has no predecessor. Its ``prev_marker`` is the empty string,
#: which is a real serialized value rather than a missing one.
GENESIS_PREV_MARKER = ""


class UnknownMarkerVersion(ValueError):
    """A lineage row carries a ``marker_version`` this build cannot canonicalize.

    Raised rather than defaulted: canonicalizing an unknown version with the v1 field order
    would produce a marker that looks valid and verifies nothing.
    """


@dataclass(frozen=True)
class LineageIntent:
    """The D-22 minimum lineage record, as references and codes only.

    Composed by the service that performs the data change, so that the provenance row and the
    row it describes are written in one transaction (IC-004 *atomic provenance*). Every
    outward pointer is a reference: never a payload, never a credential, never PII.
    """

    event_type: str
    occurred_at: str
    actor_ref: str
    source_ref: str
    target_ref: str
    operation: str
    schema_version: str
    derivation_ref: Optional[str] = None
    parent_lineage_ref: Optional[str] = None
    correlation_id: Optional[str] = None


def canonical_content(record: Mapping[str, Any], prev_marker: str, *, marker_version: int = CURRENT_MARKER_VERSION) -> bytes:
    """Deterministic bytes for ``record`` chained onto ``prev_marker``.

    ``None`` serializes as the empty string so that an absent optional field and an empty one
    are the same input — which is what makes the digest reproducible from a database row,
    where the distinction has already been lost.
    """
    if marker_version == MARKER_VERSION_V1:
        parts = [prev_marker]
        for field_name in _V1_FIELDS:
            value = record.get(field_name)
            parts.append("" if value is None else str(value))
        return _SEP.join(parts).encode("utf-8")
    raise UnknownMarkerVersion(marker_version)


def compute_marker(key: bytes, content: bytes) -> str:
    """Keyed HMAC-SHA256 hexdigest over canonical ``content`` (D-23).

    ``key`` is the resolved chain-key material for exactly one tenant. It is an argument
    rather than module state so that nothing here can hold a secret between calls.
    """
    return hmac.new(key, content, hashlib.sha256).hexdigest()


def marker_for(
    key: bytes,
    record: Mapping[str, Any],
    prev_marker: str,
    *,
    marker_version: int = CURRENT_MARKER_VERSION,
) -> str:
    """Canonicalize, then HMAC. The single way a marker is produced in this architecture."""
    return compute_marker(key, canonical_content(record, prev_marker, marker_version=marker_version))


__all__ = [
    "CURRENT_MARKER_VERSION",
    "GENESIS_PREV_MARKER",
    "MARKER_VERSION_V1",
    "LineageIntent",
    "UnknownMarkerVersion",
    "canonical_content",
    "compute_marker",
    "marker_for",
]
