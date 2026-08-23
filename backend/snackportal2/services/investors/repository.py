"""Investor persistence — this service's own tenant-database access (D-48).

The jsonb focus columns are the one thing that differs from the Startup repository, and they
are handled rather than avoided. On the PostgreSQL path they are bound with psycopg's ``Jsonb``
wrapper, **not** as a plain ``dict``/``list``: psycopg 3 has no default dumper for those, so a
raw bind raises at the driver layer before any SQL reaches PostgreSQL. That exact defect is on
record against the legacy control-plane adapter (MCC-AR-1); it is not repeated here.
"""

from __future__ import annotations

import json
from typing import List, Mapping, Optional, Protocol

from ...shared.errors import invalid_request, not_found
from ...shared.tenant_data import (
    GrantProvider,
    InMemoryTenantTable,
    compose_record_ref,
    open_tenant_connection,
    parse_record_ref,
)
from ...shared.urls import normalize_website
from .models import TenantInvestorRecord

FAMILY = "investors"
TABLE = "investors"

SCALAR_COLUMNS = (
    "global_investor_id",
    "investor_name",
    "investor_type",
    "website_url",
    "headquarters_country",
    "headquarters_city",
    "region",
    "short_description",
)
JSON_COLUMNS = ("investment_stage_focus", "industry_focus")

#: ``email`` exists in DDL 004 but is never read back into a record: IC-009 forbids it in the
#: portal shape, and a value that can never lawfully be surfaced is better not carried at all.
COLUMNS = SCALAR_COLUMNS + JSON_COLUMNS


def _decode_list(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _record_from_fields(tenant_ref: str, identity: str, fields: Mapping[str, Optional[str]]) -> TenantInvestorRecord:
    return TenantInvestorRecord(
        record_ref=compose_record_ref(tenant_ref, FAMILY, identity),
        global_investor_id=fields.get("global_investor_id"),
        investor_name=fields.get("investor_name") or "",
        investor_type=fields.get("investor_type"),
        website_url=fields.get("website_url"),
        headquarters_country=fields.get("headquarters_country"),
        headquarters_city=fields.get("headquarters_city"),
        region=fields.get("region"),
        investment_stage_focus=_decode_list(fields.get("investment_stage_focus")),
        industry_focus=_decode_list(fields.get("industry_focus")),
        short_description=fields.get("short_description"),
        lineage_reference=fields.get("lineage_reference"),
    )


class InvestorRepository(Protocol):
    """Read and write tenant Investors within exactly one tenant database."""

    def list(self, tenant_ref: str, limit: int) -> List[TenantInvestorRecord]: ...

    def read(self, tenant_ref: str, record_ref: str) -> Optional[TenantInvestorRecord]: ...

    def create(self, tenant_ref: str, fields: Mapping[str, Optional[str]]) -> TenantInvestorRecord: ...

    def update_short_description(self, tenant_ref: str, record_ref: str, value: Optional[str]) -> TenantInvestorRecord: ...


class InMemoryInvestorRepository:
    """Tenant-partitioned in-memory storage for local development and tests."""

    def __init__(self) -> None:
        self._table = InMemoryTenantTable()

    def list(self, tenant_ref: str, limit: int) -> List[TenantInvestorRecord]:
        return [_record_from_fields(tenant_ref, identity, fields) for identity, fields in self._table.list(tenant_ref, limit)]

    def read(self, tenant_ref: str, record_ref: str) -> Optional[TenantInvestorRecord]:
        identity = parse_record_ref(tenant_ref, FAMILY, record_ref)
        if identity is None:
            return None
        fields = self._table.get(tenant_ref, identity)
        return None if fields is None else _record_from_fields(tenant_ref, identity, fields)

    def create(self, tenant_ref: str, fields: Mapping[str, Optional[str]]) -> TenantInvestorRecord:
        identity = self._table.insert(tenant_ref, fields)
        return _record_from_fields(tenant_ref, identity, fields)

    def update_short_description(self, tenant_ref: str, record_ref: str, value: Optional[str]) -> TenantInvestorRecord:
        identity = parse_record_ref(tenant_ref, FAMILY, record_ref)
        if identity is None:
            raise not_found()
        updated = self._table.update(tenant_ref, identity, {"short_description": value})
        if updated is None:
            raise not_found()
        return _record_from_fields(tenant_ref, identity, updated)


class PostgresInvestorRepository:
    """The tenant database, against the accepted tenant DDL 004."""

    def __init__(self, grants: GrantProvider) -> None:
        self._grants = grants

    def _connect(self, tenant_ref: str) -> object:
        return open_tenant_connection(self._grants.grant_for(tenant_ref))

    def _row_to_fields(self, row: object) -> dict[str, Optional[str]]:
        values = list(row)  # type: ignore[call-overload]
        fields: dict[str, Optional[str]] = {}
        for index, name in enumerate(SCALAR_COLUMNS):
            value = values[index + 1]
            fields[name] = None if value is None else str(value)
        for offset, name in enumerate(JSON_COLUMNS):
            value = values[len(SCALAR_COLUMNS) + 1 + offset]
            fields[name] = json.dumps(value or [])
        return fields

    def list(self, tenant_ref: str, limit: int) -> List[TenantInvestorRecord]:
        with self._connect(tenant_ref) as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, " + ", ".join(COLUMNS) + " FROM " + TABLE + " ORDER BY id LIMIT %s",
                    (limit,),
                )
                rows = cursor.fetchall()
        return [_record_from_fields(tenant_ref, str(row[0]), self._row_to_fields(row)) for row in rows]

    def read(self, tenant_ref: str, record_ref: str) -> Optional[TenantInvestorRecord]:
        identity = parse_record_ref(tenant_ref, FAMILY, record_ref)
        if identity is None:
            return None
        with self._connect(tenant_ref) as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute("SELECT id, " + ", ".join(COLUMNS) + " FROM " + TABLE + " WHERE id = %s", (identity,))
                row = cursor.fetchone()
        return None if row is None else _record_from_fields(tenant_ref, str(row[0]), self._row_to_fields(row))

    def create(self, tenant_ref: str, fields: Mapping[str, Optional[str]]) -> TenantInvestorRecord:
        from psycopg.types.json import Jsonb

        writable = {name: value for name, value in fields.items() if name in COLUMNS}
        if not writable:
            raise invalid_request()
        names = sorted(writable)
        # jsonb columns are wrapped; a bare Python list would raise at the driver layer.
        params = tuple(Jsonb(_decode_list(writable[name])) if name in JSON_COLUMNS else writable[name] for name in names)
        with self._connect(tenant_ref) as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO " + TABLE + " (" + ", ".join(names) + ") VALUES (" + ", ".join(["%s"] * len(names)) + ") RETURNING id",
                    params,
                )
                row = cursor.fetchone()
        return _record_from_fields(tenant_ref, str(row[0]) if row else "", fields)

    def update_short_description(self, tenant_ref: str, record_ref: str, value: Optional[str]) -> TenantInvestorRecord:
        identity = parse_record_ref(tenant_ref, FAMILY, record_ref)
        if identity is None:
            raise not_found()
        with self._connect(tenant_ref) as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE " + TABLE + " SET short_description = %s, updated_at = now() WHERE id = %s",
                    (value, identity),
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
    "JSON_COLUMNS",
    "SCALAR_COLUMNS",
    "TABLE",
    "InMemoryInvestorRepository",
    "InvestorRepository",
    "PostgresInvestorRepository",
    "normalize_website",
]
