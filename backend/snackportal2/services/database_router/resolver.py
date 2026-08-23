"""Tenant-to-database resolution — one request, one active tenant, one physical database.

    input:   a validated active tenant reference (the signed claim)
    output:  exactly one physical database target, or a fail-closed denial

Six failure modes, all closing the same way and none of them reaching the Control database:

    known tenant          -> resolves
    unknown tenant        -> consistent denial (indistinguishable from unauthorized)
    disabled tenant       -> not ready
    missing mapping       -> unavailable
    unavailable mapping   -> unavailable
    any of the above      -> NEVER the Control DB

There is no Control-DB fallback anywhere in this module, and the resolution function has no
branch capable of returning one. "ACME database unavailable" is an outage, not a redirect.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Mapping, Optional, Protocol

from ...shared.errors import AppError, consistent_tenant_denial, tenant_not_ready, tenant_unavailable
from ...shared.types import TenantLifecycleState

#: Internal Control Plane base URL — non-secret internal configuration.
ENV_CONTROL_PLANE_URL = "SP2_DATABASE_ROUTER_CONTROL_PLANE_URL"

#: Internal service credential presented to the Control Plane.
ENV_SERVICE_CREDENTIAL = "SP2_DATABASE_ROUTER_SERVICE_CREDENTIAL"

#: Prefix for tenant DSN entries in the environment-backed secret store.
ENV_TENANT_DSN_PREFIX = "SP2_TENANT_DSN_"

CONTROL_PLANE_TIMEOUT_SECONDS = 2.0

_UNSAFE_ENV_CHARS = re.compile(r"[^A-Z0-9]")


@dataclass(frozen=True)
class TenantRegistryEntry:
    """What the registry says about a tenant. References only."""

    tenant_ref: str
    lifecycle_state: TenantLifecycleState
    expected_schema_version: str
    association_store_ref: str
    association_version: str


class TenantRegistry(Protocol):
    """Registry-authoritative tenant lookup (D-07 / D-30)."""

    def lookup(self, tenant_ref: str) -> Optional[TenantRegistryEntry]: ...


class TenantSecretStore(Protocol):
    """Turns a secret-store *reference* into a connection string.

    This is the one place in the system where a reference becomes a credential, which is
    exactly why it lives inside the only service permitted to open a tenant database.
    """

    def resolve(self, store_ref: str, version: str) -> Optional[str]: ...


class StaticTenantRegistry:
    """A fixed registry for local development and tests."""

    def __init__(self, entries: Mapping[str, TenantRegistryEntry]) -> None:
        self._entries = dict(entries)

    def lookup(self, tenant_ref: str) -> Optional[TenantRegistryEntry]:
        return self._entries.get(tenant_ref)


class HttpControlPlaneRegistry:
    """Read the registry from the Control Plane over internal HTTP.

    A failed read resolves nothing. It does not fall back to a cached entry, a default
    tenant, or the Control database — an unreachable registry means the router cannot know
    which single database is correct, and guessing is the one outcome isolation forbids.
    """

    def __init__(self, base_url: str, credential: str, timeout: float = CONTROL_PLANE_TIMEOUT_SECONDS) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("control plane base url must be an http(s) url")
        self._base_url = base_url.rstrip("/")
        self._credential = credential
        self._timeout = timeout

    def lookup(self, tenant_ref: str) -> Optional[TenantRegistryEntry]:
        import httpx

        try:
            response = httpx.get(
                self._base_url + "/internal/tenants/" + tenant_ref,
                headers={"Authorization": "Bearer " + self._credential},
                timeout=self._timeout,
            )
            if response.status_code != 200:
                return None
            body = response.json()
            association = body["database_association_ref"]
            return TenantRegistryEntry(
                tenant_ref=body["tenant_ref"],
                lifecycle_state=TenantLifecycleState(body["lifecycle_state"]),
                expected_schema_version=body["expected_schema_version"],
                association_store_ref=association["store_ref"],
                association_version=association["version"],
            )
        except Exception:
            return None


class EnvironmentTenantSecretStore:
    """Resolve a tenant DSN from the environment, keyed by reference.

    Portable and vendor-neutral: the same lookup shape works against a cloud secret manager
    later without changing a caller, because callers only ever hold the reference.
    """

    def __init__(self, env: Optional[Mapping[str, str]] = None) -> None:
        self._env: Mapping[str, str] = os.environ if env is None else env

    @staticmethod
    def variable_name(store_ref: str, version: str) -> str:
        safe = _UNSAFE_ENV_CHARS.sub("_", (store_ref + "_" + version).upper())
        return ENV_TENANT_DSN_PREFIX + safe

    def resolve(self, store_ref: str, version: str) -> Optional[str]:
        value = self._env.get(self.variable_name(store_ref, version), "").strip()
        return value or None


@dataclass(frozen=True)
class ResolvedTarget:
    """One bound physical database. ``target_ref`` is what leaves the service; ``dsn`` never does."""

    tenant_ref: str
    target_ref: str
    expected_schema_version: str
    dsn: str


class TenantResolver:
    """Resolve exactly one physical tenant database, or fail closed."""

    def __init__(self, registry: TenantRegistry, secrets: TenantSecretStore) -> None:
        self._registry = registry
        self._secrets = secrets

    def resolve(self, tenant_ref: Optional[str]) -> ResolvedTarget:
        """Bind one database from the signed claim, or raise the canonical denial.

        The router never re-derives the tenant. It is handed one, and it either binds that
        one or binds nothing.
        """
        if not tenant_ref:
            # A tenantless context has no tenant database. This is not an error to explain;
            # there is simply nothing to route to, and no default to fall back on.
            raise consistent_tenant_denial()

        entry = self._registry.lookup(tenant_ref)
        if entry is None:
            # Unknown tenant and unauthorized tenant answer identically (IC-013 §12).
            raise consistent_tenant_denial()

        if entry.lifecycle_state is not TenantLifecycleState.ACTIVE:
            # Provisioning, suspended and disabled all mean "not now", and all say so the
            # same way. The state itself is disclosed to internal callers only.
            raise tenant_not_ready()

        dsn = self._secrets.resolve(entry.association_store_ref, entry.association_version)
        if not dsn:
            # The registry names an association the secret store cannot produce. That is an
            # outage of this tenant, not a licence to serve a different one.
            raise tenant_unavailable()

        return ResolvedTarget(
            tenant_ref=entry.tenant_ref,
            target_ref="ref:tenant/" + entry.tenant_ref + "/database",
            expected_schema_version=entry.expected_schema_version,
            dsn=dsn,
        )


def build_registry(env: Optional[Mapping[str, str]] = None) -> TenantRegistry:
    """Select the registry transport. With no Control Plane configured, nothing resolves."""
    source: Mapping[str, str] = os.environ if env is None else env
    base_url = source.get(ENV_CONTROL_PLANE_URL, "").strip()
    if base_url:
        credential = source.get(ENV_SERVICE_CREDENTIAL, "").strip()
        if not credential:
            raise ValueError("a configured control plane url requires a service credential")
        return HttpControlPlaneRegistry(base_url, credential)
    return StaticTenantRegistry({})


__all__ = [
    "ENV_CONTROL_PLANE_URL",
    "ENV_SERVICE_CREDENTIAL",
    "ENV_TENANT_DSN_PREFIX",
    "AppError",
    "EnvironmentTenantSecretStore",
    "HttpControlPlaneRegistry",
    "ResolvedTarget",
    "StaticTenantRegistry",
    "TenantRegistry",
    "TenantRegistryEntry",
    "TenantResolver",
    "TenantSecretStore",
]
