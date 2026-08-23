"""URL normalization — technical text handling, shared by every service that stores a website.

This lives in the shared foundation rather than in one service because two services need the
*same* rule and services may not import one another (IC-013 §13). It is technical: it knows
about schemes and hosts, and nothing about startups, investors, or what a website means to
either of them.

Normalization matters for correctness, not tidiness. Two records differing only by a trailing
slash or a ``www.`` prefix are the same company, and any duplicate check comparing raw values
would miss that.
"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from .errors import invalid_request

_PERMITTED_SCHEMES = ("http", "https")

#: A host is dot-separated labels, optionally with a port. Checked explicitly because
#: ``urlsplit`` is permissive about what it will accept as a netloc: given ``https://not a url``
#: it happily reports ``not a url`` as the host, which would then be stored as if it were one.
_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_HOST = re.compile(r"\A" + _LABEL + r"(?:\." + _LABEL + r")*(?::\d{1,5})?\Z")


def normalize_website(raw: Optional[str]) -> Optional[str]:
    """Normalize a website URL, or raise the canonical 422 for a malformed one.

    Scheme-less input gets ``https://``; the host is lower-cased and a leading ``www.`` is
    dropped; a trailing slash on the path is removed; a fragment is discarded. Anything without
    a host, or with a scheme other than http/https, is **rejected** rather than stored as given
    — storing an unparseable value guarantees it can never be compared with anything later.
    """
    if raw is None:
        return None
    candidate = raw.strip()
    if not candidate:
        return None
    if "://" not in candidate:
        candidate = "https://" + candidate

    parts = urlsplit(candidate)
    if parts.scheme not in _PERMITTED_SCHEMES or not parts.netloc:
        raise invalid_request()

    host = parts.netloc.casefold()
    if host.startswith("www."):
        host = host[4:]
    if not _HOST.match(host):
        raise invalid_request()

    return urlunsplit((parts.scheme, host, parts.path.rstrip("/"), parts.query, ""))


__all__ = ["normalize_website"]
