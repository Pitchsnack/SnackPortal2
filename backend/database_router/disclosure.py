"""Database Routing Disclosure Standard (PRD-P4-R2 M; Governance §I).

Maps a tenant lifecycle state to a canonical, non-leaking denial. Responses carry
only canonical denial codes — never tenant counts, database identifiers/topology,
secret state, or internal failure reasons. Unknown/unauthorized collapse to
not_found upstream (auth_router + control-plane read API); the router applies the
authorized-member mapping for the single active tenant it was handed.
"""
from __future__ import annotations

from typing import Optional

from .models import (
    RoutingDenied,
    administratively_disabled,
    not_found,
    not_ready,
    unavailable,
)

# IC-002 lifecycle name -> denial (only Ready is routable).
_NOT_READY = {"Registered", "Provisioning", "Verifying"}


def denial_for_state(lifecycle_state: str, ready: bool) -> Optional[RoutingDenied]:
    """Return a RoutingDenied if the tenant is not routable, else None.

    Mapping (authorized-member view): Provisioning/Verifying/Registered -> not_ready
    (retry later); Suspended -> administratively_disabled; Failed -> unavailable;
    Decommissioned/unknown -> not_found. A `Ready` tenant whose readiness flag is
    false is treated as not_ready (defense-in-depth).
    """
    if lifecycle_state == "Ready" and ready:
        return None
    if lifecycle_state == "Suspended":
        return administratively_disabled("administratively_disabled")
    if lifecycle_state == "Failed":
        return unavailable("unavailable")
    if lifecycle_state == "Decommissioned":
        return not_found("not_found")
    if lifecycle_state in _NOT_READY or not ready:
        return not_ready("not_ready")
    return not_found("not_found")
