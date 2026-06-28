"""PRD 06 ATR-4 — provisioning DDL live-harness coverage guard (default suite; no PostgreSQL, no DSN).

The live-PG provisioning harness (``tests/control_plane/requires_pg/test_pg_provisioning_ddl.py``) is
``--ignore``'d by the default suite (pyproject ``addopts``) and runs only in the ADVISORY
``live-pg-durable-path.yml`` workflow (DRIFT-08: not a required check). So nothing in the default suite
would notice if that coverage silently regressed — the harness deleted, a template no longer pinned, or
the harness dropped from the workflow loop. This pure-stdlib guard makes the ATR-4 coverage
CI-visible in the DEFAULT suite. It applies NO DDL and opens NO database connection.

It asserts three structural facts:

* (a) the three provisioning ``.sql`` templates exist on disk;
* (b) the live-PG harness exists and references all three template filenames; and
* (c) the harness is listed in the ``live-pg-durable-path.yml`` run loop.

Scope: ATR-4 coverage visibility only. Does NOT prove the templates are valid (the live harness does
that), does NOT prove tenant physical multi-DB routing, and does NOT close B5-BLK-4.

Pure stdlib; imports no database driver; standalone-runnable:

    python tests/architecture/test_atr4_provisioning_ddl_coverage.py
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_PROVISIONING_DIR = _scan.REPO_ROOT / "infrastructure" / "db" / "provisioning"
_HARNESS = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "test_pg_provisioning_ddl.py"
_WORKFLOW = _scan.REPO_ROOT / ".github" / "workflows" / "live-pg-durable-path.yml"

# The three provisioning templates ATR-4 covers.
_PROVISIONING_SQL = (
    "001_tenant_database.sql",
    "002_distinctness_sentinel.sql",
    "003_provisioning_role.sql",
)
# The harness path as it appears in the workflow loop (relative to the job's backend/ working-directory).
_HARNESS_RELPATH = "tests/control_plane/requires_pg/test_pg_provisioning_ddl.py"

_LOOP_RE = re.compile(r"for\s+h\s+in\s+(?P<loop>.+?);\s*do", re.DOTALL)


# --- pure helpers (no I/O; exercised by the non-vacuity tests below) -----------------------------
def _references_all(text: str, names: tuple[str, ...]) -> bool:
    """True iff `text` mentions every filename in `names`."""
    return all(name in text for name in names)


def _path_in_loop(workflow_text: str, harness_relpath: str) -> bool:
    """True iff `harness_relpath` appears inside the workflow's `for h in … ; do` run loop."""
    m = _LOOP_RE.search(workflow_text)
    if m is None:
        return False
    return harness_relpath in m.group("loop")


# --- (a) the three templates exist --------------------------------------------------------------
def test_atr4_provisioning_ddls_exist() -> None:
    for name in _PROVISIONING_SQL:
        path = _PROVISIONING_DIR / name
        assert path.is_file(), f"provisioning template missing: {path}"
        assert path.read_text(encoding="utf-8").strip(), f"provisioning template is empty: {path}"


# --- (b) the harness exists and references all three templates -----------------------------------
def test_atr4_harness_references_all_three_ddls() -> None:
    assert _HARNESS.is_file(), f"ATR-4 live-PG harness missing: {_HARNESS}"
    src = _HARNESS.read_text(encoding="utf-8")
    missing = [name for name in _PROVISIONING_SQL if name not in src]
    assert not missing, f"ATR-4 harness does not reference provisioning template(s): {missing}"
    assert _references_all(src, _PROVISIONING_SQL)


# --- (c) the harness is in the advisory live-PG workflow run loop --------------------------------
def test_atr4_harness_in_live_pg_workflow_loop() -> None:
    assert _WORKFLOW.is_file(), f"live-pg-durable-path workflow missing: {_WORKFLOW}"
    text = _WORKFLOW.read_text(encoding="utf-8")
    assert _LOOP_RE.search(text) is not None, "could not locate the `for h in … ; do` run loop in the workflow"
    assert _path_in_loop(text, _HARNESS_RELPATH), (
        f"ATR-4 harness '{_HARNESS_RELPATH}' is not listed in the live-pg-durable-path.yml run loop"
    )


# --- non-vacuity: the detection helpers actually FAIL on synthetic regressions -------------------
def test_atr4_nv_reference_check_detects_missing() -> None:
    full = " ".join(_PROVISIONING_SQL)
    assert _references_all(full, _PROVISIONING_SQL) is True  # all present -> True
    partial = f"{_PROVISIONING_SQL[0]} {_PROVISIONING_SQL[1]}"  # 003 omitted
    assert _references_all(partial, _PROVISIONING_SQL) is False  # a missing filename -> False


def test_atr4_nv_loop_check_detects_absent() -> None:
    present = f"for h in \\\n  {_HARNESS_RELPATH} \\\n  other.py ; do\n  echo $h\ndone"
    assert _path_in_loop(present, _HARNESS_RELPATH) is True  # listed -> True
    absent = "for h in \\\n  some_other_harness.py ; do\n  echo $h\ndone"
    assert _path_in_loop(absent, _HARNESS_RELPATH) is False  # not listed -> False
    assert _path_in_loop("no loop here", _HARNESS_RELPATH) is False  # no loop at all -> False


if __name__ == "__main__":
    _scan.run(
        [
            test_atr4_provisioning_ddls_exist,
            test_atr4_harness_references_all_three_ddls,
            test_atr4_harness_in_live_pg_workflow_loop,
            test_atr4_nv_reference_check_detects_missing,
            test_atr4_nv_loop_check_detects_absent,
        ]
    )
