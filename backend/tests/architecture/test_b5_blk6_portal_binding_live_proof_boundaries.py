"""B5-BLK-6C-C — portal-binding live-proof boundary pins (default suite; no DB, no network).

Non-vacuously pins the safety boundaries of the 6C-C disposable real-Control-DB portal-composition
proof (``tests/control_plane/requires_pg/b5_blk6_portal_binding_live_proof.py`` + its standalone
wrapper) and its runbook, without touching a database or opening a socket:

* exact surface census — the 6C-C file family is exactly the operator + wrapper + this guard + the
  runbook (no second executable, no production file);
* import-inert module structure for both new python files; stdlib-plus-pinned-backend top import
  surface; no static database-driver / JWT / crypto / test-double / pytest import; the composition
  and provider modules (``control_plane.*``, ``b5_standing_topology``) are imported lazily only;
* REAL-seam-only composition: the operator applies DDL through the accepted ``_apply_control_ddl``
  pattern exactly once (lockstep-read against the accepted helper's own apply order — the standing
  ops harness itself is never imported), builds the real loopback read edge via ``make_server``
  exactly once, selects the production
  adapter through ``build_control_plane_read_from_env``, injects ``control_read=`` into EVERY
  ``build_gateway`` call, composes the plane by explicit ``ControlPlane(store=...)`` injection over
  ``PostgresControlStore`` — and can never swap in the in-memory store (needle ban);
* DDL range 001-009 ONLY: the operator's pinned apply order equals the canonical nine files, is
  lockstep-asserted against the accepted helper, and neither new file may name the excluded
  routing-audit DDL files or any tenant DDL path;
* mandatory ``finally`` teardown: the proof function's ``finally`` must drop the disposable DB,
  census ``pg_database`` by datname, assert the count is 0, and the required closing line
  ("disposable database datname count == 0") must be present;
* MANUAL_ONLY: the wrapper is a registered, justified plain-literal exception of the live-PG run-set
  completeness guard; the hosted live-pg workflow is untouched (no enrollment);
* non-skippability: the wrapper fails CLOSED on a partial configuration (never a silent skip), gates
  the proof-complete claim on the full scenario-label census, and asserts the zero-artifact census;
* envelope non-claims: the ImportInitiation leg pins ``rows_before == rows_after`` (nothing
  persisted), the TenantOperation leg pins ``portal_dto is None``, and the initiation value is
  exactly "accepted";
* secret hygiene: no token-shaped / PEM / DSN-shaped literal in any family file; environment names
  are censused to the two approved ones; ``os.environ`` writes target ONLY the gateway control-read
  selector (save/restore);
* the runbook carries the required needles and non-claims and can never claim B5-BLK-6 closure, MVP
  completion, Lovable cutover, or pagination support.

Pure stdlib; standalone-runnable:
  python tests/architecture/test_b5_blk6_portal_binding_live_proof_boundaries.py

B5-BLK-6 remains OPEN; production remains NOT READY / DO-NOT-ACTIVATE. This guard closes no blocker.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys
from typing import Dict, List, Optional, Set

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_OPS = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "b5_blk6_portal_binding_live_proof.py"
_WRAPPER = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "test_pg_b5_blk6_portal_binding_live_proof.py"
_RUNBOOK = _scan.REPO_ROOT / "infrastructure" / "runbooks" / "b5_blk6_portal_binding_live_proof.md"
_COMPLETENESS_GUARD = _scan.BACKEND_ROOT / "tests" / "architecture" / "test_live_pg_workflow_runset_completeness.py"
_WORKFLOW = _scan.REPO_ROOT / ".github" / "workflows" / "live-pg-durable-path.yml"

_FAMILY_TOKEN = "b5_blk6_portal_binding"
_MANUAL_ONLY_KEY = "tests/control_plane/requires_pg/test_pg_b5_blk6_portal_binding_live_proof.py"
_FAMILY_SKIP_PARTS = {".git", "__pycache__", "build", "dist", ".venv", "venv", "node_modules"}

# The canonical 001-009 apply order the operator must pin (guard-side copy; lockstep by equality).
_EXPECTED_DDL_ORDER = (
    "001_distinctness_ledger.sql",
    "002_provisioning_audit.sql",
    "003_provisioning_audit_append_only.sql",
    "004_control_tenants.sql",
    "005_control_memberships.sql",
    "006_control_federation.sql",
    "007_control_directory.sql",
    "008_distinctness_fingerprint_unique.sql",
    "009_control_tenants_cas_version.sql",
)

# The complete scenario census the operator must declare (guard-side copy; equality-pinned).
_EXPECTED_SCENARIO_LABELS = (
    "startup-directory",
    "investor-directory",
    "live-read-through-identity",
    "memberships-nonempty-audit",
    "memberships-empty-audit",
    "unsupported-kind-fail-closed",
    "client-kind-and-self-scope",
    "import-initiation-envelope",
    "tenant-operation-dispatch",
    "ic007-negatives",
    "pagination-one-page-limitation",
    "malformed-response",
    "oversized-response",
    "control-read-unavailable",
)

# Dynamic needles — built so THIS guard never satisfies its own bans.
_TOKEN_NEEDLE = "e" + "yJ"
_PEM_NEEDLE = "-----BE" + "GIN"
_DSN_NEEDLE = "postgre" + "sql://"
_ROUTING_DDL_NEEDLE = "010_rou" + "ting_audit"
_APPEND_DDL_NEEDLE = "011_rou" + "ting_audit_append_only"
_TENANT_DDL_NEEDLE = "db/ten" + "ant"
_TENANT_DB_NEEDLE = "sp2_ten" + "ant_"
_IN_MEMORY_STORE_NEEDLE = "InMemoryContro" + "lStore"
_PYTEST_SKIP_NEEDLE = "pytest." + "skip"
_CLOSED_CLAIM_NEEDLE = "B5-BLK-6 CLO" + "SED"
_MVP_DONE_NEEDLE = "MVP COMPL" + "ETE"
_CUTOVER_CLAIM_NEEDLE = "Lovable cut" + "over complete"
_PAGINATION_CLAIM_NEEDLE = "supports pagi" + "nation"

_ENV_NAME_RE = re.compile(r"\b(SP2_[A-Z0-9_]+|SNACKPORTAL_[A-Z0-9_]+)\b")
_ALLOWED_ENV_NAMES = {"SP2_GW_CONTROL_READ_BASE_URL", "SNACKPORTAL_TEST_DSN"}
_ENV_SELECTOR_CONST = "GW_CONTROL_READ_BASE_URL_ENV"  # the ONLY name os.environ writes may target

_OPS_TOP_IMPORT_ALLOW = {
    "__future__",
    "ast",
    "os",
    "pathlib",
    "sys",
    "threading",
    "datetime",
    "http.server",
    "typing",
    "_pg",
    "api_gateway.adapters.providers.http_control_plane_read",
    "api_gateway.main",
    "api_gateway.models",
    "api_gateway.portal",
    "api_gateway.ports",
}
_WRAPPER_TOP_IMPORT_ALLOW = {
    "__future__",
    "importlib.util",
    "pathlib",
    "sys",
    "typing",
    "_pg",
    "b5_blk6_portal_binding_live_proof",
}
_FORBIDDEN_STATIC_IMPORTS = (
    "psycopg",
    "psycopg2",
    "asyncpg",
    "sqlalchemy",
    "jwt",
    "cryptography",
    "pytest",
    "unittest",
    "mock",
    "subprocess",
    "_gateway_doubles",
    "_db_doubles",
    "_auth_doubles",
    "smoke_c_integrated_live_proof",
    "dbr_ar_2d_standing_witnesses",
    "control_plane",
    "b5_standing_topology",
)


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _source(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _top_import_names(tree: ast.Module) -> Set[str]:
    names: Set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def _inertness_problems(tree: ast.Module) -> List[str]:
    """Top level = docstring / imports / call-free assigns / defs / classes / main guard /
    ``sys.path.insert`` only — a module-level serve, connect, or request cannot pass."""
    problems: List[str] = []
    for index, node in enumerate(tree.body):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            if index != 0:
                problems.append("bare string expression outside the module docstring")
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            if ast.unparse(node.value.func) != "sys.path.insert":
                problems.append(f"top-level call is not sys.path.insert: {ast.unparse(node.value.func)}")
            continue
        if isinstance(node, ast.If):
            if "__name__" not in ast.unparse(node.test):
                problems.append("top-level If is not the __main__ guard")
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            if value is not None:
                for inner in ast.walk(value):
                    if isinstance(inner, ast.Call) and ast.unparse(inner) not in (
                        "pathlib.Path(__file__).resolve()",
                        "pathlib.Path(__file__)",
                    ):
                        problems.append(f"module-level assignment performs work at import: {ast.unparse(inner)}")
            continue
        problems.append(f"unexpected top-level statement: {type(node).__name__}")
    return problems


def _call_name(node: ast.Call) -> Optional[str]:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _call_nodes(tree: ast.Module, name: str) -> List[ast.Call]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and _call_name(n) == name]


def _module_tuple_assign(tree: ast.Module, name: str) -> Optional[tuple]:
    """A module-level ``NAME = ( <string constants>, ... )`` assignment as a plain tuple."""
    for node in tree.body:
        targets: List[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == name for t in targets):
            continue
        value = node.value
        if isinstance(value, ast.Tuple) and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in value.elts):
            return tuple(e.value for e in value.elts)
    return None


def _function(tree: ast.Module, name: str) -> Optional[ast.FunctionDef]:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _teardown_problems(run_proof: ast.FunctionDef) -> List[str]:
    """The proof function must hold exactly one top-level try whose ``finally`` drops the
    disposable database, censuses pg_database by datname, and asserts the count is zero."""
    problems: List[str] = []
    tries = [s for s in run_proof.body if isinstance(s, ast.Try)]
    if len(tries) != 1 or not tries[0].finalbody:
        return ["run_proof must hold exactly one top-level try with a non-empty finally teardown"]
    final_src = "\n".join(ast.unparse(stmt) for stmt in tries[0].finalbody)
    if "DROP DATABASE IF EXISTS" not in final_src:
        problems.append("the finally teardown does not DROP the disposable database")
    if "pg_database" not in final_src or "datname" not in final_src:
        problems.append("the finally teardown does not census pg_database by datname")
    zero_assert = any(
        isinstance(stmt, ast.Assert)
        and any(isinstance(c, ast.Constant) and c.value == 0 for n in ast.walk(stmt.test) for c in [n] if isinstance(n, ast.Constant))
        for stmt in tries[0].finalbody
    )
    if not zero_assert:
        problems.append("the finally teardown does not assert a zero datname census")
    return problems


def _family_files(root: pathlib.Path) -> Set[str]:
    return {
        p.relative_to(root).as_posix()
        for p in root.rglob(f"*{_FAMILY_TOKEN}*")
        if p.is_file() and not (_FAMILY_SKIP_PARTS & set(p.relative_to(root).parts))
    }


# --- exact surface census ---------------------------------------------------------------------------
def test_family_census_exact() -> None:
    expected = {
        "backend/tests/control_plane/requires_pg/b5_blk6_portal_binding_live_proof.py",
        "backend/tests/control_plane/requires_pg/test_pg_b5_blk6_portal_binding_live_proof.py",
        "backend/tests/architecture/test_b5_blk6_portal_binding_live_proof_boundaries.py",
        "infrastructure/runbooks/b5_blk6_portal_binding_live_proof.md",
    }
    found = _family_files(_scan.REPO_ROOT)
    assert found == expected, f"6C-C family census drifted: extra={sorted(found - expected)} missing={sorted(expected - found)}"


# --- import inertness + import surface --------------------------------------------------------------
def test_operator_and_wrapper_are_import_inert() -> None:
    for path in (_OPS, _WRAPPER):
        problems = _inertness_problems(_tree(path))
        assert not problems, f"{path.name}: {problems}"


def test_top_import_allowlists_and_forbidden_imports() -> None:
    ops_imports = _top_import_names(_tree(_OPS))
    unexpected = ops_imports - _OPS_TOP_IMPORT_ALLOW
    assert not unexpected, f"operator top imports outside the allowlist: {sorted(unexpected)}"
    wrapper_imports = _top_import_names(_tree(_WRAPPER))
    unexpected = wrapper_imports - _WRAPPER_TOP_IMPORT_ALLOW
    assert not unexpected, f"wrapper top imports outside the allowlist: {sorted(unexpected)}"
    for path in (_OPS, _WRAPPER):
        top = _top_import_names(_tree(path))
        hits = {m for m in top for banned in _FORBIDDEN_STATIC_IMPORTS if m == banned or m.startswith(banned + ".")}
        assert not hits, f"{path.name}: forbidden static import(s): {sorted(hits)} (providers/composition must stay lazy)"


# --- real-seam-only composition ---------------------------------------------------------------------
def test_operator_real_seam_composition_census() -> None:
    tree = _tree(_OPS)
    assert len(_call_nodes(tree, "_apply_control_ddl")) == 1, "the accepted _apply_control_ddl helper must be reused exactly once"
    assert len(_call_nodes(tree, "make_server")) == 1, "the real loopback read edge must be built via make_server exactly once"
    assert len(_call_nodes(tree, "build_control_plane_read_from_env")) >= 1, "the production adapter must come from the env seam"
    gateway_calls = _call_nodes(tree, "build_gateway")
    assert gateway_calls, "the operator must compose through build_gateway"
    for call in gateway_calls:
        assert any(kw.arg == "control_read" for kw in call.keywords), "every build_gateway call must inject control_read="
    assert len(_call_nodes(tree, "PostgresControlStore")) >= 1, "the proof must construct the real PostgresControlStore"
    plane_calls = _call_nodes(tree, "ControlPlane")
    assert plane_calls and all(any(kw.arg == "store" for kw in c.keywords) for c in plane_calls), (
        "the ControlPlane must be composed by explicit store= injection"
    )
    http_server_calls = _call_nodes(tree, "HTTPServer")
    assert len(http_server_calls) <= 1, "at most ONE hand-rolled HTTPServer (the fault-injecting edge) is permitted"
    for call in http_server_calls:
        assert len(call.args) == 2 and isinstance(call.args[1], ast.Name) and call.args[1].id == "_MalformedEdgeHandler", (
            "a hand-rolled HTTPServer may serve only the fault-injecting _MalformedEdgeHandler"
        )
    assert _IN_MEMORY_STORE_NEEDLE not in _source(_OPS), "the proof may NEVER compose over the in-memory control store"


# --- DDL range 001-009 only -------------------------------------------------------------------------
def test_ddl_order_pinned_and_excluded_ddl_banned() -> None:
    declared = _module_tuple_assign(_tree(_OPS), "_EXPECTED_CONTROL_DDL_ORDER")
    assert declared == _EXPECTED_DDL_ORDER, f"operator DDL order drifted from the canonical 001-009 set: {declared}"
    assert "_CONTROL_DDL_ORDER" in _source(_OPS), "the operator must lockstep-assert the accepted helper's _CONTROL_DDL_ORDER"
    for path in (_OPS, _WRAPPER):
        text = _source(path)
        for needle in (_ROUTING_DDL_NEEDLE, _APPEND_DDL_NEEDLE, _TENANT_DDL_NEEDLE, _TENANT_DB_NEEDLE):
            assert needle not in text, f"{path.name}: excluded DDL/tenant token present: {needle!r}"


# --- mandatory finally teardown + zero-artifact census ----------------------------------------------
def test_finally_teardown_and_datname_census_pinned() -> None:
    run_proof = _function(_tree(_OPS), "run_proof")
    assert run_proof is not None, "run_proof is missing"
    problems = _teardown_problems(run_proof)
    assert not problems, problems
    assert "disposable database datname count == 0" in _source(_OPS), "the required closing census line is missing"


# --- MANUAL_ONLY registration + workflow untouched --------------------------------------------------
def test_manual_only_registered_and_workflow_untouched() -> None:
    tree = _tree(_COMPLETENESS_GUARD)
    exceptions: Dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "MANUAL_ONLY_EXCEPTIONS" for t in node.targets):
            assert isinstance(node.value, ast.Dict)
            for key, value in zip(node.value.keys, node.value.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    folded = "".join(
                        part.value for part in ast.walk(value) if isinstance(part, ast.Constant) and isinstance(part.value, str)
                    )
                    exceptions[key.value] = folded
    assert _MANUAL_ONLY_KEY in exceptions, "the 6C-C wrapper must be a registered MANUAL_ONLY exception of the completeness guard"
    assert exceptions[_MANUAL_ONLY_KEY].strip(), "the MANUAL_ONLY exception must carry a written justification"
    assert _FAMILY_TOKEN not in _WORKFLOW.read_text(encoding="utf-8"), (
        "the hosted live-pg workflow must remain untouched (no 6C-C harness enrollment)"
    )


# --- wrapper: fail-closed, census-gated, never silently skippable -----------------------------------
def test_wrapper_fail_closed_and_census_gated() -> None:
    tree = _tree(_WRAPPER)
    text = _source(_WRAPPER)
    assert _PYTEST_SKIP_NEEDLE not in text, "the wrapper may never soft-skip via pytest"
    partial_assert = any(
        isinstance(node, ast.Assert)
        and isinstance(node.test, ast.UnaryOp)
        and isinstance(node.test.op, ast.Not)
        and isinstance(node.test.operand, ast.Name)
        and node.test.operand.id == "absent"
        for node in ast.walk(tree)
    )
    assert partial_assert, "the wrapper must FAIL CLOSED on a partial configuration (assert not absent)"
    clean_skip = any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.UnaryOp)
        and isinstance(node.test.op, ast.Not)
        and isinstance(node.test.operand, ast.Name)
        and node.test.operand.id == "present"
        for node in ast.walk(tree)
    )
    assert clean_skip, "the wrapper must clean-skip ONLY when nothing is configured"
    assert "SCENARIO_LABELS" in text, "the proof-complete claim must be gated on the full scenario-label census"
    assert 'evidence["datname_count"] == 0' in text, "the wrapper must assert the zero-artifact datname census"


# --- scenario-label census --------------------------------------------------------------------------
def test_scenario_label_census_pinned() -> None:
    declared = _module_tuple_assign(_tree(_OPS), "SCENARIO_LABELS")
    assert declared == _EXPECTED_SCENARIO_LABELS, f"operator scenario census drifted: {declared}"


# --- envelope / dispatch non-claims -----------------------------------------------------------------
def test_envelope_and_dispatch_non_claim_pins() -> None:
    text = _source(_OPS)
    assert "assert rows_before == rows_after" in text, (
        "the ImportInitiation leg must ASSERT the row census UNCHANGED (envelope only — prose cannot satisfy this pin)"
    )
    assert "portal_dto is None  # dispatch semantics only" in text, (
        "the TenantOperation leg must pin the absence of a business DTO (references-only dispatch outcome)"
    )
    assert 'initiation == "accepted"' in text, "the ImportInitiation envelope must state acceptance only"


# --- secret hygiene + environment-name census -------------------------------------------------------
def test_no_secret_shaped_literals_and_env_census() -> None:
    for path in (_OPS, _WRAPPER, _RUNBOOK):
        text = _source(path)
        for needle in (_TOKEN_NEEDLE, _PEM_NEEDLE, _DSN_NEEDLE):
            assert needle not in text, f"{path.name}: secret-shaped literal present: {needle!r}"
        unknown = set(_ENV_NAME_RE.findall(text)) - _ALLOWED_ENV_NAMES
        assert not unknown, f"{path.name}: unapproved environment name(s): {sorted(unknown)}"


def test_env_writes_target_only_the_control_read_selector() -> None:
    for path in (_OPS, _WRAPPER):
        tree = _tree(path)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Subscript)
                and ast.unparse(node.targets[0].value) == "os.environ"
            ):
                key = node.targets[0].slice
                assert isinstance(key, ast.Name) and key.id == _ENV_SELECTOR_CONST, (
                    f"{path.name}: os.environ write to a non-selector key: {ast.unparse(key)}"
                )
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and ast.unparse(node.func) == "os.environ.pop":
                assert node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == _ENV_SELECTOR_CONST, (
                    f"{path.name}: os.environ.pop of a non-selector key"
                )


# --- runbook needles + non-claims -------------------------------------------------------------------
def test_runbook_required_needles_and_non_claims() -> None:
    assert _RUNBOOK.is_file(), f"runbook missing: {_RUNBOOK}"
    text = _RUNBOOK.read_text(encoding="utf-8")
    for needle in (
        "MANUAL_ONLY",
        "SNACKPORTAL_TEST_DSN",
        "001-009",
        "datname count == 0",
        "finally",
        "in-memory",
        "envelope only",
        "one page",
        "B5-BLK-6 remains OPEN",
        "NOT READY / DO-NOT-ACTIVATE",
    ):
        assert needle in text, f"runbook is missing the required needle: {needle!r}"
    for needle in (_CLOSED_CLAIM_NEEDLE, _MVP_DONE_NEEDLE, _CUTOVER_CLAIM_NEEDLE, _PAGINATION_CLAIM_NEEDLE):
        assert needle not in text, f"runbook carries a forbidden overclaim: {needle!r}"


# --- non-vacuity companions (planted mutants judged through the SAME helpers) -----------------------
def test_nv_teardown_pin_detects_a_dropless_finally() -> None:
    planted = ast.parse("def run_proof(admin_dsn):\n    try:\n        pass\n    finally:\n        print('no drop, no census')\n")
    fn = planted.body[0]
    assert isinstance(fn, ast.FunctionDef)
    assert _teardown_problems(fn), "a finally without DROP + datname census + zero assert MUST be rejected"


def test_nv_ddl_pin_detects_a_widened_order() -> None:
    widened = ast.parse(f"_EXPECTED_CONTROL_DDL_ORDER = {(_EXPECTED_DDL_ORDER + (_ROUTING_DDL_NEEDLE + '.sql',))!r}")
    declared = _module_tuple_assign(widened, "_EXPECTED_CONTROL_DDL_ORDER")
    assert declared != _EXPECTED_DDL_ORDER, "a widened DDL order (010 appended) MUST fail the equality pin"


def test_nv_seam_pin_detects_a_missing_control_read_keyword() -> None:
    planted = ast.parse("gateway = build_gateway(authenticator=a, router=r, audit=x)")
    calls = [n for n in ast.walk(planted) if isinstance(n, ast.Call) and _call_name(n) == "build_gateway"]
    assert calls and not any(kw.arg == "control_read" for kw in calls[0].keywords), (
        "a build_gateway call without control_read= MUST be detectable by the keyword census"
    )


if __name__ == "__main__":
    _scan.run(
        [
            test_family_census_exact,
            test_operator_and_wrapper_are_import_inert,
            test_top_import_allowlists_and_forbidden_imports,
            test_operator_real_seam_composition_census,
            test_ddl_order_pinned_and_excluded_ddl_banned,
            test_finally_teardown_and_datname_census_pinned,
            test_manual_only_registered_and_workflow_untouched,
            test_wrapper_fail_closed_and_census_gated,
            test_scenario_label_census_pinned,
            test_envelope_and_dispatch_non_claim_pins,
            test_no_secret_shaped_literals_and_env_census,
            test_env_writes_target_only_the_control_read_selector,
            test_runbook_required_needles_and_non_claims,
            test_nv_teardown_pin_detects_a_dropless_finally,
            test_nv_ddl_pin_detects_a_widened_order,
            test_nv_seam_pin_detects_a_missing_control_read_keyword,
        ]
    )
