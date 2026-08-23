"""Per-tenant lineage chain-key resolution — the internal secret surface for D-23.

A D-23 integrity marker is a **keyed** HMAC, and the key is per tenant. Something therefore
has to turn a tenant reference into secret material, and that something is deliberately small,
internal, and confined to this module.

**What this is not.** It is not an API. No route accepts a key, no response returns one, no
Pydantic model names one, and nothing here appears in a generated OpenAPI document. It is not
a general secret store either — it resolves exactly one kind of secret, so "where can a secret
be resolved?" has one filename as its answer.

**Fail closed, per tenant.** A tenant whose key is absent, empty, or too short to be a key
resolves to nothing at all, and the caller cannot write lineage for that tenant. There is no
default key, no shared key, and no placeholder: a single fallback key would make every
tenant's chain verifiable with one secret, which is the opposite of a per-tenant chain.

**Portability.** Callers hold a *tenant reference*, never a location. The environment-backed
implementation below is the local and test resolver; a cloud secret manager can replace it
later by implementing the same protocol, with no call site changed (D-14's reference model,
and the same shape :class:`~snackportal2.services.database_router.resolver.TenantSecretStore`
already uses for tenant DSNs).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Mapping, Optional, Protocol

from .errors import tenant_unavailable

#: Environment variable prefix for a tenant's lineage chain key: ``SP2_LINEAGE_KEY_ACME``.
ENV_LINEAGE_KEY_PREFIX = "SP2_LINEAGE_KEY_"

#: The shortest value accepted as a chain key.
#:
#: Not cryptographic policy — configuration validation. HMAC accepts a key of any length and
#: reports nothing about its quality, so a placeholder like ``"x"`` or ``"changeme"`` would
#: produce a perfectly well-formed marker that proves nothing. A floor turns "the key is
#: missing" and "the key is a placeholder" into the same fail-closed outcome.
MINIMUM_KEY_CHARACTERS = 32

_UNSAFE_ENV_CHARS = re.compile(r"[^A-Z0-9]")


@dataclass(frozen=True)
class LineageChainKey:
    """Resolved chain-key material for exactly one tenant.

    A wrapper rather than bare ``bytes`` for one reason: bare bytes cannot protect their own
    ``repr``, and a lineage key that reaches a traceback has leaked. ``__repr__`` and
    ``__str__`` are both overridden — the same treatment
    :class:`~snackportal2.shared.tenant_data.TenantConnectionGrant` gives a DSN — so an
    exception rendering its arguments discloses the tenant and nothing else.

    Held for the duration of one write and then dropped. Nothing caches it.
    """

    tenant_ref: str
    material: bytes = field(repr=False)

    def __repr__(self) -> str:
        return "LineageChainKey(tenant_ref=" + repr(self.tenant_ref) + ", material=<redacted>)"

    __str__ = __repr__


class LineageKeyResolver(Protocol):
    """Resolve one tenant's lineage chain key, or fail closed.

    Implementations MUST NOT return ``None``, empty material, a placeholder, or a shared
    default for a tenant whose key is not configured. The only lawful answers are *this
    tenant's key* and *a denial*.
    """

    def resolve_lineage_key(self, tenant_ref: str) -> LineageChainKey:
        ...


class EnvironmentLineageKeyResolver:
    """Resolve a tenant's chain key from the environment.

    Keys are per tenant by construction: the variable name is derived from the tenant
    reference, so two tenants cannot share a key unless someone deliberately configures the
    same value twice — and even then they remain two separately-named secrets that can be
    rotated apart.
    """

    def __init__(self, env: Optional[Mapping[str, str]] = None) -> None:
        self._env: Mapping[str, str] = os.environ if env is None else env

    @staticmethod
    def variable_name(tenant_ref: str) -> str:
        """``acme`` -> ``SP2_LINEAGE_KEY_ACME``. Sanitized the way tenant DSN references are."""
        return ENV_LINEAGE_KEY_PREFIX + _UNSAFE_ENV_CHARS.sub("_", tenant_ref.upper())

    def resolve_lineage_key(self, tenant_ref: str) -> LineageChainKey:
        """This tenant's key, or the canonical unavailable denial.

        ``tenant_unavailable`` rather than a new code: a tenant whose provenance key cannot be
        resolved cannot lawfully be written to, which is an outage of that one tenant. It is
        never a reason to write the row without lineage, and never a reason to reach another
        tenant or the Control database. No new public denial code is introduced (IC-014 §8.3),
        and the denial names no variable, no location, and no secret state.
        """
        if not tenant_ref:
            raise tenant_unavailable()
        value = self._env.get(self.variable_name(tenant_ref), "").strip()
        if len(value) < MINIMUM_KEY_CHARACTERS:
            # Covers absent, empty, whitespace-only and placeholder values in one branch, so
            # none of them can be handled "leniently" by a later edit to just one of them.
            raise tenant_unavailable()
        return LineageChainKey(tenant_ref=tenant_ref, material=value.encode("utf-8"))


def build_lineage_key_resolver(env: Optional[Mapping[str, str]] = None) -> LineageKeyResolver:
    """The configured resolver. With nothing configured, every tenant fails closed."""
    return EnvironmentLineageKeyResolver(env)


__all__ = [
    "ENV_LINEAGE_KEY_PREFIX",
    "MINIMUM_KEY_CHARACTERS",
    "EnvironmentLineageKeyResolver",
    "LineageChainKey",
    "LineageKeyResolver",
    "build_lineage_key_resolver",
]
