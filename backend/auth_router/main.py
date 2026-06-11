"""auth_router composition (Build Phase 3).

Assembles the two-stage authenticator. Tests/dev inject a control-plane read double +
a stdlib verifier; production injects the PyJWT verifier + HTTP read client (under
adapters/providers). Liveness is static and non-disclosing. No DB access, no routing.
"""

from __future__ import annotations

from typing import Dict, Optional

from shared.audit import OperationalAudit

from .adapters.providers.in_memory_audit_sink import InMemoryAuditSink
from .authenticator import Authenticator
from .caching import CachingControlPlaneRead
from .jwt_validation import JwtValidator
from .models import IssuerConfig
from .ports import ControlPlaneReadPort, SignatureVerifier
from .tenant_context import TenantContextResolver

SERVICE = "auth_router"


def build_authenticator(
    *,
    verifier: SignatureVerifier,
    read: ControlPlaneReadPort,
    issuers: Dict[str, IssuerConfig],
    audit: Optional[OperationalAudit] = None,
    cache_ttl_seconds: float = 30.0,
) -> Authenticator:
    cached_read = CachingControlPlaneRead(read, ttl_seconds=cache_ttl_seconds)
    validator = JwtValidator(verifier)
    resolver = TenantContextResolver(cached_read)
    return Authenticator(validator, resolver, audit or InMemoryAuditSink(), issuers)


def liveness() -> Dict[str, str]:
    return {"service": SERVICE, "status": "alive", "build_phase": "3"}
