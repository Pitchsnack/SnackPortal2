"""Source adapters (D-18): Directory / CSV / JSON import -> tenant copy + lineage + audit."""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from import_service.models import ImportMode, ImportRequest, SourceDescriptor, SourceKind  # noqa: E402
from doubles import FakeDirectoryRead, make_service  # noqa: E402


def _req(source, op="op1", tenant="t1"):
    return ImportRequest(
        tenant_id=tenant, source=source, mode=ImportMode.ASYNC,
        operation_key=op, correlation_id="c", actor_ref="user1",
    )


def test_csv_import_creates_tenant_copy_and_lineage() -> None:
    svc, provider, _, audit, _ = make_service()
    payload = "record_id,display_name\n1,Acme\n2,Beta\n3,Gamma"
    status = svc.start_import(_req(SourceDescriptor(kind=SourceKind.CSV, ref="f.csv", payload=payload)))
    assert status.state == "applied" and status.applied_count == 3
    assert len(provider.tenant_copy_rows("t1")) == 3
    assert len(provider.lineage_rows("t1")) == 3        # one provenance record per imported row
    assert "ImportCompleted" in audit.actions()


def test_json_import_creates_tenant_copy() -> None:
    svc, provider, _, _, _ = make_service()
    payload = json.dumps([
        {"record_id": "1", "display_name": "Acme"},
        {"record_id": "2", "display_name": "Beta"},
    ])
    status = svc.start_import(_req(SourceDescriptor(kind=SourceKind.JSON, ref="f.json", payload=payload)))
    assert status.state == "applied" and status.applied_count == 2
    assert len(provider.tenant_copy_rows("t1")) == 2


def test_directory_import_copies_global_records() -> None:
    directory = FakeDirectoryRead()
    directory.add("startup", "g1", "Acme", sector="ai")
    directory.add("startup", "g2", "Beta", sector="health")
    svc, provider, _, _, _ = make_service(directory=directory)
    source = SourceDescriptor(kind=SourceKind.DIRECTORY, ref="startup", directory_kind="startup")
    status = svc.start_import(_req(source))
    assert status.state == "applied" and status.applied_count == 2
    rows = provider.tenant_copy_rows("t1")
    assert {r["record_id"] for r in rows} == {"g1", "g2"}            # tenant-owned copies
    # Lineage records the Global origin by reference (Global Record != Tenant Record).
    assert all(r["source_ref"].startswith("global:GlobalStartupDirectory:") for r in provider.lineage_rows("t1"))


if __name__ == "__main__":
    _h.run([
        test_csv_import_creates_tenant_copy_and_lineage,
        test_json_import_creates_tenant_copy,
        test_directory_import_copies_global_records,
    ])
