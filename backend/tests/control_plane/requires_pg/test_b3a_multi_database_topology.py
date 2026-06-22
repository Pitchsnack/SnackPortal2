"""PRD 06 B-3A — local multi-database topology proof (live; standalone-only).

Asserts the four B-3A PostgreSQL targets (Control + ACME/ZETA/NOVA) are four physically distinct
clusters: four distinct ``system_identifier`` values, four distinct database names, and four distinct
connection references. Fail-closed if any target is missing.

Driver Containment Standard: psycopg is located via ``importlib`` (mirroring ``_pg.py``); this file
carries NO static driver import, so it stays within the allow-set enforced by
``tests/architecture/test_vendor_and_db_containment.py``. It skips cleanly unless all four
``SP2_B3A_*_DSN`` variables are set and psycopg is importable, and it is excluded from the default
suite (``requires_pg`` is ``--ignore``'d in pyproject). It prints no DSNs and no passwords.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
from typing import Dict, List

import pytest

_ENV_VARS = {
    "control": "SP2_B3A_CONTROL_DB_DSN",
    "acme": "SP2_B3A_ACME_DB_DSN",
    "zeta": "SP2_B3A_ZETA_DB_DSN",
    "nova": "SP2_B3A_NOVA_DB_DSN",
}


def _dsns() -> Dict[str, str]:
    return {name: os.environ.get(var, "") for name, var in _ENV_VARS.items()}


def _available() -> bool:
    return all(_dsns().values()) and importlib.util.find_spec("psycopg") is not None


def _identities(dsns: Dict[str, str]) -> Dict[str, Dict[str, str]]:
    # psycopg located via importlib (Driver Containment) — never a static import.
    psycopg = importlib.import_module("psycopg")
    out: Dict[str, Dict[str, str]] = {}
    for name, conninfo in dsns.items():
        conn = psycopg.connect(conninfo, connect_timeout=5)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT system_identifier FROM pg_control_system()")
                sysid = str(cur.fetchone()[0])
                cur.execute("SELECT current_database()")
                dbname = str(cur.fetchone()[0])
        finally:
            conn.close()
        out[name] = {"system_identifier": sysid, "database": dbname}
    return out


def _prove() -> List[str]:
    dsns = _dsns()
    missing = [name for name, value in dsns.items() if not value]
    assert not missing, f"fail-closed: missing B-3A target DSN(s): {missing}"
    ids = _identities(dsns)
    assert len(ids) == 4, f"expected 4 reachable targets, got {len(ids)}"
    sysids = [v["system_identifier"] for v in ids.values()]
    assert len(set(sysids)) == 4, "system_identifiers not all distinct (shared cluster — not physically separate)"
    dbnames = [v["database"] for v in ids.values()]
    assert len(set(dbnames)) == 4, f"database names not all distinct: {sorted(dbnames)}"
    assert len(set(dsns.values())) == 4, "connection references not all distinct"
    # Non-secret evidence lines only (no DSN, no password).
    return [
        f"{name}: database={ids[name]['database']} system_identifier={ids[name]['system_identifier']}"
        for name in ("control", "acme", "zeta", "nova")
    ]


def test_b3a_four_distinct_physical_databases() -> None:
    if not _available():
        pytest.skip("B-3A env not set (SP2_B3A_*_DSN) or psycopg unavailable — local topology proof pending")
    for line in _prove():
        print(line)


if __name__ == "__main__":
    if not _available():
        print("SKIP (SP2_B3A_*_DSN not all set / psycopg not installed) — B-3A topology proof pending")
    else:
        for proof_line in _prove():
            print("PROOF:", proof_line)
        print("ALL PASSED")
