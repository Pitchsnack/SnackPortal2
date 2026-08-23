"""Import Service — independently bootable FastAPI application (IC-013 §21).

    python -m snackportal2.services.import_service.main
    uvicorn snackportal2.services.import_service.main:app --host 127.0.0.1 --port 8009

One operation, deliberately. **Import ≠ Synchronization**: there is exactly one entry point,
it is explicit and user-initiated, and this module contains no scheduler, timer, background
task, event subscription, or refresh operation through which a re-import could ever be
triggered (D-34, IC-013 §15).
"""

from __future__ import annotations

import os
from typing import Mapping, Optional

import uvicorn

from ...shared.config import load_settings
from ...shared.errors import error_responses
from ...shared.lineage_keys import build_lineage_key_resolver
from ...shared.security import ServiceBearer
from ...shared.service import build_app
from ...shared.tenant_data import build_grant_provider
from .models import ImportInitiationRequest, ImportOutcome, ImportResult
from .service import (
    EmptyGlobalDirectory,
    GlobalDirectoryReadPort,
    HttpGlobalDirectory,
    ImportService,
    ImportStore,
    InMemoryImportStore,
)
from .store import PostgresImportStore

SERVICE = "import_service"

ENV_CONTROL_PLANE_URL = "SP2_IMPORT_SERVICE_CONTROL_PLANE_URL"
ENV_SERVICE_CREDENTIAL = "SP2_IMPORT_SERVICE_SERVICE_CREDENTIAL"

#: Storage mode. Explicit, because a silent fallback from PostgreSQL to in-memory would turn a
#: database outage into an import that reports success and writes nothing — which is exactly
#: the gap Stage 4 recorded as blocker B-1.
ENV_STORAGE = "SP2_IMPORT_SERVICE_STORAGE"

settings = load_settings(SERVICE)

app = build_app(
    SERVICE,
    description=(
        "Discrete, user-initiated Global to Tenant import (IC-003). Produces an independent tenant copy "
        "carrying a soft reference to its global source, plus one lineage row recording the derivation. "
        "Import is never synchronization: no scheduled, background, event-triggered or timer-driven "
        "re-import exists."
    ),
    settings=settings,
)


def _build_directory(env: Optional[Mapping[str, str]] = None) -> GlobalDirectoryReadPort:
    source: Mapping[str, str] = os.environ if env is None else env
    url = source.get(ENV_CONTROL_PLANE_URL, "").strip()
    credential = source.get(ENV_SERVICE_CREDENTIAL, "").strip()
    if url and credential:
        return HttpGlobalDirectory(url, credential)
    return EmptyGlobalDirectory()


def _build_store(env: Optional[Mapping[str, str]] = None) -> ImportStore:
    """Select the import store from configuration, in-memory by omission.

    The PostgreSQL store needs two things the in-memory one does not: a Database Router grant
    provider (D-48 — the router still decides *which* database) and a per-tenant lineage chain
    key resolver (D-23). Both are composed here and both fail closed on their own, so a
    half-configured deployment cannot write a tenant record without provenance.
    """
    source: Mapping[str, str] = os.environ if env is None else env
    if source.get(ENV_STORAGE, "").strip().casefold() == "postgres":
        return PostgresImportStore(build_grant_provider(SERVICE), build_lineage_key_resolver())
    return InMemoryImportStore()


_store = _build_store()
_service = ImportService(_build_directory(), _store)


@app.post(
    "/internal/import/startup",
    response_model=ImportResult,
    status_code=201,
    summary="Import a global Startup into the active tenant",
    description=(
        "Copy one global directory Startup into the single tenant database named by the signed claim, "
        "producing an independent tenant record with a soft reference to its source and one lineage row "
        "recording the derivation (IC-003, IC-004). The operation is idempotent per (tenant, source): a "
        "repeat returns the first result with outcome 'replayed' rather than making a second copy, so a "
        "retried request cannot duplicate a record. Nothing here links, subscribes, mirrors, or re-reads "
        "the global record afterwards."
    ),
    tags=["Import"],
    operation_id="importGlobalStartup",
    response_description="The completion envelope: source, target tenant, record, lineage, job id and outcome.",
    responses=error_responses(401, 404, 409, 422, 503),
)
async def import_startup(request: ImportInitiationRequest, _credential: ServiceBearer) -> ImportResult:
    record, replayed = _service.import_startup(request.context, request.source_ref)
    return ImportResult(
        source_ref=request.source_ref,
        target_tenant_ref=request.context.tenant_context or "",
        tenant_record_ref=record.tenant_record_ref,
        lineage_ref=record.lineage_ref,
        import_id=record.import_id,
        outcome=ImportOutcome.REPLAYED if replayed else ImportOutcome.CREATED,
    )


if __name__ == "__main__":  # local development convenience — IC-013 §21 permits this block
    uvicorn.run(
        "snackportal2.services.import_service.main:app",
        host=settings.host,  # loopback by omission — E-2
        port=settings.port,
        reload=settings.reload,  # off by omission; local development only — E-4
        access_log=settings.access_log,
        server_header=settings.server_header,
        proxy_headers=settings.proxy_headers,
    )
