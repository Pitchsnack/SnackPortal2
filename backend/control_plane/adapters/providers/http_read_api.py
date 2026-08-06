"""HTTP binding for the Control Plane Read API (FastAPI/uvicorn) — PRD 07E-1 read edge.

Per-request unit-of-work transport (the PRD 07D-3b contract, wired): every GET request
acquires a FRESH ControlStore unit of work via ``ControlPlane.control_store_unit_of_work()``,
builds the read service/dispatcher on the yielded store, and the unit of work is released
(rollback + close) BEFORE the HTTP response is written. The handler never holds, caches,
shares, or carries a ``ControlStore`` beyond one logical request, and never touches the
``ControlPlane`` facade-bound services (``.store``/``.registry``/``.membership``/
``.federation``/``.directory``/``.audit``).

Fail-closed: a store/connection error returns a fixed 503 with an EMPTY body — no tenant,
database, connection, or secret detail leaks through this edge. Dispatcher 404/405 results
pass through unchanged; non-GET methods are refused with 405 (empty body) while ``do_GET``
remains the ONLY served handler.

Runtime: FastAPI served through the shared uvicorn runtime
(``shared.adapters.providers.asgi_runtime``), GET-only, internal/control-plane-scoped
(network-restricted; mTLS/internal identity at deployment). Not public, not frontend- or
Lovable-facing; carries no end-user auth (the production IC-005 auth adapter is 07E-3). The
OpenAPI/docs surface is disabled, and no database driver is imported here (driver containment).

Routing note: this edge owns NO route table. ``ControlPlaneReadDispatcher`` is the route
authority — it splits the request target itself (path + query) and answers 404/405 for
anything it does not serve. The FastAPI layer therefore declares ONE catch-all GET route and
forwards the RAW request target (undecoded path plus the verbatim query string, exactly what
the pre-migration edge passed as ``self.path``) so the dispatcher's parsing is unchanged.

Deployment recommendation (AT-07E-5): set ``idle_in_transaction_session_timeout`` and
``statement_timeout`` on the Control-DB connection/role serving this edge.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

from fastapi import FastAPI, Request, Response

from control_plane.read_api import ControlPlaneReadDispatcher, ControlPlaneReadService
from shared.adapters.providers.asgi_runtime import AsgiEdgeServer, build_asgi_server
from shared.adapters.providers.fastapi_edge import empty_response, json_response, new_edge_app

if TYPE_CHECKING:  # typing only — no composition import at runtime module load
    from control_plane.main import ControlPlane


def _request_target(request: Request) -> str:
    """Reconstruct the RAW request target the dispatcher expects (path + ``?query``).

    ``raw_path`` is the undecoded path as it arrived on the wire, so a percent-encoded
    target reaches the dispatcher exactly as it did through the stdlib handler's
    ``self.path`` — decoding here could turn an unmatched target into a matched one.
    """
    raw_path = request.scope.get("raw_path")
    target = raw_path.decode("latin-1") if isinstance(raw_path, bytes) else request.url.path
    query = request.scope.get("query_string") or b""
    if query:
        target += "?" + query.decode("latin-1")
    return target


def _make_app(control_plane: "ControlPlane") -> FastAPI:
    """Build the GET-only FastAPI app that fronts the read dispatcher.

    Every non-GET method is refused with a fixed ``405`` and an EMPTY body before anything
    is dispatched and before any unit of work is opened (``new_edge_app``).
    """
    app = new_edge_app(invalid_status=503, unavailable_status=503)

    @app.get("/{_target:path}")
    async def read(request: Request, _target: str) -> Response:
        # PRD 07E-1: one logical request == one fresh ControlStore unit of work. The
        # `with` exits (unit of work released: rollback + close) BEFORE the response
        # is written; the yielded store is never cached or reused across requests.
        try:
            with control_plane.control_store_unit_of_work() as store:
                dispatcher = ControlPlaneReadDispatcher(ControlPlaneReadService(store))
                status, body = dispatcher.handle("GET", _request_target(request))
        except Exception:
            # Fail closed: fixed 503, EMPTY body — no tenant/database/connection/secret
            # detail may leak; the failed unit of work was released by the factory.
            return empty_response(503)
        return json_response(status, body if body is not None else {})

    return app


def create_app_from_env() -> FastAPI:
    """The CANONICAL native ASGI application factory for the Control Plane read edge.

    Run directly by the operator through the ASGI runtime's own command line::

        uvicorn control_plane.adapters.providers.http_read_api:create_app_from_env --factory ...

    Takes NO arguments: the listening host and port belong to the runtime process, not to the
    application, so this factory binds no socket and owns no address. It returns the composed
    ``FastAPI`` app and nothing else.

    ONE composition path (no second composition root): the ``ControlPlane`` is composed by
    ``control_plane.main.create_app`` — the SAME single composition function the compatibility
    ``build_read_server_from_env`` seam uses — and the app is built by the SAME ``_make_app``.
    The Control-DB store binding, its reference-only secret resolution, and every SP2_CP_*
    selector-coherence rule therefore have exactly one source of truth.

    Fail closed (IC-010 §L): ``create_app()`` applies its own selector-coherence validation and
    raises on incoherent or blank required configuration, so a misconfigured process never reaches
    a served state. There is deliberately NO fallback to an in-memory store — the standing backend
    must keep the physical Control database as its only durable authority.

    Per-request unit-of-work is unchanged (PRD 07E-1): this factory acquires NO store, opens no
    connection, and runs no query. ``ControlPlane`` construction is lazy-connect, so composition
    performs no database I/O; each served GET still opens and releases its own fresh unit of work.
    """
    # Function-local absolute import (07E-1 §5A): the adapter module stays import-light and
    # cycle-free, and importing it performs no composition.
    from control_plane.main import create_app

    return _make_app(create_app())


def make_server(control_plane: "ControlPlane", host: str = "127.0.0.1", port: int = 0) -> Tuple[AsgiEdgeServer, str]:
    """Build the read-edge HTTP server bound to a ``ControlPlane`` — NOT a store.

    No store is acquired at server construction and no dispatcher outlives a request:
    each served GET opens its own unit of work (PRD 07E-1). ``port=0`` binds an ephemeral
    port; the caller runs ``server.serve_forever()`` and reads ``base_url``.
    """
    return build_asgi_server(_make_app(control_plane), host, port)


def serve_read_api(host: str = "127.0.0.1", port: int = 8080) -> None:  # pragma: no cover
    """Runnable entrypoint: compose the app and serve the internal read edge (blocking)."""
    from control_plane.main import create_app  # function-local intra-package import (07E-1 §5A)

    server, _ = make_server(create_app(), host, port)
    server.serve_forever()
