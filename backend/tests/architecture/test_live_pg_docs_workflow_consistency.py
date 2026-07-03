"""PRD 06 AT-5 — live-PG docs ↔ workflow consistency guard (default suite; no PostgreSQL, no DSN).

The advisory ``live-pg-durable-path.yml`` workflow runs a fixed set of ``requires_pg`` durable-path
harnesses in a ``for h in … ; do`` loop. Two runtime docs describe that set in prose
(``docs/runtime/b7c2_live_pg_durable_path_ci.md`` — the run-set "What it runs" section — and
``docs/runtime/atr4_provisioning_ddl_live_harness_coverage.md`` — the ATR-4 follow-up note). Nothing kept
the prose tied to the workflow, so the docs drifted: they described an *8-harness* set with provisioning
"applied by no harness" and lineage "ATR-1 remains OPEN", all stale after PR #30/#31 and ATR-4 raised the
loop to **9** and closed those gaps.

This pure-stdlib guard makes the docs↔workflow consistency CI-visible in the DEFAULT suite. It applies NO
DDL, opens NO database connection, imports NO driver, and **only reads** the workflow file (never edits it).

Asserted facts:

* **T1** — the workflow loop parses; it has exactly ``EXPECTED_HARNESS_COUNT`` (9) harness entries; the
  provisioning harness is one of them; and ``test_b3a`` is NOT an active loop entry (it is the physical
  multi-DB topology proof, excluded by design — it appears only in workflow *comments*).
* **T2** — the ``b7c2`` documented ``Run set (N harnesses)`` count equals the *parsed* workflow loop count
  (the count is tied to the workflow, not hard-coded in the doc).
* **T3** — the ``b7c2`` "What it runs" section lists the provisioning harness filename.
* **T4** — the ``b7c2`` "What it does NOT do" section no longer presents the stale current-state claims
  (``ATR-1 remains OPEN`` / provisioning ``applied by no harness``).
* **T5** — the ``atr4`` F-1 note no longer frames the ``b7c2`` "8 harnesses" wording as current truth, and
  carries a ``reconciled by AT-5`` marker.

Trap avoidance (the AT-5 design pins):

* The provisioning-present check overlaps ``test_atr4_provisioning_ddl_coverage.py`` (which also asserts the
  harness is in the loop). It is retained here for self-containment; ATR-4's guard is the authority for that
  single fact and is NOT modified. This guard's *new* value is the structural **count**, the **b3a-exclusion**
  (loop-scoped), and the **docs↔workflow count consistency**.
* The ``b3a`` check is scoped to the loop GROUP, not the whole file (b3a is named in workflow comments).
* Negative doc checks are section-scoped and whitespace-normalized, NEVER a blanket grep — so legitimate
  historical wording (e.g. ATR-4's "8 → 9" transition) is not false-flagged.
* Workflow parsing is structural (reuses the proven ``for h in … ; do`` loop regex), never line-number based.

Scope: AT-5 consistency visibility only. Does NOT prove tenant physical multi-DB routing, does NOT change the
live-PG workflow, and does NOT close B5-BLK-4. Pure stdlib; standalone-runnable:

    python tests/architecture/test_live_pg_docs_workflow_consistency.py
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_WORKFLOW = _scan.REPO_ROOT / ".github" / "workflows" / "live-pg-durable-path.yml"
_B7C2 = _scan.REPO_ROOT / "docs" / "runtime" / "b7c2_live_pg_durable_path_ci.md"
_ATR4 = _scan.REPO_ROOT / "docs" / "runtime" / "atr4_provisioning_ddl_live_harness_coverage.md"

# Reviewed expectation. A legitimate future change to the harness set must update the workflow, the b7c2
# "Run set (N harnesses)" prose, AND this constant in lockstep (same discipline as the blob-drift guards).
# 9 → 12 by the Governed CI Live-PG Bundle (adds 07B-e2e + MCC + 07C harnesses to the loop).
EXPECTED_HARNESS_COUNT = 12
# Full loop path (workflow loop) and bare filename (doc run-set prose).
_PROVISIONING_RELPATH = "tests/control_plane/requires_pg/test_pg_provisioning_ddl.py"
_PROVISIONING_FILENAME = "test_pg_provisioning_ddl.py"

# SAME idiom as test_atr4_provisioning_ddl_coverage.py (reused, not edited).
_LOOP_RE = re.compile(r"for\s+h\s+in\s+(?P<loop>.+?);\s*do", re.DOTALL)
_ENTRY_RE = re.compile(r"\S+\.py")
_RUNSET_RE = re.compile(r"Run set\s*\(\s*(\d+)\s*harnesses\s*\)")

# Stale current-state phrases that AT-5 reconciled (whitespace-normalized, markdown emphasis stripped).
_STALE_B7C2_NOT_SECTION = ("ATR-1 remains OPEN", "applied by no harness")
_STALE_ATR4_FRAMING = "still says the run set is 8 harnesses"
_ATR4_RECONCILED_MARKER = "reconciled by AT-5"


# --- pure helpers (no I/O; exercised by the non-vacuity tests) ------------------------------------
def _loop_text(workflow_text: str) -> str | None:
    """Return the text inside the workflow's ``for h in … ; do`` loop, or None if absent."""
    m = _LOOP_RE.search(workflow_text)
    return m.group("loop") if m else None


def _entries(loop_text: str) -> list[str]:
    """Harness path tokens (``\\S+\\.py``) inside a loop body."""
    return _ENTRY_RE.findall(loop_text)


def _runset_count(doc_text: str) -> int | None:
    """The N in a documented ``Run set (N harnesses)``, or None if absent."""
    m = _RUNSET_RE.search(doc_text)
    return int(m.group(1)) if m else None


def _section(text: str, header: str) -> str:
    """Body of the markdown ``## <header>`` section up to the next ``## `` (or EOF). '' if not found."""
    pat = re.compile(
        r"^##\s+" + re.escape(header) + r"\s*$(?P<body>.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pat.search(text)
    return m.group("body") if m else ""


def _norm(s: str) -> str:
    """Collapse whitespace and strip markdown bold so wrapped/emphasized prose matches plain phrases."""
    return re.sub(r"\s+", " ", s.replace("**", ""))


# --- T1: workflow loop is structurally 9, provisioning in, b3a out --------------------------------
def test_t1_workflow_loop_is_nine_with_provisioning_no_b3a() -> None:
    assert _WORKFLOW.is_file(), f"live-pg-durable-path workflow missing: {_WORKFLOW}"
    loop = _loop_text(_WORKFLOW.read_text(encoding="utf-8"))
    assert loop is not None, "could not locate the `for h in … ; do` run loop in the workflow"
    entries = _entries(loop)
    assert len(entries) == EXPECTED_HARNESS_COUNT, (
        f"live-PG workflow loop has {len(entries)} harness entries, expected {EXPECTED_HARNESS_COUNT}: {entries}"
    )
    assert _PROVISIONING_RELPATH in entries, (
        f"provisioning harness '{_PROVISIONING_RELPATH}' not in the live-PG workflow loop (overlaps ATR-4's guard)"
    )
    b3a = [e for e in entries if "test_b3a" in e]
    assert not b3a, f"test_b3a must NOT be an active live-PG loop entry (it is the excluded topology proof): {b3a}"


# --- T2: b7c2 documented count == parsed workflow count -------------------------------------------
def test_t2_b7c2_runset_count_matches_workflow() -> None:
    loop = _loop_text(_WORKFLOW.read_text(encoding="utf-8"))
    assert loop is not None
    workflow_count = len(_entries(loop))
    doc_count = _runset_count(_B7C2.read_text(encoding="utf-8"))
    assert doc_count is not None, "b7c2 doc has no `Run set (N harnesses)` marker to tie to the workflow"
    assert doc_count == workflow_count, (
        f"b7c2 documents 'Run set ({doc_count} harnesses)' but the live-PG workflow loop has {workflow_count} "
        f"entries — docs and workflow have drifted; reconcile b7c2."
    )


# --- T3: b7c2 'What it runs' section lists the provisioning harness -------------------------------
def test_t3_b7c2_runs_section_lists_provisioning() -> None:
    section = _section(_B7C2.read_text(encoding="utf-8"), "What it runs")
    assert section, "b7c2 '## What it runs' section not found"
    assert _PROVISIONING_FILENAME in section, (
        f"b7c2 'What it runs' run-set does not list the provisioning harness '{_PROVISIONING_FILENAME}'"
    )


# --- T4: b7c2 'What it does NOT do' carries no stale current-state claims -------------------------
def test_t4_b7c2_not_section_has_no_stale_current_claims() -> None:
    section = _norm(_section(_B7C2.read_text(encoding="utf-8"), "What it does NOT do"))
    assert section, "b7c2 '## What it does NOT do' section not found"
    present = [p for p in _STALE_B7C2_NOT_SECTION if p in section]
    assert not present, (
        f"b7c2 'What it does NOT do' still presents stale current-state claim(s) {present}; AT-5 reconciled "
        f"these (ATR-1 closed by PR #31; provisioning applied by test_pg_provisioning_ddl.py)."
    )


# --- T5: atr4 F-1 note reconciled (no stale 'still says 8' framing; has the AT-5 marker) ----------
def test_t5_atr4_f1_note_reconciled() -> None:
    atr4 = _norm(_ATR4.read_text(encoding="utf-8"))
    assert _STALE_ATR4_FRAMING not in atr4, (
        f"atr4 F-1 note still frames b7c2 as current-stale ('{_STALE_ATR4_FRAMING}') — reconcile it to AT-5."
    )
    assert _ATR4_RECONCILED_MARKER in atr4, f"atr4 F-1 note lacks a '{_ATR4_RECONCILED_MARKER}' marker after reconciliation"


# --- non-vacuity (synthetic strings ONLY; never mutate a tracked file) ----------------------------
def test_nv_count_detects_eight_entry_loop() -> None:  # RED-AT5-1
    eight = "for h in \\\n  " + " \\\n  ".join(f"a{i}.py" for i in range(8)) + " ; do\n done"
    assert len(_entries(_loop_text(eight) or "")) == 8  # an 8-entry loop is detected as != 9


def test_nv_detects_missing_provisioning() -> None:  # RED-AT5-2
    loop = "for h in \\\n  tests/x/test_other.py \\\n  tests/y/test_more.py ; do\n done"
    assert _PROVISIONING_RELPATH not in _entries(_loop_text(loop) or "")  # absence is detectable


def test_nv_detects_injected_b3a() -> None:  # RED-AT5-3
    loop = (
        "for h in \\\n  tests/control_plane/requires_pg/test_pg_distinctness.py \\\n"
        "  tests/control_plane/requires_pg/test_b3a_multi_database_topology.py ; do\n done"
    )
    entries = _entries(_loop_text(loop) or "")
    assert any("test_b3a" in e for e in entries)  # an injected b3a loop entry is detectable


def test_nv_runset_mismatch_detected() -> None:  # RED-AT5-4
    assert _runset_count("**Run set (8 harnesses):**") == 8  # a doc claiming 8 is read as 8 -> mismatches a 9-loop
    assert _runset_count("no run set here") is None


def test_nv_atr1_stale_claim_detected() -> None:  # RED-AT5-5
    stale = _norm("- ... still **no blob-drift guard** for it — **ATR-1 remains OPEN and tracked, not fixed**.")
    assert any(p in stale for p in _STALE_B7C2_NOT_SECTION)  # the reintroduced stale claim is caught by T4


def test_nv_historical_wording_not_flagged() -> None:  # RED-AT5-6
    historical = _norm(
        "Historical note: before ATR-4 the live-PG run loop had **8 harnesses** (the 8 → 9 transition). "
        "This is **superseded**; the current set is 9."
    )
    # Legitimate historical "8 harnesses" / "8 → 9" wording trips neither the T4 stale-claim set nor the T5 framing.
    assert not any(p in historical for p in _STALE_B7C2_NOT_SECTION)
    assert _STALE_ATR4_FRAMING not in historical


if __name__ == "__main__":
    _scan.run(
        [
            test_t1_workflow_loop_is_nine_with_provisioning_no_b3a,
            test_t2_b7c2_runset_count_matches_workflow,
            test_t3_b7c2_runs_section_lists_provisioning,
            test_t4_b7c2_not_section_has_no_stale_current_claims,
            test_t5_atr4_f1_note_reconciled,
            test_nv_count_detects_eight_entry_loop,
            test_nv_detects_missing_provisioning,
            test_nv_detects_injected_b3a,
            test_nv_runset_mismatch_detected,
            test_nv_atr1_stale_claim_detected,
            test_nv_historical_wording_not_flagged,
        ]
    )
