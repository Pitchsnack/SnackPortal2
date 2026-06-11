"""Operational / control-plane audit (IC-002) — DISTINCT from lineage (IC-004).

Append-only, references only. No lineage, no hash-chaining, no tenant-DB audit, no
secrets/credentials. Records tenant registration, lifecycle changes, database
association changes, and provisioning events. Stored in control-plane scope only.
"""

from __future__ import annotations

from typing import List, Optional

from ._util import now_iso
from .ports import ControlStore
from .records import ControlAuditRecord


class ControlPlaneAudit:
    def __init__(self, store: ControlStore) -> None:
        self._store = store

    def record(
        self,
        *,
        actor: str,
        tenant_id: Optional[str],
        action: str,
        from_state: Optional[str],
        to_state: Optional[str],
        correlation_id: str,
    ) -> ControlAuditRecord:
        rec = ControlAuditRecord(
            actor=actor,
            tenant_id=tenant_id,
            action=action,
            from_state=from_state,
            to_state=to_state,
            timestamp=now_iso(),
            correlation_id=correlation_id,
        )
        self._store.append_audit(rec)
        return rec

    def events(self) -> List[ControlAuditRecord]:
        return self._store.list_audit()
