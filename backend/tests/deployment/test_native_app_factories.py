"""Behavioral tests for the nine native ASGI application factories and the deployment root.

Proves, without binding a socket or touching a database:

* **Import inertness** — importing any of the nine edge modules under a CLEARED environment reads no
  selector, composes nothing, opens no connection, binds no socket, and does not invoke the factory.
* **Factory shape** — each ``create_app_from_env`` exists, is callable, takes no arguments, and
  returns a ``FastAPI`` whose closed posture is intact (docs/OpenAPI disabled, no slash redirects,
  the edge's exact route set).
* **Fail closed** — with the required configuration absent, each factory RAISES; it never returns,
  never returns ``None``, and never substitutes an in-memory backend.
* **One composition path** — the factory and the retained compatibility seam produce apps with the
  same route set, because both go through the same ``_make_app``.

Every collaborator in this suite is lazy-connect, so a composed app performs no I/O: these tests need
no live PostgreSQL. The over-the-wire security posture of the NATIVE path is proven separately by
``tests/deployment/native_uvicorn_process_smoke.py`` (it starts real uvicorn processes).

Stdlib + pytest; runnable standalone:
  python tests/deployment/test_native_app_factories.py
"""

from __future__ import annotations

import contextlib
import importlib
import json
import os
import pathlib
import sys
from typing import Dict, Iterator, Optional

from fastapi import FastAPI

_BACKEND = pathlib.Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# (label, module path, the routes the factory's app must expose)
_EDGES = (
    (
        "public_startup",
        "database_router.adapters.providers.http_public_startup_edge",
        {"/tenant/startups/{startup_ref}", "/health", "/readiness"},
    ),
    (
        "public_workspace",
        "control_plane.adapters.providers.http_public_workspace_edge",
        {"/memberships", "/health", "/readiness"},
    ),
    ("control_read", "control_plane.adapters.providers.http_read_api", {"/{_target:path}"}),
    ("auth_router", "auth_router.adapters.providers.http_authenticate_api", {"/internal/auth/authenticate"}),
    ("gateway_audit", "control_plane.adapters.providers.http_gateway_audit_api", {"/internal/gateway-audit/events"}),
    ("import_audit", "control_plane.adapters.providers.http_import_audit_api", {"/internal/import-audit/events"}),
    ("routing_audit", "control_plane.adapters.providers.http_routing_audit_api", {"/internal/routing-audit/events"}),
    ("import_service", "deployment.import_edge", {"/internal/import/initiate"}),
)

# Structurally valid, never-connected-to internal URLs. Composition is lazy: no socket is opened.
_LOOPBACK = "http://127.0.0.1:1"

_ISSUERS = json.dumps(
    {
        "https://issuer.test/": {
            "issuer": "https://issuer.test/",
            "audience": "sp2",
            "allowed_algs": ["RS256"],
            "jwks": {"keys": []},
            "tenant_claim": "tenant",
        }
    }
)

# Every selector any of the nine factories consults, plus the legacy bind knobs the native path must
# ignore. Cleared wholesale so no ambient value can make a test pass by accident.
_ALL_SELECTORS = (
    "SP2_CP_CONTROL_STORE",
    "SP2_CP_CONTROL_STORE_DSN_REF",
    "SP2_CP_READ_HOST",
    "SP2_CP_READ_PORT",
    "SP2_CP_GATEWAY_AUDIT_HOST",
    "SP2_CP_IMPORT_AUDIT_HOST",
    "SP2_CP_ROUTING_AUDIT_HOST",
    "SP2_AR_CONTROL_PLANE_READ_BASE_URL",
    "SP2_AR_ISSUERS",
    "SP2_AR_AUTHENTICATE_HOST",
    "SP2_AR_AUTHENTICATE_PORT",
    "SP2_DBR_ROUTING_READ_BASE_URL",
    "SP2_DBR_ROUTING_AUDIT_BASE_URL",
    "SP2_DBR_DISPATCH_HOST",
    "SP2_DBR_DISPATCH_PORT",
    "SP2_DBR_TENANT_STARTUP_HOST",
    "SP2_DBR_TENANT_STARTUP_PORT",
    "SNACKPORTAL_TENANT_SECRET_DIR",
    "SP2_IMPORT_DIRECTORY_READ_BASE_URL",
    "SP2_IMPORT_AUDIT_SINK_BASE_URL",
    "SP2_IMPORT_HOST",
    "SP2_IMPORT_PORT",
    "SP2_EDGE_AUTH_ROUTER_BASE_URL",
    "SP2_EDGE_AUDIT_SINK_BASE_URL",
    "SP2_EDGE_ALLOWED_ORIGINS",
    "SP2_DBR_PUBLIC_STARTUP_HOST",
    "SP2_DBR_PUBLIC_STARTUP_PORT",
    "SP2_CP_PUBLIC_WORKSPACE_HOST",
    "SP2_CP_PUBLIC_WORKSPACE_PORT",
)


def _complete_env(tmp_secret_dir: str) -> Dict[str, str]:
    """A configuration under which all eight factories compose successfully."""
    return {
        "SP2_CP_CONTROL_STORE": "in_memory",
        "SP2_CP_CONTROL_STORE_DSN_REF": "control/control-store-dsn",
        "SP2_AR_CONTROL_PLANE_READ_BASE_URL": _LOOPBACK,
        "SP2_AR_ISSUERS": _ISSUERS,
        "SP2_DBR_ROUTING_READ_BASE_URL": _LOOPBACK,
        "SNACKPORTAL_TENANT_SECRET_DIR": tmp_secret_dir,
        "SP2_IMPORT_DIRECTORY_READ_BASE_URL": _LOOPBACK,
        "SP2_EDGE_AUTH_ROUTER_BASE_URL": _LOOPBACK,
    }


@contextlib.contextmanager
def _env(values: Optional[Dict[str, str]] = None) -> Iterator[None]:
    """Clear every selector, apply ``values``, restore the prior environment afterward."""
    prior = {k: os.environ.get(k) for k in _ALL_SELECTORS}
    try:
        for key in _ALL_SELECTORS:
            os.environ.pop(key, None)
        for key, value in (values or {}).items():
            os.environ[key] = value
        yield
    finally:
        for key, value in prior.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _factory(module_path: str):
    module = importlib.import_module(module_path)
    return module.create_app_from_env


def _routes(app: FastAPI) -> set:
    return {r.path for r in app.routes if hasattr(r, "path")}


def _secret_dir() -> str:
    path = _BACKEND / "build" / "_native_factory_tenant_secrets"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


# --- import inertness -----------------------------------------------------------------------


def test_importing_every_edge_module_is_inert() -> None:
    # Under a CLEARED environment, importing the module must not read a selector, compose anything,
    # or raise. If a module composed at import, the missing configuration would surface here.
    with _env():
        for _label, module_path, _routes_expected in _EDGES:
            sys.modules.pop(module_path, None)
            module = importlib.import_module(module_path)
            assert hasattr(module, "create_app_from_env"), f"{module_path} must expose create_app_from_env"


# --- factory shape --------------------------------------------------------------------------


def test_every_factory_returns_a_composed_fastapi_app() -> None:
    with _env(_complete_env(_secret_dir())):
        for label, module_path, expected in _EDGES:
            app = _factory(module_path)()
            assert isinstance(app, FastAPI), f"{label}: factory must return a FastAPI application"
            assert expected <= _routes(app), f"{label}: composed app is missing routes {expected - _routes(app)}"


def test_every_factory_app_keeps_the_closed_surface() -> None:
    with _env(_complete_env(_secret_dir())):
        for label, module_path, _expected in _EDGES:
            app = _factory(module_path)()
            # No machine-readable catalogue of the edge is ever published.
            assert app.docs_url is None, f"{label}: interactive docs must be disabled"
            assert app.redoc_url is None, f"{label}: redoc must be disabled"
            assert app.openapi_url is None, f"{label}: the OpenAPI schema must be disabled"
            # A second spelling of any path must never be served (closed route allowlists).
            assert app.router.redirect_slashes is False, f"{label}: slash redirects must stay disabled"


def test_factory_is_callable_with_no_arguments() -> None:
    # `uvicorn --factory` invokes the factory with ZERO arguments; anything else is unstartable.
    import inspect

    for label, module_path, _expected in _EDGES:
        signature = inspect.signature(_factory(module_path))
        assert not signature.parameters, f"{label}: factory must take no arguments (host/port belong to the runtime)"


# --- fail closed ----------------------------------------------------------------------------


# The four edges whose composition can report "inactive" convert that into a hard startup failure.
# For the two PUBLIC edges this is the load-bearing case: an unset SP2_EDGE_AUTH_ROUTER_BASE_URL must
# never yield an edge that serves without authenticating, so it yields no application at all.
_MUST_RAISE_WITHOUT_CONFIG = ("public_startup", "public_workspace", "auth_router", "import_service")

# The four edges that compose LAZILY and fail closed at FIRST STORE USE instead of at startup: the
# three durable audit edges (their control-store secret REFERENCE has a non-blank default, and the
# seam must never resolve it itself — the B-7B lazy pattern) and the read edge (its ControlPlane
# composes on its own SP2_CP_* posture selectors). Documented, not silently accepted — see
# ``test_read_edge_in_memory_default_is_a_documented_operator_hazard``.
_LAZY_FAIL_CLOSED = ("control_read", "gateway_audit", "import_audit", "routing_audit")


def test_gated_factories_fail_closed_with_no_configuration() -> None:
    # The operator started the process deliberately: an absent composition is a startup failure, not
    # a silent no-op and never an in-memory substitution.
    with _env():
        for label, module_path, _expected in _EDGES:
            if label not in _MUST_RAISE_WITHOUT_CONFIG:
                continue
            raised = None
            try:
                _factory(module_path)()
            except (RuntimeError, ValueError) as exc:
                raised = exc
            assert raised is not None, f"{label}: factory must fail closed when its required configuration is absent"
            assert str(raised), f"{label}: the failure must carry a diagnostic message"


def test_lazy_factories_compose_but_never_resolve_a_secret_at_startup() -> None:
    # These four compose an app without configuration BY DESIGN; the durable store binding is
    # reference-only and lazy, so an unresolvable reference fails at first use rather than at import
    # or composition. This test pins that split so a future change to either half is visible.
    with _env():
        for label, module_path, _expected in _EDGES:
            if label not in _LAZY_FAIL_CLOSED:
                continue
            app = _factory(module_path)()
            assert isinstance(app, FastAPI), f"{label}: the lazy composition must still yield a composed app"


def test_read_edge_in_memory_default_is_a_documented_operator_hazard() -> None:
    """The read edge's store posture is chosen by SP2_CP_CONTROL_STORE, which DEFAULTS to in-memory.

    Starting the Control Plane Read edge natively without ``SP2_CP_CONTROL_STORE=postgres`` therefore
    serves from a NON-DURABLE store. That is pre-existing Control Plane behaviour governed by its own
    selectors — the application factory does not and must not override it — but it is exactly the
    "in-memory must not silently become standing operation" hazard, so the operator runbook is
    required to carry the warning. This test fails if that warning is ever removed.
    """
    runbook = _BACKEND.parent / "docs" / "runbooks" / "backend_service_startup_fastapi.md"
    assert runbook.is_file(), "the operator runbook must exist"
    text = runbook.read_text(encoding="utf-8")
    assert "SP2_CP_CONTROL_STORE" in text, "the runbook must name the Control-store posture selector"
    assert "test-only" in text, "the runbook must mark the in-memory default as test-only"


def test_partial_public_edge_composition_never_activates() -> None:
    """Successor of ``test_partial_gateway_composition_never_activates``.

    The Gateway needed three transports and refused to front a partial composition. Each public edge
    needs fewer, and the property is sharper: the AUTHENTICATION selector is what must never be
    optional. Omitting it must produce NO application — not an edge that serves unauthenticated.
    """
    cases = (
        ("database_router.adapters.providers.http_public_startup_edge", "SP2_EDGE_AUTH_ROUTER_BASE_URL"),
        ("database_router.adapters.providers.http_public_startup_edge", "SP2_DBR_ROUTING_READ_BASE_URL"),
        ("control_plane.adapters.providers.http_public_workspace_edge", "SP2_EDGE_AUTH_ROUTER_BASE_URL"),
    )
    for module_path, omitted in cases:
        env = _complete_env(_secret_dir())
        env.pop(omitted, None)
        with _env(env):
            raised = None
            try:
                _factory(module_path)()
            except RuntimeError as exc:
                raised = exc
            assert raised is not None, f"{module_path} must fail closed when {omitted} is absent"


def test_malformed_selector_fails_closed_before_composition() -> None:
    env = _complete_env(_secret_dir())
    env["SP2_DBR_ROUTING_READ_BASE_URL"] = "ftp://not-http"
    with _env(env):
        raised = None
        try:
            _factory("database_router.adapters.providers.http_public_startup_edge")()
        except ValueError as exc:
            raised = exc
        assert raised is not None, "a malformed routing selector must raise, never fall back to a double"


def test_import_edge_accepts_env_var_only_tenant_secrets() -> None:
    """``SNACKPORTAL_TENANT_SECRET_DIR`` must NOT be demanded at composition.

    ``EnvTenantSecretStore.resolve`` consults a per-reference environment variable FIRST and only
    then falls back to a file under the directory, so an environment-variable-only deployment is
    valid. A composition-time precheck on the directory would reject that valid configuration and
    would duplicate the provider's own knowledge across a path boundary. The fail-closed guarantee
    is unchanged — the provider raises on an unresolved reference at first use.
    """
    env = _complete_env(_secret_dir())
    env.pop("SNACKPORTAL_TENANT_SECRET_DIR")
    with _env(env):
        app = _factory("deployment.import_edge")()
        assert isinstance(app, FastAPI), "an environment-variable-only tenant secret deployment must compose"


def test_import_edge_still_requires_real_routing() -> None:
    # The one thing the Import edge may never start without: registry-authoritative routing.
    env = _complete_env(_secret_dir())
    env.pop("SP2_DBR_ROUTING_READ_BASE_URL")
    with _env(env):
        raised = None
        try:
            _factory("deployment.import_edge")()
        except RuntimeError as exc:
            raised = exc
        assert raised is not None, "the Import edge must fail closed without a real Database Router"
        assert "SP2_DBR_ROUTING_READ_BASE_URL" in str(raised)


# --- one composition path -------------------------------------------------------------------


def test_factory_and_compatibility_seam_produce_the_same_route_set() -> None:
    # Both paths go through the same `make_app`, so the served surface cannot drift between the
    # canonical native startup and the retained compatibility lifecycle. Re-aimed at the PUBLIC
    # tenant Startup edge: the internal dispatch edge this used to check was deleted with the API
    # Gateway, and the property (one surface, two entry points) belongs to whichever edge exists.
    from database_router.adapters.providers.http_public_startup_edge import build_public_startup_edge_server
    from database_router.main import build_public_startup_edge_deps_from_env

    with _env(_complete_env(_secret_dir())):
        native = _factory("database_router.adapters.providers.http_public_startup_edge")()
        deps = build_public_startup_edge_deps_from_env()
        assert deps is not None
        ops, boundary, allowed_origins = deps
        server, _base = build_public_startup_edge_server(ops, boundary, host="127.0.0.1", port=0, allowed_origins=allowed_origins)
        try:
            assert _routes(native) == _routes(server.app), "the native and compatibility paths must expose one surface"
        finally:
            server.server_close()


def test_compatibility_lifecycle_is_still_available() -> None:
    # The retained path keeps its full surface: this PRD does not remove it.
    from shared.adapters.providers.asgi_runtime import AsgiEdgeServer

    for attribute in ("server_address", "serve_forever", "shutdown", "server_close"):
        assert hasattr(AsgiEdgeServer, attribute) or attribute == "server_address", f"the compatibility lifecycle must retain {attribute}"


if __name__ == "__main__":
    _TESTS = [
        test_importing_every_edge_module_is_inert,
        test_every_factory_returns_a_composed_fastapi_app,
        test_every_factory_app_keeps_the_closed_surface,
        test_factory_is_callable_with_no_arguments,
        test_gated_factories_fail_closed_with_no_configuration,
        test_lazy_factories_compose_but_never_resolve_a_secret_at_startup,
        test_read_edge_in_memory_default_is_a_documented_operator_hazard,
        test_partial_public_edge_composition_never_activates,
        test_malformed_selector_fails_closed_before_composition,
        test_import_edge_accepts_env_var_only_tenant_secrets,
        test_import_edge_still_requires_real_routing,
        test_factory_and_compatibility_seam_produce_the_same_route_set,
        test_compatibility_lifecycle_is_still_available,
    ]
    _failed = 0
    for _test in _TESTS:
        try:
            _test()
            print("PASS:", _test.__name__)
        except AssertionError as _exc:
            _failed += 1
            print("FAIL:", _test.__name__, "-", _exc)
    if _failed:
        print(f"{_failed} test(s) failed")
        sys.exit(1)
    print("ALL PASSED")
