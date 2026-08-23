"""Cross-service topology gate — the properties no single service test can see.

Every service is checked here rather than trusting each service's own module to check
itself, because the failures this file exists to catch are failures of *omission*: a service
that forgets its OpenAPI test, a service that quietly binds a wider interface than its
siblings, a service that reaches back into the retired architecture. An absent check looks
exactly like a passing one from inside the service that lacks it.

The implemented set is asserted explicitly rather than discovered-and-skipped, so a service
that fails to import shows up as a failure instead of vanishing from the census.
"""

from __future__ import annotations

import ast
import importlib
import pathlib
from typing import Dict, List

from fastapi import FastAPI

from snackportal2.shared.config import SERVICE_REGISTRY, load_settings

from ._openapi_rules import check_document

#: All fourteen services of the Option A target architecture. Asserted explicitly rather than
#: discovered-and-skipped, so a service that fails to import shows up as a failure instead of
#: vanishing from the census.
IMPLEMENTED_SERVICES = (
    "authentication",
    "access_control",
    "control_plane",
    "database_router",
    "bff",
    "audit",
    "startups",
    "investors",
    "deals",
    "contacts",
    "sharing",
    "import_service",
    "lineage",
    "ai_agents",
)

_PACKAGE_ROOT = pathlib.Path(importlib.import_module("snackportal2").__file__ or "").parent


def _load(service_key: str) -> FastAPI:
    module = importlib.import_module("snackportal2.services." + service_key + ".main")
    app = getattr(module, "app", None)
    assert isinstance(app, FastAPI), service_key + " does not define a module-level `app = FastAPI()`"
    return app


def test_every_implemented_service_defines_its_own_app() -> None:
    """IC-013 §21: each service has its own main.py defining its own app = FastAPI()."""
    for service_key in IMPLEMENTED_SERVICES:
        main_path = _PACKAGE_ROOT / "services" / service_key / "main.py"
        assert main_path.exists(), service_key + " has no main.py"
        _load(service_key)


def test_every_implemented_service_starts_independently() -> None:
    """Independently bootable means importable and servable without any sibling present.

    Proven by the module graph rather than by starting processes: import-linter's
    independence contract already forbids a service importing another's implementation, and
    this asserts the complementary property — that a service's own module imports resolve
    with nothing else configured.
    """
    for service_key in IMPLEMENTED_SERVICES:
        app = _load(service_key)
        assert app.openapi_url == "/openapi.json"
        assert app.docs_url == "/docs"
        assert app.redoc_url == "/redoc"


def test_every_implemented_service_generates_a_valid_openapi_document() -> None:
    """The aggregate OpenAPI gate (3-day plan §3.5)."""
    problems: List[str] = []
    for service_key in IMPLEMENTED_SERVICES:
        schema = _load(service_key).openapi()
        assert schema["openapi"].startswith("3.1"), service_key + " is not OpenAPI 3.1"
        problems.extend(check_document(schema, service=service_key, expected_paths=["/health", "/readiness"]))
    assert not problems, "OpenAPI contract violations:\n  " + "\n  ".join(problems)


def test_operation_ids_are_globally_unique_across_services() -> None:
    """A collision would make two different operations indistinguishable to any generator."""
    seen: Dict[str, str] = {}
    for service_key in IMPLEMENTED_SERVICES:
        for path, item in _load(service_key).openapi()["paths"].items():
            for method, operation in item.items():
                if not isinstance(operation, dict):
                    continue
                operation_id = operation.get("operationId")
                if not operation_id:
                    continue
                previous = seen.get(operation_id)
                assert previous is None, (
                    "operationId "
                    + operation_id
                    + " is used by both "
                    + str(previous)
                    + " and "
                    + service_key
                    + " ("
                    + method.upper()
                    + " "
                    + path
                    + ")"
                )
                seen[operation_id] = service_key


def test_every_service_binds_loopback_by_omission() -> None:
    """E-2, checked across the whole topology rather than one service at a time."""
    for service_key in SERVICE_REGISTRY:
        assert load_settings(service_key, env={}).host == "127.0.0.1", service_key + " widens its default bind"


def test_only_the_bff_is_declared_a_public_ingress() -> None:
    """E-1. The registry is the single source the deployment-manifest check reads."""
    public = sorted(key for key, service in SERVICE_REGISTRY.items() if service.public_ingress)
    assert public == ["bff"]


def test_no_service_imports_the_retired_architecture() -> None:
    """D-46 category D: the flat legacy packages are not ported and not reached.

    import-linter enforces this too. It is repeated here because the two mechanisms fail
    differently: import-linter needs its contract to be present and correct, and this needs
    only the source to be present.
    """
    retired = (
        "api_gateway",
        "auth_router",
        "database_router.",
        "control_plane.",
        "import_service.",
        "lineage_service",
        "deployment",
    )
    for path in sorted(_PACKAGE_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: List[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            for name in names:
                for forbidden in retired:
                    assert not name.startswith(forbidden), str(path) + " imports retired module " + name


def test_no_service_module_is_named_after_the_retired_gateway() -> None:
    for path in sorted(_PACKAGE_ROOT.rglob("*.py")):
        assert "gateway" not in path.name.casefold(), str(path) + " is named after the retired architecture"
    for directory in sorted(_PACKAGE_ROOT.rglob("*")):
        if directory.is_dir():
            assert "gateway" not in directory.name.casefold(), str(directory) + " is named after the retired architecture"


def test_uvicorn_is_imported_by_services_not_by_a_shared_runtime_module() -> None:
    """IC-013 §21 explicitly does NOT mandate a shared uvicorn runtime module.

    A service-level ``import uvicorn`` is permitted and is what the approved simple startup
    convention looks like. What would be a departure is the *opposite*: a shared runtime
    module every service is required to route through. This asserts the shared foundation
    contains no such module.
    """
    shared = _PACKAGE_ROOT / "shared"
    for path in sorted(shared.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "uvicorn", "shared/" + path.name + " constructs the ASGI server"

    for service_key in IMPLEMENTED_SERVICES:
        source = (_PACKAGE_ROOT / "services" / service_key / "main.py").read_text(encoding="utf-8")
        assert "import uvicorn" in source, service_key + " cannot start independently"
        assert 'if __name__ == "__main__":' in source, service_key + " has no local-development entry point"


def test_no_service_enables_reload_by_default() -> None:
    """E-4: reload is local-development only, and never what happens by omission."""
    for service_key in SERVICE_REGISTRY:
        assert load_settings(service_key, env={}).reload is False, service_key + " defaults reload on"

    for service_key in IMPLEMENTED_SERVICES:
        source = (_PACKAGE_ROOT / "services" / service_key / "main.py").read_text(encoding="utf-8")
        assert "reload=True" not in source, service_key + " hard-codes reload on"
        assert "reload=settings.reload" in source, service_key + " does not take reload from configuration"


def test_no_service_hard_codes_a_wildcard_bind() -> None:
    """E-2/E-7: the Option A §4 sample using host="0.0.0.0" must not be copied as written."""
    for service_key in IMPLEMENTED_SERVICES:
        source = (_PACKAGE_ROOT / "services" / service_key / "main.py").read_text(encoding="utf-8")
        assert '"0.0.0.0"' not in source, service_key + " hard-codes a wildcard bind"
        assert "host=settings.host" in source, service_key + " does not take its bind from configuration"
