"""Gateway-side durable operational-audit transport client (stdlib urllib) — Gateway Audit V1a.

Implements the shared, sink-less ``AuditEmitterPort`` (``emit(event) -> None``) over the Control
Plane's internal Gateway-audit ingest edge, ``POST /internal/gateway-audit/events``, with NO
in-process import of ``control_plane`` (DAG rule) and NO database driver / vendor dependency (the
gateway accesses no database and holds no Control-DB credential; IC-010 §X). References only: the
wire body is exactly the eleven approved references-only Gateway-edge keys (D-42 CLM adds
``record_ref``; ``source_service`` is the store-side producer constant, never sent; ``id`` /
``recorded_at`` are DB-assigned). No event
payload is ever logged, and no credential, token, connection descriptor, hostname, topology, or
exception text enters any error raised here.

Fail closed and bounded: both ``INSERTED`` and ``DUPLICATE_MATCH`` answers are success (idempotent
replay); every other outcome — conflict, invalid, unavailability, refused/timed-out connections, or
ANY response that is not the exact two-key ``{"version": 1, "result": ...}`` envelope — raises
``DurableAuditTransportError`` with a bounded ``kind`` and a fixed non-leaking message, chained
``from None``. There is deliberately NO retry loop, NO fallback to the in-memory emitter, and NO
environment selector here: the Gateway Audit V1a composition (``api_gateway/main.py``
``BoundedGatewayAuditPolicy``) owns the single bounded retry and the audit-before-hand-back
fail-closed posture, and ``build_audit_emitter_from_env`` owns selection. This transport client is a
plain ``AuditEmitterPort`` sibling of ``InMemoryAuditEmitter``.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Dict, Optional

from ...models import GatewayAuditEvent
from ...ports import AuditEmitterPort

_INGEST_PATH = "/internal/gateway-audit/events"
_ENVELOPE_VERSION = 1
_SUCCESS_RESULTS = frozenset({"INSERTED", "DUPLICATE_MATCH"})
_RESPONSE_KEYS = frozenset({"version", "result"})

# Bounded error-kind vocabulary — the composition policy classifies these into its retry/fail-closed
# postures (``unavailable`` is the only retryable kind).
TRANSPORT_ERROR_KINDS = ("invalid", "conflict", "unavailable")

_STATUS_TO_KIND = {400: "invalid", 409: "conflict", 503: "unavailable"}


class DurableAuditTransportError(Exception):
    """Bounded gateway-local transport failure (fixed non-leaking message; no chaining).

    ``kind`` is exactly one of ``invalid`` (protocol violation / rejected envelope), ``conflict``
    (same-ID/different-payload replay), or ``unavailable`` (ingest edge unreachable, refused, timed
    out, or answering UNAVAILABLE). Carries nothing else.
    """

    def __init__(self, kind: str) -> None:
        super().__init__(f"gateway-audit transport failure ({kind})")
        self.kind = kind


def _wire_event(event: GatewayAuditEvent) -> Dict[str, object]:
    # Exactly the eleven approved references-only Gateway-edge wire keys (D-42 CLM adds
    # record_ref). ``action`` is the enum's string value; ``source_service`` / ``id`` /
    # ``recorded_at`` are never sent.
    return {
        "audit_id": event.audit_id,
        "event_version": event.event_version,
        "occurred_at": event.occurred_at,
        "correlation_id": event.correlation_id,
        "action": event.action.value,
        "outcome": event.outcome,
        "actor_ref": event.actor_ref,
        "subject_ref": event.subject_ref,
        "tenant_ref": event.tenant_ref,
        "carrier_ref": event.carrier_ref,
        "record_ref": event.record_ref,
    }


class DurableAuditEmitter(AuditEmitterPort):
    """HTTP client for the internal Gateway-audit ingest edge (satisfies ``AuditEmitterPort``)."""

    def __init__(self, base_url: str, timeout: float = 2.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def emit(self, event: GatewayAuditEvent) -> None:
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
            # Bounded mapping only — never the server body, never exception text.
            raise DurableAuditTransportError(_STATUS_TO_KIND.get(exc.code, "invalid")) from None
        except Exception:
            # Refused / unreachable / timed out: indistinguishable transport unavailability.
            raise DurableAuditTransportError("unavailable") from None
        if status != 200 or raw is None:
            raise DurableAuditTransportError("invalid") from None
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            raise DurableAuditTransportError("invalid") from None
        if not isinstance(body, dict) or set(body.keys()) != set(_RESPONSE_KEYS):
            raise DurableAuditTransportError("invalid") from None
        version = body["version"]
        if isinstance(version, bool) or version != _ENVELOPE_VERSION:
            raise DurableAuditTransportError("invalid") from None
        if body["result"] not in _SUCCESS_RESULTS:
            raise DurableAuditTransportError("invalid") from None
        return None  # INSERTED and DUPLICATE_MATCH are both success (idempotent replay)
