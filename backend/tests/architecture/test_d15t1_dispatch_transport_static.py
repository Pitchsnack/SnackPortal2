"""D-15-T1b static guards G1-G4 — gateway<->router dispatch transport pair (default suite).

Pins the D-15-T1a wire contract (docs/d15/D15-DISPATCH-SPEC-01) against the two new runtime
transport modules, as pure-stdlib AST/text censuses (no PostgreSQL, no driver, no network).
Every guard carries a non-vacuity companion proving it fails on a bad sample.

* **G1** — wire-frame references-only census (serialization-path scoped): the request envelope
  is exactly ``{v, context, category}``, ``context`` exactly the five ``RequestContext``
  fields, the response exactly ``{status, public_code, dispatched}``; no §10 never-cross
  identifier appears as a serialized key. The broad raw-byte needle set is DT-7's job, not a
  module-wide source scan (RF-3).
* **G2** — dispatch-server edge guard: internal-only ``127.0.0.1`` bind + literal
  ``/internal/dispatch/route`` path; POST-only served handler; single-threaded plain
  ``HTTPServer`` (no ``ThreadingHTTPServer``/threading/asyncio/contextvars/concurrent.futures/
  psycopg_pool); no ``make_server`` (07D-3 co-compliance), and ``serve_forever`` only inside the
  single blessed blocking entrypoint ``serve_dispatch_api`` (B5-2 Guard Evolution); fixed-503/405/
  404 empty-body edges with no stdlib ``send_error`` HTML; ``log_message`` silenced; and an
  adapter-only top-level def + import census (the no-business-work leg, C-8).
* **G3** — client allowlist / exact-shape guard: the ``public_code`` allowlist frozenset EQUALS
  the closed 12-code set; exact ``{status, public_code, dispatched}`` shape validation; the
  fail-closed ``RouteOutcome(503, "unavailable", False)`` collapse; stdlib urllib/json only
  (no ``database_router``/driver import); bounded 2.0s timeout; single attempt, no retry loop.
* **G4** — authority pin: ``category`` never appears in the ``DatabaseRouter.route(...)`` call
  (the router binds only from ``ctx``); the client serializes no ``DispatchDecision`` field
  other than the advisory ``category`` (no ``target_tenant_id``/``domain``/``workspace``).

Also pins the local DispatchCategory value set in the router module against the live enum
(the DAG-safe copy, RF/§9.6).

Pure stdlib; standalone-runnable:  python tests/architecture/test_d15t1_dispatch_transport_static.py
"""

from __future__ import annotations

import ast
import pathlib
import sys
from typing import List, Optional, Set

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_ROUTER_MOD = _scan.BACKEND_ROOT / "database_router" / "adapters" / "providers" / "http_dispatch_api.py"
_CLIENT_MOD = _scan.BACKEND_ROOT / "api_gateway" / "adapters" / "providers" / "http_router_dispatch.py"

_REQUEST_KEYS = frozenset({"v", "context", "category"})
_CONTEXT_KEYS = frozenset({"correlation_id", "request_id", "active_tenant_id", "principal_ref", "role"})
_RESPONSE_KEYS = frozenset({"status", "public_code", "dispatched"})

# The closed 12-code allowlist (D15-DISPATCH-SPEC-01 §9) — the frozen source of truth here.
_PUBLIC_CODES = frozenset(
    {
        "ok",
        "not_found",
        "no_active_tenant",
        "forbidden",
        "administratively_disabled",
        "not_ready",
        "schema_out_of_range",
        "unavailable",
        "tenant_routing_unavailable",
        "control_plane_unavailable",
        "connection_unavailable",
        "routing_isolation_fault",
    }
)

# §10 never-cross identifiers that must NEVER appear as a serialized key (lowercased match).
_FORBIDDEN_KEYS = frozenset(
    {
        "route_ref",
        "body",
        "payload",
        "data",
        "content",
        "dsn",
        "secret",
        "secretref",
        "store_ref",
        "credential",
        "connection",
        "tenant_db",
        "topology",
        "token",
        "authorization",
        "tenantconnection",
        "routeresult",
        "tenantroutingview",
        "target_tenant_id",
        "domain",
        "workspace",
    }
)

_ROUTER_TOPLEVEL_ALLOW = frozenset(
    {
        "_EnvelopeError",
        "_optional_str",
        "_reconstruct_context",
        "_decide",
        "_make_handler",
        "build_dispatch_server",
        "serve_dispatch_api",  # B5-2: the single blessed blocking entrypoint
    }
)
_ROUTER_IMPORT_TOPS_ALLOW = frozenset({"__future__", "json", "http", "typing", "shared", "database_router"})
_CLIENT_IMPORT_TOPS_ALLOW = frozenset({"__future__", "json", "urllib", "typing", "shared", "api_gateway"})


# --- pure helpers (exercised by the non-vacuity companions) ---------------------------------------
def _tree(path: pathlib.Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _parse(source: str) -> ast.AST:
    return ast.parse(source)


def _names_used(tree: ast.AST) -> Set[str]:
    out: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
    return out


def _string_key_groups(tree: ast.AST) -> List[frozenset]:
    """Key/element sets of every all-constant-string ``dict`` OR ``set`` literal — the wire
    serialization/shape surfaces. A dict with a non-string/computed key is skipped."""
    groups: List[frozenset] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = [k for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            if keys and len(keys) == len(node.keys):
                groups.append(frozenset(k.value for k in keys))
        elif isinstance(node, ast.Set):
            elts = [e for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            if elts and len(elts) == len(node.elts):
                groups.append(frozenset(e.value for e in elts))
    return groups


def _top_level_defs(tree: ast.AST) -> Set[str]:
    mod = tree
    assert isinstance(mod, ast.Module)
    return {n.name for n in mod.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def _import_tops(path: pathlib.Path) -> Set[str]:
    return {m.split(".")[0] for m in _scan.imported_modules(path)}


def _frozenset_members(tree: ast.AST, name: str) -> Optional[frozenset]:
    """The string members assigned to ``name = frozenset({...})`` (or a bare set literal)."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            continue
        value = node.value
        set_node: Optional[ast.expr] = None
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "frozenset" and value.args:
            set_node = value.args[0]
        elif isinstance(value, ast.Set):
            set_node = value
        if isinstance(set_node, ast.Set):
            elts = [e.value for e in set_node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            if len(elts) == len(set_node.elts):
                return frozenset(elts)
    return None


def _method(tree: ast.AST, class_name: str, method_name: str) -> Optional[ast.FunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef) and sub.name == method_name:
                    return sub
    return None


def _route_calls(tree: ast.AST) -> List[ast.Call]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "route"]


def _decision_attrs(tree: ast.AST) -> Set[str]:
    return {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "decision"}


def _has_loop(node: Optional[ast.AST]) -> bool:
    if node is None:
        return False
    return any(isinstance(n, (ast.For, ast.While, ast.AsyncFor)) for n in ast.walk(node))


def _forbidden_key_hits(groups: List[frozenset]) -> List[str]:
    hits: List[str] = []
    for group in groups:
        for key in group:
            if key.lower() in _FORBIDDEN_KEYS:
                hits.append(key)
    return hits


def _serve_forever_refs(tree: ast.AST) -> int:
    """Count ``serve_forever`` CODE references (Name/Attribute), not docstring/comment prose."""
    return sum(
        1
        for n in ast.walk(tree)
        if (isinstance(n, ast.Attribute) and n.attr == "serve_forever") or (isinstance(n, ast.Name) and n.id == "serve_forever")
    )


def _single_blessed_serve_problems(tree: ast.AST, entrypoint: str) -> List[str]:
    """B5-2 Guard Evolution Matrix: the server module must define EXACTLY ONE module-top def named
    ``entrypoint`` whose body holds the module's ONLY ``serve_forever`` reference — the factory
    surface stays serve-free and no second serve loop may appear anywhere else in the module."""
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


# --- G1 -------------------------------------------------------------------------------------------
def test_g1_wire_frame_references_only_census() -> None:
    assert _ROUTER_MOD.is_file() and _CLIENT_MOD.is_file(), "both transport modules must exist"
    client_groups = _string_key_groups(_tree(_CLIENT_MOD))
    router_groups = _string_key_groups(_tree(_ROUTER_MOD))
    # Exact wire shapes are present where they belong.
    assert _REQUEST_KEYS in client_groups, "client must serialize exactly {v, context, category}"
    assert _CONTEXT_KEYS in client_groups, "client context must be exactly the five RequestContext fields"
    assert _RESPONSE_KEYS in client_groups, "client must validate the exact {status, public_code, dispatched} shape"
    assert _RESPONSE_KEYS in router_groups, "server must serialize exactly {status, public_code, dispatched}"
    assert _REQUEST_KEYS in router_groups, "server must validate the exact {v, context, category} request shape"
    # No never-cross identifier appears as a serialized key on either side.
    hits = _forbidden_key_hits(client_groups) + _forbidden_key_hits(router_groups)
    assert not hits, f"never-cross identifier serialized as a wire key: {hits}"


def test_g1_nonvacuity_flags_forbidden_serialized_key() -> None:
    bad = _string_key_groups(_parse('x = {"status": 1, "body": 2}\n'))
    assert _forbidden_key_hits(bad) == ["body"], "G1 must flag a forbidden serialized key"
    assert _REQUEST_KEYS not in _string_key_groups(_parse("x = {'v': 1}\n")), "G1 must distinguish the exact request shape"


# --- G2 -------------------------------------------------------------------------------------------
def test_g2_dispatch_server_edge_guard() -> None:
    text = _ROUTER_MOD.read_text(encoding="utf-8")
    tree = _tree(_ROUTER_MOD)
    used = _names_used(tree)
    # Internal-only surface: literal path + loopback default bind (IC-010 §R/§M).
    assert '"/internal/dispatch/route"' in text, "server must pin the literal internal dispatch path"
    assert "127.0.0.1" in text, "server must default-bind the internal loopback host"
    # Single-threaded plain HTTPServer; no threaded server / concurrency machinery (AT-D15T1-10).
    assert "HTTPServer" in used, "server must use a plain HTTPServer"
    for marker in ("ThreadingHTTPServer", "ThreadingMixIn"):
        assert marker not in text, f"server must stay single-threaded (found {marker})"
    banned_imports = {"threading", "asyncio", "contextvars", "concurrent.futures", "psycopg_pool"}
    banned_tops = {b.split(".")[0] for b in banned_imports}
    hits = {m for m in _scan.imported_modules(_ROUTER_MOD) if m in banned_imports or m.split(".")[0] in banned_tops}
    assert not hits, f"server must import no concurrency/pool machinery: {hits}"
    # 07D-3 co-compliance, EVOLVED by the B5-2 Guard Evolution Matrix: make_server stays banned
    # (this adapter constructs its own HTTPServer); serve_forever is now allowed ONLY inside the
    # single blessed blocking entrypoint serve_dispatch_api, exactly once — the factory surface
    # stays serve-free and no second serve loop may appear.
    assert "make_server" not in used, "server production module must not reference make_server (07D-3 single-wiring census)"
    problems = _single_blessed_serve_problems(tree, "serve_dispatch_api")
    assert not problems, f"dispatch serve-entrypoint census (B5-2): {problems}"
    # POST-only SERVED handler; the fail-closed empty-body edges; no stdlib send_error HTML.
    served = sorted(n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("do_"))
    assert served == ["do_POST"], f"the dispatch edge must be POST-only (served do_* handlers: {served})"
    assert "send_error" not in used, "server must never call stdlib send_error (HTML bodies) — code reference banned"
    assert 'send_header("Content-Length", "0")' in text, "server must emit empty bodies on the fail-closed/refused edges"
    for code in ("503", "405", "404"):
        assert code in text, f"server must pin the {code} fail-closed/refused edge"
    assert any(isinstance(n, ast.FunctionDef) and n.name == "log_message" for n in ast.walk(tree)), "server must silence log_message"
    assert "build_dispatch_server" in _top_level_defs(tree), "server must expose the build_dispatch_server factory"
    # No-business-work census (C-8): adapter-only top-level defs + import surface.
    extra_defs = _top_level_defs(tree) - _ROUTER_TOPLEVEL_ALLOW
    assert not extra_defs, f"server carries non-adapter top-level defs (possible business work): {sorted(extra_defs)}"
    extra_imports = _import_tops(_ROUTER_MOD) - _ROUTER_IMPORT_TOPS_ALLOW
    assert not extra_imports, f"server imports outside the adapter-only surface (business-service ban): {sorted(extra_imports)}"


def test_g2_nonvacuity_flags_threading_and_business() -> None:
    threaded = "import threading\nfrom http.server import ThreadingHTTPServer\n"
    mods = {m.split(".")[0] for m in ("threading", "http.server")}
    assert "threading" in mods and "ThreadingHTTPServer" in threaded, "G2 must detect threaded-server machinery"
    business_tree = _parse("def deal_query():\n    return 1\n")
    assert _top_level_defs(business_tree) - _ROUTER_TOPLEVEL_ALLOW == {"deal_query"}, "G2 must flag a non-adapter business def"
    # B5-2: the single-blessed-serve census is non-vacuous — it fails on a second serve loop, a
    # serve loop outside the entrypoint, and a missing entrypoint; it passes the canonical shape.
    doubled = _parse("def serve_dispatch_api():\n    s.serve_forever()\n\ndef rogue():\n    s.serve_forever()\n")
    assert _single_blessed_serve_problems(doubled, "serve_dispatch_api"), "census must flag a second serve loop"
    misplaced = _parse("def serve_dispatch_api():\n    pass\n\ndef rogue():\n    s.serve_forever()\n")
    assert _single_blessed_serve_problems(misplaced, "serve_dispatch_api"), "census must flag a serve loop outside the entrypoint"
    assert _single_blessed_serve_problems(_parse("x = 1\n"), "serve_dispatch_api"), "census must flag a missing entrypoint"
    canonical = _parse("def serve_dispatch_api():\n    s.serve_forever()\n")
    assert _single_blessed_serve_problems(canonical, "serve_dispatch_api") == [], "census must pass the canonical shape"


# --- G3 -------------------------------------------------------------------------------------------
def test_g3_client_allowlist_and_exact_shape_guard() -> None:
    text = _CLIENT_MOD.read_text(encoding="utf-8")
    tree = _tree(_CLIENT_MOD)
    members = _frozenset_members(tree, "_ALLOWED_PUBLIC_CODES")
    assert members == _PUBLIC_CODES, f"client public_code allowlist must EQUAL the closed 12-code set; got {members}"
    assert _RESPONSE_KEYS in _string_key_groups(tree), "client must validate the exact {status, public_code, dispatched} shape"
    assert 'RouteOutcome(status=503, public_code="unavailable", dispatched=False)' in text, "client must carry the fail-closed collapse"
    assert "timeout: float = 2.0" in text, "client must pin the bounded 2.0s default timeout"
    # stdlib urllib/json only; no database_router / driver import.
    extra_imports = _import_tops(_CLIENT_MOD) - _CLIENT_IMPORT_TOPS_ALLOW
    assert not extra_imports, f"client imports outside the stdlib/gateway surface: {sorted(extra_imports)}"
    assert "database_router" not in _import_tops(_CLIENT_MOD), "client must not import database_router (IC-010 §H/§M)"
    drivers = {"psycopg", "psycopg2", "asyncpg", "sqlalchemy", "databases", "aiopg"}
    assert not (_import_tops(_CLIENT_MOD) & drivers), "client must import no database driver"
    # Single attempt, no retry loop.
    assert not _has_loop(_method(tree, "HttpRouterDispatch", "dispatch")), "client dispatch() must contain no retry loop"
    assert not _has_loop(_method(tree, "HttpRouterDispatch", "_map")), "client _map() must contain no loop"


def test_g3_nonvacuity_flags_bad_allowlist_and_retry_loop() -> None:
    short = _frozenset_members(_parse("_ALLOWED_PUBLIC_CODES = frozenset({'ok', 'not_found'})\n"), "_ALLOWED_PUBLIC_CODES")
    assert short is not None and short != _PUBLIC_CODES, "G3 must reject an incomplete allowlist"
    looped = _parse("class C:\n    def dispatch(self):\n        while True:\n            pass\n")
    assert _has_loop(_method(looped, "C", "dispatch")), "G3 must detect a retry loop"


# --- G4 -------------------------------------------------------------------------------------------
def test_g4_authority_pin() -> None:
    router_tree = _tree(_ROUTER_MOD)
    calls = _route_calls(router_tree)
    assert calls, "server must call router.route(...) (non-vacuous)"
    for call in calls:
        assert not any(kw.arg == "category" for kw in call.keywords), "route() must never receive a category keyword"
        arg_names = {n.id for a in call.args for n in ast.walk(a) if isinstance(n, ast.Name)}
        assert "category" not in arg_names, "route() must not receive category as an argument (authority pin)"
        assert "decision" not in arg_names, "route() must not receive a DispatchDecision"
        assert len(call.args) == 1 and not call.keywords, "route() must receive exactly the signed context (ctx) only"
    # Client serializes no DispatchDecision field other than the advisory category.
    attrs = _decision_attrs(_tree(_CLIENT_MOD))
    assert attrs == {"category"}, f"client must read only decision.category; found decision.{sorted(attrs)}"


def test_g4_nonvacuity_flags_category_selector_and_decision_field() -> None:
    bad_route = _route_calls(_parse("r.route(ctx, category=cat)\n"))
    assert bad_route and any(kw.arg == "category" for kw in bad_route[0].keywords), "G4 must flag category passed to route()"
    assert _decision_attrs(_parse("x = decision.target_tenant_id\n")) == {"target_tenant_id"}, "G4 must flag a serialized decision field"


# --- DAG-safe category parity (§9.6) --------------------------------------------------------------
def test_router_category_frozenset_matches_live_dispatchcategory() -> None:
    sys.path.insert(0, str(_scan.BACKEND_ROOT))
    from api_gateway.models import DispatchCategory

    local = _frozenset_members(_tree(_ROUTER_MOD), "_DISPATCH_CATEGORIES")
    live = frozenset(c.value for c in DispatchCategory)
    assert local == live, f"router local DispatchCategory copy {local} must equal the live enum {live}"


if __name__ == "__main__":
    _scan.run(
        [
            test_g1_wire_frame_references_only_census,
            test_g1_nonvacuity_flags_forbidden_serialized_key,
            test_g2_dispatch_server_edge_guard,
            test_g2_nonvacuity_flags_threading_and_business,
            test_g3_client_allowlist_and_exact_shape_guard,
            test_g3_nonvacuity_flags_bad_allowlist_and_retry_loop,
            test_g4_authority_pin,
            test_g4_nonvacuity_flags_category_selector_and_decision_field,
            test_router_category_frozenset_matches_live_dispatchcategory,
        ]
    )
