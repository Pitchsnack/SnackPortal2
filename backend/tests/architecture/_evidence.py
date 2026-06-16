"""Pure-stdlib helpers for the CI Evidence Record guard (PRD-CI-EVIDENCE-01-E2).

These helpers validate the durable CI evidence artifacts produced by
``PRD-CI-EVIDENCE-01-E1`` (under ``docs/reports/ci-evidence/``) WITHOUT modifying
them. They mirror ``_scan.py``: no network / gh / GitHub API / sockets / env reads /
runtime imports; every check is a pure function over already-loaded data or file text
and fails closed via ``AssertionError``. Runs under pytest and standalone.

CANONICAL-CONSTANT DOCTRINE (§9.20, ETR-SCHEMA-CANONICAL-PIN-DOC-1)
------------------------------------------------------------------
The ``CANON_*`` enum/required sets below are the frozen canonical value sets of
``PRD-CI-EVIDENCE-01-R1`` sections 9 and 13 (the committed schema binds to them
"verbatim"). They are an INDEPENDENT anchor: literal constants here, NEVER re-derived
from the schema, so weakening the schema in lock-step with the record still reds the
build. They may be changed ONLY by WIDENING via a contract-first PRD that amends
R1 §9/§13 in the same change; they must never be narrowed here.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

BACKEND_ROOT = Path(__file__).resolve().parents[2]  # .../backend
REPO_ROOT = BACKEND_ROOT.parent
EVIDENCE_DIR = REPO_ROOT / "docs" / "reports" / "ci-evidence"
DEPRECATED_DIR = REPO_ROOT / "docs" / "ci-evidence"

SCHEMA_RELPATH = "templates/CI-Evidence-Record.schema.json"
README_FILENAME = "README.md"
RECORD_FILENAME = "PRD-CI-EVIDENCE-01-E1-Evidence-Record.json"
REPORT_FILENAME = "PRD-CI-EVIDENCE-01-E1-Evidence-Report.md"
EVIDENCE_FILENAMES: Tuple[str, ...] = (README_FILENAME, SCHEMA_RELPATH, RECORD_FILENAME, REPORT_FILENAME)

# --- Frozen canonical sets (PROVENANCE: PRD-CI-EVIDENCE-01-R1 §9/§13) ----------

CANON_EVIDENCE_STRENGTH: FrozenSet[str] = frozenset(  # R1 §9 (5)
    {"OBSERVED_DIRECT", "OBSERVED_REPRODUCIBLE", "OBSERVED_HUMAN_PROVIDED", "DERIVED_INFERENCE", "UNAVAILABLE"}
)
CANON_SOURCE_CLASSIFICATION: FrozenSet[str] = frozenset(  # R1 §9 (8)
    {
        "DIRECT_GITHUB_API_EVIDENCE",
        "DIRECT_GITHUB_UI_EVIDENCE",
        "GH_CLI_EVIDENCE",
        "HUMAN_PROVIDED_GITHUB_EVIDENCE",
        "LOCAL_GIT_EVIDENCE",
        "LOCAL_TEST_EVIDENCE",
        "DERIVED_EVIDENCE",
        "UNAVAILABLE_EVIDENCE",
    }
)
CANON_REDACTION_STATUS: FrozenSet[str] = frozenset(  # R1 §9 (3)
    {"no-secrets-present", "redacted", "STOPPED-secret-detected"}
)
CANON_EVIDENCE_TYPE: FrozenSet[str] = frozenset(  # R1 §9 (13)
    {
        "workflow_run",
        "job_result",
        "job_log_excerpt",
        "check_suite",
        "check_run",
        "branch_protection",
        "ruleset",
        "workflow_file_hash",
        "commit_ancestry",
        "local_gate",
        "manual_screenshot",
        "resolved_scanner_artifact",
        "run_conclusion_assertion",
    }
)
CANON_VERDICT: FrozenSet[str] = frozenset(  # R1 §13 (6 non-null)
    {
        "PASS — EVIDENCE COMPLETE",
        "PASS WITH OBSERVATIONS",
        "BLOCKED — EVIDENCE UNAVAILABLE",
        "BLOCKED — USER ACTION REQUIRED",
        "FAIL — EVIDENCE CONTRADICTS CLAIM",
        "FAIL — CI RUNTIME BROKEN",
    }
)
CANON_NON_VACUITY_STATUS: FrozenSet[str] = frozenset(  # R1 §9 (3 non-null)
    {"SCAN-NON-VACUITY-OBSERVED", "SCAN-NON-VACUITY-NOT-OBSERVED", "NON-VACUITY-UNOBSERVABLE-WITH-CURRENT-CONFIG"}
)
CANON_STALENESS_STATUS: FrozenSet[str] = frozenset({"FRESH", "STALE-FOR-CURRENT-HEAD"})  # R1 §9 (2 non-null)

# Required-field FLOOR (DRIFT-1): schema definitions.evidence_record.required (7) INCLUDING `repository`.
CANON_REQUIRED_FLOOR: FrozenSet[str] = frozenset(
    {"evidence_id", "requirement_id", "evidence_type", "evidence_strength", "source_classification", "repository", "pass_gate_eligible"}
)
# Operational superset unioned into the per-record floor (§9.7b).
OPERATIONAL_FLOOR: FrozenSet[str] = frozenset(
    {"captured_at", "capture_method", "assertion_performed", "redaction_status", "limitations", "verdict"}
)

# record enum field -> canonical non-null set (enum-freeze + membership).
CANON_ENUMS: Dict[str, FrozenSet[str]] = {
    "evidence_strength": CANON_EVIDENCE_STRENGTH,
    "source_classification": CANON_SOURCE_CLASSIFICATION,
    "redaction_status": CANON_REDACTION_STATUS,
    "evidence_type": CANON_EVIDENCE_TYPE,
    "verdict": CANON_VERDICT,
    "non_vacuity_status": CANON_NON_VACUITY_STATUS,
    "staleness_status": CANON_STALENESS_STATUS,
}

# The eight committed E1 requirement_ids (SUBSET target; §3/§9.6).
KNOWN_REQUIREMENT_IDS: Tuple[str, ...] = (
    "PRD-CI-EVIDENCE-01-E1-GIT-HEAD",
    "PRD-CI-EVIDENCE-01-E1-ANCESTRY-63C6A91",
    "PRD-CI-EVIDENCE-01-E1-CI-YML-BLOB",
    "PRD-CI-EVIDENCE-01-E1-GUARD-BLOB",
    "PRD-CI-EVIDENCE-01-E1-RUNTIME-VALIDATE",
    "PRD-CI-EVIDENCE-01-E1-RUNTIME-SECRET-SCAN",
    "PRD-CI-EVIDENCE-01-E1-PR-EVENT-COVERAGE",
    "PRD-CI-EVIDENCE-01-E1-REQUIRED-CHECK-STATUS",
)
REQUIRED_CHECK_ID = "PRD-CI-EVIDENCE-01-E1-REQUIRED-CHECK-STATUS"
BLOCKED_UNAVAILABLE_VERDICT = "BLOCKED — EVIDENCE UNAVAILABLE"

# DRIFT-2: allowed verdict_reason_code set for BLOCKED-EVIDENCE-UNAVAILABLE records, keyed by cause.
ALLOWED_BLOCKED_REASON_CODES: FrozenSet[str] = frozenset(
    {
        "TOOL-PREREQ-UNMET",  # gh/run-status client ABSENT (schema $comment RULE 2)
        "REQUIRED-CHECK-STATUS-UNOBSERVABLE-PRIVATE-REPO-TIER",  # branch-protection unobservable (private-repo tier)
    }
)

EVIDENCE_ID_RE = re.compile(r"^CI-EVD-[0-9]{8}-[0-9]{3,}$")
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA_FIELDS: Tuple[str, ...] = ("workflow_file_blob_sha", "commit_sha", "head_sha", "base_sha")
RUNTIME_SOURCE_CLASSIFICATIONS: FrozenSet[str] = frozenset({"GH_CLI_EVIDENCE", "DIRECT_GITHUB_API_EVIDENCE", "DIRECT_GITHUB_UI_EVIDENCE"})
PASS_VERDICTS: FrozenSet[str] = frozenset({"PASS — EVIDENCE COMPLETE", "PASS WITH OBSERVATIONS"})
SECRET_SCAN_FIELDS: Tuple[str, ...] = ("supporting_excerpt", "assertion_performed", "command_used", "limitations", "verdict_reason_code")

# Allowed top-level imports for the two guard files (§9.15/§10).
ALLOWED_IMPORTS: FrozenSet[str] = frozenset(
    {"__future__", "ast", "copy", "json", "re", "pathlib", "typing", "shutil", "sys", "tempfile", "_evidence", "_scan"}
)

# --- Secret-detection patterns (§9.14) ----------------------------------------
# Built from FRAGMENTS so this file contains no complete matchable credential and never
# trips gitleaks-on-push or test_no_secret_literals.py (AKIA.../-----BEGIN...PRIVATE KEY-----/xox...).
_GH_PREFIXES = ("ghp", "gho", "ghu", "ghs", "ghr")
SECRET_PATTERNS: Tuple[re.Pattern, ...] = (
    re.compile("(?:" + "|".join(_GH_PREFIXES) + ")_[A-Za-z0-9]{30,}"),
    re.compile("github" + "_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"[Aa]uthorization\s*:\s*(?:Bearer|Basic|[Tt]oken)\s+[A-Za-z0-9._+/=\-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}"),
    re.compile("-" * 5 + "BEGIN" + r"[A-Z ]*" + "PRIV" + "ATE" + " KEY" + "-" * 5),
    re.compile(r"DATABASE_URL\s*=\s*\S+"),
    re.compile(r"postgres(?:ql)?://[^\s:@/]+:[^\s:@/]+@"),
)


# --- I/O + JSON loading (fail-closed) -----------------------------------------


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise AssertionError("required evidence file unreadable: " + str(path) + " (" + str(exc) + ")") from exc


def parse_json_text(text: str, label: str) -> Any:
    assert isinstance(text, str) and text.strip(), label + ": empty or whitespace-only JSON (fail-closed)"
    try:
        return json.loads(text)
    except ValueError as exc:  # json.JSONDecodeError is a ValueError subclass
        raise AssertionError(label + ": not well-formed JSON (" + str(exc) + ")") from exc


def evidence_dir_or_default(evidence_dir: Optional[Path] = None) -> Path:
    return EVIDENCE_DIR if evidence_dir is None else evidence_dir


def schema_path(evidence_dir: Optional[Path] = None) -> Path:
    return evidence_dir_or_default(evidence_dir) / "templates" / "CI-Evidence-Record.schema.json"


def record_path(evidence_dir: Optional[Path] = None) -> Path:
    return evidence_dir_or_default(evidence_dir) / RECORD_FILENAME


def readme_path(evidence_dir: Optional[Path] = None) -> Path:
    return evidence_dir_or_default(evidence_dir) / README_FILENAME


def report_path(evidence_dir: Optional[Path] = None) -> Path:
    return evidence_dir_or_default(evidence_dir) / REPORT_FILENAME


def load_schema(evidence_dir: Optional[Path] = None) -> Dict[str, Any]:
    obj = parse_json_text(_read_text(schema_path(evidence_dir)), "schema")
    assert isinstance(obj, dict), "schema: top-level JSON must be an object"
    return obj


def load_record(evidence_dir: Optional[Path] = None) -> Dict[str, Any]:
    obj = parse_json_text(_read_text(record_path(evidence_dir)), "record")
    assert isinstance(obj, dict), "record: top-level JSON must be an object"
    return obj


def records_of(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    assert isinstance(doc, dict), "record doc must be a JSON object"
    recs = doc.get("evidence_records")
    assert isinstance(recs, list) and recs, "evidence_records must be a non-empty list"
    for i, r in enumerate(recs):
        assert isinstance(r, dict), "evidence_records[" + str(i) + "] must be an object"
    return recs


# --- schema navigation (fail-closed derivation) -------------------------------


def _evidence_record_def(schema: Dict[str, Any]) -> Dict[str, Any]:
    try:
        defn = schema["definitions"]["evidence_record"]
    except (KeyError, TypeError) as exc:
        raise AssertionError("schema: missing definitions.evidence_record (" + str(exc) + ")") from exc
    assert isinstance(defn, dict), "schema: definitions.evidence_record must be an object"
    return defn


def schema_properties(schema: Dict[str, Any]) -> Dict[str, Any]:
    props = _evidence_record_def(schema).get("properties")
    assert isinstance(props, dict) and props, "schema: evidence_record.properties missing/empty"
    return props


def schema_required(schema: Dict[str, Any]) -> List[str]:
    req = _evidence_record_def(schema).get("required")
    assert isinstance(req, list) and req, "schema: evidence_record.required missing/empty"
    return [str(x) for x in req]


def schema_enum_raw(schema: Dict[str, Any], field: str) -> List[Any]:
    spec = schema_properties(schema).get(field)
    assert isinstance(spec, dict), "schema: property '" + field + "' missing"
    enum = spec.get("enum")
    assert isinstance(enum, list) and enum, "schema: property '" + field + "' has no enum (fail-closed)"
    return enum


def schema_enum_nonnull(schema: Dict[str, Any], field: str) -> FrozenSet[str]:
    vals = frozenset(v for v in schema_enum_raw(schema, field) if v is not None)
    assert vals, "schema: enum for '" + field + "' empty after dropping null (fail-closed)"
    return vals


def required_field_floor(schema: Dict[str, Any]) -> FrozenSet[str]:
    # §9.7 DRIFT-1: schema.required UNION the operational set; the floor MUST include `repository`.
    floor = frozenset(schema_required(schema)) | OPERATIONAL_FLOOR
    assert "repository" in floor, "required-field floor must include 'repository' (DRIFT-1)"
    return floor


# --- per-record checks --------------------------------------------------------


def _rid(record: Dict[str, Any]) -> str:
    return str(record.get("requirement_id", "<unknown>"))


def check_floor(record: Dict[str, Any], floor: FrozenSet[str]) -> None:  # §9.7
    for field in sorted(floor):
        assert field in record, "record " + _rid(record) + " missing required floor field '" + field + "'"


def check_enums(record: Dict[str, Any], schema: Dict[str, Any]) -> None:  # §9.8
    pge = record.get("pass_gate_eligible")
    assert isinstance(pge, bool), "record " + _rid(record) + " pass_gate_eligible must be a JSON boolean, got " + repr(pge)
    for field in CANON_ENUMS:
        if field not in record:
            continue
        value = record[field]
        raw = schema_enum_raw(schema, field)
        if value is None:
            assert None in raw, "record " + _rid(record) + " field '" + field + "' is null but schema enum forbids null"
            continue
        assert value in raw, "record " + _rid(record) + " field '" + field + "'=" + repr(value) + " not in schema enum"


def check_derived_inference_gate(record: Dict[str, Any]) -> None:  # §9.9
    if record.get("evidence_strength") == "DERIVED_INFERENCE":
        assert record.get("pass_gate_eligible") is False, "record " + _rid(record) + ": DERIVED_INFERENCE requires pass_gate_eligible false"


def check_unavailable_gate(record: Dict[str, Any]) -> None:  # §9.10
    if record.get("evidence_strength") == "UNAVAILABLE":
        assert record.get("pass_gate_eligible") is False, "record " + _rid(record) + ": UNAVAILABLE requires pass_gate_eligible false"


def check_runtime_not_inferred(record: Dict[str, Any]) -> None:  # §9.11
    if record.get("source_classification") in RUNTIME_SOURCE_CLASSIFICATIONS:
        strength = record.get("evidence_strength")
        assert strength != "DERIVED_INFERENCE", "record " + _rid(record) + ": runtime evidence must not be DERIVED_INFERENCE"
        assert strength in {"OBSERVED_REPRODUCIBLE", "OBSERVED_DIRECT", "UNAVAILABLE"}, (
            "record "
            + _rid(record)
            + ": runtime evidence_strength must be OBSERVED_REPRODUCIBLE/OBSERVED_DIRECT/UNAVAILABLE, got "
            + repr(strength)
        )


def check_verdict_gate_consistency(record: Dict[str, Any]) -> None:  # §9.18
    verdict = record.get("verdict")
    pge = record.get("pass_gate_eligible")
    if isinstance(verdict, str) and (verdict.startswith("BLOCKED") or verdict.startswith("FAIL")):
        assert pge is False, "record " + _rid(record) + ": " + verdict + " must have pass_gate_eligible false"
    if pge is True:
        assert verdict is None or verdict in PASS_VERDICTS, (
            "record " + _rid(record) + ": pass_gate_eligible true requires a PASS verdict, got " + repr(verdict)
        )


def check_sha_shape(record: Dict[str, Any]) -> None:  # §9.19
    for field in SHA_FIELDS:
        if field not in record:
            continue
        val = record[field]
        if val is None:
            continue
        assert isinstance(val, str) and SHA1_RE.match(val), (
            "record " + _rid(record) + " field '" + field + "'=" + repr(val) + " is not a 40-char lowercase SHA-1"
        )


# --- collection-level checks --------------------------------------------------


def _dups(seq: List[Any]) -> List[Any]:
    seen: Set[Any] = set()
    out: List[Any] = []
    for x in seq:
        if x in seen and x not in out:
            out.append(x)
        seen.add(x)
    return out


def check_known_ids_present(records: List[Dict[str, Any]]) -> None:  # §9.6 (SUBSET)
    present = {r.get("requirement_id") for r in records}
    for known in KNOWN_REQUIREMENT_IDS:
        assert known in present, "known E1 requirement_id absent: " + known


def check_evidence_ids(records: List[Dict[str, Any]]) -> None:  # §9.17 (format + uniqueness)
    ids: List[str] = []
    for r in records:
        eid = r.get("evidence_id")
        assert isinstance(eid, str) and EVIDENCE_ID_RE.match(eid), (
            "record " + _rid(r) + ": evidence_id " + repr(eid) + " is not CI-EVD-YYYYMMDD-NNN"
        )
        ids.append(eid)
    assert len(set(ids)) == len(ids), "duplicate evidence_id present: " + repr(_dups(ids))


def check_requirement_ids_unique(records: List[Dict[str, Any]]) -> None:  # §9.17 (requirement_id uniqueness)
    rids: List[Any] = []
    for r in records:
        rid = r.get("requirement_id")
        assert isinstance(rid, str) and rid, "every record must have a non-empty requirement_id"
        rids.append(rid)
    assert len(set(rids)) == len(rids), "duplicate requirement_id present: " + repr(_dups(rids))


def check_required_check_record(records: List[Dict[str, Any]]) -> None:  # §9.12
    rec = next((r for r in records if r.get("requirement_id") == REQUIRED_CHECK_ID), None)
    assert rec is not None, "required-check record '" + REQUIRED_CHECK_ID + "' is absent"
    assert rec.get("evidence_strength") == "UNAVAILABLE", "required-check record must be UNAVAILABLE"
    assert rec.get("pass_gate_eligible") is False, "required-check record must have pass_gate_eligible false"
    lim = rec.get("limitations")
    assert isinstance(lim, str) and lim.strip(), "required-check record must have non-empty limitations"
    assert rec.get("verdict") == BLOCKED_UNAVAILABLE_VERDICT, "required-check record verdict must be the BLOCKED-EVIDENCE-UNAVAILABLE value"
    code = rec.get("verdict_reason_code")
    assert isinstance(code, str) and code.strip(), "required-check record must have a non-empty verdict_reason_code"
    assert code in ALLOWED_BLOCKED_REASON_CODES, (
        "required-check verdict_reason_code " + repr(code) + " not in the documented allowed set (DRIFT-2)"
    )


def check_blocked_reason_codes(records: List[Dict[str, Any]]) -> None:  # §9.12 general (STOP on out-of-set)
    for r in records:
        if r.get("verdict") == BLOCKED_UNAVAILABLE_VERDICT:
            code = r.get("verdict_reason_code")
            assert isinstance(code, str) and code in ALLOWED_BLOCKED_REASON_CODES, (
                "record "
                + _rid(r)
                + ": BLOCKED-EVIDENCE-UNAVAILABLE verdict_reason_code "
                + repr(code)
                + " is outside the documented allowed set (STOP)"
            )


# --- secret scans (§9.14) -----------------------------------------------------


def scan_text_for_secrets(text: str, label: str) -> None:
    assert isinstance(text, str), label + ": expected text to scan"
    for i, pat in enumerate(SECRET_PATTERNS):
        assert pat.search(text) is None, label + ": high-risk credential pattern #" + str(i) + " matched (STOP)"


def scan_record_fields_for_secrets(record: Dict[str, Any]) -> None:
    for field in SECRET_SCAN_FIELDS:
        val = record.get(field)
        if isinstance(val, str) and val:
            scan_text_for_secrets(val, "record " + _rid(record) + " field '" + field + "'")


def scan_evidence_files_for_secrets(evidence_dir: Optional[Path] = None) -> None:
    base = evidence_dir_or_default(evidence_dir)
    for rel in EVIDENCE_FILENAMES:
        scan_text_for_secrets(_read_text(base / rel), "file " + rel)


# --- schema anti-weakening (§9.20) --------------------------------------------


def check_enum_freeze(schema: Dict[str, Any]) -> None:  # §9.20a
    for field, canon in CANON_ENUMS.items():
        live = schema_enum_nonnull(schema, field)
        missing = canon - live
        added = live - canon
        assert not missing, "schema enum '" + field + "' DROPPED canonical value(s): " + repr(sorted(missing))
        assert not added, (
            "schema enum '" + field + "' ADDED un-reviewed value(s) (widen canonical via contract-first PRD): " + repr(sorted(added))
        )


def check_required_floor_superset(schema: Dict[str, Any]) -> None:  # §9.20b
    missing = CANON_REQUIRED_FLOOR - frozenset(schema_required(schema))
    assert not missing, "schema required floor BELOW canonical; missing: " + repr(sorted(missing)) + " (STOP - do not auto-fix)"


def check_comment_rules(schema: Dict[str, Any]) -> None:  # §9.20c
    comment = schema.get("$comment")
    assert isinstance(comment, str) and comment.strip(), "schema $comment missing"
    assert "RULE 1" in comment, "schema $comment missing RULE 1"
    assert "DERIVED_INFERENCE" in comment, "schema $comment RULE 1 must mention DERIVED_INFERENCE"
    assert ("pass_gate_eligible" in comment) or ("PASS gate" in comment), "schema $comment RULE 1 must bind the PASS gate"
    assert "RULE 2" in comment, "schema $comment missing RULE 2"
    assert "verdict_reason_code" in comment, "schema $comment RULE 2 must mention verdict_reason_code"


def check_schema_shape(schema: Dict[str, Any]) -> None:  # §9.20d
    sid = schema.get("$schema")
    assert isinstance(sid, str) and "draft-07" in sid, "schema $schema must reference draft-07"
    props = schema.get("properties")
    assert isinstance(props, dict), "schema.properties missing"
    er = props.get("evidence_records")
    assert isinstance(er, dict) and er.get("type") == "array", "schema.properties.evidence_records must be an array"
    items = er.get("items")
    assert isinstance(items, dict) and items.get("$ref") == "#/definitions/evidence_record", (
        "evidence_records.items.$ref must be #/definitions/evidence_record"
    )
    defn = _evidence_record_def(schema)
    assert defn.get("type") == "object", "evidence_record definition must be type object"
    assert isinstance(defn.get("properties"), dict) and defn["properties"], "evidence_record must have non-empty properties"
    assert isinstance(defn.get("required"), list) and defn["required"], "evidence_record must have non-empty required"


def check_schema_record_drift(records: List[Dict[str, Any]], schema: Dict[str, Any]) -> None:  # §9.20e
    declared = set(schema_properties(schema).keys())
    for r in records:
        for key in r.keys():
            assert key in declared, "record " + _rid(r) + ": field '" + str(key) + "' is not declared in the schema (drift)"


# --- import hygiene (§9.15 / §10) ---------------------------------------------


def imported_top_modules(source_text: str, label: str) -> Set[str]:
    try:
        tree = ast.parse(source_text)
    except SyntaxError as exc:
        raise AssertionError(label + ": unparseable Python (" + str(exc) + ")") from exc
    mods: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            mods.add(node.module.split(".")[0])
    return mods


def check_no_forbidden_imports(source_text: str, label: str) -> None:
    for m in imported_top_modules(source_text, label):
        assert m in ALLOWED_IMPORTS, label + ": import '" + m + "' is not in the allowed stdlib/local set (§9.15/§10)"


# --- guard self-collection (§9.21, pure form so it is itself meta-testable) ----


def check_collection_registry(test_names: List[str], run_names: Set[str], expected_min: int, meta_min: int) -> None:
    assert len(test_names) >= expected_min, "collected " + str(len(test_names)) + " test_* < expected " + str(expected_min)
    missing = [n for n in test_names if n not in run_names]
    assert not missing, "test(s) not registered in the standalone runner (a rename breaks the build): " + repr(missing)
    metas = [n for n in test_names if n.startswith("test_meta_")]
    assert len(metas) >= meta_min, "expected >= " + str(meta_min) + " fail-closed meta-tests, found " + str(len(metas))


# --- cross-file consistency (§9.23, observation-grade) ------------------------


def _verdict_block(report_text: str) -> Optional[str]:
    lines = report_text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().lower() == "## a. verdict":
            j = i + 1
            while j < len(lines) and "```" not in lines[j]:
                j += 1
            k = j + 1
            buf: List[str] = []
            while k < len(lines) and "```" not in lines[k]:
                buf.append(lines[k])
                k += 1
            return "\n".join(buf).strip()
    return None


def check_cross_file_consistency(evidence_dir: Optional[Path] = None) -> None:
    readme = _read_text(readme_path(evidence_dir))
    assert "docs/reports/ci-evidence/" in readme, "README must state the canonical path"
    assert "docs/ci-evidence/" in readme, "README must mark the deprecated path"
    record = load_record(evidence_dir)
    schema_ref = record.get("schema")
    assert isinstance(schema_ref, str) and schema_ref, "record.schema pointer missing"
    resolves = (REPO_ROOT / schema_ref).resolve() == schema_path(evidence_dir).resolve()
    assert resolves or schema_ref.endswith("CI-Evidence-Record.schema.json"), "record.schema does not point at the schema file"
    overall = record.get("overall_verdict")
    block = _verdict_block(_read_text(report_path(evidence_dir)))
    if block is not None and isinstance(overall, str):
        assert overall.strip() == block.strip(), "record.overall_verdict != report '## A. Verdict' block"


# --- deprecated-path guard (§9.2) ---------------------------------------------


def assert_deprecated_path_unused() -> None:
    if not DEPRECATED_DIR.exists():
        return
    bad: List[str] = []
    for p in DEPRECATED_DIR.rglob("*"):
        if not p.is_file():
            continue
        n = p.name
        if n.endswith("-Evidence-Record.json") or n.endswith("-Evidence-Report.md") or n == "CI-Evidence-Record.schema.json":
            bad.append(str(p))
    assert not bad, "deprecated docs/ci-evidence/ holds evidence-like files: " + repr(bad)


# --- aggregate entrypoint (used by the tempdir red-on-regression seam) --------


def validate_evidence(evidence_dir: Optional[Path] = None) -> Dict[str, int]:
    base = evidence_dir_or_default(evidence_dir)
    assert base.is_dir(), "evidence dir missing: " + str(base)  # §9.1
    assert_deprecated_path_unused()  # §9.2
    for rel in EVIDENCE_FILENAMES:  # §9.3
        assert (base / rel).is_file(), "missing evidence file: " + rel
    schema = load_schema(evidence_dir)  # §9.4
    records = records_of(load_record(evidence_dir))  # §9.4/§9.5
    check_known_ids_present(records)  # §9.6
    check_schema_shape(schema)  # §9.20d
    check_enum_freeze(schema)  # §9.20a
    check_required_floor_superset(schema)  # §9.20b
    check_comment_rules(schema)  # §9.20c
    floor = required_field_floor(schema)  # §9.7
    for r in records:
        check_floor(r, floor)  # §9.7
        check_enums(r, schema)  # §9.8
        check_derived_inference_gate(r)  # §9.9
        check_unavailable_gate(r)  # §9.10
        check_runtime_not_inferred(r)  # §9.11
        check_verdict_gate_consistency(r)  # §9.18
        check_sha_shape(r)  # §9.19
        scan_record_fields_for_secrets(r)  # §9.14 field-level
    check_required_check_record(records)  # §9.12
    check_blocked_reason_codes(records)  # §9.12
    check_evidence_ids(records)  # §9.17
    check_requirement_ids_unique(records)  # §9.17
    check_schema_record_drift(records, schema)  # §9.20e
    scan_evidence_files_for_secrets(evidence_dir)  # §9.14 file-level
    check_cross_file_consistency(evidence_dir)  # §9.23
    return {"records": len(records)}
