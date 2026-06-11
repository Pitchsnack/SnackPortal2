"""Chain verification + tamper detection + continuity (PRD-P6-R2 E; §11)."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _doubles  # noqa: E402
import _h  # noqa: E402

from lineage_service.emit import LineageEmit  # noqa: E402
from lineage_service.verification import LineageVerifier  # noqa: E402
from shared.lineage import LineageIntent  # noqa: E402


def _setup(n: int = 4):
    prov = _doubles.InMemoryProvider()
    emit = LineageEmit(_doubles.FakeKeyStore())
    s = prov.open_session(tenant_id="t1", correlation_id="c")
    for i in range(1, n + 1):
        emit.emit(
            s,
            LineageIntent(
                event_type="import",
                occurred_at="T%d" % i,
                actor_ref="user1",
                source_ref="g:%d" % i,
                target_ref="t1:tenant_copy:%d" % i,
                operation="created",
                schema_version="1",
                derivation_ref="job1",
                correlation_id="c",
            ),
        )
    return prov


def test_clean_chain_verifies() -> None:
    prov = _setup()
    audit = _doubles.RecordingAudit()
    rep = LineageVerifier(prov, _doubles.FakeKeyStore(), audit=audit).verify(_doubles.ctx())
    assert rep.ok and rep.scanned == 4 and rep.first_seq == 1 and rep.last_seq == 4
    assert rep.findings == [] and "LineageVerified" in audit.actions()


def test_tamper_detected() -> None:
    prov = _setup()
    audit = _doubles.RecordingAudit()
    prov.store("t1").tables["lineage"][1]["target_ref"] = "t1:tenant_copy:EVIL"  # mutate w/o re-marking
    rep = LineageVerifier(prov, _doubles.FakeKeyStore(), audit=audit).verify(_doubles.ctx())
    assert not rep.ok and any(f.kind == "marker_mismatch" for f in rep.findings)
    assert "ChainBroken" in audit.actions()


def test_broken_link_detected() -> None:
    prov = _setup()
    prov.store("t1").tables["lineage"][2]["prev_marker"] = "deadbeef"
    rep = LineageVerifier(prov, _doubles.FakeKeyStore()).verify(_doubles.ctx())
    assert not rep.ok and any(f.kind in ("broken_link", "marker_mismatch") for f in rep.findings)


if __name__ == "__main__":
    _h.run([test_clean_chain_verifies, test_tamper_detected, test_broken_link_detected])
