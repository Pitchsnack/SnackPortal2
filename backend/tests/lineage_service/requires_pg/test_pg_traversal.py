"""Live-PG: recursive-CTE provenance traversal (ancestors/descendants) (PRD-P6-R2 G; §19)."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402

_ANCESTORS = (
    "WITH RECURSIVE walk AS ("
    "  SELECT lineage_id, parent_lineage_ref, 0 AS _depth FROM lineage WHERE lineage_id = %s"
    "  UNION ALL"
    "  SELECT p.lineage_id, p.parent_lineage_ref, w._depth + 1"
    "    FROM lineage p JOIN walk w ON p.lineage_id = w.parent_lineage_ref"
    "   WHERE w._depth < %s"
    ") SELECT lineage_id FROM walk ORDER BY _depth LIMIT %s"
)
_DESCENDANTS = (
    "WITH RECURSIVE walk AS ("
    "  SELECT lineage_id, parent_lineage_ref, 0 AS _depth FROM lineage WHERE lineage_id = %s"
    "  UNION ALL"
    "  SELECT c.lineage_id, c.parent_lineage_ref, w._depth + 1"
    "    FROM lineage c JOIN walk w ON c.parent_lineage_ref = w.lineage_id"
    "   WHERE w._depth < %s"
    ") SELECT lineage_id FROM walk ORDER BY _depth LIMIT %s"
)


def test_recursive_traversal(conn) -> None:
    with conn.cursor() as cur:
        _pg.insert_lineage(cur, seq=1, lineage_id="R")
        _pg.insert_lineage(cur, seq=2, lineage_id="C", parent="R")
        _pg.insert_lineage(cur, seq=3, lineage_id="G", parent="C")
    with conn.cursor() as cur:
        cur.execute(_ANCESTORS, ("G", 64, 100000))
        assert [r[0] for r in cur.fetchall()] == ["G", "C", "R"]
        cur.execute(_DESCENDANTS, ("R", 64, 100000))
        assert [r[0] for r in cur.fetchall()] == ["R", "C", "G"]


if __name__ == "__main__":
    _pg.run([test_recursive_traversal])
