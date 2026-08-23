"""The Import Service's own tenant-database write path (IC-003, IC-004, D-48).

One import is **one transaction in one tenant database**, and it writes three things:

    the tenant Startup copy      (an independent record with a soft source reference)
    one lineage row              (its provenance, with a D-23 integrity marker)
    the idempotency record       (so a retry replays instead of duplicating)

All three commit together or none of them do. That is IC-004's *atomic provenance* stated as
a transaction rather than as an intention: committed tenant data can never exist without the
provenance that explains where it came from, and an idempotency marker can never claim an
import that did not happen.

**Why the append happens here rather than in the Lineage Service.** In the retired
architecture the importer called a lineage *port* implemented by the lineage owner, on the
importer's own session, precisely so the two writes shared a transaction. In the Option A
architecture the fourteen services are separate processes that may not import one another
(IC-013 §13), and the Lineage Service is deliberately read-only — it publishes no write
operation at all. An HTTP call to another process holding another connection could not join
this transaction, so atomic provenance requires the append to happen on *this* connection.
What is preserved is the property that mattered: the marker algorithm is not re-implemented
here. It lives once, in :mod:`snackportal2.shared.lineage_chain`, and both this writer and any
future verifier compute through it.

**D-48.** The Database Router remains the sole authority on *which* database. This module asks
for a grant, opens the one connection that grant authorizes, uses it, and drops it. It never
selects a database, never caches a grant, and never reaches the Control database — a failure
to reach this tenant is an outage of this tenant and nothing else.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from ...shared.errors import invalid_request, tenant_unavailable
from ...shared.lineage_chain import CURRENT_MARKER_VERSION, GENESIS_PREV_MARKER, LineageIntent, marker_for
from ...shared.lineage_keys import LineageChainKey, LineageKeyResolver
from ...shared.tenant_data import GrantProvider, compose_record_ref, open_tenant_connection
from .service import (
    EVENT_TYPE_IMPORT,
    OPERATION_IMPORT,
    GlobalSourceRecord,
    ImportAttribution,
    ImportRecord,
)

#: Tenant tables this module writes. All three live in the same tenant database.
STARTUPS_TABLE = "startups"
LINEAGE_TABLE = "lineage"
IDEMPOTENCY_TABLE = "import_idempotency"
JOB_TABLE = "import_job"

#: The first segment of a per-tenant chain (D-24/D-25 segmentation is a label over seq ranges).
FIRST_SEGMENT = 1

#: What a completed import records in its bookkeeping rows.
COMPLETED = "completed"

#: The lineage columns, in insert order.
_LINEAGE_COLUMNS = (
    "lineage_id",
    "seq",
    "segment_id",
    "event_type",
    "occurred_at",
    "actor_ref",
    "source_ref",
    "target_ref",
    "operation",
    "schema_version",
    "derivation_ref",
    "parent_lineage_ref",
    "correlation_id",
    "marker_version",
    "prev_marker",
    "integrity_marker",
)

#: A per-database advisory lock covering one import unit of work.
#:
#: Two things need serializing and it is the same critical section for both: reading the chain
#: head before appending to it, and checking that the tenant does not already hold a copy of
#: this global record before inserting one. ``pg_advisory_xact_lock`` is core PostgreSQL,
#: needs no table privilege the append-only lineage writer role lacks, and releases at
#: transaction end — so a crashed import cannot leave the chain locked. It is the *liveness*
#: guarantee, not the correctness one: ``lineage.seq``'s UNIQUE constraint, the idempotency
#: primary key and ``startups_global_startup_id_key`` remain the fail-closed backstops.
#:
#: Each tenant has its own physical database, so the lock space is already per tenant and the
#: constant needs no tenant component.
_LOCK_NAMESPACE = "snackportal2.import.unit-of-work"
IMPORT_LOCK_KEY = int.from_bytes(hashlib.sha256(_LOCK_NAMESPACE.encode("utf-8")).digest()[:8], "big", signed=True)


class PostgresImportStore:
    """Persist one import into the tenant database the router binds.

    The chain key is resolved **before** a grant is requested. A tenant whose provenance key
    cannot be resolved therefore never causes a router call and never causes a tenant
    connection to be opened — the import is refused before it can touch anything.
    """

    def __init__(self, grants: GrantProvider, keys: LineageKeyResolver) -> None:
        self._grants = grants
        self._keys = keys

    # -- reads -------------------------------------------------------------------------

    def _require_chain_key(self, tenant_ref: str) -> LineageChainKey:
        """Resolve this tenant's chain key, or refuse the import outright.

        Called at the start of *both* store operations, not only the write. Provenance is a
        precondition of an import rather than a step within it, so a tenant whose key cannot be
        resolved is refused before anything happens at all — no router call, and no tenant
        database connection, not even for the idempotency probe. Measured, not assumed: a Stage
        5 live test watches ``pg_stat_database.sessions`` across a refused import and requires
        the delta to be zero.
        """
        return self._keys.resolve_lineage_key(tenant_ref)

    def find_existing(self, tenant_ref: str, key: str) -> Optional[ImportRecord]:
        self._require_chain_key(tenant_ref)
        with open_tenant_connection(self._grants.grant_for(tenant_ref)) as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                return self._existing(cursor, tenant_ref, key)

    @staticmethod
    def _existing(cursor: Any, tenant_ref: str, key: str) -> Optional[ImportRecord]:
        """The record a previous import of this (tenant, source) produced, if any.

        Joined rather than read separately: the idempotency row and the lineage row are written
        in one transaction, so the join can never be half-satisfied by a real import. A missing
        half would mean the tenant database had been edited outside this path.
        """
        cursor.execute(
            "SELECT idem.job_id, chain.lineage_id, chain.target_ref "
            "FROM " + IDEMPOTENCY_TABLE + " AS idem "
            "JOIN " + LINEAGE_TABLE + " AS chain ON chain.derivation_ref = idem.operation_key "
            "WHERE idem.operation_key = %s ORDER BY chain.seq LIMIT 1",
            (key,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return ImportRecord(
            import_id=str(row[0]),
            tenant_record_ref=str(row[2]),
            lineage_ref=compose_record_ref(tenant_ref, "lineage", str(row[1])),
        )

    # -- the write ---------------------------------------------------------------------

    def write_import(
        self, tenant_ref: str, key: str, source: GlobalSourceRecord, attribution: ImportAttribution
    ) -> Tuple[ImportRecord, bool]:
        """Write the copy, its provenance and its idempotency record in one transaction.

        Returns the record and whether this call turned out to be a replay — which it can be
        even after :meth:`find_existing` said otherwise, if a concurrent request completed the
        same import in between. Reporting that honestly is the difference between "idempotent"
        and "idempotent unless two requests arrive together".
        """
        chain_key = self._require_chain_key(tenant_ref)
        grant = self._grants.grant_for(tenant_ref)

        with open_tenant_connection(grant) as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (IMPORT_LOCK_KEY,))

                replayed = self._existing(cursor, tenant_ref, key)
                if replayed is not None:
                    return replayed, True

                if self._already_holds_source(cursor, source.record_ref):
                    # The tenant already holds a record derived from this global source, made
                    # outside this import path. A second independent copy would breach the
                    # accepted DDL's per-tenant uniqueness, and quietly *updating* the existing
                    # one would make an import behave like a synchronization. Refused instead,
                    # with nothing written.
                    raise invalid_request()

                target_ref = self._write_copy(cursor, tenant_ref, source)
                lineage_id = self._append_lineage(
                    cursor,
                    chain_key.material,
                    LineageIntent(
                        event_type=EVENT_TYPE_IMPORT,
                        occurred_at=datetime.now(timezone.utc).isoformat(),
                        actor_ref=attribution.actor_ref,
                        source_ref=source.record_ref,
                        target_ref=target_ref,
                        operation=OPERATION_IMPORT,
                        schema_version=grant.expected_schema_version,
                        derivation_ref=key,
                        correlation_id=attribution.correlation_id,
                    ),
                )
                self._record_bookkeeping(cursor, tenant_ref, key, attribution)

        return (
            ImportRecord(
                import_id=key,
                tenant_record_ref=target_ref,
                lineage_ref=compose_record_ref(tenant_ref, "lineage", lineage_id),
            ),
            False,
        )

    @staticmethod
    def _already_holds_source(cursor: Any, source_ref: str) -> bool:
        cursor.execute("SELECT 1 FROM " + STARTUPS_TABLE + " WHERE global_startup_id = %s LIMIT 1", (source_ref,))
        return cursor.fetchone() is not None

    @staticmethod
    def _write_copy(cursor: Any, tenant_ref: str, source: GlobalSourceRecord) -> str:
        """Insert the independent tenant copy and return its opaque record reference.

        ``global_startup_id`` is a soft text reference to the Control directory record, never a
        cross-database foreign key — after this insert the two records have separate lives, and
        nothing re-reads the global one.
        """
        cursor.execute(
            "INSERT INTO " + STARTUPS_TABLE
            + " (global_startup_id, company_name, industry, headquarters_country) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (
                source.record_ref,
                source.display_name,
                source.attributes.get("industry"),
                source.attributes.get("headquarters_country"),
            ),
        )
        row = cursor.fetchone()
        if row is None:
            raise tenant_unavailable()
        return compose_record_ref(tenant_ref, "startups", str(row[0]))

    @staticmethod
    def _append_lineage(cursor: Any, chain_key: bytes, intent: LineageIntent) -> str:
        """Append one row to this tenant's chain and return its lineage id.

        The head is read under the advisory lock taken above, so ``seq`` and ``prev_marker``
        describe the same predecessor the marker is computed against.
        """
        cursor.execute("SELECT seq, integrity_marker, segment_id FROM " + LINEAGE_TABLE + " ORDER BY seq DESC LIMIT 1")
        head = cursor.fetchone()
        sequence = (int(head[0]) + 1) if head else 1
        prev_marker = str(head[1]) if head else GENESIS_PREV_MARKER
        segment_id = int(head[2]) if head and head[2] is not None else FIRST_SEGMENT

        row: dict[str, Any] = {
            "lineage_id": uuid.uuid4().hex,
            "seq": sequence,
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
            "marker_version": CURRENT_MARKER_VERSION,
            "prev_marker": prev_marker,
        }
        row["integrity_marker"] = marker_for(chain_key, row, prev_marker, marker_version=CURRENT_MARKER_VERSION)

        cursor.execute(
            "INSERT INTO " + LINEAGE_TABLE + " (" + ", ".join(_LINEAGE_COLUMNS) + ") VALUES ("
            + ", ".join(["%s"] * len(_LINEAGE_COLUMNS)) + ")",
            tuple(row[name] for name in _LINEAGE_COLUMNS),
        )
        return str(row["lineage_id"])

    @staticmethod
    def _record_bookkeeping(cursor: Any, tenant_ref: str, key: str, attribution: ImportAttribution) -> None:
        """The job and idempotency rows.

        ``import_idempotency.operation_key`` is the table's primary key, so two concurrent
        imports of the same (tenant, source) cannot both succeed even if the advisory lock were
        removed — the second transaction fails and takes its own copy and lineage row with it.
        """
        cursor.execute(
            "INSERT INTO " + JOB_TABLE + " (job_id, operation_key, tenant_id, state, correlation_id) "
            "VALUES (%s, %s, %s, %s, %s)",
            (key, key, tenant_ref, COMPLETED, attribution.correlation_id),
        )
        cursor.execute(
            "INSERT INTO " + IDEMPOTENCY_TABLE + " (operation_key, job_id, status, applied, noop, rejected) "
            "VALUES (%s, %s, %s, 1, 0, 0)",
            (key, key, COMPLETED),
        )


__all__ = [
    "COMPLETED",
    "FIRST_SEGMENT",
    "IDEMPOTENCY_TABLE",
    "IMPORT_LOCK_KEY",
    "JOB_TABLE",
    "LINEAGE_TABLE",
    "STARTUPS_TABLE",
    "PostgresImportStore",
]
