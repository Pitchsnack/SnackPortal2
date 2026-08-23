"""Access Control Service — independently bootable FastAPI application (IC-014 §12).

    python -m snackportal2.services.access_control.main
    uvicorn snackportal2.services.access_control.main:app --host 127.0.0.1 --port 8002

Of every service in the topology this is the most consequential one to expose by mistake:
a directly-reachable authorizer can be asked for a decision no BFF flow ever requested. It
binds loopback by omission (E-2), publishes no port when containerized (E-3), and is
reachable only internally (IC-013 §13).
"""

from __future__ import annotations

import uvicorn

from ...shared.config import load_settings
from ...shared.errors import error_responses
from ...shared.security import ServiceBearer
from ...shared.service import build_app
from .membership import build_membership_port
from .models import AccessDecisionRequest, AccessDecisionResponse
from .policy import Decision, decide

SERVICE = "access_control"

settings = load_settings(SERVICE)

app = build_app(
    SERVICE,
    description=(
        "Evaluates role, permission, tenant membership, requested action and record residency and returns "
        "Allowed or Denied (IC-014). It never authenticates, never selects or opens a database, never "
        "re-derives the active tenant, never reads tenant business data, and never fails open."
    ),
    settings=settings,
)

# Fail-closed by omission: with no membership lookup configured, nobody is a member of
# anything, so every tenant operation is denied.
_memberships = build_membership_port()


@app.post(
    "/decisions",
    response_model=AccessDecisionResponse,
    summary="Evaluate an authorization decision",
    description=(
        "Decide whether the principal described by the supplied RequestContext may perform the named "
        "enumerated operation. Returns Allowed with the single lawful database domain, or Denied with a "
        "canonical code. Deny is the default outcome: any unknown principal, unknown tenant, unknown action, "
        "unknown permission, malformed context, unavailable Control Plane read, timeout, internal error, "
        "ambiguity or unhandled case yields Denied."
    ),
    tags=["Access Control"],
    operation_id="evaluateAccessDecision",
    response_description="The authorization decision and, when allowed, the single resolved database domain.",
    responses=error_responses(401, 422),
)
async def evaluate(request: AccessDecisionRequest, _credential: ServiceBearer) -> AccessDecisionResponse:
    """Return a decision. A denial is a 200 carrying Denied, not an HTTP error.

    The denial is *data* because the BFF must act on it: it has to emit the ``RouteDenied``
    ingress-edge audit event (it is the sole emitter, IC-014 §11) and then return the
    canonical 403 itself. An HTTP error here would conflate "the decision was no" with
    "the authorizer was unreachable" — and those two must never look alike, because one of
    them is also a denial and the other is a denial *plus* an outage.
    """
    outcome = decide(
        request.operation,
        request.context,
        is_member=_memberships.is_member,
        owner_agent_ref=request.owner_agent_ref,
        owner_ai_agent_ref=request.owner_ai_agent_ref,
    )
    if outcome.allowed:
        return AccessDecisionResponse(decision=Decision.ALLOWED, denial_code=None, resolved_domain=outcome.domain)
    return AccessDecisionResponse(decision=Decision.DENIED, denial_code=outcome.code, resolved_domain=None)


if __name__ == "__main__":  # local development convenience — IC-013 §21 permits this block
    uvicorn.run(
        "snackportal2.services.access_control.main:app",
        host=settings.host,  # loopback by omission — E-2
        port=settings.port,
        reload=settings.reload,  # off by omission; local development only — E-4
        access_log=settings.access_log,
        server_header=settings.server_header,
        proxy_headers=settings.proxy_headers,
    )
