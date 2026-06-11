"""Global Directory source adapter (D-18/D-31) — reads the Control-DB Global Discovery
Platform via the transport DirectoryReadPort and normalizes to RawRecord.

The Global record is read by reference from the Control Database; the import copies it into
the tenant DB (Global Record != Tenant Record). Never writes tenant data; no in-process
import of control_plane.
"""

from __future__ import annotations

from typing import Iterator

from import_service.models import RawRecord, SourceDescriptor
from import_service.ports import DirectoryReadPort, SourceAdapter


class GlobalDirectorySource(SourceAdapter):
    def __init__(self, directory_read: DirectoryReadPort, *, page_size: int = 100) -> None:
        self._read = directory_read
        self._page_size = page_size

    def read(self, descriptor: SourceDescriptor) -> Iterator[RawRecord]:
        kind = descriptor.directory_kind or "startup"
        cursor = None
        while True:
            page = self._read.page(kind, cursor, self._page_size)
            for rec in page.records:
                data = {"record_id": rec.record_id, "display_name": rec.display_name}
                data.update(rec.attributes)
                yield RawRecord(data=data, source_ref=f"global:{rec.directory}:{rec.record_id}")
            if not page.next_cursor:
                break
            cursor = page.next_cursor
