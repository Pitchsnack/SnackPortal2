"""auth_router composition (Build Phase 3).

Assembles the two-stage authenticator. Tests/dev inject a control-plane read double +
a stdlib verifier; production injects the PyJWT verifier + HTTP read client (under
adapters/providers). Liveness is static and non-disclosing. No DB access, no routing.

``build_authenticator_from_env`` adds a config-selectable, INERT production-composition
seam mirroring the merged Database Router seam (``build_router_from_env``): a structurally
valid internal ``SP2_AR_CONTROL_PLANE_READ_BASE_URL`` selects the production
``HttpControlPlaneRead`` transport + the ``PyJwtSignatureVerifier`` and, with the
``SP2_AR_ISSUERS`` trust-anchor config, returns a composed ``Authenticator``; unset/empty
keeps the caller's injected composition; a malformed/off-scheme value (or, when the
selector is active, missing/invalid issuer config) fails closed (``ValueError``). The seam
is inert — it performs no network client I/O, opens no database, and starts no service
(construction only). It composes AUTHENTICATION only (no routing, no DB); it does NOT
complete the Physical Multi-Database MVP or make the physical live-topology smoke runnable.
"""

from __future__ import annotations

import json
import os
from typing import Dict, Optional, Tuple
from urllib.parse import urlsplit

from shared.audit import OperationalAudit

from .adapters.providers.in_memory_audit_sink import InMemoryAuditSink
from .authenticator import Authenticator
from .caching import CachingControlPlaneRead
from .jwt_validation import JwtValidator
from .models import IssuerConfig
from .ports import ControlPlaneReadPort, SignatureVerifier
from .tenant_context import TenantContextResolver

SERVICE = "auth_router"

# The config-selectable Auth Router control-plane read transport selector (mirrors the
# Database Router SP2_DBR_* / gateway SP2_GW_* selector posture). The value is NON-SECRET
# internal config — the loopback/internal control-plane read base URL, never a credential —
# so it is read directly from the environment (no SecretRef, no SecretStore). Unset/empty
# keeps the caller's injected (test/dev double) composition; a structurally valid internal
# http URL selects the production HttpControlPlaneRead client; anything else raises
# ValueError (fail closed — never a silent fallback from malformed production config).
SP2_AR_CONTROL_PLANE_READ_BASE_URL = "SP2_AR_CONTROL_PLANE_READ_BASE_URL"

# The issuer trust-anchor config (JSON object mapping issuer -> issuer config). REQUIRED
# when the read selector is active. JWKS values are PUBLIC key material (not a secret) and
# are treated as OPAQUE at composition (the verifier consumes them at verify time) — so the
# seam validates issuer-config SHAPE + alg policy only and performs no cryptographic key
# validation, keeping construction inert.
SP2_AR_ISSUERS = "SP2_AR_ISSUERS"

# Production trust pin: asymmetric algorithms only (matching PyJwtSignatureVerifier, which
# supports exactly these). Symmetric / HS* algorithms are rejected fail-closed at config time.
_ASYMMETRIC_ALGS = frozenset({"RS256", "RS384", "RS512", "ES256"})

# The authenticate-server bind knobs (Slice 2 paired follow-on). Non-secret internal config: the
# host and port the internal Gateway->Auth-Router authenticate server binds. Both optional — the
# defaults are the loopback host and an ephemeral port (IC-010 §R internal-only surface). Only
# consulted when the authenticator seam is active (SP2_AR_CONTROL_PLANE_READ_BASE_URL selected).
SP2_AR_AUTHENTICATE_HOST = "SP2_AR_AUTHENTICATE_HOST"
SP2_AR_AUTHENTICATE_PORT = "SP2_AR_AUTHENTICATE_PORT"


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


def _issuer_config(key: object, cfg: object) -> IssuerConfig:
    """Validate one ``SP2_AR_ISSUERS`` entry (shape + alg policy) and build its IssuerConfig.

    Fail-closed (``ValueError``) on any violation. Each ``jwks`` value is treated as OPAQUE
    public key material — no cryptographic validation here (keeps construction inert)."""
    if not isinstance(cfg, dict):
        raise ValueError(f"{SP2_AR_ISSUERS}[{key!r}] must be a JSON object")
    if cfg.get("issuer") != key:
        raise ValueError(f"{SP2_AR_ISSUERS}[{key!r}] 'issuer' must be present and equal the map key")
    audience = cfg.get("audience")
    if not isinstance(audience, str) or not audience:
        raise ValueError(f"{SP2_AR_ISSUERS}[{key!r}] requires a non-empty string 'audience'")
    allowed_algs = cfg.get("allowed_algs")
    if not isinstance(allowed_algs, list) or not allowed_algs:
        raise ValueError(f"{SP2_AR_ISSUERS}[{key!r}] requires a non-empty 'allowed_algs' list")
    for alg in allowed_algs:
        if alg not in _ASYMMETRIC_ALGS:
            raise ValueError(
                f"{SP2_AR_ISSUERS}[{key!r}] 'allowed_algs' must be asymmetric-only "
                f"(subset of {sorted(_ASYMMETRIC_ALGS)}); rejected {alg!r} (HS*/symmetric not allowed)"
            )
    jwks = cfg.get("jwks")
    if not isinstance(jwks, dict) or not jwks:
        raise ValueError(f"{SP2_AR_ISSUERS}[{key!r}] requires a non-empty 'jwks' object")
    tenant_claim = cfg.get("tenant_claim", "tenant")
    if not isinstance(tenant_claim, str) or not tenant_claim:
        raise ValueError(f"{SP2_AR_ISSUERS}[{key!r}] 'tenant_claim' must be a non-empty string")
    return IssuerConfig(
        issuer=str(key),
        audience=audience,
        allowed_algs=list(allowed_algs),
        jwks=dict(jwks),
        tenant_claim=tenant_claim,
    )


def _issuers_from_env() -> Dict[str, IssuerConfig]:
    """Parse ``SP2_AR_ISSUERS`` fail-closed into ``Dict[str, IssuerConfig]``.

    Called only when the read selector is active, so an unset/empty value here is a
    misconfiguration (a control-plane read URL without trust anchors) → ``ValueError``.
    Anything not a JSON object of valid issuer entries → ``ValueError`` (raised BEFORE the
    Authenticator is composed)."""
    raw = (os.environ.get(SP2_AR_ISSUERS) or "").strip()
    if not raw:
        raise ValueError(
            f"{SP2_AR_CONTROL_PLANE_READ_BASE_URL} is active but {SP2_AR_ISSUERS} is unset/empty; "
            "an active control-plane read selector requires issuer trust anchors (fail closed)"
        )
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{SP2_AR_ISSUERS} is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict) or not parsed:
        raise ValueError(f"{SP2_AR_ISSUERS} must be a non-empty JSON object mapping issuer -> config")
    return {str(key): _issuer_config(key, cfg) for key, cfg in parsed.items()}


def build_authenticator_from_env() -> Optional[Authenticator]:
    """The config-selectable production composition seam (mirrors the merged Database Router
    ``build_router_from_env`` seam).

    Assembles a production ``Authenticator`` from environment configuration using the
    existing production adapters, and is INERT at construction: it performs no network
    client I/O, opens no database, and starts no service. It composes AUTHENTICATION only.

    Selection (the fail-closed env-selector pattern):

    * ``SP2_AR_CONTROL_PLANE_READ_BASE_URL`` unset, or empty/whitespace after stripping →
      ``None`` — the caller keeps its injected composition (tests/dev doubles unchanged);
      ``SP2_AR_ISSUERS`` is NOT consulted.
    * a structurally valid internal ``http://host[:port]`` value → an ``Authenticator``
      composed from ``PyJwtSignatureVerifier`` + ``HttpControlPlaneRead`` (bound to that base
      URL) + the ``SP2_AR_ISSUERS`` trust anchors (REQUIRED when active — fail-closed). The
      read client is lazy: construction performs no network client I/O; the control plane is
      reached only when the authenticator later resolves tenant context.
    * anything else → ``ValueError`` at the composition boundary — never a silent fallback
      from malformed production config to a double.

    URL validation is structural only (``urlsplit`` scheme + netloc; scheme pinned to
    ``http`` — the internal loopback transport; TLS termination is deployment scope).
    ``HttpControlPlaneRead`` does not self-validate its base URL, so the check lives here at
    the composition boundary. The verifier is asymmetric-only (JWT crypto stays under
    adapters/providers, lazily imported inside the seam so this module is JWT-vendor-free at
    import).

    No overclaim: this inert seam proves config-assembly of a production ``Authenticator``;
    it does NOT reach the control plane, run a service, complete the Physical Multi-Database
    MVP, or make the physical live-topology smoke runnable. It is one prerequisite among several.
    """
    raw = (os.environ.get(SP2_AR_CONTROL_PLANE_READ_BASE_URL) or "").strip()
    if not raw:
        return None
    parts = urlsplit(raw)
    if parts.scheme != "http" or not parts.netloc:
        raise ValueError(
            f"unsupported {SP2_AR_CONTROL_PLANE_READ_BASE_URL}={raw!r}; expected an internal "
            "http://host[:port] control-plane read base URL (fail closed — no silent fallback)"
        )
    issuers = _issuers_from_env()
    # Lazy provider imports keep auth_router/main.py JWT-vendor-free at import: the PyJWT
    # verifier binds the vendor crypto lazily, so it is deferred to selection time.
    from .adapters.providers.http_control_plane_read import HttpControlPlaneRead
    from .adapters.providers.pyjwt_verifier import PyJwtSignatureVerifier

    return build_authenticator(
        verifier=PyJwtSignatureVerifier(),
        read=HttpControlPlaneRead(raw),
        issuers=issuers,
    )


def _authenticate_port_from_env() -> int:
    """Parse ``SP2_AR_AUTHENTICATE_PORT`` fail-closed: unset/empty/whitespace → ``0`` (ephemeral);
    otherwise a base-10 integer in ``[0, 65535]``, else ``ValueError`` — raised BEFORE any socket
    bind so malformed config never opens a listener."""
    raw = (os.environ.get(SP2_AR_AUTHENTICATE_PORT) or "").strip()
    if not raw:
        return 0
    try:
        port = int(raw, 10)
    except ValueError:
        raise ValueError(f"invalid {SP2_AR_AUTHENTICATE_PORT}={raw!r}; expected an integer in [0, 65535]") from None
    if not (0 <= port <= 65535):
        raise ValueError(f"invalid {SP2_AR_AUTHENTICATE_PORT}={raw!r}; port out of range [0, 65535]")
    return port


def build_authenticate_server_from_env() -> Optional[Tuple[object, str]]:
    """The paired authenticate-server composition seam (follow-on to ``build_authenticator_from_env``).

    Authenticator-gate-first: compose the authenticator via ``build_authenticator_from_env()``; if the
    authenticator selector (``SP2_AR_CONTROL_PLANE_READ_BASE_URL``) is inactive it returns ``None`` and this
    seam returns ``None`` WITHOUT consulting the bind knobs. A malformed Slice-1 config (bad URL / invalid
    ``SP2_AR_ISSUERS``) raises ``ValueError`` (inherited) before any host/port parse. When the authenticator
    is composed, read the bind config and construct the server via the existing ``build_authenticate_server``
    adapter, returning ``(server, base_url)``.

    * ``SP2_AR_AUTHENTICATE_HOST`` — optional; unset/empty/whitespace → ``127.0.0.1`` (internal loopback,
      IC-010 §R); otherwise passed through (an unbindable host surfaces as ``OSError`` from the socket
      bind — deployment scope; no deep host validation here).
    * ``SP2_AR_AUTHENTICATE_PORT`` — optional; unset/empty → ``0`` (ephemeral); otherwise an integer in
      ``[0, 65535]``; non-integer / negative / out-of-range → ``ValueError`` raised BEFORE
      ``build_authenticate_server`` so a bad port never binds a socket.

    Side-effect boundary (LOAD-BEARING): this seam is DB-inert, network-read-inert, token-verify-inert, and
    serve-inert — it opens no database, performs no network client read, verifies no token, and starts no
    serve loop, thread, daemon, or service. But it is NOT socket-inert: when active, ``build_authenticate_server``
    binds + activates a local listening socket at construction (default ``port=0`` → ephemeral). Callers/tests
    own the socket lifecycle and must close it.

    No overclaim: it composes an authenticate server *object* from config; it does NOT serve requests, run a
    production service, open a physical database, complete the Physical Multi-Database MVP, or make the
    physical live-topology smoke runnable. It is one prerequisite among several.
    """
    authenticator = build_authenticator_from_env()
    if authenticator is None:
        return None
    host = (os.environ.get(SP2_AR_AUTHENTICATE_HOST) or "").strip() or "127.0.0.1"
    port = _authenticate_port_from_env()
    # Lazy relative import keeps auth_router/main.py import-light (the FastAPI/ASGI serving stack is
    # pulled in only when the seam is active); build_authenticate_server binds the ephemeral socket.
    from .adapters.providers.http_authenticate_api import build_authenticate_server

    return build_authenticate_server(authenticator, host=host, port=port)


def liveness() -> Dict[str, str]:
    return {"service": SERVICE, "status": "alive", "build_phase": "3"}
