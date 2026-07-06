"""HTTP binding for the Control Plane Read API (stdlib http.server) — PRD 07E-1 read edge.

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

Runtime: plain single-threaded stdlib ``HTTPServer``, GET-only, internal/control-plane-scoped
(network-restricted; mTLS/internal identity at deployment). Not public, not frontend- or
Lovable-facing; carries no end-user auth (the production IC-005 auth adapter is 07E-3).
Pure stdlib — no web framework, no database driver import here (driver containment).

Deployment recommendation (AT-07E-5): set ``idle_in_transaction_session_timeout`` and
``statement_timeout`` on the Control-DB connection/role serving this edge.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, Tuple, cast

from control_plane.read_api import ControlPlaneReadDispatcher, ControlPlaneReadService

if TYPE_CHECKING:  # typing only — no composition import at runtime module load
    from control_plane.main import ControlPlane


def _make_handler(control_plane: "ControlPlane") -> type[BaseHTTPRequestHandler]:
    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            # PRD 07E-1: one logical request == one fresh ControlStore unit of work. The
            # `with` exits (unit of work released: rollback + close) BEFORE the response
            # is written; the yielded store is never cached or reused across requests.
            try:
                with control_plane.control_store_unit_of_work() as store:
                    dispatcher = ControlPlaneReadDispatcher(ControlPlaneReadService(store))
                    status, body = dispatcher.handle("GET", self.path)
            except Exception:
                # Fail closed: fixed 503, EMPTY body — no tenant/database/connection/secret
                # detail may leak; the failed unit of work was released by the factory.
                self.send_response(503)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            payload = json.dumps(body if body is not None else {}).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _method_not_allowed(self) -> None:
            # GET-only edge: every non-GET method is refused with a fixed 405 and an
            # EMPTY body (fail closed; nothing is dispatched, no unit of work is opened).
            self.send_response(405)
            self.send_header("Content-Length", "0")
            self.end_headers()

        # Refuse (not serve) other methods: do_GET stays the ONLY do_* handler function.
        do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _method_not_allowed

        def log_message(self, *args: object) -> None:  # silence default stderr logging
            return

    return _Handler


def make_server(control_plane: "ControlPlane", host: str = "127.0.0.1", port: int = 0) -> Tuple[HTTPServer, str]:
    """Build the read-edge HTTP server bound to a ``ControlPlane`` — NOT a store.

    No store is acquired at server construction and no dispatcher outlives a request:
    each ``do_GET`` opens its own unit of work (PRD 07E-1). ``port=0`` binds an ephemeral
    port; the caller runs ``server.serve_forever()`` and reads ``base_url``.
    """
    server = HTTPServer((host, port), _make_handler(control_plane))
    bound_host, bound_port = cast(str, server.server_address[0]), server.server_address[1]
    return server, f"http://{bound_host}:{bound_port}"


def serve_read_api(host: str = "127.0.0.1", port: int = 8080) -> None:  # pragma: no cover
    """Runnable entrypoint: compose the app and serve the internal read edge (blocking)."""
    from control_plane.main import create_app  # function-local intra-package import (07E-1 §5A)

    server, _ = make_server(create_app(), host, port)
    server.serve_forever()
