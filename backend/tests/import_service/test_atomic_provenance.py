"""Atomic provenance (IC-003/IC-004; PRD-P5-R2 K): data + lineage + checkpoint commit/rollback together."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from import_service.models import ImportMode, ImportRequest, SourceDescriptor, SourceKind  # noqa: E402
from lineage_service.emit import LineageEmit  # noqa: E402
from doubles import FakeSecretStore, RaisingLineageEmit, make_service  # noqa: E402


def _req(payload, op="op1"):
    return ImportRequest(
        tenant_id="t1", source=SourceDescriptor(kind=SourceKind.CSV, ref="f", payload=payload),
        mode=ImportMode.ASYNC, operation_key=op, correlation_id="c", actor_ref="user1",
    )


def test_commit_together() -> None:
    svc, provider, _, _, _ = make_service()
    status = svc.start_import(_req("record_id,display_name\n1,A\n2,B"))
    assert status.state == "applied"
    assert len(provider.tenant_copy_rows("t1")) == 2
    assert len(provider.lineage_rows("t1")) == 2
    assert len(provider.checkpoints("t1")) == 1          # one batch committed with its provenance


def test_rollback_together_on_lineage_failure() -> None:
    # Lineage emit fails for the first record of the first batch -> the whole batch rolls back.
    flaky = RaisingLineageEmit(LineageEmit(FakeSecretStore()), {"t1:tenant_copy:1"})
    svc, provider, _, _, _ = make_service(lineage=flaky)
    status = svc.start_import(_req("record_id,display_name\n1,A\n2,B"))
    assert status.state == "failed"
    assert provider.tenant_copy_rows("t1") == []          # no data without provenance
    assert provider.lineage_rows("t1") == []
    assert provider.checkpoints("t1") == []


if __name__ == "__main__":
    _h.run([test_commit_together, test_rollback_together_on_lineage_failure])
