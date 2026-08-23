"""Authentication Service — independently bootable FastAPI application (IC-013 §21).

    python -m snackportal2.services.authentication.main
    uvicorn snackportal2.services.authentication.main:app --host 127.0.0.1 --port 8001

This service answers *who are you?* and nothing else. It imports no database driver, opens
no database, evaluates no permission, and selects no tenant.
"""

from __future__ import annotations

import uvicorn

from ...shared.config import load_settings
from ...shared.errors import error_responses, unauthenticated
from ...shared.security import ServiceBearer
from ...shared.service import build_app
from .models import AuthenticationRequest, AuthenticationResponse
from .service import AuthenticationService, InvalidCredential, build_verifier

SERVICE = "authentication"

settings = load_settings(SERVICE)

app = build_app(
    SERVICE,
    description=(
        "Validates an identity credential and returns a trusted principal context (IC-005). "
        "Never authorizes a business action, never chooses a tenant database, and never opens one."
    ),
    settings=settings,
)

# The verifier is resolved once at import. With no trust anchor configured this is the
# deny-all verifier: the service is healthy and authenticates nobody (fail closed).
_service = AuthenticationService(build_verifier())


@app.post(
    "/authenticate",
    response_model=AuthenticationResponse,
    summary="Validate a credential and return the principal context",
    description=(
        "Validate the supplied bearer credential and return the trusted, references-only principal context: "
        "principal reference, platform role, the signed active-tenant claim, and the carrier-match verdict. "
        "The credential is consumed here and is never returned, logged, or audited. An invalid credential "
        "yields 401 with no indication of why it failed."
    ),
    tags=["Authentication"],
    operation_id="authenticatePrincipal",
    response_description="The trusted authenticated identity context and the carrier-match verdict.",
    responses=error_responses(401, 422),
)
async def authenticate(request: AuthenticationRequest, _credential: ServiceBearer) -> AuthenticationResponse:
    """Validate one credential (IC-005). Authorization is IC-014's job, not this route's."""
    try:
        return _service.authenticate(request.credential, request.tenant_carrier)
    except InvalidCredential:
        raise unauthenticated() from None


if __name__ == "__main__":  # local development convenience — IC-013 §21 permits this block
    # The import string (not the app object) is used so that ``reload`` remains usable on a
    # developer machine; uvicorn cannot reload an already-constructed application.
    uvicorn.run(
        "snackportal2.services.authentication.main:app",
        host=settings.host,  # loopback by omission — E-2
        port=settings.port,
        reload=settings.reload,  # off by omission; local development only — E-4
        access_log=settings.access_log,  # secure default off, environment-configurable — E-5
        server_header=settings.server_header,
        proxy_headers=settings.proxy_headers,
    )
