"""Investor Service wire models.

Field sets come from the accepted tenant DDL (``004_investors.sql``) and IC-009 §D. The
"Add My Investor" field set is exactly the DDL's scalar columns — nothing was invented to make
the API look complete, and the jsonb focus columns are handled as lists rather than flattened.

``Global Record ≠ Tenant Record``: ``global_investor_id`` is a soft reference to a Control
directory record, never a foreign key.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from ...shared.security import RequestContext
from ...shared.types import RecordResidency

SHORT_DESCRIPTION_MAX_CHARS = 500


class TenantInvestorDetail(BaseModel):
    """The portal-facing tenant Investor shape (IC-009 §D, business-domain tier).

    Mirrors the tenant Startup detail shape: references, a display name, bounded free text, and
    the mandatory D-37 §10 provenance triple. No email, person name, owner reference, URL,
    tenant name or code, physical-DB identifier, or secret.
    """

    record_ref: str = Field(description="Opaque reference to the tenant-resident Investor record.")
    display_name: str = Field(description="The Investor's organization display name.")
    short_description: Optional[str] = Field(default=None, description="Bounded free text, at most 500 characters.")
    investor_type: Optional[str] = Field(default=None, description="Investor type label.")
    record_origin: str = Field(default="tenant", description="Provenance marker (D-37 §10).")
    record_residency: RecordResidency = Field(default=RecordResidency.TENANT, description="Provenance marker.")
    record_type: str = Field(default="investor", description="Provenance marker (D-37 §10).")
    lineage_reference: Optional[str] = Field(
        default=None, description="Tenant lineage row reference. Present only when the record was imported."
    )


class TenantInvestorRecord(BaseModel):
    """The service's full tenant Investor record — the accepted DDL columns."""

    record_ref: str = Field(description="Opaque reference to the tenant-resident Investor record.")
    global_investor_id: Optional[str] = Field(
        default=None, description="Soft reference to the global directory record this copy came from."
    )
    investor_name: str = Field(description="Organization display name as stored in the tenant database.")
    investor_type: Optional[str] = Field(default=None, description="Investor type label.")
    website_url: Optional[str] = Field(default=None, description="Normalized investor website URL, or null.")
    headquarters_country: Optional[str] = Field(default=None, description="Headquarters country label.")
    headquarters_city: Optional[str] = Field(default=None, description="Headquarters city label.")
    region: Optional[str] = Field(default=None, description="Region label.")
    investment_stage_focus: List[str] = Field(
        default_factory=list,
        description="Investment stages this investor focuses on. A jsonb array in the DDL, never flattened to a string.",
    )
    industry_focus: List[str] = Field(default_factory=list, description="Industries this investor focuses on. A jsonb array in the DDL.")
    short_description: Optional[str] = Field(default=None, description="Bounded free text, at most 500 characters.")
    lineage_reference: Optional[str] = Field(
        default=None, description="Tenant lineage row reference. Present only when the record was imported."
    )

    def to_detail(self) -> TenantInvestorDetail:
        """Narrow to the portal-facing shape. The BFF composes from this, never from the row."""
        return TenantInvestorDetail(
            record_ref=self.record_ref,
            display_name=self.investor_name,
            short_description=self.short_description,
            investor_type=self.investor_type,
            lineage_reference=self.lineage_reference,
        )


class InvestorListRequest(BaseModel):
    """List tenant Investors within exactly one tenant database."""

    context: RequestContext = Field(description="The canonical RequestContext naming the single active tenant.")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum records to return.")


class InvestorReadRequest(BaseModel):
    """Read one tenant Investor."""

    context: RequestContext = Field(description="The canonical RequestContext naming the single active tenant.")
    record_ref: str = Field(min_length=1, max_length=256, description="Opaque reference to the record to read.")


class InvestorCreateRequest(BaseModel):
    """Create one tenant Investor — the Add My Investor field set."""

    context: RequestContext = Field(description="The canonical RequestContext naming the single active tenant.")
    investor_name: str = Field(min_length=1, max_length=256, description="Organization display name. Required.")
    investor_type: Optional[str] = Field(default=None, max_length=128, description="Investor type label.")
    website_url: Optional[str] = Field(
        default=None, max_length=512, description="Investor website. Normalized on write; a malformed value is rejected."
    )
    headquarters_country: Optional[str] = Field(default=None, max_length=128, description="Headquarters country label.")
    headquarters_city: Optional[str] = Field(default=None, max_length=128, description="Headquarters city label.")
    region: Optional[str] = Field(default=None, max_length=128, description="Region label.")
    investment_stage_focus: List[str] = Field(
        default_factory=list, max_length=32, description="Investment stages this investor focuses on."
    )
    industry_focus: List[str] = Field(default_factory=list, max_length=32, description="Industries this investor focuses on.")
    short_description: Optional[str] = Field(
        default=None, max_length=SHORT_DESCRIPTION_MAX_CHARS, description="Bounded free text, at most 500 characters."
    )
    global_investor_id: Optional[str] = Field(
        default=None, max_length=256, description="Soft reference to the global record this copy came from, when imported."
    )


class InvestorUpdateRequest(BaseModel):
    """Update one tenant Investor — the same bounded single-field discipline as Startups."""

    context: RequestContext = Field(description="The canonical RequestContext naming the single active tenant.")
    record_ref: str = Field(min_length=1, max_length=256, description="Opaque reference to the record to update.")
    short_description: Optional[str] = Field(
        default=None,
        max_length=SHORT_DESCRIPTION_MAX_CHARS,
        description="The sole mutable field: bounded free text at most 500 characters, or null to clear.",
    )


class InvestorListResponse(BaseModel):
    """Investors from exactly one tenant database, in deterministic order."""

    tenant_ref: str = Field(description="The single tenant these records came from.")
    records: List[TenantInvestorRecord] = Field(description="The records, in deterministic order. Callers MUST NOT re-sort them.")


__all__ = [
    "SHORT_DESCRIPTION_MAX_CHARS",
    "InvestorCreateRequest",
    "InvestorListRequest",
    "InvestorListResponse",
    "InvestorReadRequest",
    "InvestorUpdateRequest",
    "TenantInvestorDetail",
    "TenantInvestorRecord",
]
