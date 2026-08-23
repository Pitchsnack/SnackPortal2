"""Stage 6 — every module the rebuild imports at runtime must be installed by a runtime install.

**Why this file exists.** Stage 6 containerized the fourteen services for the first time, and a
``pip install .`` produced a backend that could not make a single internal call: ``httpx`` was
imported by five runtime modules but declared only under the ``dev`` extra, described there as a
test-only need of starlette's ``TestClient``.

It did not even fail closed. In every one of those five modules the ``import httpx`` sits
*outside* the surrounding ``try``, so ``ModuleNotFoundError`` escaped the fail-closed handler and
surfaced as HTTP 500 rather than the canonical denial — the failure mode the whole
unconfigured-means-closed design exists to prevent.

The default test suite could not see this, because the test environment installs ``.[dev]`` and
therefore always has ``httpx``. A dependency present in every environment that runs the tests is
invisible to those tests. So the check here is **static**: it compares the imports in the source
against the declarations in ``pyproject.toml``, never against what happens to be importable in the
running interpreter.

Pure stdlib. Runnable standalone:  python tests/snackportal2/test_runtime_dependencies.py
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys
from typing import Dict, List, Set

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BACKEND = _REPO_ROOT / "backend"
_REBUILD = _BACKEND / "snackportal2"
_PYPROJECT = _BACKEND / "pyproject.toml"

#: Import name -> the distribution that provides it, where the two differ.
_DISTRIBUTION_OF: Dict[str, str] = {"jwt": "pyjwt"}

#: Import names a *declared* dependency is contractually guaranteed to bring, with the reason
#: spelled out. Enumerated rather than inferred: "it works here because something happened to
#: pull it in" is exactly the assumption that produced the httpx defect.
_GUARANTEED_BY: Dict[str, str] = {
    "pydantic": "fastapi",
    "starlette": "fastapi",
}


def _names_in(fragment: str) -> List[str]:
    """The distribution names in one dependency-array fragment, without version specifiers."""
    names: List[str] = []
    for quoted in re.findall(r"[\"']([^\"']+)[\"']", fragment):
        # "psycopg[binary]>=3" -> "psycopg";  "fastapi>=0.115" -> "fastapi"
        name = re.split(r"[\[(<>=!~;\s]", quoted, maxsplit=1)[0]
        if name:
            names.append(name.strip().casefold().replace("_", "-"))
    return names


def parse_declared_dependencies(text: str) -> Set[str]:
    """Return the distribution names in ``[project].dependencies``, normalized.

    Hand-rolled rather than via ``tomllib`` so the check runs identically on every interpreter the
    project supports (``requires-python >= 3.10``; ``tomllib`` arrived in 3.11). It is small, it is
    scoped to one array, and it is self-tested against a planted omission below — the same
    discipline the compose scanner in ``test_deployment_exposure.py`` uses, for the same reason: a
    parser that silently finds nothing makes every assertion built on it pass.
    """
    declared: Set[str] = set()
    in_project = False
    in_dependencies = False

    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("#"):
            continue

        if not in_dependencies and stripped.startswith("[") and stripped.endswith("]"):
            in_project = stripped == "[project]"
            continue

        if not in_project:
            continue

        if not in_dependencies:
            if re.match(r"^dependencies\s*=\s*\[", stripped):
                in_dependencies = True
                remainder = stripped.split("[", 1)[1]
                if "]" in remainder:  # a single-line array
                    declared.update(_names_in(remainder.split("]", 1)[0]))
                    in_dependencies = False
            continue

        if stripped.startswith("]"):
            in_dependencies = False
            continue

        declared.update(_names_in(stripped))

    return declared


def third_party_imports(root: pathlib.Path) -> Dict[str, Set[str]]:
    """Top-level third-party import name -> the files that import it."""
    stdlib = set(sys.stdlib_module_names)
    found: Dict[str, Set[str]] = {}

    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules: List[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                # A relative import (level > 0) is internal by construction.
                modules = [node.module]
            for module in modules:
                top = module.split(".")[0]
                if top in stdlib or top == root.name:
                    continue
                found.setdefault(top, set()).add(path.relative_to(_REPO_ROOT).as_posix())

    return found


# --- the checks -----------------------------------------------------------------------------


def test_every_runtime_import_is_a_declared_runtime_dependency() -> None:
    """The regression check. Moving ``httpx`` back to the ``dev`` extra fails here."""
    declared = parse_declared_dependencies(_PYPROJECT.read_text(encoding="utf-8"))
    assert declared, "no runtime dependencies parsed from pyproject.toml; the check would be vacuous"

    undeclared: Dict[str, Set[str]] = {}
    for imported, files in third_party_imports(_REBUILD).items():
        distribution = _DISTRIBUTION_OF.get(imported, imported).casefold().replace("_", "-")
        if distribution in declared or _GUARANTEED_BY.get(imported) in declared:
            continue
        undeclared[imported] = files

    assert undeclared == {}, "imported at runtime but not installed by `pip install .`: " + repr(
        {name: sorted(files) for name, files in sorted(undeclared.items())}
    )


def test_httpx_specifically_is_a_runtime_dependency() -> None:
    """Named on its own because it is the defect this file was written for.

    The general check above would also pass if ``httpx`` simply stopped being imported. This one
    states the actual fact: the rebuild makes internal HTTP calls, so its HTTP client is runtime.
    """
    importers = third_party_imports(_REBUILD).get("httpx", set())
    assert len(importers) >= 4, "httpx is no longer widely imported; re-derive this check rather than deleting it"
    assert "httpx" in parse_declared_dependencies(_PYPROJECT.read_text(encoding="utf-8")), "httpx is not a runtime dependency"


def test_the_dev_extra_is_not_the_home_of_a_runtime_dependency() -> None:
    """A runtime need must not be satisfied only by a ``dev``-only declaration."""
    text = _PYPROJECT.read_text(encoding="utf-8")
    parts = text.split("[project.optional-dependencies]", 1)
    assert len(parts) == 2, "the dev extra is missing; this check would be vacuous"
    dev_section = parts[1].split("[build-system]", 1)[0]
    assert '"httpx"' not in dev_section, "httpx is declared in the dev extra; it is a runtime dependency"


def test_the_image_build_context_excludes_the_virtual_environment() -> None:
    """A ``.dockerignore`` must exist and must exclude ``.venv``.

    Not tidiness. The uncontrolled context was ~1.1 GB (``backend/.venv`` alone ~871 MB) and the
    daemon receives all of it before the first instruction runs — enough, on the Stage 6
    development host, to take the Docker engine down mid-build rather than merely make the build
    slow. The Dockerfile COPYs named directories, so this is about what crosses the wire.
    """
    dockerignore = _BACKEND / ".dockerignore"
    assert dockerignore.exists(), "backend/.dockerignore is missing; the image build ships the whole worktree"
    entries = {
        line.strip().rstrip("/")
        for line in dockerignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    for required in (".venv", "build", "tests", ".git", "__pycache__"):
        assert required in entries, ".dockerignore does not exclude " + required


def test_the_dockerfile_exists_and_names_no_default_service() -> None:
    """The compose manifest declares ``build: context: ../../backend``; without this it cannot build.

    And no service may be the default: a container started without a command must fail loudly
    rather than quietly become whichever of the fourteen happened to be listed first.
    """
    dockerfile = _BACKEND / "Dockerfile"
    assert dockerfile.exists(), "backend/Dockerfile is missing; docker-compose.rebuild.yml cannot build"
    text = dockerfile.read_text(encoding="utf-8")
    assert "ENTRYPOINT" not in text, "an ENTRYPOINT would pre-empt the per-service command the manifest supplies"
    assert "USER " in text, "the image runs as root"


def test_the_declaration_scanner_detects_a_planted_omission() -> None:
    """Non-vacuity. A parser that returned an empty set would make every check above green."""
    planted = '[project]\nname = "x"\ndependencies = [\n  "fastapi>=0.115",\n  "psycopg[binary]>=3",\n  # "httpx",\n]\n'
    declared = parse_declared_dependencies(planted)
    assert declared == {"fastapi", "psycopg"}, "the scanner misread the planted array: " + repr(sorted(declared))

    single_line = '[project]\ndependencies = ["a>=1", "b"]\n'
    assert parse_declared_dependencies(single_line) == {"a", "b"}, "the scanner cannot read a single-line array"

    other_table = '[tool.other]\ndependencies = ["should-not-be-read"]\n'
    assert parse_declared_dependencies(other_table) == set(), "the scanner read a dependencies array outside [project]"


def test_the_import_census_detects_real_imports() -> None:
    """Non-vacuity for the other half: an AST walk that found nothing would also pass."""
    census = third_party_imports(_REBUILD)
    assert "fastapi" in census and "uvicorn" in census, "the import census found nothing; it proves nothing"
    assert all(not name.startswith("snackportal2") for name in census), "the census counted an internal import as third-party"


def _self_test() -> None:
    test_every_runtime_import_is_a_declared_runtime_dependency()
    test_httpx_specifically_is_a_runtime_dependency()
    test_the_dev_extra_is_not_the_home_of_a_runtime_dependency()
    test_the_image_build_context_excludes_the_virtual_environment()
    test_the_dockerfile_exists_and_names_no_default_service()
    test_the_declaration_scanner_detects_a_planted_omission()
    test_the_import_census_detects_real_imports()
    print("runtime dependency declarations: PASS")


if __name__ == "__main__":
    sys.path.insert(0, str(_BACKEND))
    _self_test()


__all__ = ["parse_declared_dependencies", "third_party_imports"]
