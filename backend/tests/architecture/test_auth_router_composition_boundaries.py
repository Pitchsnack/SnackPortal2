"""Static guard — Auth Router config-selectable composition seam (default suite).

Pins the ``build_authenticator_from_env`` seam (auth_router/main.py) as a pure-stdlib
AST/text census (no network, no PyJWT, no DB). Module-scoped and non-vacuous: the guard
fails if the seam disappears or the boundary drifts, and carries a companion proving it
flags bad samples. This lives in its own file (not the 07E-3b auth-transport-pair guard)
because it guards a distinct composition root — the Auth Router's ``build_authenticator``
composition seam — keeping each guard's scope legible.

The composition root (``auth_router/main.py``) must:

* expose the ``build_authenticator_from_env`` seam with the
  ``SP2_AR_CONTROL_PLANE_READ_BASE_URL`` selector + the ``SP2_AR_ISSUERS`` trust-anchor
  literal, validate the URL structurally at the boundary (``urlsplit``), and select the
  in-package ``HttpControlPlaneRead`` read client + the ``PyJwtSignatureVerifier`` composed
  via ``build_authenticator`` (references only — no network, no DB, no key material);
* keep ``build_authenticator`` keyword-only and injection-oriented — ``verifier``/``read``/
  ``issuers`` REQUIRED (no default) and ``audit`` + ``cache_ttl_seconds`` defaulted;
* stay JWT-vendor-free and service-independent AT IMPORT: module-top absolute imports within
  ``{__future__, os, json, typing, urllib, shared}`` only — NO sibling service (independence
  contract), NO top-level ``jwt``/``cryptography`` (the verifier is lazily imported inside the
  seam), NO ``urllib.request`` (only ``urllib.parse.urlsplit``), NO DB driver, NO concurrency;
* perform no network I/O (``urlopen``) and carry no serve lifecycle (``serve_forever`` /
  ``ThreadingHTTPServer``) or DSN literal at composition — a running service is deployment scope.

Pure stdlib; standalone-runnable:  python tests/architecture/test_auth_router_composition_boundaries.py
"""

from __future__ import annotations

import ast
import pathlib
import sys
from typing import List, Optional, Set

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_AR_MAIN = _scan.BACKEND_ROOT / "auth_router" / "main.py"

_SELECTOR_ENV = "SP2_AR_CONTROL_PLANE_READ_BASE_URL"
_ISSUERS_ENV = "SP2_AR_ISSUERS"
_MAIN_IMPORT_TOPS_ALLOW = frozenset({"__future__", "os", "json", "typing", "urllib", "shared"})
_BUILD_AUTHENTICATOR_KWONLY = ["verifier", "read", "issuers", "audit", "cache_ttl_seconds"]

# The composition root must import none of these tops: the five sibling services (independence
# contract), the vendor cloud SDKs, the JWT crypto vendors (PyJWT/cryptography — the verifier is
# lazily imported inside the seam so main.py stays JWT-vendor-free at import), any DB driver, the
# HTTP-server/socket surface, and any concurrency machinery.
_FORBIDDEN_TOPS = frozenset(
    {
        "api_gateway",
        "database_router",
        "control_plane",
        "import_service",
        "lineage_service",
        "supabase",
        "lovable",
        "jwt",
        "cryptography",
        "http",
        "socket",
        "socketserver",
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
    semantics as ``_scan.imported_modules`` (relative imports are intra-package and skipped)."""
    mods: List[str] = []
    for node in ast.walk(_parse(source)):
        if isinstance(node, ast.Import):
            mods.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.append(node.module)
    return {m.split(".")[0] for m in mods}


def _abs_import_names(tree: ast.AST) -> Set[str]:
    """Full dotted absolute import names (level 0) — lets the guard distinguish
    ``urllib.request`` (forbidden client) from ``urllib.parse`` (allowed parser)."""
    mods: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.append(node.module)
    return set(mods)


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
def test_auth_router_composition_boundary_guard() -> None:
    assert _nonempty(_AR_MAIN), "the auth_router composition root must exist and be non-empty"
    text = _AR_MAIN.read_text(encoding="utf-8")
    tree = _tree(_AR_MAIN)

    # Import surface: stdlib + shared leaf only (relative in-package imports are skipped by _scan);
    # none of the sibling services / vendor SDKs / JWT crypto / DB driver / concurrency at module top.
    tops = _import_tops(_AR_MAIN)
    extra = tops - _MAIN_IMPORT_TOPS_ALLOW
    assert not extra, f"composition root imports outside the stdlib/shared surface: {sorted(extra)}"
    banned = tops & _FORBIDDEN_TOPS
    assert not banned, f"composition root must import no sibling service / vendor / driver / concurrency at import: {sorted(banned)}"
    assert "jwt" not in tops and "cryptography" not in tops, "composition root must stay JWT-vendor-free at import (lazy verifier import)"
    # urllib.parse (urlsplit) is allowed at top; urllib.request (the network client) is NOT.
    full = _abs_import_names(tree)
    assert not any(m == "urllib.request" or m.startswith("urllib.request.") for m in full), (
        "composition root must not import urllib.request at module top (only urllib.parse.urlsplit)"
    )

    # The config-selectable seam exists: both env literals + helper def + structural validation.
    assert _SELECTOR_ENV in text, "composition root must pin the SP2_AR_CONTROL_PLANE_READ_BASE_URL selector"
    assert _ISSUERS_ENV in text, "composition root must pin the SP2_AR_ISSUERS trust-anchor literal"
    assert "build_authenticator_from_env" in _top_level_defs(tree), "the config-selectable seam helper must exist"
    names = _names_used(tree)
    assert "urlsplit" in names, "the seam must validate the URL structurally at the boundary (urlsplit)"
    # The seam selects the in-package HttpControlPlaneRead client + PyJwtSignatureVerifier and composes
    # via build_authenticator (references only — no network, no DB, no key material at composition).
    assert "HttpControlPlaneRead" in names, "the seam must select the in-package HttpControlPlaneRead read client"
    assert "PyJwtSignatureVerifier" in names, "the seam must compose the production PyJwtSignatureVerifier"
    assert "build_authenticator" in names, "the seam must compose via build_authenticator (additive; injection path preserved)"

    # build_authenticator stays required-injection + keyword-only (no runnable-composition drift):
    # the exact kwonly surface, verifier/read/issuers REQUIRED, audit + cache knob defaulted.
    ba = _func(tree, "build_authenticator")
    assert ba is not None, "build_authenticator must remain defined in the composition root"
    assert [a.arg for a in ba.args.kwonlyargs] == _BUILD_AUTHENTICATOR_KWONLY, (
        "build_authenticator keyword-only surface must stay unchanged"
    )
    assert not ba.args.args and not ba.args.posonlyargs, "build_authenticator must stay keyword-only"
    assert ba.args.kw_defaults[0] is None and ba.args.kw_defaults[1] is None and ba.args.kw_defaults[2] is None, (
        "verifier/read/issuers must stay REQUIRED (no default)"
    )
    assert all(d is not None for d in ba.args.kw_defaults[3:]), "audit + cache_ttl_seconds must keep their defaults"

    # Inert composition: no network I/O and no serve lifecycle / DSN literal at the composition root.
    assert not _urlopen_calls(tree), "the composition root must perform no network I/O at composition (lazy transport)"
    lowered = text.lower()
    for needle in ("serve_forever", "threadinghttpserver", "threadingmixin"):
        assert needle not in lowered, f"composition root must carry no serve lifecycle ({needle})"
    for needle in ("dsn", "database_url", "postgresql://", "postgres://"):
        assert needle not in lowered, f"composition root must embed no {needle} at composition"


def test_auth_router_composition_guard_nonvacuity() -> None:
    # The ban-set intersection flags sibling-service / JWT-crypto / DB-driver imports (the same
    # mechanism the guard applies to the real module).
    assert _tops_of_source("from database_router.main import build_router\n") & _FORBIDDEN_TOPS == {"database_router"}, (
        "composition guard must flag a database_router import"
    )
    assert _tops_of_source("from api_gateway.main import build_gateway\n") & _FORBIDDEN_TOPS == {"api_gateway"}, (
        "composition guard must flag an api_gateway import"
    )
    assert _tops_of_source("import jwt\n") & _FORBIDDEN_TOPS == {"jwt"}, "composition guard must flag a top-level PyJWT import"
    assert _tops_of_source("from cryptography.hazmat.primitives import serialization\n") & _FORBIDDEN_TOPS == {"cryptography"}, (
        "composition guard must flag a top-level cryptography import"
    )
    # urllib.request is distinguishable from urllib.parse at the full-name level.
    assert any(m.startswith("urllib.request") for m in _abs_import_names(_parse("import urllib.request\n"))), (
        "composition guard must detect a urllib.request import"
    )
    assert not any(m.startswith("urllib.request") for m in _abs_import_names(_parse("from urllib.parse import urlsplit\n"))), (
        "composition guard must NOT flag urllib.parse as urllib.request"
    )
    # A root missing the seam is detectable.
    assert "build_authenticator_from_env" not in _top_level_defs(_parse("def other():\n    pass\n")), (
        "composition guard must distinguish a root missing the seam"
    )
    # A defaulted REQUIRED injection arg (a runnable-composition drift) is detectable on the AST shape.
    sample = _func(_parse("def build_authenticator(*, verifier=None, read=None, issuers=None):\n    pass\n"), "build_authenticator")
    assert sample is not None and sample.args.kw_defaults[0] is not None, "composition guard must detect a defaulted required injection arg"
    # The serve-lifecycle needle catches a planted run loop; the client-name check distinguishes clients.
    assert "serve_forever" in "threading.Thread(target=server.serve_forever).start()".lower(), (
        "composition guard must detect a planted serve loop"
    )
    assert "HttpControlPlaneRead" not in _names_used(_parse("x = HttpAuthenticator()\n")), (
        "composition guard must distinguish HttpControlPlaneRead usage from another client"
    )


if __name__ == "__main__":
    _scan.run(
        [
            test_auth_router_composition_boundary_guard,
            test_auth_router_composition_guard_nonvacuity,
        ]
    )
