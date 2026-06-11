"""auth_router domain shapes (vendor-neutral, decoupled from control_plane).

These are auth-local DTOs so auth_router never imports control_plane (DAG rule 2);
the control-plane read API serializes to these shapes across the transport boundary.
No tokens/secrets/JWKS appear in any output context (IC-005 disclosure).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from shared.errors import DenialReason


class Role(Enum):
    CONTROL = "CONTROL"
    MASTER_AGENT = "MASTER_AGENT"
    TENANT_ADMIN = "TENANT_ADMIN"
    TENANT_AGENT = "TENANT_AGENT"
    STARTUP_USER = "STARTUP_USER"
    INVESTOR_USER = "INVESTOR_USER"


@dataclass(frozen=True)
class IssuerConfig:
    """Validation policy for one issuer (platform or per-tenant federation).

    `jwks` maps `kid` -> opaque key material understood by the SignatureVerifier
    (public JWK for asymmetric providers; symmetric key for the test verifier).
    `allowed_algs` is the issuer-specific allowlist (asymmetric-only in production).
    """

    issuer: str
    audience: str
    allowed_algs: List[str]
    jwks: Dict[str, object]
    tenant_claim: str = "tenant"


@dataclass(frozen=True)
class Claims:
    subject: str
    issuer: str
    audience: str
    tenant: Optional[str]
    # Only non-sensitive, needed claims are surfaced; the raw token is never retained.


@dataclass(frozen=True)
class FederationView:
    tenant_id: str
    oidc_issuer: str
    oidc_audience: str
    jwks_ref: str
    claim_to_tenant_rule: str


@dataclass(frozen=True)
class TenantStateView:
    tenant_id: str
    lifecycle_state: str  # IC-002 lifecycle state name
    ready: bool


@dataclass(frozen=True)
class AuthContext:
    """The authenticated result. Carries references only — never a token/secret."""

    correlation_id: str
    principal_ref: str
    active_tenant_id: Optional[str]
    role: Optional[str]


class AuthDenied(Exception):
    """Authentication/authorization denial. Carries only a non-sensitive reason + status."""

    def __init__(self, reason: DenialReason, http_status: int, public_code: str) -> None:
        super().__init__(public_code)
        self.reason = reason
        self.http_status = http_status
        self.public_code = public_code


def unauthenticated(code: str = "unauthenticated") -> AuthDenied:
    return AuthDenied(DenialReason.UNAUTHENTICATED, 401, code)


def forbidden(code: str = "forbidden") -> AuthDenied:
    # Consistent denial for unknown-tenant / non-member / carrier-mismatch (no existence leak).
    return AuthDenied(DenialReason.FORBIDDEN, 403, code)


def not_ready(code: str = "not_ready") -> AuthDenied:
    return AuthDenied(DenialReason.NOT_READY, 403, code)


def unavailable(code: str = "unavailable") -> AuthDenied:
    return AuthDenied(DenialReason.UNAVAILABLE, 503, code)
