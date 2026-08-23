"""Investor Service — independently bootable FastAPI application (IC-013 §21).

    python -m snackportal2.services.investors.main
    uvicorn snackportal2.services.investors.main:app --host 127.0.0.1 --port 8006

Tenant-resident Investor records (IC-002), with parity to the approved Add My Investor field
set and the same website-normalization behaviour as Startups. Every operation carries the
canonical ``RequestContext`` in its body; no route names a tenant.
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
    InvestorCreateRequest,
    InvestorListRequest,
    InvestorListResponse,
    InvestorReadRequest,
    InvestorUpdateRequest,
    TenantInvestorRecord,
)
from .repository import InMemoryInvestorRepository, InvestorRepository, PostgresInvestorRepository

SERVICE = "investors"

ENV_STORAGE = "SP2_INVESTORS_STORAGE"

settings = load_settings(SERVICE)

app = build_app(
    SERVICE,
    description=(
        "Tenant-resident Investor records (IC-002). Holds its own tenant-database connection under a "
        "Database Router grant (D-48). Global Record != Tenant Record, and Import != Synchronization."
    ),
    settings=settings,
)


def _build_repository() -> InvestorRepository:
    if os.environ.get(ENV_STORAGE, "").strip().casefold() == "postgres":
        return PostgresInvestorRepository(build_grant_provider(SERVICE))
    return InMemoryInvestorRepository()


_repository = _build_repository()

AnyInvestorRequest = Union[InvestorListRequest, InvestorReadRequest, InvestorCreateRequest, InvestorUpdateRequest]


def _tenant_of(request: AnyInvestorRequest) -> str:
    """The one tenant this request may touch — the signed claim, and nothing else."""
    tenant_ref = request.context.tenant_context
    if not tenant_ref:
        raise consistent_tenant_denial()
    return tenant_ref


@app.post(
    "/internal/investors/list",
    response_model=InvestorListResponse,
    summary="List tenant Investor records",
    description=(
        "Return up to the requested number of Investor records from the single tenant database named by "
        "the signed claim, in deterministic order. Callers MUST NOT re-sort the result."
    ),
    tags=["Investors"],
    operation_id="listTenantInvestors",
    response_description="Investor records from exactly one tenant database.",
    responses=error_responses(401, 404, 409, 422, 503),
)
async def list_investors(request: InvestorListRequest, _credential: ServiceBearer) -> InvestorListResponse:
    tenant_ref = _tenant_of(request)
    return InvestorListResponse(tenant_ref=tenant_ref, records=_repository.list(tenant_ref, request.limit))


@app.post(
    "/internal/investors/read",
    response_model=TenantInvestorRecord,
    summary="Read one tenant Investor record",
    description=(
        "Return one Investor record from the tenant database named by the signed claim. A record reference "
        "minted for a different tenant is not found here."
    ),
    tags=["Investors"],
    operation_id="readTenantInvestor",
    response_description="The requested tenant-resident Investor record.",
    responses=error_responses(401, 404, 409, 422, 503),
)
async def read_investor(request: InvestorReadRequest, _credential: ServiceBearer) -> TenantInvestorRecord:
    record = _repository.read(_tenant_of(request), request.record_ref)
    if record is None:
        raise not_found()
    return record


@app.post(
    "/internal/investors/create",
    response_model=TenantInvestorRecord,
    status_code=201,
    summary="Create a tenant Investor record",
    description=(
        "Create one Investor in the tenant database named by the signed claim, from the approved Add My "
        "Investor field set. The website is normalized on write and a malformed URL is rejected. The stage "
        "and industry focus lists are stored as jsonb arrays, never flattened to strings."
    ),
    tags=["Investors"],
    operation_id="createTenantInvestor",
    response_description="The created tenant-resident Investor record and its reference.",
    responses=error_responses(401, 404, 409, 422, 503),
)
async def create_investor(request: InvestorCreateRequest, _credential: ServiceBearer) -> TenantInvestorRecord:
    import json

    tenant_ref = _tenant_of(request)
    fields = request.model_dump(exclude={"context"})
    fields["website_url"] = normalize_website(request.website_url)
    fields["investment_stage_focus"] = json.dumps(request.investment_stage_focus)
    fields["industry_focus"] = json.dumps(request.industry_focus)
    return _repository.create(tenant_ref, fields)


@app.post(
    "/internal/investors/update",
    response_model=TenantInvestorRecord,
    summary="Update a tenant Investor record",
    description=(
        "Update the one mutable field of a tenant Investor: 'short_description', bounded at 500 characters, "
        "or null to clear. No other field is mutable through this operation."
    ),
    tags=["Investors"],
    operation_id="updateTenantInvestor",
    response_description="The updated tenant-resident Investor record.",
    responses=error_responses(401, 404, 409, 422, 503),
)
async def update_investor(request: InvestorUpdateRequest, _credential: ServiceBearer) -> TenantInvestorRecord:
    return _repository.update_short_description(_tenant_of(request), request.record_ref, request.short_description)


if __name__ == "__main__":  # local development convenience — IC-013 §21 permits this block
    uvicorn.run(
        "snackportal2.services.investors.main:app",
        host=settings.host,  # loopback by omission — E-2
        port=settings.port,
        reload=settings.reload,  # off by omission; local development only — E-4
        access_log=settings.access_log,
        server_header=settings.server_header,
        proxy_headers=settings.proxy_headers,
    )
