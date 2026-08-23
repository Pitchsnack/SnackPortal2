"""Control Plane Service — independently bootable FastAPI application (IC-013 §21).

    python -m snackportal2.services.control_plane.main
    uvicorn snackportal2.services.control_plane.main:app --host 127.0.0.1 --port 8003

Holds Control-resident metadata: the tenant registry and its lifecycle states, principal
memberships, and the global startup and investor directories. Every surface is internal
(IC-013 §13) — the frontend reaches this data only through the BFF.
"""

from __future__ import annotations

from typing import Annotated

import uvicorn
from fastapi import Path

from ...shared.config import load_settings
from ...shared.errors import consistent_tenant_denial, error_responses, invalid_request
from ...shared.security import ServiceBearer
from ...shared.service import build_app
from ...shared.types import TenantLifecycleState
from .models import (
    DirectoryKind,
    DirectoryListResponse,
    DirectoryRecord,
    MembershipRegistration,
    MembershipsResponse,
    RegistrationAck,
    TenantDescriptor,
    TenantReadinessResponse,
    TenantRegistration,
)
from .store import build_store, looks_like_a_connection_string

SERVICE = "control_plane"

settings = load_settings(SERVICE)

app = build_app(
    SERVICE,
    description=(
        "Control-resident metadata: the tenant registry and lifecycle state, principal memberships, "
        "and the global startup and investor directories (IC-001, IC-002, D-31). It never opens a tenant "
        "database and never resolves one."
    ),
    settings=settings,
)

_store = build_store()

TenantRef = Annotated[str, Path(min_length=1, max_length=128, description="Stable tenant reference to look up.")]
PrincipalRef = Annotated[str, Path(min_length=1, max_length=128, description="Principal whose memberships are read.")]
RecordRef = Annotated[str, Path(min_length=1, max_length=256, description="Global directory record reference.")]
DirectoryPath = Annotated[DirectoryKind, Path(description="Which global directory to read.")]


@app.get(
    "/internal/tenants/{tenant_ref}",
    response_model=TenantDescriptor,
    summary="Read a tenant descriptor",
    description=(
        "Return the registry's descriptor for one tenant: organization reference, lifecycle state, expected "
        "schema version, and the secret-store reference to its database association. The association is a "
        "reference, never a DSN or credential. An unknown tenant answers with the same consistent denial as "
        "an unreachable one."
    ),
    tags=["Tenant Registry"],
    operation_id="readTenantDescriptor",
    response_description="The tenant descriptor as the Control registry holds it.",
    responses=error_responses(401, 404, 422),
)
async def read_tenant(tenant_ref: TenantRef, _credential: ServiceBearer) -> TenantDescriptor:
    descriptor = _store.get_tenant(tenant_ref)
    if descriptor is None:
        raise consistent_tenant_denial()
    return descriptor


@app.get(
    "/internal/tenants/{tenant_ref}/readiness",
    response_model=TenantReadinessResponse,
    summary="Read tenant readiness",
    description=(
        "Report whether a tenant may be served. Only an ACTIVE tenant is serviceable; provisioning, "
        "suspended and disabled tenants are not. The verdict discloses no topology, database identity, or "
        "internal failure reason (IC-002, IC-013 §17)."
    ),
    tags=["Tenant Registry"],
    operation_id="readTenantReadiness",
    response_description="The tenant lifecycle state and whether it may be served.",
    responses=error_responses(401, 404, 422),
)
async def read_readiness(tenant_ref: TenantRef, _credential: ServiceBearer) -> TenantReadinessResponse:
    descriptor = _store.get_tenant(tenant_ref)
    if descriptor is None:
        raise consistent_tenant_denial()
    return TenantReadinessResponse(
        tenant_ref=descriptor.tenant_ref,
        lifecycle_state=descriptor.lifecycle_state,
        serviceable=descriptor.lifecycle_state is TenantLifecycleState.ACTIVE,
    )


@app.get(
    "/internal/memberships/{principal_ref}",
    response_model=MembershipsResponse,
    summary="List a principal's tenant memberships",
    description=(
        "Return every tenant membership the principal holds, with the role held in each (D-04 1:N). "
        "Membership is eligibility, not active selection: exactly one tenant is active per request, and it "
        "is the signed claim, never a value chosen from this list. An empty list is a lawful success."
    ),
    tags=["Memberships"],
    operation_id="listPrincipalMemberships",
    response_description="The principal's memberships in deterministic order.",
    responses=error_responses(401, 422),
)
async def list_memberships(principal_ref: PrincipalRef, _credential: ServiceBearer) -> MembershipsResponse:
    return MembershipsResponse(principal_ref=principal_ref, memberships=_store.list_memberships(principal_ref))


@app.get(
    "/internal/directories/{directory}/records",
    response_model=DirectoryListResponse,
    summary="Read a global directory",
    description=(
        "Return the records of one Control-resident global directory in deterministic order. Directory "
        "records are tenant-anonymous (D-35, which prevails on conflict): they carry no tenant reference, "
        "no membership reference and no lineage reference."
    ),
    tags=["Global Directory"],
    operation_id="readGlobalDirectory",
    response_description="The directory records in the store's deterministic order.",
    responses=error_responses(401, 422),
)
async def read_directory(directory: DirectoryPath, _credential: ServiceBearer) -> DirectoryListResponse:
    return DirectoryListResponse(directory=directory, records=_store.list_directory(directory))


@app.get(
    "/internal/directories/{directory}/records/{record_ref}",
    response_model=DirectoryRecord,
    summary="Read one global directory record",
    description=(
        "Return a single global directory record by its stable reference — the same reference an import "
        "later carries as its source (IC-003). Tenant-anonymous; a global record has no tenant to disclose."
    ),
    tags=["Global Directory"],
    operation_id="readGlobalDirectoryRecord",
    response_description="The requested global directory record.",
    responses=error_responses(401, 404, 422),
)
async def read_directory_record(
    directory: DirectoryPath, record_ref: RecordRef, _credential: ServiceBearer
) -> DirectoryRecord:
    record = _store.get_directory_record(directory, record_ref)
    if record is None:
        raise consistent_tenant_denial()
    return record


@app.put(
    "/internal/tenants",
    response_model=RegistrationAck,
    summary="Register or update a tenant",
    description=(
        "Record a tenant in the registry, including the secret-store reference to its database association. "
        "A database association that is connection-string shaped is rejected: this field is contractually a "
        "reference (D-14), and refusing at the write boundary means a DSN can never be read back out of it."
    ),
    tags=["Tenant Registry"],
    operation_id="registerTenant",
    response_description="Acknowledgement that the registry accepted the write.",
    responses=error_responses(401, 422),
)
async def register_tenant(registration: TenantRegistration, _credential: ServiceBearer) -> RegistrationAck:
    if looks_like_a_connection_string(registration.database_association_ref.store_ref):
        raise invalid_request()
    _store.put_tenant(
        TenantDescriptor(
            tenant_ref=registration.tenant_ref,
            organization_ref=registration.organization_ref,
            lifecycle_state=registration.lifecycle_state,
            expected_schema_version=registration.expected_schema_version,
            database_association_ref=registration.database_association_ref,
        )
    )
    return RegistrationAck(recorded=True, reference=registration.tenant_ref)


@app.put(
    "/internal/memberships",
    response_model=RegistrationAck,
    summary="Record a principal's membership in a tenant",
    description=(
        "Record that a principal holds a role in a tenant (D-04). Membership establishes tenant access, not "
        "what may be done there; the permission question is answered by the Access Control Service alone."
    ),
    tags=["Memberships"],
    operation_id="registerMembership",
    response_description="Acknowledgement that the registry accepted the write.",
    responses=error_responses(401, 422),
)
async def register_membership(registration: MembershipRegistration, _credential: ServiceBearer) -> RegistrationAck:
    _store.put_membership(registration.principal_ref, registration.tenant_ref, registration.role)
    return RegistrationAck(recorded=True, reference=registration.principal_ref)


if __name__ == "__main__":  # local development convenience — IC-013 §21 permits this block
    uvicorn.run(
        "snackportal2.services.control_plane.main:app",
        host=settings.host,  # loopback by omission — E-2
        port=settings.port,
        reload=settings.reload,  # off by omission; local development only — E-4
        access_log=settings.access_log,
        server_header=settings.server_header,
        proxy_headers=settings.proxy_headers,
    )
