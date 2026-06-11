"""Live-PG: least-privilege writer role cannot mutate lineage (PRD-P6-R2 A.2; §19).

Connect as the DB owner/superuser (so SET LOCAL ROLE is permitted). The writer role holds no
UPDATE/DELETE grant, and the append-only trigger is the backstop — either way the mutation
must be rejected.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402


def test_writer_role_cannot_mutate(conn) -> None:
    with conn.cursor() as cur:
        _pg.insert_lineage(cur, seq=1, lineage_id="L1")
    raised = False
    with conn.cursor() as cur:
        cur.execute("SAVEPOINT sp")
        try:
            cur.execute("SET LOCAL ROLE lineage_writer")
            cur.execute("UPDATE lineage SET operation = 'x' WHERE lineage_id = 'L1'")
        except Exception:
            raised = True
        finally:
            cur.execute("ROLLBACK TO SAVEPOINT sp")  # also resets SET LOCAL ROLE
    assert raised, "lineage_writer must not be able to UPDATE lineage (privilege + trigger)"


if __name__ == "__main__":
    _pg.run([test_writer_role_cannot_mutate])
