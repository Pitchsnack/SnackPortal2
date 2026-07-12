"""Control-Plane-local routing-audit write model and store port (DBR-AR-2B).

The durable half of the DBR-AR-2 Option B architecture (Control-Plane-owned durable
routing-audit store behind a service boundary — `docs/runtime/
dbr_ar_2_durable_routing_audit_contract.md` §4): the Database Router emits router-edge
routing-decision events over the internal ingest edge, the Control Plane translates the
references-only wire payload into the local `RoutingAuditRecord` below, and a
`RoutingAuditStorePort` adapter performs the single durable Control-DB INSERT into
`control_routing_audit` (DDL 010, created-not-applied). This module NEVER imports
`database_router` (import-linter independence contract): the record is defined from the
contract/DDL field list, with the event's inherited ``target_ref`` carried under its
durable name ``tenant_ref`` (IC-002 (3a): "tenant_ref (as-built target_ref)").

Kept separate from the frozen `ControlStore` port (the `DistinctnessLedger` precedent) so
the existing Control-DB persistence interface is unchanged. The port exposes ONLY the
minimum write operation: no read, query, export, administration, retention, or purge
method belongs here. References only (D-14; IC-001 Global Audit Representation Rule):
no credential, token, payload, tenant result data, hostname, or topology in any field —
``association_store_ref`` is the D-14 reference, never a resolved value. ``recorded_at``
and the ordering identity are store-assigned at insert time and are deliberately NOT
record fields; ``trace_ref`` is a reserved contract §8 field (always ``None`` in
DBR-AR-2B — it is not a wire key). Pure stdlib; uncomposed in production (DBR-AR-2C owns
composition and failure posture).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

# Exact frozen action vocabulary of the router-edge routing-decision subclass
# (IC-002 (3a); extension only by contract amendment). Mirrors DDL 010's CHECK.
ROUTING_AUDIT_STORE_ACTIONS = ("Route", "RouteControl", "RouteDenied", "IsolationAnomaly")


class RoutingAuditConflictError(Exception):
    """A replayed ``event_id`` arrived with a DIFFERENT payload (idempotency conflict).

    Fail closed (contract §7.2 / §12): an exact replay is an idempotent no-op, but
    same-ID/different-payload drift must never be silently accepted or silently
    deduplicated. A store/port-layer Python exception only — it carries NO row content,
    NO SQL, NO driver text, and NO topology (bounded, non-leaking); callers map it to
    their own bounded response (the ingest edge answers CONFLICT).
    """


class RoutingAuditInvalidError(Exception):
    """A routing-audit record failed Control-Plane-local validation (bounded, non-leaking).

    Raised before any durable write is attempted. Like `RoutingAuditConflictError`, it is
    a store/port-layer exception distinct from every service error type and carries no
    payload, SQL, driver text, or topology.
    """


@dataclass(frozen=True, kw_only=True)
class RoutingAuditRecord:
    """Immutable, references-only durable routing-audit write model (contract §8).

    Field-for-field the DDL 010 column contract MINUS the two store-assigned columns
    (``id`` — the ordering authority — and ``recorded_at``, DB-assigned via DEFAULT
    now()); the caller never supplies either. ``occurred_at`` is the router clock and is
    informational only — timestamps never define total ordering (contract §12).
    """

    event_id: str  # router-minted UUID; the idempotency key (unique in the store)
    event_version: int  # additive-only evolution; positive
    occurred_at: str  # UTC ISO-8601, router clock; informational only
    correlation_id: str
    actor_ref: str
    action: str  # ROUTING_AUDIT_STORE_ACTIONS member
    outcome: str  # success / denied:<public_code> / anomaly:<code>
    source_service: str  # "database_router" (router-edge producer; DDL CHECK)
    source_version: str
    request_ref: Optional[str] = None
    trace_ref: Optional[str] = None  # reserved (contract §8); always None in DBR-AR-2B
    tenant_ref: Optional[str] = None  # durable name of the event's inherited target_ref
    resolved_tenant_ref: Optional[str] = None
    public_code: Optional[str] = None  # canonical router-edge denial code; None on success
    error_class: Optional[str] = None  # bounded internal vocabulary (contract §8)
    association_store_ref: Optional[str] = None  # D-14 reference — never a resolved value
    association_version: Optional[str] = None
    lane: Optional[str] = None  # "interactive" / "bulk" (D-13)


class RoutingAuditAppendResult(Enum):
    """Result of one idempotent append (contract §7.2): both members are success."""

    INSERTED = "INSERTED"
    DUPLICATE_MATCH = "DUPLICATE_MATCH"


class RoutingAuditStorePort(ABC):
    """Control-Plane-owned durable routing-audit store boundary (append-only write).

    Exactly one operation, by design: `append_routing_audit`. No read, query, export,
    administration, retention, or purge method may be added here (contract §13/§14; those
    surfaces are separately governed later slices). Adapters must assign ``recorded_at``
    store-side, enforce ``event_id`` uniqueness, treat an exact replay as
    `DUPLICATE_MATCH`, and raise `RoutingAuditConflictError` on same-ID/different-payload
    drift. No queue, outbox, thread, worker, or background loop.
    """

    @abstractmethod
    def append_routing_audit(self, record: RoutingAuditRecord) -> RoutingAuditAppendResult: ...
