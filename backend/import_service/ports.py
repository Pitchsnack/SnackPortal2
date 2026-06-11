"""import_service ports (interfaces). Concrete adapters live under adapters/providers.

- SourceAdapter: yields raw source records (Global Directory / CSV / JSON), normalized to
  a common shape before validation; it never writes tenant data (D-18).
- DirectoryReadPort: transport read of the Control-Plane Global Discovery Platform (D-31);
  no in-process import of control_plane (DAG). Read models are import-local (decoupled).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional

from .models import RawRecord, SourceDescriptor


@dataclass(frozen=True)
class GlobalDirectoryRecordView:
    directory: str
    record_id: str
    display_name: str
    attributes: Dict[str, str]


@dataclass(frozen=True)
class DirectoryPage:
    records: List[GlobalDirectoryRecordView]
    next_cursor: Optional[str]


class DirectoryReadPort(ABC):
    @abstractmethod
    def get_record(self, kind: str, record_id: str) -> Optional[GlobalDirectoryRecordView]: ...

    @abstractmethod
    def page(self, kind: str, cursor: Optional[str], limit: int) -> DirectoryPage: ...


class SourceAdapter(ABC):
    @abstractmethod
    def read(self, descriptor: SourceDescriptor) -> Iterator[RawRecord]:
        """Yield raw source records (origin by reference). MUST NOT write tenant data."""
