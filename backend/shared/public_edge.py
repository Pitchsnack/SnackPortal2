"""The MVP public-boundary security kernel — a LIBRARY, never a runtime component.

This module is the Gateway-free MVP's answer to "who enforces the public boundary?".
It is deliberately a **linked library**, not a service, not a process, not a port, and
not a hop: each route-owning service imports it and enforces its own boundary in-process.
Nothing traverses it, so it is not a gateway, a proxy, a BFF, or a central edge.

**Why a library cannot become a gateway (machine-checked).** ``shared`` is a dependency
leaf under the import-linter contract "shared is a dependency leaf (must not import any
service)". This module therefore *structurally cannot* import, reach, classify, or
forward to any service. A gateway's defining act — receiving a request for service A and
handing it onward — is unavailable to it by construction, not by convention. The guard
that proves this is an existing, unmodified contract.

**What it owns** (exactly the public-boundary obligations, nothing else):

* recognized tenant-carrier extraction — the subdomain and ``X-Tenant-Id`` only, with
  cookies / query-string / workspace state ignored as selectors (IC-005 carriers);
* the straddle check — one request asserting more than one distinct tenant carrier is
  rejected before authentication;
* authentication *consumption* — it calls an injected ``PrincipalAuthenticatorPort``
  (the IC-005 Auth Router, over the existing internal transport). It performs no JWT,
  JWKS, signature, issuer, or OIDC handling and mints no token;
* the ``TrustedPrincipal`` — constructed **exclusively** from the authenticator's result.
  No request header, body, query, cookie, path, or host value can set or alter any of
  its fields. This is the keystone: it is why a client-supplied ``target_tenant_ref``,
  ``actor_ref``, or ``X-Tenant-Id`` is non-authoritative;
* one-request → one-authenticated-active-tenant binding for tenant-scoped routes;
* references-only edge audit emission with per-request de-duplication, and the
  fail-closed audit posture (a denial is never handed back without its evidence, and a
  success is never handed back before its evidence is durable).

**What it does NOT own** — and cannot: route classification, endpoint dispatch, service
selection, response composition for someone else's domain, database resolution, business
logic, or any knowledge that another service exists.
"""

from __future__ import annotations

import ipaddress
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Mapping, Optional, Sequence, Set, Tuple
from urllib.parse import urlsplit

__all__ = [
    "ACTION_CARRIER_MISMATCH",
    "ACTION_CARRIER_ON_CONTROL_ANOMALY",
    "ACTION_ISOLATION_ANOMALY",
    "ACTION_ROUTE_DENIED",
    "ACTION_TENANT_STARTUP_READ",
    "ACTION_TENANT_STARTUP_UPDATE",
    "ACTION_WORKSPACE_MEMBERSHIPS_READ",
    "CARRIER_HEADER",
    "EDGE_AUDIT_ACTIONS",
    "EdgeAuditEvent",
    "EdgeAuditPort",
    "PrincipalAuthenticatorPort",
    "PublicBoundary",
    "PublicBoundaryDenied",
    "PublicRequest",
    "TrustedPrincipal",
    "allowed_origins_from_env",
    "edge_bind_port_from_env",
    "forbidden",
    "internal_base_url_from_env",
    "isolation_anomaly",
    "opaque_carrier_ref",
    "recognized_carriers",
    "unauthenticated",
    "unavailable",
]

CARRIER_HEADER = "x-tenant-id"  # the only recognized carrier header (case-insensitive; IC-005/IC-010 §E)
_CARRIER_REF_MAX_LEN = 64

# The public-edge audit action vocabulary. These are the EXACT seven strings the existing
# Control-Plane operational-audit store already accepts (``control_plane.gateway_audit
# .GATEWAY_AUDIT_STORE_ACTIONS``, mirroring the DDL 012 CHECK). The Gateway-free architecture
# adds no class, removes none, renames none, and re-homes none — it changes only WHICH
# component emits them, from one central Gateway to the route-owning edge. Keeping the strings
# identical is what makes the durable audit home a no-op rather than a schema migration.
ACTION_CARRIER_MISMATCH = "CarrierMismatch"
ACTION_CARRIER_ON_CONTROL_ANOMALY = "CarrierOnControlAnomaly"
ACTION_ROUTE_DENIED = "RouteDenied"
ACTION_ISOLATION_ANOMALY = "IsolationAnomaly"
ACTION_WORKSPACE_MEMBERSHIPS_READ = "workspace_memberships_read"
ACTION_TENANT_STARTUP_READ = "tenant_startup_read"
ACTION_TENANT_STARTUP_UPDATE = "tenant_startup_update"

EDGE_AUDIT_ACTIONS = (
    ACTION_CARRIER_MISMATCH,
    ACTION_CARRIER_ON_CONTROL_ANOMALY,
    ACTION_ROUTE_DENIED,
    ACTION_ISOLATION_ANOMALY,
    ACTION_WORKSPACE_MEMBERSHIPS_READ,
    ACTION_TENANT_STARTUP_READ,
    ACTION_TENANT_STARTUP_UPDATE,
)


# --------------------------------------------------------------------------------------
# Denial vocabulary — EXACTLY the existing IC-005 / IC-010 §L public codes. The
# Gateway-free architecture introduces NO new public_code, so no denial becomes more
# specific, more disclosing, or newly distinguishable to a caller.
# --------------------------------------------------------------------------------------


class PublicBoundaryDenied(Exception):
    """A fail-closed public-boundary denial: a fixed status and a fixed public code only.

    Carries no provider body, exception text, SQL, hostname, database identity, tenant
    topology, token, or credential — a denial discloses the status line and nothing else.
    """

    def __init__(self, http_status: int, public_code: str) -> None:
        super().__init__(public_code)
        self.http_status = http_status
        self.public_code = public_code


def unauthenticated() -> PublicBoundaryDenied:
    return PublicBoundaryDenied(401, "unauthenticated")


def forbidden() -> PublicBoundaryDenied:
    """The consistent denial for unknown tenant, non-member, and not-ready alike.

    IC-005 disclosure: an unknown tenant and a non-member of a real tenant MUST be
    indistinguishable, so neither reveals whether a tenant exists.
    """
    return PublicBoundaryDenied(403, "forbidden")


def carrier_mismatch() -> PublicBoundaryDenied:
    return PublicBoundaryDenied(403, "carrier_mismatch")


def isolation_anomaly() -> PublicBoundaryDenied:
    return PublicBoundaryDenied(403, "isolation_anomaly")


def unavailable() -> PublicBoundaryDenied:
    return PublicBoundaryDenied(503, "unavailable")


# --------------------------------------------------------------------------------------
# Shapes
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PublicRequest:
    """The transport-neutral view of one inbound public request the kernel inspects.

    The kernel reads ONLY ``host``, ``headers`` and ``authorization`` from this. ``method``
    and ``path`` are carried for the owning edge's own use and are never consulted as a
    tenant, principal, or database selector. There is deliberately no ``body``, ``query``,
    or ``cookies`` field on the kernel's view: those channels are prohibited carriers, and
    the cheapest way to guarantee the kernel never reads them is not to hand them over.
    """

    method: str
    path: str
    host: str
    headers: Mapping[str, str]
    authorization: Optional[str]


@dataclass(frozen=True)
class TrustedPrincipal:
    """The authenticated identity + authorized tenant state — the ONLY tenant authority.

    Every field originates in the ``PrincipalAuthenticatorPort`` result. Nothing a client
    can write may reach this structure: the constructor is called in exactly one place
    (``PublicBoundary.admit``) with exactly the authenticator's four values.

    References only (IC-001 / D-14): never a token, credential, JWT, secret, DSN, database
    identity, name, email, or any PII payload. ``active_tenant_id`` is ``None`` for a
    tenantless CONTROL principal (derived, never a field).
    """

    correlation_id: str
    principal_ref: str
    active_tenant_id: Optional[str]
    role: Optional[str]


@dataclass(frozen=True)
class EdgeAuditEvent:
    """One references-only public-edge audit record (IC-010 §J shape, edge-owned home).

    The action vocabulary is unchanged from the Gateway's: the five durably homed CLM
    classes (``tenant_startup_read``, ``tenant_startup_update``,
    ``workspace_memberships_read``, ``route_denied``, ``carrier_mismatch``) plus the two
    in-memory anomaly classes (``carrier_on_control_anomaly``, ``isolation_anomaly``).
    No class is added, removed, renamed, or re-homed by the Gateway-free architecture —
    only the *emitter* changes, from the single central Gateway to the route-owning edge.
    """

    action: str
    correlation_id: str
    outcome: str
    audit_id: str
    occurred_at: str
    event_version: int = 1
    actor_ref: Optional[str] = None
    subject_ref: Optional[str] = None
    tenant_ref: Optional[str] = None
    carrier_ref: Optional[str] = None
    record_ref: Optional[str] = None


# --------------------------------------------------------------------------------------
# Ports
# --------------------------------------------------------------------------------------


class PrincipalAuthenticatorPort(ABC):
    """Authentication consumed as INPUT (IC-005), reached over transport by the adapter.

    The kernel — and every service that links it — performs NO JWT/JWKS/signature/issuer/
    OIDC validation and issues no token. A recognized carrier is passed in so the IC-005
    carrier-match check can reject a mismatch; that is the only permitted use of a carrier.
    Any denial raises ``PublicBoundaryDenied``; any transport failure must be collapsed by
    the adapter to ``unavailable()`` — never to a success and never to a weaker denial.
    """

    @abstractmethod
    def authenticate(self, authorization: Optional[str], carriers: Sequence[str], correlation_id: str) -> TrustedPrincipal: ...


class EdgeAuditPort(ABC):
    """The references-only public-edge audit sink (IC-010 §J emit-set, edge-owned).

    ``emit`` raises on a terminal failure; the kernel and the owning edge translate that
    raise into the fail-closed ``unavailable`` — evidence-before-hand-back.
    """

    @abstractmethod
    def emit(self, event: EdgeAuditEvent) -> None: ...


# --------------------------------------------------------------------------------------
# Carrier extraction (IC-005 carriers / IC-010 §E) — service-agnostic
# --------------------------------------------------------------------------------------


def _subdomain(host: str) -> Optional[str]:
    """The tenant subdomain carrier (the leading DNS label) of a genuine multi-label host.

    A transport address is never a tenant carrier: IPv4/IPv6 literals (bracketed or not,
    with or without a port), single-label hosts (``localhost``), empty and malformed hosts
    all assert NO host carrier and fail closed to ``None``.
    """
    h = host.strip().lower()
    if not h:
        return None
    if h.startswith("["):
        end = h.find("]")
        if end == -1:
            return None
        h = h[1:end]
    elif h.count(":") == 1:
        h = h.split(":", 1)[0]
    if not h:
        return None
    try:
        ipaddress.ip_address(h)
    except ValueError:
        pass  # not an IP literal -> may be a DNS host
    else:
        return None
    labels = h.split(".")
    if len(labels) >= 3 and labels[0]:
        return labels[0]
    return None


def recognized_carriers(request: PublicRequest) -> List[str]:
    """The recognized tenant-carrier VALUES present (subdomain + ``X-Tenant-Id``).

    Reads ONLY the host subdomain and the ``X-Tenant-Id`` header. Cookies, query-string
    parameters, portal/workspace state and client local storage are prohibited routing
    authority and are never read here — nor are they even present on ``PublicRequest``.
    """
    out: List[str] = []
    sub = _subdomain(request.host)
    if sub is not None:
        out.append(sub)
    for key, value in request.headers.items():
        if key.lower() == CARRIER_HEADER and value.strip():
            out.append(value.strip())
    return out


def internal_base_url_from_env(env_name: str) -> Optional[str]:
    """Read one internal ``http://host[:port]`` selector, fail closed.

    The single fail-closed selector rule for every public edge, in one place — the previous
    architecture repeated it six times inside one composition root, which is six chances for
    the three branches to drift apart:

    * unset, or empty/whitespace after stripping -> ``None`` (the caller keeps its injected
      composition; there is deliberately NO loopback default, because a default silently
      activates a transport);
    * a structurally valid internal ``http://host[:port]`` -> the stripped value;
    * anything else -> ``ValueError`` raised at the composition boundary, BEFORE any socket —
      never a silent fallback from malformed production config to a stub.

    Validation is structural only (scheme + netloc; the scheme is pinned to ``http`` because
    this is the internal seam — TLS terminates at a reverse proxy, deployment scope). The
    value is NON-SECRET internal routing config, never a credential, so it is read directly
    from the environment with no secret reference and no secret store.
    """
    raw = (os.environ.get(env_name) or "").strip()
    if not raw:
        return None
    parts = urlsplit(raw)
    if parts.scheme != "http" or not parts.netloc:
        raise ValueError(
            f"unsupported {env_name}={raw!r}; expected an internal http://host[:port] base URL (fail closed — no silent fallback)"
        )
    return raw


def allowed_origins_from_env(env_name: str) -> Tuple[str, ...]:
    """The exact-origin CORS allowlist (comma-separated).

    Unset/empty -> an EMPTY allowlist: every cross-origin request is denied and the browser
    blocks the response. There is no wildcard handling by design — a public edge never emits
    credentialed CORS, so no entry can produce a wildcard-with-credentials response.
    """
    raw = os.environ.get(env_name) or ""
    return tuple(origin.strip() for origin in raw.split(",") if origin.strip())


def edge_bind_port_from_env(env_name: str) -> int:
    """The bind port, fail closed: unset/empty -> ``0`` (ephemeral); else ``[0, 65535]``.

    A malformed value raises ``ValueError`` BEFORE any socket bind, so bad config never opens
    a listener.
    """
    raw = (os.environ.get(env_name) or "").strip()
    if not raw:
        return 0
    try:
        port = int(raw, 10)
    except ValueError:
        raise ValueError(f"invalid {env_name}={raw!r}; expected an integer in [0, 65535]") from None
    if not (0 <= port <= 65535):
        raise ValueError(f"invalid {env_name}={raw!r}; port out of range [0, 65535]")
    return port


def opaque_carrier_ref(value: str) -> str:
    """An opaque, length-bounded rendering of a carrier-asserted tenant id.

    Recorded for anomaly attribution only — never parsed, resolved, or treated as a
    trusted id (IC-005:116).
    """
    return ("carrier:" + value.strip())[:_CARRIER_REF_MAX_LEN]


# --------------------------------------------------------------------------------------
# The kernel
# --------------------------------------------------------------------------------------


class PublicBoundary:
    """The per-request public-boundary enforcement kernel, linked in-process by an edge.

    One instance per composed edge; ``admit`` is pure per request (its only mutable state
    is the per-request de-duplication set it creates itself).
    """

    def __init__(self, *, authenticator: PrincipalAuthenticatorPort, audit: EdgeAuditPort) -> None:
        self._authenticator = authenticator
        self._audit = audit

    # -- audit -------------------------------------------------------------------------

    def emit(
        self,
        action: str,
        outcome: str,
        correlation_id: str,
        *,
        emitted: Optional[Set[Tuple[str, str]]] = None,
        actor_ref: Optional[str] = None,
        subject_ref: Optional[str] = None,
        tenant_ref: Optional[str] = None,
        carrier_ref: Optional[str] = None,
        record_ref: Optional[str] = None,
    ) -> None:
        """Emit one references-only edge event, minting its identity triple.

        Raises ``PublicBoundaryDenied`` (503 ``unavailable``) when the sink fails
        terminally, so every caller collapses fail-closed: a denial is never handed back
        without its evidence, and a success is never handed back before its evidence is
        durable. ``emitted`` gives per-request de-duplication (the same correlation-bound
        action is emitted at most once).
        """
        if emitted is not None:
            key = (action, correlation_id)
            if key in emitted:
                return
            emitted.add(key)
        try:
            self._audit.emit(
                EdgeAuditEvent(
                    action=action,
                    correlation_id=correlation_id,
                    outcome=outcome,
                    audit_id=uuid.uuid4().hex,
                    occurred_at=datetime.now(timezone.utc).isoformat(),
                    event_version=1,
                    actor_ref=actor_ref,
                    subject_ref=subject_ref,
                    tenant_ref=tenant_ref,
                    carrier_ref=carrier_ref,
                    record_ref=record_ref,
                )
            )
        except Exception:
            raise unavailable() from None

    # -- admission ---------------------------------------------------------------------

    def admit(self, request: PublicRequest, correlation_id: str) -> TrustedPrincipal:
        """Authenticate one public request and return the ONLY tenant/principal authority.

        Ordered, fail-closed, and identical for every route family that links it:

        1. **straddle check** — more than one distinct asserted tenant carrier is an
           isolation anomaly, rejected *before* authentication;
        2. **authenticate** — the injected IC-005 port; a denial propagates unchanged;
        3. **carrier-on-CONTROL anomaly** — a recognized carrier on a tenantless CONTROL
           principal is ignored as a selector and audited;
        4. **construct the trusted principal** — exclusively from the port's result.

        Every denial is audited before it is returned; an audit sink failure turns the
        denial into ``unavailable`` rather than an unevidenced hand-back.
        """
        emitted: Set[Tuple[str, str]] = set()
        carriers = recognized_carriers(request)

        # (1) One request asserting >1 distinct tenant carrier is a straddle attempt.
        if len(set(carriers)) > 1:
            self.emit(
                ACTION_ISOLATION_ANOMALY,
                "rejected",
                correlation_id,
                emitted=emitted,
                carrier_ref=opaque_carrier_ref(",".join(sorted(set(carriers)))),
            )
            raise isolation_anomaly()

        # (2) Authentication is consumed as input; the carrier feeds the IC-005 match check.
        try:
            principal = self._authenticator.authenticate(request.authorization, carriers, correlation_id)
        except PublicBoundaryDenied as denied:
            mismatch = denied.public_code == "carrier_mismatch"
            self.emit(
                ACTION_CARRIER_MISMATCH if mismatch else ACTION_ROUTE_DENIED,
                "rejected",
                correlation_id,
                emitted=emitted,
                carrier_ref=opaque_carrier_ref(carriers[0]) if mismatch and carriers else None,
            )
            raise

        # (3) A recognized carrier on a tenantless CONTROL principal is claim-only.
        if principal.active_tenant_id is None and carriers:
            self.emit(
                ACTION_CARRIER_ON_CONTROL_ANOMALY,
                "observed",
                correlation_id,
                emitted=emitted,
                actor_ref=principal.principal_ref,
                carrier_ref=opaque_carrier_ref(carriers[0]),
            )

        # (4) The trusted principal is the port's result and nothing else.
        return principal

    # -- tenant binding ----------------------------------------------------------------

    def require_tenant(self, principal: TrustedPrincipal) -> str:
        """Bind a tenant-scoped route to EXACTLY ONE authenticated active tenant.

        ``One Request -> One Authenticated Active Tenant -> One Physical Tenant Database``:
        this is the only function that yields a tenant id to a tenant-scoped route, and it
        returns the signed active tenant or nothing at all. A tenantless CONTROL principal
        reaching a tenant route is a fail-closed denial, not a straddle and not a default.

        The returned value is the *sole* input the owning service may use to resolve a
        physical database. There is no second source, so there is no second database.
        """
        tenant = principal.active_tenant_id
        if tenant is None:
            self.emit(ACTION_ROUTE_DENIED, "rejected", principal.correlation_id, actor_ref=principal.principal_ref)
            raise forbidden()
        return tenant
