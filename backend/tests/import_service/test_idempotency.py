"""Idempotency (D-20): operation-key replay + per-record natural-key no-op; tenant-scoped."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from import_service.models import ImportMode, ImportRequest, SourceDescriptor, SourceKind  # noqa: E402
from doubles import make_service  # noqa: E402

_CSV = "record_id,display_name\n1,A\n2,B\n3,C"


def _req(op):
    return ImportRequest(
        tenant_id="t1", source=SourceDescriptor(kind=SourceKind.CSV, ref="f", payload=_CSV),
        mode=ImportMode.ASYNC, operation_key=op, correlation_id="c", actor_ref="user1",
    )


def test_operation_key_replay_is_safe_no_op() -> None:
    svc, provider, _, audit, _ = make_service()
    first = svc.start_import(_req("op1"))
    assert first.state == "applied"
    lineage_after_first = len(provider.lineage_rows("t1"))
    second = svc.start_import(_req("op1"))          # same operation key -> replay
    assert second.state == "applied" and second.import_id == first.import_id
    assert len(provider.tenant_copy_rows("t1")) == 3                 # no duplicate rows
    assert len(provider.lineage_rows("t1")) == lineage_after_first   # no reprocessing
    assert "ImportCompleted" in audit.actions()


def test_natural_key_reconciliation_no_duplicate_rows() -> None:
    svc, provider, _, _, _ = make_service()
    svc.start_import(_req("op1"))
    # A new import event (different operation key) over identical data -> all per-record no-ops.
    status = svc.start_import(_req("op2"))
    assert status.state == "applied"
    assert status.applied_count == 0 and status.noop_count == 3
    assert len(provider.tenant_copy_rows("t1")) == 3                 # still no duplicates


if __name__ == "__main__":
    _h.run([
        test_operation_key_replay_is_safe_no_op,
        test_natural_key_reconciliation_no_duplicate_rows,
    ])
