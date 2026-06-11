"""Provenance graph: ancestor/descendant traversal + bounds (PRD-P6-R2 G; §12)."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _doubles  # noqa: E402
import _h  # noqa: E402

from lineage_service.emit import LineageEmit  # noqa: E402
from lineage_service.graph import ProvenanceGraph  # noqa: E402
from shared.lineage import LineageIntent  # noqa: E402


def _chain():
    prov = _doubles.InMemoryProvider()
    emit = LineageEmit(_doubles.FakeKeyStore())
    s = prov.open_session(tenant_id="t1", correlation_id="c")

    def _e(target, op, parent):
        return emit.emit(s, LineageIntent(
            event_type="import" if parent is None else "transform", occurred_at="T",
            actor_ref="u", source_ref="g", target_ref=target, operation=op,
            schema_version="1", derivation_ref="job1", parent_lineage_ref=parent, correlation_id="c",
        ))

    root = _e("t1:c:1", "created", None)
    child = _e("t1:c:2", "derived", root)
    grand = _e("t1:c:3", "derived", child)
    return prov, root, child, grand


def test_ancestors_trace_to_root() -> None:
    prov, root, child, grand = _chain()
    res = ProvenanceGraph(prov).ancestors(_doubles.ctx(), grand)
    assert [n.lineage_id for n in res.nodes] == [grand, child, root]
    assert res.direction == "ancestors" and not res.truncated


def test_descendants_from_root() -> None:
    prov, root, child, grand = _chain()
    res = ProvenanceGraph(prov).descendants(_doubles.ctx(), root)
    assert {n.lineage_id for n in res.nodes} == {root, child, grand}


def test_node_limit_truncates() -> None:
    prov, root, child, grand = _chain()
    res = ProvenanceGraph(prov, max_nodes=2).descendants(_doubles.ctx(), root)
    assert res.truncated and len(res.nodes) == 2


if __name__ == "__main__":
    _h.run([test_ancestors_trace_to_root, test_descendants_from_root, test_node_limit_truncates])
