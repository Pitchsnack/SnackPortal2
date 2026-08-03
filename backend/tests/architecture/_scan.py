"""Pure-stdlib helpers for the architecture tests.

These checks encode the Build Phase 1 dependency/governance rules. They run under
pytest and also standalone (`python tests/architecture/test_*.py`) so they can be
executed without third-party tooling.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Callable, Iterator, List

BACKEND_ROOT = Path(__file__).resolve().parents[2]  # .../backend
REPO_ROOT = BACKEND_ROOT.parent

SERVICE_PACKAGES = [
    "api_gateway",
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


def own_route_methods(node: ast.AST) -> List[str]:
    """The HTTP methods declared by THIS function's own ``@app.<method>(...)`` decorators.

    Deliberately does not descend into the node: an app factory (``_make_app``) encloses the
    decorated handlers, and walking into it would attribute their routes to the factory too.
    ``@app.middleware`` / ``@app.exception_handler`` are excluded — neither exposes a method.
    """
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return []
    methods: List[str] = []
    for dec in node.decorator_list:
        func = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(func, ast.Attribute) and func.attr in ROUTE_VERBS:
            methods.append(func.attr)
    return sorted(methods)


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
