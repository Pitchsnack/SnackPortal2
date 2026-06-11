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
