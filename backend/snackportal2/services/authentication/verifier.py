"""Credential verification (IC-005) — and nothing beyond it.

This module answers *who are you?* It does not answer *what may you do?*, it does not
choose a tenant database, and it never opens one. Those are IC-014 and the Database
Router respectively, and the four-way separation (D-46 §3) depends on this module staying
strictly inside its lane.

Three verifiers, chosen by explicit configuration:

* :class:`DenyAllVerifier` — the default. A service that starts without a configured trust
  anchor authenticates nobody. Failing closed is what makes an unconfigured deployment
  useless rather than open.
* :class:`JwtTokenVerifier` — production. Asymmetric algorithms only, with the issuer,
  audience and public key pinned by configuration.
* :class:`StaticTokenVerifier` — local development and tests, and only when explicitly
  enabled. It is never selected by omission.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Protocol

from ...shared.types import PlatformRole

#: Asymmetric algorithms only. A symmetric algorithm would mean the verifier holds a key
#: capable of *minting* tokens, so possession of the verifying secret would be sufficient
#: to forge any principal. Rejected at configuration time, not at verification time.
ASYMMETRIC_ALGORITHMS = frozenset({"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"})

#: Claim names. ``sub`` is the principal reference; the tenant claim is the signed active
#: tenant and the only routing authority in the system (IC-013 §7).
CLAIM_PRINCIPAL = "sub"
CLAIM_ROLE = "role"
CLAIM_ACTIVE_TENANT = "active_tenant"


class InvalidCredential(Exception):
    """The credential is not valid. Deliberately carries no reason.

    A verifier that explained *why* a credential failed — expired, wrong issuer, unknown
    key, bad signature — would let a prober map the trust configuration one denial at a
    time. Every failure is the same failure to the caller.
    """


@dataclass(frozen=True)
class VerifiedIdentity:
    """The claims a valid credential established. References only."""

    principal_ref: str
    role: PlatformRole
    active_tenant_ref: Optional[str]


class TokenVerifier(Protocol):
    """The verification port every credential path implements."""

    def verify(self, credential: str) -> VerifiedIdentity:
        """Return the verified identity, or raise :class:`InvalidCredential`."""
        ...


class DenyAllVerifier:
    """The fail-closed default: no trust anchor is configured, so nobody authenticates."""

    def verify(self, credential: str) -> VerifiedIdentity:
        del credential
        raise InvalidCredential()


class StaticTokenVerifier:
    """A fixed credential-to-identity map for local development and tests.

    Selected only by explicit configuration (``SP2_AUTHENTICATION_STATIC_PRINCIPALS``).
    It exists so the request-security spine can be exercised end-to-end without standing up
    an identity provider; it is never reachable by omission, and a deployment that sets it
    has deliberately chosen a development posture.
    """

    def __init__(self, principals: Mapping[str, VerifiedIdentity]) -> None:
        self._principals = dict(principals)

    def verify(self, credential: str) -> VerifiedIdentity:
        identity = self._principals.get(credential)
        if identity is None:
            raise InvalidCredential()
        return identity

    @classmethod
    def from_json(cls, raw: str) -> "StaticTokenVerifier":
        """Build from ``{"<credential>": {"principal_ref": ..., "role": ..., "active_tenant": ...}}``."""
        try:
            parsed = json.loads(raw)
        except Exception as exc:  # noqa: BLE001 - configuration error, surfaced at startup
            raise ValueError("static principal configuration is not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("static principal configuration must be a JSON object")

        principals: Dict[str, VerifiedIdentity] = {}
        for credential, claims in parsed.items():
            if not isinstance(claims, dict):
                raise ValueError("static principal entry must be a JSON object")
            role_value = claims.get("role")
            if role_value not in {role.value for role in PlatformRole}:
                # An unknown role must not silently become a default one. Fail at
                # configuration time, where a human can see it.
                raise ValueError("static principal declares an unknown role")
            tenant = claims.get("active_tenant")
            if tenant is not None and not isinstance(tenant, str):
                raise ValueError("static principal active_tenant must be a string or null")
            principal_ref = claims.get("principal_ref")
            if not isinstance(principal_ref, str) or not principal_ref:
                raise ValueError("static principal requires a principal_ref")
            principals[credential] = VerifiedIdentity(
                principal_ref=principal_ref,
                role=PlatformRole(role_value),
                active_tenant_ref=tenant,
            )
        return cls(principals)


@dataclass(frozen=True)
class IssuerTrustAnchor:
    """One pinned OIDC issuer: its public key, permitted algorithms, and audience."""

    issuer: str
    audience: str
    algorithms: frozenset[str]
    public_key_pem: str


class JwtTokenVerifier:
    """Validate an OIDC JWT against pinned issuers (IC-005).

    Vendor-neutral by construction: standard JWT verified with a configured public key. No
    cloud IAM primitive, no Supabase Auth, no provider SDK — the same configuration runs on
    AWS, Azure, Google Cloud and self-hosted (IC-013 §23).
    """

    def __init__(self, anchors: Mapping[str, IssuerTrustAnchor]) -> None:
        if not anchors:
            raise ValueError("a JWT verifier requires at least one configured issuer")
        for anchor in anchors.values():
            unsupported = anchor.algorithms - ASYMMETRIC_ALGORITHMS
            if unsupported:
                raise ValueError("symmetric or unsupported algorithms are rejected: " + ",".join(sorted(unsupported)))
        self._anchors = dict(anchors)

    def verify(self, credential: str) -> VerifiedIdentity:
        import jwt  # imported lazily so the module is importable without the dependency present

        try:
            unverified = jwt.get_unverified_header(credential)
            del unverified  # header is read only to fail fast on a malformed credential
            issuer = str(jwt.decode(credential, options={"verify_signature": False}).get("iss", ""))
        except Exception as exc:
            raise InvalidCredential() from exc

        anchor = self._anchors.get(issuer)
        if anchor is None:
            raise InvalidCredential()

        try:
            claims = jwt.decode(
                credential,
                anchor.public_key_pem,
                algorithms=sorted(anchor.algorithms),
                audience=anchor.audience,
                issuer=anchor.issuer,
                options={"require": ["exp", "iss", "aud", CLAIM_PRINCIPAL]},
            )
        except Exception as exc:
            raise InvalidCredential() from exc

        return _identity_from_claims(claims)


def _identity_from_claims(claims: Mapping[str, object]) -> VerifiedIdentity:
    """Map validated claims onto a :class:`VerifiedIdentity`, fail-closed on anything odd."""
    principal_ref = claims.get(CLAIM_PRINCIPAL)
    if not isinstance(principal_ref, str) or not principal_ref:
        raise InvalidCredential()

    role_value = claims.get(CLAIM_ROLE)
    if not isinstance(role_value, str) or role_value not in {role.value for role in PlatformRole}:
        # An unrecognized role — including the reserved CONTROL_AI role, which is unbound
        # under this revision (IC-014 §5.1) — authenticates nobody.
        raise InvalidCredential()

    tenant = claims.get(CLAIM_ACTIVE_TENANT)
    if tenant is not None and (not isinstance(tenant, str) or not tenant):
        raise InvalidCredential()

    return VerifiedIdentity(
        principal_ref=principal_ref,
        role=PlatformRole(role_value),
        active_tenant_ref=tenant,
    )


__all__ = [
    "ASYMMETRIC_ALGORITHMS",
    "DenyAllVerifier",
    "InvalidCredential",
    "IssuerTrustAnchor",
    "JwtTokenVerifier",
    "StaticTokenVerifier",
    "TokenVerifier",
    "VerifiedIdentity",
]
