"""The PUBLIC workspace edge (FastAPI/uvicorn) — Gateway-free MVP, Control-Plane-owned.

Serves exactly one business route, ``GET /memberships``: the self-scoped IC-002
MembershipsForPrincipal enumeration that drives the workspace switcher. The data is
Control-DB data this service already owns, so under the Gateway-free MVP this service serves
it directly:

    browser -> API Gateway (8820) -> [HTTP] -> internal Control-Plane read (8003)     (before)
    browser -> workspace edge -> ControlStore unit of work                            (after)

**Why this is not the Gateway renamed.** One route family, owned by the service that owns the
records behind it. It classifies nothing, dispatches nothing, and forwards nothing.

**The load-bearing invariant.** The internal read dispatcher answers
``GET /memberships?p=<principal_ref>`` — the subject comes from a QUERY PARAMETER, and that
edge performs no authentication. This edge never exposes that parameter: the subject is
``TrustedPrincipal.principal_ref`` and nothing else, and any non-empty query string is
refused ``404`` by the shared transport gate before a handler runs. Actor and subject are
therefore always the same authenticated principal; there is no "on behalf of" form and no way
to ask for one. Note which of those two facts is load-bearing: the subject would still be the
authenticated principal even if the query reached the handler, because no handler reads a query
parameter — the rejection is defence-in-depth, not the control (see mutation M6).

**Per-request unit of work is preserved.** Each served request opens its own fresh
``ControlStore`` unit of work and releases it (rollback + close) before the response is
written. No store is cached, shared, or carried across requests.

Fail closed: every denial and unavailability carries a fixed status and an EMPTY body — never
a provider body, exception text, stack, token, connection material, database identity, or
tenant topology. Bearer-only; no cookie authentication, so CSRF is not applicable.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, List, Tuple, cast

from fastapi import FastAPI, Request, Response

from control_plane.portal import MembershipEntryDTO, WorkspaceMembershipDTO, compose_display_ref, serialize_portal_dto
from control_plane.read_api import ControlPlaneReadService
from shared.adapters.providers.asgi_runtime import AsgiEdgeServer, build_asgi_server
from shared.adapters.providers.fastapi_edge import empty_response, new_edge_app
from shared.adapters.providers.public_edge_transport import PublicEdgePolicy, install_public_transport, write_preflight
from shared.health import GlobalReadiness
from shared.public_edge import (
    ACTION_WORKSPACE_MEMBERSHIPS_READ,
    PublicBoundary,
    PublicBoundaryDenied,
    PublicRequest,
    TrustedPrincipal,
)

if TYPE_CHECKING:  # typing only — no composition import at runtime module load
    from control_plane.main import ControlPlane

SERVICE = "workspace_edge"

_MEMBERSHIPS_PATH = "/memberships"


def _body_budget(_target: str, _method: str) -> int:
    """Every route on this edge is body-less; any non-empty body is refused pre-handler."""
    return 0


def _liveness() -> bytes:
    return json.dumps({"service": SERVICE, "status": "alive"}).encode("utf-8")


def _readiness() -> bytes:
    # Operational status only; never a database name, tenant identity/count, or topology.
    return json.dumps({"service": SERVICE, "state": GlobalReadiness.READY.value}).encode("utf-8")


def _raw_headers(request: Request) -> List[Tuple[str, str]]:
    """The raw ASGI header pairs, duplicates preserved.

    Starlette's ``Headers`` is a multi-value mapping, so ``dict(request.headers)`` silently
    discards every repeat of a name. The kernel needs to see repeats — two ``X-Tenant-Id``
    values in one request is exactly the straddle it must reject.
    """
    return [(name.decode("latin-1"), value.decode("latin-1")) for name, value in (request.scope.get("headers") or [])]


def _compose(rows: object) -> WorkspaceMembershipDTO:
    """Compose the IC-009-R1 DTO from the read service's typed enumeration.

    Composition, never relay: each entry is rebuilt field-by-field and ``display_ref`` is
    derived here. A malformed or unexpected shape raises, and the caller fails closed — an
    unapproved dictionary can never reach the wire.
    """
    if not isinstance(rows, dict):
        raise ValueError("membership enumeration must be a mapping")
    records = rows.get("memberships")
    if not isinstance(records, list):
        raise ValueError("membership enumeration must carry a list")
    entries = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("membership record must be a mapping")
        tenant_id = record.get("tenant_id")
        role = record.get("role")
        if not isinstance(tenant_id, str) or not isinstance(role, str):
            raise ValueError("membership record must carry string tenant_id and role")
        entries.append(MembershipEntryDTO(tenant_id=tenant_id, role=role, display_ref=compose_display_ref(tenant_id)))
    return WorkspaceMembershipDTO(memberships=tuple(entries))


def make_app(control_plane: "ControlPlane", boundary: PublicBoundary, allowed_origins: Tuple[str, ...] = ()) -> FastAPI:
    """Build the public workspace application bound to a composed ControlPlane + boundary."""
    app = new_edge_app(invalid_status=400, unavailable_status=503)
    install_public_transport(
        app,
        PublicEdgePolicy(
            allowed_origins=allowed_origins,
            body_budget=_body_budget,
            default_cors_methods="GET, OPTIONS",
            default_cors_headers="Authorization, x-correlation-id",
        ),
    )

    def _admit(request: Request) -> TrustedPrincipal:
        """The ONE admission call site. No body, query, or cookies are handed to the kernel."""
        return boundary.admit(
            PublicRequest(
                method=request.method,
                path=request.state.raw_target,
                host=request.headers.get("Host", "") or "",
                # The RAW ASGI header list, not a mapping: a mapping keeps only the first value
                # per name, which would make the kernel's straddle check unreachable for the
                # ordinary two-header form of a multi-tenant assertion.
                headers=_raw_headers(request),
                authorization=request.headers.get("Authorization"),
            ),
            request.state.correlation_id,
        )

    @app.get(_MEMBERSHIPS_PATH)
    async def memberships(request: Request) -> Response:
        try:
            principal = _admit(request)
        except PublicBoundaryDenied as denied:
            return empty_response(denied.http_status)

        try:
            # One logical request == one fresh ControlStore unit of work, released before the
            # response is written. The subject is the authenticated principal, full stop.
            with control_plane.control_store_unit_of_work() as store:
                rows = ControlPlaneReadService(store).memberships_for_principal(principal.principal_ref)
            composed = _compose(rows)
        except Exception:
            # Store/connection/shape failure -> fixed 503, empty body: no tenant, database,
            # connection, or store detail may leak.
            return empty_response(503)

        # Evidence before hand-back: exactly ONE references-only success event per successful
        # enumeration — a successful EMPTY enumeration included, never one per membership and
        # never one per tenant. Actor == subject == the authenticated principal.
        try:
            boundary.emit(
                ACTION_WORKSPACE_MEMBERSHIPS_READ,
                "success",
                principal.correlation_id,
                actor_ref=principal.principal_ref,
                subject_ref=principal.principal_ref,
            )
        except PublicBoundaryDenied as denied:
            return empty_response(denied.http_status)

        return Response(status_code=200, content=serialize_portal_dto(composed), media_type="application/json")

    @app.options(_MEMBERSHIPS_PATH)
    async def memberships_preflight(request: Request) -> Response:
        return write_preflight(request, "GET, OPTIONS", "Authorization, x-correlation-id")

    @app.get("/health")
    async def health(_request: Request) -> Response:
        return Response(status_code=200, content=_liveness(), media_type="application/json")

    @app.get("/readiness")
    async def readiness_route(_request: Request) -> Response:
        return Response(status_code=200, content=_readiness(), media_type="application/json")

    return app


def create_app_from_env() -> FastAPI:
    """The native ASGI application factory for the public workspace edge.

    Run directly by the operator through the ASGI runtime's own command line::

        uvicorn control_plane.adapters.providers.http_public_workspace_edge:create_app_from_env --factory ...

    Takes NO arguments: the listening host and port belong to the runtime process, so this
    factory binds no socket and owns no address.

    Fail closed: an INACTIVE composition is a misconfiguration, not a no-op — the required
    ``SP2_EDGE_AUTH_ROUTER_BASE_URL`` unset/empty raises ``RuntimeError``; a malformed value
    raises ``ValueError``. There is deliberately NO fallback to an unauthenticated edge: a
    public edge that cannot authenticate must never bind.

    Store posture is unchanged Control-Plane behaviour: ``create_app()`` applies its own
    selector-coherence validation, and an UNSET ``SP2_CP_CONTROL_STORE`` still composes the
    in-memory, test-only store. A listening workspace edge is therefore not by itself evidence
    that the physical Control database is the authority behind it.
    """
    from control_plane.main import build_public_workspace_edge_deps_from_env

    deps = build_public_workspace_edge_deps_from_env()
    if deps is None:
        raise RuntimeError(
            "create_app_from_env: public workspace edge composition is INACTIVE — "
            "SP2_EDGE_AUTH_ROUTER_BASE_URL is unset/empty (fail closed: no application composed)"
        )
    control_plane, boundary, allowed_origins = deps
    return make_app(control_plane, boundary, allowed_origins)


def build_public_workspace_edge_server(
    control_plane: "ControlPlane",
    boundary: PublicBoundary,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    allowed_origins: Tuple[str, ...] = (),
) -> Tuple[AsgiEdgeServer, str]:
    """Construct the public workspace HTTP server. ``port=0`` binds an ephemeral port.

    Constructs only — it does not serve. Returns ``(server, base_url)``.
    """
    return build_asgi_server(make_app(control_plane, boundary, allowed_origins), host, port)


def serve_public_workspace_edge() -> None:
    """Blocking runnable entrypoint for the public workspace edge.

    An inactive composition raises ``RuntimeError`` (no socket bound, nothing served); an
    active one calls ``serve_forever`` exactly once and always closes the server in ``finally``.
    """
    from control_plane.main import build_public_workspace_edge_server_from_env

    composed = build_public_workspace_edge_server_from_env()
    if composed is None:
        raise RuntimeError(
            "serve_public_workspace_edge: composition is INACTIVE — SP2_EDGE_AUTH_ROUTER_BASE_URL is "
            "unset/empty (fail closed: no socket bound, nothing served)"
        )
    server_obj, _base_url = composed
    server = cast(AsgiEdgeServer, server_obj)
    try:
        server.serve_forever()
    finally:
        server.server_close()


__all__ = [
    "SERVICE",
    "build_public_workspace_edge_server",
    "create_app_from_env",
    "make_app",
    "serve_public_workspace_edge",
]
