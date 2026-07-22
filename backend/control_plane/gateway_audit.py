"""Control-Plane-local Gateway operational-audit write model and store port (Gateway Audit V1a).

The durable half of the Gateway Audit V1a architecture (Control-Plane-owned durable Gateway
operational-audit store behind a service boundary — the DBR-AR-2 Option B precedent re-homed to the
API-Gateway edge): the API Gateway emits its references-only edge events over the internal loopback
ingest edge, the Control Plane translates the wire payload into the local ``GatewayAuditRecord``
below, and a ``GatewayAuditStorePort`` adapter performs the single durable Control-DB INSERT into
``control_gateway_audit`` (DDL 012, created-not-applied). This module NEVER imports ``api_gateway``
(import-linter independence contract): the record is defined from the contract/DDL field list.

V1a wires ONLY the ``workspace_memberships_read`` success-access event (IC-002 class 3b; the
self-scoped MembershipsForPrincipal success); the record and DDL are shaped for the WHOLE
Gateway-edge class (the five frozen ``AuditAction`` string values) so the four denial/anomaly events
become a later additive sibling to the SAME store without a schema change.

Kept separate from the frozen ``ControlStore`` port (the ``DistinctnessLedger`` / ``RoutingAudit``
precedent) so the existing Control-DB persistence interface is unchanged. The port exposes ONLY the
minimum write operation: no read, query, export, administration, retention, or purge method belongs
here (V1b operator retrieval is a separately governed later slice). References only (D-14; IC-001
Global Audit Representation Rule): no credential, token, payload, returned membership collection,
hostname, or topology in any field. ``source_service`` is the ingest/store-side producer constant
``api_gateway`` (never a wire field); ``recorded_at`` and the ordering identity are store-assigned at
insert time and are deliberately NOT record fields. Pure stdlib; uncomposed in production until the
Gateway Audit V1a composition seam is env-selected.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

# Exact frozen action vocabulary of the API-Gateway-edge operational-audit class (IC-010 §J
# AuditAction + the D-42 CLM success-access set; extension only by contract amendment — the two
# ``tenant_startup_*`` actions were ratified by D-42 / the IC-010 CLM section). Mirrors DDL 012's
# CHECK. The durably WIRED set is the four CLM-homed classes (the three success-access events plus
# the class-3 ``RouteDenied`` denial record); the remaining denial/anomaly actions stay homed for a
# later additive sibling.
GATEWAY_AUDIT_STORE_ACTIONS = (
    "CarrierMismatch",
    "CarrierOnControlAnomaly",
    "RouteDenied",
    "IsolationAnomaly",
    "workspace_memberships_read",
    "tenant_startup_read",
    "tenant_startup_update",
)

# The producer constant enforced by the DDL 012 source_service CHECK (never a wire field).
GATEWAY_AUDIT_SOURCE_SERVICE = "api_gateway"


class GatewayAuditConflictError(Exception):
    """A replayed ``audit_id`` arrived with a DIFFERENT payload (idempotency conflict).

    Fail closed: an exact replay is an idempotent no-op, but same-ID/different-payload drift must
    never be silently accepted or silently deduplicated. A store/port-layer Python exception only —
    it carries NO row content, NO SQL, NO driver text, and NO topology (bounded, non-leaking);
    callers map it to their own bounded response (the ingest edge answers CONFLICT).
    """


class GatewayAuditInvalidError(Exception):
    """A Gateway operational-audit record failed Control-Plane-local validation (bounded, non-leaking).

    Raised before any durable write is attempted. Like ``GatewayAuditConflictError``, it is a
    store/port-layer exception distinct from every service error type and carries no payload, SQL,
    driver text, or topology.
    """


@dataclass(frozen=True, kw_only=True)
class GatewayAuditRecord:
    """Immutable, references-only durable Gateway operational-audit write model.

    Field-for-field the DDL 012 column contract MINUS the two store-assigned columns (``id`` — the
    ordering authority — and ``recorded_at``, DB-assigned via DEFAULT now()); the caller never
    supplies either. ``occurred_at`` is the gateway clock and is informational only — timestamps
    never define total ordering. ``source_service`` is the store-side producer constant
    (``api_gateway``), set by the ingest edge and never read from the wire.
    """

    audit_id: str  # gateway-minted uuid4().hex; the idempotency key (unique in the store)
    event_version: int  # additive-only evolution; positive
    occurred_at: str  # UTC ISO-8601, gateway clock; informational only
    correlation_id: str
    action: str  # GATEWAY_AUDIT_STORE_ACTIONS member
    outcome: str  # success / rejected / observed / denied:<code>
    source_service: str  # "api_gateway" (producer constant; DDL CHECK)
    actor_ref: Optional[str] = None  # authenticated subject reference; None on some denial classes
    subject_ref: Optional[str] = None  # self-scoped success subject reference (== actor_ref)
    tenant_ref: Optional[str] = None  # authenticated active tenant reference; None for the CONTROL edge
    carrier_ref: Optional[str] = None  # opaque, length-bounded carrier reference (anomaly attribution only)
    # D-42 CLM: the tenant-resident record reference the tenant Startup success events
    # address — a reference only, never field content.
    record_ref: Optional[str] = None


class GatewayAuditAppendResult(Enum):
    """Result of one idempotent append: both members are success."""

    INSERTED = "INSERTED"
    DUPLICATE_MATCH = "DUPLICATE_MATCH"


class GatewayAuditStorePort(ABC):
    """Control-Plane-owned durable Gateway operational-audit store boundary (append-only write).

    Exactly one operation, by design: ``append_gateway_audit``. No read, query, export,
    administration, retention, or purge method may be added here (V1b operator retrieval is a
    separately governed later slice). Adapters must assign ``recorded_at`` store-side, enforce
    ``audit_id`` uniqueness, treat an exact replay as ``DUPLICATE_MATCH``, and raise
    ``GatewayAuditConflictError`` on same-ID/different-payload drift. No queue, outbox, thread,
    worker, or background loop.
    """

    @abstractmethod
    def append_gateway_audit(self, record: GatewayAuditRecord) -> GatewayAuditAppendResult: ...
