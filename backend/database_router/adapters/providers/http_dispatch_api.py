"""Internal Gateway->Database-Router dispatch transport server (FastAPI/uvicorn) — D-15-T1b.

The router side of the D-15-T1a dispatch wire contract
(docs/d15/D15-DISPATCH-SPEC-01). Exposes ONE internal-only surface,
``POST /internal/dispatch/route``, which MUST remain internal-only and MUST NEVER be
portal-reachable or registered as a public/frontend ingress (IC-010 §R Internal-Surface
Protection; §M Service Contract). It binds ``127.0.0.1`` by default and serves through the
shared uvicorn runtime (``shared.adapters.providers.asgi_runtime``); the FastAPI app declares
exactly the one route and the OpenAPI/docs surface is disabled, so the closed single-surface
posture is unchanged.

Wire contract. The request envelope is exactly ``{v, context, category}`` where
``context`` is exactly the five ``RequestContext`` fields; ``v`` MUST be ``1``.
``category`` is ADVISORY metadata only and is NEVER a database selector — the router
binds SOLELY from the signed ``RequestContext`` claim (IC-010 §X/§H), so ``category`` is
never handed to ``route()``. ``DispatchDecision`` is never on the wire. A successful
dispatch resolves routing and, for a tenant route, binds and IMMEDIATELY RELEASES exactly
one tenant connection before responding; the live connection stays router-side and is
never serialized. The response envelope is exactly ``{status, public_code, dispatched}`` —
references only: no connection, database name, credential, DSN value, topology, route
reference, body, or business payload crosses the wire.

Fail closed (IC-010 §L — no error path may downgrade to a less-isolated outcome or expose
internal detail): a malformed / wrong-shape / unknown-version / unknown-category request,
and any unhandled server exception, produce a fixed ``503`` with an EMPTY body; a non-POST
method is refused ``405`` empty; a wrong path is refused ``404`` empty; a query-bearing
request target is refused ``404`` empty (the pre-migration edge compared the raw request
target, so a stray ``?query`` never matched the path — restored explicitly here); no
framework error body is ever emitted. This is a routing transport adapter only — it
performs NO business work.
"""

from __future__ import annotations

import json
from typing import Optional, Tuple, cast

from fastapi import FastAPI, Request, Response

from database_router.models import RoutingDenied
from database_router.router import DatabaseRouter
from shared.adapters.providers.asgi_runtime import AsgiEdgeServer, build_asgi_server
from shared.adapters.providers.fastapi_edge import empty_response, has_query_string, json_response, new_edge_app
from shared.context import RequestContext

_DISPATCH_PATH = "/internal/dispatch/route"

# The four DispatchCategory value strings, copied verbatim from api_gateway/models.py
# (IC-010 §Q). Held as a LOCAL frozenset because database_router must not import
# api_gateway (DAG independence); the static guard asserts this set equals the live enum.
_DISPATCH_CATEGORIES = frozenset({"TENANT_OPERATION", "GLOBAL_DIRECTORY_READ", "MEMBERSHIPS_FOR_PRINCIPAL", "IMPORT_INITIATION"})

_CONTEXT_KEYS = frozenset({"correlation_id", "request_id", "active_tenant_id", "principal_ref", "role"})


class _EnvelopeError(Exception):
    """A malformed/invalid request envelope — mapped fail-closed to a 503 empty body."""


def _optional_str(value: object) -> Optional[str]:
    if value is not None and not isinstance(value, str):
        raise _EnvelopeError("context field must be a string or null")
    return value


def _reconstruct_context(context: object) -> RequestContext:
    if not isinstance(context, dict) or set(context.keys()) != set(_CONTEXT_KEYS):
        raise _EnvelopeError("context keys must be exactly the five RequestContext fields")
    correlation_id = context["correlation_id"]
    if not isinstance(correlation_id, str):  # only correlation_id is always present (non-null)
        raise _EnvelopeError("correlation_id must be a non-null string")
    return RequestContext(
        correlation_id=correlation_id,
        request_id=_optional_str(context["request_id"]),
        active_tenant_id=_optional_str(context["active_tenant_id"]),
        principal_ref=_optional_str(context["principal_ref"]),
        role=_optional_str(context["role"]),
    )


def _decide(router: DatabaseRouter, raw: bytes) -> Tuple[int, str, bool]:
    """Validate the T1a envelope, route from the signed claim, and return the references-only
    ``(status, public_code, dispatched)`` triple. Raises ``_EnvelopeError`` on any invalid
    envelope (mapped to a 503 empty body by the caller). A ``RoutingDenied`` is mapped to its
    canonical ``(http_status, public_code, False)``; a successful route binds and releases any
    tenant connection before returning."""
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise _EnvelopeError("body is not valid JSON") from exc
    if not isinstance(envelope, dict) or set(envelope.keys()) != {"v", "context", "category"}:
        raise _EnvelopeError("request keys must be exactly {v, context, category}")
    if envelope["v"] != 1:
        raise _EnvelopeError("unknown envelope version")
    category = envelope["category"]
    if not isinstance(category, str) or category not in _DISPATCH_CATEGORIES:
        raise _EnvelopeError("unknown dispatch category")
    ctx = _reconstruct_context(envelope["context"])

    # AUTHORITY PIN: the router binds solely from ctx; `category` is advisory only and is
    # never passed to route() (IC-010 §X — category is never a database selector).
    try:
        result = router.route(ctx)
    except RoutingDenied as denied:
        return (denied.http_status, denied.public_code, False)
    # References-only success: release any bound tenant connection before responding; the
    # live connection never leaves the router (CONTROL routes carry no connection).
    router.release(result)
    return (200, "ok", True)


def _make_app(router: DatabaseRouter) -> FastAPI:
    """Build the FastAPI app exposing EXACTLY the one internal dispatch surface.

    The app declares one route and one method; every other path is ``404`` and every other
    method ``405``, both with an EMPTY body, decided by the app's fail-closed handlers before
    the router is ever reached (``new_edge_app``). Docs/OpenAPI are disabled.
    """
    app = new_edge_app(invalid_status=503, unavailable_status=503)

    @app.post(_DISPATCH_PATH)
    async def route(request: Request) -> Response:
        if has_query_string(request):
            return empty_response(404)  # query-bearing target: refused, no route call
        try:
            raw = await request.body()
            status, public_code, dispatched = _decide(router, raw)
        except Exception:
            # Invalid envelope OR any unhandled server exception -> fixed 503 empty body
            # (no stack trace, topology, database detail, or credential disclosure).
            return empty_response(503)
        # Mirror envelope.status on the HTTP status line.
        return json_response(status, {"status": status, "public_code": public_code, "dispatched": dispatched})

    return app


def create_app_from_env() -> FastAPI:
    """The CANONICAL native ASGI application factory for the internal dispatch edge.

    Run directly by the operator through the ASGI runtime's own command line::

        uvicorn database_router.adapters.providers.http_dispatch_api:create_app_from_env --factory ...

    Takes NO arguments: the listening host and port belong to the runtime process, not to the
    application, so this factory binds no socket and owns no address. It returns the composed
    ``FastAPI`` app and nothing else.

    ONE composition path (no second composition root): the ``DatabaseRouter`` is built by
    ``database_router.main.build_router_from_env`` — the SAME single env-parsing/adapter-wiring
    function the compatibility ``build_dispatch_server_from_env`` seam uses — and the app is built
    by the SAME ``_make_app``. Routing-read transport, the reference-only tenant secret store, the
    connection factory, and the routing-audit selection therefore have exactly one source of truth.

    Fail closed (IC-010 §L): the operator invoked this process deliberately, so an INACTIVE
    composition is a misconfiguration, not a no-op. ``SP2_DBR_ROUTING_READ_BASE_URL`` unset/empty →
    ``RuntimeError``; a malformed value → ``ValueError`` (inherited). There is deliberately NO
    fallback to an in-memory or test double — a standing router must never silently stop resolving
    registry-authoritative routing against the real control plane.

    Import-time inertness is preserved: nothing here runs at module import, and the driver-bearing
    provider modules are imported lazily inside the composition function, never at module load.
    """
    # Function-local absolute import (the established composition-root idiom): the adapter module
    # stays import-light and cycle-free, and importing it performs no composition.
    from database_router.main import build_router_from_env

    router = build_router_from_env()
    if router is None:
        raise RuntimeError(
            "create_app_from_env: dispatch composition is INACTIVE — "
            "SP2_DBR_ROUTING_READ_BASE_URL is unset/empty (fail closed: no application composed)"
        )
    return _make_app(router)


def build_dispatch_server(router: DatabaseRouter, host: str = "127.0.0.1", port: int = 0) -> Tuple[AsgiEdgeServer, str]:
    """Build the internal dispatch HTTP server bound to a composed ``DatabaseRouter``.

    ``port=0`` binds an ephemeral port. This factory constructs the server only — it does
    NOT start serving (the blocking runnable entrypoint is ``serve_dispatch_api``; tests may
    also host the server directly via ``serve_forever``/``shutdown``/``server_close``).
    Returns ``(server, base_url)``.
    """
    return build_asgi_server(_make_app(router), host, port)


def serve_dispatch_api() -> None:
    """Blocking runnable entrypoint for the internal dispatch edge (B5-2).

    Composes the server via the merged env seam ``build_dispatch_server_from_env``
    (``database_router/main.py``) and serves it on the CALLING thread:

    * inactive composition (``SP2_DBR_ROUTING_READ_BASE_URL`` unset/empty) → deterministic
      ``RuntimeError`` — fail closed; no socket was bound and nothing is served;
    * malformed composition config → ``ValueError`` from the seam (inherited, fail closed);
    * active → ``server.serve_forever()`` exactly once on the calling thread (AT-D15T1-10: one
      server per operating-system process; no thread, daemon, subprocess, supervisor, or retry
      loop is created HERE — request concurrency is the ASGI runtime's own event loop), and
      ``server.server_close()`` ALWAYS runs in ``finally`` — ``KeyboardInterrupt`` and any
      serve-time exception propagate to the caller unswallowed.

    Ops: docs/runbooks/b5_service_startup_order.md (the control-plane read edge starts first; its
    URL feeds ``SP2_DBR_ROUTING_READ_BASE_URL``; this service's URL then feeds
    ``SP2_GW_DB_ROUTER_BASE_URL``). No overclaim: this makes the service RUNNABLE — it does not
    deploy or supervise it, prove a served-request live topology, provision a physical database,
    or complete Smoke C / the Physical Multi-Database MVP (B5-BLK-4 stays OPEN).
    """
    # Function-local absolute import mirrors the 07E-1 serve_read_api precedent (composition root
    # imported lazily at call time; the adapter module stays import-light and cycle-free).
    from database_router.main import build_dispatch_server_from_env

    composed = build_dispatch_server_from_env()
    if composed is None:
        raise RuntimeError(
            "serve_dispatch_api: dispatch-server composition is INACTIVE — "
            "SP2_DBR_ROUTING_READ_BASE_URL is unset/empty (fail closed: no socket bound, nothing served)"
        )
    server_obj, _base_url = composed
    server = cast(AsgiEdgeServer, server_obj)
    try:
        server.serve_forever()
    finally:
        server.server_close()
