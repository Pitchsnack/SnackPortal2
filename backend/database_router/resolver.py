"""Tenant routing resolver (PRD-P4-R2 B/K; D-07/D-16/D-17).

Registry-authoritative resolution: reads the control-plane routing view (through a
transport port + tenant-scoped cache) and applies readiness + schema-version
gating. Returns a routable `TenantRoutingView` or raises a non-leaking RoutingDenied.
Never hardcodes a database, never guesses a name, never spans tenants.
"""
from __future__ import annotations

from typing import Iterable

from .cache import RoutingViewCache
from .disclosure import denial_for_state
from .models import TenantRoutingView, not_found, not_ready, unavailable
from .ports import ControlPlaneRoutingReadPort


class RoutingResolver:
    def __init__(
        self,
        read: ControlPlaneRoutingReadPort,
        cache: RoutingViewCache,
        *,
        supported_schema_versions: Iterable[str],
    ) -> None:
        self._read = read
        self._cache = cache
        self._supported = frozenset(supported_schema_versions)

    def resolve(self, tenant_id: str) -> TenantRoutingView:
        view = self._cache.get(tenant_id)
        if view is None:
            try:
                view = self._read.get_routing_view(tenant_id)
            except Exception:
                # Fail closed; never reveal control-plane internals.
                raise unavailable("control_plane_unavailable")
            if view is None:
                # Unknown / unauthorized-to-know — consistent denial (no existence leak).
                raise not_found("not_found")
            self._cache.put(tenant_id, view)

        denial = denial_for_state(view.lifecycle_state, view.ready)
        if denial is not None:
            raise denial
        # Routing-time schema-version gate (defense in depth; D-17).
        if view.expected_schema_version not in self._supported:
            raise not_ready("schema_out_of_range")
        return view

    def invalidate(self, tenant_id: str) -> None:
        """Optional push invalidation hook (e.g. on re-association)."""
        self._cache.invalidate(tenant_id)
