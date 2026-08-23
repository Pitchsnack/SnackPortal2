"""AI Agent Service — independently bootable FastAPI application (IC-013 §21).

    python -m snackportal2.services.ai_agents.main
    uvicorn snackportal2.services.ai_agents.main:app --host 127.0.0.1 --port 8012

**Inert under this revision, and that is the approved MVP level.**

IC-006 is a `Draft` placeholder whose normative sections are all TBD. IC-013 §18 says the BFF
exposes **no AI behaviour**; IC-014 §9 says `ai.invoke` stays defined and unwired, the
`CONTROL_AI` role stays reserved and unbound, and **IC-006 MUST be authored to Draft-complete
before any AI authorization is implemented** — with the Canonical Overview Part 4B governance
gate (a compliance and permissions review is a prerequisite, not an afterthought) explicitly
**unwaived**. So "the currently approved MVP level" is: no AI operation exists.

What this service does is hold the *shape* the eventual implementation must take, as data and as
refusals, so that the design survives the gap and nobody has to reconstruct it later:

    Research -> AI Draft -> Human Review -> Approved Global Record

with a **duplicate check rerun immediately before approval creates a Global record**, and with
"delete" in this workflow meaning **the AI Draft only** — never an existing Global record.

Three separations are recorded here and are normative whenever this is built:

    AI Skill ≠ Permission          possessing a skill grants nothing
    AI Skill ≠ Tenant Access       an agent's tenant access is evaluated exactly as a human's
    AI Skill ≠ Database Routing    routing stays registry-authoritative from the signed claim

And one absolute: **AI cannot authorize.** An AI agent may not grant, escalate, or delegate a
permission — to itself, to another agent, or to a human (D-38).
"""

from __future__ import annotations

from enum import Enum
from typing import List

import uvicorn
from pydantic import BaseModel, Field

from ...shared.config import load_settings
from ...shared.errors import access_denied, error_responses
from ...shared.security import RequestContext, ServiceBearer
from ...shared.service import build_app

SERVICE = "ai_agents"

settings = load_settings(SERVICE)

app = build_app(
    SERVICE,
    description=(
        "AI Agent Service (IC-006). Inert under this revision: IC-006 is an all-TBD placeholder, ai.invoke "
        "is defined and unwired, the CONTROL_AI role is reserved and unbound, and the Part 4B governance "
        "gate is unwaived. The service records the approved draft lifecycle and refuses every operation."
    ),
    settings=settings,
)


class DraftState(str, Enum):
    """The approved AI draft lifecycle. Recorded now so it cannot be reinvented later.

    Note what is absent: there is no transition from ``RESEARCHED`` straight to ``APPROVED``.
    AI research MUST NOT automatically become an official Global record — a human review stands
    between them, and the duplicate check reruns at the approval boundary.
    """

    RESEARCHED = "researched"
    DRAFTED = "drafted"
    UNDER_HUMAN_REVIEW = "under_human_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class AiGovernanceResponse(BaseModel):
    """What is implemented, what blocks it, and the rules any implementation must preserve."""

    implemented: bool = Field(description="Whether any AI operation is available. False until IC-006 is Draft-complete.")
    blocked_on: List[str] = Field(description="The named prerequisites outstanding before AI behaviour may be built.")
    separations: List[str] = Field(description="The normative separations any AI implementation must preserve.")
    draft_lifecycle: List[DraftState] = Field(description="The approved lifecycle from research to an approved Global record, in order.")
    approval_preconditions: List[str] = Field(description="What must hold before an approval may create a Global record.")


class AiTaskRequest(BaseModel):
    """A structured AI task. Always refused under this revision."""

    context: RequestContext = Field(description="The canonical RequestContext. Consumed as given; never re-derived.")
    skill_ref: str = Field(min_length=1, max_length=128, description="Reference to the agent skill being requested.")
    subject_ref: str = Field(min_length=1, max_length=256, description="Reference to the record or topic the task concerns.")


@app.get(
    "/internal/ai/governance",
    response_model=AiGovernanceResponse,
    summary="Report AI governance status",
    description=(
        "Report whether AI operations are available, which prerequisites remain, and the rules any future "
        "implementation must preserve. This is the only operation this service exposes."
    ),
    tags=["AI Agents"],
    operation_id="readAiGovernanceStatus",
    response_description="The current AI governance status, separations and approved draft lifecycle.",
    responses=error_responses(401),
)
async def governance(_credential: ServiceBearer) -> AiGovernanceResponse:
    return AiGovernanceResponse(
        implemented=False,
        blocked_on=[
            "IC-006 (AI Gateway Contract — Draft, all normative sections TBD)",
            "Canonical Overview Part 4B governance gate (compliance and permissions review) — unwaived",
        ],
        separations=[
            "AI Skill is not Permission: possessing a skill grants nothing.",
            "AI Skill is not Tenant Access: an agent's tenant access is evaluated exactly as a human principal's.",
            "AI Skill is not Database Routing: routing stays registry-authoritative from the signed claim.",
            "AI cannot authorize: an agent may not grant, escalate, or delegate a permission to anyone.",
        ],
        draft_lifecycle=[
            DraftState.RESEARCHED,
            DraftState.DRAFTED,
            DraftState.UNDER_HUMAN_REVIEW,
            DraftState.APPROVED,
        ],
        approval_preconditions=[
            "A human review has occurred; AI research never becomes an official Global record automatically.",
            "The duplicate check is rerun immediately before approval creates a Global record.",
            "On a duplicate, the reviewer either views the existing record and rejects the draft, or "
            "explicitly overrides and creates a new Global record.",
            "'Delete' in this workflow means the AI Draft only, never an existing Global record.",
        ],
    )


@app.post(
    "/internal/ai/tasks",
    response_model=AiGovernanceResponse,
    summary="Submit an AI task",
    description=(
        "Always refused under this revision. IC-006 is an all-TBD placeholder and the Part 4B governance "
        "gate is unwaived, so no AI operation exists. The surface is present so the refusal is explicit and "
        "testable rather than merely unbuilt."
    ),
    tags=["AI Agents"],
    operation_id="submitAiTask",
    response_description="Never returned under this revision; the operation always denies.",
    responses=error_responses(401, 403, 422),
)
async def submit_task(request: AiTaskRequest, _credential: ServiceBearer) -> AiGovernanceResponse:
    del request
    raise access_denied()


if __name__ == "__main__":  # local development convenience — IC-013 §21 permits this block
    uvicorn.run(
        "snackportal2.services.ai_agents.main:app",
        host=settings.host,  # loopback by omission — E-2
        port=settings.port,
        reload=settings.reload,  # off by omission; local development only — E-4
        access_log=settings.access_log,
        server_header=settings.server_header,
        proxy_headers=settings.proxy_headers,
    )
