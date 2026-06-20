"""api_gateway ports (interfaces). Concrete adapters live under adapters/providers.

The gateway is an enforcement boundary, not a decision-maker (IC-010 §A). It reaches
the Authenticator (IC-005) and the Database Router over TRANSPORT ports — never an
in-process import of another service (IC-010 §M; DAG independence). It emits audit
events through a port with NO persistence sink (AD-1 Option A).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Sequence

from shared.context import RequestContext

from .models import AuthResult, DispatchDecision, GatewayAuditEvent


class AuthenticatorPort(ABC):
    """IC-005 authentication consumed as INPUT (IC-010 §D). The gateway performs no
    JWT/signature/OIDC validation and issues no token. A recognized carrier is fed into
    the IC-005 carrier-match check; a mismatch is rejected — the only permitted use of a
    carrier (IC-010 §E/§G/§T). Raises ``RequestRejected`` on any denial (fail-closed)."""

    @abstractmethod
    def authenticate(self, authorization: Optional[str], recognized_carriers: Sequence[str], correlation_id: str) -> AuthResult: ...


class RouterDispatchPort(ABC):
    """``Gateway → Database Router`` — the only approved routing boundary (IC-010 §H),
    reached over transport (NO in-process import of database_router). The gateway hands
    the already-resolved RequestContext + a single DispatchDecision; the ROUTER selects
    exactly one database from the signed claim. The gateway never resolves a database
    (IC-010 §X). Live end-to-end routing is D-15-deferred; this seam is exercised against
    a stub."""

    @abstractmethod
    def dispatch(self, context: RequestContext, decision: DispatchDecision) -> None: ...


class AuditEmitterPort(ABC):
    """IC-010 §J emit-set, sink-less port (AD-1 Option A). Records are references only
    (IC-001:94-98). No Control-DB/tenant-DB/file/external persistence; the runtime
    operational-audit class-home remains the pending IC-005/IC-002 extension."""

    @abstractmethod
    def emit(self, event: GatewayAuditEvent) -> None: ...
