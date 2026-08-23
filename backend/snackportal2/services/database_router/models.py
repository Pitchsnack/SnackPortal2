"""Database Router wire models.

Nothing here carries a DSN, a credential, a database name, or a host. A caller learns that
a tenant resolved, and to *which reference* — never to which machine. That is the whole
point of putting resolution behind a service: the thing that knows how to reach a tenant
database is the only thing that knows how to reach a tenant database.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from ...shared.security import RequestContext


class RecordFamily(str, Enum):
    """The closed set of tenant-resident record families this router can address.

    This is a **physical storage map**, not domain knowledge: it names the tables of the
    accepted tenant DDL and nothing about what they mean. Business meaning — field sets,
    bounded update rules, provenance markers, duplicate checks, DTO composition — lives in
    the domain services, which is why those services own their own contracts and this one
    owns none of them.

    The set is closed because an open one would make this a generic data proxy addressable
    by table name, and a caller could then reach any table by asking for it.
    """

    STARTUPS = "startups"
    INVESTORS = "investors"
    DEALS = "deals"
    CONTACTS = "contacts"
    LINEAGE = "lineage"


class RoutingRequest(BaseModel):
    """Ask the router to bind exactly one physical database for this request."""

    context: RequestContext = Field(
        description="The canonical RequestContext. The router consumes the signed claim and re-derives nothing."
    )


class RoutingResolution(BaseModel):
    """Exactly one resolved physical database, expressed as a reference."""

    tenant_ref: str = Field(description="The single active tenant this request resolved to, from the signed claim.")
    target_ref: str = Field(
        description="Opaque reference to the bound physical database. Never a DSN, host, database name, or credential."
    )
    expected_schema_version: str = Field(description="Schema version the registry expects of that tenant database.")


class TenantRecord(BaseModel):
    """One tenant-resident row, as references and scalar fields."""

    record_ref: str = Field(description="Opaque reference to the tenant-resident record. Never a raw row primary key.")
    fields: Dict[str, Optional[str]] = Field(
        description="The record's stored scalar fields. Interpretation belongs to the owning domain service."
    )


class RecordListRequest(BaseModel):
    """List records of one family within exactly one tenant database."""

    context: RequestContext = Field(description="The canonical RequestContext naming the single active tenant.")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum records to return. Bounded to keep reads finite.")


class RecordReadRequest(BaseModel):
    """Read one record of one family within exactly one tenant database."""

    context: RequestContext = Field(description="The canonical RequestContext naming the single active tenant.")
    record_ref: str = Field(min_length=1, max_length=256, description="Opaque reference to the record to read.")


class RecordWriteRequest(BaseModel):
    """Create or update one record of one family within exactly one tenant database."""

    context: RequestContext = Field(description="The canonical RequestContext naming the single active tenant.")
    record_ref: Optional[str] = Field(
        default=None,
        max_length=256,
        description="Record to update, or null to create. A create never addresses an existing record.",
    )
    fields: Dict[str, Optional[str]] = Field(
        description="Scalar fields to write. Names outside the family's allowlist are rejected fail-closed."
    )


class RecordListResponse(BaseModel):
    """Records from exactly one tenant database, in deterministic order."""

    tenant_ref: str = Field(description="The single tenant these records came from.")
    family: RecordFamily = Field(description="The record family that was read.")
    records: List[TenantRecord] = Field(description="The records, in deterministic order. Callers MUST NOT re-sort them.")


__all__ = [
    "RecordFamily",
    "RecordListRequest",
    "RecordListResponse",
    "RecordReadRequest",
    "RecordWriteRequest",
    "RoutingRequest",
    "RoutingResolution",
    "TenantRecord",
]
