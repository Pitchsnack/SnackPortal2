"""Served northbound API Gateway HTTP edge (FastAPI/uvicorn) — Served API Gateway Edge V1 (+ W1b import).

The single thin serving edge that converts a real HTTP request into the existing
framework-neutral Gateway core (IC-010 §A/§N) and back. It owns TRANSPORT ONLY:
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

Route-allowlist closure under FastAPI. The static allowlist ``_EXPOSED_ROUTES`` remains the
authority for the three unparameterized targets and their methods — the FastAPI routes are
REGISTERED FROM it, so the exposed surface cannot drift from the pinned dict. The two
parameterized business families are registered as dedicated bounded routes and are then
re-validated against the RAW request target by ``_is_valid_import_target`` /
``_is_valid_tenant_startup_target`` before the core is reached: the framework's path
converter decides only that a candidate reached the right handler, never that it is
acceptable. Redirect-slashes is DISABLED app-wide (``new_edge_app``) so no second spelling
of any path is ever served, and the OpenAPI/docs surface is disabled so the edge publishes
no machine-readable catalogue of itself.

The served import route is denial-fidelity terminal (W1b, IC-010 §L/§V.2): a success serializes
ONLY a real, core-composed ``ImportResultDTO``; a genuine ``status >= 400`` is preserved with an
empty body; every residual non-error result that is NOT an ``ImportResultDTO`` — including a
port-absent ``ImportInitiationDTO`` accepted-initiation envelope — fails closed to ``503`` with an
empty body. The edge never serializes an ``ImportInitiationDTO`` on the served import route.

Runtime: FastAPI served by the shared uvicorn runtime
(``shared.adapters.providers.asgi_runtime``), bound to ``127.0.0.1`` by default (TLS terminates
at a reverse proxy — deployment scope; this edge pins ``http`` at the internal seam). No
database or sibling-service import, no JWT/OIDC/crypto. Bearer-only (the ``Authorization``
header); no cookie authentication, so CSRF is not applicable to this V1, and forwarded
headers (``X-Forwarded-*``) are never trusted as a tenant selector or security decision.
Fail closed (IC-010 §L): every denial and unavailability carries a fixed status and NO
detail — never a provider body, exception text, stack, token, DSN, database identity, or
tenant topology. Success bodies are produced ONLY by the core-owned ``serialize_portal_dto``.
Request logging is fully disabled in the shared runtime (the migrated equivalent of the
stdlib edge's silenced ``log_message``). The blocking runnable ``serve_gateway_edge`` calls
``serve_forever`` exactly once and always closes the server in ``finally``.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Awaitable, Callable, Dict, Mapping, Optional, Tuple, cast

from fastapi import FastAPI, Request, Response

from api_gateway.gateway import Gateway
from api_gateway.models import GatewayResponse, InboundRequest
from api_gateway.portal import ImportResultDTO, TenantStartupDetailDTO, serialize_portal_dto
from api_gateway.readiness import liveness, readiness
from shared.adapters.providers.asgi_runtime import AsgiEdgeServer, build_asgi_server
from shared.adapters.providers.fastapi_edge import empty_response, new_edge_app

# --- transport constants (conservative, review-pinned; test-pinned by the boundary guard) ---
_CORRELATION_HEADER = "x-correlation-id"
_TENANT_HEADER = "X-Tenant-Id"  # the only recognized carrier header (case-insensitive, IC-010 §E)

_MAX_CORRELATION_LEN = 128  # accept a bounded opaque id; longer/unsafe -> mint a fresh one
_SAFE_CORRELATION = re.compile(r"[A-Za-z0-9._\-]+")  # anti-log-injection / anti-spoof charset

_MAX_REQUEST_TARGET_BYTES = 2048  # request-target (path + any query) byte cap
_MAX_HEADER_COUNT = 64  # header-count cap
_MAX_TOTAL_HEADER_BYTES = 16384  # 16 KiB total accepted header bytes
_MAX_BODY_BYTES = 0  # both business routes (GET /memberships, POST /import/<ref>) are body-less; any non-empty body is rejected

# The closed transport route allowlist: exact request-target -> the methods it exposes. Any
# other target is 404 (route not exposed); a non-listed method on a listed target is 405.
# Everything here is decided BEFORE the Gateway core is invoked, and the FastAPI routes for
# these three targets are REGISTERED FROM this dict so the served surface cannot drift from it.
# The parameterized import route (below) is deliberately NOT here — it carries a source_ref and
# is matched separately.
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

# The FastAPI path templates the two bounded parameterized families register under. They are
# reach-only: matching one merely routes a candidate to its handler, which then re-validates the
# RAW request target with the bounded matcher above before anything else happens.
_IMPORT_ROUTE_TEMPLATE = "/import/{source_ref:path}"
_TENANT_STARTUP_ROUTE_TEMPLATE = "/tenant/startups/{startup_ref}"


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


def _request_target(request: Request) -> str:
    """The RAW request-target (undecoded path plus any verbatim ``?query``).

    Every allowlist and bounded-matcher decision is made against THIS string, exactly as the
    pre-migration edge decided against ``self.path``. Using the raw target is load-bearing: a
    stray ``?query`` must never equal a listed route, and a percent-encoded traversal
    (``%2e%2e``, ``%2F``) must be judged as it arrived rather than after the framework has
    decoded it into something the matcher would accept.
    """
    raw_path = request.scope.get("raw_path")
    target = raw_path.decode("latin-1") if isinstance(raw_path, bytes) else request.url.path
    query = request.scope.get("query_string") or b""
    if query:
        target += "?" + query.decode("latin-1")
    return target


def _correlation_id(request: Request) -> str:
    """Accept a bounded, safe inbound correlation id; otherwise mint a fresh opaque one."""
    raw = request.headers.get(_CORRELATION_HEADER)
    if raw is not None:
        value = raw.strip()
        if 1 <= len(value) <= _MAX_CORRELATION_LEN and _SAFE_CORRELATION.fullmatch(value):
            return value
    # Missing / blank / oversized / unsafe -> mint a fresh opaque id (anti-spoof).
    return uuid.uuid4().hex


def _body_budget(target: str, method: str) -> int:
    """Per-route body budget (D-42 CLM): ONLY the served tenant Startup PATCH accepts a body,
    bounded at exactly 16384 bytes (IC-010 CLM); every other route stays body-less."""
    if method == "PATCH" and _is_valid_tenant_startup_target(target):
        return _MAX_PATCH_BODY_BYTES
    return _MAX_BODY_BYTES


def _bounds_violation(request: Request, target: str, body_budget: int) -> Optional[int]:
    """The pre-core transport bounds: request target, header count/bytes, transfer-encoding, body."""
    if len(target.encode("utf-8")) > _MAX_REQUEST_TARGET_BYTES:
        return 413
    raw_headers = request.scope.get("headers") or []
    if len(raw_headers) > _MAX_HEADER_COUNT:
        return 413
    # Total accepted header bytes, counted on the wire shape ("name: value\r\n" == 4 extra bytes).
    if sum(len(name) + len(value) + 4 for name, value in raw_headers) > _MAX_TOTAL_HEADER_BYTES:
        return 413
    if request.headers.get("Transfer-Encoding"):
        return 413  # chunked/streamed bodies are never accepted (bounded Content-Length only)
    raw_len = request.headers.get("Content-Length")
    if raw_len is not None:
        try:
            length = int(raw_len)
        except ValueError:
            return 400  # malformed transport request
        if length > body_budget:
            return 413  # a body beyond the per-route budget (0 for every body-less route)
    return None


def _write_cors_headers(
    response: Response,
    origin: Optional[str],
    allowed_origins: Tuple[str, ...],
    *,
    preflight: bool,
    cors_methods: str,
    cors_headers: str,
) -> None:
    """Exact-origin allowlist only. A denied or absent origin receives NO CORS headers
    (the browser blocks the response). NEVER a wildcard; NEVER credentialed CORS."""
    if origin is None or origin not in allowed_origins:
        return
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "false"
    response.headers["Vary"] = "Origin"
    if preflight:
        response.headers["Access-Control-Allow-Methods"] = cors_methods
        response.headers["Access-Control-Allow-Headers"] = cors_headers


def _preflight(request: Request, cors_methods: str, cors_headers: str) -> Response:
    """A CORS preflight answer: 204, EMPTY body. The Gateway core is NEVER invoked for a
    preflight — the allowed methods/headers are stashed for the transport middleware, which
    emits them only when the Origin is on the exact-origin allowlist."""
    request.state.cors_methods = cors_methods
    request.state.cors_headers = cors_headers
    request.state.preflight = True
    return empty_response(204)


def _make_app(gateway: Gateway, allowed_origins: Tuple[str, ...]) -> FastAPI:
    """Build the FastAPI app bound to a composed ``Gateway`` and the exact-origin CORS
    allowlist. The app owns transport only; it calls ``gateway.handle`` (through the single
    shared ``_invoke_core`` site) exactly once for a valid ``/memberships``, ``/import`` or
    tenant Startup business request and never for a rejection, preflight, or operational route."""
    app = new_edge_app(invalid_status=400, unavailable_status=503)

    def _invoke_core(request_model: InboundRequest) -> GatewayResponse:
        # The ONE shared Gateway-core invocation site for EVERY business route (Memberships +
        # Import + tenant Startup): exactly one textual ``gateway.handle`` call in the whole module
        # (IC-010 §A — the edge calls exactly ONE thing). No loop, no retry, no DTO construction, no
        # authentication, no database — each accepted request reaches the core exactly once.
        return gateway.handle(request_model)

    def _forwarded_headers(request: Request, correlation_id: str) -> Dict[str, str]:
        # Faithful, minimal pass-through: the edge OWNS x-correlation-id (accept/mint) and
        # forwards ONLY the recognized X-Tenant-Id carrier so the core can enforce isolation.
        # Cookies/query are prohibited carriers and are never populated; no X-Forwarded-* header
        # is trusted as a selector or a security decision.
        headers: Dict[str, str] = {_CORRELATION_HEADER: correlation_id}
        tenant = request.headers.get(_TENANT_HEADER)
        if tenant is not None:
            headers[_TENANT_HEADER] = tenant
        return headers

    def _import_forwarded_headers(request: Request, correlation_id: str) -> Dict[str, str]:
        # The import route additionally forwards the optional x-operation-key carrier (references
        # only; bounded/minted INSIDE the core) on top of the base correlation + X-Tenant-Id
        # pass-through. Tenant authority is never derived from this or any other header at the edge.
        headers = _forwarded_headers(request, correlation_id)
        operation_key = request.headers.get(_OPERATION_KEY_HEADER)
        if operation_key is not None:
            headers[_OPERATION_KEY_HEADER] = operation_key
        return headers

    def _terminal(response: GatewayResponse, expected: Optional[type]) -> Response:
        # The shared denial-fidelity terminal (W1b/D-42 idiom; IC-010 §L/§V.2): ONLY a real,
        # core-composed success DTO serializes; a genuine >=400 status is preserved with an empty
        # body; every residual non-error result fails closed to 503 (empty body). Success bodies
        # come ONLY from the core-owned serializer (catalogue-closed).
        #
        # ``expected`` is the route's pinned success DTO type where the contract names one — the
        # import route (ImportResultDTO) and the tenant Startup routes (TenantStartupDetailDTO),
        # whose terminals are type-exact so a port-absent envelope can never be served. It is None
        # for /memberships, whose success is any DTO the core composed for it (the pre-migration
        # ``portal_dto is not None`` test). The edge references those types ONLY for this check:
        # it constructs no DTO on any route.
        composed = response.portal_dto
        if response.status == 200 and composed is not None and (expected is None or isinstance(composed, expected)):
            return Response(status_code=200, content=serialize_portal_dto(composed), media_type="application/json")
        status = response.status if response.status >= 400 else 503
        return empty_response(status)

    @app.middleware("http")
    async def _transport(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        # The one pre-core transport gate: correlation accept/mint, request bounds, and the
        # exact-origin CORS emission that every response (including the 404/405 rejections
        # produced by the app's fail-closed handlers) passes back through.
        correlation_id = _correlation_id(request)
        origin = request.headers.get("Origin")
        target = _request_target(request)
        request.state.correlation_id = correlation_id
        request.state.raw_target = target
        request.state.preflight = False
        request.state.cors_methods = "GET, OPTIONS"
        request.state.cors_headers = "Authorization, x-correlation-id"
        bounds_status = _bounds_violation(request, target, _body_budget(target, request.method))
        if bounds_status is not None:
            # Rejected pre-core; the unread request body is discarded by the ASGI server.
            response = empty_response(bounds_status)
        elif request.scope.get("query_string"):
            # NO exposed target accepts a query string. The pre-migration edge got this for free
            # by matching the raw request target, so a query-bearing "/memberships?p=evil" never
            # equalled the listed "/memberships". FastAPI matches on the path alone, so the
            # property is restored here, once, for every route: 404 route-not-exposed, pre-core.
            response = empty_response(404)
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers[_CORRELATION_HEADER] = correlation_id
        # The preflight fields were seeded above and are only ever narrowed by an OPTIONS route,
        # so they are always present here regardless of which branch produced the response.
        _write_cors_headers(
            response,
            origin,
            allowed_origins,
            preflight=bool(request.state.preflight),
            cors_methods=request.state.cors_methods,
            cors_headers=request.state.cors_headers,
        )
        return response

    # --- the closed static allowlist: /memberships (business) + /health + /readiness (operational).
    # Each route is registered with EXACTLY the methods _EXPOSED_ROUTES names for it, so the served
    # surface is derived from the pinned dict and a non-listed method resolves to 405 pre-core.
    @app.api_route("/memberships", methods=sorted(_EXPOSED_ROUTES["/memberships"] - {"OPTIONS"}))
    async def memberships(request: Request) -> Response:
        # The self-scoped MembershipsForPrincipal business path: build the typed InboundRequest and
        # invoke the core through the ONE shared call site. The edge validates nothing about
        # identity/tenant/route beyond transport.
        return _terminal(
            _invoke_core(
                InboundRequest(
                    method="GET",
                    path="/memberships",
                    host=request.headers.get("Host", "") or "",
                    headers=_forwarded_headers(request, request.state.correlation_id),
                    authorization=request.headers.get("Authorization"),
                )
            ),
            None,  # /memberships succeeds with whatever approved DTO the core composed for it
        )

    @app.options("/memberships")
    async def memberships_preflight(request: Request) -> Response:
        return _preflight(request, "GET, OPTIONS", "Authorization, x-correlation-id")

    @app.api_route("/health", methods=sorted(_EXPOSED_ROUTES["/health"]))
    async def health(_request: Request) -> Response:
        return Response(status_code=200, content=json.dumps(liveness()).encode("utf-8"), media_type="application/json")

    @app.api_route("/readiness", methods=sorted(_EXPOSED_ROUTES["/readiness"]))
    async def readiness_route(_request: Request) -> Response:
        # In-process liveness/state only — NOT a full production-readiness proof.
        return Response(status_code=200, content=json.dumps(readiness()).encode("utf-8"), media_type="application/json")

    # --- the bounded /import/<source_ref> business route (W1b): POST executes, OPTIONS preflights.
    @app.post(_IMPORT_ROUTE_TEMPLATE)
    async def import_route(request: Request) -> Response:
        target = request.state.raw_target
        if not _is_valid_import_target(target):
            return empty_response(404)  # unbounded/traversal/percent-encoded form: route not exposed (pre-core)
        # Build the typed InboundRequest from the validated request target + the existing bearer, and
        # invoke the core through the ONE shared call site. Tenant/actor authority stays SIGNED-CONTEXT
        # owned inside the core — the edge derives it from nothing (never the path, body, query, cookie,
        # or carrier). The optional x-operation-key is forwarded for the core's operation-level idempotency.
        return _terminal(
            _invoke_core(
                InboundRequest(
                    method="POST",
                    path=target,
                    host=request.headers.get("Host", "") or "",
                    headers=_import_forwarded_headers(request, request.state.correlation_id),
                    authorization=request.headers.get("Authorization"),
                )
            ),
            ImportResultDTO,
        )

    @app.options(_IMPORT_ROUTE_TEMPLATE)
    async def import_preflight(request: Request) -> Response:
        if not _is_valid_import_target(request.state.raw_target):
            return empty_response(404)
        # x-operation-key is added to the allowed request headers for this target.
        return _preflight(request, "POST, OPTIONS", "Authorization, x-correlation-id, x-operation-key")

    # --- the bounded /tenant/startups/<startup_ref> business routes (D-42 CLM): GET reads,
    # PATCH executes the bounded update, OPTIONS preflights.
    @app.api_route(_TENANT_STARTUP_ROUTE_TEMPLATE, methods=["GET", "PATCH"])
    async def tenant_startup(request: Request) -> Response:
        target = request.state.raw_target
        if not _is_valid_tenant_startup_target(target):
            return empty_response(404)  # unbounded/traversal/percent-encoded form: route not exposed (pre-core)
        patch_body: Optional[bytes] = None
        if request.method == "PATCH":
            # The bounded PATCH body (already <= the 16384-byte budget per the pre-core bounds
            # check) is forwarded RAW to the core and never interpreted at the edge.
            patch_body = await request.body()
        # Tenant/actor authority stays SIGNED-CONTEXT owned inside the core — the edge derives it
        # from nothing (never the path, body, query, cookie, or carrier). The core parses the body.
        return _terminal(
            _invoke_core(
                InboundRequest(
                    method=request.method,
                    path=target,
                    host=request.headers.get("Host", "") or "",
                    headers=_forwarded_headers(request, request.state.correlation_id),
                    authorization=request.headers.get("Authorization"),
                    patch_body=patch_body,
                )
            ),
            TenantStartupDetailDTO,
        )

    @app.options(_TENANT_STARTUP_ROUTE_TEMPLATE)
    async def tenant_startup_preflight(request: Request) -> Response:
        if not _is_valid_tenant_startup_target(request.state.raw_target):
            return empty_response(404)
        # content-type is added to the allowed request headers (the PATCH body is application/json),
        # and the x-tenant-id match-only carrier is granted (TA-1 — IC-010 §E: the carrier is never
        # authorization; the core still match-or-rejects it per request).
        return _preflight(request, "GET, PATCH, OPTIONS", "Authorization, x-correlation-id, content-type, x-tenant-id")

    return app


def create_app_from_env() -> FastAPI:
    """The CANONICAL native ASGI application factory for the served northbound gateway edge.

    Run directly by the operator through the ASGI runtime's own command line::

        uvicorn api_gateway.adapters.providers.http_gateway_edge:create_app_from_env --factory ...

    Takes NO arguments: the listening host and port belong to the runtime process, not to the
    application, so this factory binds no socket and owns no address. It returns the composed
    ``FastAPI`` app and nothing else.

    ONE composition path (no second composition root): the ``Gateway`` and the exact-origin CORS
    allowlist are built by ``api_gateway.main.build_gateway_edge_deps_from_env`` — the SAME single
    env-parsing/transport-wiring function the compatibility ``build_gateway_edge_server_from_env``
    seam uses — and the app is built by the SAME ``_make_app``. The authenticator, router dispatch,
    control-plane read, audit sink, import initiation, and tenant Startup ports therefore have
    exactly one source of truth.

    Fail closed (IC-010 §L): the operator invoked this process deliberately, so an INACTIVE
    composition is a misconfiguration, not a no-op. If any of the three required real transports is
    unset/empty → ``RuntimeError``; a malformed transport URL → ``ValueError`` (inherited). There is
    deliberately NO fallback to an in-memory stub — a partially composed gateway must never front a
    standing backend.

    CORS is unchanged: ``SP2_GW_EDGE_ALLOWED_ORIGINS`` unset/empty yields an EMPTY allowlist, so
    every cross-origin request is denied. The allowlist stays exact-origin; no wildcard and no
    credentialed CORS is reachable from this path.
    """
    # Function-local absolute import mirrors the established composition-root idiom (the composition
    # root is imported lazily at call time; the adapter module stays import-light and cycle-free).
    from api_gateway.main import build_gateway_edge_deps_from_env

    deps = build_gateway_edge_deps_from_env()
    if deps is None:
        raise RuntimeError(
            "create_app_from_env: gateway-edge composition is INACTIVE — the required real transports "
            "(SP2_GW_AUTH_ROUTER_BASE_URL / SP2_GW_CONTROL_READ_BASE_URL / SP2_GW_DB_ROUTER_BASE_URL) "
            "are not all set (fail closed: no application composed)"
        )
    gateway, allowed_origins = deps
    return _make_app(gateway, allowed_origins)


def build_gateway_edge_server(
    gateway: Gateway,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    allowed_origins: Tuple[str, ...] = (),
) -> Tuple[AsgiEdgeServer, str]:
    """Build the served gateway-edge HTTP server bound to a composed ``Gateway``.

    ``port=0`` binds an ephemeral port. This factory constructs the server only — it does NOT
    start serving (the blocking runnable entrypoint is ``serve_gateway_edge``; tests may host
    the server directly via ``serve_forever``/``shutdown``/``server_close``). Returns
    ``(server, base_url)``."""
    return build_asgi_server(_make_app(gateway, allowed_origins), host, port)


def serve_gateway_edge() -> None:
    """Blocking runnable entrypoint for the served gateway edge (B5-2 Guard Evolution — the
    single blessed serve loop of this module).

    Composes the server via the env seam ``build_gateway_edge_server_from_env``
    (``api_gateway/main.py``) and serves it on the CALLING thread:

    * inactive composition (any required real transport unset) → deterministic ``RuntimeError``
      — fail closed; no socket was bound and nothing is served;
    * malformed composition config → ``ValueError`` from the seam (inherited, fail closed,
      raised before any socket bind);
    * active → ``server.serve_forever()`` exactly once on the calling thread (AT-D15T1-10: one
      server per operating-system process; no thread, daemon, subprocess, supervisor, or retry
      loop is created HERE — request concurrency is the ASGI runtime's own event loop), and
      ``server.server_close()`` ALWAYS runs in ``finally`` — ``KeyboardInterrupt`` and any
      serve-time exception propagate to the caller unswallowed.

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
    server = cast(AsgiEdgeServer, server_obj)
    try:
        server.serve_forever()
    finally:
        server.server_close()
