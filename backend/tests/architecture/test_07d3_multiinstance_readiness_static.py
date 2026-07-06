"""PRD 07D-3a — multi-instance readiness static guards (census freeze + Tier-2 tripwires).

Freezes the Tier-1 (separate-instance) readiness assumptions proven by PRD 07D-2e and
fences the OPEN Tier-2 gap (AT-PMV46-4: one shared cached connection per
``PostgresControlStore`` instance; not safe across concurrent requests/threads) until the
PRD 07D-3b connection/transaction-model rework lands. Grounded in the 07D-3 planning
package (folder 32) and its independent verification rider V-1..V-8:

* **AR-1 (broadened).** ``TenantLifecycleService`` (``lifecycle.py``) stays un-wired in
  EVERY production control-plane module — not just the ``main.py`` composition root
  (the b7c1 guard) — because its dormant ``verify_tenant()`` re-reads state after the
  probe and would CAS-overwrite a concurrent winner (OBS-1; harden before Phase-4 wiring).
* **AR-2 (conjunctive tripwire; V-1).** (a) ``postgres_store.py`` keeps the single
  cached-connection shape AND the documented Tier-2 constraint marker; (b) the
  composition root wires no concurrent transport; (c) the dormant HTTP read-API binding
  ``http_read_api.py`` — a REAL request-handler surface in product code (V-1 refuted the
  "no request handlers" universal) — stays GET-only, single-threaded (plain
  ``HTTPServer``), and product-unwired until the 07E transport decision lands WITH 07D-3b.
* **Thread census (V-1).** Product modules importing ``threading`` are frozen to the
  known-benign set: ``database_router/pool.py`` (lock-guarded per-tenant pool, by design).
  The guard must PASS on that benign lock and FAIL on any new product thread use.
* **CAS caller census (V-4).** Exactly 5 production ``compare_and_swap_tenant`` callers;
  the create path stays the only ``put_tenant`` producer (with the b7c1 census).

Tripwire, not fix: removing the marker, upgrading the read API to a threaded server, or
wiring a transport over the shared store must land TOGETHER with the 07D-3b rework — any
one alone fails here. Pure stdlib AST/text; standalone-runnable:
  python tests/architecture/test_07d3_multiinstance_readiness_static.py
"""

from __future__ import annotations

import ast
import pathlib
import sys
from typing import List, Set, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_CP = _scan.BACKEND_ROOT / "control_plane"
_MAIN = _CP / "main.py"
_LIFECYCLE = _CP / "lifecycle.py"
_STORE = _CP / "adapters" / "providers" / "postgres_store.py"
_READ_API = _CP / "adapters" / "providers" / "http_read_api.py"
_POOL = _scan.BACKEND_ROOT / "database_router" / "pool.py"

# The Tier-2 constraint marker recorded in postgres_store.py (07D-3a comment-only edit).
# Deleting/rewording it without the 07D-3b rework fails AR-2 leg (a).
_TIER2_MARKER = "07D-3A-TIER2-CONSTRAINT"
_TIER2_PHRASE = "Per-unit-of-work connection/transaction scoping (PRD 07D-3b, AT-PMV46-4) is REQUIRED"

# Transport / concurrency machinery that must NOT appear in the composition root until the
# 07D-3b store rework lands with the 07E transport (AR-2 leg (b) denylist).
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


def test_control_store_keeps_single_connection_shape_and_tier2_marker() -> None:
    # AR-2 leg (a): the store keeps the single cached-connection shape AND carries the
    # documented Tier-2 constraint. Starting the 07D-3b rework (pool/threading/contextvars)
    # or deleting the caveat without the rework fails here, forcing both to move together.
    text = _STORE.read_text(encoding="utf-8")
    assert _TIER2_MARKER in text, "postgres_store.py must carry the 07D-3A-TIER2-CONSTRAINT marker (V-1/AT-PMV46-4)"
    assert _TIER2_PHRASE in text, "the Tier-2 marker must state the 07D-3b per-unit-of-work requirement verbatim"
    tree = _tree(_STORE)
    has_conn_cache = any(isinstance(node, ast.Attribute) and node.attr == "_conn_cache" for node in ast.walk(tree))
    assert has_conn_cache, "PostgresControlStore must keep the _conn_cache single-connection shape (or update this guard with 07D-3b)"
    forbidden = {"threading", "contextvars", "psycopg_pool", "concurrent.futures"}
    imported = set(_scan.imported_modules(_STORE))
    hits = {m for m in imported if m in forbidden or m.split(".")[0] in {f.split(".")[0] for f in forbidden}}
    assert not hits, f"connection-scoping machinery in postgres_store.py is 07D-3b scope, not 07D-3a: {hits}"


def test_composition_root_wires_no_concurrent_transport() -> None:
    # AR-2 leg (b): the create_app() composition root must not construct a request transport
    # or thread machinery over the shared store singleton until 07D-3b lands.
    imported = set(_scan.imported_modules(_MAIN))
    hits = sorted(m for m in imported if m in _TRANSPORT_DENYLIST or m.split(".")[0] in _TRANSPORT_DENYLIST)
    assert not hits, f"main.py must not wire a concurrent transport over the shared store (07D-3b + 07E): {hits}"
    used = _names_used(_tree(_MAIN))
    for name in ("make_server", "serve_forever", "HTTPServer", "ThreadingHTTPServer"):
        assert name not in used, f"main.py must not reference {name} (transport wiring is 07D-3b + 07E scope)"


def test_http_read_api_stays_dormant_get_only_single_threaded() -> None:
    # AR-2 leg (c) / V-1: the dormant read-API binding is a REAL request-handler surface.
    # Pin its hazard-relevant shape: GET-only, plain single-threaded HTTPServer, no thread
    # machinery of its own, and NO production caller (wiring stays test-only until 07E).
    assert _READ_API.exists(), "http_read_api.py is a recognized dormant transport surface (V-1) — update this guard if it moves"
    text = _READ_API.read_text(encoding="utf-8")
    tree = _tree(_READ_API)
    handlers = [
        node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("do_")
    ]
    assert handlers == ["do_GET"], f"the read API must stay GET-only (found handlers: {handlers})"
    for marker in ("ThreadingHTTPServer", "ThreadingMixIn"):
        assert marker not in text, f"http_read_api.py must stay single-threaded plain HTTPServer (found {marker})"
    imported = set(_scan.imported_modules(_READ_API))
    assert "threading" not in imported and "asyncio" not in imported, (
        "http_read_api.py must not grow its own thread/async machinery before 07D-3b"
    )
    # Dormancy census: no production module imports it or calls its constructors.
    offenders: List[str] = []
    for pkg in _scan.SERVICE_PACKAGES + ["shared"]:
        for path in _product_files(_scan.BACKEND_ROOT / pkg):
            if path == _READ_API:
                continue
            if any(mod.endswith("http_read_api") for mod in _scan.imported_modules(path)):
                offenders.append(f"{_scan.relposix(path)} imports http_read_api")
                continue
            used = _names_used(_tree(path))
            if "make_server" in used or "serve_forever" in used:
                offenders.append(f"{_scan.relposix(path)} references make_server/serve_forever")
    assert not offenders, f"the HTTP read API must stay product-unwired until the 07E transport decision (with 07D-3b): {offenders}"


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
            test_control_store_keeps_single_connection_shape_and_tier2_marker,
            test_composition_root_wires_no_concurrent_transport,
            test_http_read_api_stays_dormant_get_only_single_threaded,
            test_product_thread_import_census_is_frozen_to_benign_set,
            test_verify_yield_policy_constants_pinned,
            test_cas_caller_census_frozen_to_five_production_sites,
        ]
    )
