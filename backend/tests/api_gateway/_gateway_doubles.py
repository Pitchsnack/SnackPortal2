"""Stdlib test doubles + factories for api_gateway behavior tests (no network, no real
auth/DB). The Authenticator (IC-005) and Database Router are stubbed; the audit emitter
records events. Live end-to-end routing is D-15-deferred, so the router stub resolves no
database — it only records the gateway's handoff."""

from __future__ import annotations

import pathlib
import sys
from typing import Dict, List, Optional, Sequence, Tuple

_BACKEND = pathlib.Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from api_gateway.main import build_gateway  # noqa: E402
from api_gateway.models import (  # noqa: E402
    AuthResult,
    DispatchDecision,
    GatewayAuditEvent,
    InboundRequest,
    RouteOutcome,
    carrier_mismatch,
    forbidden,
    unauthenticated,
    unavailable,
)
from api_gateway.ports import AuditEmitterPort, AuthenticatorPort, RouterDispatchPort  # noqa: E402
from shared.context import RequestContext  # noqa: E402


class StubAuthenticator(AuthenticatorPort):
    """An IC-005 authenticator stub: maps a bearer token-ref to (principal, tenant, role),
    enforces carrier match-or-reject against the signed claim, and fails closed. A
    tenantless CONTROL token (tenant=None) ignores the carrier (claim-only)."""

    def __init__(self) -> None:
        self._tokens: Dict[str, Tuple[str, Optional[str], Optional[str]]] = {}
        self._available = True
        self._deny_access = False

    def add_token(self, token: str, *, principal: str, tenant: Optional[str], role: Optional[str] = None) -> None:
        self._tokens[token] = (principal, tenant, role)

    def set_unavailable(self) -> None:
        self._available = False

    def set_deny_access(self) -> None:
        # Models auth_router's consistent denial (unknown tenant / non-member look identical).
        self._deny_access = True

    def authenticate(self, authorization: Optional[str], recognized_carriers: Sequence[str], correlation_id: str) -> AuthResult:
        if not self._available:
            raise unavailable()
        if authorization is None or authorization not in self._tokens:
            raise unauthenticated()
        if self._deny_access:
            raise forbidden("tenant_access_denied")
        principal, tenant, role = self._tokens[authorization]
        if tenant is not None:
            for carrier in recognized_carriers:
                if carrier != tenant:
                    raise carrier_mismatch()
        return AuthResult(correlation_id=correlation_id, principal_ref=principal, active_tenant_id=tenant, role=role)


class StubRouterDispatch(RouterDispatchPort):
    """Records the (context, decision) handoff, then returns the default references-only
    RouteOutcome. Resolves NO database (D-15-deferred)."""

    def __init__(self) -> None:
        self.handoffs: List[Tuple[RequestContext, DispatchDecision]] = []

    def dispatch(self, context: RequestContext, decision: DispatchDecision) -> RouteOutcome:
        self.handoffs.append((context, decision))
        return RouteOutcome(status=200, public_code="ok", dispatched=True)


class RecordingAuditEmitter(AuditEmitterPort):
    def __init__(self) -> None:
        self.events: List[GatewayAuditEvent] = []

    def emit(self, event: GatewayAuditEvent) -> None:
        self.events.append(event)


def req(
    method: str = "GET",
    path: str = "/tenant/x",
    *,
    host: str = "",
    headers: Optional[Dict[str, str]] = None,
    query: Optional[Dict[str, str]] = None,
    cookies: Optional[Dict[str, str]] = None,
    authorization: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> InboundRequest:
    hdrs: Dict[str, str] = dict(headers or {})
    if correlation_id is not None:
        hdrs["X-Correlation-Id"] = correlation_id
    return InboundRequest(
        method=method,
        path=path,
        host=host,
        headers=hdrs,
        query=query or {},
        cookies=cookies or {},
        authorization=authorization,
    )


def tenant_setup(*, token: str = "tok-t1", principal: str = "p1", tenant: str = "t1", role: str = "TENANT_AGENT"):
    """A gateway wired with a StubAuthenticator holding one tenant token. Returns
    (gateway, authenticator, router, audit)."""
    authn = StubAuthenticator()
    authn.add_token(token, principal=principal, tenant=tenant, role=role)
    router = StubRouterDispatch()
    audit = RecordingAuditEmitter()
    gateway = build_gateway(authenticator=authn, router=router, audit=audit)
    return gateway, authn, router, audit
