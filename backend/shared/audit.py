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


@dataclass(frozen=True)
class ImportOperationalAuditEvent(OperationalAuditEvent):
    """Import operational-audit event (IC-003) — the base ``OperationalAuditEvent`` plus the import
    ``source_ref`` (IC-003:131 completeness: each import audit record carries a source reference).

    A distinct subclass so the SHARED base field set stays closed: ``database_router.RoutingAuditEvent``
    subclasses ``OperationalAuditEvent`` and its exact field set is pinned by
    ``tests/database_router/test_dbr_ar_2a_event_contract.py``; adding ``source_ref`` to the base would
    propagate to the routing event by dataclass inheritance and break that pin (W1a NBO — a forced-lockstep
    the accepted "no guard pins this field set" sweep missed). References only — no payload/secret/PII.
    """

    source_ref: Optional[str] = None


class OperationalAudit(ABC):
    @abstractmethod
    def initiate(self, event: OperationalAuditEvent) -> None: ...
