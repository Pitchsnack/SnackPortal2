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
        # 07D-3A-TIER2-CONSTRAINT: NOT safe to share one store instance across concurrent
        # requests/threads. This adapter holds ONE lazily-cached connection per store instance
        # (no pool, no lock, no per-request scoping), and lifecycle CAS writes stay UNCOMMITTED
        # until the transition's audit append commits both — so a second logical writer on the
        # same instance would share this connection's open transaction (cross-request
        # commit/rollback leakage). Separate instances (one store + connection each) are safe:
        # cross-writer races are closed by the version-predicated CAS (PRD 07D-2e).
        # Per-unit-of-work connection/transaction scoping (PRD 07D-3b, AT-PMV46-4) is REQUIRED
        # before any concurrent-request transport is wired over a shared instance; the static
        # guard test_07d3_multiinstance_readiness_static.py pins this marker and fails if it is
        # removed without the 07D-3b rework.
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
            return psycopg.connect(descriptor)
        finally:
            descriptor = None  # never retained on the adapter

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
        with self._conn.cursor() as cur:
            cur.execute(
                """INSERT INTO control_memberships (principal_ref, tenant_id, role)
                   VALUES (%s,%s,%s) ON CONFLICT (principal_ref, tenant_id) DO UPDATE
                   SET role = EXCLUDED.role""",
                (record.principal_ref, record.tenant_id, record.role.value),
            )
        self._conn.commit()

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
        with self._conn.cursor() as cur:
            cur.execute(
                """INSERT INTO control_directory (directory, record_id, display_name, attributes)
                   VALUES (%s,%s,%s,%s)
                   ON CONFLICT (directory, record_id) DO UPDATE SET
                       display_name = EXCLUDED.display_name, attributes = EXCLUDED.attributes""",
                (record.directory.value, record.record_id, record.display_name, dict(record.attributes)),
            )
        self._conn.commit()

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
