"""api_gateway composition (Build Phase 7).

Assembles the gateway pipeline from injected ports: the Authenticator (IC-005), the
Database Router transport port, and the audit emitter (AD-1 no-sink default). Tests/dev
inject stubs; production injects transport adapters (under adapters/providers). Liveness
is static and non-disclosing. The gateway resolves no database and imports no other
service (DAG independence).
"""

from __future__ import annotations

from typing import Callable, Optional

from .adapters.providers.in_memory_audit_emitter import InMemoryAuditEmitter
from .dispatch import default_classifier
from .gateway import Gateway
from .models import DispatchCategory, InboundRequest
from .ports import AuditEmitterPort, AuthenticatorPort, RouterDispatchPort
from .readiness import liveness

SERVICE = "api_gateway"

__all__ = ["build_gateway", "liveness", "SERVICE"]


def build_gateway(
    *,
    authenticator: AuthenticatorPort,
    router: RouterDispatchPort,
    classify: Optional[Callable[[InboundRequest], DispatchCategory]] = None,
    audit: Optional[AuditEmitterPort] = None,
) -> Gateway:
    """Compose the gateway. The audit default is the no-sink in-memory emitter (AD-1 A)."""
    return Gateway(
        authenticator=authenticator,
        router=router,
        classify=classify if classify is not None else default_classifier,
        audit=audit if audit is not None else InMemoryAuditEmitter(),
    )
