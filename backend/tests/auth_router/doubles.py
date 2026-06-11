"""Stdlib test doubles for auth_router (no PyJWT, no network).

Provides an HS256 signature verifier, an in-memory control-plane read, and a JWT
builder so the validation policy + tenant-context logic are exercised end-to-end
without the production PyJWT/HTTP providers.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import pathlib
import sys
import time
from typing import Dict, Optional, Tuple

_BACKEND = pathlib.Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from auth_router.models import FederationView, IssuerConfig, Role, TenantStateView  # noqa: E402
from auth_router.ports import ControlPlaneReadPort, SignatureVerifier  # noqa: E402


def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def make_hs256_jwt(payload: dict, *, secret: bytes, kid: str = "k1", alg: str = "HS256") -> str:
    header = {"alg": alg, "kid": kid, "typ": "JWT"}
    h = b64u(json.dumps(header, separators=(",", ":")).encode())
    p = b64u(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(secret, (h + "." + p).encode("ascii"), hashlib.sha256).digest()
    return h + "." + p + "." + b64u(sig)


class HmacTestVerifier(SignatureVerifier):
    """HS256 verifier (stdlib). `key` is the symmetric secret (bytes)."""

    def verify_signature(self, signing_input: bytes, signature: bytes, key: object, alg: str) -> bool:
        if alg != "HS256" or not isinstance(key, (bytes, bytearray)):
            return False
        expected = hmac.new(bytes(key), signing_input, hashlib.sha256).digest()
        return hmac.compare_digest(expected, signature)


def issuer_cfg(
    issuer: str = "https://platform.snackportal",
    audience: str = "snackportal",
    secret: bytes = b"k1secret",
    kid: str = "k1",
    allowed_algs=None,
    tenant_claim: str = "tenant",
) -> IssuerConfig:
    return IssuerConfig(
        issuer=issuer, audience=audience, allowed_algs=allowed_algs or ["HS256"],
        jwks={kid: secret}, tenant_claim=tenant_claim,
    )


def claims(
    sub: str = "user1",
    iss: str = "https://platform.snackportal",
    aud: str = "snackportal",
    tenant: Optional[str] = "t1",
    ttl: int = 3600,
) -> dict:
    now = int(time.time())
    out = {"sub": sub, "iss": iss, "aud": aud, "iat": now, "exp": now + ttl}
    if tenant is not None:
        out["tenant"] = tenant
    return out


class FakeControlPlaneRead(ControlPlaneReadPort):
    def __init__(self, available: bool = True) -> None:
        self._available = available
        self._federation: Dict[str, FederationView] = {}
        self._states: Dict[str, TenantStateView] = {}
        self._members: set = set()
        self._roles: Dict[Tuple[str, str], Role] = {}

    # --- configuration helpers ---
    def set_tenant(self, tenant_id: str, *, ready: bool = True, lifecycle: str = "Ready") -> None:
        self._states[tenant_id] = TenantStateView(tenant_id=tenant_id, lifecycle_state=lifecycle, ready=ready)

    def add_member(self, principal: str, tenant: str, role: Role) -> None:
        self._members.add((principal, tenant))
        self._roles[(principal, tenant)] = role

    def set_unavailable(self) -> None:
        self._available = False

    # --- port implementation (raises when unavailable -> callers fail closed) ---
    def _guard(self) -> None:
        if not self._available:
            raise RuntimeError("control plane unavailable")

    def get_federation_for_issuer(self, issuer: str) -> Optional[FederationView]:
        self._guard()
        return self._federation.get(issuer)

    def get_tenant_state(self, tenant_id: str) -> Optional[TenantStateView]:
        self._guard()
        return self._states.get(tenant_id)

    def is_member(self, principal_ref: str, tenant_id: str) -> bool:
        self._guard()
        return (principal_ref, tenant_id) in self._members

    def get_role(self, principal_ref: str, tenant_id: str) -> Optional[Role]:
        self._guard()
        return self._roles.get((principal_ref, tenant_id))
