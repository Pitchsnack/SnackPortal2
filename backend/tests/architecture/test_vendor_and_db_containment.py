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

# --- Option A rebuild (D-46) driver containment ---------------------------------------------
# The rebuild does not use the legacy hexagonal `adapters/providers/**` layout, so its
# driver-holding modules are enumerated as EXACT FILES rather than directory prefixes. That is a
# tightening, not a widening: a new module under `snackportal2/services/*/` cannot acquire a
# driver by being dropped into an already-blessed directory — it has to be added here, in review.
# Each entry is the one module of its service permitted to hold a connection.
REBUILD_DB_DRIVER_ALLOW = (
    "snackportal2/services/control_plane/store.py",  # Control-DB persistence (tenants/memberships/directory)
    "snackportal2/services/audit/sink.py",  # Control-DB durable audit sink (migration M-1)
    # Tenant-database access. Under D-48 the Database Router is the sole AUTHORITY on which
    # database a request may reach, but a tenant-resident domain service holds the connection it
    # opens. `shared/tenant_data.py` is the one place that turns a router grant into a socket;
    # `investors/repository.py` additionally imports psycopg's Jsonb wrapper, because binding a
    # bare Python list to a jsonb column raises at the driver layer (the MCC-AR-1 defect).
    "snackportal2/shared/tenant_data.py",
    "snackportal2/services/investors/repository.py",
)

# JWT/crypto vendor containment (PRD B5-5). The allowance below is ONE exact file — the
# blessed runtime RS256 test fixture — and must stay a single plain path string forever
# (widening it to a tuple, directory, package prefix, or wildcard is a containment breach;
# `test_jwt_crypto_allowance_is_exact_file_and_nonvacuous` fails on any such widening).
JWT_CRYPTO_PREFIXES = ["jwt", "cryptography"]
JWT_CRYPTO_FIXTURE_ALLOW = "tests/api_gateway/crypto_fixture.py"

# The Option A rebuild's one credential-verifying module (IC-005). Exact files only, for the
# same reason as REBUILD_DB_DRIVER_ALLOW: the rebuild has no provider directory to blanket-bless,
# so each verifier is named individually and a second one is a review event, not an accident.
REBUILD_JWT_CRYPTO_ALLOW = ("snackportal2/services/authentication/verifier.py",)


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
                assert _db_driver_allowed(rp), (
                    f"database driver '{mod}' outside permitted provider zones {DB_PROVIDER_ZONES} "
                    f"and rebuild driver modules {REBUILD_DB_DRIVER_ALLOW}: {rp}"
                )


def _db_driver_allowed(rp: str) -> bool:
    """True iff `rp` may import a database driver.

    Legacy packages are matched by directory prefix (the hexagonal provider zones); the Option A
    rebuild is matched by EXACT path equality, so a sibling module cannot inherit the allowance.
    """
    return any(rp.startswith(zone) for zone in DB_PROVIDER_ZONES) or rp in REBUILD_DB_DRIVER_ALLOW


def _jwt_crypto_allowed(rp: str) -> bool:
    """True iff `rp` may import a JWT/crypto vendor: the provider containment zone, the ONE
    blessed fixture file, or a named Option A rebuild verifier — the latter two by exact-path
    equality (never a prefix/directory/glob match)."""
    return "/adapters/providers/" in ("/" + rp) or rp == JWT_CRYPTO_FIXTURE_ALLOW or rp in REBUILD_JWT_CRYPTO_ALLOW


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
    assert JWT_CRYPTO_FIXTURE_ALLOW == "tests/api_gateway/crypto_fixture.py", "the allowance names exactly the one blessed fixture"
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
        "tests/api_gateway/test_crypto_fixture.py",  # a SECOND test module is never blessed
        "tests/api_gateway/crypto_fixture2.py",  # nor a same-directory sibling
        "tests/auth_router/crypto_fixture.py",  # nor the same basename in another package
        "tests/architecture/test_vendor_and_db_containment.py",
        "tests/",  # nor any directory/prefix widening
        "api_gateway/main.py",
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


def test_rebuild_allowances_are_exact_files_and_nonvacuous() -> None:
    """The Option A allowances are exact files, they exist, and the census actually sees them.

    Held to the same standard as the blessed fixture above. Two failure modes are checked, and
    both are the kind that leave a guard green while it protects nothing: an allowance naming a
    file that does not exist (so the census never meets it), and an allowance naming a file that
    imports no vendor at all (so the entry is dead and could be widened without anyone noticing).
    """
    for allowance, prefixes in ((REBUILD_DB_DRIVER_ALLOW, DB_PREFIXES), (REBUILD_JWT_CRYPTO_ALLOW, JWT_CRYPTO_PREFIXES)):
        assert isinstance(allowance, tuple) and allowance, "the allowance must be a non-empty tuple of exact paths"
        for entry in allowance:
            assert isinstance(entry, str), "each allowance entry must be a plain path string"
            assert "*" not in entry and "?" not in entry, f"no wildcard forms: {entry}"
            assert not entry.endswith(("/", ".")), f"no directory/prefix forms: {entry}"
            assert (_scan.BACKEND_ROOT / entry).is_file(), f"allowed module does not exist: {entry}"
            mods = _scan.imported_modules(_scan.BACKEND_ROOT / entry)
            assert any(_matches(m, prefixes) for m in mods), f"allowance is dead — {entry} imports no such vendor"

    # Exact-path equality, never prefix or sibling inheritance.
    assert _db_driver_allowed("snackportal2/shared/tenant_data.py")
    for rejected in (
        "snackportal2/services/database_router/main.py",  # a sibling in the same package
        "snackportal2/services/database_router/resolver.py",  # resolves and issues grants; opens nothing itself
        "snackportal2/services/startups/repository.py",  # reaches its tenant DB only via shared/tenant_data
        "snackportal2/services/",  # any directory widening
        "snackportal2/shared/config.py",
    ):
        assert not _db_driver_allowed(rejected), f"driver allowance must not widen to {rejected}"

    assert _jwt_crypto_allowed("snackportal2/services/authentication/verifier.py")
    for rejected in (
        "snackportal2/services/authentication/main.py",
        "snackportal2/services/authentication/service.py",
        "snackportal2/services/access_control/policy.py",  # the authorizer must never verify a token
        "snackportal2/services/",
    ):
        assert not _jwt_crypto_allowed(rejected), f"JWT allowance must not widen to {rejected}"


if __name__ == "__main__":
    _scan.run(
        [
            test_vendor_imports_only_in_providers,
            test_db_drivers_only_in_permitted_provider_zones,
            test_jwt_crypto_vendors_only_in_providers_or_the_one_blessed_fixture,
            test_jwt_crypto_allowance_is_exact_file_and_nonvacuous,
            test_rebuild_allowances_are_exact_files_and_nonvacuous,
        ]
    )
