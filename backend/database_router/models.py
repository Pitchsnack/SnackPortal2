"""database_router domain shapes (vendor-neutral, decoupled from control_plane).

These are router-local DTOs so database_router never imports control_plane or
auth_router (DAG rule). The control-plane routing-read API serializes to
`TenantRoutingView` across the transport boundary. No tokens, secrets, or raw
credentials appear in any field — `database_association_ref` is a *reference*
({store_ref, version}), never the credentials (D-14; IC-002).

Denial semantics reuse the shared canonical `DenialReason` and follow the
Database Routing Disclosure Standard (PRD-P4-R2 M): the HTTP mapping below is the
*authorized-member* view; unauthorized callers never reach the router with a
foreign tenant active (consistent denial is enforced upstream by auth_router and
the control-plane read API).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from shared.audit import OperationalAuditEvent
from shared.errors import DenialReason
from shared.secrets import SecretRef
from shared.session import Lane


class RoutingTarget(Enum):
    TENANT = "tenant"  # exactly one tenant database
    CONTROL = "control"  # the Control Database (control-plane-scoped read)


@dataclass(frozen=True)
class TenantRoutingView:
    """Routing-read model (PRD-P4-R2 B). References only — never credentials."""

    tenant_id: str
    lifecycle_state: str  # IC-002 lifecycle state name
    ready: bool  # derived two-state readiness (control-plane authoritative)
    database_association_ref: SecretRef  # reference {store_ref, version}; resolved at connect time
    expected_schema_version: str  # registry-intended tenant schema version (D-17)


@dataclass(frozen=True)
class RouteResult:
    """The routing decision. Carries no token/secret/credential.

    For a CONTROL route, `tenant_id`/`association_version`/`connection` are None.
    """

    target: RoutingTarget
    tenant_id: Optional[str] = None
    association_version: Optional[str] = None
    connection: Optional[object] = None  # a bound TenantConnection for TENANT routes
    lane: Lane = Lane.INTERACTIVE  # which capacity lane served this route (D-13)


# --- router-edge routing-decision audit events (DBR-AR-2A; IC-002 class 3 — Database Router edge) ---

# Router-local source identity (mirrors the liveness `build_phase` string; main.py is
# the composition root and is never imported from here — DAG rule).
ROUTING_AUDIT_SOURCE_SERVICE = "database_router"
ROUTING_AUDIT_SOURCE_VERSION = "4"

# Additive-only event-shape version (IC-002 class 3 — Database Router edge).
ROUTING_AUDIT_EVENT_VERSION = 1

# Exact frozen action vocabulary of the router-edge routing-decision subclass.
# Extension only by contract amendment (IC-002/IC-005).
ROUTING_AUDIT_ACTIONS = ("Route", "RouteControl", "RouteDenied", "IsolationAnomaly")


@dataclass(frozen=True, kw_only=True)
class RoutingAuditEvent(OperationalAuditEvent):
    """Router-edge routing-decision event (IC-002 class 3 — Database Router edge).

    Immutable, versioned, references only. Extends the shared operational-audit shape
    (inherited: `actor_ref`, `action`, `correlation_id`, `outcome`, `target_ref` — the
    authenticated active-tenant reference) with the router-minted identity and reference
    fields of the DBR-AR-2 contract §8. The Database Router is the sole emitter of this
    subclass (IC-005 Runtime Operational Audit Emission); exactly one event is emitted
    per completed or denied `route()` invocation. `recorded_at` is store-assigned at
    persistence time (a later slice) and is deliberately NOT a router-minted field.
    No credentials, tokens, payloads, tenant result data, hostnames, or topology —
    `association_store_ref` is the D-14 reference, never a resolved value.
    """

    event_id: str  # router-minted UUID; the idempotency identity
    event_version: int  # ROUTING_AUDIT_EVENT_VERSION; additive-only evolution
    occurred_at: str  # UTC ISO-8601, router clock; informational only — never an ordering authority
    source_service: str  # ROUTING_AUDIT_SOURCE_SERVICE
    source_version: str  # ROUTING_AUDIT_SOURCE_VERSION
    request_ref: Optional[str] = None  # RequestContext.request_id where present
    resolved_tenant_ref: Optional[str] = None  # tenant the router actually bound (divergence => IsolationAnomaly)
    public_code: Optional[str] = None  # canonical router-edge denial code; None on success
    error_class: Optional[str] = None  # bounded internal vocabulary; unpopulated in DBR-AR-2A
    association_store_ref: Optional[str] = None  # D-14 SecretRef.store_ref — a reference, never a value
    association_version: Optional[str] = None  # association reference version bound for this route
    lane: Optional[str] = None  # "interactive" / "bulk" (D-13 capacity lane)


class RoutingDenied(Exception):
    """Routing denial carrying only a non-sensitive reason + status + public code.

    MUST NOT carry tenant identifiers beyond the (already authenticated) active
    tenant, database hostnames/topology, secret state, or internal failure detail.
    """

    def __init__(self, reason: DenialReason, http_status: int, public_code: str) -> None:
        super().__init__(public_code)
        self.reason = reason
        self.http_status = http_status
        self.public_code = public_code


# --- canonical denial constructors (Database Routing Disclosure Standard, PRD-P4-R2 M) ---
def not_found(code: str = "not_found") -> RoutingDenied:
    # unknown / decommissioned / unauthorized-to-know — existence never confirmed
    return RoutingDenied(DenialReason.NOT_FOUND, 404, code)


def forbidden(code: str = "forbidden") -> RoutingDenied:
    return RoutingDenied(DenialReason.FORBIDDEN, 403, code)


def not_ready(code: str = "not_ready") -> RoutingDenied:
    # provisioning / verifying / registered / schema-out-of-range — retry later
    return RoutingDenied(DenialReason.NOT_READY, 503, code)


def administratively_disabled(code: str = "administratively_disabled") -> RoutingDenied:
    # suspended (to an authorized member)
    return RoutingDenied(DenialReason.ADMINISTRATIVELY_DISABLED, 403, code)


def unavailable(code: str = "unavailable") -> RoutingDenied:
    # failed / database unreachable / internal resolution failure (no leak)
    return RoutingDenied(DenialReason.UNAVAILABLE, 503, code)
