"""api_gateway composition (Build Phase 7).

Assembles the gateway pipeline from injected ports: the Authenticator (IC-005), the
Database Router transport port, and the audit emitter (AD-1 no-sink default). Tests/dev
inject stubs; production injects transport adapters (under adapters/providers). Liveness
is static and non-disclosing. The gateway resolves no database and imports no other
service (DAG independence).

07E-3c adds ``build_authenticator_from_env`` — a config-selectable ``AuthenticatorPort``
seam over the 07E-3b HTTP auth transport client. 07E-3d adds the symmetric
``build_router_dispatch_from_env`` — a config-selectable ``RouterDispatchPort`` seam over
the D-15-T1b HTTP dispatch transport client. Neither creates a runnable production gateway:
even with both seams selected, end-to-end routing requires a production-composed Database
Router over physical tenant databases (B5-BLK-4 / Physical Multi-Database MVP scope), which
is NOT part of these slices. No production ``build_gateway`` call site is created; the
gateway resolves no database (IC-010 §X) and full production Gateway composition is deferred.
"""

from __future__ import annotations

import os
from typing import Callable, Optional, Tuple
from urllib.parse import urlsplit

from .adapters.providers.http_authenticator import HttpAuthenticator
from .adapters.providers.http_control_plane_read import HttpControlPlaneRead
from .adapters.providers.http_router_dispatch import HttpRouterDispatch
from .adapters.providers.in_memory_audit_emitter import InMemoryAuditEmitter
from .adapters.providers.in_memory_metrics import InMemoryMetrics
from .dispatch import default_classifier
from .gateway import Gateway
from .models import DispatchCategory, GatewayAuditEvent, InboundRequest
from .ports import AuditEmitterPort, AuthenticatorPort, ControlPlaneReadPort, MetricsPort, RouterDispatchPort
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

# 07E-3d: the dispatch-transport selector (mirrors the 07E-3c auth selector). The value is
# NON-SECRET internal routing config — the loopback/internal Database Router dispatch base
# URL, never a credential — so it is read directly from the environment (no SecretRef, no
# SecretStore). Named SP2_GW_DB_ROUTER_BASE_URL to disambiguate from the Auth Router selector
# (SP2_GW_AUTH_ROUTER_BASE_URL): this one targets the Database Router dispatch endpoint. Unset/
# empty keeps the existing injected (test/dev stub) composition; a structurally valid internal
# http URL selects the production-shaped HttpRouterDispatch transport client; anything else
# raises ValueError (fail closed — never a silent fallback from malformed production config).
GW_DB_ROUTER_BASE_URL_ENV = "SP2_GW_DB_ROUTER_BASE_URL"

# B5-BLK-6B: the Control-Plane read-transport selector (mirrors the 07E-3c/07E-3d
# selectors). The value is NON-SECRET internal routing config — the loopback/internal
# Control-Plane read-edge base URL, never a credential — so it is read directly from the
# environment (no SecretRef, no SecretStore). Unset/empty keeps the existing injected
# composition (the read seam stays OFF — no silent activation, no loopback default); a
# structurally valid internal http URL selects the production-shaped HttpControlPlaneRead
# transport client; anything else raises ValueError (fail closed — never a silent
# fallback from malformed production config).
GW_CONTROL_READ_BASE_URL_ENV = "SP2_GW_CONTROL_READ_BASE_URL"

# Gateway Audit V1a: the durable operational-audit sink selector (mirrors the 07E-3c/07E-3d/6B
# selectors). The value is NON-SECRET internal routing config — the loopback/internal Control-Plane
# Gateway-audit ingest base URL, never a credential — so it is read directly from the environment (no
# SecretRef, no SecretStore). Unset/empty keeps the default in-memory no-sink emitter (AD-1 Option A;
# there is deliberately NO loopback default — a default would silently activate a durable transport);
# a structurally valid internal http URL selects the durable DurableAuditEmitter wrapped in the
# bounded BoundedGatewayAuditPolicy; anything else raises ValueError before any socket (fail closed —
# never a silent fallback from malformed production config to the in-memory emitter).
GW_AUDIT_SINK_BASE_URL_ENV = "SP2_GW_AUDIT_SINK_BASE_URL"

# Served API Gateway Edge V1: the edge bind + browser-policy knobs (NON-SECRET deployment
# config — a loopback host, a port, and an exact-origin CORS allowlist; never a credential).
# The three transport selectors above remain the ACTIVATION gate; these knobs are consulted
# only once the complete real composition is present (gate-first, mirroring the auth/dispatch
# server seams). None of these is a secret, so all are read directly from the environment.
GW_EDGE_HOST_ENV = "SP2_GW_EDGE_HOST"
GW_EDGE_PORT_ENV = "SP2_GW_EDGE_PORT"
GW_EDGE_ALLOWED_ORIGINS_ENV = "SP2_GW_EDGE_ALLOWED_ORIGINS"

__all__ = [
    "BoundedGatewayAuditPolicy",
    "GW_AUDIT_SINK_BASE_URL_ENV",
    "GW_AUTH_ROUTER_BASE_URL_ENV",
    "GW_CONTROL_READ_BASE_URL_ENV",
    "GW_DB_ROUTER_BASE_URL_ENV",
    "GW_EDGE_ALLOWED_ORIGINS_ENV",
    "GW_EDGE_HOST_ENV",
    "GW_EDGE_PORT_ENV",
    "SERVICE",
    "build_audit_emitter_from_env",
    "build_authenticator_from_env",
    "build_control_plane_read_from_env",
    "build_gateway",
    "build_gateway_edge_server_from_env",
    "build_router_dispatch_from_env",
    "liveness",
]


def build_gateway(
    *,
    authenticator: AuthenticatorPort,
    router: RouterDispatchPort,
    control_read: Optional[ControlPlaneReadPort] = None,
    classify: Optional[Callable[[InboundRequest], DispatchCategory]] = None,
    audit: Optional[AuditEmitterPort] = None,
    metrics: Optional[MetricsPort] = None,
) -> Gateway:
    """Compose the gateway. The audit + metrics defaults are the no-sink / vendor-neutral
    in-memory adapters (AD-1 Option A; WP-11). ``control_read`` (B5-BLK-6B) is OPTIONAL
    and defaulted: None keeps the pre-6B pipeline unchanged (every category through the
    router; ``portal_dto`` always None) — the IC-010 §V composition seam activates only
    when a typed Control-Plane read port is explicitly injected or env-selected."""
    return Gateway(
        authenticator=authenticator,
        router=router,
        control_read=control_read,
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


def build_router_dispatch_from_env() -> Optional[RouterDispatchPort]:
    """The config-selectable ``RouterDispatchPort`` seam (07E-3d; D-15 dispatch wire contract
    docs/d15/D15-DISPATCH-SPEC-01; IC-010 §H).

    This helper exposes a production-shaped ``RouterDispatchPort`` selection seam. It does not
    create a runnable production gateway. Even with the auth seam also selected, end-to-end
    routing requires a production-composed Database Router over physical tenant databases
    (B5-BLK-4 / Physical Multi-Database MVP scope), which is NOT part of this slice. No
    production ``build_gateway`` call site is created.

    Selection (the same fail-closed env-selector pattern as ``build_authenticator_from_env``):

    * ``SP2_GW_DB_ROUTER_BASE_URL`` unset, or empty/whitespace after stripping → ``None`` —
      the caller keeps its injected router (tests/dev stubs unchanged).
    * a structurally valid internal ``http://host[:port]`` value → an ``HttpRouterDispatch``
      bound to that base URL. The transport client is lazy: construction performs no network
      I/O; every failure at call time collapses fail-closed to
      ``RouteOutcome(503, "unavailable", False)`` (IC-010 §L — no new public_code).
    * anything else → ``ValueError`` at the composition boundary — never a silent fallback
      from malformed production config to a stub.

    Validation is structural only (``urlsplit`` scheme + netloc; the scheme is pinned to
    ``http`` — this is the internal loopback transport; TLS termination is deployment scope).
    No network I/O, no ``database_router`` import, no database access, no tenant DB binding —
    references only (the router binds the tenant database from the signed claim, router-side).
    """
    raw = (os.environ.get(GW_DB_ROUTER_BASE_URL_ENV) or "").strip()
    if not raw:
        return None
    parts = urlsplit(raw)
    if parts.scheme != "http" or not parts.netloc:
        raise ValueError(
            f"unsupported {GW_DB_ROUTER_BASE_URL_ENV}={raw!r}; expected an internal "
            "http://host[:port] Database Router dispatch base URL (fail closed — no silent fallback)"
        )
    return HttpRouterDispatch(raw)


def build_control_plane_read_from_env() -> Optional[ControlPlaneReadPort]:
    """The config-selectable ``ControlPlaneReadPort`` seam (B5-BLK-6B; IC-010 §V typed
    composition inputs over the §M internal read transport).

    This helper exposes a production-shaped ``ControlPlaneReadPort`` selection seam. It
    does not create a runnable production gateway and adds no serving edge; composition
    behavior activates only where ``build_gateway`` receives the selected port.

    Selection (the same fail-closed env-selector pattern as the 07E-3c/07E-3d seams):

    * ``SP2_GW_CONTROL_READ_BASE_URL`` unset, or empty/whitespace after stripping →
      ``None`` — the caller keeps its injected (or absent) read port and the gateway
      preserves the pre-6B routing behavior with ``portal_dto`` always None. There is
      deliberately NO loopback default — a default would silently activate a transport.
    * a structurally valid internal ``http://host[:port]`` value → an
      ``HttpControlPlaneRead`` bound to that base URL. The transport client is lazy:
      construction performs no network I/O; every call-time failure collapses fail-closed
      to the existing §L vocabulary (503 ``unavailable`` — no new public_code).
    * anything else → ``ValueError`` at the composition boundary, raised BEFORE any
      socket — never a silent fallback from malformed production config.

    Validation is structural only (``urlsplit`` scheme + netloc; the scheme is pinned to
    ``http`` — this is the internal loopback transport; TLS termination is deployment
    scope). No network I/O, no ``control_plane`` import, no database access, no secret
    handling (the base URL is non-secret internal routing config; no SecretRef).
    """
    raw = (os.environ.get(GW_CONTROL_READ_BASE_URL_ENV) or "").strip()
    if not raw:
        return None
    parts = urlsplit(raw)
    if parts.scheme != "http" or not parts.netloc:
        raise ValueError(
            f"unsupported {GW_CONTROL_READ_BASE_URL_ENV}={raw!r}; expected an internal "
            "http://host[:port] Control-Plane read base URL (fail closed — no silent fallback)"
        )
    return HttpControlPlaneRead(raw)


class BoundedGatewayAuditPolicy(AuditEmitterPort):
    """Gateway Audit V1a fail-closed durable-audit policy (the DBR-AR-2C ``BoundedRoutingAuditPolicy``
    precedent, success-class only).

    Wraps the durable transport emitter behind the same sink-less ``AuditEmitterPort`` and owns the
    two fail-closed decisions for the single ``workspace_memberships_read`` success-access event:

    * exactly ONE immediate, synchronous, idempotent retry of the SAME event (maximum two total
      transport calls), and only when the transport failure kind is ``unavailable`` (transient);
      ``invalid`` and ``conflict`` are NEVER retried. No retry loop, sleep, queue, outbox, thread, or
      background machinery.
    * terminal posture: re-raise so the gateway fails the served success closed
      (audit-before-hand-back — the gateway maps the raise to the typed 503 ``unavailable``; a served
      success is never handed back unless its durable audit was confirmed). A duplicate replay
      answered ``DUPLICATE_MATCH`` is success inside the wrapped client and never reaches this
      policy's failure path.
    """

    def __init__(self, inner: AuditEmitterPort, *, transport_error: type[Exception]) -> None:
        self._inner = inner
        self._transport_error = transport_error

    def _retryable(self, failure: Exception) -> bool:
        # Exactly the transient transport kind is retryable; invalid/conflict never.
        return isinstance(failure, self._transport_error) and getattr(failure, "kind", None) == "unavailable"

    def emit(self, event: GatewayAuditEvent) -> None:
        try:
            self._inner.emit(event)
            return
        except Exception as first:
            if not self._retryable(first):
                raise  # invalid/conflict → terminal fail-closed, no retry
        self._inner.emit(event)  # the single bounded retry: the SAME event (re-raises on terminal)


def build_audit_emitter_from_env() -> Optional[AuditEmitterPort]:
    """The config-selectable durable ``AuditEmitterPort`` seam (Gateway Audit V1a; IC-010 §J /
    IC-002 class 3b durable persistence over the §M internal transport).

    This helper exposes a production-shaped durable ``AuditEmitterPort`` selection seam. It does not
    create a runnable production gateway; the durable emitter is wired only at the (deferred/
    rehearsal) edge composition call site, never as a forced default (B5-BLK-1 preserved).

    Selection (the same fail-closed env-selector pattern as the 07E-3c/07E-3d/6B seams):

    * ``SP2_GW_AUDIT_SINK_BASE_URL`` unset, or empty/whitespace after stripping → ``None`` — the
      caller keeps the default in-memory no-sink emitter (AD-1 Option A). There is deliberately NO
      loopback default — a default would silently activate a durable transport.
    * a structurally valid internal ``http://host[:port]`` value → a ``DurableAuditEmitter`` bound to
      that base URL, wrapped in the bounded ``BoundedGatewayAuditPolicy`` (one idempotent retry for
      transient unavailability only; fail-closed re-raise on terminal failure). The transport client
      is lazy: construction performs no network I/O.
    * anything else → ``ValueError`` at the composition boundary, raised BEFORE any socket — never a
      silent fallback from malformed production config to the in-memory emitter.

    Validation is structural only (``urlsplit`` scheme + netloc; the scheme is pinned to ``http`` —
    this is the internal loopback transport; TLS termination is deployment scope). No network I/O, no
    ``control_plane`` import, no database access, no secret handling (the base URL is non-secret
    internal routing config; no SecretRef).
    """
    raw = (os.environ.get(GW_AUDIT_SINK_BASE_URL_ENV) or "").strip()
    if not raw:
        return None
    parts = urlsplit(raw)
    if parts.scheme != "http" or not parts.netloc:
        raise ValueError(
            f"unsupported {GW_AUDIT_SINK_BASE_URL_ENV}={raw!r}; expected an internal "
            "http://host[:port] Gateway operational-audit sink base URL (fail closed — no silent fallback)"
        )
    # Lazy relative import (the merged seam shape): the transport client is deferred to selection time
    # so api_gateway/main.py stays import-light while inactive.
    from .adapters.providers.durable_audit_emitter import DurableAuditEmitter, DurableAuditTransportError

    return BoundedGatewayAuditPolicy(DurableAuditEmitter(raw), transport_error=DurableAuditTransportError)


def _edge_port_from_env() -> int:
    """Parse ``SP2_GW_EDGE_PORT`` fail-closed: unset/empty/whitespace → ``0`` (ephemeral);
    otherwise a base-10 integer in ``[0, 65535]``, else ``ValueError`` — raised BEFORE any
    socket bind so malformed config never opens a listener."""
    raw = (os.environ.get(GW_EDGE_PORT_ENV) or "").strip()
    if not raw:
        return 0
    try:
        port = int(raw, 10)
    except ValueError:
        raise ValueError(f"invalid {GW_EDGE_PORT_ENV}={raw!r}; expected an integer in [0, 65535]") from None
    if not (0 <= port <= 65535):
        raise ValueError(f"invalid {GW_EDGE_PORT_ENV}={raw!r}; port out of range [0, 65535]")
    return port


def _edge_allowed_origins_from_env() -> Tuple[str, ...]:
    """The exact-origin CORS allowlist from ``SP2_GW_EDGE_ALLOWED_ORIGINS`` (comma-separated).
    Unset/empty → an EMPTY allowlist (every cross-origin request is denied — fail closed; the
    browser blocks it). No wildcard handling: the edge never emits credentialed CORS, so no
    entry can produce a wildcard-with-credentials response."""
    raw = os.environ.get(GW_EDGE_ALLOWED_ORIGINS_ENV) or ""
    return tuple(origin.strip() for origin in raw.split(",") if origin.strip())


def build_gateway_edge_server_from_env() -> Optional[Tuple[object, str]]:
    """The served northbound gateway-edge composition seam (Served API Gateway Edge V1).

    Composition-gate-first: assemble the COMPLETE real Gateway from the three existing
    transport seams — ``build_authenticator_from_env`` (IC-005), ``build_router_dispatch_from_env``
    (IC-010 §H), and ``build_control_plane_read_from_env`` (IC-010 §V) — before any bind knob is
    read. ``build_gateway`` structurally requires all three ports; the served edge therefore
    activates ONLY on a complete real composition and NEVER on a partial one or a silent
    in-memory stub. If ANY of the three transport selectors is unset/empty, this seam returns
    ``None`` (serve-inert; no bind knob consulted, no socket bound). A malformed transport URL
    raises ``ValueError`` (inherited) before any host/port parse.

    When the composition is complete, the bind + browser knobs are read:

    * ``SP2_GW_EDGE_HOST`` — optional; unset/empty/whitespace → ``127.0.0.1`` (internal loopback,
      IC-010 §R; TLS terminates at a reverse proxy — deployment scope). Passed through otherwise
      (an unbindable host surfaces as ``OSError`` at construction — deployment scope).
    * ``SP2_GW_EDGE_PORT`` — optional; unset/empty → ``0`` (ephemeral); otherwise an integer in
      ``[0, 65535]``; non-integer / negative / out-of-range → ``ValueError`` raised BEFORE the
      edge server is built so a bad port never binds a socket.
    * ``SP2_GW_EDGE_ALLOWED_ORIGINS`` — optional; the exact-origin CORS allowlist (comma-separated);
      unset/empty → deny every cross-origin request.

    Side-effect boundary (LOAD-BEARING): this seam is DB-inert, network-read-inert, and
    serve-inert — it opens no database, performs no network client read, and starts no serve
    loop, thread, daemon, or service. But it is NOT socket-inert: when active,
    ``build_gateway_edge_server`` binds + activates a local listening socket at construction
    (default ``port=0`` → ephemeral). Callers/tests own the socket lifecycle and must close it.

    No overclaim: it composes a served edge *object* from config; it does NOT serve requests,
    run a production service, terminate TLS, activate production, or close any B5 blocker.
    """
    authenticator = build_authenticator_from_env()
    control_read = build_control_plane_read_from_env()
    router = build_router_dispatch_from_env()
    if authenticator is None or control_read is None or router is None:
        return None
    host = (os.environ.get(GW_EDGE_HOST_ENV) or "").strip() or "127.0.0.1"
    port = _edge_port_from_env()
    allowed_origins = _edge_allowed_origins_from_env()
    # Gateway Audit V1a: the durable operational-audit sink is wired at THIS composition call site
    # (never a forced default; B5-BLK-1 preserved). Unset SP2_GW_AUDIT_SINK_BASE_URL → None →
    # build_gateway keeps the in-memory no-sink default (AD-1 Option A); a valid URL → the fail-closed
    # durable policy. A malformed value raises ValueError here (before any socket bind).
    audit = build_audit_emitter_from_env()
    # Lazy relative import keeps api_gateway/main.py import-light and server-token-free (the
    # concrete serving edge and its socket live in the adapter, never in the composition root).
    from .adapters.providers.http_gateway_edge import build_gateway_edge_server

    gateway = build_gateway(authenticator=authenticator, router=router, control_read=control_read, audit=audit)
    return build_gateway_edge_server(gateway, host=host, port=port, allowed_origins=allowed_origins)
