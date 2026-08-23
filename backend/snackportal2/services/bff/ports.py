"""BFF-local transport shapes and the ports the ingress pipeline depends on.

The BFF imports no other service's implementation (IC-013 §13), so the shapes it exchanges
with Authentication, Access Control, the Database Router, the domain services and Audit are
declared here and serialized across the boundary. That is not duplication for its own sake: it
is what keeps the fourteen services independently bootable and independently deployable, and it
is what the import-linter independence contract enforces.

Note what the routing port can and cannot do. It **resolves** — proving exactly one database was
bound — and that is all. It cannot read or write a tenant record, because under D-48 the BFF is
permanently off the connection-grant allowlist: the process nearest the internet is the one
furthest from a credential.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol

from ...shared.operations import BffOperation
from ...shared.security import AuthContext, RequestContext
from ...shared.types import DatabaseDomain


class CarrierVerdict(str, Enum):
    """Mirror of the Authentication Service's carrier-match verdict (IC-013 §5)."""

    ABSENT = "absent"
    MATCHED = "matched"
    MISMATCH = "mismatch"
    CONTROL_ANOMALY = "control_anomaly"


@dataclass(frozen=True)
class AuthenticationResult:
    """What Authentication returned: a trusted identity plus a carrier verdict."""

    auth_context: AuthContext
    carrier_verdict: CarrierVerdict


@dataclass(frozen=True)
class AuthorizationResult:
    """What Access Control decided, and the single domain it decided for."""

    allowed: bool
    denial_code: Optional[str]
    resolved_domain: Optional[DatabaseDomain]


@dataclass(frozen=True)
class RoutedTenant:
    """The one physical database the router bound. A reference, never a DSN."""

    tenant_ref: str
    target_ref: str


class AuthenticationPort(Protocol):
    """Validate a client credential and check the carrier (IC-005)."""

    def authenticate(self, credential: str, carrier: Optional[str], correlation_id: str) -> Optional[AuthenticationResult]:
        """Return the result, or ``None`` when the credential is not valid."""
        ...


class AccessControlPort(Protocol):
    """Ask for an allow/deny decision (IC-014). Never evaluates one locally."""

    def decide(
        self,
        context: RequestContext,
        operation: BffOperation,
        record_ref: Optional[str] = None,
    ) -> AuthorizationResult:
        ...


class TenantRoutingPort(Protocol):
    """Bind exactly one physical database and report it as a reference.

    Resolution only. The BFF never receives a connection grant (D-48 C-1), so there is no method
    here through which it could read or write tenant data even if a future route tried.
    """

    def resolve(self, context: RequestContext) -> RoutedTenant:
        ...


class ControlReadPort(Protocol):
    """Read Control-resident data: memberships and the global directories."""

    def list_memberships(self, principal_ref: str) -> List[Dict[str, str]]:
        ...

    def list_directory(self, directory: str) -> List[Dict[str, str]]:
        ...

    def get_directory_record(self, directory: str, record_ref: str) -> Optional[Dict[str, str]]:
        ...


class DomainServicePort(Protocol):
    """Invoke one operation on one tenant-resident domain service.

    Typed at the *BFF route*, not here: every enumerated operation declares its own Pydantic
    request and response models and composes a contract-approved DTO from what this returns
    (IC-013 §19). This port carries the call, not the contract — which is precisely why no BFF
    route may hand a caller what it returns without composing.
    """

    def call(self, path: str, payload: Dict[str, Any]) -> Any:
        ...


class AuditPort(Protocol):
    """Emit one ingress-edge audit event. The BFF is the sole emitter (IC-013 §10)."""

    def emit(
        self,
        action: str,
        outcome: str,
        correlation_id: str,
        actor_ref: str,
        subject_ref: Optional[str] = None,
        tenant_ref: Optional[str] = None,
        record_ref: Optional[str] = None,
        carrier_ref: Optional[str] = None,
    ) -> None:
        ...


__all__ = [
    "AccessControlPort",
    "AuditPort",
    "AuthenticationPort",
    "AuthenticationResult",
    "AuthorizationResult",
    "CarrierVerdict",
    "ControlReadPort",
    "DomainServicePort",
    "RoutedTenant",
    "TenantRoutingPort",
]
