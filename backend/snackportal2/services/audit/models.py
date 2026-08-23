"""Audit Service wire models (IC-013 §10; IC-001 Global Audit Representation Rule).

**Every audit record is references only.** Prohibited in any event: names, emails, PII,
business payloads, field content, raw rows, tenant business data, tenant database identity,
database name, DSN, secret, credential, connection string, token, provider body, router
internals, stack trace.

**Server-derived fields are not accepted from the client.** The event id, the timestamp and
the emitting service are set here, not submitted. An emitter that could name itself could
name someone else (3-day plan §10).
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class AuditAction(str, Enum):
    """The ingress-edge audit vocabulary (IC-013 §10).

    The four denial/anomaly classes are exactly the historic set — none added, removed or
    renamed. The success-access classes are separate subclasses: a success is never a
    denial, an anomaly, or a routing action. The nine ``share_*`` actions are
    **authored-but-inert** until IC-007 is Final; they exist so the vocabulary is complete
    and their disuse is testable.
    """

    CARRIER_MISMATCH = "CarrierMismatch"
    CARRIER_ON_CONTROL_ANOMALY = "CarrierOnControlAnomaly"
    ROUTE_DENIED = "RouteDenied"
    ISOLATION_ANOMALY = "IsolationAnomaly"

    WORKSPACE_MEMBERSHIPS_READ = "workspace_memberships_read"
    TENANT_STARTUP_READ = "tenant_startup_read"
    TENANT_STARTUP_UPDATE = "tenant_startup_update"

    SHARE_PROPOSED = "share_proposed"
    SHARE_APPROVED = "share_approved"
    SHARE_GRANTED = "share_granted"
    SHARE_READ = "share_read"
    SHARE_REVOKED = "share_revoked"
    SHARE_EXPIRED = "share_expired"
    SHARE_SUSPENDED = "share_suspended"
    SHARE_DENIED = "share_denied"
    FORWARD_ATTEMPT_DENIED = "forward_attempt_denied"


#: The four denial/anomaly classes, unchanged from IC-010 §J.
DENIAL_ANOMALY_ACTIONS = frozenset(
    {
        AuditAction.CARRIER_MISMATCH,
        AuditAction.CARRIER_ON_CONTROL_ANOMALY,
        AuditAction.ROUTE_DENIED,
        AuditAction.ISOLATION_ANOMALY,
    }
)

#: Authored-but-inert until IC-007 is Final (IC-013 §18).
SHARING_ACTIONS = frozenset(action for action in AuditAction if action.value.startswith(("share_", "forward_")))


class AuditOutcome(str, Enum):
    """What happened. Never why."""

    ALLOWED = "allowed"
    DENIED = "denied"
    ANOMALY = "anomaly"


class AuditEventSubmission(BaseModel):
    """An ingress-edge event as its emitter submits it.

    Note what is absent: no event id, no timestamp, and no emitting service. Those are
    derived by this service from the authenticated credential and its own clock, so an
    emitter cannot backdate an event, collide an id, or attribute its action to another
    service.
    """

    action: AuditAction = Field(description="The ingress-edge audit class. The vocabulary is closed.")
    outcome: AuditOutcome = Field(description="Whether the audited operation was allowed, denied, or anomalous.")
    correlation_id: str = Field(min_length=1, max_length=128, description="Correlation id of the audited request.")
    actor_ref: str = Field(min_length=1, max_length=256, description="Opaque reference to the acting principal. Never a name or email.")
    subject_ref: Optional[str] = Field(
        default=None, max_length=256, description="Opaque reference to the principal the action concerned, if different."
    )
    tenant_ref: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Tenant reference. An audit record lawfully carries one; it is not a directory record.",
    )
    record_ref: Optional[str] = Field(
        default=None, max_length=256, description="Opaque reference to the record addressed, where the action names one."
    )
    carrier_ref: Optional[str] = Field(
        default=None,
        max_length=128,
        description="The carrier-asserted tenant value, for anomaly attribution only. Never parsed, resolved, or trusted.",
    )


class AuditEvent(BaseModel):
    """A stored ingress-edge audit record."""

    event_id: str = Field(description="Server-generated event identifier. Never supplied by the emitter.")
    occurred_at: str = Field(description="Server-generated ISO-8601 UTC timestamp. Never supplied by the emitter.")
    source_service: str = Field(description="Server-derived emitting service, taken from the authenticated credential.")
    action: AuditAction = Field(description="The ingress-edge audit class.")
    outcome: AuditOutcome = Field(description="Whether the audited operation was allowed, denied, or anomalous.")
    correlation_id: str = Field(description="Correlation id of the audited request.")
    actor_ref: str = Field(description="Opaque reference to the acting principal.")
    subject_ref: Optional[str] = Field(default=None, description="Opaque reference to the principal the action concerned.")
    tenant_ref: Optional[str] = Field(default=None, description="Tenant reference this event is scoped to.")
    record_ref: Optional[str] = Field(default=None, description="Opaque reference to the record addressed.")
    carrier_ref: Optional[str] = Field(default=None, description="Carrier-asserted tenant value, for anomaly attribution only.")


class AuditWriteAck(BaseModel):
    """Acknowledgement of an accepted audit write."""

    event_id: str = Field(description="The server-generated identifier of the recorded event.")
    recorded: bool = Field(description="True when the event was durably accepted by the configured sink.")


class AuditReadResponse(BaseModel):
    """Audit events visible to the caller under its own read scope."""

    events: List[AuditEvent] = Field(description="Matching events, newest last, within the caller's read scope.")
    scope: str = Field(description="The read scope applied. Callers see only what their scope permits.")


__all__ = [
    "DENIAL_ANOMALY_ACTIONS",
    "SHARING_ACTIONS",
    "AuditAction",
    "AuditEvent",
    "AuditEventSubmission",
    "AuditOutcome",
    "AuditReadResponse",
    "AuditWriteAck",
]
