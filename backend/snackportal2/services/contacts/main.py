"""Contacts Service — independently bootable FastAPI application (IC-013 §21).

    python -m snackportal2.services.contacts.main
    uvicorn snackportal2.services.contacts.main:app --host 127.0.0.1 --port 8011

**This service intentionally exposes no business operation, and that is the finding.**

The 3-day plan (Day 2.4) says: *"If a required Contacts contract is genuinely absent, implement
only behavior already supported by accepted requirements and mark the unresolved contract item
explicitly."* Two things are absent, not one:

1. **IC-015 — Contacts Service Contract is reserved and unauthored** (Action Tracker #26,
   D-46 §6 CONF-7). It is a named prerequisite for Option A Phase 7.
2. **There is no contacts table anywhere in `infrastructure/db`.** The tenant DDL has agents,
   ai_agents, startups, investors, deals, ownership and links — and no contacts.

So there is no accepted requirement describing what a contact *is*: not its field set, not its
residency, not its relationship to agents or to deals, not whether it is tenant-resident at all.
Implementing one would mean inventing a schema and a shape that no contract governs, and every
later contract decision would then have to argue with code that already shipped.

What this service does instead is start, report health, and **disclose the gap** through a
capability surface. That is honest and it is useful: the BFF can ask whether contacts are
available rather than discovering it from a 404, and the disclosure names the blocker.
"""

from __future__ import annotations

from typing import List

import uvicorn
from pydantic import BaseModel, Field

from ...shared.config import load_settings
from ...shared.errors import error_responses
from ...shared.security import ServiceBearer
from ...shared.service import build_app

SERVICE = "contacts"

settings = load_settings(SERVICE)

app = build_app(
    SERVICE,
    description=(
        "Contacts. No business operation is implemented: IC-015 is reserved and unauthored and no contacts "
        "table exists in the accepted DDL, so there is no approved definition of what a contact is. The "
        "service starts, reports health, and discloses the blocking contract gap."
    ),
    settings=settings,
)


class CapabilityResponse(BaseModel):
    """What this service can currently do, and what is stopping it doing more."""

    implemented: bool = Field(description="Whether any business operation is available. False until IC-015 lands.")
    blocked_on: List[str] = Field(description="The named prerequisites that must be satisfied before contact operations can be authored.")
    detail: str = Field(description="Plain statement of the gap, for an operator reading this without the contracts to hand.")


@app.get(
    "/internal/contacts/capabilities",
    response_model=CapabilityResponse,
    summary="Report contact capability status",
    description=(
        "Report whether contact operations are available and, if not, which contract prerequisites are "
        "outstanding. This is the only operation this service exposes: implementing contact behaviour "
        "without IC-015 and without an accepted schema would mean inventing a definition no contract governs."
    ),
    tags=["Contacts"],
    operation_id="readContactsCapabilities",
    response_description="The current capability status and its outstanding prerequisites.",
    responses=error_responses(401),
)
async def capabilities(_credential: ServiceBearer) -> CapabilityResponse:
    return CapabilityResponse(
        implemented=False,
        blocked_on=["IC-015 (Contacts Service Contract — reserved, unauthored)", "tenant contacts DDL (absent)"],
        detail=(
            "No accepted requirement defines a contact's field set, residency, or relationships. "
            "Contact operations are authored only after IC-015 exists and a tenant contacts schema is accepted."
        ),
    )


if __name__ == "__main__":  # local development convenience — IC-013 §21 permits this block
    uvicorn.run(
        "snackportal2.services.contacts.main:app",
        host=settings.host,  # loopback by omission — E-2
        port=settings.port,
        reload=settings.reload,  # off by omission; local development only — E-4
        access_log=settings.access_log,
        server_header=settings.server_header,
        proxy_headers=settings.proxy_headers,
    )
