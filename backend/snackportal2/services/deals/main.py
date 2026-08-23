"""Deal Service — independently bootable FastAPI application (IC-013 §21).

    python -m snackportal2.services.deals.main
    uvicorn snackportal2.services.deals.main:app --host 127.0.0.1 --port 8007

Tenant-resident Deal records. **Sharing ≠ Deal Duplication**: this service exposes no
operation that copies a deal, and no operation that produces a second record from an existing
one. Cross-tenant deal behaviour does not exist here and is IC-007-deferred.
"""

from __future__ import annotations

import os
from typing import Optional, Union

import uvicorn

from ...shared.config import load_settings
from ...shared.errors import consistent_tenant_denial, error_responses, not_found
from ...shared.security import ServiceBearer
from ...shared.service import build_app
from ...shared.tenant_data import build_grant_provider
from .models import (
    DealCreateRequest,
    DealListRequest,
    DealListResponse,
    DealReadRequest,
    DealUpdateRequest,
    TenantDealRecord,
)
from .repository import DealRepository, InMemoryDealRepository, PostgresDealRepository, resolve_party

SERVICE = "deals"

ENV_STORAGE = "SP2_DEALS_STORAGE"

settings = load_settings(SERVICE)

app = build_app(
    SERVICE,
    description=(
        "Tenant-resident Deal records. A deal references a Startup and optionally an Investor, both within "
        "the same tenant database. Sharing is never duplication: no operation here copies a deal. Holds its "
        "own tenant-database connection under a Database Router grant (D-48)."
    ),
    settings=settings,
)


def _build_repository() -> DealRepository:
    if os.environ.get(ENV_STORAGE, "").strip().casefold() == "postgres":
        return PostgresDealRepository(build_grant_provider(SERVICE))
    return InMemoryDealRepository()


_repository = _build_repository()

AnyDealRequest = Union[DealListRequest, DealReadRequest, DealCreateRequest, DealUpdateRequest]


def _tenant_of(request: AnyDealRequest) -> str:
    """The one tenant this request may touch — the signed claim, and nothing else."""
    tenant_ref = request.context.tenant_context
    if not tenant_ref:
        raise consistent_tenant_denial()
    return tenant_ref


@app.post(
    "/internal/deals/list",
    response_model=DealListResponse,
    summary="List tenant Deal records",
    description=(
        "Return up to the requested number of Deal records from the single tenant database named by the "
        "signed claim, in deterministic order."
    ),
    tags=["Deals"],
    operation_id="listTenantDeals",
    response_description="Deal records from exactly one tenant database.",
    responses=error_responses(401, 404, 409, 422, 503),
)
async def list_deals(request: DealListRequest, _credential: ServiceBearer) -> DealListResponse:
    tenant_ref = _tenant_of(request)
    return DealListResponse(tenant_ref=tenant_ref, records=_repository.list(tenant_ref, request.limit))


@app.post(
    "/internal/deals/read",
    response_model=TenantDealRecord,
    summary="Read one tenant Deal record",
    description="Return one Deal record from the tenant database named by the signed claim.",
    tags=["Deals"],
    operation_id="readTenantDeal",
    response_description="The requested tenant-resident Deal record.",
    responses=error_responses(401, 404, 409, 422, 503),
)
async def read_deal(request: DealReadRequest, _credential: ServiceBearer) -> TenantDealRecord:
    record = _repository.read(_tenant_of(request), request.record_ref)
    if record is None:
        raise not_found()
    return record


@app.post(
    "/internal/deals/create",
    response_model=TenantDealRecord,
    status_code=201,
    summary="Create a tenant Deal record",
    description=(
        "Create one Deal in the tenant database named by the signed claim. Both party references are "
        "verified to belong to this tenant: a reference minted for another tenant is rejected outright "
        "rather than ignored, so a request that tries to cross tenants fails instead of quietly producing "
        "an unmatched deal."
    ),
    tags=["Deals"],
    operation_id="createTenantDeal",
    response_description="The created tenant-resident Deal record and its reference.",
    responses=error_responses(401, 404, 409, 422, 503),
)
async def create_deal(request: DealCreateRequest, _credential: ServiceBearer) -> TenantDealRecord:
    tenant_ref = _tenant_of(request)
    fields: dict[str, Optional[str]] = {
        "startup_id": resolve_party(tenant_ref, "startups", request.startup_ref),
        "investor_id": resolve_party(tenant_ref, "investors", request.investor_ref),
        "deal_name": request.deal_name,
        "stage": request.stage,
        "amount": request.amount,
        "currency": request.currency,
        "status": request.status.value,
    }
    return _repository.create(tenant_ref, fields)


@app.post(
    "/internal/deals/update",
    response_model=TenantDealRecord,
    summary="Update a tenant Deal's stage or status",
    description=(
        "Update a Deal's stage and/or status. The party references are immutable through this operation: "
        "re-pointing a deal at a different startup is not an edit, it is a different deal, and allowing it "
        "would make the record's history meaningless."
    ),
    tags=["Deals"],
    operation_id="updateTenantDeal",
    response_description="The updated tenant-resident Deal record.",
    responses=error_responses(401, 404, 409, 422, 503),
)
async def update_deal(request: DealUpdateRequest, _credential: ServiceBearer) -> TenantDealRecord:
    fields: dict[str, Optional[str]] = {
        "stage": request.stage,
        "status": request.status.value if request.status is not None else None,
    }
    return _repository.update(_tenant_of(request), request.record_ref, fields)


if __name__ == "__main__":  # local development convenience — IC-013 §21 permits this block
    uvicorn.run(
        "snackportal2.services.deals.main:app",
        host=settings.host,  # loopback by omission — E-2
        port=settings.port,
        reload=settings.reload,  # off by omission; local development only — E-4
        access_log=settings.access_log,
        server_header=settings.server_header,
        proxy_headers=settings.proxy_headers,
    )
