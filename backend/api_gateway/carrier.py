"""Carrier extraction & prohibited-carrier handling (IC-010 §E / IC-005 carriers).

Exactly two recognized tenant carriers: the tenant subdomain (host-based) and the
``X-Tenant-Id`` header (case-insensitive) — the ONLY recognized carrier header. Cookies,
query-string, portal/workspace/local-storage state are PROHIBITED routing authority:
ignored here and never read by any backend component as a tenant selector
(IC-010 §E/§G/§T). Recognized carriers are only fed into the IC-005 carrier-match check.
"""

from __future__ import annotations

from typing import List, Optional

from .models import InboundRequest

CARRIER_HEADER = "x-tenant-id"  # the only recognized carrier header (case-insensitive)
_PROHIBITED_HEADERS = ("x-workspace-id", "x-workspace", "workspace")
_CARRIER_REF_MAX_LEN = 64


def _subdomain(host: str) -> Optional[str]:
    h = host.split(":")[0].strip().lower()  # drop any port suffix
    if not h:
        return None
    labels = h.split(".")
    # tenant.base.tld → the leading label is the tenant subdomain carrier.
    if len(labels) >= 3 and labels[0]:
        return labels[0]
    return None


def recognized_carriers(request: InboundRequest) -> List[str]:
    """The recognized tenant-carrier VALUES present (subdomain + X-Tenant-Id), order-stable.

    Reads ONLY the host subdomain and the X-Tenant-Id header — never a cookie, query
    parameter, or workspace value.
    """
    out: List[str] = []
    sub = _subdomain(request.host)
    if sub is not None:
        out.append(sub)
    for key, value in request.headers.items():
        if key.lower() == CARRIER_HEADER and value.strip():
            out.append(value.strip())
    return out


def prohibited_carrier_present(request: InboundRequest) -> bool:
    """True if a tenant/workspace value rides a PROHIBITED channel (cookie, query, or a
    workspace header). Such values are ignored as selectors — never honored for routing.
    """
    for key in request.cookies:
        low = key.lower()
        if "tenant" in low or "workspace" in low:
            return True
    for key in request.query:
        low = key.lower()
        if "tenant" in low or "workspace" in low:
            return True
    for key in request.headers:
        if key.lower() in _PROHIBITED_HEADERS:
            return True
    return False


def opaque_carrier_ref(value: str) -> str:
    """An opaque, length-bounded rendering of a carrier-asserted tenant id, recorded for
    anomaly attribution only — never parsed, resolved, or treated as a trusted id
    (IC-005:116)."""
    return ("carrier:" + value.strip())[:_CARRIER_REF_MAX_LEN]
