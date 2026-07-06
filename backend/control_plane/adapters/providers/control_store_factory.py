"""Per-unit-of-work ControlStore factory (PRD 07D-3b — Tier-2 / AT-PMV46-4 closure).

One logical request (unit of work) → one ``ControlStore`` instance → one Control-DB
connection, held for the whole unit of work and released (rollback + close) at its end.
This is the boundary that makes in-process concurrent requests safe: a transition's CAS
stays UNCOMMITTED until its audit append commits both on the SAME connection (PRD 07D-2e),
so two logical requests sharing one store/connection would cross-commit / cross-rollback
each other's work. The factory guarantees they never share one.

**The 07E transport contract:** every request transport MUST acquire a fresh ControlStore
unit of work per request (``factory.acquire()`` / ``ControlPlane.control_store_unit_of_work()``)
and MUST NOT share it across concurrent requests.

Connection scoping is **connect-per-unit-of-work** (the D-3b-1a fallback, adopted with
proof): ``psycopg_pool`` is NOT a declared dependency — ``backend/pyproject.toml`` pins
``psycopg[binary]>=3`` only, and ``psycopg-pool`` is a separate distribution — so pooling
would require a dependency/envelope widening. The control plane is low-frequency (tenant
lifecycle operations), so a fresh connection per unit of work is ample, keeps the slice
tight, and gives connection health by construction (AT-07D3A-4): a broken connection dies
with its own unit of work and can never poison a later one. Standard PostgreSQL only; no
external pooler; a pool remains a 07E-era optimization if load ever warrants it.

Driver containment: this module imports NO database driver at module load — the
``PostgresControlStore`` import is function-local (the same discipline as the composition
root), so importing this factory binds no driver.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator, Optional

from control_plane.ports import ControlStore
from shared.secrets import SecretRef, SecretStore

if TYPE_CHECKING:  # driver-free at runtime; the store import stays function-local
    from control_plane.adapters.providers.postgres_store import PostgresControlStore


class SharedControlStoreFactory:
    """Yields ONE process-local store for every unit of work.

    For the in-memory composition (and explicit ``store=`` constructor injection) the
    store's state lives in the instance itself, so every unit of work must see the same
    object — this factory is the single-process shape of the per-UoW boundary. Tier-2
    connection scoping is a durable-path property; the durable counterpart is
    ``PostgresControlStoreFactory``.
    """

    def __init__(self, store: ControlStore) -> None:
        self._store = store

    @contextmanager
    def acquire(self) -> Iterator[ControlStore]:
        yield self._store


class PostgresControlStoreFactory:
    """Issues a FRESH lazily-connecting ``PostgresControlStore`` per unit of work.

    Dual construction mirrors the store (references only, D-14): a literal ``dsn=``
    descriptor (live harnesses) OR ``secrets=`` + ``ref=`` (the composition root — no DSN
    literal transits it). Construction performs NO I/O; each unit of work's connection
    opens lazily on its first store operation and FAILS CLOSED there (unresolvable ref /
    unreachable Control DB reject the operation). On unit-of-work exit — normal or
    exceptional — the store is released: any open transaction is rolled back and the
    connection is closed, so uncommitted work is discarded fail-closed and no open
    transaction can leak into a later unit of work (AT-07D3A-3 boundary guarantee).
    """

    def __init__(
        self,
        dsn: Optional[str] = None,
        *,
        secrets: Optional[SecretStore] = None,
        ref: Optional[SecretRef] = None,
    ) -> None:
        # Same fail-closed validation as PostgresControlStore (exactly one source), applied
        # eagerly so a misconfigured factory rejects at composition time, not first request.
        if (dsn is None) == (ref is None):
            raise ValueError("PostgresControlStoreFactory requires exactly one of dsn= or (secrets=, ref=)")
        if ref is not None and secrets is None:
            raise ValueError("PostgresControlStoreFactory ref= requires a SecretStore (secrets=)")
        self._dsn = dsn
        self._secrets = secrets
        self._ref = ref

    @contextmanager
    def acquire(self) -> Iterator["PostgresControlStore"]:
        from control_plane.adapters.providers.postgres_store import PostgresControlStore  # driver containment

        store = PostgresControlStore(self._dsn, secrets=self._secrets, ref=self._ref)
        try:
            yield store
        finally:
            store.release()  # rollback any open transaction + close; idempotent
