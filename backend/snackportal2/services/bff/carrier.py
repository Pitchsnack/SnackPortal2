"""Carrier extraction — exactly two recognized tenant carriers, and nothing else.

Re-homed from IC-010 §E to IC-013 §5. Phase 0 identified this as one of four behaviours
that lived only inside the Gateway: deleting the Gateway without re-homing this section
would have silently removed tenant-carrier enforcement altogether.

The two carriers are the **tenant subdomain** and the **``X-Tenant-Id`` header**. Everything
else — cookies, query-string parameters, portal state, workspace state, client local storage
— is **prohibited as routing authority** and is never read as a tenant selector by any
component, for any purpose, including token issuance.

A carrier is match-or-reject only. It is never authorization, and it never selects a
database: the signed tenant claim remains the sole routing authority.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Optional

#: The one recognized carrier header (case-insensitive).
TENANT_HEADER = "X-Tenant-Id"

#: Header names that look tenant-ish and are deliberately NOT carriers. They are listed so
#: the test suite can assert each is ignored, rather than relying on the absence of code.
NON_CARRIER_HEADERS = (
    "X-Tenant",
    "X-Tenant-Ref",
    "X-Active-Tenant",
    "X-Workspace",
    "X-Workspace-Id",
    "X-Forwarded-Host",
    "X-Original-Host",
)

#: A carrier value is opaque and bounded. It is compared, never parsed or resolved.
_CARRIER_VALUE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")

#: Hosts whose first label is never a tenant.
_RESERVED_SUBDOMAINS = frozenset({"www", "api", "app", "localhost", "control"})


def carrier_from_header(headers: Mapping[str, str]) -> Optional[str]:
    """Read ``X-Tenant-Id`` and nothing else.

    Case-insensitive on the name, strict on the value: a malformed value is treated as
    absent rather than passed on, so it can never reach a comparison as a partial match.
    """
    wanted = TENANT_HEADER.casefold()
    for name, value in headers.items():
        if name.casefold() == wanted:
            candidate = value.strip()
            return candidate if _CARRIER_VALUE.match(candidate) else None
    return None


def carrier_from_host(host: str, base_domain: str = "") -> Optional[str]:
    """Read the tenant subdomain, if the host actually has one under the base domain.

    Requires an explicitly configured ``base_domain``. Without one, host-based addressing is
    off: guessing which label of an arbitrary host is "the tenant" would make the carrier
    depend on deployment topology, and a carrier that changes meaning with topology is not a
    carrier, it is an accident waiting to match.
    """
    if not base_domain:
        return None
    hostname = host.split(":", 1)[0].strip().casefold()
    suffix = "." + base_domain.strip().casefold().lstrip(".")
    if not hostname.endswith(suffix):
        return None
    label = hostname[: -len(suffix)]
    if not label or "." in label or label in _RESERVED_SUBDOMAINS:
        return None
    return label if _CARRIER_VALUE.match(label) else None


@dataclass(frozen=True)
class CarrierObservation:
    """What the ingress observed: at most one carrier, and whether the two disagreed."""

    value: Optional[str]
    conflict: bool


def recognized_carrier(headers: Mapping[str, str], host: str, base_domain: str = "") -> CarrierObservation:
    """Observe the request's single recognized carrier, or record that it has two.

    Both carriers present and disagreeing is reported as a **conflict**, not resolved by
    precedence. Picking a winner would mean that a request addressed to ``acme.example.com``
    while asserting ``X-Tenant-Id: zeta`` could pass the match check whenever the signed
    claim happened to equal the one that was picked — the exact confusion the carrier
    contract exists to prevent. Two carriers that disagree is a rejected request.
    """
    from_header = carrier_from_header(headers)
    from_host = carrier_from_host(host, base_domain)

    if from_header is not None and from_host is not None and from_header != from_host:
        return CarrierObservation(value=None, conflict=True)
    return CarrierObservation(value=from_header if from_header is not None else from_host, conflict=False)


__all__ = [
    "NON_CARRIER_HEADERS",
    "TENANT_HEADER",
    "CarrierObservation",
    "carrier_from_header",
    "carrier_from_host",
    "recognized_carrier",
]
