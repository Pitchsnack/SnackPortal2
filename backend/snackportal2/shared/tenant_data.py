"""Tenant data access for domain services (D-48).

Technical scaffolding only. This module knows how to *obtain* a tenant connection and how to
hold rows in memory for local development; it knows nothing about startups, investors, deals
or contacts. Each domain service owns its own SQL and its own field semantics.

**The D-48 model.** The Database Router remains the sole authority on which single physical
database a request may reach. What changed is custody: a tenant-resident domain service may
now hold the connection it opens, under a short-lived, single-tenant **grant** issued by the
router, and only if that service is on the router's explicit allowlist. The BFF and the
Access Control Service are never on it.

**The grant is not a credential a service keeps.** It is fetched per request, used, and
dropped. It is never logged, never returned to a caller, and never placed in an audit record
or an error message (D-48 C-3).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Iterator, List, Mapping, Optional, Protocol

from .errors import AppError, ErrorCode, tenant_unavailable

#: Internal Database Router base URL, per service. Non-secret internal configuration.
ENV_ROUTER_URL_TEMPLATE = "SP2_{service}_DATABASE_ROUTER_URL"

#: The internal credential the service presents when asking for a grant.
ENV_CREDENTIAL_TEMPLATE = "SP2_{service}_SERVICE_CREDENTIAL"

GRANT_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class TenantConnectionGrant:
    """One short-lived permission to open one tenant database.

    ``dsn`` is the only credential-bearing value anywhere in the rebuild's service layer, and
    it exists for the duration of a single request. Its ``__repr__`` is overridden because the
    default one would print it into any traceback that happened to include the object.
    """

    tenant_ref: str
    target_ref: str
    expected_schema_version: str
    dsn: str
    expires_at: str

    def __repr__(self) -> str:
        return "TenantConnectionGrant(tenant_ref=" + repr(self.tenant_ref) + ", dsn=<redacted>)"

    __str__ = __repr__


class GrantProvider(Protocol):
    """Obtain a connection grant for the request's single active tenant."""

    def grant_for(self, tenant_ref: Optional[str]) -> TenantConnectionGrant:
        ...


class NoGrantProvider:
    """The fail-closed default: no router configured, so no tenant database is reachable."""

    def grant_for(self, tenant_ref: Optional[str]) -> TenantConnectionGrant:
        del tenant_ref
        raise tenant_unavailable()


class RouterGrantProvider:
    """Ask the Database Router to bind one tenant database and issue a grant.

    Deliberately uncached. A cached grant would outlive the resolution that justified it, so a
    tenant disabled a moment ago would keep being served until the cache expired — and the
    router's fail-closed lifecycle check would be advisory rather than binding.
    """

    def __init__(self, base_url: str, credential: str, timeout: float = GRANT_TIMEOUT_SECONDS) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("database router base url must be an http(s) url")
        self._base_url = base_url.rstrip("/")
        self._credential = credential
        self._timeout = timeout

    def grant_for(self, tenant_ref: Optional[str]) -> TenantConnectionGrant:
        import httpx

        if not tenant_ref:
            raise tenant_unavailable()
        try:
            response = httpx.post(
                self._base_url + "/internal/routing/bind",
                headers={"Authorization": "Bearer " + self._credential},
                json={"tenant_ref": tenant_ref},
                timeout=self._timeout,
            )
        except Exception:
            raise tenant_unavailable() from None

        if response.status_code >= 400:
            # The router's canonical denial is propagated unchanged: re-coding it here would
            # let "not ready" quietly become "not found", which are different facts about a
            # tenant and are answered differently by the caller.
            body = response.json() if response.content else {}
            try:
                raise AppError(response.status_code, ErrorCode(body.get("code", "tenant_unavailable")))
            except ValueError:
                raise tenant_unavailable() from None

        body = response.json()
        return TenantConnectionGrant(
            tenant_ref=body["tenant_ref"],
            target_ref=body["target_ref"],
            expected_schema_version=body["expected_schema_version"],
            dsn=body["dsn"],
            expires_at=body["expires_at"],
        )


def build_grant_provider(service_key: str, env: Optional[Mapping[str, str]] = None) -> GrantProvider:
    """Select the grant provider from configuration, fail-closed by omission."""
    source: Mapping[str, str] = os.environ if env is None else env
    url = source.get(ENV_ROUTER_URL_TEMPLATE.format(service=service_key.upper()), "").strip()
    credential = source.get(ENV_CREDENTIAL_TEMPLATE.format(service=service_key.upper()), "").strip()
    if url and credential:
        return RouterGrantProvider(url, credential)
    return NoGrantProvider()


def open_tenant_connection(grant: TenantConnectionGrant) -> object:
    """Open the one connection this grant authorizes.

    A failure is ``tenant_unavailable`` — an outage of *this* tenant. It is never a reason to
    serve a different one and never a reason to reach the Control database.
    """
    import psycopg

    try:
        return psycopg.connect(grant.dsn)
    except Exception:
        raise tenant_unavailable() from None


class InMemoryTenantTable:
    """A tenant-partitioned row store for local development and tests.

    The partitioning is the isolation. Rows live under ``self._rows[tenant_ref]`` and no method
    reads two tenant buckets, so a cross-tenant read is not something this store can be asked
    to do incorrectly — it is something it cannot express.
    """

    def __init__(self) -> None:
        self._rows: Dict[str, Dict[str, Dict[str, Optional[str]]]] = {}
        self._counters: Dict[str, int] = {}

    def _bucket(self, tenant_ref: str) -> Dict[str, Dict[str, Optional[str]]]:
        return self._rows.setdefault(tenant_ref, {})

    def insert(self, tenant_ref: str, fields: Mapping[str, Optional[str]]) -> str:
        identity = str(self._counters.get(tenant_ref, 0) + 1)
        self._counters[tenant_ref] = int(identity)
        self._bucket(tenant_ref)[identity] = dict(fields)
        return identity

    def get(self, tenant_ref: str, identity: str) -> Optional[Dict[str, Optional[str]]]:
        stored = self._bucket(tenant_ref).get(identity)
        return dict(stored) if stored is not None else None

    def update(self, tenant_ref: str, identity: str, fields: Mapping[str, Optional[str]]) -> Optional[Dict[str, Optional[str]]]:
        stored = self._bucket(tenant_ref).get(identity)
        if stored is None:
            return None
        stored.update(fields)
        return dict(stored)

    def list(self, tenant_ref: str, limit: int) -> List[tuple[str, Dict[str, Optional[str]]]]:
        bucket = self._bucket(tenant_ref)
        identities = sorted(bucket, key=lambda identity: (len(identity), identity))[:limit]
        return [(identity, dict(bucket[identity])) for identity in identities]

    def iter_all(self, tenant_ref: str) -> Iterator[tuple[str, Dict[str, Optional[str]]]]:
        for identity, fields in self._bucket(tenant_ref).items():
            yield identity, dict(fields)


def compose_record_ref(tenant_ref: str, family: str, identity: str) -> str:
    """The opaque record reference a domain service exposes. Never a bare row primary key."""
    return "ref:" + tenant_ref + ":" + family + ":" + identity


def parse_record_ref(tenant_ref: str, family: str, record_ref: str) -> Optional[str]:
    """Recover the row identity, or ``None`` when the reference is not for this tenant/family.

    A reference minted for one tenant cannot be replayed against another: the tenant and family
    are part of the reference and are checked, not merely decorative.
    """
    prefix = "ref:" + tenant_ref + ":" + family + ":"
    if not record_ref.startswith(prefix):
        return None
    identity = record_ref[len(prefix) :]
    return identity or None


__all__ = [
    "ENV_CREDENTIAL_TEMPLATE",
    "ENV_ROUTER_URL_TEMPLATE",
    "GrantProvider",
    "InMemoryTenantTable",
    "NoGrantProvider",
    "RouterGrantProvider",
    "TenantConnectionGrant",
    "build_grant_provider",
    "compose_record_ref",
    "open_tenant_connection",
    "parse_record_ref",
]
