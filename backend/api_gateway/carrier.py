"""Carrier extraction & prohibited-carrier handling (IC-010 §E / IC-005 carriers).

Exactly two recognized tenant carriers: the tenant subdomain (host-based) and the
``X-Tenant-Id`` header (case-insensitive) — the ONLY recognized carrier header. Cookies,
query-string, portal/workspace/local-storage state are PROHIBITED routing authority:
ignored here and never read by any backend component as a tenant selector
(IC-010 §E/§G/§T). Recognized carriers are only fed into the IC-005 carrier-match check.
"""

from __future__ import annotations

import ipaddress
from typing import List, Optional

from .models import InboundRequest

CARRIER_HEADER = "x-tenant-id"  # the only recognized carrier header (case-insensitive)
_PROHIBITED_HEADERS = ("x-workspace-id", "x-workspace", "workspace")
_CARRIER_REF_MAX_LEN = 64


def _subdomain(host: str) -> Optional[str]:
    """The tenant subdomain carrier (the leading DNS label) of a genuine multi-label DNS
    host, else None.

    A host-derived carrier is a tenant DNS subdomain ONLY (IC-005 D-33; IC-010 §E). A
    transport address is never a tenant carrier: IPv4 and IPv6 LITERAL hosts (bracketed
    or not, with or without a port), single-label hosts (e.g. ``localhost``), empty, and
    malformed hosts assert NO host carrier and fail closed to None. Genuine multi-label
    DNS hosts (``tenant.base.tld``) are unchanged — the leading label is the carrier and
    a trailing ``:port`` never alters it.
    """
    h = host.strip().lower()
    if not h:
        return None
    # Drop an optional port and IPv6 brackets WITHOUT corrupting a bracketed IPv6 literal
    # (a naive ``split(":")`` would): "[v6]"/"[v6]:port" → the bracketed literal; an
    # unterminated bracket is malformed → fail closed; "host"/"host:port" → the host.
    if h.startswith("["):
        end = h.find("]")
        if end == -1:
            return None
        h = h[1:end]
    elif h.count(":") == 1:
        h = h.split(":", 1)[0]
    if not h:
        return None
    # An IPv4/IPv6 literal is a transport address, not a tenant DNS subdomain carrier.
    try:
        ipaddress.ip_address(h)
    except ValueError:
        pass  # not an IP literal → may be a DNS host
    else:
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
