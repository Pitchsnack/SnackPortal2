"""PRD 06 B-5 — activation-gate CONTRACT guard (text-inspection only; no runtime, no driver import).

Asserts the B-5 gate ARTIFACTS exist and commit to a fail-closed, references-only posture. B-5-specific only: secret /
*_REF hygiene for the .template is ALREADY enforced by test_no_secret_literals (test_templates_reference_only + the
pattern scan over infrastructure/**), so this test does not duplicate it. Text inspection only — no static
database-driver import (string literals naming paths are not imports). Pure stdlib; standalone-runnable:
  python tests/architecture/test_b5_runtime_activation_gate_contract.py
"""

from __future__ import annotations

import pathlib
import re
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
#
# Fix R1 hardening (2026-07-12, PRD B5-D Fix R1): G6/G7 closure- and
# completion-synonym coverage; explicit per-occurrence negation masking so a
# different-subject caveat (e.g. an MVP "not complete") can never exempt a
# B5-BLK-4 closure assertion (allow-list shadowing); G8 word-boundary /
# explicit-negation matching (bare substrings such as "Note"/"Another"/
# "Annotation" never count as negation); per-document governing-sentence and
# granularity-boundary anchors for ALL THREE docs (a sibling doc cannot satisfy
# a missing matrix disclaimer); bounded synonym extensions for G3/G9/G10/G11.
# Finite vocabularies only — this is not a natural-language parser.
# ---------------------------------------------------------------------------

_RUNTIME_DIR = _scan.REPO_ROOT / "docs" / "runtime"
_GATE_DOC = _RUNTIME_DIR / "b5_production_runtime_activation_gate.md"
_BLOCKERS_DOC = _RUNTIME_DIR / "b5_activation_blockers.md"
_MATRIX_DOC = _RUNTIME_DIR / "b5_runtime_readiness_matrix.md"
_GATE_DOCS = (_GATE_DOC, _BLOCKERS_DOC, _MATRIX_DOC)

_CURRENT_BASELINE = "fff215b5bd004760ea0d81915c3d93ca128673ed"
_STALE_BASELINE = "9684919"

# ---------------------------------------------------------------------------
# B5-E closure decision pins (2026-07-12). Dan authorized the separate closure
# review (PRD B5-E); it recorded Decision A (B5-BLK-4 closed — evidence-bound
# governance decision) and Decision B (Physical Multi-Database MVP accepted at
# database granularity) in all three gate documents at the decision baseline.
# The guards below evolve the B5-D pins: closure/acceptance wording is allowed
# ONLY in B5-E-anchored scoped decision sentences; unanchored closure claims,
# unauthorized reopening, other-blocker closures, unqualified MVP completion,
# stale blocker counts, baseline regression, and boundary erosion all reject.
# Each detector keeps a planted non-vacuity companion.
#
# B5-E Fix R1 hardening (2026-07-12, PRD B5-E Fix R1): the independent pre-merge
# verification proved required mutations #19/#20 escaped — the §5-not-waived
# sentence was the only B5-E decision sentence with no per-document pin and no
# polarity guard, and G6's waiver vocabulary fires only on lines carrying the
# literal token `b5-blk-4`. G15 adds the exact per-document non-waiver sentence
# anchor plus a corpus-wide affirmative-waiver detector that does NOT require
# the B5-BLK-4 token (see the G15 section header for its allow rules).
# ---------------------------------------------------------------------------
_DECISION_BASELINE = "84882c77cfe409bab0af454b4411cf65795bcbfd"
_B5E_ANCHOR = "b5-e"
_DECISION_A_SENTENCE = "decision a (b5-e, 2026-07-12, dan-authorized): b5-blk-4 — closed — evidence-bound governance decision"
_DECISION_B_SENTENCE = "decision b (b5-e, 2026-07-12, dan-authorized): physical multi-database mvp — accepted at database granularity"
_SCOPED_MVP_ACCEPTANCE = "accepted at database granularity"
_MVP_BOUNDARY_SENTENCE = (
    "mvp acceptance at database granularity is not cluster-level proof, not production deployment,"
    " not production activation, not lovable cutover, not billing completion, and not ai agent completion"
)
# The ONLY sanctioned DBR-AR-2 closure claim (PRD DBR-AR-2 Closure Decision V2 START-GATE §7 —
# MC-CD-3): the exact full anchored sentence — date + Dan-authorized governance-decision label +
# zero-blocker-closure statement + nine-census/8-of-9 count + NOT READY / DO-NOT-ACTIVATE posture.
_DBR_CLOSURE_SENTENCE = (
    "dbr-ar-2 — closed (dan-authorized governance decision, 2026-07-16); this closure closes zero b5"
    " activation blockers, the blocker census remains nine with 8 of 9 open, and production remains"
    " not ready / do-not-activate."
)
# The superseded pre-closure status sentence — it must NOT be resurrected in any gate doc.
_DBR_SUPERSEDED_OPEN_SENTENCE = "dbr-ar-2 (durable routing audit) remains open — a separate database router follow-on"
# The exact V1 contract-capture status sentence (pinned per document by
# test_dbr_ar_2_readiness_contract.py) — masked as a sanctioned exact sentence in G9.
_DBR_V1_STATUS_SENTENCE = (
    "this v1 records the implementation contract only. no durable routing-audit adapter,"
    " schema, production wiring or activation change is delivered by v1."
)
_FAIL_CLOSED_SENTENCE = "production runtime activation remains not ready / do-not-activate — 8 of 9 activation blockers remain open"
_NEXT_STEP_SENTENCE = "next step: the next dan-authorized governed slice"
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


def _normalized_doc(doc_text: str) -> str:
    # Markdown-normalise: drop emphasis '*', lower-case, collapse whitespace so
    # anchors that wrap across lines or carry bold markers still match.
    return " ".join(doc_text.lower().replace("*", "").split())


def _negation_masker(terms: "tuple[str, ...]") -> "re.Pattern[str]":
    """Build a masker for EXPLICITLY negated occurrences of the given status terms.

    Explicit negation only: a word-boundary negator ('not', 'never', 'no',
    "n't", 'cannot be') directly governing the term (with a bounded filler
    window). Bare substrings such as 'Note', 'Another', or 'Annotation' never
    count as negation. Masked occurrences are invisible to the affirmative-claim
    detectors, so a caveat about a DIFFERENT subject on the same line (e.g. an
    MVP 'not complete') can no longer exempt an affirmative closure assertion.
    """
    alt = "|".join(re.escape(t) for t in terms)
    return re.compile(
        rf"(?:\b(?:not|never|no|neither|nor)\s+(?:yet\s+)?(?:been\s+)?(?:be\s+)?(?:fully\s+)?(?:itself\s+)?(?:marked\s+)?(?:{alt})\b"
        rf"|\bcannot\s+(?:yet\s+)?(?:be\s+)?(?:marked\s+)?(?:{alt})\b"
        rf"|n['’]t\s+(?:yet\s+)?(?:been\s+)?(?:marked\s+)?(?:{alt})\b"
        rf"|\bdoes\s+not\s+(?:itself\s+)?close\b"
        rf"|\bnot\s+itself\s+close\b)"
    )


# The governing sentence required by PRD B5-D §7 / Fix R1 — pinned PER DOCUMENT
# (a sibling document must not satisfy a missing disclaimer).
_GOVERNING_SENTENCE_PART_1 = "smoke c v2 including fix r3 supplies database-granularity evidence"
_GOVERNING_SENTENCE_PART_2 = "it does not itself close b5-blk-4"


def _contains_governing_sentence(doc_text: str) -> bool:
    norm = _normalized_doc(doc_text)
    return _GOVERNING_SENTENCE_PART_1 in norm and _GOVERNING_SENTENCE_PART_2 in norm


# --- G1: baseline re-grounded (reject reversion to 9684919) -----------------
def _has_stale_baseline(text: str) -> bool:
    return _STALE_BASELINE in text


def _has_current_baseline(text: str) -> bool:
    return _CURRENT_BASELINE in text


def _decision_baseline_pinned(doc_text: str) -> bool:
    """Every 'decision baseline' line must carry EXACTLY the B5-E decision SHA; at least one such line."""
    found = False
    for line in doc_text.lower().splitlines():
        if "decision baseline" in line:
            if _DECISION_BASELINE not in line:
                return False
            found = True
    return found


def test_b5d_01_baseline_regrounded() -> None:
    t = _gate_docs_text()
    assert not _has_stale_baseline(t), "stale baseline 9684919 must not reappear in the B5 gate docs"
    assert _has_current_baseline(t), "the historic re-ground baseline fff215b… must stay recorded"
    for doc in _GATE_DOCS:
        assert _decision_baseline_pinned(doc.read_text(encoding="utf-8")), (
            f"{doc.name} must pin the B5-E decision baseline 84882c7… on every 'decision baseline' line"
        )


def test_b5d_01_baseline_nonvacuity() -> None:
    assert _has_stale_baseline("Baseline: origin/main @ 9684919"), "guard must detect a reverted baseline"
    assert not _has_current_baseline("Baseline: origin/main @ 9684919")
    # B5-E: the decision baseline is pinned per document and cannot regress.
    assert _decision_baseline_pinned(f"decision baseline `origin/main @ {_DECISION_BASELINE}` (B5-E)")
    assert not _decision_baseline_pinned(f"decision baseline `origin/main @ {_CURRENT_BASELINE}`")
    assert not _decision_baseline_pinned("a document with no decision-baseline line at all")
    assert not _decision_baseline_pinned(
        f"decision baseline `origin/main @ {_DECISION_BASELINE}`\ndecision baseline `origin/main @ {_STALE_BASELINE}aaaa`"
    )


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
# Contiguous-phrase blacklist (bounded; Fix R1 adds pending/outstanding/deferred
# equivalents). Kept adjacency-based on purpose: loose per-line co-occurrence of
# "Smoke C" with e.g. "deferred" would false-positive on honest matrix rows that
# mention Smoke C and an unrelated deferred item in separate columns.
_SMOKE_C_NOT_EXECUTED_PHRASES = (
    "smoke c not executed",
    "smoke c v2 not executed",
    "smoke c has not",
    "smoke c not run",
    "smoke c not yet",
    "smoke c is deferred",
    "smoke c was deferred",
    "smoke c deferred",
    "smoke c v2 deferred",
    "smoke c pending",
    "smoke c v2 pending",
    "smoke c is pending",
    "smoke c remains pending",
    "smoke c still pending",
    "smoke c outstanding",
    "smoke c v2 outstanding",
    "smoke c is outstanding",
    "smoke c remains outstanding",
    "smoke c postponed",
    "smoke c v2 postponed",
    "smoke c is postponed",
    "smoke c on hold",
    "smoke c is on hold",
    "smoke c awaiting",
    "smoke c to be run",
    "smoke c to be executed",
    "smoke c yet to run",
    "smoke c yet to be run",
)


def _claims_smoke_c_not_executed(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in _SMOKE_C_NOT_EXECUTED_PHRASES)


def _records_smoke_c_arc(text: str) -> bool:
    return "Smoke C V2" in text and "#75" in text


def test_b5d_03_smoke_c_executed() -> None:
    t = _gate_docs_text()
    assert not _claims_smoke_c_not_executed(t), "gate docs must not claim Smoke C is not executed / deferred"
    assert _records_smoke_c_arc(t), "gate docs must record the Smoke C V2 arc closure (PR #75)"


def test_b5d_03_smoke_c_nonvacuity() -> None:
    assert _claims_smoke_c_not_executed("Smoke C not executed.")
    assert _claims_smoke_c_not_executed("Smoke C deferred / HARD-GATE")
    # Fix R1: every added pending/outstanding/deferred equivalent fires.
    for phrase in _SMOKE_C_NOT_EXECUTED_PHRASES:
        assert _claims_smoke_c_not_executed(f"Status: {phrase}."), phrase
    assert _claims_smoke_c_not_executed("Smoke C remains outstanding for this gate")
    assert _claims_smoke_c_not_executed("Smoke C on hold until the next arc")
    assert not _claims_smoke_c_not_executed("Smoke C V2 executed and merged via PR #75")
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


# --- G6: B5-BLK-4 stays OPEN (reject closed/resolved/complete + synonyms) ----
# Fix R1: full closure-synonym vocabulary (PRD B5-D Fix R1 §4) and SUBJECT-SCOPED
# logic. The old per-line allow-list skipped the whole line when ANY allow-phrase
# appeared, so an MVP-scoped "not complete" caveat exempted a B5-BLK-4 closure
# assertion on the same line (allow-list shadowing, finding F2). Now each negation
# is masked PER OCCURRENCE and any remaining affirmative closure term on a
# B5-BLK-4 line rejects — a caveat about a different subject can no longer shadow.
_B5BLK4_CLOSURE_WORDS = (
    "closed",
    "resolved",
    "complete",
    "completed",
    "satisfied",
    "cleared",
    "lifted",
    "discharged",
    "waived",
    "met",
    "done",
    # present-tense verb forms ("Smoke C V2 closes B5-BLK-4") and adjacent
    # closure vocabulary — adversarial-verify additions, still a finite list
    "closes",
    "resolves",
    "satisfies",
    "clears",
    "waives",
    "discharges",
    "lifts",
    "fixed",
    "retired",
)
_B5BLK4_CLOSURE_PHRASES = (
    "no longer blocks",
    "no longer blocking",
    "not blocking",
    "removed as a blocker",
    "no longer a blocker",
    "no longer applies",
    "no longer required",
    # recording the closure/waiver DECISION as taken is closure in effect
    "closure approved",
    "closure granted",
    "closure authorized",
    "closure recorded",
    "closure has been approved",
    "closure was approved",
    "closure decision was taken",
    "closure decision taken",
    "waiver approved",
    "waiver granted",
    "waiver authorized",
    "waiver has been granted",
    "waiver was granted",
    "waiver has been approved",
    "waiver was approved",
    "waiver in effect",
)
_B5BLK4_NEGATION_MASK = _negation_masker(_B5BLK4_CLOSURE_WORDS)
_B5BLK4_CLOSURE_WORD_RE = re.compile(r"\b(?:" + "|".join(_B5BLK4_CLOSURE_WORDS) + r")\b")


def _b5blk4_marked_closed(text: str) -> bool:
    """B5-E evolution: an UNANCHORED closure claim rejects. A line carrying the
    B5-E decision anchor is the scoped decision wording the closure review
    authorized; every other closure assertion on a B5-BLK-4 line is drift."""
    for raw in text.lower().splitlines():
        if "b5-blk-4" not in raw:
            continue
        if _B5E_ANCHOR in raw:
            continue
        line = _B5BLK4_NEGATION_MASK.sub(" <negated> ", raw.replace("*", ""))
        if any(phrase in line for phrase in _B5BLK4_CLOSURE_PHRASES):
            return True
        if _B5BLK4_CLOSURE_WORD_RE.search(line):
            return True
    return False


# B5-E: a CLOSED blocker must not be silently reopened. Adjacency-bounded so a
# different-subject OPEN on the same line (DBR-AR-2, the other blockers, "8 of 9
# blockers remain OPEN") never false-positives.
_B5BLK4_REOPEN_RE = re.compile(
    r"\bb5-blk-4\b\W{0,6}(?:\([^)]{0,40}\)\W{0,6})?(?:is\s+|remains\s+|stays\s+|now\s+|still\s+)?(?:re)?open(?:ed)?\b"
)


def _b5blk4_reopened(text: str) -> bool:
    low = text.replace("*", "").lower()
    return any(_B5BLK4_REOPEN_RE.search(line) for line in low.splitlines())


def _register_row_records_closure(register_text: str) -> bool:
    """The register's B5-BLK-4 table row must carry the anchored CLOSED status cell."""
    for raw in register_text.lower().splitlines():
        stripped = raw.replace("*", "").strip()
        if stripped.startswith("| b5-blk-4"):
            return "closed (b5-e" in stripped
    return False


def test_b5d_06_b5blk4_closure_decision() -> None:
    t = _gate_docs_text()
    assert not _b5blk4_marked_closed(t), "no unanchored B5-BLK-4 closure claim may appear outside the B5-E scoped wording"
    assert not _b5blk4_reopened(t), "B5-BLK-4 was closed by the B5-E decision and must not be silently reopened"
    assert "does not itself close B5-BLK-4" in t, "the required B5-BLK-4 governing sentence must be present"
    assert _register_row_records_closure(_BLOCKERS_DOC.read_text(encoding="utf-8")), (
        "the blocker register's B5-BLK-4 row must record the anchored CLOSED (B5-E…) status"
    )
    # Per-document anchors: each doc carries the governing sentence AND the exact
    # Decision A sentence itself — a sibling document cannot mask either.
    for doc in _GATE_DOCS:
        text = doc.read_text(encoding="utf-8")
        assert _contains_governing_sentence(text), (
            f"the governing sentence (database-granularity evidence / does not itself close B5-BLK-4) must be present in {doc.name} itself"
        )
        assert _DECISION_A_SENTENCE in _normalized_doc(text), f"the exact Decision A sentence must be present in {doc.name} itself"


def test_b5d_06_b5blk4_nonvacuity() -> None:
    assert _b5blk4_marked_closed("B5-BLK-4 is now CLOSED")
    assert _b5blk4_marked_closed("Blocker B5-BLK-4 resolved by Smoke C V2")
    # Fix R1: every closure synonym and phrase fires (PRD Fix R1 §4).
    for word in _B5BLK4_CLOSURE_WORDS:
        assert _b5blk4_marked_closed(f"B5-BLK-4 is {word}"), word
    for phrase in _B5BLK4_CLOSURE_PHRASES:
        assert _b5blk4_marked_closed(f"B5-BLK-4 {phrase}"), phrase
    assert _b5blk4_marked_closed("B5-BLK-4 is satisfied.")
    # Fix R1: allow-list shadowing is defeated — an MVP caveat on the same line
    # cannot exempt a B5-BLK-4 closure assertion (PRD Fix R1 §4 required-fail set).
    assert _b5blk4_marked_closed("B5-BLK-4 is complete; the MVP is not complete")
    assert _b5blk4_marked_closed("B5-BLK-4 was resolved yesterday, though the MVP is not complete.")
    assert _b5blk4_marked_closed("B5-BLK-4 is now closed since the MVP is not complete.")
    assert _b5blk4_marked_closed("B5-BLK-4 fully resolved; Physical Multi-Database MVP not complete.")
    # Explicitly negated / open forms remain allowed (PRD Fix R1 §4 allow set).
    assert not _b5blk4_marked_closed("B5-BLK-4 OPEN.")
    assert not _b5blk4_marked_closed("B5-BLK-4 remains OPEN.")
    assert not _b5blk4_marked_closed("B5-BLK-4 is not closed.")
    assert not _b5blk4_marked_closed("B5-BLK-4 is not resolved.")
    assert not _b5blk4_marked_closed("B5-BLK-4 is not yet satisfied.")
    assert not _b5blk4_marked_closed("Smoke C V2 including Fix R3 does not itself close B5-BLK-4.")
    assert not _b5blk4_marked_closed("Smoke C V2 including Fix R3 does not close B5-BLK-4.")
    assert not _b5blk4_marked_closed("B5-BLK-4 remains OPEN and the MVP is not complete")
    # Adversarial-verify additions: verb-form and decision-recording drift fires;
    # explicitly negated honest phrasings (incl. 'cannot be marked', 'neither/nor') stay green.
    assert _b5blk4_marked_closed("Together with the standing fixtures, Smoke C V2 closes B5-BLK-4.")
    assert _b5blk4_marked_closed("PR #75 resolves B5-BLK-4.")
    assert _b5blk4_marked_closed("The standing fixture satisfies B5-BLK-4.")
    assert _b5blk4_marked_closed("It does not itself close B5-BLK-4 on its own; combined with PR #75, however, it closes it.")
    assert _b5blk4_marked_closed("B5-BLK-4 closure approved by Dan on 2026-07-12; see the evidence record.")
    assert _b5blk4_marked_closed("An explicit waiver granted for B5-BLK-4.")
    assert _b5blk4_marked_closed("An explicit approved waiver has been granted for B5-BLK-4.")
    assert _b5blk4_marked_closed("B5-BLK-4 no longer applies after the Smoke C V2 arc.")
    assert _b5blk4_marked_closed("B5-BLK-4 is fixed by PR #75.")
    assert _b5blk4_marked_closed("B5-BLK-4 retired 2026-07-12.")
    assert not _b5blk4_marked_closed("B5-BLK-4 cannot be marked closed without a separate Dan-authorized decision.")
    assert not _b5blk4_marked_closed("B5-BLK-4 must not be marked closed until the Dan review completes.")
    assert not _b5blk4_marked_closed("B5-BLK-4 is neither closed nor resolved; the gate stays DO-NOT-ACTIVATE.")
    assert not _b5blk4_marked_closed("closure of B5-BLK-4 is a separate Dan-authorized decision (or an explicit approved waiver).")
    # B5-E: the anchored scoped decision wording is allowed; unanchored closure stays drift.
    assert not _b5blk4_marked_closed(
        "Decision A (B5-E, 2026-07-12, Dan-authorized): B5-BLK-4 — CLOSED — EVIDENCE-BOUND GOVERNANCE DECISION."
    )
    assert _b5blk4_marked_closed("B5-BLK-4 — CLOSED — EVIDENCE-BOUND GOVERNANCE DECISION.")  # anchor missing → drift
    # B5-E: silent reopening is rejected; different-subject OPEN on the same line is not.
    assert _b5blk4_reopened("B5-BLK-4 — OPEN")
    assert _b5blk4_reopened("B5-BLK-4 remains OPEN.")
    assert _b5blk4_reopened("**B5-BLK-4** OPEN")
    assert _b5blk4_reopened("B5-BLK-4 (B5-E) is reopened")
    assert not _b5blk4_reopened("Decision A (B5-E, 2026-07-12, Dan-authorized): B5-BLK-4 — CLOSED — EVIDENCE-BOUND GOVERNANCE DECISION.")
    assert not _b5blk4_reopened("8 of 9 activation blockers remain OPEN; the B5-E closure of B5-BLK-4 changes no other blocker")
    assert not _b5blk4_reopened("DBR-AR-2 remains OPEN; it was not part of the B5-BLK-4 closure evidence bar")
    assert not _b5blk4_reopened("retain their authoring-time open-status wording for B5-BLK-4 by design")
    # B5-E: the register row pin fires when the status cell loses the anchored closure.
    assert _register_row_records_closure(
        "| **B5-BLK-4** | desc | Major | Control Plane | evidence | **CLOSED (B5-E, 2026-07-12, Dan-authorized)** | NO |"
    )
    assert not _register_row_records_closure("| **B5-BLK-4** | desc | Major | Control Plane | evidence | OPEN | YES |")
    assert not _register_row_records_closure("a register with no B5-BLK-4 row at all")
    # B5-E: each document's own Decision A sentence anchor is non-vacuous.
    for doc in _GATE_DOCS:
        norm_doc = _normalized_doc(doc.read_text(encoding="utf-8"))
        assert _DECISION_A_SENTENCE in norm_doc, doc.name
        assert _DECISION_A_SENTENCE not in norm_doc.replace(_DECISION_A_SENTENCE, ""), doc.name
    # Fix R1 per-document governing-sentence anchor is non-vacuous: removing either
    # sentence from a document's own text fails that document's anchor.
    for doc in _GATE_DOCS:
        norm = _normalized_doc(doc.read_text(encoding="utf-8"))
        assert _contains_governing_sentence(norm), doc.name
        assert not _contains_governing_sentence(norm.replace(_GOVERNING_SENTENCE_PART_1, "")), doc.name
        assert not _contains_governing_sentence(norm.replace(_GOVERNING_SENTENCE_PART_2, "")), doc.name
    assert not _contains_governing_sentence("a document whose siblings carry the disclaimer but which lacks it itself")


# --- G7: Physical Multi-DB MVP not unqualified-complete ----------------------
# Fix R1: full completion/readiness/acceptance vocabulary (PRD B5-D Fix R1 §5)
# with per-occurrence negation masking (replacing the shadowable allow-list) and
# an assertion-linkage requirement so honest vocabulary collisions (the IC-002
# "Ready" state, "live proof") cannot false-positive: the term must be predicated
# of the MVP itself ("MVP is ready", "MVP: complete", "MVP done"), not merely
# co-occur somewhere on the line.
_MVP_COMPLETION_TERMS = (
    "complete",
    "completed",
    "done",
    "ready",
    "accepted",
    "achieved",
    "finished",
    "signed off",
    "signed-off",
    "delivered",
    "operational",
    "live",
    "in place",
    "production-ready",
    "release-ready",
    "approved",
    "closed",
    # adversarial-verify additions: the repo's own shipping idioms
    "shipped",
    "landed",
)
_MVP_NEGATION_MASK = _negation_masker(_MVP_COMPLETION_TERMS)
_MVP_TERM_ALT = "|".join(re.escape(t) for t in _MVP_COMPLETION_TERMS)
# "MVP <link> [up to two qualifiers] <term>" — e.g. "MVP is ready", "MVP has been
# accepted", "MVP — done", "MVP, at last, is complete", "| MVP | ✅ done |".
_MVP_LINKED_CLAIM = re.compile(
    r"\bmvp\b[,;)]*(?:\s+\S+){0,3}?"
    r"(?:\s+(?:is|are|was|were|has\s+been|have\s+been|has|have|now|remains|stands|went|goes)\b|\s*(?::|—|–|->|→|=|\|))"
    rf"\s*(?:[^\s|]+\s+){{0,2}}?(?:{_MVP_TERM_ALT})\b"
)
# "MVP <term>" direct adjacency — e.g. "MVP complete", "MVP ready".
_MVP_ADJACENT_CLAIM = re.compile(rf"\bmvp\s+(?:fully\s+|officially\s+|now\s+)?(?:{_MVP_TERM_ALT})\b")
# "<term> ... MVP" reverse assertion — e.g. "completed the Physical Multi-Database
# MVP", "signed off on the entire Physical Multi-Database MVP".
_MVP_REVERSE_CLAIM = re.compile(
    r"\b(?:completed|delivered|finished|achieved|accepted|approved|closed|shipped|signed\s+off(?:\s+on)?)\s+(?:[\w-]+\s+){0,4}?mvp\b"
)
# Line-wide predicate assertion on an MVP line — catches a completion clause whose
# verb sits beyond the bounded MVP-anchored windows ("... but is now complete").
_MVP_PREDICATE_CLAIM = re.compile(
    rf"\b(?:is|are|was|were|has\s+been|have\s+been|has|have)\s+(?:now\s+|fully\s+|officially\s+|formally\s+|finally\s+)?(?:{_MVP_TERM_ALT})\b"
)


def _claims_mvp_complete(text: str) -> bool:
    # Subject scope: within these three gate documents "MVP" always denotes the
    # Physical Multi-Database MVP, so any MVP line is in scope (a shortened
    # "the MVP is complete" must not slip past a qualifier filter).
    # B5-E evolution: the EXACT scoped acceptance phrase on a B5-E-anchored line
    # is the authorized Decision B wording and is masked per occurrence; every
    # other completion/readiness/acceptance claim (including an UNANCHORED or
    # UNQUALIFIED "accepted") still rejects.
    for raw in text.lower().splitlines():
        if "mvp" not in raw:
            continue
        line = raw.replace("*", "")
        if _B5E_ANCHOR in line:
            line = line.replace(_SCOPED_MVP_ACCEPTANCE, " <scoped-acceptance> ")
        line = _MVP_NEGATION_MASK.sub(" <negated> ", line)
        if _MVP_LINKED_CLAIM.search(line) or _MVP_ADJACENT_CLAIM.search(line) or _MVP_REVERSE_CLAIM.search(line):
            return True
        if _MVP_PREDICATE_CLAIM.search(line):
            return True
    return False


def test_b5d_07_mvp_not_complete() -> None:
    t = _gate_docs_text()
    assert not _claims_mvp_complete(t), (
        "outside the B5-E scoped Decision B wording, the Physical Multi-Database MVP must not be claimed complete/ready/etc."
    )
    low_norm = _normalized_doc(t)
    assert "remains mandatory and binding" in low_norm, "the IC-010 §O MVP mandate must remain recorded as binding"
    # Per-document anchors: the exact Decision B sentence AND the acceptance
    # boundary sentence must live in EVERY gate doc itself.
    for doc in _GATE_DOCS:
        norm_doc = _normalized_doc(doc.read_text(encoding="utf-8"))
        assert _DECISION_B_SENTENCE in norm_doc, f"the exact Decision B sentence must be present in {doc.name} itself"
        assert _MVP_BOUNDARY_SENTENCE in norm_doc, f"the MVP acceptance boundary sentence must be present in {doc.name} itself"


def test_b5d_07_mvp_nonvacuity() -> None:
    assert _claims_mvp_complete("The Physical Multi-Database MVP is complete")
    # Fix R1: every completion/readiness/acceptance synonym fires (PRD Fix R1 §5).
    for term in _MVP_COMPLETION_TERMS:
        assert _claims_mvp_complete(f"The Physical Multi-Database MVP is {term}."), term
    assert _claims_mvp_complete("The Physical Multi-Database MVP is ready.")
    assert _claims_mvp_complete("The Physical Multi-Database MVP is accepted.")
    assert _claims_mvp_complete("The Physical Multi-Database MVP is achieved.")
    assert _claims_mvp_complete("The Physical Multi-Database MVP is operational.")
    assert _claims_mvp_complete("The Physical Multi-Database MVP is in place.")
    assert _claims_mvp_complete("Physical Multi-Database MVP complete.")
    assert _claims_mvp_complete("**Physical Multi-Database MVP** is ready")
    assert _claims_mvp_complete("Physical Multi-Database MVP: done")
    assert _claims_mvp_complete("The Physical Multi-Database MVP has been signed off")
    assert _claims_mvp_complete("We have completed the Physical Multi-Database MVP")
    assert _claims_mvp_complete("The Physical Multi-Database MVP is now fully operational")
    # Explicitly negated / qualified forms remain allowed (PRD Fix R1 §5 allow set).
    assert not _claims_mvp_complete("Physical Multi-Database MVP mandatory and NOT complete.")
    assert not _claims_mvp_complete("Physical Multi-Database MVP not ready.")
    assert not _claims_mvp_complete("Physical Multi-Database MVP acceptance remains separate.")
    assert not _claims_mvp_complete("The Physical Multi-Database MVP remains mandatory and NOT complete")
    # Honest vocabulary collisions do not false-positive: the IC-002 "Ready" state
    # and Smoke C "live proof" wording are not MVP-completion predicates.
    assert not _claims_mvp_complete("Physical Multi-Database MVP requires that standing tenants reach Ready; it is NOT complete")
    assert not _claims_mvp_complete("Smoke C V2 integrated live proof supports the physical Multi-Database MVP closure review")
    # Adversarial-verify additions: shortened-subject, comma-appositive, table-row,
    # shipped/landed, sign-off, and beyond-window completion clauses all fire.
    assert _claims_mvp_complete("The MVP is now complete.")
    assert _claims_mvp_complete("MVP status: complete")
    assert _claims_mvp_complete("The Physical Multi-Database MVP, at last, is complete.")
    assert _claims_mvp_complete("The Physical Multi-Database MVP, per the closure review, is complete.")
    assert _claims_mvp_complete("The Physical Multi-Database MVP was not complete at the last review, but is now complete.")
    assert _claims_mvp_complete("The Physical Multi-Database MVP has shipped.")
    assert _claims_mvp_complete("The Physical Multi-Database MVP has landed.")
    assert _claims_mvp_complete("Physical Multi-Database MVP = shipped")
    assert _claims_mvp_complete("| Physical Multi-Database MVP | done |")
    assert _claims_mvp_complete("Dan signed off on the Physical Multi-Database MVP on 2026-07-12.")
    assert _claims_mvp_complete("We have completed the entire Physical Multi-Database MVP.")
    # Negation still governs the shortened subject and predicate scans.
    assert not _claims_mvp_complete("The MVP is not complete.")
    assert not _claims_mvp_complete("The MVP has not shipped; the closure review remains separate.")
    # B5-E: the anchored scoped Decision B wording is allowed; anything else still fires.
    assert not _claims_mvp_complete(
        "Decision B (B5-E, 2026-07-12, Dan-authorized): Physical Multi-Database MVP — ACCEPTED AT DATABASE GRANULARITY."
    )
    assert _claims_mvp_complete("Physical Multi-Database MVP — ACCEPTED AT DATABASE GRANULARITY.")  # anchor missing
    assert _claims_mvp_complete("The Physical Multi-Database MVP is accepted (B5-E).")  # qualifier missing
    assert _claims_mvp_complete("Physical Multi-Database MVP accepted at cluster level (B5-E).")  # wrong granularity
    assert _claims_mvp_complete("The Physical Multi-Database MVP is complete (B5-E).")  # acceptance is never 'complete'
    # The boundary sentence never neutralizes an overclaim elsewhere on the line's document,
    # and each document's own Decision B / boundary anchors are non-vacuous.
    for doc in _GATE_DOCS:
        norm_doc = _normalized_doc(doc.read_text(encoding="utf-8"))
        assert _DECISION_B_SENTENCE in norm_doc, doc.name
        assert _DECISION_B_SENTENCE not in norm_doc.replace(_DECISION_B_SENTENCE, ""), doc.name
        assert _MVP_BOUNDARY_SENTENCE in norm_doc, doc.name
        assert _MVP_BOUNDARY_SENTENCE not in norm_doc.replace(_MVP_BOUNDARY_SENTENCE, ""), doc.name
    assert "remains mandatory and binding" not in _normalized_doc(_gate_docs_text()).replace("remains mandatory and binding", "")


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
    # adversarial-verify additions (stems, matching the list's stem style)
    "validat",
    "verif",
    "guarante",
    "ensur",
    "isolation",
)
# Fix R1 (finding F4): explicit negation matching only. The old bare-substring
# "not" scope-away skipped any line containing "Note"/"Another"/"cannot"/
# "annotation". Negation now requires a word-boundary negator; other scope-away
# vocabulary is word-bounded too.
_CLUSTER_NEGATION_RE = re.compile(r"\b(?:not|cannot|never|no)\b|n['’]t\b")
_CLUSTER_SCOPE_AWAY_RE = re.compile(r"\b(?:deployment|iac|separate|stays|future)\b")


def _mislabels_cluster_level(text: str) -> bool:
    for line in text.lower().splitlines():
        if "cluster-level" not in line and "cluster level" not in line and "multi-cluster" not in line:
            continue
        if _CLUSTER_NEGATION_RE.search(line) or _CLUSTER_SCOPE_AWAY_RE.search(line):
            continue
        if any(word in line for word in _CLUSTER_ASSERTION_WORDS):
            return True
    return False


def _distinguishes_granularity_in(doc_text: str) -> bool:
    # Markdown-normalise, then require the explicit database-granularity-is-NOT-
    # cluster-level distinction inside THIS document. A "whether or not
    # cluster-level" construction is NOT a disclaimer and does not satisfy the
    # anchor (adversarial-verify addition).
    norm = _normalized_doc(doc_text)
    if "database granularity" not in norm:
        return False
    return re.search(r"(?<!whether or )not cluster-level", norm) is not None


def test_b5d_08_granularity_not_cluster() -> None:
    t = _gate_docs_text()
    assert not _mislabels_cluster_level(t), "database-granularity evidence must not be mislabeled cluster-level"
    # Fix R1 (finding F6): the distinction must live in EVERY gate doc itself —
    # gate doc, blocker register, AND readiness matrix. A corpus-wide check would
    # let a sibling doc mask a deletion in any one of them.
    for doc in _GATE_DOCS:
        assert _distinguishes_granularity_in(doc.read_text(encoding="utf-8")), (
            f"{doc.name} must itself distinguish database granularity from cluster-level distinctness"
        )


def test_b5d_08_granularity_nonvacuity() -> None:
    # canonical phrasing AND a synonym-verb rephrasing are both caught
    assert _mislabels_cluster_level("Smoke C proves cluster-level distinctness")
    assert _mislabels_cluster_level("Smoke C V2 including Fix R3 establishes cluster-level distinctness across the standing fleet")
    # Fix R1 (finding F4): words merely CONTAINING "not" are not negation.
    assert _mislabels_cluster_level("Note: Smoke C V2 including Fix R3 proves cluster-level distinctness.")
    assert _mislabels_cluster_level("Another proof: Smoke C establishes cluster-level distinctness.")
    assert _mislabels_cluster_level("Annotation: database-granularity evidence proves cluster-level distinctness.")
    # Explicit negation forms remain allowed (PRD Fix R1 §6 valid-negation set).
    assert not _mislabels_cluster_level("It is not cluster-level / multi-cluster distinctness")
    assert not _mislabels_cluster_level("Smoke C does not prove cluster-level distinctness")
    assert not _mislabels_cluster_level("Smoke C has not established cluster-level distinctness")
    assert not _mislabels_cluster_level("The evidence cannot claim cluster-level distinctness")
    # Adversarial-verify additions: new assertion stems fire on unnegated claims.
    assert _mislabels_cluster_level("Smoke C V2 validates cluster-level isolation end-to-end")
    assert _mislabels_cluster_level("Cluster-level tenant isolation is guaranteed by the standing fixture")
    assert _mislabels_cluster_level("The fixture verifies cluster-level distinctness across tenants")
    # positive anchor is per-doc: a doc lacking the disclaimer fails it
    assert not _distinguishes_granularity_in("some doc that never draws the distinction")
    assert _distinguishes_granularity_in("Database granularity ... it is not cluster-level distinctness")
    # a "whether or not cluster-level" construction is not a disclaimer
    assert not _distinguishes_granularity_in(
        "database granularity is supplied; whether or not cluster-level distinctness was still owed, Smoke C V3 now supplies it"
    )
    # Fix R1 (finding F6): the matrix disclaimer removed while sibling docs remain
    # unchanged is caught by the matrix's OWN anchor.
    matrix_norm = _normalized_doc(_MATRIX_DOC.read_text(encoding="utf-8"))
    assert _distinguishes_granularity_in(matrix_norm)
    assert not _distinguishes_granularity_in(matrix_norm.replace("database granularity", "").replace("database-granularity", ""))
    assert not _distinguishes_granularity_in(matrix_norm.replace("not cluster-level", "at cluster-level"))


# --- G9: durable routing audit (DBR-AR-2) closure wording is exact-only ------
# Fix R1 §8: bounded completed/achieved/wired/in-place synonym coverage; the
# open-marker skip uses word-boundary "not" (no bare-substring negation).
# Closure evolution (2026-07-16): the exact canonical closure sentence is masked
# per line (the B5-E G6 anchor idiom at full-decision-phrase width); every OTHER
# closure claim — bare, shortened, date-free, count-free, zero-closure-free, or
# production-posture-free — rejects REGARDLESS of open-marker vocabulary on the
# line (the canonical sentence itself carries "OPEN" and "NOT READY", so the
# open-marker skip alone cannot police closure variants).
_ROUTING_AUDIT_DONE_WORDS = (
    "complete",
    "completed",
    "done",
    "closed",
    "achieved",
    "wired",
    "in place",
    "in-place",
    "landed",
    "built",
    "implemented",
    "delivered",
    "finished",
    "satisfied",
    "shipped",
)
_ROUTING_AUDIT_OPEN_RE = re.compile(r"\b(?:open|in-memory|follow-on|not|pending|remains|absent|outstanding)\b")
# Unanchored-closure detector: status-claim token = CLOSED; the bounded [^.;|] window never
# crosses a sentence boundary or a table-cell pipe (so the anchored B5-BLK-4 CLOSED register
# cell can never bind to a DBR-AR-2 token in a neighboring cell); "fail closed"/"fail-closed"
# posture vocabulary and underscored identifiers (routing_audit_unavailable) are out of scope.
_ROUTING_AUDIT_UNANCHORED_CLOSED_RE = re.compile(
    r"\b(?:dbr-ar-2\b|durable routing audit\b|routing[ -]audit\b)[^.;|]{0,80}?(?<!fail )(?<!fail-)\bclosed\b"
)


def _claims_routing_audit_complete(text: str) -> bool:
    for raw in text.lower().splitlines():
        line = " ".join(raw.replace("*", "").replace("`", "").split())
        line = line.replace(_DBR_CLOSURE_SENTENCE, " <dbr-closure-sentence> ")
        line = line.replace(_DBR_V1_STATUS_SENTENCE, " <dbr-v1-status-sentence> ")
        if _ROUTING_AUDIT_UNANCHORED_CLOSED_RE.search(line):
            return True
        if "dbr-ar-2" not in line and "routing audit" not in line and "routing-audit" not in line:
            continue
        if _ROUTING_AUDIT_OPEN_RE.search(line):
            continue
        if any(w in line for w in _ROUTING_AUDIT_DONE_WORDS):
            return True
    return False


def test_b5d_09_routing_audit_closure_exact() -> None:
    t = _gate_docs_text()
    assert not _claims_routing_audit_complete(t), (
        "outside the exact canonical closure sentence, no DBR-AR-2 closed/complete claim may appear in the gate docs"
    )
    assert "DBR-AR-2" in t, "the durable routing audit DBR-AR-2 must be recorded"
    # Closure evolution: the exact canonical closure sentence is pinned PER DOCUMENT, and the
    # superseded open/follow-on sentence must not be resurrected in any gate doc.
    for doc in _GATE_DOCS:
        norm_doc = _normalized_doc(doc.read_text(encoding="utf-8"))
        assert _DBR_CLOSURE_SENTENCE in norm_doc, f"the exact canonical DBR-AR-2 closure sentence must be present in {doc.name} itself"
        assert _DBR_SUPERSEDED_OPEN_SENTENCE not in norm_doc, (
            f"{doc.name} must not resurrect the superseded DBR-AR-2 open/follow-on sentence"
        )


def test_b5d_09_routing_audit_nonvacuity() -> None:
    assert _claims_routing_audit_complete("The durable routing audit DBR-AR-2 is complete")
    # Fix R1: every added completion synonym fires.
    for word in _ROUTING_AUDIT_DONE_WORDS:
        assert _claims_routing_audit_complete(f"DBR-AR-2 is {word}"), word
    assert _claims_routing_audit_complete("The durable routing audit is wired and achieved")
    assert not _claims_routing_audit_complete("Durable routing audit (DBR-AR-2) remains OPEN, in-memory only")
    assert not _claims_routing_audit_complete("DBR-AR-2 not yet wired; still absent")
    # Closure evolution: the exact canonical sentence is sanctioned; every required-reject
    # variant trips even though it carries open-marker vocabulary.
    assert not _claims_routing_audit_complete(_DBR_CLOSURE_SENTENCE)
    assert not _claims_routing_audit_complete("**" + _DBR_CLOSURE_SENTENCE.upper() + "**")
    assert _claims_routing_audit_complete("dbr-ar-2 — closed")  # bare
    assert _claims_routing_audit_complete("DBR-AR-2 is CLOSED")  # short
    assert _claims_routing_audit_complete(
        "dbr-ar-2 — closed (dan-authorized governance decision); this closure closes zero b5 activation"
        " blockers, the blocker census remains nine with 8 of 9 open, and production remains not ready /"
        " do-not-activate."
    )  # date-free
    assert _claims_routing_audit_complete(
        "dbr-ar-2 — closed (dan-authorized governance decision, 2026-07-16); production remains not ready / do-not-activate."
    )  # count-free and zero-closure-free
    assert _claims_routing_audit_complete(
        "dbr-ar-2 — closed (dan-authorized governance decision, 2026-07-16); this closure closes zero b5"
        " activation blockers, the blocker census remains nine with 8 of 9 open."
    )  # production-posture-free
    # References, cell boundaries, fail-closed vocabulary, and identifiers stay out of scope.
    assert not _claims_routing_audit_complete("see the DBR-AR-2 closure record below (Dan-authorized governance decision, 2026-07-16)")
    assert not _claims_routing_audit_complete(
        "| durable routing audit (DBR-AR-2) — not a gate §5 activation condition | B5-BLK-4 — CLOSED (B5-E, 2026-07-12) |"
    )
    assert not _claims_routing_audit_complete("internal code routing_audit_unavailable; the request is denied fail closed")
    assert not _claims_routing_audit_complete(_DBR_V1_STATUS_SENTENCE), "the exact V1 status sentence stays sanctioned"
    assert _claims_routing_audit_complete("no durable routing-audit adapter is delivered by v1"), (
        "a shortened V1-status variant stays unmasked"
    )
    # The per-document canonical anchor is non-vacuous; the superseded-sentence rejection fires.
    for doc in _GATE_DOCS:
        norm_doc = _normalized_doc(doc.read_text(encoding="utf-8"))
        assert _DBR_CLOSURE_SENTENCE in norm_doc, doc.name
        assert _DBR_CLOSURE_SENTENCE not in norm_doc.replace(_DBR_CLOSURE_SENTENCE, ""), doc.name
    assert _DBR_CLOSURE_SENTENCE not in _normalized_doc("dbr-ar-2 — closed.")
    assert _DBR_SUPERSEDED_OPEN_SENTENCE in _normalized_doc(
        "DBR-AR-2 (durable routing audit) remains OPEN — a separate Database Router follow-on."
    ), "a resurrected superseded open sentence must be detectable"


# --- G10: production deployment not complete --------------------------------
# Fix R1 §8: bounded deployed/shipped/promoted/live synonym coverage.
_PRODUCTION_DEPLOYED_PHRASES = (
    "production deployment complete",
    "production deployment is complete",
    "production deployment completed",
    "production deployment proven",
    "production deployment done",
    "production deployment finished",
    "production deployment achieved",
    "production deployment in place",
    "production deployment shipped",
    "production deployment succeeded",
    "deployed to production",
    "deployed to prod",
    "deployed in production",
    "production is deployed",
    "production runtime activated",
    "production supervision complete",
    "production supervision in place",
    "live in production",
    "shipped to production",
    "shipped to prod",
    "promoted to production",
    "promoted to prod",
    "released to production",
    "production rollout complete",
    "running in production",
    "gone live",
    "went live",
    "now live",
    "is live in prod",
    "production activated",
    "activated in production",
)


def _claims_production_deployed(text: str) -> bool:
    low = text.lower()
    return any(b in low for b in _PRODUCTION_DEPLOYED_PHRASES)


def test_b5d_10_production_not_deployed() -> None:
    t = _gate_docs_text()
    assert not _claims_production_deployed(t), "production deployment must not be claimed complete"
    low = t.lower()
    assert "production deployment" in low and ("open" in low or "required" in low), (
        "production deployment/supervision must be recorded as OPEN"
    )


def test_b5d_10_production_nonvacuity() -> None:
    assert _claims_production_deployed("Production deployment complete and supervised")
    # Fix R1: every added deployed/shipped/promoted/live equivalent fires.
    for phrase in _PRODUCTION_DEPLOYED_PHRASES:
        assert _claims_production_deployed(f"Status: {phrase}."), phrase
    assert _claims_production_deployed("The runtime was shipped to production yesterday")
    assert _claims_production_deployed("The B5 runtime has gone live")
    assert not _claims_production_deployed("Production deployment / supervision — OPEN (deployment evidence required)")


# --- G11: Lovable / API-Gateway cutover not complete ------------------------
# Fix R1 §8: bounded cutover/migrated/re-pointed/switched synonym coverage.
# Completion-asserting forms only — the honest docs describe the cutover as a
# pending/planned step, so plan-tense wording must not false-positive.
_LOVABLE_CUTOVER_DONE_PHRASES = (
    "cutover complete",
    "cutover is complete",
    "cutover completed",
    "cutover done",
    "cutover finished",
    "cutover achieved",
    "cutover executed",
    "cutover performed",
    "cutover shipped",
    "lovable cutover complete",
    "cutover: complete",
    "fully cut over",
    "lovable integrated through the api gateway",
    "has been re-pointed",
    "was re-pointed",
    "now re-pointed",
    "has been repointed",
    "was repointed",
    "re-pointed off supabase",
    "migrated off supabase",
    "has been migrated",
    "was migrated",
    "migration off supabase complete",
    "switched off supabase",
    "has been switched",
    "was switched",
    "now switched",
    "supabase decommissioned",
    "supabase retired",
)


def _claims_lovable_cutover_complete(text: str) -> bool:
    low = text.lower()
    return any(b in low for b in _LOVABLE_CUTOVER_DONE_PHRASES)


def test_b5d_11_lovable_cutover_open() -> None:
    t = _gate_docs_text()
    assert not _claims_lovable_cutover_complete(t), "the Lovable/API-Gateway cutover must not be claimed complete"
    assert "cutover" in t.lower(), "the Lovable/API-Gateway cutover must be recorded (kept separate/open)"


def test_b5d_11_lovable_nonvacuity() -> None:
    assert _claims_lovable_cutover_complete("The Lovable cutover is complete")
    # Fix R1: every added cutover/migrated/re-pointed/switched equivalent fires.
    for phrase in _LOVABLE_CUTOVER_DONE_PHRASES:
        assert _claims_lovable_cutover_complete(f"Status: {phrase}."), phrase
    assert _claims_lovable_cutover_complete("The frontend data layer has been re-pointed at the API Gateway")
    assert _claims_lovable_cutover_complete("Lovable was migrated off Supabase last week")
    assert not _claims_lovable_cutover_complete("Lovable / API-Gateway cutover — separate track (interim Supabase/RLS)")
    assert not _claims_lovable_cutover_complete("the RPC seam is to be re-pointed at the API Gateway at cutover (pending)")


# --- G12: next step stays the governed, Dan-authorized sequence --------------
# B5-E evolution: the closure review has been performed; the pinned next step is
# now the next Dan-authorized governed slice (deployment-scope blockers,
# product/integration track, or the DBR-AR-2 follow-on PRD) — never a bypass.
def _states_governed_next_step(text: str) -> bool:
    # Line-scoped: the NEXT-STEP statement must itself commit to the governed,
    # Dan-authorized sequence. Coarse corpus-wide co-occurrence would not catch
    # a bypass, since the words also appear in unrelated sentences.
    for line in text.lower().splitlines():
        if "next step" in line and "dan-authorized" in line and "governed" in line:
            return True
    return False


def test_b5d_12_next_step_separate_closure() -> None:
    t = _gate_docs_text()
    assert _states_governed_next_step(t), "docs must state the next step is the next Dan-authorized governed slice"
    for doc in _GATE_DOCS:
        assert _NEXT_STEP_SENTENCE in _normalized_doc(doc.read_text(encoding="utf-8")), (
            f"the exact next-step sentence must be present in {doc.name} itself"
        )
    low = t.lower()
    assert "does not perform" in low or "neither performs nor bypasses" in low or "does not perform or bypass" in low, (
        "docs must state the re-grounding did not perform/bypass the separate closure decision"
    )


def test_b5d_12_next_step_nonvacuity() -> None:
    assert not _states_governed_next_step("Next step: activate production runtime now")
    assert not _states_governed_next_step("the next step is a separate Dan-authorized closure review")  # pre-B5-E wording
    assert _states_governed_next_step(
        "Next step: the next Dan-authorized governed slice; every remaining activation blocker is deployment-scope"
    )
    for doc in _GATE_DOCS:
        norm_doc = _normalized_doc(doc.read_text(encoding="utf-8"))
        assert _NEXT_STEP_SENTENCE in norm_doc, doc.name
        assert _NEXT_STEP_SENTENCE not in norm_doc.replace(_NEXT_STEP_SENTENCE, ""), doc.name


# --- G13 (B5-E): unrelated blockers keep their exact live statuses -----------
_OTHER_BLOCKER_IDS = tuple(f"b5-blk-{i}" for i in (1, 2, 3, 5, 6, 7, 8, 9))


def _other_blocker_marked_closed(text: str) -> bool:
    """No blocker other than B5-BLK-4 may carry closure wording — B5-E has no
    authority over them and there is no anchored allowance for any other id."""
    for raw in text.lower().splitlines():
        if not any(b in raw for b in _OTHER_BLOCKER_IDS):
            continue
        line = _B5BLK4_NEGATION_MASK.sub(" <negated> ", raw.replace("*", ""))
        if any(phrase in line for phrase in _B5BLK4_CLOSURE_PHRASES):
            return True
        if _B5BLK4_CLOSURE_WORD_RE.search(line):
            return True
    return False


def _register_row_is_open(register_text: str, blocker_id: str) -> bool:
    for raw in register_text.lower().splitlines():
        stripped = raw.replace("*", "").strip()
        if stripped.startswith(f"| {blocker_id} ") and "| open |" in stripped:
            return True
    return False


def test_b5e_13_unrelated_blockers_unchanged() -> None:
    t = _gate_docs_text()
    assert not _other_blocker_marked_closed(t), "no blocker other than B5-BLK-4 may be marked closed by the B5-E decision"
    reg = _BLOCKERS_DOC.read_text(encoding="utf-8")
    for i in (1, 2, 3, 5, 6, 7, 8, 9):
        assert _register_row_is_open(reg, f"b5-blk-{i}"), f"B5-BLK-{i} must remain OPEN on its register row"


def test_b5e_13_unrelated_blockers_nonvacuity() -> None:
    assert _other_blocker_marked_closed("B5-BLK-2 is now closed")
    assert _other_blocker_marked_closed("| **B5-BLK-7** | ... | CLOSED | YES |")
    assert _other_blocker_marked_closed("B5-BLK-5 no longer blocks activation")
    assert _other_blocker_marked_closed("the fleet work satisfies B5-BLK-2")
    assert not _other_blocker_marked_closed("B5-BLK-2 is not closed; production fleet evidence is still required")
    assert not _other_blocker_marked_closed(
        "every remaining activation blocker is deployment-scope (B5-BLK-2/3/7/8/9) or product/integration-track (B5-BLK-5/6)"
    )
    assert _register_row_is_open("| **B5-BLK-2** | desc | Critical | Infra | evidence | OPEN | YES |", "b5-blk-2")
    assert not _register_row_is_open("| **B5-BLK-2** | desc | Critical | Infra | evidence | CLOSED | YES |", "b5-blk-2")
    assert not _register_row_is_open("no such row", "b5-blk-2")


# --- G14 (B5-E): blocker counts agree and activation stays fail-closed -------
_ACTIVATION_READY_PHRASES = (
    "gate is ready",
    "gate: ready",
    "activation is ready",
    "ready to activate",
    "ready for activation",
    "activation approved",
    "activation authorized",
    "activate now",
    "standing decision: activate",
    "standing decision is activate",
)


def _claims_activation_ready(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in _ACTIVATION_READY_PHRASES)


def test_b5e_14_fail_closed_and_counts() -> None:
    t = _gate_docs_text()
    assert not _claims_activation_ready(t), "production activation must not be claimed ready while blockers remain open"
    assert "9 / 9" not in t, "the stale 9 / 9 blocker count must not persist after the B5-E closure"
    reg = _BLOCKERS_DOC.read_text(encoding="utf-8")
    assert "NOT READY (8 / 9 blockers OPEN" in reg, "the register must record the recalculated 8 / 9 open count"
    for doc in _GATE_DOCS:
        assert _FAIL_CLOSED_SENTENCE in _normalized_doc(doc.read_text(encoding="utf-8")), (
            f"the fail-closed activation sentence must be present in {doc.name} itself"
        )


def test_b5e_14_fail_closed_nonvacuity() -> None:
    for phrase in _ACTIVATION_READY_PHRASES:
        assert _claims_activation_ready(f"Status: {phrase}."), phrase
    assert not _claims_activation_ready("decision   ACTIVATE / DO-NOT-ACTIVATE (default DO-NOT-ACTIVATE)")
    assert not _claims_activation_ready("A request to activate is READY only if all of the following are proven")
    assert not _claims_activation_ready("Production runtime activation remains NOT READY / DO-NOT-ACTIVATE")
    for doc in _GATE_DOCS:
        norm_doc = _normalized_doc(doc.read_text(encoding="utf-8"))
        assert _FAIL_CLOSED_SENTENCE in norm_doc, doc.name
        assert _FAIL_CLOSED_SENTENCE not in norm_doc.replace(_FAIL_CLOSED_SENTENCE, ""), doc.name
    assert _FAIL_CLOSED_SENTENCE not in _normalized_doc(
        "production runtime activation remains not ready / do-not-activate — 9 of 9 activation blockers remain open"
    )


# --- G15 (B5-E Fix R1): §5 non-waiver posture — exact per-document sentence ---
# anchor + corpus-wide affirmative-waiver detector.
# The exact normalized non-waiver sentence must be present in EVERY gate doc
# itself (a sibling document cannot satisfy a deleted, flipped, shortened, or
# rewritten sentence), and no affirmative waiver claim may appear anywhere in
# the three-document corpus — the detector is deliberately NOT scoped to lines
# carrying the `b5-blk-4` token. Allowed and masked before detection: the §5
# conditional noun phrase "or an explicit, approved waiver", explicitly negated
# wording ("is not waived", "does not waive", "no waiver", "is not a waiver",
# "does not constitute a waiver"), and subjunctive/hypothetical forms ("an
# explicit approved waiver would be required", "could waive"). Finite
# vocabularies only — as declared for the guards above, a paraphrase outside
# the pinned grant/release/effect vocabulary is out of detection scope.
_WAIVER_SENTENCE = (
    'the gate §5 activation condition "provisioning audit sink available (b-6) — or an explicit,'
    ' approved waiver" remains binding at activation time and is not waived by the b5-e closure'
)
_WAIVER_LEGAL_CONDITIONAL = "or an explicit, approved waiver"
_WAIVER_RELEASE_SCOPE_TERMS = ("audit sink", "audit-sink", "§5", "activation condition", "availability condition")
_WAIVER_RELEASE_WORDS = ("lifted", "suspended", "bypassed", "discharged", "removed", "vacated")
_WAIVER_EFFECT_WORDS = ("granted", "approved", "authorized", "authorised", "recorded", "issued", "effective")
_WAIVER_GRANT_VERBS = ("constitutes", "constitute", "grants", "grant", "approves", "authorizes", "authorises", "issues")
_WAIVER_GRANT_PAST_VERBS = ("constituted", "granted", "approved", "authorized", "authorised", "recorded", "issued")
_WAIVER_NEGATION_MASKS = (
    # explicitly negated participles: "not waived", "cannot be waived", "never bypassed", …
    re.compile(
        r"\b(?:not|never|neither|nor|cannot\s+be|can\s+never\s+be)\s+(?:\w+\s+){0,2}?"
        r"(?:waived|lifted|suspended|bypassed|discharged|removed|vacated)\b"
    ),
    # negated verb forms: "does not waive", "never waives", "not waiving", "without waiving"
    re.compile(r"\b(?:does\s+not|do\s+not|did\s+not|not|never|cannot|without)\s+(?:\w+\s+){0,2}?waiv(?:e|es|ing)\b"),
    # subjunctive/modal hypotheticals: "could waive", "would waive", "to waive"
    re.compile(r"\b(?:to|can|could|may|might|would)\s+waive\b"),
    # negated noun: "no waiver", "without a waiver", "no such waiver"
    re.compile(r"\b(?:no|without(?:\s+an?y?)?|absent\s+an?y?)\s+(?:such\s+)?(?:explicit\s+)?(?:approved\s+)?waivers?\b"),
    # "is not a waiver" / "was not an explicit approved waiver"
    re.compile(r"\b(?:is|are|was|were)\s+not\s+(?:an?|the)\s+(?:[\w,§()'/-]+\s+){0,3}?waivers?\b"),
    # negated granting verbs: "does not constitute", "never grants", …
    re.compile(
        r"\b(?:does\s+not|do\s+not|did\s+not|not|never|neither|nor)\s+(?:constitute|grant|approve|authorize|authorise|record|issue)s?\b"
    ),
    # subjunctive requirement: "an explicit approved waiver would be required …"
    re.compile(r"\bwaivers?\s+would\b"),
)
# affirmative waive/waived/waives/waiving surviving the negation masks
_WAIVER_AFFIRMED_RE = re.compile(r"\bwaived\b|\bwaiv(?:e|es|ing)\b")
# granting verb → waiver: "constitutes an explicit approved waiver", "authorizes a waiver"
_WAIVER_GRANTED_FORWARD_RE = re.compile(
    r"\b(?:constitutes?|grants?|approves|authorizes?|authorises?|issues?)\s+(?:an?|the|this|that)?\s*(?:[\w,§()'/-]+\s+){0,4}?waivers?\b"
)
# past-tense granting verbs are adjectives in the legal phrase, so they require an
# article/demonstrative before the noun: "approved the waiver", "granted a waiver"
_WAIVER_GRANTED_PAST_RE = re.compile(
    r"\b(?:constituted|granted|approved|authorized|authorised|recorded|issued)\s+(?:an?|the|this|that)\s+(?:[\w,§()'/-]+\s+){0,3}?waivers?\b"
)
# waiver in subject position with an affirmative effect predicate: "a waiver … has
# been granted", "a waiver is in effect", "the waiver remains in force"
_WAIVER_EFFECT_RE = re.compile(
    r"\bwaivers?\b[^.;:]{0,80}?\b(?:has\s+been|have\s+been|is|are|was|were|now|hereby|stands?|remains|becomes?|became)\s+"
    r"(?:\w+\s+){0,2}?(?:granted|approved|authorized|authorised|recorded|issued|effective)\b"
    r"|\bwaivers?\s+(?:is\s+|are\s+|now\s+|currently\s+|remains\s+)?in\s+(?:effect|force|place)\b"
)
# X-is-a-waiver equations: "the START-GATE is an explicit approved waiver"
_WAIVER_EQUATED_RE = re.compile(
    r"\b(?:is|are|was|were|becomes?|became|remains|amounts\s+to|serves\s+as|acts\s+as|counts\s+as|operates\s+as|functions\s+as|qualifies\s+as)"
    r"\s+(?:an?|the|this|that)\s+(?:[\w,§()'/-]+\s+){0,4}?waivers?\b"
)
# condition-release claims, scoped to lines about the §5/audit-sink condition so
# unrelated lifecycle wording ("a Ready tenant is Suspended first") cannot false-positive
_WAIVER_RELEASE_RE = re.compile(
    r"\bno\s+longer\s+(?:binding|required|applies|needed|in\s+force|in\s+effect)\b"
    r"|\b(?:is|are|was|were|has\s+been|have\s+been|hereby|now|stands?)\s+(?:\w+\s+){0,2}?"
    r"(?:lifted|suspended|bypassed|discharged|removed|vacated|set\s+aside)\b"
)


def _affirms_waiver(text: str) -> bool:
    """True when any line of the corpus makes an affirmative waiver claim: the §5
    audit-sink condition waived/lifted/suspended/bypassed/no-longer-binding, a
    waiver granted/approved/authorized/recorded/effective/in effect, or the B5-E
    closure / Dan START-GATE constituting or authorizing a waiver."""
    for raw in text.lower().splitlines():
        line = raw.replace("*", "").replace(_WAIVER_LEGAL_CONDITIONAL, " <legal-conditional> ")
        for mask in _WAIVER_NEGATION_MASKS:
            line = mask.sub(" <negated> ", line)
        if _WAIVER_AFFIRMED_RE.search(line):
            return True
        if _WAIVER_GRANTED_FORWARD_RE.search(line) or _WAIVER_GRANTED_PAST_RE.search(line):
            return True
        if _WAIVER_EFFECT_RE.search(line) or _WAIVER_EQUATED_RE.search(line):
            return True
        if any(term in line for term in _WAIVER_RELEASE_SCOPE_TERMS) and _WAIVER_RELEASE_RE.search(line):
            return True
    return False


def test_b5e_15_waiver_posture_pinned() -> None:
    t = _gate_docs_text()
    assert not _affirms_waiver(t), (
        "no affirmative waiver claim (B5-E/START-GATE-as-waiver, waiver granted/approved/in effect,"
        " §5 condition waived/lifted/suspended/bypassed/no-longer-binding) may appear in the gate docs"
    )
    for doc in _GATE_DOCS:
        assert _WAIVER_SENTENCE in _normalized_doc(doc.read_text(encoding="utf-8")), (
            f"the exact gate-§5 non-waiver sentence must be present in {doc.name} itself"
        )


def test_b5e_15_waiver_nonvacuity() -> None:
    # PRD B5-E Fix R1 §6 required-fail set — every claim class fires.
    assert _affirms_waiver("The gate §5 activation condition is waived by the B5-E closure.")
    assert _affirms_waiver("The B5-E closure waives the production audit-sink availability condition.")
    assert _affirms_waiver("The Dan B5-E START-GATE constitutes an explicit approved waiver.")
    assert _affirms_waiver("The Dan B5-E START-GATE authorizes a waiver of gate §5.")
    assert _affirms_waiver("A waiver of the production audit-sink requirement has been granted.")
    assert _affirms_waiver("The production audit-sink condition is no longer binding.")
    assert _affirms_waiver("The production audit-sink condition is bypassed by Decision A.")
    assert _affirms_waiver("The production audit-sink condition is no longer required.")
    # the detector fires WITHOUT the B5-BLK-4 token anywhere on the line (PRD §6)
    assert _affirms_waiver("the activation condition is hereby waived")
    # mutation-20 forms: START-GATE-as-waiver and Dan-approved-the-waiver
    assert _affirms_waiver("Dan approved the waiver.")
    assert _affirms_waiver("The Dan B5-E START-GATE grants a waiver.")
    assert _affirms_waiver("The Dan B5-E START-GATE approves a waiver of the audit-sink condition.")
    assert _affirms_waiver("The START-GATE is an explicit approved waiver.")
    assert _affirms_waiver("The START-GATE serves as the waiver.")
    assert _affirms_waiver("The B5-E closure and the START-GATE together waive the production audit-sink condition.")
    assert _affirms_waiver("Decision A is waiving the production audit-sink condition.")
    assert _affirms_waiver("A waiver is in effect.")
    assert _affirms_waiver("The waiver remains in force.")
    assert _affirms_waiver("The waiver is hereby recorded and effective.")
    assert _affirms_waiver("The production audit-sink condition is set aside by Decision A.")
    # every release / effect / granting vocabulary item fires (per-branch coverage)
    for word in _WAIVER_RELEASE_WORDS:
        assert _affirms_waiver(f"The production audit-sink condition is {word} by Decision A."), word
    for word in _WAIVER_EFFECT_WORDS:
        assert _affirms_waiver(f"A waiver of the production audit-sink requirement has been {word}."), word
    for verb in _WAIVER_GRANT_VERBS:
        assert _affirms_waiver(f"The Dan B5-E START-GATE {verb} a waiver of gate §5."), verb
    for verb in _WAIVER_GRANT_PAST_VERBS:
        assert _affirms_waiver(f"The Dan B5-E START-GATE {verb} the waiver of gate §5."), verb
    for term in _WAIVER_RELEASE_SCOPE_TERMS:
        assert _affirms_waiver(f"The {term} for production is no longer binding."), term
    # PRD §7 explicitly allowed wording — all stay green.
    assert not _affirms_waiver("The gate §5 activation condition remains binding and is not waived by B5-E.")
    assert not _affirms_waiver("An explicit approved waiver would be required if the audit sink were unavailable.")
    assert not _affirms_waiver("No waiver is granted by this decision.")
    assert not _affirms_waiver("The START-GATE authorizes the closure review; it does not waive the production audit-sink condition.")
    assert not _affirms_waiver("or an explicit, approved waiver")
    assert not _affirms_waiver("provisioning audit sink available (B-6) — or an explicit, approved waiver")
    assert not _affirms_waiver("Production-environment availability stays a gate §5 activation condition — not waived.")
    # explicit-negation and subjunctive mask branches — each stays green
    assert not _affirms_waiver("The closure does not constitute a waiver of the production audit-sink condition.")
    assert not _affirms_waiver("The Dan B5-E START-GATE is not a waiver.")
    assert not _affirms_waiver("The decision proceeds without waiving the production audit-sink condition.")
    assert not _affirms_waiver("Activation cannot proceed without a waiver unless the audit sink is available.")
    assert not _affirms_waiver("Only a separate Dan-authorized decision could waive the §5 condition.")
    assert not _affirms_waiver("The production audit-sink condition is not lifted, and it is never bypassed.")
    assert not _affirms_waiver("The gate §5 activation condition cannot be waived by a closure review.")
    # release vocabulary OUTSIDE the §5/audit-sink scope stays green (no subjectless false positive)
    assert not _affirms_waiver("direct Ready → Decommissioned transition is removed (a Ready tenant is Suspended first).")
    assert not _affirms_waiver("The old branch was removed after the merge.")
    # per-document anchor is non-vacuous: deletion, polarity flip, shortening, and a
    # B5-E-becomes-the-waiver rewrite each break the pin in that document itself.
    for doc in _GATE_DOCS:
        norm_doc = _normalized_doc(doc.read_text(encoding="utf-8"))
        assert _WAIVER_SENTENCE in norm_doc, doc.name
        assert _WAIVER_SENTENCE not in norm_doc.replace(_WAIVER_SENTENCE, ""), doc.name
        assert _WAIVER_SENTENCE not in norm_doc.replace("is not waived", "is waived"), doc.name
        assert _WAIVER_SENTENCE not in norm_doc.replace(" remains binding at activation time and is not waived by the b5-e closure", ""), (
            doc.name
        )
    flipped = _WAIVER_SENTENCE.replace("is not waived", "is waived")
    assert _WAIVER_SENTENCE not in _normalized_doc(flipped)
    assert _affirms_waiver(flipped)
    rewrite = (
        'the gate §5 activation condition "provisioning audit sink available (b-6) — or an explicit,'
        ' approved waiver" is satisfied because the b5-e closure constitutes the approved waiver'
    )
    assert _WAIVER_SENTENCE not in _normalized_doc(rewrite)
    assert _affirms_waiver(rewrite)
    # the unmutated sentence itself stays green under the detector
    assert not _affirms_waiver(_WAIVER_SENTENCE)


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
            test_b5d_06_b5blk4_closure_decision,
            test_b5d_06_b5blk4_nonvacuity,
            test_b5d_07_mvp_not_complete,
            test_b5d_07_mvp_nonvacuity,
            test_b5d_08_granularity_not_cluster,
            test_b5d_08_granularity_nonvacuity,
            test_b5d_09_routing_audit_closure_exact,
            test_b5d_09_routing_audit_nonvacuity,
            test_b5d_10_production_not_deployed,
            test_b5d_10_production_nonvacuity,
            test_b5d_11_lovable_cutover_open,
            test_b5d_11_lovable_nonvacuity,
            test_b5d_12_next_step_separate_closure,
            test_b5d_12_next_step_nonvacuity,
            test_b5e_13_unrelated_blockers_unchanged,
            test_b5e_13_unrelated_blockers_nonvacuity,
            test_b5e_14_fail_closed_and_counts,
            test_b5e_14_fail_closed_nonvacuity,
            test_b5e_15_waiver_posture_pinned,
            test_b5e_15_waiver_nonvacuity,
        ]
    )
