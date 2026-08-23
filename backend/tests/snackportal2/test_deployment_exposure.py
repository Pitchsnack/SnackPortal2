"""IC-013 §21.1 E-6 — the deployment-manifest exposure check, and the zero-Gateway census.

**Why this file has to exist at all.** E-1 (only the BFF is a public ingress) and E-3 (internal
services publish no port) are violated by *configuration*, not by code. A service can be
perfectly written, bind loopback by default, and still be exposed to the internet by one line in
a compose file. No application-layer test can see that. So the acceptance set includes a check
that reads the manifests themselves.

The check is scoped to **application** services. The word in E-1 is "public *application*
ingress", and the plan says "exactly one public application service → BFF". A local PostgreSQL
fixture publishing 5432 to 127.0.0.1 is a database, not an application service, and treating it
as a violation would make the check cry wolf until someone switched it off.

Compose files are parsed with a small indentation scanner rather than a YAML library, because
the repository's test suite is stdlib-only and adding a parser dependency to satisfy one check is
a poor trade. The scanner is self-tested against a planted violation below, so it cannot pass by
failing to parse anything.

Pure stdlib. Runnable standalone:  python tests/snackportal2/test_deployment_exposure.py
"""

from __future__ import annotations

import pathlib
import re
from typing import Dict, List

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BACKEND = _REPO_ROOT / "backend"
_REBUILD = _BACKEND / "snackportal2"

#: The compose file that describes the Option A rebuild's container topology.
_REBUILD_COMPOSE = _REPO_ROOT / "infrastructure" / "docker" / "docker-compose.rebuild.yml"

#: Compose services that are databases or other infrastructure, not application services. Matched
#: by name so a new application service cannot be excluded by accident.
_INFRASTRUCTURE_SERVICE = re.compile(r"(postgres|redis|minio|mailhog|keycloak|jaeger|prometheus)", re.IGNORECASE)


def parse_compose_publishing(text: str) -> Dict[str, bool]:
    """Return ``{service_name: publishes_a_port}`` for one compose document.

    Deliberately small. It finds the ``services:`` mapping, treats each key at the next
    indentation level as a service, and records whether that service's block contains a ``ports:``
    key. ``expose:`` is *not* publishing — it declares container-network reachability only, which
    is exactly what E-3 permits.
    """
    lines = text.splitlines()
    services: Dict[str, bool] = {}

    in_services = False
    service_indent: int | None = None
    current: str | None = None

    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())

        if not in_services:
            if indent == 0 and stripped == "services:":
                in_services = True
            continue

        # A new top-level key ends the services mapping.
        if indent == 0:
            in_services = False
            current = None
            continue

        if service_indent is None:
            service_indent = indent

        if indent == service_indent and stripped.endswith(":"):
            current = stripped[:-1].strip()
            services.setdefault(current, False)
            continue

        if current is not None and stripped.startswith("ports:"):
            services[current] = True

    return services


def application_services(published: Dict[str, bool]) -> Dict[str, bool]:
    """Drop database and other infrastructure services from the census."""
    return {name: publishes for name, publishes in published.items() if not _INFRASTRUCTURE_SERVICE.search(name)}


# --- E-6: exactly one application service publishes, and it is the BFF ---------------------------

def test_the_rebuild_compose_file_exists() -> None:
    """A missing manifest would make every check below pass vacuously."""
    assert _REBUILD_COMPOSE.exists(), "the rebuild compose file is missing; the exposure check proves nothing"


def test_exactly_one_application_service_publishes_a_port_and_it_is_the_bff() -> None:
    published = application_services(parse_compose_publishing(_REBUILD_COMPOSE.read_text(encoding="utf-8")))
    assert len(published) >= 14, "expected the fourteen services in the census, found " + repr(sorted(published))

    publishers = sorted(name for name, publishes in published.items() if publishes)
    assert publishers == ["bff"], "expected only the BFF to publish a port, found " + repr(publishers)


def test_the_access_control_service_publishes_nothing() -> None:
    """Named separately because it is the most consequential one to get wrong.

    A directly-reachable authorizer can be asked for a decision that no BFF flow ever requested.
    """
    published = parse_compose_publishing(_REBUILD_COMPOSE.read_text(encoding="utf-8"))
    assert published.get("access-control") is False, "the Access Control Service publishes a port"


def test_every_internal_service_is_present_in_the_manifest() -> None:
    """A service absent from the manifest is not compliant — it is simply undeployed and unchecked."""
    from snackportal2.shared.config import SERVICE_REGISTRY

    published = parse_compose_publishing(_REBUILD_COMPOSE.read_text(encoding="utf-8"))
    compose_names = {name.replace("-", "_") for name in published}
    missing = sorted(set(SERVICE_REGISTRY) - compose_names)
    assert missing == [], "services missing from the deployment manifest: " + repr(missing)


def test_no_other_compose_file_publishes_an_application_service() -> None:
    """The legacy local fixture publishes PostgreSQL ports, which is not an application ingress."""
    for compose in sorted((_REPO_ROOT / "infrastructure" / "docker").glob("*.yml")):
        published = application_services(parse_compose_publishing(compose.read_text(encoding="utf-8")))
        publishers = sorted(name for name, publishes in published.items() if publishes)
        assert publishers in ([], ["bff"]), compose.name + " publishes application services " + repr(publishers)


def test_the_manifest_scanner_detects_a_planted_violation() -> None:
    """Non-vacuity. A parser that silently found nothing would make every check above green."""
    planted = """
name: probe

services:
  bff:
    image: x
    ports:
      - "8000:8000"
  access-control:
    image: x
    ports:
      - "8002:8002"
  audit:
    image: x
    expose:
      - "8013"
"""
    published = parse_compose_publishing(planted)
    assert published == {"bff": True, "access-control": True, "audit": False}

    publishers = sorted(name for name, publishes in application_services(published).items() if publishes)
    assert publishers == ["access-control", "bff"], "the scanner missed the planted publish"

    # And the real check would fail on it.
    assert publishers != ["bff"]


def test_expose_is_not_treated_as_publish() -> None:
    """E-3 permits container-network reachability. Conflating the two would cry wolf."""
    text = _REBUILD_COMPOSE.read_text(encoding="utf-8")
    assert text.count("expose:") >= 13, "internal services should declare expose, not ports"
    published = parse_compose_publishing(text)
    assert published["authentication"] is False
    assert published["database-router"] is False


def test_no_source_default_binds_a_wildcard_interface() -> None:
    """E-2: `0.0.0.0` is never what happens by omission, in any service's code."""
    from snackportal2.shared.config import SERVICE_REGISTRY, load_settings

    for service_key in SERVICE_REGISTRY:
        assert load_settings(service_key, env={}).host == "127.0.0.1", service_key + " widens its default bind"

    for path in sorted(_REBUILD.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if 'host="0.0.0.0"' in text:
            raise AssertionError(str(path) + " hard-codes a wildcard bind in source")


def test_reload_is_never_enabled_outside_a_local_development_path() -> None:
    """E-4. The compose file is a shared environment; `--reload` must not appear in it."""
    text = _REBUILD_COMPOSE.read_text(encoding="utf-8")
    assert "--reload" not in text and "reload=True" not in text, "reload is enabled in a container manifest"

    for path in sorted(_REBUILD.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        assert "reload=True" not in path.read_text(encoding="utf-8"), str(path) + " hard-codes reload on"


# --- Day 3.7: the zero-Gateway census --------------------------------------------------------------

#: Tokens that would indicate the retired architecture in the NEW runtime. Historical mentions in
#: documentation and in the legacy packages are deliberately out of scope: D-46 keeps them as the
#: historical record, and rewriting history to make a string count reach zero would be dishonest
#: about what the system used to be.
_GATEWAY_TOKENS = ("api_gateway", "http_gateway", "gateway_edge", "apigateway")


def test_the_new_runtime_contains_no_gateway_identifier() -> None:
    """Scoped to code, not prose — deliberately.

    The plan is explicit: "Do not rewrite history merely to make string counts zero." The
    rebuild's own docstrings *name* the retired packages, because saying which packages must not
    be imported is how the boundary is explained to the next reader. A blanket text search would
    force those explanations to be deleted, which would make the count zero and the codebase
    worse.

    So this walks the AST and checks the things that would constitute an actual dependency:
    imports, identifiers, attribute names, route paths, and configuration string constants.
    Docstrings and comments are out of scope, and the separate module- and directory-name check
    below covers naming.
    """
    import ast

    for path in sorted(_REBUILD.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))

        for node in ast.walk(tree):
            names: List[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names = [node.name]
            elif isinstance(node, ast.Name):
                names = [node.id]
            elif isinstance(node, ast.Attribute):
                names = [node.attr]
            for name in names:
                folded = name.casefold()
                for token in _GATEWAY_TOKENS + ("gateway",):
                    assert token not in folded, str(path) + " uses the identifier " + name

        # Route paths and upper-case configuration constants — the string literals that would
        # make a gateway a runtime dependency rather than a historical mention.
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
                if any(target.isupper() for target in targets) and isinstance(node.value, ast.Constant):
                    value = node.value.value
                    if isinstance(value, str):
                        for token in _GATEWAY_TOKENS + ("gateway",):
                            assert token not in value.casefold(), str(path) + " configures " + repr(value)
            if isinstance(node, ast.Call):
                for argument in node.args:
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str) and argument.value.startswith("/"):
                        assert "gateway" not in argument.value.casefold(), str(path) + " routes " + argument.value


def test_no_new_runtime_module_or_directory_is_named_after_the_gateway() -> None:
    for path in sorted(_REBUILD.rglob("*")):
        assert "gateway" not in path.name.casefold(), str(path) + " is named after the retired architecture"


def test_the_rebuild_deployment_manifest_declares_no_gateway_process() -> None:
    """0 Gateway runtime, process, port, launcher, compatibility layer or config dependency.

    A manifest is configuration end to end, so here the blanket text search IS the right check:
    there is no prose in it that needs to name the retired architecture.
    """
    folded = _REBUILD_COMPOSE.read_text(encoding="utf-8").casefold()
    assert "gateway" not in folded, "the rebuild deployment manifest references a gateway"


def test_the_bff_exposes_no_generic_proxy_route() -> None:
    """A catch-all path would make the surface grow by configuration instead of by contract."""
    from snackportal2.services.bff import main as bff_main

    for path in bff_main.app.openapi()["paths"]:
        assert "{path" not in path, "the BFF exposes a catch-all route: " + path
        assert not path.endswith("/{proxy}"), "the BFF exposes a proxy route: " + path
        assert ":path" not in path, "the BFF exposes a wildcard path route: " + path


def test_the_retired_gateway_package_is_still_on_disk_and_untouched() -> None:
    """D-46 keeps it as the historical record. Its absence would be a different violation.

    The census is about the new runtime being Gateway-free, not about erasing what the system
    used to be. If this ever fails, someone deleted history to make a count look better.
    """
    assert (_BACKEND / "api_gateway").is_dir(), "the retired api_gateway package was deleted"


def _self_test() -> None:
    test_the_rebuild_compose_file_exists()
    test_exactly_one_application_service_publishes_a_port_and_it_is_the_bff()
    test_the_access_control_service_publishes_nothing()
    test_every_internal_service_is_present_in_the_manifest()
    test_no_other_compose_file_publishes_an_application_service()
    test_the_manifest_scanner_detects_a_planted_violation()
    test_expose_is_not_treated_as_publish()
    test_no_source_default_binds_a_wildcard_interface()
    test_reload_is_never_enabled_outside_a_local_development_path()
    test_the_new_runtime_contains_no_gateway_identifier()
    test_no_new_runtime_module_or_directory_is_named_after_the_gateway()
    test_the_rebuild_deployment_manifest_declares_no_gateway_process()
    test_the_retired_gateway_package_is_still_on_disk_and_untouched()
    print("deployment exposure + zero-Gateway census: PASS")


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(_BACKEND))
    _self_test()


__all__ = ["application_services", "parse_compose_publishing"]

