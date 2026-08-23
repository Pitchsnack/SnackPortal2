"""Startup Service wire models.

Field sets come from the accepted tenant DDL (``003_startups.sql``) and from IC-009 §D, not
from anything invented to round out the API. Two shapes exist on purpose:

* :class:`TenantStartupRecord` — the internal service's full record, which IC-009 §D permits
  for the business-domain tier ("permission-scoped fields");
* :class:`TenantStartupDetail` — the **contract-pinned** eight-field shape adopted under D-42
  and carried in IC-009's CLM section, which the BFF composes for the frontend. It carries no
  email, person name, founder, owner reference, media field, URL, tenant name or code,
  physical-DB identifier, or secret, and nothing may be added to it here.

``Global Record ≠ Tenant Record``: ``global_startup_id`` is a **soft reference** to a Control
directory record, never a foreign key, and a tenant edit never mutates the global record.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from ...shared.security import RequestContext
from ...shared.types import RecordResidency

#: The sole CLM-mutable field bound: at most 500 characters (IC-009 CLM section).
SHORT_DESCRIPTION_MAX_CHARS = 500


class TenantStartupDetail(BaseModel):
    """The contract-pinned tenant Startup read/update shape (IC-009 CLM, adopted under D-42).

    Exactly eight fields. The provenance triple follows D-37 §10 with tenant-resident values,
    and ``lineage_reference`` is present only when the record was imported.
    """

    record_ref: str = Field(description="Opaque reference to the tenant-resident Startup record. Never a raw row key.")
    display_name: str = Field(description="The Startup's organization display name.")
    short_description: Optional[str] = Field(
        default=None, description="Bounded free text, at most 500 characters. The sole CLM-mutable field."
    )
    investment_stage: Optional[str] = Field(default=None, description="Bounded investment-stage label.")
    record_origin: str = Field(default="tenant", description="Provenance marker (D-37 §10). Always 'tenant' for this record.")
    record_residency: RecordResidency = Field(
        default=RecordResidency.TENANT, description="Provenance marker. Tenant-resident records live in one tenant database."
    )
    record_type: str = Field(default="startup", description="Provenance marker (D-37 §10).")
    lineage_reference: Optional[str] = Field(
        default=None, description="Tenant lineage row reference. Present only when the record was imported."
    )


class TenantStartupRecord(BaseModel):
    """The service's full tenant Startup record — the accepted DDL columns, as references and scalars."""

    record_ref: str = Field(description="Opaque reference to the tenant-resident Startup record.")
    global_startup_id: Optional[str] = Field(
        default=None,
        description="Soft reference to the Control global directory record this copy came from. Never a foreign key.",
    )
    company_name: str = Field(description="Organization display name as stored in the tenant database.")
    company_type: Optional[str] = Field(default=None, description="Organization type label.")
    company_url: Optional[str] = Field(default=None, description="Normalized company website URL, or null.")
    headquarters_country: Optional[str] = Field(default=None, description="Headquarters country label.")
    headquarters_city: Optional[str] = Field(default=None, description="Headquarters city label.")
    region: Optional[str] = Field(default=None, description="Region label.")
    year_founded: Optional[str] = Field(default=None, description="Year founded, as stored.")
    industry: Optional[str] = Field(default=None, description="Industry label.")
    investment_stage: Optional[str] = Field(default=None, description="Investment-stage label.")
    short_description: Optional[str] = Field(default=None, description="Bounded free text, at most 500 characters.")
    product_overview: Optional[str] = Field(default=None, description="Product overview free text.")
    lineage_reference: Optional[str] = Field(
        default=None, description="Tenant lineage row reference. Present only when the record was imported."
    )

    def to_detail(self) -> TenantStartupDetail:
        """Narrow to the contract-pinned shape. The BFF composes from this, never from the row."""
        return TenantStartupDetail(
            record_ref=self.record_ref,
            display_name=self.company_name,
            short_description=self.short_description,
            investment_stage=self.investment_stage,
            lineage_reference=self.lineage_reference,
        )


class StartupListRequest(BaseModel):
    """List tenant Startups within exactly one tenant database."""

    context: RequestContext = Field(description="The canonical RequestContext naming the single active tenant.")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum records to return. Bounded to keep reads finite.")


class StartupReadRequest(BaseModel):
    """Read one tenant Startup."""

    context: RequestContext = Field(description="The canonical RequestContext naming the single active tenant.")
    record_ref: str = Field(min_length=1, max_length=256, description="Opaque reference to the record to read.")


class StartupCreateRequest(BaseModel):
    """Create one tenant Startup."""

    context: RequestContext = Field(description="The canonical RequestContext naming the single active tenant.")
    company_name: str = Field(min_length=1, max_length=256, description="Organization display name. Required.")
    company_type: Optional[str] = Field(default=None, max_length=128, description="Organization type label.")
    company_url: Optional[str] = Field(
        default=None, max_length=512, description="Company website. Normalized on write; a malformed value is rejected."
    )
    headquarters_country: Optional[str] = Field(default=None, max_length=128, description="Headquarters country label.")
    headquarters_city: Optional[str] = Field(default=None, max_length=128, description="Headquarters city label.")
    region: Optional[str] = Field(default=None, max_length=128, description="Region label.")
    year_founded: Optional[str] = Field(default=None, max_length=8, description="Year founded.")
    industry: Optional[str] = Field(default=None, max_length=128, description="Industry label.")
    investment_stage: Optional[str] = Field(default=None, max_length=128, description="Investment-stage label.")
    short_description: Optional[str] = Field(
        default=None, max_length=SHORT_DESCRIPTION_MAX_CHARS, description="Bounded free text, at most 500 characters."
    )
    product_overview: Optional[str] = Field(default=None, max_length=4000, description="Product overview free text.")
    global_startup_id: Optional[str] = Field(
        default=None,
        max_length=256,
        description="Soft reference to the global record this copy came from, when created by import.",
    )


class StartupUpdateRequest(BaseModel):
    """Update one tenant Startup — the bounded CLM update.

    Exactly one mutable field. A request carrying any other field is rejected fail-closed with
    no partial write (IC-009 CLM section), which is why this model does not simply accept the
    create shape with everything optional.
    """

    context: RequestContext = Field(description="The canonical RequestContext naming the single active tenant.")
    record_ref: str = Field(min_length=1, max_length=256, description="Opaque reference to the record to update.")
    short_description: Optional[str] = Field(
        default=None,
        max_length=SHORT_DESCRIPTION_MAX_CHARS,
        description="The sole mutable field: bounded free text at most 500 characters, or null to clear.",
    )


class StartupListResponse(BaseModel):
    """Startups from exactly one tenant database, in deterministic order."""

    tenant_ref: str = Field(description="The single tenant these records came from.")
    records: List[TenantStartupRecord] = Field(
        description="The records, in deterministic order. Callers MUST NOT re-sort them."
    )


class DuplicateCandidate(BaseModel):
    """One possible duplicate of a proposed Startup, by reference."""

    record_ref: str = Field(description="Opaque reference to the existing record that may be a duplicate.")
    display_name: str = Field(description="Display name of the existing record, for human review.")
    reason: str = Field(description="Why it matched: 'name' or 'website'. Never a similarity score presented as truth.")


class DuplicateCheckRequest(BaseModel):
    """Check a proposed Startup against what the tenant already holds."""

    context: RequestContext = Field(description="The canonical RequestContext naming the single active tenant.")
    company_name: str = Field(min_length=1, max_length=256, description="Proposed organization display name.")
    company_url: Optional[str] = Field(default=None, max_length=512, description="Proposed company website, if any.")


class DuplicateCheckResponse(BaseModel):
    """The duplicate-check verdict — candidates for a human, never an automatic decision."""

    candidates: List[DuplicateCandidate] = Field(
        description="Possible duplicates, in deterministic order. An empty list means none were found."
    )
    blocking: bool = Field(
        description="True when at least one candidate matched exactly. Advisory: the caller decides, this service does not."
    )


__all__ = [
    "SHORT_DESCRIPTION_MAX_CHARS",
    "DuplicateCandidate",
    "DuplicateCheckRequest",
    "DuplicateCheckResponse",
    "StartupCreateRequest",
    "StartupListRequest",
    "StartupListResponse",
    "StartupReadRequest",
    "StartupUpdateRequest",
    "TenantStartupDetail",
    "TenantStartupRecord",
]
