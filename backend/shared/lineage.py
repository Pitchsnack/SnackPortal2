"""Lineage emit port (shared) — PRD-P5-R2 D; IC-004 (D-22 core).

`import_service` composes a `LineageIntent` (references only) and calls `emit()` on the
**same** `RoutedTenantSession` as the tenant-copy write, so provenance commits/rolls back
atomically with the data. `lineage_service` implements `emit()` — append + per-tenant
cryptographic hash-chaining (D-23) — which it owns; `import_service` never hash-chains or
persists lineage (E5). No payloads, PII, or secrets appear in this port: every outward
pointer is a reference (D-22).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from shared.session import RoutedTenantSession


@dataclass(frozen=True)
class LineageIntent:
    event_type: str  # "import" (D-22)
    occurred_at: str
    actor_ref: str  # identity reference, never a token/credential
    source_ref: str  # global record reference + key — never the payload/credentials
    target_ref: str  # the affected tenant record (in the active tenant DB)
    operation: str  # "created" | "updated" | "noop"
    schema_version: str
    derivation_ref: Optional[str] = None  # import job id
    parent_lineage_ref: Optional[str] = None
    correlation_id: Optional[str] = None


class LineageEmitPort(ABC):
    @abstractmethod
    def emit(self, session: RoutedTenantSession, intent: LineageIntent) -> str:
        """Append one lineage record within the caller's transaction; return its lineage_id.

        MUST raise on failure (so the caller's transaction rolls back — atomic provenance)
        and MUST open no autonomous connection (runs only on the provided session).
        """
