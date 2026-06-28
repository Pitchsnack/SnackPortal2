"""PRD 06 B-7C-1R2 (B7C1R-AR-1) — Control-DB DDL / harness-pin completeness meta-guard.

The B-7C-1/1R blob-drift guard (``test_b7c1_control_audit_ddl_blob_pins.py``) pins the reviewed Control-DB
DDL (``001``/``002``/``003``) and cross-checks the live-PG harness pins — but it enumerates that coverage by
HAND. A future ``infrastructure/db/control/004_*.sql`` or a new ``requires_pg`` ``_REVIEWED_*_BLOB`` pin could
be added without the blob-drift guard noticing (the live-PG harnesses are ``--ignore``'d by the default
suite, so drift there surfaces only on a manual live run). This meta-guard closes those two silent-escape
paths in the DEFAULT suite (no PostgreSQL, no DSN, no DDL application).

Design (PRD 06 B-7C-1R2 V1 R1):

- **Independent discovery is the AUTHORITY.** This guard derives ground truth itself: it globs
  ``infrastructure/db/control/*.sql`` and scans ``tests/control_plane/requires_pg/`` for reviewed pins. The
  blob-drift guard's DECLARED coverage (parsed from its source) is the SUBJECT compared against that truth —
  so a weak/incomplete guard list cannot fool this meta-guard (Decision 6.2).
- **Control-association is STRUCTURAL, never value-matching.** A discovered pin is Control-DB-associated iff
  its harness source contains the segment-literal sequence ``"infrastructure" / "db" / "control"`` (the
  pathlib idiom the harnesses actually use; the full path never appears as a monolithic string literal).
  This is drift-independent: a STALE control pin stays in scope and fails, instead of being misclassified
  out-of-scope by a value coincidence.
- **No value allow-set.** Out-of-scope is decided by the structural rule; the non-control pin set is asserted
  empty on ``main`` so any future non-control pin trips this guard for CONSCIOUS classification.

Scope: Control-DB DDL only (``infrastructure/db/control/*.sql``). Does NOT cover ``db/lineage`` or
``db/provisioning``; does NOT prove tenant physical multi-DB routing; does NOT close B5-BLK-4. CI regression
hardening only. Pure stdlib; imports no database driver; standalone-runnable:

    python tests/architecture/test_b7c1r2_control_ddl_pin_completeness.py
"""

from __future__ import annotations

import pathlib
import re
import sys
import tempfile
from collections.abc import Callable

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_CONTROL_DIR = _scan.REPO_ROOT / "infrastructure" / "db" / "control"
_REQUIRES_PG_DIR = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg"
_GUARD = pathlib.Path(__file__).resolve().parent / "test_b7c1_control_audit_ddl_blob_pins.py"

# Assignment-anchored: capture (variable, 40-hex value) at the declaration site, not the assert-message
# reference sites. Matches _REVIEWED_DDL_BLOB as well as _REVIEWED_002_BLOB / _REVIEWED_003_BLOB.
_PIN_ASSIGN = re.compile(r'(_REVIEWED_[A-Z0-9]+_BLOB)\s*=\s*"([0-9a-f]{40})"')
# The pathlib segment sequence the pin-bearing harnesses use to reach the Control-DB DDL dir.
_CONTROL_SEG = re.compile(r'"infrastructure"\s*/\s*"db"\s*/\s*"control"')


# --- AUTHORITY: independent filesystem discovery ---------------------------------------------------------
def discover_control_ddls(control_dir: pathlib.Path = _CONTROL_DIR) -> set[str]:
    """Control-DB DDL filenames on disk. ``*.sql`` only — README.md/any non-.sql file is excluded."""
    return {p.name for p in control_dir.glob("*.sql")}


def discover_pins(requires_pg_dir: pathlib.Path = _REQUIRES_PG_DIR) -> list[tuple[str, str, str, bool]]:
    """Reviewed-blob pins in requires_pg as (harness_name, variable, value, is_control_associated)."""
    out: list[tuple[str, str, str, bool]] = []
    for path in sorted(requires_pg_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        src = path.read_text(encoding="utf-8")
        is_control = bool(_CONTROL_SEG.search(src))
        for match in _PIN_ASSIGN.finditer(src):
            out.append((path.name, match.group(1), match.group(2), is_control))
    return out


# --- SUBJECT under test: the blob-drift guard's DECLARED coverage (assignment-anchored source parse) ------
def guard_declared_ddls(guard: pathlib.Path = _GUARD) -> set[str]:
    """DDL filenames the blob-drift guard declares it pins (``_DDL_xxx = _CONTROL / "...sql"``)."""
    src = guard.read_text(encoding="utf-8")
    return set(re.findall(r'_DDL_\w+\s*=\s*_CONTROL\s*/\s*"([^"]+\.sql)"', src))


def guard_referenced(guard: pathlib.Path = _GUARD) -> tuple[set[str], set[str]]:
    """(harness basenames the guard enumerates, reviewed-pin variable names the guard references)."""
    src = guard.read_text(encoding="utf-8")
    harnesses = set(re.findall(r'"(\w+\.py)"', src))
    pin_vars = set(re.findall(r"_REVIEWED_[A-Z0-9]+_BLOB", src))
    return harnesses, pin_vars


# --- INV-A: Control-DB DDL completeness (primary, drift-proof, bidirectional) -----------------------------
def test_inv_a_control_ddl_completeness_bidirectional() -> None:
    disk = discover_control_ddls()
    assert len(disk) >= 3, f"expected >=3 Control-DB DDL files on disk; found {sorted(disk)} — has infrastructure/db/control moved?"
    assert "README.md" not in disk, "README.md must be excluded by the *.sql glob"
    declared = guard_declared_ddls()
    uncovered = disk - declared
    assert not uncovered, (
        f"Control-DB DDL on disk NOT covered by test_b7c1_control_audit_ddl_blob_pins.py: {sorted(uncovered)}. "
        f"Extend the blob-drift guard (and the matching requires_pg harness pin) in lockstep before merge."
    )
    stale = declared - disk
    assert not stale, (
        f"test_b7c1_control_audit_ddl_blob_pins.py pins DDL not present on disk: {sorted(stale)}. "
        f"A Control-DB DDL was deleted/renamed — repair the guard pins."
    )


# --- INV-B: control-associated harness-pin completeness (independent of INV-A) ----------------------------
def test_inv_b_control_pin_completeness() -> None:
    pins = discover_pins()
    assert len(pins) >= 5, f"expected >=5 reviewed-blob pin occurrences; found {len(pins)} — has requires_pg moved?"
    harnesses, pin_vars = guard_referenced()
    for name, var, _value, is_control in pins:
        if not is_control:
            continue
        assert name in harnesses, (
            f"{name} declares control pin {var} (references the Control-DB DDL dir) but is not in the guard's "
            f"harness set — extend test_b7c1_control_audit_ddl_blob_pins.py to cross-check it."
        )
        assert var in pin_vars, f"{name}:{var} is a control-associated pin not referenced by the blob-drift guard — extend the guard."


# --- INV-C: no silent out-of-scope pin (Control-DB-only scope; conscious review, no value allow-set) ------
def test_inv_c_no_silent_out_of_scope_pin() -> None:
    non_control = [(name, var) for (name, var, _value, is_control) in discover_pins() if not is_control]
    assert non_control == [], (
        f"non-control _REVIEWED_*_BLOB pin(s) discovered: {non_control}. A new requires_pg reviewed pin must be "
        f"consciously classified — register it in this meta-guard (Control-DB-only scope, PRD 06 B-7C-1R2 §6.1)."
    )


# --- Non-vacuity (boundary-safe: tmp_path only; never writes into governed DDL/requires_pg dirs) ----------
def test_nv_inv_a_fails_on_uncovered_ddl(tmp_path: pathlib.Path) -> None:
    (tmp_path / "001_a.sql").write_text("x", encoding="utf-8")
    (tmp_path / "004_probe.sql").write_text("y", encoding="utf-8")
    disk = discover_control_ddls(tmp_path)
    declared = {"001_a.sql"}  # a guard that does NOT cover 004
    assert (disk - declared) == {"004_probe.sql"}  # INV-A forward WOULD fail on this


def test_nv_inv_a_fails_on_deleted_ddl(tmp_path: pathlib.Path) -> None:
    (tmp_path / "001_a.sql").write_text("x", encoding="utf-8")
    disk = discover_control_ddls(tmp_path)
    declared = {"001_a.sql", "002_gone.sql"}  # guard still pins a DDL no longer on disk
    assert (declared - disk) == {"002_gone.sql"}  # INV-A reverse WOULD fail on this


def test_nv_inv_b_fails_on_unaccounted_control_pin(tmp_path: pathlib.Path) -> None:
    probe = tmp_path / "test_pg_probe.py"
    probe.write_text(
        'p = root / "infrastructure" / "db" / "control" / "004_x.sql"\n_REVIEWED_PROBE_BLOB = "' + "0" * 40 + '"\n',
        encoding="utf-8",
    )
    probe_pins = [(name, var, is_control) for (name, var, _value, is_control) in discover_pins(tmp_path)]
    assert probe_pins == [("test_pg_probe.py", "_REVIEWED_PROBE_BLOB", True)]  # discovered + control-associated
    _harnesses, pin_vars = guard_referenced()
    assert "_REVIEWED_PROBE_BLOB" not in pin_vars  # absent from the real guard → INV-B WOULD fail


def test_nv_readme_and_non_sql_excluded(tmp_path: pathlib.Path) -> None:
    (tmp_path / "001_a.sql").write_text("x", encoding="utf-8")
    (tmp_path / "README.md").write_text("doc", encoding="utf-8")
    (tmp_path / "NOTES.txt").write_text("notes", encoding="utf-8")
    assert discover_control_ddls(tmp_path) == {"001_a.sql"}  # README.md / NOTES.txt excluded by *.sql


def _with_tmpdir(fn: Callable[[pathlib.Path], None]) -> Callable[[], None]:
    """Adapt a tmp_path-taking negative-control test to the no-arg ``_scan.run`` standalone driver."""

    def inner() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fn(pathlib.Path(tmp))

    inner.__name__ = getattr(fn, "__name__", "nv")
    return inner


if __name__ == "__main__":
    _scan.run(
        [
            test_inv_a_control_ddl_completeness_bidirectional,
            test_inv_b_control_pin_completeness,
            test_inv_c_no_silent_out_of_scope_pin,
            _with_tmpdir(test_nv_inv_a_fails_on_uncovered_ddl),
            _with_tmpdir(test_nv_inv_a_fails_on_deleted_ddl),
            _with_tmpdir(test_nv_inv_b_fails_on_unaccounted_control_pin),
            _with_tmpdir(test_nv_readme_and_non_sql_excluded),
        ]
    )
