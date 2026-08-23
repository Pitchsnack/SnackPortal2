"""Import application logic (IC-003) — discrete, idempotent, and never a synchronization.

The shape of an import:

    read the global source by reference   (Control Plane, non-sensitive global reference data)
    write ONE independent tenant record   (this tenant database, carrying a soft source ref)
    write ONE lineage row                 (same tenant database — provenance, IC-004)

All three parts of the write happen in the tenant the signed claim names, and only there. The
global read is a service-internal read of Control-resident reference data; it does not make the
request straddle two database domains, because nothing about the global record is *written*.

**No re-import mechanism exists in this module, by construction.** There is no scheduler, no
timer, no background task, no event subscription and no "refresh" operation — the only entry
point is an explicit, user-initiated call. That is what ``Import ≠ Synchronization`` means in
code rather than in prose.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Protocol

from ...shared.errors import consistent_tenant_denial, not_found
from ...shared.tenant_data import InMemoryTenantTable, compose_record_ref


@dataclass(frozen=True)
class GlobalSourceRecord:
    """A global directory record, as reference data. Tenant-anonymous by construction (D-35)."""

    record_ref: str
    display_name: str
    attributes: Mapping[str, str]


class GlobalDirectoryReadPort(Protocol):
    """Read one global directory record by reference."""

    def read(self, source_ref: str) -> Optional[GlobalSourceRecord]:
        ...


class StaticGlobalDirectory:
    """A fixed global directory for local development and tests."""

    def __init__(self, records: Mapping[str, GlobalSourceRecord]) -> None:
        self._records = dict(records)

    def read(self, source_ref: str) -> Optional[GlobalSourceRecord]:
        return self._records.get(source_ref)


class EmptyGlobalDirectory:
    """The fail-closed default: nothing is importable until a Control Plane is configured."""

    def read(self, source_ref: str) -> Optional[GlobalSourceRecord]:
        del source_ref
        return None


class HttpGlobalDirectory:
    """Read the global directory from the Control Plane over internal HTTP."""

    def __init__(self, base_url: str, credential: str, directory: str = "GlobalStartupDirectory") -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("control plane base url must be an http(s) url")
        self._base_url = base_url.rstrip("/")
        self._credential = credential
        self._directory = directory

    def read(self, source_ref: str) -> Optional[GlobalSourceRecord]:
        import httpx

        try:
            response = httpx.get(
                self._base_url + "/internal/directories/" + self._directory + "/records/" + source_ref,
                headers={"Authorization": "Bearer " + self._credential},
                timeout=5.0,
            )
            if response.status_code != 200:
                return None
            body = response.json()
            return GlobalSourceRecord(
                record_ref=body["record_ref"],
                display_name=body["display_name"],
                attributes={str(k): str(v) for k, v in (body.get("attributes") or {}).items()},
            )
        except Exception:
            return None


def operation_key(tenant_ref: str, source_ref: str) -> str:
    """The idempotency key for one (tenant, source) import.

    Derived, never client-supplied: an import that could choose its own key could choose one
    that has never been used and duplicate a record that already exists.
    """
    digest = hashlib.sha256((tenant_ref + "\x00" + source_ref).encode("utf-8")).hexdigest()
    return "imp-" + digest[:32]


@dataclass(frozen=True)
class ImportRecord:
    """What an import produced, as references."""

    import_id: str
    tenant_record_ref: str
    lineage_ref: str


class ImportStore(Protocol):
    """Persist the tenant copy, its lineage row, and the idempotency record."""

    def find_existing(self, tenant_ref: str, key: str) -> Optional[ImportRecord]:
        ...

    def write_import(self, tenant_ref: str, key: str, source: GlobalSourceRecord) -> ImportRecord:
        ...


class InMemoryImportStore:
    """Tenant-partitioned in-memory import storage for local development and tests.

    Holds three things in the same tenant partition — the startup copy, the lineage row, and the
    idempotency record — because in a real deployment they are three writes to one tenant
    database, and a store that separated them would let the test suite pass while the real
    transaction boundary was wrong.
    """

    def __init__(self) -> None:
        self.startups = InMemoryTenantTable()
        self.lineage = InMemoryTenantTable()
        self._by_key: Dict[tuple[str, str], ImportRecord] = {}

    def find_existing(self, tenant_ref: str, key: str) -> Optional[ImportRecord]:
        return self._by_key.get((tenant_ref, key))

    def write_import(self, tenant_ref: str, key: str, source: GlobalSourceRecord) -> ImportRecord:
        startup_identity = self.startups.insert(
            tenant_ref,
            {
                "global_startup_id": source.record_ref,
                "company_name": source.display_name,
                "industry": source.attributes.get("industry"),
                "headquarters_country": source.attributes.get("headquarters_country"),
            },
        )
        tenant_record_ref = compose_record_ref(tenant_ref, "startups", startup_identity)

        lineage_identity = self.lineage.insert(
            tenant_ref,
            {
                "event_type": "import",
                "operation": "global_startup_import",
                "source_ref": source.record_ref,
                "target_ref": tenant_record_ref,
                "derivation_ref": key,
            },
        )
        lineage_ref = compose_record_ref(tenant_ref, "lineage", lineage_identity)

        record = ImportRecord(import_id=key, tenant_record_ref=tenant_record_ref, lineage_ref=lineage_ref)
        self._by_key[(tenant_ref, key)] = record
        return record


class ImportService:
    """Perform one discrete import. There is no other way to invoke this class."""

    def __init__(self, directory: GlobalDirectoryReadPort, store: ImportStore) -> None:
        self._directory = directory
        self._store = store

    def import_startup(self, tenant_ref: Optional[str], source_ref: str) -> tuple[ImportRecord, bool]:
        """Import one global Startup into one tenant. Returns the record and whether it replayed."""
        if not tenant_ref:
            # A tenantless context has no tenant database to import into.
            raise consistent_tenant_denial()

        key = operation_key(tenant_ref, source_ref)
        existing = self._store.find_existing(tenant_ref, key)
        if existing is not None:
            # The same source into the same tenant. Return the first result rather than making
            # a second copy: a retried request must not duplicate a record.
            return existing, True

        source = self._directory.read(source_ref)
        if source is None:
            raise not_found()

        return self._store.write_import(tenant_ref, key, source), False


__all__ = [
    "EmptyGlobalDirectory",
    "GlobalDirectoryReadPort",
    "GlobalSourceRecord",
    "HttpGlobalDirectory",
    "ImportRecord",
    "ImportService",
    "ImportStore",
    "InMemoryImportStore",
    "StaticGlobalDirectory",
    "operation_key",
]
