"""Lineage emit — append-only write path (IC-004; D-22/D-23/D-25; D-14).

Implements the shared `LineageEmitPort`: append a minimal lineage record (D-22 core) plus a
per-tenant **cryptographic hash-chain** integrity marker (D-23), executed on the caller's
`RoutedTenantSession` so it commits/rolls back atomically with the imported data (IC-004
atomic provenance). The marker is produced **only** via `canonical.marker_for` (single
source of truth — PRD-P6-R2 C). Hash-chaining lives here (the lineage owner), never in
import (E5).

Build Phase 6 additions (additive; Phase-5 callers unaffected):
- `segment_id` + `marker_version` columns (D-24/D-25 segmentation-ready; C versioning).
- Optional chain-head serialization: if the session exposes `lock_chain()` (a router
  capability), it is taken before the head read so concurrent appends serialize; the
  `UNIQUE(seq)` DB constraint is the fail-closed backstop (PRD-P6-R2 B / P6-OBS-2).
- Optional `OperationalAudit` sink: emits `LineageWritten` (references only; ≠ lineage).
"""

from __future__ import annotations

import uuid
from typing import Optional

from shared.audit import OperationalAudit, OperationalAuditEvent
from shared.lineage import LineageEmitPort, LineageIntent
from shared.secrets import SecretRef, SecretStore
from shared.session import RoutedTenantSession

from . import canonical
from .models import LINEAGE_TABLE

FIRST_SEGMENT = 1


class LineageEmit(LineageEmitPort):
    def __init__(
        self,
        secret_store: SecretStore,
        *,
        key_prefix: str = "lineage",
        audit: Optional[OperationalAudit] = None,
    ) -> None:
        self._secrets = secret_store
        self._key_prefix = key_prefix
        self._audit = audit

    def emit(self, session: RoutedTenantSession, intent: LineageIntent) -> str:
        # Serialize the chain head if the routed session supports it (provider capability);
        # correctness does not depend on it — UNIQUE(seq) fails a fork closed (D-23/R-B).
        lock = getattr(session, "lock_chain", None)
        if callable(lock):
            lock()

        # Per-tenant chain head (tenant-resident; the chain never crosses tenants — D-25).
        prev = session.latest(LINEAGE_TABLE, {}, order_by="seq")
        seq = (int(prev["seq"]) + 1) if prev else 1
        prev_marker = prev["integrity_marker"] if prev else ""
        segment_id = int(prev["segment_id"]) if prev and prev.get("segment_id") is not None else FIRST_SEGMENT

        lineage_id = uuid.uuid4().hex
        row = {
            "lineage_id": lineage_id,
            "seq": seq,
            "segment_id": segment_id,
            "event_type": intent.event_type,
            "occurred_at": intent.occurred_at,
            "actor_ref": intent.actor_ref,
            "source_ref": intent.source_ref,
            "target_ref": intent.target_ref,
            "operation": intent.operation,
            "schema_version": intent.schema_version,
            "derivation_ref": intent.derivation_ref,
            "parent_lineage_ref": intent.parent_lineage_ref,
            "correlation_id": intent.correlation_id,
            "marker_version": canonical.CURRENT_MARKER_VERSION,
            "prev_marker": prev_marker,
        }
        key = self._chain_key(session.tenant_id)
        row["integrity_marker"] = canonical.marker_for(key, row, prev_marker, marker_version=canonical.CURRENT_MARKER_VERSION)

        session.append(LINEAGE_TABLE, row)
        self._audit_written(session.tenant_id, intent, lineage_id)
        return lineage_id

    # -- per-tenant keyed-hash key by reference (D-14; never stored in lineage) ----
    def _chain_key(self, tenant_id: str) -> str:
        store_ref = f"{self._key_prefix}/{tenant_id}/chainkey"
        version: Optional[str] = self._secrets.current_version(store_ref)
        return self._secrets.resolve(SecretRef(store_ref=store_ref, version=version)).material

    def _audit_written(self, tenant_id: str, intent: LineageIntent, lineage_id: str) -> None:
        if self._audit is None:
            return
        # Operational audit (IC-002) — references only; DISTINCT from the lineage record.
        self._audit.initiate(
            OperationalAuditEvent(
                actor_ref=intent.actor_ref,
                action="LineageWritten",
                correlation_id=intent.correlation_id or "",
                outcome="success",
                target_ref=intent.target_ref,
            )
        )
