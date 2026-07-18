"""Served API Gateway Edge V1 — static/AST boundary guard (default suite; pure stdlib).

Pins the served northbound edge (``api_gateway/adapters/providers/http_gateway_edge.py``) to a
transport-only contract without binding a socket, opening a database, or reaching the network.
Module-scoped and non-vacuous: the guard fails if the edge module disappears or empties, and each
census carries a companion proving it flags a bad sample. It enforces:

* single-threaded stdlib only — plain ``HTTPServer`` (never ``ThreadingHTTPServer``), no threading /
  asyncio / web framework, no new dependency;
* no sibling-service / database-driver / vendor-SDK / crypto import (edge-only enforcement boundary);
* the Gateway core is called EXACTLY ONCE (``gateway.handle``) — the edge owns no auth / authorization /
  routing / tenant selection / DTO composition / business logic;
* a CLOSED transport route allowlist == {/memberships, /health, /readiness} — /tenant, /directory,
  /import and any unknown path never appear;
* correlation accept/mint/echo is present (the ``x-correlation-id`` header, a mint via ``uuid4``);
* CORS is exact-origin only — never a wildcard origin, never credentialed CORS
  (``Access-Control-Allow-Credentials: false``);
* success bodies come ONLY from the core-owned ``serialize_portal_dto`` — the edge hand-rolls no DTO
  (it constructs no portal DTO type) and calls the stdlib HTML error path (``send_error``) never;
* no raw leakage surface — no ``logging`` / ``print`` / ``traceback`` / connection-string literal;
* ``log_message`` is silenced;
* exactly ONE blessed blocking entrypoint ``serve_gateway_edge`` — one ``serve_forever`` inside it and
  ``server_close`` for teardown.

Standalone-runnable:  python tests/architecture/test_gateway_edge_boundaries.py
"""

from __future__ import annotations

import ast
import pathlib
import sys
from typing import List, Optional, Set

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_EDGE = _scan.BACKEND_ROOT / "api_gateway" / "adapters" / "providers" / "http_gateway_edge.py"

_IMPORT_TOPS_ALLOW = frozenset({"__future__", "json", "re", "uuid", "http", "typing", "api_gateway"})
_FORBIDDEN_TOPS = frozenset(
    {
        "auth_router",
        "control_plane",
        "database_router",
        "import_service",
        "lineage_service",
        "jwt",
        "cryptography",
        "psycopg",
        "psycopg2",
        "asyncpg",
        "sqlalchemy",
        "databases",
        "aiopg",
        "supabase",
        "lovable",
        "threading",
        "asyncio",
        "contextvars",
        "concurrent",
        "multiprocessing",
        "fastapi",
        "flask",
        "django",
        "starlette",
        "uvicorn",
        "gunicorn",
        "aiohttp",
        "tornado",
        "logging",
        "socketserver",
    }
)

_EXPECTED_ROUTES = frozenset({"/memberships", "/health", "/readiness"})
# Portal DTO types the edge must never construct itself (it serializes only what the core composed).
_FORBIDDEN_DTO_NAMES = frozenset(
    {
        "MembershipEntryDTO",
        "WorkspaceMembershipDTO",
        "GlobalStartupSummaryDTO",
        "GlobalInvestorSummaryDTO",
        "ImportInitiationDTO",
        "DirectoryEntryDTO",
        "compose_portal_dto",
    }
)


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


def _top_level_defs(tree: ast.AST) -> Set[str]:
    mod = tree
    assert isinstance(mod, ast.Module)
    return {n.name for n in mod.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def _import_tops(path: pathlib.Path) -> Set[str]:
    return {m.split(".")[0] for m in _scan.imported_modules(path)}


def _tops_of_source(source: str) -> Set[str]:
    mods: List[str] = []
    for node in ast.walk(_parse(source)):
        if isinstance(node, ast.Import):
            mods.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.append(node.module)
    return {m.split(".")[0] for m in mods}


def _attr_call_count(tree: ast.AST, attr: str) -> int:
    return sum(1 for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == attr)


def _name_call_count(tree: ast.AST, name: str) -> int:
    return sum(1 for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name)


def _print_calls(tree: ast.AST) -> int:
    return _name_call_count(tree, "print")


def _dict_string_keys(tree: ast.AST, var: str) -> Optional[Set[str]]:
    """The constant-string key set of the module-level ``var = {...}`` dict literal (or None)."""
    mod = tree
    assert isinstance(mod, ast.Module)
    for node in mod.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == var
            and isinstance(node.value, ast.Dict)
        ):
            keys = [k.value for k in node.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            return set(keys)
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == var:
                    keys = [k.value for k in node.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
                    return set(keys)
    return None


def _serve_forever_refs(tree: ast.AST) -> int:
    return sum(
        1
        for n in ast.walk(tree)
        if (isinstance(n, ast.Attribute) and n.attr == "serve_forever") or (isinstance(n, ast.Name) and n.id == "serve_forever")
    )


def _def(tree: ast.AST, name: str) -> Optional[ast.AST]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _has_loop(node: ast.AST) -> bool:
    return any(isinstance(n, (ast.For, ast.While, ast.AsyncFor)) for n in ast.walk(node))


def _nonempty(path: pathlib.Path) -> bool:
    return path.is_file() and bool(path.read_text(encoding="utf-8").strip())


# --- single-threaded stdlib + import surface ------------------------------------------------------
def test_edge_is_single_threaded_stdlib_only() -> None:
    assert _nonempty(_EDGE), "the served gateway-edge module must exist and be non-empty"
    text = _EDGE.read_text(encoding="utf-8")
    tree = _tree(_EDGE)
    used = _names_used(tree)
    assert "HTTPServer" in used, "the edge must use a plain single-threaded HTTPServer"
    assert "ThreadingHTTPServer" not in used, "the edge must never use ThreadingHTTPServer (AT-D15T1-10)"
    assert "ThreadingMixIn" not in text, "the edge must not mix in threading"
    tops = _import_tops(_EDGE)
    extra = tops - _IMPORT_TOPS_ALLOW
    assert not extra, f"the edge imports outside the stdlib/gateway surface: {sorted(extra)}"
    banned = tops & _FORBIDDEN_TOPS
    assert not banned, f"the edge must import no sibling service / driver / vendor / concurrency / framework: {sorted(banned)}"


def test_edge_calls_gateway_handle_exactly_once() -> None:
    tree = _tree(_EDGE)
    handle_calls = _attr_call_count(tree, "handle")
    assert handle_calls == 1, f"the edge must call the Gateway core exactly once (gateway.handle); found {handle_calls}"
    # The edge owns no auth/authorization/routing/composition — it must not use those primitives.
    used = _names_used(tree)
    for banned_name in ("authenticate", "decide", "dispatch", "compose_portal_dto", "recognized_carriers", "build_request_context"):
        assert banned_name not in used, f"the edge must not perform core logic ({banned_name})"
    # No retry loop may wrap the single Gateway.handle call — the enclosing _handle_memberships
    # business path must contain no loop (an automatic downstream retry is rejected here, and also
    # by the behavioral exactly-once handle counting).
    mm = _def(tree, "_handle_memberships")
    assert mm is not None, "the edge must own the _handle_memberships business path"
    assert not _has_loop(mm), "the Gateway.handle call must not be wrapped in a retry loop"


def test_edge_route_allowlist_is_closed() -> None:
    keys = _dict_string_keys(_tree(_EDGE), "_EXPOSED_ROUTES")
    assert keys is not None, "the edge must define the _EXPOSED_ROUTES allowlist dict"
    assert keys == set(_EXPECTED_ROUTES), f"the route allowlist must be exactly {sorted(_EXPECTED_ROUTES)}; got {sorted(keys)}"
    for hidden in ("/tenant", "/directory", "/import"):
        assert hidden not in keys, f"the edge must never expose {hidden}"


def test_edge_correlation_accept_mint_echo() -> None:
    text = _EDGE.read_text(encoding="utf-8")
    tree = _tree(_EDGE)
    assert '"x-correlation-id"' in text, "the edge must handle the x-correlation-id header"
    used = _names_used(tree)
    assert "uuid4" in used, "the edge must mint a correlation id via uuid4 when absent/malformed"
    assert _def(tree, "_correlation_id") is not None, "the edge must own a _correlation_id accept/mint helper"


def test_edge_cors_exact_origin_no_credentialed_wildcard() -> None:
    text = _EDGE.read_text(encoding="utf-8")
    tree = _tree(_EDGE)
    assert "allowed_origins" in _names_used(tree), "the edge must gate CORS on the exact-origin allowlist"
    assert '"Access-Control-Allow-Credentials", "false"' in text, "credentialed CORS is forbidden (Allow-Credentials must be false)"
    assert '"Access-Control-Allow-Credentials", "true"' not in text, "the edge must never enable credentialed CORS"
    assert '"Access-Control-Allow-Origin", "*"' not in text, "the edge must never emit a wildcard CORS origin"


def test_edge_serialize_portal_dto_is_only_success_serializer() -> None:
    used = _names_used(_tree(_EDGE))
    assert "serialize_portal_dto" in used, "success bodies must be produced by the core-owned serialize_portal_dto"
    hand_rolled = _FORBIDDEN_DTO_NAMES & used
    assert not hand_rolled, f"the edge must not construct/compose portal DTOs itself: {sorted(hand_rolled)}"


def test_edge_no_raw_error_or_secret_leakage() -> None:
    text = _EDGE.read_text(encoding="utf-8")
    tree = _tree(_EDGE)
    used = _names_used(tree)
    assert "send_error" not in used, "the edge must never call stdlib send_error (HTML/detail bodies)"
    assert "traceback" not in used and "format_exc" not in used, "the edge must never render a traceback"
    assert _print_calls(tree) == 0, "the edge must not print (no token/payload logging)"
    assert 'send_header("Content-Length", "0")' in text, "denials/rejections must carry an EMPTY body"
    lowered = text.lower()
    for needle in ("postgresql://", "postgres://", "database_url", "secretref"):
        assert needle not in lowered, f"the edge must carry no connection-string / secret material ({needle})"


def test_edge_log_message_silenced() -> None:
    assert _def(_tree(_EDGE), "log_message") is not None, "the edge must silence log_message (no stderr request logging)"


def test_edge_single_blessed_serve_entrypoint_and_close() -> None:
    tree = _tree(_EDGE)
    text = _EDGE.read_text(encoding="utf-8")
    entry = _def(tree, "serve_gateway_edge")
    assert entry is not None, "the edge must define the single blessed blocking entrypoint serve_gateway_edge"
    inside = _serve_forever_refs(entry)
    total = _serve_forever_refs(tree)
    assert inside == 1, f"serve_gateway_edge must reference serve_forever exactly once, found {inside}"
    assert total == inside, f"serve_forever must appear ONLY inside serve_gateway_edge ({total} total vs {inside} inside)"
    assert "server_close" in _names_used(tree), "the entrypoint must close the server (server_close in finally)"
    assert "def build_gateway_edge_server" in text, "the edge must expose the build_gateway_edge_server factory"


# --- non-vacuity companions -----------------------------------------------------------------------
def test_edge_boundary_guard_nonvacuity() -> None:
    # Import bans flag a planted sibling/driver/concurrency import.
    assert _tops_of_source("import threading\nfrom control_plane.x import y\n") & _FORBIDDEN_TOPS == {"threading", "control_plane"}, (
        "the import ban-set must flag a planted forbidden import"
    )
    # The Gateway.handle census counts real calls (a doubled call is detectable).
    assert _attr_call_count(_parse("g.handle(a)\ng.handle(b)\n"), "handle") == 2, "the handle census must count calls"
    # The route-allowlist extractor reads the dict keys and would flag a widened set.
    widened = _parse('_EXPOSED_ROUTES = {"/memberships": 1, "/directory": 2}\n')
    assert _dict_string_keys(widened, "_EXPOSED_ROUTES") == {"/memberships", "/directory"}, "the route extractor must read keys"
    assert _dict_string_keys(widened, "_EXPOSED_ROUTES") != set(_EXPECTED_ROUTES), "a widened allowlist must be detectable"
    # The serve-loop census flags a second/misplaced serve loop and a missing entrypoint.
    doubled = _parse("def serve_gateway_edge():\n    s.serve_forever()\n\ndef rogue():\n    s.serve_forever()\n")
    entry = _def(doubled, "serve_gateway_edge")
    assert entry is not None and _serve_forever_refs(entry) == 1 and _serve_forever_refs(doubled) == 2, (
        "a second serve loop must be detectable"
    )
    # A hand-rolled DTO construction is flagged.
    assert _FORBIDDEN_DTO_NAMES & _names_used(_parse("x = WorkspaceMembershipDTO(memberships=())\n")) == {"WorkspaceMembershipDTO"}, (
        "a hand-rolled DTO must be flagged"
    )
    # A print (token-logging) is detectable.
    assert _print_calls(_parse("print(authorization)\n")) == 1, "a print (token logging) must be detectable"
    # A retry loop wrapping the handle call is detectable (and a loop-free body passes).
    assert _has_loop(_parse("def _handle_memberships():\n    while True:\n        g.handle(r)\n")), "a retry loop must be detectable"
    assert not _has_loop(_parse("def _handle_memberships():\n    g.handle(r)\n")), "a loop-free business path must pass"


if __name__ == "__main__":
    _scan.run(
        [
            test_edge_is_single_threaded_stdlib_only,
            test_edge_calls_gateway_handle_exactly_once,
            test_edge_route_allowlist_is_closed,
            test_edge_correlation_accept_mint_echo,
            test_edge_cors_exact_origin_no_credentialed_wildcard,
            test_edge_serialize_portal_dto_is_only_success_serializer,
            test_edge_no_raw_error_or_secret_leakage,
            test_edge_log_message_silenced,
            test_edge_single_blessed_serve_entrypoint_and_close,
            test_edge_boundary_guard_nonvacuity,
        ]
    )
