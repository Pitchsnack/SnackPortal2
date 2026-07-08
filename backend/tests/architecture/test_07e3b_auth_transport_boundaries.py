"""07E-3b/07E-3c static guards — gateway<->auth-router authentication transport pair (default suite).

Pins the 07E-3a auth wire contract (docs/auth/AUTH-TRANSPORT-SPEC-01) against the two new
runtime transport modules, as pure-stdlib AST/text censuses (no PostgreSQL, no driver, no
network, no token validation). Module-scoped and non-vacuous: each guard fails if a runtime
module disappears or empties, and each carries a companion proving it flags a bad sample.

* **Client guard** (``http_authenticator.py``): serializes exactly ``{v, authorization,
  recognized_carriers, correlation_id}`` and validates exactly ``{correlation_id,
  principal_ref, active_tenant_id, role}``; no never-cross identifier as a serialized key;
  stdlib urllib/json + api_gateway only; imports NO ``auth_router``/``database_router``/DB
  driver/Supabase/Lovable/``jwt``/``PyJWT``/``cryptography``; no DSN, token-mint, permission
  matrix, ``DispatchDecision``, ``RouteOutcome``, ``RequestContext``, or ``.route(...)``; no
  token/authorization logging (no ``logging`` import, no ``print``); bounded timeout; single
  attempt (no retry loop); adapter-only top-level defs.
* **Server guard** (``http_authenticate_api.py``): internal-only ``127.0.0.1`` bind + literal
  ``/internal/auth/authenticate`` path; POST-only served handler; single-threaded plain
  ``HTTPServer`` (no ``ThreadingHTTPServer``/threading/asyncio/concurrent/multiprocessing);
  fixed-503/405/404 empty-body edges with no stdlib ``send_error`` HTML; ``log_message``
  silenced; the ``{v,...}`` / 4-field-success / ``{status, public_code}`` shapes present; NO
  ``api_gateway`` import; no ``RequestContext`` emission; no public login/password/OAuth route;
  no token/authorization logging; adapter-only top-level defs + import surface. The server
  guard PERMITS ``jwt`` (auth_router owns validation) — the client guard forbids it.
* **Composition guard** (07E-3c; ``api_gateway/main.py``): the config-selectable
  ``build_authenticator_from_env`` seam exists with the ``SP2_GW_AUTH_ROUTER_BASE_URL``
  selector; the composition root imports only ``os``/``typing``/``urllib`` stdlib tops (NO
  ``auth_router``/``database_router``/``jwt``/crypto/DB driver/threading); ``build_gateway``
  stays required-injection (authenticator + router have NO defaults — no runnable production
  composition); no DSN, no network I/O (``urlopen``) at composition, and no
  ``serve_forever``/lifecycle launcher in the composition root OR the auth server module.

Pure stdlib; standalone-runnable:  python tests/architecture/test_07e3b_auth_transport_boundaries.py
"""

from __future__ import annotations

import ast
import pathlib
import sys
from typing import List, Optional, Set

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_CLIENT_MOD = _scan.BACKEND_ROOT / "api_gateway" / "adapters" / "providers" / "http_authenticator.py"
_SERVER_MOD = _scan.BACKEND_ROOT / "auth_router" / "adapters" / "providers" / "http_authenticate_api.py"

_REQUEST_KEYS = frozenset({"v", "authorization", "recognized_carriers", "correlation_id"})
_SUCCESS_KEYS = frozenset({"correlation_id", "principal_ref", "active_tenant_id", "role"})
_FAILURE_KEYS = frozenset({"status", "public_code"})

# Never-cross identifiers that must NEVER appear as a serialized wire key (lowercased match).
# The legitimate envelope keys (v/authorization/recognized_carriers/correlation_id/principal_ref/
# active_tenant_id/role/status/public_code) are deliberately EXCLUDED — "authorization" is a
# legitimate REQUEST key, but has no place in any RESPONSE (that is pinned by the exact-shape census).
_FORBIDDEN_KEYS = frozenset(
    {
        "token",
        "refresh_token",
        "session_cookie",
        "jwks",
        "secret",
        "secretref",
        "credential",
        "password",
        "email",
        "name",
        "display_name",
        "profile",
        "pii",
        "roles",
        "memberships",
        "permission_matrix",
        "permissions",
        "is_control_context",
        "database_url",
        "dsn",
        "database_name",
        "tenant_database_id",
        "tenant_db",
        "connection",
        "topology",
        "dispatchdecision",
        "routeoutcome",
        "route_ref",
        "body",
        "payload",
    }
)

_CLIENT_IMPORT_TOPS_ALLOW = frozenset({"__future__", "json", "urllib", "typing", "api_gateway"})
# The server allow-set PERMITS jwt (auth_router owns validation) — the asymmetry vs the client.
_SERVER_IMPORT_TOPS_ALLOW = frozenset({"__future__", "json", "http", "typing", "auth_router", "jwt"})

# NOTE (07E-3c polish): no "PyJWT" entry — the PyPI distribution PyJWT imports as module
# ``jwt`` (already banned); a "PyJWT" top is unreachable via _import_tops and would be a
# dead entry advertising protection it cannot deliver.
_CLIENT_FORBIDDEN_TOPS = frozenset(
    {
        "auth_router",
        "database_router",
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
    }
)

# 07E-3c composition guard surface: the gateway composition root and its import allow-set.
_GATEWAY_MAIN = _scan.BACKEND_ROOT / "api_gateway" / "main.py"
_GW_MAIN_IMPORT_TOPS_ALLOW = frozenset({"__future__", "os", "typing", "urllib"})
_GW_SELECTOR_ENV = "SP2_GW_AUTH_ROUTER_BASE_URL"
_GW_BUILD_GATEWAY_KWONLY = ["authenticator", "router", "classify", "audit", "metrics"]

_CLIENT_TOPLEVEL_ALLOW = frozenset({"_is_optional_str", "HttpAuthenticator"})
_SERVER_TOPLEVEL_ALLOW = frozenset(
    {
        "_EnvelopeError",
        "_Reject",
        "_bearer_token",
        "_reduce_carriers",
        "_map_denied",
        "_authenticate",
        "_make_handler",
        "build_authenticate_server",
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


def _tops_of_source(source: str) -> Set[str]:
    """Top-level imported module names of an in-memory source sample — the same absolute-import
    semantics as ``_scan.imported_modules`` (relative imports are intra-package and skipped), so
    the non-vacuity companions can prove the ban-set intersection mechanism flags a bad module."""
    mods: List[str] = []
    for node in ast.walk(_parse(source)):
        if isinstance(node, ast.Import):
            mods.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.append(node.module)
    return {m.split(".")[0] for m in mods}


def _method(tree: ast.AST, class_name: str, method_name: str) -> Optional[ast.FunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef) and sub.name == method_name:
                    return sub
    return None


def _has_loop(node: Optional[ast.AST]) -> bool:
    if node is None:
        return False
    return any(isinstance(n, (ast.For, ast.While, ast.AsyncFor)) for n in ast.walk(node))


def _route_calls(tree: ast.AST) -> List[ast.Call]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "route"]


def _print_calls(tree: ast.AST) -> List[ast.Call]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "print"]


def _urlopen_calls(tree: ast.AST) -> List[ast.Call]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "urlopen"]


def _forbidden_key_hits(groups: List[frozenset]) -> List[str]:
    hits: List[str] = []
    for group in groups:
        for key in group:
            if key.lower() in _FORBIDDEN_KEYS:
                hits.append(key)
    return hits


def _nonempty(path: pathlib.Path) -> bool:
    return path.is_file() and bool(path.read_text(encoding="utf-8").strip())


# --- client guard ---------------------------------------------------------------------------------
def test_client_boundary_guard() -> None:
    assert _nonempty(_CLIENT_MOD), "the gateway auth client module must exist and be non-empty"
    text = _CLIENT_MOD.read_text(encoding="utf-8")
    tree = _tree(_CLIENT_MOD)
    groups = _string_key_groups(tree)
    # Exact wire shapes are present where they belong.
    assert _REQUEST_KEYS in groups, "client must serialize exactly {v, authorization, recognized_carriers, correlation_id}"
    assert _SUCCESS_KEYS in groups, "client must validate the exact 4-field success shape"
    hits = _forbidden_key_hits(groups)
    assert not hits, f"never-cross identifier serialized as a wire key: {hits}"
    # stdlib urllib/json + api_gateway only; no auth_router/database_router/jwt/crypto/driver/supabase/threading.
    tops = _import_tops(_CLIENT_MOD)
    extra = tops - _CLIENT_IMPORT_TOPS_ALLOW
    assert not extra, f"client imports outside the stdlib/gateway surface: {sorted(extra)}"
    banned = tops & _CLIENT_FORBIDDEN_TOPS
    assert not banned, f"client must import none of auth_router/database_router/jwt/crypto/driver/supabase/threading: {sorted(banned)}"
    # No DSN / token-mint / permission-matrix material (raw-text scan; not present even in prose).
    lowered = text.lower()
    for needle in ("dsn", "database_url", "postgresql://", "postgres://", "permission"):
        assert needle not in lowered, f"client must not reference {needle}"
    # Routing/context identifiers are banned as ACTUAL AST names used (a docstring may legitimately
    # mention "DispatchDecision"/"RouteOutcome"/"RequestContext" in prose to say it does NOT use them).
    client_names = _names_used(tree)
    for banned_name in ("DispatchDecision", "RouteOutcome", "RequestContext"):
        assert banned_name not in client_names, f"client must not use {banned_name}"
    assert not _route_calls(tree), "client must not call .route(...) (no dispatch)"
    # No token/authorization logging: no logging import, no print().
    assert "logging" not in tops, "client must not import logging"
    assert not _print_calls(tree), "client must not print (no token/authorization logging)"
    # Bounded timeout: the declared default AND the timeout keyword APPLIED on the urlopen call
    # (an AST check — a declared-but-unused timeout would pass the substring check vacuously).
    assert "timeout: float = 2.0" in text, "client must pin a bounded default timeout"
    opens = _urlopen_calls(tree)
    assert opens, "client must reach the wire via urllib urlopen (non-vacuous)"
    for call in opens:
        assert any(kw.arg == "timeout" for kw in call.keywords), "every urlopen call must apply the bounded timeout keyword"
    # Single attempt (no retry loop).
    assert not _has_loop(_method(tree, "HttpAuthenticator", "authenticate")), "client authenticate() must contain no retry loop"
    # Adapter-only top-level defs.
    extra_defs = _top_level_defs(tree) - _CLIENT_TOPLEVEL_ALLOW
    assert not extra_defs, f"client carries non-adapter top-level defs: {sorted(extra_defs)}"


def test_client_guard_nonvacuity() -> None:
    bad = _string_key_groups(_parse('x = {"correlation_id": 1, "token": 2}\n'))
    assert _forbidden_key_hits(bad) == ["token"], "client guard must flag a forbidden serialized key"
    looped = _parse("class C:\n    def authenticate(self):\n        while True:\n            pass\n")
    assert _has_loop(_method(looped, "C", "authenticate")), "client guard must detect a retry loop"
    assert _print_calls(_parse("print(authorization)\n")), "client guard must detect a print (token-logging)"
    assert _route_calls(_parse("r.route(ctx)\n")), "client guard must detect a .route(...) call"
    assert "DispatchDecision" in _names_used(_parse("x = DispatchDecision()\n")), "client guard must detect a banned AST name"
    unbounded = _urlopen_calls(_parse("urllib.request.urlopen(req)\n"))
    assert unbounded and not any(kw.arg == "timeout" for kw in unbounded[0].keywords), "client guard must detect an unbounded urlopen"
    assert _REQUEST_KEYS not in _string_key_groups(_parse("x = {'v': 1}\n")), "client guard must distinguish the exact request shape"
    # 07E-3c polish: the concurrency-import ban-set intersection flags a bad sample (the same
    # `tops & _CLIENT_FORBIDDEN_TOPS` mechanism the client guard applies to the real module).
    assert _tops_of_source("import threading\nimport asyncio\n") & _CLIENT_FORBIDDEN_TOPS == {"threading", "asyncio"}, (
        "client guard must flag a planted concurrency import"
    )


# --- server guard ---------------------------------------------------------------------------------
def test_server_boundary_guard() -> None:
    assert _nonempty(_SERVER_MOD), "the auth-router server module must exist and be non-empty"
    text = _SERVER_MOD.read_text(encoding="utf-8")
    tree = _tree(_SERVER_MOD)
    used = _names_used(tree)
    # Internal-only surface: literal path + loopback default bind (IC-010 §R/§M; Section B).
    assert '"/internal/auth/authenticate"' in text, "server must pin the literal internal auth path"
    assert "127.0.0.1" in text, "server must default-bind the internal loopback host"
    # Single-threaded plain HTTPServer; no threaded server / concurrency machinery (07E-3c scope).
    assert "HTTPServer" in used, "server must use a plain HTTPServer"
    for marker in ("ThreadingHTTPServer", "ThreadingMixIn"):
        assert marker not in text, f"server must stay single-threaded (found {marker})"
    banned = {"threading", "asyncio", "contextvars", "concurrent.futures", "multiprocessing"}
    banned_tops = {b.split(".")[0] for b in banned}
    conc_hits = {m for m in _scan.imported_modules(_SERVER_MOD) if m in banned or m.split(".")[0] in banned_tops}
    assert not conc_hits, f"server must import no concurrency machinery: {conc_hits}"
    # POST-only SERVED handler; fail-closed empty-body edges; no stdlib send_error HTML.
    served = sorted(n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("do_"))
    assert served == ["do_POST"], f"the auth edge must be POST-only (served do_* handlers: {served})"
    assert "send_error" not in used, "server must never call stdlib send_error (HTML bodies)"
    assert 'send_header("Content-Length", "0")' in text, "server must emit empty bodies on the fail-closed/refused edges"
    for code in ("503", "405", "404"):
        assert code in text, f"server must pin the {code} fail-closed/refused edge"
    assert any(isinstance(n, ast.FunctionDef) and n.name == "log_message" for n in ast.walk(tree)), "server must silence log_message"
    assert "build_authenticate_server" in _top_level_defs(tree), "server must expose the build_authenticate_server factory"
    # Exact wire shapes present; references-only responses.
    groups = _string_key_groups(tree)
    assert _REQUEST_KEYS in groups, "server must validate the exact request envelope shape"
    assert _SUCCESS_KEYS in groups, "server must serialize exactly the 4-field success response"
    assert _FAILURE_KEYS in groups, "server must serialize exactly {status, public_code} on denial"
    hits = _forbidden_key_hits(groups)
    assert not hits, f"never-cross identifier serialized as a wire key: {hits}"
    # No api_gateway import; no Database Router RequestContext emission.
    tops = _import_tops(_SERVER_MOD)
    assert "api_gateway" not in tops, "server must not import api_gateway (DAG independence)"
    # AST-name ban (the docstring legitimately explains it emits NO RequestContext in prose).
    assert "RequestContext" not in used, "server must emit no Database Router RequestContext"
    # No public login/password/OAuth route (Section B).
    lowered = text.lower()
    for needle in ("login", "password", "oauth", "signin", "/authorize"):
        assert needle not in lowered, f"server must expose no public {needle} route"
    # No token/authorization logging: no logging import, no print().
    assert "logging" not in tops, "server must not import logging"
    assert not _print_calls(tree), "server must not print (no token/authorization logging)"
    # Adapter-only top-level defs + import surface.
    extra_defs = _top_level_defs(tree) - _SERVER_TOPLEVEL_ALLOW
    assert not extra_defs, f"server carries non-adapter top-level defs: {sorted(extra_defs)}"
    extra_imports = tops - _SERVER_IMPORT_TOPS_ALLOW
    assert not extra_imports, f"server imports outside the adapter-only surface: {sorted(extra_imports)}"


def test_server_guard_nonvacuity() -> None:
    threaded = "from http.server import ThreadingHTTPServer\n"
    assert "ThreadingHTTPServer" in threaded, "server guard must detect threaded-server machinery"
    business = _parse("def deal_query():\n    return 1\n")
    assert _top_level_defs(business) - _SERVER_TOPLEVEL_ALLOW == {"deal_query"}, "server guard must flag a non-adapter business def"
    bad = _string_key_groups(_parse('x = {"status": 1, "dsn": 2}\n'))
    assert _forbidden_key_hits(bad) == ["dsn"], "server guard must flag a forbidden serialized response field"


# --- guard asymmetry: client forbids jwt/crypto, server permits jwt -------------------------------
def test_guard_asymmetry_client_forbids_jwt_server_permits() -> None:
    # (07E-3c polish: the dead "PyJWT" entry is gone — the PyPI package imports as `jwt`.)
    assert {"jwt", "cryptography"} <= _CLIENT_FORBIDDEN_TOPS, "client guard must ban jwt/cryptography"
    assert not (_import_tops(_CLIENT_MOD) & {"jwt", "cryptography"}), "client module must import no jwt/crypto"
    assert "jwt" in _SERVER_IMPORT_TOPS_ALLOW, "server guard must permit jwt (validation lives in auth_router)"
    assert "jwt" not in _CLIENT_IMPORT_TOPS_ALLOW, "client guard must not permit jwt"


# --- 07E-3c composition guard: the config-selectable seam stays boundary-clean ---------------------
def test_composition_boundary_guard() -> None:
    assert _nonempty(_GATEWAY_MAIN), "the gateway composition root must exist and be non-empty"
    text = _GATEWAY_MAIN.read_text(encoding="utf-8")
    tree = _tree(_GATEWAY_MAIN)
    # Import surface: stdlib-only absolute tops (relative imports are intra-package); the ban set
    # covers auth_router/database_router/jwt/crypto/DB driver/supabase/threading explicitly.
    tops = _import_tops(_GATEWAY_MAIN)
    extra = tops - _GW_MAIN_IMPORT_TOPS_ALLOW
    assert not extra, f"composition root imports outside the stdlib surface: {sorted(extra)}"
    banned = tops & _CLIENT_FORBIDDEN_TOPS
    assert not banned, f"composition root must import none of auth_router/database_router/jwt/crypto/driver/threading: {sorted(banned)}"
    # The config-selectable seam exists: selector literal + helper def + the in-package client.
    assert _GW_SELECTOR_ENV in text, "composition root must pin the SP2_GW_AUTH_ROUTER_BASE_URL selector"
    assert "build_authenticator_from_env" in _top_level_defs(tree), "the config-selectable seam helper must exist"
    assert "HttpAuthenticator" in _names_used(tree), "the seam must select the in-package HttpAuthenticator transport client"
    # build_gateway stays required-injection (no runnable production composition): keyword-only
    # surface unchanged, authenticator + router carry NO defaults, the tail params keep theirs.
    bg: Optional[ast.FunctionDef] = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "build_gateway":
            bg = node
    assert bg is not None, "build_gateway must remain defined in the composition root"
    assert [a.arg for a in bg.args.kwonlyargs] == _GW_BUILD_GATEWAY_KWONLY, "build_gateway keyword-only surface must stay unchanged"
    assert not bg.args.args and not bg.args.posonlyargs, "build_gateway must stay keyword-only"
    assert bg.args.kw_defaults[0] is None and bg.args.kw_defaults[1] is None, "authenticator + router must stay REQUIRED (no default)"
    assert all(d is not None for d in bg.args.kw_defaults[2:]), "classify/audit/metrics must keep their defaults"
    # Composition performs no network I/O and no DSN/DB material; no serve lifecycle anywhere in
    # the composition root OR the auth server module (a running service is deployment scope).
    assert not _urlopen_calls(tree), "the composition root must perform no network I/O (lazy transport)"
    lowered = text.lower()
    for needle in ("dsn", "database_url", "postgresql://", "postgres://"):
        assert needle not in lowered, f"composition root must not reference {needle}"
    for needle in ("serve_forever", "threadinghttpserver"):
        assert needle not in lowered, f"composition root must not carry a serve lifecycle ({needle})"
    assert "serve_forever" not in _SERVER_MOD.read_text(encoding="utf-8"), "the auth server module must stay factory-only (no serve loop)"
    # No token/authorization handling or logging in the composition root.
    assert "logging" not in tops, "composition root must not import logging"
    assert not _print_calls(tree), "composition root must not print"


def test_composition_guard_nonvacuity() -> None:
    # The ban-set intersection flags a bad composition sample (same mechanism as the guard).
    assert _tops_of_source("from auth_router.main import build_authenticator\n") & _CLIENT_FORBIDDEN_TOPS == {"auth_router"}, (
        "composition guard must flag an auth_router import"
    )
    assert _tops_of_source("import psycopg\n") & _CLIENT_FORBIDDEN_TOPS == {"psycopg"}, "composition guard must flag a DB driver import"
    # A defaulted router (a runnable-composition drift) is detectable on the AST shape.
    sample = _parse("def build_gateway(*, authenticator=None, router=None):\n    pass\n")
    bad: Optional[ast.FunctionDef] = None
    for node in ast.walk(sample):
        if isinstance(node, ast.FunctionDef):
            bad = node
    assert bad is not None and bad.args.kw_defaults[1] is not None, "composition guard must detect a defaulted router"
    # The serve-lifecycle needle catches a planted run loop.
    assert "serve_forever" in "threading.Thread(target=server.serve_forever).start()".lower(), (
        "composition guard must detect a planted serve loop"
    )


if __name__ == "__main__":
    _scan.run(
        [
            test_client_boundary_guard,
            test_client_guard_nonvacuity,
            test_server_boundary_guard,
            test_server_guard_nonvacuity,
            test_guard_asymmetry_client_forbids_jwt_server_permits,
            test_composition_boundary_guard,
            test_composition_guard_nonvacuity,
        ]
    )
