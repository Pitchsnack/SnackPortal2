"""Membership lookup — the only external read the Access Control Service performs.

It is a **references-only** read against the Control Plane (IC-014 §6): principal
reference in, boolean out. It is not a tenant-database read, and it cannot become one —
this module imports no database driver and holds no DSN, because "the service that decides
access must not be the service that has access".

Deliberately **uncached**. IC-014 §12 permits a bounded-TTL cache, but §8.4 requires that a
decision not depend on cache warmth or on which instance served it. Given a lookup this
cheap, correctness under §8.4 is worth more than the round trip a cache would save; if a
cache is added later it must fail closed on miss and invalidate per tenant (D-11).
"""

from __future__ import annotations

import os
from typing import Mapping, Optional, Protocol, Set, Tuple

#: The internal Control Plane base URL. Non-secret internal configuration, never a
#: credential. Unset means no lookup transport is configured.
ENV_CONTROL_PLANE_URL = "SP2_ACCESS_CONTROL_CONTROL_PLANE_URL"

#: The internal service credential presented to the Control Plane.
ENV_SERVICE_CREDENTIAL = "SP2_ACCESS_CONTROL_SERVICE_CREDENTIAL"

#: Development/test membership map: ``{"<principal_ref>": ["<tenant_ref>", ...]}``.
ENV_STATIC_MEMBERSHIPS = "SP2_ACCESS_CONTROL_STATIC_MEMBERSHIPS"

#: How long the Control Plane read may take before the answer becomes Denied (§8.2).
LOOKUP_TIMEOUT_SECONDS = 2.0


class MembershipPort(Protocol):
    """Is this principal a member of this tenant?"""

    def is_member(self, principal_ref: str, tenant_ref: str) -> bool: ...


class DenyAllMemberships:
    """The fail-closed default: with no lookup configured, nobody is a member of anything."""

    def is_member(self, principal_ref: str, tenant_ref: str) -> bool:
        del principal_ref, tenant_ref
        return False


class StaticMemberships:
    """A fixed membership map for local development and tests, selected only explicitly."""

    def __init__(self, memberships: Mapping[str, Set[str]]) -> None:
        self._pairs: Set[Tuple[str, str]] = {(principal, tenant) for principal, tenants in memberships.items() for tenant in tenants}

    def is_member(self, principal_ref: str, tenant_ref: str) -> bool:
        return (principal_ref, tenant_ref) in self._pairs

    @classmethod
    def from_json(cls, raw: str) -> "StaticMemberships":
        import json

        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("static membership configuration must be a JSON object")
        memberships: dict[str, Set[str]] = {}
        for principal, tenants in parsed.items():
            if not isinstance(tenants, list) or not all(isinstance(t, str) for t in tenants):
                raise ValueError("static membership entry must be a list of tenant references")
            memberships[principal] = set(tenants)
        return cls(memberships)


class HttpControlPlaneMemberships:
    """Read membership from the Control Plane over internal HTTP.

    Any failure — connection refused, timeout, non-200, malformed body — answers ``False``.
    That is not defensive coding; it is §8.2: an unavailable Control Plane read is one of
    the named conditions under which the answer is Denied.
    """

    def __init__(self, base_url: str, credential: str, timeout: float = LOOKUP_TIMEOUT_SECONDS) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("control plane base url must be an http(s) url")
        self._base_url = base_url.rstrip("/")
        self._credential = credential
        self._timeout = timeout

    def is_member(self, principal_ref: str, tenant_ref: str) -> bool:
        import httpx

        try:
            response = httpx.get(
                self._base_url + "/internal/memberships/" + principal_ref,
                headers={"Authorization": "Bearer " + self._credential},
                timeout=self._timeout,
            )
            if response.status_code != 200:
                return False
            body = response.json()
            memberships = body.get("memberships")
            if not isinstance(memberships, list):
                return False
            return any(isinstance(entry, dict) and entry.get("tenant_ref") == tenant_ref for entry in memberships)
        except Exception:
            return False


def build_membership_port(env: Optional[Mapping[str, str]] = None) -> MembershipPort:
    """Select the membership lookup from explicit configuration, fail-closed by omission."""
    source: Mapping[str, str] = os.environ if env is None else env

    base_url = source.get(ENV_CONTROL_PLANE_URL, "").strip()
    if base_url:
        credential = source.get(ENV_SERVICE_CREDENTIAL, "").strip()
        if not credential:
            raise ValueError("a configured control plane url requires a service credential")
        return HttpControlPlaneMemberships(base_url, credential)

    static = source.get(ENV_STATIC_MEMBERSHIPS, "").strip()
    if static:
        return StaticMemberships.from_json(static)

    return DenyAllMemberships()


__all__ = [
    "ENV_CONTROL_PLANE_URL",
    "ENV_SERVICE_CREDENTIAL",
    "ENV_STATIC_MEMBERSHIPS",
    "DenyAllMemberships",
    "HttpControlPlaneMemberships",
    "MembershipPort",
    "StaticMemberships",
    "build_membership_port",
]
