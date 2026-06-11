"""JSON source adapter (D-18) — client-uploaded JSON array/object, normalized to RawRecord.

Pure stdlib (`json`); portable ingestion only. Yields raw records with an origin
reference; never writes tenant data.
"""
from __future__ import annotations

import json
from typing import Iterator

from import_service.models import RawRecord, SourceDescriptor
from import_service.ports import SourceAdapter


class JsonSourceAdapter(SourceAdapter):
    def read(self, descriptor: SourceDescriptor) -> Iterator[RawRecord]:
        payload = json.loads(descriptor.payload or "[]")
        if isinstance(payload, dict):
            payload = [payload]
        for i, obj in enumerate(payload):
            yield RawRecord(data=dict(obj), source_ref=f"upload:json:{descriptor.ref}:{i}")
