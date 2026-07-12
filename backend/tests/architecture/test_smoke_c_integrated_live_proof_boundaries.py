"""PRD Smoke C V2 — integrated-live-proof boundary pins (default suite; no DB, no network).

Non-vacuously pins the safety boundaries of the Smoke C V2 operator
(``tests/control_plane/requires_pg/smoke_c_integrated_live_proof.py``), its live proof, and its runbook
without touching a database or opening a socket:

* exact surface census: the Smoke C V2 file family is exactly the operator + live proof + this guard +
  the runbook — no second executable, no production file;
* import-inert module structure for BOTH new python files with a STDLIB-ONLY top import surface (every
  backend/provider import is lazy, inside commands); no static database-driver / JWT / crypto vendor
  import; no import of the B5-4/B5-4A operators (status-only subprocess); no import of any test double
  (``_db_doubles`` / ``_auth_doubles`` / ``_gateway_doubles``) or mocking library; no static import of the
  crypto fixture (loaded lazily by file location); the proof imports no ``subprocess`` at all;
* REAL production composition seams only: the operator calls EXACTLY ``build_read_server_from_env``,
  ``build_authenticate_server_from_env``, ``build_dispatch_server_from_env``, ``build_gateway``,
  ``build_authenticator_from_env``, and ``build_router_dispatch_from_env`` (once each) and drives ONE
  ``Gateway.handle`` call site; hand-rolled composition (``build_router`` / ``build_authenticator`` /
  ``build_dispatch_server`` / ``build_authenticate_server`` / ``make_server`` / ``HTTPServer``) and wire
  bypasses (direct ``route`` / ``authenticate`` / ``dispatch`` calls) are banned;
* command surface EXACTLY ``plan`` / ``run`` / ``status`` (``add_parser`` census); no removal token and no
  confirmation-flag surface anywhere in the python files;
* the ONLY subprocess sites are the two status-only standing-operator delegations plus the read-only
  ``git rev-parse HEAD`` commit witness — each argv AST-bound to its pinned builder; inline argv and any
  non-status standing-operator token are rejected;
* read-only SQL only: every cursor-sink argument must statically resolve to one of the pinned SELECT
  statements; the full sink surface (``execute(many/script)`` + the psycopg2/psycopg3 copy family) is
  censused; no string constant carries a mutating-SQL keyword (case-insensitive, word-boundary, with
  ``ast.BinOp(Add)`` folding so split verbs are caught);
* zero write reachability: every supported-write / lifecycle / provisioning / recovery / file-write API
  and every raw-connection transaction primitive is banned in both files; environment writes exist ONLY
  inside the ``_EnvPatch`` save/restore seam, may touch ONLY the pinned existing key census, never set a
  ``*_PORT`` key, and never carry a non-loopback host;
* the binding scenario matrix is pinned EXACTLY (nine rows: two success rows routed to the two distinct
  standing databases; dormant -> ``tenant_not_ready``; unknown -> ``tenant_access_denied``; carrier /
  signature / kid / issuer / unavailability rows with their exact envelopes) — and the operator's pure
  evaluators must REJECT every state-shaped mutation of the PRD matrix (fake evidence, swapped routes,
  denial dispatch/pool acquisition, skipped scenarios, leftover listeners, unrestored environment,
  before != after);
* structural run pins: bounded readiness (``READINESS_TIMEOUT_SECONDS``), ``finally`` shutdown +
  environment restoration, and an AST-pinned zero-mutation verdict (Fix R3 — a source substring can
  never satisfy it): ``before``/``after`` each bound exactly once from ``_snapshot_state()`` and exactly
  one top-level ``evidence["before_equals_after"] = before == after`` — a direct single-``ast.Eq``
  ``ast.Compare`` over exactly those two names in capture -> try/finally -> capture -> verdict order;
  forged constants, ``is``/``!=``/chains, self- or wrong-name comparisons, ``bool()``/helper wrappers,
  value aliases, dead branches, duplicate assignments, and side-channel writes of the verdict —
  keyword, ``**{…}`` splat, computed/folded keys on ``Assign``/``AnnAssign``/``AugAssign``, evidence
  aliasing, mutator-method or delete — as well as comparison text living only in strings/f-strings all
  fail; the two snapshots may not be tampered with after capture (no ``clear``/``update``/``pop`` or
  subscript-store into ``before``/``after``) and the ``_snapshot_state`` witness source is pinned as a
  single, real-reading, top-level def that cmd_run may not shadow/rebind, returning a freshly-built
  mapping carrying EXACTLY the twelve pinned witness dimensions with none hard-coded; the verdict is
  consumed by
  ``evaluate_run`` -> ``proof_complete`` (statically pinned AND dynamically proven: a false or absent
  verdict blocks the claim; an empty record can never claim), and the status command's proof claim is
  gated on ``proof_complete`` (prerequisite health alone can never claim Smoke C);
* the live proof is a registered, justified plain-literal MANUAL_ONLY exception of the run-set
  completeness guard; the hosted live-PG workflow is untouched and does NOT enroll the new harness;
* the runbook carries the required needles and can never claim Smoke C success, B5-BLK-4 closure, or MVP
  completion; no new file carries a token-shaped literal, a PEM header, a DSN-shaped literal, or a new
  environment variable name.

Pure stdlib; standalone-runnable:
  python tests/architecture/test_smoke_c_integrated_live_proof_boundaries.py

B5-BLK-4 remains OPEN; the Physical Multi-Database MVP remains mandatory and is NOT completed by this
guard or the proof it pins.
"""

from __future__ import annotations

import ast
import importlib.util
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_OPS = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "smoke_c_integrated_live_proof.py"
_PROOF = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "test_pg_smoke_c_integrated_live_proof.py"
_RUNBOOK = _scan.REPO_ROOT / "infrastructure" / "runbooks" / "smoke_c_integrated_live_proof.md"
_COMPLETENESS_GUARD = _scan.BACKEND_ROOT / "tests" / "architecture" / "test_live_pg_workflow_runset_completeness.py"
_WORKFLOW = _scan.REPO_ROOT / ".github" / "workflows" / "live-pg-durable-path.yml"
_SPEC = _scan.REPO_ROOT / "docs" / "acceptance" / "SMOKE-C-SPEC-01.md"
_TESTS_DIR = _scan.BACKEND_ROOT / "tests"

_NEW_PY_FILES = (_OPS, _PROOF)
_FAMILY_NAME = "smoke_c_integrated_live_proof"
_MANUAL_ONLY_KEY = "tests/control_plane/requires_pg/test_pg_smoke_c_integrated_live_proof.py"

# The zero-mutation verdict contract (Fix R3): the exact evidence key and the two independently
# captured snapshot names the committed comparison must — semantically, per AST — be built from.
_VERDICT_KEY = "before_equals_after"
_SNAPSHOT_BEFORE = "before"
_SNAPSHOT_AFTER = "after"
# The honest snapshot source and the mutators that would forge "independently captured" operands:
# a snapshot the run clobbers/pops after capture, or one drawn from a shadowed source, is not a
# genuine witness — so ``before``/``after`` may never be reassigned into or method-mutated, and the
# ``_snapshot_state`` name may never be shadowed/rebound/redefined. (``.get`` etc. stay read-only.)
_SNAPSHOT_FN = "_snapshot_state"
_SNAPSHOT_MUTATORS = frozenset({"clear", "update", "pop", "popitem", "setdefault", "__setitem__", "__delitem__"})
# The pinned witness census: the snapshot must carry EXACTLY these dimensions (in this order) and no
# dimension may be a hard-coded literal — a fresh-but-content-hollow mapping (real execute, constant
# return) would otherwise forge before == after under real mutation. Static analysis cannot prove the
# VALUES faithful (that residual belongs to the live proof's cross-checks and the fully external
# pre/post-merge verification witnesses); this census makes a hollow snapshot a wholesale, incoherent
# fabrication instead of a one-line drift.
_SNAPSHOT_WITNESS_KEYS = (
    "tenant_ids",
    "tenants",
    "memberships",
    "audit_total",
    "dormant_register_audit",
    "residue",
    "federation",
    "pg_tenant_databases",
    "dormant_database_present",
    "tenant_db_invariants",
    "secret_root_files",
    "env",
)

# Dynamic needles — built so THIS guard never satisfies its own bans.
_TOKEN_NEEDLE = "e" + "yJ"
_PEM_NEEDLE = "-----BE" + "GIN"
_DSN_NEEDLE = "postgre" + "sql://"
_REMOVAL_TOKEN = "tear" + "down"
_APPLY_TOKEN = "app" + "ly"
_CLOSURE_NEEDLE = "B5-BLK-4 CLO" + "SED"
_MVP_DONE_NEEDLE = "MVP COMPL" + "ETE"
_SMOKE_PASSED_NEEDLES = ("smoke c pass" + "ed", "smoke c succe" + "eded", "smoke c has been exec" + "uted")
_NONLOOPBACK_NEEDLE = "0.0." + "0.0"

_OPS_TOP_IMPORT_ALLOW = {
    "__future__",
    "argparse",
    "importlib",
    "importlib.util",
    "os",
    "pathlib",
    "socket",
    "subprocess",
    "sys",
    "threading",
    "time",
    "typing",
    "urllib.error",
    "urllib.parse",
    "urllib.request",
}
_PROOF_TOP_IMPORT_ALLOW = {"__future__", "contextlib", "importlib", "io", "os", "pathlib", "sys", "typing", _FAMILY_NAME}

_FORBIDDEN_IMPORTS = (
    "psycopg",
    "psycopg2",
    "asyncpg",
    "sqlalchemy",
    "jwt",
    "cryptography",
    "crypto_fixture",
    "b5_standing_topology",
    "b5_standing_auth_fixture",
    "_db_doubles",
    "_auth_doubles",
    "_gateway_doubles",
    "unittest",
    "mock",
    "pytest",
)

# The exact production composition seams the operator must call ONCE each — and nothing lower-level.
_REQUIRED_SEAM_CALLS = (
    "build_read_server_from_env",
    "build_authenticate_server_from_env",
    "build_dispatch_server_from_env",
    "build_gateway",
    "build_authenticator_from_env",
    "build_router_dispatch_from_env",
)
_BANNED_COMPOSITION_CALLS = frozenset(
    {
        "build_router",
        "build_router_from_env",
        "build_authenticator",
        "build_dispatch_server",
        "build_authenticate_server",
        "make_server",
        "HTTPServer",
        "BaseHTTPRequestHandler",
        "serve_read_api",
        "serve_authenticate_api",
        "serve_dispatch_api",
    }
)
_BANNED_WIRE_BYPASS_CALLS = frozenset({"route", "authenticate", "dispatch"})
_BANNED_WRITE_CALLS = frozenset(
    {
        "register_tenant",
        "add_membership",
        "put_tenant",
        "put_membership",
        "put_federation",
        "put_directory_record",
        "compare_and_swap_tenant",
        "append_audit",
        "record",
        "suspend_tenant",
        "decommission_tenant",
        "quarantine_tenant",
        "mark_provisioning",
        "onboard",
        "reassociate",
        "recover",
        "deprovision",
        "provision",
        "apply_schema",
        "disable_routing",
        "scan_for_orphans",
        "deprovision_tenant_database",
        "unlink",
        "rmdir",
        "removedirs",
        "rmtree",
        "chmod",
        "mkdir",
        "makedirs",
        "write_text",
        "write_bytes",
        "rename",
        "remove",
        "begin",
        "commit",
        "rollback",
        "write",
        "write_row",
        "executemany",
        "executescript",
        "copy_expert",
        "copy_from",
        "copy_to",
    }
)

_SQL_SINK_METHODS = frozenset({"execute", "executemany", "executescript", "copy", "copy_expert", "copy_from", "copy_to"})
_MUTATING_SQL_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|TRUNCATE|ALTER|DROP|CREATE|MERGE|REPLACE|GRANT|REVOKE|COPY)\b",
    re.IGNORECASE,
)
# The codec error-handler value at the three subprocess seams (errors="replace") word-boundary-matches
# REPLACE but is not SQL; every sink argument is independently pinned to the SELECT allowlist below.
_SQL_CENSUS_EXEMPT_EXACT = frozenset({"replace"})
_ALLOWED_SQL_CONSTANT_NAMES = (
    "_SQL_PG_TENANT_DATABASES",
    "_SQL_PG_DATABASE_PRESENT",
    "_SQL_CURRENT_DATABASE",
    "_SQL_AGENTS_TOTAL",
    "_SQL_SYSTEM_PRIMARY",
    "_SQL_SCHEMA_VERSION",
    "_SQL_ROUTED_IDENTITY",
)

# The pinned existing environment-key census (NO new name; *_PORT keys may only ever be UNSET).
_ENV_SET_VALUE_CONSTANTS = frozenset({"postgres", "in_memory"})
_ENV_ALLOWED_NAME_ARGS = frozenset({"LOOPBACK_HOST", "read_url", "auth_url", "dispatch_url", "key", "name"})
_ALLOWED_ENV_NAMES = {
    "SP2_CP_CONTROL_STORE",
    "SP2_CP_PROVISIONING_ADAPTER",
    "SP2_CP_TENANT_SCHEMA_APPLICATOR",
    "SP2_CP_DISTINCTNESS_LEDGER",
    "SP2_CP_READ_HOST",
    "SP2_CP_READ_PORT",
    "SP2_AR_CONTROL_PLANE_READ_BASE_URL",
    "SP2_AR_ISSUERS",
    "SP2_AR_AUTHENTICATE_HOST",
    "SP2_AR_AUTHENTICATE_PORT",
    "SP2_DBR_ROUTING_READ_BASE_URL",
    "SP2_DBR_DISPATCH_HOST",
    "SP2_DBR_DISPATCH_PORT",
    "SP2_GW_AUTH_ROUTER_BASE_URL",
    "SP2_GW_DB_ROUTER_BASE_URL",
    "SNACKPORTAL_TENANT_SECRET_DIR",
}
_ENV_NAME_RE = re.compile(r"\b(SP2_[A-Z0-9_]+|SNACKPORTAL_[A-Z0-9_]+)\b")

# The EXACT binding scenario matrix (guard-side copy — the operator's table must equal it verbatim).
_EXPECTED_MATRIX: Tuple[Dict[str, Any], ...] = (
    {
        "label": "alpha-success",
        "status": 200,
        "public_code": "ok",
        "dispatched": True,
        "internal_code": None,
        "database": "sp2_tenant_b5_standing_alpha",
    },
    {
        "label": "beta-success",
        "status": 200,
        "public_code": "ok",
        "dispatched": True,
        "internal_code": None,
        "database": "sp2_tenant_b5_standing_beta",
    },
    {
        "label": "dormant-not-ready",
        "status": 403,
        "public_code": "forbidden",
        "dispatched": False,
        "internal_code": "tenant_not_ready",
        "database": None,
    },
    {
        "label": "unknown-tenant",
        "status": 403,
        "public_code": "forbidden",
        "dispatched": False,
        "internal_code": "tenant_access_denied",
        "database": None,
    },
    {
        "label": "carrier-mismatch",
        "status": 403,
        "public_code": "carrier_mismatch",
        "dispatched": False,
        "internal_code": "carrier_mismatch",
        "database": None,
    },
    {
        "label": "bad-signature",
        "status": 401,
        "public_code": "unauthenticated",
        "dispatched": False,
        "internal_code": "bad_signature",
        "database": None,
    },
    {
        "label": "unknown-kid",
        "status": 401,
        "public_code": "unauthenticated",
        "dispatched": False,
        "internal_code": "unknown_kid",
        "database": None,
    },
    {
        "label": "unknown-issuer",
        "status": 401,
        "public_code": "unauthenticated",
        "dispatched": False,
        "internal_code": "unknown_issuer",
        "database": None,
    },
    {
        "label": "control-plane-unavailable",
        "status": 503,
        "public_code": "unavailable",
        "dispatched": False,
        "internal_code": "control_plane_unavailable",
        "database": None,
    },
)


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _load_ops_module() -> Any:
    """Load the operator module by file location (its import is inert by pinned contract)."""
    spec = importlib.util.spec_from_file_location("smoke_c_v2_ops_under_guard", _OPS)
    assert spec is not None and spec.loader is not None, "operator module could not be located"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- shared predicates (used by the real pins AND the planted-mutant companions) -------------------
def _top_import_names(tree: ast.Module) -> Set[str]:
    names: Set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def _inertness_problems(tree: ast.Module) -> List[str]:
    """Top level = docstring / imports / call-free-or-path-resolution assigns / defs / main guard /
    ``sys.path.insert`` only. A module-level serve/keygen/request cannot pass."""
    allowed_assign_calls = {"pathlib.Path(__file__).resolve()", "pathlib.Path(__file__)"}
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
                    if isinstance(inner, ast.Call) and ast.unparse(inner) not in allowed_assign_calls:
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


def _called_name_counts(tree: ast.Module) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name is not None:
                counts[name] = counts.get(name, 0) + 1
    return counts


def _banned_call_hits(tree: ast.Module, banned: frozenset) -> Set[str]:
    return {name for name in _called_name_counts(tree) if name in banned}


def _seam_census_problems(tree: ast.Module) -> List[str]:
    counts = _called_name_counts(tree)
    problems = [f"missing/duplicated seam call: {name} x{counts.get(name, 0)}" for name in _REQUIRED_SEAM_CALLS if counts.get(name, 0) != 1]
    problems.extend(f"banned composition call: {name}" for name in sorted(_banned_call_hits(tree, _BANNED_COMPOSITION_CALLS)))
    problems.extend(f"banned wire-bypass call: {name}" for name in sorted(_banned_call_hits(tree, _BANNED_WIRE_BYPASS_CALLS)))
    if counts.get("handle", 0) != 1:
        problems.append(f"Gateway.handle must be driven at exactly ONE call site (found {counts.get('handle', 0)})")
    return problems


def _module_string_constants(tree: ast.Module) -> Dict[str, str]:
    """Module-level ``NAME = <static string>`` constants (folding ``+`` concatenations)."""
    constants: Dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            folded = _fold_static_string(node.value, {})
            if folded is not None:
                constants[node.targets[0].id] = folded
    return constants


def _fold_static_string(node: ast.expr, constants: Dict[str, str]) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _fold_static_string(node.left, constants)
        right = _fold_static_string(node.right, constants)
        if left is not None and right is not None:
            return left + right
    return None


def _sql_census_problems(tree: ast.Module, *, allow_sinks: bool) -> List[str]:
    """Every SQL-capable sink must be ``execute`` with a statically resolvable SELECT argument from
    the pinned allowlist; no string constant anywhere may carry a mutating-SQL keyword."""
    constants = _module_string_constants(tree)
    allowed_sql = {constants[name] for name in _ALLOWED_SQL_CONSTANT_NAMES if name in constants}
    problems: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in _SQL_SINK_METHODS:
            if not allow_sinks:
                problems.append(f"SQL sink present in a sink-free file: {node.func.attr}")
                continue
            if node.func.attr != "execute":
                problems.append(f"non-execute SQL sink: {node.func.attr}")
                continue
            if not node.args:
                problems.append("execute() with no statement argument")
                continue
            statement = _fold_static_string(node.args[0], constants)
            if statement is None:
                problems.append("execute() argument does not statically resolve (computed SQL is banned)")
            elif statement not in allowed_sql or not statement.upper().startswith("SELECT"):
                problems.append(f"execute() statement is not a pinned read-only SELECT: {statement[:60]!r}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in _SQL_CENSUS_EXEMPT_EXACT or node.value in allowed_sql:
                continue
            match = _MUTATING_SQL_RE.search(node.value)
            if match:
                problems.append(f"mutating-SQL keyword {match.group(0)!r} in string constant {node.value[:40]!r}")
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            folded = _fold_static_string(node, constants)
            if folded is not None and folded not in allowed_sql and folded not in _SQL_CENSUS_EXEMPT_EXACT:
                match = _MUTATING_SQL_RE.search(folded)
                if match and not any(
                    isinstance(part, ast.Constant) and isinstance(part.value, str) and _MUTATING_SQL_RE.search(part.value)
                    for part in ast.walk(node)
                ):
                    problems.append(f"split-string mutating-SQL keyword {match.group(0)!r} (folded: {folded[:40]!r})")
    return problems


def _subprocess_census_problems(tree: ast.Module) -> List[str]:
    """Exactly three ``subprocess.run`` sites, each argv a call to its pinned status-only/read-only
    builder; the builders themselves carry no non-status standing-operator token."""
    allowed_builders = {"_b5_4_status_argv", "_b5_4a_status_argv", "_git_head_argv"}
    problems: List[str] = []
    sites = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and ast.unparse(node.func) == "subprocess.run"
    ]
    if len(sites) != 3:
        problems.append(f"{len(sites)} subprocess.run site(s), expected exactly 3")
    for site in sites:
        if not site.args or not isinstance(site.args[0], ast.Call) or not isinstance(site.args[0].func, ast.Name):
            problems.append("subprocess.run argv is not a pinned builder call (inline argv is banned)")
            continue
        if site.args[0].func.id not in allowed_builders:
            problems.append(f"subprocess.run argv builder {site.args[0].func.id!r} is not pinned")
    for func in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in allowed_builders):
        source = ast.unparse(func)
        if func.name == "_git_head_argv":
            if "'git'" not in source or "'rev-parse'" not in source or "'HEAD'" not in source:
                problems.append("_git_head_argv drifted from the pinned read-only commit witness")
            continue
        if "_STATUS_COMMAND" not in source:
            problems.append(f"{func.name} does not bind the pinned status-only token")
        for banned in (_APPLY_TOKEN, _REMOVAL_TOKEN):
            if banned in source:
                problems.append(f"{func.name} carries a non-status standing-operator token")
    return problems


def _env_write_problems(tree: ast.Module) -> List[str]:
    """``os.environ`` writes only inside ``_EnvPatch``; ``.set`` values only loopback/selector/URL
    forms — never a port value, never a non-loopback host, never an unknown key."""
    problems: List[str] = []
    envpatch_functions: Set[Any] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "_EnvPatch":
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    envpatch_functions.update(ast.walk(item))
    for node in ast.walk(tree):
        is_env_assign = (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Subscript)
            and ast.unparse(node.targets[0].value) == "os.environ"
        )
        is_env_pop = isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and ast.unparse(node.func) == "os.environ.pop"
        if (is_env_assign or is_env_pop) and node not in envpatch_functions:
            problems.append("os.environ write outside the _EnvPatch save/restore seam")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "set" and len(node.args) == 2:
            key_node, value_node = node.args
            if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                if key_node.value not in _ALLOWED_ENV_NAMES:
                    problems.append(f"env set of an unknown key: {key_node.value!r}")
                if key_node.value.endswith("_PORT") and not (isinstance(value_node, ast.Constant) and value_node.value is None):
                    problems.append(f"a *_PORT key may only ever be UNSET (fixed ports are banned): {key_node.value!r}")
            if isinstance(value_node, ast.Constant):
                if value_node.value is None or value_node.value in _ENV_SET_VALUE_CONSTANTS:
                    continue
                problems.append(f"env set with an unpinned constant value: {value_node.value!r}")
            elif isinstance(value_node, ast.Name):
                if value_node.id not in _ENV_ALLOWED_NAME_ARGS:
                    problems.append(f"env set with an unpinned name value: {value_node.id!r}")
            elif not (isinstance(value_node, ast.Call) and "issuer_env_json" in ast.unparse(value_node)):
                problems.append(f"env set with an unpinned value form: {ast.unparse(value_node)[:50]}")
    return problems


def _function(tree: ast.Module, name: str) -> Optional[ast.FunctionDef]:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _before_after_verdict_problems(cmd_run: ast.FunctionDef) -> List[str]:
    """AST-semantic pin of the zero-mutation verdict (Fix R3) — source text can never satisfy it.

    Inside ``cmd_run``: ``before``/``after`` each bound exactly once, top-level, directly from
    ``_snapshot_state()``; exactly ONE top-level ``evidence["before_equals_after"] = before == after``
    whose value is a direct single-``ast.Eq`` ``ast.Compare`` over exactly those two names, in
    capture -> try/finally -> capture -> verdict statement order; and no side-channel touch of the
    verdict key (keyword/update writes, computed evidence keys, evidence aliasing, deletes). Forged
    constants, ``is``/``!=``/chains, self- or wrong-name comparisons, ``bool()``/helper wrappers, value
    aliases, dead branches, duplicates, and string-/f-string-only comparison text all fail."""
    problems: List[str] = []
    body = cmd_run.body

    def _is_verdict_target(target: ast.expr) -> bool:
        return (
            isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Name)
            and target.value.id == "evidence"
            and isinstance(target.slice, ast.Constant)
            and target.slice.value == _VERDICT_KEY
        )

    # -- the two snapshot operands: bound exactly once each, top-level, directly from _snapshot_state()
    capture_sites: Dict[str, Optional[ast.Assign]] = {}
    for name in (_SNAPSHOT_BEFORE, _SNAPSHOT_AFTER):
        stores = [n for n in ast.walk(cmd_run) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and n.id == name]
        site: Optional[ast.Assign] = None
        if len(stores) == 1:
            site = next((s for s in body if isinstance(s, ast.Assign) and len(s.targets) == 1 and s.targets[0] is stores[0]), None)
        if site is not None and not (
            isinstance(site.value, ast.Call)
            and _call_name(site.value) == "_snapshot_state"
            and not site.value.args
            and not site.value.keywords
        ):
            site = None
        if site is None:
            problems.append(
                f"cmd_run must bind {name!r} exactly once, top-level, by a direct '{name} = _snapshot_state()' snapshot capture"
            )
        capture_sites[name] = site

    # -- exactly one verdict assignment: top-level, plain, a direct before == after Compare(Eq) --------
    verdict_assignments = [
        node
        for node in ast.walk(cmd_run)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign))
        and any(_is_verdict_target(t) for t in (node.targets if isinstance(node, ast.Assign) else [node.target]))
    ]
    verdict: Optional[ast.Assign] = None
    if len(verdict_assignments) != 1:
        problems.append(
            'cmd_run must assign the zero-mutation verdict exactly once as evidence["before_equals_after"] = before == after '
            f"(found {len(verdict_assignments)} assignment(s) to the verdict key)"
        )
    else:
        node = verdict_assignments[0]
        if node not in body:
            problems.append("the verdict assignment must be a direct top-level statement of cmd_run (dead/nested placement is banned)")
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            problems.append("the verdict must be one plain single-target assignment")
        else:
            verdict = node
            value = node.value
            if not isinstance(value, ast.Compare):
                problems.append(
                    "the verdict value must be a direct comparison — never a constant, call, bool(), helper, or alias: "
                    f"{ast.unparse(value)!r}"
                )
            else:
                if len(value.ops) != 1 or not isinstance(value.ops[0], ast.Eq):
                    problems.append(f"the verdict comparison must use exactly one == operator: {ast.unparse(value)!r}")
                operand_names = [n.id if isinstance(n, ast.Name) else None for n in (value.left, *value.comparators)]
                if operand_names != [_SNAPSHOT_BEFORE, _SNAPSHOT_AFTER]:
                    problems.append(
                        "the verdict operands must be exactly the two independently captured snapshot names "
                        f"'{_SNAPSHOT_BEFORE} == {_SNAPSHOT_AFTER}': {ast.unparse(value)!r}"
                    )

    # -- statement order: capture before -> try/finally (the run) -> capture after -> assign verdict --
    tries = [s for s in body if isinstance(s, ast.Try)]
    if len(tries) != 1:
        problems.append(f"cmd_run must hold exactly one top-level try/finally (found {len(tries)})")
    elif (
        capture_sites[_SNAPSHOT_BEFORE] is not None
        and capture_sites[_SNAPSHOT_AFTER] is not None
        and verdict is not None
        and verdict in body
    ):
        order = [
            body.index(capture_sites[_SNAPSHOT_BEFORE]),
            body.index(tries[0]),
            body.index(capture_sites[_SNAPSHOT_AFTER]),
            body.index(verdict),
        ]
        if order != sorted(order):
            problems.append("cmd_run statement order drifted from: capture before -> try/finally -> capture after -> assign the verdict")

    # -- snapshot-source integrity: cmd_run may never shadow/rebind the honest snapshot source -------
    for node in ast.walk(cmd_run):
        if isinstance(node, (ast.Global, ast.Nonlocal)) and _SNAPSHOT_FN in node.names:
            problems.append(f"cmd_run may never rebind the snapshot source {_SNAPSHOT_FN!r} via global/nonlocal")
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == _SNAPSHOT_FN for t in node.targets):
            problems.append(f"cmd_run may never shadow the snapshot source {_SNAPSHOT_FN!r} with a local binding")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node is not cmd_run and node.name == _SNAPSHOT_FN:
            problems.append(f"cmd_run may never redefine the snapshot source {_SNAPSHOT_FN!r}")

    # -- no post-capture tampering: the two snapshots must be compared exactly as captured -----------
    for node in ast.walk(cmd_run):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in (_SNAPSHOT_BEFORE, _SNAPSHOT_AFTER)
            and node.func.attr in _SNAPSHOT_MUTATORS
        ):
            problems.append(f"cmd_run may never mutate a captured snapshot: {node.func.value.id}.{node.func.attr}()")
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id in (_SNAPSHOT_BEFORE, _SNAPSHOT_AFTER)
            and isinstance(node.ctx, (ast.Store, ast.Del))
        ):
            problems.append(f"cmd_run may never assign into or delete from a captured snapshot: {node.value.id}[...]")

    # -- no side channel: the single pinned assignment is the ONLY writer of the verdict key, and
    #    every evidence write is a constant-string-keyed subscript store — no computed/folded key on
    #    Assign / AnnAssign / AugAssign, no mutator method (update/**{…} splat), no aliasing, no
    #    deletion — so an overwrite through an annotated/augmented/folded side door cannot forge it.
    evidence_slice_ids = {
        id(n.slice)
        for n in ast.walk(cmd_run)
        if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id == "evidence"
    }

    def _assign_targets(node: ast.AST) -> List[ast.expr]:
        if isinstance(node, ast.Assign):
            return list(node.targets)
        if isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            return [node.target]
        return []

    for node in ast.walk(cmd_run):
        if isinstance(node, ast.Constant) and node.value == _VERDICT_KEY and id(node) not in evidence_slice_ids:
            problems.append(
                "the verdict key may only ever appear as an evidence[...] subscript key (side-channel/computed access is banned)"
            )
        if isinstance(node, ast.keyword) and node.arg == _VERDICT_KEY:
            problems.append("the verdict key may never be written through a keyword argument (update()/dict side channels are banned)")
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.ctx, ast.Del)
            and isinstance(node.value, ast.Name)
            and node.value.id == "evidence"
        ):
            problems.append("cmd_run may never delete an evidence key")
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name) and node.value.id == "evidence":
            problems.append("cmd_run may never alias the evidence mapping")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "evidence"
            and node.func.attr in _SNAPSHOT_MUTATORS
        ):
            problems.append(f"cmd_run may never mutate the evidence mapping through a method call: evidence.{node.func.attr}()")
        for target in _assign_targets(node):
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == "evidence"
                and not (isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str))
            ):
                problems.append("cmd_run may never store to evidence through a computed key (Assign/AnnAssign/AugAssign)")
    return problems


def _verdict_consumption_problems(tree: ast.Module) -> List[str]:
    """The verdict must be CONSUMED by the claim path (Fix R3 §7): ``evaluate_run`` fail-closes on the
    exact key, ``proof_complete`` consumes ``evaluate_run``, and ``cmd_run`` evaluates the collected
    evidence record — so a false verdict can never survive into a Smoke C success claim."""
    problems: List[str] = []
    evaluate = _function(tree, "evaluate_run")
    if evaluate is None:
        problems.append("evaluate_run is missing")
    else:
        checks = [
            node
            for node in ast.walk(evaluate)
            if isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and isinstance(node.ops[0], ast.IsNot)
            and len(node.comparators) == 1
            and isinstance(node.comparators[0], ast.Constant)
            and node.comparators[0].value is True
            and isinstance(node.left, ast.Call)
            and isinstance(node.left.func, ast.Attribute)
            and node.left.func.attr == "get"
            and isinstance(node.left.func.value, ast.Name)
            and node.left.func.value.id == "evidence"
            and len(node.left.args) == 1
            and not node.left.keywords
            and isinstance(node.left.args[0], ast.Constant)
            and node.left.args[0].value == _VERDICT_KEY
        ]
        if len(checks) != 1:
            problems.append(
                f"evaluate_run must fail-close on exactly one evidence.get(<verdict key>) is not True check (found {len(checks)})"
            )
    complete = _function(tree, "proof_complete")
    if complete is None:
        problems.append("proof_complete is missing")
    elif not any(isinstance(node, ast.Call) and _call_name(node) == "evaluate_run" for node in ast.walk(complete)):
        problems.append("proof_complete does not consume evaluate_run — the verdict would be uncoupled from the claim")
    cmd_run = _function(tree, "cmd_run")
    if cmd_run is None:
        problems.append("cmd_run is missing")
    elif not any(
        isinstance(node, ast.Call)
        and _call_name(node) == "evaluate_run"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "evidence"
        for node in ast.walk(cmd_run)
    ):
        problems.append("cmd_run does not evaluate the collected evidence record (evaluate_run(evidence))")
    return problems


def _own_returns(fn: ast.FunctionDef) -> List[ast.Return]:
    """``return`` statements owned by ``fn`` itself — not those belonging to a nested def/lambda."""
    returns: List[ast.Return] = []

    def _walk(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue  # a nested scope's returns belong to it
            if isinstance(child, ast.Return):
                returns.append(child)
            _walk(child)

    _walk(fn)
    return returns


def _snapshot_source_integrity_problems(tree: ast.Module) -> List[str]:
    """Module-scope guarantee that ``_snapshot_state`` is a single honest witness source (Fix R3):
    defined exactly once at top level, never reassigned at module scope, genuinely reading state (at
    least one ``execute`` — the SQL census pins every such call to a read-only SELECT), and returning a
    FRESHLY-CONSTRUCTED mapping (``ast.Dict``/``ast.DictComp``) on every value-bearing return. A hollow
    ``return {}`` snapshot, a module-level rebind, a duplicate definition, or a cached/shared return
    object (which would make ``before is after`` and forge equality even under real mutation) all fail."""
    problems: List[str] = []
    defs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == _SNAPSHOT_FN]
    if len(defs) != 1:
        problems.append(f"the module must define the snapshot source {_SNAPSHOT_FN!r} exactly once, top-level (found {len(defs)})")
    if any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == _SNAPSHOT_FN for t in n.targets) for n in tree.body):
        problems.append(f"the snapshot source {_SNAPSHOT_FN!r} may never be reassigned at module scope")
    if len(defs) == 1:
        reads = [
            node
            for node in ast.walk(defs[0])
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "execute"
        ]
        if not reads:
            problems.append(f"{_SNAPSHOT_FN!r} performs no real read (no execute) — a hollow snapshot cannot witness state")
        value_returns = [ret for ret in _own_returns(defs[0]) if ret.value is not None]
        if not value_returns:
            problems.append(f"{_SNAPSHOT_FN!r} returns no witness snapshot value")
        for ret in value_returns:
            if not isinstance(ret.value, (ast.Dict, ast.DictComp)):
                problems.append(
                    f"{_SNAPSHOT_FN!r} must return a freshly-constructed mapping so before/after are distinct objects "
                    f"(a cached/shared return forges equality): {ast.unparse(ret.value)[:40]!r}"
                )
    return problems


def _snapshot_witness_census_problems(tree: ast.Module) -> List[str]:
    """The operator's witness snapshot must carry EXACTLY the pinned dimensions and none hard-coded:
    a fresh-but-content-hollow mapping (real execute, constant return) would forge ``before == after``
    even under real mutation. Pins the committed explicit ``ast.Dict`` return of ``_snapshot_state``."""
    defs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == _SNAPSHOT_FN]
    if len(defs) != 1:
        return [f"the module must define the snapshot source {_SNAPSHOT_FN!r} exactly once, top-level (found {len(defs)})"]
    problems: List[str] = []
    dict_returns = [ret.value for ret in _own_returns(defs[0]) if isinstance(ret.value, ast.Dict)]
    if len(dict_returns) != 1:
        problems.append(f"{_SNAPSHOT_FN!r} must return exactly one explicit witness mapping (found {len(dict_returns)})")
        return problems
    witness = dict_returns[0]
    keys = [key.value if isinstance(key, ast.Constant) else None for key in witness.keys]
    if keys != list(_SNAPSHOT_WITNESS_KEYS):
        problems.append(f"the witness snapshot census drifted from the pinned dimensions: {keys}")
    for key, value in zip(witness.keys, witness.values):
        if isinstance(value, ast.Constant):
            label = key.value if isinstance(key, ast.Constant) else ast.unparse(key)
            problems.append(f"witness dimension {label!r} is hard-coded to a literal (a constant witness cannot observe state)")
    return problems


def _run_structure_problems(tree: ast.Module) -> List[str]:
    """cmd_run must carry the AST-pinned zero-mutation verdict, evaluate, and clean up in ``finally``,
    over a single honest ``_snapshot_state`` witness source."""
    cmd_run = _function(tree, "cmd_run")
    if cmd_run is None:
        return ["cmd_run is missing"]
    problems: List[str] = _before_after_verdict_problems(cmd_run)
    problems.extend(_snapshot_source_integrity_problems(tree))
    if not any(isinstance(node, ast.Call) and _call_name(node) == "evaluate_run" for node in ast.walk(cmd_run)):
        problems.append("cmd_run does not evaluate the run-level obligations")
    finally_calls: Set[str] = set()
    for node in ast.walk(cmd_run):
        if isinstance(node, ast.Try):
            for stmt in node.finalbody:
                for inner in ast.walk(stmt):
                    if isinstance(inner, ast.Call):
                        name = _call_name(inner)
                        if name is not None:
                            finally_calls.add(name)
    if "_stop_all" not in finally_calls:
        problems.append("cmd_run has no finally-block _stop_all shutdown")
    if "restore" not in finally_calls:
        problems.append("cmd_run has no finally-block environment restore")
    return problems


def _readiness_problems(tree: ast.Module, module: Any) -> List[str]:
    problems: List[str] = []
    timeout = getattr(module, "READINESS_TIMEOUT_SECONDS", None)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        problems.append("READINESS_TIMEOUT_SECONDS must be a positive bound")
    await_ready = _function(tree, "_await_ready")
    if await_ready is None:
        problems.append("_await_ready is missing")
    else:
        source = ast.unparse(await_ready)
        if "READINESS_TIMEOUT_SECONDS" not in source or "monotonic" not in source:
            problems.append("_await_ready is not bounded by READINESS_TIMEOUT_SECONDS over a monotonic clock")
    return problems


def _status_claim_problems(tree: ast.Module) -> List[str]:
    cmd_status = _function(tree, "cmd_status")
    if cmd_status is None:
        return ["cmd_status is missing"]
    gated = any(
        isinstance(node, ast.If) and any(isinstance(c, ast.Call) and _call_name(c) == "proof_complete" for c in ast.walk(node.test))
        for node in ast.walk(cmd_status)
    )
    return [] if gated else ["cmd_status does not gate the proof claim on proof_complete (prerequisites alone could claim)"]


def _matrix_problems(scenarios: Tuple[Dict[str, Any], ...]) -> List[str]:
    """The operator's scenario table must equal the guard-side binding matrix EXACTLY."""
    problems: List[str] = []
    if len(scenarios) != len(_EXPECTED_MATRIX):
        problems.append(f"{len(scenarios)} scenario row(s), expected exactly {len(_EXPECTED_MATRIX)}")
    by_label = {str(s.get("label")): s for s in scenarios}
    for expected in _EXPECTED_MATRIX:
        row = by_label.get(str(expected["label"]))
        if row is None:
            problems.append(f"missing binding scenario: {expected['label']}")
            continue
        for field in ("status", "public_code", "dispatched", "internal_code", "database"):
            if row.get(field) != expected[field]:
                problems.append(f"{expected['label']}.{field} is {row.get(field)!r}, expected {expected[field]!r}")
        if expected["status"] != 200 and row.get("internal_code") in (None, ""):
            problems.append(f"{expected['label']} omits the binding internal denial code (the envelope alone is insufficient)")
    extra = set(by_label) - {str(e["label"]) for e in _EXPECTED_MATRIX}
    if extra:
        problems.append(f"unexpected extra scenario row(s): {sorted(extra)}")
    return problems


def _good_observed(expected: Dict[str, Any]) -> Dict[str, Any]:
    if expected["internal_code"] is None:
        return {
            "executed": True,
            "status": expected["status"],
            "public_code": expected["public_code"],
            "dispatched": expected["dispatched"],
            "category": "TENANT_OPERATION",
            "internal_code": None,
            "route_events": 1,
            "pool_delta": 0,
            "new_pool_keys": 0,
            "database": expected["database"],
            "readback_reused": True,
            "other_pool_delta": 0,
        }
    return {
        "executed": True,
        "status": expected["status"],
        "public_code": expected["public_code"],
        "dispatched": expected["dispatched"],
        "category": None,
        "internal_code": expected["internal_code"],
        "route_events": 0,
        "pool_delta": 0,
        "new_pool_keys": 0,
        "database": None,
        "readback_reused": None,
        "other_pool_delta": None,
    }


def _good_evidence(module: Any) -> Dict[str, Any]:
    return {
        "scenarios": {str(s["label"]): _good_observed(s) for s in module.SCENARIOS},
        "before_equals_after": True,
        "state_diff": [],
        "shutdown_problems": [],
        "ports_released": True,
        "pools_drained": True,
        "env_restored": True,
    }


# --- the real pins ---------------------------------------------------------------------------------
def test_surface_files_exist_and_family_is_closed() -> None:
    for path in (_OPS, _PROOF, _RUNBOOK, _COMPLETENESS_GUARD, _WORKFLOW, _SPEC):
        assert path.is_file(), f"Smoke C V2 surface file missing: {path}"
    family = sorted(
        p.relative_to(_scan.REPO_ROOT).as_posix()
        for root in (_TESTS_DIR, _scan.REPO_ROOT / "infrastructure" / "runbooks")
        for p in root.rglob(f"*{_FAMILY_NAME}*")
        if p.is_file() and "__pycache__" not in p.parts
    )
    expected = sorted(p.relative_to(_scan.REPO_ROOT).as_posix() for p in (_OPS, _PROOF, _RUNBOOK, pathlib.Path(__file__).resolve()))
    assert family == expected, f"the Smoke C V2 file family drifted from the authorized surface: {family}"


def test_ops_import_inert_with_stdlib_only_top_imports() -> None:
    tree = _tree(_OPS)
    problems = _inertness_problems(tree)
    assert not problems, f"operator must be import-inert: {problems}"
    unexpected = _top_import_names(tree) - _OPS_TOP_IMPORT_ALLOW
    assert not unexpected, f"operator top-level imports must be stdlib-only (backend imports stay lazy): {sorted(unexpected)}"


def test_proof_import_inert_and_subprocess_free() -> None:
    tree = _tree(_PROOF)
    problems = _inertness_problems(tree)
    assert not problems, f"proof must be import-inert: {problems}"
    unexpected = _top_import_names(tree) - _PROOF_TOP_IMPORT_ALLOW
    assert not unexpected, f"proof top-level imports drifted: {sorted(unexpected)}"
    mods = {m.split(".")[0] for m in _scan.imported_modules(_PROOF)}
    assert "subprocess" not in mods, "the proof must not import subprocess (only the operator holds that seam)"


def test_no_forbidden_imports_anywhere_in_the_new_files() -> None:
    for path in _NEW_PY_FILES:
        rp = _scan.relposix(path)
        for mod in _scan.imported_modules(path):
            top = mod.split(".")[0]
            assert top not in _FORBIDDEN_IMPORTS, f"forbidden import {mod!r} in {rp}"
            assert "b5_standing" not in mod, f"{rp} must never import a standing operator (subprocess-only)"
    # Non-vacuity: the census detects synthetic vendor/double/operator imports.
    for planted in ("import psycopg\n", "import jwt\n", "import _db_doubles\n", "import b5_standing_topology\n"):
        names = {m.split(".")[0] for m in _import_names_of(planted)}
        assert names & set(_FORBIDDEN_IMPORTS) or any("b5_standing" in m for m in _import_names_of(planted)), (
            f"forbidden-import detector went vacuous for {planted.strip()}"
        )


def _import_names_of(source: str) -> List[str]:
    tree = ast.parse(source)
    names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_real_composition_seams_only() -> None:
    problems = _seam_census_problems(_tree(_OPS))
    assert not problems, f"composition seam census failed: {problems}"


def test_seam_census_non_vacuity() -> None:
    # [matrix 1] fake substitution, [matrix 2] auth bypass, [matrix 3] router bypass — all rejected
    # by the SAME predicate that passes the real operator.
    fake = ast.parse("def f():\n    server, url = build_dispatch_server(FakeRouter(), '127.0.0.1', 0)\n")
    assert any("build_dispatch_server" in p for p in _seam_census_problems(fake)), "a hand-rolled dispatch server must be rejected"
    bypass_auth = ast.parse("def f(a, t):\n    return a.authenticate(t, correlation_id='x')\n")
    assert any("authenticate" in p for p in _seam_census_problems(bypass_auth)), "a direct authenticate() bypass must be rejected"
    bypass_router = ast.parse("def f(r, ctx):\n    return r.route(ctx)\n")
    assert any("route" in p for p in _seam_census_problems(bypass_router)), "a direct route() bypass must be rejected"
    two_gateways = ast.parse("def f():\n    build_gateway(x=1)\n    build_gateway(x=2)\n")
    assert any("build_gateway" in p for p in _seam_census_problems(two_gateways)), "a duplicated seam call must be rejected"


def test_command_surface_is_exactly_plan_run_status() -> None:
    tree = _tree(_OPS)
    subcommands = [
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_parser"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    ]
    assert subcommands == ["plan", "run", "status"], f"operator subcommands drifted: {subcommands}"
    for path in _NEW_PY_FILES:
        source = path.read_text(encoding="utf-8")
        assert _REMOVAL_TOKEN not in source, f"the removal-command token must not appear in {path.name}"
        assert "--confirm" not in source, f"no confirmation-flag surface may exist in {path.name} (nothing destructive exists)"


def test_subprocess_seams_are_status_only_and_builder_bound() -> None:
    problems = _subprocess_census_problems(_tree(_OPS))
    assert not problems, f"subprocess census failed: {problems}"
    module = _load_ops_module()
    assert module._STATUS_COMMAND == "status", "the standing-operator delegation token is pinned to status"
    assert module._b5_4_status_argv()[-1] == "status" and module._b5_4a_status_argv()[-1] == "status"
    assert module._git_head_argv() == ["git", "rev-parse", "HEAD"]


def test_subprocess_census_non_vacuity() -> None:
    # [matrix 21] a B5-4/B5-4A apply invocation (builder-token or inline argv) must be rejected.
    mutated_builder = ast.parse(
        "def _b5_4_status_argv():\n"
        f"    return [sys.executable, str(_B5_4_OPS), '{_APPLY_TOKEN}']\n"
        "def f():\n"
        "    subprocess.run(_b5_4_status_argv())\n    subprocess.run(_b5_4a_status_argv())\n    subprocess.run(_git_head_argv())\n"
    )
    assert any("non-status" in p for p in _subprocess_census_problems(mutated_builder)), "an apply-token builder must be rejected"
    inline = ast.parse(
        "def f():\n"
        "    subprocess.run(['python', 'x.py', 'status'])\n"
        "    subprocess.run(_b5_4a_status_argv())\n    subprocess.run(_git_head_argv())\n"
    )
    assert any("inline argv" in p for p in _subprocess_census_problems(inline)), "inline argv must be rejected"
    extra_site = ast.parse(
        "def f():\n"
        "    subprocess.run(_b5_4_status_argv())\n    subprocess.run(_b5_4a_status_argv())\n"
        "    subprocess.run(_git_head_argv())\n    subprocess.run(_git_head_argv())\n"
    )
    assert any("expected exactly 3" in p for p in _subprocess_census_problems(extra_site)), "a fourth subprocess site must be rejected"


def test_sql_surface_is_readonly_and_pinned() -> None:
    problems = _sql_census_problems(_tree(_OPS), allow_sinks=True)
    assert not problems, f"operator SQL census failed: {problems}"
    proof_problems = _sql_census_problems(_tree(_PROOF), allow_sinks=False)
    assert not proof_problems, f"proof SQL census failed: {proof_problems}"


def test_sql_census_non_vacuity() -> None:
    # [matrix 20] INSERT/UPDATE/DELETE/TRUNCATE/DDL and the copy/batch family are all rejected.
    verbs = ("DELETE FROM control_tenants", "INSERT INTO x VALUES (1)", "TRUNCATE control_audit", "CREATE TABLE x (y int)")
    for verb in verbs:
        mutant = ast.parse(f'def f(cur):\n    cur.execute("{verb}")\n')
        assert _sql_census_problems(mutant, allow_sinks=True), f"mutating SQL must be rejected: {verb.split()[0]}"
    lower = ast.parse('def f(cur):\n    cur.executemany("delete from x", [])\n')
    assert any("non-execute" in p for p in _sql_census_problems(lower, allow_sinks=True)), "executemany must be rejected"
    copy_sink = ast.parse('def f(cur):\n    cur.copy("COP" + "Y x FROM STDIN")\n')
    assert _sql_census_problems(copy_sink, allow_sinks=True), "the psycopg3 copy sink must be rejected"
    split = ast.parse('def f(cur):\n    cur.execute("DEL" + "ETE FROM x")\n')
    assert _sql_census_problems(split, allow_sinks=True), "a split-string mutating verb must be rejected"
    computed = ast.parse("def f(cur, q):\n    cur.execute(q)\n")
    assert any("statically resolve" in p for p in _sql_census_problems(computed, allow_sinks=True)), "computed SQL must be rejected"
    in_proof = ast.parse('def f(cur):\n    cur.execute("SELECT 1")\n')
    assert any("sink-free" in p for p in _sql_census_problems(in_proof, allow_sinks=False)), "any sink in the proof must be rejected"


def test_no_write_reachability_in_either_file() -> None:
    for path in _NEW_PY_FILES:
        hits = _banned_call_hits(_tree(path), _BANNED_WRITE_CALLS)
        assert not hits, f"banned write/lifecycle/file/transaction call(s) in {path.name}: {sorted(hits)}"
    # Non-vacuity ([matrix 19/22/23] source side): supported-write and raw-transaction mutants are caught.
    for planted in (
        "def f(cp):\n    cp.registry.register_tenant(tenant_id='x')\n",
        "def f(cp):\n    cp.membership.add_membership(principal_ref='p', tenant_id='t', role=None)\n",
        "def f(conn):\n    conn.commit()\n",
        "def f(p):\n    p.unlink()\n",
    ):
        assert _banned_call_hits(ast.parse(planted), _BANNED_WRITE_CALLS), f"write-ban detector went vacuous for: {planted.strip()}"


def test_env_writes_are_patch_scoped_loopback_only_and_port_free() -> None:
    problems = _env_write_problems(_tree(_OPS))
    assert not problems, f"environment-write census failed: {problems}"
    module = _load_ops_module()
    assert module.LOOPBACK_HOST == "127.0.0.1", "the bind host is pinned to loopback"
    assert set(module._ENV_TOUCHED_KEYS) <= _ALLOWED_ENV_NAMES, "the operator touch census introduces an unknown env name"
    for path in _NEW_PY_FILES:
        names = set(_ENV_NAME_RE.findall(path.read_text(encoding="utf-8")))
        unexpected = names - _ALLOWED_ENV_NAMES
        assert not unexpected, f"{path.name} references unexpected env names (no new variable): {sorted(unexpected)}"
        assert _NONLOOPBACK_NEEDLE not in path.read_text(encoding="utf-8"), f"non-loopback bind literal in {path.name}"


def test_env_census_non_vacuity() -> None:
    # [matrix 13] hardcoded DSN, [matrix 14] non-loopback bind, [matrix 15] fixed port.
    fixed_port = ast.parse("def f(patch):\n    patch.set('SP2_DBR_DISPATCH_PORT', '5599')\n")
    assert any("_PORT" in p for p in _env_write_problems(fixed_port)), "a fixed-port env set must be rejected"
    strange_host = ast.parse(f"def f(patch):\n    patch.set('SP2_CP_READ_HOST', '{_NONLOOPBACK_NEEDLE}')\n")
    assert any("unpinned constant" in p for p in _env_write_problems(strange_host)), "a non-loopback host value must be rejected"
    rogue_key = ast.parse("def f(patch):\n    patch.set('SP2_NEW_KNOB', 'postgres')\n")
    assert any("unknown key" in p for p in _env_write_problems(rogue_key)), "an unknown env key must be rejected"
    outside = ast.parse("def f():\n    os.environ['SP2_CP_READ_HOST'] = 'x'\n")
    assert any("outside the _EnvPatch" in p for p in _env_write_problems(outside)), "an unpatched env write must be rejected"
    dsn_literal = f"x = '{_DSN_NEEDLE}u:p@h/db'\n"
    for path in _NEW_PY_FILES:
        assert _DSN_NEEDLE not in path.read_text(encoding="utf-8"), f"DSN-shaped literal in {path.name}"
    assert _DSN_NEEDLE in dsn_literal, "DSN-needle detector went vacuous"


def test_run_structure_finally_cleanup_and_before_after() -> None:
    problems = _run_structure_problems(_tree(_OPS))
    assert not problems, f"cmd_run structural pins failed: {problems}"


# The canonical run shape: the minimal MODULE (honest snapshot source + cmd_run) that PASSES the full
# structural predicate. Every planted Fix R3 mutant below swaps exactly the verdict line (or a nearby
# line) so its rejection is attributable to that mutation alone.
_CANONICAL_RUN_SHAPE = (
    "def _snapshot_state():\n"
    "    cur.execute(_SQL)\n"
    "    return {}\n"
    "def cmd_run(a):\n"
    "    before = _snapshot_state()\n"
    "    evidence = {}\n"
    "    try:\n"
    "        pass\n"
    "    finally:\n"
    "        problems = _stop_all()\n"
    "        patch.restore()\n"
    "    after = _snapshot_state()\n"
    '    evidence["before_equals_after"] = before == after\n'
    "    evaluate_run(evidence)\n"
)
_VERDICT_LINE = '    evidence["before_equals_after"] = before == after\n'


def _mutated_run(replacement: str) -> ast.Module:
    assert _CANONICAL_RUN_SHAPE.count(_VERDICT_LINE) == 1, "the canonical run template drifted"
    return ast.parse(_CANONICAL_RUN_SHAPE.replace(_VERDICT_LINE, replacement))


def test_run_structure_non_vacuity() -> None:
    # The canonical shape passes the FULL structural predicate — so every rejection is attributable.
    assert _run_structure_problems(ast.parse(_CANONICAL_RUN_SHAPE)) == [], "the canonical cmd_run shape must PASS"
    # [matrix 17] omitted finally shutdown and [matrix 24] omitted before/after comparison.
    no_finally = ast.parse(_CANONICAL_RUN_SHAPE.replace("        problems = _stop_all()\n        patch.restore()\n", "        pass\n"))
    assert any("finally" in p for p in _run_structure_problems(no_finally)), "a missing finally cleanup must be rejected"
    assert any("before == after" in p for p in _run_structure_problems(_mutated_run(""))), (
        "a missing before/after comparison must be rejected"
    )
    one_snapshot = ast.parse(_CANONICAL_RUN_SHAPE.replace("    after = _snapshot_state()\n", ""))
    assert any("_snapshot_state" in p for p in _run_structure_problems(one_snapshot)), "a single-snapshot run must be rejected"


def test_before_after_verdict_semantic_pin_non_vacuity() -> None:
    # Fix R3: every forged-comparison variant must be rejected by the SAME predicate that passes the
    # committed operator — including the forged constant that defeated the retired substring pin (VF-3).
    rejected: Tuple[Tuple[str, str], ...] = (
        ('    evidence["before_equals_after"] = True\n', "direct comparison"),
        ('    evidence["before_equals_after"] = False\n', "direct comparison"),
        ('    evidence["before_equals_after"] = 1 == 1\n', "snapshot names"),
        ('    evidence["before_equals_after"] = before is after\n', "== operator"),
        ('    evidence["before_equals_after"] = before != after\n', "== operator"),
        ('    evidence["before_equals_after"] = before == before\n', "snapshot names"),
        ('    evidence["before_equals_after"] = after == after\n', "snapshot names"),
        ('    evidence["before_equals_after"] = after == before\n', "snapshot names"),
        ('    evidence["before_equals_after"] = before == after == after\n', "== operator"),
        ('    evidence["before_equals_after"] = bool(before == after)\n', "direct comparison"),
        ('    evidence["before_equals_after"] = helper(before, after)\n', "direct comparison"),
        ('    verdict = before == after\n    evidence["before_equals_after"] = verdict\n', "direct comparison"),
        ('    evidence["before_equals_after"] = env_before == env_after\n', "snapshot names"),
        ("", "exactly once"),
        ('    if False:\n        evidence["before_equals_after"] = before == after\n', "top-level"),
        ('    x = "before == after"\n', "exactly once"),
        ('    print(f"before == after -> {before == after}")\n', "exactly once"),
        ('    evidence["unrelated_key"] = before == after\n', "exactly once"),
        (_VERDICT_LINE + _VERDICT_LINE, "exactly once"),
        (_VERDICT_LINE + '    evidence["before_equals_after"] = True\n', "exactly once"),
        (_VERDICT_LINE + "    evidence.update(before_equals_after=True)\n", "keyword argument"),
        (_VERDICT_LINE + '    del evidence["before_equals_after"]\n', "delete an evidence key"),
        (_VERDICT_LINE + "    e = evidence\n", "alias"),
        ('    key = "before_equals_after"\n    evidence[key] = True\n', "computed"),
        (_VERDICT_LINE + "    after = before\n", "_snapshot_state"),
        # Finding A — folded/annotated/augmented computed-key overwrite of the honest verdict.
        (_VERDICT_LINE + "    k = 'before_equals_' + 'after'\n    evidence[k]: bool = True\n", "computed key"),
        (_VERDICT_LINE + "    k = 'before_equals_' + 'after'\n    evidence[k] |= True\n", "computed key"),
        (_VERDICT_LINE + "    evidence['before_equals_' + 'after']: bool = True\n", "computed key"),
        (_VERDICT_LINE + "    evidence['before_equals_' + 'after'] |= True\n", "computed key"),
        (_VERDICT_LINE + "    evidence.update(**{'before_equals_' + 'after': True})\n", "method call"),
        (_VERDICT_LINE + "    evidence.setdefault('x', True)\n", "method call"),
        # post-capture tampering with the two captured snapshots.
        (_VERDICT_LINE + "    after.clear()\n", "mutate a captured snapshot"),
        ("    after.update(before)\n" + _VERDICT_LINE, "mutate a captured snapshot"),
        ("    before.pop('audit_total', None)\n" + _VERDICT_LINE, "mutate a captured snapshot"),
        ("    after['audit_total'] = before['audit_total']\n" + _VERDICT_LINE, "assign into or delete from a captured snapshot"),
        # shadowing / rebinding the honest snapshot source inside cmd_run.
        (_VERDICT_LINE + "    _snapshot_state = dict\n", "shadow the snapshot source"),
        (_VERDICT_LINE + "    global _snapshot_state\n", "global/nonlocal"),
    )
    for replacement, needle in rejected:
        problems = _run_structure_problems(_mutated_run(replacement))
        assert any(needle in p for p in problems), (
            f"a forged verdict variant must be rejected via {needle!r}: {replacement!r} -> {problems}"
        )
    # Hoisting the verdict above the run (comparing before with itself in time) must be rejected.
    hoisted = _CANONICAL_RUN_SHAPE.replace(_VERDICT_LINE, "").replace(
        "    before = _snapshot_state()\n", "    before = _snapshot_state()\n" + _VERDICT_LINE
    )
    assert any("order drifted" in p for p in _run_structure_problems(ast.parse(hoisted))), "a hoisted verdict must be rejected"


def test_snapshot_source_integrity_non_vacuity() -> None:
    # The honest witness source must be a single, real-reading, top-level def — hollow/duplicate/
    # rebound snapshot sources are rejected by the SAME module-scope predicate that passes the operator.
    assert _snapshot_source_integrity_problems(_tree(_OPS)) == [], "the real operator's snapshot source must PASS"
    hollow = ast.parse("def _snapshot_state():\n    return {}\n")
    assert any("no real read" in p for p in _snapshot_source_integrity_problems(hollow)), "a hollow snapshot source must be rejected"
    duplicate = ast.parse("def _snapshot_state():\n    cur.execute(_SQL)\n    return {}\ndef _snapshot_state():\n    return {}\n")
    assert any("exactly once" in p for p in _snapshot_source_integrity_problems(duplicate)), "a duplicate snapshot def must be rejected"
    rebound = ast.parse("def _snapshot_state():\n    cur.execute(_SQL)\n    return {}\n_snapshot_state = dict\n")
    assert any("reassigned at module scope" in p for p in _snapshot_source_integrity_problems(rebound)), (
        "a module-scope rebind of the snapshot source must be rejected"
    )
    # A cached/shared return object (real execute, but the SAME object every call → before IS after).
    singleton = ast.parse("_CACHE = {}\ndef _snapshot_state():\n    cur.execute(_SQL)\n    return _CACHE\n")
    assert any("freshly-constructed mapping" in p for p in _snapshot_source_integrity_problems(singleton)), (
        "a cached/shared snapshot return must be rejected"
    )
    # A freshly-built dict comprehension is a genuine distinct object and must PASS.
    comp = ast.parse("def _snapshot_state():\n    cur.execute(_SQL)\n    return {k: v for k, v in rows}\n")
    assert _snapshot_source_integrity_problems(comp) == [], "a freshly-constructed snapshot mapping must PASS"


def test_snapshot_witness_census_is_pinned() -> None:
    # A fresh-but-content-hollow snapshot (real execute, constant mapping) would forge before == after
    # under real mutation. The witness census pins the twelve committed dimensions, none hard-coded.
    problems = _snapshot_witness_census_problems(_tree(_OPS))
    assert not problems, f"witness census pins failed: {problems}"
    real = _OPS.read_text(encoding="utf-8")
    hollow = ast.parse('def _snapshot_state():\n    cur.execute(_SQL)\n    return {"residue": 0}\n')
    hollow_problems = _snapshot_witness_census_problems(hollow)
    assert any("census drifted" in p for p in hollow_problems), "a content-hollow witness snapshot must be rejected"
    assert any("hard-coded" in p for p in hollow_problems), "a hard-coded witness dimension must be rejected"
    dropped_needle = '        "audit_total": len(audit_rows),\n'
    assert real.count(dropped_needle) == 1, "the committed witness mapping drifted"
    dropped = _snapshot_witness_census_problems(ast.parse(real.replace(dropped_needle, "")))
    assert any("census drifted" in p for p in dropped), "a dropped witness dimension must be rejected"
    hardcoded_needle = '        "residue": residue,\n'
    assert real.count(hardcoded_needle) == 1, "the committed witness mapping drifted"
    hardcoded = _snapshot_witness_census_problems(ast.parse(real.replace(hardcoded_needle, '        "residue": 0,\n')))
    assert any("hard-coded" in p for p in hardcoded), "a hard-coded witness dimension must be rejected"


def test_before_after_verdict_is_consumed_by_the_claim_path() -> None:
    # Fix R3 §7 — static pins over the committed tree, then DYNAMIC proof against the live module.
    problems = _verdict_consumption_problems(_tree(_OPS))
    assert not problems, f"verdict consumption pins failed: {problems}"
    module = _load_ops_module()
    forged_false = _good_evidence(module)
    forged_false["before_equals_after"] = False
    assert module.proof_complete(forged_false) is False, "a false before/after verdict must block the Smoke C success claim"
    absent = _good_evidence(module)
    del absent["before_equals_after"]
    assert module.proof_complete(absent) is False, "an absent before/after verdict must block the Smoke C success claim"
    assert module.proof_complete({}) is False, "prerequisite health alone can never claim proof completion"


def test_verdict_consumption_non_vacuity() -> None:
    # Removing the verdict from the completion predicate (or hollowing the predicate) must be rejected.
    real = _OPS.read_text(encoding="utf-8")
    check_needle = 'evidence.get("before_equals_after") is not True'
    assert real.count(check_needle) == 1, "the committed evaluate_run verdict check drifted"
    unchecked = real.replace(check_needle, "False")
    assert any("evaluate_run" in p for p in _verdict_consumption_problems(ast.parse(unchecked))), (
        "an evaluate_run that no longer checks the verdict must be rejected"
    )
    complete_needle = "all(problem is None for _name, problem in evaluate_run(evidence))"
    assert real.count(complete_needle) == 1, "the committed proof_complete predicate drifted"
    hollow = real.replace(complete_needle, "True")
    assert any("proof_complete" in p for p in _verdict_consumption_problems(ast.parse(hollow))), (
        "a proof_complete that no longer consumes evaluate_run must be rejected"
    )
    run_needle = "for name, problem in evaluate_run(evidence):"
    assert real.count(run_needle) == 1, "the committed cmd_run evaluation loop drifted"
    unevaluated = real.replace(run_needle, "for name, problem in []:")
    assert any("evaluate_run(evidence)" in p for p in _verdict_consumption_problems(ast.parse(unevaluated))), (
        "a cmd_run that no longer evaluates the evidence record must be rejected"
    )


def test_readiness_is_bounded() -> None:
    problems = _readiness_problems(_tree(_OPS), _load_ops_module())
    assert not problems, f"readiness pins failed: {problems}"
    # [matrix 16] non-vacuity: an unbounded wait must be rejected by the SAME predicate.
    unbounded = ast.parse("def _await_ready(label, probe):\n    while True:\n        if probe():\n            return\n")

    class _Stub:
        READINESS_TIMEOUT_SECONDS = 30.0

    assert any("_await_ready" in p or "bounded" in p for p in _readiness_problems(unbounded, _Stub())), (
        "an unbounded readiness wait must be rejected"
    )

    class _NoTimeout:
        READINESS_TIMEOUT_SECONDS = 0

    assert _readiness_problems(_tree(_OPS), _NoTimeout()), "a zero/absent readiness bound must be rejected"


def test_status_claim_is_evidence_gated() -> None:
    problems = _status_claim_problems(_tree(_OPS))
    assert not problems, f"status claim-gating pin failed: {problems}"
    ungated = ast.parse("def cmd_status(a):\n    print('all prerequisites healthy')\n    return 0\n")
    assert _status_claim_problems(ungated), "an ungated status claim must be rejected"


def test_scenario_matrix_is_pinned_exactly() -> None:
    module = _load_ops_module()
    problems = _matrix_problems(module.SCENARIOS)
    assert not problems, f"binding scenario matrix drifted: {problems}"
    assert module.TENANT_ALPHA == "b5_standing_alpha" and module.TENANT_BETA == "b5_standing_beta"
    assert module.TENANT_DORMANT == "b5_standing_dormant" and module.PRINCIPAL == "b5_standing_member"
    assert module.ALPHA_DB == "sp2_tenant_b5_standing_alpha" and module.BETA_DB == "sp2_tenant_b5_standing_beta"
    assert module.ASSOCIATION_VERSION == "1"


def test_scenario_matrix_non_vacuity() -> None:
    # [matrix 4..10] every scenario-shaped mutation of the PRD matrix must be rejected.
    def _mutate(label: str, **changes: Any) -> Tuple[Dict[str, Any], ...]:
        rows = []
        for row in _EXPECTED_MATRIX:
            row = dict(row)
            if row["label"] == label:
                row.update(changes)
            rows.append(row)
        return tuple(rows)

    assert _matrix_problems(_mutate("alpha-success", database="sp2_tenant_b5_standing_beta")), "alpha->beta routing must be rejected"
    assert _matrix_problems(_mutate("beta-success", database="sp2_tenant_b5_standing_alpha")), "beta->alpha routing must be rejected"
    assert _matrix_problems(_mutate("dormant-not-ready", status=200, public_code="ok", dispatched=True)), "dormant success must be rejected"
    assert _matrix_problems(_mutate("unknown-tenant", status=200, public_code="ok", dispatched=True)), "unknown success must be rejected"
    assert _matrix_problems(_mutate("dormant-not-ready", internal_code="tenant_access_denied")), "dormant code swap must be rejected"
    assert _matrix_problems(_mutate("unknown-tenant", internal_code="tenant_not_ready")), "unknown code swap must be rejected"
    assert _matrix_problems(_mutate("dormant-not-ready", internal_code=None)), "an envelope-only denial row must be rejected"
    assert _matrix_problems(_EXPECTED_MATRIX[:-1]), "a dropped binding scenario must be rejected"
    assert _matrix_problems((*_EXPECTED_MATRIX, {"label": "extra", "status": 200})), "an extra scenario row must be rejected"


def test_evaluators_pass_good_evidence_and_reject_every_state_mutation() -> None:
    module = _load_ops_module()
    good = _good_evidence(module)
    assert all(problem is None for _name, problem in module.evaluate_run(good)), "canonical evidence must PASS the evaluators"
    assert module.proof_complete(good) is True
    assert module.proof_complete({}) is False, "an empty evidence record can never claim the proof"

    def _bad(mutator: Any) -> bool:
        evidence = _good_evidence(module)
        mutator(evidence)
        return any(problem is not None for _name, problem in module.evaluate_run(evidence))

    # [matrix 4/5] swapped routing identities.
    assert _bad(lambda e: e["scenarios"]["alpha-success"].update(database=module.BETA_DB)), "alpha->beta evidence must fail"
    assert _bad(lambda e: e["scenarios"]["beta-success"].update(database=module.ALPHA_DB)), "beta->alpha evidence must fail"
    # [matrix 6/7] denials accepted as success.
    dormant_ok = _bad(lambda e: e["scenarios"]["dormant-not-ready"].update(status=200, public_code="ok", dispatched=True))
    assert dormant_ok, "dormant success must fail"
    unknown_ok = _bad(lambda e: e["scenarios"]["unknown-tenant"].update(status=200, public_code="ok", dispatched=True))
    assert unknown_ok, "unknown success must fail"
    # [matrix 8] envelope-only denial (internal code omitted).
    assert _bad(lambda e: e["scenarios"]["dormant-not-ready"].update(internal_code=None)), "an omitted internal code must fail"
    # [matrix 9/10] swapped denial codes.
    assert _bad(lambda e: e["scenarios"]["dormant-not-ready"].update(internal_code="tenant_access_denied")), "dormant code swap must fail"
    assert _bad(lambda e: e["scenarios"]["unknown-tenant"].update(internal_code="tenant_not_ready")), "unknown code swap must fail"
    # [matrix 11/12] denied dispatch / denied pool acquisition.
    assert _bad(lambda e: e["scenarios"]["unknown-tenant"].update(route_events=1)), "denied dispatch must fail"
    assert _bad(lambda e: e["scenarios"]["dormant-not-ready"].update(pool_delta=1)), "denied pool acquisition must fail"
    assert _bad(lambda e: e["scenarios"]["unknown-tenant"].update(new_pool_keys=1)), "a denied tenant bind must fail"
    # [matrix 18] leftover listener/thread; undrained pools.
    assert _bad(lambda e: e.update(ports_released=False)), "an unreleased port must fail"
    assert _bad(lambda e: e.update(shutdown_problems=["thread alive"])), "a live thread must fail"
    assert _bad(lambda e: e.update(pools_drained=False)), "undrained pools must fail"
    # [matrix 19/22/23] any observable state mutation (temporary row, standing-row drift, dormant DB).
    assert _bad(lambda e: e.update(before_equals_after=False, state_diff=["tenant_ids"])), "a state delta must fail"
    # [matrix 24] omitted comparison surfaces as an incomplete record.
    assert _bad(lambda e: e.update(before_equals_after=None)), "a missing before/after verdict must fail"
    # [matrix 25] a skipped scenario can never count as passed.
    assert _bad(lambda e: e["scenarios"]["control-plane-unavailable"].update(executed=False)), "a skipped scenario must fail"
    assert _bad(lambda e: e["scenarios"].pop("beta-success")), "a missing scenario must fail"
    assert _bad(lambda e: e["scenarios"].update(extra={"executed": True})), "an unexpected extra scenario must fail"
    # Environment leakage and the success-row witnesses.
    assert _bad(lambda e: e.update(env_restored=False)), "unrestored environment must fail"
    assert _bad(lambda e: e["scenarios"]["alpha-success"].update(readback_reused=False)), "a non-reused readback must fail"
    assert _bad(lambda e: e["scenarios"]["alpha-success"].update(other_pool_delta=1)), "an other-tenant pool touch must fail"
    assert _bad(lambda e: e["scenarios"]["alpha-success"].update(route_events=0)), "a success row without its Route event must fail"


def test_manual_only_entry_is_registered_and_workflow_untouched() -> None:
    tree = _tree(_COMPLETENESS_GUARD)
    mapping: Optional[Dict[str, str]] = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "MANUAL_ONLY_EXCEPTIONS" for t in node.targets):
            mapping = ast.literal_eval(node.value)
    assert isinstance(mapping, dict), "MANUAL_ONLY_EXCEPTIONS must stay a plain literal dict"
    assert _MANUAL_ONLY_KEY in mapping, "the Smoke C V2 proof must be a registered MANUAL_ONLY exception"
    assert isinstance(mapping[_MANUAL_ONLY_KEY], str) and mapping[_MANUAL_ONLY_KEY].strip(), "the exception needs a written justification"
    for preserved in (
        "tests/control_plane/requires_pg/test_b3a_multi_database_topology.py",
        "tests/control_plane/requires_pg/test_pg_b5_standing_topology.py",
        "tests/control_plane/requires_pg/test_pg_b5_standing_auth_fixture.py",
    ):
        assert preserved in mapping, f"a pre-existing MANUAL_ONLY exception was dropped: {preserved}"
    workflow_text = _WORKFLOW.read_text(encoding="utf-8")
    assert _MANUAL_ONLY_KEY not in workflow_text, "the hosted live-PG workflow must NOT enroll the new harness in this slice"
    assert _FAMILY_NAME not in workflow_text, "the hosted live-PG workflow must stay untouched by this slice"


def test_no_production_import_of_the_new_modules() -> None:
    offenders: List[str] = []
    for path in _scan.py_files():
        if _TESTS_DIR in path.parents:
            continue
        if any(_FAMILY_NAME in mod for mod in _scan.imported_modules(path)):
            offenders.append(_scan.relposix(path))
    assert not offenders, f"production code must never import the Smoke C V2 modules: {offenders}"
    synthetic = _import_names_of(f"import {_FAMILY_NAME}\n")
    assert any(_FAMILY_NAME in m for m in synthetic), "production-import census went vacuous"


def test_runbook_obligations_and_no_overclaim() -> None:
    text = _RUNBOOK.read_text(encoding="utf-8")
    required = (
        "plan",
        "run",
        "status",
        "smoke_c_integrated_live_proof.py",
        "SMOKE-C-SPEC-01",
        "b5_standing_alpha",
        "b5_standing_beta",
        "b5_standing_dormant",
        "tenant_not_ready",
        "tenant_access_denied",
        "loopback",
        "ephemeral",
        "zero-mutation",
        "no teardown command",
        "never printed",
        "B5-BLK-4 OPEN.",
        "Physical Multi-Database MVP mandatory and NOT complete.",
    )
    missing = [needle for needle in required if needle not in text]
    assert not missing, f"runbook lost required needle(s): {missing}"
    lowered = text.lower()
    for banned in (_CLOSURE_NEEDLE, _MVP_DONE_NEEDLE, _TOKEN_NEEDLE, _PEM_NEEDLE):
        assert banned not in text, f"forbidden needle {banned!r} in the runbook"
    for banned_phrase in _SMOKE_PASSED_NEEDLES:
        assert banned_phrase not in lowered, f"the runbook must never claim {banned_phrase!r}"


def test_no_token_pem_or_closure_material_in_new_files() -> None:
    for path in (_OPS, _PROOF, _RUNBOOK, pathlib.Path(__file__).resolve()):
        text = path.read_text(encoding="utf-8")
        assert _TOKEN_NEEDLE not in text, f"token-shaped literal in {path.name}"
        assert _PEM_NEEDLE not in text, f"PEM header in {path.name}"
        assert _CLOSURE_NEEDLE not in text, f"closure claim in {path.name}"
        assert _MVP_DONE_NEEDLE not in text, f"MVP-completion claim in {path.name}"
    assert _TOKEN_NEEDLE in ("e" + "yJhbGciOi"), "token detector went vacuous"
    assert _PEM_NEEDLE in ("-----BE" + "GIN RSA PRIVATE KEY-----"), "PEM detector went vacuous"


def test_inertness_non_vacuity() -> None:
    keygen = ast.parse("import os\nKP = generate_keypair()\n")
    assert _inertness_problems(keygen), "module-level work at import must be rejected"
    serve = ast.parse("import os\nserve()\n")
    assert _inertness_problems(serve), "a module-level serve call must be rejected"
    clean = ast.parse('"""doc"""\nimport os\nX = 1\ndef f():\n    pass\nif __name__ == "__main__":\n    f()\n')
    assert not _inertness_problems(clean), "the canonical inert shape must PASS"


if __name__ == "__main__":
    _scan.run(
        [
            test_surface_files_exist_and_family_is_closed,
            test_ops_import_inert_with_stdlib_only_top_imports,
            test_proof_import_inert_and_subprocess_free,
            test_no_forbidden_imports_anywhere_in_the_new_files,
            test_real_composition_seams_only,
            test_seam_census_non_vacuity,
            test_command_surface_is_exactly_plan_run_status,
            test_subprocess_seams_are_status_only_and_builder_bound,
            test_subprocess_census_non_vacuity,
            test_sql_surface_is_readonly_and_pinned,
            test_sql_census_non_vacuity,
            test_no_write_reachability_in_either_file,
            test_env_writes_are_patch_scoped_loopback_only_and_port_free,
            test_env_census_non_vacuity,
            test_run_structure_finally_cleanup_and_before_after,
            test_run_structure_non_vacuity,
            test_before_after_verdict_semantic_pin_non_vacuity,
            test_snapshot_source_integrity_non_vacuity,
            test_snapshot_witness_census_is_pinned,
            test_before_after_verdict_is_consumed_by_the_claim_path,
            test_verdict_consumption_non_vacuity,
            test_readiness_is_bounded,
            test_status_claim_is_evidence_gated,
            test_scenario_matrix_is_pinned_exactly,
            test_scenario_matrix_non_vacuity,
            test_evaluators_pass_good_evidence_and_reject_every_state_mutation,
            test_manual_only_entry_is_registered_and_workflow_untouched,
            test_no_production_import_of_the_new_modules,
            test_runbook_obligations_and_no_overclaim,
            test_no_token_pem_or_closure_material_in_new_files,
            test_inertness_non_vacuity,
        ]
    )
