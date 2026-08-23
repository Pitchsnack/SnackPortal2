"""Audit sinks — where an ingress-edge event durably lands.

**Migration dependency (IC-013 §10, normative).** Control DDL 012 pins
``CHECK (source_service = 'api_gateway')``, so the existing ``control_gateway_audit`` table
would *physically reject* a BFF-emitted row. The approved approach is a new append-only
table, leaving 012/013 and their byte-pins intact as historical evidence. That table is
migration **M-1** (D-46 §7), authored at
``backend/migrations/control/016_bff_ingress_audit.sql``, and the PostgreSQL sink here
targets it — never ``control_gateway_audit``.

The in-memory sink is the default. It is honest about what it is: an audit trail that does
not survive a restart is a development convenience, so a deployment that wants durability
must configure the DSN explicitly rather than discover the gap later.
"""

from __future__ import annotations

import os
from typing import List, Mapping, Optional, Protocol

from ...shared.config import db_connect_timeout
from .models import AuditEvent

#: Control-database DSN for the durable sink. Unset selects the in-memory sink.
ENV_AUDIT_DSN = "SP2_AUDIT_DSN"

#: The M-1 table. Deliberately NOT ``control_gateway_audit``: that table's CHECK constraint
#: rejects any source_service other than the retired Gateway.
AUDIT_TABLE = "control_ingress_audit"


class AuditSink(Protocol):
    """Append one event; read events back."""

    def append(self, event: AuditEvent) -> None:
        ...

    def read(self, tenant_ref: Optional[str], actor_ref: Optional[str], limit: int) -> List[AuditEvent]:
        ...


class InMemoryAuditSink:
    """Append-only in-process sink. Insertion order is preserved and never rewritten."""

    def __init__(self) -> None:
        self._events: List[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self._events.append(event)

    def read(self, tenant_ref: Optional[str], actor_ref: Optional[str], limit: int) -> List[AuditEvent]:
        selected = [
            event
            for event in self._events
            if (tenant_ref is None or event.tenant_ref == tenant_ref)
            and (actor_ref is None or event.actor_ref == actor_ref)
        ]
        return selected[-limit:]


class PostgresAuditSink:
    """The durable Control-DB sink, targeting migration M-1's append-only table."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _connect(self) -> object:
        import psycopg

        # Time-bounded, for the same reason as every other connect in the rebuild: an audit
        # write that blocks for two minutes on an unreachable Control database would hold the
        # emitting request open far past the point where its caller has given up.
        return psycopg.connect(self._dsn, connect_timeout=db_connect_timeout())

    def append(self, event: AuditEvent) -> None:
        with self._connect() as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO " + AUDIT_TABLE + " (event_id, occurred_at, source_service, action, outcome, "
                    "correlation_id, actor_ref, subject_ref, tenant_ref, record_ref, carrier_ref) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        event.event_id,
                        event.occurred_at,
                        event.source_service,
                        event.action.value,
                        event.outcome.value,
                        event.correlation_id,
                        event.actor_ref,
                        event.subject_ref,
                        event.tenant_ref,
                        event.record_ref,
                        event.carrier_ref,
                    ),
                )

    def read(self, tenant_ref: Optional[str], actor_ref: Optional[str], limit: int) -> List[AuditEvent]:
        clauses: List[str] = []
        params: List[object] = []
        if tenant_ref is not None:
            clauses.append("tenant_ref = %s")
            params.append(tenant_ref)
        if actor_ref is not None:
            clauses.append("actor_ref = %s")
            params.append(actor_ref)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        with self._connect() as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT event_id, occurred_at, source_service, action, outcome, correlation_id, actor_ref, "
                    "subject_ref, tenant_ref, record_ref, carrier_ref FROM " + AUDIT_TABLE + where
                    + " ORDER BY occurred_at, event_id LIMIT %s",
                    tuple(params),
                )
                rows = cursor.fetchall()
        return [
            AuditEvent(
                event_id=row[0],
                occurred_at=row[1],
                source_service=row[2],
                action=row[3],
                outcome=row[4],
                correlation_id=row[5],
                actor_ref=row[6],
                subject_ref=row[7],
                tenant_ref=row[8],
                record_ref=row[9],
                carrier_ref=row[10],
            )
            for row in rows
        ]


def build_sink(env: Optional[Mapping[str, str]] = None) -> AuditSink:
    """Select the sink from configuration; in-memory when no Control DSN is set."""
    source: Mapping[str, str] = os.environ if env is None else env
    dsn = source.get(ENV_AUDIT_DSN, "").strip()
    if dsn:
        return PostgresAuditSink(dsn)
    return InMemoryAuditSink()


__all__ = ["AUDIT_TABLE", "ENV_AUDIT_DSN", "AuditSink", "InMemoryAuditSink", "PostgresAuditSink", "build_sink"]
