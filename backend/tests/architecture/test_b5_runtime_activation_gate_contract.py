"""PRD 06 B-5 — activation-gate CONTRACT guard (text-inspection only; no runtime, no driver import).

Asserts the B-5 gate ARTIFACTS exist and commit to a fail-closed, references-only posture. B-5-specific only: secret /
*_REF hygiene for the .template is ALREADY enforced by test_no_secret_literals (test_templates_reference_only + the
pattern scan over infrastructure/**), so this test does not duplicate it. Text inspection only — no static
database-driver import (string literals naming paths are not imports). Pure stdlib; standalone-runnable:
  python tests/architecture/test_b5_runtime_activation_gate_contract.py
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_TEMPLATE = _scan.REPO_ROOT / "infrastructure" / "runtime" / "b5_activation_gate.template"
_DOCS = [
    "b5_production_runtime_activation_gate.md",
    "b5_activation_blockers.md",
    "b5_activation_evidence_template.md",
    "b5_runtime_readiness_matrix.md",
]
_BLOCKER_IDS = [f"B5-BLK-{i}" for i in range(1, 10)]
_FORBIDDEN_DIRS = (
    "infrastructure/db/",
    "infrastructure/iac/",
    "infrastructure/docker/",
    "infrastructure/env/",
)


def test_activation_gate_template_exists_and_disabled_by_default() -> None:
    assert _TEMPLATE.is_file(), "infrastructure/runtime/b5_activation_gate.template must exist"
    text = _TEMPLATE.read_text(encoding="utf-8")
    assert "RUNTIME_ACTIVATION_ENABLED=false" in text, "activation switch must be present and false by default"


def test_activation_gate_template_location() -> None:
    rel = _TEMPLATE.relative_to(_scan.REPO_ROOT).as_posix()
    assert rel.startswith("infrastructure/runtime/"), rel
    for forbidden in _FORBIDDEN_DIRS:
        assert not rel.startswith(forbidden), f"runtime template must not live under {forbidden}"


def test_b5_runtime_docs_exist() -> None:
    base = _scan.REPO_ROOT / "docs" / "runtime"
    for name in _DOCS:
        assert (base / name).is_file(), f"missing B-5 doc: docs/runtime/{name}"


def test_blocker_register_is_not_ready_by_default() -> None:
    reg = (_scan.REPO_ROOT / "docs" / "runtime" / "b5_activation_blockers.md").read_text(encoding="utf-8")
    assert "NOT READY" in reg, "blocker register must commit a NOT READY posture"
    for blocker_id in _BLOCKER_IDS:
        assert blocker_id in reg, f"blocker register must list {blocker_id}"


# ---------------------------------------------------------------------------
# B5-D re-grounding guards (2026-07-12). The three B5 runtime gate documents
# were re-grounded from the stale baseline 9684919 to the verified main
# fff215b… after the B5-1..B5-5 / B5-4A / Smoke C V2 (Fix R3) arc merged. Each
# guard below rejects a specific stale/overclaim regression (PRD B5-D §12); each
# is paired with a planted NON-VACUITY companion proving the guard's detection
# logic actually fires on the mutation it forbids (so the guard cannot silently
# pass by inspecting the wrong text). Text inspection only — no runtime, no
# driver import. The four pins above are unchanged.
# ---------------------------------------------------------------------------

_RUNTIME_DIR = _scan.REPO_ROOT / "docs" / "runtime"
_GATE_DOC = _RUNTIME_DIR / "b5_production_runtime_activation_gate.md"
_BLOCKERS_DOC = _RUNTIME_DIR / "b5_activation_blockers.md"
_MATRIX_DOC = _RUNTIME_DIR / "b5_runtime_readiness_matrix.md"
_GATE_DOCS = (_GATE_DOC, _BLOCKERS_DOC, _MATRIX_DOC)

_CURRENT_BASELINE = "fff215b5bd004760ea0d81915c3d93ca128673ed"
_STALE_BASELINE = "9684919"
_IC002_STATES = (
    "Registered",
    "Provisioning",
    "Verifying",
    "Ready",
    "Suspended",
    "Failed",
    "Quarantined",
    "Decommissioned",
)


def _gate_docs_text() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in _GATE_DOCS)


# --- G1: baseline re-grounded (reject reversion to 9684919) -----------------
def _has_stale_baseline(text: str) -> bool:
    return _STALE_BASELINE in text


def _has_current_baseline(text: str) -> bool:
    return _CURRENT_BASELINE in text


def test_b5d_01_baseline_regrounded() -> None:
    t = _gate_docs_text()
    assert not _has_stale_baseline(t), "stale baseline 9684919 must not reappear in the B5 gate docs"
    assert _has_current_baseline(t), "current baseline fff215b… must be recorded"


def test_b5d_01_baseline_nonvacuity() -> None:
    assert _has_stale_baseline("Baseline: origin/main @ 9684919"), "guard must detect a reverted baseline"
    assert not _has_current_baseline("Baseline: origin/main @ 9684919")


# --- G2: IC-002 eight-state lifecycle (reject reversion to seven) -----------
_STALE_STATE_DESCRIPTORS = ("7-state", "seven-state", "7 states", "seven states")


def _describes_seven_states(text: str) -> bool:
    low = text.lower()
    return any(d in low for d in _STALE_STATE_DESCRIPTORS)


def _describes_eight_states(text: str) -> bool:
    low = text.lower()
    return "eight-state" in low or "eight authoritative states" in low or "ic-002 8 states" in low


def test_b5d_02_ic002_eight_state() -> None:
    t = _gate_docs_text()
    assert not _describes_seven_states(t), "IC-002 must not be described as a seven/7-state lifecycle"
    assert _describes_eight_states(t), "IC-002 must be recorded as the eight-state lifecycle"
    gate = _GATE_DOC.read_text(encoding="utf-8")
    for state in _IC002_STATES:
        assert state in gate, f"IC-002 authoritative state name missing from the gate doc: {state}"


def test_b5d_02_ic002_nonvacuity() -> None:
    assert _describes_seven_states("IC-002 seven-state lifecycle")
    assert _describes_seven_states("control-plane signals (IC-002 7 states)")
    assert not _describes_eight_states("IC-002 seven-state lifecycle")


# --- G3: Smoke C V2 executed (reject "not executed"/"deferred") -------------
def _claims_smoke_c_not_executed(text: str) -> bool:
    low = text.lower()
    return any(
        p in low
        for p in (
            "smoke c not executed",
            "smoke c v2 not executed",
            "smoke c has not",
            "smoke c not run",
            "smoke c not yet",
            "smoke c is deferred",
            "smoke c was deferred",
            "smoke c deferred",
            "smoke c v2 deferred",
        )
    )


def _records_smoke_c_arc(text: str) -> bool:
    return "Smoke C V2" in text and "#75" in text


def test_b5d_03_smoke_c_executed() -> None:
    t = _gate_docs_text()
    assert not _claims_smoke_c_not_executed(t), "gate docs must not claim Smoke C is not executed / deferred"
    assert _records_smoke_c_arc(t), "gate docs must record the Smoke C V2 arc closure (PR #75)"


def test_b5d_03_smoke_c_nonvacuity() -> None:
    assert _claims_smoke_c_not_executed("Smoke C not executed.")
    assert _claims_smoke_c_not_executed("Smoke C deferred / HARD-GATE")
    assert not _records_smoke_c_arc("no smoke evidence here")


# --- G4: B5-4A recorded (reject omission) -----------------------------------
def test_b5d_04_b5_4a_present() -> None:
    t = _gate_docs_text()
    assert "B5-4A" in t, "the B5-4A standing-auth fixture must be recorded"
    assert "#74" in t, "the B5-4A PR #74 must be recorded"


def test_b5d_04_b5_4a_nonvacuity() -> None:
    assert "B5-4A" not in "arc: B5-1 B5-2 B5-3 B5-4 B5-5", "guard must detect an omission of B5-4A"


# --- G5: PR #75 / Fix R3 closure recorded (reject omission) ------------------
def test_b5d_05_pr75_fixr3_present() -> None:
    t = _gate_docs_text()
    assert "#75" in t, "PR #75 must be recorded"
    assert "Fix R3" in t, "the Fix R3 closure must be recorded"


def test_b5d_05_pr75_fixr3_nonvacuity() -> None:
    assert "#75" not in "arc through #74", "guard must detect an omission of PR #75"
    assert "Fix R3" not in "Smoke C V2 integrated live proof", "guard must detect an omission of Fix R3"


# --- G6: B5-BLK-4 stays OPEN (reject closed/resolved/complete) ---------------
_CLOSED_WORDS = ("closed", "resolved", "complete", "completed")
_B5BLK4_OPEN_ALLOW = (
    "does not itself close b5-blk-4",
    "does not close b5-blk-4",
    "remains open",
    "remain open",
    "is open",
    "not complete",
    "not closed",
    "not resolved",
    "incomplete",
)


# Direct assertions that B5-BLK-4 itself is closed/resolved/complete, caught even
# when a later "not complete" (about the MVP) sits on the same line (allow-list shadowing).
_B5BLK4_DIRECT_CLOSED = (
    "b5-blk-4 is closed",
    "b5-blk-4 is resolved",
    "b5-blk-4 is complete",
    "b5-blk-4 is completed",
    "b5-blk-4 closed",
    "b5-blk-4 resolved",
    "b5-blk-4 complete",
    "b5-blk-4 completed",
    "b5-blk-4 now closed",
    "b5-blk-4: closed",
    "b5-blk-4 -> closed",
    "closed b5-blk-4",
    "resolved b5-blk-4",
    "completed b5-blk-4",
)


def _b5blk4_marked_closed(text: str) -> bool:
    low = text.lower()
    if any(p in low for p in _B5BLK4_DIRECT_CLOSED):
        return True
    for line in low.splitlines():
        if "b5-blk-4" not in line:
            continue
        if any(allow in line for allow in _B5BLK4_OPEN_ALLOW):
            continue
        if any(word in line for word in _CLOSED_WORDS):
            return True
    return False


def test_b5d_06_b5blk4_open() -> None:
    t = _gate_docs_text()
    assert not _b5blk4_marked_closed(t), "B5-BLK-4 must not be marked closed/resolved/complete"
    assert "does not itself close B5-BLK-4" in t, "the required B5-BLK-4 governing sentence must be present"


def test_b5d_06_b5blk4_nonvacuity() -> None:
    assert _b5blk4_marked_closed("B5-BLK-4 is now CLOSED")
    assert _b5blk4_marked_closed("Blocker B5-BLK-4 resolved by Smoke C V2")
    # allow-list shadowing attempt (a false close smuggled onto an MVP 'not complete' line) is caught
    assert _b5blk4_marked_closed("B5-BLK-4 is complete; the MVP is not complete")
    assert not _b5blk4_marked_closed("Smoke C V2 including Fix R3 does not itself close B5-BLK-4.")
    assert not _b5blk4_marked_closed("B5-BLK-4 remains OPEN and the MVP is not complete")


# --- G7: Physical Multi-DB MVP not unqualified-complete ----------------------
_MVP_INCOMPLETE_ALLOW = ("not complete", "mandatory and not complete", "not yet complete", "incomplete")


def _claims_mvp_complete(text: str) -> bool:
    for line in text.lower().splitlines():
        if "mvp" not in line:
            continue
        if not ("multi-database" in line or "multi-db" in line or "physical" in line):
            continue
        if any(allow in line for allow in _MVP_INCOMPLETE_ALLOW):
            continue
        if "complete" in line or "completed" in line or "done" in line:
            return True
    return False


def test_b5d_07_mvp_not_complete() -> None:
    t = _gate_docs_text()
    assert not _claims_mvp_complete(t), "the Physical Multi-Database MVP must not be claimed complete"
    assert "mandatory and NOT complete" in t, "MVP must be recorded as mandatory and NOT complete"


def test_b5d_07_mvp_nonvacuity() -> None:
    assert _claims_mvp_complete("The Physical Multi-Database MVP is complete")
    assert not _claims_mvp_complete("The Physical Multi-Database MVP remains mandatory and NOT complete")


# --- G8: database-granularity not mislabeled cluster-level -------------------
# An affirmative-claim detector (not a fixed phrase blacklist): any line that
# asserts cluster-level / multi-cluster distinctness with ANY assertion verb, and
# does NOT negate or scope it away, is a mislabel. Paired with a PER-DOC positive
# anchor so deleting the disclaimer in one doc cannot be masked by a sibling doc.
_CLUSTER_ASSERTION_WORDS = (
    "distinct",
    "granular",
    "proof",
    "prove",
    "proven",
    "proves",
    "establish",
    "demonstrat",
    "confirm",
    "show",
    "achiev",
    "supplie",
    "supply",
    "evidence",
)
_CLUSTER_SCOPE_AWAY = ("not", "deployment", "iac", "separate", "stays", "future")


def _mislabels_cluster_level(text: str) -> bool:
    for line in text.lower().splitlines():
        if "cluster-level" not in line and "cluster level" not in line and "multi-cluster" not in line:
            continue
        if any(scope in line for scope in _CLUSTER_SCOPE_AWAY):
            continue
        if any(word in line for word in _CLUSTER_ASSERTION_WORDS):
            return True
    return False


def _distinguishes_granularity_in(doc_text: str) -> bool:
    # Markdown-normalise (drop emphasis '*' and collapse whitespace so a disclaimer
    # that wraps across lines still matches), then require the explicit
    # database-granularity-is-NOT-cluster-level distinction inside THIS document.
    norm = " ".join(doc_text.lower().replace("*", "").split())
    return "database granularity" in norm and "not cluster-level" in norm


def test_b5d_08_granularity_not_cluster() -> None:
    t = _gate_docs_text()
    assert not _mislabels_cluster_level(t), "database-granularity evidence must not be mislabeled cluster-level"
    # The distinction must live in the gate doc AND the blocker register themselves —
    # a corpus-wide check would let a sibling doc mask a deletion in the primary doc.
    assert _distinguishes_granularity_in(_GATE_DOC.read_text(encoding="utf-8")), (
        "the activation-gate doc must distinguish database granularity from cluster-level distinctness"
    )
    assert _distinguishes_granularity_in(_BLOCKERS_DOC.read_text(encoding="utf-8")), (
        "the blocker register must distinguish database granularity from cluster-level distinctness"
    )


def test_b5d_08_granularity_nonvacuity() -> None:
    # canonical phrasing AND a synonym-verb rephrasing are both caught
    assert _mislabels_cluster_level("Smoke C proves cluster-level distinctness")
    assert _mislabels_cluster_level("Smoke C V2 including Fix R3 establishes cluster-level distinctness across the standing fleet")
    assert not _mislabels_cluster_level("It is not cluster-level / multi-cluster distinctness")
    # positive anchor is per-doc: a doc lacking the disclaimer fails it
    assert not _distinguishes_granularity_in("some doc that never draws the distinction")
    assert _distinguishes_granularity_in("Database granularity ... it is not cluster-level distinctness")


# --- G9: durable routing audit (DBR-AR-2) not complete ----------------------
def _claims_routing_audit_complete(text: str) -> bool:
    for line in text.lower().splitlines():
        if "dbr-ar-2" not in line and "routing audit" not in line and "routing-audit" not in line:
            continue
        if any(a in line for a in ("open", "in-memory", "follow-on", "not ", "pending", "remains")):
            continue
        if any(w in line for w in ("complete", "completed", "done", "closed")):
            return True
    return False


def test_b5d_09_routing_audit_open() -> None:
    t = _gate_docs_text()
    assert not _claims_routing_audit_complete(t), "the durable routing audit (DBR-AR-2) must not be claimed complete"
    assert "DBR-AR-2" in t, "the durable routing audit DBR-AR-2 must be recorded as open"


def test_b5d_09_routing_audit_nonvacuity() -> None:
    assert _claims_routing_audit_complete("The durable routing audit DBR-AR-2 is complete")
    assert not _claims_routing_audit_complete("Durable routing audit (DBR-AR-2) remains OPEN, in-memory only")


# --- G10: production deployment not complete --------------------------------
def _claims_production_deployed(text: str) -> bool:
    low = text.lower()
    bad = (
        "production deployment complete",
        "production deployment is complete",
        "production deployment completed",
        "production deployment proven",
        "production deployment done",
        "production deployment finished",
        "production deployment achieved",
        "production deployment in place",
        "deployed to production",
        "production is deployed",
        "production runtime activated",
        "production supervision complete",
        "production supervision in place",
        "live in production",
    )
    return any(b in low for b in bad)


def test_b5d_10_production_not_deployed() -> None:
    t = _gate_docs_text()
    assert not _claims_production_deployed(t), "production deployment must not be claimed complete"
    low = t.lower()
    assert "production deployment" in low and ("open" in low or "required" in low), (
        "production deployment/supervision must be recorded as OPEN"
    )


def test_b5d_10_production_nonvacuity() -> None:
    assert _claims_production_deployed("Production deployment complete and supervised")
    assert not _claims_production_deployed("Production deployment / supervision — OPEN (deployment evidence required)")


# --- G11: Lovable / API-Gateway cutover not complete ------------------------
def _claims_lovable_cutover_complete(text: str) -> bool:
    low = text.lower()
    bad = (
        "cutover complete",
        "cutover is complete",
        "cutover completed",
        "cutover done",
        "cutover finished",
        "cutover achieved",
        "lovable cutover complete",
        "cutover: complete",
        "fully cut over",
        "lovable integrated through the api gateway",
    )
    return any(b in low for b in bad)


def test_b5d_11_lovable_cutover_open() -> None:
    t = _gate_docs_text()
    assert not _claims_lovable_cutover_complete(t), "the Lovable/API-Gateway cutover must not be claimed complete"
    assert "cutover" in t.lower(), "the Lovable/API-Gateway cutover must be recorded (kept separate/open)"


def test_b5d_11_lovable_nonvacuity() -> None:
    assert _claims_lovable_cutover_complete("The Lovable cutover is complete")
    assert not _claims_lovable_cutover_complete("Lovable / API-Gateway cutover — separate track (interim Supabase/RLS)")


# --- G12: next step is the SEPARATE Dan-authorized closure decision ----------
def _states_separate_closure_next_step(text: str) -> bool:
    # Line-scoped: the NEXT-STEP statement must itself tie to the separate closure
    # decision. Coarse corpus-wide co-occurrence would not catch a bypass, since
    # "separate"/"closure"/"dan-authorized" also appear in unrelated sentences.
    for line in text.lower().splitlines():
        if "next" in line and "closure" in line and ("separate" in line or "dan-authorized" in line or "dan authorized" in line):
            return True
    return False


def test_b5d_12_next_step_separate_closure() -> None:
    t = _gate_docs_text()
    assert _states_separate_closure_next_step(t), "docs must state the next step is a separate Dan-authorized closure decision"
    low = t.lower()
    assert "does not perform" in low or "neither performs nor bypasses" in low or "does not perform or bypass" in low, (
        "docs must state this re-grounding does not perform/bypass the separate closure decision"
    )


def test_b5d_12_next_step_nonvacuity() -> None:
    assert not _states_separate_closure_next_step("Next step: activate production runtime now")
    assert _states_separate_closure_next_step("the next step is a separate Dan-authorized closure review")


if __name__ == "__main__":
    _scan.run(
        [
            test_activation_gate_template_exists_and_disabled_by_default,
            test_activation_gate_template_location,
            test_b5_runtime_docs_exist,
            test_blocker_register_is_not_ready_by_default,
            test_b5d_01_baseline_regrounded,
            test_b5d_01_baseline_nonvacuity,
            test_b5d_02_ic002_eight_state,
            test_b5d_02_ic002_nonvacuity,
            test_b5d_03_smoke_c_executed,
            test_b5d_03_smoke_c_nonvacuity,
            test_b5d_04_b5_4a_present,
            test_b5d_04_b5_4a_nonvacuity,
            test_b5d_05_pr75_fixr3_present,
            test_b5d_05_pr75_fixr3_nonvacuity,
            test_b5d_06_b5blk4_open,
            test_b5d_06_b5blk4_nonvacuity,
            test_b5d_07_mvp_not_complete,
            test_b5d_07_mvp_nonvacuity,
            test_b5d_08_granularity_not_cluster,
            test_b5d_08_granularity_nonvacuity,
            test_b5d_09_routing_audit_open,
            test_b5d_09_routing_audit_nonvacuity,
            test_b5d_10_production_not_deployed,
            test_b5d_10_production_nonvacuity,
            test_b5d_11_lovable_cutover_open,
            test_b5d_11_lovable_nonvacuity,
            test_b5d_12_next_step_separate_closure,
            test_b5d_12_next_step_nonvacuity,
        ]
    )
