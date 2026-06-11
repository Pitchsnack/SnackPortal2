"""Bounded TTL cache with tenant-scoped invalidation (federation/membership/JWKS).

A read-through caching decorator over ControlPlaneReadPort reduces control-plane
round-trips while honoring tenant-scoped invalidation on re-association/membership
change (D-11). Stdlib only.
"""
from __future__ import annotations

import time
from typing import Callable, Dict, Optional, Tuple

from .models import FederationView, Role, TenantStateView
from .ports import ControlPlaneReadPort


class TtlCache:
    def __init__(self, ttl_seconds: float = 30.0, max_entries: int = 1024) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._data: Dict[str, Tuple[float, object]] = {}

    def get(self, key: str) -> Optional[object]:
        item = self._data.get(key)
        if item is None:
            return None
        expires_at, value = item
        if time.monotonic() > expires_at:
            self._data.pop(key, None)
            return None
        return value

    def put(self, key: str, value: object) -> None:
        if len(self._data) >= self._max:
            self._data.pop(next(iter(self._data)), None)  # simple bound (drop oldest-inserted)
        self._data[key] = (time.monotonic() + self._ttl, value)

    def invalidate(self, key: str) -> None:
        self._data.pop(key, None)

    def invalidate_tenant(self, tenant_id: str) -> None:
        for k in [k for k in self._data if tenant_id in k]:
            self._data.pop(k, None)


class CachingControlPlaneRead(ControlPlaneReadPort):
    """Read-through cache wrapper; same fail-closed contract as the wrapped port."""

    def __init__(self, inner: ControlPlaneReadPort, ttl_seconds: float = 30.0) -> None:
        self._inner = inner
        self._cache = TtlCache(ttl_seconds=ttl_seconds)

    def _cached(self, key: str, loader: Callable[[], object]) -> object:
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        value = loader()
        if value is not None:
            self._cache.put(key, value)
        return value

    def get_federation_for_issuer(self, issuer: str) -> Optional[FederationView]:
        return self._cached(f"fed::{issuer}", lambda: self._inner.get_federation_for_issuer(issuer))  # type: ignore[return-value]

    def get_tenant_state(self, tenant_id: str) -> Optional[TenantStateView]:
        return self._cached(f"state::{tenant_id}", lambda: self._inner.get_tenant_state(tenant_id))  # type: ignore[return-value]

    def is_member(self, principal_ref: str, tenant_id: str) -> bool:
        return bool(self._cached(f"member::{tenant_id}::{principal_ref}", lambda: self._inner.is_member(principal_ref, tenant_id)))

    def get_role(self, principal_ref: str, tenant_id: str) -> Optional[Role]:
        return self._cached(f"role::{tenant_id}::{principal_ref}", lambda: self._inner.get_role(principal_ref, tenant_id))  # type: ignore[return-value]

    def invalidate_tenant(self, tenant_id: str) -> None:
        self._cache.invalidate_tenant(tenant_id)
