"""Live-PG: DB-level append-only rejects UPDATE/DELETE/TRUNCATE (D-23; PRD-P6-R2 A; §19)."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402


def test_append_only_rejects_update_delete_truncate(conn) -> None:
    with conn.cursor() as cur:
        _pg.insert_lineage(cur, seq=1, lineage_id="L1")
    assert _pg.expect_error(conn, "UPDATE lineage SET operation = 'x' WHERE lineage_id = 'L1'"), \
        "UPDATE on lineage must be rejected (P6A01)"
    assert _pg.expect_error(conn, "DELETE FROM lineage WHERE lineage_id = 'L1'"), \
        "DELETE on lineage must be rejected (P6A01)"
    assert _pg.expect_error(conn, "TRUNCATE lineage"), \
        "TRUNCATE on lineage must be rejected (P6A01)"


if __name__ == "__main__":
    _pg.run([test_append_only_rejects_update_delete_truncate])
