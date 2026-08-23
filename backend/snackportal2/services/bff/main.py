"""FastAPI BFF — the single frontend-facing ingress (IC-013).

    python -m snackportal2.services.bff.main
    uvicorn snackportal2.services.bff.main:app --host 127.0.0.1 --port 8000

**This is not a gateway.** Its operation surface is enumerated by contract (IC-013 §16), every
surface is backed by Pydantic request and response models, and a surface that merely relayed a
downstream body would be a gateway route and is forbidden (§19). It is the only service that may
be a public ingress (§21.1 E-1); every other service sits behind it.

It is also, deliberately, the process with the fewest credentials. It holds no database
connection and is permanently off the Database Router's connection-grant allowlist (D-48 C-1):
the process nearest the internet is the one furthest from a credential.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, cast

import uvicorn
from fastapi import Depends

from ...shared.config import load_settings
from ...shared.security import client_bearer
from ...shared.service import build_app
from .clients import build_components
from .operations import build_router
from .pipeline import IngressPipeline
from .ports import AccessControlPort, AuditPort, AuthenticationPort, ControlReadPort, DomainServicePort, TenantRoutingPort

SERVICE = "bff"

settings = load_settings(SERVICE)

app = build_app(
    SERVICE,
    description=(
        "The single frontend-facing ingress. Application-oriented orchestration with an enumerated operation "
        "surface (IC-013 §16) — not a proxy, not a routing gateway, and not a compatibility shim. It "
        "authenticates through the Authentication Service, validates the tenant carrier, builds the canonical "
        "RequestContext from the signed claim alone, asks the Access Control Service for a decision, resolves "
        "exactly one database through the Database Router, invokes the owning service, and composes a "
        "contract-approved DTO."
    ),
    settings=settings,
)

_components: Dict[str, Any] = build_components()

#: The composed request pipeline. Fail-closed by omission: with no service URLs configured
#: nobody authenticates and nothing is authorized.
pipeline = IngressPipeline(
    authentication=cast(AuthenticationPort, _components["authentication"]),
    access_control=cast(AccessControlPort, _components["access_control"]),
    routing=cast(TenantRoutingPort, _components["routing"]),
    audit=cast(AuditPort, _components["audit"]),
    base_domain=cast(str, _components["base_domain"]),
)

#: Control-resident reads (memberships, global directories) for the CONTROL-domain operations.
control_read = cast(ControlReadPort, _components["control_read"])

#: The tenant-resident domain services the TENANT-domain operations orchestrate.
domains = cast(Mapping[str, DomainServicePort], _components["domains"])

# The client bearer scheme is attached at the router so it appears in components.securitySchemes
# and on every enumerated operation. It does not itself enforce: `auto_error=False` means a
# missing credential reaches the pipeline, which raises the canonical 401 rather than FastAPI's.
app.include_router(build_router(pipeline, control_read, domains), dependencies=[Depends(client_bearer)])


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
