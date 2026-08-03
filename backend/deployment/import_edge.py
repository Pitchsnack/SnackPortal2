"""Native ASGI application factory for the Import Service edge (the deployment composition root).

This module exists because ``import_service`` cannot compose two of its three collaborator ports
without violating the service-independence DAG (see ``deployment/__init__.py``). It is the ONLY
production module in the backend that imports more than one service package, and it does so purely
to wire objects together.

Canonical operator startup::

    uvicorn deployment.import_edge:create_app_from_env --factory --host 127.0.0.1 --port 8088 \\
      --workers 1 --no-access-log --no-server-header --no-proxy-headers

What is composed, and by whose seam (no wiring is re-derived here):

* ``RoutedSessionProvider`` — ``database_router.main.build_router_from_env`` builds the real
  ``DatabaseRouter`` (routing-read transport + reference-only tenant secret store + connection
  factory + routing-audit selection); it is wrapped in ``PgRoutedSessionProvider``. One routed
  tenant session therefore still resolves to EXACTLY ONE physical tenant database (IC-010 §K/§O;
  D-07) — this root introduces no new routing authority and selects no database itself.
* ``LineageEmitPort`` — ``lineage_service.emit.LineageEmit`` over the tenant-scoped secret store,
  with the ``"tenant"`` key prefix. Lineage semantics, the hash chain, and append-only behaviour are
  entirely the lineage service's; nothing is reimplemented here.
* ``DirectoryReadPort`` — selected inside import_service by
  ``import_service.main.build_directory_read_from_env`` from
  ``SP2_IMPORT_DIRECTORY_READ_BASE_URL``.
* the ``ImportService`` itself, the composed-core directory source, and the durable Import-audit
  sink — all by ``import_service.main.build_import_service_from_env``, the same single function the
  compatibility ``build_import_server_from_env`` seam uses.
* the ``FastAPI`` app — by ``import_service.adapters.providers.http_import_api.create_app``, the same
  public application seam ``build_import_server`` uses, so the route set and every fail-closed
  handler have one definition.

Fail closed (IC-010 §L): a missing routing selector, a missing tenant secret directory, a missing
directory-read selector, or a malformed value raises BEFORE anything is served. There is
deliberately NO fallback to an in-memory session provider, lineage double, or audit sink: the
standing Import path must always write through the real Database Router to a real physical tenant
database, with real lineage and a real durable audit trail.

Import-time inertness: nothing below runs at module import. Every service import inside the factory
is function-local, so importing this module reads no environment variable, opens no connection,
binds no socket, materializes no secret, and starts nothing.
"""

from __future__ import annotations

from fastapi import FastAPI

__all__ = ["create_app_from_env"]

# The lineage chain key prefix for tenant-resident lineage (the composed-core convention: the chain
# is per-tenant and never crosses tenants — D-25).
_LINEAGE_KEY_PREFIX = "tenant"


def create_app_from_env() -> FastAPI:
    """The CANONICAL native ASGI application factory for the Import Service edge.

    Takes NO arguments: the listening host and port belong to the runtime process, not to the
    application, so this factory binds no socket and owns no address. It returns the composed
    ``FastAPI`` app and nothing else.

    ONE composition path (no second composition root): every collaborator is built by the owning
    service's own published seam, and the app is built by ``http_import_api.create_app`` — the same
    seam the retained ``build_import_server`` compatibility path uses. No environment selector is
    parsed here that a service already parses.

    Fail closed: ``SP2_DBR_ROUTING_READ_BASE_URL`` unset/empty → ``RuntimeError``;
    ``SP2_IMPORT_DIRECTORY_READ_BASE_URL`` unset/empty → ``ValueError`` from the Import seam; any
    malformed value → ``ValueError`` (inherited). No in-memory substitute is ever composed.

    Per-tenant credentials are NOT pre-checked here. ``EnvTenantSecretStore`` accepts two sources —
    a per-reference environment variable, or a file under ``SNACKPORTAL_TENANT_SECRET_DIR`` — and it
    resolves them lazily, by reference, at first use. Demanding the directory at composition would
    duplicate the provider's own knowledge and would REJECT a valid environment-variable-only
    deployment. The provider raises on an unresolved reference, so the fail-closed guarantee is
    unchanged; it simply lands on the first request rather than at startup, exactly as it does for
    every other reference-only store in the backend.

    Import semantics are untouched: this composes the SAME ``ImportService`` with the SAME ports,
    routes, lineage, audit, and contract that the injected composition has always produced.
    """
    # Function-local service imports: this module stays inert at import, and the driver-bearing
    # provider modules are pulled in only when a real composition is actually requested.
    from database_router.adapters.providers.env_tenant_secret_store import EnvTenantSecretStore
    from database_router.main import build_router_from_env
    from database_router.session_provider import PgRoutedSessionProvider
    from import_service.adapters.providers.http_import_api import create_app
    from import_service.main import build_import_service_from_env
    from lineage_service.emit import LineageEmit

    router = build_router_from_env()
    if router is None:
        raise RuntimeError(
            "create_app_from_env: Import composition is INACTIVE — SP2_DBR_ROUTING_READ_BASE_URL is "
            "unset/empty, so no real Database Router can be composed (fail closed: no application "
            "composed; the Import path must never run without registry-authoritative routing)"
        )
    # The tenant secret store is reference-only and lazy: construction resolves nothing.
    tenant_secrets = EnvTenantSecretStore()
    service = build_import_service_from_env(
        session_provider=PgRoutedSessionProvider(router),
        lineage=LineageEmit(tenant_secrets, key_prefix=_LINEAGE_KEY_PREFIX),
    )
    return create_app(service)
