"""CI Evidence Record guard (PRD-CI-EVIDENCE-01-E2-R2).

Validates the durable E1 CI evidence artifacts under ``docs/reports/ci-evidence/``
WITHOUT modifying them: structural/enum checks, the evidentiary gate rules, verdict<->
gate consistency, schema anti-weakening, evidence_id/requirement_id uniqueness, SHA
shape, file+field secret scan, fail-closed in-memory mutation meta-tests, guard
self-collection, and a safe tempdir red-on-regression demo. Pure-stdlib, fail-closed,
no network / gh / GitHub API. Runs under ``pytest tests/architecture`` and standalone.
"""

from __future__ import annotations

import copy
import json
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _evidence  # noqa: E402
import _scan  # noqa: E402

# §9.21 self-collection floor = number of positive tests + meta cases defined below.
EXPECTED_MIN_TESTS = 57

# Synthetic credentials for §9.14 meta-tests, built from fragments so this file holds
# no complete matchable credential (no AKIA.../-----BEGIN...PRIVATE KEY-----/xox.../ghp_<body>).
_SYNTH_GH_TOKEN = "gh" + "p" + "_" + ("A" * 36)
_SYNTH_AUTH_HEADER = "Authorization: " + "Bearer " + ("z" * 40)


def _expect_raises(fn, *args, **kwargs) -> None:
    try:
        fn(*args, **kwargs)
    except AssertionError:
        return
    raise AssertionError("guard did not fail closed: " + getattr(fn, "__name__", repr(fn)))


def _records():
    return _evidence.records_of(_evidence.load_record())


def _schema():
    return _evidence.load_schema()


# --- positive tests (against the REAL on-disk artifacts) ----------------------


def test_canonical_path_exists() -> None:  # §9.1
    assert _evidence.EVIDENCE_DIR.is_dir(), "canonical evidence dir missing"


def test_deprecated_path_unused() -> None:  # §9.2
    _evidence.assert_deprecated_path_unused()


def test_required_e1_files_exist() -> None:  # §9.3
    for rel in _evidence.EVIDENCE_FILENAMES:
        assert (_evidence.EVIDENCE_DIR / rel).is_file(), "missing evidence file: " + rel


def test_json_well_formed() -> None:  # §9.4
    _evidence.load_schema()
    _evidence.load_record()


def test_record_shape() -> None:  # §9.5
    assert _records(), "evidence_records must be non-empty"


def test_known_requirement_ids_present() -> None:  # §9.6
    _evidence.check_known_ids_present(_records())


def test_required_field_floor() -> None:  # §9.7 (incl. repository / DRIFT-1)
    floor = _evidence.required_field_floor(_schema())
    assert "repository" in floor
    for r in _records():
        _evidence.check_floor(r, floor)


def test_enum_validation() -> None:  # §9.8
    schema = _schema()
    for r in _records():
        _evidence.check_enums(r, schema)


def test_derived_inference_not_gate_eligible() -> None:  # §9.9
    for r in _records():
        _evidence.check_derived_inference_gate(r)


def test_unavailable_not_gate_eligible() -> None:  # §9.10
    for r in _records():
        _evidence.check_unavailable_gate(r)


def test_runtime_evidence_not_inferred() -> None:  # §9.11
    for r in _records():
        _evidence.check_runtime_not_inferred(r)


def test_required_check_record_honest() -> None:  # §9.12 (DRIFT-2)
    recs = _records()
    _evidence.check_required_check_record(recs)
    _evidence.check_blocked_reason_codes(recs)


def test_verdict_gate_consistency() -> None:  # §9.18
    for r in _records():
        _evidence.check_verdict_gate_consistency(r)


def test_evidence_id_and_requirement_id_unique() -> None:  # §9.17
    recs = _records()
    _evidence.check_evidence_ids(recs)
    _evidence.check_requirement_ids_unique(recs)


def test_sha_shape() -> None:  # §9.19
    for r in _records():
        _evidence.check_sha_shape(r)


def test_no_secrets_in_files_and_fields() -> None:  # §9.14
    _evidence.scan_evidence_files_for_secrets()
    for r in _records():
        _evidence.scan_record_fields_for_secrets(r)


def test_schema_enum_freeze() -> None:  # §9.20a
    _evidence.check_enum_freeze(_schema())


def test_schema_required_floor() -> None:  # §9.20b
    _evidence.check_required_floor_superset(_schema())


def test_schema_comment_rules() -> None:  # §9.20c
    _evidence.check_comment_rules(_schema())


def test_schema_shape() -> None:  # §9.20d
    _evidence.check_schema_shape(_schema())


def test_schema_record_drift() -> None:  # §9.20e
    _evidence.check_schema_record_drift(_records(), _schema())


def test_no_forbidden_imports_in_guard() -> None:  # §9.15 / §10
    here = pathlib.Path(__file__).resolve().parent
    for name in ("_evidence.py", "test_evidence_capture.py"):
        _evidence.check_no_forbidden_imports((here / name).read_text(encoding="utf-8"), name)


def test_cross_file_consistency() -> None:  # §9.23
    _evidence.check_cross_file_consistency()


def test_positive_checks_read_real_files() -> None:  # §9.22 (committed: real-file invocation)
    summary = _evidence.validate_evidence(_evidence.EVIDENCE_DIR)
    assert summary["records"] >= len(_evidence.KNOWN_REQUIREMENT_IDS)


def test_red_on_regression_tempdir_demo() -> None:  # §9.22 (tempdir seam; PASSES by asserting the raise)
    src = _evidence.EVIDENCE_DIR
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="ci-evd-demo-"))
    try:
        (tmp / "templates").mkdir(parents=True, exist_ok=True)
        for rel in _evidence.EVIDENCE_FILENAMES:
            shutil.copyfile(src / rel, tmp / rel)
        doc = json.loads((tmp / _evidence.RECORD_FILENAME).read_text(encoding="utf-8"))
        doc["evidence_records"][0]["evidence_strength"] = "DERIVED_INFERENCE"
        doc["evidence_records"][0]["pass_gate_eligible"] = True
        (tmp / _evidence.RECORD_FILENAME).write_text(json.dumps(doc), encoding="utf-8")
        _expect_raises(_evidence.validate_evidence, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    # the REAL artifacts remain valid (never touched)
    _evidence.validate_evidence(_evidence.EVIDENCE_DIR)


# --- fail-closed meta-tests (§9.16): mutate IN-MEMORY copies; never touch disk -


def test_meta_derived_inference_gate() -> None:  # §9.9
    r = copy.deepcopy(_records()[0])
    r["evidence_strength"] = "DERIVED_INFERENCE"
    r["pass_gate_eligible"] = True
    _expect_raises(_evidence.check_derived_inference_gate, r)


def test_meta_unavailable_gate() -> None:  # §9.10
    r = copy.deepcopy(_records()[0])
    r["evidence_strength"] = "UNAVAILABLE"
    r["pass_gate_eligible"] = True
    _expect_raises(_evidence.check_unavailable_gate, r)


def test_meta_floor_missing_repository() -> None:  # §9.7 (DRIFT-1)
    floor = _evidence.required_field_floor(_schema())
    r = copy.deepcopy(_records()[0])
    del r["repository"]
    _expect_raises(_evidence.check_floor, r, floor)


def test_meta_floor_missing_verdict() -> None:  # §9.7 (operational field)
    floor = _evidence.required_field_floor(_schema())
    r = copy.deepcopy(_records()[0])
    del r["verdict"]
    _expect_raises(_evidence.check_floor, r, floor)


def test_meta_enum_bad_strength() -> None:  # §9.8
    r = copy.deepcopy(_records()[0])
    r["evidence_strength"] = "TOTALLY_BOGUS"
    _expect_raises(_evidence.check_enums, r, _schema())


def test_meta_enum_bad_source() -> None:  # §9.8
    r = copy.deepcopy(_records()[0])
    r["source_classification"] = "BOGUS_SOURCE"
    _expect_raises(_evidence.check_enums, r, _schema())


def test_meta_enum_bad_evidence_type() -> None:  # §9.8
    r = copy.deepcopy(_records()[0])
    r["evidence_type"] = "not_a_type"
    _expect_raises(_evidence.check_enums, r, _schema())


def test_meta_pass_gate_not_boolean() -> None:  # §9.8 (boolean)
    r = copy.deepcopy(_records()[0])
    r["pass_gate_eligible"] = "true"
    _expect_raises(_evidence.check_enums, r, _schema())


def test_meta_runtime_inferred() -> None:  # §9.11
    recs = _records()
    r = copy.deepcopy(next(x for x in recs if x.get("source_classification") == "GH_CLI_EVIDENCE"))
    r["evidence_strength"] = "DERIVED_INFERENCE"
    _expect_raises(_evidence.check_runtime_not_inferred, r)


def test_meta_required_check_verdict_changed() -> None:  # §9.12
    recs = copy.deepcopy(_records())
    for r in recs:
        if r.get("requirement_id") == _evidence.REQUIRED_CHECK_ID:
            r["verdict"] = "PASS — EVIDENCE COMPLETE"
    _expect_raises(_evidence.check_required_check_record, recs)


def test_meta_blocked_reason_code_out_of_set() -> None:  # §9.12 (STOP)
    recs = copy.deepcopy(_records())
    for r in recs:
        if r.get("requirement_id") == _evidence.REQUIRED_CHECK_ID:
            r["verdict_reason_code"] = "SOME-UNKNOWN-CODE"
    _expect_raises(_evidence.check_blocked_reason_codes, recs)
    _expect_raises(_evidence.check_required_check_record, recs)


def test_meta_known_id_removed() -> None:  # §9.6
    recs = [r for r in copy.deepcopy(_records()) if r.get("requirement_id") != _evidence.KNOWN_REQUIREMENT_IDS[0]]
    _expect_raises(_evidence.check_known_ids_present, recs)


def test_meta_empty_json() -> None:  # §9.4
    _expect_raises(_evidence.parse_json_text, "", "empty")


def test_meta_garbled_json() -> None:  # §9.4
    _expect_raises(_evidence.parse_json_text, "not json at all <<<", "garbled")


def test_meta_record_shape_not_list() -> None:  # §9.5
    _expect_raises(_evidence.records_of, {"evidence_records": {}})
    _expect_raises(_evidence.records_of, {"evidence_records": []})


def test_meta_secret_in_file_text() -> None:  # §9.14 (file-level)
    _expect_raises(_evidence.scan_text_for_secrets, "prefix " + _SYNTH_AUTH_HEADER + " suffix", "synthetic-file")


def test_meta_secret_in_record_field() -> None:  # §9.14 (field-level)
    r = copy.deepcopy(_records()[0])
    r["assertion_performed"] = "leaked " + _SYNTH_GH_TOKEN
    _expect_raises(_evidence.scan_record_fields_for_secrets, r)


def test_meta_verdict_gate_inconsistent() -> None:  # §9.18
    recs = _records()
    r = copy.deepcopy(next(x for x in recs if str(x.get("verdict", "")).startswith("BLOCKED")))
    r["pass_gate_eligible"] = True
    _expect_raises(_evidence.check_verdict_gate_consistency, r)


def test_meta_evidence_id_bad_format() -> None:  # §9.17
    recs = copy.deepcopy(_records())
    recs[0]["evidence_id"] = "foo"
    _expect_raises(_evidence.check_evidence_ids, recs)


def test_meta_evidence_id_duplicate() -> None:  # §9.17
    recs = copy.deepcopy(_records())
    recs[1]["evidence_id"] = recs[0]["evidence_id"]
    _expect_raises(_evidence.check_evidence_ids, recs)


def test_meta_requirement_id_duplicate() -> None:  # §9.17 (the closed Minor)
    recs = copy.deepcopy(_records())
    recs[1]["requirement_id"] = recs[0]["requirement_id"]
    _expect_raises(_evidence.check_requirement_ids_unique, recs)


def test_meta_sha_shape_bad() -> None:  # §9.19
    r = copy.deepcopy(_records()[0])
    r["commit_sha"] = "ABC123"
    _expect_raises(_evidence.check_sha_shape, r)


def test_meta_schema_enum_dropped() -> None:  # §9.20a (DROPPED branch)
    schema = copy.deepcopy(_schema())
    enum = schema["definitions"]["evidence_record"]["properties"]["evidence_strength"]["enum"]
    schema["definitions"]["evidence_record"]["properties"]["evidence_strength"]["enum"] = [v for v in enum if v != "DERIVED_INFERENCE"]
    _expect_raises(_evidence.check_enum_freeze, schema)


def test_meta_schema_enum_added() -> None:  # §9.20a (ADDED branch)
    schema = copy.deepcopy(_schema())
    schema["definitions"]["evidence_record"]["properties"]["evidence_strength"]["enum"].append("UNREVIEWED_NEW_VALUE")
    _expect_raises(_evidence.check_enum_freeze, schema)


def test_meta_schema_required_emptied() -> None:  # §9.20b
    schema = copy.deepcopy(_schema())
    schema["definitions"]["evidence_record"]["required"] = ["evidence_id"]
    _expect_raises(_evidence.check_required_floor_superset, schema)


def test_meta_schema_comment_rule1_deleted() -> None:  # §9.20c
    schema = copy.deepcopy(_schema())
    schema["$comment"] = schema["$comment"].replace("RULE 1", "RULE X")
    _expect_raises(_evidence.check_comment_rules, schema)


def test_meta_schema_definitions_removed() -> None:  # §9.20d
    schema = copy.deepcopy(_schema())
    del schema["definitions"]
    _expect_raises(_evidence.check_schema_shape, schema)
    _expect_raises(_evidence.schema_enum_nonnull, schema, "verdict")


def test_meta_schema_record_drift() -> None:  # §9.20e
    schema = _schema()
    recs = copy.deepcopy(_records())
    recs[0]["totally_undeclared_field"] = "x"
    _expect_raises(_evidence.check_schema_record_drift, recs, schema)


def test_meta_forbidden_import_detected() -> None:  # §9.15
    _expect_raises(_evidence.check_no_forbidden_imports, "import socket\n", "synthetic")
    _expect_raises(_evidence.check_no_forbidden_imports, "import os\n", "synthetic")


# --- guard self-collection (§9.21) --------------------------------------------


def test_guard_self_collection() -> None:  # §9.21 positive
    test_globals = sorted(n for n, v in globals().items() if n.startswith("test_") and callable(v))
    run_names = {getattr(t, "__name__", "") for t in ALL_TESTS}
    _evidence.check_collection_registry(test_globals, run_names, EXPECTED_MIN_TESTS, 25)


def test_meta_self_collection_unregistered() -> None:  # §9.21 (mutation: a collected test not in the runner)
    _expect_raises(_evidence.check_collection_registry, ["test_a", "test_meta_x"], {"test_a"}, 1, 1)


def test_meta_self_collection_count_floor() -> None:  # §9.21 (mutation: collected count below the floor)
    _expect_raises(_evidence.check_collection_registry, ["test_a"], {"test_a"}, 5, 0)


# Explicit standalone-runner registry (hand-listed so a rename breaks the build; §9.21).
ALL_TESTS = [
    test_canonical_path_exists,
    test_deprecated_path_unused,
    test_required_e1_files_exist,
    test_json_well_formed,
    test_record_shape,
    test_known_requirement_ids_present,
    test_required_field_floor,
    test_enum_validation,
    test_derived_inference_not_gate_eligible,
    test_unavailable_not_gate_eligible,
    test_runtime_evidence_not_inferred,
    test_required_check_record_honest,
    test_verdict_gate_consistency,
    test_evidence_id_and_requirement_id_unique,
    test_sha_shape,
    test_no_secrets_in_files_and_fields,
    test_schema_enum_freeze,
    test_schema_required_floor,
    test_schema_comment_rules,
    test_schema_shape,
    test_schema_record_drift,
    test_no_forbidden_imports_in_guard,
    test_cross_file_consistency,
    test_positive_checks_read_real_files,
    test_red_on_regression_tempdir_demo,
    test_meta_derived_inference_gate,
    test_meta_unavailable_gate,
    test_meta_floor_missing_repository,
    test_meta_floor_missing_verdict,
    test_meta_enum_bad_strength,
    test_meta_enum_bad_source,
    test_meta_enum_bad_evidence_type,
    test_meta_pass_gate_not_boolean,
    test_meta_runtime_inferred,
    test_meta_required_check_verdict_changed,
    test_meta_blocked_reason_code_out_of_set,
    test_meta_known_id_removed,
    test_meta_empty_json,
    test_meta_garbled_json,
    test_meta_record_shape_not_list,
    test_meta_secret_in_file_text,
    test_meta_secret_in_record_field,
    test_meta_verdict_gate_inconsistent,
    test_meta_evidence_id_bad_format,
    test_meta_evidence_id_duplicate,
    test_meta_requirement_id_duplicate,
    test_meta_sha_shape_bad,
    test_meta_schema_enum_dropped,
    test_meta_schema_enum_added,
    test_meta_schema_required_emptied,
    test_meta_schema_comment_rule1_deleted,
    test_meta_schema_definitions_removed,
    test_meta_schema_record_drift,
    test_meta_forbidden_import_detected,
    test_guard_self_collection,
    test_meta_self_collection_unregistered,
    test_meta_self_collection_count_floor,
]


if __name__ == "__main__":
    _scan.run(ALL_TESTS)
