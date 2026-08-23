"""Lineage Service — independently bootable FastAPI application (IC-013 §21).

    python -m snackportal2.services.lineage.main
    uvicorn snackportal2.services.lineage.main:app --host 127.0.0.1 --port 8010

Provenance for tenant-resident records (IC-004). Lineage records **where a tenant record came
from**; it does not make the tenant copy track the global record, and reading it never triggers
a re-read of the source. It is append-only: this service exposes no update and no delete, and
the accepted lineage DDL enforces that in the database as well.

Lineage rows are tenant-resident, so they live in the same tenant database as the records they
describe, and are read under the same single-tenant grant (D-48).
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Union

import uvicorn
from pydantic import BaseModel, Field

from ...shared.config import load_settings
from ...shared.errors import consistent_tenant_denial, error_responses, not_found
from ...shared.security import RequestContext, ServiceBearer
from ...shared.service import build_app
from ...shared.tenant_data import (
    GrantProvider,
    InMemoryTenantTable,
    build_grant_provider,
    compose_record_ref,
    open_tenant_connection,
    parse_record_ref,
)

SERVICE = "lineage"
FAMILY = "lineage"
TABLE = "lineage"

ENV_STORAGE = "SP2_LINEAGE_STORAGE"

settings = load_settings(SERVICE)

app = build_app(
    SERVICE,
    description=(
        "Provenance for tenant-resident records (IC-004). Records where a tenant record came from; never "
        "makes it track the source. Append-only: no update and no delete operation exists here. Holds its "
        "own tenant-database connection under a Database Router grant (D-48)."
    ),
    settings=settings,
)


class LineageEntry(BaseModel):
    """One provenance row — references only, never a payload."""

    lineage_ref: str = Field(description="Opaque reference to this lineage row.")
    event_type: str = Field(description="What kind of derivation this was: import, transform, correction, ai-derivation.")
    operation: str = Field(description="The named operation that produced the derivation.")
    source_ref: str = Field(description="Reference to the origin. Never the origin's content.")
    target_ref: str = Field(description="Reference to the affected tenant record, in this tenant database.")
    derivation_ref: Optional[str] = Field(
        default=None, description="Reference to the producing process, such as an import job id."
    )


class LineageListRequest(BaseModel):
    """List provenance rows within exactly one tenant database."""

    context: RequestContext = Field(description="The canonical RequestContext naming the single active tenant.")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum rows to return.")


class LineageForRecordRequest(BaseModel):
    """List the provenance of one tenant record."""

    context: RequestContext = Field(description="The canonical RequestContext naming the single active tenant.")
    target_ref: str = Field(min_length=1, max_length=256, description="Reference to the tenant record whose lineage is read.")


class LineageListResponse(BaseModel):
    """Provenance rows from exactly one tenant database, in deterministic order."""

    tenant_ref: str = Field(description="The single tenant these rows came from.")
    entries: List[LineageEntry] = Field(description="The lineage rows, in deterministic order.")


class LineageRepository:
    """In-memory provenance storage for local development and tests."""

    def __init__(self, table: Optional[InMemoryTenantTable] = None) -> None:
        self.table = table if table is not None else InMemoryTenantTable()

    def list(self, tenant_ref: str, limit: int) -> List[LineageEntry]:
        return [_entry(tenant_ref, identity, fields) for identity, fields in self.table.list(tenant_ref, limit)]

    def for_target(self, tenant_ref: str, target_ref: str) -> List[LineageEntry]:
        return [
            _entry(tenant_ref, identity, fields)
            for identity, fields in self.table.iter_all(tenant_ref)
            if fields.get("target_ref") == target_ref
        ]


class PostgresLineageRepository:
    """The tenant database's lineage schema, read-only."""

    COLUMNS = ("event_type", "operation", "source_ref", "target_ref", "derivation_ref")

    def __init__(self, grants: GrantProvider) -> None:
        self._grants = grants

    def _connect(self, tenant_ref: str) -> object:
        return open_tenant_connection(self._grants.grant_for(tenant_ref))

    def _rows(self, tenant_ref: str, where: str, params: tuple[object, ...], limit: int = 500) -> List[LineageEntry]:
        # ORDER BY seq, not by timestamp: the lineage DDL's seq is the hash-chain order, and it
        # is the only ordering that reflects what actually happened.
        with self._connect(tenant_ref) as connection:  # type: ignore[attr-defined]
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT lineage_id, " + ", ".join(self.COLUMNS) + " FROM " + TABLE + where
                    + " ORDER BY seq LIMIT %s",
                    params + (limit,),
                )
                rows = cursor.fetchall()
        entries: List[LineageEntry] = []
        for row in rows:
            fields: Dict[str, Optional[str]] = {
                name: (None if row[index + 1] is None else str(row[index + 1])) for index, name in enumerate(self.COLUMNS)
            }
            entries.append(_entry(tenant_ref, str(row[0]), fields))
        return entries

    def list(self, tenant_ref: str, limit: int) -> List[LineageEntry]:
        return self._rows(tenant_ref, "", (), limit)

    def for_target(self, tenant_ref: str, target_ref: str) -> List[LineageEntry]:
        return self._rows(tenant_ref, " WHERE target_ref = %s", (target_ref,))


def _entry(tenant_ref: str, identity: str, fields: Dict[str, Optional[str]]) -> LineageEntry:
    return LineageEntry(
        lineage_ref=compose_record_ref(tenant_ref, FAMILY, identity),
        event_type=fields.get("event_type") or "",
        operation=fields.get("operation") or "",
        source_ref=fields.get("source_ref") or "",
        target_ref=fields.get("target_ref") or "",
        derivation_ref=fields.get("derivation_ref"),
    )


def _build_repository() -> Union[LineageRepository, PostgresLineageRepository]:
    if os.environ.get(ENV_STORAGE, "").strip().casefold() == "postgres":
        return PostgresLineageRepository(build_grant_provider(SERVICE))
    return LineageRepository()


_repository = _build_repository()


def _tenant_of(request: Union[LineageListRequest, LineageForRecordRequest]) -> str:
    tenant_ref = request.context.tenant_context
    if not tenant_ref:
        raise consistent_tenant_denial()
    return tenant_ref


@app.post(
    "/internal/lineage/list",
    response_model=LineageListResponse,
    summary="List provenance rows",
    description=(
        "Return provenance rows from the single tenant database named by the signed claim, in "
        "deterministic order. Reading lineage never re-reads a source record and never synchronizes."
    ),
    tags=["Lineage"],
    operation_id="listTenantLineage",
    response_description="Provenance rows from exactly one tenant database.",
    responses=error_responses(401, 404, 409, 422, 503),
)
async def list_lineage(request: LineageListRequest, _credential: ServiceBearer) -> LineageListResponse:
    tenant_ref = _tenant_of(request)
    return LineageListResponse(tenant_ref=tenant_ref, entries=_repository.list(tenant_ref, request.limit))


@app.post(
    "/internal/lineage/for-record",
    response_model=LineageListResponse,
    summary="Read one record's provenance",
    description=(
        "Return the provenance of one tenant record — where it came from and which process derived it. "
        "A target reference minted for a different tenant matches nothing here."
    ),
    tags=["Lineage"],
    operation_id="readTenantRecordLineage",
    response_description="The provenance rows describing the named record.",
    responses=error_responses(401, 404, 409, 422, 503),
)
async def lineage_for_record(request: LineageForRecordRequest, _credential: ServiceBearer) -> LineageListResponse:
    tenant_ref = _tenant_of(request)
    # A target reference is only meaningful within the tenant that minted it; one from another
    # tenant is refused rather than searched for and quietly not found.
    if parse_record_ref(tenant_ref, "startups", request.target_ref) is None:
        if parse_record_ref(tenant_ref, "investors", request.target_ref) is None:
            if parse_record_ref(tenant_ref, "deals", request.target_ref) is None:
                raise not_found()
    return LineageListResponse(tenant_ref=tenant_ref, entries=_repository.for_target(tenant_ref, request.target_ref))


if __name__ == "__main__":  # local development convenience — IC-013 §21 permits this block
    uvicorn.run(
        "snackportal2.services.lineage.main:app",
        host=settings.host,  # loopback by omission — E-2
        port=settings.port,
        reload=settings.reload,  # off by omission; local development only — E-4
        access_log=settings.access_log,
        server_header=settings.server_header,
        proxy_headers=settings.proxy_headers,
    )
