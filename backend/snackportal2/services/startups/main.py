"""Startup Service — independently bootable FastAPI application (IC-013 §21).

    python -m snackportal2.services.startups.main
    uvicorn snackportal2.services.startups.main:app --host 127.0.0.1 --port 8005

Tenant-resident Startup records (IC-002). Every operation carries the canonical
``RequestContext`` in its body rather than a tenant in its path: the route is never a
client-controlled routing channel (IC-013 §16), and there is no parameter through which a
caller could name a tenant other than the one its signed claim names.

``Global Record ≠ Tenant Record``. An imported Startup is an independent tenant copy carrying
a soft reference to its global source; editing it never touches the global record, and nothing
here synchronizes the two.
"""

from __future__ import annotations

import os
from typing import Union

import uvicorn

from ...shared.config import load_settings
from ...shared.errors import consistent_tenant_denial, error_responses, not_found
from ...shared.security import ServiceBearer
from ...shared.service import build_app
from ...shared.tenant_data import build_grant_provider
from ...shared.urls import normalize_website
from .models import (
    DuplicateCandidate,
    DuplicateCheckRequest,
    DuplicateCheckResponse,
    StartupCreateRequest,
    StartupListRequest,
    StartupListResponse,
    StartupReadRequest,
    StartupUpdateRequest,
    TenantStartupRecord,
)
from .repository import InMemoryStartupRepository, PostgresStartupRepository, StartupRepository, find_duplicates

SERVICE = "startups"

#: Storage mode. Explicit, because a silent fallback from PostgreSQL to in-memory would turn a
#: database outage into apparently-successful reads of an empty tenant.
ENV_STORAGE = "SP2_STARTUPS_STORAGE"

settings = load_settings(SERVICE)

app = build_app(
    SERVICE,
    description=(
        "Tenant-resident Startup records (IC-002). Holds its own tenant-database connection under a "
        "Database Router grant (D-48); the router remains the sole authority on which single database a "
        "request may reach. Global Record != Tenant Record, and Import != Synchronization."
    ),
    settings=settings,
)


def _build_repository() -> StartupRepository:
    if os.environ.get(ENV_STORAGE, "").strip().casefold() == "postgres":
        return PostgresStartupRepository(build_grant_provider(SERVICE))
    return InMemoryStartupRepository()


_repository = _build_repository()


AnyStartupRequest = Union[
    StartupListRequest, StartupReadRequest, StartupCreateRequest, StartupUpdateRequest, DuplicateCheckRequest
]


def _tenant_of(request: AnyStartupRequest) -> str:
    """The one tenant this request may touch — the signed claim, and nothing else."""
    tenant_ref = request.context.tenant_context
    if not tenant_ref:
        # A tenantless context has no tenant database. Answered with the consistent denial so
        # it is indistinguishable from an unknown tenant.
        raise consistent_tenant_denial()
    return tenant_ref


@app.post(
    "/internal/startups/list",
    response_model=StartupListResponse,
    summary="List tenant Startup records",
    description=(
        "Return up to the requested number of Startup records from the single tenant database named by the "
        "signed claim, in deterministic order. Callers MUST NOT re-sort the result."
    ),
    tags=["Startups"],
    operation_id="listTenantStartups",
    response_description="Startup records from exactly one tenant database.",
    responses=error_responses(401, 404, 409, 422, 503),
)
async def list_startups(request: StartupListRequest, _credential: ServiceBearer) -> StartupListResponse:
    tenant_ref = _tenant_of(request)
    return StartupListResponse(tenant_ref=tenant_ref, records=_repository.list(tenant_ref, request.limit))


@app.post(
    "/internal/startups/read",
    response_model=TenantStartupRecord,
    summary="Read one tenant Startup record",
    description=(
        "Return one Startup record from the tenant database named by the signed claim. A record reference "
        "minted for a different tenant is not found here: the tenant is part of the reference and is verified."
    ),
    tags=["Startups"],
    operation_id="readTenantStartup",
    response_description="The requested tenant-resident Startup record.",
    responses=error_responses(401, 404, 409, 422, 503),
)
async def read_startup(request: StartupReadRequest, _credential: ServiceBearer) -> TenantStartupRecord:
    record = _repository.read(_tenant_of(request), request.record_ref)
    if record is None:
        raise not_found()
    return record


@app.post(
    "/internal/startups/create",
    response_model=TenantStartupRecord,
    status_code=201,
    summary="Create a tenant Startup record",
    description=(
        "Create one Startup in the tenant database named by the signed claim. The company website is "
        "normalized on write — scheme added, host lower-cased, a leading 'www.' and a trailing slash "
        "removed — and a malformed URL is rejected rather than stored as given. When 'global_startup_id' "
        "is supplied the record is an independent tenant copy carrying a soft reference to its global "
        "source; it is never a foreign key and never synchronizes."
    ),
    tags=["Startups"],
    operation_id="createTenantStartup",
    response_description="The created tenant-resident Startup record and its reference.",
    responses=error_responses(401, 404, 409, 422, 503),
)
async def create_startup(request: StartupCreateRequest, _credential: ServiceBearer) -> TenantStartupRecord:
    tenant_ref = _tenant_of(request)
    fields = request.model_dump(exclude={"context"})
    fields["company_url"] = normalize_website(request.company_url)
    # The repositories carry column values as text — the in-memory table is typed that way and
    # psycopg casts the parameter into the DDL's ``integer`` column. Validation has already
    # happened against the published integer contract, so this is a storage representation, not
    # a second, looser acceptance of the value.
    fields["year_founded"] = None if request.year_founded is None else str(request.year_founded)
    return _repository.create(tenant_ref, fields)


@app.post(
    "/internal/startups/update",
    response_model=TenantStartupRecord,
    summary="Update a tenant Startup record",
    description=(
        "Update the one mutable field of a tenant Startup: 'short_description', bounded at 500 characters, "
        "or null to clear (IC-009 CLM section, adopted under D-42). No other field is mutable through this "
        "operation, and a request naming one is rejected with no partial write."
    ),
    tags=["Startups"],
    operation_id="updateTenantStartup",
    response_description="The updated tenant-resident Startup record.",
    responses=error_responses(401, 404, 409, 422, 503),
)
async def update_startup(request: StartupUpdateRequest, _credential: ServiceBearer) -> TenantStartupRecord:
    return _repository.update_short_description(_tenant_of(request), request.record_ref, request.short_description)


@app.post(
    "/internal/startups/duplicate-check",
    response_model=DuplicateCheckResponse,
    summary="Check a proposed Startup for duplicates",
    description=(
        "Return records in this tenant that may already represent the proposed company, matched exactly "
        "after normalization on name and on website. The result is candidates for human review and an "
        "advisory 'blocking' flag; this service makes no merge decision and deletes nothing."
    ),
    tags=["Startups"],
    operation_id="checkTenantStartupDuplicates",
    response_description="Possible duplicates and whether any matched exactly.",
    responses=error_responses(401, 404, 409, 422, 503),
)
async def check_duplicates(request: DuplicateCheckRequest, _credential: ServiceBearer) -> DuplicateCheckResponse:
    tenant_ref = _tenant_of(request)
    matches = find_duplicates(_repository, tenant_ref, request.company_name, request.company_url)
    return DuplicateCheckResponse(
        candidates=[
            DuplicateCandidate(record_ref=record.record_ref, display_name=record.company_name, reason=reason)
            for record, reason in matches
        ],
        blocking=bool(matches),
    )


if __name__ == "__main__":  # local development convenience — IC-013 §21 permits this block
    uvicorn.run(
        "snackportal2.services.startups.main:app",
        host=settings.host,  # loopback by omission — E-2
        port=settings.port,
        reload=settings.reload,  # off by omission; local development only — E-4
        access_log=settings.access_log,
        server_header=settings.server_header,
        proxy_headers=settings.proxy_headers,
    )
