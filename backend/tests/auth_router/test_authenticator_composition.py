"""Behavioral tests for the Auth Router config-selectable composition seam.

Proves ``build_authenticator_from_env`` (auth_router/main.py): unset/empty/whitespace
selector keeps the caller's injected composition (returns ``None``) and does NOT consult
``SP2_AR_ISSUERS``; a structurally valid internal ``http`` base URL with valid issuer trust
anchors composes a production ``Authenticator`` wired to the ``HttpControlPlaneRead`` client
bound to exactly that URL + the ``PyJwtSignatureVerifier`` + the parsed
``Dict[str, IssuerConfig]``; a malformed/off-scheme/missing-netloc URL, or (when the selector
is active) a missing/malformed/symmetric-alg/empty issuer config, fails closed with
``ValueError`` — never a silent fallback. Construction is INERT: it performs no network I/O —
proven non-vacuously by arming the sole network path (``HttpControlPlaneRead._get``) with a
trap the test would trip on. ``build_authenticator`` direct-injection behavior stays unchanged.
Stdlib-only; DB-free, network-free (no PyJWT token, no real key material — a placeholder JWK);
runnable standalone:  python tests/auth_router/test_authenticator_composition.py
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import sys
from typing import Dict, Iterator, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _auth_doubles as D  # noqa: E402
import _h  # noqa: E402

from auth_router.adapters.providers.http_control_plane_read import HttpControlPlaneRead  # noqa: E402
from auth_router.authenticator import Authenticator  # noqa: E402
from auth_router.caching import CachingControlPlaneRead  # noqa: E402
from auth_router.main import (  # noqa: E402
    SP2_AR_CONTROL_PLANE_READ_BASE_URL,
    SP2_AR_ISSUERS,
    build_authenticator,
    build_authenticator_from_env,
)

_URL = "http://127.0.0.1:1234"
_ISS = "https://issuer.example"

# A structurally valid issuers config with a PLACEHOLDER public JWK (no real key material,
# no token/secret literal). The seam treats jwks as opaque, so this never touches crypto.
_PLACEHOLDER_JWK = {
    "kty": "RSA",
    "kid": "kid-placeholder",
    "use": "sig",
    "alg": "RS256",
    "n": "placeholder-public-modulus",
    "e": "AQAB",
}


def _issuers_json(
    *,
    issuer: str = _ISS,
    map_key: Optional[str] = None,
    audience: object = "snackportal2",
    allowed_algs: object = ("RS256",),
    jwks: object = None,
    include_tenant_claim: bool = True,
    tenant_claim: object = "tenant",
) -> str:
    """Build a SP2_AR_ISSUERS JSON string; knobs let each test perturb exactly one field."""
    entry: Dict[str, object] = {"issuer": issuer, "audience": audience}
    if allowed_algs is not None:
        entry["allowed_algs"] = list(allowed_algs) if isinstance(allowed_algs, tuple) else allowed_algs
    if jwks is None:
        jwks = {"kid-placeholder": dict(_PLACEHOLDER_JWK)}
    entry["jwks"] = jwks
    if include_tenant_claim:
        entry["tenant_claim"] = tenant_claim
    return json.dumps({map_key if map_key is not None else issuer: entry})


_VALID_ISSUERS = _issuers_json()


@contextlib.contextmanager
def _env(values: Dict[str, Optional[str]]) -> Iterator[None]:
    """Set/unset the given env vars for one test and always restore the prior values."""
    prior = {k: os.environ.get(k) for k in values}
    try:
        for k, v in values.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _expect_value_error(values: Dict[str, Optional[str]], why: str) -> None:
    with _env(values):
        try:
            build_authenticator_from_env()
        except ValueError:
            return
        raise AssertionError(f"{why} must fail closed with ValueError (never a silent fallback)")


# --- selection behavior -----------------------------------------------------------------------------
def test_selector_unset_returns_none() -> None:
    with _env({SP2_AR_CONTROL_PLANE_READ_BASE_URL: None, SP2_AR_ISSUERS: None}):
        assert build_authenticator_from_env() is None, "unset selector must preserve the injected composition"


def test_selector_empty_or_whitespace_returns_none() -> None:
    for value in ("", "   ", "\t"):
        with _env({SP2_AR_CONTROL_PLANE_READ_BASE_URL: value, SP2_AR_ISSUERS: _VALID_ISSUERS}):
            assert build_authenticator_from_env() is None, f"empty/whitespace {value!r} must behave as unset"


def test_inactive_selector_does_not_consult_issuers() -> None:
    # A garbage SP2_AR_ISSUERS value must NOT raise when the selector is unset (issuers not consulted).
    with _env({SP2_AR_CONTROL_PLANE_READ_BASE_URL: None, SP2_AR_ISSUERS: "{ not valid json at all"}):
        assert build_authenticator_from_env() is None, "inactive selector must not consult/parse SP2_AR_ISSUERS"


# --- fail-closed URL boundary ------------------------------------------------------------------------
def test_malformed_url_raises_value_error() -> None:
    for value in ("not a url", "127.0.0.1:1234", "ftp://127.0.0.1:1234", "http//missing-colon"):
        _expect_value_error({SP2_AR_CONTROL_PLANE_READ_BASE_URL: value, SP2_AR_ISSUERS: _VALID_ISSUERS}, repr(value))


def test_https_scheme_raises_value_error() -> None:
    # scheme is pinned to http (internal loopback transport; TLS termination is deployment scope).
    _expect_value_error({SP2_AR_CONTROL_PLANE_READ_BASE_URL: "https://127.0.0.1:8443", SP2_AR_ISSUERS: _VALID_ISSUERS}, "https URL")


def test_missing_netloc_raises_value_error() -> None:
    for value in ("http://", "http:///federation", "http:relative"):
        _expect_value_error({SP2_AR_CONTROL_PLANE_READ_BASE_URL: value, SP2_AR_ISSUERS: _VALID_ISSUERS}, repr(value))


# --- fail-closed issuers boundary (selector active) --------------------------------------------------
def test_active_selector_missing_issuers_raises_value_error() -> None:
    _expect_value_error({SP2_AR_CONTROL_PLANE_READ_BASE_URL: _URL, SP2_AR_ISSUERS: None}, "active selector with unset SP2_AR_ISSUERS")


def test_malformed_issuers_json_raises_value_error() -> None:
    _expect_value_error({SP2_AR_CONTROL_PLANE_READ_BASE_URL: _URL, SP2_AR_ISSUERS: "{not: valid json"}, "malformed issuers JSON")


def test_issuers_not_object_raises_value_error() -> None:
    for value in ("[]", '"a string"', "123", "{}"):
        _expect_value_error({SP2_AR_CONTROL_PLANE_READ_BASE_URL: _URL, SP2_AR_ISSUERS: value}, f"non-object/empty issuers {value!r}")


def test_missing_required_issuer_fields_raises_value_error() -> None:
    # Omit audience (a required field).
    bad = json.dumps({_ISS: {"issuer": _ISS, "allowed_algs": ["RS256"], "jwks": {"k": dict(_PLACEHOLDER_JWK)}}})
    _expect_value_error({SP2_AR_CONTROL_PLANE_READ_BASE_URL: _URL, SP2_AR_ISSUERS: bad}, "issuer entry missing 'audience'")


def test_issuer_not_equal_map_key_raises_value_error() -> None:
    bad = _issuers_json(issuer="https://other.example", map_key=_ISS)
    _expect_value_error({SP2_AR_CONTROL_PLANE_READ_BASE_URL: _URL, SP2_AR_ISSUERS: bad}, "issuer field != map key")


def test_empty_allowed_algs_raises_value_error() -> None:
    bad = _issuers_json(allowed_algs=[])
    _expect_value_error({SP2_AR_CONTROL_PLANE_READ_BASE_URL: _URL, SP2_AR_ISSUERS: bad}, "empty allowed_algs")


def test_symmetric_algs_raise_value_error() -> None:
    for algs in (["HS256"], ["RS256", "HS512"], ["none"], ["PS256"]):
        bad = _issuers_json(allowed_algs=algs)
        _expect_value_error({SP2_AR_CONTROL_PLANE_READ_BASE_URL: _URL, SP2_AR_ISSUERS: bad}, f"non-asymmetric algs {algs}")


def test_empty_or_non_object_jwks_raises_value_error() -> None:
    for jwks in ({}, [], "not-an-object"):
        bad = _issuers_json(jwks=jwks)
        _expect_value_error({SP2_AR_CONTROL_PLANE_READ_BASE_URL: _URL, SP2_AR_ISSUERS: bad}, f"empty/non-object jwks {jwks!r}")


# --- valid composition (white-box) -------------------------------------------------------------------
def test_valid_selector_and_issuers_returns_authenticator() -> None:
    with _env({SP2_AR_CONTROL_PLANE_READ_BASE_URL: _URL, SP2_AR_ISSUERS: _VALID_ISSUERS}):
        auth = build_authenticator_from_env()
    assert isinstance(auth, Authenticator), "a valid selector + issuers must compose an Authenticator"


def test_valid_composition_wires_expected_objects() -> None:
    with _env({SP2_AR_CONTROL_PLANE_READ_BASE_URL: _URL, SP2_AR_ISSUERS: _VALID_ISSUERS}):
        auth = build_authenticator_from_env()
    assert isinstance(auth, Authenticator)
    # White-box: the read client must be the HttpControlPlaneRead bound to exactly the configured URL,
    # wrapped by the read-through cache the composition root always installs.
    cached = auth._resolver._read
    assert isinstance(cached, CachingControlPlaneRead), "the seam must wrap the read in the caching decorator"
    inner = cached._inner
    assert isinstance(inner, HttpControlPlaneRead), "a valid internal http URL must select HttpControlPlaneRead"
    assert inner._base == _URL, "the read client must be bound to exactly the configured base URL"
    # The verifier is the production asymmetric PyJWT verifier (by type name — keeps the test jwt-free).
    assert type(auth._validator._verifier).__name__ == "PyJwtSignatureVerifier", "must compose the PyJwtSignatureVerifier"
    # The parsed issuers map is wired through with the expected IssuerConfig shape.
    assert set(auth._issuers) == {_ISS}, "the parsed issuers map must key on exactly the configured issuer"
    cfg = auth._issuers[_ISS]
    assert type(cfg).__name__ == "IssuerConfig"
    assert cfg.issuer == _ISS and cfg.audience == "snackportal2"
    assert cfg.allowed_algs == ["RS256"]
    assert "kid-placeholder" in cfg.jwks
    assert cfg.tenant_claim == "tenant"


def test_tenant_claim_defaults_when_omitted() -> None:
    with _env({SP2_AR_CONTROL_PLANE_READ_BASE_URL: _URL, SP2_AR_ISSUERS: _issuers_json(include_tenant_claim=False)}):
        auth = build_authenticator_from_env()
    assert isinstance(auth, Authenticator)
    assert auth._issuers[_ISS].tenant_claim == "tenant", "tenant_claim must default to 'tenant' when omitted"


# --- inert construction: no network I/O --------------------------------------------------------------
def test_construction_is_inert_no_network() -> None:
    # HttpControlPlaneRead._get is the SOLE network path. The seam constructs the client but must
    # never call it during composition. Arm _get to raise, compose a valid-but-dead config, and assert
    # composition succeeds without ever tripping the trap; then prove the trap is actually armed.
    sentinel = "composition-must-not-perform-network-io"

    def _boom_get(*args: object, **kwargs: object) -> object:
        raise AssertionError(sentinel)

    orig_get = HttpControlPlaneRead._get
    HttpControlPlaneRead._get = _boom_get  # type: ignore[method-assign]
    try:
        with _env({SP2_AR_CONTROL_PLANE_READ_BASE_URL: _URL, SP2_AR_ISSUERS: _VALID_ISSUERS}):
            auth = build_authenticator_from_env()  # must compose WITHOUT any network call
        assert isinstance(auth, Authenticator), "inert composition must still return an Authenticator"
        # Non-vacuity: the trap is actually armed, so a composition-time network call WOULD have tripped it.
        tripped = False
        try:
            HttpControlPlaneRead(_URL)._get("/federation?issuer=x")
        except AssertionError as exc:
            tripped = sentinel in str(exc)
        assert tripped, "the inert-construction trap was not armed (the inert proof would be vacuous)"
    finally:
        HttpControlPlaneRead._get = orig_get  # type: ignore[method-assign]


# --- direct injection path unchanged -----------------------------------------------------------------
def test_direct_injection_build_authenticator_unchanged() -> None:
    # The additive seam must not disturb build_authenticator's keyword-only injection path.
    auth = build_authenticator(
        verifier=D.HmacTestVerifier(),
        read=D.FakeControlPlaneRead(),
        issuers={"https://platform.snackportal": D.issuer_cfg()},
    )
    assert isinstance(auth, Authenticator), "build_authenticator direct injection must still compose an Authenticator"


if __name__ == "__main__":
    _h.run(
        [
            test_selector_unset_returns_none,
            test_selector_empty_or_whitespace_returns_none,
            test_inactive_selector_does_not_consult_issuers,
            test_malformed_url_raises_value_error,
            test_https_scheme_raises_value_error,
            test_missing_netloc_raises_value_error,
            test_active_selector_missing_issuers_raises_value_error,
            test_malformed_issuers_json_raises_value_error,
            test_issuers_not_object_raises_value_error,
            test_missing_required_issuer_fields_raises_value_error,
            test_issuer_not_equal_map_key_raises_value_error,
            test_empty_allowed_algs_raises_value_error,
            test_symmetric_algs_raise_value_error,
            test_empty_or_non_object_jwks_raises_value_error,
            test_valid_selector_and_issuers_returns_authenticator,
            test_valid_composition_wires_expected_objects,
            test_tenant_claim_defaults_when_omitted,
            test_construction_is_inert_no_network,
            test_direct_injection_build_authenticator_unchanged,
        ]
    )
