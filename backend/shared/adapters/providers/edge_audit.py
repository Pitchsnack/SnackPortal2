"""Public-edge operational-audit sinks — the in-memory default and the durable transport.

The Gateway-free MVP keeps the audit architecture it inherited and changes exactly one thing:
the emitter. The seven action classes, the eleven references-only wire keys, the ingest edge
path, the two-key result envelope, the idempotent-replay semantics, the bounded retry policy,
and the durably-homed partition are all unchanged, so the durable home is a no-op rather than
a migration.

Three collaborators, matching the shapes the API Gateway composition used:

* ``InMemoryEdgeAudit`` — the no-sink default (AD-1 Option A). Never raises, so an edge
  composed without a durable sink behaves exactly as the pre-durable composition did;
* ``HttpEdgeAudit`` — the transport client for the Control Plane's internal ingest edge,
  ``POST /internal/gateway-audit/events``. No in-process import of ``control_plane``, no
  database driver, no credential;
* ``BoundedEdgeAuditPolicy`` — exactly ONE immediate, synchronous, idempotent retry of the
  SAME event, and only for the transient ``unavailable`` kind. ``invalid`` and ``conflict``
  are never retried. No loop, sleep, queue, outbox, thread, or background machinery. A
  terminal failure re-raises so the edge fails the request closed;
* ``DurableEdgeAuditPartition`` — routes exactly the five durably homed CLM classes to the
  durable sink and every other class to the in-memory sink, so selecting a durable sink homes
  the CLM evidence set and nothing wider.

Placement in ``shared`` is lawful and load-bearing: this module cannot import any service, so
it can hold no service-specific knowledge beyond a base URL and a wire envelope.

**Known constraint, not hidden.** The Control-DB store constant for this table is the literal
``api_gateway`` (``control_plane.gateway_audit.EDGE_AUDIT_SOURCE_SERVICE``, mirroring the
DDL 012 ``source_service`` CHECK). It is a store-side producer constant and is never a wire
field, so nothing here sends it — but adopting the Gateway-free architecture for real would
need that CHECK widened to name the route-owning edges. No DDL is applied or altered here.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Dict, List, Optional

from shared.public_edge import (
    ACTION_CARRIER_MISMATCH,
    ACTION_ROUTE_DENIED,
    ACTION_TENANT_STARTUP_READ,
    ACTION_TENANT_STARTUP_UPDATE,
    ACTION_WORKSPACE_MEMBERSHIPS_READ,
    EdgeAuditEvent,
    EdgeAuditPort,
)

__all__ = [
    "DURABLE_EDGE_AUDIT_ACTIONS",
    "BoundedEdgeAuditPolicy",
    "DurableEdgeAuditPartition",
    "EdgeAuditTransportError",
    "HttpEdgeAudit",
    "InMemoryEdgeAudit",
]

_INGEST_PATH = "/internal/gateway-audit/events"
_ENVELOPE_VERSION = 1
_SUCCESS_RESULTS = frozenset({"INSERTED", "DUPLICATE_MATCH"})
_RESPONSE_KEYS = frozenset({"version", "result"})
_STATUS_TO_KIND = {400: "invalid", 409: "conflict", 503: "unavailable"}

# Exactly the five durably homed CLM classes (D-42 + D-43): the three success-access events
# plus the two durably homed denial records. The two remaining anomaly classes keep their
# in-memory posture — durably homing them would be the wider audit expansion D-42/D-43 forbid.
DURABLE_EDGE_AUDIT_ACTIONS = frozenset(
    {
        ACTION_WORKSPACE_MEMBERSHIPS_READ,
        ACTION_TENANT_STARTUP_READ,
        ACTION_TENANT_STARTUP_UPDATE,
        ACTION_ROUTE_DENIED,
        ACTION_CARRIER_MISMATCH,
    }
)


class EdgeAuditTransportError(Exception):
    """Bounded edge-local transport failure (fixed non-leaking message; no chaining).

    ``kind`` is exactly one of ``invalid`` (protocol violation / rejected envelope),
    ``conflict`` (same-ID/different-payload replay), or ``unavailable`` (ingest edge
    unreachable, refused, timed out, or answering UNAVAILABLE). It carries nothing else — no
    server body, exception text, connection descriptor, hostname, or topology.
    """

    def __init__(self, kind: str) -> None:
        super().__init__(f"edge-audit transport failure ({kind})")
        self.kind = kind


class InMemoryEdgeAudit(EdgeAuditPort):
    """The no-sink default (AD-1 Option A): records in process memory and never raises."""

    def __init__(self) -> None:
        self.events: List[EdgeAuditEvent] = []

    def emit(self, event: EdgeAuditEvent) -> None:
        self.events.append(event)


def _wire_event(event: EdgeAuditEvent) -> Dict[str, object]:
    """Exactly the eleven approved references-only wire keys.

    ``source_service`` / ``id`` / ``recorded_at`` are store-assigned and are never sent.
    """
    return {
        "audit_id": event.audit_id,
        "event_version": event.event_version,
        "occurred_at": event.occurred_at,
        "correlation_id": event.correlation_id,
        "action": event.action,
        "outcome": event.outcome,
        "actor_ref": event.actor_ref,
        "subject_ref": event.subject_ref,
        "tenant_ref": event.tenant_ref,
        "carrier_ref": event.carrier_ref,
        "record_ref": event.record_ref,
    }


class HttpEdgeAudit(EdgeAuditPort):
    """HTTP client for the internal operational-audit ingest edge.

    Both ``INSERTED`` and ``DUPLICATE_MATCH`` are success (idempotent replay); every other
    outcome raises ``EdgeAuditTransportError`` with a bounded kind. There is deliberately no
    retry, no fallback to the in-memory sink, and no environment selector here — the
    composition root owns selection and ``BoundedEdgeAuditPolicy`` owns the single retry.
    """

    def __init__(self, base_url: str, timeout: float = 2.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def emit(self, event: EdgeAuditEvent) -> None:
        payload = json.dumps({"version": _ENVELOPE_VERSION, "event": _wire_event(event)}).encode("utf-8")
        request = urllib.request.Request(
            self._base + _INGEST_PATH,
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        raw: Optional[bytes] = None
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as resp:  # internal control-plane URL
                status = int(resp.status)
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raise EdgeAuditTransportError(_STATUS_TO_KIND.get(exc.code, "invalid")) from None
        except Exception:
            # Refused / unreachable / timed out: indistinguishable transport unavailability.
            raise EdgeAuditTransportError("unavailable") from None
        if status != 200 or raw is None:
            raise EdgeAuditTransportError("invalid") from None
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            raise EdgeAuditTransportError("invalid") from None
        if not isinstance(body, dict) or set(body.keys()) != set(_RESPONSE_KEYS):
            raise EdgeAuditTransportError("invalid") from None
        version = body["version"]
        if isinstance(version, bool) or version != _ENVELOPE_VERSION:
            raise EdgeAuditTransportError("invalid") from None
        if body["result"] not in _SUCCESS_RESULTS:
            raise EdgeAuditTransportError("invalid") from None
        return None


class BoundedEdgeAuditPolicy(EdgeAuditPort):
    """One bounded, idempotent retry for transient unavailability; otherwise terminal.

    At most two total transport calls for the same event, and only when the failure kind is
    ``unavailable``. ``invalid`` and ``conflict`` re-raise immediately — a rejected or
    conflicting record is a protocol fault, not a blip, and retrying one would be a way to
    turn a real failure into a silent success.
    """

    def __init__(self, inner: EdgeAuditPort, *, transport_error: type[Exception] = EdgeAuditTransportError) -> None:
        self._inner = inner
        self._transport_error = transport_error

    def _retryable(self, failure: Exception) -> bool:
        return isinstance(failure, self._transport_error) and getattr(failure, "kind", None) == "unavailable"

    def emit(self, event: EdgeAuditEvent) -> None:
        try:
            self._inner.emit(event)
            return
        except Exception as first:
            if not self._retryable(first):
                raise  # invalid/conflict -> terminal fail-closed, no retry
        self._inner.emit(event)  # the single bounded retry: the SAME event (re-raises on terminal)


class DurableEdgeAuditPartition(EdgeAuditPort):
    """Route the five durably homed CLM classes to ``durable``; everything else in-memory.

    Selecting a durable sink therefore homes the CLM evidence set and NOTHING wider: the
    un-homed anomaly classes keep their in-memory posture byte-for-byte. A durable failure
    re-raises unchanged and the edge collapses it fail-closed.
    """

    def __init__(self, durable: EdgeAuditPort, in_memory: EdgeAuditPort) -> None:
        self._durable = durable
        self._in_memory = in_memory

    def emit(self, event: EdgeAuditEvent) -> None:
        if event.action in DURABLE_EDGE_AUDIT_ACTIONS:
            self._durable.emit(event)
            return
        self._in_memory.emit(event)
