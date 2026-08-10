"""Build Phase 3 guards: auth_router stays within IC-005 authentication scope.

auth_router must import no other service in-process (DAG rule 2; especially not
control_plane), no database driver, and no vendor identity SDK (Supabase/Lovable).
PyJWT (`jwt`) is the approved portable JWT library and is allowed (used only by the
SignatureVerifier provider).
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

AR = _scan.BACKEND_ROOT / "auth_router"
FORBIDDEN_SERVICES = ["control_plane", "database_router", "import_service", "lineage_service"]
FORBIDDEN_LIBS = [
    "psycopg2",
    "psycopg",
    "asyncpg",
    "sqlalchemy",
    "databases",
    "aiopg",
    "supabase",
    "lovable",
    "boto3",
    "botocore",
    "azure",
    "google.cloud",
]


def _matches(mod: str, prefixes: list) -> bool:
    return any(mod == p or mod.startswith(p + ".") for p in prefixes)


def test_auth_router_no_forbidden_imports() -> None:
    for f in _scan.py_files(AR):
        for mod in _scan.imported_modules(f):
            top = mod.split(".")[0]
            assert top not in FORBIDDEN_SERVICES, f"{_scan.relposix(f)} imports service '{mod}'"
            assert not _matches(mod, FORBIDDEN_LIBS), f"{_scan.relposix(f)} imports forbidden lib '{mod}'"


if __name__ == "__main__":
    _scan.run([test_auth_router_no_forbidden_imports])
