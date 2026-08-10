"""Static guard — Database Router config-selectable composition seam (default suite).

Pins the ``build_router_from_env`` seam (database_router/main.py) as a pure-stdlib AST/text
census (no PostgreSQL, no driver, no network). Module-scoped and non-vacuous: the guard fails
if the seam disappears or the boundary drifts, and carries a companion proving it flags a bad
sample. This lives in its own file (not the 07E-3b auth-transport-pair guard) because it guards
a distinct service's composition root — the Database Router — keeping each guard's scope legible.

The composition root (``database_router/main.py``) must:

* expose the ``build_router_from_env`` seam with the ``SP2_DBR_ROUTING_READ_BASE_URL`` selector,
  validate structurally at the boundary (``urlsplit``), and select the in-package
  ``HttpRoutingRead`` routing-read client composed via ``build_router`` with the env tenant
  ``EnvTenantSecretStore`` + the ``PsycopgConnectionFactory`` (references only — no DB open);
* keep ``build_router`` keyword-only and injection-oriented — ``read``/``secret_store``/
  ``connection_factory`` REQUIRED (no default), the ``audit`` + config knobs defaulted, and the
  separate ``max_per_tenant`` / ``bulk_max_per_tenant`` pool-lane knobs preserved (D-13);
* stay driver-free and service-independent AT IMPORT: module-top absolute imports within
  ``{__future__, os, typing, urllib, shared}`` only — NO sibling service (independence contract),
  NO top-level ``psycopg``/DB driver (the factory is lazily imported inside the seam), NO threading;
* perform no network I/O (``urlopen``) and carry no serve lifecycle (``serve_forever`` /
  ``ThreadingHTTPServer``) at composition — a running service is deployment scope;
* additionally expose the paired ``build_dispatch_server_from_env`` seam (router-gate-first via
  ``build_router_from_env``, the ``SP2_DBR_DISPATCH_HOST`` / ``SP2_DBR_DISPATCH_PORT`` bind knobs,
  and the ``build_dispatch_server`` adapter) WITHOUT widening the module-top import surface or adding
  a serve lifecycle — it constructs a server object (binding an ephemeral socket) but never serves.

Pure stdlib; standalone-runnable:  python tests/architecture/test_dbr_composition_boundaries.py
"""

from __future__ import annotations

import ast
import pathlib
import sys
from typing import List, Optional, Set

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_DBR_MAIN = _scan.BACKEND_ROOT / "database_router" / "main.py"

_SELECTOR_ENV = "SP2_DBR_ROUTING_READ_BASE_URL"
# The bind knobs of the SERVER seam this guard covers. They were the internal Gateway-facing
# dispatch server's (SP2_DBR_DISPATCH_HOST/PORT) until that edge was deleted with the API
# Gateway; the surviving server seam in this composition root is the PUBLIC tenant Startup edge.
_EDGE_HOST_ENV = "SP2_DBR_PUBLIC_STARTUP_HOST"
_EDGE_PORT_ENV = "SP2_DBR_PUBLIC_STARTUP_PORT"
_MAIN_IMPORT_TOPS_ALLOW = frozenset({"__future__", "os", "typing", "urllib", "shared"})
_BUILD_ROUTER_KWONLY = [
    "read",
    "secret_store",
    "connection_factory",
    "audit",
    "supported_schema_versions",
    "cache_ttl_seconds",
    "max_per_tenant",
    "bulk_max_per_tenant",
    "idle_timeout_seconds",
]

# The composition root must import none of these tops: the five sibling services (independence
# contract), the vendor SDKs, any top-level DB driver (the psycopg factory is lazily imported
# inside the seam so main.py stays driver-free at import), and any concurrency machinery.
_FORBIDDEN_TOPS = frozenset(
    {
        "auth_router",
        "control_plane",
        "import_service",
        "lineage_service",
        "supabase",
        "lovable",
        "psycopg",
        "psycopg2",
        "asyncpg",
        "sqlalchemy",
        "databases",
        "aiopg",
        "threading",
        "asyncio",
        "concurrent",
        "multiprocessing",
        "contextvars",
    }
)


# --- pure helpers (exercised by the non-vacuity companion) ----------------------------------------
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
    assert isinstance(tree, ast.Module)
    return {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def _import_tops(path: pathlib.Path) -> Set[str]:
    return {m.split(".")[0] for m in _scan.imported_modules(path)}


def _tops_of_source(source: str) -> Set[str]:
    """Top-level imported module names of an in-memory source sample — the same absolute-import
    semantics as ``_scan.imported_modules`` (relative imports are intra-package and skipped), so the
    non-vacuity companion can prove the ban-set intersection mechanism flags a bad module."""
    mods: List[str] = []
    for node in ast.walk(_parse(source)):
        if isinstance(node, ast.Import):
            mods.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.append(node.module)
    return {m.split(".")[0] for m in mods}


def _urlopen_calls(tree: ast.AST) -> List[ast.Call]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "urlopen"]


def _func(tree: ast.AST, name: str) -> Optional[ast.FunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _nonempty(path: pathlib.Path) -> bool:
    return path.is_file() and bool(path.read_text(encoding="utf-8").strip())


# --- composition boundary guard -------------------------------------------------------------------
def test_dbr_composition_boundary_guard() -> None:
    assert _nonempty(_DBR_MAIN), "the database_router composition root must exist and be non-empty"
    text = _DBR_MAIN.read_text(encoding="utf-8")
    tree = _tree(_DBR_MAIN)

    # Import surface: stdlib + shared leaf only (relative in-package imports are skipped by _scan);
    # none of the sibling services / vendor SDKs / DB driver / concurrency machinery at module top.
    tops = _import_tops(_DBR_MAIN)
    extra = tops - _MAIN_IMPORT_TOPS_ALLOW
    assert not extra, f"composition root imports outside the stdlib/shared surface: {sorted(extra)}"
    banned = tops & _FORBIDDEN_TOPS
    assert not banned, f"composition root must import no sibling service / driver / concurrency at import: {sorted(banned)}"
    assert "psycopg" not in tops, "composition root must stay driver-free at import (lazy psycopg factory import)"

    # The config-selectable seam exists: selector literal + helper def + structural validation.
    assert _SELECTOR_ENV in text, "composition root must pin the SP2_DBR_ROUTING_READ_BASE_URL selector"
    assert "build_router_from_env" in _top_level_defs(tree), "the config-selectable seam helper must exist"
    names = _names_used(tree)
    assert "urlsplit" in names, "the seam must validate structurally at the boundary (urlsplit)"
    # The seam selects the in-package HttpRoutingRead client and composes via build_router with the
    # existing production tenant SecretStore + psycopg connection factory (references only).
    assert "HttpRoutingRead" in names, "the seam must select the in-package HttpRoutingRead routing-read client"
    assert "build_router" in names, "the seam must compose via build_router (additive; injection path preserved)"
    for adapter in ("EnvTenantSecretStore", "PsycopgConnectionFactory"):
        assert adapter in names, f"the seam must compose the existing {adapter} adapter"

    # build_router stays required-injection + keyword-only (no runnable-composition drift): the exact
    # kwonly surface, read/secret_store/connection_factory REQUIRED, audit + config knobs defaulted.
    br = _func(tree, "build_router")
    assert br is not None, "build_router must remain defined in the composition root"
    assert [a.arg for a in br.args.kwonlyargs] == _BUILD_ROUTER_KWONLY, "build_router keyword-only surface must stay unchanged"
    assert not br.args.args and not br.args.posonlyargs, "build_router must stay keyword-only"
    assert br.args.kw_defaults[0] is None and br.args.kw_defaults[1] is None and br.args.kw_defaults[2] is None, (
        "read/secret_store/connection_factory must stay REQUIRED (no default)"
    )
    assert all(d is not None for d in br.args.kw_defaults[3:]), "audit + config knobs must keep their defaults"
    # Pool-lane isolation preserved (D-13): separate interactive + bulk capacity knobs both present.
    assert "max_per_tenant" in _BUILD_ROUTER_KWONLY and "bulk_max_per_tenant" in _BUILD_ROUTER_KWONLY, (
        "interactive + bulk pool-lane knobs must stay separate (D-13)"
    )

    # Inert composition: no network I/O and no serve lifecycle / DSN literal at the composition root.
    assert not _urlopen_calls(tree), "the composition root must perform no network I/O at composition (lazy transport)"
    lowered = text.lower()
    for needle in ("serve_forever", "threadinghttpserver", "threadingmixin"):
        assert needle not in lowered, f"composition root must carry no serve lifecycle ({needle})"
    for needle in ("dsn", "database_url", "postgresql://", "postgres://"):
        assert needle not in lowered, f"composition root must embed no {needle} at composition"


def test_dbr_composition_guard_nonvacuity() -> None:
    # The ban-set intersection flags sibling-service / DB-driver imports (the same mechanism the guard
    # applies to the real module) — critically NO auth_router/control_plane and NO psycopg.
    # The probe names a package that EXISTS: after the API Gateway was deleted a planted
    # `import api_gateway` would be flagged for the wrong reason (unresolvable).
    assert _tops_of_source("from auth_router.main import build_authenticator\n") & _FORBIDDEN_TOPS == {"auth_router"}, (
        "composition guard must flag a sibling-service import"
    )
    assert _tops_of_source("import auth_router\n") & _FORBIDDEN_TOPS == {"auth_router"}, "composition guard must flag an auth_router import"
    assert _tops_of_source("import psycopg\n") & _FORBIDDEN_TOPS == {"psycopg"}, "composition guard must flag a top-level DB driver import"
    # A root missing the seam is detectable.
    assert "build_router_from_env" not in _top_level_defs(_parse("def other():\n    pass\n")), (
        "composition guard must distinguish a root missing the seam"
    )
    # A defaulted REQUIRED injection arg (a runnable-composition drift) is detectable on the AST shape.
    sample = _func(_parse("def build_router(*, read=None, secret_store=None, connection_factory=None):\n    pass\n"), "build_router")
    assert sample is not None and sample.args.kw_defaults[0] is not None, "composition guard must detect a defaulted required injection arg"
    # The serve-lifecycle needle catches a planted run loop; the client-name check distinguishes clients.
    assert "serve_forever" in "threading.Thread(target=server.serve_forever).start()".lower(), (
        "composition guard must detect a planted serve loop"
    )
    assert "HttpRoutingRead" not in _names_used(_parse("x = HttpRouterDispatch()\n")), (
        "composition guard must distinguish HttpRoutingRead usage from another client"
    )


# --- public-edge server composition guard (build_public_startup_edge_server_from_env) --------------
# Successor of the dispatch-server composition guard. The subject changed (the internal
# Gateway->Database-Router dispatch server was deleted with the API Gateway); every property is the
# same, because they were never properties of the Gateway — they are properties of composing a
# server object inside this composition root.
def test_dbr_public_edge_server_composition_boundary_guard() -> None:
    assert _nonempty(_DBR_MAIN), "the database_router composition root must exist and be non-empty"
    text = _DBR_MAIN.read_text(encoding="utf-8")
    tree = _tree(_DBR_MAIN)
    names = _names_used(tree)
    defs = _top_level_defs(tree)

    # The public-edge seam exists with BOTH bind selectors, is gate-first, and composes the edge's
    # own factory (references only — construction binds a socket, not a DB).
    assert "build_public_startup_edge_server_from_env" in defs, "the public-edge server composition seam must exist"
    assert _EDGE_HOST_ENV in text, "composition root must pin the SP2_DBR_PUBLIC_STARTUP_HOST selector"
    assert _EDGE_PORT_ENV in text, "composition root must pin the SP2_DBR_PUBLIC_STARTUP_PORT selector"
    assert "build_public_startup_edge_server" in names, "the seam must compose via the edge's build_public_startup_edge_server factory"
    assert "build_router_from_env" in names, "the seam must be router-gate-first (calls build_router_from_env)"
    # The deleted seams must not come back under their old names.
    for gone in ("build_dispatch_server_from_env", "build_tenant_startup_server_from_env"):
        assert gone not in defs, f"{gone} was removed with the API Gateway and must not reappear"

    # Additive + boundary-clean: the seam does NOT widen the module-top import surface (the edge
    # factory is lazily/relatively imported inside the seam -> skipped by _scan), imports no sibling
    # service / DB driver / concurrency top, and adds no serve lifecycle at composition.
    tops = _import_tops(_DBR_MAIN)
    assert not (tops - _MAIN_IMPORT_TOPS_ALLOW), (
        f"the seam must not widen the module-top import surface: {sorted(tops - _MAIN_IMPORT_TOPS_ALLOW)}"
    )
    assert not (tops & _FORBIDDEN_TOPS), "the seam must import no sibling service / DB driver / concurrency at module top"
    assert "psycopg" not in tops, "the seam must keep the composition root driver-free at import"
    assert not _urlopen_calls(tree), "the composition root must perform no network I/O at composition"
    lowered = text.lower()
    for needle in ("serve_forever", "threadinghttpserver", "threadingmixin"):
        assert needle not in lowered, f"the seam must carry no serve lifecycle ({needle}) — it constructs only"


def test_dbr_public_edge_guard_nonvacuity() -> None:
    # A root missing the public-edge seam is detectable.
    assert "build_public_startup_edge_server_from_env" not in _top_level_defs(_parse("def other():\n    pass\n")), (
        "the guard must distinguish a root missing the public-edge seam"
    )
    # The serve-lifecycle needle catches a planted serve loop (the seam must construct, never serve).
    assert "serve_forever" in "threading.Thread(target=server.serve_forever).start()".lower(), "the guard must detect a planted serve loop"
    # The ban-set intersection still flags a sibling-service import in a bad seam sample.
    assert _tops_of_source("from auth_router.main import build_authenticator\n") & _FORBIDDEN_TOPS == {"auth_router"}, (
        "the guard must flag a sibling-service import"
    )


if __name__ == "__main__":
    _scan.run(
        [
            test_dbr_composition_boundary_guard,
            test_dbr_composition_guard_nonvacuity,
            test_dbr_public_edge_server_composition_boundary_guard,
            test_dbr_public_edge_guard_nonvacuity,
        ]
    )
