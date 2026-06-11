"""Live-PG: UNIQUE(seq) fork prevention + advisory-lock acquisition (PRD-P6-R2 B; §19)."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402


def test_unique_seq_prevents_fork(conn) -> None:
    with conn.cursor() as cur:
        _pg.insert_lineage(cur, seq=10, lineage_id="A")
        cur.execute("SAVEPOINT sp")
        raised = False
        try:
            _pg.insert_lineage(cur, seq=10, lineage_id="B")  # a fork claims the same seq
        except Exception:
            raised = True
            cur.execute("ROLLBACK TO SAVEPOINT sp")
        else:
            cur.execute("RELEASE SAVEPOINT sp")
    assert raised, "a duplicate seq (chain fork) must fail closed via UNIQUE(seq)"


def test_advisory_lock_acquires(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("lineage_chain:t1",))
        cur.execute("SELECT 1")
        assert cur.fetchone()[0] == 1


if __name__ == "__main__":
    _pg.run([test_unique_seq_prevents_fork, test_advisory_lock_acquires])
