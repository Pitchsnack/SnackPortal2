"""Import-Service durable operational-audit transport client (stdlib urllib) — W1a durable Import Audit.

Implements the shared ``OperationalAudit`` sink (``initiate(event) -> None``) over the Control Plane's
internal Import-audit ingest edge, ``POST /internal/import-audit/events``, with NO in-process import of
``control_plane`` (DAG rule) and NO database driver / vendor dependency (the Import Service accesses no
Control database and holds no Control-DB credential). References only: the wire body is exactly the nine
approved references-only Import-event keys (``source_service`` is the store-side producer constant, never
sent; ``id`` / ``recorded_at`` are DB-assigned). No event payload is ever logged, and no credential, token,
connection descriptor, hostname, topology, or exception text enters any error raised here.

Minting: each ``initiate`` mints ``audit_id = uuid4().hex``, ``event_version = 1``, and ``occurred_at`` (UTC
ISO) and performs exactly one POST via ``post``. Fail closed and bounded: both ``INSERTED`` and
``DUPLICATE_MATCH`` answers are success (idempotent replay); every other outcome — conflict, invalid,
unavailability, refused/timed-out connections, or ANY response that is not the exact two-key
``{"version": 1, "result": ...}`` envelope — raises ``ImportAuditTransportError`` with a bounded ``kind`` and
a fixed non-leaking message, chained ``from None``. There is deliberately NO retry loop here, NO fallback to
the in-memory sink, and NO environment selector: the W1a composition (``import_service/main.py``
``BoundedImportAuditPolicy``) owns the single bounded retry (reusing the SAME ``audit_id`` via ``post``) and
the audit-before-hand-back fail-closed posture, and ``build_import_audit_sink_from_env`` owns selection. This
transport client is a plain ``OperationalAudit`` sibling of ``InMemoryAuditSink``.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

from shared.audit import OperationalAudit, OperationalAuditEvent

_INGEST_PATH = "/internal/import-audit/events"
_ENVELOPE_VERSION = 1
_EVENT_VERSION = 1
_SUCCESS_RESULTS = frozenset({"INSERTED", "DUPLICATE_MATCH"})
_RESPONSE_KEYS = frozenset({"version", "result"})

# Bounded error-kind vocabulary — the composition policy classifies these into its retry/fail-closed
# postures (``unavailable`` is the only retryable kind).
TRANSPORT_ERROR_KINDS = ("invalid", "conflict", "unavailable")

_STATUS_TO_KIND = {400: "invalid", 409: "conflict", 503: "unavailable"}


class ImportAuditTransportError(Exception):
    """Bounded Import-Service-local transport failure (fixed non-leaking message; no chaining).

    ``kind`` is exactly one of ``invalid`` (protocol violation / rejected envelope), ``conflict``
    (same-ID/different-payload replay), or ``unavailable`` (ingest edge unreachable, refused, timed out, or
    answering UNAVAILABLE). Carries nothing else.
    """

    def __init__(self, kind: str) -> None:
        super().__init__(f"import-audit transport failure ({kind})")
        self.kind = kind


def _wire_event(event: OperationalAuditEvent, *, audit_id: str, event_version: int, occurred_at: str) -> Dict[str, object]:
    # Exactly the nine approved references-only Import-event wire keys. ``source_service`` / ``id`` /
    # ``recorded_at`` are never sent (store-side producer constant / DB-assigned).
    return {
        "audit_id": audit_id,
        "event_version": event_version,
        "occurred_at": occurred_at,
        "correlation_id": event.correlation_id,
        "action": event.action,
        "outcome": event.outcome,
        "actor_ref": event.actor_ref,
        "target_ref": event.target_ref,
        # source_ref lives on the ImportOperationalAuditEvent subclass (kept off the shared base so
        # RoutingAuditEvent's closed field set is unaffected); read defensively for any base event.
        "source_ref": getattr(event, "source_ref", None),
    }


class DurableImportAuditEmitter(OperationalAudit):
    """HTTP client for the internal Import-audit ingest edge (satisfies ``OperationalAudit``)."""

    def __init__(self, base_url: str, timeout: float = 2.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def initiate(self, event: OperationalAuditEvent) -> None:
        # Mint the idempotency key + metadata and perform exactly one POST (no retry here — the policy owns it).
        self.post(
            event,
            audit_id=uuid.uuid4().hex,
            event_version=_EVENT_VERSION,
            occurred_at=datetime.now(timezone.utc).isoformat(),
        )

    def post(self, event: OperationalAuditEvent, *, audit_id: str, event_version: int, occurred_at: str) -> None:
        """One durable POST for a caller-minted ``audit_id`` (the policy reuses the SAME id on its single
        retry so a retry is an idempotent DUPLICATE_MATCH, never a second row). Single attempt, no loop."""
        wire = _wire_event(event, audit_id=audit_id, event_version=event_version, occurred_at=occurred_at)
        payload = json.dumps({"version": _ENVELOPE_VERSION, "event": wire}).encode("utf-8")
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
            raise ImportAuditTransportError(_STATUS_TO_KIND.get(exc.code, "invalid")) from None
        except Exception:
            # Refused / unreachable / timed out: indistinguishable transport unavailability.
            raise ImportAuditTransportError("unavailable") from None
        if status != 200 or raw is None:
            raise ImportAuditTransportError("invalid") from None
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            raise ImportAuditTransportError("invalid") from None
        if not isinstance(body, dict) or set(body.keys()) != set(_RESPONSE_KEYS):
            raise ImportAuditTransportError("invalid") from None
        version = body["version"]
        if isinstance(version, bool) or version != _ENVELOPE_VERSION:
            raise ImportAuditTransportError("invalid") from None
        if body["result"] not in _SUCCESS_RESULTS:
            raise ImportAuditTransportError("invalid") from None
        return None  # INSERTED and DUPLICATE_MATCH are both success (idempotent replay)
