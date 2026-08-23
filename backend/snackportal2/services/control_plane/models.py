"""Control Plane wire models — Control-resident metadata, references only.

Field sets are carried forward from the accepted Control DDL (``control_tenants``,
``control_memberships``, ``control_directory``) so the schemas the rebuild serves are the
schemas already proven, not a fresh invention. What is *not* carried forward is the wire
exposure of anything credential-shaped: ``database_association_ref`` is a
:class:`SecretReference` — a pointer into a secret store, never the secret, never a DSN
(D-14).
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List

from pydantic import BaseModel, Field

from ...shared.types import PlatformRole, TenantLifecycleState


class DirectoryKind(str, Enum):
    """The Control-resident global directories (IC-001; D-31).

    There is no ``DEAL`` kind: the D-35 Global Deal Directory is architected but has no DDL
    and no contract-complete definition, so inventing one here would create a surface the
    contracts do not govern (Action Tracker #29).
    """

    GLOBAL_STARTUP = "GlobalStartupDirectory"
    GLOBAL_INVESTOR = "GlobalInvestorDirectory"


class SecretReference(BaseModel):
    """A pointer into a secret store (D-14). Never the secret, never a connection string."""

    store_ref: str = Field(description="Opaque key identifying the entry in the configured secret store.")
    version: str = Field(description="Version of the secret-store entry. A reference component, never a credential.")


class TenantDescriptor(BaseModel):
    """The IC-002 tenant descriptor as the registry holds it — references only.

    Carries no password, DSN, connection string, raw secret, session, API key, cloud
    credential, PII, or tenant business payload.
    """

    tenant_ref: str = Field(description="Stable tenant reference. The natural key of the registry.")
    organization_ref: str = Field(description="Opaque organization reference. Never an organization name.")
    lifecycle_state: TenantLifecycleState = Field(description="Registry lifecycle state governing readiness (IC-002).")
    expected_schema_version: str = Field(description="Schema version the tenant database is expected to be at.")
    database_association_ref: SecretReference = Field(
        description="Secret-store reference to the tenant's database association. A reference only, never a DSN."
    )


class MembershipEntry(BaseModel):
    """One principal-tenant-role membership (D-04 1:N; IC-002 Principal Membership Record).

    A membership DTO lawfully carries ``tenant_ref``: it is not a directory record, and the
    D-35 tenant-anonymity rule binds directory and publication DTOs only (IC-009 IR-08).
    """

    tenant_ref: str = Field(description="The tenant this membership is held in.")
    role: PlatformRole = Field(description="The platform role held in that tenant.")


class MembershipsResponse(BaseModel):
    """Every membership a principal holds. An empty list is a lawful success."""

    principal_ref: str = Field(description="The principal these memberships belong to.")
    memberships: List[MembershipEntry] = Field(
        description="The principal's memberships, in deterministic order. Empty is a valid answer, not an error."
    )


class DirectoryRecord(BaseModel):
    """One global directory record — tenant-anonymous (D-35, which prevails on conflict).

    Never carries ``tenant_id``, ``tenant_name``, ``tenant_code``, a tenant reference, a
    membership reference, or a lineage reference: a global record has no tenant and no
    provenance to disclose.
    """

    record_ref: str = Field(description="Stable global directory record identifier. The IC-003 import source reference.")
    display_name: str = Field(description="Non-sensitive global reference display name.")
    attributes: Dict[str, str] = Field(
        default_factory=dict,
        description="Non-sensitive global reference data. Never PII, never tenant-attributable.",
    )


class DirectoryListResponse(BaseModel):
    """A directory read, in the store's deterministic order."""

    directory: DirectoryKind = Field(description="Which global directory was read.")
    records: List[DirectoryRecord] = Field(
        description="The directory records in deterministic order. Callers MUST NOT re-sort them."
    )


class TenantReadinessResponse(BaseModel):
    """Whether a tenant may be served, without disclosing why it may not be."""

    tenant_ref: str = Field(description="The tenant the readiness verdict concerns.")
    lifecycle_state: TenantLifecycleState = Field(description="Registry lifecycle state (IC-002).")
    serviceable: bool = Field(description="True only when the tenant is ACTIVE. Any other state is not serviceable.")


class TenantRegistration(BaseModel):
    """Register or update one tenant in the registry."""

    tenant_ref: str = Field(min_length=1, max_length=128, description="Stable tenant reference to register.")
    organization_ref: str = Field(min_length=1, max_length=128, description="Opaque organization reference.")
    lifecycle_state: TenantLifecycleState = Field(description="Lifecycle state to record for this tenant.")
    expected_schema_version: str = Field(min_length=1, max_length=64, description="Expected tenant schema version.")
    database_association_ref: SecretReference = Field(
        description="Secret-store reference to the tenant's database association. Rejected if it looks like a DSN."
    )


class MembershipRegistration(BaseModel):
    """Record one principal-tenant-role membership."""

    principal_ref: str = Field(min_length=1, max_length=128, description="The principal gaining the membership.")
    tenant_ref: str = Field(min_length=1, max_length=128, description="The tenant the membership is held in.")
    role: PlatformRole = Field(description="The platform role held in that tenant.")


class RegistrationAck(BaseModel):
    """Acknowledgement of a registry write. Discloses no registry contents."""

    recorded: bool = Field(description="True when the registry accepted the write.")
    reference: str = Field(description="The reference that was written. Never a secret or a database identifier.")


__all__ = [
    "DirectoryKind",
    "DirectoryListResponse",
    "DirectoryRecord",
    "MembershipEntry",
    "MembershipRegistration",
    "MembershipsResponse",
    "RegistrationAck",
    "SecretReference",
    "TenantDescriptor",
    "TenantReadinessResponse",
    "TenantRegistration",
]
