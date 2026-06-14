"""Live-PostgreSQL harness for D15 distinctness evidence (standalone-only).

Mirrors the lineage requires_pg harness: clean-skip unless SNACKPORTAL_TEST_DSN is set and
psycopg is importable. The DSN must be an admin connection permitted to CREATE/DROP DATABASE
(controlled non-production only). psycopg is located via importlib so this file carries no
static driver import (Driver Containment Standard).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from typing import Callable, List
from urllib.parse import urlsplit, urlunsplit


def dsn() -> str:
    return os.environ.get("SNACKPORTAL_TEST_DSN", "")


def available() -> bool:
    return bool(dsn()) and importlib.util.find_spec("psycopg") is not None


def swap_db(base_dsn: str, dbname: str) -> str:
    """Return base_dsn with its database path replaced by `dbname`."""
    parts = urlsplit(base_dsn)
    return urlunsplit((parts.scheme, parts.netloc, "/" + dbname, parts.query, parts.fragment))


def run(tests: List[Callable]) -> None:
    if not available():
        print("SKIP (no SNACKPORTAL_TEST_DSN set / psycopg not installed) — live-PG D15 distinctness evidence pending")
        return
    admin = dsn()
    failed = 0
    for t in tests:
        try:
            t(admin)
            print("PASS:", t.__name__)
        except AssertionError as exc:
            failed += 1
            print("FAIL:", t.__name__, "-", exc)
    if failed:
        print(f"{failed} test(s) failed")
        sys.exit(1)
    print("ALL PASSED")
