"""Control-Plane-local Import operational-audit write model and store port (W1a — durable Import Audit).

The durable half of the W1a Import Operational Audit architecture (Control-Plane-owned durable Import
operational-audit store behind a service boundary — the Gateway Audit V1a / DBR-AR-2 Option B precedent
re-homed to the Import boundary): the Import Service emits its references-only import events over the
internal loopback ingest edge, the Control Plane translates the wire payload into the local
``ImportAuditRecord`` below, and an ``ImportAuditStorePort`` adapter performs the single durable Control-DB
INSERT into ``control_import_audit`` (DDL 014, created-not-applied). This module NEVER imports
``import_service`` (import-linter independence contract): the record is defined from the contract/DDL field
list.

The audit class home is IC-003 "Import Audit" — already a first-class member of the closed audit taxonomy
(``test_audit_class_homes.py`` pins ``"Import Audit": "IC-003"``); durabilizing an already-homed class needs
no taxonomy edit and no contract amendment (the exact Gateway Audit V1a precedent). The store is shaped for
the WHOLE Import-operational-audit class — the five actions the Import Service emits — so persistence covers
every emitted import event, not a single action.

Kept separate from the frozen ``ControlStore`` port (the ``DistinctnessLedger`` / ``RoutingAudit`` /
``GatewayAudit`` precedent) so the existing Control-DB persistence interface is unchanged. The port exposes
ONLY the minimum write operation: no read, query, export, administration, retention, or purge method belongs
here (operator retrieval is a separately governed later slice). References only (D-14; IC-001 Global Audit
Representation Rule; IC-003:131): actor/tenant/source references, action, outcome, correlation id, and event
metadata only — no credential, token, payload, source record content, hostname, or topology in any field.
``source_service`` is the ingest/store-side producer constant ``import_service`` (never a wire field);
``recorded_at`` and the ordering identity are store-assigned at insert time and are deliberately NOT record
fields. Pure stdlib; uncomposed in production until the W1a Import-audit composition seam is env-selected.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

# Exact frozen action vocabulary of the Import-operational-audit class (IC-003; the five actions the Import
# Service emits through ``ImportService._emit_audit``). Mirrors DDL 014's CHECK. ``LineageWritten`` is
# deliberately EXCLUDED (the durable provenance evidence is the hash-chained lineage row itself, IC-004; a
# lineage emit fires inside the still-open batch transaction and must never trigger a durable network emit).
IMPORT_AUDIT_STORE_ACTIONS = (
    "ImportRequested",
    "ImportStarted",
    "ImportResumed",
    "ImportCompleted",
    "ImportFailed",
)

# The producer constant enforced by the DDL 014 source_service CHECK (never a wire field).
IMPORT_AUDIT_SOURCE_SERVICE = "import_service"


class ImportAuditConflictError(Exception):
    """A replayed ``audit_id`` arrived with a DIFFERENT payload (idempotency conflict).

    Fail closed: an exact replay is an idempotent no-op, but same-ID/different-payload drift must never be
    silently accepted or silently deduplicated. A store/port-layer Python exception only — it carries NO row
    content, NO SQL, NO driver text, and NO topology (bounded, non-leaking); callers map it to their own
    bounded response (the ingest edge answers CONFLICT).
    """


class ImportAuditInvalidError(Exception):
    """An Import operational-audit record failed Control-Plane-local validation (bounded, non-leaking).

    Raised before any durable write is attempted. Like ``ImportAuditConflictError``, it is a store/port-layer
    exception distinct from every service error type and carries no payload, SQL, driver text, or topology.
    """


@dataclass(frozen=True, kw_only=True)
class ImportAuditRecord:
    """Immutable, references-only durable Import operational-audit write model.

    Field-for-field the DDL 014 column contract MINUS the two store-assigned columns (``id`` — the ordering
    authority — and ``recorded_at``, DB-assigned via DEFAULT now()); the caller never supplies either.
    ``occurred_at`` is the emitter clock and is informational only — timestamps never define total ordering.
    ``source_service`` is the store-side producer constant (``import_service``), set by the ingest edge and
    never read from the wire. Carries the full IC-003:131 set exactly: actor (``actor_ref``), tenant id
    (``target_ref``), action, source reference (``source_ref``), outcome, timestamp, correlation id.
    """

    audit_id: str  # emitter-minted uuid4().hex; the idempotency key (unique in the store)
    event_version: int  # additive-only evolution; positive
    occurred_at: str  # UTC ISO-8601, emitter clock; informational only
    correlation_id: str
    action: str  # IMPORT_AUDIT_STORE_ACTIONS member
    outcome: str  # success / replayed / error:<code> (references only)
    source_service: str  # "import_service" (producer constant; DDL CHECK)
    actor_ref: Optional[str] = None  # authenticated subject reference; never a credential
    target_ref: Optional[str] = None  # the active tenant reference (IC-003:131 tenant id)
    source_ref: Optional[str] = None  # the import source reference (IC-003:131)


class ImportAuditAppendResult(Enum):
    """Result of one idempotent append: both members are success."""

    INSERTED = "INSERTED"
    DUPLICATE_MATCH = "DUPLICATE_MATCH"


class ImportAuditStorePort(ABC):
    """Control-Plane-owned durable Import operational-audit store boundary (append-only write).

    Exactly one operation, by design: ``append_import_audit``. No read, query, export, administration,
    retention, or purge method may be added here (operator retrieval is a separately governed later slice).
    Adapters must assign ``recorded_at`` store-side, enforce ``audit_id`` uniqueness, treat an exact replay as
    ``DUPLICATE_MATCH``, and raise ``ImportAuditConflictError`` on same-ID/different-payload drift. No queue,
    outbox, thread, worker, or background loop.
    """

    @abstractmethod
    def append_import_audit(self, record: ImportAuditRecord) -> ImportAuditAppendResult: ...
