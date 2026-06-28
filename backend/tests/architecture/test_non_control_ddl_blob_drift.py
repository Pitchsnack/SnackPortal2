"""PRD 06 AT-1 + ATR-1 — default-suite blob-drift guards for NON-control DDL (architecture; no PostgreSQL).

The Control-DB DDL has a default-suite blob-drift guard (``test_b7c1_control_audit_ddl_blob_pins.py``) and a
completeness meta-guard (``test_b7c1r2_control_ddl_pin_completeness.py``), but those are **Control-DB only**.
The provisioning and lineage DDL families had no required-suite drift detection:

* **AT-1 (provisioning).** ``infrastructure/db/provisioning/{001,002,003}.sql`` are pinned by the ATR-4
  live-PG harness (``test_pg_provisioning_ddl.py``), but that harness is ``--ignore``'d by the default suite
  and runs only in the ADVISORY live-PG workflow — so a provisioning DDL change can avoid required-CI
  detection.
* **ATR-1 (lineage).** ``infrastructure/db/lineage/{001_lineage_schema,002_append_only,003_roles}.sql`` are
  APPLIED live by ``tests/lineage_service/requires_pg/_pg.py::apply_schema`` (used by all four lineage
  ``requires_pg`` harnesses) but were pinned by **nothing** — there was no blob-drift guard at all.

This pure-stdlib guard runs in the DEFAULT (required) suite and is the SINGLE SOURCE OF TRUTH: it recomputes
the LF-normalized git-blob SHA-1 of each DDL file and asserts (a) it matches the known pin, (b) the guarded
set is directory-complete (a new/renamed/removed ``*.sql`` fails), and (c) it cross-checks the live-PG
references — for provisioning, the harness's scalar pins (``_PROVISIONING_DDL_SHA_001/002/003``); for lineage,
the file set applied by ``_pg.apply_schema``. A DDL revision therefore fails CI here until the pin (and, for
provisioning, the harness pin) is updated in lockstep — no live database required, and the DDL/harness files
are read-only (never applied/modified).

SCOPE. Provisioning + lineage DDL only. Does NOT touch the Control-DB-only B-7C-1R2 meta-guard (kept
Control-DB-only by design). Does NOT prove tenant physical multi-DB routing and does NOT close B5-BLK-4.

Pure stdlib (hashlib/re/pathlib); imports no database driver; standalone-runnable:
  python tests/architecture/test_non_control_ddl_blob_drift.py
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

# --- AT-1: provisioning DDL (db/provisioning) ----------------------------------------------------
_PROVISIONING_DIR = _scan.REPO_ROOT / "infrastructure" / "db" / "provisioning"
_PROVISIONING_HARNESS = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "test_pg_provisioning_ddl.py"
_PROVISIONING_DDL_SHA_BY_FILE = {
    "001_tenant_database.sql": "d3073e82a6b9b5dc3bc9774201c6932c956a6897",
    "002_distinctness_sentinel.sql": "04b1401de262320e140d79f5133051f41ff92693",
    "003_provisioning_role.sql": "2564826cc2d00b63b2edf0c7f88fc2c88bcc853b",
}

# --- ATR-1: lineage DDL (db/lineage) -------------------------------------------------------------
_LINEAGE_DIR = _scan.REPO_ROOT / "infrastructure" / "db" / "lineage"
_LINEAGE_PG = _scan.BACKEND_ROOT / "tests" / "lineage_service" / "requires_pg" / "_pg.py"
_LINEAGE_DDL_SHA_BY_FILE = {
    "001_lineage_schema.sql": "5891b5dbce621bffda2ca15ac29cf6621d1dd725",
    "002_append_only.sql": "e32be83c37ac37c3f3a96a3b008bd1b1b1dc0521",
    "003_roles.sql": "b962d4ca2b0cbfbb9ac1ce0b11e2bdfa4cab6a33",
}

# Harness scalar-pin assignment (the ATR-4 provisioning harness uses _PROVISIONING_DDL_SHA_00N = "<40hex>").
_PROV_SCALAR_PIN = re.compile(r'_PROVISIONING_DDL_SHA_(\d{3})\s*=\s*"([0-9a-f]{40})"')
# The apply_schema() tuple literal in the lineage live-PG runner: `for name in ( "...sql", ... ):`.
_APPLY_TUPLE = re.compile(r"for\s+name\s+in\s+\((?P<body>.*?)\)\s*:", re.DOTALL)


# --- helpers (stdlib only; no DB) ----------------------------------------------------------------
def _git_blob_sha1(path: pathlib.Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")  # autocrlf normalization (the git blob is LF)
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _sql_filenames(directory: pathlib.Path) -> set[str]:
    """The ``*.sql`` basenames in a directory (README.md / non-.sql excluded by the glob)."""
    return {p.name for p in directory.glob("*.sql")}


def _provisioning_scalar_pins(harness_text: str) -> dict[str, str]:
    """{"001": sha, "002": sha, "003": sha} parsed from the ATR-4 harness's _PROVISIONING_DDL_SHA_00N lines."""
    return {m.group(1): m.group(2) for m in _PROV_SCALAR_PIN.finditer(harness_text)}


def _applied_lineage_sql(pg_text: str) -> list[str]:
    """The ``*.sql`` filenames the lineage runner's apply_schema() for-loop applies (in source order)."""
    m = _APPLY_TUPLE.search(pg_text)
    if m is None:
        return []
    return re.findall(r'"([^"]+\.sql)"', m.group("body"))


# --- AT-1: provisioning blob-drift ---------------------------------------------------------------
def test_at1_provisioning_ddl_blobs_match_pins() -> None:
    for name, pin in _PROVISIONING_DDL_SHA_BY_FILE.items():
        actual = _git_blob_sha1(_PROVISIONING_DIR / name)
        assert actual == pin, (
            f"provisioning DDL {name} drifted from pin {pin} (got {actual}); a governed DDL change must update "
            f"this guard AND the test_pg_provisioning_ddl.py _PROVISIONING_DDL_SHA_* pin in lockstep"
        )


def test_at1_provisioning_ddl_directory_complete() -> None:
    on_disk = _sql_filenames(_PROVISIONING_DIR)
    pinned = set(_PROVISIONING_DDL_SHA_BY_FILE)
    assert on_disk == pinned, (
        f"provisioning DDL set on disk {sorted(on_disk)} != pinned {sorted(pinned)}; a new/renamed/removed "
        f".sql must be pinned here (and in the harness) before merge"
    )


def test_at1_provisioning_harness_pins_match_current_blobs() -> None:
    pins = _provisioning_scalar_pins(_PROVISIONING_HARNESS.read_text(encoding="utf-8"))
    assert set(pins) == {"001", "002", "003"}, (
        f"test_pg_provisioning_ddl.py must pin _PROVISIONING_DDL_SHA_001/002/003; found {sorted(pins)}"
    )
    for name, pin in _PROVISIONING_DDL_SHA_BY_FILE.items():
        num = name[:3]
        actual = _git_blob_sha1(_PROVISIONING_DIR / name)
        assert pins[num] == actual == pin, (
            f"single-source-of-truth mismatch for {name}: harness pin {pins[num]}, guard pin {pin}, current blob {actual} must all be equal"
        )


# --- ATR-1: lineage blob-drift -------------------------------------------------------------------
def test_atr1_lineage_ddl_blobs_match_pins() -> None:
    for name, pin in _LINEAGE_DDL_SHA_BY_FILE.items():
        actual = _git_blob_sha1(_LINEAGE_DIR / name)
        assert actual == pin, (
            f"lineage DDL {name} drifted from pin {pin} (got {actual}); a governed DDL change must update this "
            f"guard in lockstep (lineage DDL is applied live by tests/lineage_service/requires_pg/_pg.py)"
        )


def test_atr1_lineage_ddl_directory_complete() -> None:
    on_disk = _sql_filenames(_LINEAGE_DIR)
    pinned = set(_LINEAGE_DDL_SHA_BY_FILE)
    assert on_disk == pinned, (
        f"lineage DDL set on disk {sorted(on_disk)} != pinned {sorted(pinned)}; a new/renamed/removed .sql must be pinned here before merge"
    )


def test_atr1_lineage_applied_set_matches_pins() -> None:
    applied = _applied_lineage_sql(_LINEAGE_PG.read_text(encoding="utf-8"))
    assert applied, "could not parse the apply_schema() for-loop tuple in lineage requires_pg/_pg.py"
    assert set(applied) == set(_LINEAGE_DDL_SHA_BY_FILE), (
        f"lineage applied-set {sorted(set(applied))} (from _pg.apply_schema) != pinned set "
        f"{sorted(_LINEAGE_DDL_SHA_BY_FILE)}; pin exactly the DDL the live harness applies (both directions)"
    )


# --- non-vacuity: the helpers actually FAIL on synthetic drift / extra / missing (tempfile only) --
def test_nv_blob_and_completeness_helpers() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        d = pathlib.Path(tmp)
        (d / "001_x.sql").write_text("CREATE TABLE x();\n", encoding="utf-8")
        (d / "002_y.sql").write_text("CREATE TABLE y();\n", encoding="utf-8")
        (d / "README.md").write_text("doc", encoding="utf-8")
        assert _sql_filenames(d) == {"001_x.sql", "002_y.sql"}  # README excluded; both .sql found
        good = _git_blob_sha1(d / "001_x.sql")
        assert re.fullmatch(r"[0-9a-f]{40}", good)  # a real 40-hex blob SHA
        assert good != "0" * 40  # a corrupted pin would NOT match -> blob test WOULD fail
        # completeness: an extra unpinned file makes on_disk != pinned
        pinned = {"001_x.sql", "002_y.sql"}
        (d / "003_extra.sql").write_text("CREATE TABLE z();\n", encoding="utf-8")
        assert _sql_filenames(d) != pinned  # extra .sql -> directory-completeness WOULD fail


def test_nv_provisioning_scalar_pin_parse() -> None:
    snippet = '_PROVISIONING_DDL_SHA_001 = "' + "a" * 40 + '"\n_PROVISIONING_DDL_SHA_002 = "' + "b" * 40 + '"\n'
    parsed = _provisioning_scalar_pins(snippet)
    assert parsed == {"001": "a" * 40, "002": "b" * 40}  # parses present pins
    assert "003" not in _provisioning_scalar_pins("no pins here")  # absent -> cross-check WOULD fail


def test_nv_lineage_applied_set_parse() -> None:
    good = 'for name in ("001_lineage_schema.sql", "002_append_only.sql", "003_roles.sql"):'
    assert _applied_lineage_sql(good) == ["001_lineage_schema.sql", "002_append_only.sql", "003_roles.sql"]
    drifted = 'for name in ("001_lineage_schema.sql", "999_new.sql"):'
    assert set(_applied_lineage_sql(drifted)) != set(_LINEAGE_DDL_SHA_BY_FILE)  # mismatch -> T6 WOULD fail
    assert _applied_lineage_sql("no for-loop") == []  # unparseable -> T6 WOULD fail (empty)


if __name__ == "__main__":
    _scan.run(
        [
            test_at1_provisioning_ddl_blobs_match_pins,
            test_at1_provisioning_ddl_directory_complete,
            test_at1_provisioning_harness_pins_match_current_blobs,
            test_atr1_lineage_ddl_blobs_match_pins,
            test_atr1_lineage_ddl_directory_complete,
            test_atr1_lineage_applied_set_matches_pins,
            test_nv_blob_and_completeness_helpers,
            test_nv_provisioning_scalar_pin_parse,
            test_nv_lineage_applied_set_parse,
        ]
    )
