"""PRD 07D-3a/07D-3b — multi-instance readiness static guards (census freeze + Tier-2 pins).

Freezes the Tier-1 (separate-instance) readiness assumptions proven by PRD 07D-2e and pins
the PRD 07D-3b Tier-2 resolution (AT-PMV46-4): the per-unit-of-work ``ControlStore``
boundary — one logical request → one store → one connection, issued by
``control_store_factory`` and released (rollback + close) at unit-of-work end. Grounded in
the 07D-3/07D-3b planning packages (folder 32) and the V-1..V-8 verification rider:

* **AR-1 (broadened).** ``TenantLifecycleService`` (``lifecycle.py``) stays un-wired in
  EVERY production control-plane module — not just the ``main.py`` composition root
  (the b7c1 guard) — because its dormant ``verify_tenant()`` re-reads state after the
  probe and would CAS-overwrite a concurrent winner (OBS-1; harden before Phase-4 wiring).
* **AR-2 (conjunctive, evolved by 07D-3b lockstep — AT-07D3A-PM-5).** (a)
  ``postgres_store.py`` carries the ``07D-3B-TIER2-RESOLVED`` marker, the ``release()``
  unit-of-work teardown, and the ``autocommit=False`` pin; the per-UoW factory exists,
  issues a FRESH store per acquire, and stays driver-free at import; un-reviewed
  connection machinery (threading/contextvars/psycopg_pool) still fails fast. (b) the
  composition root wires no concurrent transport (07E not started — transports must honour
  the "fresh unit of work per request, never shared" contract). (c) the dormant HTTP
  read-API binding ``http_read_api.py`` — a REAL request-handler surface in product code
  (V-1) — stays GET-only, single-threaded (plain ``HTTPServer``), and product-unwired
  until 07E.
* **Thread census (V-1).** Product modules importing ``threading`` are frozen to the
  known-benign set: ``database_router/pool.py`` (lock-guarded per-tenant pool, by design).
  The guard must PASS on that benign lock and FAIL on any new product thread use.
* **CAS caller census (V-4).** Exactly 5 production ``compare_and_swap_tenant`` callers;
  the create path stays the only ``put_tenant`` producer (with the b7c1 census).

Pure stdlib AST/text; standalone-runnable:
  python tests/architecture/test_07d3_multiinstance_readiness_static.py
"""

from __future__ import annotations

import ast
import pathlib
import sys
from typing import List, Optional, Set, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_CP = _scan.BACKEND_ROOT / "control_plane"
_MAIN = _CP / "main.py"
_LIFECYCLE = _CP / "lifecycle.py"
_STORE = _CP / "adapters" / "providers" / "postgres_store.py"
_READ_API = _CP / "adapters" / "providers" / "http_read_api.py"
_POOL = _scan.BACKEND_ROOT / "database_router" / "pool.py"

# The Tier-2 marker in postgres_store.py — evolved by PRD 07D-3b from "constraint (fenced)"
# to "resolved": per-unit-of-work scoping via the ControlStoreFactory (AR-2 lockstep,
# AT-07D3A-PM-5). Deleting/rewording it without a reviewed connection-model change fails here.
_TIER2_MARKER = "07D-3B-TIER2-RESOLVED"
_TIER2_PHRASE = "MUST acquire a fresh unit of work per request"
_FACTORY = _CP / "adapters" / "providers" / "control_store_factory.py"

# Transport / concurrency machinery that must NOT appear in the composition root until a
# 07E transport lands honouring the per-UoW contract (AR-2 leg (b) denylist).
_TRANSPORT_DENYLIST = {
    "http.server",
    "socketserver",
    "wsgiref",
    "asyncio",
    "threading",
    "concurrent.futures",
    "fastapi",
    "flask",
    "uvicorn",
    "starlette",
    "aiohttp",
    "tornado",
    "django",
}

# Product modules allowed to import `threading` (V-1 benign classification; frozen census).
_THREADING_ALLOWED = {"database_router/pool.py"}

# The read edge's blessed production make_server wirers (07E-1 + B5-1 Guard Evolution Matrix).
# ``http_read_api.py`` is the read adapter itself (skipped in the census by identity);
# ``control_plane/main.py`` is the B5-1 server-composition seam (``build_read_server_from_env``),
# authorized to reference ``make_server`` while composing a server object. This is a narrow, named
# per-module exemption — never a directory/substring open, and it never blesses ``serve_forever``.
_READ_EDGE_MAKE_SERVER_BLESSED = {"control_plane/main.py"}

# The production serve-loop census (B5-2 Guard Evolution Matrix, EVOLVED by Served API Gateway
# Edge V1). ``http_read_api.py`` (the 07E-1 ``serve_read_api`` precedent) is the read adapter
# itself, skipped in the census by identity and retained unchanged; B5-2 blessed two more blocking
# entrypoints, and Served API Gateway Edge V1 blesses ONE more — the served northbound edge
# ``serve_gateway_edge`` — for a total of THREE blessed adapter entrypoints. Each module may
# reference ``serve_forever`` ONLY inside its single named entrypoint, exactly once. Narrow, named,
# per-module (module -> sole approved entrypoint) — never a directory/substring open.
# ``ThreadingHTTPServer`` is never blessed anywhere (AT-D15T1-10 single-threaded HARD-GATE).
_SERVE_LOOP_BLESSED = {
    "auth_router/adapters/providers/http_authenticate_api.py": "serve_authenticate_api",
    "database_router/adapters/providers/http_dispatch_api.py": "serve_dispatch_api",
    "api_gateway/adapters/providers/http_gateway_edge.py": "serve_gateway_edge",
}

# The 5 production CAS callers frozen by the 07D-3 planning census (V-4).
_EXPECTED_CAS_CALLERS = {
    ("registry.py", "_transition"),
    ("provisioning.py", "reassociate"),
    ("provisioning.py", "_transition"),
    ("lifecycle.py", "reassociate_database"),
    ("lifecycle.py", "_set"),
}


def _product_files(root: pathlib.Path) -> List[pathlib.Path]:
    """Production .py files under `root` (tests live under backend/tests — outside all
    service package roots — so a package rglob is production-only by construction)."""
    return sorted(p for p in root.rglob("*.py") if not (_scan.SKIP_PARTS & set(p.parts)))


def _tree(path: pathlib.Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _names_used(tree: ast.AST) -> Set[str]:
    """Identifiers referenced as code (Name/Attribute), NOT docstring/comment text."""
    out: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
    return out


def _function_def(tree: ast.AST, name: str) -> Optional[ast.AST]:
    """The first def/async-def named ``name`` in ``tree`` (or None)."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _serve_forever_refs(tree: ast.AST) -> int:
    """Count ``serve_forever`` CODE references (Name/Attribute), not docstring/comment prose."""
    return sum(
        1
        for n in ast.walk(tree)
        if (isinstance(n, ast.Attribute) and n.attr == "serve_forever") or (isinstance(n, ast.Name) and n.id == "serve_forever")
    )


def _single_blessed_serve_problems(tree: ast.AST, entrypoint: str) -> List[str]:
    """B5-2 Guard Evolution Matrix: a serve-blessed module must define EXACTLY ONE module-top
    def named ``entrypoint`` whose body holds the module's ONLY ``serve_forever`` reference —
    the factory surface stays serve-free and no second serve loop may appear anywhere else."""
    problems: List[str] = []
    mod = tree
    assert isinstance(mod, ast.Module)
    defs = [n for n in mod.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == entrypoint]
    if len(defs) != 1:
        problems.append(f"expected exactly one top-level {entrypoint} def, found {len(defs)}")
        return problems
    inside = _serve_forever_refs(defs[0])
    total = _serve_forever_refs(tree)
    if inside != 1:
        problems.append(f"{entrypoint} must contain exactly one serve_forever reference, found {inside}")
    if total != inside:
        problems.append(f"serve_forever referenced outside {entrypoint} ({total} total vs {inside} inside)")
    return problems


def _read_edge_wiring_offense(relp: str, tree: ast.AST, imported: List[str]) -> List[str]:
    """The read-edge single-wiring + serve-loop census predicate (07E-1, EVOLVED by the B5-1 and
    B5-2 Guard Evolution Matrices). Given one production module (never the read adapter itself,
    which the caller skips by identity), report its offenses:

    * imports ``http_read_api`` while not a blessed wirer → offense;
    * references ``ThreadingHTTPServer`` → offense — never blessed anywhere (AT-D15T1-10);
    * references ``serve_forever`` → offense UNLESS the module is in ``_SERVE_LOOP_BLESSED`` AND
      every reference sits inside its single named blocking entrypoint, exactly once (B5-2);
    * references ``make_server`` while not a blessed wirer → offense.

    The blessed sets are exact per-module names (``_READ_EDGE_MAKE_SERVER_BLESSED`` /
    ``_SERVE_LOOP_BLESSED``) — never a directory/substring open."""
    blessed = relp in _READ_EDGE_MAKE_SERVER_BLESSED
    if any(mod.endswith("http_read_api") for mod in imported) and not blessed:
        return [f"{relp} imports http_read_api"]
    used = _names_used(tree)
    offenses: List[str] = []
    if "ThreadingHTTPServer" in used:
        offenses.append(f"{relp} references ThreadingHTTPServer")
    if "serve_forever" in used:
        serve_entrypoint = _SERVE_LOOP_BLESSED.get(relp)
        if serve_entrypoint is None:
            offenses.append(f"{relp} references serve_forever")
        else:
            offenses.extend(f"{relp}: {problem}" for problem in _single_blessed_serve_problems(tree, serve_entrypoint))
    if "make_server" in used and not blessed:
        offenses.append(f"{relp} references make_server")
    return offenses


def test_lifecycle_service_not_wired_in_any_product_module() -> None:
    # AR-1 (broadened from the b7c1 main.py-only guard): NO production control-plane module
    # imports lifecycle or references TenantLifecycleService in code. Docstring mentions
    # (e.g. provisioning.py's contrast note) are allowed — the scan reads code identifiers
    # and import statements, not prose.
    offenders: List[str] = []
    scanned: List[str] = []
    for path in _product_files(_CP):
        if path == _LIFECYCLE:  # the definition site itself
            continue
        scanned.append(_scan.relposix(path))
        tree = _tree(path)
        for mod in _scan.imported_modules(path):
            if mod.split(".")[-1] == "lifecycle" or mod.endswith("control_plane.lifecycle"):
                offenders.append(f"{_scan.relposix(path)} imports {mod!r}")
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level > 0 and (node.module or "").split(".")[-1] == "lifecycle":
                offenders.append(f"{_scan.relposix(path)} imports .{node.module}")
        if "TenantLifecycleService" in _names_used(tree):
            offenders.append(f"{_scan.relposix(path)} references TenantLifecycleService")
    assert not offenders, (
        "TenantLifecycleService must stay un-wired in production until its OBS-1 stale-read "
        f"hardening lands (Phase-4 wiring slice): {offenders}"
    )
    # Non-vacuity: the definition exists and the composition root was actually swept.
    defined = any(isinstance(node, ast.ClassDef) and node.name == "TenantLifecycleService" for node in ast.walk(_tree(_LIFECYCLE)))
    assert defined, "lifecycle.py must define TenantLifecycleService (the guarded surface is real)"
    assert "control_plane/main.py" in scanned, "composition root must be in the swept set"


def test_control_store_per_uow_scoping_and_tier2_marker() -> None:
    # AR-2 leg (a), evolved by PRD 07D-3b (lockstep, AT-07D3A-PM-5): the store carries the
    # RESOLVED Tier-2 marker + the 07E contract phrase + the autocommit pin; one instance
    # still means one connection (the per-UoW connection) with a release() that rolls back
    # and closes; and the per-UoW factory exists, issues a FRESH store per acquire, and
    # stays driver-free at import. Un-reviewed connection machinery still fails fast.
    text = _STORE.read_text(encoding="utf-8")
    assert _TIER2_MARKER in text, "postgres_store.py must carry the 07D-3B-TIER2-RESOLVED marker (AT-PMV46-4)"
    assert "(AT-PMV46-4)" in text, "the Tier-2 marker must cite AT-PMV46-4"
    assert _TIER2_PHRASE in text, "the marker must state the 07E contract (fresh unit of work per request) verbatim"
    assert "conn.autocommit = False" in text, "the autocommit=False pin must survive (AT-07D3A-5; D-2e-4 atomicity)"
    tree = _tree(_STORE)
    has_conn_cache = any(isinstance(node, ast.Attribute) and node.attr == "_conn_cache" for node in ast.walk(tree))
    assert has_conn_cache, "one store instance == one (unit-of-work) connection: _conn_cache shape must survive"
    release_fns = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "release"]
    assert release_fns, "PostgresControlStore.release() (rollback + close at UoW end) must exist (07D-3b)"
    assert any("rollback" in ast.dump(n) for n in release_fns), "release() must roll back any open transaction"
    forbidden = {"threading", "contextvars", "psycopg_pool", "concurrent.futures"}
    for path, label in ((_STORE, "postgres_store.py"), (_FACTORY, "control_store_factory.py")):
        imported = set(_scan.imported_modules(path))
        hits = {m for m in imported if m in forbidden or m.split(".")[0] in {f.split(".")[0] for f in forbidden}}
        assert not hits, f"unreviewed connection-scoping machinery in {label}: {hits} (update this guard in lockstep)"
    # The factory: exists, issues a FRESH PostgresControlStore per acquire, binds no driver
    # at module load (the store import is function-local / TYPE_CHECKING only).
    assert _FACTORY.exists(), "control_store_factory.py (the per-UoW boundary) must exist (07D-3b)"
    ftree = _tree(_FACTORY)
    fclasses = {n.name for n in ast.walk(ftree) if isinstance(n, ast.ClassDef)}
    assert {"PostgresControlStoreFactory", "SharedControlStoreFactory"} <= fclasses, f"factory classes missing: {fclasses}"
    acquire_fns = [n for n in ast.walk(ftree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "acquire"]
    assert acquire_fns, "the factory must expose acquire()"
    fresh_per_acquire = any(
        isinstance(sub, ast.Call)
        and (
            (isinstance(sub.func, ast.Name) and sub.func.id == "PostgresControlStore")
            or (isinstance(sub.func, ast.Attribute) and sub.func.attr == "PostgresControlStore")
        )
        for fn in acquire_fns
        for sub in ast.walk(fn)
    )
    assert fresh_per_acquire, "PostgresControlStoreFactory.acquire() must construct a FRESH store per unit of work"
    release_calls = any(
        isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == "release"
        for fn in acquire_fns
        for sub in ast.walk(fn)
    )
    assert release_calls, "acquire() must release() the store at unit-of-work end"
    assert "psycopg" not in {m.split(".")[0] for m in _scan.imported_modules(_FACTORY) if m.split(".")[0] == "psycopg"}, (
        "the factory must not import the driver at module level (driver containment)"
    )
    # The composition wires the factory + the per-UoW acquisition surface (no transport).
    main_text = _MAIN.read_text(encoding="utf-8")
    for token in ("store_factory", "_build_store_factory", "control_store_unit_of_work"):
        assert token in main_text, f"main.py must wire the per-UoW factory surface ({token}) — 07D-3b"


def test_composition_root_wires_no_concurrent_transport() -> None:
    # AR-2 leg (b), EVOLVED by the B5-1 Guard Evolution Matrix: the create_app() composition root
    # must not construct a request transport or thread machinery — a running serve lifecycle stays
    # 07E/B5-2 scope and must honour the 07D-3b per-UoW contract (fresh store per request via
    # control_store_unit_of_work, never shared). B5-1 adds ONE blessed exception: the socket-binding,
    # serve-INERT read-edge server-composition seam ``build_read_server_from_env`` may reference
    # ``make_server`` (it composes a server object; it never serves, threads, or opens a DB).
    # ``serve_forever`` / ``HTTPServer`` / ``ThreadingHTTPServer`` STAY banned in main.py (the serve
    # loop and the concrete server type live in the read adapter, not the composition root), and no
    # transport module may be imported at module scope.
    imported = set(_scan.imported_modules(_MAIN))
    hits = sorted(m for m in imported if m in _TRANSPORT_DENYLIST or m.split(".")[0] in _TRANSPORT_DENYLIST)
    assert not hits, f"main.py must not wire a concurrent transport (07E scope; per-UoW contract): {hits}"
    main_tree = _tree(_MAIN)
    used = _names_used(main_tree)
    for name in ("serve_forever", "HTTPServer", "ThreadingHTTPServer"):
        assert name not in used, f"main.py must not reference {name} (serve loop / server type is read-adapter scope)"
    # Positive, NON-VACUOUS census of the one blessed make_server reference (B5-1): the seam exists,
    # the two env literals exist, and EVERY make_server name reference in main.py is lexically inside
    # the seam (referenced ONLY by the composition seam — never at module scope or any other function).
    seam = _function_def(main_tree, "build_read_server_from_env")
    assert seam is not None, "B5-1: control_plane/main.py must define build_read_server_from_env"
    main_text = _MAIN.read_text(encoding="utf-8")
    for literal in ('"SP2_CP_READ_HOST"', '"SP2_CP_READ_PORT"'):
        assert literal in main_text, f"B5-1: the {literal} env literal must exist in main.py"
    seam_refs = sum(1 for n in ast.walk(seam) if isinstance(n, ast.Name) and n.id == "make_server")
    total_refs = sum(1 for n in ast.walk(main_tree) if isinstance(n, ast.Name) and n.id == "make_server")
    assert seam_refs >= 1, "B5-1: build_read_server_from_env must reference make_server (the blessed seam)"
    assert total_refs == seam_refs, (
        "make_server may be referenced ONLY inside build_read_server_from_env "
        f"(found {total_refs} total in main.py, {seam_refs} inside the seam)"
    )


def test_http_read_api_per_request_uow_get_only_single_threaded() -> None:
    # AR-2 leg (c), EVOLVED by PRD 07E-1 (authorized Guard Evolution Matrix #4): the read
    # edge is now WIRED — the dormancy census is replaced by a POSITIVE per-handler-UoW
    # census. Every GET request must acquire a fresh control_store_unit_of_work() and use
    # only the yielded store; the GET-only and single-threaded pins remain; the machinery
    # ban now covers http_read_api.py; and no OTHER production module wires the edge.
    assert _READ_API.exists(), "http_read_api.py is the wired read edge (07E-1) — update this guard if it moves"
    text = _READ_API.read_text(encoding="utf-8")
    tree = _tree(_READ_API)
    handlers = [
        node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("do_")
    ]
    assert handlers == ["do_GET"], f"the read edge must stay GET-only (served handlers: {handlers})"
    for marker in ("ThreadingHTTPServer", "ThreadingMixIn"):
        assert marker not in text, f"http_read_api.py must stay single-threaded plain HTTPServer (found {marker})"
    # Machinery-import ban extended to the transport module (07E-1 §6.7/§6.8).
    banned = {"threading", "asyncio", "contextvars", "psycopg_pool", "concurrent.futures"}
    imported = set(_scan.imported_modules(_READ_API))
    hits = {m for m in imported if m in banned or m.split(".")[0] in {b.split(".")[0] for b in banned}}
    assert not hits, f"http_read_api.py must stay single-threaded stdlib (banned machinery: {hits})"
    # POSITIVE per-handler-UoW census (non-vacuous): do_GET must exist, must open exactly
    # one `with ... control_store_unit_of_work() / .acquire()` unit of work, and must not
    # touch any ControlPlane facade-bound service.
    do_get = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "do_GET":
            do_get = node
    assert do_get is not None, "the wired read edge must define do_GET (positive census is non-vacuous)"
    uow_withs = [
        w
        for w in ast.walk(do_get)
        if isinstance(w, ast.With)
        and any(
            isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Attribute)
            and item.context_expr.func.attr in ("control_store_unit_of_work", "acquire")
            for item in w.items
        )
    ]
    assert uow_withs, "do_GET must acquire a fresh control_store_unit_of_work() per request (with-block)"
    facade_banned = {"store", "registry", "membership", "federation", "directory", "audit"}
    facade_hits = sorted({node.attr for node in ast.walk(do_get) if isinstance(node, ast.Attribute) and node.attr in facade_banned})
    assert not facade_hits, f"do_GET must use ONLY the yielded UoW store — facade-bound access: {facade_hits}"
    # The server binds a ControlPlane, never a store; the runnable entrypoint lives here.
    for fn_name in ("_make_handler", "make_server"):
        fn = next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn_name)
        first_arg = fn.args.args[0].arg if fn.args.args else None
        assert first_arg == "control_plane", f"{fn_name} must take the ControlPlane accessor, not a store ({first_arg!r})"
    assert "def serve_read_api" in text, "the runnable entrypoint (serve_read_api) must live in http_read_api.py"
    assert "from control_plane.main import create_app" in text, "entrypoint composes via function-local create_app import"
    assert "503" in text, "the fail-closed 5xx (503, empty body) contract must survive in the transport"
    # Single-wiring census, EVOLVED by the B5-1 Guard Evolution Matrix: the read edge has exactly
    # TWO blessed production wirers — the read adapter itself (http_read_api.py, skipped by identity)
    # and the B5-1 composition seam control_plane/main.py (build_read_server_from_env, authorized to
    # reference make_server). Every OTHER production module must import neither the edge nor its
    # server symbols; and NO module (blessed or not) may reference serve_forever here (the serve loop
    # stays in the read adapter). See _read_edge_wiring_offense for the shared predicate.
    offenders: List[str] = []
    for pkg in _scan.SERVICE_PACKAGES + ["shared"]:
        for path in _product_files(_scan.BACKEND_ROOT / pkg):
            if path == _READ_API:
                continue
            offenders.extend(_read_edge_wiring_offense(_scan.relposix(path), _tree(path), _scan.imported_modules(path)))
    assert not offenders, f"the read edge must have no unblessed production wiring (07E-1 + B5-1): {offenders}"


def test_read_edge_wiring_census_is_non_vacuous() -> None:
    # B5-1 + B5-2 Guard Evolution Matrices — non-vacuity companion: prove the EVOLVED census
    # predicate still FAILS on an unauthorized make_server / serve_forever / ThreadingHTTPServer /
    # http_read_api reference, that the serve blessing is per-module AND per-entrypoint, and that
    # every blessing is a real, narrow, named exemption (not a directory/substring open). Exercises
    # the REAL predicate (_read_edge_wiring_offense) over planted in-memory sources — no files written.
    def probe(relp: str, source: str, imported: Optional[List[str]] = None) -> List[str]:
        return _read_edge_wiring_offense(relp, ast.parse(source), imported or [])

    # An UNBLESSED module referencing make_server / serve_forever / importing http_read_api is flagged.
    assert probe("some_service/evil.py", "x = make_server(app)\n") == ["some_service/evil.py references make_server"]
    assert probe("some_service/evil.py", "srv.serve_forever()\n") == ["some_service/evil.py references serve_forever"]
    assert probe("some_service/evil.py", "", imported=["pkg.http_read_api"]) == ["some_service/evil.py imports http_read_api"]
    # The BLESSED seam module may reference make_server and import http_read_api...
    assert probe("control_plane/main.py", "make_server(create_app())\n", imported=["pkg.http_read_api"]) == []
    # ...but serve_forever is banned EVEN THERE (the composition root never serves).
    assert probe("control_plane/main.py", "srv.serve_forever()\n") == ["control_plane/main.py references serve_forever"]
    # The exemptions are narrow (exactly the named modules) and REAL (main.py truly references make_server).
    assert _READ_EDGE_MAKE_SERVER_BLESSED == {"control_plane/main.py"}, "the make_server blessing must stay one named module"
    assert "make_server" in _names_used(_tree(_MAIN)), "control_plane/main.py must really reference make_server (B5-1 seam)"
    # --- B5-2 serve-loop census planted offenses (Guard Evolution Matrix §8.1) ---
    auth_relp = "auth_router/adapters/providers/http_authenticate_api.py"
    # The canonical blessed shape passes: one entrypoint, one serve_forever inside it.
    assert probe(auth_relp, "def serve_authenticate_api():\n    s.serve_forever()\n") == []
    # A blessed module with a SECOND unauthorized serve loop is flagged.
    doubled = "def serve_authenticate_api():\n    s.serve_forever()\n\ndef rogue():\n    s.serve_forever()\n"
    assert probe(auth_relp, doubled), "a second serve loop in a blessed module must be flagged"
    # A blessed module whose serve loop sits OUTSIDE the named entrypoint is flagged.
    misplaced = "def serve_authenticate_api():\n    pass\n\ndef rogue():\n    s.serve_forever()\n"
    assert probe(auth_relp, misplaced), "a serve loop outside the blessed entrypoint must be flagged"
    # ThreadingHTTPServer is flagged EVERYWHERE — even in a serve-blessed module (AT-D15T1-10).
    assert probe(auth_relp, "srv = ThreadingHTTPServer(addr, handler)\n") == [f"{auth_relp} references ThreadingHTTPServer"]
    assert probe("some_service/evil.py", "srv = ThreadingHTTPServer(addr, handler)\n"), "unblessed ThreadingHTTPServer must be flagged"
    # The dispatch blessing is entrypoint-specific: the auth entrypoint name does not bless dispatch.
    dbr_relp = "database_router/adapters/providers/http_dispatch_api.py"
    assert probe(dbr_relp, "def serve_authenticate_api():\n    s.serve_forever()\n"), "the wrong entrypoint name must be flagged"
    assert probe(dbr_relp, "def serve_dispatch_api():\n    s.serve_forever()\n") == []


def test_serve_loop_census_blessed_entrypoints_are_real() -> None:
    # B5-2 Guard Evolution Matrix — POSITIVE, non-vacuous census: each serve-blessed module REALLY
    # defines its single blocking entrypoint with exactly one serve_forever inside it (the blessing
    # never outlives the code it blesses); the blessed set stays exactly the two named adapter
    # modules; and the retained 07E-1 precedent (serve_read_api in the read adapter) survives.
    assert set(_SERVE_LOOP_BLESSED) == {
        "auth_router/adapters/providers/http_authenticate_api.py",
        "database_router/adapters/providers/http_dispatch_api.py",
        "api_gateway/adapters/providers/http_gateway_edge.py",
    }, "the serve-loop blessing must stay exactly the three named adapter modules"
    for relp, entrypoint in _SERVE_LOOP_BLESSED.items():
        path = _scan.BACKEND_ROOT / relp
        assert path.is_file(), f"serve-blessed module missing: {relp}"
        problems = _single_blessed_serve_problems(_tree(path), entrypoint)
        assert not problems, f"{relp}: {problems}"
    assert "def serve_read_api" in _READ_API.read_text(encoding="utf-8"), "the 07E-1 read-edge serve precedent must survive"


def test_product_thread_import_census_is_frozen_to_benign_set() -> None:
    # V-1 census freeze: `import threading` in production code is exactly the known-benign
    # database_router/pool.py (lock-guarded per-tenant pool). New product thread use — e.g.
    # serve_forever in a thread over a ControlStore — must consciously update this census
    # together with the 07D-3b rework. The benign lock itself must keep PASSING here.
    importers: Set[str] = set()
    for pkg in _scan.SERVICE_PACKAGES + ["shared"]:
        for path in _product_files(_scan.BACKEND_ROOT / pkg):
            mods = _scan.imported_modules(path)
            if any(m == "threading" or m.startswith("threading.") for m in mods):
                importers.add(_scan.relposix(path))
    assert importers == _THREADING_ALLOWED, (
        f"product `threading` importers must equal the frozen benign census {_THREADING_ALLOWED}; got {sorted(importers)}"
    )
    # Non-vacuity: the benign member really holds a lock (the distinction the guard proves).
    assert "threading.Lock()" in _POOL.read_text(encoding="utf-8"), "pool.py benign lock expected (census member is real)"


def test_cas_caller_census_frozen_to_five_production_sites() -> None:
    # V-4 census freeze: the production compare_and_swap_tenant callers are EXACTLY the five
    # sites the 07D-3 planning census pinned (b7c1 asserts >= 5; this pins the exact set so a
    # new unreviewed CAS caller — or a silently vanished one — fails loud).
    callers: Set[Tuple[str, str]] = set()
    for path in _product_files(_CP):
        if "adapters" in path.parts or path.name == "ports.py":  # port decl + providers implement, not call
            continue
        for node in ast.walk(_tree(path)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for sub in ast.walk(node):
                    if (
                        isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr == "compare_and_swap_tenant"
                        and isinstance(sub.func.value, ast.Attribute)
                        and sub.func.value.attr == "_store"
                    ):
                        callers.add((path.name, node.name))
    assert callers == _EXPECTED_CAS_CALLERS, (
        f"production CAS caller census must equal the frozen five sites {sorted(_EXPECTED_CAS_CALLERS)}; got {sorted(callers)}"
    )


def test_verify_yield_policy_constants_pinned() -> None:
    # Tier-1 floor (static leg; behavioral enforcement lives in test_lifecycle_cas_2e.py and
    # the live-PG proofs): the 07D-2e yield policy's outcome-reason constant survives.
    text = (_CP / "provisioning.py").read_text(encoding="utf-8")
    assert 'REASON_CONCURRENT_LIFECYCLE_WINNER = "concurrent_lifecycle_winner"' in text, (
        "the verify() concurrency-yield reason constant must survive (07D-2e D-2e-5)"
    )
    assert "VERIFICATION_INCOMPLETE" in text, "verify() must keep yielding the EXISTING non-routable result"


if __name__ == "__main__":
    _scan.run(
        [
            test_lifecycle_service_not_wired_in_any_product_module,
            test_control_store_per_uow_scoping_and_tier2_marker,
            test_composition_root_wires_no_concurrent_transport,
            test_http_read_api_per_request_uow_get_only_single_threaded,
            test_read_edge_wiring_census_is_non_vacuous,
            test_serve_loop_census_blessed_entrypoints_are_real,
            test_product_thread_import_census_is_frozen_to_benign_set,
            test_verify_yield_policy_constants_pinned,
            test_cas_caller_census_frozen_to_five_production_sites,
        ]
    )
