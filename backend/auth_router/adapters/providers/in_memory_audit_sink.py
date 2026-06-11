"""In-memory operational-audit sink (stdlib) — default auth-audit sink for dev/test.

Reuses the shared OperationalAudit port (auth audit is operational audit, never
lineage). Records carry references only — no JWT contents, secrets, or credentials.
"""

from __future__ import annotations

from typing import List

from shared.audit import OperationalAudit, OperationalAuditEvent


class InMemoryAuditSink(OperationalAudit):
    def __init__(self) -> None:
        self._events: List[OperationalAuditEvent] = []

    def initiate(self, event: OperationalAuditEvent) -> None:
        self._events.append(event)

    def events(self) -> List[OperationalAuditEvent]:
        return list(self._events)
