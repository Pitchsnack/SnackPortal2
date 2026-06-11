"""import_service composition (Build Phase 5).

Wires the import coordinator from injected shared-port providers: the RoutedSessionProvider
(implemented by database_router), the LineageEmitPort (implemented by lineage_service), and a
DirectoryReadPort transport client. No service is imported directly (DAG) — only shared ports
+ this service's own adapters. Liveness is static and non-disclosing.
"""

from __future__ import annotations

from typing import Dict, Optional

from shared.audit import OperationalAudit
from shared.lineage import LineageEmitPort
from shared.session import RoutedSessionProvider

from .adapters.providers.csv_source import CsvSourceAdapter
from .adapters.providers.global_directory_source import GlobalDirectorySource
from .adapters.providers.in_memory_audit_sink import InMemoryAuditSink
from .adapters.providers.json_source import JsonSourceAdapter
from .models import SourceKind
from .ports import DirectoryReadPort
from .service import ImportService

SERVICE = "import_service"


def build_import_service(
    *,
    session_provider: RoutedSessionProvider,
    lineage: LineageEmitPort,
    directory_read: DirectoryReadPort,
    audit: Optional[OperationalAudit] = None,
    batch_size: int = 2,
    schema_version: str = "1",
) -> ImportService:
    sources = {
        SourceKind.DIRECTORY: GlobalDirectorySource(directory_read),
        SourceKind.CSV: CsvSourceAdapter(),
        SourceKind.JSON: JsonSourceAdapter(),
    }
    return ImportService(
        session_provider=session_provider,
        lineage=lineage,
        audit=audit or InMemoryAuditSink(),
        sources=sources,
        schema_version=schema_version,
        batch_size=batch_size,
    )


def liveness() -> Dict[str, str]:
    return {"service": SERVICE, "status": "alive", "build_phase": "5"}
