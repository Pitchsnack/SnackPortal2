"""In-memory, NON-PERSISTENT gateway audit emitter (stdlib) — AD-1 Option A default.

Implements ``AuditEmitterPort`` with NO persistence sink (no Control-DB/tenant-DB/file/
external sink). Records are references only (IC-001:94-98). The runtime operational-audit
class-home remains the pending IC-005/IC-002 audit-section extension — not homed here.
"""

from __future__ import annotations

from typing import List

from ...models import GatewayAuditEvent
from ...ports import AuditEmitterPort


class InMemoryAuditEmitter(AuditEmitterPort):
    """Holds emitted events in process memory only (dev/test). Not a persistence sink."""

    def __init__(self) -> None:
        self._events: List[GatewayAuditEvent] = []

    def emit(self, event: GatewayAuditEvent) -> None:
        self._events.append(event)

    def events(self) -> List[GatewayAuditEvent]:
        return list(self._events)
