"""Build Phase 4 architecture guards (database_router + control-plane completion).

Encodes the Phase-4 boundaries from PRD-P4-R2:
- database_router consumes the control plane only via transport (no in-process import
  of control_plane), and never imports auth_router (DAG; Standard H).
- control_plane never imports database_router (no runtime cycle; Standard G).
- database drivers stay within the permitted provider zones (Standard C).
- no secret literals in database_router source.

Pure stdlib; runs under pytest and standalone.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

SECRETY = ("password", "passwd", "secret=", "dsn=", "BEGIN PRIVATE KEY")


def _imports(pkg: str):
    for f in _scan.py_files(_scan.BACKEND_ROOT / pkg):
        for mod in _scan.imported_modules(f):
            yield f, mod


def test_database_router_imports_no_other_service() -> None:
    for f, mod in _imports("database_router"):
        top = mod.split(".")[0]
        assert top not in {"control_plane", "auth_router", "import_service", "lineage_service", "api_gateway"}, (
            f"{_scan.relposix(f)} imports another service '{mod}' — transport ports only (Standard H)"
        )


def test_control_plane_does_not_import_database_router() -> None:
    for f, mod in _imports("control_plane"):
        assert mod.split(".")[0] != "database_router", (
            f"{_scan.relposix(f)} imports database_router — would create a runtime cycle (Standard G)"
        )


def test_database_router_db_drivers_confined() -> None:
    db_prefixes = ("psycopg2", "psycopg", "asyncpg", "sqlalchemy", "databases", "aiopg")
    for f, mod in _imports("database_router"):
        if any(mod == p or mod.startswith(p + ".") for p in db_prefixes):
            rp = _scan.relposix(f)
            assert rp.startswith("database_router/adapters/providers/"), f"tenant-DB driver '{mod}' outside the serving provider zone: {rp}"


def test_database_router_has_no_secret_literals() -> None:
    for f in _scan.py_files(_scan.BACKEND_ROOT / "database_router"):
        text = f.read_text(encoding="utf-8").lower()
        for needle in SECRETY:
            assert needle.lower() not in text, f"possible secret-bearing literal '{needle}' in {_scan.relposix(f)}"


if __name__ == "__main__":
    _scan.run(
        [
            test_database_router_imports_no_other_service,
            test_control_plane_does_not_import_database_router,
            test_database_router_db_drivers_confined,
            test_database_router_has_no_secret_literals,
        ]
    )
