"""Stage 1 token validation: signature, alg-confusion, kid, claims (IC-005 / L-1)."""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _auth_doubles as D  # noqa: E402
import _h  # noqa: E402

from auth_router.jwt_validation import JwtValidator  # noqa: E402
from auth_router.models import AuthDenied  # noqa: E402

V = JwtValidator(D.HmacTestVerifier())


def test_valid_token_yields_claims() -> None:
    tok = D.make_hs256_jwt(D.claims(tenant="t1"), secret=b"k1secret", kid="k1")
    c = V.validate(tok, D.issuer_cfg())
    assert c.subject == "user1" and c.tenant == "t1"


def test_reject_alg_none() -> None:
    h = D.b64u(json.dumps({"alg": "none", "kid": "k1"}).encode())
    p = D.b64u(json.dumps(D.claims()).encode())
    try:
        V.validate(h + "." + p + ".", D.issuer_cfg())
        assert False, "alg=none must be rejected"
    except AuthDenied as e:
        assert e.http_status == 401 and e.public_code == "alg_none_rejected"


def test_reject_hs_rs_confusion() -> None:
    cfg = D.issuer_cfg(allowed_algs=["RS256"])  # asymmetric-only issuer
    tok = D.make_hs256_jwt(D.claims(), secret=b"k1secret", kid="k1")  # symmetric token
    try:
        V.validate(tok, cfg)
        assert False, "HS token must be rejected for RS-only issuer"
    except AuthDenied as e:
        assert e.public_code == "alg_not_allowed"


def test_reject_unknown_kid() -> None:
    tok = D.make_hs256_jwt(D.claims(), secret=b"k1secret", kid="other")
    try:
        V.validate(tok, D.issuer_cfg())
        assert False
    except AuthDenied as e:
        assert e.public_code == "unknown_kid"


def test_reject_bad_signature() -> None:
    tok = D.make_hs256_jwt(D.claims(), secret=b"WRONG-SECRET", kid="k1")
    try:
        V.validate(tok, D.issuer_cfg())
        assert False
    except AuthDenied as e:
        assert e.public_code == "bad_signature"


def test_reject_aud_mismatch() -> None:
    tok = D.make_hs256_jwt(D.claims(aud="someone-else"), secret=b"k1secret", kid="k1")
    try:
        V.validate(tok, D.issuer_cfg())
        assert False
    except AuthDenied as e:
        assert e.public_code == "aud_mismatch"


def test_reject_expired() -> None:
    tok = D.make_hs256_jwt(D.claims(ttl=-7200), secret=b"k1secret", kid="k1")
    try:
        V.validate(tok, D.issuer_cfg())
        assert False
    except AuthDenied as e:
        assert e.public_code == "expired"


if __name__ == "__main__":
    _h.run(
        [
            test_valid_token_yields_claims,
            test_reject_alg_none,
            test_reject_hs_rs_confusion,
            test_reject_unknown_kid,
            test_reject_bad_signature,
            test_reject_aud_mismatch,
            test_reject_expired,
        ]
    )
