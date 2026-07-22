"""Served northbound API Gateway HTTP edge (stdlib http.server) — Served API Gateway Edge V1 (+ W1b import).

The single thin, single-threaded serving edge that converts a real HTTP request into the
existing framework-neutral Gateway core (IC-010 §A/§N) and back. It owns TRANSPORT ONLY:
a closed route + method allowlist, conservative request bounds, correlation accept/mint/echo,
an exact-origin CORS allowlist, and the mapping ``InboundRequest`` -> ``Gateway.handle`` ->
``serialize_portal_dto`` (success) / a fixed safe status (denial). It does NOT authenticate,
mint principals, authorize, classify routes for business, select tenants, route databases,
compose portal DTOs, decide audit, or run business logic — every one of those stays inside
the composed Gateway core it fronts (``ports.py`` / ``gateway.py`` / ``dispatch.py`` /
``portal.py``). The edge calls exactly ONE thing: ``Gateway.handle`` (one shared call site).

Exposed surface: the business routes ``GET /memberships`` (self-scoped MembershipsForPrincipal),
``POST /import/<source_ref>`` (the bounded, traversal-safe served import route — W1b), and the
two D-42 CLM tenant Startup routes ``GET/PATCH /tenant/startups/<startup_ref>`` (bounded,
traversal-safe, single-segment — IC-010 CLM section), the operational ``GET /health`` /
``GET /readiness``, and the matching CORS preflights (``OPTIONS`` per business target). Every
other path is ``404`` route-not-exposed and every non-allowed method is ``405`` — decided BEFORE
the core is ever reached. ``Gateway.handle`` is invoked through exactly ONE shared call site and
at most once per accepted business request; operational routes, preflights, and pre-core
rejections never reach it. Every route is body-less (``_MAX_BODY_BYTES = 0``) EXCEPT the served
tenant Startup PATCH, whose body is bounded at exactly ``_MAX_PATCH_BODY_BYTES = 16384`` bytes
(IC-010 CLM) and is forwarded raw to the core (never interpreted at the edge).

The served import route is denial-fidelity terminal (W1b, IC-010 §L/§V.2): a success serializes
ONLY a real, core-composed ``ImportResultDTO``; a genuine ``status >= 400`` is preserved with an
empty body; every residual non-error result that is NOT an ``ImportResultDTO`` — including a
port-absent ``ImportInitiationDTO`` accepted-initiation envelope — fails closed to ``503`` with an
empty body. The edge never serializes an ``ImportInitiationDTO`` on the served import route.

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
from api_gateway.portal import ImportResultDTO, TenantStartupDetailDTO, serialize_portal_dto
from api_gateway.readiness import liveness, readiness

# --- transport constants (conservative, review-pinned; test-pinned by the boundary guard) ---
_CORRELATION_HEADER = "x-correlation-id"
_TENANT_HEADER = "X-Tenant-Id"  # the only recognized carrier header (case-insensitive, IC-010 §E)

_MAX_CORRELATION_LEN = 128  # accept a bounded opaque id; longer/unsafe -> mint a fresh one
_SAFE_CORRELATION = re.compile(r"[A-Za-z0-9._\-]+")  # anti-log-injection / anti-spoof charset

_MAX_REQUEST_TARGET_BYTES = 2048  # request-target (path + any query) byte cap
_MAX_HEADER_COUNT = 64  # header-count cap (below the stdlib 100-header parse limit)
_MAX_TOTAL_HEADER_BYTES = 16384  # 16 KiB total accepted header bytes
_MAX_BODY_BYTES = 0  # both business routes (GET /memberships, POST /import/<ref>) are body-less; any non-empty body is rejected
_MAX_DRAIN_BYTES = 65536  # bounded read of a rejected body so the response delivers without a reset

# The closed transport route allowlist: exact request-target -> the methods it exposes. Any
# other target is 404 (route not exposed); a non-listed method on a listed target is 405.
# Everything here is decided BEFORE the Gateway core is invoked. The parameterized import
# route (below) is deliberately NOT here — it carries a source_ref and is matched separately.
_EXPOSED_ROUTES: Mapping[str, "frozenset[str]"] = {
    "/memberships": frozenset({"GET", "OPTIONS"}),
    "/health": frozenset({"GET"}),
    "/readiness": frozenset({"GET"}),
}

# --- the bounded served import route (W1b) — NOT a static allowlist entry (it carries a
# parameter) and NOT a generic router. A dedicated matcher recognizes exactly
# ``/import/<source_ref>`` where source_ref is a bounded, traversal-safe suffix (PRD §4.1).
_IMPORT_PREFIX = "/import/"  # the served import target is exactly this prefix + a valid source_ref suffix
_MAX_SOURCE_REF_BYTES = 512  # the source_ref suffix byte cap (1..512 UTF-8 bytes)
_IMPORT_TARGET_METHODS = frozenset({"POST", "OPTIONS"})  # the ONLY methods the import target exposes
_OPERATION_KEY_HEADER = "x-operation-key"  # forwarded (when present) for the core's operation-level idempotency (D-20)
# Each source_ref segment: an alnum lead then alnum/dot/dash/underscore. No empty / "." / ".." /
# percent-encoded / backslash / query / fragment form can match — traversal- and injection-safe by
# construction (a "." or ".." segment fails the alnum-lead rule; "%", "\\", "?", "#" are outside the charset).
_SAFE_IMPORT_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\-]*")


# --- the bounded served tenant Startup routes (D-42 CLM Stage B) — NOT static allowlist entries
# (they carry a parameter) and NOT a generic router. A dedicated matcher recognizes exactly
# ``/tenant/startups/<startup_ref>`` where startup_ref is a bounded, traversal-safe, SINGLE-SEGMENT
# suffix (IC-010 CLM: opaque, 1..512 UTF-8 bytes; never a tenant or database selector).
_TENANT_STARTUP_PREFIX = "/tenant/startups/"
_MAX_STARTUP_REF_BYTES = 512  # the startup_ref suffix byte cap (1..512 UTF-8 bytes; IC-010 CLM)
_TENANT_STARTUP_METHODS = frozenset({"GET", "PATCH", "OPTIONS"})  # the ONLY methods the tenant Startup target exposes
_MAX_PATCH_BODY_BYTES = 16384  # IC-010 CLM: the tenant Startup PATCH request body is bounded at 16384 bytes
# One single segment: an alnum lead then alnum/dot/dash/underscore/colon. No empty / "." / ".." /
# "/" / percent-encoded / backslash / query / fragment form can match — traversal- and
# injection-safe by construction (a "." or ".." segment fails the alnum-lead rule; "%", "\\",
# "/", "?", "#" are outside the charset; ":" admits the tenant record-reference shape).
_SAFE_STARTUP_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:\-]*")


def _is_valid_tenant_startup_target(target: str) -> bool:
    """True iff ``target`` is a bounded, traversal-safe ``/tenant/startups/<startup_ref>`` served
    tenant Startup target (D-42 CLM; IC-010 CLM section). ``startup_ref`` is the exact request-target
    suffix after ``/tenant/startups/``: ONE segment of 1..512 UTF-8 bytes matching
    ``[A-Za-z0-9][A-Za-z0-9._:-]*``. Every bare / empty / multi-segment / ``.`` / ``..`` /
    percent-encoded / backslash / query / fragment form fails to match and is ``404`` pre-core. A
    bounded parameterized matcher — NEVER a generic wildcard or prefix router (the static allowlist
    stays closed to {/memberships, /health, /readiness})."""
    if not target.startswith(_TENANT_STARTUP_PREFIX):
        return False
    suffix = target[len(_TENANT_STARTUP_PREFIX) :]
    if not 1 <= len(suffix.encode("utf-8")) <= _MAX_STARTUP_REF_BYTES:
        return False
    return _SAFE_STARTUP_REF.fullmatch(suffix) is not None


def _is_valid_import_target(target: str) -> bool:
    """True iff ``target`` is a bounded, traversal-safe ``/import/<source_ref>`` served import target
    (W1b; PRD §4.1). ``source_ref`` is the exact request-target suffix after ``/import/``: 1..512 UTF-8
    bytes of one or more ``/``-separated segments, each ``[A-Za-z0-9][A-Za-z0-9._-]*``. Every bare / empty /
    ``.`` / ``..`` / percent-encoded / backslash / query / fragment form fails to match and is ``404``
    pre-core. A bounded parameterized matcher — NEVER a generic wildcard or prefix router (the static
    allowlist stays closed to {/memberships, /health, /readiness})."""
    if not target.startswith(_IMPORT_PREFIX):
        return False
    suffix = target[len(_IMPORT_PREFIX) :]
    if not 1 <= len(suffix.encode("utf-8")) <= _MAX_SOURCE_REF_BYTES:
        return False
    return all(_SAFE_IMPORT_SEGMENT.fullmatch(segment) for segment in suffix.split("/"))


def _make_handler(gateway: Gateway, allowed_origins: Tuple[str, ...]) -> "type[BaseHTTPRequestHandler]":
    """Build the request handler bound to a composed ``Gateway`` and the exact-origin CORS
    allowlist. The handler owns transport only; it calls ``gateway.handle`` (through the single
    shared ``_invoke_core`` site) exactly once for a valid ``/memberships`` or ``/import`` business
    request and never for a rejection, preflight, or operational route."""

    class _GatewayEdgeHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            self._dispatch("GET")

        def do_POST(self) -> None:  # noqa: N802 (http.server API)
            # POST is a served method for the bounded /import/<source_ref> route only; _dispatch
            # yields 405 on a POST to any other listed target and 404 on an unlisted one (pre-core).
            self._dispatch("POST")

        def do_PATCH(self) -> None:  # noqa: N802 (http.server API)
            # PATCH is a served method for the bounded /tenant/startups/<startup_ref> route only
            # (D-42 CLM); _dispatch yields 405 on a PATCH to any other listed target and 404 on an
            # unlisted one (pre-core).
            self._dispatch("PATCH")

        def do_OPTIONS(self) -> None:  # noqa: N802 (http.server API)
            self._dispatch("OPTIONS")

        def _method_not_allowed(self) -> None:
            # Route every other method through the same dispatch so a listed target yields 405
            # and an unlisted target yields 404 (both pre-core, fixed status, empty body).
            self._dispatch(self.command)

        # do_GET / do_POST / do_PATCH / do_OPTIONS are the served handlers; every other method
        # dispatches by its real command name and resolves to 405 (listed target) or 404 (unlisted).
        do_PUT = do_DELETE = do_HEAD = _method_not_allowed

        def _dispatch(self, method: str) -> None:
            correlation_id = self._correlation_id()
            origin = self.headers.get("Origin")
            target = self.path  # exact request-target: a stray ?query never equals a listed route or a valid business target
            # Per-route body budget (D-42 CLM): ONLY the served tenant Startup PATCH accepts a body,
            # bounded at exactly 16384 bytes (IC-010 CLM); every other route stays body-less.
            patch_target = _is_valid_tenant_startup_target(target) and method == "PATCH"
            body_budget = _MAX_PATCH_BODY_BYTES if patch_target else _MAX_BODY_BYTES
            # Transport bounds first (pre-core): request target, header count/bytes, body budget.
            bounds_status = self._bounds_violation(body_budget)
            if bounds_status is not None:
                # Drain the declared body (bounded, discarded — never interpreted) so the rejection
                # response delivers cleanly on the connection instead of resetting the peer.
                self._drain_body()
                self._respond(bounds_status, correlation_id, origin)
                return
            patch_body: Optional[bytes] = None
            if patch_target:
                # Read the bounded PATCH body EXACTLY (already <= the budget per the bounds check);
                # the bytes are forwarded raw to the core and never interpreted at the edge.
                patch_body = self._read_bounded_body(body_budget)
                if patch_body is None:
                    self._respond(400, correlation_id, origin)  # malformed transport body (pre-core)
                    return
            else:
                # Drain any declared request body (bounded, discarded — never interpreted) so a
                # rejection response delivers cleanly on the connection.
                self._drain_body()
            allowed_methods = _EXPOSED_ROUTES.get(target)
            if allowed_methods is not None:
                # The closed static allowlist: /memberships (business) + /health + /readiness (operational).
                if method not in allowed_methods:
                    self._respond(405, correlation_id, origin)  # method not allowed (pre-core)
                    return
                if method == "OPTIONS":
                    # CORS preflight for /memberships: 204, GET+OPTIONS, exact-origin headers only when
                    # the origin is allowlisted. The Gateway core is NEVER invoked for a preflight.
                    self._respond(
                        204,
                        correlation_id,
                        origin,
                        preflight=True,
                        cors_methods="GET, OPTIONS",
                        cors_headers="Authorization, x-correlation-id",
                    )
                    return
                if target == "/health":
                    self._respond_json(200, json.dumps(liveness()).encode("utf-8"), correlation_id, origin)
                    return
                if target == "/readiness":
                    # In-process liveness/state only — NOT a full production-readiness proof.
                    self._respond_json(200, json.dumps(readiness()).encode("utf-8"), correlation_id, origin)
                    return
                self._handle_memberships(correlation_id, origin)
                return
            if _is_valid_import_target(target):
                # The bounded /import/<source_ref> business route (W1b): POST executes, OPTIONS preflights.
                if method not in _IMPORT_TARGET_METHODS:
                    self._respond(405, correlation_id, origin)  # method not allowed (pre-core)
                    return
                if method == "OPTIONS":
                    # CORS preflight for /import: 204, POST+OPTIONS. The Gateway core is NEVER invoked
                    # for a preflight; x-operation-key is added to the allowed request headers.
                    self._respond(
                        204,
                        correlation_id,
                        origin,
                        preflight=True,
                        cors_methods="POST, OPTIONS",
                        cors_headers="Authorization, x-correlation-id, x-operation-key",
                    )
                    return
                self._handle_import(correlation_id, origin)
                return
            if _is_valid_tenant_startup_target(target):
                # The bounded /tenant/startups/<startup_ref> business routes (D-42 CLM): GET reads,
                # PATCH executes the bounded update, OPTIONS preflights.
                if method not in _TENANT_STARTUP_METHODS:
                    self._respond(405, correlation_id, origin)  # method not allowed (pre-core)
                    return
                if method == "OPTIONS":
                    # CORS preflight for the tenant Startup routes: 204, GET+PATCH+OPTIONS. The
                    # Gateway core is NEVER invoked for a preflight; content-type is added to the
                    # allowed request headers (the PATCH body is application/json).
                    self._respond(
                        204,
                        correlation_id,
                        origin,
                        preflight=True,
                        cors_methods="GET, PATCH, OPTIONS",
                        cors_headers="Authorization, x-correlation-id, content-type",
                    )
                    return
                self._handle_tenant_startup(method, correlation_id, origin, patch_body)
                return
            self._respond(404, correlation_id, origin)  # route not exposed (pre-core)

        def _handle_memberships(self, correlation_id: str, origin: Optional[str]) -> None:
            # The self-scoped MembershipsForPrincipal business path: build the typed InboundRequest and
            # invoke the core through the ONE shared call site. The edge validates nothing about
            # identity/tenant/route beyond transport.
            request = InboundRequest(
                method="GET",
                path="/memberships",
                host=self.headers.get("Host", "") or "",
                headers=self._forwarded_headers(correlation_id),
                authorization=self.headers.get("Authorization"),
            )
            response = self._invoke_core(request)
            if response.status == 200 and response.portal_dto is not None:
                # Success bodies come ONLY from the core-owned serializer (catalogue-closed).
                self._respond_json(200, serialize_portal_dto(response.portal_dto), correlation_id, origin)
                return
            # Every denial/unavailable -> fixed status, EMPTY body, no detail (fail closed).
            status = response.status if response.status >= 400 else 503
            self._respond(status, correlation_id, origin)

        def _handle_import(self, correlation_id: str, origin: Optional[str]) -> None:
            # The bounded /import/<source_ref> business path (W1b): build the typed InboundRequest from
            # the validated request target + the existing bearer, and invoke the core through the ONE
            # shared call site. Tenant/actor authority stays SIGNED-CONTEXT owned inside the core — the
            # edge derives it from nothing (never the path, body, query, cookie, or carrier). The optional
            # x-operation-key is forwarded for the core's operation-level idempotency.
            request = InboundRequest(
                method="POST",
                path=self.path,
                host=self.headers.get("Host", "") or "",
                headers=self._import_forwarded_headers(correlation_id),
                authorization=self.headers.get("Authorization"),
            )
            response = self._invoke_core(request)
            # Denial-fidelity terminal (PRD §6.4): only a real, core-composed ImportResultDTO success
            # serializes; a genuine >=400 status is preserved (empty body); every residual non-error
            # result that is NOT an ImportResultDTO — including a port-absent ImportInitiationDTO envelope
            # — fails closed to 503 (empty body). The edge references ImportResultDTO ONLY for this type
            # check: it never constructs one and never serializes an ImportInitiationDTO on this route.
            if response.status == 200 and isinstance(response.portal_dto, ImportResultDTO):
                self._respond_json(200, serialize_portal_dto(response.portal_dto), correlation_id, origin)
                return
            status = response.status if response.status >= 400 else 503
            self._respond(status, correlation_id, origin)

        def _handle_tenant_startup(self, method: str, correlation_id: str, origin: Optional[str], patch_body: Optional[bytes]) -> None:
            # The bounded /tenant/startups/<startup_ref> business paths (D-42 CLM): build the typed
            # InboundRequest from the validated request target + the existing bearer, and invoke the
            # core through the ONE shared call site. Tenant/actor authority stays SIGNED-CONTEXT
            # owned inside the core — the edge derives it from nothing (never the path, body, query,
            # cookie, or carrier). The bounded PATCH body is forwarded raw; the core parses it.
            request = InboundRequest(
                method=method,
                path=self.path,
                host=self.headers.get("Host", "") or "",
                headers=self._forwarded_headers(correlation_id),
                authorization=self.headers.get("Authorization"),
                patch_body=patch_body,
            )
            response = self._invoke_core(request)
            # Denial-fidelity terminal (the W1b idiom; IC-010 §L/§V.2): only a real, core-composed
            # TenantStartupDetailDTO success serializes; a genuine >=400 status is preserved with an
            # empty body; every residual non-error result that is NOT a TenantStartupDetailDTO fails
            # closed to 503 (empty body). The edge references TenantStartupDetailDTO ONLY for this
            # type check: it never constructs one and never parses or references the update request
            # DTO (body parsing is core-owned).
            if response.status == 200 and isinstance(response.portal_dto, TenantStartupDetailDTO):
                self._respond_json(200, serialize_portal_dto(response.portal_dto), correlation_id, origin)
                return
            status = response.status if response.status >= 400 else 503
            self._respond(status, correlation_id, origin)

        def _read_bounded_body(self, budget: int) -> Optional[bytes]:
            # Read EXACTLY the declared Content-Length (already validated <= budget by the bounds
            # check). Missing/zero Content-Length yields the empty body (the core rejects it as
            # malformed, fail-closed); a short read is a malformed transport request (None -> 400).
            raw_len = self.headers.get("Content-Length")
            try:
                length = int(raw_len) if raw_len else 0
            except ValueError:
                return None
            if length <= 0:
                return b""
            if length > budget:
                return None  # defensive: the bounds check already rejected this pre-read
            body = self.rfile.read(length)
            if len(body) != length:
                return None
            return body

        def _invoke_core(self, request: InboundRequest) -> GatewayResponse:
            # The ONE shared Gateway-core invocation site for EVERY business route (Memberships + Import):
            # exactly one textual ``gateway.handle`` call in the whole module (IC-010 §A — the edge calls
            # exactly ONE thing). No loop, no retry, no DTO construction, no authentication, no database —
            # each accepted request reaches the core exactly once.
            return gateway.handle(request)

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

        def _import_forwarded_headers(self, correlation_id: str) -> Dict[str, str]:
            # The import route additionally forwards the optional x-operation-key carrier (references
            # only; bounded/minted INSIDE the core) on top of the base correlation + X-Tenant-Id
            # pass-through. Tenant authority is never derived from this or any other header at the edge.
            headers = self._forwarded_headers(correlation_id)
            operation_key = self.headers.get(_OPERATION_KEY_HEADER)
            if operation_key is not None:
                headers[_OPERATION_KEY_HEADER] = operation_key
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

        def _bounds_violation(self, body_budget: int = _MAX_BODY_BYTES) -> Optional[int]:
            if len(self.path.encode("utf-8")) > _MAX_REQUEST_TARGET_BYTES:
                return 413
            if len(self.headers) > _MAX_HEADER_COUNT:
                return 413
            if len(str(self.headers).encode("utf-8")) > _MAX_TOTAL_HEADER_BYTES:
                return 413
            if self.headers.get("Transfer-Encoding"):
                return 413  # chunked/streamed bodies are never accepted (bounded Content-Length only)
            raw_len = self.headers.get("Content-Length")
            if raw_len is not None:
                try:
                    length = int(raw_len)
                except ValueError:
                    return 400  # malformed transport request
                if length > body_budget:
                    return 413  # a body beyond the per-route budget (0 for every body-less route)
            return None

        def _respond(
            self,
            status: int,
            correlation_id: str,
            origin: Optional[str],
            *,
            preflight: bool = False,
            cors_methods: str = "GET, OPTIONS",
            cors_headers: str = "Authorization, x-correlation-id",
        ) -> None:
            # Fixed safe response, EMPTY body — the only shape for every denial/rejection/preflight.
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.send_header(_CORRELATION_HEADER, correlation_id)
            self._write_cors_headers(origin, preflight=preflight, cors_methods=cors_methods, cors_headers=cors_headers)
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

        def _write_cors_headers(
            self,
            origin: Optional[str],
            *,
            preflight: bool,
            cors_methods: str = "GET, OPTIONS",
            cors_headers: str = "Authorization, x-correlation-id",
        ) -> None:
            # Exact-origin allowlist only. A denied or absent origin receives NO CORS headers
            # (the browser blocks the response). NEVER a wildcard; NEVER credentialed CORS.
            if origin is None or origin not in allowed_origins:
                return
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "false")
            self.send_header("Vary", "Origin")
            if preflight:
                self.send_header("Access-Control-Allow-Methods", cors_methods)
                self.send_header("Access-Control-Allow-Headers", cors_headers)

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
