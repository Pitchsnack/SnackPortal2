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
  B5-4 scope; tracked follow-up).

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
from typing import List, Set

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
    assert on_disk == sorted(_EXPECTED_DDL), f"canonical control DDL inventory drifted: {on_disk}"
    assert module._CONTROL_DDL_DIR == _CONTROL_DDL_DIR, "the ops module must read the canonical infrastructure/db/control directory"


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
    # PM-B54-1 pin (fix round 1): ONE shared per-tenant eligibility structure gates the
    # reconciliation AND both cleanup loops — a refused tenant is skipped with resources preserved.
    assert teardown_src.count("cleanup_eligible") >= 4, (
        "teardown must share ONE per-tenant eligibility structure across reconciliation, database "
        "drop, and secret removal (a refused tenant must be excluded from ALL later cleanup)"
    )
    assert "SKIPPED" in teardown_src and "PRESERVED" in teardown_src, (
        "refused tenants must be reported as skipped with their resources preserved"
    )


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


def test_preflight_inventory_complete() -> None:
    # PM-B54-2 pin (fix round 1): the disposable proof's pre-flight refusal inventory includes
    # EVERY database name its finally block may drop — including the rename-scratch name, held as
    # a single named constant so pre-flight, the rename leg, and the finally can never diverge.
    src = _PROOF.read_text(encoding="utf-8")
    assert '_RENAME_SCRATCH = "sp2_b54_hidden"' in src, "the rename-scratch name must be a single named constant"
    assert src.count("_RENAME_SCRATCH") >= 5, (
        "the rename-scratch constant must be used in the pre-flight inventory, the rename leg, "
        "the finally cleanup, and the PM-B54-2 refusal proof"
    )
    assert src.count('"sp2_b54_hidden"') == 1, "the raw scratch name must appear ONLY in the constant definition"


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
            test_fixed_deterministic_identities_and_bounded_teardown,
            test_teardown_refuses_without_confirmation_behaviorally,
            test_secret_root_containment_refusals_behaviorally,
            test_redaction_never_emits_credentials,
            test_no_production_import_of_ops_module,
            test_no_b5_5_or_smoke_c_content,
            test_preflight_inventory_complete,
            test_manual_only_exception_registered_with_justification,
        ]
    )
