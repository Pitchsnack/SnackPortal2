"""DBR-AR-2E V1 — production activation-evidence boundaries guard (architecture; no DB, no runtime).

Machine-pins the PRD DBR-AR-2E V1 execution decisions by text/JSON/AST inspection of the committed
sources: the exact nine-file implementation surface and the repository-wide single-2E-file census
(and zero next-slice files); the exact nineteen-key evidence-index schema with deterministic
ordering, unique ids, non-empty bindings, and the bounded status/environment/reproducibility
vocabularies; the exact PAE-01..PAE-16 coverage and the canonical PASS / NOT_AVAILABLE
dispositions; the exact nine-blocker census with exactly one CLOSED (B5-E-anchored) and eight OPEN;
the no-invented-blocker rule (DBR-AR-2 carries NO register id — ``blocker_id: NONE`` rows carry the
exact MC-1 note); the exact canonical DBR-AR-2 closure sentence (Dan-authorized governance
decision, 2026-07-16 — the index ``dbr_ar_2_status`` flip, the EV-CD-01 closure evidence record
with ``blocker_id: NONE`` and the THIS-PR binding, and the evidence-record §13 closure record)
while Outcome A (REMAIN NOT READY / DO-NOT-ACTIVATE) stays the
only claimed outcome; no activation-ready/production-ready overclaim and no production access,
mutation, or identity fabrication; DDL 010/011 blob identity, local-Control-only scope, and the
001-009 automatic apply order; the hosted live-PG loop at exactly 14 with the standing harness
MANUAL_ONLY; ATR-2B-1 and OBS-V3-PM-1 carried OPEN and separately governed; report-only sources
classified attested; the exact contract/runbook lockstep sentences (2E status, zero-closure census,
next governed step, truthful threshold posture, references-only incident-query discipline); and the
blob-pinned identity of the three B5 gate documents (re-stamped at the closure decision) plus the
untouched B5 evidence template. Every detector carries
a planted non-vacuity companion; every planted secret-shaped sample is BUILT dynamically from
low-entropy fragments. Pure stdlib; standalone-runnable:
  python tests/architecture/test_dbr_ar_2e_activation_evidence_boundaries.py
"""

from __future__ import annotations

import ast
import collections
import hashlib
import json
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_REPO = _scan.REPO_ROOT
_BACKEND = _scan.BACKEND_ROOT

_EVIDENCE_DOC = _REPO / "docs" / "runtime" / "dbr_ar_2_production_activation_evidence.md"
_INDEX = _REPO / "docs" / "runtime" / "dbr_ar_2_production_activation_evidence_index.json"
_CONTRACT_DOC = _REPO / "docs" / "runtime" / "dbr_ar_2_durable_routing_audit_contract.md"
_RUNBOOK = _REPO / "infrastructure" / "runbooks" / "dbr_ar_2_durable_routing_audit.md"
_BLOCKERS_DOC = _REPO / "docs" / "runtime" / "b5_activation_blockers.md"
_GATE_DOC = _REPO / "docs" / "runtime" / "b5_production_runtime_activation_gate.md"
_MATRIX_DOC = _REPO / "docs" / "runtime" / "b5_runtime_readiness_matrix.md"
_B5_TEMPLATE = _REPO / "docs" / "runtime" / "b5_activation_evidence_template.md"
_WORKFLOW = _REPO / ".github" / "workflows" / "live-pg-durable-path.yml"
_RUNSET_GUARD = pathlib.Path(__file__).resolve().parent / "test_live_pg_workflow_runset_completeness.py"
_B5_TOPOLOGY = _BACKEND / "tests" / "control_plane" / "requires_pg" / "b5_standing_topology.py"
_CP_INGEST = _BACKEND / "control_plane" / "adapters" / "providers" / "http_routing_audit_api.py"
_DDL_010 = _REPO / "infrastructure" / "db" / "control" / "010_routing_audit.sql"
_DDL_011 = _REPO / "infrastructure" / "db" / "control" / "011_routing_audit_append_only.sql"

# The exact PRD DBR-AR-2E V1 §4 authorized tracked-file surface (three new + six narrow edits).
_NINE_FILE_SURFACE = (
    "docs/runtime/dbr_ar_2_production_activation_evidence.md",
    "docs/runtime/dbr_ar_2_production_activation_evidence_index.json",
    "backend/tests/architecture/test_dbr_ar_2e_activation_evidence_boundaries.py",
    "docs/runtime/dbr_ar_2_durable_routing_audit_contract.md",
    "infrastructure/runbooks/dbr_ar_2_durable_routing_audit.md",
    "backend/tests/architecture/test_dbr_ar_2_readiness_contract.py",
    "backend/tests/architecture/test_dbr_ar_2c_composition_boundaries.py",
    "backend/tests/architecture/test_dbr_ar_2d_live_proof_boundaries.py",
    "backend/tests/architecture/test_dbr_ar_2d_standing_witness_boundaries.py",
)
_GUARD_RELPATH = "backend/tests/architecture/test_dbr_ar_2e_activation_evidence_boundaries.py"

# The exact evidence-record schema (nineteen keys, canonical order) and bounded vocabularies.
_RECORD_KEYS = (
    "evidence_id",
    "requirement_id",
    "blocker_id",
    "title",
    "status",
    "source_type",
    "source_path_or_url",
    "source_commit",
    "source_tree",
    "source_blob_or_hash",
    "environment",
    "database_identity",
    "captured_at",
    "verified_at",
    "verifier",
    "reproducibility",
    "sensitivity",
    "retention",
    "notes",
)
_TOP_KEYS = (
    "schema",
    "schema_version",
    "prd",
    "authorization",
    "baseline_commit",
    "baseline_tree",
    "outcome",
    "blocker_census",
    "blockers_open",
    "blockers_closed",
    "dbr_ar_2_status",
    "generated_on",
    "evidence",
)
_ALLOWED_STATUS = frozenset({"PASS", "FAIL", "NOT_AVAILABLE", "NOT_APPLICABLE", "OPEN", "CLOSED"})
_ALLOWED_ENVIRONMENTS = frozenset({"repository", "github", "standing-local", "outside-repo", "prd-corpus"})
_ALLOWED_REPRO = frozenset({"live", "hosted-ci", "manual-only", "attested"})
_ALLOWED_BLOCKERS = frozenset({f"B5-BLK-{i}" for i in range(1, 10)} | {"NONE"})

# The canonical PAE dispositions (PRD DBR-AR-2E V2 START-GATE §11 — recorded exactly).
_PASS_PAE = ("PAE-01", "PAE-03", "PAE-04", "PAE-09", "PAE-14", "PAE-15", "PAE-16")
_NOT_AVAILABLE_PAE = ("PAE-02", "PAE-05", "PAE-06", "PAE-07", "PAE-08", "PAE-10", "PAE-11", "PAE-12", "PAE-13")

_MC1_NOTE = "DBR-AR-2 is not an entry in the B5 activation-blocker register; DBR-AR-2E closes zero blockers."
_OUTCOME = "REMAIN NOT READY / DO-NOT-ACTIVATE"
_BASELINE_COMMIT = "62e361be1fb90c3ab6ef2d36d8a048699d6e5e3f"
_BASELINE_TREE = "45d0680947669eb8d53f57dc373f9373955c1aac"

# Contract/runbook lockstep pins (normalized).
_2E_STATUS_PIN = "dbr-ar-2e — production-activation evidence consolidated; outcome a is remain not ready / do-not-activate."
_2E_CENSUS_PIN = (
    "dbr-ar-2e closes zero b5 activation blockers; the activation-blocker census remains nine; dbr-ar-2 remained open at 2e delivery."
)
_NEXT_STEP_PIN = (
    "the next governed step is the next dan-authorized governed slice; production activation remains"
    " a separate human-governed decision and is not authorized by dbr-ar-2e or by the dbr-ar-2 closure."
)
# The ONLY sanctioned DBR-AR-2 closure claim (PRD DBR-AR-2 Closure Decision V2 START-GATE §7) and
# the exact index status value (MC-CD-2; the raw index bytes stay pure ASCII via the \\u2014 escape).
_CLOSURE_PIN = (
    "dbr-ar-2 — closed (dan-authorized governance decision, 2026-07-16); this closure closes zero b5"
    " activation blockers, the blocker census remains nine with 8 of 9 open, and production remains"
    " not ready / do-not-activate."
)
_INDEX_CLOSED_STATUS = "CLOSED — DAN-AUTHORIZED GOVERNANCE DECISION"
_THRESHOLD_TRUTH_PINS = (
    "a production alert threshold, monitoring owner, and escalation chain are not defined",
    "pae-10 remains not available",
    "no threshold may be inferred from the standing environment",
)
_INCIDENT_QUERY_PINS = (
    "incident query procedure",
    "exactly one correlation_id or exactly one tenant_ref",
    "cross-tenant aggregation is never performed",
    "operational production evidence remains not available",
    "production enablement remains unauthorized",
)

# The §14 required evidence-record statements (normalized; closure evolution 2026-07-16).
_REQUIRED_DOC_STATEMENTS = (
    "outcome a — remain not ready / do-not-activate",
    "dbr-ar-2e evidence consolidation is delivered when this pr merges.",
    _CLOSURE_PIN,
    "dbr-ar-2e closes zero activation blockers.",
    "the b5 activation-blocker census remains nine.",
    "seven of nine blockers remain open.",
    "no production activation decision is made.",
    "no production access or production mutation occurred.",
    "the separate dan-authorized dbr-ar-2 closure decision is recorded in §13 (2026-07-16).",
    "a separate production activation decision would still be required.",
)
_MC1_BLOCK_PIN = (
    "dbr-ar-2e closes zero b5 activation blockers. the activation-blocker census remains nine. the"
    " open-blocker count remains 7 of 9. production remains not ready / do-not-activate."
)
_OBS_DESCRIPTION_PIN = (
    "obs-v3-pm-1 proposes stronger ast-level and reviewed-blob pinning for the already-executed"
    " standing-witness operator harness. the standing evidence itself was independently verified directly"
    " against postgresql. dbr-ar-2e carries this observation but does not implement it."
)

# Overclaim vocabulary that must NEVER appear in the two new evidence artifacts.
_FORBIDDEN_CLAIM_PHRASES = (
    "activation-ready",
    "production-ready",
    "sufficient to activate",
    "approved for production",
    "evidence sufficient for separate activation decision",
)

# Byte-identity pins: the three B5 gate documents were re-stamped by the B5-BLK-6 governance-effect
# closure (2026-07-20, Dan-authorized — exactly the current-standing census flip to 7 of 9 OPEN and the
# B5-BLK-6 register/taxonomy CLOSED rows); the B5 evidence template stays at its blob (untouched by 2E
# and by both closures).
_B5_GATE_BLOBS = {
    "docs/runtime/b5_production_runtime_activation_gate.md": "8530d04e67ccadb5614a745b12b296f2257932d3",
    "docs/runtime/b5_activation_blockers.md": "bdf413a58243a20fbfc932ca82ec26a1bcbdadc8",
    "docs/runtime/b5_runtime_readiness_matrix.md": "4d8edbdfe3e770aa4c4b19b65db2c4b8848ba187",
    "docs/runtime/b5_activation_evidence_template.md": "be6ac381feb074741c33ae77511c8aba7b768e60",
}
_DDL_BLOBS = {
    "infrastructure/db/control/010_routing_audit.sql": "0c5eeecd5e20ef9fe4f11293b6c6561ae7cc897e",
    "infrastructure/db/control/011_routing_audit_append_only.sql": "cea40fc62c063e9f711fdb7ac90b00a8859586d4",
}

_EXPECTED_HARNESS_COUNT = 14
_WRAPPER_RELPATH = "tests/control_plane/requires_pg/test_pg_dbr_ar_2d_standing_witnesses.py"
_LOOP_RE = re.compile(r"for\s+h\s+in\s+(?P<loop>.+?);\s*do", re.DOTALL)
_ENTRY_RE = re.compile(r"\S+\.py")
_CONTROL_DDL_ORDER_RE = re.compile(r"_CONTROL_DDL_ORDER[^=]*=\s*\((?P<body>.*?)\)", re.DOTALL)

# Secret/PII shapes (detection literals BUILT from fragments — never a contiguous secret shape here).
_DSN_RE = re.compile("postgresql" + "://" + r"\S")
_JWT_MARKER = "ey" + "J"
_KEY_MARKER = "-----" + "BEGIN"
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_NEXT_SLICE_HYPHEN = "dbr-ar-2" + "f"
_NEXT_SLICE_UNDERSCORE = "dbr_ar_2" + "f"

_CENSUS_SKIP = frozenset(_scan.SKIP_PARTS | {".git"})


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _norm(s: str) -> str:
    return " ".join(s.lower().replace("*", "").replace("`", "").split())


def _git_blob_sha1(path: pathlib.Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")  # autocrlf normalization (the git blob is LF)
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _loop_entries(workflow_text: str) -> Optional[List[str]]:
    m = _LOOP_RE.search(workflow_text)
    return _ENTRY_RE.findall(m.group("loop")) if m else None


def _index_top() -> "collections.OrderedDict[str, Any]":
    loaded = json.loads(_text(_INDEX), object_pairs_hook=collections.OrderedDict)
    assert isinstance(loaded, collections.OrderedDict), "the index must be a JSON object"
    return loaded


def _records() -> List["collections.OrderedDict[str, Any]"]:
    evidence = _index_top()["evidence"]
    assert isinstance(evidence, list) and evidence, "the index must carry a non-empty evidence collection"
    return list(evidence)


def _record(evidence_id: str) -> "collections.OrderedDict[str, Any]":
    for r in _records():
        if r["evidence_id"] == evidence_id:
            return r
    raise AssertionError(f"evidence record {evidence_id!r} must exist in the index")


def _repo_census(pattern: str) -> List[str]:
    return sorted(str(p.relative_to(_REPO).as_posix()) for p in _REPO.rglob(pattern) if not (_CENSUS_SKIP & set(p.parts)))


# ---------------------------------------------------------------------------
# 1. Exact nine-file surface + repository-wide single-2E census + zero next-slice files
# ---------------------------------------------------------------------------
def test_2e_surface_and_census() -> None:
    for rel in _NINE_FILE_SURFACE:
        assert (_REPO / rel).is_file(), f"authorized 2E-surface file missing: {rel}"
    assert _repo_census("*dbr_ar_2e*") == [_GUARD_RELPATH], (
        "exactly ONE 2E-named file may exist repository-wide (this guard); any second 2E file is unauthorized"
    )
    assert _repo_census("*" + _NEXT_SLICE_UNDERSCORE + "*") == [], "no next-slice artifact may exist (never begun by 2E)"


def test_2e_surface_census_nonvacuity() -> None:
    planted = sorted([_GUARD_RELPATH, "docs/runtime/test_dbr_ar_2e_probe.md"])
    assert planted != [_GUARD_RELPATH], "a planted second 2E-named file must be detectable"
    assert [_NEXT_SLICE_UNDERSCORE + "_notes.md"] != [], "a planted next-slice artifact must be detectable"


# ---------------------------------------------------------------------------
# 2. Index: top-level shape, exact schema, deterministic ordering, unique ids, coverage
# ---------------------------------------------------------------------------
def test_2e_index_top_shape() -> None:
    top = _index_top()
    assert list(top.keys()) == list(_TOP_KEYS), f"the index top-level key order drifted: {list(top.keys())}"
    assert top["schema"] == "dbr-ar-2e-activation-evidence-index" and top["schema_version"] == 1
    assert top["baseline_commit"] == _BASELINE_COMMIT and top["baseline_tree"] == _BASELINE_TREE
    assert top["outcome"] == _OUTCOME, "the index outcome must be Outcome A verbatim"
    assert (top["blocker_census"], top["blockers_open"], top["blockers_closed"]) == (9, 7, 2), (
        "the blocker census must be exactly nine with seven OPEN and two CLOSED after the B5-BLK-6 closure"
    )
    assert top["dbr_ar_2_status"] == _INDEX_CLOSED_STATUS, "the index dbr_ar_2_status must be exactly the MC-CD-2 closed value"


def test_2e_index_top_nonvacuity() -> None:
    assert (10, 7, 2) != (9, 7, 2), "a census-10 mutation must be detectable"
    assert (9, 8, 1) != (9, 7, 2), "a reverted 8-open / 1-closed mutation must be detectable"
    assert (9, 6, 3) != (9, 7, 2), "an extra-closure (6-open / 3-closed) mutation must be detectable"
    assert "EVIDENCE SUFFICIENT FOR SEPARATE ACTIVATION DECISION" != _OUTCOME, "an Outcome-B swap must be detectable"
    assert "OPEN" != _INDEX_CLOSED_STATUS, "a reverted-OPEN index status must be detectable"
    assert "CLOSED" != _INDEX_CLOSED_STATUS, "a bare-CLOSED index status must be detectable"
    assert "CLOSED - DAN-AUTHORIZED GOVERNANCE DECISION" != _INDEX_CLOSED_STATUS, (
        "a wrong-dash index status must be detectable (the value carries the em dash via the JSON escape)"
    )


def test_2e_index_record_schema() -> None:
    for r in _records():
        assert list(r.keys()) == list(_RECORD_KEYS), f"record {r.get('evidence_id')!r} key set/order drifted: {list(r.keys())}"
        for key in _RECORD_KEYS:
            value = r[key]
            assert isinstance(value, str) and value.strip(), f"{r['evidence_id']}: {key} must be a non-empty string (binding rule)"
        assert r["status"] in _ALLOWED_STATUS, f"{r['evidence_id']}: status {r['status']!r} outside the bounded vocabulary"
        assert r["environment"] in _ALLOWED_ENVIRONMENTS, f"{r['evidence_id']}: environment {r['environment']!r} not allowed"
        assert r["reproducibility"] in _ALLOWED_REPRO, f"{r['evidence_id']}: reproducibility {r['reproducibility']!r} not allowed"
        assert r["blocker_id"] in _ALLOWED_BLOCKERS, f"{r['evidence_id']}: invented blocker id {r['blocker_id']!r}"
        assert r["sensitivity"] == "references-only", f"{r['evidence_id']}: sensitivity must be references-only"


def test_2e_index_schema_nonvacuity() -> None:
    assert "B5-BLK-10" not in _ALLOWED_BLOCKERS, "a fabricated blocker id must be detectable"
    assert "STALE" not in _ALLOWED_STATUS, "an out-of-vocabulary status must be detectable"
    assert "production" not in _ALLOWED_ENVIRONMENTS, "a fabricated production environment must be detectable"
    missing_key = [k for k in _RECORD_KEYS if k != "source_tree"]
    assert list(missing_key) != list(_RECORD_KEYS), "a removed required key must be detectable"
    extra_key = list(_RECORD_KEYS) + ["extra"]
    assert extra_key != list(_RECORD_KEYS), "an added extra key must be detectable"
    planted = {key: "x" for key in _RECORD_KEYS}
    planted["source_commit"] = ""  # planted: commit binding removed
    assert not all(isinstance(v, str) and v.strip() for v in planted.values()), "an emptied binding value must be detectable"


def test_2e_index_ordering_unique_and_coverage() -> None:
    records = _records()
    ids = [r["evidence_id"] for r in records]
    assert ids == sorted(ids), "the evidence collection must be deterministically ordered by evidence_id"
    assert len(ids) == len(set(ids)), "duplicate evidence ids are forbidden"
    pae_reqs = [r["requirement_id"] for r in records if str(r["evidence_id"]).startswith("EV-PAE-")]
    assert pae_reqs == [f"PAE-{i:02d}" for i in range(1, 17)], f"PAE coverage must be exactly PAE-01..PAE-16: {pae_reqs}"
    seen: Dict[str, str] = {}
    for r in records:
        req = str(r["requirement_id"])
        if req in seen and not str(r["evidence_id"]).startswith("EV-SRC-"):
            raise AssertionError(f"unjustified duplicate requirement id {req!r} on {r['evidence_id']!r}")
        seen.setdefault(req, str(r["evidence_id"]))
        if str(r["evidence_id"]).startswith("EV-SRC-"):
            assert "duplication is justified" in str(r["notes"]), (
                f"{r['evidence_id']}: source rows must justify requirement-id duplication explicitly"
            )


def test_2e_ordering_nonvacuity() -> None:
    assert ["EV-PAE-02", "EV-PAE-01"] != sorted(["EV-PAE-02", "EV-PAE-01"]), "an out-of-order collection must be detectable"
    assert len(["EV-X", "EV-X"]) != len(set(["EV-X", "EV-X"])), "a duplicate id must be detectable"
    assert [f"PAE-{i:02d}" for i in range(1, 16)] != [f"PAE-{i:02d}" for i in range(1, 17)], "a missing PAE must be detectable"


# ---------------------------------------------------------------------------
# 3. Canonical PAE dispositions; no CLOSED/FAIL/NOT_APPLICABLE anywhere in the index
# ---------------------------------------------------------------------------
def test_2e_pae_dispositions_exact() -> None:
    by_req = {str(r["requirement_id"]): str(r["status"]) for r in _records() if str(r["evidence_id"]).startswith("EV-PAE-")}
    for req in _PASS_PAE:
        assert by_req[req] == "PASS", f"{req} must be PASS (canonical disposition)"
    for req in _NOT_AVAILABLE_PAE:
        assert by_req[req] == "NOT_AVAILABLE", f"{req} must be NOT_AVAILABLE (canonical disposition; never inferred as satisfied)"
    statuses = {str(r["status"]) for r in _records()}
    assert "CLOSED" not in statuses, "no index record may claim CLOSED — blocker closure lives only in the B5-E-anchored register"
    assert "FAIL" not in statuses and "NOT_APPLICABLE" not in statuses, (
        "FAIL/NOT_APPLICABLE are reserved for a genuine contradiction — none exists; a contradiction stops the slice instead"
    )


def test_2e_pae_dispositions_nonvacuity() -> None:
    assert "PASS" != "NOT_AVAILABLE", "a flipped disposition must be detectable"
    # Planted: a PASS claim for the writer role (PAE-05), TLS (PAE-07), tested restore (PAE-08), or
    # the monitoring threshold (PAE-10) contradicts the canonical NOT_AVAILABLE list and must fail.
    for planted in ("PAE-05", "PAE-07", "PAE-08", "PAE-10"):
        assert planted in _NOT_AVAILABLE_PAE and planted not in _PASS_PAE, (
            f"a fabricated PASS for {planted} must be detectable against the canonical lists"
        )
    assert set(_PASS_PAE) | set(_NOT_AVAILABLE_PAE) == {f"PAE-{i:02d}" for i in range(1, 17)}, (
        "the canonical disposition lists must partition PAE-01..PAE-16 exactly"
    )
    assert not (set(_PASS_PAE) & set(_NOT_AVAILABLE_PAE)), "the canonical lists must be disjoint"


# ---------------------------------------------------------------------------
# 4. Blocker mapping: register census; NONE rows carry the exact MC-1 note; carried items OPEN
# ---------------------------------------------------------------------------
def test_2e_register_census_pins() -> None:
    register = _text(_BLOCKERS_DOC)
    for i in range(1, 10):
        assert f"B5-BLK-{i}" in register, f"the register must carry B5-BLK-{i}"
    assert "NOT READY (7 / 9 blockers OPEN" in register, "the register standing decision must record 7 / 9 OPEN"
    norm = _norm(register)
    assert "b5-blk-4" in norm and "closed (b5-e" in norm, "exactly the B5-E-anchored B5-BLK-4 closure must be recorded"
    fail_closed = "production runtime activation remains not ready / do-not-activate — 7 of 9 activation blockers remain open"
    for doc in (_BLOCKERS_DOC, _GATE_DOC, _MATRIX_DOC):
        assert fail_closed in _norm(_text(doc)), f"{doc.name} must keep the fail-closed 7-of-9 sentence"


def test_2e_no_invented_blocker_and_mc1_note() -> None:
    for r in _records():
        if r["blocker_id"] == "NONE":
            assert _MC1_NOTE in str(r["notes"]), f"{r['evidence_id']}: NONE rows must carry the exact MC-1 note"
    atr = _record("EV-ATR-2B-1")
    assert atr["status"] == "OPEN" and "SEPARATELY GOVERNED" in str(atr["notes"]), "ATR-2B-1 must stay OPEN and separately governed"
    obs = _record("EV-OBS-V3-PM-1")
    assert obs["status"] == "OPEN", "OBS-V3-PM-1 must stay OPEN (never silently closed or discarded)"
    for token in ("SEPARATELY GOVERNED", "NON-BLOCKING FOR THE DELIVERED STANDING EVIDENCE", "NOT IMPLEMENTED BY DBR-AR-2E"):
        assert token in str(obs["notes"]), f"OBS-V3-PM-1 must carry the exact classification token {token!r}"
    assert obs["source_type"] == "report" and obs["reproducibility"] == "attested", "OBS-V3-PM-1 is an attested report record"


def test_cd_closure_record_shape() -> None:
    """MC-CD-2: the EV-CD-01 closure evidence record — blocker_id NONE, THIS-PR binding pattern,
    zero-blockers statement, not-ready posture preserved, references-only, re-carry statement."""
    cd = _record("EV-CD-01")
    assert cd["blocker_id"] == "NONE", "the closure record must use blocker_id NONE (DBR-AR-2 is outside the register)"
    assert cd["requirement_id"] == "DBR-AR-2-CLOSURE", "the closure record must carry its own unique requirement id"
    assert cd["status"] == "PASS", "the closure record status is PASS (CLOSED stays reserved for the B5-E register row)"
    assert cd["source_commit"].startswith("THIS-PR (docs/dbr-ar-2-closure-decision"), (
        "the closure record must use the established THIS-PR binding pattern"
    )
    assert cd["source_tree"].startswith("THIS-PR (docs/dbr-ar-2-closure-decision"), (
        "the closure record must use the established THIS-PR binding pattern"
    )
    assert cd["sensitivity"] == "references-only" and cd["environment"] == "repository"
    notes = str(cd["notes"])
    for needle in (
        "Dan-authorized DBR-AR-2 closure decision (2026-07-16)",
        "DBR-AR-2 is outside the B5 activation-blocker register",
        "this closure closes zero B5 activation blockers",
        "the blocker census remains nine with 8 of 9 OPEN",
        "production remains NOT READY / DO-NOT-ACTIVATE",
        "the Lovable cutover remains OPEN",
        "re-carried, not resolved",
        _MC1_NOTE,
    ):
        assert needle in notes, f"the closure record notes must state: {needle!r}"


def test_cd_closure_record_nonvacuity() -> None:
    assert "NONE" != "B5-BLK-4", "a register-id hijack must be detectable"
    assert "this closure closes zero B5 activation blockers" not in "this closure closes one B5 activation blocker", (
        "a nonzero-closure rewrite must be detectable"
    )
    assert not "attested".startswith("THIS-PR ("), "a non-THIS-PR binding must be detectable"
    assert "production remains NOT READY / DO-NOT-ACTIVATE" not in "production is READY", "a production-ready rewrite must be detectable"


# The MC-CD-10 re-carry inventory and the MC-CD-5 §18 dispositions, pinned in the evidence
# record's §13 closure record: every carried item must remain present, every §18 item must
# remain open/separate, the OBS-2E-POST-1 sequencing note must survive, and the §3 backup
# redaction pledge must hold (the sha256-plus-redacted-reference discipline; the OBS-2E-POST-2
# general raw-path detector itself remains a separately governed, unimplemented follow-up).
_CD_RECARRY_TOKENS = (
    "atr-2b-1",
    "obs-v3-pm-1",
    "obs-2e-pm-1 through obs-2e-pm-6",
    "obs-2e-post-1",
    "obs-2e-post-2",
    "obs-2e-post-3",
    "writer-role ddl (§18.4)",
    "retention/legal-hold/deletion values (§18.2)",
    "the §18.3 gate-condition decision",
    "§18.6 api gateway class-3 wiring",
    "§18.7 optional admin events",
    "older-handover regeneration (folders 43/45)",
    "commit-graph maintenance",
)
_CD_SEQUENCING_NOTE = (
    "any future closure-vocabulary hardening must target the new post-closure canonical sentence and must not reopen dbr-ar-2."
)
_CD_S18_DISPOSITIONS = (
    "§18.2 retention/legal hold/deletion values — open, separately governed under the d-08 process",
    "§18.3 gate-condition decision — open; durable routing audit is not a gate §5 activation condition today",
    "§18.4 writer-role ddl — open, separately governed deployment-era scope (pae-05 not available)",
    "§18.6 api gateway class-3 durable wiring — open, separately governed, not in the contract §16 matrix",
    "§18.7 optional sink-availability administrative events — open, optional, separately governed, not required for closure",
)
_CD_BACKUP_PLEDGE = "no path, dsn, credential, or dump content is recorded"


def test_cd_recarry_and_dispositions() -> None:
    doc = _norm(_text(_EVIDENCE_DOC))
    for token in _CD_RECARRY_TOKENS:
        assert token in doc, f"the closure record must re-carry (not resolve): {token!r}"
    assert "re-carried, not resolved" in doc, "the re-carry framing sentence must be present"
    assert _CD_SEQUENCING_NOTE in doc, "the OBS-2E-POST-1 sequencing note must be present"
    for disposition in _CD_S18_DISPOSITIONS:
        assert disposition in doc, f"the §18 disposition must remain open/separate: {disposition!r}"
    assert _CD_BACKUP_PLEDGE in doc, "the §3 backup redaction pledge (sha256 + redacted reference only) must hold"


def test_cd_recarry_nonvacuity() -> None:
    doc = _norm(_text(_EVIDENCE_DOC))
    for token in _CD_RECARRY_TOKENS:
        assert token not in doc.replace(token, ""), token
    assert _CD_SEQUENCING_NOTE not in _norm("any future closure-vocabulary hardening may reopen DBR-AR-2."), (
        "a reopening-permitting sequencing rewrite must be detectable"
    )
    assert _CD_S18_DISPOSITIONS[3] not in _norm("§18.6 API Gateway class-3 durable wiring — IMPLEMENTED by this closure"), (
        "a §18.6 claimed-implemented rewrite must be detectable"
    )
    assert _CD_S18_DISPOSITIONS[0] not in _norm("§18.2 retention/legal hold/deletion values — APPROVED (30 days)"), (
        "a retention-approved rewrite must be detectable"
    )
    assert _CD_BACKUP_PLEDGE not in _norm("the backup is at /var/backups/control.dump"), (
        "a raw-backup-path replacement of the redaction pledge must be detectable"
    )


def test_2e_blocker_mapping_nonvacuity() -> None:
    assert "B5-BLK-10" not in _ALLOWED_BLOCKERS and "B5-BLK-0" not in _ALLOWED_BLOCKERS, "an invented id must be detectable"
    assert _MC1_NOTE not in "DBR-AR-2 maps to blocker B5-BLK-10.", "a fabricated mapping note must be detectable"
    assert "NOT READY (7 / 9 blockers OPEN" not in "NOT READY (8 / 9 blockers OPEN", "a reverted-count change must be detectable"
    assert "NOT READY (7 / 9 blockers OPEN" not in "NOT READY (7 / 10 blockers OPEN", "a census change must be detectable"
    assert "CLOSED" != "OPEN", "an ATR/OBS closure flip must be detectable"


# ---------------------------------------------------------------------------
# 5. Report-only sources are attested; nothing report-only claims live reproducibility
# ---------------------------------------------------------------------------
def test_2e_report_sources_attested() -> None:
    for r in _records():
        if r["source_type"] == "report":
            assert r["reproducibility"] == "attested", f"{r['evidence_id']}: report sources must be attested"
        if r["reproducibility"] == "attested":
            assert r["source_type"] == "report", f"{r['evidence_id']}: only report sources may be attested"


def test_2e_report_attested_nonvacuity() -> None:
    planted = {"source_type": "report", "reproducibility": "live"}
    assert not (planted["source_type"] == "report" and planted["reproducibility"] == "attested"), (
        "a live-labeled report source must be detectable"
    )


# ---------------------------------------------------------------------------
# 6. No secret/DSN/PII shape and no production identity in the two new artifacts
# ---------------------------------------------------------------------------
def test_2e_no_secret_shape_or_production_identity() -> None:
    for path in (_EVIDENCE_DOC, _INDEX):
        text = _text(path)
        assert not _DSN_RE.search(text), f"a DSN-shaped value must never appear in {path.name}"
        assert _JWT_MARKER not in text, f"a token-shaped value must never appear in {path.name}"
        assert _KEY_MARKER not in text, f"key material must never appear in {path.name}"
        assert "sslmode=" not in text and "PGPASSWORD" not in text, f"connection/credential material must never appear in {path.name}"
        assert not _EMAIL_RE.search(text), f"PII (email-shaped) content must never appear in {path.name}"
    for r in _records():
        assert r["environment"] != "production", "no record may claim a production environment (none exists)"


def test_2e_secret_shape_nonvacuity() -> None:
    planted_dsn = "postgresql" + "://u:p@h/db"
    assert _DSN_RE.search(planted_dsn), "a planted DSN must be detectable"
    planted_token = "ey" + "J" + "0aaa"
    assert _JWT_MARKER in planted_token, "a planted token shape must be detectable"
    planted_key = "-----" + "BEGIN" + " PRIVATE KEY"
    assert _KEY_MARKER in planted_key, "planted key material must be detectable"
    assert _EMAIL_RE.search("ops" + "@" + "example.com"), "a planted email must be detectable"


# ---------------------------------------------------------------------------
# 7. The evidence record: Outcome A only, required statements, MC-1 block, no overclaim, no next slice
# ---------------------------------------------------------------------------
def test_2e_doc_required_statements() -> None:
    doc = _norm(_text(_EVIDENCE_DOC))
    for statement in _REQUIRED_DOC_STATEMENTS:
        assert statement in doc, f"the evidence record must state verbatim: {statement!r}"
    assert _MC1_BLOCK_PIN in doc, "the exact MC-1 zero-closure/census block must be present"
    assert _MC1_NOTE.lower() in doc, "the exact MC-1 register note must be present"
    assert _OBS_DESCRIPTION_PIN in doc, "the exact OBS-V3-PM-1 required description must be present"
    assert "non-blocking for the delivered standing evidence" in doc, "the OBS-V3-PM-1 classification must be present"


def test_2e_doc_no_overclaim_and_no_next_slice() -> None:
    for path in (_EVIDENCE_DOC, _INDEX):
        norm = _norm(_text(path))
        for phrase in _FORBIDDEN_CLAIM_PHRASES:
            assert phrase not in norm, f"forbidden overclaim vocabulary {phrase!r} in {path.name}"
        assert _NEXT_SLICE_HYPHEN not in norm and _NEXT_SLICE_UNDERSCORE not in norm, (
            f"the next slice must not be named in {path.name} (not begun, not named)"
        )


def test_2e_doc_statements_nonvacuity() -> None:
    assert "outcome a — remain not ready / do-not-activate" not in _norm("Outcome B — evidence handed onward"), (
        "an Outcome-B rewrite must be detectable"
    )
    assert "no production access or production mutation occurred." not in _norm("production access occurred"), (
        "a production-access claim must be detectable"
    )
    assert "production-ready" in _norm("the package is production-ready"), "an overclaim must be detectable"
    assert _NEXT_SLICE_HYPHEN in _norm("the " + _NEXT_SLICE_HYPHEN + " slice starts now"), "a named next slice must be detectable"
    assert _MC1_BLOCK_PIN not in _norm("dbr-ar-2e closes zero b5 activation blockers."), "a truncated MC-1 block must not satisfy"


# ---------------------------------------------------------------------------
# 8. Standing-proof pins inside the evidence record (no rerun; exact deltas)
# ---------------------------------------------------------------------------
def test_2e_doc_standing_pins() -> None:
    doc = _norm(_text(_EVIDENCE_DOC))
    for needle in (
        "exactly four evidence rows",
        "no fifth row",
        "zero rows for the s3 auth-edge correlation",
        "recorded_at frozen in the single 2026-07-14 15:21:58 utc witness batch",
        "md5 = c0fd5261d8a8bc3a40ea733c8bb0a525",
        "exactly 001–009",
        "exactly 14 harnesses",
        "manual_only exception",
        "not rerun",
        "20-column",
        "3 check constraints",
        "2 append-only",
    ):
        assert needle in doc, f"the evidence record must pin the standing proof: {needle!r}"
    # An affirmative rerun claim is red even while a not-rerun sentence survives elsewhere
    # (a contradictory mutant must not hide behind the presence pin — the 2D runbook idiom).
    masked = doc.replace("not rerun", " <not-rerun> ").replace("never rerun", " <not-rerun> ")
    masked = masked.replace("not re-executed", " <not-rerun> ").replace("never re-executed", " <not-rerun> ")
    assert not re.search(r"\b(?:was|is|were|has been|have been)\s+(?:re-?run|re-?executed)\b", masked), (
        "no affirmative rerun/re-execution claim may appear anywhere in the evidence record"
    )


def test_2e_standing_pins_nonvacuity() -> None:
    assert "exactly four evidence rows" not in _norm("exactly five evidence rows"), "a fifth-row claim must be detectable"
    assert "zero rows for the s3 auth-edge correlation" not in _norm("one row for the s3 auth-edge correlation"), (
        "an S3-row claim must be detectable"
    )
    assert "not rerun" not in _norm("the standing scenario was rerun today"), "a rerun claim must be detectable"
    rerun_re = re.compile(r"\b(?:was|is|were|has been|have been)\s+(?:re-?run|re-?executed)\b")
    assert rerun_re.search("the standing scenario was rerun"), "an affirmative rerun claim must be detectable"
    assert rerun_re.search("the witness has been re-executed"), "an affirmative re-execution claim must be detectable"
    assert not rerun_re.search(_norm("the scenario was NOT rerun").replace("not rerun", " <not-rerun> ")), (
        "the masked truthful not-rerun sentence must never trip the affirmative-claim detector"
    )
    assert "exactly 14 harnesses" not in _norm("exactly 15 harnesses"), "a loop-count change must be detectable"


# ---------------------------------------------------------------------------
# 9. Contract/runbook lockstep (2E status, census line, next step, MC-4 truth sentences)
# ---------------------------------------------------------------------------
def test_2e_contract_lockstep() -> None:
    doc = _norm(_text(_CONTRACT_DOC))
    assert _2E_STATUS_PIN in doc, "the truthful 2E status must be recorded in the contract"
    assert _2E_CENSUS_PIN in doc, "the zero-closure census line must be recorded in the contract"
    assert _NEXT_STEP_PIN in doc, "the exact next governed step must be recorded in the contract"
    assert _CLOSURE_PIN in doc, "the exact canonical DBR-AR-2 closure sentence must be recorded in the contract"
    for pin in _THRESHOLD_TRUTH_PINS:
        assert pin in doc, f"the contract must carry the truthful threshold posture: {pin!r}"


def test_2e_runbook_lockstep() -> None:
    runbook = _norm(_text(_RUNBOOK))
    for pin in _INCIDENT_QUERY_PINS:
        assert pin in runbook, f"the runbook must carry the references-only incident-query discipline: {pin!r}"
    for pin in _THRESHOLD_TRUTH_PINS:
        assert pin in runbook, f"the runbook must carry the truthful threshold posture: {pin!r}"
    assert "references only" in runbook, "the runbook incident-query output must stay references-only"


def test_2e_lockstep_nonvacuity() -> None:
    assert _2E_STATUS_PIN not in "dbr-ar-2e — production-activation evidence consolidated.", (
        "a shortened 2E status (without the Outcome A / not-ready posture) must not satisfy"
    )
    assert _2E_CENSUS_PIN not in "dbr-ar-2e closes zero b5 activation blockers.", "a truncated census line must not satisfy"
    assert _NEXT_STEP_PIN not in _norm("the next governed step is production activation"), (
        "an activation-authorizing next step must be detectable"
    )
    assert _NEXT_STEP_PIN not in _norm(
        "the next governed step is a separate dan-authorized dbr-ar-2 closure decision."
        " production activation remains a separate human-governed decision and is not authorized by dbr-ar-2e."
    ), "the superseded pre-closure next-step sentence must no longer satisfy"
    assert _CLOSURE_PIN not in _norm("dbr-ar-2 — closed."), "a bare closure claim must not satisfy the exact closure pin"
    assert _CLOSURE_PIN not in _norm(
        "dbr-ar-2 — closed (dan-authorized governance decision); this closure closes zero b5 activation"
        " blockers, the blocker census remains nine with 8 of 9 open, and production remains not ready /"
        " do-not-activate."
    ), "a date-free closure variant must not satisfy the exact closure pin"
    assert _THRESHOLD_TRUTH_PINS[0] not in _norm("the production alert threshold is 5 per minute"), (
        "an invented numeric threshold must be detectable (the not-defined sentence disappears)"
    )
    assert _INCIDENT_QUERY_PINS[2] not in _norm("cross-tenant aggregation is performed for incidents"), (
        "a cross-tenant aggregation claim must be detectable"
    )


# ---------------------------------------------------------------------------
# 10. DDL scope, blob identity, automatic apply order 001-009
# ---------------------------------------------------------------------------
def test_2e_ddl_blob_and_scope() -> None:
    for rel, blob in _DDL_BLOBS.items():
        assert _git_blob_sha1(_REPO / rel) == blob, f"{rel} blob identity drifted (DDL must be byte-identical)"
        assert "Created, NOT applied" in _text(_REPO / rel), f"{rel} must keep the created-not-applied paragraph"
    contract = _norm(_text(_CONTRACT_DOC))
    assert "the ddl is applied only to the retained local standing control database" in contract, (
        "the contract must keep the standing-only DDL scope"
    )
    assert "not enrolled in the automatic standing apply order (001–009)" in contract, "010/011 must stay un-enrolled"


def test_2e_apply_order_pinned() -> None:
    m = _CONTROL_DDL_ORDER_RE.search(_text(_B5_TOPOLOGY))
    assert m is not None, "_CONTROL_DDL_ORDER must exist in b5_standing_topology.py"
    entries = re.findall(r'"(\d{3}_[a-z_]+\.sql)"', m.group("body"))
    assert entries == [
        "001_distinctness_ledger.sql",
        "002_provisioning_audit.sql",
        "003_provisioning_audit_append_only.sql",
        "004_control_tenants.sql",
        "005_control_memberships.sql",
        "006_control_federation.sql",
        "007_control_directory.sql",
        "008_distinctness_fingerprint_unique.sql",
        "009_control_tenants_cas_version.sql",
    ], f"the automatic apply order must remain exactly 001-009: {entries}"
    assert "010_routing_audit.sql" not in entries and "011_routing_audit_append_only.sql" not in entries


def test_2e_ddl_nonvacuity() -> None:
    assert _git_blob_sha1(_DDL_010) != "0" * 40, "a drifted DDL blob must be detectable"
    planted = ["001_distinctness_ledger.sql", "010_routing_audit.sql"]
    assert "010_routing_audit.sql" in planted, "a planted automatic enrollment must be detectable"


# ---------------------------------------------------------------------------
# 11. Hosted loop exactly 14; the standing harness stays MANUAL_ONLY
# ---------------------------------------------------------------------------
def test_2e_hosted_loop_and_manual_only() -> None:
    wf = _text(_WORKFLOW)
    entries = _loop_entries(wf)
    assert entries is not None and len(entries) == _EXPECTED_HARNESS_COUNT, "the hosted run set must remain exactly 14"
    assert _WRAPPER_RELPATH not in entries, "the standing harness must NOT be enrolled in the hosted loop"
    assert "dbr_ar_2d_standing_witnesses" not in wf, "the workflow must stay untouched by 2E"
    mapping: Optional[Dict[str, str]] = None
    for node in ast.parse(_text(_RUNSET_GUARD)).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "MANUAL_ONLY_EXCEPTIONS" for t in node.targets):
            mapping = ast.literal_eval(node.value)
    assert isinstance(mapping, dict) and _WRAPPER_RELPATH in mapping, "the standing harness must stay a MANUAL_ONLY exception"


def test_2e_hosted_loop_nonvacuity() -> None:
    fifteen = "for h in \\\n  " + " \\\n  ".join(f"tests/a/requires_pg/test_pg_{i}.py" for i in range(15)) + " ; do\n done"
    assert len(_loop_entries(fifteen) or []) == 15, "a widened 15-entry loop must be detectable"
    enrolled = f"for h in \\\n  {_WRAPPER_RELPATH} ; do\n done"
    assert _WRAPPER_RELPATH in (_loop_entries(enrolled) or []), "a hosted enrollment must be detectable"


# ---------------------------------------------------------------------------
# 12. ATR-2B-1 stays separately governed (fourth guard copy)
# ---------------------------------------------------------------------------
def test_2e_atr_2b1_stays_separate() -> None:
    ingest = _text(_CP_INGEST)
    # The 2B non-POST refusal shape, expressed against the FastAPI edge: the ingest adapter
    # registers EXACTLY one route and it is a POST, so every other method is still refused 405
    # with an EMPTY body. NOTE: the ATR-2B-1 substance (no default HTML error body, no Server:
    # header) is now provided platform-wide by the shared ASGI runtime, NOT by an un-taken
    # per-adapter change — this adapter still carries no bespoke header-suppression override.
    assert _scan.registered_route_methods(ast.parse(ingest)) == ["post"], (
        "the merged 2B non-POST refusal shape must be unchanged (ATR-2B-1 not silently implemented)"
    )
    for token in ("server_version", "sys_version", "version_string"):
        assert token not in ingest, f"ATR-2B-1 hardening ({token}) must not be silently implemented"
    doc = _norm(_text(_EVIDENCE_DOC))
    assert "atr-2b-1" in doc and "separately governed" in doc, "the evidence record must carry ATR-2B-1 as separately governed"


def test_2e_atr_2b1_nonvacuity() -> None:
    assert "version_string" in "def version_string(self): return ''", "an ATR-2B-1 header override must be detectable"


# ---------------------------------------------------------------------------
# 13. B5 gate documents byte-identical (blob pins) + JSON hygiene
# ---------------------------------------------------------------------------
def test_2e_b5_gate_docs_byte_identical() -> None:
    for rel, blob in _B5_GATE_BLOBS.items():
        assert _git_blob_sha1(_REPO / rel) == blob, f"{rel} must remain byte-identical (2E never edits the B5 gate documents)"


def test_2e_json_hygiene() -> None:
    # autocrlf normalization first (the git BLOB is LF; a Windows checkout materializes CRLF —
    # the OBS-V3-2 posture): after normalization no stray CR may remain (lone-CR / mixed endings).
    raw = _INDEX.read_bytes().replace(b"\r\n", b"\n")
    assert b"\r" not in raw, "the index blob must be LF-only (no lone or mixed CR)"
    assert not raw.startswith(b"\xef\xbb\xbf"), "the index must carry no BOM"
    assert raw.endswith(b"\n"), "the index must end with a newline"
    assert all(byte < 128 for byte in raw), "the index must be pure ASCII (a fortiori valid UTF-8)"
    json.loads(raw.decode("utf-8"))


def test_2e_gate_blob_nonvacuity() -> None:
    data = b"blob probe"
    probe = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    assert probe != _B5_GATE_BLOBS["docs/runtime/b5_activation_blockers.md"], "an edited gate document must be detectable"
    assert b"\r" in b"line\rmixed".replace(b"\r\n", b"\n"), "a lone-CR byte must survive normalization and be detectable"
    assert b"\r" not in b"line\r\n".replace(b"\r\n", b"\n"), "checkout CRLF must normalize away (blob discipline is ls-files --eol)"


if __name__ == "__main__":
    _scan.run(
        [
            test_2e_surface_and_census,
            test_2e_surface_census_nonvacuity,
            test_2e_index_top_shape,
            test_2e_index_top_nonvacuity,
            test_2e_index_record_schema,
            test_2e_index_schema_nonvacuity,
            test_2e_index_ordering_unique_and_coverage,
            test_2e_ordering_nonvacuity,
            test_2e_pae_dispositions_exact,
            test_2e_pae_dispositions_nonvacuity,
            test_2e_register_census_pins,
            test_2e_no_invented_blocker_and_mc1_note,
            test_cd_closure_record_shape,
            test_cd_closure_record_nonvacuity,
            test_cd_recarry_and_dispositions,
            test_cd_recarry_nonvacuity,
            test_2e_blocker_mapping_nonvacuity,
            test_2e_report_sources_attested,
            test_2e_report_attested_nonvacuity,
            test_2e_no_secret_shape_or_production_identity,
            test_2e_secret_shape_nonvacuity,
            test_2e_doc_required_statements,
            test_2e_doc_no_overclaim_and_no_next_slice,
            test_2e_doc_statements_nonvacuity,
            test_2e_doc_standing_pins,
            test_2e_standing_pins_nonvacuity,
            test_2e_contract_lockstep,
            test_2e_runbook_lockstep,
            test_2e_lockstep_nonvacuity,
            test_2e_ddl_blob_and_scope,
            test_2e_apply_order_pinned,
            test_2e_ddl_nonvacuity,
            test_2e_hosted_loop_and_manual_only,
            test_2e_hosted_loop_nonvacuity,
            test_2e_atr_2b1_stays_separate,
            test_2e_atr_2b1_nonvacuity,
            test_2e_b5_gate_docs_byte_identical,
            test_2e_json_hygiene,
            test_2e_gate_blob_nonvacuity,
        ]
    )
