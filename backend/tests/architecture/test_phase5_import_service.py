"""Build Phase 5 architecture guards (import_service + lineage write-path slice).

Encodes the Phase-5 boundaries from PRD-P5-R2/E1:
- import_service imports NO other service (database_router / control_plane / lineage_service /
  auth_router) — it collaborates only via shared ports (injected) + transport (Standard B/D/E).
- lineage_service imports neither database_router nor import_service (it runs on the shared
  session it is handed; Standard D).
- no database drivers and no secret literals inside import_service.

Pure stdlib; runs under pytest and standalone.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

DB_PREFIXES = ("psycopg2", "psycopg", "asyncpg", "sqlalchemy", "databases", "aiopg")
SECRETY = ("password", "passwd", "secret=", "dsn=", "BEGIN PRIVATE KEY")


def _imports(pkg: str):
    for f in _scan.py_files(_scan.BACKEND_ROOT / pkg):
        for mod in _scan.imported_modules(f):
            yield f, mod


def test_import_service_imports_no_other_service() -> None:
    for f, mod in _imports("import_service"):
        top = mod.split(".")[0]
        assert top not in {"database_router", "control_plane", "lineage_service", "auth_router", "api_gateway"}, (
            f"{_scan.relposix(f)} imports another service '{mod}' — shared ports/transport only (PRD-P5-R2 B/D/E)"
        )


def test_lineage_service_imports_no_router_or_import() -> None:
    for f, mod in _imports("lineage_service"):
        top = mod.split(".")[0]
        assert top not in {"database_router", "import_service", "auth_router", "control_plane", "api_gateway"}, (
            f"{_scan.relposix(f)} imports another service '{mod}' — lineage runs on the injected session (Standard D)"
        )


def test_import_service_has_no_db_driver() -> None:
    for f, mod in _imports("import_service"):
        assert not any(mod == p or mod.startswith(p + ".") for p in DB_PREFIXES), (
            f"{_scan.relposix(f)} imports a database driver '{mod}' — import never opens tenant DBs (D2/D3)"
        )


def test_import_service_has_no_secret_literals() -> None:
    for f in _scan.py_files(_scan.BACKEND_ROOT / "import_service"):
        text = f.read_text(encoding="utf-8").lower()
        for needle in SECRETY:
            assert needle.lower() not in text, f"possible secret-bearing literal '{needle}' in {_scan.relposix(f)}"


if __name__ == "__main__":
    _scan.run([
        test_import_service_imports_no_other_service,
        test_lineage_service_imports_no_router_or_import,
        test_import_service_has_no_db_driver,
        test_import_service_has_no_secret_literals,
    ])
