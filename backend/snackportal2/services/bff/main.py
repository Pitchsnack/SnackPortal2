"""FastAPI BFF — the single frontend-facing ingress (IC-013).

    python -m snackportal2.services.bff.main
    uvicorn snackportal2.services.bff.main:app --host 127.0.0.1 --port 8000

**This is not a gateway.** Its operation surface is enumerated by contract (IC-013 §16),
every surface is backed by a Pydantic request and response model, and a surface that merely
relayed a downstream body would be a gateway route and is forbidden (§19). It is the only
service that may be a public ingress (§21.1 E-1); every other service sits behind it.

Day 1 establishes the application, the health and readiness surfaces, correlation, and the
composed ingress pipeline. The enumerated business operations arrive with Day 3.1.
"""

from __future__ import annotations

from typing import Optional, cast

import uvicorn
from fastapi import Request

from ...shared.config import load_settings
from ...shared.security import client_bearer
from ...shared.service import build_app
from .clients import build_components
from .pipeline import IngressPipeline
from .ports import AccessControlPort, AuditPort, AuthenticationPort, ControlReadPort, TenantRoutingPort

SERVICE = "bff"

settings = load_settings(SERVICE)

app = build_app(
    SERVICE,
    description=(
        "The single frontend-facing ingress. Application-oriented orchestration with an enumerated operation "
        "surface (IC-013 §16) — not a proxy, not a routing gateway, and not a compatibility shim. It "
        "authenticates through the Authentication Service, validates the tenant carrier, builds the canonical "
        "RequestContext from the signed claim alone, asks the Access Control Service for a decision, routes "
        "through the Database Router, and composes contract-approved DTOs."
    ),
    settings=settings,
)

_components = build_components()

#: The composed request pipeline. Fail-closed by omission: with no service URLs configured
#: nobody authenticates and nothing is authorized.
pipeline = IngressPipeline(
    authentication=cast(AuthenticationPort, _components["authentication"]),
    access_control=cast(AccessControlPort, _components["access_control"]),
    routing=cast(TenantRoutingPort, _components["routing"]),
    audit=cast(AuditPort, _components["audit"]),
    base_domain=cast(str, _components["base_domain"]),
)

#: Control-resident reads (memberships, global directories) used by the enumerated
#: Control-domain operations.
control_read = cast(ControlReadPort, _components["control_read"])


def bearer_credential(request: Request) -> Optional[str]:
    """Extract the client bearer credential from the request.

    Read directly rather than through a FastAPI security dependency so the pipeline sees a
    missing credential and a malformed one identically — both are simply "no credential",
    and both produce the same canonical 401.
    """
    header = request.headers.get("Authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.casefold() != "bearer":
        return None
    return value.strip() or None


# ``client_bearer`` is referenced so the ClientBearer scheme is registered in
# components.securitySchemes even before the first protected route is declared; the
# enumerated operations attach it explicitly (Day 3.1).
_ = client_bearer


if __name__ == "__main__":  # local development convenience — IC-013 §21 permits this block
    uvicorn.run(
        "snackportal2.services.bff.main:app",
        host=settings.host,  # loopback by omission — E-2. Only this service may be PUBLISHED (E-1/E-3).
        port=settings.port,
        reload=settings.reload,  # off by omission; local development only — E-4
        access_log=settings.access_log,
        server_header=settings.server_header,
        proxy_headers=settings.proxy_headers,
    )
