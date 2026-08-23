"""Database Router Service — independently bootable FastAPI application (IC-013 §21).

    python -m snackportal2.services.database_router.main
    uvicorn snackportal2.services.database_router.main:app --host 127.0.0.1 --port 8004

Answers *which active tenant and which physical database?* — the **sole authority** on tenant
database resolution (IC-013 §8 as amended by D-48). It authenticates nothing, authorizes
nothing, and never falls back to the Control database.

Two surfaces, deliberately different:

* ``/internal/routing/resolve`` returns a **reference** and is what the BFF calls. It proves
  exactly one database resolved without telling the ingress how to reach it.
* ``/internal/routing/bind`` returns a **grant** and is what a tenant-resident domain service
  calls. It is restricted to the explicit allowlist, from which the BFF and the Access Control
  Service are permanently excluded (D-48 C-1).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import uvicorn

from ...shared.config import load_settings
from ...shared.errors import access_denied, error_responses, unauthenticated
from ...shared.security import ServiceBearer
from ...shared.service import build_app
from .grants import GRANT_TTL_SECONDS, build_allowlist
from .models import (
    GranteeListResponse,
    GranteeRegistration,
    RoutingRequest,
    RoutingResolution,
    TenantBindRequest,
    TenantConnectionGrantResponse,
)
from .resolver import EnvironmentTenantSecretStore, TenantResolver, build_registry

SERVICE = "database_router"

settings = load_settings(SERVICE)

app = build_app(
    SERVICE,
    description=(
        "Resolves exactly one physical tenant database from the signed active-tenant claim, registry-"
        "authoritatively, and issues short-lived single-tenant connection grants to allowlisted "
        "tenant-resident services (IC-013 §8, D-48). It authenticates nothing, authorizes nothing, and "
        "never falls back to the Control database."
    ),
    settings=settings,
)

_resolver = TenantResolver(build_registry(), EnvironmentTenantSecretStore())
_allowlist = build_allowlist()


@app.post(
    "/internal/routing/resolve",
    response_model=RoutingResolution,
    summary="Resolve the single physical database for a request",
    description=(
        "Bind exactly one physical tenant database from the signed active-tenant claim, registry-"
        "authoritatively, and return it as an opaque reference. Fails closed in every other case: a "
        "tenantless or unknown tenant answers with the consistent denial, a non-ACTIVE tenant with "
        "not-ready, and a missing or unreachable association with unavailable. There is no Control-database "
        "fallback and no default tenant. The response carries no DSN, host, database name, or credential."
    ),
    tags=["Routing"],
    operation_id="resolveTenantDatabase",
    response_description="The single resolved database, expressed as an opaque reference.",
    responses=error_responses(401, 404, 409, 422, 503),
)
async def resolve(request: RoutingRequest, _credential: ServiceBearer) -> RoutingResolution:
    target = _resolver.resolve(request.context.tenant_context)
    return RoutingResolution(
        tenant_ref=target.tenant_ref,
        target_ref=target.target_ref,
        expected_schema_version=target.expected_schema_version,
    )


@app.post(
    "/internal/routing/bind",
    response_model=TenantConnectionGrantResponse,
    summary="Issue a tenant connection grant",
    description=(
        "Issue a short-lived, single-tenant connection grant to an allowlisted tenant-resident service "
        "(D-48). The same registry-authoritative resolution and the same six fail-closed cases apply as "
        "for resolution, so a service cannot obtain a connection the router would not itself have opened. "
        "A caller whose credential is not on the grant allowlist is refused even though the credential is "
        "otherwise valid for this router; the BFF and the Access Control Service are permanently excluded."
    ),
    tags=["Routing"],
    operation_id="bindTenantConnection",
    response_description="A grant authorizing one connection to one tenant database, with its expiry.",
    responses=error_responses(401, 403, 404, 409, 422, 503),
)
async def bind(request: TenantBindRequest, credential: ServiceBearer) -> TenantConnectionGrantResponse:
    service_ref = _allowlist.service_for(credential)
    if service_ref is None:
        # Refused before resolution, so an unallowlisted caller cannot even use this endpoint
        # to probe which tenants exist.
        raise access_denied()

    target = _resolver.resolve(request.tenant_ref)
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=GRANT_TTL_SECONDS)).isoformat()
    return TenantConnectionGrantResponse(
        tenant_ref=target.tenant_ref,
        target_ref=target.target_ref,
        expected_schema_version=target.expected_schema_version,
        dsn=target.dsn,
        expires_at=expires_at,
    )


@app.get(
    "/internal/routing/grantees",
    response_model=GranteeListResponse,
    summary="List the services permitted to hold a tenant connection",
    description=(
        "Return the service references on the grant allowlist, for operational review (D-48 C-1). "
        "Credentials are never returned — only the service references they map to."
    ),
    tags=["Routing"],
    operation_id="listConnectionGrantees",
    response_description="The allowlisted service references, in deterministic order.",
    responses=error_responses(401),
)
async def list_grantees(credential: ServiceBearer) -> GranteeListResponse:
    if not credential:
        raise unauthenticated()
    return GranteeListResponse(
        grantees=[GranteeRegistration(service_ref=service_ref) for service_ref in _allowlist.service_refs()]
    )


if __name__ == "__main__":  # local development convenience — IC-013 §21 permits this block
    uvicorn.run(
        "snackportal2.services.database_router.main:app",
        host=settings.host,  # loopback by omission — E-2
        port=settings.port,
        reload=settings.reload,  # off by omission; local development only — E-4
        access_log=settings.access_log,
        server_header=settings.server_header,
        proxy_headers=settings.proxy_headers,
    )
