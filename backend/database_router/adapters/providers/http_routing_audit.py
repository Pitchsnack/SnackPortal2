"""Router-side durable routing-audit transport client (stdlib urllib) — DBR-AR-2B.

Structurally implements the router-local ``RoutingAuditPort`` (``initiate(event) ->
None``) over the Control Plane's internal routing-audit ingest edge,
``POST /internal/routing-audit/events``, with NO in-process import of ``control_plane``
(DAG rule) and no vendor dependency. References only: the wire body is exactly the
seventeen approved event keys (the inherited ``target_ref`` travels under its durable
name ``tenant_ref``); ``id`` / ``store_id`` / ``recorded_at`` / ``trace_ref`` are never
sent, no event payload is ever logged, and no credential, token, connection descriptor,
hostname, topology, or exception text enters any error raised here.

Fail closed and bounded (DBR-AR-2B MC10): both ``INSERTED`` and ``DUPLICATE_MATCH``
answers are success (idempotent replay); every other outcome — conflict, invalid,
unavailability, refused/timed-out connections, or ANY response that is not the exact
two-key ``{"version": 1, "result": ...}`` envelope — raises `RoutingAuditTransportError`
with a bounded ``kind`` and a fixed non-leaking message, chained ``from None``. There is
deliberately NO retry loop, NO fallback to the in-memory sink, NO environment selector,
and NO composition into ``DatabaseRouter`` here: DBR-AR-2C owns composition,
audit-before-hand-back ordering, the failure postures, and the single bounded retry.
Uncomposed in DBR-AR-2B — nothing constructs this client in production.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Dict, Optional

from database_router.models import RoutingAuditEvent

_INGEST_PATH = "/internal/routing-audit/events"
_ENVELOPE_VERSION = 1
_SUCCESS_RESULTS = frozenset({"INSERTED", "DUPLICATE_MATCH"})
_RESPONSE_KEYS = frozenset({"version", "result"})

# Bounded error-kind vocabulary (MC10) — DBR-AR-2C classifies these into the §11 postures.
TRANSPORT_ERROR_KINDS = ("invalid", "conflict", "unavailable")

_STATUS_TO_KIND = {400: "invalid", 409: "conflict", 503: "unavailable"}


class RoutingAuditTransportError(Exception):
    """Bounded router-local transport failure (fixed non-leaking message; no chaining).

    ``kind`` is exactly one of ``invalid`` (protocol violation / rejected envelope),
    ``conflict`` (same-ID/different-payload replay), or ``unavailable`` (ingest edge
    unreachable, refused, timed out, or answering UNAVAILABLE). Carries nothing else.
    """

    def __init__(self, kind: str) -> None:
        super().__init__(f"routing-audit transport failure ({kind})")
        self.kind = kind


def _wire_event(event: RoutingAuditEvent) -> Dict[str, object]:
    # Exactly the seventeen approved wire keys (MC9); target_ref -> tenant_ref.
    return {
        "event_id": event.event_id,
        "event_version": event.event_version,
        "occurred_at": event.occurred_at,
        "correlation_id": event.correlation_id,
        "actor_ref": event.actor_ref,
        "action": event.action,
        "outcome": event.outcome,
        "source_service": event.source_service,
        "source_version": event.source_version,
        "request_ref": event.request_ref,
        "tenant_ref": event.target_ref,
        "resolved_tenant_ref": event.resolved_tenant_ref,
        "public_code": event.public_code,
        "error_class": event.error_class,
        "association_store_ref": event.association_store_ref,
        "association_version": event.association_version,
        "lane": event.lane,
    }


class HttpRoutingAudit:
    """HTTP client for the internal routing-audit ingest edge (satisfies ``RoutingAuditPort``)."""

    def __init__(self, base_url: str, timeout: float = 2.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def initiate(self, event: RoutingAuditEvent) -> None:
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
            raise RoutingAuditTransportError(_STATUS_TO_KIND.get(exc.code, "invalid")) from None
        except Exception:
            # Refused / unreachable / timed out: indistinguishable transport unavailability.
            raise RoutingAuditTransportError("unavailable") from None
        if status != 200 or raw is None:
            raise RoutingAuditTransportError("invalid") from None
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            raise RoutingAuditTransportError("invalid") from None
        if not isinstance(body, dict) or set(body.keys()) != set(_RESPONSE_KEYS):
            raise RoutingAuditTransportError("invalid") from None
        version = body["version"]
        if isinstance(version, bool) or version != _ENVELOPE_VERSION:
            raise RoutingAuditTransportError("invalid") from None
        if body["result"] not in _SUCCESS_RESULTS:
            raise RoutingAuditTransportError("invalid") from None
        return None  # INSERTED and DUPLICATE_MATCH are both success (idempotent replay)
