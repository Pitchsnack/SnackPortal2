"""PRD B5-4A V2 — standing-auth-fixture operator boundary pins (default suite; no DB).

Non-vacuously pins the safety boundaries of the B5-4A V2 operator tool
(``tests/control_plane/requires_pg/b5_standing_auth_fixture.py``) and its proof/runbook without touching a
database:

* import-inert module structure (top-level = docstring/imports/constants/defs/main-guard only) with a
  STDLIB-ONLY top import surface; every backend/provider import is lazy, inside commands;
* no static database-driver / JWT / crypto / threading / socket / http import in either new file; the
  proof may not import subprocess at all (only the operator holds the one sanctioned subprocess seam);
* NEITHER new file imports the original B5-4 harness (``b5_standing_topology``) — the operator reaches it
  ONLY through one pinned subprocess call whose argv is token-closed to the status subcommand (no apply /
  no removal token is constructible) AND whose run site is AST-bound to exactly ``_b5_4_status_argv()``:
  inline argv (even with the status token), aliases, and alternate builders are rejected, preserving the
  B5-5 no-new-invocation census;
* the operator's own command surface is EXACTLY ``plan`` / ``apply`` / ``status`` — structurally (the
  ``add_parser`` census) and behaviorally (an unknown subcommand exits non-zero); the removal-command
  token and the temporary smoke-row prefix appear NOWHERE in either new file (text-level, dynamic
  needles);
* no direct SQL mutation anywhere: the FULL cursor sink surface (``execute`` / ``executemany`` /
  ``executescript`` / psycopg3 ``copy`` / psycopg2 ``copy_expert`` / ``copy_from`` / ``copy_to``) is
  censused — the operator's ONLY sink is the single read-only ``pg_database`` execute probe (its argument
  the pinned ``_PG_DATABASE_SQL`` name, value pinned verbatim), the proof's sinks are read-only ``SELECT``
  executes whose argument must STATICALLY RESOLVE, and no string constant in either file carries a
  mutating-SQL keyword (case-insensitive, word-boundary; two pinned benign whole-constant literals
  exempt). A strict static-string evaluator FOLDS ``ast.BinOp(Add)`` concatenations before the census so a
  split verb (``"COP" + "Y ..."``) is caught as ``COPY``; a non-static / f-string / computed sink argument
  is blocking (F3-B);
* no raw/private Control-DB connection reachability: the raw ``._conn`` property, ``getattr(..., "_conn")``,
  any cursor/copy/commit/rollback/write/write_row path rooted at ``cp.store``, and any bare
  ``commit`` / ``rollback`` / ``write`` / ``write_row`` call are all forbidden; the ONLY sanctioned private
  handle is the ``_conn_cache`` close in ``_close_plane`` — pinned to its exact reviewed shape and exact
  count (one attribute + one getattr string, both rooted at ``cp.store``, both inside ``_close_plane``);
  raw cursor use is confined to a LOCAL short-lived connection (never ``cp.store``) (F3-A/F3-C);
* supported write APIs only: exactly one ``register_tenant`` call (dormant tenant id, pinned actor) and
  exactly one ``add_membership`` call site (fixture principal, ``Role.TENANT_AGENT``); the full mutating
  ban-list (store puts / CAS / audit append / lifecycle transitions / onboarding / recovery /
  deprovision / file writes) is enforced on the operator, and the proof performs NO direct store write;
* the composition posture is pinned: the operator's only env writes set the control store to postgres and
  FORCE the three live-side selectors to in_memory, and the compose helper must assert both the durable
  store and the mixed-posture onboarding deny-guard (defense in depth against a provisioning-capable
  plane);
* both effectful commands consult the ORIGINAL B5-4 status FIRST (structural order pins), and the exact
  four intended rows (three memberships + one dormant tenant; no fifth row) are pinned via the module's
  own constants and pure classification/evaluation predicates;
* the state-shaped mutation matrix runs here as planted-snapshot companions: every named status check
  must reject its mutant facts (membership omitted/drifted, tenant Ready, reference drift, secret
  material, physical database, duplicate/missing audit provenance, smoke residue, unrelated fifth row) —
  and the source-shaped matrix runs as planted-source companions (SQL delete/truncate, removal command,
  B5-4 apply argv, omitted B5-4 delegation, widened/computed manual-only entry) plus the Fix R1 variant
  companions (lowercase ``executemany``/``executescript``/``copy_expert`` mutations and inline run-site
  argv — apply and status) and the Fix R2 F3 companions (psycopg3 ``cursor.copy``, split-string / f-string
  COPY, ``copier.write``/``write_row``, ``cp.store._conn`` cursor/commit/rollback, ``getattr(..., "_conn")``,
  raw-connection aliases, extra ``_conn_cache`` occurrences, and the exact reproduced F3 proof of concept);
* the proof is a registered, justified MANUAL_ONLY exception of the live-PG run-set completeness guard
  (plain-literal entry; the original B5-4 entry is preserved) and production code never imports the
  operator;
* the runbook carries the required documentation needles (four rows, membership-before-readiness
  rationale, no-removal statement, resumable partial apply, standing-status block) and can never claim
  Smoke C success or B5-BLK-4 closure (dynamic banned needles).

Pure stdlib; standalone-runnable:
  python tests/architecture/test_b5_standing_auth_fixture_boundaries.py

B5-BLK-4 remains OPEN; the Physical Multi-Database MVP remains mandatory and is NOT completed by this
guard or the fixture it pins. Smoke C is NOT executed here.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_OPS = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "b5_standing_auth_fixture.py"
_PROOF = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "test_pg_b5_standing_auth_fixture.py"
_RUNBOOK = _scan.REPO_ROOT / "infrastructure" / "runbooks" / "b5_standing_auth_fixture.md"
_COMPLETENESS_GUARD = _scan.BACKEND_ROOT / "tests" / "architecture" / "test_live_pg_workflow_runset_completeness.py"
_TESTS_DIR = _scan.BACKEND_ROOT / "tests"

_NEW_PY_FILES = (_OPS, _PROOF)

# Dynamic needles — built so THIS guard never satisfies its own bans.
_REMOVAL_TOKEN = "tear" + "down"
_SMOKE_NEEDLE = "smoke" + "_c_"
_CLOSURE_NEEDLE = "B5-BLK-4 CLO" + "SED"
_MVP_DONE_NEEDLE = "MVP COMPL" + "ETE"
_SMOKE_PASSED_NEEDLES = ("smoke c pass" + "ed", "smoke c succe" + "eded", "smoke c has been exec" + "uted")

_OPS_TOP_IMPORT_ALLOW = {"__future__", "argparse", "importlib", "os", "pathlib", "subprocess", "sys", "typing", "urllib.parse"}
_FORBIDDEN_IMPORTS = ("psycopg", "psycopg2", "asyncpg", "sqlalchemy", "jwt", "cryptography", "threading", "socket", "http")
_FORBIDDEN_NAMES = ("serve_forever", "ThreadingHTTPServer", "ThreadingMixIn")

# Case-insensitive, word-boundary mutating-SQL keyword census over STRING CONSTANTS (SELECT is the only
# sanctioned SQL verb on this surface; lowercase/mixed-case near-misses are banned equally).
_MUTATING_SQL_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|TRUNCATE|ALTER|DROP|CREATE|MERGE|REPLACE|GRANT|REVOKE|COPY)\b",
    re.IGNORECASE,
)
# EVERY SQL-execution-capable cursor method is a sink — the batch/script/copy near-neighbors count
# exactly like ``execute`` itself (F1: a lowercase executemany DELETE must be as loud as execute DELETE;
# F3: psycopg3's bare ``cursor.copy`` bulk-write primitive is a sink too — COPY regardless of the
# psycopg2 ``copy_expert``/``copy_from``/``copy_to`` vs psycopg3 ``copy`` naming).
_SQL_SINK_METHODS = frozenset({"execute", "executemany", "executescript", "copy", "copy_expert", "copy_from", "copy_to"})

# F3 raw-connection reachability. The durable ControlStore caches a real psycopg connection behind the
# ``_conn`` property (``PostgresControlStore._conn``); ``cp.store._conn`` therefore reaches the live
# Control DB with cursor/copy/commit/rollback/write primitives that bypass the supported write APIs. The
# ONLY sanctioned private-handle use on this surface is the ``_conn_cache`` close in ``_close_plane`` (the
# 07D finally idiom); the raw ``_conn`` property and every write/transaction primitive are forbidden.
_RAW_CONN_ATTR = "_conn"  # the raw cached connection property (DISTINCT from the sanctioned _conn_cache)
_CONN_CACHE_ATTR = "_conn_cache"  # the sanctioned cleanup handle — exact reviewed shape + exact count only
_RAW_STORE_OP_METHODS = frozenset({"cursor", "copy", "commit", "rollback", "write", "write_row"})
_FORBIDDEN_CONN_CALLS = frozenset({"commit", "rollback", "write", "write_row"})  # banned outright, any root
# The case-insensitive census would otherwise flag two benign committed literals (word-boundary keyword
# hits that are not SQL): the codec error-handler value at the operator's one subprocess seam
# (errors="replace") and the cmd_plan intent-line prose fragment. EXACT whole-constant matches only —
# neither parses as a mutating statement, and every sink argument is independently pinned to the
# read-only probe/SELECT surface below. Do not widen this set.
_SQL_CENSUS_EXEMPT_EXACT = frozenset({"replace", " absent row(s) to create)"})
_OPS_ALLOWED_SQL_PREFIX = "SELECT 1 FROM pg_database"

# The operator's mutating-call ban-list (attribute-call names). The two supported write APIs are pinned
# separately; everything else that could mutate the Control DB, the lifecycle, files, or the environment
# of another tenant is banned outright in the operator.
_OPS_BANNED_CALLS = frozenset(
    {
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
        "verify",
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
        "executemany",
        "executescript",
        "copy",
        "copy_expert",
        "copy_from",
        "copy_to",
        "write",
        "write_row",
        "commit",
        "rollback",
    }
)
# The proof drives everything through the operator CLI: it may touch the (outside-repo) secret-root file
# for its restored negative leg, but it may never write to the Control DB directly.
_PROOF_BANNED_CALLS = frozenset(
    {
        "put_tenant",
        "put_membership",
        "put_federation",
        "put_directory_record",
        "compare_and_swap_tenant",
        "append_audit",
        "add_membership",
        "register_tenant",
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
        "executemany",
        "executescript",
        "copy",
        "copy_expert",
        "copy_from",
        "copy_to",
        "write",
        "write_row",
        "commit",
        "rollback",
    }
)

_EXPECTED_SUBCOMMANDS = {"plan", "apply", "status"}
_EXPECTED_INTENDED_ROWS = (
    "membership:b5_standing_alpha",
    "membership:b5_standing_beta",
    "membership:b5_standing_dormant",
    "tenant:b5_standing_dormant",
)
_MANUAL_ONLY_KEY = "tests/control_plane/requires_pg/test_pg_b5_standing_auth_fixture.py"
_B5_4_MANUAL_ONLY_KEY = "tests/control_plane/requires_pg/test_pg_b5_standing_topology.py"

_RUNBOOK_REQUIRED_NEEDLES = (
    "b5_standing_member",
    "b5_standing_alpha",
    "b5_standing_beta",
    "b5_standing_dormant",
    "TENANT_AGENT",
    "Registered",
    "tenant/b5_standing_dormant/dsn@1",
    "membership BEFORE readiness",
    "tenant_access_denied",
    "tenant_not_ready",
    "control-store-standalone",
    "physically incapable",
    "no teardown command and no delete path",
    "safely resumable",
    "fails closed",
    "6/6",
    "Smoke C V2",
    "Smoke C has not yet run",
    "Smoke C not executed.",
    "B5-BLK-4 OPEN.",
    "Physical Multi-Database MVP mandatory and NOT complete.",
)


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _load_ops_module():  # noqa: ANN202  (test helper)
    """Load the operator by path (behavioral probes + the pure mutation-matrix predicates). Loading in
    the default suite itself proves import-inertness: no configuration, database, or network exists here."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("b5_standing_auth_fixture_under_pin", _OPS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _string_constants(tree: ast.AST) -> List[str]:
    return [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def _attr_call_names(tree: ast.AST) -> Set[str]:
    return {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"required function {name!r} not found (fail closed)")


def _first_call_lineno(root: ast.AST, name: str) -> Optional[int]:
    linenos = [
        node.lineno
        for node in ast.walk(root)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == name) or (isinstance(node.func, ast.Attribute) and node.func.attr == name)
        )
    ]
    return min(linenos) if linenos else None


# ------------------------------------------------------------------------------------------------
# shared predicates (used by the real pins AND the planted-mutant companions)
# ------------------------------------------------------------------------------------------------
def _sql_sink_calls(tree: ast.AST) -> List[Tuple[str, Optional[ast.expr]]]:
    """Every SQL-execution-capable cursor call: ``(method name, first positional argument or None)``.

    The census subject is the FULL sink surface (``_SQL_SINK_METHODS``) — counting only ``execute``
    is exactly the F1 evasion (a lowercase ``executemany`` DELETE slipping through). A sink call
    without a positional first argument still counts (fail closed: its SQL cannot be inspected)."""
    out: List[Tuple[str, Optional[ast.expr]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in _SQL_SINK_METHODS:
            out.append((node.func.attr, node.args[0] if node.args else None))
    return out


def _static_sql_string(node: Optional[ast.expr]) -> Optional[str]:
    """Strict guard-only SQL-expression evaluator (F3-B). Resolves ONLY:

    * ``ast.Constant(str)``;
    * ``ast.BinOp(Add)`` whose BOTH operands recursively resolve to strings (folding ``"COP" + "Y ..."``
      into ``"COPY ..."``).

    Everything else — ``Name`` / ``Attribute`` / f-string (``JoinedStr``) / ``Call`` / ``Subscript`` /
    conditional expression / ``.format``/``.join``/``.replace`` construction / any unsupported node —
    is non-static and returns ``None`` (fail closed: a computed SQL argument cannot be inspected)."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _static_sql_string(node.left)
        right = _static_sql_string(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _folded_sql_strings(tree: ast.AST) -> List[str]:
    """Every ``ast.BinOp(Add)`` chain in the tree that statically folds to a string — the split-verb
    evasion surface (``"COP" + "Y ..."``). Folded strings are censused with NO exemption: there is no
    legitimate reason to split a benign literal across ``+`` on this surface."""
    out: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            folded = _static_sql_string(node)
            if folded is not None:
                out.append(folded)
    return out


def _mutating_sql_census(tree: ast.AST) -> List[str]:
    """Case-insensitive, word-boundary mutating-SQL keyword sweep. Runs over every whole string constant
    (skipping ONLY the two pinned benign whole-constant literals ``_SQL_CENSUS_EXEMPT_EXACT``) AND — after
    static folding — over every ``+``-concatenated string expression (F3: ``"COP" + "Y ..."`` folds to
    ``COPY`` and is caught; folded expressions get no exemption)."""
    problems: List[str] = []
    for value in _string_constants(tree):
        if value in _SQL_CENSUS_EXEMPT_EXACT:
            continue
        match = _MUTATING_SQL_RE.search(value)
        if match:
            problems.append(f"mutating-SQL keyword {match.group(0)!r} in a string constant: {value[:60]!r}")
    for folded in _folded_sql_strings(tree):
        match = _MUTATING_SQL_RE.search(folded)
        if match:
            problems.append(f"mutating-SQL keyword {match.group(0)!r} in a folded string expression: {folded[:60]!r}")
    return problems


def _receiver_is_cp_store_rooted(node: Optional[ast.expr]) -> bool:
    """True iff the attribute/value chain bottoms out at ``cp.store`` (``Name('cp') -> Attribute('store')``).

    Reconstructs the chain so a raw path like ``cp.store._conn.cursor`` is recognized regardless of depth
    (F3-C: the guard must inspect attribute chains, not just the leaf method name)."""
    current = node
    while isinstance(current, ast.Attribute):
        if current.attr == "store" and isinstance(current.value, ast.Name) and current.value.id == "cp":
            return True
        current = current.value
    return False


def _raw_conn_problems(tree: ast.AST) -> List[str]:
    """F3-C raw-connection reachability. Reject unreviewed private/raw Control-DB connection access:

    * any ``._conn`` attribute access (the raw cached-connection property — NOT the sanctioned
      ``_conn_cache``);
    * any ``getattr(..., "_conn")`` dynamic access;
    * any cursor/copy/commit/rollback/write/write_row path ROOTED at ``cp.store``;
    * any bare ``commit`` / ``rollback`` / ``write`` / ``write_row`` call, regardless of receiver."""
    problems: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == _RAW_CONN_ATTR:
            problems.append("raw private-connection attribute access '._conn' is forbidden (use the supported store APIs)")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == _RAW_CONN_ATTR
        ):
            problems.append("getattr(..., '_conn') dynamic raw-connection access is forbidden")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            method = node.func.attr
            if method in _RAW_STORE_OP_METHODS and _receiver_is_cp_store_rooted(node.func.value):
                problems.append(f"raw '{method}' path rooted at cp.store is forbidden (bypasses the supported write APIs)")
            if method in _FORBIDDEN_CONN_CALLS:
                problems.append(f"forbidden connection call '{method}' is banned outright (no write/transaction primitive on this surface)")
    return problems


def _conn_cache_occurrences(tree: ast.AST) -> Tuple[List[ast.Attribute], List[ast.Constant]]:
    """Every textual ``_conn_cache`` use: attribute accesses (``cp.store._conn_cache``) and getattr string
    args (``getattr(..., "_conn_cache")``). The reviewed shape has exactly one of each, both in
    ``_close_plane`` — any additional occurrence is blocking (F3-C)."""
    attrs = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == _CONN_CACHE_ATTR]
    strings = [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and n.value == _CONN_CACHE_ATTR]
    return attrs, strings


def _ops_sql_problems(tree: ast.AST) -> List[str]:
    """The operator's raw-SQL rules: exactly ONE SQL sink, an ``execute``, read-only, the pg_database
    probe. Every other sink method (``executemany`` / ``executescript`` / ``copy_*``) is forbidden.

    The sanctioned site passes the module constant ``_PG_DATABASE_SQL`` (whose VALUE is pinned by the
    loaded-module check in the real test and swept by the mutating-SQL census below); an inline constant
    is accepted only if it IS the probe text — anything else fails."""
    problems: List[str] = []
    sinks = _sql_sink_calls(tree)
    if len(sinks) != 1:
        problems.append(f"expected exactly one SQL execution sink, found {len(sinks)}")
    for method, arg in sinks:
        if method != "execute":
            problems.append(f"forbidden SQL execution sink method {method!r} (only the single read-only execute probe is sanctioned)")
            continue
        # The sole sanctioned non-static sink argument is the pinned ``_PG_DATABASE_SQL`` Name (its VALUE
        # is pinned verbatim by the loaded-module assertion in the real test); every other argument must
        # STATICALLY RESOLVE to the read-only probe text (F3-B fail-closed).
        named_probe = isinstance(arg, ast.Name) and arg.id == "_PG_DATABASE_SQL"
        folded = _static_sql_string(arg)
        inline_probe = folded is not None and folded.startswith(_OPS_ALLOWED_SQL_PREFIX)
        if not (named_probe or inline_probe):
            problems.append("an execute argument is not the single sanctioned read-only pg_database probe (static resolution required)")
    problems.extend(_mutating_sql_census(tree))
    return problems


def _proof_sql_problems(tree: ast.AST) -> List[str]:
    """The proof's raw-SQL rules: every SQL sink is an ``execute`` whose argument STATICALLY RESOLVES to a
    read-only SELECT statement (F3-B fail-closed: a non-static / missing / f-string / computed argument is
    blocking); the batch/script/copy sink methods are forbidden outright."""
    problems: List[str] = []
    for method, arg in _sql_sink_calls(tree):
        if method != "execute":
            problems.append(f"forbidden SQL execution sink method {method!r} in the proof (read-only SELECT executes only)")
            continue
        folded = _static_sql_string(arg)
        if folded is None:
            problems.append("a proof execute argument is not a statically-resolvable string (fail closed)")
            continue
        if not folded.lstrip().startswith("SELECT"):
            problems.append("a proof execute argument does not resolve to a read-only SELECT statement")
    problems.extend(_mutating_sql_census(tree))
    return problems


def _subparser_names(tree: ast.AST) -> Set[str]:
    names: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_parser" and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                names.add(first.value)
    return names


def _argv_builder_problems(fn: ast.FunctionDef) -> List[str]:
    """The B5-4 subprocess argv builder must return EXACTLY
    ``[sys.executable, str(_B5_4_OPS), _B5_4_STATUS_COMMAND]`` — token-closed: no string constant other
    than the docstring may appear, so no apply/removal token is constructible."""
    problems: List[str] = []
    returns = [node for node in ast.walk(fn) if isinstance(node, ast.Return)]
    if len(returns) != 1 or not isinstance(returns[0].value, ast.List):
        return ["the argv builder must have exactly one return of a list literal"]
    elts = returns[0].value.elts
    if len(elts) != 3:
        problems.append(f"argv must have exactly 3 tokens, found {len(elts)}")
        return problems
    e0, e1, e2 = elts
    if not (isinstance(e0, ast.Attribute) and e0.attr == "executable" and isinstance(e0.value, ast.Name) and e0.value.id == "sys"):
        problems.append("argv[0] must be sys.executable")
    if not (
        isinstance(e1, ast.Call)
        and isinstance(e1.func, ast.Name)
        and e1.func.id == "str"
        and len(e1.args) == 1
        and isinstance(e1.args[0], ast.Name)
        and e1.args[0].id == "_B5_4_OPS"
    ):
        problems.append("argv[1] must be str(_B5_4_OPS)")
    if not (isinstance(e2, ast.Name) and e2.id == "_B5_4_STATUS_COMMAND"):
        problems.append("argv[2] must be the _B5_4_STATUS_COMMAND constant (never an inline token)")
    body_constants = [node.value for node in ast.walk(fn) if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    docstring = ast.get_docstring(fn, clean=False)
    for value in body_constants:
        if value != docstring:
            problems.append(f"stray string token inside the argv builder: {value!r}")
    return problems


def _subprocess_run_calls(tree: ast.AST) -> List[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
    ]


def _run_site_argv_problems(call: ast.Call) -> List[str]:
    """The sanctioned ``subprocess.run`` call must receive EXACTLY ``_b5_4_status_argv()`` as its argv:
    an ``ast.Call`` whose func is the ``ast.Name`` ``_b5_4_status_argv`` with no positional and no
    keyword arguments (F2: pinning the builder alone proves nothing if the run site never uses it).
    Inline argv is rejected even when it carries the status token — the run site must be bound to the
    single reviewed builder; aliases and alternate builders fail the exact-name requirement."""
    if not call.args:
        return ["the subprocess.run call carries no positional argv argument"]
    argv = call.args[0]
    if not isinstance(argv, ast.Call):
        return ["the subprocess.run argv is not a call to the reviewed builder (inline argv is banned, even status)"]
    if not (isinstance(argv.func, ast.Name) and argv.func.id == "_b5_4_status_argv"):
        return ["the subprocess.run argv is not _b5_4_status_argv() (aliases and alternate builders are banned)"]
    if argv.args or argv.keywords:
        return ["_b5_4_status_argv must be called with no positional and no keyword arguments"]
    return []


def _manual_only_mapping(guard_tree: ast.Module) -> Dict[str, str]:
    for node in ast.walk(guard_tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "MANUAL_ONLY_EXCEPTIONS" for t in node.targets):
            mapping = ast.literal_eval(node.value)  # plain literals ONLY — a computed entry raises here
            assert isinstance(mapping, dict)
            return {str(k): str(v) for k, v in mapping.items()}
    raise AssertionError("MANUAL_ONLY_EXCEPTIONS not found in the completeness guard")


def _runbook_problems(text: str) -> List[str]:
    problems = [f"missing:{needle}" for needle in _RUNBOOK_REQUIRED_NEEDLES if needle not in text]
    lowered = text.lower()
    for banned in (_CLOSURE_NEEDLE, _MVP_DONE_NEEDLE):
        if banned in text:
            problems.append(f"forbidden:{banned}")
    for banned in _SMOKE_PASSED_NEEDLES:
        if banned in lowered:
            problems.append(f"forbidden:{banned}")
    return problems


def _canonical_facts(module) -> Dict[str, object]:  # noqa: ANN001  (test helper)
    return {
        "membership_roles": {tid: module._ROLE_VALUE for tid in module.MEMBERSHIP_TENANT_IDS},
        "membership_count": len(module.MEMBERSHIP_TENANT_IDS),
        "tenant_ids": [*module.READY_TENANT_IDS, module.DORMANT_TENANT_ID],
        "dormant_row": dict(module._EXPECTED_DORMANT_ROW),
        "dormant_read_state": {"tenant_id": module.DORMANT_TENANT_ID, "lifecycle_state": "Registered", "ready": False},
        "dormant_member": True,
        "register_audit": [{"actor": module._ACTOR, "from_state": None, "to_state": "Registered"}],
        "dormant_secret_file": False,
        "dormant_secret_env": False,
        "cp_adapter_resolves": False,
        "dbr_adapter_resolves": False,
        "dormant_database_present": False,
        "smoke_residue_count": 0,
    }


def _problem_for(module, facts: Dict[str, object], check_name: str) -> Optional[str]:  # noqa: ANN001
    for name, problem in module._evaluate(facts):
        if name == check_name:
            return problem
    raise AssertionError(f"status check {check_name!r} not found (fail closed)")


# ------------------------------------------------------------------------------------------------
# the real pins
# ------------------------------------------------------------------------------------------------
def test_files_exist() -> None:
    for path in (_OPS, _PROOF, _RUNBOOK, _COMPLETENESS_GUARD):
        assert path.is_file(), f"B5-4A V2 surface file missing: {path}"


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
    for path in _NEW_PY_FILES:
        rp = _scan.relposix(path)
        mods = _scan.imported_modules(path)
        for mod in mods:
            top = mod.split(".")[0]
            assert top not in _FORBIDDEN_IMPORTS, f"forbidden import '{mod}' in {rp} (driver/vendor/threading/socket/http banned)"
            assert "b5_standing_topology" not in mod, f"{rp} must never import the original B5-4 harness (subprocess-only)"
        source = path.read_text(encoding="utf-8")
        for name in _FORBIDDEN_NAMES:
            assert name not in source, f"forbidden name '{name}' in {rp}"
    proof_mods = {m.split(".")[0] for m in _scan.imported_modules(_PROOF)}
    assert "subprocess" not in proof_mods, "the proof must not import subprocess (only the operator holds that seam)"
    # Non-vacuity: the import census detects a synthetic harness import.
    synthetic = [a.name for n in ast.walk(ast.parse("import b5_standing_topology\n")) if isinstance(n, ast.Import) for a in n.names]
    assert any("b5_standing_topology" in m for m in synthetic), "harness-import detector went vacuous"


def test_no_removal_token_or_smoke_prefix_in_new_files() -> None:
    for path in _NEW_PY_FILES:
        source = path.read_text(encoding="utf-8")
        assert _REMOVAL_TOKEN not in source, f"the removal-command token must not appear in {path.name}"
        assert _SMOKE_NEEDLE not in source, f"the temporary smoke-row prefix literal must not appear in {path.name}"
        assert "--confirm" not in source, f"no confirmation-flag surface may exist in {path.name} (nothing destructive exists)"
    # Non-vacuity: both needles detect planted samples.
    assert _REMOVAL_TOKEN in ("tear" + "down teardown-sample"), "removal-token detector went vacuous"
    assert _SMOKE_NEEDLE in ("smoke" + "_c_tenant_row"), "smoke-prefix detector went vacuous"


def test_ops_sql_surface_is_single_readonly_probe() -> None:
    problems = _ops_sql_problems(_tree(_OPS))
    assert not problems, f"operator raw-SQL pins failed: {problems}"
    module = _load_ops_module()
    assert module._PG_DATABASE_SQL == "SELECT 1 FROM pg_database WHERE datname = %s", "the probe constant is pinned verbatim"


def test_proof_sql_surface_is_readonly() -> None:
    problems = _proof_sql_problems(_tree(_PROOF))
    assert not problems, f"proof raw-SQL pins failed: {problems}"


def test_sql_pin_non_vacuity() -> None:
    # [matrix 1] direct SQL delete and [matrix 2] truncate are rejected by the SAME predicates.
    delete_mutant = ast.parse('def f(cur):\n    cur.execute("DELETE FROM control_memberships WHERE tenant_id = %s", (t,))\n')
    truncate_mutant = ast.parse('def f(cur):\n    cur.execute("TRUNCATE control_audit")\n')
    second_probe_mutant = ast.parse(
        'def f(cur):\n    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (t,))\n'
        '    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (u,))\n'
    )
    assert _ops_sql_problems(delete_mutant), "pin must reject a direct SQL delete mutant"
    assert _proof_sql_problems(delete_mutant), "proof pin must reject a direct SQL delete mutant"
    assert _ops_sql_problems(truncate_mutant), "pin must reject a truncate mutant"
    assert _proof_sql_problems(truncate_mutant), "proof pin must reject a truncate mutant"
    assert _ops_sql_problems(second_probe_mutant), "pin must reject a second operator execute site"
    canonical = ast.parse('def f(cur):\n    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (t,))\n')
    assert not _ops_sql_problems(canonical), "the canonical single probe must PASS"


def test_sql_sink_census_non_vacuity() -> None:
    # [Fix R1 — variants V1..V4 of matrix 1/2] the batch/script/copy sinks with LOWERCASE mutating SQL
    # are rejected by the SAME production predicates that pin the committed files (F1 closure).
    variant_mutants = {
        "V1 lowercase executemany DELETE": (
            'def f(cur):\n    cur.executemany("delete from control_memberships where tenant_id = %s", rows)\n'
        ),
        "V2 lowercase executemany TRUNCATE": 'def f(cur):\n    cur.executemany("truncate control_audit", rows)\n',
        "V3 lowercase executescript DELETE": 'def f(cur):\n    cur.executescript("delete from control_memberships;")\n',
        "V4 copy_expert COPY": 'def f(cur):\n    cur.copy_expert("copy control_memberships from stdin", stream)\n',
        "copy_from sink": 'def f(cur):\n    cur.copy_from(stream, "control_memberships")\n',
        "copy_to sink": 'def f(cur):\n    cur.copy_to(stream, "control_memberships")\n',
        "mixed-case execute Delete": 'def f(cur):\n    cur.execute("Delete From control_memberships Where tenant_id = %s", (t,))\n',
        "argument-less sink": "def f(cur):\n    cur.executescript()\n",
        "sink beside the sanctioned probe": (
            'def f(cur):\n    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (t,))\n'
            '    cur.executemany("delete from control_memberships where tenant_id = %s", rows)\n'
        ),
    }
    for label, source in variant_mutants.items():
        mutant = ast.parse(source)
        assert _ops_sql_problems(mutant), f"ops SQL pin must reject variant mutant: {label}"
        assert _proof_sql_problems(mutant), f"proof SQL pin must reject variant mutant: {label}"
    # The keyword census stays case-insensitive and word-boundary based for EVERY banned verb …
    for keyword in ("insert", "update", "delete", "truncate", "alter", "drop", "create", "merge", "replace", "grant", "revoke", "copy"):
        planted = ast.parse(f'sql = "{keyword} something control_audit"\n')
        assert _mutating_sql_census(planted), f"census must flag the lowercase {keyword!r} keyword"
        assert _mutating_sql_census(ast.parse(f'sql = "{keyword.upper()} something control_audit"\n')), (
            f"census must flag the uppercase {keyword!r} keyword"
        )
    # … while benign prose near-misses (word-boundary) and the two pinned exempt literals stay clean,
    # and the exemptions are WHOLE-CONSTANT only: a real statement embedding an exempt word is flagged.
    assert not _mutating_sql_census(ast.parse('msg = "created deletion removes drops creates"\n')), "prose near-misses must stay clean"
    assert not _mutating_sql_census(ast.parse('proc = subprocess.run(argv, errors="replace")\n')), "the codec literal is exempt"
    assert not _mutating_sql_census(ast.parse('msg = f"intent ({n} absent row(s) to create)"\n')), "the intent fragment is exempt"
    assert _mutating_sql_census(ast.parse('sql = "replace into control_memberships values (1)"\n')), "a REPLACE statement is flagged"
    assert _mutating_sql_census(ast.parse('sql = "we will create) the row"\n')), "a drifted exempt-like fragment is flagged"


def test_raw_connection_paths_are_forbidden() -> None:
    # F3-C — neither new file may reach a raw/private Control-DB connection or call a write/transaction
    # primitive; every write must go through the two supported store APIs.
    for path in _NEW_PY_FILES:
        problems = _raw_conn_problems(_tree(path))
        assert not problems, f"{path.name} reaches a raw/private Control-DB connection: {problems}"


def test_conn_cache_is_exact_reviewed_shape() -> None:
    # F3-C — the sole sanctioned private handle is the ``_conn_cache`` close in ``_close_plane`` (the 07D
    # finally idiom): exactly one attribute + one getattr string, both inside ``_close_plane``, rooted at
    # cp.store. Any additional occurrence (a new alias, a raw handle grab) is blocking.
    ops_tree = _tree(_OPS)
    attrs, strings = _conn_cache_occurrences(ops_tree)
    assert len(attrs) == 1, f"exactly one cp.store._conn_cache attribute is reviewed, found {len(attrs)}"
    assert len(strings) == 1, f"exactly one '_conn_cache' getattr string is reviewed, found {len(strings)}"
    close_fn = _function(ops_tree, "_close_plane")
    span = {n.lineno for n in ast.walk(close_fn) if hasattr(n, "lineno")}
    assert attrs[0].lineno in span, "the _conn_cache attribute must live inside _close_plane"
    assert strings[0].lineno in span, "the _conn_cache getattr string must live inside _close_plane"
    assert _receiver_is_cp_store_rooted(attrs[0]), "the _conn_cache attribute must be rooted at cp.store"
    getattrs = [
        node
        for node in ast.walk(close_fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == _CONN_CACHE_ATTR
    ]
    assert len(getattrs) == 1 and _receiver_is_cp_store_rooted(getattrs[0].args[0]), (
        "the sole _conn_cache getattr must be getattr(cp.store, '_conn_cache', ...)"
    )
    close_calls = [
        node
        for node in ast.walk(close_fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "close"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == _CONN_CACHE_ATTR
    ]
    assert len(close_calls) == 1, "the sole _conn_cache use must be a .close() on cp.store._conn_cache"
    proof_attrs, proof_strings = _conn_cache_occurrences(_tree(_PROOF))
    assert not proof_attrs and not proof_strings, "_conn_cache must not appear in the proof"


def test_copy_and_raw_conn_non_vacuity() -> None:
    # [Fix R2 — F3 variants] psycopg3 COPY sinks, split-string verbs, and raw cp.store._conn reachability
    # are rejected by the SAME production predicates that pin the committed files (F3 closure).

    # F3-A/F3-B — the psycopg3 ``copy`` sink + static-argument + fold census (variants 1–4, 11).
    sql_mutants = {
        "V1 bare cursor.copy COPY": 'def f(cur):\n    cur.copy("COPY control_federation FROM STDIN")\n',
        "V2 split-string cursor.copy": 'def f(cur):\n    cur.copy("COP" + "Y control_federation FROM STDIN")\n',
        "V3 dynamic cursor.copy": "def f(cur, dynamic_sql):\n    cur.copy(dynamic_sql)\n",
        "V4 f-string cursor.copy": 'def f(cur, table):\n    cur.copy(f"COPY {table} FROM STDIN")\n',
        "V11 copy targeting control_federation": 'def f(cur):\n    cur.copy("copy control_federation (tenant_id) from stdin")\n',
    }
    for label, source in sql_mutants.items():
        mutant = ast.parse(source)
        assert _ops_sql_problems(mutant), f"ops SQL pin must reject F3 mutant: {label}"
        assert _proof_sql_problems(mutant), f"proof SQL pin must reject F3 mutant: {label}"

    # V12 — split-string mutating verbs (lowercase / mixed-case) are caught by the FOLD census directly.
    fold_mutants = {
        "split lowercase delete": 'sql = "dele" + "te from control_memberships"\n',
        "split mixed-case copy": 'sql = "Co" + "PY control_federation from stdin"\n',
        "split truncate": 'sql = "trun" + "cate control_audit"\n',
        "three-way split insert": 'sql = "in" + "se" + "rt into control_audit values (1)"\n',
    }
    for label, source in fold_mutants.items():
        assert _mutating_sql_census(ast.parse(source)), f"fold census must flag split verb: {label}"

    # F3-C — raw cp.store._conn reachability + forbidden write/transaction primitives (variants 5–9).
    raw_mutants = {
        "V5 copier.write_row": "def f(copier, x):\n    copier.write_row((x,))\n",
        "V6 copier.write": "def f(copier):\n    copier.write(b'row')\n",
        "V7 cp.store._conn.commit": "def f(cp):\n    cp.store._conn.commit()\n",
        "V8 getattr _conn then cursor": 'def f(cp):\n    getattr(cp.store, "_conn").cursor()\n',
        "V9 alias raw = cp.store._conn": "def f(cp):\n    raw = cp.store._conn\n",
        "raw cursor rooted at cp.store": "def f(cp):\n    cp.store._conn.cursor()\n",
        "raw copy rooted at cp.store": 'def f(cp):\n    cp.store._conn.copy("COPY x FROM STDIN")\n',
        "raw rollback rooted at cp.store": "def f(cp):\n    cp.store._conn.rollback()\n",
        "deep alias then commit": "def f(cp):\n    raw = cp.store._conn\n    raw.commit()\n",
    }
    for label, source in raw_mutants.items():
        assert _raw_conn_problems(ast.parse(source)), f"raw-conn pin must reject F3 mutant: {label}"

    # V10 — an EXTRA ``_conn_cache`` occurrence outside the reviewed shape is detected (count-based pin).
    extra = ast.parse("def g(cp):\n    raw = cp.store._conn_cache\n    other = cp.store._conn_cache\n")
    extra_attrs, _extra_strings = _conn_cache_occurrences(extra)
    assert len(extra_attrs) == 2, "_conn_cache occurrence detector went vacuous"

    # The EXACT independently reproduced F3 proof of concept is rejected on BOTH axes.
    f3_poc = (
        "def cmd_apply(cp, x):\n"
        "    with cp.store._conn.cursor() as cur:\n"
        '        with cur.copy("COP" + "Y control_federation (tenant_id) FROM STDIN") as copier:\n'
        "            copier.write_row((x,))\n"
        "    cp.store._conn.commit()\n"
    )
    poc_tree = ast.parse(f3_poc)
    assert _raw_conn_problems(poc_tree), "the exact F3 PoC must be rejected by the raw-connection pin"
    assert _ops_sql_problems(poc_tree), "the exact F3 PoC must be rejected by the operator SQL pin"

    # Positive controls — the exact sanctioned shapes stay ACCEPTED (the pins are not blanket bans).
    ok_close = ast.parse(
        'def _close_plane(cp):\n    if getattr(cp.store, "_conn_cache", None) is not None:\n        cp.store._conn_cache.close()\n'
    )
    assert not _raw_conn_problems(ok_close), "the sanctioned _conn_cache close must PASS the raw-conn pin"
    ok_probe = ast.parse(
        'def g(conn, t):\n    with conn.cursor() as cur:\n        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (t,))\n'
    )
    assert not _raw_conn_problems(ok_probe), "the sanctioned local-connection read-only probe must PASS the raw-conn pin"
    assert not _proof_sql_problems(ok_probe), "the sanctioned SELECT probe must PASS the proof SQL pin"


def test_command_surface_is_exactly_plan_apply_status() -> None:
    # [matrix 3] a removal command cannot exist: structural census + behavioral refusal.
    names = _subparser_names(_tree(_OPS))
    assert names == _EXPECTED_SUBCOMMANDS, f"operator subcommands must be exactly plan/apply/status: {sorted(names)}"
    import contextlib
    import io

    module = _load_ops_module()
    for token in (_REMOVAL_TOKEN, "delete", "remove"):
        buf = io.StringIO()
        refused = False
        with contextlib.redirect_stderr(buf):
            try:
                module.build_parser().parse_args([token])
            except SystemExit as exc:
                refused = exc.code != 0
        assert refused, f"unknown subcommand {token!r} must be refused"
    # Non-vacuity: the census sees a planted removal subparser.
    mutant = ast.parse(f'def build():\n    sub.add_parser("plan")\n    sub.add_parser("{_REMOVAL_TOKEN}")\n')
    assert _subparser_names(mutant) != _EXPECTED_SUBCOMMANDS, "subcommand census went vacuous"


def test_b5_4_subprocess_is_status_only() -> None:
    # [matrix 4] a B5-4 apply/removal subprocess is unconstructible: one run site, token-closed argv,
    # and the run site AST-BOUND to the reviewed builder (a pinned-but-unused builder proves nothing).
    tree = _tree(_OPS)
    runs = _subprocess_run_calls(tree)
    assert len(runs) == 1, f"exactly ONE subprocess.run call site is allowed, found {len(runs)}"
    status_fn = _function(tree, "_b5_4_status")
    assert len(_subprocess_run_calls(status_fn)) == 1, "the subprocess.run call site must live inside _b5_4_status"
    binding = _run_site_argv_problems(runs[0])
    assert not binding, f"B5-4 run-site argv binding failed: {binding}"
    problems = _argv_builder_problems(_function(tree, "_b5_4_status_argv"))
    assert not problems, f"B5-4 argv builder pins failed: {problems}"
    module = _load_ops_module()
    assert module._B5_4_STATUS_COMMAND == "status", "the B5-4 subcommand constant must be pinned to status"
    assert module._b5_4_status_argv()[-1] == "status", "the built argv must end with the status token"


def test_b5_4_argv_pin_non_vacuity() -> None:
    mutants = {
        "apply token inline": 'def _b5_4_status_argv():\n    return [sys.executable, str(_B5_4_OPS), "apply"]\n',
        "removal token inline": f'def _b5_4_status_argv():\n    return [sys.executable, str(_B5_4_OPS), "{_REMOVAL_TOKEN}"]\n',
        "different command constant": "def _b5_4_status_argv():\n    return [sys.executable, str(_B5_4_OPS), _B5_4_APPLY_COMMAND]\n",
        "extra argv token": "def _b5_4_status_argv():\n    return [sys.executable, str(_B5_4_OPS), _B5_4_STATUS_COMMAND, extra]\n",
        "different target script": "def _b5_4_status_argv():\n    return [sys.executable, str(_OTHER_OPS), _B5_4_STATUS_COMMAND]\n",
    }
    canonical = "def _b5_4_status_argv():\n    return [sys.executable, str(_B5_4_OPS), _B5_4_STATUS_COMMAND]\n"
    fn = ast.parse(canonical).body[0]
    assert isinstance(fn, ast.FunctionDef) and not _argv_builder_problems(fn), "the canonical argv builder must PASS"
    for label, source in mutants.items():
        mutant_fn = ast.parse(source).body[0]
        assert isinstance(mutant_fn, ast.FunctionDef)
        assert _argv_builder_problems(mutant_fn), f"argv pin must reject mutant: {label}"


def test_b5_4_run_site_binding_non_vacuity() -> None:
    # [Fix R1 — variants V5/V6 of matrix 4] the run site must be BOUND to the reviewed builder: an
    # inline argv leaves every builder pin green (the builder stays pristine, unused) yet must be
    # rejected — even when the inline token is "status" (F2 closure).
    def _single_run(source: str) -> ast.Call:
        calls = _subprocess_run_calls(ast.parse(source))
        assert len(calls) == 1, "companion source must contain exactly one subprocess.run call"
        return calls[0]

    canonical = _single_run("def f():\n    proc = subprocess.run(_b5_4_status_argv(), cwd=str(_BACKEND_ROOT), capture_output=True)\n")
    assert not _run_site_argv_problems(canonical), "the canonical builder-bound run site must PASS"
    run_mutants = {
        "V5 inline apply argv": 'def f():\n    proc = subprocess.run([sys.executable, str(_B5_4_OPS), "apply"], cwd=c)\n',
        "V6 inline status argv": 'def f():\n    proc = subprocess.run([sys.executable, str(_B5_4_OPS), "status"], cwd=c)\n',
        "inline removal-token argv": f'def f():\n    proc = subprocess.run([sys.executable, str(_B5_4_OPS), "{_REMOVAL_TOKEN}"], cwd=c)\n',
        "alternate builder": "def f():\n    proc = subprocess.run(_b5_4_apply_argv(), cwd=c)\n",
        "aliased builder through an attribute": "def f():\n    proc = subprocess.run(mod._b5_4_status_argv(), cwd=c)\n",
        "builder called with a positional argument": 'def f():\n    proc = subprocess.run(_b5_4_status_argv("apply"), cwd=c)\n',
        "builder called with a keyword argument": "def f():\n    proc = subprocess.run(_b5_4_status_argv(command=cmd), cwd=c)\n",
        "no positional argv at all": "def f():\n    proc = subprocess.run(args=_b5_4_status_argv(), cwd=c)\n",
        "argv smuggled through a name": "def f():\n    argv = _b5_4_status_argv()\n    proc = subprocess.run(argv, cwd=c)\n",
    }
    for label, source in run_mutants.items():
        assert _run_site_argv_problems(_single_run(source)), f"run-site binding must reject mutant: {label}"
    # A SECOND subprocess.run call site anywhere breaks the ==1 census (the other half of the pin).
    doubled = _subprocess_run_calls(ast.parse("def f():\n    subprocess.run(_b5_4_status_argv())\n    subprocess.run(other())\n"))
    assert len(doubled) == 2, "second-run-site census went vacuous"


def test_supported_write_apis_only() -> None:
    ops_tree = _tree(_OPS)
    ops_calls = _attr_call_names(ops_tree)
    banned = ops_calls & _OPS_BANNED_CALLS
    assert not banned, f"operator calls banned mutating APIs: {sorted(banned)}"
    assert {"add_membership", "register_tenant"} <= ops_calls, "the two supported write APIs must be present"
    register_calls = [
        node
        for node in ast.walk(ops_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "register_tenant"
    ]
    assert len(register_calls) == 1, "exactly ONE register_tenant call site is allowed"
    kw = {k.arg: k.value for k in register_calls[0].keywords}
    assert isinstance(kw.get("tenant_id"), ast.Name) and kw["tenant_id"].id == "DORMANT_TENANT_ID", (
        "register_tenant must target the pinned dormant tenant id"
    )
    assert isinstance(kw.get("actor"), ast.Name) and kw["actor"].id == "_ACTOR", "register_tenant must use the pinned actor"
    membership_calls = [
        node
        for node in ast.walk(ops_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_membership"
    ]
    assert len(membership_calls) == 1, "exactly ONE add_membership call site is allowed"
    kw = {k.arg: k.value for k in membership_calls[0].keywords}
    assert isinstance(kw.get("principal_ref"), ast.Name) and kw["principal_ref"].id == "PRINCIPAL", (
        "add_membership must use the pinned fixture principal"
    )
    role = kw.get("role")
    assert (
        isinstance(role, ast.Attribute) and role.attr == "TENANT_AGENT" and isinstance(role.value, ast.Name) and role.value.id == "Role"
    ), "add_membership must pass Role.TENANT_AGENT explicitly"
    proof_banned = _attr_call_names(_tree(_PROOF)) & _PROOF_BANNED_CALLS
    assert not proof_banned, f"the proof must drive everything through the operator CLI (banned calls: {sorted(proof_banned)})"


def test_env_writes_pinned_to_standalone_posture() -> None:
    tree = _tree(_OPS)
    env_assigns: List[Tuple[int, ast.Assign]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Subscript):
            target = node.targets[0]
            if (
                isinstance(target.value, ast.Attribute)
                and target.value.attr == "environ"
                and isinstance(target.value.value, ast.Name)
                and target.value.value.id == "os"
            ):
                env_assigns.append((node.lineno, node))
    assert len(env_assigns) == 2, f"exactly TWO os.environ writes are allowed (the posture selectors), found {len(env_assigns)}"
    compose = _function(tree, "_compose_control_store_standalone_plane")
    span = {n.lineno for n in ast.walk(compose) if hasattr(n, "lineno")}
    values = set()
    for lineno, assign in env_assigns:
        assert lineno in span, "os.environ writes must live inside the compose helper only"
        assert isinstance(assign.value, ast.Constant), "selector values must be inline constants"
        values.add(assign.value.value)
    assert values == {"postgres", "in_memory"}, f"selector values must be exactly postgres + in_memory, found {sorted(values)}"
    compose_src = ast.get_source_segment(_OPS.read_text(encoding="utf-8"), compose) or ""
    for required in ("PostgresControlStore", "_MixedPostureOnboardingGuard"):
        assert required in compose_src, f"the compose helper must assert the {required} defense-in-depth check"


def test_effectful_commands_consult_b5_4_first() -> None:
    # [matrix 17] status (and apply) can never omit the original B5-4 6/6 delegation.
    tree = _tree(_OPS)
    status_fn = _function(tree, "cmd_status")
    b5_4 = _first_call_lineno(status_fn, "_b5_4_status")
    gather = _first_call_lineno(status_fn, "_gather_facts")
    assert b5_4 is not None, "cmd_status must invoke the original B5-4 status"
    assert gather is not None and b5_4 < gather, "cmd_status must report the original B5-4 status BEFORE the extension checks"
    apply_fn = _function(tree, "cmd_apply")
    b5_4 = _first_call_lineno(apply_fn, "_b5_4_status")
    preflight = _first_call_lineno(apply_fn, "_preflight")
    register = _first_call_lineno(apply_fn, "register_tenant")
    membership = _first_call_lineno(apply_fn, "add_membership")
    assert b5_4 is not None and preflight is not None and register is not None and membership is not None
    assert b5_4 < preflight < register, "cmd_apply must require B5-4 6/6, then preflight, before ANY write"
    assert preflight < membership, "cmd_apply must preflight before the membership writes"
    # Non-vacuity: a status without the delegation is caught by the same predicate.
    mutant = _function(ast.parse("def cmd_status(a):\n    facts = _gather_facts(cp, dsn, sd)\n    return 0\n"), "cmd_status")
    assert _first_call_lineno(mutant, "_b5_4_status") is None, "delegation-order detector went vacuous"


def test_intended_rows_are_exactly_four() -> None:
    module = _load_ops_module()
    assert module.PRINCIPAL == "b5_standing_member"
    assert tuple(module.READY_TENANT_IDS) == ("b5_standing_alpha", "b5_standing_beta")
    assert module.DORMANT_TENANT_ID == "b5_standing_dormant"
    assert tuple(module.MEMBERSHIP_TENANT_IDS) == ("b5_standing_alpha", "b5_standing_beta", "b5_standing_dormant")
    assert module._ROLE_VALUE == "TENANT_AGENT"
    assert module.intended_rows() == _EXPECTED_INTENDED_ROWS, "the intended permanent rows must be EXACTLY the four"
    assert len(module.intended_rows()) == 4, "no fifth intended row may exist"
    assert module._EXPECTED_DORMANT_ROW == {
        "lifecycle_state": "Registered",
        "organization_ref": "b5_standing_org",
        "expected_schema_version": "1",
        "federation_config_ref": "b5_standing_fed",
        "assoc_store_ref": "tenant/b5_standing_dormant/dsn",
        "assoc_version": "1",
    }, "the exact dormant registry row is pinned"


def test_classification_predicates() -> None:
    module = _load_ops_module()
    assert module._membership_classification(None) == module.ABSENT
    assert module._membership_classification("TENANT_AGENT") == module.EXACT
    assert module._membership_classification("MASTER_AGENT") == module.CONFLICTING  # [matrix 8] role drift
    assert module._tenant_classification(None) == module.ABSENT
    assert module._tenant_classification(dict(module._EXPECTED_DORMANT_ROW)) == module.EXACT
    drifted = dict(module._EXPECTED_DORMANT_ROW)
    drifted["lifecycle_state"] = "Ready"
    assert module._tenant_classification(drifted) == module.CONFLICTING  # [matrix 9] dormant marked Ready
    drifted = dict(module._EXPECTED_DORMANT_ROW)
    drifted["assoc_version"] = "2"
    assert module._tenant_classification(drifted) == module.CONFLICTING  # [matrix 13] canonical ref drift


def test_b5_4_status_predicate() -> None:
    # [matrix 5/6] any drift the original B5-4 status detects (alpha non-Ready, beta association) must
    # fail this operator too: the delegation predicate accepts ONLY exit 0 + the full 6/6 PASS set.
    module = _load_ops_module()
    six_pass = "\n".join(f"  PASS: check {i}" for i in range(6)) + "\nSTATUS OK — complete standing topology\n"
    assert module._b5_4_status_problem(0, six_pass) is None, "the canonical 6/6 output must PASS"
    assert module._b5_4_status_problem(1, six_pass) is not None, "a non-zero B5-4 exit must fail"
    five_pass = "\n".join(f"  PASS: check {i}" for i in range(5)) + "\nSTATUS OK\n"
    assert module._b5_4_status_problem(0, five_pass) is not None, "a 5/6 output must fail"
    no_ok = "\n".join(f"  PASS: check {i}" for i in range(6))
    assert module._b5_4_status_problem(0, no_ok) is not None, "output without the STATUS OK line must fail"


def test_status_mutation_matrix() -> None:
    # The state-shaped mutation matrix (planted facts snapshots; the SAME _evaluate the live status runs).
    module = _load_ops_module()
    canonical = _canonical_facts(module)
    for name, problem in module._evaluate(canonical):
        assert problem is None, f"canonical facts must PASS every check; {name!r} said: {problem}"

    def mutate(**overrides):  # noqa: ANN003, ANN202
        facts = _canonical_facts(module)
        facts.update(overrides)
        return facts

    roles_missing = dict(canonical["membership_roles"])
    roles_missing["b5_standing_dormant"] = None
    omitted = _problem_for(module, mutate(membership_roles=roles_missing), "dormant membership exact")
    assert omitted, "[matrix 7] omitted dormant membership must fail"

    roles_drift = dict(canonical["membership_roles"])
    roles_drift["b5_standing_dormant"] = "MASTER_AGENT"
    drifted_role = _problem_for(module, mutate(membership_roles=roles_drift), "dormant membership exact")
    assert drifted_role, "[matrix 8] drifted dormant role must fail"

    ready_row = dict(module._EXPECTED_DORMANT_ROW)
    ready_row["lifecycle_state"] = "Ready"
    ready_state = {"tenant_id": module.DORMANT_TENANT_ID, "lifecycle_state": "Ready", "ready": True}
    facts = mutate(dormant_row=ready_row, dormant_read_state=ready_state)
    assert _problem_for(module, facts, "dormant tenant exact"), "[matrix 9] Ready dormant row must fail the exact-row check"
    assert _problem_for(module, facts, "dormant ready=false through real read service"), "[matrix 9] Ready dormant must fail readiness"
    assert _problem_for(module, facts, "dormant tenant produces the membership-gated non-Ready precondition"), "[matrix 9] precondition"

    for label, override in (
        ("secret file", {"dormant_secret_file": True}),
        ("secret env key", {"dormant_secret_env": True}),
        ("cp-adapter resolution", {"cp_adapter_resolves": True}),
        ("dbr-adapter resolution", {"dbr_adapter_resolves": True}),
    ):
        assert _problem_for(module, mutate(**override), "no dormant secret material"), f"[matrix 10] {label} must fail"

    assert _problem_for(module, mutate(dormant_database_present=True), "no dormant physical database or tenant schema"), (
        "[matrix 11/12] a dormant physical database (schema implied) must fail"
    )

    ref_drift = dict(module._EXPECTED_DORMANT_ROW)
    ref_drift["assoc_store_ref"] = "tenant/b5_standing_dormant/raw"
    assert _problem_for(module, mutate(dormant_row=ref_drift), "dormant canonical reference exact"), "[matrix 13] ref drift must fail"

    extra_membership = mutate(membership_count=4)
    check = "no unrelated standing rows (exactly three memberships; exactly the three standing tenants)"
    assert _problem_for(module, extra_membership, check), "[matrix 14] an unrelated fifth record must fail"
    extra_tenant = mutate(tenant_ids=[*canonical["tenant_ids"], "b5_unrelated"])
    assert _problem_for(module, extra_tenant, check), "[matrix 14] an unrelated tenant row must fail"

    smoke_name = f"zero {module._SMOKE_PREFIX} residue"
    assert _problem_for(module, mutate(smoke_residue_count=1), smoke_name), "[matrix 15] smoke residue must fail"

    dup_audit = [
        {"actor": module._ACTOR, "from_state": None, "to_state": "Registered"},
        {"actor": module._ACTOR, "from_state": None, "to_state": "Registered"},
    ]
    audit_check = "exactly one permanent RegisterTenant audit row"
    assert _problem_for(module, mutate(register_audit=dup_audit), audit_check), "[matrix 16] duplicate audit provenance must fail"
    assert _problem_for(module, mutate(register_audit=[]), audit_check), "[matrix 16] missing audit provenance must fail"
    wrong_actor = [{"actor": "someone_else", "from_state": None, "to_state": "Registered"}]
    assert _problem_for(module, mutate(register_audit=wrong_actor), audit_check), "[matrix 16] foreign provenance must fail"


def test_manual_only_exception_exact() -> None:
    # [matrix 18] the manual-only entry can be neither absent, widened, nor computed.
    mapping = _manual_only_mapping(_tree(_COMPLETENESS_GUARD))
    assert _MANUAL_ONLY_KEY in mapping, "the B5-4A V2 proof must be a registered MANUAL_ONLY exception"
    assert mapping[_MANUAL_ONLY_KEY].strip(), "the B5-4A V2 exception must carry a written justification"
    assert _B5_4_MANUAL_ONLY_KEY in mapping, "the original B5-4 exception must be preserved"
    assert "*" not in _MANUAL_ONLY_KEY and _MANUAL_ONLY_KEY.endswith(".py"), "the exception key must be one exact file"
    # Non-vacuity: the SAME extractor rejects a computed entry and misses an absent key.
    computed = ast.parse('MANUAL_ONLY_EXCEPTIONS = {"tests/x.py": f"computed {reason}"}\n')
    raised = False
    try:
        _manual_only_mapping(computed)
    except ValueError:
        raised = True
    assert raised, "a computed (non-literal) justification must break the literal_eval extraction"
    without = _manual_only_mapping(ast.parse('MANUAL_ONLY_EXCEPTIONS = {"tests/other.py": "reason"}\n'))
    assert _MANUAL_ONLY_KEY not in without, "manual-only detector went vacuous"


def test_no_production_import_of_ops_module() -> None:
    # [matrix 19] production code can never import the operator.
    offenders: List[str] = []
    for path in _scan.py_files():
        if _TESTS_DIR in path.parents:
            continue
        if any("b5_standing_auth_fixture" in mod for mod in _scan.imported_modules(path)):
            offenders.append(_scan.relposix(path))
    assert not offenders, f"production code must never import the B5-4A V2 ops harness: {offenders}"
    # Non-vacuity: the census detects a synthetic import.
    synthetic = ast.parse("import b5_standing_auth_fixture\n")
    names = [a.name for n in ast.walk(synthetic) if isinstance(n, ast.Import) for a in n.names]
    assert "b5_standing_auth_fixture" in names, "import census went vacuous"


def test_runbook_obligations_and_no_overclaim() -> None:
    # [matrix 20] the runbook can never claim Smoke C success or B5-BLK-4 closure.
    problems = _runbook_problems(_RUNBOOK.read_text(encoding="utf-8"))
    assert not problems, f"runbook census failed: {problems}"


def test_runbook_census_non_vacuity() -> None:
    canonical = " ".join(_RUNBOOK_REQUIRED_NEEDLES)
    assert _runbook_problems(canonical) == [], "the canonical needle join must PASS the census"
    dropped = canonical.replace("B5-BLK-4 OPEN.", "")
    assert "missing:B5-BLK-4 OPEN." in _runbook_problems(dropped), "a dropped standing-status line must be caught"
    dropped = canonical.replace("no teardown command and no delete path", "removal is available")
    assert any(p.startswith("missing:no ") for p in _runbook_problems(dropped)), "a dropped no-removal statement must be caught"
    closed = canonical + " " + _CLOSURE_NEEDLE
    assert f"forbidden:{_CLOSURE_NEEDLE}" in _runbook_problems(closed), "a closure claim must be caught"
    passed = canonical + " Smoke C pass" + "ed."
    assert any(p.startswith("forbidden:smoke c pass") for p in _runbook_problems(passed)), "a smoke-passed claim must be caught"
    done = canonical + " " + _MVP_DONE_NEEDLE
    assert f"forbidden:{_MVP_DONE_NEEDLE}" in _runbook_problems(done), "an MVP-completion claim must be caught"


if __name__ == "__main__":
    _scan.run(
        [
            test_files_exist,
            test_ops_module_is_import_inert_and_stdlib_only_at_top,
            test_no_forbidden_imports_or_names_anywhere,
            test_no_removal_token_or_smoke_prefix_in_new_files,
            test_ops_sql_surface_is_single_readonly_probe,
            test_proof_sql_surface_is_readonly,
            test_sql_pin_non_vacuity,
            test_sql_sink_census_non_vacuity,
            test_raw_connection_paths_are_forbidden,
            test_conn_cache_is_exact_reviewed_shape,
            test_copy_and_raw_conn_non_vacuity,
            test_command_surface_is_exactly_plan_apply_status,
            test_b5_4_subprocess_is_status_only,
            test_b5_4_argv_pin_non_vacuity,
            test_b5_4_run_site_binding_non_vacuity,
            test_supported_write_apis_only,
            test_env_writes_pinned_to_standalone_posture,
            test_effectful_commands_consult_b5_4_first,
            test_intended_rows_are_exactly_four,
            test_classification_predicates,
            test_b5_4_status_predicate,
            test_status_mutation_matrix,
            test_manual_only_exception_exact,
            test_no_production_import_of_ops_module,
            test_runbook_obligations_and_no_overclaim,
            test_runbook_census_non_vacuity,
        ]
    )
