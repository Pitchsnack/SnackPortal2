"""CSV source adapter (D-18) — client-uploaded CSV, normalized to RawRecord.

Pure stdlib (`csv`); portable ingestion only (no provider bulk-load). Yields raw records
with an origin reference; never writes tenant data.
"""
from __future__ import annotations

import csv
import io
from typing import Iterator

from import_service.models import RawRecord, SourceDescriptor
from import_service.ports import SourceAdapter


class CsvSourceAdapter(SourceAdapter):
    def read(self, descriptor: SourceDescriptor) -> Iterator[RawRecord]:
        reader = csv.DictReader(io.StringIO(descriptor.payload or ""))
        for i, row in enumerate(reader):
            yield RawRecord(data=dict(row), source_ref=f"upload:csv:{descriptor.ref}:{i}")
