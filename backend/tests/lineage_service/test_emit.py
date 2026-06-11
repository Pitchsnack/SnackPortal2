"""Lineage write path: append-only chain + tamper-evident marker + audit (IC-004; D-22/23)."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _doubles  # noqa: E402
import _h  # noqa: E402

from lineage_service import canonical  # noqa: E402
from lineage_service.emit import LineageEmit  # noqa: E402
from shared.lineage import LineageIntent  # noqa: E402


def _intent(target: str, op: str = "created") -> LineageIntent:
    return LineageIntent(
        event_type="import", occurred_at="2026-06-06T00:00:00Z", actor_ref="user1",
        source_ref="global:GlobalStartupDirectory:g1", target_ref=target, operation=op,
        schema_version="1", derivation_ref="job1", correlation_id="c",
    )


def _emit_two():
    prov = _doubles.InMemoryProvider()
    audit = _doubles.RecordingAudit()
    emit = LineageEmit(_doubles.FakeKeyStore(), audit=audit)
    s = prov.open_session(tenant_id="t1", correlation_id="c")
    emit.emit(s, _intent("t1:tenant_copy:1"))
    emit.emit(s, _intent("t1:tenant_copy:2"))
    return prov, audit, prov.store("t1").tables["lineage"]


def test_emit_appends_a_per_tenant_chain() -> None:
    _, _, rows = _emit_two()
    assert [r["seq"] for r in rows] == [1, 2]
    assert rows[0]["prev_marker"] == "" and rows[1]["prev_marker"] == rows[0]["integrity_marker"]
    assert rows[0]["segment_id"] == 1 and rows[1]["segment_id"] == 1
    assert rows[0]["marker_version"] == canonical.CURRENT_MARKER_VERSION
    assert rows[0]["integrity_marker"]


def test_marker_binds_content_tamper_evident() -> None:
    _, _, rows = _emit_two()
    row = rows[0]
    key = "chainkey-lineage/t1/chainkey"
    assert canonical.marker_for(key, row, row["prev_marker"]) == row["integrity_marker"]
    tampered = dict(row, target_ref="t1:tenant_copy:EVIL")
    assert canonical.marker_for(key, tampered, row["prev_marker"]) != row["integrity_marker"]


def test_emit_runs_only_on_the_provided_session() -> None:
    prov, _, rows = _emit_two()
    assert "lineage" in prov.store("t1").tables and len(rows) == 2


def test_emit_audits_lineage_written() -> None:
    _, audit, _ = _emit_two()
    assert audit.actions() == ["LineageWritten", "LineageWritten"]


if __name__ == "__main__":
    _h.run([
        test_emit_appends_a_per_tenant_chain,
        test_marker_binds_content_tamper_evident,
        test_emit_runs_only_on_the_provided_session,
        test_emit_audits_lineage_written,
    ])
