"""Security *types* and FastAPI security dependencies.

This module holds no policy. It declares the OpenAPI security schemes, the two shapes that
travel between services — :class:`AuthContext` (what Authentication produces) and
:class:`RequestContext` (what everything downstream consumes) — and the dependencies that
attach a scheme to a route.

**The load-bearing rule (IC-013 §7).** :class:`RequestContext` has exactly one constructor,
:meth:`RequestContext.from_auth_context`, and it accepts exactly one argument: an
:class:`AuthContext`. No inbound tenant or workspace parameter — header, cookie,
query-string, path segment, body field, host, or portal state — can reach it. That is what
stops a client injecting a tenant, and an architecture test proves the constructor is the
only construction site in the BFF.
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from .correlation import current_correlation_id
from .errors import unauthenticated
from .types import PlatformRole, WorkspaceType

#: The scheme presented to frontend clients at the BFF — the only public ingress (E-1).
client_bearer = HTTPBearer(
    scheme_name="ClientBearer",
    description="OIDC bearer access token issued by the configured identity provider (IC-005).",
    auto_error=False,
)

#: The scheme presented on internal service-to-service surfaces. These surfaces are never
#: client-reachable (IC-013 §13); the credential is a second, independent control so that a
#: misconfigured network boundary alone is not sufficient to reach an internal service.
service_bearer = HTTPBearer(
    scheme_name="InternalServiceBearer",
    description="Internal service-to-service credential. Never issued to a client; internal network zones only (IC-013 §13).",
    auto_error=False,
)


class AuthContext(BaseModel):
    """The Authentication Service's output — references only (IC-005).

    Never carries a token, a secret, a credential, a name, an email, or any PII. The
    ``active_tenant_ref`` is the **signed** active-tenant claim; ``None`` denotes a
    tenantless CONTROL principal operating in the Control Workspace.
    """

    correlation_id: str = Field(description="Correlation id this authentication was performed under.")
    principal_ref: str = Field(description="Opaque reference to the authenticated principal. Never a name or email.")
    role: PlatformRole = Field(description="The platform role carried by the validated token.")
    active_tenant_ref: Optional[str] = Field(
        default=None,
        description="The signed active-tenant claim, or null for a tenantless CONTROL principal.",
    )


class RequestContext(BaseModel):
    """The canonical per-request context (IC-013 §7) consumed without further resolution.

    Exactly the five canonical fields. It carries no token, secret, credential, DSN, or
    physical-database identifier, and no name, email, or PII — identity is resolved at
    presentation time, never carried here.
    """

    correlation_id: str = Field(description="Correlation id tying this request together across services.")
    principal_ref: str = Field(description="Opaque reference to the authenticated principal.")
    role: PlatformRole = Field(description="The principal's platform role, taken from the validated token.")
    tenant_context: Optional[str] = Field(
        default=None,
        description="The signed active-tenant claim, or null for tenantless-CONTROL. The sole routing authority.",
    )
    workspace_type: WorkspaceType = Field(
        description="Presentation label derived FROM the tenant context. Never a routing input or database selector."
    )

    @classmethod
    def from_auth_context(cls, auth: AuthContext) -> "RequestContext":
        """The one and only way to build a :class:`RequestContext` (IC-013 §7).

        The signature is the enforcement: there is no parameter through which a header,
        cookie, query value, or body field could contribute. ``workspace_type`` is
        *computed from* the signed claim — the tenant context is never derived from the
        workspace (IC-013 §6).
        """
        workspace = WorkspaceType.CONTROL_WORKSPACE if auth.active_tenant_ref is None else WorkspaceType.TENANT_WORKSPACE
        return cls(
            correlation_id=auth.correlation_id,
            principal_ref=auth.principal_ref,
            role=auth.role,
            tenant_context=auth.active_tenant_ref,
            workspace_type=workspace,
        )


#: ``Annotated`` dependency aliases. Using ``Annotated`` rather than a call in the default
#: argument keeps the FastAPI idiom and the repository lint rules (flake8-bugbear B008)
#: compatible without a per-file exemption.
_ClientCredentials = Annotated[Optional[HTTPAuthorizationCredentials], Depends(client_bearer)]
_ServiceCredentials = Annotated[Optional[HTTPAuthorizationCredentials], Depends(service_bearer)]


async def require_client_bearer(credentials: _ClientCredentials) -> str:
    """Extract a client bearer credential or fail closed with the canonical 401."""
    if credentials is None or not credentials.credentials:
        raise unauthenticated()
    return credentials.credentials


async def require_service_bearer(credentials: _ServiceCredentials) -> str:
    """Extract an internal service credential or fail closed with the canonical 401."""
    if credentials is None or not credentials.credentials:
        raise unauthenticated()
    return credentials.credentials


#: The two dependency aliases route handlers use. ``ClientBearer`` appears on BFF routes;
#: ``ServiceBearer`` appears on internal service routes (IC-013 §13).
ClientBearer = Annotated[str, Depends(require_client_bearer)]
ServiceBearer = Annotated[str, Depends(require_service_bearer)]


async def correlation(request: Request) -> str:
    """The correlation id bound to this request by :class:`CorrelationMiddleware`."""
    del request  # bound via contextvar, not via request state
    return current_correlation_id()


__all__ = [
    "AuthContext",
    "ClientBearer",
    "RequestContext",
    "ServiceBearer",
    "client_bearer",
    "correlation",
    "require_client_bearer",
    "require_service_bearer",
    "service_bearer",
]
