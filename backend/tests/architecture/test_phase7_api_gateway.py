"""Build Phase 7 guards: api_gateway stays an edge-only enforcement boundary.

The gateway MUST import no other service in-process (DAG independence; IC-010 §H/§M —
the Database Router and Authenticator are reached over transport ports), no database
driver (it never accesses a database; IC-010 §X), and — because it is edge-only and
needs no vendor provider zone — NO vendor/cloud SDK ANYWHERE in the package, including
under adapters/providers (IC-010 Anti-Vendor-Lock-In). This api_gateway-scoped check is
stricter than the repo-wide containment test, which permits vendor imports inside any
``adapters/providers/`` path.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

AG = _scan.BACKEND_ROOT / "api_gateway"
FORBIDDEN_SERVICES = ["auth_router", "control_plane", "database_router", "import_service", "lineage_service"]
FORBIDDEN_LIBS = [
    # database drivers (the gateway accesses no database)
    "psycopg2",
    "psycopg",
    "asyncpg",
    "sqlalchemy",
    "databases",
    "aiopg",
    # vendor / cloud SDKs (no vendor provider zone in the gateway)
    "supabase",
    "lovable",
    "boto3",
    "botocore",
    "azure",
    "google.cloud",
    "google.auth",
]


def _matches(mod: str, prefixes: list) -> bool:
    return any(mod == p or mod.startswith(p + ".") for p in prefixes)


def test_api_gateway_no_forbidden_imports() -> None:
    for f in _scan.py_files(AG):
        for mod in _scan.imported_modules(f):
            top = mod.split(".")[0]
            assert top not in FORBIDDEN_SERVICES, f"{_scan.relposix(f)} imports service '{mod}'"
            assert not _matches(mod, FORBIDDEN_LIBS), f"{_scan.relposix(f)} imports forbidden lib '{mod}'"


if __name__ == "__main__":
    _scan.run([test_api_gateway_no_forbidden_imports])
