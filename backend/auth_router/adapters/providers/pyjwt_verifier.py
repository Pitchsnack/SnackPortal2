"""Production SignatureVerifier using PyJWT algorithm primitives (asymmetric only).

Vendor-neutral JWT crypto (PyJWT + cryptography). Imported ONLY here, under the
adapters/providers containment zone, and never eagerly (so the stdlib test suite,
which uses a test verifier, does not require PyJWT). Validation *policy* stays in
auth_router.jwt_validation; this adapter performs the signature check only.
"""

from __future__ import annotations

import json

from auth_router.ports import SignatureVerifier


class PyJwtSignatureVerifier(SignatureVerifier):
    def __init__(self) -> None:
        from jwt.algorithms import ECAlgorithm, RSAAlgorithm  # PyJWT

        self._algs = {
            "RS256": RSAAlgorithm(RSAAlgorithm.SHA256),
            "RS384": RSAAlgorithm(RSAAlgorithm.SHA384),
            "RS512": RSAAlgorithm(RSAAlgorithm.SHA512),
            "ES256": ECAlgorithm(ECAlgorithm.SHA256),
        }

    def verify_signature(self, signing_input: bytes, signature: bytes, key: object, alg: str) -> bool:
        impl = self._algs.get(alg)
        if impl is None:
            return False  # asymmetric-only; symmetric algs are rejected by policy upstream
        try:
            loaded = impl.from_jwk(json.dumps(key))
            return bool(impl.verify(signing_input, loaded, signature))
        except Exception:
            return False
