"""In-memory operational-audit sink (stdlib) — default import-audit sink for dev/test.

Import operational audit (IC-003) is DISTINCT from data-provenance lineage (IC-004).
Records carry references only — no payloads, PII, secrets, or source credentials.
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
