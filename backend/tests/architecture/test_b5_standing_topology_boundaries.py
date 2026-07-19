"""PRD B5-4 — standing-topology operator-harness boundary pins (default suite; no DB).

Non-vacuously pins the safety boundaries of the B5-4 operator tool
(``tests/control_plane/requires_pg/b5_standing_topology.py``) without touching a database:

* import-inert module structure (top-level = docstring/imports/constants/defs/main-guard only);
  module-level imports are STDLIB-ONLY (every backend/provider import is lazy, inside commands);
* no static database-driver import anywhere in the B5-4 files (importlib idiom — the repo-wide
  vendor/DB containment census also covers this; here it is pinned locally and non-vacuously);
* no threading / subprocess / socket / http / serve_forever / ThreadingHTTPServer anywhere
  (AT-D15T1-10 adjacency: an ops harness must never become a service);
* no embedded CREATE/ALTER/DROP DDL literal in the ops module — control DDL is READ from the
  canonical ``infrastructure/db/control`` assets (exact 001-009 inventory pinned against disk),
  and the ONLY database-drop call site is the existing identifier-guarded
  ``PostgresProvisioningOperator.deprovision`` inside ``cmd_teardown`` (bounded, recomputed
  targets — never a wildcard, list, or caller-supplied name);
* teardown refuses WITHOUT ``--confirm-b5-teardown`` — structurally (the confirmation check is
  the function's FIRST effect) and behaviorally (``main(["teardown"])`` exits non-zero with the
  refusal, importing nothing first-party and touching nothing);
* the tenant-secret root must be ABSOLUTE and OUTSIDE the repository (behavioral refusals);
* the redaction helper never emits userinfo/query material (behavioral);
* no production module imports the ops harness; the fixed deterministic tenant identities are
  pinned; no B5-5/RS256/JWK or Smoke C content appears in any B5-4 file;
* the disposable requires_pg proof is registered as a justified MANUAL_ONLY exception of the
  live-PG run-set completeness guard (enrollment in the workflow loop is a .github edit — out of
  B5-4 scope; tracked follow-up);
* PM-R2-1 STRUCTURAL regression pins (fix round 2, AST-only — comments/docstrings/strings cannot
  satisfy them): BOTH cleanup loops in ``cmd_teardown`` must begin with the fail-closed
  ``cleanup_eligible.get(<tenant>, False)`` gate ending in ``continue`` (loop identification by
  action call, exactly one deprovision + one unlink loop), and the disposable proof's pre-flight
  ownership-refusal inventory ITSELF must carry the ``_RENAME_SCRATCH`` Name (with the same
  constant pinned as the rename-leg and finally-cleanup identity) — each with planted-mutation
  non-vacuity companions sharing the exact same predicates.

Pure stdlib; standalone-runnable:
  python tests/architecture/test_b5_standing_topology_boundaries.py

B5-BLK-4 remains OPEN; the Physical Multi-Database MVP remains mandatory and is NOT completed by
this guard or the harness it pins.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys
from typing import Dict, List, Optional, Set

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_OPS = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "b5_standing_topology.py"
_PROOF = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "test_pg_b5_standing_topology.py"
_RUNBOOK = _scan.REPO_ROOT / "infrastructure" / "runbooks" / "b5_standing_topology.md"
_COMPLETENESS_GUARD = _scan.BACKEND_ROOT / "tests" / "architecture" / "test_live_pg_workflow_runset_completeness.py"
_CONTROL_DDL_DIR = _scan.REPO_ROOT / "infrastructure" / "db" / "control"
_TESTS_DIR = _scan.BACKEND_ROOT / "tests"

_B5_4_FILES = (_OPS, _PROOF)

# Module-scope import allow-set for the ops module (stdlib only; backend/provider imports are lazy).
_OPS_TOP_IMPORT_ALLOW = {"__future__", "argparse", "importlib", "os", "pathlib", "sys", "typing", "urllib.parse"}

_FORBIDDEN_IMPORTS = ("psycopg", "psycopg2", "asyncpg", "sqlalchemy", "jwt", "cryptography", "threading", "subprocess", "socket", "http")
_FORBIDDEN_NAMES = ("serve_forever", "ThreadingHTTPServer", "ThreadingMixIn")

_DDL_LITERAL_RE = re.compile(r"(?i)\b(create|alter|drop)\s+(table|index|trigger|function|role|database|schema)\b")

_EXPECTED_TENANTS = ("b5_standing_alpha", "b5_standing_beta")
_EXPECTED_DDL = (
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
# Created-not-applied Control DDL. Present on disk beside the canonical apply set, but deliberately
# NOT enrolled in the standing-topology apply order — applying each is a separately governed later
# phase, and the ops module (schema-application code) is unchanged:
#   010/011 routing-audit (DBR-AR-2B; exercised by the DBR-AR-2D disposable live proof);
#   012/013 Gateway operational-audit (Gateway Audit V1a; control_gateway_audit + its append-only
#   trigger, exercised only by the MANUAL_ONLY disposable proof test_pg_gateway_audit_durable.py);
#   014/015 Import operational-audit (W1a; control_import_audit + its append-only trigger, exercised
#   only by the MANUAL_ONLY disposable proof test_pg_import_copy_durable.py).
_EXPECTED_UNENROLLED_DDL = (
    "010_routing_audit.sql",
    "011_routing_audit_append_only.sql",
    "012_gateway_operational_audit.sql",
    "013_gateway_operational_audit_append_only.sql",
    "014_import_operational_audit.sql",
    "015_import_operational_audit_append_only.sql",
)


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _load_ops_module():  # noqa: ANN202  (test helper)
    """Load the ops module by path (behavioral probes). Loading itself proves import-inertness:
    no configuration, database, or network is present in the default suite."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("b5_standing_topology_under_pin", _OPS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _string_constants(tree: ast.AST) -> List[str]:
    return [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def test_files_exist() -> None:
    for path in (_OPS, _PROOF, _RUNBOOK):
        assert path.is_file(), f"B5-4 surface file missing: {path}"


def test_ops_module_is_import_inert_and_stdlib_only_at_top() -> None:
    tree = _tree(_OPS)
    imported: Set[str] = set()
    for index, node in enumerate(tree.body):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            assert index == 0, "only the module docstring may be a bare expression"
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif node.module and node.level == 0:
                imported.add(node.module)
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.FunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = ast.unparse(node.value.func)
            assert call == "sys.path.insert", f"the only top-level call allowed is sys.path.insert (found {call})"
            continue
        if isinstance(node, ast.If):
            test_src = ast.unparse(node.test)
            assert "__name__" in test_src, f"top-level If must be the __main__ guard (found: {test_src})"
            continue
        raise AssertionError(f"import-inertness violated: unexpected top-level statement {ast.dump(node)[:120]}")
    unexpected = {m for m in imported if m.split(".")[0] not in {a.split(".")[0] for a in _OPS_TOP_IMPORT_ALLOW}}
    assert not unexpected, f"ops module top-level imports must be stdlib-only (lazy backend imports): {sorted(unexpected)}"


def test_no_forbidden_imports_or_names_anywhere() -> None:
    for path in _B5_4_FILES:
        tree = _tree(path)
        rp = _scan.relposix(path)
        for node in ast.walk(tree):
            mods: List[str] = []
            if isinstance(node, ast.Import):
                mods = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                mods = [node.module]
            for mod in mods:
                top = mod.split(".")[0]
                assert top not in _FORBIDDEN_IMPORTS, f"forbidden import '{mod}' in {rp} (driver/threading/subprocess/socket/http banned)"
        source = path.read_text(encoding="utf-8")
        for name in _FORBIDDEN_NAMES:
            assert name not in source, f"forbidden name '{name}' in {rp}"


def test_no_embedded_ddl_literals_in_ops_module() -> None:
    # Control DDL is READ from canonical assets; teardown drops via the existing guarded operator
    # adapter — so the ops module may contain NO DDL-shaped string literal at all.
    offenders = [s for s in _string_constants(_tree(_OPS)) if _DDL_LITERAL_RE.search(s)]
    assert not offenders, f"embedded DDL literal(s) in the ops module (DDL must come from canonical assets): {offenders}"
    # Non-vacuity: the detector sees a planted sample.
    assert _DDL_LITERAL_RE.search("CREATE TABLE x (y int)"), "DDL-literal detector went vacuous"
    assert _DDL_LITERAL_RE.search("drop database evil"), "DDL-literal detector went vacuous (drop leg)"
    assert not _DDL_LITERAL_RE.search("SELECT 1 FROM pg_database WHERE datname = %s"), "read-only queries must not match"


def test_ddl_loaded_only_from_canonical_assets() -> None:
    module = _load_ops_module()
    assert tuple(module._CONTROL_DDL_ORDER) == _EXPECTED_DDL, "the ops module must apply EXACTLY the canonical 001-009 set in order"
    on_disk = sorted(p.name for p in _CONTROL_DDL_DIR.glob("*.sql"))
    assert on_disk == sorted(_EXPECTED_DDL + _EXPECTED_UNENROLLED_DDL), f"canonical control DDL inventory drifted: {on_disk}"
    assert module._CONTROL_DDL_DIR == _CONTROL_DDL_DIR, "the ops module must read the canonical infrastructure/db/control directory"


def test_routing_audit_ddl_not_enrolled_for_application() -> None:
    # DBR-AR-2B: the routing-audit DDL is created-not-applied — it must be present on disk
    # (inventory above) and must NOT be enrolled in the standing-topology apply order; the
    # ops module's schema-application surface is unchanged (PRD DBR-AR-2B §7.4).
    module = _load_ops_module()
    for name in _EXPECTED_UNENROLLED_DDL:
        assert name in (p.name for p in _CONTROL_DDL_DIR.glob("*.sql")), f"{name} missing from the control DDL inventory"
        assert name not in module._CONTROL_DDL_ORDER, (
            f"{name} is created-not-applied (DBR-AR-2B) and must NOT be enrolled in the standing-topology apply order"
        )
    # Non-vacuity: the detector notices a planted enrollment and a planted de-enrollment.
    planted_order = _EXPECTED_DDL + ("010_routing_audit.sql",)
    assert any(name in planted_order for name in _EXPECTED_UNENROLLED_DDL), "not-enrolled detector went vacuous (planted enrollment)"
    assert all(name not in _EXPECTED_DDL for name in _EXPECTED_UNENROLLED_DDL), "apply-order pin must exclude the 2B DDL"


def test_fixed_deterministic_identities_and_bounded_teardown() -> None:
    module = _load_ops_module()
    assert tuple(module.TENANT_IDS) == _EXPECTED_TENANTS, "the deterministic B5-4 tenant ids are pinned"
    tree = _tree(_OPS)
    teardown = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "cmd_teardown")
    # Structural confirm-first: the first statement is the confirmation refusal.
    first = teardown.body[0]
    assert isinstance(first, ast.If) and "confirm" in ast.unparse(first.test), "cmd_teardown must check the confirmation flag FIRST"
    teardown_src = ast.get_source_segment(_OPS.read_text(encoding="utf-8"), teardown) or ""
    for banned in ("pg_database", "list_candidate_databases", "scan_for_orphans", "DROP DATABASE"):
        assert banned not in teardown_src, f"teardown must be bounded (no inventory/wildcard/raw-drop): found {banned!r}"

    # The ONLY drop call site is the guarded operator adapter, inside cmd_teardown, target-recomputed.
    def _deprovision_calls(root: ast.AST) -> List[ast.Call]:
        return [n for n in ast.walk(root) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "deprovision"]

    assert len(_deprovision_calls(tree)) == 1, "exactly ONE deprovision call site is allowed (inside cmd_teardown)"
    assert len(_deprovision_calls(teardown)) == 1, "the deprovision call site must live inside cmd_teardown"
    assert "operator.deprovision(target=target)" in teardown_src and "_tenant_target(tid)" in teardown_src, (
        "teardown targets must be recomputed from the fixed tenant ids, never caller-supplied"
    )
    # PM-B54-1 regression protection is STRUCTURAL (fix round 2): see
    # test_cleanup_loops_share_failclosed_eligibility_gate + its planted-mutation companions.


def test_teardown_refuses_without_confirmation_behaviorally() -> None:
    import contextlib
    import io

    module = _load_ops_module()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = module.main(["teardown"])  # the refusal is checked BEFORE any config read or import
    out = buf.getvalue()
    assert code != 0, "teardown without --confirm-b5-teardown must exit non-zero"
    assert "REFUSED" in out and "--confirm-b5-teardown" in out, f"refusal message must name the flag: {out!r}"


def test_secret_root_containment_refusals_behaviorally() -> None:
    import os
    import tempfile

    module = _load_ops_module()
    key = module._SECRET_DIR_ENV
    saved = os.environ.get(key)
    try:
        for bad in ("relative/dir", str(_scan.REPO_ROOT / "infrastructure")):
            os.environ[key] = bad
            refused = False
            try:
                module._validated_secret_dir()
            except module.OpsConfigError:
                refused = True
            assert refused, f"secret root {bad!r} must be refused (absolute + outside repo required)"
        with tempfile.TemporaryDirectory() as ok_dir:
            os.environ[key] = ok_dir
            resolved = module._validated_secret_dir()
            assert resolved.is_absolute(), "a valid outside-repo secret root must resolve"
    finally:
        if saved is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = saved


def test_redaction_never_emits_credentials() -> None:
    module = _load_ops_module()
    redacted = module._redacted("postgresql://alice:hunter2@db.example:5432/mydb?password=leakme&sslmode=disable")
    assert "db.example" in redacted and "5432" in redacted and "/mydb" in redacted
    for secret in ("alice", "hunter2", "leakme", "@", "password"):
        assert secret not in redacted, f"redaction leaked {secret!r}: {redacted}"


def test_no_production_import_of_ops_module() -> None:
    offenders: List[str] = []
    for path in _scan.py_files():
        if _TESTS_DIR in path.parents:
            continue
        if "b5_standing_topology" in _scan.imported_modules(path):
            offenders.append(_scan.relposix(path))
    assert not offenders, f"production code must never import the B5-4 ops harness: {offenders}"
    # Non-vacuity: the census detects a synthetic import.
    synthetic = ast.parse("import b5_standing_topology\n")
    names = [a.name for n in ast.walk(synthetic) if isinstance(n, ast.Import) for a in n.names]
    assert "b5_standing_topology" in names, "import census went vacuous"


def test_no_b5_5_or_smoke_c_content() -> None:
    needles = ("RS" + "256", "J" + "WK", "Smoke" + "-C-SPEC")  # built dynamically so THIS guard never self-matches
    for path in (_OPS, _PROOF, _RUNBOOK):
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            assert needle not in text, f"B5-5/Smoke-C content {needle!r} must not appear in {path.name} (out of B5-4 scope)"


# ------------------------------------------------------------------------------------------------
# PM-R2-1 structural predicates (fix round 2) — shared by the real pins AND the planted-mutation
# non-vacuity companions below. Pure AST: comments, docstrings, and string literals cannot satisfy
# any leg; a missing function/loop/gate fails closed with a deterministic diagnostic.
# ------------------------------------------------------------------------------------------------
_CLEANUP_ACTIONS = ("deprovision", "unlink")


def _find_cleanup_loops(teardown: ast.FunctionDef) -> Dict[str, ast.For]:
    """The two tenant cleanup loops in ``cmd_teardown``, identified by their ACTION call.

    Fail-closed: exactly ONE loop performing ``.deprovision(`` and exactly ONE performing
    ``.unlink(`` must exist — 0 or >1 of either fails loud (a renamed, deleted, or duplicated
    cleanup loop can never pass silently)."""
    found: Dict[str, List[ast.For]] = {action: [] for action in _CLEANUP_ACTIONS}
    for node in ast.walk(teardown):
        if isinstance(node, ast.For):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute) and inner.func.attr in _CLEANUP_ACTIONS:
                    found[inner.func.attr].append(node)
                    break
    result: Dict[str, ast.For] = {}
    for action, loops in found.items():
        assert len(loops) == 1, f"cmd_teardown must contain exactly ONE {action} cleanup loop (found {len(loops)})"
        result[action] = loops[0]
    return result


def _cleanup_gate_problem(loop: ast.For) -> Optional[str]:
    """None iff the loop has the canonical fail-closed eligibility gate as its FIRST statement:

    for tid in TENANT_IDS:
        if not cleanup_eligible.get(tid, False):
            ...
            continue
        <cleanup action only after the gate>
    """
    if not (isinstance(loop.iter, ast.Name) and loop.iter.id == "TENANT_IDS"):
        return "does not iterate the deterministic TENANT_IDS collection"
    if not loop.body or not isinstance(loop.body[0], ast.If):
        return "first statement is not the eligibility gate"
    gate = loop.body[0]
    test = gate.test
    if not (isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not) and isinstance(test.operand, ast.Call)):
        return "gate is not an `if not cleanup_eligible.get(...)` refusal"
    call = test.operand
    if not (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "get"
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "cleanup_eligible"
    ):
        return "gate does not consult cleanup_eligible.get"
    if len(call.args) != 2 or call.keywords:
        return "gate lookup must be cleanup_eligible.get(<tenant>, False)"
    tenant_arg, default_arg = call.args
    if not (isinstance(tenant_arg, ast.Name) and isinstance(loop.target, ast.Name) and tenant_arg.id == loop.target.id):
        return "gate does not test the loop's tenant variable"
    if not (isinstance(default_arg, ast.Constant) and default_arg.value is False):
        return "gate default is not the fail-closed constant False"
    if not gate.body or not isinstance(gate.body[-1], ast.Continue):
        return "ineligible branch does not end in continue"
    for inner in ast.walk(gate):
        if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute) and inner.func.attr in _CLEANUP_ACTIONS:
            return "cleanup action reachable inside the gate"
    return None


def _preflight_inventory(proof_fn: ast.FunctionDef) -> ast.Tuple:
    """The pre-flight ownership-refusal inventory: the For-over-Tuple whose body asserts
    ``not _db_exists(...)``. Fail-closed if absent."""
    for node in ast.walk(proof_fn):
        if isinstance(node, ast.For) and isinstance(node.iter, ast.Tuple) and node.body and isinstance(node.body[0], ast.Assert):
            test = node.body[0].test
            if (
                isinstance(test, ast.UnaryOp)
                and isinstance(test.op, ast.Not)
                and isinstance(test.operand, ast.Call)
                and isinstance(test.operand.func, ast.Name)
                and test.operand.func.id == "_db_exists"
            ):
                return node.iter
    raise AssertionError("pre-flight ownership-refusal inventory not found (fail closed)")


def _preflight_names(proof_fn: ast.FunctionDef) -> Set[str]:
    return {e.id for e in _preflight_inventory(proof_fn).elts if isinstance(e, ast.Name)}


def _proof_main_fn(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "test_b5_standing_topology_ops":
            return node
    raise AssertionError("test_b5_standing_topology_ops not found in the proof module (fail closed)")


def test_cleanup_loops_share_failclosed_eligibility_gate() -> None:
    # PM-B54-1 STRUCTURAL pin (PM-R2-1): both cleanup loops in cmd_teardown must begin with the
    # canonical fail-closed cleanup_eligible gate — a refused tenant can never be reached by the
    # database-drop or secret-removal steps. AST-only: comments cannot satisfy this.
    tree = _tree(_OPS)
    teardown = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "cmd_teardown")
    loops = _find_cleanup_loops(teardown)
    for kind in sorted(loops):
        problem = _cleanup_gate_problem(loops[kind])
        assert problem is None, f"cmd_teardown {kind} cleanup loop: {problem}"


_SAMPLE_CANONICAL_TEARDOWN = """
def cmd_teardown(args):
    for tid in TENANT_IDS:
        if not cleanup_eligible.get(tid, False):
            print("skipped")
            continue
        operator.deprovision(target=target)
    for tid in TENANT_IDS:
        if not cleanup_eligible.get(tid, False):
            continue
        path.unlink(missing_ok=True)
"""

_PIN_A_MUTANTS = {
    "db loop without gate": """
def cmd_teardown(args):
    for tid in TENANT_IDS:
        operator.deprovision(target=target)
    for tid in TENANT_IDS:
        if not cleanup_eligible.get(tid, False):
            continue
        path.unlink(missing_ok=True)
""",
    "secret loop without gate": """
def cmd_teardown(args):
    for tid in TENANT_IDS:
        if not cleanup_eligible.get(tid, False):
            continue
        operator.deprovision(target=target)
    for tid in TENANT_IDS:
        path.unlink(missing_ok=True)
""",
    "gate after the cleanup action": """
def cmd_teardown(args):
    for tid in TENANT_IDS:
        operator.deprovision(target=target)
        if not cleanup_eligible.get(tid, False):
            continue
    for tid in TENANT_IDS:
        if not cleanup_eligible.get(tid, False):
            continue
        path.unlink(missing_ok=True)
""",
    "fail-open default True": """
def cmd_teardown(args):
    for tid in TENANT_IDS:
        if not cleanup_eligible.get(tid, True):
            continue
        operator.deprovision(target=target)
    for tid in TENANT_IDS:
        if not cleanup_eligible.get(tid, False):
            continue
        path.unlink(missing_ok=True)
""",
    "gate without continue": """
def cmd_teardown(args):
    for tid in TENANT_IDS:
        if not cleanup_eligible.get(tid, False):
            print("skipped")
        operator.deprovision(target=target)
    for tid in TENANT_IDS:
        if not cleanup_eligible.get(tid, False):
            continue
        path.unlink(missing_ok=True)
""",
    "gate on a different mapping": """
def cmd_teardown(args):
    for tid in TENANT_IDS:
        if not other_mapping.get(tid, False):
            continue
        operator.deprovision(target=target)
    for tid in TENANT_IDS:
        if not cleanup_eligible.get(tid, False):
            continue
        path.unlink(missing_ok=True)
""",
    "gate on a different tenant variable": """
def cmd_teardown(args):
    for tid in TENANT_IDS:
        if not cleanup_eligible.get(other, False):
            continue
        operator.deprovision(target=target)
    for tid in TENANT_IDS:
        if not cleanup_eligible.get(tid, False):
            continue
        path.unlink(missing_ok=True)
""",
}


def test_cleanup_gate_pin_non_vacuity() -> None:
    # The SAME predicates that guard the real module must accept the canonical shape and reject
    # every planted regression mutant (incl. the exact PM-B54-1 reintroductions).
    def gate_problems(source: str) -> List[Optional[str]]:
        fn = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef))
        loops = _find_cleanup_loops(fn)
        return [_cleanup_gate_problem(loops[kind]) for kind in sorted(loops)]

    assert gate_problems(_SAMPLE_CANONICAL_TEARDOWN) == [None, None], "the canonical repaired shape must PASS"
    for label, sample in _PIN_A_MUTANTS.items():
        assert any(problem is not None for problem in gate_problems(sample)), f"pin A must reject mutant: {label}"


def test_preflight_inventory_complete() -> None:
    # PM-B54-2 STRUCTURAL pin (PM-R2-1): the pre-flight ownership-refusal inventory itself — not
    # the module at large — must carry a Name reference to _RENAME_SCRATCH, and the same constant
    # must remain the rename-leg identity and the bounded finally-cleanup identity.
    proof_fn = _proof_main_fn(_tree(_PROOF))
    names = _preflight_names(proof_fn)
    assert "_RENAME_SCRATCH" in names, "pre-flight refusal inventory must include the rename-scratch constant (PM-B54-2)"
    assert {"_SENTINEL_DB", "_CTL_DB"} <= names, "pre-flight inventory must keep the sentinel + scratch Control DB names"
    renames = [
        node
        for node in ast.walk(proof_fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_admin_exec"
        and any(
            isinstance(value, ast.FormattedValue) and isinstance(value.value, ast.Name) and value.value.id == "_RENAME_SCRATCH"
            for arg in node.args
            if isinstance(arg, ast.JoinedStr)
            for value in arg.values
        )
    ]
    assert len(renames) >= 2, "the missing-DB leg must rename away AND back using the rename-scratch constant"
    finally_drops: List[str] = []
    for node in ast.walk(proof_fn):
        if isinstance(node, ast.Try) and node.finalbody:
            for stmt in node.finalbody:
                for inner in ast.walk(stmt):
                    if (
                        isinstance(inner, ast.Call)
                        and isinstance(inner.func, ast.Name)
                        and inner.func.id == "_drop_db"
                        and len(inner.args) == 3
                        and isinstance(inner.args[2], ast.Name)
                    ):
                        finally_drops.append(inner.args[2].id)
    assert "_RENAME_SCRATCH" in finally_drops, "the finally cleanup must cover the rename-scratch constant"
    src = _PROOF.read_text(encoding="utf-8")
    assert '_RENAME_SCRATCH = "sp2_b54_hidden"' in src, "the rename-scratch name must be a single named constant"
    assert src.count('"sp2_b54_hidden"') == 1, "the raw scratch name must appear ONLY in the constant definition"


_SAMPLE_CANONICAL_PREFLIGHT = """
def test_b5_standing_topology_ops(admin_dsn):
    for name in (*targets.values(), _RENAME_SCRATCH, _SENTINEL_DB, _CTL_DB):
        assert not _db_exists(psycopg, admin_dsn, name)
"""

_PIN_B_MUTANTS = {
    "inventory missing _RENAME_SCRATCH": """
def test_b5_standing_topology_ops(admin_dsn):
    for name in (*targets.values(), _SENTINEL_DB, _CTL_DB):
        assert not _db_exists(psycopg, admin_dsn, name)
""",
    "constant only in the finally": """
def test_b5_standing_topology_ops(admin_dsn):
    for name in (*targets.values(), _SENTINEL_DB, _CTL_DB):
        assert not _db_exists(psycopg, admin_dsn, name)
    try:
        pass
    finally:
        _drop_db(psycopg, admin_dsn, _RENAME_SCRATCH)
""",
    "constant only in the rename leg": """
def test_b5_standing_topology_ops(admin_dsn):
    for name in (*targets.values(), _SENTINEL_DB, _CTL_DB):
        assert not _db_exists(psycopg, admin_dsn, name)
    _admin_exec(psycopg, admin_dsn, f'ALTER DATABASE "x" RENAME TO "{_RENAME_SCRATCH}"')
""",
    "raw string in the tuple instead of the Name": """
def test_b5_standing_topology_ops(admin_dsn):
    for name in (*targets.values(), "sp2_b54_hidden", _SENTINEL_DB, _CTL_DB):
        assert not _db_exists(psycopg, admin_dsn, name)
""",
}


def test_preflight_pin_non_vacuity() -> None:
    # The SAME inventory predicate must accept the canonical pre-flight and reject every planted
    # mutant — including the EXACT original PM-B54-2 defect (constant present elsewhere but absent
    # from the refusal inventory) and a same-value raw string smuggled into the tuple.
    canonical = _proof_main_fn(ast.parse(_SAMPLE_CANONICAL_PREFLIGHT))
    assert "_RENAME_SCRATCH" in _preflight_names(canonical), "the canonical pre-flight must PASS"
    for label, sample in _PIN_B_MUTANTS.items():
        names = _preflight_names(_proof_main_fn(ast.parse(sample)))
        assert "_RENAME_SCRATCH" not in names, f"pin B must reject mutant: {label}"


def test_manual_only_exception_registered_with_justification() -> None:
    # The disposable proof is consciously OUT of the advisory live-PG loop this slice (workflow
    # edits are out of B5-4 scope); the completeness guard must carry the justified exception.
    text = _COMPLETENESS_GUARD.read_text(encoding="utf-8")
    key = "tests/control_plane/requires_pg/test_pg_b5_standing_topology.py"
    assert key in text, "the B5-4 harness must be a registered MANUAL_ONLY exception of the run-set completeness guard"
    tree = _tree(_COMPLETENESS_GUARD)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "MANUAL_ONLY_EXCEPTIONS" for t in node.targets):
            mapping = ast.literal_eval(node.value)
            assert key in mapping and str(mapping[key]).strip(), "the B5-4 exception must carry a written justification"
            return
    raise AssertionError("MANUAL_ONLY_EXCEPTIONS not found in the completeness guard")


if __name__ == "__main__":
    _scan.run(
        [
            test_files_exist,
            test_ops_module_is_import_inert_and_stdlib_only_at_top,
            test_no_forbidden_imports_or_names_anywhere,
            test_no_embedded_ddl_literals_in_ops_module,
            test_ddl_loaded_only_from_canonical_assets,
            test_routing_audit_ddl_not_enrolled_for_application,
            test_fixed_deterministic_identities_and_bounded_teardown,
            test_teardown_refuses_without_confirmation_behaviorally,
            test_secret_root_containment_refusals_behaviorally,
            test_redaction_never_emits_credentials,
            test_no_production_import_of_ops_module,
            test_no_b5_5_or_smoke_c_content,
            test_cleanup_loops_share_failclosed_eligibility_gate,
            test_cleanup_gate_pin_non_vacuity,
            test_preflight_inventory_complete,
            test_preflight_pin_non_vacuity,
            test_manual_only_exception_registered_with_justification,
        ]
    )
