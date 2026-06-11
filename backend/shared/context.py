"""Request context & correlation (shared, vendor-neutral) — shapes only.

Carries correlation only. MUST NEVER hold tokens, JWTs, credentials, secrets, or
raw payloads (D-14). The active tenant is established by IC-005 routing in a later
build phase; the field exists here as a reference placeholder only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RequestContext:
    correlation_id: str
    request_id: Optional[str] = None
    active_tenant_id: Optional[str] = None  # set by IC-005 tenant resolution (Phase 3)
    principal_ref: Optional[str] = None  # identity reference, never a token/credential
    role: Optional[str] = None  # active role (D-32), set by Phase 3; never a permission set
    # Invariant: no field may contain a secret, token, credential, or payload.
