"""database_router composition (Build Phase 4).

Assembles the Database Router from config-selected providers. Tests/dev inject an
in-memory routing-read double, a fake connection factory, and a tenant SecretStore;
production injects the HTTP routing-read client + the psycopg connection factory
(under adapters/providers) and a tenant-credential SecretStore provider. Liveness is
static and non-disclosing. This is the ONLY service permitted to open tenant databases.
"""

from __future__ import annotations

from typing import Dict, Iterable, Optional

from shared.audit import OperationalAudit
from shared.secrets import SecretStore

from .adapters.providers.in_memory_audit_sink import InMemoryAuditSink
from .cache import RoutingViewCache
from .pool import ConnectionPoolManager
from .ports import ConnectionFactory, ControlPlaneRoutingReadPort
from .resolver import RoutingResolver
from .router import DatabaseRouter

SERVICE = "database_router"


def build_router(
    *,
    read: ControlPlaneRoutingReadPort,
    secret_store: SecretStore,
    connection_factory: ConnectionFactory,
    audit: Optional[OperationalAudit] = None,
    supported_schema_versions: Iterable[str] = ("1",),
    cache_ttl_seconds: float = 15.0,
    max_per_tenant: int = 5,
    bulk_max_per_tenant: int = 2,
    idle_timeout_seconds: float = 60.0,
) -> DatabaseRouter:
    cache = RoutingViewCache(ttl_seconds=cache_ttl_seconds)
    resolver = RoutingResolver(read, cache, supported_schema_versions=supported_schema_versions)
    pool = ConnectionPoolManager(max_per_tenant=max_per_tenant, idle_timeout_seconds=idle_timeout_seconds)
    # Separate bounded capacity so bulk/import workloads cannot starve interactive traffic (D-13).
    bulk_pool = ConnectionPoolManager(max_per_tenant=bulk_max_per_tenant, idle_timeout_seconds=idle_timeout_seconds)
    return DatabaseRouter(
        resolver=resolver,
        pool=pool,
        secret_store=secret_store,
        connection_factory=connection_factory,
        audit=audit or InMemoryAuditSink(),
        bulk_pool=bulk_pool,
    )


def liveness() -> Dict[str, str]:
    # Static, non-disclosing liveness (no tenant/database detail).
    return {"service": SERVICE, "status": "alive", "build_phase": "4"}
