"""api_gateway domain shapes (vendor-neutral) — Build Phase 7.

Gateway-local DTOs so the gateway never imports another service (DAG independence;
IC-010 §M): the Authenticator (IC-005) and Database Router are reached over transport
ports and serialize to these shapes across the boundary. References only — a shape
never holds a token, secret, credential, or payload (IC-010 §G/§T; IC-001).
Governed by IC-010 (§A/§B/§G/§J/§K/§Q/§X), IC-005, IC-002, IC-001.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional

from .portal import PortalDTO


class DispatchCategory(Enum):
    """IC-010 §Q endpoint-dispatch taxonomy — exactly one category per request."""

    TENANT_OPERATION = "TENANT_OPERATION"
    GLOBAL_DIRECTORY_READ = "GLOBAL_DIRECTORY_READ"
    MEMBERSHIPS_FOR_PRINCIPAL = "MEMBERSHIPS_FOR_PRINCIPAL"
    IMPORT_INITIATION = "IMPORT_INITIATION"


class DatabaseDomain(Enum):
    """The single resolution domain a request targets (IC-010 §K/§O — never both)."""

    CONTROL = "CONTROL"
    TENANT = "TENANT"


class AuditAction(Enum):
    """IC-010 §J runtime/operational-audit emit-set (the gateway is the emitter).

    The four denial/anomaly actions are the historic gateway-edge set — unchanged.
    ``WORKSPACE_MEMBERSHIPS_READ`` (B5-BLK-6C-B) is the separate gateway-edge
    success-access subclass (IC-002 Audit-Section Extension class 3b): never a denial,
    anomaly, or routing action.
    """

    CARRIER_MISMATCH = "CarrierMismatch"
    CARRIER_ON_CONTROL_ANOMALY = "CarrierOnControlAnomaly"
    ROUTE_DENIED = "RouteDenied"
    ISOLATION_ANOMALY = "IsolationAnomaly"
    WORKSPACE_MEMBERSHIPS_READ = "workspace_memberships_read"


@dataclass(frozen=True)
class InboundRequest:
    """A channel-agnostic client request at the gateway edge (IC-010 §N).

    `authorization` is the bearer credential handed to the Authenticator (IC-005); it is
    NEVER placed in the RequestContext. Recognized carriers are read only via
    ``carrier.recognized_carriers``; cookies/query/workspace state are prohibited carriers
    (IC-010 §E) and are never read as a tenant selector.
    """

    method: str
    path: str
    host: str = ""
    headers: Mapping[str, str] = field(default_factory=dict)
    query: Mapping[str, str] = field(default_factory=dict)
    cookies: Mapping[str, str] = field(default_factory=dict)
    authorization: Optional[str] = None


@dataclass(frozen=True)
class AuthResult:
    """The Authenticator (IC-005) output the gateway consumes — references only.

    Mirrors ``auth_router.AuthContext`` across the transport boundary (the gateway never
    imports auth_router). ``active_tenant_id`` is the signed active-tenant claim, or None
    for a tenantless CONTROL principal. Never a token/secret.
    """

    correlation_id: str
    principal_ref: str
    active_tenant_id: Optional[str]
    role: Optional[str]


@dataclass(frozen=True)
class DispatchDecision:
    """A single resolved dispatch (IC-010 §Q): one category → one domain → one database."""

    category: DispatchCategory
    domain: DatabaseDomain
    target_tenant_id: Optional[str]  # the single active tenant for TENANT domain; None for CONTROL


@dataclass(frozen=True)
class GatewayAuditEvent:
    """IC-010 §J record — references only (IC-001:94-98 Global Audit Representation Rule).

    Never carries names/emails/PII/payloads/secrets. ``carrier_ref`` (when present) is the
    carrier-asserted tenant id rendered as an opaque, length-bounded string for anomaly
    attribution only — never parsed, resolved, or trusted (IC-005:116).

    The four optional success-shape fields (B5-BLK-6C-B; IC-002 class 3b) default to
    ``None`` so the four denial/anomaly events construct unchanged. The
    ``workspace_memberships_read`` success-access event populates them; its contract
    mapping is ``actor_ref`` -> actor_principal_ref and ``subject_ref`` ->
    subject_principal_ref (self-scoped: equal). Never the returned membership collection.
    """

    action: AuditAction
    correlation_id: str
    outcome: str
    actor_ref: Optional[str] = None
    tenant_ref: Optional[str] = None
    carrier_ref: Optional[str] = None
    audit_id: Optional[str] = None
    subject_ref: Optional[str] = None
    occurred_at: Optional[str] = None
    event_version: Optional[int] = None


@dataclass(frozen=True)
class GatewayResponse:
    """The gateway's fail-closed result. On rejection: status + public_code, no payload.

    ``portal_dto`` (B5-BLK-6B; IC-010 §V) is the single gateway-composed,
    contract-approved DTO seam: attached ONLY on an allowed, dispatched success and ONLY
    from the approved IC-009-R1 catalogue (``portal.py``). On every denial it is ``None``
    (§V.2: the gateway returns the §L denial and no DTO). Never a body/payload field —
    arbitrary downstream pass-through remains forbidden.
    """

    status: int
    public_code: str
    dispatched: bool = False
    category: Optional[DispatchCategory] = None
    portal_dto: Optional[PortalDTO] = None


@dataclass(frozen=True)
class RouteOutcome:
    """References-only router-dispatch outcome (IC-010 §152-154; D-07E-6a; 07E-2-X).

    The Database Router's non-live handoff result that the gateway maps into a
    GatewayResponse. Carries NO DB handle/connection, tenant id, DB name, secret/DSN/
    credential, request/response body, or business payload (IC-010 §G/§T; §154 forbids
    full response-body pass-through) — non-live: it confirms the handoff outcome only.
    ``category`` is gateway-owned (§Q) and is NEVER carried here.
    """

    status: int
    public_code: str
    dispatched: bool = True


@dataclass(frozen=True)
class RequestMetric:
    """A non-disclosing per-request observability metric (IC-010 §S; WP-11).

    Operational labels ONLY — NEVER a tenant identity/count, database name, connection
    detail, or topology. ``category`` is a DispatchCategory value (or None for a
    pre-dispatch rejection); ``outcome`` is the fixed public_code; both are tenant-agnostic.
    """

    category: Optional[str]
    outcome: str
    status: int
    duration_ms: float


class RequestRejected(Exception):
    """Fail-closed rejection (IC-010 §L). Carries only a non-sensitive status + public code."""

    def __init__(self, http_status: int, public_code: str) -> None:
        super().__init__(public_code)
        self.http_status = http_status
        self.public_code = public_code


def carrier_mismatch() -> RequestRejected:
    # Consistent 403; never leaks tenant existence (IC-010 §E/§L).
    return RequestRejected(403, "carrier_mismatch")


def unauthenticated() -> RequestRejected:
    return RequestRejected(401, "unauthenticated")


def forbidden(code: str = "forbidden") -> RequestRejected:
    return RequestRejected(403, code)


def unavailable() -> RequestRejected:
    return RequestRejected(503, "unavailable")
