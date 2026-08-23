"""The ingress pipeline — the one approved per-request flow (IC-013 §4).

    Request
      -> Authentication            (Authentication Service, IC-005)
      -> Carrier Validation        (here, §5, match-or-reject)
      -> RequestContext Creation   (here, §7, exclusively from AuthContext)
      -> Access Control            (Access Control Service, IC-014)
      -> Tenant Routing            (Database Router)
      -> Service invocation
      -> Response Composition      (here, §19)

No alternate flow is permitted, and the ordering is not incidental. Carrier validation is
pre-context and pre-routing, so a mismatch is denied before any ``RequestContext`` exists
and before any tenant database is contacted. Access Control runs after context construction
and before routing, so a denied request never causes a tenant-database connection — a
decision made after routing would already have paid the isolation cost it exists to prevent.

This module also holds the BFF's half of the isolation contract (§11): Access Control
*decides* the single lawful domain, and the pipeline *enforces* that exactly one was
decided, refusing to invoke a service when it was not. A decision without enforcement is
advisory; enforcement without a decision is a guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

from ...shared.errors import access_denied, carrier_mismatch, isolation_violation, unauthenticated
from ...shared.operations import BffOperation, domain_of
from ...shared.security import RequestContext
from ...shared.types import DatabaseDomain
from .carrier import recognized_carrier
from .ports import AccessControlPort, AuditPort, AuthenticationPort, CarrierVerdict, TenantRoutingPort

#: The four ingress-edge denial/anomaly classes (IC-013 §10). Unchanged from IC-010 §J:
#: none added, none removed, none renamed. Only the emitter moved.
ACTION_CARRIER_MISMATCH = "CarrierMismatch"
ACTION_CARRIER_ON_CONTROL_ANOMALY = "CarrierOnControlAnomaly"
ACTION_ROUTE_DENIED = "RouteDenied"
ACTION_ISOLATION_ANOMALY = "IsolationAnomaly"

OUTCOME_ALLOWED = "allowed"
OUTCOME_DENIED = "denied"
OUTCOME_ANOMALY = "anomaly"


@dataclass(frozen=True)
class EstablishedContext:
    """A validated request: its canonical context, and the carrier that was observed."""

    context: RequestContext
    carrier_ref: Optional[str]


class IngressPipeline:
    """Runs the approved flow. Owns no business logic and decides no authorization."""

    def __init__(
        self,
        authentication: AuthenticationPort,
        access_control: AccessControlPort,
        routing: TenantRoutingPort,
        audit: AuditPort,
        base_domain: str = "",
    ) -> None:
        self._authentication = authentication
        self._access_control = access_control
        self._routing = routing
        self._audit = audit
        self._base_domain = base_domain

    # --- stages 1-3 ------------------------------------------------------------------

    def establish(
        self,
        credential: Optional[str],
        headers: Mapping[str, str],
        host: str,
        correlation_id: str,
    ) -> EstablishedContext:
        """Authenticate, validate the carrier, and build the canonical context."""
        if not credential:
            raise unauthenticated()

        observation = recognized_carrier(headers, host, self._base_domain)

        result = self._authentication.authenticate(credential, observation.value, correlation_id)
        if result is None:
            raise unauthenticated()

        # Two recognized carriers that disagree is a rejected request, and it is rejected
        # here — after authentication established an actor to attribute the event to, and
        # before any context exists to route with.
        if observation.conflict:
            self._audit.emit(
                action=ACTION_CARRIER_MISMATCH,
                outcome=OUTCOME_DENIED,
                correlation_id=correlation_id,
                actor_ref=result.auth_context.principal_ref,
                tenant_ref=result.auth_context.active_tenant_ref,
            )
            raise carrier_mismatch()

        if result.carrier_verdict is CarrierVerdict.MISMATCH:
            self._audit.emit(
                action=ACTION_CARRIER_MISMATCH,
                outcome=OUTCOME_DENIED,
                correlation_id=correlation_id,
                actor_ref=result.auth_context.principal_ref,
                tenant_ref=result.auth_context.active_tenant_ref,
                carrier_ref=observation.value,
            )
            raise carrier_mismatch()

        if result.carrier_verdict is CarrierVerdict.CONTROL_ANOMALY:
            # A tenantless CONTROL principal arriving with a tenant carrier. The carrier is
            # ignored (claim-only) and the request proceeds — but the anomaly is recorded,
            # because something is addressing Control through a tenant carrier and that is
            # worth knowing (IC-013 §6, D-33-E1 Item 1).
            self._audit.emit(
                action=ACTION_CARRIER_ON_CONTROL_ANOMALY,
                outcome=OUTCOME_ANOMALY,
                correlation_id=correlation_id,
                actor_ref=result.auth_context.principal_ref,
                carrier_ref=observation.value,
            )

        # The single permitted construction site. Nothing from `headers`, `host`, the query
        # string, a cookie, or a body reaches it — the constructor takes one AuthContext and
        # has no parameter through which anything else could arrive (IC-013 §7).
        return EstablishedContext(
            context=RequestContext.from_auth_context(result.auth_context),
            carrier_ref=observation.value,
        )

    # --- stage 4, and the BFF's half of stage 5 ---------------------------------------

    def authorize(
        self,
        context: RequestContext,
        operation: BffOperation,
        record_ref: Optional[str] = None,
    ) -> DatabaseDomain:
        """Ask Access Control, then enforce that exactly one lawful domain was decided."""
        decision = self._access_control.decide(context, operation, record_ref)

        if not decision.allowed:
            self._audit.emit(
                action=ACTION_ROUTE_DENIED,
                outcome=OUTCOME_DENIED,
                correlation_id=context.correlation_id,
                actor_ref=context.principal_ref,
                tenant_ref=context.tenant_context,
                record_ref=record_ref,
            )
            raise access_denied()

        if decision.resolved_domain is None:
            # Allowed without a domain is not a lawful decision. Refusing here is the
            # enforcement half of §11: the BFF will not invoke a service on the strength of
            # an allow that never said where the request may go.
            self._audit.emit(
                action=ACTION_ISOLATION_ANOMALY,
                outcome=OUTCOME_ANOMALY,
                correlation_id=context.correlation_id,
                actor_ref=context.principal_ref,
                tenant_ref=context.tenant_context,
            )
            raise isolation_violation()

        expected = domain_of(operation)
        if decision.resolved_domain is not expected:
            # The decided domain disagrees with the operation's own category. One of the two
            # is wrong, and there is no safe way to pick; both are recorded and the request
            # is refused.
            self._audit.emit(
                action=ACTION_ISOLATION_ANOMALY,
                outcome=OUTCOME_ANOMALY,
                correlation_id=context.correlation_id,
                actor_ref=context.principal_ref,
                tenant_ref=context.tenant_context,
            )
            raise isolation_violation()

        if expected is DatabaseDomain.TENANT and not context.tenant_context:
            self._audit.emit(
                action=ACTION_ISOLATION_ANOMALY,
                outcome=OUTCOME_ANOMALY,
                correlation_id=context.correlation_id,
                actor_ref=context.principal_ref,
            )
            raise isolation_violation()

        return expected

    # --- stage 5: routing -------------------------------------------------------------

    @property
    def routing(self) -> TenantRoutingPort:
        """The router. The BFF hands it a context; it decides which database, never the BFF."""
        return self._routing

    @property
    def audit(self) -> AuditPort:
        """The ingress-edge audit emitter. The BFF is the sole emitter (IC-013 §10)."""
        return self._audit


__all__ = [
    "ACTION_CARRIER_MISMATCH",
    "ACTION_CARRIER_ON_CONTROL_ANOMALY",
    "ACTION_ISOLATION_ANOMALY",
    "ACTION_ROUTE_DENIED",
    "OUTCOME_ALLOWED",
    "OUTCOME_ANOMALY",
    "OUTCOME_DENIED",
    "EstablishedContext",
    "IngressPipeline",
]
