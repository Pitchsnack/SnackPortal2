"""BFF-local transport shapes and the ports the ingress pipeline depends on.

The BFF imports no other service's implementation (IC-013 §13), so the shapes it exchanges
with Authentication, Access Control, the Database Router and Audit are declared here and
serialized across the boundary. That is not duplication for its own sake: it is what keeps
the fourteen services independently bootable and independently deployable, and it is what
the import-linter independence contract enforces.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Protocol

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


@dataclass(frozen=True)
class TenantRecordView:
    """A tenant-resident record as the router returned it, before DTO composition."""

    record_ref: str
    fields: Dict[str, Optional[str]]


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
    """Bind exactly one physical database, and read or write within it."""

    def resolve(self, context: RequestContext) -> RoutedTenant:
        ...

    def list_records(self, context: RequestContext, family: str, limit: int) -> List[TenantRecordView]:
        ...

    def read_record(self, context: RequestContext, family: str, record_ref: str) -> Optional[TenantRecordView]:
        ...

    def create_record(self, context: RequestContext, family: str, fields: Dict[str, Optional[str]]) -> TenantRecordView:
        ...

    def update_record(
        self, context: RequestContext, family: str, record_ref: str, fields: Dict[str, Optional[str]]
    ) -> TenantRecordView:
        ...


class ControlReadPort(Protocol):
    """Read Control-resident data: memberships and the global directories."""

    def list_memberships(self, principal_ref: str) -> List[Dict[str, str]]:
        ...

    def list_directory(self, directory: str) -> List[Dict[str, str]]:
        ...

    def get_directory_record(self, directory: str, record_ref: str) -> Optional[Dict[str, str]]:
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
    "RoutedTenant",
    "TenantRecordView",
    "TenantRoutingPort",
]
