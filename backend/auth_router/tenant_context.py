"""Stage 2 — Tenant Context Establishment.

May read the control plane (federation/membership/role/tenant-state) via the read
port; MUST NOT read tenant databases, route, or store sessions. Fail-closed: never
assume membership/state/role. Consistent denial: unknown tenant and non-member are
indistinguishable (no existence leak).
"""

from __future__ import annotations

from typing import Optional

from .models import AuthContext, Claims, forbidden, not_ready, unavailable
from .ports import ControlPlaneReadPort


class TenantContextResolver:
    def __init__(self, read: ControlPlaneReadPort) -> None:
        self._read = read

    def resolve(self, claims: Claims, *, correlation_id: str, carrier_tenant: Optional[str] = None) -> AuthContext:
        active = claims.tenant
        if active is None:
            # No tenant claim -> control-plane-scoped principal (e.g. CONTROL). No active tenant.
            return AuthContext(
                correlation_id=correlation_id,
                principal_ref=claims.subject,
                active_tenant_id=None,
                role=None,
            )

        # Signed claim is authoritative; carrier (subdomain/header) MUST match (D-06/D-30).
        if carrier_tenant is not None and carrier_tenant != active:
            raise forbidden("carrier_mismatch")

        try:
            state = self._read.get_tenant_state(active)
            member = self._read.is_member(claims.subject, active)
        except Exception:
            # Sanitized: never chain (reveal) control-plane internals.
            raise unavailable("control_plane_unavailable") from None

        # Unknown tenant and non-member deny identically (consistent disclosure).
        if state is None or not member:
            raise forbidden("tenant_access_denied")
        if not state.ready:
            raise not_ready("tenant_not_ready")

        try:
            role = self._read.get_role(claims.subject, active)
        except Exception:
            # Sanitized: never chain (reveal) control-plane internals.
            raise unavailable("control_plane_unavailable") from None

        return AuthContext(
            correlation_id=correlation_id,
            principal_ref=claims.subject,
            active_tenant_id=active,
            role=(role.value if role is not None else None),
        )
