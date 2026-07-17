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
from api_gateway.portal import (  # noqa: E402
    DirectoryEntryDTO,
    GlobalInvestorSummaryDTO,
    GlobalStartupSummaryDTO,
    MembershipEntryDTO,
    WorkspaceMembershipDTO,
)
from api_gateway.ports import AuditEmitterPort, AuthenticatorPort, ControlPlaneReadPort, RouterDispatchPort  # noqa: E402
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


class StubControlPlaneRead(ControlPlaneReadPort):
    """A configurable ``ControlPlaneReadPort`` double (B5-BLK-6B) with the exact adapter
    outcome modes:

    * ``"success"``     — returns the configured page/memberships DTOs;
    * ``"empty"``       — returns DTOs carrying EMPTY tuples (a lawful success);
    * ``"absent"``      — returns ``None`` (the adapter's live-404 -> None mapping, LW-1);
    * ``"unavailable"`` — raises OSError (the adapter's transport-failure contract);
    * ``"timeout"``     — raises TimeoutError (the adapter's bounded-timeout contract);
    * ``"malformed"``   — raises ValueError (the adapter's typed-parse failure contract).

    Records every requested directory kind and membership principal so tests can assert
    self-scoping (the gateway must pass ONLY the authenticated principal) and
    call-ordering (denials must never reach the port)."""

    def __init__(
        self,
        mode: str = "success",
        *,
        startup_entries: Sequence[DirectoryEntryDTO] = (),
        investor_entries: Sequence[DirectoryEntryDTO] = (),
        memberships: Sequence[MembershipEntryDTO] = (),
    ) -> None:
        self.mode = mode
        self.directory_kinds: List[str] = []
        self.principals: List[str] = []
        self._startup = tuple(startup_entries)
        self._investor = tuple(investor_entries)
        self._memberships = tuple(memberships)

    def _raise_for_mode(self) -> bool:
        """True when the mode is ``absent`` (return None); raises for the failure modes."""
        if self.mode == "unavailable":
            raise OSError("control-plane read unavailable (stub)")
        if self.mode == "timeout":
            raise TimeoutError("control-plane read timed out (stub)")
        if self.mode == "malformed":
            raise ValueError("malformed control-plane read result (stub)")
        return self.mode == "absent"

    def directory(self, kind: str):
        self.directory_kinds.append(kind)
        if self._raise_for_mode():
            return None
        if kind == "startup":
            return GlobalStartupSummaryDTO(records=self._startup if self.mode == "success" else ())
        if kind == "investor":
            return GlobalInvestorSummaryDTO(records=self._investor if self.mode == "success" else ())
        return None  # unknown/unapproved kind -> the adapter's consistent None

    def memberships_for_principal(self, principal_ref: str) -> Optional[WorkspaceMembershipDTO]:
        self.principals.append(principal_ref)
        if self._raise_for_mode():
            return None
        return WorkspaceMembershipDTO(memberships=self._memberships if self.mode == "success" else ())


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


def control_read_setup(
    control_read: ControlPlaneReadPort,
    *,
    token: str = "tok-ctl",
    principal: str = "ops",
    tenant: Optional[str] = None,
    role: Optional[str] = "CONTROL",
):
    """A gateway with the B5-BLK-6B Control-Plane read seam ACTIVE (a stub or real port
    injected) plus one token. Returns (gateway, authenticator, router, audit)."""
    authn = StubAuthenticator()
    authn.add_token(token, principal=principal, tenant=tenant, role=role)
    router = StubRouterDispatch()
    audit = RecordingAuditEmitter()
    gateway = build_gateway(authenticator=authn, router=router, control_read=control_read, audit=audit)
    return gateway, authn, router, audit
