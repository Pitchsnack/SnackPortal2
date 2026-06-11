"""Queue port (interface only) — dispatch only (D-19, D-13).

The queue conveys work intent by reference. It is NOT a state store: durable,
authoritative tenant job state lives in the tenant's own database (written via
database_router). Envelopes carry references and non-sensitive routing fields
only — no payloads, secrets, or PII. No queue processing exists in Build Phase 1.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class JobEnvelope:
    tenant_id: str
    job_id: str
    idempotency_key: str
    correlation_id: str
    state_ref: str  # reference to tenant-resident job state (never the state itself)


class Queue(ABC):
    @abstractmethod
    def enqueue(self, envelope: JobEnvelope) -> None: ...

    @abstractmethod
    def dequeue(self) -> Optional[JobEnvelope]: ...

    @abstractmethod
    def ack(self, job_id: str) -> None: ...
