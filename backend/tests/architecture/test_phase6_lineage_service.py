"""Build Phase 6 architecture guards (full Lineage Service).

Encodes the Phase-6 boundaries from PRD-P6-E1 §18 / P6-R2:
- lineage_service imports NO other service (database_router / control_plane / import_service
  / auth_router / api_gateway) — it runs on injected shared sessions/ports (Standard D).
- no database drivers and no secret literals inside lineage_service.
- canonicalization is single-sourced: only canonical.py constructs the HMAC content join /
  uses hmac/hashlib (closes P6-OBS-3).

Pure stdlib; runs under pytest and standalone.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

DB_PREFIXES = ("psycopg2", "psycopg", "asyncpg", "sqlalchemy", "databases", "aiopg")
SECRETY = ("password", "passwd", "secret=", "dsn=", "begin private key")


def _files():
    return list(_scan.py_files(_scan.BACKEND_ROOT / "lineage_service"))


def _imports():
    for f in _files():
        for mod in _scan.imported_modules(f):
            yield f, mod


def test_lineage_service_imports_no_other_service() -> None:
    for f, mod in _imports():
        top = mod.split(".")[0]
        assert top not in {"database_router", "control_plane", "import_service", "auth_router", "api_gateway"}, (
            f"{_scan.relposix(f)} imports another service '{mod}' — injected shared ports only (Standard D)"
        )


def test_lineage_service_has_no_db_driver() -> None:
    for f, mod in _imports():
        assert not any(mod == p or mod.startswith(p + ".") for p in DB_PREFIXES), (
            f"{_scan.relposix(f)} imports a database driver '{mod}' — lineage never opens tenant DBs (J2)"
        )


def test_lineage_service_has_no_secret_literals() -> None:
    for f in _files():
        text = f.read_text(encoding="utf-8").lower()
        for needle in SECRETY:
            assert needle not in text, f"possible secret-bearing literal '{needle}' in {_scan.relposix(f)}"


def test_canonicalization_is_single_source() -> None:
    for f in _files():
        if f.name == "canonical.py":
            continue
        text = f.read_text(encoding="utf-8")
        for token in ("hmac", "hashlib", "\\x1f"):
            assert token not in text, (
                f"{_scan.relposix(f)} re-implements canonicalization ('{token}') — "
                f"use lineage_service.canonical (P6-OBS-3)"
            )


if __name__ == "__main__":
    _scan.run([
        test_lineage_service_imports_no_other_service,
        test_lineage_service_has_no_db_driver,
        test_lineage_service_has_no_secret_literals,
        test_canonicalization_is_single_source,
    ])
