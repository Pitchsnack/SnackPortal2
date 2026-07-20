"""B5-BLK-8B — controlled-rollback-rehearsal boundary guard (default suite; no DB, no network).

Static text/AST boundary pins for the B5-BLK-8B disposable rollback rehearsal surfaces:

  - backend/tests/control_plane/requires_pg/test_pg_controlled_rollback_rehearsal.py   (the harness)
  - infrastructure/runbooks/controlled_rollback_rehearsal.md                           (the runbook)

This guard binds no runtime, imports no database driver, opens no socket, and touches no database. It keeps
the rollback rehearsal an honest, NON-PRODUCTION / MANUAL_ONLY, composed-core, disposable-only proof, and
fails CLOSED on any Gateway/Auth/served-edge reintroduction, standing/production database name, secret leak,
census drift, or production/closure/destructive overclaim. It references the 8A rollback runbook, the 8A
evidence template, and the served-write runbook as reference-delta targets (existence only).

Exactly eighteen tests (the accepted 17-test boundary battery + the 8B evidence-finalization-order corrective pin):

 1. test_manifest_surfaces_exist
 2. test_harness_is_manual_only_requires_pg_and_start_gated
 3. test_harness_uses_exactly_three_disposable_db_names
 4. test_harness_forbids_standing_and_production_db_names
 5. test_harness_is_composed_core_no_gateway_no_auth
 6. test_harness_is_portless_no_served_edges
 7. test_harness_names_secret_resolution_trigger_and_fallback
 8. test_harness_rollback_target_is_in_memory_no_io
 9. test_harness_before_equals_after_and_adjacent_unchanged
10. test_harness_nondestructive_no_tenant_deletion
11. test_harness_complete_disposal_finally
12. test_harness_maps_all_22_evidence_fields
13. test_harness_evidence_is_references_only_dbr_ar_2e_shape
14. test_runbook_manual_only_nonproduction_and_reference_delta
15. test_surfaces_reject_production_and_closure_overclaims
16. test_surfaces_preserve_blk8_open_census_and_do_not_activate
17. test_harness_touches_no_contract_adr_or_workflow_surface
18. test_harness_finalizes_authoritative_evidence_only_after_disposal

This guard closes no blocker. B5-BLK-8 remains OPEN; the live blocker census remains 7 of 9 OPEN; production
remains NOT READY / DO-NOT-ACTIVATE. The guard positively requires exactly that and rejects any drift.

Pure stdlib; standalone-runnable:
  python tests/architecture/test_controlled_rollback_rehearsal_boundaries.py
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_HARNESS = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "test_pg_controlled_rollback_rehearsal.py"
_RUNBOOK = _scan.REPO_ROOT / "infrastructure" / "runbooks" / "controlled_rollback_rehearsal.md"

# Reference-delta targets — referenced (existence-only), never restated by the 8B surfaces.
_REF_8A_RUNBOOK = _scan.REPO_ROOT / "infrastructure" / "runbooks" / "b5_blk8_rollback_to_deferred_composition.md"
_REF_SERVED_RUNBOOK = _scan.REPO_ROOT / "infrastructure" / "runbooks" / "controlled_served_write_rehearsal.md"
_REF_8A_TEMPLATE = _scan.REPO_ROOT / "docs" / "runtime" / "b5_blk8_rollback_evidence_template.md"

# The three disposable database names — the ONLY database names the harness may create/drop.
_DISPOSABLE_DBS = {"sp2_rollback_control", "sp2_rollback_target", "sp2_rollback_adjacent"}
_DB_NAME_RE = re.compile(r"^sp2_[a-z0-9]+_[a-z0-9]+$")

# Standing / sibling-disposable / staging database name fragments that must NEVER appear in the harness.
_FORBIDDEN_DB_NAMES = [
    "sp2_b3a_control",
    "snackportal2_control_local",
    "b5_standing",
    "sp2_rehearsal",
    "sp2_tenant_",
    "sp2_w1a_import_proof",
    "sp2_gateway_audit_v1a_proof",
    "sp2_b5_blk6",
]

# Imports the harness must NEVER carry (composed-core has no served ingress, no crypto).
_FORBIDDEN_IMPORT_PREFIXES = ("api_gateway", "auth_router")
_FORBIDDEN_IMPORT_EXACT = {"jwt", "cryptography", "socket"}
# Runtime-source packages the harness must never import (contract/ADR/workflow minimum pin — test 17).
_FORBIDDEN_RUNTIME_IMPORTS = ("api_gateway", "auth_router", "import_service", "lineage_service")

# Served-edge markers that must NEVER appear in the composed-core harness.
_SERVED_MARKERS = ["_server_from_env", "httpconnection", "socket.create_connection", "create_connection"]
_SERVED_ENV_PREFIXES = ["sp2_gw_", "sp2_ar_", "sp2_dbr_", "sp2_import_"]

# The 22 references-only rollback-record field tokens (the 8A template shape).
_ROLLBACK_FIELDS = [
    "EXECUTION_ID",
    "EXECUTION_DATE",
    "OPERATOR",
    "ENVIRONMENT_CLASS",
    "BASELINE_MAIN_SHA",
    "ACTIVATION_MODE",
    "ROLLBACK_TRIGGER",
    "ROLLBACK_PLAN_REF",
    "PRE_ROLLBACK_STATE_REF",
    "POST_ROLLBACK_STATE_REF",
    "TENANT_SCOPE",
    "ADJACENT_TENANT_SCOPE",
    "BEFORE_DATA_DIGEST",
    "AFTER_DATA_DIGEST",
    "ISOLATION_ASSERTION",
    "NON_DESTRUCTIVE_ASSERTION",
    "FAILURE_RECORD_REF",
    "AUDIT_RECORD_REF",
    "SECRET_REFERENCE_ONLY_ASSERTION",
    "DEFERRED_COMPOSITION_ASSERTION",
    "DISPOSAL_ASSERTION",
    "FINAL_VERDICT",
]

# The 19-key DBR-AR-2E evidence-entry shape the harness must map.
_EVIDENCE_KEYS = [
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
]

# Destructive tenant-data SQL the harness must NEVER contain (only disposable DROP DATABASE is allowed).
_DESTRUCTIVE_SQL = ["drop table", "delete from", "truncate"]

# Forbidden production / closure / destructive-rollback / census overclaim patterns (normalized text).
_FORBIDDEN_PATTERNS = [
    (r"production\s+ready", "'production ready' overclaim"),
    (r"production\s+activation\s+authorized", "'production activation authorized' overclaim"),
    (r"activate\s+production", "'activate production' overclaim"),
    (r"production\s+rollback\s+proven", "'production rollback proven' overclaim"),
    (r"rollback\s+proof\s+(?:for\s+)?production", "'rollback proof for production' overclaim"),
    (r"b5-?blk-?8\s+(?:is\s+|now\s+)?closed", "'B5-BLK-8 closed' overclaim"),
    (r"b5-?blk-?8\s*[:=]\s*closed", "'B5-BLK-8: closed' overclaim"),
    (r"\b6\s*(?:of|/)\s*9\b", "false census '6 of 9'"),
    (r"\b8\s*(?:of|/)\s*9\b", "stale census '8 of 9'"),
    (r"destructive\s+rollback\s+authoriz", "'destructive rollback authorized' overclaim"),
    (r"delete[sd]?\s+tenant\s+data", "'delete tenant data' destructive claim"),
    (r"drop\s+tenant\s+database", "'drop tenant database' destructive claim"),
    (r"do-not-activate\s+lifted", "'do-not-activate lifted' overclaim"),
]

_LOCKED_STATE_NEEDLES = ["b5-blk-8 remains open", "7 of 9 open", "not ready / do-not-activate"]

# Secret/PII shape detectors (BUILT from low-entropy fragments — never a contiguous shape here).
_DSN_RE = re.compile("postgresql" + "://" + r"\S")
_JWT_MARKER = "ey" + "J"
_KEY_MARKER = "-----" + "BEGIN"
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def _text(path: pathlib.Path) -> str:
    assert path.is_file(), f"{path} must exist"
    return path.read_text(encoding="utf-8")


def _norm(s: str) -> str:
    """Lowercase, normalize dash/arrow glyphs, drop markdown emphasis, and collapse whitespace."""
    s = s.lower()
    s = s.replace("—", "-").replace("–", "-").replace("→", "->")
    s = s.replace("*", "").replace("`", "")
    return re.sub(r"\s+", " ", s)


def _harness_tree() -> ast.AST:
    return ast.parse(_text(_HARNESS), filename=str(_HARNESS))


def _string_literals(tree: ast.AST) -> set[str]:
    return {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}


def test_manifest_surfaces_exist() -> None:
    assert _HARNESS.is_file(), "the B5-BLK-8B rollback rehearsal harness must exist at the manifest path"
    assert _RUNBOOK.is_file(), "the B5-BLK-8B rollback rehearsal runbook must exist at the manifest path"
    for ref in (_REF_8A_RUNBOOK, _REF_SERVED_RUNBOOK, _REF_8A_TEMPLATE):
        assert ref.is_file(), f"the reference-delta target must exist: {ref.name}"


def test_harness_is_manual_only_requires_pg_and_start_gated() -> None:
    norm = _norm(_text(_HARNESS))
    for needle in ("manual_only", "requires_pg", "start-gate", "clean-skip", "psycopg", "snackportal_test_dsn"):
        assert needle in norm, f"the harness must be a MANUAL_ONLY, requires_pg, START-GATED clean-skip harness: missing {needle!r}"


def test_harness_uses_exactly_three_disposable_db_names() -> None:
    literals = _string_literals(_harness_tree())
    db_names = {s for s in literals if _DB_NAME_RE.match(s)}
    assert db_names == _DISPOSABLE_DBS, f"the harness must create/drop EXACTLY the three disposable databases; got {sorted(db_names)}"
    # non-vacuity: the DB-name detector must fire on a planted DB name and ignore a scratch-dir prefix.
    assert _DB_NAME_RE.match("sp2_rollback_control"), "the DB-name detector must match a planted disposable name"
    assert not _DB_NAME_RE.match("sp2_rollback_secrets_"), "the DB-name detector must ignore a scratch-dir prefix"


def test_harness_forbids_standing_and_production_db_names() -> None:
    norm = _norm(_text(_HARNESS))
    for name in _FORBIDDEN_DB_NAMES:
        assert name not in norm, f"the harness must never name a standing/sibling database: {name!r}"
    # non-vacuity: a planted standing name must be detected.
    assert "sp2_b3a_control" in _norm("touch sp2_b3a_control"), "the standing-name detector must fire on a planted sample"


def test_harness_is_composed_core_no_gateway_no_auth() -> None:
    src = _text(_HARNESS)
    for needle in ("control_plane.main", "database_router.router", "PgRoutedSessionProvider"):
        assert needle in src, f"the harness must compose the core (Control Plane + Database Router): missing {needle!r}"
    imported = _scan.imported_modules(_HARNESS)
    for mod in imported:
        assert not mod.startswith(_FORBIDDEN_IMPORT_PREFIXES), f"composed-core must import no served ingress: {mod!r}"
        assert mod not in _FORBIDDEN_IMPORT_EXACT, f"composed-core must import no crypto/socket: {mod!r}"
        assert "crypto_fixture" not in mod, f"composed-core must not load the crypto fixture: {mod!r}"
    # non-vacuity: the forbidden-import detector must fire on a planted module list.
    planted = ["api_gateway.main", "auth_router.main", "jwt"]
    assert any(m.startswith(_FORBIDDEN_IMPORT_PREFIXES) or m in _FORBIDDEN_IMPORT_EXACT for m in planted), "detector must fire"


def test_harness_is_portless_no_served_edges() -> None:
    norm = _norm(_text(_HARNESS))
    for marker in _SERVED_MARKERS:
        assert marker not in norm, f"the composed-core harness must host no served edge: {marker!r}"
    for prefix in _SERVED_ENV_PREFIXES:
        assert prefix not in norm, f"the composed-core harness must set no served-edge env key: {prefix!r}"
    # non-vacuity: the served-edge detectors must fire on planted samples.
    assert "_server_from_env" in _norm("build_gateway_edge_server_from_env()"), "the served-factory detector must fire"
    assert "sp2_gw_" in _norm("SP2_GW_EDGE_HOST"), "the served-env detector must fire"


def test_harness_names_secret_resolution_trigger_and_fallback() -> None:
    norm = _norm(_text(_HARNESS))
    assert "secret-resolution failure" in norm, "the harness must name the preferred secret-resolution failure trigger"
    assert "distinctness regression" in norm, "the harness must name the documented distinctness-regression fallback"


def test_harness_rollback_target_is_in_memory_no_io() -> None:
    norm = _norm(_text(_HARNESS))
    for needle in ("in-memory", "construction performs no i/o", "calls == []"):
        assert needle in norm, f"the rollback target must be the in-memory default proven with no I/O: missing {needle!r}"
    assert "notimplementederror" not in norm, "the rollback proof must NOT require a NotImplementedError assertion (C-1)"
    # non-vacuity: the NotImplementedError detector must fire on a planted sample.
    assert "notimplementederror" in _norm("raise NotImplementedError"), "the NotImplementedError detector must fire"


def test_harness_before_equals_after_and_adjacent_unchanged() -> None:
    norm = _norm(_text(_HARNESS))
    for needle in ("before_data_digest", "after_data_digest", "adjacent", "untouched"):
        assert needle in norm, f"the harness must prove before == after with the adjacent tenant untouched: missing {needle!r}"


def test_harness_nondestructive_no_tenant_deletion() -> None:
    norm = _norm(_text(_HARNESS))
    for needle in ("d-24", "non-destructive"):
        assert needle in norm, f"the harness must state the D-24 non-destructive discipline: missing {needle!r}"
    assert "drop database" in norm, "the harness must dispose disposable databases with DROP DATABASE"
    for banned in _DESTRUCTIVE_SQL:
        assert banned not in norm, f"the harness must never run destructive tenant-table SQL: {banned!r}"
    # non-vacuity: the destructive-SQL detector must fire on planted samples.
    for banned in _DESTRUCTIVE_SQL:
        assert banned in _norm("DROP TABLE x; DELETE FROM y; TRUNCATE z"), f"the destructive-SQL detector must fire: {banned!r}"


def test_harness_complete_disposal_finally() -> None:
    norm = _norm(_text(_HARNESS))
    for needle in ("finally", "pg_terminate_backend", "drop database if exists", "retained == 0"):
        assert needle in norm, f"the harness must guarantee complete finally disposal: missing {needle!r}"
    tree = _harness_tree()
    has_finally = any(isinstance(node, ast.Try) and node.finalbody for node in ast.walk(tree))
    assert has_finally, "the harness must dispose in a finally block (AST Try.finalbody)"


def test_harness_maps_all_22_evidence_fields() -> None:
    src = _text(_HARNESS)
    for field in _ROLLBACK_FIELDS:
        assert field in src, f"the harness must map the 22-field evidence record: missing {field}"
    assert len(_ROLLBACK_FIELDS) == 22, "the rollback record shape must be exactly 22 fields"


def test_harness_evidence_is_references_only_dbr_ar_2e_shape() -> None:
    src = _text(_HARNESS)
    norm = _norm(src)
    assert "references only" in norm, "the harness evidence must declare a references-only discipline"
    assert "ref:" in src, "the harness evidence must use ref:... reference anchors"
    for key in _EVIDENCE_KEYS:
        assert key in src, f"the harness must build the 19-key DBR-AR-2E evidence entry: missing {key}"
    for key in ("sensitivity", "retention"):
        assert key in src, f"the DBR-AR-2E entry must carry {key}"
    assert not _DSN_RE.search(src), "a DSN-shaped value must never appear in the harness"
    assert _JWT_MARKER not in src, "a token-shaped value must never appear in the harness"
    assert _KEY_MARKER not in src, "key material must never appear in the harness"
    assert not _EMAIL_RE.search(src), "PII (email-shaped) content must never appear in the harness"
    # non-vacuity: every secret detector must fire on a fragment-built planted sample.
    assert _DSN_RE.search("postgresql" + "://u:p@h/db"), "a planted DSN must be detectable"
    assert _JWT_MARKER in ("ey" + "J" + "0aaa"), "a planted token shape must be detectable"
    assert _KEY_MARKER in ("-----" + "BEGIN" + " PRIVATE KEY"), "planted key material must be detectable"
    assert _EMAIL_RE.search("ops" + "@" + "example.com"), "a planted email must be detectable"


def test_runbook_manual_only_nonproduction_and_reference_delta() -> None:
    norm = _norm(_text(_RUNBOOK))
    for needle in ("manual_only", "non-production"):
        assert needle in norm, f"the runbook must be MANUAL_ONLY / non-production: missing {needle!r}"
    for ref in ("b5_blk8_rollback_to_deferred_composition.md", "controlled_served_write_rehearsal.md"):
        assert ref in norm, f"the runbook must reference (not restate) the delta target: {ref}"
    for needle in ("composition rollback", "r-a disposal"):
        assert needle in norm, f"the runbook must keep the composition-rollback vs R-A-disposal distinction: missing {needle!r}"


def test_surfaces_reject_production_and_closure_overclaims() -> None:
    for path in (_HARNESS, _RUNBOOK):
        norm = _norm(_text(path))
        for pattern, label in _FORBIDDEN_PATTERNS:
            assert re.search(pattern, norm) is None, f"forbidden wording present in {path.name} ({label}): /{pattern}/"
    # non-vacuity: every detector must fire on a planted normalized sample built from fragments.
    planted = _norm(
        "production ready. production activation authorized. activate production. "
        "production rollback proven. rollback proof for production. b5-blk-8 is closed. "
        "b5-blk-8: closed. 6 of 9. 8 of 9. destructive rollback authorized. "
        "deletes tenant data. drop tenant database. do-not-activate lifted."
    )
    for pattern, label in _FORBIDDEN_PATTERNS:
        assert re.search(pattern, planted), f"forbidden-pattern detector must fire on a planted sample ({label}): /{pattern}/"


def test_surfaces_preserve_blk8_open_census_and_do_not_activate() -> None:
    for path in (_HARNESS, _RUNBOOK):
        norm = _norm(_text(path))
        for needle in _LOCKED_STATE_NEEDLES:
            assert needle in norm, f"{path.name} must preserve the locked state: missing {needle!r}"
    guard_src = _norm(pathlib.Path(__file__).read_text(encoding="utf-8"))
    assert "closes no blocker" in guard_src, "the guard must declare that it closes no blocker"


def test_harness_touches_no_contract_adr_or_workflow_surface() -> None:
    norm = _norm(_text(_HARNESS))
    for fragment in ("contracts/", ".github/workflows", "architecture-decision-register"):
        assert fragment not in norm, f"the harness must not reference a contract/ADR/workflow surface: {fragment!r}"
    imported = _scan.imported_modules(_HARNESS)
    for mod in imported:
        assert not mod.startswith(_FORBIDDEN_RUNTIME_IMPORTS), f"the harness must not import runtime service source: {mod!r}"
    # non-vacuity: the forbidden-surface detectors must fire on planted samples.
    assert "contracts/" in _norm("open contracts/IC-002.md"), "the contract-path detector must fire"
    assert any(m.startswith(_FORBIDDEN_RUNTIME_IMPORTS) for m in ["import_service.main"]), "the runtime-import detector must fire"


# --- 8B evidence-finalization-order corrective pin (single-final-write) --------------------------
def _rehearsal_fn(tree: ast.AST) -> ast.FunctionDef:
    """The one ``test_pg_controlled_rollback_rehearsal`` function node in a rehearsal-shaped module tree."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "test_pg_controlled_rollback_rehearsal":
            return node
    raise AssertionError("the rehearsal harness must define test_pg_controlled_rollback_rehearsal")


def _subscript_assign_lines(scope: ast.AST, base: str, key: str) -> list[int]:
    """Line numbers of ``base["key"] = ...`` assignment statements within ``scope`` (sorted)."""
    lines: list[int] = []
    for node in ast.walk(scope):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == base
                and isinstance(target.slice, ast.Constant)
                and target.slice.value == key
            ):
                lines.append(node.lineno)
    return sorted(lines)


def _finalization_positions(fn: ast.FunctionDef) -> tuple[int, int, int, int, int]:
    """Return ``(try_end, retained_ln, disposal_ln, verdict_ln, write_ln)`` for a rehearsal-shaped function,
    raising AssertionError when a required single-final-write element is missing or duplicated:
      * exactly one top-level ``try/finally`` disposal block (its end line);
      * exactly one ``retained == 0`` assertion inside that finally;
      * exactly one ``_write_evidence_bundle(...)`` call in the whole function;
      * exactly one ``record["DISPOSAL_ASSERTION"] = ...`` and one ``record["FINAL_VERDICT"] = ...`` assignment.
    """
    outer_try = next((n for n in fn.body if isinstance(n, ast.Try) and n.finalbody), None)
    assert outer_try is not None and outer_try.end_lineno is not None, "a top-level try/finally disposal block is required"
    retained = [
        n.lineno
        for n in ast.walk(outer_try)
        if isinstance(n, ast.Assert)
        and isinstance(n.test, ast.Compare)
        and isinstance(n.test.left, ast.Name)
        and n.test.left.id == "retained"
        and len(n.test.ops) == 1
        and isinstance(n.test.ops[0], ast.Eq)
        and len(n.test.comparators) == 1
        and isinstance(n.test.comparators[0], ast.Constant)
        and n.test.comparators[0].value == 0
    ]
    assert len(retained) == 1, f"exactly one 'retained == 0' finally assertion is required (found {len(retained)})"
    writes = [
        n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_write_evidence_bundle"
    ]
    assert len(writes) == 1, f"exactly one authoritative _write_evidence_bundle(...) call is required (found {len(writes)})"
    disposal = _subscript_assign_lines(fn, "record", "DISPOSAL_ASSERTION")
    verdict = _subscript_assign_lines(fn, "record", "FINAL_VERDICT")
    assert len(disposal) == 1, f"record['DISPOSAL_ASSERTION'] must be assigned exactly once (found {len(disposal)})"
    assert len(verdict) == 1, f"record['FINAL_VERDICT'] must be assigned exactly once (found {len(verdict)})"
    return outer_try.end_lineno, retained[0], disposal[0], verdict[0], writes[0]


def _valid_finalization_order(fn: ast.FunctionDef) -> bool:
    """True iff the sole write and BOTH the PASS/verdict assignments occur strictly after the ``retained == 0``
    assertion AND outside (after) the cleanup finally — the single-final-write invariant."""
    try:
        try_end, retained_ln, disposal_ln, verdict_ln, write_ln = _finalization_positions(fn)
    except AssertionError:
        return False
    return (
        retained_ln <= try_end
        and disposal_ln > try_end
        and verdict_ln > try_end
        and write_ln > try_end
        and retained_ln < disposal_ln < write_ln
        and retained_ln < verdict_ln < write_ln
    )


# One minimal single-final-write chronology (valid) + five rejected chronologies (each an independent
# violation the corrective pin must refuse). Parsed with ast for the non-vacuity companion — never executed.
_GOOD_FINALIZATION = """
def test_pg_controlled_rollback_rehearsal(admin_dsn):
    record = {}
    evidence = []
    try:
        record = {"BEFORE_DATA_DIGEST": "x"}
    finally:
        retained = 0
        assert retained == 0
    record["DISPOSAL_ASSERTION"] = "PASS (retained=0)"
    record["FINAL_VERDICT"] = "ROLLBACK-PROVEN-LOCAL"
    _write_evidence_bundle(bundle_path, record, evidence)
"""

_REJECT_WRITE_IN_S9 = """
def test_pg_controlled_rollback_rehearsal(admin_dsn):
    record = {}
    evidence = []
    try:
        record = {"BEFORE_DATA_DIGEST": "x"}
        _write_evidence_bundle(bundle_path, record, evidence)
    finally:
        retained = 0
        assert retained == 0
    record["DISPOSAL_ASSERTION"] = "PASS (retained=0)"
    record["FINAL_VERDICT"] = "ROLLBACK-PROVEN-LOCAL"
"""

_REJECT_WRITE_BEFORE_DISPOSAL = """
def test_pg_controlled_rollback_rehearsal(admin_dsn):
    record = {}
    evidence = []
    try:
        record = {"BEFORE_DATA_DIGEST": "x"}
    finally:
        _write_evidence_bundle(bundle_path, record, evidence)
        retained = 0
        assert retained == 0
    record["DISPOSAL_ASSERTION"] = "PASS (retained=0)"
    record["FINAL_VERDICT"] = "ROLLBACK-PROVEN-LOCAL"
"""

_REJECT_PASS_BEFORE_RETAINED = """
def test_pg_controlled_rollback_rehearsal(admin_dsn):
    record = {}
    evidence = []
    try:
        record = {"BEFORE_DATA_DIGEST": "x"}
    finally:
        record["DISPOSAL_ASSERTION"] = "PASS (retained=0)"
        retained = 0
        assert retained == 0
    record["FINAL_VERDICT"] = "ROLLBACK-PROVEN-LOCAL"
    _write_evidence_bundle(bundle_path, record, evidence)
"""

_REJECT_VERDICT_BEFORE_RETAINED = """
def test_pg_controlled_rollback_rehearsal(admin_dsn):
    record = {}
    evidence = []
    try:
        record = {"BEFORE_DATA_DIGEST": "x"}
    finally:
        record["FINAL_VERDICT"] = "ROLLBACK-PROVEN-LOCAL"
        retained = 0
        assert retained == 0
    record["DISPOSAL_ASSERTION"] = "PASS (retained=0)"
    _write_evidence_bundle(bundle_path, record, evidence)
"""

_REJECT_DUPLICATE_WRITE = """
def test_pg_controlled_rollback_rehearsal(admin_dsn):
    record = {}
    evidence = []
    try:
        record = {"BEFORE_DATA_DIGEST": "x"}
    finally:
        retained = 0
        assert retained == 0
    record["DISPOSAL_ASSERTION"] = "PASS (retained=0)"
    record["FINAL_VERDICT"] = "ROLLBACK-PROVEN-LOCAL"
    _write_evidence_bundle(bundle_path, record, evidence)
    _write_evidence_bundle(bundle_path, record, evidence)
"""

_REJECTED_FINALIZATIONS = (
    ("write inside S9 (before disposal)", _REJECT_WRITE_IN_S9),
    ("write in finally before retained==0", _REJECT_WRITE_BEFORE_DISPOSAL),
    ("DISPOSAL_ASSERTION=PASS before retained==0", _REJECT_PASS_BEFORE_RETAINED),
    ("FINAL_VERDICT before retained==0", _REJECT_VERDICT_BEFORE_RETAINED),
    ("duplicate authoritative write", _REJECT_DUPLICATE_WRITE),
)


def test_harness_finalizes_authoritative_evidence_only_after_disposal() -> None:
    """8B corrective single-final-write pin: the sole ``_write_evidence_bundle(...)`` call AND both the
    ``record["DISPOSAL_ASSERTION"] = "PASS (retained=0)"`` and ``record["FINAL_VERDICT"] =
    "ROLLBACK-PROVEN-LOCAL"`` assignments must occur strictly AFTER the finally disposal's ``retained == 0``
    assertion and OUTSIDE the cleanup finally — so a failed run or a failed disposal can never retain a
    false-PASS record. Rejects a premature PASS, a premature ROLLBACK-PROVEN-LOCAL, a write before disposal,
    a write inside S9, and a duplicate authoritative write."""
    fn = _rehearsal_fn(_harness_tree())
    try_end, retained_ln, disposal_ln, verdict_ln, write_ln = _finalization_positions(fn)
    assert retained_ln <= try_end, "the retained==0 assertion must live inside the cleanup finally"
    assert disposal_ln > try_end, "DISPOSAL_ASSERTION must be assigned OUTSIDE (after) the cleanup finally"
    assert verdict_ln > try_end, "FINAL_VERDICT must be assigned OUTSIDE (after) the cleanup finally"
    assert write_ln > try_end, "the sole authoritative write must occur OUTSIDE (after) the cleanup finally"
    assert retained_ln < disposal_ln, "DISPOSAL_ASSERTION=PASS must be set AFTER the retained==0 assertion"
    assert retained_ln < verdict_ln, "FINAL_VERDICT must be set AFTER the retained==0 assertion"
    assert disposal_ln < write_ln, "the authoritative write must occur AFTER the DISPOSAL_ASSERTION assignment"
    assert verdict_ln < write_ln, "the authoritative write must occur AFTER the FINAL_VERDICT assignment"
    assert _valid_finalization_order(fn), "the harness must satisfy the single-final-write finalization order"

    # the finalized authoritative tokens are exactly the accepted values (no wording drift).
    src = _text(_HARNESS)
    assert 'record["DISPOSAL_ASSERTION"] = "PASS (retained=0)"' in src, "DISPOSAL_ASSERTION must finalize to 'PASS (retained=0)'"
    assert 'record["FINAL_VERDICT"] = "ROLLBACK-PROVEN-LOCAL"' in src, "FINAL_VERDICT must finalize to 'ROLLBACK-PROVEN-LOCAL'"

    # the DISPOSAL_ASSERTION / FINAL_VERDICT tokens must appear ONLY after the finally (never as an S9 dict key).
    for token in ("DISPOSAL_ASSERTION", "FINAL_VERDICT"):
        occ = sorted(
            node.lineno for node in ast.walk(fn) if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value == token
        )
        assert occ, f"the {token} finalization token must be present in the rehearsal body"
        assert min(occ) > try_end, f"{token} must be finalized only AFTER the cleanup finally (found one at/inside it)"

    # C9 pin: the authoritative bundle is written to a FRESH, post-disposal evidence mkdtemp — never the
    # scratch-secret dir; the scratch-secret dir is not referenced anywhere in the post-disposal finalization.
    assert 'tempfile.mkdtemp(prefix="sp2_rollback_evidence_")' in src, (
        "S-final must create a dedicated evidence dir (not reuse the scratch-secret dir)"
    )
    evidence_dir_lines = sorted(
        node.lineno
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "mkdtemp"
        and any(
            kw.arg == "prefix" and isinstance(kw.value, ast.Constant) and kw.value.value == "sp2_rollback_evidence_" for kw in node.keywords
        )
    )
    assert len(evidence_dir_lines) == 1 and evidence_dir_lines[0] > try_end, (
        "the evidence dir must be created exactly once, AFTER the finally disposal"
    )
    assert not any(isinstance(node, ast.Name) and node.id == "secret_dir" and node.lineno > try_end for node in ast.walk(fn)), (
        "the scratch-secret dir must not be referenced in the post-disposal finalization (C9)"
    )

    # C10 pin: a post-write existence assertion guards the finalized bundle and must follow the write.
    existence_asserts = [
        node.lineno
        for node in ast.walk(fn)
        if isinstance(node, ast.Assert) and any(isinstance(c, ast.Attribute) and c.attr == "is_file" for c in ast.walk(node.test))
    ]
    assert existence_asserts and min(existence_asserts) > write_ln, (
        "a post-write bundle_path.is_file() existence assertion must follow the write (C10)"
    )

    # non-vacuity: the good chronology validates and every rejected chronology is refused.
    assert _valid_finalization_order(_rehearsal_fn(ast.parse(_GOOD_FINALIZATION))), "the single-final-write chronology must validate"
    for label, snippet in _REJECTED_FINALIZATIONS:
        assert not _valid_finalization_order(_rehearsal_fn(ast.parse(snippet))), f"a rejected chronology must be refused: {label}"


if __name__ == "__main__":
    _scan.run(
        [
            test_manifest_surfaces_exist,
            test_harness_is_manual_only_requires_pg_and_start_gated,
            test_harness_uses_exactly_three_disposable_db_names,
            test_harness_forbids_standing_and_production_db_names,
            test_harness_is_composed_core_no_gateway_no_auth,
            test_harness_is_portless_no_served_edges,
            test_harness_names_secret_resolution_trigger_and_fallback,
            test_harness_rollback_target_is_in_memory_no_io,
            test_harness_before_equals_after_and_adjacent_unchanged,
            test_harness_nondestructive_no_tenant_deletion,
            test_harness_complete_disposal_finally,
            test_harness_maps_all_22_evidence_fields,
            test_harness_evidence_is_references_only_dbr_ar_2e_shape,
            test_runbook_manual_only_nonproduction_and_reference_delta,
            test_surfaces_reject_production_and_closure_overclaims,
            test_surfaces_preserve_blk8_open_census_and_do_not_activate,
            test_harness_touches_no_contract_adr_or_workflow_surface,
            test_harness_finalizes_authoritative_evidence_only_after_disposal,
        ]
    )
