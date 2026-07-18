"""B5-BLK-6C-D — closure-evidence-matrix text-drift guard (default suite; no DB, no network).

Static text-only boundary pins for the evidence-only closure matrix
``docs/runtime/b5_blk6_closure_evidence_matrix.md``. This guard binds no runtime, imports no database
driver, opens no socket, and touches no database. It exists to keep the matrix an honest
PROPOSED-EVIDENCE-ONLY assembly and to fail CLOSED on any future overclaim drift.

Exactly six tests:

1. test_closure_evidence_matrix_exists_and_has_all_r6_sections
2. test_closure_evidence_matrix_pins_accepted_evidence_references
3. test_closure_evidence_matrix_preserves_required_qualifiers
4. test_closure_evidence_matrix_lists_all_four_live_locations
5. test_closure_evidence_matrix_is_proposal_only_and_keeps_blocker_open
6. test_closure_evidence_matrix_rejects_effected_closure_and_production_overclaims

The guard POSITIVELY REQUIRES the foundation-tier / composed-Gateway-core / in-memory-recorder /
disposable-PostgreSQL / composition-level-isolation / Deferred / OUT OF SCOPE / PROPOSED-EVIDENCE-ONLY /
"B5-BLK-6 remains OPEN" / "8 of 9 OPEN" / "NOT READY / DO-NOT-ACTIVATE" needles, and REJECTS the effected
present/past-tense closure, 7-of-9 census, served/durable/write "complete", positive-IC-007-capability,
and production-ready overclaims. It distinguishes a PROPOSED future decision from an EFFECTED current-state
claim: the matrix may legitimately *propose* a future reconciliation, but must never *assert* an effected
closure.

Pure stdlib; standalone-runnable:
  python tests/architecture/test_b5_blk6_closure_evidence_matrix_boundaries.py

B5-BLK-6 remains OPEN; production remains NOT READY / DO-NOT-ACTIVATE. This guard closes no blocker.
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_MATRIX = _scan.REPO_ROOT / "docs" / "runtime" / "b5_blk6_closure_evidence_matrix.md"

# Accepted evidence references (Test 2). Case-sensitive presence against the raw document text.
_REQUIRED_PR_TOKENS = ["#86", "#87", "#88", "#89", "#90"]
_REQUIRED_SHAS = [
    "585ec8b",  # merge #86 (6A)
    "9eb892b",  # merge #87 (6B)
    "5b7da75",  # 6B source: bind IC-009 foundation-tier portal operations
    "1fb1a7c",  # 6B source: strengthen portal guard coverage
    "15b69e4",  # merge #88 (6C-A)
    "6c7aacc",  # merge #89 (6C-B)
    "aa7e9f1",  # 6C-A source: reconcile audit obligations
    "062e359",  # 6C-B source: bind workspace_memberships_read success audit
    "0b6d63e",  # 6C-C source: prove real Control-DB portal composition
    "663dc92",  # merge #90 (6C-C)
]
_REQUIRED_PATHS = [
    "backend/api_gateway/gateway.py",
    "backend/api_gateway/portal.py",
    "backend/tests/control_plane/requires_pg/b5_blk6_portal_binding_live_proof.py",
    "infrastructure/runbooks/b5_blk6_portal_binding_live_proof.md",
    "contracts/IC-007-Deal-Collaboration-Cross-Tenant-Sharing-Contract.md",
    "contracts/IC-010-API-Gateway-Contract.md",
]

# Positively required binding qualifiers (Test 3). Matched against the normalized text.
_REQUIRED_QUALIFIERS = [
    "foundation-tier",
    "composed gateway core",
    "in-memory recorder",
    "disposable postgresql",
    "composition-level isolation",
    "deferred",
    "out of scope",
]

# Four live stale locations (Test 4).
_LIVE_LOCATION_FILES = [
    "b5_activation_blockers.md",
    "dbr_ar_2_production_activation_evidence.md",
]
_LIVE_LOCATION_DESCRIPTORS = [
    "b5-blk-6 row",
    "b5-blk-6 taxonomy",
    "standing decision",
    "traceability row",
]
_LIVE_LOCATION_LABELS = [
    "reconciled by governance evidence record",
    "not edited by 6c-d",
    "current live status remains open",
]
_LIVE_LOCATION_COUNT = 4

# Positively required governance + proposal-framing needles (Test 5).
_REQUIRED_GOVERNANCE = [
    "proposed evidence only",
    "b5-blk-6 remains open",
    "8 of 9 open",
    "not ready / do-not-activate",
]
_PROPOSAL_FRAMING = [
    "proposed future governance decision",
    "not effected by this document",
]

# Rejected effected-state / overclaim patterns (Test 6). Matched against the normalized text.
# Each pattern targets an EFFECTED assertion; the matrix's PROPOSED framing must never trip these.
_FORBIDDEN_PATTERNS = [
    (r"b5-?blk-?6\s+is\s+closed", "effected 'B5-BLK-6 is CLOSED'"),
    (r"b5-?blk-?6\s+has\s+been\s+closed", "effected 'B5-BLK-6 has been closed'"),
    (r"b5-?blk-?6\s+is\s+currently\s+closed", "effected 'B5-BLK-6 is currently CLOSED'"),
    (r"b5-?blk-?6\s*[:=]\s*closed", "effected 'B5-BLK-6: CLOSED'"),
    (r"b5-?blk-?6\s*->\s*closed", "effected 'B5-BLK-6 -> CLOSED'"),
    (r"status\s*:\s*closed", "effected 'Status: CLOSED'"),
    (r"\b7\s*(?:of|/)\s*9\b", "census overclaim '7 of 9'"),
    (r"\bproduction\s+ready\b", "'production ready' overclaim"),
    (r"production\s+activation\s+authorized", "'production activation authorized' overclaim"),
    (r"served\s+northbound\s+ingress\s+complete", "'served northbound ingress complete' overclaim"),
    (r"durable\s+audit\s+persistence\s+complete", "'durable audit persistence complete' overclaim"),
    (r"persistent\s+write\s+path\s+complete", "'persistent write path complete' overclaim"),
    (
        r"positive\s+ic-?007\s+capability\s+(?:is\s+)?(?:implemented|built)",
        "'positive IC-007 capability implemented/built' overclaim",
    ),
]


def _text() -> str:
    assert _MATRIX.is_file(), "docs/runtime/b5_blk6_closure_evidence_matrix.md must exist"
    return _MATRIX.read_text(encoding="utf-8")


def _norm(s: str) -> str:
    """Lowercase, normalize dash/arrow glyphs, drop markdown emphasis, and collapse whitespace."""
    s = s.lower()
    s = s.replace("—", "-").replace("–", "-").replace("→", "->")
    s = s.replace("*", "").replace("`", "")
    return re.sub(r"\s+", " ", s)


def test_closure_evidence_matrix_exists_and_has_all_r6_sections() -> None:
    assert _MATRIX.is_file(), "docs/runtime/b5_blk6_closure_evidence_matrix.md must exist"
    text = _text()
    for n in range(1, 7):
        assert re.search(rf"(?m)^#{{2,4}}\s+R6-{n}\b", text), f"missing R6-{n} section heading"


def test_closure_evidence_matrix_pins_accepted_evidence_references() -> None:
    text = _text()
    for tok in _REQUIRED_PR_TOKENS:
        assert tok in text, f"missing accepted PR reference: {tok}"
    for sha in _REQUIRED_SHAS:
        assert sha in text, f"missing accepted evidence SHA: {sha}"
    for path in _REQUIRED_PATHS:
        assert path in text, f"missing accepted source/proof path: {path}"


def test_closure_evidence_matrix_preserves_required_qualifiers() -> None:
    norm = _norm(_text())
    for qualifier in _REQUIRED_QUALIFIERS:
        assert qualifier in norm, f"missing required qualifier needle: {qualifier!r}"


def test_closure_evidence_matrix_lists_all_four_live_locations() -> None:
    text = _text()
    norm = _norm(text)
    for filename in _LIVE_LOCATION_FILES:
        assert filename in text, f"missing live-location file reference: {filename}"
    for descriptor in _LIVE_LOCATION_DESCRIPTORS:
        assert descriptor in norm, f"missing live-location descriptor: {descriptor!r}"
    # Every one of the four live locations must carry all three reconciliation labels.
    for label in _LIVE_LOCATION_LABELS:
        assert norm.count(label) >= _LIVE_LOCATION_COUNT, f"label {label!r} must appear once per live location (>= {_LIVE_LOCATION_COUNT})"


def test_closure_evidence_matrix_is_proposal_only_and_keeps_blocker_open() -> None:
    norm = _norm(_text())
    for needle in _REQUIRED_GOVERNANCE:
        assert needle in norm, f"missing required governance needle: {needle!r}"
    for needle in _PROPOSAL_FRAMING:
        assert needle in norm, f"missing proposal-framing needle: {needle!r}"


def test_closure_evidence_matrix_rejects_effected_closure_and_production_overclaims() -> None:
    norm = _norm(_text())
    for pattern, label in _FORBIDDEN_PATTERNS:
        assert re.search(pattern, norm) is None, f"forbidden effected/overclaim wording present ({label}): matched /{pattern}/"


if __name__ == "__main__":
    _scan.run(
        [
            test_closure_evidence_matrix_exists_and_has_all_r6_sections,
            test_closure_evidence_matrix_pins_accepted_evidence_references,
            test_closure_evidence_matrix_preserves_required_qualifiers,
            test_closure_evidence_matrix_lists_all_four_live_locations,
            test_closure_evidence_matrix_is_proposal_only_and_keeps_blocker_open,
            test_closure_evidence_matrix_rejects_effected_closure_and_production_overclaims,
        ]
    )
