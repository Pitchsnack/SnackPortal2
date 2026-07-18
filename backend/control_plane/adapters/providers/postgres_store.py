"""PostgreSQL ControlStore provider (Build Phase 4; closes O-2/O-5).

Concrete Control-Database persistence behind the vendor-neutral ControlStore port.
The control-plane domain stays persistence-agnostic — it depends only on the port;
the composition root selects this provider. Standard PostgreSQL only (AWS RDS / Azure
/ Cloud SQL / self-hosted); no provider-proprietary features. The database driver
import is confined to this provider zone (Driver Containment Standard; PRD-P4-R2 C).

Not exercised by the stdlib unit suite (requires a live Control DB + installed
driver); the suite uses the in-memory ControlStore. Stores references only — never
credentials (D-14): the tenant database association is two columns
({store_ref, version}), never the secret value.

Lazy-connect (PRD 06 B-7B / B7B-D11). Construction performs NO ``psycopg.connect`` —
``__init__`` only records its inputs — so ``ControlPlane`` construction and
``create_app()`` perform no PostgreSQL I/O even when this durable store is selected. The
connection opens on the first store operation and FAILS CLOSED there if the descriptor is
unresolvable / the DSN is invalid / the Control DB is unreachable / the schema is absent.
Dual construction (references only, D-14): pass a literal ``dsn=`` connection descriptor
(the B-7A live harness path) OR ``secrets=`` + ``ref=`` to resolve the descriptor from a
``SecretStore`` by reference (the composition-root durable path — no DSN literal transits
the composition root). The resolved descriptor is held only for the connect call and is
never retained on the adapter.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

import psycopg  # type: ignore  # noqa: F401  (driver import confined to this zone)

from control_plane.gateway_audit import (
    GATEWAY_AUDIT_SOURCE_SERVICE,
    GATEWAY_AUDIT_STORE_ACTIONS,
    GatewayAuditAppendResult,
    GatewayAuditConflictError,
    GatewayAuditInvalidError,
    GatewayAuditRecord,
    GatewayAuditStorePort,
)
from control_plane.import_audit import (
    IMPORT_AUDIT_SOURCE_SERVICE,
    IMPORT_AUDIT_STORE_ACTIONS,
    ImportAuditAppendResult,
    ImportAuditConflictError,
    ImportAuditInvalidError,
    ImportAuditRecord,
    ImportAuditStorePort,
)
from control_plane.ports import ControlStore, ControlStoreConcurrencyError
from control_plane.records import (
    ControlAuditRecord,
    DirectoryKind,
    DirectoryRecord,
    FederationConfig,
    MembershipRecord,
    Role,
    TenantLifecycleState,
    TenantRecord,
)
from control_plane.routing_audit import (
    ROUTING_AUDIT_STORE_ACTIONS,
    RoutingAuditAppendResult,
    RoutingAuditConflictError,
    RoutingAuditInvalidError,
    RoutingAuditRecord,
    RoutingAuditStorePort,
)
from shared.secrets import SecretRef, SecretStore


def _ts_to_iso(value: Any) -> str:
    """Normalize a stored ``ts`` value to a UTC ISO-8601 string (same instant).

    A ``timestamptz`` column is returned by the driver as a timezone-aware ``datetime``,
    but ``ControlAuditRecord.timestamp`` is typed ``str`` — and the in-memory adapter
    round-trips the written ``now_iso()`` string. Normalize on read (PRD 06 B-7B / B7B-D7)
    so BOTH adapters return ``str`` representing the same instant, without retyping the
    record (``records.py`` is unchanged). A naive datetime is assumed UTC; an already-``str``
    value passes through (defensive)."""
    if isinstance(value, datetime):
        dt = value.astimezone(timezone.utc) if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    return str(value)


class PostgresControlStore(ControlStore):
    def __init__(
        self,
        dsn: Optional[str] = None,
        schema_version: int = 1,
        *,
        secrets: Optional[SecretStore] = None,
        ref: Optional[SecretRef] = None,
    ) -> None:
        # Lazy-connect: record inputs only; NO psycopg.connect here (B7B-D11). Exactly one
        # connection source is required — a literal dsn= OR a secret reference (secrets=, ref=).
        if (dsn is None) == (ref is None):
            raise ValueError("PostgresControlStore requires exactly one of dsn= or (secrets=, ref=)")
        if ref is not None and secrets is None:
            raise ValueError("PostgresControlStore ref= requires a SecretStore (secrets=)")
        self._dsn = dsn
        self._secrets = secrets
        self._ref = ref
        self._schema_version = schema_version
        # 07D-3B-TIER2-RESOLVED (AT-PMV46-4): per-unit-of-work scoping. One store instance ==
        # one lazily-cached connection == ONE unit of work; per-request instances are issued by
        # control_store_factory.PostgresControlStoreFactory.acquire(), which release()s this
        # connection (rollback + close) at unit-of-work end, so no open transaction ever leaks
        # between units of work. A transition's CAS stays UNCOMMITTED until its audit append
        # commits both ON THIS SAME CONNECTION (PRD 07D-2e) — which is exactly why one
        # store/connection must NEVER be shared across concurrent logical requests: a sibling's
        # commit/rollback would finalize/discard this unit of work's pending state (the proven
        # pre-07D-3b hazard). 07E contract: every request transport
        # MUST acquire a fresh unit of work per request via the factory and
        # MUST NOT share it across concurrent requests.
        # The static guard test_07d3_multiinstance_readiness_static.py pins this marker, the
        # factory shape, and the autocommit pin in lockstep.
        self._conn_cache: Any = None

    @property
    def _conn(self) -> Any:
        """Lazily open and cache the Control-DB connection (no I/O until first use)."""
        if self._conn_cache is None:
            self._conn_cache = self._open()
        return self._conn_cache

    def _open(self) -> Any:
        """Resolve the Control-DB descriptor (by reference or literal) and open the connection.

        Fail-closed: ``PermissionError`` (ref not allow-listed), ``LookupError`` (unresolved
        ref), and connect errors all propagate — the caller's operation is rejected and no
        partial state is committed. The resolved descriptor is dropped immediately (D-14)."""
        descriptor: Optional[str] = None
        try:
            if self._ref is not None:
                assert self._secrets is not None  # guaranteed by __init__
                descriptor = self._secrets.resolve(self._ref).material  # in-memory only
            else:
                assert self._dsn is not None  # guaranteed by __init__ (exactly one source)
                descriptor = self._dsn
            conn = psycopg.connect(descriptor)
            # PRD 07D-3b (AT-07D3A-5) pin: the 07D-2e transactional contract (uncommitted CAS +
            # audit append commits both) REQUIRES autocommit=False — psycopg's default, pinned
            # explicitly so a driver/config change cannot silently break atomicity. The isolation
            # level is deliberately NOT overridden: the PostgreSQL default (READ COMMITTED) is
            # the model the version-predicated CAS is proven under (row locks + per-statement
            # snapshots; 07D-2e/07D-3a/07D-3b live proofs). Standard PostgreSQL only.
            conn.autocommit = False
            return conn
        finally:
            descriptor = None  # never retained on the adapter

    def release(self) -> None:
        """End this store's unit of work: roll back any open transaction and close (idempotent).

        PRD 07D-3b: a unit of work's durable effects are ONLY what its audit append committed;
        anything still uncommitted at release is discarded (fail closed), and the closed
        connection can never leak an open transaction into a later unit of work. Cleanup is
        best-effort on an already-broken connection (its server session dies with it)."""
        conn = self._conn_cache
        if conn is None:
            return
        self._conn_cache = None
        try:
            conn.rollback()
        except Exception:
            pass  # broken connection: no transaction survives it
        try:
            conn.close()
        except Exception:
            pass

    # -- control metadata -----------------------------------------------------
    def is_reachable(self) -> bool:
        try:
            with self._conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            return True
        except Exception:
            return False

    def schema_version(self) -> int:
        return self._schema_version

    # -- tenant registry ------------------------------------------------------
    def put_tenant(self, record: TenantRecord) -> None:
        # PRD 07D-3b (AT-07D3A-3): a failure between execute and commit must roll back —
        # a dangling open transaction on a connection reused/released after this call would
        # leak into the next operation (fail closed, no partial write). Same pattern on the
        # other three single-commit sites and append_audit.
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                INSERT INTO control_tenants (
                    tenant_id, organization_ref, lifecycle_state, expected_schema_version,
                    assoc_store_ref, assoc_version, federation_config_ref, created_at, updated_at, version
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (tenant_id) DO UPDATE SET
                    organization_ref = EXCLUDED.organization_ref,
                    lifecycle_state = EXCLUDED.lifecycle_state,
                    expected_schema_version = EXCLUDED.expected_schema_version,
                    assoc_store_ref = EXCLUDED.assoc_store_ref,
                    assoc_version = EXCLUDED.assoc_version,
                    federation_config_ref = EXCLUDED.federation_config_ref,
                    updated_at = EXCLUDED.updated_at,
                    version = EXCLUDED.version
                """,
                    (
                        record.tenant_id,
                        record.organization_ref,
                        record.lifecycle_state.value,
                        record.expected_schema_version,
                        record.database_association_ref.store_ref,
                        record.database_association_ref.version,
                        record.federation_config_ref,
                        record.created_at,
                        record.updated_at,
                        record.version,
                    ),
                )
            self._conn.commit()
        except Exception:
            try:
                self._conn.rollback()
            except Exception:
                pass  # connection-level failure: the original error below is the signal
            raise

    def compare_and_swap_tenant(self, updated: TenantRecord, *, expected_version: int) -> TenantRecord:
        # PRD 07D-2e (D-2e-1/D-2e-4): version-predicated lifecycle write. The UPDATE matches a
        # row ONLY at the caller's expected version (explicit version column; never xmin) and
        # increments it in place. It deliberately does NOT commit: the transition's subsequent
        # append_audit commits the audit row and this write in ONE Control-DB transaction, so
        # a conflict rolls back with no orphan audit and a failed audit write rolls back the
        # state change (see the port docstring). A conflict (0 rows) rolls back and raises the
        # typed error — a newer concurrent lifecycle write is never silently overwritten.
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE control_tenants SET
                    organization_ref = %s,
                    lifecycle_state = %s,
                    expected_schema_version = %s,
                    assoc_store_ref = %s,
                    assoc_version = %s,
                    federation_config_ref = %s,
                    updated_at = %s,
                    version = version + 1
                WHERE tenant_id = %s AND version = %s
                """,
                (
                    updated.organization_ref,
                    updated.lifecycle_state.value,
                    updated.expected_schema_version,
                    updated.database_association_ref.store_ref,
                    updated.database_association_ref.version,
                    updated.federation_config_ref,
                    updated.updated_at,
                    updated.tenant_id,
                    expected_version,
                ),
            )
            matched = cur.rowcount
        if matched != 1:
            self._conn.rollback()  # discard any uncommitted composite work (no orphan audit)
            raise ControlStoreConcurrencyError("stale tenant version (concurrent lifecycle write)")
        return replace(updated, version=expected_version + 1)

    def get_tenant(self, tenant_id: str) -> Optional[TenantRecord]:
        with self._conn.cursor() as cur:
            cur.execute(
                """SELECT tenant_id, organization_ref, lifecycle_state, expected_schema_version,
                          assoc_store_ref, assoc_version, federation_config_ref, created_at, updated_at, version
                   FROM control_tenants WHERE tenant_id = %s""",
                (tenant_id,),
            )
            row = cur.fetchone()
        return self._tenant_from_row(row) if row else None

    def list_tenant_ids(self) -> List[str]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT tenant_id FROM control_tenants")
            return [r[0] for r in cur.fetchall()]

    # -- membership -----------------------------------------------------------
    def put_membership(self, record: MembershipRecord) -> None:
        # PRD 07D-3b (AT-07D3A-3): rollback on failure — no dangling open transaction.
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO control_memberships (principal_ref, tenant_id, role)
                   VALUES (%s,%s,%s) ON CONFLICT (principal_ref, tenant_id) DO UPDATE
                   SET role = EXCLUDED.role""",
                    (record.principal_ref, record.tenant_id, record.role.value),
                )
            self._conn.commit()
        except Exception:
            try:
                self._conn.rollback()
            except Exception:
                pass
            raise

    def list_memberships(self, principal_ref: Optional[str] = None, tenant_id: Optional[str] = None) -> List[MembershipRecord]:
        clauses, params = [], []
        if principal_ref is not None:
            clauses.append("principal_ref = %s")
            params.append(principal_ref)
        if tenant_id is not None:
            clauses.append("tenant_id = %s")
            params.append(tenant_id)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._conn.cursor() as cur:
            cur.execute("SELECT principal_ref, tenant_id, role FROM control_memberships" + where, params)
            return [MembershipRecord(principal_ref=r[0], tenant_id=r[1], role=Role(r[2])) for r in cur.fetchall()]

    # -- federation config ----------------------------------------------------
    def put_federation(self, config: FederationConfig) -> None:
        # PRD 07D-3b (AT-07D3A-3): rollback on failure — no dangling open transaction.
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO control_federation
                       (tenant_id, oidc_issuer, oidc_audience, jwks_ref, claim_to_tenant_rule)
                   VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT (tenant_id) DO UPDATE SET
                       oidc_issuer = EXCLUDED.oidc_issuer,
                       oidc_audience = EXCLUDED.oidc_audience,
                       jwks_ref = EXCLUDED.jwks_ref,
                       claim_to_tenant_rule = EXCLUDED.claim_to_tenant_rule""",
                    (config.tenant_id, config.oidc_issuer, config.oidc_audience, config.jwks_ref, config.claim_to_tenant_rule),
                )
            self._conn.commit()
        except Exception:
            try:
                self._conn.rollback()
            except Exception:
                pass
            raise

    def get_federation(self, tenant_id: str) -> Optional[FederationConfig]:
        with self._conn.cursor() as cur:
            cur.execute(
                """SELECT tenant_id, oidc_issuer, oidc_audience, jwks_ref, claim_to_tenant_rule
                   FROM control_federation WHERE tenant_id = %s""",
                (tenant_id,),
            )
            r = cur.fetchone()
        if not r:
            return None
        return FederationConfig(tenant_id=r[0], oidc_issuer=r[1], oidc_audience=r[2], jwks_ref=r[3], claim_to_tenant_rule=r[4])

    # -- global discovery platform --------------------------------------------
    def put_directory_record(self, record: DirectoryRecord) -> None:
        # PRD 07D-3b (AT-07D3A-3): rollback on failure — no dangling open transaction.
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO control_directory (directory, record_id, display_name, attributes)
                   VALUES (%s,%s,%s,%s)
                   ON CONFLICT (directory, record_id) DO UPDATE SET
                       display_name = EXCLUDED.display_name, attributes = EXCLUDED.attributes""",
                    (record.directory.value, record.record_id, record.display_name, dict(record.attributes)),
                )
            self._conn.commit()
        except Exception:
            try:
                self._conn.rollback()
            except Exception:
                pass
            raise

    def get_directory_record(self, directory: DirectoryKind, record_id: str) -> Optional[DirectoryRecord]:
        with self._conn.cursor() as cur:
            cur.execute(
                """SELECT directory, record_id, display_name, attributes
                   FROM control_directory WHERE directory = %s AND record_id = %s""",
                (directory.value, record_id),
            )
            r = cur.fetchone()
        if not r:
            return None
        return DirectoryRecord(directory=DirectoryKind(r[0]), record_id=r[1], display_name=r[2], attributes=dict(r[3] or {}))

    def list_directory(self, directory: DirectoryKind) -> List[DirectoryRecord]:
        with self._conn.cursor() as cur:
            cur.execute(
                """SELECT directory, record_id, display_name, attributes
                   FROM control_directory WHERE directory = %s""",
                (directory.value,),
            )
            return [
                DirectoryRecord(
                    directory=DirectoryKind(r[0]),
                    record_id=r[1],
                    display_name=r[2],
                    attributes=dict(r[3] or {}),
                )
                for r in cur.fetchall()
            ]

    # -- operational audit (append-only) --------------------------------------
    def append_audit(self, record: ControlAuditRecord) -> None:
        # PRD 07D-2e (D-2e-4): the commit here finalizes the connection's open transaction —
        # for a lifecycle transition that includes the preceding compare_and_swap_tenant
        # UPDATE, making audit + state change atomic. On ANY failure the transaction is
        # rolled back explicitly (a failed required audit write must reject the transition
        # with NO committed partial state — B7B-D5, now transactional) and the error
        # propagates unchanged (fail closed).
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO control_audit
                           (actor, tenant_id, action, from_state, to_state, ts, correlation_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        record.actor,
                        record.tenant_id,
                        record.action,
                        record.from_state,
                        record.to_state,
                        record.timestamp,
                        record.correlation_id,
                    ),
                )
            self._conn.commit()
        except Exception:
            try:
                self._conn.rollback()
            except Exception:
                pass  # connection-level failure: the original error below is the signal
            raise

    def list_audit(self) -> List[ControlAuditRecord]:
        with self._conn.cursor() as cur:
            cur.execute(
                """SELECT actor, tenant_id, action, from_state, to_state, ts, correlation_id
                   FROM control_audit ORDER BY id ASC"""
            )
            return [
                ControlAuditRecord(
                    actor=r[0],
                    tenant_id=r[1],
                    action=r[2],
                    from_state=r[3],
                    to_state=r[4],
                    timestamp=_ts_to_iso(r[5]),  # driver datetime -> UTC ISO-8601 str (B7B-D7)
                    correlation_id=r[6],
                )
                for r in cur.fetchall()
            ]

    # -- internals ------------------------------------------------------------
    @staticmethod
    def _tenant_from_row(row: Tuple[Any, ...]) -> TenantRecord:
        return TenantRecord(
            tenant_id=row[0],
            organization_ref=row[1],
            lifecycle_state=TenantLifecycleState(row[2]),
            expected_schema_version=row[3],
            database_association_ref=SecretRef(store_ref=row[4], version=row[5]),
            federation_config_ref=row[6],
            created_at=row[7],
            updated_at=row[8],
            version=int(row[9]),
        )


# --- DBR-AR-2B: durable routing-audit store (dedicated port; ControlStore unchanged) ---

# Caller-bound columns of control_routing_audit (DDL 010) in INSERT/SELECT order.
# id and recorded_at are store-assigned and are never bound by the adapter.
_ROUTING_AUDIT_COLUMNS = (
    "event_id",
    "event_version",
    "occurred_at",
    "correlation_id",
    "actor_ref",
    "action",
    "outcome",
    "source_service",
    "source_version",
    "request_ref",
    "trace_ref",
    "tenant_ref",
    "resolved_tenant_ref",
    "public_code",
    "error_class",
    "association_store_ref",
    "association_version",
    "lane",
)

_ROUTING_AUDIT_INSERT = (
    "INSERT INTO control_routing_audit ("
    + ", ".join(_ROUTING_AUDIT_COLUMNS)
    + ") VALUES ("
    + ", ".join(["%s"] * len(_ROUTING_AUDIT_COLUMNS))
    + ") ON CONFLICT (event_id) DO NOTHING RETURNING id"
)

_ROUTING_AUDIT_SELECT = "SELECT " + ", ".join(_ROUTING_AUDIT_COLUMNS) + " FROM control_routing_audit WHERE event_id = %s"


def _same_instant(stored: Any, submitted: str) -> bool:
    """True iff a stored ``occurred_at`` and the submitted ISO-8601 string are the same instant.

    A ``timestamptz`` comes back from the driver as an aware ``datetime`` whose textual form
    may differ from the router-minted ISO string for the SAME instant — a replay must not be
    misclassified as a conflict over representation (nor a different instant accepted as a
    match). Naive values are assumed UTC (the ``_ts_to_iso`` convention)."""
    try:
        submitted_dt = datetime.fromisoformat(submitted)
    except ValueError:
        return str(stored) == submitted  # non-ISO caller value: byte comparison only
    if isinstance(stored, datetime):
        stored_dt = stored
    else:
        try:
            stored_dt = datetime.fromisoformat(str(stored))
        except ValueError:
            return False
    if stored_dt.tzinfo is None:
        stored_dt = stored_dt.replace(tzinfo=timezone.utc)
    if submitted_dt.tzinfo is None:
        submitted_dt = submitted_dt.replace(tzinfo=timezone.utc)
    return stored_dt == submitted_dt


class PostgresRoutingAuditStore(RoutingAuditStorePort):
    """Durable routing-audit adapter (DBR-AR-2B): one idempotent append into control_routing_audit.

    A DEDICATED adapter behind ``RoutingAuditStorePort`` — deliberately NOT a ``ControlStore``
    method (the frozen port is unchanged; the DistinctnessLedger precedent). Same conventions as
    ``PostgresControlStore``: lazy-connect (construction performs NO ``psycopg.connect``), dual
    construction (literal ``dsn=`` OR ``secrets=`` + ``ref=`` reference resolution, D-14),
    ``autocommit = False``, commit ONLY on a newly inserted row, rollback-then-reraise on any
    failure, ``release()`` = rollback + close. ``recorded_at`` and ``id`` are assigned by the
    database (DDL 010) and are never bound here. An exact replay of an existing ``event_id`` is
    an idempotent no-op (``DUPLICATE_MATCH``, nothing committed); a same-ID/different-payload
    replay fails closed with ``RoutingAuditConflictError`` (contract §7.2/§12). Append-only:
    this adapter contains no UPDATE, DELETE, read, query, export, or purge surface. Errors are
    re-raised unchanged and never wrapped with SQL, descriptor, topology, or row content.
    Uncomposed in DBR-AR-2B: no composition root constructs it (DBR-AR-2C owns composition)."""

    def __init__(
        self,
        dsn: Optional[str] = None,
        *,
        secrets: Optional[SecretStore] = None,
        ref: Optional[SecretRef] = None,
    ) -> None:
        # Lazy-connect: record inputs only; NO psycopg.connect here (B7B-D11 convention).
        if (dsn is None) == (ref is None):
            raise ValueError("PostgresRoutingAuditStore requires exactly one of dsn= or (secrets=, ref=)")
        if ref is not None and secrets is None:
            raise ValueError("PostgresRoutingAuditStore ref= requires a SecretStore (secrets=)")
        self._dsn = dsn
        self._secrets = secrets
        self._ref = ref
        self._conn_cache: Any = None

    @property
    def _conn(self) -> Any:
        """Lazily open and cache the Control-DB connection (no I/O until first use)."""
        if self._conn_cache is None:
            self._conn_cache = self._open()
        return self._conn_cache

    def _open(self) -> Any:
        """Resolve the Control-DB descriptor (by reference or literal) and open the connection.

        Fail-closed: resolution and connect errors propagate — the append is rejected and no
        partial state is committed. The resolved descriptor is dropped immediately (D-14)."""
        descriptor: Optional[str] = None
        try:
            if self._ref is not None:
                assert self._secrets is not None  # guaranteed by __init__
                descriptor = self._secrets.resolve(self._ref).material  # in-memory only
            else:
                assert self._dsn is not None  # guaranteed by __init__ (exactly one source)
                descriptor = self._dsn
            conn = psycopg.connect(descriptor)
            conn.autocommit = False  # single-INSERT transaction; commit only on a new row
            return conn
        finally:
            descriptor = None  # never retained on the adapter

    def release(self) -> None:
        """Roll back any open transaction and close the cached connection (idempotent)."""
        conn = self._conn_cache
        if conn is None:
            return
        self._conn_cache = None
        try:
            conn.rollback()
        except Exception:
            pass  # broken connection: no transaction survives it
        try:
            conn.close()
        except Exception:
            pass

    def append_routing_audit(self, record: RoutingAuditRecord) -> RoutingAuditAppendResult:
        self._validate(record)
        try:
            with self._conn.cursor() as cur:
                cur.execute(_ROUTING_AUDIT_INSERT, self._params(record))
                inserted = cur.fetchone() is not None
                stored = None
                if not inserted:
                    cur.execute(_ROUTING_AUDIT_SELECT, (record.event_id,))
                    stored = cur.fetchone()
            if inserted:
                self._conn.commit()  # the ONLY commit: exactly one new durable row
                return RoutingAuditAppendResult.INSERTED
            # Replay path: nothing durable to persist — end the transaction WITHOUT committing.
            self._conn.rollback()
            if stored is not None and self._replay_matches(stored, record):
                return RoutingAuditAppendResult.DUPLICATE_MATCH
            raise RoutingAuditConflictError("routing-audit idempotency conflict for a replayed event_id")
        except (RoutingAuditConflictError, RoutingAuditInvalidError):
            raise  # bounded errors: transaction already closed above
        except Exception:
            try:
                self._conn.rollback()
            except Exception:
                pass  # connection-level failure: the original error below is the signal
            raise

    @staticmethod
    def _validate(record: RoutingAuditRecord) -> None:
        """Bounded pre-insert validation (fail closed BEFORE any durable write)."""
        if record.action not in ROUTING_AUDIT_STORE_ACTIONS:
            raise RoutingAuditInvalidError("routing-audit record rejected: unknown action")
        if record.event_version <= 0:
            raise RoutingAuditInvalidError("routing-audit record rejected: non-positive event_version")
        if record.source_service != "database_router":
            raise RoutingAuditInvalidError("routing-audit record rejected: unknown source_service")
        for name in ("event_id", "occurred_at", "correlation_id", "actor_ref", "outcome", "source_version"):
            if not getattr(record, name):
                raise RoutingAuditInvalidError("routing-audit record rejected: missing required field")

    @staticmethod
    def _params(record: RoutingAuditRecord) -> Tuple[Any, ...]:
        return (
            record.event_id,
            record.event_version,
            record.occurred_at,
            record.correlation_id,
            record.actor_ref,
            record.action,
            record.outcome,
            record.source_service,
            record.source_version,
            record.request_ref,
            record.trace_ref,
            record.tenant_ref,
            record.resolved_tenant_ref,
            record.public_code,
            record.error_class,
            record.association_store_ref,
            record.association_version,
            record.lane,
        )

    @staticmethod
    def _replay_matches(row: Tuple[Any, ...], record: RoutingAuditRecord) -> bool:
        """Exact field comparison of a stored row against a replayed record (contract §7.2)."""
        if str(row[0]).lower() != record.event_id.lower():
            return False  # defensive: the select is keyed by event_id
        if int(row[1]) != record.event_version:
            return False
        if not _same_instant(row[2], record.occurred_at):
            return False
        return tuple(row[3:18]) == (
            record.correlation_id,
            record.actor_ref,
            record.action,
            record.outcome,
            record.source_service,
            record.source_version,
            record.request_ref,
            record.trace_ref,
            record.tenant_ref,
            record.resolved_tenant_ref,
            record.public_code,
            record.error_class,
            record.association_store_ref,
            record.association_version,
            record.lane,
        )


# --- Gateway Audit V1a: durable Gateway operational-audit store (dedicated port; ControlStore unchanged) ---

# Caller-bound columns of control_gateway_audit (DDL 012) in INSERT/SELECT order.
# id and recorded_at are store-assigned and are never bound by the adapter.
_GATEWAY_AUDIT_COLUMNS = (
    "audit_id",
    "event_version",
    "occurred_at",
    "correlation_id",
    "action",
    "outcome",
    "source_service",
    "actor_ref",
    "subject_ref",
    "tenant_ref",
    "carrier_ref",
)

_GATEWAY_AUDIT_INSERT = (
    "INSERT INTO control_gateway_audit ("
    + ", ".join(_GATEWAY_AUDIT_COLUMNS)
    + ") VALUES ("
    + ", ".join(["%s"] * len(_GATEWAY_AUDIT_COLUMNS))
    + ") ON CONFLICT (audit_id) DO NOTHING RETURNING id"
)

_GATEWAY_AUDIT_SELECT = "SELECT " + ", ".join(_GATEWAY_AUDIT_COLUMNS) + " FROM control_gateway_audit WHERE audit_id = %s"


class PostgresGatewayAuditStore(GatewayAuditStorePort):
    """Durable Gateway operational-audit adapter (Gateway Audit V1a): one idempotent append into control_gateway_audit.

    A DEDICATED adapter behind ``GatewayAuditStorePort`` — deliberately NOT a ``ControlStore`` method
    (the frozen port is unchanged; the DistinctnessLedger / RoutingAudit precedent). Same conventions
    as ``PostgresRoutingAuditStore``: lazy-connect (construction performs NO ``psycopg.connect``),
    dual construction (literal ``dsn=`` OR ``secrets=`` + ``ref=`` reference resolution, D-14),
    ``autocommit = False``, commit ONLY on a newly inserted row, rollback-then-reraise on any failure,
    ``release()`` = rollback + close. ``recorded_at`` and ``id`` are assigned by the database (DDL 012)
    and are never bound here. An exact replay of an existing ``audit_id`` is an idempotent no-op
    (``DUPLICATE_MATCH``, nothing committed); a same-ID/different-payload replay fails closed with
    ``GatewayAuditConflictError``. Append-only: this adapter contains no UPDATE, DELETE, read, query,
    export, or purge surface. Errors are re-raised unchanged and never wrapped with SQL, descriptor,
    topology, or row content. Uncomposed in production until the Gateway Audit V1a seam is env-selected.
    """

    def __init__(
        self,
        dsn: Optional[str] = None,
        *,
        secrets: Optional[SecretStore] = None,
        ref: Optional[SecretRef] = None,
    ) -> None:
        # Lazy-connect: record inputs only; NO psycopg.connect here (B7B-D11 convention).
        if (dsn is None) == (ref is None):
            raise ValueError("PostgresGatewayAuditStore requires exactly one of dsn= or (secrets=, ref=)")
        if ref is not None and secrets is None:
            raise ValueError("PostgresGatewayAuditStore ref= requires a SecretStore (secrets=)")
        self._dsn = dsn
        self._secrets = secrets
        self._ref = ref
        self._conn_cache: Any = None

    @property
    def _conn(self) -> Any:
        """Lazily open and cache the Control-DB connection (no I/O until first use)."""
        if self._conn_cache is None:
            self._conn_cache = self._open()
        return self._conn_cache

    def _open(self) -> Any:
        """Resolve the Control-DB descriptor (by reference or literal) and open the connection.

        Fail-closed: resolution and connect errors propagate — the append is rejected and no partial
        state is committed. The resolved descriptor is dropped immediately (D-14)."""
        descriptor: Optional[str] = None
        try:
            if self._ref is not None:
                assert self._secrets is not None  # guaranteed by __init__
                descriptor = self._secrets.resolve(self._ref).material  # in-memory only
            else:
                assert self._dsn is not None  # guaranteed by __init__ (exactly one source)
                descriptor = self._dsn
            conn = psycopg.connect(descriptor)
            conn.autocommit = False  # single-INSERT transaction; commit only on a new row
            return conn
        finally:
            descriptor = None  # never retained on the adapter

    def release(self) -> None:
        """Roll back any open transaction and close the cached connection (idempotent)."""
        conn = self._conn_cache
        if conn is None:
            return
        self._conn_cache = None
        try:
            conn.rollback()
        except Exception:
            pass  # broken connection: no transaction survives it
        try:
            conn.close()
        except Exception:
            pass

    def append_gateway_audit(self, record: GatewayAuditRecord) -> GatewayAuditAppendResult:
        self._validate(record)
        try:
            with self._conn.cursor() as cur:
                cur.execute(_GATEWAY_AUDIT_INSERT, self._params(record))
                inserted = cur.fetchone() is not None
                stored = None
                if not inserted:
                    cur.execute(_GATEWAY_AUDIT_SELECT, (record.audit_id,))
                    stored = cur.fetchone()
            if inserted:
                self._conn.commit()  # the ONLY commit: exactly one new durable row
                return GatewayAuditAppendResult.INSERTED
            # Replay path: nothing durable to persist — end the transaction WITHOUT committing.
            self._conn.rollback()
            if stored is not None and self._replay_matches(stored, record):
                return GatewayAuditAppendResult.DUPLICATE_MATCH
            raise GatewayAuditConflictError("gateway-audit idempotency conflict for a replayed audit_id")
        except (GatewayAuditConflictError, GatewayAuditInvalidError):
            raise  # bounded errors: transaction already closed above
        except Exception:
            try:
                self._conn.rollback()
            except Exception:
                pass  # connection-level failure: the original error below is the signal
            raise

    @staticmethod
    def _validate(record: GatewayAuditRecord) -> None:
        """Bounded pre-insert validation (fail closed BEFORE any durable write)."""
        if record.action not in GATEWAY_AUDIT_STORE_ACTIONS:
            raise GatewayAuditInvalidError("gateway-audit record rejected: unknown action")
        if record.event_version <= 0:
            raise GatewayAuditInvalidError("gateway-audit record rejected: non-positive event_version")
        if record.source_service != GATEWAY_AUDIT_SOURCE_SERVICE:
            raise GatewayAuditInvalidError("gateway-audit record rejected: unknown source_service")
        for name in ("audit_id", "occurred_at", "correlation_id", "outcome"):
            if not getattr(record, name):
                raise GatewayAuditInvalidError("gateway-audit record rejected: missing required field")

    @staticmethod
    def _params(record: GatewayAuditRecord) -> Tuple[Any, ...]:
        return (
            record.audit_id,
            record.event_version,
            record.occurred_at,
            record.correlation_id,
            record.action,
            record.outcome,
            record.source_service,
            record.actor_ref,
            record.subject_ref,
            record.tenant_ref,
            record.carrier_ref,
        )

    @staticmethod
    def _replay_matches(row: Tuple[Any, ...], record: GatewayAuditRecord) -> bool:
        """Exact field comparison of a stored row against a replayed record (idempotent-conflict rule)."""
        if str(row[0]).lower() != record.audit_id.lower():
            return False  # defensive: the select is keyed by audit_id
        if int(row[1]) != record.event_version:
            return False
        if not _same_instant(row[2], record.occurred_at):
            return False
        return tuple(row[3:11]) == (
            record.correlation_id,
            record.action,
            record.outcome,
            record.source_service,
            record.actor_ref,
            record.subject_ref,
            record.tenant_ref,
            record.carrier_ref,
        )


# --- W1a: durable Import operational-audit store (dedicated port; ControlStore unchanged) ---

# Caller-bound columns of control_import_audit (DDL 014) in INSERT/SELECT order.
# id and recorded_at are store-assigned and are never bound by the adapter.
_IMPORT_AUDIT_COLUMNS = (
    "audit_id",
    "event_version",
    "occurred_at",
    "correlation_id",
    "action",
    "outcome",
    "source_service",
    "actor_ref",
    "target_ref",
    "source_ref",
)

_IMPORT_AUDIT_INSERT = (
    "INSERT INTO control_import_audit ("
    + ", ".join(_IMPORT_AUDIT_COLUMNS)
    + ") VALUES ("
    + ", ".join(["%s"] * len(_IMPORT_AUDIT_COLUMNS))
    + ") ON CONFLICT (audit_id) DO NOTHING RETURNING id"
)

_IMPORT_AUDIT_SELECT = "SELECT " + ", ".join(_IMPORT_AUDIT_COLUMNS) + " FROM control_import_audit WHERE audit_id = %s"


class PostgresImportAuditStore(ImportAuditStorePort):
    """Durable Import operational-audit adapter (W1a): one idempotent append into control_import_audit.

    A DEDICATED adapter behind ``ImportAuditStorePort`` — deliberately NOT a ``ControlStore`` method (the
    frozen port is unchanged; the DistinctnessLedger / RoutingAudit / GatewayAudit precedent). Same
    conventions as ``PostgresGatewayAuditStore``: lazy-connect (construction performs NO ``psycopg.connect``),
    dual construction (literal ``dsn=`` OR ``secrets=`` + ``ref=`` reference resolution, D-14),
    ``autocommit = False``, commit ONLY on a newly inserted row, rollback-then-reraise on any failure,
    ``release()`` = rollback + close. ``recorded_at`` and ``id`` are assigned by the database (DDL 014) and are
    never bound here. An exact replay of an existing ``audit_id`` is an idempotent no-op
    (``DUPLICATE_MATCH``, nothing committed); a same-ID/different-payload replay fails closed with
    ``ImportAuditConflictError``. Append-only: this adapter contains no UPDATE, DELETE, read, query, export, or
    purge surface. Errors are re-raised unchanged and never wrapped with SQL, descriptor, topology, or row
    content. Uncomposed in production until the W1a Import-audit seam is env-selected.
    """

    def __init__(
        self,
        dsn: Optional[str] = None,
        *,
        secrets: Optional[SecretStore] = None,
        ref: Optional[SecretRef] = None,
    ) -> None:
        # Lazy-connect: record inputs only; NO psycopg.connect here (B7B-D11 convention).
        if (dsn is None) == (ref is None):
            raise ValueError("PostgresImportAuditStore requires exactly one of dsn= or (secrets=, ref=)")
        if ref is not None and secrets is None:
            raise ValueError("PostgresImportAuditStore ref= requires a SecretStore (secrets=)")
        self._dsn = dsn
        self._secrets = secrets
        self._ref = ref
        self._conn_cache: Any = None

    @property
    def _conn(self) -> Any:
        """Lazily open and cache the Control-DB connection (no I/O until first use)."""
        if self._conn_cache is None:
            self._conn_cache = self._open()
        return self._conn_cache

    def _open(self) -> Any:
        """Resolve the Control-DB descriptor (by reference or literal) and open the connection.

        Fail-closed: resolution and connect errors propagate — the append is rejected and no partial
        state is committed. The resolved descriptor is dropped immediately (D-14)."""
        descriptor: Optional[str] = None
        try:
            if self._ref is not None:
                assert self._secrets is not None  # guaranteed by __init__
                descriptor = self._secrets.resolve(self._ref).material  # in-memory only
            else:
                assert self._dsn is not None  # guaranteed by __init__ (exactly one source)
                descriptor = self._dsn
            conn = psycopg.connect(descriptor)
            conn.autocommit = False  # single-INSERT transaction; commit only on a new row
            return conn
        finally:
            descriptor = None  # never retained on the adapter

    def release(self) -> None:
        """Roll back any open transaction and close the cached connection (idempotent)."""
        conn = self._conn_cache
        if conn is None:
            return
        self._conn_cache = None
        try:
            conn.rollback()
        except Exception:
            pass  # broken connection: no transaction survives it
        try:
            conn.close()
        except Exception:
            pass

    def append_import_audit(self, record: ImportAuditRecord) -> ImportAuditAppendResult:
        self._validate(record)
        try:
            with self._conn.cursor() as cur:
                cur.execute(_IMPORT_AUDIT_INSERT, self._params(record))
                inserted = cur.fetchone() is not None
                stored = None
                if not inserted:
                    cur.execute(_IMPORT_AUDIT_SELECT, (record.audit_id,))
                    stored = cur.fetchone()
            if inserted:
                self._conn.commit()  # the ONLY commit: exactly one new durable row
                return ImportAuditAppendResult.INSERTED
            # Replay path: nothing durable to persist — end the transaction WITHOUT committing.
            self._conn.rollback()
            if stored is not None and self._replay_matches(stored, record):
                return ImportAuditAppendResult.DUPLICATE_MATCH
            raise ImportAuditConflictError("import-audit idempotency conflict for a replayed audit_id")
        except (ImportAuditConflictError, ImportAuditInvalidError):
            raise  # bounded errors: transaction already closed above
        except Exception:
            try:
                self._conn.rollback()
            except Exception:
                pass  # connection-level failure: the original error below is the signal
            raise

    @staticmethod
    def _validate(record: ImportAuditRecord) -> None:
        """Bounded pre-insert validation (fail closed BEFORE any durable write)."""
        if record.action not in IMPORT_AUDIT_STORE_ACTIONS:
            raise ImportAuditInvalidError("import-audit record rejected: unknown action")
        if record.event_version <= 0:
            raise ImportAuditInvalidError("import-audit record rejected: non-positive event_version")
        if record.source_service != IMPORT_AUDIT_SOURCE_SERVICE:
            raise ImportAuditInvalidError("import-audit record rejected: unknown source_service")
        for name in ("audit_id", "occurred_at", "correlation_id", "outcome"):
            if not getattr(record, name):
                raise ImportAuditInvalidError("import-audit record rejected: missing required field")

    @staticmethod
    def _params(record: ImportAuditRecord) -> Tuple[Any, ...]:
        return (
            record.audit_id,
            record.event_version,
            record.occurred_at,
            record.correlation_id,
            record.action,
            record.outcome,
            record.source_service,
            record.actor_ref,
            record.target_ref,
            record.source_ref,
        )

    @staticmethod
    def _replay_matches(row: Tuple[Any, ...], record: ImportAuditRecord) -> bool:
        """Exact field comparison of a stored row against a replayed record (idempotent-conflict rule)."""
        if str(row[0]).lower() != record.audit_id.lower():
            return False  # defensive: the select is keyed by audit_id
        if int(row[1]) != record.event_version:
            return False
        if not _same_instant(row[2], record.occurred_at):
            return False
        return tuple(row[3:10]) == (
            record.correlation_id,
            record.action,
            record.outcome,
            record.source_service,
            record.actor_ref,
            record.target_ref,
            record.source_ref,
        )
