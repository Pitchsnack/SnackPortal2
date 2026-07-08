"""database_router composition (Build Phase 4).

Assembles the Database Router from config-selected providers. Tests/dev inject an
in-memory routing-read double, a fake connection factory, and a tenant SecretStore;
production injects the HTTP routing-read client + the psycopg connection factory
(under adapters/providers) and a tenant-credential SecretStore provider. Liveness is
static and non-disclosing. This is the ONLY service permitted to open tenant databases.

``build_router_from_env`` adds a config-selectable, INERT production-composition seam
mirroring the merged gateway seams (07E-3c/3d): a structurally valid internal
``SP2_DBR_ROUTING_READ_BASE_URL`` selects the production ``HttpRoutingRead`` client +
the psycopg connection factory + the env tenant-credential SecretStore and returns a
composed ``DatabaseRouter``; unset/empty keeps the caller's injected composition; a
malformed/off-scheme value fails closed (``ValueError``). The seam is inert — it opens
no connection, starts no service, and touches no physical database (construction only).
It composes ``build_router``'s default in-memory audit sink, so the composed router is
NOT production-durable; a durable routing-audit sink is a separate follow-on (DBR-AR-2).
This seam does NOT complete the Physical Multi-Database MVP or make Smoke C runnable.
"""

from __future__ import annotations

import os
from typing import Dict, Iterable, Optional
from urllib.parse import urlsplit

from shared.audit import OperationalAudit
from shared.secrets import SecretStore

from .adapters.providers.in_memory_audit_sink import InMemoryAuditSink
from .cache import RoutingViewCache
from .pool import ConnectionPoolManager
from .ports import ConnectionFactory, ControlPlaneRoutingReadPort
from .resolver import RoutingResolver
from .router import DatabaseRouter

SERVICE = "database_router"

# The config-selectable Database Router routing-read transport selector (mirrors the
# gateway SP2_GW_* / control_plane SP2_CP_* selector posture). The value is NON-SECRET
# internal routing config — the loopback/internal control-plane routing-read base URL,
# never a credential — so it is read directly from the environment (no SecretRef, no
# SecretStore). Unset/empty keeps the caller's injected (test/dev double) composition; a
# structurally valid internal http URL selects the production HttpRoutingRead client;
# anything else raises ValueError (fail closed — never a silent fallback from malformed
# production config to a double).
SP2_DBR_ROUTING_READ_BASE_URL = "SP2_DBR_ROUTING_READ_BASE_URL"


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


def build_router_from_env() -> Optional[DatabaseRouter]:
    """The config-selectable production composition seam (mirrors the merged gateway
    ``build_authenticator_from_env`` / ``build_router_dispatch_from_env`` seams).

    Assembles a production ``DatabaseRouter`` from environment configuration using the
    existing production adapters, and is INERT at construction: it opens no connection,
    performs no network I/O, calls no ``psycopg.connect``, and starts no service.

    Selection (the fail-closed env-selector pattern):

    * ``SP2_DBR_ROUTING_READ_BASE_URL`` unset, or empty/whitespace after stripping →
      ``None`` — the caller keeps its injected composition (tests/dev doubles unchanged).
    * a structurally valid internal ``http://host[:port]`` value → a ``DatabaseRouter``
      composed from ``HttpRoutingRead`` (bound to that base URL) + ``EnvTenantSecretStore``
      + ``PsycopgConnectionFactory``. The routing-read client is lazy: construction performs
      no network I/O; the control plane is reached only when the router later routes.
    * anything else → ``ValueError`` at the composition boundary — never a silent fallback
      from malformed production config to a double.

    Validation is structural only (``urlsplit`` scheme + netloc; the scheme is pinned to
    ``http`` — this is the internal loopback transport; TLS termination is deployment
    scope). ``HttpRoutingRead`` does not self-validate its base URL, so the check lives
    here at the composition boundary.

    Secret store: ``EnvTenantSecretStore()`` reads ``SNACKPORTAL_TENANT_SECRET_DIR`` (an
    infra-owned, deployment-pinned absolute path); the adapter's ``tenant/`` guard is
    preserved (composition cannot weaken it) and no in-slice secret-store hardening is
    performed. Audit: this seam composes ``build_router``'s default in-memory audit sink,
    so the composed router's routing audit is NON-durable — a durable routing-audit sink
    is a separate follow-on (DBR-AR-2). The bulk/interactive pool lanes (D-13) are
    preserved via ``build_router``'s defaults.

    No overclaim: this inert seam proves config-assembly of a production ``DatabaseRouter``;
    it does NOT open a physical database, start a running service, provide durable routing
    audit, complete the Physical Multi-Database MVP, or make Smoke C runnable. It is one
    prerequisite among several.
    """
    raw = (os.environ.get(SP2_DBR_ROUTING_READ_BASE_URL) or "").strip()
    if not raw:
        return None
    parts = urlsplit(raw)
    if parts.scheme != "http" or not parts.netloc:
        raise ValueError(
            f"unsupported {SP2_DBR_ROUTING_READ_BASE_URL}={raw!r}; expected an internal "
            "http://host[:port] control-plane routing-read base URL (fail closed — no silent fallback)"
        )
    # Lazy provider imports keep database_router/main.py driver-free at import: the psycopg
    # connection factory module binds the driver at load, so it is deferred to selection time.
    from .adapters.providers.env_tenant_secret_store import EnvTenantSecretStore
    from .adapters.providers.http_routing_read import HttpRoutingRead
    from .adapters.providers.psycopg_connection import PsycopgConnectionFactory

    return build_router(
        read=HttpRoutingRead(raw),
        secret_store=EnvTenantSecretStore(),
        connection_factory=PsycopgConnectionFactory(),
    )


def liveness() -> Dict[str, str]:
    # Static, non-disclosing liveness (no tenant/database detail).
    return {"service": SERVICE, "status": "alive", "build_phase": "4"}
