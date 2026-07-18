"""Import execution coordinator (IC-003; D-19/D-20/D-21) — the import unit of work.

Consumes a RoutedTenantSession from the injected RoutedSessionProvider (bulk lane) and a
LineageEmitPort (implemented by lineage_service). For each batch it writes the tenant copy
(idempotent upsert), emits lineage, and advances the checkpoint **in one transaction**
(atomic provenance — PRD-P5-R2 K): commit-together / rollback-together. Operation-level
idempotency replays a completed import; an incomplete import resumes from its last
checkpoint. Job state, checkpoints, and the idempotency ledger are tenant-resident (written
through the session — never the control DB or the queue). Performs NO authentication,
authorization, routing, credential resolution, lineage persistence, or hash-chaining.
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional, Tuple

from shared.audit import ImportOperationalAuditEvent, OperationalAudit
from shared.lineage import LineageEmitPort, LineageIntent
from shared.session import Lane, RoutedSessionProvider, RoutedTenantSession

from ._util import now_iso
from .models import ImportRecord, ImportRequest, ImportStatus, SourceKind
from .ports import SourceAdapter
from .validation import ValidationError, validate

JOB_TABLE = "import_job"
IDEM_TABLE = "import_idempotency"
CHECKPOINT_TABLE = "import_checkpoint"


class ImportService:
    def __init__(
        self,
        *,
        session_provider: RoutedSessionProvider,
        lineage: LineageEmitPort,
        audit: OperationalAudit,
        sources: Dict[SourceKind, SourceAdapter],
        schema_version: str = "1",
        batch_size: int = 2,
    ) -> None:
        self._provider = session_provider
        self._lineage = lineage
        self._audit = audit
        self._sources = sources
        self._schema_version = schema_version
        self._batch_size = batch_size

    # -- public API ------------------------------------------------------------
    def start_import(self, req: ImportRequest) -> ImportStatus:
        self._emit_audit(req, "ImportRequested", "success")
        session = self._provider.open_session(
            tenant_id=req.tenant_id,
            correlation_id=req.correlation_id,
            principal_ref=req.actor_ref,
            lane=Lane.BULK,
        )
        try:
            job_id, resuming, replay = self._begin_job(session, req)
            if replay is not None:
                self._emit_audit(req, "ImportCompleted", "replayed")
                return replay
            self._emit_audit(req, "ImportResumed" if resuming else "ImportStarted", "success")

            valid, rejected = self._collect(req)
            start_seq = self._resume_point(session, job_id)
            applied, noop = self._apply_batches(session, req, job_id, valid, start_seq)

            return self._finalize(session, req, job_id, applied, noop, rejected)
        except _ImportFailed as failure:
            self._emit_audit(req, "ImportFailed", "error:" + failure.code)
            return failure.status
        finally:
            session.close()

    def get_status(self, *, tenant_id: str, operation_key: str, correlation_id: str) -> Optional[ImportStatus]:
        session = self._provider.open_session(tenant_id=tenant_id, correlation_id=correlation_id, lane=Lane.BULK)
        try:
            session.begin()
            idem = session.get(IDEM_TABLE, {"operation_key": operation_key})
            session.commit()
        finally:
            session.close()
        if not idem:
            return None
        return ImportStatus(
            import_id=idem["job_id"],
            tenant_id=tenant_id,
            state=idem.get("status", "in_progress"),
            applied_count=int(idem.get("applied", 0)),
            noop_count=int(idem.get("noop", 0)),
            rejected_count=int(idem.get("rejected", 0)),
            last_error_summary="",
            correlation_id=correlation_id,
        )

    # -- internals -------------------------------------------------------------
    def _begin_job(self, session: RoutedTenantSession, req: ImportRequest) -> Tuple[str, bool, Optional[ImportStatus]]:
        """Returns (job_id, resuming, replay_status_or_None)."""
        session.begin()
        idem = session.get(IDEM_TABLE, {"operation_key": req.operation_key})
        if idem and idem.get("status") == "applied":
            session.commit()
            return (
                idem["job_id"],
                False,
                ImportStatus(
                    import_id=idem["job_id"],
                    tenant_id=req.tenant_id,
                    state="applied",
                    applied_count=int(idem.get("applied", 0)),
                    noop_count=int(idem.get("noop", 0)),
                    rejected_count=int(idem.get("rejected", 0)),
                    last_error_summary="",
                    correlation_id=req.correlation_id,
                    replayed=True,  # W1a: operation-level idempotent replay (else field-identical to a fresh success)
                ),
            )
        if idem:
            session.commit()
            return idem["job_id"], True, None  # resume an incomplete import
        job_id = uuid.uuid4().hex
        session.upsert(
            JOB_TABLE,
            {"job_id": job_id},
            {
                "job_id": job_id,
                "operation_key": req.operation_key,
                "tenant_id": req.tenant_id,
                "state": "in_progress",
                "correlation_id": req.correlation_id,
            },
        )
        session.upsert(
            IDEM_TABLE,
            {"operation_key": req.operation_key},
            {
                "operation_key": req.operation_key,
                "job_id": job_id,
                "status": "in_progress",
            },
        )
        session.commit()
        return job_id, False, None

    def _collect(self, req: ImportRequest) -> Tuple[List[ImportRecord], int]:
        adapter = self._sources.get(req.source.kind)
        if adapter is None:
            raise _ImportFailed("unsupported_source", self._failed_status(req, "unknown", 0, 0, 0))
        valid: List[ImportRecord] = []
        rejected = 0
        for raw in adapter.read(req.source):
            try:
                valid.append(validate(raw, req.natural_key_field))
            except ValidationError:
                rejected += 1  # non-sensitive: count only (D-21 partial failure; K5 safe logging)
        return valid, rejected

    def _resume_point(self, session: RoutedTenantSession, job_id: str) -> int:
        session.begin()
        cp = session.latest(CHECKPOINT_TABLE, {"job_id": job_id}, "batch_seq")
        session.commit()
        return (int(cp["batch_seq"]) + 1) if cp else 1

    def _apply_batches(
        self,
        session: RoutedTenantSession,
        req: ImportRequest,
        job_id: str,
        valid: List[ImportRecord],
        start_seq: int,
    ) -> Tuple[int, int]:
        applied = noop = 0
        batches = [valid[i : i + self._batch_size] for i in range(0, len(valid), self._batch_size)]
        for seq, batch in enumerate(batches, start=1):
            if seq < start_seq:
                continue  # already committed in a prior run (resume)
            session.begin()
            try:
                b_applied = self._apply_one_batch(session, req, job_id, seq, batch)
            except Exception:
                session.rollback()  # atomic: tenant data + lineage + checkpoint all reverted
                session.begin()  # mark the import failed (separate txn, same session)
                session.upsert(
                    IDEM_TABLE,
                    {"operation_key": req.operation_key},
                    {
                        "operation_key": req.operation_key,
                        "job_id": job_id,
                        "status": "failed",
                    },
                )
                session.commit()
                # Failure surfaces as a status DTO; the batch exception is not chained.
                raise _ImportFailed("batch", self._failed_status(req, job_id, applied, noop, 0)) from None
            session.commit()
            applied += b_applied
            noop += len(batch) - b_applied
        return applied, noop

    def _apply_one_batch(
        self,
        session: RoutedTenantSession,
        req: ImportRequest,
        job_id: str,
        seq: int,
        batch: List[ImportRecord],
    ) -> int:
        b_applied = 0
        for rec in batch:
            row = dict(rec.fields)
            row[req.natural_key_field] = rec.natural_key
            changed = session.upsert(req.target_table, {req.natural_key_field: rec.natural_key}, row)
            if changed:
                b_applied += 1
            # Attributable lineage reflecting the de-duplication outcome (D-20), in this txn.
            self._lineage.emit(
                session,
                LineageIntent(
                    event_type="import",
                    occurred_at=now_iso(),
                    actor_ref=req.actor_ref,
                    source_ref=rec.source_ref,
                    target_ref=f"{req.tenant_id}:{req.target_table}:{rec.natural_key}",
                    operation="created" if changed else "noop",
                    schema_version=self._schema_version,
                    derivation_ref=job_id,
                    correlation_id=req.correlation_id,
                ),
            )
        session.append(
            CHECKPOINT_TABLE,
            {
                "job_id": job_id,
                "batch_seq": seq,
                "last_offset": seq * self._batch_size,
                "applied_count": b_applied,
                "status": "applied",
                "updated_at": now_iso(),
            },
        )
        return b_applied

    def _finalize(
        self,
        session: RoutedTenantSession,
        req: ImportRequest,
        job_id: str,
        applied: int,
        noop: int,
        rejected: int,
    ) -> ImportStatus:
        session.begin()
        session.upsert(
            JOB_TABLE,
            {"job_id": job_id},
            {
                "job_id": job_id,
                "operation_key": req.operation_key,
                "tenant_id": req.tenant_id,
                "state": "applied",
                "correlation_id": req.correlation_id,
            },
        )
        session.upsert(
            IDEM_TABLE,
            {"operation_key": req.operation_key},
            {
                "operation_key": req.operation_key,
                "job_id": job_id,
                "status": "applied",
                "applied": applied,
                "noop": noop,
                "rejected": rejected,
            },
        )
        session.commit()
        self._emit_audit(req, "ImportCompleted", "success")
        return ImportStatus(
            import_id=job_id,
            tenant_id=req.tenant_id,
            state="applied",
            applied_count=applied,
            noop_count=noop,
            rejected_count=rejected,
            last_error_summary="",
            correlation_id=req.correlation_id,
        )

    def _failed_status(
        self,
        req: ImportRequest,
        job_id: str,
        applied: int,
        noop: int,
        rejected: int,
    ) -> ImportStatus:
        return ImportStatus(
            import_id=job_id,
            tenant_id=req.tenant_id,
            state="failed",
            applied_count=applied,
            noop_count=noop,
            rejected_count=rejected,
            last_error_summary="batch_failed",
            correlation_id=req.correlation_id,
        )

    def _emit_audit(self, req: ImportRequest, action: str, outcome: str) -> None:
        self._audit.initiate(
            ImportOperationalAuditEvent(
                actor_ref=req.actor_ref,
                action=action,
                correlation_id=req.correlation_id,
                outcome=outcome,
                target_ref=req.tenant_id,
                source_ref=req.source.ref,  # IC-003:131 completeness — the import source reference (references only)
            )
        )


class _ImportFailed(Exception):
    def __init__(self, code: str, status: ImportStatus) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
