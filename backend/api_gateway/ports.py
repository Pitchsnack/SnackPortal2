"""api_gateway ports (interfaces). Concrete adapters live under adapters/providers.

The gateway is an enforcement boundary, not a decision-maker (IC-010 §A). It reaches
the Authenticator (IC-005) and the Database Router over TRANSPORT ports — never an
in-process import of another service (IC-010 §M; DAG independence). It emits audit
events through a port with NO persistence sink (AD-1 Option A).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Sequence, Union

from shared.context import RequestContext

from .models import AuthResult, DispatchDecision, GatewayAuditEvent, RequestMetric, RouteOutcome
from .portal import (
    GlobalInvestorSummaryDTO,
    GlobalStartupSummaryDTO,
    TenantStartupDetailDTO,
    WorkspaceMembershipDTO,
)


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
    (IC-010 §X). Returns a references-only ``RouteOutcome`` (status/public_code/dispatched)
    that carries no DB handle/name/DSN/secret/credential or body/payload — still non-live:
    end-to-end routing remains D-15-deferred and is exercised against a stub."""

    @abstractmethod
    def dispatch(self, context: RequestContext, decision: DispatchDecision) -> RouteOutcome: ...

#this is comment
class ControlPlaneReadPort(ABC):
    """The gateway-side typed Control-Plane READ port (B5-BLK-6B; IC-010 §V.1 "typed
    results from injected ports"; §M internal transport — NO in-process import of
    control_plane). Only IC-009-R1 portal DTOs cross this port: raw dictionaries, raw
    response bodies, and provider-specific objects never do (typed parsing lives inside
    the adapter). ``None`` is the consistent not-found/unknown mapping (B5-3 LW-1: a live
    404 maps to ``None``; the gateway maps it to the existing 403 denial); every transport
    failure raises, and the gateway collapses it fail-closed to 503 ``unavailable``
    (IC-010 §L — no new public_code)."""

    @abstractmethod
    def directory(self, kind: str) -> Optional[Union[GlobalStartupSummaryDTO, GlobalInvestorSummaryDTO]]:
        """The tenant-anonymous Global Directory page read for an approved kind
        (``startup``/``investor`` only) — Control-Plane order preserved. Unknown or
        unapproved kind -> ``None`` (consistent denial)."""

    @abstractmethod
    def memberships_for_principal(self, principal_ref: str) -> Optional[WorkspaceMembershipDTO]:
        """The IC-002 MembershipsForPrincipal enumeration for the AUTHENTICATED principal
        only (self-scoped; the gateway never forwards a client-supplied selector). An
        empty membership set is a lawful success (an empty tuple, not ``None``)."""


class AuditEmitterPort(ABC):
    """IC-010 §J emit-set, sink-less port (AD-1 Option A). Records are references only
    (IC-001:94-98). No Control-DB/tenant-DB/file/external persistence; the runtime
    operational-audit class-home remains the pending IC-005/IC-002 extension."""

    @abstractmethod
    def emit(self, event: GatewayAuditEvent) -> None: ...


class MetricsPort(ABC):
    """Vendor-neutral request/latency metrics sink (IC-010 §S; WP-11). Records operational
    labels only — never a tenant identity/count, database name, or topology (§S). No
    provider observability SDK may be used (vendor-neutrality is enforced by
    tests/architecture/test_phase7_api_gateway.py)."""

    @abstractmethod
    def record_request(self, metric: RequestMetric) -> None: ...


@dataclass(frozen=True)
class ImportInitiationRequest:
    """The references-only IMPORT_INITIATION request the gateway hands to the ``ImportInitiationPort``
    (W1a composed-core). Content comes EXCLUSIVELY from the gateway-validated request (the source
    reference in the path) and the signed claim (the active tenant, the authenticated principal) —
    never a token, secret, payload, source record, DB handle, or topology. ``operation_key`` is the
    bounded ``x-operation-key`` header value, else a gateway-minted uuid4().hex (operation-level
    idempotency, D-20)."""

    source_ref: str  # the Global Startup reference (IR-09: carried by reference, never joined in-request)
    target_tenant_ref: str  # the signed active tenant (never a client-supplied selector)
    operation_key: str
    correlation_id: str
    actor_ref: str  # the authenticated principal reference (never a token)


@dataclass(frozen=True)
class ImportInitiationOutcome:
    """The references-only outcome the ``ImportInitiationPort`` returns to the gateway (W1a). Never a
    tenant row, source record, DB handle/name/DSN, credential, or payload. ``ok`` is False for any
    transport/edge failure (the gateway maps it fail-closed to §L 503). On a served import the counts +
    ``replayed`` + ``import_id`` let the gateway compose the exact ``ImportResultDTO`` outcome
    (created/replayed/noop) and the LW-1 zero-record consistent denial — from a real, durably-audited
    result only."""

    ok: bool
    state: str  # the ImportStatus.state ("applied" / "failed"); "" on a transport failure
    replayed: bool
    applied_count: int
    noop_count: int
    import_id: str  # the import job id (== the lineage derivation reference); "" on a transport failure


class ImportInitiationPort(ABC):
    """``Gateway → Import Service`` — the only approved import-initiation boundary (W1a composed-core),
    reached over transport (NO in-process import of ``import_service``; IC-010 §M/DAG independence). The
    gateway hands references only and receives a references-only ``ImportInitiationOutcome``; it never
    resolves a database (IC-010 §X) and the method is named ``initiate`` (NOT ``start_import`` — the
    gateway must reference no import-execution name). Every transport failure collapses fail-closed to a
    non-ok outcome (the gateway maps it to 503 ``unavailable`` — no new public_code)."""

    @abstractmethod
    def initiate(self, request: ImportInitiationRequest) -> ImportInitiationOutcome: ...


@dataclass(frozen=True)
class TenantStartupReadRequest:
    """The references-only CLM tenant Startup READ request (D-42; IC-010 CLM section) the
    gateway hands to the ``TenantStartupOperationsPort``. Content comes EXCLUSIVELY from
    the gateway-validated request (the opaque, bounded ``<startup_ref>`` path suffix) and
    the signed claim (the single active tenant, the authenticated principal) — never a
    token, secret, payload, DB handle, or topology, and never a client-supplied tenant
    selector (``target_tenant_ref`` is the dispatch decision's signed active tenant)."""

    startup_ref: str  # the opaque tenant-resident Startup record reference (1..512 UTF-8 bytes)
    target_tenant_ref: str  # the signed active tenant (never a client-supplied selector)
    correlation_id: str
    actor_ref: str  # the authenticated principal reference (never a token)


@dataclass(frozen=True)
class TenantStartupUpdateRequest:
    """The bounded CLM tenant Startup UPDATE request (D-42; IC-010 CLM section). Exactly
    the read request plus the single allowlisted field value: ``short_description`` is
    the SOLE CLM-mutable field (a UTF-8 string of at most 500 characters, or None to
    clear), already validated fail-closed by the gateway
    (``portal.parse_tenant_startup_update_request``) BEFORE this request is built —
    no unvalidated content ever crosses this port."""

    startup_ref: str
    target_tenant_ref: str
    correlation_id: str
    actor_ref: str
    short_description: Optional[str]


class TenantStartupOperationsPort(ABC):
    """``Gateway → Database Router`` tenant Startup data seam (D-42 CLM Stage B; IC-010
    CLM section) — reached over transport ONLY, never an in-process import of
    ``database_router`` (IC-010 §M; DAG independence). The Database Router side resolves,
    from the signed claim, EXACTLY ONE physical tenant database (IC-010 §K/§O; D-07) and
    executes the bounded read/update there; the gateway never resolves a database (§X).

    Only the adopted ``TenantStartupDetailDTO`` crosses this port (IC-010 §V.1 typed port
    results — raw dictionaries, raw response bodies, and provider objects never do; typed
    parsing lives inside the adapter). ``None`` is the consistent IC-002 not-found
    mapping (an unknown ``<startup_ref>`` within the bound tenant database — the gateway
    maps it to the existing ``not_found`` denial, leaking no cross-tenant existence).
    Every transport failure raises, and the gateway collapses it fail-closed to 503
    ``unavailable`` (IC-010 §L — no new public_code). The update is bounded and atomic:
    the Database Router side writes the sole allowlisted field or nothing (no partial
    write)."""

    @abstractmethod
    def read(self, request: TenantStartupReadRequest) -> Optional[TenantStartupDetailDTO]: ...

    @abstractmethod
    def update(self, request: TenantStartupUpdateRequest) -> Optional[TenantStartupDetailDTO]: ...
