"""Authentication application logic: verify a credential, then check the carrier.

Two things happen here and nothing else. The credential is verified (IC-005), and the
recognized carrier the ingress observed is *compared* to the signed claim. The comparison
produces a verdict; it never produces an authority, and it never selects anything.
"""

from __future__ import annotations

import os
from typing import Mapping, Optional

from .models import AuthenticationResponse, CarrierCheck
from .verifier import (
    DenyAllVerifier,
    InvalidCredential,
    IssuerTrustAnchor,
    JwtTokenVerifier,
    StaticTokenVerifier,
    TokenVerifier,
    VerifiedIdentity,
)

#: Explicit configuration selectors. Neither is set by default, and with neither set the
#: service authenticates nobody (see :func:`build_verifier`).
ENV_ISSUERS = "SP2_AUTHENTICATION_ISSUERS"
ENV_STATIC_PRINCIPALS = "SP2_AUTHENTICATION_STATIC_PRINCIPALS"


def check_carrier(identity: VerifiedIdentity, carrier: Optional[str]) -> CarrierCheck:
    """The IC-005 carrier-match check, subordinate to the signed claim (IC-013 §5).

    Match-or-reject only. A carrier never grants tenant access and never selects a
    database — at most it agrees with the claim, and disagreement is fatal.

    The tenantless-CONTROL case is deliberately not a mismatch: per IC-013 §6 and D-33-E1
    the carrier is *ignored* (claim-only) and the anomaly is recorded. Treating it as a
    mismatch would deny a legitimate Control-Workspace request; treating it as ordinary
    would lose the signal that something is addressing Control through a tenant carrier.
    """
    if carrier is None or carrier == "":
        return CarrierCheck.ABSENT
    if identity.active_tenant_ref is None:
        return CarrierCheck.CONTROL_ANOMALY
    if carrier == identity.active_tenant_ref:
        return CarrierCheck.MATCHED
    return CarrierCheck.MISMATCH


class AuthenticationService:
    """Validates identity. Authorizes nothing, routes nothing, opens nothing."""

    def __init__(self, verifier: TokenVerifier) -> None:
        self._verifier = verifier

    def authenticate(self, credential: str, carrier: Optional[str]) -> AuthenticationResponse:
        """Return the trusted identity context, or raise :class:`InvalidCredential`."""
        identity = self._verifier.verify(credential)
        return AuthenticationResponse(
            principal_ref=identity.principal_ref,
            role=identity.role,
            active_tenant_ref=identity.active_tenant_ref,
            carrier_check=check_carrier(identity, carrier),
        )


def _parse_issuers(raw: str) -> dict[str, IssuerTrustAnchor]:
    """Parse ``SP2_AUTHENTICATION_ISSUERS`` into pinned trust anchors."""
    import json

    parsed = json.loads(raw)
    if not isinstance(parsed, dict) or not parsed:
        raise ValueError("issuer configuration must be a non-empty JSON object")

    anchors: dict[str, IssuerTrustAnchor] = {}
    for issuer, entry in parsed.items():
        if not isinstance(entry, dict):
            raise ValueError("issuer entry must be a JSON object")
        audience = entry.get("audience")
        algorithms = entry.get("algorithms")
        public_key = entry.get("public_key_pem")
        if not isinstance(audience, str) or not audience:
            raise ValueError("issuer entry requires an audience")
        if not isinstance(algorithms, list) or not algorithms or not all(isinstance(a, str) for a in algorithms):
            raise ValueError("issuer entry requires a non-empty list of algorithms")
        if not isinstance(public_key, str) or not public_key:
            raise ValueError("issuer entry requires a public_key_pem")
        anchors[issuer] = IssuerTrustAnchor(
            issuer=issuer,
            audience=audience,
            algorithms=frozenset(algorithms),
            public_key_pem=public_key,
        )
    return anchors


def build_verifier(env: Optional[Mapping[str, str]] = None) -> TokenVerifier:
    """Select the verifier from explicit configuration, fail-closed by omission.

    Production configuration (``SP2_AUTHENTICATION_ISSUERS``) wins over the development
    static map, so a stray development variable in a production environment cannot widen
    the trust surface. With neither set, :class:`DenyAllVerifier` is returned: the service
    starts, reports healthy, and authenticates nobody.
    """
    source: Mapping[str, str] = os.environ if env is None else env

    issuers = source.get(ENV_ISSUERS, "").strip()
    if issuers:
        return JwtTokenVerifier(_parse_issuers(issuers))

    static = source.get(ENV_STATIC_PRINCIPALS, "").strip()
    if static:
        return StaticTokenVerifier.from_json(static)

    return DenyAllVerifier()


__all__ = [
    "ENV_ISSUERS",
    "ENV_STATIC_PRINCIPALS",
    "AuthenticationService",
    "InvalidCredential",
    "build_verifier",
    "check_carrier",
]
