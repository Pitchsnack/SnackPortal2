"""Operational audit port (interface only) — DISTINCT from lineage (IC-004).

Operational / control-plane audit (IC-002, IC-003). It MUST NOT be conflated with
data-provenance lineage and MUST NOT be written into tenant databases. Records are
reference-only and non-sensitive. No audit sink is implemented in Build Phase 1.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class OperationalAuditEvent:
    actor_ref: str
    action: str
    correlation_id: str
    outcome: str
    target_ref: Optional[str] = None
    # No payloads, secrets, or PII — references and non-sensitive fields only.


class OperationalAudit(ABC):
    @abstractmethod
    def initiate(self, event: OperationalAuditEvent) -> None: ...
