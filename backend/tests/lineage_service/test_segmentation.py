"""Chain segmentation & archival framework: summaries + continuity (PRD-P6-R2 J; §15)."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _doubles  # noqa: E402
import _h  # noqa: E402

from lineage_service.emit import LineageEmit  # noqa: E402
from lineage_service.models import SegmentInfo  # noqa: E402
from lineage_service.segmentation import Segmentation  # noqa: E402
from shared.lineage import LineageIntent  # noqa: E402


def _setup(n: int = 3):
    prov = _doubles.InMemoryProvider()
    emit = LineageEmit(_doubles.FakeKeyStore())
    s = prov.open_session(tenant_id="t1", correlation_id="c")
    for i in range(1, n + 1):
        emit.emit(
            s,
            LineageIntent(
                event_type="import",
                occurred_at="T%d" % i,
                actor_ref="u",
                source_ref="g",
                target_ref="t1:c:%d" % i,
                operation="created",
                schema_version="1",
                derivation_ref="job1",
                correlation_id="c",
            ),
        )
    return prov


def test_current_segment_summary() -> None:
    prov = _setup(3)
    info = Segmentation(prov).current_segment(_doubles.ctx())
    rows = prov.store("t1").tables["lineage"]
    assert info is not None
    assert info.segment_id == 1 and info.first_seq == 1 and info.last_seq == 3 and info.count == 3
    assert info.opening_prev_marker == "" and info.closing_marker == rows[-1]["integrity_marker"]


def test_prepare_archive_audits() -> None:
    audit = _doubles.RecordingAudit()
    info = Segmentation(_setup(2), audit=audit).prepare_archive(_doubles.ctx(), 1)
    assert info is not None and "ArchivePrepared" in audit.actions()


def test_verify_continuity() -> None:
    a = SegmentInfo(1, 1, 5, "", "MARK_A", 5)
    good = SegmentInfo(2, 6, 10, "MARK_A", "MARK_B", 5)
    bad = SegmentInfo(2, 6, 10, "X", "MARK_B", 5)
    assert Segmentation.verify_continuity(a, good) is True
    assert Segmentation.verify_continuity(a, bad) is False


def test_empty_segment_is_none() -> None:
    assert Segmentation(_doubles.InMemoryProvider()).current_segment(_doubles.ctx()) is None


if __name__ == "__main__":
    _h.run(
        [
            test_current_segment_summary,
            test_prepare_archive_audits,
            test_verify_continuity,
            test_empty_segment_is_none,
        ]
    )
