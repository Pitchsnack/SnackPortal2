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
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

import psycopg  # type: ignore  # noqa: F401  (driver import confined to this zone)

from control_plane.ports import ControlStore
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
from shared.secrets import SecretRef


class PostgresControlStore(ControlStore):
    def __init__(self, dsn: str, schema_version: int = 1) -> None:
        # dsn is a connection descriptor for the CONTROL database (resolved by the
        # composition root via a SecretStore; not retained beyond connection setup).
        self._conn = psycopg.connect(dsn)
        self._schema_version = schema_version

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
                    assoc_store_ref, assoc_version, federation_config_ref, created_at, updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (tenant_id) DO UPDATE SET
                    organization_ref = EXCLUDED.organization_ref,
                    lifecycle_state = EXCLUDED.lifecycle_state,
                    expected_schema_version = EXCLUDED.expected_schema_version,
                    assoc_store_ref = EXCLUDED.assoc_store_ref,
                    assoc_version = EXCLUDED.assoc_version,
                    federation_config_ref = EXCLUDED.federation_config_ref,
                    updated_at = EXCLUDED.updated_at
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
                ),
            )
        self._conn.commit()

    def get_tenant(self, tenant_id: str) -> Optional[TenantRecord]:
        with self._conn.cursor() as cur:
            cur.execute(
                """SELECT tenant_id, organization_ref, lifecycle_state, expected_schema_version,
                          assoc_store_ref, assoc_version, federation_config_ref, created_at, updated_at
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
                    timestamp=r[5],
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
        )
