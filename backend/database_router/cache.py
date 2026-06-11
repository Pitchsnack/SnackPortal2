"""Database Association Cache (PRD-P4-R2 K; D-11).

Tenant-scoped routing-view cache with a bounded TTL and explicit invalidation.
The cached value carries the association version; connection pools key on
(tenant_id, association_version), so a re-association (version bump) naturally
routes to a fresh pool once the new view is observed.

Baseline invalidation is pull-based (short TTL re-read); `invalidate()` provides
the optional push hook. The clock is injectable for deterministic tests. Stdlib only.
"""
from __future__ import annotations

import time
from typing import Callable, Dict, Optional, Tuple

from .models import TenantRoutingView


class RoutingViewCache:
    def __init__(
        self,
        *,
        ttl_seconds: float = 15.0,
        max_entries: int = 4096,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._clock = clock
        self._data: Dict[str, Tuple[float, TenantRoutingView]] = {}

    def get(self, tenant_id: str) -> Optional[TenantRoutingView]:
        item = self._data.get(tenant_id)
        if item is None:
            return None
        expires_at, view = item
        if self._clock() > expires_at:
            self._data.pop(tenant_id, None)
            return None
        return view

    def put(self, tenant_id: str, view: TenantRoutingView) -> None:
        if len(self._data) >= self._max and tenant_id not in self._data:
            self._data.pop(next(iter(self._data)), None)  # simple bound (drop oldest-inserted)
        self._data[tenant_id] = (self._clock() + self._ttl, view)

    def invalidate(self, tenant_id: str) -> None:
        self._data.pop(tenant_id, None)
