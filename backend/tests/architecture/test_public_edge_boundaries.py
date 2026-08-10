"""Public MVP edges — static/AST boundary guard (default suite; pure stdlib).

**Provenance.** This file is the migrated successor of `test_gateway_edge_boundaries.py`, which
pinned the served API Gateway edge (`api_gateway/adapters/providers/http_gateway_edge.py`). That
module was deleted with the Gateway. Every property below was carried across and re-aimed at the
two edges that now terminate browser requests — deleting the component was never authority to
delete its transport contract:

| Gateway-edge property | Where it lives now |
|---|---|
| serves through the SHARED containment-zone ASGI runtime, hand-rolls no server/thread | both edges |
| no sibling-service / driver / vendor / crypto / second-framework import | both edges (per-edge allow-set) |
| exactly ONE core call site; the edge owns no auth/authorization/routing/composition |
  both edges: one `boundary.admit`, and only the owner composes its DTO |
| CLOSED route allowlist; `/tenant`, `/directory` never appear where they are not owned | both edges: one route family each |
| bounded, traversal-safe parameterized matcher (single segment, 512-byte cap) | the Startup
  edge's `is_valid_tenant_startup_target` |
| served method sets read from the DECORATORS, never from a self-agreeing constant | both edges |
| correlation accept / mint / echo | the shared transport gate (one implementation, both edges) |
| exact-origin CORS, never wildcard, never credentialed | the shared transport gate |
| success bytes ONLY from `serialize_portal_dto` | both edges |
| no raw error/secret leakage; no traceback, print, framework detail body | both edges |
| no self-describing surface (OpenAPI/docs/redirect-slashes) | the shared app factory |
| exactly ONE blessed blocking entrypoint with `server_close` teardown | both edges |

Two properties from the old file are **not** carried across because their subject no longer
exists, and both are recorded rather than dropped silently:

* the `POST /import/<source_ref>` bounded matcher — Import is outside the controlled local MVP
  journey (IMPORT-A / D-3) and no public edge serves it. `test_no_public_edge_serves_import_or_directory`
  below asserts that absence, so "we forgot it" and "we deliberately do not serve it" are
  distinguishable;
* `gateway.handle` called exactly once — there is no core to call once. The successor property is
  "exactly one `boundary.admit` site per edge", asserted here and in GF-3c.

Module-scoped and non-vacuous: the guard fails if either edge module disappears or empties, and
each census carries a companion proving it flags a bad sample.

Standalone-runnable:  python tests/architecture/test_public_edge_boundaries.py
"""

from __future__ import annotations

import ast
import pathlib
import sys
import tempfile
from typing import Optional, Set

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

if str(_scan.BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_scan.BACKEND_ROOT))

# The bounded matcher and its pins are pure, socket-free values — exercised directly (no bind, no
# network, no database), the idiom the Gateway-edge guard used for the same property.
from database_router.adapters.providers.http_public_startup_edge import (  # noqa: E402
    _MAX_PATCH_BODY_BYTES,
    _MAX_STARTUP_REF_BYTES,
    _TENANT_STARTUP_ROUTE_TEMPLATE,
    is_valid_tenant_startup_target,
)

_STARTUP_EDGE = _scan.BACKEND_ROOT / "database_router" / "adapters" / "providers" / "http_public_startup_edge.py"
_WORKSPACE_EDGE = _scan.BACKEND_ROOT / "control_plane" / "adapters" / "providers" / "http_public_workspace_edge.py"
_RUNTIME = _scan.BACKEND_ROOT / "shared" / "adapters" / "providers" / "asgi_runtime.py"
_APP_FACTORY = _scan.BACKEND_ROOT / "shared" / "adapters" / "providers" / "fastapi_edge.py"
_TRANSPORT = _scan.BACKEND_ROOT / "shared" / "adapters" / "providers" / "public_edge_transport.py"

# (edge module, its owning service, its single blessed blocking entrypoint, its route family).
# The census is the registry: a THIRD public edge is unguarded until it is added here, which is
# the same hard-coded-census limitation the Gateway-free result document records as a known risk.
_PUBLIC_EDGES = (
    (_STARTUP_EDGE, "database_router", "serve_public_startup_edge", "build_public_startup_edge_server"),
    (_WORKSPACE_EDGE, "control_plane", "serve_public_workspace_edge", "build_public_workspace_edge_server"),
)

# Each edge may import its OWN service plus the shared surface and FastAPI — and nothing else.
_COMMON_IMPORT_ALLOW = frozenset({"__future__", "json", "re", "typing", "fastapi", "shared"})

_FORBIDDEN_TOPS = frozenset(
    {
        "auth_router",
        "import_service",
        "lineage_service",
        "jwt",
        "cryptography",
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
        # The edge must not reach past FastAPI to the ASGI server or its plumbing.
        "uvicorn",
        "starlette",
        "http",
        "socketserver",
        "wsgiref",
    }
)

# A public edge composes its OWN portal DTO — that is the whole point of owner-resident
# composition (IC-010 §V, re-homed). It must not construct the OTHER owner's shapes.
_FOREIGN_DTO_NAMES = {
    _STARTUP_EDGE: {"WorkspaceMembershipDTO", "MembershipEntryDTO"},
    _WORKSPACE_EDGE: {"TenantStartupDetailDTO", "TenantStartupUpdateRequestDTO"},
}


def _parse(src: str) -> ast.Module:
    return ast.parse(src)


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _nonempty(path: pathlib.Path) -> bool:
    return path.is_file() and bool(path.read_text(encoding="utf-8").strip())


def _import_tops(path: pathlib.Path) -> Set[str]:
    return {mod.split(".")[0] for mod in _scan.imported_modules(path)}


def _tops_of_source(src: str) -> Set[str]:
    tree = _parse(src)
    mods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.append(node.module)
    return {m.split(".")[0] for m in mods}


def _names_used(node: ast.AST) -> Set[str]:
    out = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    out |= {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
    return out


def _def(tree: ast.AST, name: str) -> Optional[ast.AST]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _name_call_count(tree: ast.AST, name: str) -> int:
    return sum(1 for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name)


def _attr_call_count(tree: ast.AST, attr: str) -> int:
    return sum(1 for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == attr)


def _print_calls(tree: ast.AST) -> int:
    return _name_call_count(tree, "print")


def _serve_forever_refs(node: ast.AST) -> int:
    return sum(1 for n in ast.walk(node) if isinstance(n, ast.Attribute) and n.attr == "serve_forever")


def _served_methods(path: pathlib.Path, route_key: str) -> frozenset:
    """The methods an edge ACTUALLY registers for ``route_key`` (literal path or constant NAME).

    Read from the DECORATORS. Comparing a module constant against itself answers a different
    question and answers it tautologically — a widened ``methods=`` list would not move it.
    """
    served = frozenset(method for p, method in _scan.route_registrations(_tree(path)) if p == route_key)
    assert _scan.COMPUTED_METHODS.upper() not in served, f"{route_key} in {_scan.relposix(path)} must declare a LITERAL methods= list"
    assert served, f"{route_key} registers no route at all in {_scan.relposix(path)} — the census cannot be vacuous"
    return served


def _registered_paths(path: pathlib.Path) -> Set[str]:
    """Every route path an edge registers, resolving a constant NAME to its string value."""
    tree = _tree(path)
    constants = {
        target.id: node.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    return {constants.get(p, p) for p, _method in _scan.route_registrations(tree)}


# --- shared runtime / app factory ------------------------------------------------------------
def test_public_edges_serve_through_the_shared_runtime_only() -> None:
    for edge, _service, _entry, _factory in _PUBLIC_EDGES:
        assert _nonempty(edge), f"{_scan.relposix(edge)} must exist and be non-empty"
        text = edge.read_text(encoding="utf-8")
        used = _names_used(_tree(edge))
        assert "build_asgi_server" in used, f"{_scan.relposix(edge)} must build its server through the shared ASGI runtime"
        assert "AsgiEdgeServer" in used, f"{_scan.relposix(edge)} must serve on the shared AsgiEdgeServer lifecycle"
        for hand_rolled in ("HTTPServer", "ThreadingHTTPServer", "ThreadingMixIn", "Thread", "run_in_executor"):
            assert hand_rolled not in text, f"{_scan.relposix(edge)} must not hand-roll a server/thread ({hand_rolled})"


def test_public_edge_import_surface_is_own_service_plus_shared() -> None:
    for edge, service, _entry, _factory in _PUBLIC_EDGES:
        tops = _import_tops(edge)
        allowed = _COMMON_IMPORT_ALLOW | {service}
        extra = tops - allowed
        assert not extra, f"{_scan.relposix(edge)} imports outside its own service + the shared surface: {sorted(extra)}"
        banned = tops & _FORBIDDEN_TOPS
        assert not banned, (
            f"{_scan.relposix(edge)} must import no sibling service / vendor / concurrency / second framework: {sorted(banned)}"
        )
    # The DB driver stays in the Database Router's own provider zone (the containment standard);
    # neither public edge may name one directly.
    for edge, _service, _entry, _factory in _PUBLIC_EDGES:
        assert not (_import_tops(edge) & {"psycopg", "psycopg2", "asyncpg", "sqlalchemy", "databases", "aiopg"}), (
            f"{_scan.relposix(edge)} must not import a database driver directly"
        )


def test_shared_runtime_disables_request_logging_and_server_disclosure() -> None:
    # The migrated home of the stdlib edge's silenced `log_message`: uvicorn must never install a
    # logging config or write an access log (no request line, header, token, or payload to stderr),
    # and must disclose no server identity/version header.
    assert _nonempty(_RUNTIME), "the shared ASGI runtime module must exist and be non-empty"
    runtime = _RUNTIME.read_text(encoding="utf-8")
    for pin in ("log_config=None", "access_log=False", "server_header=False"):
        assert pin in runtime, f"the shared ASGI runtime must pin {pin} (no request logging / no server disclosure)"
    assert _print_calls(_tree(_RUNTIME)) == 0, "the shared ASGI runtime must not print"


def test_public_edges_publish_no_self_describing_surface() -> None:
    # These are closed, contract-governed routes (IC-010 §R, re-homed to the owning edges). A
    # generated OpenAPI schema or docs page would publish a machine-readable catalogue of every
    # route, method and shape — exactly what a closed allowlist forbids.
    assert _nonempty(_APP_FACTORY), "the shared FastAPI edge-app factory must exist and be non-empty"
    factory = _APP_FACTORY.read_text(encoding="utf-8")
    for pin in ("docs_url=None", "redoc_url=None", "openapi_url=None"):
        assert pin in factory, f"the shared edge app must disable its self-describing surface ({pin})"
    # Redirect-slashes would serve a SECOND spelling of every exposed path, silently widening
    # every closed route allowlist in the codebase.
    assert "redirect_slashes = False" in factory, "the shared edge app must disable slash-redirects (closed allowlists)"
    for edge, _service, _entry, _factory_name in _PUBLIC_EDGES:
        assert "new_edge_app" in _names_used(_tree(edge)), f"{_scan.relposix(edge)} must build its app through the shared factory"


# --- one core call site, one route family -----------------------------------------------------
def _has_loop(node: ast.AST) -> bool:
    return any(isinstance(n, (ast.For, ast.While, ast.AsyncFor)) for n in ast.walk(node))


def test_each_public_edge_has_exactly_one_admit_site_and_owns_no_core_logic() -> None:
    for edge, _service, _entry, _factory in _PUBLIC_EDGES:
        tree = _tree(edge)
        admits = _attr_call_count(tree, "admit")
        assert admits == 1, f"{_scan.relposix(edge)} must call the shared boundary exactly once (boundary.admit); found {admits}"
        # AND it must not sit inside a retry loop. The Gateway-edge guard asserted this of
        # `gateway.handle`, and an earlier draft of THIS file dropped it: counting one call site is
        # not the same property. An automatic retry around admission re-drives authentication and
        # the executor on a transient failure, which is how one accepted request becomes two tenant
        # database sessions — the exact thing A11 exists to forbid.
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not any(isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "admit" for c in ast.walk(node)):
                continue
            assert not _has_loop(node), (
                f"{_scan.relposix(edge)}:{node.name} wraps the boundary admission in a loop — an automatic retry "
                "re-drives authentication and the executor, turning one accepted request into two tenant sessions"
            )
        used = _names_used(tree)
        # The successor to "the Gateway edge performs no core logic": the edge performs no
        # authentication, no membership decision, and no carrier interpretation of its own.
        for banned_name in ("authenticate", "recognized_carriers", "opaque_carrier_ref", "decide", "dispatch"):
            assert banned_name not in used, f"{_scan.relposix(edge)} must not perform boundary logic itself ({banned_name})"


def test_each_public_edge_serves_exactly_its_own_route_family() -> None:
    startup_paths = _registered_paths(_STARTUP_EDGE)
    workspace_paths = _registered_paths(_WORKSPACE_EDGE)
    assert startup_paths == {_TENANT_STARTUP_ROUTE_TEMPLATE, "/health", "/readiness"}, (
        f"the Startup edge must serve exactly its own family plus health/readiness; got {sorted(startup_paths)}"
    )
    assert workspace_paths == {"/memberships", "/health", "/readiness"}, (
        f"the Workspace edge must serve exactly its own family plus health/readiness; got {sorted(workspace_paths)}"
    )
    # Neither edge may serve the other's family — the property that stops either becoming a gateway.
    assert "/memberships" not in startup_paths, "the Startup edge must never serve the Workspace family"
    assert not any(p.startswith("/tenant") for p in workspace_paths), "the Workspace edge must never serve the tenant family"


def test_no_public_edge_serves_import_or_directory() -> None:
    """Recorded absence, not an oversight.

    The Gateway edge served a bounded ``POST /import/<source_ref>`` and its core classified
    ``GET /directory/<kind>``. Import is outside the controlled local MVP journey (IMPORT-A /
    D-3) and no served Gateway route ever exposed ``/directory``. Neither is served here, and
    this test is what distinguishes "deliberately not served" from "quietly forgotten".
    """
    for edge, _service, _entry, _factory in _PUBLIC_EDGES:
        paths = _registered_paths(edge)
        assert not any(p.startswith("/import") for p in paths), f"{_scan.relposix(edge)} must not serve an import route"
        assert not any(p.startswith("/directory") for p in paths), f"{_scan.relposix(edge)} must not serve a directory route"


# --- the bounded parameterized matcher --------------------------------------------------------
def test_tenant_startup_route_is_bounded_single_segment_get_patch_only() -> None:
    # The served /tenant/startups/<startup_ref> matcher is a BOUNDED, traversal-safe,
    # SINGLE-SEGMENT route — never a wildcard/prefix router — exercised directly (a pure,
    # socket-free function).
    for ok in ("/tenant/startups/clm-startup-1", "/tenant/startups/t1:startups:g1", "/tenant/startups/a.b_c-d"):
        assert is_valid_tenant_startup_target(ok), f"{ok!r} must be an accepted bounded tenant Startup target"
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
        assert not is_valid_tenant_startup_target(bad), f"{bad!r} must be rejected by the bounded tenant Startup matcher"
    # The startup_ref byte bound is pinned at 512 (IC-010 CLM: 1..512 UTF-8 bytes).
    assert _MAX_STARTUP_REF_BYTES == 512, "the startup_ref byte bound must be pinned at 512"
    assert is_valid_tenant_startup_target("/tenant/startups/" + "a" * 512), "a 512-byte startup_ref is at the bound (accepted)"
    assert not is_valid_tenant_startup_target("/tenant/startups/" + "a" * 513), "a 513-byte startup_ref exceeds the bound (rejected)"
    # The PATCH body budget is pinned at exactly 16384 bytes (IC-010 CLM).
    assert _MAX_PATCH_BODY_BYTES == 16384, "the tenant Startup PATCH body budget must be pinned at 16384 bytes"
    # GET + PATCH + OPTIONS only — never POST/PUT/DELETE/HEAD (no create/delete capability),
    # asserted against the SERVED registrations. This family is exactly the surface Gate-B class
    # M14 authorizes persistent writes on, and V7 §21.1 states that M14 "does not authorize a new
    # route, new HTTP method" — so the guard that would notice a widening must observe the
    # decorator, not a constant.
    assert _served_methods(_STARTUP_EDGE, "_TENANT_STARTUP_ROUTE_TEMPLATE") == frozenset({"GET", "PATCH", "OPTIONS"}), (
        "the tenant Startup route family must SERVE exactly GET, PATCH, OPTIONS "
        f"(served: {sorted(_served_methods(_STARTUP_EDGE, '_TENANT_STARTUP_ROUTE_TEMPLATE'))})"
    )
    assert _served_methods(_WORKSPACE_EDGE, "_MEMBERSHIPS_PATH") == frozenset({"GET", "OPTIONS"}), (
        "the memberships family must SERVE exactly GET, OPTIONS — it is a read capability"
    )
    # The matcher is wired into the edge's own decision, against the RAW target.
    text = _STARTUP_EDGE.read_text(encoding="utf-8")
    assert "is_valid_tenant_startup_target(" in text, "the edge must gate the tenant Startup routes on the bounded matcher"


# --- correlation / CORS / serialization / leakage ----------------------------------------------
def test_correlation_accept_mint_echo_lives_in_the_shared_transport_gate() -> None:
    # One implementation for both edges: correlation is minted once, at the transport gate, not
    # re-derived per edge (the Gateway minted it in its core AND its edge).
    assert _nonempty(_TRANSPORT), "the shared public transport gate must exist and be non-empty"
    text = _TRANSPORT.read_text(encoding="utf-8")
    used = _names_used(_tree(_TRANSPORT))
    assert '"x-correlation-id"' in text, "the transport gate must handle the x-correlation-id header"
    assert "uuid4" in used, "the transport gate must mint a correlation id via uuid4 when absent/malformed"
    for edge, _service, _entry, _factory in _PUBLIC_EDGES:
        assert "uuid4" not in _names_used(_tree(edge)), f"{_scan.relposix(edge)} must not mint its own correlation id"


def test_cors_is_exact_origin_never_wildcard_never_credentialed() -> None:
    text = _TRANSPORT.read_text(encoding="utf-8")
    assert "allowed_origins" in _names_used(_tree(_TRANSPORT)), "the transport gate must gate CORS on the exact-origin allowlist"
    assert '["Access-Control-Allow-Credentials"] = "false"' in text, "credentialed CORS is forbidden (Allow-Credentials must be false)"
    assert '"true"' not in text, "the transport gate must never enable credentialed CORS"
    assert '["Access-Control-Allow-Origin"] = "*"' not in text, "the transport gate must never emit a wildcard CORS origin"
    assert '"*"' not in text, "the transport gate must never emit a wildcard CORS value"
    # FastAPI ships a permissive CORS middleware; wiring it anywhere would bypass the exact-origin
    # allowlist above (and can emit a wildcard).
    for path in (_TRANSPORT, _STARTUP_EDGE, _WORKSPACE_EDGE, _APP_FACTORY):
        assert "CORSMiddleware" not in path.read_text(encoding="utf-8"), (
            f"{_scan.relposix(path)} must not delegate CORS to the framework's permissive middleware"
        )


def test_serialize_portal_dto_is_the_only_success_serializer() -> None:
    for edge, _service, _entry, _factory in _PUBLIC_EDGES:
        tree = _tree(edge)
        used = _names_used(tree)
        assert "serialize_portal_dto" in used, f"{_scan.relposix(edge)} success bodies must come from serialize_portal_dto"
        foreign = _FOREIGN_DTO_NAMES[edge] & used
        assert not foreign, f"{_scan.relposix(edge)} must not touch another owner's portal shapes: {sorted(foreign)}"
    # The Startup edge composes exactly one detail DTO per served success; the Workspace edge
    # composes its envelope. Owner composition is the property IC-010 §V now names.
    assert _name_call_count(_tree(_STARTUP_EDGE), "TenantStartupDetailDTO") >= 1, "the Startup edge composes its own DTO"
    assert _name_call_count(_tree(_WORKSPACE_EDGE), "WorkspaceMembershipDTO") >= 1, "the Workspace edge composes its own DTO"


def test_public_edges_have_no_raw_error_or_secret_leakage() -> None:
    for edge, _service, _entry, _factory in _PUBLIC_EDGES:
        text = edge.read_text(encoding="utf-8")
        tree = _tree(edge)
        used = _names_used(tree)
        assert "send_error" not in used, f"{_scan.relposix(edge)} must never call stdlib send_error (HTML/detail bodies)"
        assert "traceback" not in used and "format_exc" not in used, f"{_scan.relposix(edge)} must never render a traceback"
        assert _print_calls(tree) == 0, f"{_scan.relposix(edge)} must not print (no token/payload logging)"
        assert "logging" not in used, f"{_scan.relposix(edge)} must not log"
        # Every denial/rejection goes through the shared EMPTY-body helper — never a framework
        # detail body (FastAPI's default {"detail": ...}) and never a hand-written error payload.
        assert "empty_response" in used, f"{_scan.relposix(edge)} denials must carry an EMPTY body (empty_response)"
        assert "HTTPException" not in used, f"{_scan.relposix(edge)} must not raise framework HTTPExceptions (they render a detail body)"
        assert "JSONResponse" not in used, f"{_scan.relposix(edge)} success bytes come from serialize_portal_dto, not the framework"
        lowered = text.lower()
        for needle in ("postgresql://", "postgres://", "database_url", "secretref"):
            assert needle not in lowered, f"{_scan.relposix(edge)} must carry no connection-string / secret material ({needle})"


def test_each_public_edge_has_one_blessed_serve_entrypoint_and_closes_it() -> None:
    for edge, _service, entry_name, factory_name in _PUBLIC_EDGES:
        tree = _tree(edge)
        text = edge.read_text(encoding="utf-8")
        entry = _def(tree, entry_name)
        assert entry is not None, f"{_scan.relposix(edge)} must define the single blessed blocking entrypoint {entry_name}"
        inside = _serve_forever_refs(entry)
        total = _serve_forever_refs(tree)
        assert inside == 1, f"{entry_name} must reference serve_forever exactly once, found {inside}"
        assert total == inside, f"serve_forever must appear ONLY inside {entry_name} ({total} total vs {inside} inside)"
        assert "server_close" in _names_used(tree), f"{_scan.relposix(edge)} must close the server (server_close in finally)"
        assert f"def {factory_name}" in text, f"{_scan.relposix(edge)} must expose the {factory_name} factory"
    # The shared runtime is the ONLY thing that may run a request loop; it must expose the same
    # lifecycle the entrypoints (and every composition test) drive.
    runtime = _RUNTIME.read_text(encoding="utf-8")
    for lifecycle in ("def serve_forever", "def shutdown", "def server_close"):
        assert lifecycle in runtime, f"the shared ASGI runtime must expose {lifecycle}"


# --- non-vacuity companions --------------------------------------------------------------------
def test_public_edge_boundary_guard_nonvacuity() -> None:
    # Import bans flag a planted sibling/vendor/concurrency import.
    assert _tops_of_source("import threading\nfrom auth_router.x import y\n") & _FORBIDDEN_TOPS == {"threading", "auth_router"}, (
        "the import ban-set must flag a planted forbidden import"
    )
    # The allow-set is per-edge: the Workspace edge's own service is forbidden to the Startup edge.
    assert "control_plane" not in (_COMMON_IMPORT_ALLOW | {"database_router"}), "each edge's allow-set names only its OWN service"
    # The admit census counts real calls (a doubled call site is detectable).
    assert _attr_call_count(_parse("b.admit(a)\nb.admit(c)\n"), "admit") == 2, "the admit census must count call sites"
    # The route-path extractor resolves a constant NAME and would flag a widened surface.
    widened = "_P = '/memberships'\n\n@app.get(_P)\ndef a():\n    ...\n\n@app.get('/directory/{kind}')\ndef b():\n    ...\n"
    # Written into a TEMPORARY directory, never into the tracked tree. An earlier draft wrote the
    # probe into tests/architecture/ and removed it in a `finally` — which still dirties the working
    # tree for the duration of a normal `pytest` run and leaves a stray file behind if the process
    # is killed mid-test.
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = pathlib.Path(tmpdir) / "_nv_probe_public_edge.py"
        tmp.write_text(widened, encoding="utf-8")
        paths = _registered_paths(tmp)
    assert paths == {"/memberships", "/directory/{kind}"}, f"the path extractor must resolve constants AND literals; got {paths}"
    assert any(p.startswith("/directory") for p in paths), "a widened directory surface must be detectable"
    # The serve-loop census flags a second/misplaced serve loop.
    doubled = _parse("def serve_public_startup_edge():\n    s.serve_forever()\n\ndef rogue():\n    s.serve_forever()\n")
    entry = _def(doubled, "serve_public_startup_edge")
    assert entry is not None and _serve_forever_refs(entry) == 1 and _serve_forever_refs(doubled) == 2, (
        "a second serve loop must be detectable"
    )
    # A foreign DTO construction is flagged on the edge that must not own it.
    assert _FOREIGN_DTO_NAMES[_STARTUP_EDGE] & _names_used(_parse("x = WorkspaceMembershipDTO(memberships=())\n")) == {
        "WorkspaceMembershipDTO"
    }, "a foreign portal DTO must be flagged"
    # A print (token-logging) is detectable.
    assert _print_calls(_parse("print(authorization)\n")) == 1, "a print (token logging) must be detectable"
    # A retry loop wrapping the admission is detectable (and a loop-free body passes).
    looped = _parse("async def h(r):\n    while True:\n        boundary.admit(r, c)\n")
    assert _has_loop(_def(looped, "h")), "a retry loop around admission must be detectable"
    assert not _has_loop(_def(_parse("async def h(r):\n    boundary.admit(r, c)\n"), "h")), "a loop-free handler must pass"
    # The bounded matcher rejects wildcard/traversal/bare forms — a widened matcher is detectable.
    assert is_valid_tenant_startup_target("/tenant/startups/g1"), "a bounded single-segment ref must be accepted"
    assert not is_valid_tenant_startup_target("/tenant/startups/../g1"), "a traversal ref must be rejected (non-vacuous)"
    assert not is_valid_tenant_startup_target("/tenant/startups"), "a bare family path must be rejected (non-vacuous)"


if __name__ == "__main__":
    _scan.run(
        [
            test_public_edges_serve_through_the_shared_runtime_only,
            test_public_edge_import_surface_is_own_service_plus_shared,
            test_shared_runtime_disables_request_logging_and_server_disclosure,
            test_public_edges_publish_no_self_describing_surface,
            test_each_public_edge_has_exactly_one_admit_site_and_owns_no_core_logic,
            test_each_public_edge_serves_exactly_its_own_route_family,
            test_no_public_edge_serves_import_or_directory,
            test_tenant_startup_route_is_bounded_single_segment_get_patch_only,
            test_correlation_accept_mint_echo_lives_in_the_shared_transport_gate,
            test_cors_is_exact_origin_never_wildcard_never_credentialed,
            test_serialize_portal_dto_is_the_only_success_serializer,
            test_public_edges_have_no_raw_error_or_secret_leakage,
            test_each_public_edge_has_one_blessed_serve_entrypoint_and_closes_it,
            test_public_edge_boundary_guard_nonvacuity,
        ]
    )
