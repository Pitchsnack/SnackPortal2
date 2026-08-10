"""Pure-stdlib helpers for the architecture tests.

These checks encode the Build Phase 1 dependency/governance rules. They run under
pytest and also standalone (`python tests/architecture/test_*.py`) so they can be
executed without third-party tooling.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Callable, Iterator, List, Tuple

BACKEND_ROOT = Path(__file__).resolve().parents[2]  # .../backend
REPO_ROOT = BACKEND_ROOT.parent

# The runtime service packages. ``api_gateway`` was removed with the API Gateway; every census
# built from this list therefore covers the SURVIVING services exhaustively, and re-adding a
# service here is the single edit that enrolls it in all of them.
SERVICE_PACKAGES = [
    "auth_router",
    "database_router",
    "control_plane",
    "import_service",
    "lineage_service",
]
SKIP_PARTS = {".venv", "venv", "__pycache__", "build", "dist"}


def py_files(root: Path = BACKEND_ROOT) -> Iterator[Path]:
    for p in root.rglob("*.py"):
        if SKIP_PARTS & set(p.parts):
            continue
        yield p


def imported_modules(path: Path) -> List[str]:
    """Absolute imported module names (relative imports, level>0, are intra-package)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    mods: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                mods.append(node.module)
    return mods


def relposix(path: Path) -> str:
    return path.relative_to(BACKEND_ROOT).as_posix()


# The FastAPI route-decorator verbs. Every serving edge declares its exposed method set through
# these, so they are what the route/method censuses read (the pre-FastAPI edges expressed the same
# set as ``do_GET`` / ``do_POST`` handler names).
ROUTE_VERBS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})

# The generic registration form. `@app.api_route(path, methods=[...])` serves exactly the listed
# methods and is NOT covered by ROUTE_VERBS — a census that only knew the verb decorators was blind
# to it. On the API Gateway edge that blindness hid four registrations, including the tenant-Startup
# family's served GET and PATCH.
ROUTE_ANY = "api_route"

# Emitted when a registration's `methods=` is a computed expression rather than a literal list (the
# Gateway edge derives `/memberships`, `/health` and `/readiness` from the `_EXPOSED_ROUTES` dict, so
# the served set is structurally bound to that dict and cannot be read statically here). A census
# that silently dropped these would under-report the served surface; this makes the gap VISIBLE.
COMPUTED_METHODS = "<computed>"


def _decorator_path(dec: ast.AST) -> "str | None":
    """The route path of a registration decorator: the string literal, or the NAME it refers to."""
    if not isinstance(dec, ast.Call) or not dec.args:
        return None
    first = dec.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    if isinstance(first, ast.Name):
        return first.id
    return None


def _api_route_methods(dec: ast.AST) -> List[str]:
    if not isinstance(dec, ast.Call):
        return []
    for keyword in dec.keywords or []:
        if keyword.arg != "methods":
            continue
        if isinstance(keyword.value, (ast.List, ast.Tuple, ast.Set)):
            out = []
            for element in keyword.value.elts:
                if isinstance(element, ast.Constant) and isinstance(element.value, str):
                    out.append(element.value.lower())
                else:
                    out.append(COMPUTED_METHODS)
            return out
        return [COMPUTED_METHODS]
    return [COMPUTED_METHODS]


def own_route_methods(node: ast.AST) -> List[str]:
    """The HTTP methods declared by THIS function's own route decorators.

    Covers both registration forms: the verb decorators (``@app.get`` …) and the generic
    ``@app.api_route(path, methods=[...])``. Deliberately does not descend into the node: an app
    factory (``_make_app``) encloses the decorated handlers, and walking into it would attribute
    their routes to the factory too. ``@app.middleware`` / ``@app.exception_handler`` are excluded —
    neither exposes a method.
    """
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return []
    methods: List[str] = []
    for dec in node.decorator_list:
        func = dec.func if isinstance(dec, ast.Call) else dec
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr in ROUTE_VERBS:
            methods.append(func.attr)
        elif func.attr == ROUTE_ANY:
            methods.extend(_api_route_methods(dec))
    return sorted(methods)


def route_registrations(tree: ast.AST) -> List[Tuple[str, str]]:
    """Every ``(route path, METHOD)`` a module registers, across both decorator forms.

    The path is the string literal when the decorator carries one, and otherwise the NAME of the
    constant it refers to (e.g. ``_TENANT_STARTUP_ROUTE_TEMPLATE``) — the parameterized families are
    registered through module constants, so a literal-only reader would see nothing.

    This is the census to use when the question is *"which methods does this route actually serve?"*.
    Comparing a module constant against itself answers a different question, and answers it
    tautologically: a widened ``@app.api_route(..., methods=[...])`` would not move it.
    """
    out: List[Tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            func = dec.func if isinstance(dec, ast.Call) else dec
            if not isinstance(func, ast.Attribute):
                continue
            path = _decorator_path(dec)
            if path is None:
                continue
            if func.attr in ROUTE_VERBS:
                out.append((path, func.attr.upper()))
            elif func.attr == ROUTE_ANY:
                out.extend((path, method.upper()) for method in _api_route_methods(dec))
    return out


def registered_route_methods(tree: ast.AST) -> List[str]:
    """The sorted HTTP methods a module exposes as routes — its served method census."""
    methods: List[str] = []
    for node in ast.walk(tree):
        methods.extend(own_route_methods(node))
    return sorted(methods)


def run(tests: List[Callable[[], None]]) -> None:
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS:", t.__name__)
        except AssertionError as exc:
            failed += 1
            print("FAIL:", t.__name__, "-", exc)
    if failed:
        print(f"{failed} test(s) failed")
        sys.exit(1)
    print("ALL PASSED")
