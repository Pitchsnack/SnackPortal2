"""Stage 1 — Token Validation (stateless, DB-free, Control-DB-free, Tenant-DB-free).

A vendor-neutral validation *policy* (parsing + alg allowlist + claim checks) that
delegates ONLY the signature crypto to a SignatureVerifier port. No DB, no session
store, no network beyond the (separately cached) JWKS the verifier was given.
"""
from __future__ import annotations

import base64
import json
import time
from typing import Optional, Tuple

from .models import Claims, IssuerConfig, unauthenticated
from .ports import SignatureVerifier

_DEFAULT_SKEW = 60.0


def _b64url_decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def _split(token: str) -> Tuple[str, str, str]:
    parts = token.split(".")
    if len(parts) != 3:
        raise unauthenticated("malformed_token")
    return parts[0], parts[1], parts[2]


def _audience_ok(aud: object, expected: str) -> bool:
    if isinstance(aud, str):
        return aud == expected
    if isinstance(aud, (list, tuple)):
        return expected in aud
    return False


class JwtValidator:
    def __init__(self, verifier: SignatureVerifier, skew_seconds: float = _DEFAULT_SKEW) -> None:
        self._verifier = verifier
        self._skew = skew_seconds

    def validate(self, token: str, issuer_cfg: IssuerConfig, *, now: Optional[float] = None) -> Claims:
        now = time.time() if now is None else now
        h_b64, p_b64, s_b64 = _split(token)
        try:
            header = json.loads(_b64url_decode(h_b64))
            payload = json.loads(_b64url_decode(p_b64))
        except Exception:
            raise unauthenticated("undecodable_token")

        alg = header.get("alg")
        if not alg or str(alg).lower() == "none":
            raise unauthenticated("alg_none_rejected")
        if alg not in issuer_cfg.allowed_algs:
            # HS/RS confusion guard: asymmetric-only issuers refuse symmetric-alg tokens.
            raise unauthenticated("alg_not_allowed")

        kid = header.get("kid")
        if not kid:
            raise unauthenticated("missing_kid")
        key = issuer_cfg.jwks.get(kid)
        if key is None:
            raise unauthenticated("unknown_kid")

        signing_input = (h_b64 + "." + p_b64).encode("ascii")
        try:
            signature = _b64url_decode(s_b64)
        except Exception:
            raise unauthenticated("bad_signature_encoding")
        if not self._verifier.verify_signature(signing_input, signature, key, alg):
            raise unauthenticated("bad_signature")

        if payload.get("iss") != issuer_cfg.issuer:
            raise unauthenticated("iss_mismatch")
        if not _audience_ok(payload.get("aud"), issuer_cfg.audience):
            raise unauthenticated("aud_mismatch")
        exp = payload.get("exp")
        if exp is None or now > float(exp) + self._skew:
            raise unauthenticated("expired")
        nbf = payload.get("nbf")
        if nbf is not None and now + self._skew < float(nbf):
            raise unauthenticated("not_yet_valid")
        sub = payload.get("sub")
        if not sub:
            raise unauthenticated("missing_sub")

        return Claims(
            subject=sub,
            issuer=issuer_cfg.issuer,
            audience=issuer_cfg.audience,
            tenant=payload.get(issuer_cfg.tenant_claim),
        )
