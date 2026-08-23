"""The grant allowlist (D-48 C-1) — who may be handed a tenant connection at all.

Two services are **permanently excluded**, and the exclusion is enforced at configuration
time rather than at request time so that a misconfiguration fails on startup instead of
silently widening the blast radius:

* the **BFF**, because it is the public ingress — the whole point of the exposure model is
  that the process nearest the internet is the furthest from a credential; and
* the **Access Control Service**, because IC-014 §6 is absolute: the service that decides
  access must not be the service that has access.

Everything else about the allowlist is ordinary: a credential maps to a service reference,
and a caller whose credential is absent is refused even though the credential is otherwise
valid for talking to this router.
"""

from __future__ import annotations

import json
import os
from typing import Dict, FrozenSet, Mapping, Optional

#: Credential -> service reference, as JSON: ``{"<credential>": "<service_ref>"}``.
ENV_GRANTEES = "SP2_DATABASE_ROUTER_GRANTEES"

#: The tenant-resident services that may legitimately hold a tenant connection.
TENANT_RESIDENT_SERVICES: FrozenSet[str] = frozenset({"startups", "investors", "deals", "contacts", "lineage", "import_service", "sharing"})

#: Never grantees, in any environment, for any reason (D-48 C-1).
PERMANENTLY_EXCLUDED: FrozenSet[str] = frozenset({"bff", "access_control", "authentication", "control_plane", "audit"})

#: How long a grant is valid. Short, because it authorizes one request's worth of work.
GRANT_TTL_SECONDS = 60


class GrantAllowlist:
    """Resolves a presented credential to the service reference it is allowed to act as."""

    def __init__(self, grantees: Mapping[str, str]) -> None:
        for credential, service_ref in grantees.items():
            del credential
            if service_ref in PERMANENTLY_EXCLUDED:
                raise ValueError(service_ref + " may never receive a tenant connection grant (D-48 C-1)")
            if service_ref not in TENANT_RESIDENT_SERVICES:
                raise ValueError(service_ref + " is not a tenant-resident service and cannot hold a tenant connection")
        self._grantees = dict(grantees)

    def service_for(self, credential: str) -> Optional[str]:
        """The service this credential may act as, or ``None`` — which means refused."""
        return self._grantees.get(credential)

    def service_refs(self) -> list[str]:
        """The allowed service references, sorted. Never the credentials."""
        return sorted(set(self._grantees.values()))

    @classmethod
    def from_json(cls, raw: str) -> "GrantAllowlist":
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("grantee configuration must be a JSON object")
        grantees: Dict[str, str] = {}
        for credential, service_ref in parsed.items():
            if not isinstance(service_ref, str) or not service_ref:
                raise ValueError("each grantee entry must map a credential to a service reference")
            grantees[credential] = service_ref
        return cls(grantees)


def build_allowlist(env: Optional[Mapping[str, str]] = None) -> GrantAllowlist:
    """Build the allowlist from configuration; empty (granting nothing) by omission."""
    source: Mapping[str, str] = os.environ if env is None else env
    raw = source.get(ENV_GRANTEES, "").strip()
    if raw:
        return GrantAllowlist.from_json(raw)
    return GrantAllowlist({})


__all__ = [
    "ENV_GRANTEES",
    "GRANT_TTL_SECONDS",
    "PERMANENTLY_EXCLUDED",
    "TENANT_RESIDENT_SERVICES",
    "GrantAllowlist",
    "build_allowlist",
]
