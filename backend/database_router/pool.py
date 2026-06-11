"""Per-tenant connection manager (PRD-P4-R2 E/I; D-13/D-30).

Lazy, bounded per-tenant pools keyed by (tenant_id, association_version) with LRU
idle eviction. A connection is bound to exactly one tenant for its lifetime and is
NEVER reused across tenants — separate keyed pools make a cross-tenant borrow
structurally impossible (the critical isolation correctness point).

Threading model (PRD-P4-R2 I): eviction is lazy/opportunistic on pool interaction,
not a background sweeper, so the suite stays stdlib-runnable on Python 3.8. Pool
operations are guarded by a lock. The clock is injectable for deterministic tests.
No credentials are held here — new connections are minted by a caller-supplied
`open_fn` (the router resolves the secret at connect time and discards it).
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Dict, List, Tuple

from .ports import TenantConnection


class PoolExhausted(Exception):
    """The per-tenant pool is at its bound and has no idle connection."""


class _Idle:
    __slots__ = ("conn", "last_used")

    def __init__(self, conn: TenantConnection, last_used: float) -> None:
        self.conn = conn
        self.last_used = last_used


class _Pool:
    def __init__(self, max_size: int) -> None:
        self.max_size = max_size
        self.idle: List[_Idle] = []
        self.in_use: set = set()


class ConnectionPoolManager:
    def __init__(
        self,
        *,
        max_per_tenant: int = 5,
        idle_timeout_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_per_tenant
        self._idle_timeout = idle_timeout_seconds
        self._clock = clock
        self._pools: Dict[Tuple[str, str], _Pool] = {}
        self._lock = threading.Lock()

    # -- acquisition / release -------------------------------------------------
    def acquire(
        self,
        tenant_id: str,
        association_version: str,
        open_fn: Callable[[], TenantConnection],
    ) -> TenantConnection:
        key = (tenant_id, association_version)
        with self._lock:
            self._evict_idle_locked()
            pool = self._pools.setdefault(key, _Pool(self._max))
            # Reuse a healthy idle connection for THIS tenant only.
            while pool.idle:
                idle = pool.idle.pop()
                if idle.conn.is_alive():
                    pool.in_use.add(idle.conn)
                    return idle.conn
                idle.conn.close()  # discard broken; never hand to another tenant
            if len(pool.in_use) >= pool.max_size:
                raise PoolExhausted("per-tenant pool exhausted")
            conn = open_fn()
            # Defense in depth: the minted connection must be bound to this key.
            if conn.tenant_id != tenant_id or conn.association_version != association_version:
                conn.close()
                raise PoolExhausted("connection bound to the wrong tenant/version")
            pool.in_use.add(conn)
            return conn

    def release(self, conn: TenantConnection) -> None:
        with self._lock:
            key = (conn.tenant_id, conn.association_version)
            pool = self._pools.get(key)
            if pool is None or conn not in pool.in_use:
                conn.close()
                return
            pool.in_use.discard(conn)
            try:
                conn.rollback()
                conn.reset()
            except Exception:
                conn.close()
                return
            if not conn.is_alive():
                conn.close()
                return
            pool.idle.append(_Idle(conn, self._clock()))
            self._evict_idle_locked()

    def discard(self, conn: TenantConnection) -> None:
        with self._lock:
            pool = self._pools.get((conn.tenant_id, conn.association_version))
            if pool is not None:
                pool.in_use.discard(conn)
            conn.close()

    def invalidate_version(self, tenant_id: str, keep_version: str) -> None:
        """Drain pools for `tenant_id` whose version != keep_version (re-association)."""
        with self._lock:
            for key in list(self._pools):
                if key[0] == tenant_id and key[1] != keep_version:
                    pool = self._pools.pop(key)
                    for idle in pool.idle:
                        idle.conn.close()
                    # in-use connections close on release (key no longer present)

    # -- maintenance / introspection ------------------------------------------
    def _evict_idle_locked(self) -> None:
        now = self._clock()
        for key in list(self._pools):
            pool = self._pools[key]
            keep: List[_Idle] = []
            for idle in pool.idle:
                if now - idle.last_used > self._idle_timeout:
                    idle.conn.close()
                else:
                    keep.append(idle)
            pool.idle = keep
            if not pool.idle and not pool.in_use:
                del self._pools[key]

    def pool_keys(self) -> List[Tuple[str, str]]:
        with self._lock:
            return list(self._pools.keys())

    def counts(self, tenant_id: str, association_version: str) -> Tuple[int, int]:
        """(idle, in_use) for a pool key — introspection for tests/metrics."""
        with self._lock:
            pool = self._pools.get((tenant_id, association_version))
            if pool is None:
                return (0, 0)
            return (len(pool.idle), len(pool.in_use))
