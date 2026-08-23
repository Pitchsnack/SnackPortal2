"""Database Router Service — independently bootable FastAPI application (IC-013 §21).

    python -m snackportal2.services.database_router.main
    uvicorn snackportal2.services.database_router.main:app --host 127.0.0.1 --port 8004

Answers *which active tenant and which physical database?* and is the only service
permitted to open a tenant database (IC-013 §8). It never authenticates and never
authorizes: authentication and authorization are complete before it is reached, and it
consumes the already-authenticated, already-authorized context as given.
"""

from __future__ import annotations

import os
from typing import Annotated

import uvicorn
from fastapi import Path

from ...shared.config import load_settings
from ...shared.errors import error_responses, invalid_request, not_found
from ...shared.security import ServiceBearer
from ...shared.service import build_app
from .models import (
    RecordFamily,
    RecordListRequest,
    RecordListResponse,
    RecordReadRequest,
    RecordWriteRequest,
    RoutingRequest,
    RoutingResolution,
    TenantRecord,
)
from .resolver import EnvironmentTenantSecretStore, TenantResolver, build_registry
from .store import InMemoryTenantRecordStore, PostgresTenantRecordStore, TenantRecordStore, UnsupportedFamily

SERVICE = "database_router"

#: Storage mode. Explicit, because a *silent* fallback from PostgreSQL to in-memory would
#: turn a database outage into apparently-successful reads of an empty tenant.
ENV_STORAGE = "SP2_DATABASE_ROUTER_STORAGE"

settings = load_settings(SERVICE)

app = build_app(
    SERVICE,
    description=(
        "Resolves exactly one physical tenant database from the signed active-tenant claim and performs "
        "tenant-resident record access within it (IC-013 §8). It authenticates nothing, authorizes nothing, "
        "and never falls back to the Control database."
    ),
    settings=settings,
)

_resolver = TenantResolver(build_registry(), EnvironmentTenantSecretStore())


def _build_store() -> TenantRecordStore:
    mode = os.environ.get(ENV_STORAGE, "").strip().casefold()
    if mode == "postgres":
        return PostgresTenantRecordStore()
    return InMemoryTenantRecordStore()


_store = _build_store()

FamilyPath = Annotated[RecordFamily, Path(description="The tenant-resident record family to address.")]


@app.post(
    "/internal/routing/resolve",
    response_model=RoutingResolution,
    summary="Resolve the single physical database for a request",
    description=(
        "Bind exactly one physical tenant database from the signed active-tenant claim, registry-"
        "authoritatively. Fails closed in every other case: a tenantless or unknown tenant answers with the "
        "consistent denial, a non-ACTIVE tenant with not-ready, and a missing or unreachable association with "
        "unavailable. There is no Control-database fallback and no default tenant."
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
    "/internal/tenant-records/{family}/list",
    response_model=RecordListResponse,
    summary="List tenant-resident records of one family",
    description=(
        "Read up to the requested number of records of one family from the single tenant database bound by "
        "the signed claim. The family is a closed enumeration and the caller supplies no table, column, or "
        "SQL. Order is deterministic and callers MUST NOT re-sort it."
    ),
    tags=["Tenant Records"],
    operation_id="listTenantRecords",
    response_description="The records read from exactly one tenant database.",
    responses=error_responses(401, 404, 409, 422, 503),
)
async def list_records(family: FamilyPath, request: RecordListRequest, _credential: ServiceBearer) -> RecordListResponse:
    target = _resolver.resolve(request.context.tenant_context)
    try:
        records = _store.list_records(target.tenant_ref, family, request.limit, target.dsn)
    except UnsupportedFamily:
        raise invalid_request() from None
    return RecordListResponse(tenant_ref=target.tenant_ref, family=family, records=records)


@app.post(
    "/internal/tenant-records/{family}/read",
    response_model=TenantRecord,
    summary="Read one tenant-resident record",
    description=(
        "Read a single record of one family from the tenant database bound by the signed claim. A record "
        "reference minted for a different tenant or a different family is not found here — the tenant and "
        "family are part of the reference and are verified, not decorative."
    ),
    tags=["Tenant Records"],
    operation_id="readTenantRecord",
    response_description="The requested tenant-resident record.",
    responses=error_responses(401, 404, 409, 422, 503),
)
async def read_record(family: FamilyPath, request: RecordReadRequest, _credential: ServiceBearer) -> TenantRecord:
    target = _resolver.resolve(request.context.tenant_context)
    try:
        record = _store.read_record(target.tenant_ref, family, request.record_ref, target.dsn)
    except UnsupportedFamily:
        raise invalid_request() from None
    if record is None:
        raise not_found()
    return record


@app.post(
    "/internal/tenant-records/{family}/create",
    response_model=TenantRecord,
    status_code=201,
    summary="Create one tenant-resident record",
    description=(
        "Insert a record of one family into the tenant database bound by the signed claim. Field names "
        "outside the family's column allowlist are rejected with no partial write."
    ),
    tags=["Tenant Records"],
    operation_id="createTenantRecord",
    response_description="The created tenant-resident record and its reference.",
    responses=error_responses(401, 404, 409, 422, 503),
)
async def create_record(family: FamilyPath, request: RecordWriteRequest, _credential: ServiceBearer) -> TenantRecord:
    if request.record_ref is not None:
        # A create never addresses an existing record; accepting one would make "create"
        # quietly capable of overwriting.
        raise invalid_request()
    target = _resolver.resolve(request.context.tenant_context)
    try:
        return _store.create_record(target.tenant_ref, family, request.fields, target.dsn)
    except UnsupportedFamily:
        raise invalid_request() from None


@app.post(
    "/internal/tenant-records/{family}/update",
    response_model=TenantRecord,
    summary="Update one tenant-resident record",
    description=(
        "Update the named fields of one record in the tenant database bound by the signed claim. Field names "
        "outside the family's column allowlist are rejected with no partial write, and append-only families "
        "reject updates outright."
    ),
    tags=["Tenant Records"],
    operation_id="updateTenantRecord",
    response_description="The updated tenant-resident record.",
    responses=error_responses(401, 404, 409, 422, 503),
)
async def update_record(family: FamilyPath, request: RecordWriteRequest, _credential: ServiceBearer) -> TenantRecord:
    if request.record_ref is None:
        raise invalid_request()
    target = _resolver.resolve(request.context.tenant_context)
    try:
        return _store.update_record(target.tenant_ref, family, request.record_ref, request.fields, target.dsn)
    except UnsupportedFamily:
        raise invalid_request() from None


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
