"""Lineage query: lookup, keyset pagination, filtering, tenant scope (PRD-P6-R2 D; §10)."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _doubles  # noqa: E402
import _h  # noqa: E402

from lineage_service.emit import LineageEmit  # noqa: E402
from lineage_service.query import LineageQuery  # noqa: E402
from shared.lineage import LineageIntent  # noqa: E402


def _setup(n: int = 5, tenant: str = "t1"):
    prov = _doubles.InMemoryProvider()
    emit = LineageEmit(_doubles.FakeKeyStore())
    s = prov.open_session(tenant_id=tenant, correlation_id="c")
    ids = []
    for i in range(1, n + 1):
        ids.append(emit.emit(s, LineageIntent(
            event_type="import", occurred_at="T%d" % i, actor_ref="user1",
            source_ref="g:%d" % i, target_ref="%s:tenant_copy:%d" % (tenant, i),
            operation="created", schema_version="1", derivation_ref="job1", correlation_id="c",
        )))
    return prov, LineageQuery(prov), ids


def test_get_by_id() -> None:
    prov, q, ids = _setup()
    v = q.get(_doubles.ctx(), ids[2])
    assert v is not None and v.lineage_id == ids[2] and v.seq == 3


def test_for_record() -> None:
    prov, q, _ = _setup()
    page = q.for_record(_doubles.ctx(), "t1:tenant_copy:2")
    assert len(page.items) == 1 and page.items[0].target_ref == "t1:tenant_copy:2"


def test_keyset_pagination() -> None:
    prov, q, _ = _setup(n=5)
    p1 = q.events(_doubles.ctx(), limit=2)
    assert [i.seq for i in p1.items] == [5, 4] and p1.next_cursor == 4
    p2 = q.events(_doubles.ctx(), after=p1.next_cursor, limit=2)
    assert [i.seq for i in p2.items] == [3, 2] and p2.next_cursor == 2
    p3 = q.events(_doubles.ctx(), after=p2.next_cursor, limit=2)
    assert [i.seq for i in p3.items] == [1] and p3.next_cursor is None


def test_for_import_filters() -> None:
    prov, q, _ = _setup()
    page = q.for_import(_doubles.ctx(), "job1", limit=100)
    assert len(page.items) == 5 and all(i.derivation_ref == "job1" for i in page.items)


def test_tenant_scoped_isolation() -> None:
    prov, q, _ = _setup(n=3, tenant="t1")
    assert q.events(_doubles.ctx(tenant="t2")).items == []  # t2's DB is empty


if __name__ == "__main__":
    _h.run([
        test_get_by_id, test_for_record, test_keyset_pagination,
        test_for_import_filters, test_tenant_scoped_isolation,
    ])
