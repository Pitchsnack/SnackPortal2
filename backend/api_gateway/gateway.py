"""The API Gateway request pipeline (IC-010 §A/§C) — Build Phase 7.

The single approved per-request flow: Authentication → Carrier Validation → RequestContext
(constructed exclusively from AuthContext) → Database Router → Response. An enforcement
boundary, not a decision-maker: it never resolves a database, decides ownership, or runs
business logic. Fail-closed (§L); one request → one active tenant → one database (§K/§O);
emits the §J audit set once per anomaly through a no-sink port (AD-1 Option A; single edge
emission). Framework-agnostic core — no web framework dependency.
"""

from __future__ import annotations

import time
import uuid
from typing import Callable, Optional, Set, Tuple

from shared.context import RequestContext

from .carrier import opaque_carrier_ref, recognized_carriers
from .dispatch import DispatchError, assert_single_database, decide
from .models import (
    AuditAction,
    DispatchCategory,
    GatewayAuditEvent,
    GatewayResponse,
    InboundRequest,
    RequestMetric,
    RequestRejected,
)
from .ports import AuditEmitterPort, AuthenticatorPort, MetricsPort, RouterDispatchPort
from .request_context import build_request_context

_CORRELATION_HEADER = "x-correlation-id"


class Gateway:
    """The composed gateway pipeline. Ports are injected (tests/dev stubs; prod transport)."""

    def __init__(
        self,
        *,
        authenticator: AuthenticatorPort,
        router: RouterDispatchPort,
        classify: Callable[[InboundRequest], DispatchCategory],
        audit: AuditEmitterPort,
        metrics: MetricsPort,
    ) -> None:
        self._authenticator = authenticator
        self._router = router
        self._classify = classify
        self._audit = audit
        self._metrics = metrics

    def handle(self, request: InboundRequest) -> GatewayResponse:
        # Observability (§S/WP-11): time every request and record a non-disclosing metric
        # (operational labels only — never a tenant identity/count, DB name, or topology).
        start = time.monotonic()
        response = self._handle(request)
        self._metrics.record_request(
            RequestMetric(
                category=response.category.value if response.category is not None else None,
                outcome=response.public_code,
                status=response.status,
                duration_ms=(time.monotonic() - start) * 1000.0,
            )
        )
        return response

    def _handle(self, request: InboundRequest) -> GatewayResponse:
        correlation_id = self._correlation_id(request)
        emitted: Set[Tuple[AuditAction, str]] = set()  # per-request dedup: single edge emission per anomaly

        def emit(
            action: AuditAction,
            outcome: str,
            *,
            actor_ref: Optional[str] = None,
            tenant_ref: Optional[str] = None,
            carrier_ref: Optional[str] = None,
        ) -> None:
            key = (action, correlation_id)
            if key in emitted:  # idempotent: the same correlation-bound event is emitted at most once
                return
            emitted.add(key)
            self._audit.emit(
                GatewayAuditEvent(
                    action=action,
                    correlation_id=correlation_id,
                    outcome=outcome,
                    actor_ref=actor_ref,
                    tenant_ref=tenant_ref,
                    carrier_ref=carrier_ref,
                )
            )

        carriers = recognized_carriers(request)

        # Isolation (§K): one request asserting >1 distinct tenant carrier is a straddle
        # attempt (e.g. a MASTER_AGENT fan-out across t1/t2) — reject + audit, fail-closed.
        if len(set(carriers)) > 1:
            emit(AuditAction.ISOLATION_ANOMALY, "rejected", carrier_ref=opaque_carrier_ref(",".join(sorted(set(carriers)))))
            return GatewayResponse(status=403, public_code="isolation_anomaly")

        # Authentication (§D): consumed as input; the recognized carrier is fed into the
        # IC-005 carrier-match check inside the authenticator (the only permitted carrier use).
        try:
            auth = self._authenticator.authenticate(request.authorization, carriers, correlation_id)
        except RequestRejected as rejected:
            action = AuditAction.CARRIER_MISMATCH if rejected.public_code == "carrier_mismatch" else AuditAction.ROUTE_DENIED
            emit(action, "rejected")
            return GatewayResponse(status=rejected.http_status, public_code=rejected.public_code)

        # §F: a recognized carrier on a tenantless CONTROL token is ignored (claim-only) and
        # MUST emit the mandatory CarrierOnControlAnomaly (references only, opaque carrier id).
        if auth.active_tenant_id is None and carriers:
            emit(
                AuditAction.CARRIER_ON_CONTROL_ANOMALY,
                "observed",
                actor_ref=auth.principal_ref,
                carrier_ref=opaque_carrier_ref(carriers[0]),
            )

        # RequestContext is constructed EXCLUSIVELY from AuthContext (§G/§T; load-bearing).
        context: RequestContext = build_request_context(auth)

        # Endpoint dispatch by path/operation only (§X/§Q); one request → one category → one DB (§K).
        try:
            category = self._classify(request)
            decision = decide(category, context)
            assert_single_database(decision)
        except DispatchError as denied:
            if denied.isolation_anomaly:
                emit(AuditAction.ISOLATION_ANOMALY, "rejected", actor_ref=auth.principal_ref, tenant_ref=context.active_tenant_id)
                return GatewayResponse(status=403, public_code="isolation_anomaly")
            emit(AuditAction.ROUTE_DENIED, "rejected", actor_ref=auth.principal_ref, tenant_ref=context.active_tenant_id)
            return GatewayResponse(status=403, public_code=denied.public_code)

        # Hand off to the Database Router (it selects exactly one DB from the signed claim).
        # The gateway resolves no database (§X/§H); it maps the router's references-only
        # RouteOutcome into the response. `category` stays gateway-owned (§Q) — it is the
        # gateway's own per-request classification and is NEVER taken from the router.
        outcome = self._router.dispatch(context, decision)
        return GatewayResponse(
            status=outcome.status,
            public_code=outcome.public_code,
            dispatched=outcome.dispatched,
            category=category,
        )

    @staticmethod
    def _correlation_id(request: InboundRequest) -> str:
        for key, value in request.headers.items():
            if key.lower() == _CORRELATION_HEADER and value.strip():
                return value.strip()
        return uuid.uuid4().hex
