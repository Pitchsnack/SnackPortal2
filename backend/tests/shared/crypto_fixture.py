"""Runtime RS256 test-token fixture (PRD B5-5) — THE one blessed test-only crypto module.

This module is the SINGLE test-side module permitted to import the JWT/crypto vendors
(``jwt``/PyJWT + ``cryptography``) under the exact-file containment allowance in
``tests/architecture/test_vendor_and_db_containment.py`` (``JWT_CRYPTO_FIXTURE_ALLOW``).
It lives under ``tests/shared/`` — a service-neutral home; it was previously under the deleted
``tests/api_gateway/`` tree and moved unchanged when the API Gateway was removed.
Production JWT crypto stays where it always was — the ``PyJwtSignatureVerifier`` provider
under ``auth_router/adapters/providers/``. Production code must never import this module.

Contract (pinned by ``tests/architecture/test_b5_5_smoke_c_spec_and_crypto_fixture.py``):

* import-inert — importing this module performs no work: no key generation, no I/O, no
  environment read, no module-global key material;
* a FRESH RSA keypair is generated only when ``generate_rs256_keypair`` is called; the
  private key lives in process memory only and is NEVER serialized, printed, logged, or
  written to disk (no file-write API exists in this module);
* minting is **RS256 only** with the exact current claim contract (``iss``/``aud``/``sub``/
  ``iat``/``exp`` + the ``tenant`` claim only when a tenant is given; ``kid`` always in the
  header); the token is returned ONLY to the caller — never printed or persisted;
* ``issuer_env_json`` builds a sanitized ``SP2_AR_ISSUERS`` value for a test-process
  environment from the PUBLIC JWK only (``kty``/``alg``/``use``/``kid``/``n``/``e``; private
  members are fail-closed absent).

No overclaim: this fixture mints test credentials for auth-path validation and later Smoke C
harness use. It proves nothing about running services, physical databases, Smoke C, or the
Physical Multi-Database MVP (B5-BLK-4 stays OPEN).
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

import jwt  # PyJWT — permitted ONLY here among tests (exact-file containment allowance)
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

# 2048 is the fixture's pinned RSA modulus size (standard floor for RS256 test material).
RS256_KEY_SIZE = 2048
_PUBLIC_EXPONENT = 65537

# Private JWK members that must NEVER appear in the public JWK this fixture exposes.
PRIVATE_JWK_MEMBERS = ("d", "p", "q", "dp", "dq", "qi", "oth", "k")


@dataclass(frozen=True)
class RS256TestKeypair:
    """A fresh in-memory RS256 test keypair. ``private_key`` is the cryptography
    ``RSAPrivateKey`` object — held only in memory, excluded from ``repr``, and never
    serialized by this module."""

    kid: str
    public_jwk: Dict[str, object]
    private_key: object = field(repr=False)


def generate_rs256_keypair(*, kid: Optional[str] = None, key_size: int = RS256_KEY_SIZE) -> RS256TestKeypair:
    """Generate a FRESH RSA keypair (called-only; never at import; no seed, no reuse, no I/O).

    ``kid`` defaults to a fresh unique test value; callers may pin one. The returned
    ``public_jwk`` is the exact public representation the ``SP2_AR_ISSUERS`` parser and the
    production ``PyJwtSignatureVerifier`` consume (``kty=RSA``, ``alg=RS256``, ``use=sig``,
    ``kid``, correct ``n``/``e``) — private members are fail-closed absent."""
    private_key = rsa.generate_private_key(public_exponent=_PUBLIC_EXPONENT, key_size=key_size)
    vendor_jwk: Dict[str, object] = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    for member in PRIVATE_JWK_MEMBERS:
        if member in vendor_jwk:  # to_jwk(public) emits public members only; fail closed on vendor drift
            raise AssertionError("public JWK must never carry a private member")
    resolved_kid = kid if kid else "b55-" + uuid.uuid4().hex[:12]
    # Rebuilt explicitly so the exposed member set is EXACTLY {kty, n, e, kid, alg, use} across
    # PyJWT versions (some emit extra public members such as key_ops — dropped, never private).
    public_jwk: Dict[str, object] = {
        "kty": vendor_jwk["kty"],
        "n": vendor_jwk["n"],
        "e": vendor_jwk["e"],
        "kid": resolved_kid,
        "alg": "RS256",
        "use": "sig",
    }
    return RS256TestKeypair(kid=resolved_kid, public_jwk=public_jwk, private_key=private_key)


def mint_rs256_token(
    keypair: RS256TestKeypair,
    *,
    issuer: str,
    audience: str,
    subject: str,
    tenant: Optional[str] = None,
    ttl_seconds: int = 120,
    now: Optional[int] = None,
    kid_override: Optional[str] = None,
) -> str:
    """Mint a fresh RS256 token under the exact current claim contract.

    ``tenant=None`` mints a control-plane-scoped token (no tenant claim); otherwise the
    ``tenant`` claim (the current default ``tenant_claim``) is set. ``now``/``ttl_seconds``
    let tests mint short-lived or already-expired tokens. ``kid_override`` lets tests present
    a mismatched ``kid`` header (unknown-kid / wrong-key legs). RS256 is hardcoded — this
    helper can mint nothing else. The token is returned only to the caller."""
    issued_at = int(time.time()) if now is None else int(now)
    payload: Dict[str, object] = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "iat": issued_at,
        "exp": issued_at + int(ttl_seconds),
    }
    if tenant is not None:
        payload["tenant"] = tenant
    return jwt.encode(
        payload,
        keypair.private_key,
        algorithm="RS256",
        headers={"kid": keypair.kid if kid_override is None else kid_override},
    )


def issuer_env_json(
    keypair: RS256TestKeypair,
    *,
    issuer: str,
    audience: str,
    tenant_claim: str = "tenant",
) -> str:
    """The sanitized ``SP2_AR_ISSUERS`` JSON value for a test-process environment.

    Built from the PUBLIC JWK only, in the exact shape ``auth_router.main._issuers_from_env``
    accepts: ``{issuer: {issuer, audience, allowed_algs=["RS256"], jwks={kid: public JWK},
    tenant_claim}}``. Contains no private member, key, token, or secret."""
    entry: Dict[str, object] = {
        "issuer": issuer,
        "audience": audience,
        "allowed_algs": ["RS256"],
        "jwks": {keypair.kid: dict(keypair.public_jwk)},
        "tenant_claim": tenant_claim,
    }
    return json.dumps({issuer: entry})
