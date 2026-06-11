"""Stdlib test doubles for database_router (no DB driver, no network).

Provides an in-memory routing-read port, a fake tenant connection + factory, a fake
tenant SecretStore, an audit sink, an injectable clock, and a wiring helper so the
router's routing/isolation/lifecycle behaviour is exercised end-to-end without the
production psycopg / HTTP providers.
"""

from __future__ import annotations

import pathlib
import sys
from typing import Dict, List, Optional, Tuple

_BACKEND = pathlib.Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from database_router.cache import RoutingViewCache  # noqa: E402
from database_router.models import TenantRoutingView  # noqa: E402
from database_router.pool import ConnectionPoolManager  # noqa: E402
from database_router.ports import (  # noqa: E402
    ConnectionFactory,
    ControlPlaneRoutingReadPort,
    TenantConnection,
)
from database_router.resolver import RoutingResolver  # noqa: E402
from database_router.router import DatabaseRouter  # noqa: E402
from shared.audit import OperationalAudit, OperationalAuditEvent  # noqa: E402
from shared.secrets import SecretRef, SecretStore, SecretValue  # noqa: E402


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class FakeRoutingRead(ControlPlaneRoutingReadPort):
    def __init__(self, available: bool = True) -> None:
        self._available = available
        self._views: Dict[str, TenantRoutingView] = {}
        self.calls = 0

    def set_view(
        self,
        tenant_id: str,
        *,
        lifecycle: str = "Ready",
        ready: bool = True,
        store_ref: Optional[str] = None,
        version: str = "1",
        schema: str = "1",
    ) -> None:
        self._views[tenant_id] = TenantRoutingView(
            tenant_id=tenant_id,
            lifecycle_state=lifecycle,
            ready=ready,
            database_association_ref=SecretRef(store_ref or f"tenant/{tenant_id}/db", version),
            expected_schema_version=schema,
        )

    def remove(self, tenant_id: str) -> None:
        self._views.pop(tenant_id, None)

    def set_unavailable(self) -> None:
        self._available = False

    def set_available(self) -> None:
        self._available = True

    def get_routing_view(self, tenant_id: str) -> Optional[TenantRoutingView]:
        self.calls += 1
        if not self._available:
            raise RuntimeError("control plane unavailable")
        return self._views.get(tenant_id)


class FakeConnection(TenantConnection):
    _counter = 0

    def __init__(self, tenant_id: str, association_version: str) -> None:
        FakeConnection._counter += 1
        self.id = FakeConnection._counter
        self._tenant_id = tenant_id
        self._association_version = association_version
        self._alive = True
        self.closed = False
        self.in_transaction = False
        self.rolled_back = 0
        self.reset_count = 0
        self.executed: list = []

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    @property
    def association_version(self) -> str:
        return self._association_version

    def is_alive(self) -> bool:
        return self._alive and not self.closed

    def begin(self) -> None:
        self.in_transaction = True

    def commit(self) -> None:
        self.in_transaction = False

    def rollback(self) -> None:
        self.in_transaction = False
        self.rolled_back += 1

    def reset(self) -> None:
        self.reset_count += 1

    def close(self) -> None:
        self.closed = True
        self._alive = False

    def break_it(self) -> None:
        self._alive = False

    def execute(self, statement: str, params: tuple = ()) -> None:
        self.executed.append((statement, params))

    def query(self, statement: str, params: tuple = ()) -> list:
        return []


class FakeConnectionFactory(ConnectionFactory):
    def __init__(self) -> None:
        self.opens: List[Tuple[str, str]] = []
        self.descriptors: List[str] = []
        self.fail_tenants: set = set()
        self.misbind = False

    def fail_for(self, tenant_id: str) -> None:
        self.fail_tenants.add(tenant_id)

    def open(self, tenant_id: str, association_version: str, descriptor: str) -> TenantConnection:
        self.opens.append((tenant_id, association_version))
        self.descriptors.append(descriptor)
        if tenant_id in self.fail_tenants:
            raise RuntimeError("connection failed")
        if self.misbind:
            return FakeConnection("evil-other-tenant", association_version)
        return FakeConnection(tenant_id, association_version)


class FakeSecretStore(SecretStore):
    def __init__(self) -> None:
        self.resolved: List[SecretRef] = []
        self.missing: set = set()

    def set_missing(self, store_ref: str) -> None:
        self.missing.add(store_ref)

    def resolve(self, ref: SecretRef) -> SecretValue:
        self.resolved.append(ref)
        if ref.store_ref in self.missing:
            raise LookupError("unresolved")
        return SecretValue(material=f"descriptor::{ref.store_ref}@{ref.version}")

    def current_version(self, store_ref: str) -> str:
        return "1"


class FakeAudit(OperationalAudit):
    def __init__(self) -> None:
        self.events: List[OperationalAuditEvent] = []

    def initiate(self, event: OperationalAuditEvent) -> None:
        self.events.append(event)

    def actions(self) -> List[str]:
        return [e.action for e in self.events]

    def outcomes(self) -> List[str]:
        return [e.outcome for e in self.events]


def make_router(
    *,
    read: FakeRoutingRead,
    secret_store: SecretStore,
    factory: ConnectionFactory,
    audit: OperationalAudit,
    supported=("1",),
    ttl: float = 15.0,
    max_per_tenant: int = 5,
    idle_timeout: float = 60.0,
    clock=None,
):
    clk = clock or (lambda: 0.0)
    cache = RoutingViewCache(ttl_seconds=ttl, clock=clk)
    resolver = RoutingResolver(read, cache, supported_schema_versions=supported)
    pool = ConnectionPoolManager(max_per_tenant=max_per_tenant, idle_timeout_seconds=idle_timeout, clock=clk)
    router = DatabaseRouter(
        resolver=resolver,
        pool=pool,
        secret_store=secret_store,
        connection_factory=factory,
        audit=audit,
    )
    return router, cache, pool, resolver
