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

``build_dispatch_server_from_env`` is the paired follow-on: it composes an internal
Database Router dispatch **server object** from config — ``build_router_from_env()`` first
(router-gate: an unset selector returns ``None``), then the ``SP2_DBR_DISPATCH_HOST`` /
``SP2_DBR_DISPATCH_PORT`` knobs, then the existing ``build_dispatch_server`` adapter. It is
DB-inert and serve-inert (no serve loop, no thread, no ``route`` call, no ``psycopg.connect``),
but it is NOT socket-inert: when active, ``HTTPServer`` construction binds an ephemeral (default
port 0) local listening socket. It does not serve requests, run a service, open a physical
DB, or make Smoke C runnable.
"""

from __future__ import annotations

import os
from typing import Dict, Iterable, Optional, Tuple
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

# The dispatch-server bind knobs (paired follow-on). Non-secret internal config: the host
# and port the internal Gateway->Database-Router dispatch server binds. Both optional — the
# defaults are the loopback host and an ephemeral port (IC-010 §R internal-only surface).
# Only consulted when the router seam is active (SP2_DBR_ROUTING_READ_BASE_URL selected).
SP2_DBR_DISPATCH_HOST = "SP2_DBR_DISPATCH_HOST"
SP2_DBR_DISPATCH_PORT = "SP2_DBR_DISPATCH_PORT"


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


def _dispatch_port_from_env() -> int:
    """Parse ``SP2_DBR_DISPATCH_PORT`` fail-closed: unset/empty/whitespace → ``0`` (ephemeral);
    otherwise a base-10 integer in ``[0, 65535]``, else ``ValueError`` — raised BEFORE any socket
    bind so malformed config never opens a listener."""
    raw = (os.environ.get(SP2_DBR_DISPATCH_PORT) or "").strip()
    if not raw:
        return 0
    try:
        port = int(raw, 10)
    except ValueError:
        raise ValueError(f"invalid {SP2_DBR_DISPATCH_PORT}={raw!r}; expected an integer in [0, 65535]") from None
    if not (0 <= port <= 65535):
        raise ValueError(f"invalid {SP2_DBR_DISPATCH_PORT}={raw!r}; port out of range [0, 65535]")
    return port


def build_dispatch_server_from_env() -> Optional[Tuple[object, str]]:
    """The paired dispatch-server composition seam (follow-on to ``build_router_from_env``).

    Router-gate-first: compose the router via ``build_router_from_env()``; if the router
    selector (``SP2_DBR_ROUTING_READ_BASE_URL``) is inactive it returns ``None`` and this seam
    returns ``None`` WITHOUT consulting the dispatch knobs. When the router is composed, read the
    dispatch bind config and construct the server via the existing ``build_dispatch_server``
    adapter, returning ``(server, base_url)``.

    * ``SP2_DBR_ROUTING_READ_BASE_URL`` unset/empty → ``None`` (dispatch host/port unread). A
      malformed routing URL raises ``ValueError`` (inherited from ``build_router_from_env``).
    * ``SP2_DBR_DISPATCH_HOST`` — optional; unset/empty/whitespace → ``127.0.0.1`` (internal
      loopback, IC-010 §R); otherwise passed through (an unbindable host surfaces as ``OSError``
      from ``HTTPServer`` construction — deployment scope; no deep host validation here).
    * ``SP2_DBR_DISPATCH_PORT`` — optional; unset/empty → ``0`` (ephemeral); otherwise an integer
      in ``[0, 65535]``; non-integer / negative / out-of-range → ``ValueError`` raised BEFORE
      ``build_dispatch_server`` so a bad port never binds a socket.

    Side-effect boundary (LOAD-BEARING): this seam is DB-inert and serve-inert — it opens no
    connection, calls no ``route`` / ``psycopg.connect`` and performs no network client I/O, starts
    no serve loop, thread, daemon, or service. But it is NOT socket-inert: when active,
    ``build_dispatch_server`` constructs an ``HTTPServer`` which binds + activates a local listening
    socket at construction (default ``port=0`` → ephemeral). Callers/tests own the socket lifecycle
    and must close it.

    No overclaim: it composes a dispatch server *object* from config; it does NOT serve requests,
    run a production service, open a physical database, complete the Physical Multi-Database MVP,
    or make Smoke C runnable. It is one prerequisite among several.
    """
    router = build_router_from_env()
    if router is None:
        return None
    host = (os.environ.get(SP2_DBR_DISPATCH_HOST) or "").strip() or "127.0.0.1"
    port = _dispatch_port_from_env()
    # Lazy relative import keeps database_router/main.py import-light (http.server is pulled in
    # only when the seam is active); build_dispatch_server binds the ephemeral socket.
    from .adapters.providers.http_dispatch_api import build_dispatch_server

    return build_dispatch_server(router, host=host, port=port)


def liveness() -> Dict[str, str]:
    # Static, non-disclosing liveness (no tenant/database detail).
    return {"service": SERVICE, "status": "alive", "build_phase": "4"}
