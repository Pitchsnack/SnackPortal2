"""Startup persistence — this service's own tenant-database access (D-48).

Under D-48 a tenant-resident domain service holds the connection it opens, obtained as a
short-lived single-tenant grant from the Database Router. The router remains the sole
authority on *which* database; this module is merely where the socket is opened.

Website handling lives here rather than in the route, because normalization is a property of
what gets stored: two records differing only by a trailing slash or a ``www.`` prefix are the
same company, and the duplicate check below would miss that if the values were stored raw.
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
from ...shared.urls import normalize_website
from .models import TenantStartupRecord

FAMILY = "startups"
TABLE = "startups"

#: Exactly the scalar columns of the accepted tenant DDL 003. The jsonb tag columns
#: (``product_service_tags``, ``market_tags``) are deliberately excluded: flattening a jsonb
#: array into a string would corrupt the shape the DDL guarantees.
COLUMNS = (
    "global_startup_id",
    "company_name",
    "company_type",
    "email",
    "company_url",
    "headquarters_country",
    "headquarters_city",
    "region",
    "year_founded",
    "industry",
    "investment_stage",
    "short_description",
    "product_overview",
)

#: Columns this service will surface. ``email`` is stored by the DDL but never read back into
#: a record here: IC-009 forbids it in the portal shape, and a value that can never lawfully be
#: surfaced is better not carried through the service at all.
READABLE_COLUMNS = tuple(column for column in COLUMNS if column != "email")


def _fields_from_row(row: object) -> Dict[str, Optional[str]]:
    """Map one SELECT row onto the readable column names, preserving nulls as nulls."""
    values = list(row)  # type: ignore[call-overload]
    return {name: (None if values[i + 1] is None else str(values[i + 1])) for i, name in enumerate(READABLE_COLUMNS)}


def _as_year(value: Optional[str]) -> Optional[int]:
    """The stored year as the integer the contract publishes.

    Both storage paths hold this column's value as text — PostgreSQL returns the ``integer``
    column and :func:`_fields_from_row` stringifies it; the in-memory table is typed
    ``Optional[str]`` throughout. The conversion happens once, here, so the record the service
    composes is an integer whichever store produced it.

    Deliberately strict. Silently answering ``None`` for a value that would not parse would
    turn corrupt data into missing data, which is the harder failure to notice.
    """
    return None if value is None else int(value)


def _record_from_fields(tenant_ref: str, identity: str, fields: Mapping[str, Optional[str]]) -> TenantStartupRecord:
    return TenantStartupRecord(
        record_ref=compose_record_ref(tenant_ref, FAMILY, identity),
        global_startup_id=fields.get("global_startup_id"),
        company_name=fields.get("company_name") or "",
        company_type=fields.get("company_type"),
        company_url=fields.get("company_url"),
        headquarters_country=fields.get("headquarters_country"),
        headquarters_city=fields.get("headquarters_city"),
        region=fields.get("region"),
        year_founded=_as_year(fields.get("year_founded")),
        industry=fields.get("industry"),
        investment_stage=fields.get("investment_stage"),
        short_description=fields.get("short_description"),
        product_overview=fields.get("product_overview"),
        lineage_reference=fields.get("lineage_reference"),
    )


class StartupRepository(Protocol):
    """Read and write tenant Startups within exactly one tenant database."""

    def list(self, tenant_ref: str, limit: int) -> List[TenantStartupRecord]:
        ...

    def read(self, tenant_ref: str, record_ref: str) -> Optional[TenantStartupRecord]:
        ...

    def create(self, tenant_ref: str, fields: Mapping[str, Optional[str]]) -> TenantStartupRecord:
        ...

    def update_short_description(self, tenant_ref: str, record_ref: str, value: Optional[str]) -> TenantStartupRecord:
        ...


class InMemoryStartupRepository:
    """Tenant-partitioned in-memory storage for local development and tests."""

    def __init__(self) -> None:
        self._table = InMemoryTenantTable()

    def list(self, tenant_ref: str, limit: int) -> List[TenantStartupRecord]:
        return [_record_from_fields(tenant_ref, identity, fields) for identity, fields in self._table.list(tenant_ref, limit)]

    def read(self, tenant_ref: str, record_ref: str) -> Optional[TenantStartupRecord]:
        identity = parse_record_ref(tenant_ref, FAMILY, record_ref)
        if identity is None:
            return None
        fields = self._table.get(tenant_ref, identity)
        return None if fields is None else _record_from_fields(tenant_ref, identity, fields)

    def create(self, tenant_ref: str, fields: Mapping[str, Optional[str]]) -> TenantStartupRecord:
        identity = self._table.insert(tenant_ref, fields)
        return _record_from_fields(tenant_ref, identity, fields)

    def update_short_description(self, tenant_ref: str, record_ref: str, value: Optional[str]) -> TenantStartupRecord:
        identity = parse_record_ref(tenant_ref, FAMILY, record_ref)
        if identity is None:
            raise not_found()
        updated = self._table.update(tenant_ref, identity, {"short_description": value})
        if updated is None:
            raise not_found()
        return _record_from_fields(tenant_ref, identity, updated)


class PostgresStartupRepository:
    """The tenant database, against the accepted tenant DDL 003.

    A grant is obtained per call and dropped again. Nothing here retains a connection string,
    and the grant object's own ``__repr__`` is redacted so it cannot reach a traceback.
    """

    def __init__(self, grants: GrantProvider) -> None:
        self._grants = grants

    def _connect(self, tenant_ref: str) -> object:
        return open_tenant_connection(self._grants.grant_for(tenant_ref))

    def list(self, tenant_ref: str, limit: int) -> List[TenantStartupRecord]:
        with self._connect(tenant_ref) as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, " + ", ".join(READABLE_COLUMNS) + " FROM " + TABLE + " ORDER BY id LIMIT %s",
                    (limit,),
                )
                rows = cursor.fetchall()
        return [_record_from_fields(tenant_ref, str(row[0]), _fields_from_row(row)) for row in rows]

    def read(self, tenant_ref: str, record_ref: str) -> Optional[TenantStartupRecord]:
        identity = parse_record_ref(tenant_ref, FAMILY, record_ref)
        if identity is None:
            return None
        with self._connect(tenant_ref) as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, " + ", ".join(READABLE_COLUMNS) + " FROM " + TABLE + " WHERE id = %s",
                    (identity,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return _record_from_fields(tenant_ref, str(row[0]), _fields_from_row(row))

    def create(self, tenant_ref: str, fields: Mapping[str, Optional[str]]) -> TenantStartupRecord:
        writable = {name: value for name, value in fields.items() if name in COLUMNS}
        if not writable:
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

    def update_short_description(self, tenant_ref: str, record_ref: str, value: Optional[str]) -> TenantStartupRecord:
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


def find_duplicates(
    repository: StartupRepository, tenant_ref: str, company_name: str, company_url: Optional[str]
) -> List[tuple[TenantStartupRecord, str]]:
    """Find records that may already represent the same company.

    Matching is exact-after-normalization on two axes — name and website — and deliberately
    returns *candidates for a human*, never a decision. A fuzzy score presented as truth is how
    a duplicate check quietly becomes an automatic merge.
    """
    normalized_name = company_name.strip().casefold()
    normalized_url = normalize_website(company_url)

    matches: List[tuple[TenantStartupRecord, str]] = []
    for record in repository.list(tenant_ref, 500):
        if record.company_name.strip().casefold() == normalized_name:
            matches.append((record, "name"))
        elif normalized_url is not None and record.company_url == normalized_url:
            matches.append((record, "website"))
    return matches


__all__ = [
    "COLUMNS",
    "FAMILY",
    "READABLE_COLUMNS",
    "TABLE",
    "InMemoryStartupRepository",
    "PostgresStartupRepository",
    "StartupRepository",
    "find_duplicates",
]
