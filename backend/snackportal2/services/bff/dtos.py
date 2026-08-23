"""The IC-009-R1 portal DTO catalogue, as Pydantic models.

These are the **only** shapes the BFF may return (IC-013 §19). The composer refuses any type
absent from the catalogue, and a surface that merely relayed a downstream body would be a
gateway route and is forbidden — which is why every DTO below is built field by field from a
typed service result rather than constructed from a response dict.

Field sets are exactly IC-009's, unchanged. Two rules bind every one of them:

* **References only.** No name, email, PII, secret, token, DSN, physical-database identifier,
  connection datum, or router decision.
* **Tenant anonymity, scoped (IR-08).** *Directory* DTOs carry no tenant reference of any kind.
  *Membership* and *audit* DTOs are not directory records and lawfully carry ``tenant_id`` — the
  two record classes must never be conflated.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from ...shared.types import PlatformRole

#: The contract and revision this composing seam serves (IC-013 §19.3 traceability).
PORTAL_CONTRACT_ID = "IC-009"
PORTAL_CONTRACT_REVISION = "IC-009-R1"


class ImportOutcomeDTO(str, Enum):
    """What an import call actually did."""

    CREATED = "created"
    REPLAYED = "replayed"


class DirectoryEntryDTO(BaseModel):
    """One tenant-anonymous discovery entry (IC-001 Directory Data; D-35).

    Carries no tenant attribution, no lineage reference and no physical-database identifier: a
    global record has no tenant, and a directory reader must not be able to infer one.
    """

    record_ref: str = Field(description="Stable global directory record id. The IC-003 import source reference.")
    display_name: str = Field(description="Non-sensitive global reference display value.")


class GlobalStartupSummaryDTO(BaseModel):
    """The Global Startup Directory read summary — tenant-anonymous (D-35 prevails)."""

    records: List[DirectoryEntryDTO] = Field(
        description="Directory entries in the Control Plane's deterministic order. The BFF never re-sorts them."
    )
    record_origin: str = Field(default="global", description="Provenance marker (D-37 §10), with its global value.")
    record_residency: str = Field(default="global", description="Provenance marker. Global records are Control-resident.")
    record_type: str = Field(default="GlobalStartupDirectory", description="Provenance marker naming the directory kind.")


class GlobalInvestorSummaryDTO(BaseModel):
    """The Global Investor Directory read summary — same rules as the startup summary."""

    records: List[DirectoryEntryDTO] = Field(
        description="Directory entries in the Control Plane's deterministic order. The BFF never re-sorts them."
    )
    record_origin: str = Field(default="global", description="Provenance marker (D-37 §10), with its global value.")
    record_residency: str = Field(default="global", description="Provenance marker. Global records are Control-resident.")
    record_type: str = Field(default="GlobalInvestorDirectory", description="Provenance marker naming the directory kind.")


class MembershipEntryDTO(BaseModel):
    """Exactly the IC-002 Principal Membership Record triple.

    ``display_ref`` is composed by the BFF and never stored: the Control Plane returns no display
    value, and resolving one to a label happens at presentation time (D-03).
    """

    tenant_id: str = Field(description="The tenant this membership is held in. Lawful here: a membership is not a directory record.")
    role: PlatformRole = Field(description="The platform role held in that tenant.")
    display_ref: str = Field(description="Composed, deterministic display reference. Never a name or PII.")


class WorkspaceMembershipDTO(BaseModel):
    """The workspace-switcher feed. An empty list is a lawful success, not an error."""

    memberships: List[MembershipEntryDTO] = Field(
        description="The principal's memberships. A principal with none is a valid answer, never a failure."
    )


class TenantStartupDetailDTO(BaseModel):
    """The tenant Startup read/update response — exactly the eight contract-pinned fields.

    No email, person name, founder, owner reference, media or logo field, URL, tenant name or
    code, physical-database identifier, secret, or any other tenant business payload may ever
    join this shape.
    """

    record_ref: str = Field(description="The tenant-resident Startup record reference the route addressed.")
    display_name: str = Field(description="The Startup's organization display name.")
    short_description: Optional[str] = Field(default=None, description="Bounded free text, at most 500 characters.")
    investment_stage: Optional[str] = Field(default=None, description="Bounded investment-stage label.")
    record_origin: str = Field(default="tenant", description="Provenance marker (D-37 §10).")
    record_residency: str = Field(default="tenant", description="Provenance marker. This record lives in one tenant database.")
    record_type: str = Field(default="startup", description="Provenance marker (D-37 §10).")
    lineage_reference: Optional[str] = Field(
        default=None, description="Tenant lineage row reference. Present only when the record was imported."
    )


class TenantStartupListDTO(BaseModel):
    """A page of tenant Startups, in the service's deterministic order."""

    records: List[TenantStartupDetailDTO] = Field(description="Startup details in deterministic order.")


class TenantInvestorDetailDTO(BaseModel):
    """The tenant Investor read/update response — the Investor counterpart shape."""

    record_ref: str = Field(description="The tenant-resident Investor record reference the route addressed.")
    display_name: str = Field(description="The Investor's organization display name.")
    short_description: Optional[str] = Field(default=None, description="Bounded free text, at most 500 characters.")
    investor_type: Optional[str] = Field(default=None, description="Investor type label.")
    record_origin: str = Field(default="tenant", description="Provenance marker (D-37 §10).")
    record_residency: str = Field(default="tenant", description="Provenance marker.")
    record_type: str = Field(default="investor", description="Provenance marker (D-37 §10).")
    lineage_reference: Optional[str] = Field(
        default=None, description="Tenant lineage row reference. Present only when the record was imported."
    )


class TenantInvestorListDTO(BaseModel):
    """A page of tenant Investors, in the service's deterministic order."""

    records: List[TenantInvestorDetailDTO] = Field(description="Investor details in deterministic order.")


class TenantDealDetailDTO(BaseModel):
    """The tenant Deal read response."""

    record_ref: str = Field(description="The tenant-resident Deal record reference the route addressed.")
    deal_name: str = Field(description="Deal display name.")
    startup_ref: str = Field(description="Reference to the tenant Startup this deal concerns.")
    investor_ref: Optional[str] = Field(default=None, description="Reference to the tenant Investor, or null while unmatched.")
    stage: Optional[str] = Field(default=None, description="Deal stage label.")
    status: Optional[str] = Field(default=None, description="Deal status from the service's closed vocabulary.")
    record_origin: str = Field(default="tenant", description="Provenance marker (D-37 §10).")
    record_residency: str = Field(default="tenant", description="Provenance marker.")
    record_type: str = Field(default="deal", description="Provenance marker (D-37 §10).")


class TenantDealListDTO(BaseModel):
    """A page of tenant Deals, in the service's deterministic order."""

    records: List[TenantDealDetailDTO] = Field(description="Deal details in deterministic order.")


class ImportResultDTO(BaseModel):
    """The import completion envelope — references only (IC-009 §D).

    Never carries a tenant row, the source record's content, a database name, a secret, or any
    router detail.
    """

    source_ref: str = Field(description="The global source reference this copy came from.")
    target_tenant_ref: str = Field(description="The signed active tenant the copy was written into.")
    tenant_record_ref: str = Field(description="Reference to the created tenant record. Never a raw row key.")
    lineage_ref: str = Field(description="Reference to the lineage row recording this derivation.")
    import_id: str = Field(description="Identifier of the import job. Stable across a replay.")
    outcome: ImportOutcomeDTO = Field(description="Whether this call created the copy or replayed an existing import.")


class LineageSummaryDTO(BaseModel):
    """A tenant record's provenance — tenant-resident references only (IC-004)."""

    target_ref: str = Field(description="The tenant record whose provenance this describes.")
    lineage_references: List[str] = Field(description="References to the lineage rows, in deterministic order.")
    source_references: List[str] = Field(description="References to the origins those rows name. Never origin content.")


#: The approved catalogue. :func:`compose` refuses any type absent from it, which is what keeps
#: the composing seam from degenerating into a pass-through.
APPROVED_DTOS = (
    DirectoryEntryDTO,
    GlobalStartupSummaryDTO,
    GlobalInvestorSummaryDTO,
    MembershipEntryDTO,
    WorkspaceMembershipDTO,
    TenantStartupDetailDTO,
    TenantStartupListDTO,
    TenantInvestorDetailDTO,
    TenantInvestorListDTO,
    TenantDealDetailDTO,
    TenantDealListDTO,
    ImportResultDTO,
    LineageSummaryDTO,
)


def compose_display_ref(tenant_id: str) -> str:
    """The deterministic, references-only membership display reference. Derived, never stored."""
    return "ref:tenant/" + tenant_id + "/display"


def compose(dto: BaseModel) -> BaseModel:
    """Emit only types the approved catalogue names (IC-013 §19.1).

    Any other type is refused, and the refusal collapses fail-closed rather than producing a
    partial or unapproved response.
    """
    if type(dto) not in APPROVED_DTOS:
        raise ValueError("unapproved portal DTO type: " + type(dto).__name__)
    return dto


__all__ = [
    "APPROVED_DTOS",
    "PORTAL_CONTRACT_ID",
    "PORTAL_CONTRACT_REVISION",
    "DirectoryEntryDTO",
    "GlobalInvestorSummaryDTO",
    "GlobalStartupSummaryDTO",
    "ImportOutcomeDTO",
    "ImportResultDTO",
    "LineageSummaryDTO",
    "MembershipEntryDTO",
    "TenantDealDetailDTO",
    "TenantDealListDTO",
    "TenantInvestorDetailDTO",
    "TenantInvestorListDTO",
    "TenantStartupDetailDTO",
    "TenantStartupListDTO",
    "WorkspaceMembershipDTO",
    "compose",
    "compose_display_ref",
]
