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
from datetime import datetime, timezone
from typing import Callable, Optional, Set, Tuple

from shared.context import RequestContext

from .carrier import opaque_carrier_ref, recognized_carriers
from .dispatch import DispatchError, assert_single_database, decide
from .models import (
    AuditAction,
    DatabaseDomain,
    DispatchCategory,
    GatewayAuditEvent,
    GatewayResponse,
    InboundRequest,
    RequestMetric,
    RequestRejected,
)
from .portal import ImportInitiationDTO, PortalDTO, compose_portal_dto
from .ports import AuditEmitterPort, AuthenticatorPort, ControlPlaneReadPort, MetricsPort, RouterDispatchPort
from .request_context import build_request_context

_CORRELATION_HEADER = "x-correlation-id"

_DIRECTORY_PREFIX = "/directory/"
_IMPORT_PREFIX = "/import/"


def _directory_kind(path: str) -> str:
    """The directory-kind OPERATION parameter from the path (IC-010 §X: an application-
    level dispatch input, never a tenant/workspace selector). Anything that is not an
    exact ``/directory/<kind>`` remainder resolves to an unknown kind -> fail-closed."""
    return path[len(_DIRECTORY_PREFIX) :] if path.startswith(_DIRECTORY_PREFIX) else ""


def _import_source_ref(path: str) -> str:
    """The global-source REFERENCE the import request itself carries (references only;
    IR-09: the global source is carried by reference, never joined/read in-request)."""
    return path[len(_IMPORT_PREFIX) :] if path.startswith(_IMPORT_PREFIX) else ""


class Gateway:
    """The composed gateway pipeline. Ports are injected (tests/dev stubs; prod transport)."""

    def __init__(
        self,
        *,
        authenticator: AuthenticatorPort,
        router: RouterDispatchPort,
        control_read: Optional[ControlPlaneReadPort] = None,
        classify: Callable[[InboundRequest], DispatchCategory],
        audit: AuditEmitterPort,
        metrics: MetricsPort,
    ) -> None:
        self._authenticator = authenticator
        self._router = router
        # B5-BLK-6B (IC-010 §V): the OPTIONAL typed Control-Plane read port. None (the
        # default) keeps the pre-6B pipeline byte-identical — every category continues
        # through the router and portal_dto stays None (rollback-by-default; no silent
        # activation).
        self._control_read = control_read
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

        # B5-BLK-6B (IC-010 §V): with the typed Control-Plane read port injected, the two
        # CONTROL-domain read categories are COMPOSED from typed port results — the gateway
        # builds the approved IC-009-R1 DTO itself; no downstream body is ever relayed.
        # Composition never selects a database (§V.1): the decision above already resolved
        # the single CONTROL domain, and no tenant database is touched.
        if self._control_read is not None and decision.domain is DatabaseDomain.CONTROL:
            try:
                composed: Optional[PortalDTO]
                if category is DispatchCategory.GLOBAL_DIRECTORY_READ:
                    page = self._control_read.directory(_directory_kind(request.path))
                    composed = compose_portal_dto(page) if page is not None else None
                else:
                    # MembershipsForPrincipal is SELF-SCOPED ONLY (IC-002:207 narrowed;
                    # no CONTROL override in 6B): the subject principal comes exclusively
                    # from AuthResult.principal_ref — a client-supplied selector (query,
                    # header, body) is never read.
                    memberships = self._control_read.memberships_for_principal(auth.principal_ref)
                    composed = compose_portal_dto(memberships) if memberships is not None else None
            except Exception:
                # CP unavailable / timeout / malformed / oversized / internal failure ->
                # fail closed to the existing §L vocabulary (no new public_code); no raw
                # exception, provider body, SQL, hostname, or DB identity leaks (§V.2).
                return GatewayResponse(status=503, public_code="unavailable", category=category)
            if composed is None:
                # Unknown kind / not found -> the existing consistent denial (LW-1:
                # 404 -> None -> 403); never leaks existence, never a DTO on denial.
                emit(AuditAction.ROUTE_DENIED, "rejected", actor_ref=auth.principal_ref, tenant_ref=context.active_tenant_id)
                return GatewayResponse(status=403, public_code="forbidden")
            if category is DispatchCategory.MEMBERSHIPS_FOR_PRINCIPAL:
                # B5-BLK-6C-B (IC-010 §J success-access subclass; IC-002 class 3b): exactly
                # ONE references-only workspace_memberships_read event per successful
                # self-scoped enumeration — a successful EMPTY enumeration included. Emitted
                # only here: after the successful Control-Plane read and DTO composition,
                # after the composed-is-None denial, before the single success return —
                # never on a denial/failure path, never per membership, never per tenant.
                # The category gate keeps directory-read success unaudited (§R Reserved).
                # Self-scoped: actor == subject == the authenticated principal only.
                self._audit.emit(
                    GatewayAuditEvent(
                        action=AuditAction.WORKSPACE_MEMBERSHIPS_READ,
                        correlation_id=correlation_id,
                        outcome="success",
                        actor_ref=auth.principal_ref,
                        subject_ref=auth.principal_ref,
                        audit_id=uuid.uuid4().hex,
                        occurred_at=datetime.now(timezone.utc).isoformat(),
                        event_version=1,
                    )
                )
            return GatewayResponse(status=200, public_code="ok", dispatched=True, category=category, portal_dto=composed)

        # Hand off to the Database Router (it selects exactly one DB from the signed claim).
        # The gateway resolves no database (§X/§H); it maps the router's references-only
        # RouteOutcome into the response. `category` stays gateway-owned (§Q) — it is the
        # gateway's own per-request classification and is NEVER taken from the router.
        outcome = self._router.dispatch(context, decision)

        # B5-BLK-6B (IC-010 §V): the accepted-initiation envelope, composed ONLY when the
        # 6B composition seam is active AND the route outcome is dispatched and successful.
        # Content comes EXCLUSIVELY from the gateway-validated request (the source
        # reference in the path) and the dispatch-decision references — never from the
        # RouteOutcome (§V.2: composition never sources content from it) and never from an
        # import execution (ImportService.start_import is never called; nothing is created).
        portal_dto: Optional[PortalDTO] = None
        if (
            self._control_read is not None
            and category is DispatchCategory.IMPORT_INITIATION
            and outcome.dispatched
            and outcome.status < 400
            and decision.target_tenant_id is not None
        ):
            portal_dto = compose_portal_dto(
                ImportInitiationDTO(
                    source_ref=_import_source_ref(request.path),
                    target_tenant_ref=decision.target_tenant_id,
                )
            )
        return GatewayResponse(
            status=outcome.status,
            public_code=outcome.public_code,
            dispatched=outcome.dispatched,
            category=category,
            portal_dto=portal_dto,
        )

    @staticmethod
    def _correlation_id(request: InboundRequest) -> str:
        for key, value in request.headers.items():
            if key.lower() == _CORRELATION_HEADER and value.strip():
                return value.strip()
        return uuid.uuid4().hex
