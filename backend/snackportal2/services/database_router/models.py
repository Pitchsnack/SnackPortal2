"""Database Router wire models.

The resolution response carries **no** DSN, host, database name, or credential: a caller
learns that a tenant resolved and to *which reference*, never to which machine.

The grant response is the one exception, and it exists only because D-48 moved connection
custody to the domain services. It is issued to an explicitly allowlisted service, names one
tenant, expires, and is never returned to the BFF or to any client (D-48 C-1…C-3).
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from ...shared.security import RequestContext


class RoutingRequest(BaseModel):
    """Ask the router to bind exactly one physical database for this request."""

    context: RequestContext = Field(
        description="The canonical RequestContext. The router consumes the signed claim and re-derives nothing."
    )


class RoutingResolution(BaseModel):
    """Exactly one resolved physical database, expressed as a reference.

    This is what the BFF receives. It proves that exactly one database was resolved without
    telling the ingress how to reach it.
    """

    tenant_ref: str = Field(description="The single active tenant this request resolved to, from the signed claim.")
    target_ref: str = Field(
        description="Opaque reference to the bound physical database. Never a DSN, host, database name, or credential."
    )
    expected_schema_version: str = Field(description="Schema version the registry expects of that tenant database.")


class TenantBindRequest(BaseModel):
    """A tenant-resident domain service asking for a connection grant (D-48)."""

    tenant_ref: str = Field(
        min_length=1,
        max_length=128,
        description="The single active tenant to bind, taken from the request's signed claim by the calling service.",
    )


class TenantConnectionGrantResponse(BaseModel):
    """A short-lived permission to open exactly one tenant database (D-48 C-2).

    Issued only to a service on the router's explicit grant allowlist. The BFF and the Access
    Control Service are never on it: the process nearest the internet and the process that
    decides access are both, deliberately, the furthest from a credential.
    """

    tenant_ref: str = Field(description="The one tenant this grant authorizes. A grant is never reusable across tenants.")
    target_ref: str = Field(description="Opaque reference to the bound physical database.")
    expected_schema_version: str = Field(description="Schema version the registry expects of that tenant database.")
    dsn: str = Field(
        description=(
            "Connection string for the one bound tenant database. MUST NOT be logged, audited, returned onward, "
            "or disclosed in any error, health or readiness response (D-48 C-3)."
        )
    )
    expires_at: str = Field(description="ISO-8601 UTC expiry. A service MUST NOT retain the grant beyond it.")


class GranteeRegistration(BaseModel):
    """One service permitted to receive connection grants. Read-only diagnostic shape."""

    service_ref: str = Field(description="The tenant-resident service permitted to hold a tenant connection.")


class GranteeListResponse(BaseModel):
    """The router's grant allowlist, as references. Never the credentials themselves."""

    grantees: List[GranteeRegistration] = Field(
        description="Services permitted to receive a connection grant, in deterministic order. Never a credential."
    )


__all__ = [
    "GranteeListResponse",
    "GranteeRegistration",
    "RoutingRequest",
    "RoutingResolution",
    "TenantBindRequest",
    "TenantConnectionGrantResponse",
]
