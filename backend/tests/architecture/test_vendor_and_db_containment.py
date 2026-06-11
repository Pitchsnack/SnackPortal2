"""Vendor/cloud SDK and database-driver import containment.

Vendor SDK imports are permitted only under `**/adapters/providers/**`.
Database drivers are permitted only within the enumerated provider-zone allow-set
(Driver Containment Standard, PRD-P4-R2 C): the Database Router's serving zone and the
Control Plane's persistence/verification zone. Forbidden everywhere else.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

VENDOR_PREFIXES = ["supabase", "lovable", "boto3", "botocore", "azure", "google.cloud", "google.auth"]
DB_PREFIXES = ["psycopg2", "psycopg", "asyncpg", "sqlalchemy", "databases", "aiopg"]

# Per-owning-service provider zones permitted to import a database driver (PRD-P4-R2 C).
DB_PROVIDER_ZONES = (
    "database_router/adapters/providers/",  # tenant-DB serving + tenant-credential resolution
    "control_plane/adapters/providers/",  # Control-DB persistence + tenant-DB verification probe
)


def _matches(mod: str, prefixes: list) -> bool:
    return any(mod == p or mod.startswith(p + ".") for p in prefixes)


def test_vendor_imports_only_in_providers() -> None:
    for f in _scan.py_files():
        rp = _scan.relposix(f)
        for mod in _scan.imported_modules(f):
            if _matches(mod, VENDOR_PREFIXES):
                assert "/adapters/providers/" in ("/" + rp), f"vendor import '{mod}' outside adapters/providers: {rp}"


def test_db_drivers_only_in_permitted_provider_zones() -> None:
    for f in _scan.py_files():
        rp = _scan.relposix(f)
        for mod in _scan.imported_modules(f):
            if _matches(mod, DB_PREFIXES):
                assert any(rp.startswith(z) for z in DB_PROVIDER_ZONES), (
                    f"database driver '{mod}' outside permitted provider zones {DB_PROVIDER_ZONES}: {rp}"
                )


if __name__ == "__main__":
    _scan.run([test_vendor_imports_only_in_providers, test_db_drivers_only_in_permitted_provider_zones])
