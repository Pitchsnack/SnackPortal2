"""Checkpoint + resume (D-21): crash mid-import -> resume from the last committed batch."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from import_service.models import ImportMode, ImportRequest, SourceDescriptor, SourceKind  # noqa: E402
from lineage_service.emit import LineageEmit  # noqa: E402
from doubles import FakeSecretStore, FlakyLineageEmit, make_service  # noqa: E402

_CSV = "record_id,display_name\n1,A\n2,B\n3,C\n4,D"   # batch_size 2 -> batch1 {1,2}, batch2 {3,4}


def _req(op="op1"):
    return ImportRequest(
        tenant_id="t1", source=SourceDescriptor(kind=SourceKind.CSV, ref="f", payload=_CSV),
        mode=ImportMode.ASYNC, operation_key=op, correlation_id="c", actor_ref="user1",
    )


def test_failure_then_resume_completes_without_duplication() -> None:
    # Batch 2 fails once (lineage emit for record 3); the import resumes and finishes.
    flaky = FlakyLineageEmit(LineageEmit(FakeSecretStore()), {"t1:tenant_copy:3"})
    svc, provider, _, _, _ = make_service(lineage=flaky, batch_size=2)

    first = svc.start_import(_req())
    assert first.state == "failed"
    assert len(provider.tenant_copy_rows("t1")) == 2        # only batch 1 committed
    assert len(provider.lineage_rows("t1")) == 2
    assert len(provider.checkpoints("t1")) == 1             # checkpoint at batch 1

    second = svc.start_import(_req())                       # same operation key -> resume
    assert second.state == "applied"
    rows = provider.tenant_copy_rows("t1")
    assert {r["record_id"] for r in rows} == {"1", "2", "3", "4"}   # all present, no dupes
    lineage = provider.lineage_rows("t1")
    assert sorted(int(r["seq"]) for r in lineage) == [1, 2, 3, 4]   # contiguous chain across resume
    assert len(provider.checkpoints("t1")) == 2


if __name__ == "__main__":
    _h.run([test_failure_then_resume_completes_without_duplication])
