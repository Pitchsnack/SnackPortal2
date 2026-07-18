"""Served northbound API Gateway HTTP edge (stdlib http.server) — Served API Gateway Edge V1.

The single thin, single-threaded serving edge that converts a real HTTP request into the
existing framework-neutral Gateway core (IC-010 §A/§N) and back. It owns TRANSPORT ONLY:
a closed route + method allowlist, conservative request bounds, correlation accept/mint/echo,
an exact-origin CORS allowlist, and the mapping ``InboundRequest`` -> ``Gateway.handle`` ->
``serialize_portal_dto`` (success) / a fixed safe status (denial). It does NOT authenticate,
mint principals, authorize, classify routes for business, select tenants, route databases,
compose portal DTOs, decide audit, or run business logic — every one of those stays inside
the composed Gateway core it fronts (``ports.py`` / ``gateway.py`` / ``dispatch.py`` /
``portal.py``). The edge calls exactly ONE thing: ``Gateway.handle``.

Exposed surface (V1): ``GET /memberships`` (the only business route — self-scoped
MembershipsForPrincipal), ``GET /health``, ``GET /readiness``, and ``OPTIONS /memberships``
(the CORS preflight). Every other path is ``404`` route-not-exposed and every non-allowed
method is ``405`` — decided BEFORE the core is ever reached. ``Gateway.handle`` is invoked
exactly once, and only for a valid ``GET /memberships`` business request; operational routes
and pre-core rejections never reach it.

Runtime: plain single-threaded stdlib ``HTTPServer`` + ``BaseHTTPRequestHandler`` bound to
``127.0.0.1`` by default (TLS terminates at a reverse proxy — deployment scope; this edge
pins ``http`` at the internal seam). No web framework, no new dependency, no threading, no
database or sibling-service import, no JWT/OIDC/crypto. Bearer-only (the ``Authorization``
header); no cookie authentication, so CSRF is not applicable to this V1, and forwarded
headers (``X-Forwarded-*``) are never trusted as a tenant selector or security decision.
Fail closed (IC-010 §L): every denial and unavailability carries a fixed status and NO
detail — never a provider body, exception text, stack, token, DSN, database identity, or
tenant topology. Success bodies are produced ONLY by the core-owned ``serialize_portal_dto``.
``log_message`` is silenced. The blocking runnable ``serve_gateway_edge`` calls
``serve_forever`` exactly once and always closes the server in ``finally``.
"""

from __future__ import annotations

import json
import re
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Mapping, Optional, Tuple, cast

from api_gateway.gateway import Gateway
from api_gateway.models import GatewayResponse, InboundRequest
from api_gateway.portal import serialize_portal_dto
from api_gateway.readiness import liveness, readiness

# --- transport constants (conservative, review-pinned; test-pinned by the boundary guard) ---
_CORRELATION_HEADER = "x-correlation-id"
_TENANT_HEADER = "X-Tenant-Id"  # the only recognized carrier header (case-insensitive, IC-010 §E)

_MAX_CORRELATION_LEN = 128  # accept a bounded opaque id; longer/unsafe -> mint a fresh one
_SAFE_CORRELATION = re.compile(r"[A-Za-z0-9._\-]+")  # anti-log-injection / anti-spoof charset

_MAX_REQUEST_TARGET_BYTES = 2048  # request-target (path + any query) byte cap
_MAX_HEADER_COUNT = 64  # header-count cap (below the stdlib 100-header parse limit)
_MAX_TOTAL_HEADER_BYTES = 16384  # 16 KiB total accepted header bytes
_MAX_BODY_BYTES = 0  # the exposed GETs carry no business body; any non-empty body is rejected
_MAX_DRAIN_BYTES = 65536  # bounded read of a rejected body so the response delivers without a reset

# The closed transport route allowlist: exact request-target -> the methods it exposes. Any
# other target is 404 (route not exposed); a non-listed method on a listed target is 405.
# Everything here is decided BEFORE the Gateway core is invoked.
_EXPOSED_ROUTES: Mapping[str, "frozenset[str]"] = {
    "/memberships": frozenset({"GET", "OPTIONS"}),
    "/health": frozenset({"GET"}),
    "/readiness": frozenset({"GET"}),
}


def _make_handler(gateway: Gateway, allowed_origins: Tuple[str, ...]) -> "type[BaseHTTPRequestHandler]":
    """Build the request handler bound to a composed ``Gateway`` and the exact-origin CORS
    allowlist. The handler owns transport only; it calls ``gateway.handle`` exactly once for a
    valid ``GET /memberships`` business request and never for a rejection or operational route."""

    class _GatewayEdgeHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            self._dispatch("GET")

        def do_OPTIONS(self) -> None:  # noqa: N802 (http.server API)
            self._dispatch("OPTIONS")

        def _method_not_allowed(self) -> None:
            # Route every other method through the same dispatch so a listed target yields 405
            # and an unlisted target yields 404 (both pre-core, fixed status, empty body).
            self._dispatch(self.command)

        # Refuse (not serve) other methods; do_GET/do_OPTIONS stay the only served handlers.
        do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = _method_not_allowed

        def _dispatch(self, method: str) -> None:
            correlation_id = self._correlation_id()
            origin = self.headers.get("Origin")
            # Drain any declared request body (bounded, discarded — never interpreted) so a rejection
            # response delivers cleanly on the connection instead of resetting the peer.
            self._drain_body()
            # Transport bounds first (pre-core): request target, header count/bytes, body.
            bounds_status = self._bounds_violation()
            if bounds_status is not None:
                self._respond(bounds_status, correlation_id, origin)
                return
            target = self.path  # exact request-target: a stray ?query never equals a listed route
            allowed_methods = _EXPOSED_ROUTES.get(target)
            if allowed_methods is None:
                self._respond(404, correlation_id, origin)  # route not exposed (pre-core)
                return
            if method not in allowed_methods:
                self._respond(405, correlation_id, origin)  # method not allowed (pre-core)
                return
            if method == "OPTIONS":
                # CORS preflight for /memberships: 204, exact-origin headers only when the
                # origin is allowlisted. The Gateway core is NEVER invoked for a preflight.
                self._respond(204, correlation_id, origin, preflight=True)
                return
            if target == "/health":
                self._respond_json(200, json.dumps(liveness()).encode("utf-8"), correlation_id, origin)
                return
            if target == "/readiness":
                # In-process liveness/state only — NOT a full production-readiness proof.
                self._respond_json(200, json.dumps(readiness()).encode("utf-8"), correlation_id, origin)
                return
            self._handle_memberships(correlation_id, origin)

        def _handle_memberships(self, correlation_id: str, origin: Optional[str]) -> None:
            # The ONE business path: build the typed InboundRequest and call the core exactly
            # once. The edge validates nothing about identity/tenant/route beyond transport.
            request = InboundRequest(
                method="GET",
                path="/memberships",
                host=self.headers.get("Host", "") or "",
                headers=self._forwarded_headers(correlation_id),
                authorization=self.headers.get("Authorization"),
            )
            response: GatewayResponse = gateway.handle(request)
            if response.status == 200 and response.portal_dto is not None:
                # Success bodies come ONLY from the core-owned serializer (catalogue-closed).
                self._respond_json(200, serialize_portal_dto(response.portal_dto), correlation_id, origin)
                return
            # Every denial/unavailable -> fixed status, EMPTY body, no detail (fail closed).
            status = response.status if response.status >= 400 else 503
            self._respond(status, correlation_id, origin)

        def _forwarded_headers(self, correlation_id: str) -> Dict[str, str]:
            # Faithful, minimal pass-through: the edge OWNS x-correlation-id (accept/mint) and
            # forwards ONLY the recognized X-Tenant-Id carrier so the core can enforce isolation.
            # Cookies/query are prohibited carriers and are never populated; no X-Forwarded-* header
            # is trusted as a selector or a security decision.
            headers: Dict[str, str] = {_CORRELATION_HEADER: correlation_id}
            tenant = self.headers.get(_TENANT_HEADER)
            if tenant is not None:
                headers[_TENANT_HEADER] = tenant
            return headers

        def _correlation_id(self) -> str:
            raw = self.headers.get(_CORRELATION_HEADER)
            if raw is not None:
                value = raw.strip()
                if 1 <= len(value) <= _MAX_CORRELATION_LEN and _SAFE_CORRELATION.fullmatch(value):
                    return value
            # Missing / blank / oversized / unsafe -> mint a fresh opaque id (anti-spoof).
            return uuid.uuid4().hex

        def _drain_body(self) -> None:
            # Read and discard a declared request body up to a bounded cap so the response delivers
            # cleanly (a served edge must not leave unread bytes and reset the peer). The body is
            # NEVER interpreted, forwarded, or logged — draining is not processing. Chunked bodies
            # (no Content-Length) are not drained; they are rejected by _bounds_violation.
            raw_len = self.headers.get("Content-Length")
            if not raw_len:
                return
            try:
                remaining = min(int(raw_len), _MAX_DRAIN_BYTES)
            except ValueError:
                return
            while remaining > 0:
                chunk = self.rfile.read(min(remaining, 8192))
                if not chunk:
                    break
                remaining -= len(chunk)

        def _bounds_violation(self) -> Optional[int]:
            if len(self.path.encode("utf-8")) > _MAX_REQUEST_TARGET_BYTES:
                return 413
            if len(self.headers) > _MAX_HEADER_COUNT:
                return 413
            if len(str(self.headers).encode("utf-8")) > _MAX_TOTAL_HEADER_BYTES:
                return 413
            if self.headers.get("Transfer-Encoding"):
                return 413  # chunked/streamed bodies are not accepted on these GETs
            raw_len = self.headers.get("Content-Length")
            if raw_len is not None:
                try:
                    length = int(raw_len)
                except ValueError:
                    return 400  # malformed transport request
                if length > _MAX_BODY_BYTES:
                    return 413  # a non-empty body on a body-less GET
            return None

        def _respond(self, status: int, correlation_id: str, origin: Optional[str], *, preflight: bool = False) -> None:
            # Fixed safe response, EMPTY body — the only shape for every denial/rejection/preflight.
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.send_header(_CORRELATION_HEADER, correlation_id)
            self._write_cors_headers(origin, preflight=preflight)
            self.end_headers()

        def _respond_json(self, status: int, payload: bytes, correlation_id: str, origin: Optional[str]) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header(_CORRELATION_HEADER, correlation_id)
            self._write_cors_headers(origin, preflight=False)
            self.end_headers()
            self.wfile.write(payload)

        def _write_cors_headers(self, origin: Optional[str], *, preflight: bool) -> None:
            # Exact-origin allowlist only. A denied or absent origin receives NO CORS headers
            # (the browser blocks the response). NEVER a wildcard; NEVER credentialed CORS.
            if origin is None or origin not in allowed_origins:
                return
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "false")
            self.send_header("Vary", "Origin")
            if preflight:
                self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Authorization, x-correlation-id")

        def log_message(self, *args: object) -> None:  # silence default stderr logging (no token/payload leak)
            return

    return _GatewayEdgeHandler


def build_gateway_edge_server(
    gateway: Gateway,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    allowed_origins: Tuple[str, ...] = (),
) -> Tuple[HTTPServer, str]:
    """Build the served gateway-edge HTTP server bound to a composed ``Gateway``.

    ``port=0`` binds an ephemeral port. This factory constructs the server only — it does NOT
    start serving (the blocking runnable entrypoint is ``serve_gateway_edge``; tests may host
    the single-threaded server directly). Returns ``(server, base_url)``. A plain
    single-threaded ``HTTPServer`` — never ``ThreadingHTTPServer`` (AT-D15T1-10 single-threaded
    HARD-GATE)."""
    server = HTTPServer((host, port), _make_handler(gateway, allowed_origins))
    bound_host, bound_port = cast(str, server.server_address[0]), server.server_address[1]
    return server, f"http://{bound_host}:{bound_port}"


def serve_gateway_edge() -> None:
    """Blocking runnable entrypoint for the served gateway edge (B5-2 Guard Evolution — the
    single blessed serve loop of this module).

    Composes the server via the env seam ``build_gateway_edge_server_from_env``
    (``api_gateway/main.py``) and serves it on the CALLING thread:

    * inactive composition (any required real transport unset) → deterministic ``RuntimeError``
      — fail closed; no socket was bound and nothing is served;
    * malformed composition config → ``ValueError`` from the seam (inherited, fail closed,
      raised before any socket bind);
    * active → ``server.serve_forever()`` exactly once on a single-threaded plain ``HTTPServer``
      (AT-D15T1-10: one server per operating-system process; no thread, daemon, subprocess,
      supervisor, or retry loop here), and ``server.server_close()`` ALWAYS runs in ``finally`` —
      ``KeyboardInterrupt`` and any serve-time exception propagate to the caller unswallowed.

    No overclaim: this makes the served edge RUNNABLE. It does not deploy or supervise it, prove
    a live production topology, terminate TLS, activate production, or close any B5 blocker.
    """
    # Function-local absolute import mirrors the 07E-1 / B5-2 serve precedents (the composition
    # root is imported lazily at call time; the adapter module stays import-light and cycle-free).
    from api_gateway.main import build_gateway_edge_server_from_env

    composed = build_gateway_edge_server_from_env()
    if composed is None:
        raise RuntimeError(
            "serve_gateway_edge: gateway-edge composition is INACTIVE — the required real transports "
            "(SP2_GW_AUTH_ROUTER_BASE_URL / SP2_GW_CONTROL_READ_BASE_URL / SP2_GW_DB_ROUTER_BASE_URL) "
            "are not all set (fail closed: no socket bound, nothing served)"
        )
    server_obj, _base_url = composed
    server = cast(HTTPServer, server_obj)
    try:
        server.serve_forever()
    finally:
        server.server_close()
