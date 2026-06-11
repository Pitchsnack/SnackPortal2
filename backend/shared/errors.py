"""Denial semantics (shared, vendor-neutral) — shapes only.

Canonical, non-leaking denial reasons used by every service so callers receive
consistent semantics that never reveal tenant/database existence or internal
detail.

Governed by: IC-002 (denial semantics), IC-005 (401/403), IC-001 (minimally
disclosing). No transport mapping and no business logic here.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DenialReason(Enum):
    UNAUTHENTICATED = "unauthenticated"                       # 401
    FORBIDDEN = "forbidden"                                   # 403
    NOT_FOUND = "not_found"                                   # unknown / decommissioned / unauthorized-to-know
    NOT_READY = "not_ready"                                   # provisioning/verifying -> retry later
    ADMINISTRATIVELY_DISABLED = "administratively_disabled"   # suspended
    UNAVAILABLE = "unavailable"                               # failed / database unreachable


@dataclass(frozen=True)
class Denial:
    """A non-sensitive denial descriptor. MUST NOT carry secrets, PII, or internal detail."""

    reason: DenialReason
    public_code: str
    message: str = ""  # caller-safe, non-sensitive text only


class DenialError(Exception):
    """Signals a denial, carrying only a non-sensitive Denial descriptor."""

    def __init__(self, denial: Denial) -> None:
        super().__init__(denial.public_code)
        self.denial = denial
