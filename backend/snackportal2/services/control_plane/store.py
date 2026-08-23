"""Control Plane persistence — the Control database, and only the Control database.

Two adapters behind one port. The in-memory store is the default and is what the tests and
local development run against; the PostgreSQL store targets the accepted Control DDL
(``control_tenants`` 004, ``control_memberships`` 005, ``control_directory`` 007) unchanged,
so the rebuild inherits schemas that have already been reviewed rather than inventing new
ones.

**This service never opens a tenant database.** It holds Control-resident metadata,
including the *reference* by which the Database Router later resolves a tenant database —
but a reference to a secret-store entry is not a connection, and this module has no way to
turn one into a connection.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict, List, Mapping, Optional, Protocol, Tuple

from ...shared.config import db_connect_timeout
from ...shared.types import PlatformRole, TenantLifecycleState
from .models import DirectoryKind, DirectoryRecord, MembershipEntry, SecretReference, TenantDescriptor

#: Control-database DSN. Unset selects the in-memory store.
ENV_CONTROL_DSN = "SP2_CONTROL_PLANE_DSN"

#: Anything that looks like a connection string is refused where a reference is expected.
_DSN_MARKERS = ("://", "password=", "host=", "dbname=", "user=")


def looks_like_a_connection_string(value: str) -> bool:
    """True when a supposed reference is actually credential- or connection-shaped.

    Cheap, and worth it: the single most damaging mistake available in this registry is
    storing a DSN in the field that is contractually a reference (D-14). Refusing at the
    write boundary means it can never be read back out of one.
    """
    folded = value.casefold()
    return any(marker in folded for marker in _DSN_MARKERS)


class ControlStore(Protocol):
    """The Control-database port."""

    def get_tenant(self, tenant_ref: str) -> Optional[TenantDescriptor]:
        ...

    def put_tenant(self, descriptor: TenantDescriptor) -> None:
        ...

    def list_memberships(self, principal_ref: str) -> List[MembershipEntry]:
        ...

    def put_membership(self, principal_ref: str, tenant_ref: str, role: PlatformRole) -> None:
        ...

    def list_directory(self, directory: DirectoryKind) -> List[DirectoryRecord]:
        ...

    def get_directory_record(self, directory: DirectoryKind, record_ref: str) -> Optional[DirectoryRecord]:
        ...


class InMemoryControlStore:
    """Process-local Control store. Deterministic ordering, no clock, no I/O."""

    def __init__(self) -> None:
        self._tenants: Dict[str, TenantDescriptor] = {}
        self._memberships: Dict[Tuple[str, str], PlatformRole] = {}
        self._directory: Dict[Tuple[DirectoryKind, str], DirectoryRecord] = {}

    def get_tenant(self, tenant_ref: str) -> Optional[TenantDescriptor]:
        return self._tenants.get(tenant_ref)

    def put_tenant(self, descriptor: TenantDescriptor) -> None:
        self._tenants[descriptor.tenant_ref] = descriptor

    def list_memberships(self, principal_ref: str) -> List[MembershipEntry]:
        # Sorted, so two instances answer identically and a caller can rely on the order
        # without the store having to promise a natural one (IC-014 §8.4 determinism).
        entries = [
            MembershipEntry(tenant_ref=tenant, role=role)
            for (principal, tenant), role in self._memberships.items()
            if principal == principal_ref
        ]
        return sorted(entries, key=lambda entry: entry.tenant_ref)

    def put_membership(self, principal_ref: str, tenant_ref: str, role: PlatformRole) -> None:
        self._memberships[(principal_ref, tenant_ref)] = role

    def list_directory(self, directory: DirectoryKind) -> List[DirectoryRecord]:
        records = [record for (kind, _), record in self._directory.items() if kind is directory]
        return sorted(records, key=lambda record: record.record_ref)

    def get_directory_record(self, directory: DirectoryKind, record_ref: str) -> Optional[DirectoryRecord]:
        return self._directory.get((directory, record_ref))

    def put_directory_record(self, directory: DirectoryKind, record: DirectoryRecord) -> None:
        self._directory[(directory, record.record_ref)] = record


class PostgresControlStore:
    """The Control database, against the accepted Control DDL.

    Column names and types are exactly those of migrations 004 / 005 / 007. The text typing
    of ``control_tenants`` is deliberate and carried forward: those columns round-trip as
    strings, and changing them to ``timestamptz`` or ``integer`` would silently change what
    the registry returns.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _connect(self) -> object:
        import psycopg

        # Time-bounded: an unreachable Control database must fail rather than block. Left
        # unbounded the driver spends over two minutes before giving up (Stage 4 measurement),
        # which would hold a worker open on every read the registry serves.
        return psycopg.connect(self._dsn, connect_timeout=db_connect_timeout())

    def get_tenant(self, tenant_ref: str) -> Optional[TenantDescriptor]:
        with self._connect() as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT tenant_id, organization_ref, lifecycle_state, expected_schema_version, "
                    "assoc_store_ref, assoc_version FROM control_tenants WHERE tenant_id = %s",
                    (tenant_ref,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return TenantDescriptor(
            tenant_ref=row[0],
            organization_ref=row[1],
            lifecycle_state=TenantLifecycleState(row[2]),
            expected_schema_version=row[3],
            database_association_ref=SecretReference(store_ref=row[4], version=row[5]),
        )

    def put_tenant(self, descriptor: TenantDescriptor) -> None:
        """Upsert one registry row.

        ``created_at`` and ``updated_at`` are ISO-8601 UTC strings, not empty ones. DDL 004
        types them ``text`` rather than ``timestamptz`` so the value round-trips as a string,
        and a ``text NOT NULL`` column accepts ``''`` quite happily — which is precisely why
        the empty write was invisible until a real database held the row. It is server-derived
        here rather than carried on :class:`TenantDescriptor`, because a registry timestamp a
        caller could supply is a registry timestamp a caller could backdate.

        ``created_at`` is deliberately absent from the ``DO UPDATE`` list: an update must not
        restamp when the tenant was first registered. ``updated_at`` is in it, so the two
        columns mean what their names say.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO control_tenants (tenant_id, organization_ref, lifecycle_state, "
                    "expected_schema_version, assoc_store_ref, assoc_version, federation_config_ref, "
                    "created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (tenant_id) DO UPDATE SET organization_ref = EXCLUDED.organization_ref, "
                    "lifecycle_state = EXCLUDED.lifecycle_state, "
                    "expected_schema_version = EXCLUDED.expected_schema_version, "
                    "assoc_store_ref = EXCLUDED.assoc_store_ref, assoc_version = EXCLUDED.assoc_version, "
                    "updated_at = EXCLUDED.updated_at",
                    (
                        descriptor.tenant_ref,
                        descriptor.organization_ref,
                        descriptor.lifecycle_state.value,
                        descriptor.expected_schema_version,
                        descriptor.database_association_ref.store_ref,
                        descriptor.database_association_ref.version,
                        # Federation configuration is a separate contract (DDL 006) that this
                        # service does not yet carry; the column is NOT NULL, so an empty
                        # reference is the honest value for "none recorded".
                        "",
                        now,
                        now,
                    ),
                )

    def list_memberships(self, principal_ref: str) -> List[MembershipEntry]:
        with self._connect() as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT tenant_id, role FROM control_memberships WHERE principal_ref = %s ORDER BY tenant_id",
                    (principal_ref,),
                )
                rows = cursor.fetchall()
        return [MembershipEntry(tenant_ref=row[0], role=PlatformRole(row[1])) for row in rows]

    def put_membership(self, principal_ref: str, tenant_ref: str, role: PlatformRole) -> None:
        with self._connect() as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO control_memberships (principal_ref, tenant_id, role) VALUES (%s, %s, %s) "
                    "ON CONFLICT (principal_ref, tenant_id) DO UPDATE SET role = EXCLUDED.role",
                    (principal_ref, tenant_ref, role.value),
                )

    def list_directory(self, directory: DirectoryKind) -> List[DirectoryRecord]:
        with self._connect() as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT record_id, display_name, attributes FROM control_directory "
                    "WHERE directory = %s ORDER BY record_id",
                    (directory.value,),
                )
                rows = cursor.fetchall()
        return [DirectoryRecord(record_ref=row[0], display_name=row[1], attributes=dict(row[2] or {})) for row in rows]

    def get_directory_record(self, directory: DirectoryKind, record_ref: str) -> Optional[DirectoryRecord]:
        with self._connect() as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT record_id, display_name, attributes FROM control_directory "
                    "WHERE directory = %s AND record_id = %s",
                    (directory.value, record_ref),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return DirectoryRecord(record_ref=row[0], display_name=row[1], attributes=dict(row[2] or {}))


def build_store(env: Optional[Mapping[str, str]] = None) -> ControlStore:
    """Select the Control store from configuration; in-memory when no DSN is set."""
    source: Mapping[str, str] = os.environ if env is None else env
    dsn = source.get(ENV_CONTROL_DSN, "").strip()
    if dsn:
        return PostgresControlStore(dsn)
    return InMemoryControlStore()


__all__ = [
    "ENV_CONTROL_DSN",
    "ControlStore",
    "InMemoryControlStore",
    "PostgresControlStore",
    "build_store",
    "looks_like_a_connection_string",
]
