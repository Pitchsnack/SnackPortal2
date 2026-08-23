"""Audit Service — independently bootable FastAPI application (IC-013 §21).

    python -m snackportal2.services.audit.main
    uvicorn snackportal2.services.audit.main:app --host 127.0.0.1 --port 8013

The durable sink for the BFF's ingress-edge operational audit. The BFF is the sole
*emitter* (IC-013 §10); this service is where what it emits lands, and the only place those
records can be read back.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

import uvicorn
from fastapi import Query

from ...shared.config import load_settings
from ...shared.errors import access_denied, error_responses, unauthenticated
from ...shared.security import ServiceBearer
from ...shared.service import build_app
from .identity import AuditPrincipal, build_credential_directory
from .models import AuditEvent, AuditEventSubmission, AuditReadResponse, AuditWriteAck
from .sink import build_sink

SERVICE = "audit"

settings = load_settings(SERVICE)

app = build_app(
    SERVICE,
    description=(
        "Durable sink for ingress-edge operational audit (IC-013 §10). Every record is references only: no "
        "name, email, PII, business payload, raw row, database identity, DSN, secret, credential, token, or "
        "stack trace. The event id, timestamp and emitting service are server-derived, never submitted."
    ),
    settings=settings,
)

_credentials = build_credential_directory()
_sink = build_sink()


def _principal(credential: str) -> AuditPrincipal:
    """Resolve the presented credential to its derived identity, or fail closed."""
    resolved = _credentials.resolve(credential)
    if resolved is None:
        raise unauthenticated()
    return resolved


TenantFilter = Annotated[
    Optional[str],
    Query(max_length=128, description="Restrict results to one tenant reference. Omit for every tenant in scope."),
]
OnBehalfOf = Annotated[
    Optional[str],
    Query(
        max_length=256,
        description="Read as another principal. Requires the delegation scope AND that principal in the caller's delegable set.",
    ),
]
ReadLimit = Annotated[int, Query(ge=1, le=500, description="Maximum events to return.")]


@app.post(
    "/audit/events",
    response_model=AuditWriteAck,
    status_code=201,
    summary="Record an ingress-edge audit event",
    description=(
        "Append one ingress-edge audit event. The submission carries references, an action and an outcome; "
        "the event id, the UTC timestamp and the emitting service are derived here from the authenticated "
        "credential and this service's own clock. An emitter cannot backdate an event, choose its id, or "
        "attribute its action to another service. Requires the audit:write scope."
    ),
    tags=["Audit"],
    operation_id="recordAuditEvent",
    response_description="The server-generated identifier of the recorded event.",
    responses=error_responses(401, 403, 422),
)
async def record_event(submission: AuditEventSubmission, credential: ServiceBearer) -> AuditWriteAck:
    principal = _principal(credential)
    if not principal.may_write():
        raise access_denied()

    event = AuditEvent(
        event_id=str(uuid.uuid4()),
        occurred_at=datetime.now(timezone.utc).isoformat(),
        source_service=principal.emitter_ref,
        action=submission.action,
        outcome=submission.outcome,
        correlation_id=submission.correlation_id,
        actor_ref=submission.actor_ref,
        subject_ref=submission.subject_ref,
        tenant_ref=submission.tenant_ref,
        record_ref=submission.record_ref,
        carrier_ref=submission.carrier_ref,
    )
    _sink.append(event)
    return AuditWriteAck(event_id=event.event_id, recorded=True)


@app.get(
    "/audit/events",
    response_model=AuditReadResponse,
    summary="Read ingress-edge audit events",
    description=(
        "Read audit events within the caller's own read scope. A caller holding audit:read:all sees every "
        "event; a caller holding only audit:read sees events it is itself the actor of. Reading as another "
        "principal requires the delegation scope and that specific principal in the caller's enumerated "
        "delegable set — a broad delegation scope is never authority to impersonate everyone."
    ),
    tags=["Audit"],
    operation_id="readAuditEvents",
    response_description="Matching audit events and the read scope that was applied.",
    responses=error_responses(401, 403, 422),
)
async def read_events(
    credential: ServiceBearer,
    tenant_ref: TenantFilter = None,
    on_behalf_of: OnBehalfOf = None,
    limit: ReadLimit = 100,
) -> AuditReadResponse:
    principal = _principal(credential)
    if not principal.may_read():
        raise access_denied()

    if on_behalf_of is not None:
        if not principal.may_read_on_behalf_of(on_behalf_of):
            raise access_denied()
        return AuditReadResponse(
            events=_sink.read(tenant_ref, on_behalf_of, limit),
            scope="delegated:" + on_behalf_of,
        )

    if principal.reads_everything():
        return AuditReadResponse(events=_sink.read(tenant_ref, None, limit), scope="audit:read:all")

    # Self-scoped: the caller sees only what it was the actor of.
    return AuditReadResponse(events=_sink.read(tenant_ref, principal.emitter_ref, limit), scope="audit:read")


if __name__ == "__main__":  # local development convenience — IC-013 §21 permits this block
    uvicorn.run(
        "snackportal2.services.audit.main:app",
        host=settings.host,  # loopback by omission — E-2
        port=settings.port,
        reload=settings.reload,  # off by omission; local development only — E-4
        access_log=settings.access_log,
        server_header=settings.server_header,
        proxy_headers=settings.proxy_headers,
    )
