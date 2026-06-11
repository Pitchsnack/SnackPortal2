"""Global Discovery Platform (IC-001 / D-31) — Control Database only.

Global Startup / Investor directories. Global Record != Tenant Record. No tenant
copies, no import processing, no synchronization, no lineage. Records carry stable
identifiers for future IC-003 import / IC-004 lineage integration.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .ports import ControlStore
from .records import DirectoryKind, DirectoryRecord


class GlobalDirectory:
    def __init__(self, store: ControlStore) -> None:
        self._store = store

    def add(
        self,
        *,
        directory: DirectoryKind,
        record_id: str,
        display_name: str,
        attributes: Optional[Dict[str, str]] = None,
    ) -> DirectoryRecord:
        record = DirectoryRecord(
            directory=directory,
            record_id=record_id,
            display_name=display_name,
            attributes=dict(attributes or {}),
        )
        self._store.put_directory_record(record)
        return record

    def get(self, directory: DirectoryKind, record_id: str) -> Optional[DirectoryRecord]:
        return self._store.get_directory_record(directory, record_id)

    def list(self, directory: DirectoryKind) -> List[DirectoryRecord]:
        return self._store.list_directory(directory)
