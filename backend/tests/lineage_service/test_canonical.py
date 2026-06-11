"""Canonicalization single-source + frozen v1 (PRD-P6-R2 C; closes P6-OBS-3)."""
from __future__ import annotations

import hashlib
import hmac
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from lineage_service import canonical  # noqa: E402

_REC = {
    "lineage_id": "L1", "seq": 3, "event_type": "import", "occurred_at": "T",
    "actor_ref": "a", "source_ref": "s", "target_ref": "t", "operation": "created",
    "schema_version": "1", "derivation_ref": "job", "parent_lineage_ref": None,
    "correlation_id": "ignored", "segment_id": 2,
}
_EXPECTED = "\x1f".join(
    ["PREV", "L1", "3", "import", "T", "a", "s", "t", "created", "1", "job", ""]
).encode("utf-8")


def test_canonical_content_is_frozen_v1() -> None:
    assert canonical.canonical_content(_REC, "PREV") == _EXPECTED


def test_correlation_and_segment_excluded_from_digest() -> None:
    other = dict(_REC, correlation_id="different", segment_id=9)
    assert canonical.canonical_content(other, "PREV") == _EXPECTED  # both excluded


def test_marker_matches_independent_hmac() -> None:
    content = canonical.canonical_content(_REC, "PREV")
    expected = hmac.new(b"k", content, hashlib.sha256).hexdigest()
    assert canonical.compute_marker("k", content) == expected
    assert canonical.marker_for("k", _REC, "PREV") == expected


def test_unknown_marker_version_raises() -> None:
    try:
        canonical.canonical_content({"seq": 1}, "", marker_version=999)
        assert False, "expected UnknownMarkerVersion"
    except canonical.UnknownMarkerVersion:
        pass


if __name__ == "__main__":
    _h.run([
        test_canonical_content_is_frozen_v1,
        test_correlation_and_segment_excluded_from_digest,
        test_marker_matches_independent_hmac,
        test_unknown_marker_version_raises,
    ])
