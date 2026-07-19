"""Startup directory source adapter (W1a) — the single-record Global→tenant mapping that makes the import real.

Reads exactly ONE Global Startup Directory record by reference (the composed-core import copies a single
referenced global record into the tenant DB — Global Record != Tenant Record) via the transport
``DirectoryReadPort`` and normalizes it to the ``startups`` tenant-table shape. Distinct from
``GlobalDirectorySource`` (which pages the whole directory and yields the raw directory shape
``{record_id, display_name, ...attributes}`` — a shape that never lands on the 07C ``startups`` columns and,
with ``natural_key_field="global_startup_id"``, silently rejects every record): this adapter maps
``record_id -> global_startup_id`` (the natural key / unique arbiter of tenant DDL 008) and
``display_name -> company_name`` (the ``startups`` NOT NULL column), so the upsert writes a real, lawful
tenant row.

Never writes tenant data; no in-process import of ``control_plane`` (DAG). References only: the source
reference is carried, never the payload/credentials.
"""

from __future__ import annotations

from typing import Iterator

from import_service.models import RawRecord, SourceDescriptor
from import_service.ports import DirectoryReadPort, SourceAdapter


class StartupDirectorySource(SourceAdapter):
    def __init__(self, directory_read: DirectoryReadPort) -> None:
        self._read = directory_read

    def read(self, descriptor: SourceDescriptor) -> Iterator[RawRecord]:
        kind = descriptor.directory_kind or "startup"
        rec = self._read.get_record(kind, descriptor.ref)
        if rec is None:
            return  # absent record -> zero-record completion (the gateway maps it to the LW-1 consistent denial)
        yield RawRecord(
            data={"global_startup_id": rec.record_id, "company_name": rec.display_name},
            source_ref=f"global:{rec.directory}:{rec.record_id}",
        )
