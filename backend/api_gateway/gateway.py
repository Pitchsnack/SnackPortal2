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
from .portal import (
    ImportInitiationDTO,
    ImportResultDTO,
    PortalDTO,
    compose_portal_dto,
    parse_tenant_startup_update_request,
)
from .ports import (
    AuditEmitterPort,
    AuthenticatorPort,
    ControlPlaneReadPort,
    ImportInitiationPort,
    ImportInitiationRequest,
    MetricsPort,
    RouterDispatchPort,
    TenantStartupOperationsPort,
    TenantStartupReadRequest,
    TenantStartupUpdateRequest,
)
from .request_context import build_request_context

_CORRELATION_HEADER = "x-correlation-id"
_OPERATION_KEY_HEADER = "x-operation-key"
_MAX_OPERATION_KEY_LEN = 200

_DIRECTORY_PREFIX = "/directory/"
_IMPORT_PREFIX = "/import/"
_TENANT_STARTUP_PREFIX = "/tenant/startups/"
_MAX_STARTUP_REF_BYTES = 512  # IC-010 CLM: <startup_ref> is opaque and length-bounded (1..512 UTF-8 bytes)


def _directory_kind(path: str) -> str:
    """The directory-kind OPERATION parameter from the path (IC-010 §X: an application-
    level dispatch input, never a tenant/workspace selector). Anything that is not an
    exact ``/directory/<kind>`` remainder resolves to an unknown kind -> fail-closed."""
    return path[len(_DIRECTORY_PREFIX) :] if path.startswith(_DIRECTORY_PREFIX) else ""


def _import_source_ref(path: str) -> str:
    """The global-source REFERENCE the import request itself carries (references only;
    IR-09: the global source is carried by reference, never joined/read in-request)."""
    return path[len(_IMPORT_PREFIX) :] if path.startswith(_IMPORT_PREFIX) else ""


def _tenant_startup_ref(path: str) -> Optional[str]:
    """The opaque tenant-resident ``<startup_ref>`` path suffix of a CLM tenant Startup
    route (IC-010 CLM: 1..512 UTF-8 bytes, single segment, traversal-safe — the strict
    charset is enforced pre-core at the serving edge; this core check is the bounded
    defense-in-depth half). ``None`` for any non-matching, empty, multi-segment, or
    over-bound path — the request then follows the pre-CLM TENANT_OPERATION handoff.
    The suffix is never a tenant selector and never a database selector (§X)."""
    if not path.startswith(_TENANT_STARTUP_PREFIX):
        return None
    suffix = path[len(_TENANT_STARTUP_PREFIX) :]
    if not suffix or "/" in suffix or len(suffix.encode("utf-8")) > _MAX_STARTUP_REF_BYTES:
        return None
    return suffix


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
        import_initiation: Optional[ImportInitiationPort] = None,
        tenant_startup: Optional[TenantStartupOperationsPort] = None,
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
        # W1a composed-core (IC-003; IC-009 ImportResultDTO): the OPTIONAL Gateway→Import transport
        # port. None (the default) keeps the port-absent accepted-initiation envelope path
        # byte-behavior-unchanged; when injected, IMPORT_INITIATION EXECUTES the real import via the
        # port and NEVER calls self._router.dispatch (single-route).
        self._import_initiation = import_initiation
        # D-42 CLM Stage B (IC-010 CLM section): the OPTIONAL Gateway→Database-Router tenant Startup
        # data port. None (the default) keeps every TENANT_OPERATION on the pre-CLM router handoff
        # byte-behavior-unchanged; when injected, the two CLM tenant Startup routes execute the
        # bounded read/update through the port (Gateway → Database Router → exactly one physical
        # tenant database) and NEVER call self._router.dispatch on that path (single-route).
        self._tenant_startup = tenant_startup

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
        ) -> bool:
            """Emit one references-only edge event; True on success (or per-request dedup).

            D-42 CLM Stage B: every event now carries the minted identity triple
            (``audit_id`` / ``occurred_at`` / ``event_version == 1``) so the durably homed
            classes persist idempotently (DDL 012). A sink failure returns ``False`` and the
            caller collapses fail-closed to the §L 503 ``unavailable`` — a denial is never
            handed back without its audit evidence once its class is durably homed (the
            default in-memory emitter never raises, so pre-CLM compositions are unchanged).
            """
            key = (action, correlation_id)
            if key in emitted:  # idempotent: the same correlation-bound event is emitted at most once
                return True
            emitted.add(key)
            try:
                self._audit.emit(
                    GatewayAuditEvent(
                        action=action,
                        correlation_id=correlation_id,
                        outcome=outcome,
                        actor_ref=actor_ref,
                        tenant_ref=tenant_ref,
                        carrier_ref=carrier_ref,
                        audit_id=uuid.uuid4().hex,
                        occurred_at=datetime.now(timezone.utc).isoformat(),
                        event_version=1,
                    )
                )
            except Exception:
                return False
            return True

        carriers = recognized_carriers(request)

        # Isolation (§K): one request asserting >1 distinct tenant carrier is a straddle
        # attempt (e.g. a MASTER_AGENT fan-out across t1/t2) — reject + audit, fail-closed.
        if len(set(carriers)) > 1:
            if not emit(AuditAction.ISOLATION_ANOMALY, "rejected", carrier_ref=opaque_carrier_ref(",".join(sorted(set(carriers))))):
                return GatewayResponse(status=503, public_code="unavailable")
            return GatewayResponse(status=403, public_code="isolation_anomaly")

        # Authentication (§D): consumed as input; the recognized carrier is fed into the
        # IC-005 carrier-match check inside the authenticator (the only permitted carrier use).
        try:
            auth = self._authenticator.authenticate(request.authorization, carriers, correlation_id)
        except RequestRejected as rejected:
            mismatch = rejected.public_code == "carrier_mismatch"
            action = AuditAction.CARRIER_MISMATCH if mismatch else AuditAction.ROUTE_DENIED
            # D-43: the durably homed CarrierMismatch denial record carries the REQUIRED opaque
            # carrier_ref — the recognized carrier value rendered by the existing opaque helper
            # (never the bearer token, never the signed tenant claim; IC-005:116). No actor,
            # subject, tenant, or record reference is fabricated, denial ordering is unchanged,
            # and the denial stays pre-context and pre-routing (no RequestContext, no dispatch).
            if not emit(action, "rejected", carrier_ref=opaque_carrier_ref(carriers[0]) if mismatch and carriers else None):
                # D-42 CLM: a durably homed denial record that cannot persist fails the
                # denial closed (503) — never an unevidenced hand-back (§L; no new code).
                return GatewayResponse(status=503, public_code="unavailable")
            return GatewayResponse(status=rejected.http_status, public_code=rejected.public_code)

        # §F: a recognized carrier on a tenantless CONTROL token is ignored (claim-only) and
        # MUST emit the mandatory CarrierOnControlAnomaly (references only, opaque carrier id).
        if auth.active_tenant_id is None and carriers:
            if not emit(
                AuditAction.CARRIER_ON_CONTROL_ANOMALY,
                "observed",
                actor_ref=auth.principal_ref,
                carrier_ref=opaque_carrier_ref(carriers[0]),
            ):
                return GatewayResponse(status=503, public_code="unavailable")

        # RequestContext is constructed EXCLUSIVELY from AuthContext (§G/§T; load-bearing).
        context: RequestContext = build_request_context(auth)

        # Endpoint dispatch by path/operation only (§X/§Q); one request → one category → one DB (§K).
        try:
            category = self._classify(request)
            decision = decide(category, context)
            assert_single_database(decision)
        except DispatchError as denied:
            if denied.isolation_anomaly:
                if not emit(AuditAction.ISOLATION_ANOMALY, "rejected", actor_ref=auth.principal_ref, tenant_ref=context.active_tenant_id):
                    return GatewayResponse(status=503, public_code="unavailable")
                return GatewayResponse(status=403, public_code="isolation_anomaly")
            if not emit(AuditAction.ROUTE_DENIED, "rejected", actor_ref=auth.principal_ref, tenant_ref=context.active_tenant_id):
                return GatewayResponse(status=503, public_code="unavailable")
            return GatewayResponse(status=403, public_code=denied.public_code)

        # D-42 CLM Stage B (IC-010 CLM section): with the typed tenant Startup port injected,
        # the two CLM tenant Startup routes — GET/PATCH /tenant/startups/<startup_ref> —
        # execute the bounded read/update through the port (Gateway → Database Router →
        # exactly one physical tenant database, resolved from the signed claim) and compose
        # the adopted TenantStartupDetailDTO from the typed port result (§V.1). Every other
        # TENANT_OPERATION keeps the pre-CLM router handoff unchanged. No new dispatch
        # category, no new carrier, no new public_code (§L/§Q/§X unchanged).
        if self._tenant_startup is not None and category is DispatchCategory.TENANT_OPERATION:
            startup_ref = _tenant_startup_ref(request.path)
            if startup_ref is not None and request.method in ("GET", "PATCH"):
                # TENANT domain: assert_single_database above guarantees exactly one signed active tenant.
                assert decision.target_tenant_id is not None
                detail: Optional[PortalDTO]
                if request.method == "PATCH":
                    # Bounded update validation FIRST (IC-010 CLM): exactly the one allowlisted
                    # field, string-or-null, at most 500 characters — anything else is rejected
                    # fail-closed with NO partial write and no port call (the 16384-byte
                    # transport bound was enforced pre-core at the serving edge).
                    try:
                        update_request = parse_tenant_startup_update_request(request.patch_body or b"")
                    except ValueError:
                        return GatewayResponse(status=403, public_code="forbidden", category=category)
                    try:
                        detail = self._tenant_startup.update(
                            TenantStartupUpdateRequest(
                                startup_ref=startup_ref,
                                target_tenant_ref=decision.target_tenant_id,
                                correlation_id=correlation_id,
                                actor_ref=auth.principal_ref,
                                short_description=update_request.short_description,
                            )
                        )
                    except Exception:
                        # Transport / router / tenant-DB unavailability -> fail closed to the
                        # existing §L vocabulary (no new public_code); no raw exception, SQL,
                        # hostname, or DB identity leaks (§V.2). No partial write: the Database
                        # Router side writes the sole allowlisted field atomically or nothing.
                        return GatewayResponse(status=503, public_code="unavailable", category=category)
                else:
                    try:
                        detail = self._tenant_startup.read(
                            TenantStartupReadRequest(
                                startup_ref=startup_ref,
                                target_tenant_ref=decision.target_tenant_id,
                                correlation_id=correlation_id,
                                actor_ref=auth.principal_ref,
                            )
                        )
                    except Exception:
                        # Same fail-closed collapse as the update half (§L; no new public_code).
                        return GatewayResponse(status=503, public_code="unavailable", category=category)
                if detail is None:
                    # Unknown <startup_ref> within the bound tenant database -> the consistent
                    # IC-002 not-found semantic (existing `not_found` public code; no new code,
                    # no cross-tenant existence leak, no audit success event, no DTO).
                    return GatewayResponse(status=404, public_code="not_found", category=category)
                composed_detail = compose_portal_dto(detail)
                # CLM success-access audit (IC-010 CLM: exactly one references-only event per
                # successful read/update; the API Gateway is the sole emitter; the value of
                # short_description NEVER appears in the event). Audit-before-hand-back: a
                # terminally unavailable durable sink collapses the served success to the §L
                # 503 `unavailable` — a CLM tenant Startup success is never handed back unless
                # its event is durably persisted (the workspace_memberships_read posture).
                try:
                    self._audit.emit(
                        GatewayAuditEvent(
                            action=AuditAction.TENANT_STARTUP_READ if request.method == "GET" else AuditAction.TENANT_STARTUP_UPDATE,
                            correlation_id=correlation_id,
                            outcome="success",
                            actor_ref=auth.principal_ref,
                            tenant_ref=decision.target_tenant_id,
                            record_ref=startup_ref,
                            audit_id=uuid.uuid4().hex,
                            occurred_at=datetime.now(timezone.utc).isoformat(),
                            event_version=1,
                        )
                    )
                except Exception:
                    return GatewayResponse(status=503, public_code="unavailable", category=category)
                return GatewayResponse(status=200, public_code="ok", dispatched=True, category=category, portal_dto=composed_detail)

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
                if not emit(AuditAction.ROUTE_DENIED, "rejected", actor_ref=auth.principal_ref, tenant_ref=context.active_tenant_id):
                    return GatewayResponse(status=503, public_code="unavailable", category=category)
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
                #
                # Gateway Audit V1a (audit-before-hand-back, fail closed): the emit is wrapped so a
                # DURABLE audit sink that is terminally unavailable — after the composition's single
                # bounded retry (BoundedGatewayAuditPolicy, api_gateway/main.py) — collapses to the
                # existing §L 503 `unavailable` (no new public_code; no raw exception / provider body /
                # SQL / DB identity leaks). A served MembershipsForPrincipal success is NEVER handed
                # back unless its workspace_memberships_read event is durably persisted (the DBR-AR-2C
                # §11 condition-1 posture, re-homed to the gateway success edge). The default in-memory
                # no-sink emitter never raises, so the pre-V1a non-durable composition is byte-unchanged.
                try:
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
                except Exception:
                    return GatewayResponse(status=503, public_code="unavailable", category=category)
            return GatewayResponse(status=200, public_code="ok", dispatched=True, category=category, portal_dto=composed)

        # W1a composed-core: with the ImportInitiationPort injected, IMPORT_INITIATION EXECUTES the
        # real import through the port and does NOT hand off to the Database Router (single-route: no
        # self._router.dispatch on this path — the router.route() is performed once inside the Import
        # Service's routed session). Content comes EXCLUSIVELY from the gateway-validated request (the
        # source reference in the path) and the signed claim (the active tenant, the principal) — never
        # from a client-supplied selector. The ImportResultDTO is composed only from a real, durably-
        # audited result; §L maps every failure/denial fail-closed (no DTO on any denial).
        if self._import_initiation is not None and category is DispatchCategory.IMPORT_INITIATION:
            # TENANT domain: assert_single_database above guarantees exactly one signed active tenant.
            assert decision.target_tenant_id is not None
            source_ref = _import_source_ref(request.path)
            result = self._import_initiation.initiate(
                ImportInitiationRequest(
                    source_ref=source_ref,
                    target_tenant_ref=decision.target_tenant_id,
                    operation_key=self._operation_key(request),
                    correlation_id=correlation_id,
                    actor_ref=auth.principal_ref,
                )
            )
            if not result.ok or result.state != "applied":
                # Any transport/audit/engine failure -> fail closed 503 (§L; no DTO; no new public_code).
                return GatewayResponse(status=503, public_code="unavailable", category=category)
            if result.applied_count == 0 and result.noop_count == 0:
                # Zero-record completion (source ref unknown / all records rejected) -> the LW-1
                # consistent denial; global-record existence is never leaked.
                if not emit(AuditAction.ROUTE_DENIED, "rejected", actor_ref=auth.principal_ref, tenant_ref=context.active_tenant_id):
                    return GatewayResponse(status=503, public_code="unavailable", category=category)
                return GatewayResponse(status=403, public_code="forbidden")
            token = "replayed" if result.replayed else ("created" if result.applied_count >= 1 else "noop")
            composed_result = compose_portal_dto(
                ImportResultDTO(
                    source_ref=source_ref,
                    target_tenant_ref=decision.target_tenant_id,
                    tenant_record_ref=f"{decision.target_tenant_id}:startups:{source_ref}",
                    lineage_ref=result.import_id,
                    import_id=result.import_id,
                    outcome=token,
                )
            )
            return GatewayResponse(status=200, public_code="ok", dispatched=True, category=category, portal_dto=composed_result)

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

    @staticmethod
    def _operation_key(request: InboundRequest) -> str:
        # W1a operation-level idempotency (D-20): a bounded "x-operation-key" header, else gateway-minted.
        for key, value in request.headers.items():
            if key.lower() == _OPERATION_KEY_HEADER:
                candidate = value.strip()
                if candidate and len(candidate) <= _MAX_OPERATION_KEY_LEN:
                    return candidate
        return uuid.uuid4().hex
