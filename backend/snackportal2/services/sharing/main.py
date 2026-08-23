"""Sharing Service — independently bootable FastAPI application (IC-013 §21).

    python -m snackportal2.services.sharing.main
    uvicorn snackportal2.services.sharing.main:app --host 127.0.0.1 --port 8008

**Authored but inert.** IC-007 is `Draft / Proposed` and MUST be promoted to `Final` before any
sharing authorization exists (D-46 §6 CONF-6; IC-013 §18; IC-014 §10). Under this revision
cross-tenant access is **denied by default and no positive sharing capability exists.**

The share-proposal surface below is deliberately present and deliberately always refused. An
absent route would be indistinguishable from an unbuilt one; a route that visibly refuses, with
a test asserting the refusal, is a claim the suite can keep honest. When IC-007 is promoted,
whoever implements sharing has to delete a denial rather than remember to add one.

Three invariants that survive whatever IC-007 eventually says:

    Sharing ≠ Ownership          a share never transfers an owner
    Sharing ≠ Tenant Transfer    a share never moves a record between tenants
    Sharing ≠ Deal Duplication   a share never produces a second record
"""

from __future__ import annotations

from typing import List

import uvicorn
from pydantic import BaseModel, Field

from ...shared.config import load_settings
from ...shared.errors import access_denied, error_responses
from ...shared.security import RequestContext, ServiceBearer
from ...shared.service import build_app

SERVICE = "sharing"

settings = load_settings(SERVICE)

app = build_app(
    SERVICE,
    description=(
        "Governed cross-tenant sharing (IC-007). Authored but inert: IC-007 is Draft / Proposed, so "
        "cross-tenant access is denied by default and no positive sharing capability exists. Sharing is "
        "never ownership, never a tenant transfer, and never a duplication."
    ),
    settings=settings,
)


class ShareProposalRequest(BaseModel):
    """A proposal to share a record across a tenant boundary. Always refused under this revision."""

    context: RequestContext = Field(description="The canonical RequestContext naming the single active tenant.")
    source_record_ref: str = Field(min_length=1, max_length=256, description="Reference to the record proposed for sharing.")
    target_ref: str = Field(min_length=1, max_length=256, description="Reference to the proposed share target.")


class SharingCapabilityResponse(BaseModel):
    """What this service can currently do, and what is stopping it doing more."""

    implemented: bool = Field(description="Whether any positive sharing capability exists. False until IC-007 is Final.")
    blocked_on: List[str] = Field(description="The named prerequisites outstanding before sharing may be implemented.")
    invariants: List[str] = Field(description="The invariants any future sharing implementation must preserve, whatever IC-007 settles.")


@app.get(
    "/internal/sharing/capabilities",
    response_model=SharingCapabilityResponse,
    summary="Report sharing capability status",
    description=(
        "Report whether governed sharing is available and which prerequisites remain. IC-007 must be "
        "promoted from Draft / Proposed to Final before any sharing authorization is implemented."
    ),
    tags=["Sharing"],
    operation_id="readSharingCapabilities",
    response_description="The current capability status and its outstanding prerequisites.",
    responses=error_responses(401),
)
async def capabilities(_credential: ServiceBearer) -> SharingCapabilityResponse:
    return SharingCapabilityResponse(
        implemented=False,
        blocked_on=["IC-007 (Deal Collaboration & Cross-Tenant Sharing Contract — Draft / Proposed)"],
        invariants=[
            "Sharing is not ownership: a share never transfers an owner.",
            "Sharing is not a tenant transfer: a share never moves a record between tenants.",
            "Sharing is not duplication: a share never produces a second record.",
        ],
    )


@app.post(
    "/internal/sharing/proposals",
    response_model=SharingCapabilityResponse,
    summary="Propose a governed share",
    description=(
        "Always refused under this revision. IC-007 is Draft / Proposed, so no positive sharing capability "
        "exists and cross-tenant access is denied by default. The surface exists so the refusal is explicit "
        "and testable rather than merely unbuilt: when IC-007 is promoted, sharing is implemented by removing "
        "a denial, not by remembering to add one."
    ),
    tags=["Sharing"],
    operation_id="proposeGovernedShare",
    response_description="Never returned under this revision; the operation always denies.",
    responses=error_responses(401, 403, 422),
)
async def propose_share(request: ShareProposalRequest, _credential: ServiceBearer) -> SharingCapabilityResponse:
    del request
    raise access_denied()


if __name__ == "__main__":  # local development convenience — IC-013 §21 permits this block
    uvicorn.run(
        "snackportal2.services.sharing.main:app",
        host=settings.host,  # loopback by omission — E-2
        port=settings.port,
        reload=settings.reload,  # off by omission; local development only — E-4
        access_log=settings.access_log,
        server_header=settings.server_header,
        proxy_headers=settings.proxy_headers,
    )
