"""HTTP binding for the Control Plane Read API (stdlib http.server).

Thin transport adapter: serves `ControlPlaneReadDispatcher` results as JSON. The
routing endpoint is internal/control-plane-scoped (network-restricted; mTLS/internal
identity at deployment). The read *logic* lives in control_plane.read_api and is unit
tested directly; this binding is exercised by an optional loopback round-trip test.
Pure stdlib (no web framework) — vendor-neutral and portable.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Tuple

from control_plane.read_api import ControlPlaneReadDispatcher, ControlPlaneReadService
from control_plane.ports import ControlStore


def _make_handler(dispatcher: ControlPlaneReadDispatcher):
    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            status, body = dispatcher.handle("GET", self.path)
            payload = json.dumps(body if body is not None else {}).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args: object) -> None:  # silence default stderr logging
            return

    return _Handler


def make_server(store: ControlStore, host: str = "127.0.0.1", port: int = 0) -> Tuple[HTTPServer, str]:
    """Build an HTTP server for the read API. Returns (server, base_url).

    `port=0` binds an ephemeral port; the caller runs `server.serve_forever()` (e.g.
    in a thread) and reads `base_url` for the bound address.
    """
    dispatcher = ControlPlaneReadDispatcher(ControlPlaneReadService(store))
    server = HTTPServer((host, port), _make_handler(dispatcher))
    bound_host, bound_port = server.server_address[0], server.server_address[1]
    return server, f"http://{bound_host}:{bound_port}"


def serve(store: ControlStore, host: str = "127.0.0.1", port: int = 8080) -> None:  # pragma: no cover
    server, _ = make_server(store, host, port)
    server.serve_forever()
