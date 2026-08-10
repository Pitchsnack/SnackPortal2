"""The PUBLIC tenant Startup edge (FastAPI/uvicorn) — Gateway-free MVP, Database-Router-owned.

This is the Gateway-free MVP's tenant data-plane boundary. It replaces two runtime hops with
one process: where the previous architecture ran

    browser -> API Gateway (8820) -> [HTTP] -> internal tenant Startup API (8004) -> executor

this edge is

    browser -> tenant Startup edge -> executor          (the executor is in-process)

**Why this is not the Gateway renamed.** It serves exactly one route family — the tenant
Startup records this very service already owns and executes. It classifies nothing, dispatches
nothing, forwards nothing, and knows of no other service's routes. Removing it does not orphan
another component; it just removes these two routes. A gateway is defined by standing *between*
a client and the service that owns the data; there is no "between" here.

**Security ownership (unambiguous, all in one place).**

* *authenticates* — the shared ``PublicBoundary`` kernel, via the injected IC-005 port (the
  Auth Router, over the existing internal transport). This service performs no JWT, JWKS,
  signature, issuer, or OIDC handling and imports no ``auth_router``;
* *authorizes tenant access* — the Auth Router's Stage-2 membership + readiness check, inside
  the same call (an unknown tenant and a non-member deny identically);
* *derives tenant identity* — ``PublicBoundary.require_tenant``, from the signed claim only;
* *owns HTTP validation* — this module (bounded matcher, bounded body, allowlisted field);
* *maps the public response shape* — ``database_router.portal`` (owner-resident IC-009-R1);
* *records audit evidence* — the injected ``EdgeAuditPort``, evidence-before-hand-back;
* *selects the physical tenant database* — ``TenantStartupOperations`` -> ``RoutedSessionProvider``
  (D-07: the Database Router alone resolves a database), from the derived tenant and nothing else.

**The load-bearing invariant.** ``target_tenant_ref`` and ``actor_ref`` are NOT request inputs
here. They do not appear in any accepted body, header, query, or path; they are produced from
``TrustedPrincipal`` immediately before the executor call. That is the structural difference
from the internal envelope edge this replaces, whose ``target_tenant_ref`` *was* a body field —
the exact hazard the previous removal experiment demonstrated. The MVP topology does not run
that internal edge at all, so the hazard is deleted rather than merely fronted.

Fail closed: every denial and unavailability carries a fixed status and an EMPTY body — never a
provider body, exception text, stack, token, connection material, database identity, or tenant
topology. Bearer-only (the ``Authorization`` header); no cookie authentication, so CSRF is not
applicable, and no forwarded header is ever trusted as a tenant selector.
"""

from __future__ import annotations

import json
import re
from typing import Optional, Tuple, cast

from fastapi import FastAPI, Request, Response

from database_router.portal import TenantStartupDetailDTO, parse_tenant_startup_update_request, serialize_portal_dto
from database_router.tenant_startup_ops import TenantStartupOperations, TenantStartupRecord
from shared.adapters.providers.asgi_runtime import AsgiEdgeServer, build_asgi_server
from shared.adapters.providers.fastapi_edge import empty_response, new_edge_app
from shared.adapters.providers.public_edge_transport import PublicEdgePolicy, install_public_transport, write_preflight
from shared.health import GlobalReadiness
from shared.public_edge import (
    ACTION_TENANT_STARTUP_READ,
    ACTION_TENANT_STARTUP_UPDATE,
    PublicBoundary,
    PublicBoundaryDenied,
    PublicRequest,
    TrustedPrincipal,
)

SERVICE = "tenant_startup_edge"

_TENANT_STARTUP_PREFIX = "/tenant/startups/"
_MAX_STARTUP_REF_BYTES = 512  # IC-010 CLM: the startup_ref suffix byte cap (1..512 UTF-8 bytes)
_MAX_PATCH_BODY_BYTES = 16384  # IC-010 CLM: the tenant Startup PATCH request body bound
_TENANT_STARTUP_ROUTE_TEMPLATE = "/tenant/startups/{startup_ref}"

# One single segment: an alnum lead then alnum/dot/dash/underscore/colon. No empty / "." / ".." /
# "/" / percent-encoded / backslash / query / fragment form can match — traversal- and
# injection-safe by construction.
_SAFE_STARTUP_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:\-]*")

_AUDIT_READ = ACTION_TENANT_STARTUP_READ
_AUDIT_UPDATE = ACTION_TENANT_STARTUP_UPDATE


def is_valid_tenant_startup_target(target: str) -> bool:
    """True iff ``target`` is a bounded, traversal-safe ``/tenant/startups/<startup_ref>``.

    ``startup_ref`` is the exact raw request-target suffix: ONE segment of 1..512 UTF-8 bytes
    matching ``[A-Za-z0-9][A-Za-z0-9._:-]*``. Every bare / empty / multi-segment / ``.`` /
    ``..`` / percent-encoded / backslash / query / fragment form fails to match and is ``404``
    before any authentication, executor call, or database session. A bounded parameterized
    matcher — never a generic wildcard or prefix router.
    """
    if not target.startswith(_TENANT_STARTUP_PREFIX):
        return False
    suffix = target[len(_TENANT_STARTUP_PREFIX) :]
    if not 1 <= len(suffix.encode("utf-8")) <= _MAX_STARTUP_REF_BYTES:
        return False
    return _SAFE_STARTUP_REF.fullmatch(suffix) is not None


def _body_budget(target: str, method: str) -> int:
    """Only the tenant Startup PATCH accepts a body; every other route stays body-less."""
    if method == "PATCH" and is_valid_tenant_startup_target(target):
        return _MAX_PATCH_BODY_BYTES
    return 0


def _liveness() -> bytes:
    return json.dumps({"service": SERVICE, "status": "alive"}).encode("utf-8")


def _readiness() -> bytes:
    # Operational status only; never a database name, tenant identity/count, or topology.
    return json.dumps({"service": SERVICE, "state": GlobalReadiness.READY.value}).encode("utf-8")


def _detail(record: TenantStartupRecord) -> TenantStartupDetailDTO:
    """Compose the owner-resident IC-009-R1 DTO from the executor's typed record.

    Composition, never relay: the provenance triple is supplied by the DTO's own defaults and
    the five bounded record fields are copied field-by-field. No executor row, dictionary, or
    envelope reaches the wire.
    """
    return TenantStartupDetailDTO(
        record_ref=record.record_ref,
        display_name=record.display_name,
        short_description=record.short_description,
        investment_stage=record.investment_stage,
        lineage_reference=record.lineage_reference,
    )


def make_app(ops: TenantStartupOperations, boundary: PublicBoundary, allowed_origins: Tuple[str, ...] = ()) -> FastAPI:
    """Build the public tenant Startup application bound to a composed executor + boundary."""
    app = new_edge_app(invalid_status=400, unavailable_status=503)
    install_public_transport(
        app,
        PublicEdgePolicy(
            allowed_origins=allowed_origins,
            body_budget=_body_budget,
            default_cors_methods="GET, PATCH, OPTIONS",
            default_cors_headers="Authorization, x-correlation-id, content-type, x-tenant-id",
        ),
    )

    def _admit(request: Request) -> Tuple[TrustedPrincipal, str]:
        """Authenticate, then bind exactly one authenticated active tenant.

        The ONE admission call site for every business route on this edge. Note what is NOT
        passed to ``PublicRequest``: no body, no query, no cookies. Those channels are
        prohibited tenant carriers, and withholding them makes it structurally impossible for
        the kernel to read one.
        """
        principal = boundary.admit(
            PublicRequest(
                method=request.method,
                path=request.state.raw_target,
                host=request.headers.get("Host", "") or "",
                headers=dict(request.headers),
                authorization=request.headers.get("Authorization"),
            ),
            request.state.correlation_id,
        )
        return principal, boundary.require_tenant(principal)

    @app.api_route(_TENANT_STARTUP_ROUTE_TEMPLATE, methods=["GET", "PATCH"])
    async def tenant_startup(request: Request) -> Response:
        target = request.state.raw_target
        if not is_valid_tenant_startup_target(target):
            return empty_response(404)  # unbounded/traversal/percent-encoded form: route not exposed
        startup_ref = target[len(_TENANT_STARTUP_PREFIX) :]

        # Authentication precedes everything the request can influence. An anonymous or
        # unauthorized caller's PATCH body is never even read, so it can learn nothing about
        # whether its body was well-formed, and no tenant session is opened on its behalf.
        try:
            principal, tenant_ref = _admit(request)
        except PublicBoundaryDenied as denied:
            return empty_response(denied.http_status)

        # Bounded by the transport gate before the handler ran (16384 bytes for this route).
        raw_body: Optional[bytes] = await request.body() if request.method == "PATCH" else None

        try:
            if request.method == "PATCH":
                try:
                    update = parse_tenant_startup_update_request(raw_body or b"")
                except ValueError:
                    # Fail closed with NO partial write and no executor call.
                    return empty_response(403)
                record = ops.update(
                    tenant_ref=tenant_ref,
                    startup_ref=startup_ref,
                    short_description=update.short_description,
                    correlation_id=principal.correlation_id,
                    actor_ref=principal.principal_ref,
                )
            else:
                record = ops.read(
                    tenant_ref=tenant_ref,
                    startup_ref=startup_ref,
                    correlation_id=principal.correlation_id,
                    actor_ref=principal.principal_ref,
                )
        except Exception:
            # Any routing/session/executor failure -> fixed 503, empty body. The executor rolled
            # back, so no partial write survives, and nothing about the failure is disclosed.
            return empty_response(503)

        if record is None:
            # Unknown startup_ref within the bound tenant database (IC-002 not-found): no
            # cross-tenant existence is derivable, no audit success event, no body.
            return empty_response(404)

        # Evidence before hand-back: a success is never returned unless its references-only
        # audit event was accepted. A terminal sink failure collapses to 503.
        try:
            boundary.emit(
                _AUDIT_UPDATE if request.method == "PATCH" else _AUDIT_READ,
                "success",
                principal.correlation_id,
                actor_ref=principal.principal_ref,
                tenant_ref=tenant_ref,
                record_ref=startup_ref,
            )
        except PublicBoundaryDenied as denied:
            return empty_response(denied.http_status)

        return Response(status_code=200, content=serialize_portal_dto(_detail(record)), media_type="application/json")

    @app.options(_TENANT_STARTUP_ROUTE_TEMPLATE)
    async def tenant_startup_preflight(request: Request) -> Response:
        if not is_valid_tenant_startup_target(request.state.raw_target):
            return empty_response(404)
        return write_preflight(request, "GET, PATCH, OPTIONS", "Authorization, x-correlation-id, content-type, x-tenant-id")

    @app.get("/health")
    async def health(_request: Request) -> Response:
        return Response(status_code=200, content=_liveness(), media_type="application/json")

    @app.get("/readiness")
    async def readiness_route(_request: Request) -> Response:
        return Response(status_code=200, content=_readiness(), media_type="application/json")

    return app


def create_app_from_env() -> FastAPI:
    """The native ASGI application factory for the public tenant Startup edge.

    Run directly by the operator through the ASGI runtime's own command line::

        uvicorn database_router.adapters.providers.http_public_startup_edge:create_app_from_env --factory ...

    Takes NO arguments: the listening host and port belong to the runtime process, so this
    factory binds no socket and owns no address.

    ONE composition path: the executor and the public boundary are built by
    ``database_router.main.build_public_startup_edge_deps_from_env`` — the same single
    env-parsing function every other entry point uses.

    Fail closed: the operator invoked this process deliberately, so an INACTIVE composition is
    a misconfiguration, not a no-op. Any required selector unset/empty -> ``RuntimeError``; a
    malformed selector -> ``ValueError`` (inherited). There is deliberately NO fallback to an
    unauthenticated edge, an in-memory double, or a partial composition: a public edge that
    cannot authenticate must never bind.
    """
    from database_router.main import build_public_startup_edge_deps_from_env

    deps = build_public_startup_edge_deps_from_env()
    if deps is None:
        raise RuntimeError(
            "create_app_from_env: public tenant Startup edge composition is INACTIVE — the required "
            "selectors (SP2_DBR_ROUTING_READ_BASE_URL / SP2_EDGE_AUTH_ROUTER_BASE_URL) are not all set "
            "(fail closed: no application composed)"
        )
    ops, boundary, allowed_origins = deps
    return make_app(ops, boundary, allowed_origins)


def build_public_startup_edge_server(
    ops: TenantStartupOperations,
    boundary: PublicBoundary,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    allowed_origins: Tuple[str, ...] = (),
) -> Tuple[AsgiEdgeServer, str]:
    """Construct the public tenant Startup HTTP server. ``port=0`` binds an ephemeral port.

    Constructs only — it does not serve. Returns ``(server, base_url)``.
    """
    return build_asgi_server(make_app(ops, boundary, allowed_origins), host, port)


def serve_public_startup_edge() -> None:
    """Blocking runnable entrypoint for the public tenant Startup edge.

    Composes via ``build_public_startup_edge_server_from_env`` (``database_router/main.py``)
    and serves on the CALLING thread: an inactive composition raises ``RuntimeError`` (no
    socket bound, nothing served); an active one calls ``serve_forever`` exactly once and
    always closes the server in ``finally``.
    """
    from database_router.main import build_public_startup_edge_server_from_env

    composed = build_public_startup_edge_server_from_env()
    if composed is None:
        raise RuntimeError(
            "serve_public_startup_edge: composition is INACTIVE — the required selectors are not all set "
            "(fail closed: no socket bound, nothing served)"
        )
    server_obj, _base_url = composed
    server = cast(AsgiEdgeServer, server_obj)
    try:
        server.serve_forever()
    finally:
        server.server_close()


__all__ = [
    "SERVICE",
    "build_public_startup_edge_server",
    "create_app_from_env",
    "is_valid_tenant_startup_target",
    "make_app",
    "serve_public_startup_edge",
]
