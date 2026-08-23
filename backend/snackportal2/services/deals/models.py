"""Deal Service wire models.

Field sets come from the accepted tenant DDL (``005_deals.sql``). A deal references a tenant
Startup and, optionally, a tenant Investor — both **within the same tenant database**, because
a deal that could reference across tenants would be a cross-tenant capability, and those are
IC-007-deferred.

**Sharing ≠ Deal Duplication.** Nothing here copies a deal, and there is no operation that
produces a second record from an existing one.

No **global** deal behaviour is modelled. `DirectoryKind` has STARTUP and INVESTOR only: the
D-35 Global Deal Directory has no DDL and no contract-complete definition (Action Tracker #29),
so inventing one here would create a surface no contract governs.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from ...shared.security import RequestContext
from ...shared.types import RecordResidency


class DealStatus(str, Enum):
    """Deal status vocabulary. A closed enum, so an unknown status cannot be stored."""

    OPEN = "open"
    IN_DILIGENCE = "in_diligence"
    COMMITTED = "committed"
    CLOSED = "closed"
    WITHDRAWN = "withdrawn"


class TenantDealRecord(BaseModel):
    """One tenant-resident Deal record."""

    record_ref: str = Field(description="Opaque reference to the tenant-resident Deal record.")
    deal_name: str = Field(description="Deal display name.")
    startup_ref: str = Field(description="Reference to the tenant Startup this deal concerns. Same tenant, always.")
    investor_ref: Optional[str] = Field(
        default=None, description="Reference to the tenant Investor, or null while the deal is unmatched."
    )
    stage: Optional[str] = Field(default=None, description="Deal stage label.")
    amount: Optional[str] = Field(default=None, description="Deal amount as stored. A string, so no precision is lost in transit.")
    currency: Optional[str] = Field(default=None, description="ISO currency code for the amount.")
    status: Optional[DealStatus] = Field(default=None, description="Deal status from the closed vocabulary.")
    record_origin: str = Field(default="tenant", description="Provenance marker (D-37 §10).")
    record_residency: RecordResidency = Field(default=RecordResidency.TENANT, description="Provenance marker.")
    record_type: str = Field(default="deal", description="Provenance marker (D-37 §10).")


class DealListRequest(BaseModel):
    """List tenant Deals within exactly one tenant database."""

    context: RequestContext = Field(description="The canonical RequestContext naming the single active tenant.")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum records to return.")


class DealReadRequest(BaseModel):
    """Read one tenant Deal."""

    context: RequestContext = Field(description="The canonical RequestContext naming the single active tenant.")
    record_ref: str = Field(min_length=1, max_length=256, description="Opaque reference to the record to read.")


class DealCreateRequest(BaseModel):
    """Create one tenant Deal."""

    context: RequestContext = Field(description="The canonical RequestContext naming the single active tenant.")
    deal_name: str = Field(min_length=1, max_length=256, description="Deal display name. Required.")
    startup_ref: str = Field(
        min_length=1,
        max_length=256,
        description="Reference to the tenant Startup. Rejected if it was minted for a different tenant.",
    )
    investor_ref: Optional[str] = Field(
        default=None,
        max_length=256,
        description="Reference to the tenant Investor, or null for an unmatched deal. Same-tenant only.",
    )
    stage: Optional[str] = Field(default=None, max_length=128, description="Deal stage label.")
    amount: Optional[str] = Field(default=None, max_length=64, description="Deal amount.")
    currency: Optional[str] = Field(default=None, max_length=8, description="ISO currency code.")
    status: DealStatus = Field(default=DealStatus.OPEN, description="Initial status from the closed vocabulary.")


class DealUpdateRequest(BaseModel):
    """Update one tenant Deal's stage and status. Never its parties.

    The startup and investor references are deliberately immutable through this operation:
    re-pointing a deal at a different startup is not an edit, it is a different deal, and
    allowing it would make the record's history meaningless.
    """

    context: RequestContext = Field(description="The canonical RequestContext naming the single active tenant.")
    record_ref: str = Field(min_length=1, max_length=256, description="Opaque reference to the record to update.")
    stage: Optional[str] = Field(default=None, max_length=128, description="New deal stage label, or null to leave unchanged.")
    status: Optional[DealStatus] = Field(default=None, description="New status from the closed vocabulary, or null to leave unchanged.")


class DealListResponse(BaseModel):
    """Deals from exactly one tenant database, in deterministic order."""

    tenant_ref: str = Field(description="The single tenant these records came from.")
    records: List[TenantDealRecord] = Field(description="The records, in deterministic order.")


__all__ = [
    "DealCreateRequest",
    "DealListRequest",
    "DealListResponse",
    "DealReadRequest",
    "DealStatus",
    "DealUpdateRequest",
    "TenantDealRecord",
]
