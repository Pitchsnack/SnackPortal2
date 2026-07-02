"""PRD 06 PM-AR-1 — cross-family DDL-coverage meta-guard (architecture; no PostgreSQL).

Every DDL family under ``infrastructure/db/`` now has a required-suite blob-drift guard:
``infrastructure/db/control`` → ``test_b7c1_control_audit_ddl_blob_pins.py`` (+ ``test_b7c1r2_*`` completeness);
``infrastructure/db/provisioning`` + ``infrastructure/db/lineage`` → ``test_non_control_ddl_blob_drift.py``.
But nothing asserted, at the PROGRAM level, that *every* family with ``*.sql`` is covered. A future
``infrastructure/db/<newfamily>/001_*.sql`` could be added with no required-CI blob-drift guard and nothing
would notice — exactly the silent-escape class the Control-DB-only B-7C-1R2 meta-guard closes, but one level
up across families.

This guard is the program-level analogue of B-7C-1R2. It keeps an explicit, reviewed **coverage registry**
(family → its blob-drift guard file) and asserts:

- **INV-A (bidirectional completeness).** The set of on-disk families containing ``*.sql`` equals the registry
  family set — a new unguarded family OR a stale registry key both FAIL, forcing conscious classification.
- **INV-B (structural sanity).** Each registry guard file exists and its source references that family's DDL
  directory via the pathlib segment idiom ``"infrastructure" / "db" / "<family>"`` — so a guard that no longer
  targets its family FAILs (it is not enough that *some* test mentions the path; the *designated* guard must).

A bare "is the family path referenced by some architecture test" check is intentionally NOT used: boundary
tests and the secret-literal guard also reference ``infrastructure/db/<family>`` without pinning the DDL, so
that check would pass even if the real blob-drift guard were deleted.

Scope: required-CI coverage completeness only. Does NOT broaden the B-7C-1R2 Control-DB meta-guard, does NOT
prove tenant physical multi-DB routing, and does NOT close B5-BLK-4. Pure stdlib; imports no database driver;
standalone-runnable:

    python tests/architecture/test_required_ci_ddl_coverage_meta_guard.py
"""

from __future__ import annotations

import pathlib
import re
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_DB_DIR = _scan.REPO_ROOT / "infrastructure" / "db"
_ARCH_DIR = pathlib.Path(__file__).resolve().parent

# Explicit, reviewed coverage registry: DDL family → the required-suite blob-drift guard(s) that pin it.
# A new family MUST be added here (with its guard) in lockstep; an intentionally-unguarded family would need a
# NAMED, commented exemption — never a silent omission.
_COVERAGE: dict[str, list[str]] = {
    "control": ["test_b7c1_control_audit_ddl_blob_pins.py"],
    "provisioning": ["test_non_control_ddl_blob_drift.py"],
    "lineage": ["test_non_control_ddl_blob_drift.py"],
    "tenant": ["test_tenant_ddl_blob_drift.py"],
}


# --- helpers (stdlib only; no DB) ----------------------------------------------------------------
def _families_with_sql(db_dir: pathlib.Path) -> set[str]:
    """Names of immediate subdirectories of ``db_dir`` that contain at least one ``*.sql`` file."""
    return {d.name for d in db_dir.iterdir() if d.is_dir() and any(d.glob("*.sql"))}


def _segment_re(family: str) -> re.Pattern[str]:
    """Match the pathlib idiom ``"infrastructure" / "db" / "<family>"`` the blob-drift guards use."""
    return re.compile(r'"infrastructure"\s*/\s*"db"\s*/\s*"' + re.escape(family) + r'"')


# --- INV-A: bidirectional family completeness ----------------------------------------------------
def test_inv_a_ddl_family_coverage_completeness_bidirectional() -> None:
    on_disk = _families_with_sql(_DB_DIR)
    registry = set(_COVERAGE)
    uncovered = on_disk - registry
    assert not uncovered, (
        f"DDL families with *.sql but NO required-CI coverage registry entry: {sorted(uncovered)}. Add the "
        f"family (and its blob-drift guard) to _COVERAGE in lockstep before merge."
    )
    stale = registry - on_disk
    assert not stale, (
        f"_COVERAGE pins families not present on disk: {sorted(stale)}. A DDL family was deleted/renamed — repair the registry."
    )


# --- INV-B: each registry guard exists and targets its family ------------------------------------
def test_inv_b_registry_guards_target_their_family() -> None:
    for family, guards in _COVERAGE.items():
        assert guards, f"family {family!r} has an empty guard list in _COVERAGE"
        seg = _segment_re(family)
        for guard_name in guards:
            guard_path = _ARCH_DIR / guard_name
            assert guard_path.is_file(), f"coverage registry names a missing guard for {family!r}: {guard_name}"
            src = guard_path.read_text(encoding="utf-8")
            assert seg.search(src), (
                f"guard {guard_name} no longer references the {family!r} DDL dir "
                f'("infrastructure" / "db" / "{family}") — coverage is stale; repair the guard or registry.'
            )


# --- non-vacuity (tempfile only; never writes into infrastructure/db or tests) -------------------
def test_nv_completeness_detects_new_unguarded_family() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        d = pathlib.Path(tmp)
        (d / "control").mkdir()
        (d / "control" / "001_x.sql").write_text("x", encoding="utf-8")
        (d / "newfamily").mkdir()
        (d / "newfamily" / "001_y.sql").write_text("y", encoding="utf-8")
        (d / "emptydir").mkdir()  # no .sql -> must be ignored
        discovered = _families_with_sql(d)
        assert discovered == {"control", "newfamily"}  # emptydir excluded; newfamily discovered
        assert (discovered - {"control"}) == {"newfamily"}  # INV-A forward WOULD fail on an unguarded family


def test_nv_structural_detects_missing_segment() -> None:
    has = 'x = _scan.REPO_ROOT / "infrastructure" / "db" / "lineage"\n'
    missing = "x = somewhere_else / 'lineage'\n"
    assert _segment_re("lineage").search(has)  # the real idiom matches
    assert not _segment_re("lineage").search(missing)  # a guard that dropped the segment WOULD fail INV-B


if __name__ == "__main__":
    _scan.run(
        [
            test_inv_a_ddl_family_coverage_completeness_bidirectional,
            test_inv_b_registry_guards_target_their_family,
            test_nv_completeness_detects_new_unguarded_family,
            test_nv_structural_detects_missing_segment,
        ]
    )
