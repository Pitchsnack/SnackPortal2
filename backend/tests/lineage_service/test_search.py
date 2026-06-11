"""Lineage search: filterable, paginated, tenant-scoped (PRD-P6-R2 D; §13)."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _doubles  # noqa: E402
import _h  # noqa: E402

from lineage_service.emit import LineageEmit  # noqa: E402
from lineage_service.search import LineageSearch  # noqa: E402
from shared.lineage import LineageIntent  # noqa: E402


def _setup():
    prov = _doubles.InMemoryProvider()
    emit = LineageEmit(_doubles.FakeKeyStore())
    s = prov.open_session(tenant_id="t1", correlation_id="c")

    def _e(event_type, op, deriv, actor, target):
        emit.emit(
            s,
            LineageIntent(
                event_type=event_type,
                occurred_at="T",
                actor_ref=actor,
                source_ref="g",
                target_ref=target,
                operation=op,
                schema_version="1",
                derivation_ref=deriv,
                correlation_id="c",
            ),
        )

    _e("import", "created", "jobA", "alice", "t1:c:1")
    _e("transform", "derived", "jobB", "bob", "t1:c:2")
    _e("import", "noop", "jobA", "alice", "t1:c:1")
    return prov


def test_search_by_event_type() -> None:
    page = LineageSearch(_setup()).search(_doubles.ctx(), event_type="import")
    assert len(page.items) == 2 and all(i.event_type == "import" for i in page.items)


def test_search_by_derivation_and_actor() -> None:
    page = LineageSearch(_setup()).search(_doubles.ctx(), derivation_ref="jobB")
    assert len(page.items) == 1 and page.items[0].actor_ref == "bob"


def test_search_pagination() -> None:
    se = LineageSearch(_setup())
    p1 = se.search(_doubles.ctx(), limit=2)
    assert len(p1.items) == 2 and p1.next_cursor is not None
    p2 = se.search(_doubles.ctx(), after=p1.next_cursor, limit=2)
    assert len(p2.items) == 1 and p2.next_cursor is None


if __name__ == "__main__":
    _h.run([test_search_by_event_type, test_search_by_derivation_and_actor, test_search_pagination])
