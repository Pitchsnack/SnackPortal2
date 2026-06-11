"""import_service domain shapes (IC-003) — references only; no credentials/secrets.

The Import Request/Status DTOs are owned by this service (governance E). Source
payloads (CSV/JSON client upload) are import *data*, never credentials; source
credentials (future API-pull adapters) are D-14 references, never inlined here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class ImportMode(Enum):
    ASYNC = "async"
    SYNC = "sync"


class SourceKind(Enum):
    DIRECTORY = "directory"  # Global Startup/Investor Directory (Control DB, D-31)
    CSV = "csv"  # client upload (D-18)
    JSON = "json"  # client upload (D-18)


@dataclass(frozen=True)
class SourceDescriptor:
    kind: SourceKind
    ref: str  # non-sensitive handle/name (for source_ref)
    payload: Optional[str] = None  # CSV/JSON uploaded content (data, never a credential)
    directory_kind: Optional[str] = None  # "startup" | "investor" for DIRECTORY


@dataclass(frozen=True)
class ImportRequest:
    tenant_id: str  # the single active tenant (D-04)
    source: SourceDescriptor
    mode: ImportMode
    operation_key: str  # operation-level idempotency (D-20)
    correlation_id: str
    actor_ref: str  # identity reference, never a token
    natural_key_field: str = "record_id"  # per-record idempotency key (D-20)
    target_table: str = "tenant_copy"


@dataclass(frozen=True)
class RawRecord:
    data: Dict[str, Any]
    source_ref: str  # origin reference — never the payload/credentials


@dataclass(frozen=True)
class ImportRecord:
    natural_key: str
    fields: Dict[str, Any]
    pii_fields: List[str]  # classified PII field names (D-09)
    source_ref: str


@dataclass(frozen=True)
class ImportStatus:
    import_id: str
    tenant_id: str
    state: str  # "applied" | "failed" | "in_progress"
    applied_count: int
    noop_count: int
    rejected_count: int
    last_error_summary: str  # non-sensitive
    correlation_id: str
