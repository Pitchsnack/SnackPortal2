"""Tenant-database access — the only place in the rebuild that opens a tenant database.

Two adapters behind one port. The in-memory store is the default and backs local
development and the test suite; the PostgreSQL store targets the accepted tenant DDL
(``003_startups``, ``004_investors``, ``005_deals``, and the lineage schema) unchanged.

Three properties keep this from being a generic data proxy:

* the record family is a **closed enum**, so a caller cannot name a table;
* each family carries a **column allowlist** taken from the accepted DDL, so a caller
  cannot name a column either; and
* **no caller supplies SQL** — every statement is built here from the allowlist and bound
  with parameters.

Business meaning stays in the domain services. This module knows that ``startups`` has a
``company_name`` column; it does not know what a startup is, when one may be created, or
who may see it.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Protocol, Sequence, Tuple

from ...shared.errors import invalid_request, not_found, tenant_unavailable
from .models import RecordFamily, TenantRecord


class UnsupportedFamily(Exception):
    """The family has no accepted tenant DDL, so there is nothing to persist it in."""


#: family -> (table, identity column, writable column allowlist)
#: Column sets are exactly those of the accepted tenant DDL. jsonb tag columns
#: (``product_service_tags``, ``market_tags``, ``investment_stage_focus``, ``industry_focus``)
#: are deliberately excluded: this is a scalar-field surface, and silently flattening a jsonb
#: array into a string would corrupt the shape the DDL guarantees.
TENANT_TABLES: Mapping[RecordFamily, Tuple[str, str, Tuple[str, ...]]] = {
    RecordFamily.STARTUPS: (
        "startups",
        "id",
        (
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
        ),
    ),
    RecordFamily.INVESTORS: (
        "investors",
        "id",
        (
            "global_investor_id",
            "investor_name",
            "investor_type",
            "email",
            "website_url",
            "headquarters_country",
            "headquarters_city",
            "region",
            "short_description",
        ),
    ),
    RecordFamily.DEALS: (
        "deals",
        "id",
        ("startup_id", "investor_id", "deal_name", "stage", "amount", "currency", "status"),
    ),
    RecordFamily.LINEAGE: (
        "lineage",
        "lineage_id",
        ("event_type", "occurred_at", "actor_ref", "source_ref", "target_ref", "operation", "schema_version", "derivation_ref"),
    ),
}

#: Families with no accepted tenant DDL. ``contacts`` is one: IC-015 is reserved and
#: unauthored (Action Tracker #26), and there is no contacts table anywhere in
#: ``infrastructure/db``. Persisting it would mean inventing a schema no contract governs,
#: so the PostgreSQL adapter refuses rather than improvising one.
FAMILIES_WITHOUT_DDL = frozenset({RecordFamily.CONTACTS})

#: Families this router will not write to. Lineage is append-only provenance owned by the
#: Lineage Service's own emit path (IC-004); a generic update here could rewrite history.
READ_ONLY_FAMILIES = frozenset({RecordFamily.LINEAGE})


def compose_record_ref(tenant_ref: str, family: RecordFamily, identity: str) -> str:
    """Build the opaque record reference callers see. Never a bare row primary key."""
    return "ref:" + tenant_ref + ":" + family.value + ":" + identity


def parse_record_ref(tenant_ref: str, family: RecordFamily, record_ref: str) -> str:
    """Recover the row identity from a record reference, refusing a mismatched one.

    A reference minted for one tenant or one family cannot be replayed against another:
    the tenant and family are part of the reference and are checked, not merely decorative.
    """
    prefix = "ref:" + tenant_ref + ":" + family.value + ":"
    if not record_ref.startswith(prefix):
        raise not_found()
    identity = record_ref[len(prefix) :]
    if not identity:
        raise not_found()
    return identity


def validate_fields(family: RecordFamily, fields: Mapping[str, Optional[str]]) -> None:
    """Reject any column outside the family's allowlist, with no partial write."""
    table = TENANT_TABLES.get(family)
    if table is None:
        raise UnsupportedFamily(family.value)
    allowed = set(table[2])
    unknown = sorted(set(fields) - allowed)
    if unknown:
        raise invalid_request()


class TenantRecordStore(Protocol):
    """Read and write tenant-resident records within exactly one tenant database.

    ``dsn`` is passed per call rather than held: the resolver produces it for one request
    and this layer forgets it again, so there is no long-lived object anywhere holding a
    tenant credential.
    """

    def list_records(self, tenant_ref: str, family: RecordFamily, limit: int, dsn: str) -> List[TenantRecord]:
        ...

    def read_record(self, tenant_ref: str, family: RecordFamily, record_ref: str, dsn: str) -> Optional[TenantRecord]:
        ...

    def create_record(
        self, tenant_ref: str, family: RecordFamily, fields: Mapping[str, Optional[str]], dsn: str
    ) -> TenantRecord:
        ...

    def update_record(
        self, tenant_ref: str, family: RecordFamily, record_ref: str, fields: Mapping[str, Optional[str]], dsn: str
    ) -> TenantRecord:
        ...


class InMemoryTenantRecordStore:
    """Per-tenant in-memory storage.

    The nesting is the isolation: records live under ``self._data[tenant_ref][family]`` and
    there is no code path that reads two tenant buckets, so a cross-tenant read is not a
    thing this store can be asked to do incorrectly — it is a thing it cannot express.
    """

    def __init__(self) -> None:
        self._data: Dict[str, Dict[RecordFamily, Dict[str, Dict[str, Optional[str]]]]] = {}
        self._counters: Dict[Tuple[str, RecordFamily], int] = {}

    def _bucket(self, tenant_ref: str, family: RecordFamily) -> Dict[str, Dict[str, Optional[str]]]:
        return self._data.setdefault(tenant_ref, {}).setdefault(family, {})

    def list_records(self, tenant_ref: str, family: RecordFamily, limit: int, dsn: str = "") -> List[TenantRecord]:
        del dsn  # in-memory storage has no connection to open
        bucket = self._bucket(tenant_ref, family)
        identities = sorted(bucket, key=lambda identity: (len(identity), identity))[:limit]
        return [
            TenantRecord(record_ref=compose_record_ref(tenant_ref, family, identity), fields=dict(bucket[identity]))
            for identity in identities
        ]

    def read_record(self, tenant_ref: str, family: RecordFamily, record_ref: str, dsn: str = "") -> Optional[TenantRecord]:
        del dsn
        identity = parse_record_ref(tenant_ref, family, record_ref)
        stored = self._bucket(tenant_ref, family).get(identity)
        if stored is None:
            return None
        return TenantRecord(record_ref=record_ref, fields=dict(stored))

    def create_record(
        self, tenant_ref: str, family: RecordFamily, fields: Mapping[str, Optional[str]], dsn: str = ""
    ) -> TenantRecord:
        del dsn
        validate_fields(family, fields)
        key = (tenant_ref, family)
        identity = str(self._counters.get(key, 0) + 1)
        self._counters[key] = int(identity)
        self._bucket(tenant_ref, family)[identity] = dict(fields)
        return TenantRecord(record_ref=compose_record_ref(tenant_ref, family, identity), fields=dict(fields))

    def update_record(
        self, tenant_ref: str, family: RecordFamily, record_ref: str, fields: Mapping[str, Optional[str]], dsn: str = ""
    ) -> TenantRecord:
        del dsn
        validate_fields(family, fields)
        identity = parse_record_ref(tenant_ref, family, record_ref)
        bucket = self._bucket(tenant_ref, family)
        stored = bucket.get(identity)
        if stored is None:
            raise not_found()
        stored.update(fields)
        return TenantRecord(record_ref=record_ref, fields=dict(stored))


class PostgresTenantRecordStore:
    """The tenant database, against the accepted tenant DDL.

    A DSN is supplied per call by the resolver, and is never held, cached, or logged here.
    Every statement is built from the family allowlist; no caller-supplied identifier ever
    reaches SQL.
    """

    def _connect(self, dsn: str) -> object:
        import psycopg

        try:
            return psycopg.connect(dsn)
        except Exception:
            # The tenant database is unreachable. That is an outage of this tenant — never
            # a reason to serve a different one, and never a reason to reach the Control DB.
            raise tenant_unavailable() from None

    @staticmethod
    def _table(family: RecordFamily) -> Tuple[str, str, Tuple[str, ...]]:
        if family in FAMILIES_WITHOUT_DDL:
            raise UnsupportedFamily(family.value)
        table = TENANT_TABLES.get(family)
        if table is None:
            raise UnsupportedFamily(family.value)
        return table

    def _rows_to_records(
        self, tenant_ref: str, family: RecordFamily, identity_column: str, columns: Sequence[str], rows: Sequence[Sequence[object]]
    ) -> List[TenantRecord]:
        records: List[TenantRecord] = []
        for row in rows:
            identity = str(row[0])
            fields = {name: (None if row[index + 1] is None else str(row[index + 1])) for index, name in enumerate(columns)}
            records.append(TenantRecord(record_ref=compose_record_ref(tenant_ref, family, identity), fields=fields))
        del identity_column
        return records

    def list_records(self, tenant_ref: str, family: RecordFamily, limit: int, dsn: str = "") -> List[TenantRecord]:
        table, identity_column, columns = self._table(family)
        with self._connect(dsn) as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT " + identity_column + ", " + ", ".join(columns) + " FROM " + table
                    + " ORDER BY " + identity_column + " LIMIT %s",
                    (limit,),
                )
                rows = cursor.fetchall()
        return self._rows_to_records(tenant_ref, family, identity_column, columns, rows)

    def read_record(self, tenant_ref: str, family: RecordFamily, record_ref: str, dsn: str = "") -> Optional[TenantRecord]:
        table, identity_column, columns = self._table(family)
        identity = parse_record_ref(tenant_ref, family, record_ref)
        with self._connect(dsn) as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT " + identity_column + ", " + ", ".join(columns) + " FROM " + table
                    + " WHERE " + identity_column + " = %s",
                    (identity,),
                )
                rows = cursor.fetchall()
        records = self._rows_to_records(tenant_ref, family, identity_column, columns, rows)
        return records[0] if records else None

    def create_record(
        self, tenant_ref: str, family: RecordFamily, fields: Mapping[str, Optional[str]], dsn: str = ""
    ) -> TenantRecord:
        table, identity_column, _ = self._table(family)
        validate_fields(family, fields)
        names = sorted(fields)
        if not names:
            raise invalid_request()
        placeholders = ", ".join(["%s"] * len(names))
        with self._connect(dsn) as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO " + table + " (" + ", ".join(names) + ") VALUES (" + placeholders + ") "
                    "RETURNING " + identity_column,
                    tuple(fields[name] for name in names),
                )
                row = cursor.fetchone()
        identity = str(row[0]) if row else ""
        return TenantRecord(record_ref=compose_record_ref(tenant_ref, family, identity), fields=dict(fields))

    def update_record(
        self, tenant_ref: str, family: RecordFamily, record_ref: str, fields: Mapping[str, Optional[str]], dsn: str = ""
    ) -> TenantRecord:
        table, identity_column, _ = self._table(family)
        if family in READ_ONLY_FAMILIES:
            raise invalid_request()
        validate_fields(family, fields)
        identity = parse_record_ref(tenant_ref, family, record_ref)
        names = sorted(fields)
        if not names:
            raise invalid_request()
        assignments = ", ".join(name + " = %s" for name in names)
        with self._connect(dsn) as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE " + table + " SET " + assignments + " WHERE " + identity_column + " = %s",
                    tuple(fields[name] for name in names) + (identity,),
                )
                if cursor.rowcount == 0:
                    raise not_found()
        return TenantRecord(record_ref=record_ref, fields=dict(fields))


__all__ = [
    "FAMILIES_WITHOUT_DDL",
    "READ_ONLY_FAMILIES",
    "TENANT_TABLES",
    "InMemoryTenantRecordStore",
    "PostgresTenantRecordStore",
    "TenantRecordStore",
    "UnsupportedFamily",
    "compose_record_ref",
    "parse_record_ref",
    "validate_fields",
]
