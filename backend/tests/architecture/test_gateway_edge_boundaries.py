"""Served API Gateway Edge V1 — static/AST boundary guard (default suite; pure stdlib).

Pins the served northbound edge (``api_gateway/adapters/providers/http_gateway_edge.py``) to a
transport-only contract without binding a socket, opening a database, or reaching the network.
Module-scoped and non-vacuous: the guard fails if the edge module disappears or empties, and each
census carries a companion proving it flags a bad sample. It enforces:

* the edge serves through the SHARED containment-zone ASGI runtime (``build_asgi_server``) and
  owns no server, socket, or concurrency machinery of its own — it must not import ``uvicorn`` /
  ``starlette`` / ``threading`` / ``asyncio`` directly, and FastAPI is the ONE sanctioned
  framework (no second web framework may appear);
* no sibling-service / database-driver / vendor-SDK / crypto import (edge-only enforcement boundary);
* the Gateway core is called EXACTLY ONCE (``gateway.handle``, through the one shared ``_invoke_core``
  site reached by both business paths) — the edge owns no auth / authorization / routing / tenant
  selection / DTO composition / business logic;
* a CLOSED static transport route allowlist == {/memberships, /health, /readiness} — /tenant, /directory
  and any unknown path never appear; plus the W1b bounded, traversal-safe ``POST /import/<source_ref>``
  route (multi-segment, 512-byte-capped, POST+OPTIONS only) served via a DEDICATED matcher, never as a
  static allowlist key;
* correlation accept/mint/echo is present (the ``x-correlation-id`` header, a mint via ``uuid4``);
* CORS is exact-origin only — never a wildcard origin, never credentialed CORS
  (``Access-Control-Allow-Credentials: false``);
* success bodies come ONLY from the core-owned ``serialize_portal_dto`` — the edge hand-rolls no DTO
  (it constructs no portal DTO type) and calls the stdlib HTML error path (``send_error``) never;
* no raw leakage surface — no ``logging`` / ``print`` / ``traceback`` / connection-string literal;
* request logging stays disabled at the shared runtime (``access_log=False``, ``log_config=None``)
  — the migrated home of the stdlib edge's silenced ``log_message``;
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

if str(_scan.BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_scan.BACKEND_ROOT))

# W1b: the edge's bounded import matcher + its pins are pure, socket-free values — imported and
# exercised directly by the import-route guard below (no bind, no network, no database).
# D-42 CLM: the bounded tenant Startup matcher + its pins are exercised the same way.
from api_gateway.adapters.providers.http_gateway_edge import (  # noqa: E402
    _IMPORT_TARGET_METHODS,
    _MAX_PATCH_BODY_BYTES,
    _MAX_SOURCE_REF_BYTES,
    _MAX_STARTUP_REF_BYTES,
    _TENANT_STARTUP_METHODS,
    _is_valid_import_target,
    _is_valid_tenant_startup_target,
)

_EDGE = _scan.BACKEND_ROOT / "api_gateway" / "adapters" / "providers" / "http_gateway_edge.py"

# The two parameterized families register through module constants, so the served method set has to be
# read from the DECORATORS keyed by the constant NAME — not from a sibling constant, which would only
# ever agree with itself.
_IMPORT_ROUTE_TEMPLATE_NAME = "_IMPORT_ROUTE_TEMPLATE"
_TENANT_STARTUP_ROUTE_TEMPLATE_NAME = "_TENANT_STARTUP_ROUTE_TEMPLATE"


def _served_methods(route_key: str) -> frozenset:
    """The methods the edge ACTUALLY registers for ``route_key`` (literal path or constant name).

    Raises if the registration's ``methods=`` is a computed expression: the two parameterized families
    must stay statically enumerable, or this guard silently goes blind again.
    """
    tree = ast.parse(_EDGE.read_text(encoding="utf-8"), filename=str(_EDGE))
    served = frozenset(method for path, method in _scan.route_registrations(tree) if path == route_key)
    assert _scan.COMPUTED_METHODS.upper() not in served, (
        f"{route_key} registers a COMPUTED methods= expression. The three unparameterized routes may do that (they are "
        "registered FROM the _EXPOSED_ROUTES allowlist, which is separately pinned), but the two parameterized families "
        "must declare a literal method list — otherwise no static guard can see the served surface widen."
    )
    assert served, f"{route_key} registers no route at all — the census cannot be vacuous"
    return served


# The shared containment-zone ASGI runtime the edge MUST serve through (it constructs no server).
_RUNTIME = _scan.BACKEND_ROOT / "shared" / "adapters" / "providers" / "asgi_runtime.py"

# FastAPI is the ONE sanctioned framework import; the concrete ASGI server and its socket live in
# the shared runtime (`shared.adapters.providers.asgi_runtime`), never in the edge.
_IMPORT_TOPS_ALLOW = frozenset({"__future__", "json", "re", "uuid", "typing", "fastapi", "api_gateway", "shared"})
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
        # A second web framework is never permitted; FastAPI alone is sanctioned.
        "flask",
        "django",
        "gunicorn",
        "aiohttp",
        "tornado",
        # The edge must not reach past FastAPI to the ASGI server or its plumbing: the socket,
        # the serve loop, and the logging posture are the shared runtime's to own.
        "starlette",
        "uvicorn",
        "http",
        "socket",
        "socketserver",
        "logging",
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
def test_edge_serves_through_the_shared_runtime_only() -> None:
    assert _nonempty(_EDGE), "the served gateway-edge module must exist and be non-empty"
    text = _EDGE.read_text(encoding="utf-8")
    tree = _tree(_EDGE)
    used = _names_used(tree)
    # The edge composes an app and hands it to the SHARED runtime; it never builds a server itself.
    assert "build_asgi_server" in used, "the edge must build its server through the shared ASGI runtime"
    assert "AsgiEdgeServer" in used, "the edge must serve on the shared AsgiEdgeServer lifecycle"
    for hand_rolled in ("HTTPServer", "ThreadingHTTPServer", "ThreadingMixIn", "Thread", "run_in_executor"):
        assert hand_rolled not in text, f"the edge must not hand-roll a server/thread ({hand_rolled}); the shared runtime owns it"
    tops = _import_tops(_EDGE)
    extra = tops - _IMPORT_TOPS_ALLOW
    assert not extra, f"the edge imports outside the FastAPI/gateway/shared surface: {sorted(extra)}"
    banned = tops & _FORBIDDEN_TOPS
    assert not banned, f"the edge must import no sibling service / driver / vendor / concurrency / second framework: {sorted(banned)}"


def test_shared_runtime_disables_request_logging_and_server_disclosure() -> None:
    # The migrated home of the stdlib edge's silenced `log_message`: uvicorn must never install a
    # logging config or write an access log (no request line, header, token, or payload to stderr),
    # and must disclose no server identity/version header.
    assert _nonempty(_RUNTIME), "the shared ASGI runtime module must exist and be non-empty"
    runtime = _RUNTIME.read_text(encoding="utf-8")
    for pin in ("log_config=None", "access_log=False", "server_header=False"):
        assert pin in runtime, f"the shared ASGI runtime must pin {pin} (no request logging / no server disclosure)"
    assert _print_calls(_tree(_RUNTIME)) == 0, "the shared ASGI runtime must not print"


def test_edge_calls_gateway_handle_exactly_once() -> None:
    tree = _tree(_EDGE)
    handle_calls = _attr_call_count(tree, "handle")
    assert handle_calls == 1, f"the edge must call the Gateway core exactly once (gateway.handle); found {handle_calls}"
    # The edge owns no auth/authorization/routing/composition — it must not use those primitives.
    used = _names_used(tree)
    for banned_name in ("authenticate", "decide", "dispatch", "compose_portal_dto", "recognized_carriers", "build_request_context"):
        assert banned_name not in used, f"the edge must not perform core logic ({banned_name})"
    # W1b: the sole Gateway.handle call lives in the ONE shared _invoke_core site; BOTH business paths
    # (_handle_memberships + _handle_import) reach the core through it, and NONE of the three wraps the
    # call in a retry loop (an automatic downstream retry is rejected here, and also by the behavioral
    # exactly-once handle counting).
    shared = _def(tree, "_invoke_core")
    assert shared is not None, "the edge must own the single shared _invoke_core handle site"
    assert _attr_call_count(shared, "handle") == 1, "the sole gateway.handle call must live inside _invoke_core"
    for path_name in ("_invoke_core", "memberships", "import_route", "tenant_startup"):
        node = _def(tree, path_name)
        assert node is not None, f"the edge must own the {path_name} business path"
        assert not _has_loop(node), f"the Gateway.handle call must not be wrapped in a retry loop ({path_name})"


def test_edge_route_allowlist_is_closed() -> None:
    keys = _dict_string_keys(_tree(_EDGE), "_EXPOSED_ROUTES")
    assert keys is not None, "the edge must define the _EXPOSED_ROUTES allowlist dict"
    assert keys == set(_EXPECTED_ROUTES), f"the route allowlist must be exactly {sorted(_EXPECTED_ROUTES)}; got {sorted(keys)}"
    # /tenant and /directory are never exposed. The W1b import route carries a source_ref parameter and
    # is served ONLY via the dedicated bounded matcher (test_edge_import_route_...), NEVER as a static
    # allowlist key — so no "/import"* literal may appear in the static dict.
    for hidden in ("/tenant", "/directory"):
        assert hidden not in keys, f"the edge must never expose {hidden}"
    assert not any(k.startswith("/import") for k in keys), "the parameterized import route must not be a static allowlist key"


def test_edge_import_route_is_bounded_multisegment_and_post_only() -> None:
    # W1b: the served /import/<source_ref> matcher is a BOUNDED, traversal-safe, multi-segment route —
    # never a wildcard/prefix router — exercised directly (a pure, socket-free function).
    for ok in ("/import/g1", "/import/global-startup/rec-9", "/import/a.b_c-d/e1"):
        assert _is_valid_import_target(ok), f"{ok!r} must be an accepted bounded import target"
    for bad in (
        "/import",  # bare (no source_ref)
        "/import/",  # empty suffix
        "/import//rec-9",  # empty segment
        "/import/../rec-9",  # dot-dot traversal
        "/import/global-startup/../rec-9",  # interior dot-dot traversal
        "/import/%2e%2e/rec-9",  # percent-encoded dot-dot
        "/import/global-startup%2Frec-9",  # percent-encoded delimiter
        "/import/global-startup\\rec-9",  # backslash
        "/import/g1?tenant=t1",  # query form
        "/import/g1#frag",  # fragment form
        "/memberships",  # a different route
        "/importx/g1",  # prefix look-alike (not /import/)
    ):
        assert not _is_valid_import_target(bad), f"{bad!r} must be rejected by the bounded import matcher"
    # The source_ref byte bound is pinned at 512: at-bound accepted, over-bound rejected.
    assert _MAX_SOURCE_REF_BYTES == 512, "the source_ref byte bound must be pinned at 512"
    assert _is_valid_import_target("/import/" + "a" * 512), "a 512-byte source_ref is at the bound (accepted)"
    assert not _is_valid_import_target("/import/" + "a" * 513), "a 513-byte source_ref exceeds the bound (rejected)"
    # POST + OPTIONS only — never GET/PUT/PATCH/DELETE/HEAD, asserted against the SERVED registrations.
    assert _served_methods(_IMPORT_ROUTE_TEMPLATE_NAME) == frozenset({"POST", "OPTIONS"}), (
        f"the import route family must SERVE exactly POST, OPTIONS (served: {sorted(_served_methods(_IMPORT_ROUTE_TEMPLATE_NAME))})"
    )
    assert _IMPORT_TARGET_METHODS == _served_methods(_IMPORT_ROUTE_TEMPLATE_NAME), (
        "the _IMPORT_TARGET_METHODS constant must equal the SERVED method set — a constant that agrees only with itself notices nothing"
    )
    # The matcher is wired into the edge dispatch, and the static allowlist stays closed (no /import key).
    text = _EDGE.read_text(encoding="utf-8")
    assert "_is_valid_import_target(target)" in text, "the edge dispatch must gate the import route on the bounded matcher"
    assert _dict_string_keys(_tree(_EDGE), "_EXPOSED_ROUTES") == set(_EXPECTED_ROUTES), (
        "the static allowlist must not carry a parameterized import key"
    )


def test_edge_tenant_startup_route_is_bounded_single_segment_get_patch_only() -> None:
    # D-42 CLM: the served /tenant/startups/<startup_ref> matcher is a BOUNDED, traversal-safe,
    # SINGLE-SEGMENT route — never a wildcard/prefix router — exercised directly (a pure,
    # socket-free function; the W1b import-matcher guard idiom).
    for ok in ("/tenant/startups/clm-startup-1", "/tenant/startups/t1:startups:g1", "/tenant/startups/a.b_c-d"):
        assert _is_valid_tenant_startup_target(ok), f"{ok!r} must be an accepted bounded tenant Startup target"
    for bad in (
        "/tenant/startups",  # bare (no startup_ref)
        "/tenant/startups/",  # empty suffix
        "/tenant/startups/a/b",  # multi-segment (the ref is ONE segment)
        "/tenant/startups/..",  # dot-dot traversal
        "/tenant/startups/%2e%2e",  # percent-encoded dot-dot
        "/tenant/startups/a\\b",  # backslash
        "/tenant/startups/g1?tenant=t1",  # query form
        "/tenant/startups/g1#frag",  # fragment form
        "/tenant/investors/i1",  # a different tenant family (never served in CLM)
        "/tenant/deals/d1",  # a different tenant family (never served in CLM)
        "/tenant/startupsx/g1",  # prefix look-alike
        "/memberships",  # a different route
    ):
        assert not _is_valid_tenant_startup_target(bad), f"{bad!r} must be rejected by the bounded tenant Startup matcher"
    # The startup_ref byte bound is pinned at 512 (IC-010 CLM: 1..512 UTF-8 bytes).
    assert _MAX_STARTUP_REF_BYTES == 512, "the startup_ref byte bound must be pinned at 512"
    assert _is_valid_tenant_startup_target("/tenant/startups/" + "a" * 512), "a 512-byte startup_ref is at the bound (accepted)"
    assert not _is_valid_tenant_startup_target("/tenant/startups/" + "a" * 513), "a 513-byte startup_ref exceeds the bound (rejected)"
    # GET + PATCH + OPTIONS only — never POST/PUT/DELETE/HEAD (no create/delete capability), asserted
    # against the SERVED registrations. This family is exactly the surface Gate-B class M14 authorizes
    # persistent writes on, and V7 §21.1 states that M14 "does not authorize a new route, new HTTP
    # method" — so the guard that would notice a widening must observe the decorator, not a constant.
    assert _served_methods(_TENANT_STARTUP_ROUTE_TEMPLATE_NAME) == frozenset({"GET", "PATCH", "OPTIONS"}), (
        "the tenant Startup route family must SERVE exactly GET, PATCH, OPTIONS "
        f"(served: {sorted(_served_methods(_TENANT_STARTUP_ROUTE_TEMPLATE_NAME))})"
    )
    assert _TENANT_STARTUP_METHODS == _served_methods(_TENANT_STARTUP_ROUTE_TEMPLATE_NAME), (
        "the _TENANT_STARTUP_METHODS constant must equal the SERVED method set — a constant that agrees only with itself notices nothing"
    )
    # The PATCH body budget is pinned at exactly 16384 bytes (IC-010 CLM).
    assert _MAX_PATCH_BODY_BYTES == 16384, "the tenant Startup PATCH body budget must be pinned at 16384 bytes"
    # The matcher is wired into the edge dispatch, and the static allowlist stays closed.
    text = _EDGE.read_text(encoding="utf-8")
    assert "_is_valid_tenant_startup_target(target)" in text, "the edge dispatch must gate the tenant Startup routes on the bounded matcher"
    assert _dict_string_keys(_tree(_EDGE), "_EXPOSED_ROUTES") == set(_EXPECTED_ROUTES), (
        "the static allowlist must not carry a parameterized tenant Startup key"
    )


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
    assert '["Access-Control-Allow-Credentials"] = "false"' in text, "credentialed CORS is forbidden (Allow-Credentials must be false)"
    assert '"true"' not in text, "the edge must never enable credentialed CORS"
    assert '["Access-Control-Allow-Origin"] = "*"' not in text, "the edge must never emit a wildcard CORS origin"
    assert '"*"' not in text, "the edge must never emit a wildcard CORS value"
    # FastAPI ships a permissive CORS middleware; wiring it here would bypass the exact-origin
    # allowlist above (and can emit a wildcard). The edge must keep its own allowlist emitter.
    assert "CORSMiddleware" not in text, "the edge must not delegate CORS to the framework's permissive middleware"


def test_edge_serialize_portal_dto_is_only_success_serializer() -> None:
    tree = _tree(_EDGE)
    used = _names_used(tree)
    assert "serialize_portal_dto" in used, "success bodies must be produced by the core-owned serialize_portal_dto"
    hand_rolled = _FORBIDDEN_DTO_NAMES & used
    assert not hand_rolled, f"the edge must not construct/compose portal DTOs itself: {sorted(hand_rolled)}"
    # W1b: the edge may REFERENCE ImportResultDTO for the served-import success type check only — never
    # CONSTRUCT one — and must NEVER reference/serialize an ImportInitiationDTO on the served import route
    # (a port-absent ImportInitiationDTO envelope is fail-closed to 503, not serialized).
    assert "ImportResultDTO" in used, "the import terminal must type-check the success DTO (ImportResultDTO)"
    assert _name_call_count(tree, "ImportResultDTO") == 0, "the edge must never construct an ImportResultDTO"
    assert "ImportInitiationDTO" not in used, "the edge must never reference/serialize ImportInitiationDTO"
    # D-42 CLM: the same reference-not-construct rule binds the tenant Startup terminal, and the
    # edge must NEVER reference the update REQUEST shape (body parsing is core-owned — the raw
    # bounded bytes pass through untouched).
    assert "TenantStartupDetailDTO" in used, "the tenant Startup terminal must type-check the success DTO"
    assert _name_call_count(tree, "TenantStartupDetailDTO") == 0, "the edge must never construct a TenantStartupDetailDTO"
    assert "TenantStartupUpdateRequestDTO" not in used, "the edge must never reference/parse the update request DTO"
    assert "parse_tenant_startup_update_request" not in used, "PATCH body parsing is core-owned, never edge-owned"


def test_edge_no_raw_error_or_secret_leakage() -> None:
    text = _EDGE.read_text(encoding="utf-8")
    tree = _tree(_EDGE)
    used = _names_used(tree)
    assert "send_error" not in used, "the edge must never call stdlib send_error (HTML/detail bodies)"
    assert "traceback" not in used and "format_exc" not in used, "the edge must never render a traceback"
    assert _print_calls(tree) == 0, "the edge must not print (no token/payload logging)"
    # Every denial/rejection goes through the shared EMPTY-body helper — never a framework
    # detail body (FastAPI's default {"detail": ...}) and never a hand-written error payload.
    assert "empty_response" in used, "denials/rejections must carry an EMPTY body (empty_response)"
    assert "HTTPException" not in used, "the edge must not raise framework HTTPExceptions (they render a detail body)"
    assert "JSONResponse" not in used, "success bytes come from serialize_portal_dto, never the framework encoder"
    lowered = text.lower()
    for needle in ("postgresql://", "postgres://", "database_url", "secretref"):
        assert needle not in lowered, f"the edge must carry no connection-string / secret material ({needle})"


def test_edge_publishes_no_self_describing_surface() -> None:
    # These are closed, contract-governed routes (IC-010 §R). A generated OpenAPI schema or docs
    # page would publish a machine-readable catalogue of every route, method, and shape — exactly
    # what the closed allowlist forbids — so the shared app factory must disable all three.
    shared_app = _scan.BACKEND_ROOT / "shared" / "adapters" / "providers" / "fastapi_edge.py"
    assert _nonempty(shared_app), "the shared FastAPI edge-app factory must exist and be non-empty"
    factory = shared_app.read_text(encoding="utf-8")
    for pin in ("docs_url=None", "redoc_url=None", "openapi_url=None"):
        assert pin in factory, f"the shared edge app must disable its self-describing surface ({pin})"
    # Redirect-slashes would serve a SECOND spelling of every exposed path, silently widening
    # every closed route allowlist in the codebase.
    assert "redirect_slashes = False" in factory, "the shared edge app must disable slash-redirects (closed allowlists)"


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
    # The shared runtime is the ONLY thing that may run a request loop; it must expose the same
    # lifecycle the entrypoint (and every composition test) drives.
    runtime = _RUNTIME.read_text(encoding="utf-8")
    for lifecycle in ("def serve_forever", "def shutdown", "def server_close"):
        assert lifecycle in runtime, f"the shared ASGI runtime must expose {lifecycle}"


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
    # W1b: the bounded import matcher accepts a multi-segment ref and rejects wildcard/traversal/bare
    # forms — so a widened matcher (accepting "/import/../x" or a bare "/import") is detectable.
    assert _is_valid_import_target("/import/global-startup/rec-9"), "a bounded multi-segment ref must be accepted"
    assert not _is_valid_import_target("/import/../rec-9"), "a traversal ref must be rejected (non-vacuous)"
    assert not _is_valid_import_target("/import"), "a bare /import must be rejected (non-vacuous)"


if __name__ == "__main__":
    _scan.run(
        [
            test_edge_serves_through_the_shared_runtime_only,
            test_shared_runtime_disables_request_logging_and_server_disclosure,
            test_edge_calls_gateway_handle_exactly_once,
            test_edge_route_allowlist_is_closed,
            test_edge_import_route_is_bounded_multisegment_and_post_only,
            test_edge_tenant_startup_route_is_bounded_single_segment_get_patch_only,
            test_edge_correlation_accept_mint_echo,
            test_edge_cors_exact_origin_no_credentialed_wildcard,
            test_edge_serialize_portal_dto_is_only_success_serializer,
            test_edge_no_raw_error_or_secret_leakage,
            test_edge_publishes_no_self_describing_surface,
            test_edge_single_blessed_serve_entrypoint_and_close,
            test_edge_boundary_guard_nonvacuity,
        ]
    )
