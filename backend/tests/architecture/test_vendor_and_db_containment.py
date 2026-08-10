"""Vendor/cloud SDK, database-driver, and JWT/crypto-vendor import containment.

Vendor SDK imports are permitted only under `**/adapters/providers/**`.
Database drivers are permitted only within the enumerated provider-zone allow-set
(Driver Containment Standard, PRD-P4-R2 C): the Database Router's serving zone and the
Control Plane's persistence/verification zone. Forbidden everywhere else.

JWT/crypto vendors (PyJWT ``jwt`` + ``cryptography``) are permitted only under
`**/adapters/providers/**` (production: the SignatureVerifier provider) plus EXACTLY ONE
blessed test-only module — the B5-5 runtime RS256 fixture (``JWT_CRYPTO_FIXTURE_ALLOW``,
a single exact file: never a directory, package prefix, glob, or blanket ``tests/``
allowance). This census is ADDITIVE (PRD B5-5): it strengthens the pre-existing per-module
pins (07E-3b client guard, both composition-root guards) with a repo-wide sweep; alias and
``from``-import forms resolve through ``_scan.imported_modules`` (static AST scope,
matching every existing census here).
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

# JWT/crypto vendor containment (PRD B5-5). The allowance below is ONE exact file — the
# blessed runtime RS256 test fixture — and must stay a single plain path string forever
# (widening it to a tuple, directory, package prefix, or wildcard is a containment breach;
# `test_jwt_crypto_allowance_is_exact_file_and_nonvacuous` fails on any such widening).
JWT_CRYPTO_PREFIXES = ["jwt", "cryptography"]
JWT_CRYPTO_FIXTURE_ALLOW = "tests/shared/crypto_fixture.py"


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


def _jwt_crypto_allowed(rp: str) -> bool:
    """True iff `rp` may import a JWT/crypto vendor: the provider containment zone, or the
    ONE blessed fixture file by exact-path equality (never a prefix/directory/glob match)."""
    return "/adapters/providers/" in ("/" + rp) or rp == JWT_CRYPTO_FIXTURE_ALLOW


def test_jwt_crypto_vendors_only_in_providers_or_the_one_blessed_fixture() -> None:
    for f in _scan.py_files():
        rp = _scan.relposix(f)
        for mod in _scan.imported_modules(f):
            if _matches(mod, JWT_CRYPTO_PREFIXES):
                assert _jwt_crypto_allowed(rp), (
                    f"JWT/crypto vendor import '{mod}' outside adapters/providers and the one "
                    f"blessed fixture ({JWT_CRYPTO_FIXTURE_ALLOW}): {rp}"
                )


def test_jwt_crypto_allowance_is_exact_file_and_nonvacuous() -> None:
    # The allowance is ONE exact file: a plain string, no wildcard/prefix/directory/tuple form.
    assert isinstance(JWT_CRYPTO_FIXTURE_ALLOW, str), "the allowance must be a single exact-path string"
    assert JWT_CRYPTO_FIXTURE_ALLOW == "tests/shared/crypto_fixture.py", "the allowance names exactly the one blessed fixture"
    assert "*" not in JWT_CRYPTO_FIXTURE_ALLOW and "?" not in JWT_CRYPTO_FIXTURE_ALLOW, "no wildcard forms"
    assert not JWT_CRYPTO_FIXTURE_ALLOW.endswith(("/", ".")), "no directory/prefix forms"
    assert (_scan.BACKEND_ROOT / JWT_CRYPTO_FIXTURE_ALLOW).is_file(), "the blessed fixture module must exist"
    # The census actually SEES the fixture's vendor imports (detector non-vacuity on the live tree).
    fixture_mods = _scan.imported_modules(_scan.BACKEND_ROOT / JWT_CRYPTO_FIXTURE_ALLOW)
    assert any(_matches(m, JWT_CRYPTO_PREFIXES) for m in fixture_mods), "census must see the fixture's vendor imports"
    # The predicate blesses exactly the fixture + the provider zone — and nothing else under tests/.
    assert _jwt_crypto_allowed(JWT_CRYPTO_FIXTURE_ALLOW)
    assert _jwt_crypto_allowed("auth_router/adapters/providers/pyjwt_verifier.py")
    for rejected in (
        "tests/shared/test_crypto_fixture.py",  # a SECOND test module is never blessed
        "tests/shared/crypto_fixture2.py",  # nor a same-directory sibling
        "tests/auth_router/crypto_fixture.py",  # nor the same basename in another package
        "tests/architecture/test_vendor_and_db_containment.py",
        "tests/",  # nor any directory/prefix widening
        "auth_router/main.py",
        "shared/audit.py",
    ):
        assert not _jwt_crypto_allowed(rejected), f"allowance must not widen to {rejected}"
    # Detector non-vacuity: plain, dotted-submodule, and aliased/from-import forms all resolve
    # through _matches (imported_modules yields the real module name for `import x as y` and
    # `from x.y import z` alike).
    assert _matches("jwt", JWT_CRYPTO_PREFIXES)
    assert _matches("jwt.algorithms", JWT_CRYPTO_PREFIXES)
    assert _matches("cryptography.hazmat.primitives.asymmetric", JWT_CRYPTO_PREFIXES)
    assert not _matches("jwt_helpers", JWT_CRYPTO_PREFIXES), "prefix matching must stay dotted-boundary exact"
    assert not _matches("cryptographyx", JWT_CRYPTO_PREFIXES), "prefix matching must stay dotted-boundary exact"


if __name__ == "__main__":
    _scan.run(
        [
            test_vendor_imports_only_in_providers,
            test_db_drivers_only_in_permitted_provider_zones,
            test_jwt_crypto_vendors_only_in_providers_or_the_one_blessed_fixture,
            test_jwt_crypto_allowance_is_exact_file_and_nonvacuous,
        ]
    )
