"""Stage 4G/4H/4I — the standing gates, re-run against a live-PostgreSQL configuration.

The default suite already runs the OpenAPI contract gate, the deployment-exposure gate and the
zero-Gateway census — but it runs them against services composed with **no** storage configured.
That leaves one question open, and it is the question Stage 4 exists to answer: does configuring
real PostgreSQL change what the services publish?

It must not. A contract that shifts when a database is attached is not a contract. So this
module regenerates all fourteen OpenAPI documents in a subprocess carrying the full Stage 4
environment — real Control DSN, real router URLs, real grant credentials, PostgreSQL storage
selected on every domain service — and requires them to be **byte-identical** to the documents
the unconfigured process produces, and to satisfy every standing rule in both.

It also proves the Stage 4 harness's own containment: exactly one file under this package may
touch the database driver.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

from .. import _openapi_rules
from . import _stage4_pg as pg
from . import _stage4_servers as srv

pytestmark = pytest.mark.skipif(not pg.configured(), reason=pg.SKIP_REASON)

#: The fourteen services, in registry order.
SERVICES = tuple(srv.SERVICE_MODULE)

#: A full production-shaped configuration: every storage selector on, every internal URL set.
#: The URLs are unreachable on purpose — the document must not depend on a dependency being up.
_UNREACHABLE = "http://127.0.0.1:9"


def _live_environment() -> Dict[str, str]:
    env: Dict[str, str] = {
        "SP2_CONTROL_PLANE_DSN": pg.dsn("control"),
        "SP2_AUDIT_DSN": pg.dsn("control"),
        "SP2_AUDIT_CREDENTIALS": json.dumps({"k": {"emitter_ref": "bff", "scopes": ["audit:write"]}}),
        "SP2_AUTHENTICATION_STATIC_PRINCIPALS": json.dumps({"t": {"principal_ref": "p", "role": "TENANT_AGENT", "active_tenant": "acme"}}),
        "SP2_ACCESS_CONTROL_CONTROL_PLANE_URL": _UNREACHABLE,
        "SP2_ACCESS_CONTROL_SERVICE_CREDENTIAL": "c",
        "SP2_DATABASE_ROUTER_CONTROL_PLANE_URL": _UNREACHABLE,
        "SP2_DATABASE_ROUTER_SERVICE_CREDENTIAL": "c",
        "SP2_DATABASE_ROUTER_GRANTEES": json.dumps({"c": "startups"}),
        "SP2_IMPORT_SERVICE_CONTROL_PLANE_URL": _UNREACHABLE,
        "SP2_IMPORT_SERVICE_SERVICE_CREDENTIAL": "c",
        "SP2_BFF_SERVICE_CREDENTIAL": "c",
        "SP2_BFF_BASE_DOMAIN": "snackportal2.example",
    }
    for service in ("startups", "investors", "deals", "lineage"):
        prefix = "SP2_" + service.upper()
        env[prefix + "_STORAGE"] = "postgres"
        env[prefix + "_DATABASE_ROUTER_URL"] = _UNREACHABLE
        env[prefix + "_SERVICE_CREDENTIAL"] = "c"
    for name in (
        "AUTHENTICATION",
        "ACCESS_CONTROL",
        "DATABASE_ROUTER",
        "CONTROL_PLANE",
        "AUDIT",
        "STARTUPS",
        "INVESTORS",
        "DEALS",
        "LINEAGE",
        "IMPORT_SERVICE",
    ):
        env["SP2_BFF_" + name + "_URL"] = _UNREACHABLE
    return env


_GENERATOR = """
import json, sys
from snackportal2.shared.config import SERVICE_REGISTRY
from importlib import import_module

documents = {}
for key in SERVICE_REGISTRY:
    module = import_module("snackportal2.services." + key + ".main")
    documents[key] = module.app.openapi()
sys.stdout.write(json.dumps(documents, sort_keys=True))
"""


def _documents(extra_env: Dict[str, str]) -> Dict[str, Any]:
    """Generate all fourteen documents in a fresh process under the supplied environment.

    A subprocess, because each service composes its adapters at import time: changing the
    environment inside this process after the modules are imported would prove nothing.
    """
    import os

    child = {name: value for name, value in os.environ.items() if not name.startswith("SP2_")}
    child["PYTHONPATH"] = str(pg.BACKEND_ROOT)
    child.update(extra_env)
    completed = subprocess.run(
        [sys.executable, "-c", _GENERATOR],
        cwd=str(pg.BACKEND_ROOT),
        env=child,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert completed.returncode == 0, "document generation failed:\n" + completed.stderr[-4000:]
    return dict(json.loads(completed.stdout))


@pytest.fixture(scope="module")
def unconfigured() -> Dict[str, Any]:
    return _documents({})


@pytest.fixture(scope="module")
def configured() -> Dict[str, Any]:
    return _documents(_live_environment())


# --- Stage 4G: the OpenAPI contract gate, under live configuration --------------------------


def test_all_fourteen_services_generate_a_document_under_live_configuration(configured: Dict[str, Any]) -> None:
    assert set(configured) == set(SERVICES)
    assert len(configured) == 14


@pytest.mark.parametrize("service", SERVICES)
def test_every_document_is_openapi_31_with_an_explicit_title_and_version(configured: Dict[str, Any], service: str) -> None:
    document = configured[service]
    assert str(document["openapi"]).startswith("3.1"), service + " -> " + str(document["openapi"])
    assert document["info"]["title"].startswith("SnackPortal2 ")
    assert document["info"]["version"] and document["info"]["version"] != "0.1.0"


@pytest.mark.parametrize("service", SERVICES)
def test_every_document_satisfies_every_standing_rule_under_live_configuration(configured: Dict[str, Any], service: str) -> None:
    """The same validator the default suite uses, applied to the live-configured document."""
    problems = _openapi_rules.check_document(configured[service], service=service)
    assert not problems, "\n  ".join(problems)


@pytest.mark.parametrize("service", SERVICES)
def test_configuring_postgresql_changes_no_published_contract(
    unconfigured: Dict[str, Any], configured: Dict[str, Any], service: str
) -> None:
    """§9's central requirement: a contract that shifts when a database is attached is not one.

    Compared as canonical JSON, so a reordered key is not a difference and a changed schema is.
    """
    before = json.dumps(unconfigured[service], sort_keys=True)
    after = json.dumps(configured[service], sort_keys=True)
    assert before == after, service + "'s OpenAPI document changed when PostgreSQL was configured"


@pytest.mark.parametrize("service", SERVICES)
def test_no_success_response_regresses_to_an_empty_schema(configured: Dict[str, Any], service: str) -> None:
    """§0.1, stated as its own check because it is the specific regression the brief names."""
    for path, item in configured[service]["paths"].items():
        for method, operation in item.items():
            if not isinstance(operation, dict) or "operationId" not in operation:
                continue
            for status, response in operation.get("responses", {}).items():
                if not str(status).startswith("2") or str(status) == "204":
                    continue
                content = response.get("content") or {}
                assert content, service + " " + method.upper() + " " + path + " " + str(status) + " has no content"
                for media in content.values():
                    assert media.get("schema"), service + " " + method.upper() + " " + path + " " + str(status) + " has an empty schema"


def test_operation_ids_are_globally_unique_across_all_fourteen_documents(configured: Dict[str, Any]) -> None:
    seen: Dict[str, str] = {}
    for service, document in configured.items():
        for item in document["paths"].values():
            for operation in item.values():
                if not isinstance(operation, dict) or "operationId" not in operation:
                    continue
                identifier = str(operation["operationId"])
                assert identifier not in seen, identifier + " is used by both " + seen[identifier] + " and " + service
                seen[identifier] = service
    assert len(seen) >= 14


def test_the_bff_publishes_a_client_security_scheme_and_internal_services_publish_theirs(
    configured: Dict[str, Any],
) -> None:
    bff_schemes = set(configured["bff"]["components"].get("securitySchemes", {}))
    assert "ClientBearer" in bff_schemes, bff_schemes

    for service in SERVICES:
        if service == "bff":
            continue
        schemes = set(configured[service]["components"].get("securitySchemes", {}))
        if any(
            "operationId" in operation
            for item in configured[service]["paths"].values()
            for operation in item.values()
            if isinstance(operation, dict) and operation.get("security")
        ):
            assert "InternalServiceBearer" in schemes, service + " -> " + repr(schemes)


def test_health_and_readiness_stay_public_on_every_service(configured: Dict[str, Any]) -> None:
    for service, document in configured.items():
        for path in ("/health", "/readiness"):
            operation = document["paths"][path]["get"]
            assert not operation.get("security"), service + path + " requires authentication"


# --- Stage 4H: exposure, under live configuration --------------------------------------------


def test_only_the_bff_is_a_public_ingress_in_the_live_registry() -> None:
    from snackportal2.shared.config import PUBLIC_INGRESS_SERVICE, SERVICE_REGISTRY

    public = [key for key, descriptor in SERVICE_REGISTRY.items() if descriptor.public_ingress]
    assert public == ["bff"] == [PUBLIC_INGRESS_SERVICE]
    assert len(SERVICE_REGISTRY) == 14


def test_every_service_binds_loopback_by_omission_even_with_postgresql_configured() -> None:
    """E-2 is a property of omission, and configuring storage must not disturb it."""
    from snackportal2.shared.config import SERVICE_REGISTRY, load_settings

    for key in SERVICE_REGISTRY:
        settings = load_settings(key, env=_live_environment())
        assert settings.host == "127.0.0.1", key + " binds " + settings.host
        assert settings.reload is False, key + " enables reload"
        assert settings.access_log is False
        assert settings.server_header is False
        assert settings.proxy_headers is False


def test_the_stage4_postgresql_fixture_is_loopback_only() -> None:
    """§10 permits a local PostgreSQL fixture; it does not permit a publicly bound one."""
    from urllib.parse import urlsplit

    for name in ("control",) + tuple(pg.TENANTS):
        host = urlsplit(pg.dsn(name)).hostname or ""
        assert host in ("127.0.0.1", "localhost", "::1"), "the Stage 4 fixture is not loopback-only"


# --- Stage 4I: zero-Gateway, under live configuration ----------------------------------------


def test_no_live_configured_service_imports_the_retired_gateway(configured: Dict[str, Any]) -> None:
    """The census, re-run against the modules as they compose with PostgreSQL attached.

    An import that only happens on the PostgreSQL branch would be invisible to a census run
    against the unconfigured process, which is precisely the hole this closes.
    """
    import os

    probe = (
        "import json, sys\n"
        "from importlib import import_module\n"
        "from snackportal2.shared.config import SERVICE_REGISTRY\n"
        "for key in SERVICE_REGISTRY:\n"
        "    import_module('snackportal2.services.' + key + '.main')\n"
        "offending = sorted(name for name in sys.modules if name.split('.')[0] in "
        "('api_gateway', 'auth_router', 'database_router', 'control_plane', 'import_service', "
        "'lineage_service', 'deployment'))\n"
        "sys.stdout.write(json.dumps(offending))\n"
    )
    child = {name: value for name, value in os.environ.items() if not name.startswith("SP2_")}
    child["PYTHONPATH"] = str(pg.BACKEND_ROOT)
    child.update(_live_environment())
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(pg.BACKEND_ROOT),
        env=child,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert completed.returncode == 0, completed.stderr[-3000:]
    assert json.loads(completed.stdout) == [], "the live-configured rebuild imported the retired architecture"

    del configured


def test_no_service_document_mentions_a_gateway_route(configured: Dict[str, Any]) -> None:
    for service, document in configured.items():
        paths = " ".join(document["paths"])
        assert "gateway" not in paths.casefold(), service + " publishes a gateway-named path: " + paths
        assert "{path:path}" not in paths, service + " publishes a catch-all proxy route"


# --- the harness's own containment ------------------------------------------------------------


_DRIVER_ROOTS = ("psycopg", "psycopg2", "asyncpg", "sqlalchemy", "aiopg", "databases")


def _driver_references(source: str) -> Dict[str, str]:
    """Every way ``source`` could reach a database driver, found structurally.

    AST rather than substring, and not out of fastidiousness: a substring scan flags this very
    module for containing the names it searches for, and misses ``import  psycopg`` with two
    spaces. Both import forms and the ``importlib.import_module("…")`` escape hatch are
    covered, so neither route is a silent way in.
    """
    import ast

    found: Dict[str, str] = {}
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _DRIVER_ROOTS:
                    found[alias.name] = "import"
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in _DRIVER_ROOTS:
                found[str(node.module)] = "from-import"
        elif isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if name in ("import_module", "find_spec") and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    if first.value.split(".")[0] in _DRIVER_ROOTS:
                        found[first.value] = "importlib"
    return found


def test_only_the_stage4_fixture_module_reaches_the_database_driver() -> None:
    """The Driver Containment Standard, applied to this package rather than assumed of it.

    ``_stage4_pg.py`` resolves psycopg through ``importlib`` — the idiom the repository's
    existing live-PG harness uses, and the reason the production driver census in
    ``tests/architecture/test_vendor_and_db_containment.py`` does not have to be widened with a
    test path. This check keeps that true: no sibling module may acquire a driver, by either
    route.
    """
    package = Path(__file__).resolve().parent
    for module in sorted(package.glob("*.py")):
        references = _driver_references(module.read_text(encoding="utf-8"))
        if module.name == "_stage4_pg.py":
            assert references.get("psycopg") == "importlib", "the fixture no longer resolves the driver: " + repr(references)
            continue
        assert not references, module.name + " reaches the database driver directly: " + repr(references)


def test_the_driver_containment_check_detects_a_planted_reference() -> None:
    """The check above passes trivially if it cannot see anything; prove that it can."""
    assert _driver_references("import psycopg") == {"psycopg": "import"}
    assert _driver_references("import  psycopg as db") == {"psycopg": "import"}
    assert _driver_references("from psycopg.types.json import Jsonb") == {"psycopg.types.json": "from-import"}
    assert _driver_references("importlib.import_module('psycopg')") == {"psycopg": "importlib"}
    assert _driver_references("x = 'import psycopg'") == {}, "a string literal is not a driver reference"


def _literal_strings(source: str) -> Any:
    import ast

    return [node.value for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Constant) and isinstance(node.value, str)]


#: Reserved top-level domains that can never name a real host (RFC 2606 / RFC 6761).
_RESERVED_SUFFIXES = (".example", ".example.com", ".example.org", ".example.net", ".invalid", ".test", ".localhost")


def _is_unroutable_host(hostname: str) -> bool:
    """True when a hostname cannot possibly name a real database.

    Three ways to qualify: loopback; a bare single label, which is not a resolvable FQDN and is
    the idiom the negative fixtures use (``…@host/db``); or a reserved domain.
    """
    host = hostname.casefold()
    if host in ("127.0.0.1", "localhost", "::1"):
        return True
    if "." not in host:
        return True
    return host.endswith(_RESERVED_SUFFIXES)


def test_no_stage4_module_contains_a_hard_coded_database_credential() -> None:
    """§2: DSNs come from configuration, so no literal here may carry a real one.

    Semantic rather than textual: a string counts only when it *parses* as a DSN with a
    netloc, which is why this file's own search terms are not flagged. Two rules then apply —
    a literal DSN must point at loopback, and it must contain no part of a configured Stage 4
    credential. Deliberately-broken loopback DSNs (an unreachable port with a placeholder
    user) are exactly what the fail-closed tests need, and are not a leak.
    """
    from urllib.parse import urlsplit

    fragments = srv.dsn_secret_fragments()
    assert fragments, "the leakage check needs configured DSNs to compare against"

    package = Path(__file__).resolve().parent
    for module in sorted(package.glob("*.py")):
        source = module.read_text(encoding="utf-8")
        for fragment in fragments:
            assert fragment not in source, module.name + " contains part of a configured Stage 4 credential"
        for literal in _literal_strings(source):
            parts = urlsplit(literal)
            if parts.scheme not in ("postgres", "postgresql") or not parts.netloc:
                continue
            assert _is_unroutable_host(parts.hostname or ""), (
                module.name + " contains a DSN naming a host that could be real: " + repr(parts.hostname)
            )


def test_the_credential_check_detects_a_planted_dsn() -> None:
    from urllib.parse import urlsplit

    # Assembled rather than written as one literal: a whole DSN literal here would be caught by
    # the very check it exists to exercise, which is the check working correctly.
    planted = urlsplit("postgresql://" + "user:hunter2@" + "db.prod.internal:5432/prod")
    assert planted.password == "hunter2"
    assert not _is_unroutable_host(planted.hostname or ""), "a routable host must be rejected"
    # ...while the negative fixtures the suite legitimately needs are accepted.
    for allowed in ("127.0.0.1", "localhost", "host", "db.example.com", "tenant.invalid"):
        assert _is_unroutable_host(allowed), allowed
    # ...and the literals this file searches with are not DSNs, which is why it is clean.
    assert not urlsplit("postgres://").netloc
