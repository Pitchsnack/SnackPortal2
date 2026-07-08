"""api_gateway composition (Build Phase 7).

Assembles the gateway pipeline from injected ports: the Authenticator (IC-005), the
Database Router transport port, and the audit emitter (AD-1 no-sink default). Tests/dev
inject stubs; production injects transport adapters (under adapters/providers). Liveness
is static and non-disclosing. The gateway resolves no database and imports no other
service (DAG independence).

07E-3c adds ``build_authenticator_from_env`` — a config-selectable ``AuthenticatorPort``
seam over the 07E-3b HTTP auth transport client. It does not create a runnable production
gateway: the router port remains caller-injected (no production ``RouterDispatchPort``
adapter exists; D-15 dispatch composition is a separate gate), and full production Gateway
composition is deferred.
"""

from __future__ import annotations

import os
from typing import Callable, Optional
from urllib.parse import urlsplit

from .adapters.providers.http_authenticator import HttpAuthenticator
from .adapters.providers.in_memory_audit_emitter import InMemoryAuditEmitter
from .adapters.providers.in_memory_metrics import InMemoryMetrics
from .dispatch import default_classifier
from .gateway import Gateway
from .models import DispatchCategory, InboundRequest
from .ports import AuditEmitterPort, AuthenticatorPort, MetricsPort, RouterDispatchPort
from .readiness import liveness

SERVICE = "api_gateway"

# 07E-3c: the auth-transport selector (mirrors the control_plane SP2_CP_* selector posture).
# The value is NON-SECRET internal routing config — the loopback/internal Auth Router base
# URL, never a credential — so it is read directly from the environment (no SecretRef, no
# SecretStore). Unset/empty keeps the existing injected (test/dev stub) composition; a
# structurally valid internal http URL selects the production-shaped HttpAuthenticator
# transport client; anything else raises ValueError (fail closed — never a silent fallback
# from malformed production config to a stub).
GW_AUTH_ROUTER_BASE_URL_ENV = "SP2_GW_AUTH_ROUTER_BASE_URL"

__all__ = ["GW_AUTH_ROUTER_BASE_URL_ENV", "SERVICE", "build_authenticator_from_env", "build_gateway", "liveness"]


def build_gateway(
    *,
    authenticator: AuthenticatorPort,
    router: RouterDispatchPort,
    classify: Optional[Callable[[InboundRequest], DispatchCategory]] = None,
    audit: Optional[AuditEmitterPort] = None,
    metrics: Optional[MetricsPort] = None,
) -> Gateway:
    """Compose the gateway. The audit + metrics defaults are the no-sink / vendor-neutral
    in-memory adapters (AD-1 Option A; WP-11)."""
    return Gateway(
        authenticator=authenticator,
        router=router,
        classify=classify if classify is not None else default_classifier,
        audit=audit if audit is not None else InMemoryAuditEmitter(),
        metrics=metrics if metrics is not None else InMemoryMetrics(),
    )


def build_authenticator_from_env() -> Optional[AuthenticatorPort]:
    """The config-selectable ``AuthenticatorPort`` seam (07E-3c; IC-010 §D via the merged
    AUTH-TRANSPORT-SPEC-01 wire contract).

    This helper exposes a production-shaped ``AuthenticatorPort`` selection seam. It does
    not create a runnable production gateway. The router port remains caller-injected.
    Full production Gateway composition is deferred.

    Selection (the fail-closed control_plane env-selector pattern):

    * ``SP2_GW_AUTH_ROUTER_BASE_URL`` unset, or empty/whitespace after stripping →
      ``None`` — the caller keeps its injected authenticator (tests/dev stubs unchanged).
    * a structurally valid internal ``http://host[:port]`` value → an ``HttpAuthenticator``
      bound to that base URL. The transport client is lazy: construction performs no
      network I/O; every failure at call time collapses fail-closed to the existing
      ``RequestRejected`` semantics (no new public_code).
    * anything else → ``ValueError`` at the composition boundary — never a silent
      fallback from malformed production config to a stub.

    Validation is structural only (``urlsplit`` scheme + netloc; the scheme is pinned to
    ``http`` — this is the internal loopback transport; TLS termination is deployment
    scope). No network I/O, no JWT validation, no ``auth_router``/``database_router``
    import, no database, no token/credential handling.
    """
    raw = (os.environ.get(GW_AUTH_ROUTER_BASE_URL_ENV) or "").strip()
    if not raw:
        return None
    parts = urlsplit(raw)
    if parts.scheme != "http" or not parts.netloc:
        raise ValueError(
            f"unsupported {GW_AUTH_ROUTER_BASE_URL_ENV}={raw!r}; expected an internal "
            "http://host[:port] Auth Router base URL (fail closed — no silent fallback)"
        )
    return HttpAuthenticator(raw)
