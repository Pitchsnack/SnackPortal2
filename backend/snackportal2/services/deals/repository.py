"""Deal persistence — this service's own tenant-database access (D-48).

The party references (``startup_ref``, ``investor_ref``) are verified to belong to the same
tenant before anything is written. That check is the whole cross-tenant defence at this layer:
a deal is the one record type that names two other records, so it is the one place where a
reference minted elsewhere could otherwise smuggle a second tenant into a single request.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Protocol

from ...shared.errors import invalid_request, not_found
from ...shared.tenant_data import (
    GrantProvider,
    InMemoryTenantTable,
    compose_record_ref,
    open_tenant_connection,
    parse_record_ref,
)
from .models import DealStatus, TenantDealRecord

FAMILY = "deals"
TABLE = "deals"
COLUMNS = ("startup_id", "investor_id", "deal_name", "stage", "amount", "currency", "status")


def resolve_party(tenant_ref: str, family: str, record_ref: Optional[str]) -> Optional[str]:
    """Turn a party reference into a row identity, refusing one from another tenant or family.

    Returns ``None`` only for an absent optional party. A *present* reference that does not
    belong to this tenant and family is rejected outright — never silently ignored, which would
    quietly create an unmatched deal instead of failing the request that tried to cross tenants.
    """
    if record_ref is None:
        return None
    identity = parse_record_ref(tenant_ref, family, record_ref)
    if identity is None:
        raise invalid_request()
    return identity


def _record_from_fields(tenant_ref: str, identity: str, fields: Mapping[str, Optional[str]]) -> TenantDealRecord:
    raw_status = fields.get("status")
    startup_identity = fields.get("startup_id") or ""
    investor_identity = fields.get("investor_id")
    known_status = raw_status in {member.value for member in DealStatus}
    return TenantDealRecord(
        record_ref=compose_record_ref(tenant_ref, FAMILY, identity),
        deal_name=fields.get("deal_name") or "",
        startup_ref=compose_record_ref(tenant_ref, "startups", startup_identity),
        investor_ref=compose_record_ref(tenant_ref, "investors", investor_identity) if investor_identity else None,
        stage=fields.get("stage"),
        amount=fields.get("amount"),
        currency=fields.get("currency"),
        status=DealStatus(raw_status) if known_status and raw_status is not None else None,
    )


class DealRepository(Protocol):
    """Read and write tenant Deals within exactly one tenant database."""

    def list(self, tenant_ref: str, limit: int) -> List[TenantDealRecord]:
        ...

    def read(self, tenant_ref: str, record_ref: str) -> Optional[TenantDealRecord]:
        ...

    def create(self, tenant_ref: str, fields: Mapping[str, Optional[str]]) -> TenantDealRecord:
        ...

    def update(self, tenant_ref: str, record_ref: str, fields: Mapping[str, Optional[str]]) -> TenantDealRecord:
        ...


class InMemoryDealRepository:
    """Tenant-partitioned in-memory storage for local development and tests."""

    def __init__(self) -> None:
        self._table = InMemoryTenantTable()

    def list(self, tenant_ref: str, limit: int) -> List[TenantDealRecord]:
        return [_record_from_fields(tenant_ref, identity, fields) for identity, fields in self._table.list(tenant_ref, limit)]

    def read(self, tenant_ref: str, record_ref: str) -> Optional[TenantDealRecord]:
        identity = parse_record_ref(tenant_ref, FAMILY, record_ref)
        if identity is None:
            return None
        fields = self._table.get(tenant_ref, identity)
        return None if fields is None else _record_from_fields(tenant_ref, identity, fields)

    def create(self, tenant_ref: str, fields: Mapping[str, Optional[str]]) -> TenantDealRecord:
        identity = self._table.insert(tenant_ref, fields)
        return _record_from_fields(tenant_ref, identity, fields)

    def update(self, tenant_ref: str, record_ref: str, fields: Mapping[str, Optional[str]]) -> TenantDealRecord:
        identity = parse_record_ref(tenant_ref, FAMILY, record_ref)
        if identity is None:
            raise not_found()
        present = {name: value for name, value in fields.items() if value is not None}
        updated = self._table.update(tenant_ref, identity, present)
        if updated is None:
            raise not_found()
        return _record_from_fields(tenant_ref, identity, updated)


class PostgresDealRepository:
    """The tenant database, against the accepted tenant DDL 005."""

    def __init__(self, grants: GrantProvider) -> None:
        self._grants = grants

    def _connect(self, tenant_ref: str) -> object:
        return open_tenant_connection(self._grants.grant_for(tenant_ref))

    @staticmethod
    def _fields(row: object) -> Dict[str, Optional[str]]:
        values = list(row)  # type: ignore[call-overload]
        return {name: (None if values[i + 1] is None else str(values[i + 1])) for i, name in enumerate(COLUMNS)}

    def list(self, tenant_ref: str, limit: int) -> List[TenantDealRecord]:
        with self._connect(tenant_ref) as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, " + ", ".join(COLUMNS) + " FROM " + TABLE + " ORDER BY id LIMIT %s", (limit,)
                )
                rows = cursor.fetchall()
        return [_record_from_fields(tenant_ref, str(row[0]), self._fields(row)) for row in rows]

    def read(self, tenant_ref: str, record_ref: str) -> Optional[TenantDealRecord]:
        identity = parse_record_ref(tenant_ref, FAMILY, record_ref)
        if identity is None:
            return None
        with self._connect(tenant_ref) as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute("SELECT id, " + ", ".join(COLUMNS) + " FROM " + TABLE + " WHERE id = %s", (identity,))
                row = cursor.fetchone()
        return None if row is None else _record_from_fields(tenant_ref, str(row[0]), self._fields(row))

    def create(self, tenant_ref: str, fields: Mapping[str, Optional[str]]) -> TenantDealRecord:
        writable = {name: value for name, value in fields.items() if name in COLUMNS}
        if not writable.get("startup_id"):
            raise invalid_request()
        names = sorted(writable)
        with self._connect(tenant_ref) as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO " + TABLE + " (" + ", ".join(names) + ") VALUES ("
                    + ", ".join(["%s"] * len(names)) + ") RETURNING id",
                    tuple(writable[name] for name in names),
                )
                row = cursor.fetchone()
        return _record_from_fields(tenant_ref, str(row[0]) if row else "", fields)

    def update(self, tenant_ref: str, record_ref: str, fields: Mapping[str, Optional[str]]) -> TenantDealRecord:
        identity = parse_record_ref(tenant_ref, FAMILY, record_ref)
        if identity is None:
            raise not_found()
        mutable = ("stage", "status")
        writable = {name: value for name, value in fields.items() if name in mutable and value is not None}
        if not writable:
            raise invalid_request()
        names = sorted(writable)
        assignments = ", ".join(name + " = %s" for name in names)
        with self._connect(tenant_ref) as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE " + TABLE + " SET " + assignments + ", updated_at = now() WHERE id = %s",
                    tuple(writable[name] for name in names) + (identity,),
                )
                if cursor.rowcount == 0:
                    raise not_found()
        read_back = self.read(tenant_ref, record_ref)
        if read_back is None:
            raise not_found()
        return read_back


__all__ = [
    "COLUMNS",
    "FAMILY",
    "TABLE",
    "DealRepository",
    "InMemoryDealRepository",
    "PostgresDealRepository",
    "resolve_party",
]
