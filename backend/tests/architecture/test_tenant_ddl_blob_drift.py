"""PRD 07C V5 — default-suite blob-drift guard for the TENANT business DDL family (architecture; no PostgreSQL).

PRD 07C V5 introduces ``infrastructure/db/tenant/`` — the tenant business schema applied to every physical
tenant database (agents + System Primary constraints, ai_agents, startups, investors, deals, ownership,
links). This pure-stdlib guard runs in the DEFAULT (required) suite and is the SINGLE SOURCE OF TRUTH for
that family: it recomputes the LF-normalized git-blob SHA-1 of each tenant DDL file and asserts (a) each
matches its known pin, (b) the guarded set is directory-complete in BOTH directions (a new/renamed/removed
``*.sql`` fails), (c) the ORDERED apply list below matches the pinned set — this list is the machine-readable
apply-order authority PRD 07B.1 later sequences into ``default_tenant_schema_ddl_paths()`` — and (d) the
07C live-PG harness (``test_pg_tenant_business_schema_07c.py``) pins the SAME blobs under its
``_TENANT_BLOB_NNN`` scalar pins and applies the SAME files in the SAME order. A tenant DDL revision
therefore fails CI here until guard + harness pins move in lockstep.

NAMING RULE (07C V5 §13.D): the harness's tenant pins are deliberately named ``_TENANT_BLOB_NNN`` — NOT
``_REVIEWED_*_BLOB`` — because ``test_b7c1r2_control_ddl_pin_completeness.py`` scans all of
``tests/control_plane/requires_pg`` for ``_REVIEWED_[A-Z0-9]+_BLOB`` pins with per-FILE control-association,
and the 07C harness references the Control DDL directory (it applies MCC 001-007 for the registry proof).
``_TENANT_BLOB_*`` keeps the tenant pins invisible to the Control-DB-only meta-guard, so b7c1r2 and the
control blob-pin guard stay untouched.

SCOPE. Tenant DDL family only. Registered in the cross-family coverage meta-guard as
``_COVERAGE["tenant"]``. Does NOT touch the Control-DB guards; does NOT prove tenant physical multi-DB
routing; does NOT close B5-BLK-4. Pure stdlib; imports no database driver; standalone-runnable:
  python tests/architecture/test_tenant_ddl_blob_drift.py
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_TENANT_DIR = _scan.REPO_ROOT / "infrastructure" / "db" / "tenant"
_HARNESS = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "test_pg_tenant_business_schema_07c.py"

# The machine-readable ORDERED apply authority (07C V5 §8/§10): 07B.1 sequences exactly this list, in this
# order, after the six existing 07B templates. Order is load-bearing (FK dependencies: agents <- ai_agents
# <- entities <- ownership <- links).
TENANT_DDL_APPLY_ORDER = [
    "001_agents.sql",
    "002_ai_agents.sql",
    "003_startups.sql",
    "004_investors.sql",
    "005_deals.sql",
    "006_ownership.sql",
    "007_links.sql",
]

# Reviewed LF-normalized git-blob SHA-1 pins (PRD 07C V5). A governed DDL change must update these AND the
# harness's _TENANT_BLOB_NNN pins in lockstep.
_TENANT_DDL_SHA_BY_FILE = {
    "001_agents.sql": "34805052d5f860aebde5c7d9b2f6ac71d5130550",
    "002_ai_agents.sql": "71d4c9dbceea10a42d728b0186b601d42ae53050",
    "003_startups.sql": "8cc12ea25a1ed8df1e482b34dfcbc2f5bad4163e",
    "004_investors.sql": "07015fd6a1c63629e0f682e79c03705f5e69ea3f",
    "005_deals.sql": "22e91ab26ecf4ff33752f12ba1421ec31d4f7bbc",
    "006_ownership.sql": "d5dd83548543538df97ac75527af2a37127325d3",
    "007_links.sql": "ea1c8a911df5023e5f5902b591ee44b91790b06c",
}

# Harness scalar-pin assignment style: _TENANT_BLOB_001 = "<40hex>" (NOT _REVIEWED_* — see NAMING RULE).
_TENANT_SCALAR_PIN = re.compile(r'_TENANT_BLOB_(\d{3})\s*=\s*"([0-9a-f]{40})"')
# Tenant DDL filename literals as they appear in the harness's ordered apply list.
_TENANT_SQL_LITERAL = re.compile(r'"(00[0-9]_[a-z_]+\.sql)"')


# --- helpers (stdlib only; no DB) ----------------------------------------------------------------
def _git_blob_sha1(path: pathlib.Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")  # autocrlf normalization (the git blob is LF)
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _sql_filenames(directory: pathlib.Path) -> set[str]:
    """The ``*.sql`` basenames in a directory (README.md / non-.sql excluded by the glob)."""
    return {p.name for p in directory.glob("*.sql")}


def _harness_scalar_pins(harness_text: str) -> dict[str, str]:
    """{"001": sha, ...} parsed from the 07C harness's _TENANT_BLOB_NNN assignment lines."""
    return {m.group(1): m.group(2) for m in _TENANT_SCALAR_PIN.finditer(harness_text)}


def _harness_apply_order(harness_text: str) -> list[str]:
    """TENANT DDL filenames in first-appearance order in the harness source (its ordered apply list).

    Filtered to the pinned tenant set: the harness also names CONTROL DDL literals (it applies MCC
    001-007 unpinned for the registry proof) and those must not pollute the order comparison."""
    known = set(_TENANT_DDL_SHA_BY_FILE)
    seen: list[str] = []
    for m in _TENANT_SQL_LITERAL.finditer(harness_text):
        name = m.group(1)
        if name in known and name not in seen:
            seen.append(name)
    return seen


# --- T1: blob pins -------------------------------------------------------------------------------
def test_tenant_ddl_blobs_match_pins() -> None:
    for name, pin in _TENANT_DDL_SHA_BY_FILE.items():
        actual = _git_blob_sha1(_TENANT_DIR / name)
        assert actual == pin, (
            f"tenant DDL {name} drifted from pin {pin} (got {actual}); a governed DDL change must update "
            f"this guard AND the test_pg_tenant_business_schema_07c.py _TENANT_BLOB_* pin in lockstep"
        )


# --- T2: bidirectional directory completeness ----------------------------------------------------
def test_tenant_ddl_directory_complete_bidirectional() -> None:
    on_disk = _sql_filenames(_TENANT_DIR)
    pinned = set(_TENANT_DDL_SHA_BY_FILE)
    assert on_disk == pinned, (
        f"tenant DDL set on disk {sorted(on_disk)} != pinned {sorted(pinned)}; a new/renamed/removed .sql "
        f"must be pinned here (and in the harness) before merge"
    )


# --- T3: the ordered apply authority is internally consistent ------------------------------------
def test_tenant_ddl_apply_order_matches_pinned_set() -> None:
    assert len(TENANT_DDL_APPLY_ORDER) == len(set(TENANT_DDL_APPLY_ORDER)), "apply order must not repeat files"
    assert set(TENANT_DDL_APPLY_ORDER) == set(_TENANT_DDL_SHA_BY_FILE), (
        f"apply order {TENANT_DDL_APPLY_ORDER} and pinned set {sorted(_TENANT_DDL_SHA_BY_FILE)} must cover "
        f"the same files — the order list is the 07B.1 sequencing authority"
    )
    assert TENANT_DDL_APPLY_ORDER == sorted(TENANT_DDL_APPLY_ORDER), (
        "apply order must be the numeric filename order (001..007) — renumber consciously if this ever changes"
    )


# --- T4: harness pins match current blobs (single source of truth) -------------------------------
def test_harness_tenant_pins_match_current_blobs() -> None:
    text = _HARNESS.read_text(encoding="utf-8")
    pins = _harness_scalar_pins(text)
    expected_nums = {name[:3] for name in _TENANT_DDL_SHA_BY_FILE}
    assert set(pins) == expected_nums, (
        f"test_pg_tenant_business_schema_07c.py must pin _TENANT_BLOB_{{{sorted(expected_nums)}}}; found {sorted(pins)}"
    )
    for name, pin in _TENANT_DDL_SHA_BY_FILE.items():
        num = name[:3]
        actual = _git_blob_sha1(_TENANT_DIR / name)
        assert pins[num] == actual == pin, (
            f"single-source-of-truth mismatch for {name}: harness pin {pins[num]}, guard pin {pin}, current blob {actual} must all be equal"
        )


# --- T5: harness applies the same files in the same order ----------------------------------------
def test_harness_apply_order_matches_authority() -> None:
    applied = _harness_apply_order(_HARNESS.read_text(encoding="utf-8"))
    assert applied == TENANT_DDL_APPLY_ORDER, (
        f"harness tenant apply order {applied} != guard authority {TENANT_DDL_APPLY_ORDER}; "
        f"07B.1 sequencing depends on ONE order — fix whichever side drifted"
    )


# --- non-vacuity (tempfile only; never writes into governed dirs) --------------------------------
def test_nv_blob_and_completeness_helpers() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        d = pathlib.Path(tmp)
        (d / "001_a.sql").write_text("CREATE TABLE a();\n", encoding="utf-8")
        (d / "README.md").write_text("doc", encoding="utf-8")
        assert _sql_filenames(d) == {"001_a.sql"}  # README excluded
        good = _git_blob_sha1(d / "001_a.sql")
        assert re.fullmatch(r"[0-9a-f]{40}", good) and good != "0" * 40  # a corrupted pin WOULD fail T1
        (d / "008_extra.sql").write_text("CREATE TABLE z();\n", encoding="utf-8")
        assert _sql_filenames(d) != {"001_a.sql"}  # an extra unpinned .sql WOULD fail T2


def test_nv_harness_parsers() -> None:
    snippet = '_TENANT_BLOB_001 = "' + "a" * 40 + '"\nx = ("001_agents.sql", "002_ai_agents.sql")\n'
    assert _harness_scalar_pins(snippet) == {"001": "a" * 40}  # parses present pins; absent nums WOULD fail T4
    assert _harness_apply_order(snippet) == ["001_agents.sql", "002_ai_agents.sql"]  # order = first appearance
    assert _harness_apply_order("no filenames") == []  # unparseable WOULD fail T5
    mixed = 'c = ("001_distinctness_ledger.sql",)\nt = ("001_agents.sql",)\n'
    assert _harness_apply_order(mixed) == ["001_agents.sql"]  # CONTROL literals are filtered out


if __name__ == "__main__":
    _scan.run(
        [
            test_tenant_ddl_blobs_match_pins,
            test_tenant_ddl_directory_complete_bidirectional,
            test_tenant_ddl_apply_order_matches_pinned_set,
            test_harness_tenant_pins_match_current_blobs,
            test_harness_apply_order_matches_authority,
            test_nv_blob_and_completeness_helpers,
            test_nv_harness_parsers,
        ]
    )
