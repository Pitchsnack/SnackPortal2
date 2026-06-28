"""PRD 06 AT2-AR-2 — lineage DDL applier-exclusivity guard (architecture; no PostgreSQL).

The ATR-1 blob-drift guard's lineage cross-check (T6) treats the ``apply_schema()`` tuple in
``tests/lineage_service/requires_pg/_pg.py`` as the AUTHORITATIVE set of lineage DDL the live harnesses apply.
That authority holds only while ``_pg.apply_schema`` is the SOLE place lineage ``requires_pg`` harnesses apply
DDL. If a future lineage harness applied a ``.sql`` directly (bypassing ``apply_schema``), the applied-set
authority would silently fragment and ATR-1 could miss drift.

This guard enforces the invariant: among the lineage ``requires_pg`` harnesses (the ``test_*.py`` files), none
may reference a ``.sql`` file, the lineage DDL directory, or a ``DDL_DIR`` constant directly — DDL application
must route through ``_pg.py::apply_schema`` (``_pg.py`` is the sanctioned applier and is exempt: it is not a
``test_*.py`` file).

Scope: required-CI structural invariant only. Does NOT run PostgreSQL, does NOT prove tenant physical multi-DB
routing, and does NOT close B5-BLK-4. Pure stdlib; imports no database driver; standalone-runnable:

    python tests/architecture/test_lineage_ddl_applier_exclusivity.py
"""

from __future__ import annotations

import pathlib
import re
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_LINEAGE_REQ_PG = _scan.BACKEND_ROOT / "tests" / "lineage_service" / "requires_pg"

_SQL_REF = re.compile(r"\.sql\b")
_LINEAGE_DIR_SEG = re.compile(r'"infrastructure"\s*/\s*"db"\s*/\s*"lineage"')


# --- helpers (stdlib only; no DB) ----------------------------------------------------------------
def _harness_files(req_pg_dir: pathlib.Path) -> list[pathlib.Path]:
    """The lineage requires_pg HARNESSES (test_*.py). _pg.py (the sanctioned applier) is NOT a test_* file."""
    return sorted(req_pg_dir.glob("test_*.py"))


def _violations(harness_text: str) -> list[str]:
    """Direct-DDL-application markers a lineage harness must NOT contain (it must route via _pg.apply_schema)."""
    out: list[str] = []
    if _SQL_REF.search(harness_text):
        out.append(".sql reference")
    if "DDL_DIR" in harness_text:
        out.append("DDL_DIR reference")
    if _LINEAGE_DIR_SEG.search(harness_text) or "infrastructure/db/lineage" in harness_text:
        out.append("lineage DDL dir reference")
    return out


# --- the guard -----------------------------------------------------------------------------------
def test_at2ar2_no_lineage_harness_applies_ddl_directly() -> None:
    harnesses = _harness_files(_LINEAGE_REQ_PG)
    offenders = {h.name: _violations(h.read_text(encoding="utf-8")) for h in harnesses}
    offenders = {name: v for name, v in offenders.items() if v}
    assert not offenders, (
        f"lineage requires_pg harness(es) apply DDL outside _pg.apply_schema: {offenders}. Route lineage DDL "
        f"application through _pg.py::apply_schema so the ATR-1 applied-set cross-check stays authoritative."
    )


def test_at2ar2_harness_discovery_sanity() -> None:
    harnesses = _harness_files(_LINEAGE_REQ_PG)
    assert len(harnesses) >= 4, (
        f"expected >=4 lineage requires_pg harnesses (append_only, chain_serialization, privilege, traversal); "
        f"found {[h.name for h in harnesses]}"
    )


# --- non-vacuity (tempfile only) -----------------------------------------------------------------
def test_nv_direct_sql_reference_detected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        d = pathlib.Path(tmp)
        clean = d / "test_pg_clean.py"
        clean.write_text("import _pg\n_pg.run([])\n", encoding="utf-8")
        bad = d / "test_pg_bad.py"
        bad.write_text('cur.execute(open("001_lineage_schema.sql").read())\n', encoding="utf-8")
        assert _violations(clean.read_text(encoding="utf-8")) == []  # routes via _pg → no violation
        assert _violations(bad.read_text(encoding="utf-8"))  # a direct .sql reference IS flagged
        assert {p.name for p in _harness_files(d)} == {"test_pg_clean.py", "test_pg_bad.py"}


if __name__ == "__main__":
    _scan.run(
        [
            test_at2ar2_no_lineage_harness_applies_ddl_directly,
            test_at2ar2_harness_discovery_sanity,
            test_nv_direct_sql_reference_detected,
        ]
    )
