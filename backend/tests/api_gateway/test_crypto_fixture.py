"""Real-auth-path validation of the runtime RS256 fixture (PRD B5-5) — NOT Smoke C.

Proves the B5-5 fixture (``crypto_fixture.py``) end-to-end against the REAL existing auth
verification path, network-free and DB-free:

* the REAL ``SP2_AR_ISSUERS`` parser (via ``build_authenticator_from_env``) accepts the
  fixture's runtime public JWK and composes the REAL ``PyJwtSignatureVerifier``;
* a fresh fixture-minted RS256 token is accepted by ``Authenticator.authenticate`` — the
  full real path (``JwtValidator`` + ``TenantContextResolver``) with ZERO network I/O
  (control-scoped and carrier-mismatch legs resolve before any control-plane read; the sole
  network path is armed with a trap that must never trip);
* tenant flows run the REAL verifier/validator/resolver/authenticator over the parsed-by-the-
  real-parser ``IssuerConfig`` map, with only the read port injected as the stdlib double;
* wrong key, unknown kid, unknown issuer, expiry, and wrong carrier fail with the exact
  current denial codes; a second keypair can never validate the first keypair's token;
* the fixture is import-inert, keeps private JWK members out of every public artifact,
  writes no file, prints nothing, and the process environment is always restored.

This module imports NO JWT/crypto vendor itself — the vendor surface stays inside the one
blessed fixture module (exact-file containment). It is isolated auth-fixture validation
only: no gateway, no server, no thread, no database, no Smoke C execution, no standing-
fixture interaction. B5-BLK-4 stays OPEN; the Physical Multi-Database MVP is NOT completed
or advanced by these tests.

Stdlib + fixture only; runnable standalone:
  python tests/api_gateway/test_crypto_fixture.py
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import time
from typing import Dict, Iterator, Optional

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "auth_router"))
sys.path.insert(0, str(_HERE))
import _auth_doubles as A  # noqa: E402
import _h  # noqa: E402
import crypto_fixture as CF  # noqa: E402

from auth_router.adapters.providers.http_control_plane_read import HttpControlPlaneRead  # noqa: E402
from auth_router.adapters.providers.pyjwt_verifier import PyJwtSignatureVerifier  # noqa: E402
from auth_router.authenticator import Authenticator  # noqa: E402
from auth_router.main import (  # noqa: E402
    SP2_AR_CONTROL_PLANE_READ_BASE_URL,
    SP2_AR_ISSUERS,
    build_authenticator,
    build_authenticator_from_env,
)
from auth_router.models import AuthDenied, Role  # noqa: E402

_ISS = "https://issuer.b5-5.test"
_AUD = "snackportal2"
_SUB = "u-b55"
# Structurally valid, never-contacted internal URL (port 9, discard). Every leg exercised here
# resolves BEFORE the control-plane read; the trap below proves no network call ever happens.
_DEAD_URL = "http://127.0.0.1:9"


@contextlib.contextmanager
def _env(values: Dict[str, Optional[str]]) -> Iterator[None]:
    """Set/unset env vars for one test and always restore the prior values (composition-test idiom)."""
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


@contextlib.contextmanager
def _no_network() -> Iterator[None]:
    """Arm the sole control-plane network path with a trap: any read during the block fails loud."""
    sentinel = "b5-5 fixture tests must perform no network I/O"

    def _boom(*args: object, **kwargs: object) -> object:
        raise AssertionError(sentinel)

    orig = HttpControlPlaneRead._get
    HttpControlPlaneRead._get = _boom  # type: ignore[method-assign]
    try:
        yield
    finally:
        HttpControlPlaneRead._get = orig  # type: ignore[method-assign]


def _real_authenticator(keypair: "CF.RS256TestKeypair") -> Authenticator:
    """Env-compose the REAL production authenticator through the REAL SP2_AR_ISSUERS parser."""
    values = {
        SP2_AR_CONTROL_PLANE_READ_BASE_URL: _DEAD_URL,
        SP2_AR_ISSUERS: CF.issuer_env_json(keypair, issuer=_ISS, audience=_AUD),
    }
    with _env(values):
        auth = build_authenticator_from_env()
    assert isinstance(auth, Authenticator), "the real parser must accept the fixture's runtime public JWK"
    return auth


def _denial(auth: Authenticator, minted: str, *, carrier: Optional[str] = None) -> AuthDenied:
    try:
        auth.authenticate(minted, correlation_id="b55-denial", carrier_tenant=carrier)
    except AuthDenied as denied:
        return denied
    raise AssertionError("authenticate must have denied this token (fail closed)")


# --- real parser + real verifier accept a fresh runtime-minted token ---------------------------------
def test_real_path_accepts_fresh_control_scoped_token_no_network() -> None:
    keypair = CF.generate_rs256_keypair()
    auth = _real_authenticator(keypair)
    # The composed verifier is the production asymmetric verifier (by type — this module stays vendor-free).
    assert type(auth._validator._verifier).__name__ == "PyJwtSignatureVerifier"
    # The runtime public JWK is what the real parser wired through (n/e verbatim under the fixture kid).
    wired = auth._issuers[_ISS].jwks[keypair.kid]
    assert isinstance(wired, dict) and wired["n"] == keypair.public_jwk["n"] and wired["e"] == keypair.public_jwk["e"]
    minted = CF.mint_rs256_token(keypair, issuer=_ISS, audience=_AUD, subject=_SUB)
    with _no_network():  # control-scoped resolution returns before any control-plane read
        ctx = auth.authenticate(minted, correlation_id="b55-accept")
    assert ctx.principal_ref == _SUB and ctx.active_tenant_id is None and ctx.role is None


def test_real_path_accepts_tenant_token_over_real_components() -> None:
    # Real verifier + real validator + real resolver + real Authenticator; the parsed-by-the-REAL-parser
    # IssuerConfig map is reused; ONLY the read port is the sanctioned stdlib double (no network exists).
    keypair = CF.generate_rs256_keypair()
    issuers = _real_authenticator(keypair)._issuers
    read = A.FakeControlPlaneRead()
    read.set_tenant("t1", ready=True)
    read.add_member(_SUB, "t1", Role.TENANT_AGENT)
    auth = build_authenticator(verifier=PyJwtSignatureVerifier(), read=read, issuers=issuers)
    minted = CF.mint_rs256_token(keypair, issuer=_ISS, audience=_AUD, subject=_SUB, tenant="t1")
    ctx = auth.authenticate(minted, correlation_id="b55-tenant", carrier_tenant="t1")
    assert ctx.active_tenant_id == "t1" and ctx.role == "TENANT_AGENT" and ctx.principal_ref == _SUB


# --- exact current denial semantics -------------------------------------------------------------------
def test_wrong_key_signature_rejected() -> None:
    keypair_a = CF.generate_rs256_keypair()
    keypair_b = CF.generate_rs256_keypair()
    auth = _real_authenticator(keypair_a)
    # Signed by B but presenting A's kid: the real verifier must refuse the signature.
    forged = CF.mint_rs256_token(keypair_b, issuer=_ISS, audience=_AUD, subject=_SUB, kid_override=keypair_a.kid)
    denied = _denial(auth, forged)
    assert (denied.http_status, denied.public_code) == (401, "bad_signature")


def test_second_keypair_cannot_validate_first_token() -> None:
    keypair_a = CF.generate_rs256_keypair(kid="b55-pinned-kid")
    keypair_b = CF.generate_rs256_keypair(kid="b55-pinned-kid")  # same kid, DIFFERENT key material
    assert keypair_a.public_jwk["n"] != keypair_b.public_jwk["n"], "fresh keypairs must be distinct"
    token_a = CF.mint_rs256_token(keypair_a, issuer=_ISS, audience=_AUD, subject=_SUB)
    denied = _denial(_real_authenticator(keypair_b), token_a)  # trusts B only
    assert (denied.http_status, denied.public_code) == (401, "bad_signature")


def test_unknown_kid_rejected() -> None:
    keypair = CF.generate_rs256_keypair()
    auth = _real_authenticator(keypair)
    minted = CF.mint_rs256_token(keypair, issuer=_ISS, audience=_AUD, subject=_SUB, kid_override="b55-not-in-jwks")
    denied = _denial(auth, minted)
    assert (denied.http_status, denied.public_code) == (401, "unknown_kid")


def test_unknown_issuer_rejected() -> None:
    keypair = CF.generate_rs256_keypair()
    auth = _real_authenticator(keypair)
    minted = CF.mint_rs256_token(keypair, issuer="https://issuer.not-configured.test", audience=_AUD, subject=_SUB)
    denied = _denial(auth, minted)
    assert (denied.http_status, denied.public_code) == (401, "unknown_issuer")


def test_expired_token_rejected() -> None:
    keypair = CF.generate_rs256_keypair()
    auth = _real_authenticator(keypair)
    stale = CF.mint_rs256_token(keypair, issuer=_ISS, audience=_AUD, subject=_SUB, now=int(time.time()) - 600, ttl_seconds=120)
    denied = _denial(auth, stale)
    assert (denied.http_status, denied.public_code) == (401, "expired")


def test_wrong_carrier_rejected_before_any_read() -> None:
    keypair = CF.generate_rs256_keypair()
    auth = _real_authenticator(keypair)
    minted = CF.mint_rs256_token(keypair, issuer=_ISS, audience=_AUD, subject=_SUB, tenant="t1")
    with _no_network():  # the carrier/claim match is checked BEFORE any control-plane read
        denied = _denial(auth, minted, carrier="t2")
    assert (denied.http_status, denied.public_code) == (403, "carrier_mismatch")


def test_unknown_and_not_ready_tenants_deny_per_current_contract() -> None:
    keypair = CF.generate_rs256_keypair()
    issuers = _real_authenticator(keypair)._issuers
    read = A.FakeControlPlaneRead()
    read.set_tenant("t2", ready=False)
    read.add_member(_SUB, "t2", Role.TENANT_AGENT)
    auth = build_authenticator(verifier=PyJwtSignatureVerifier(), read=read, issuers=issuers)
    unknown = _denial(auth, CF.mint_rs256_token(keypair, issuer=_ISS, audience=_AUD, subject=_SUB, tenant="t9"))
    assert (unknown.http_status, unknown.public_code) == (403, "tenant_access_denied")
    not_ready = _denial(auth, CF.mint_rs256_token(keypair, issuer=_ISS, audience=_AUD, subject=_SUB, tenant="t2"))
    assert (not_ready.http_status, not_ready.public_code) == (403, "tenant_not_ready")


# --- fixture hygiene -----------------------------------------------------------------------------------
def test_public_artifacts_carry_no_private_jwk_member() -> None:
    keypair = CF.generate_rs256_keypair()
    for member in CF.PRIVATE_JWK_MEMBERS:
        assert member not in keypair.public_jwk, f"public JWK leaked private member {member!r}"
    parsed = json.loads(CF.issuer_env_json(keypair, issuer=_ISS, audience=_AUD))
    sanitized = parsed[_ISS]["jwks"][keypair.kid]
    assert set(sanitized) == {"kty", "alg", "use", "kid", "n", "e"}, f"sanitized JWK members drifted: {sorted(sanitized)}"
    assert sanitized["kty"] == "RSA" and sanitized["alg"] == "RS256" and sanitized["use"] == "sig"
    assert parsed[_ISS]["allowed_algs"] == ["RS256"] and parsed[_ISS]["tenant_claim"] == "tenant"
    # The private key object never leaks through repr (dataclass excludes it).
    assert "private_key" not in repr(keypair)


def test_import_inert_and_material_is_fresh_per_call() -> None:
    # No module-global key material exists after import (generation is called-only).
    assert not any(isinstance(value, CF.RS256TestKeypair) for value in vars(CF).values()), (
        "the fixture module must hold no module-global keypair"
    )
    first, second = CF.generate_rs256_keypair(), CF.generate_rs256_keypair()
    assert first.kid != second.kid and first.public_jwk["n"] != second.public_jwk["n"], (
        "each call must generate FRESH material (no seed, no reuse)"
    )


def test_no_stdout_stderr_no_file_writes_and_env_restored() -> None:
    prior_env = {k: os.environ.get(k) for k in (SP2_AR_CONTROL_PLANE_READ_BASE_URL, SP2_AR_ISSUERS)}
    out, err = io.StringIO(), io.StringIO()
    with tempfile.TemporaryDirectory() as scratch:
        cwd = os.getcwd()
        os.chdir(scratch)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                keypair = CF.generate_rs256_keypair()
                minted = CF.mint_rs256_token(keypair, issuer=_ISS, audience=_AUD, subject=_SUB)
                config = CF.issuer_env_json(keypair, issuer=_ISS, audience=_AUD)
                auth = _real_authenticator(keypair)
                with _no_network():
                    auth.authenticate(minted, correlation_id="b55-quiet")
        finally:
            os.chdir(cwd)
        assert os.listdir(scratch) == [], "the fixture must write no file"
    assert out.getvalue() == "" and err.getvalue() == "", "no token/key/output may reach stdout/stderr"
    assert minted and minted not in out.getvalue() and "BEGIN" not in config
    for key, value in prior_env.items():
        assert os.environ.get(key) == value, f"process environment must be restored for {key}"


if __name__ == "__main__":
    _h.run(
        [
            test_real_path_accepts_fresh_control_scoped_token_no_network,
            test_real_path_accepts_tenant_token_over_real_components,
            test_wrong_key_signature_rejected,
            test_second_keypair_cannot_validate_first_token,
            test_unknown_kid_rejected,
            test_unknown_issuer_rejected,
            test_expired_token_rejected,
            test_wrong_carrier_rejected_before_any_read,
            test_unknown_and_not_ready_tenants_deny_per_current_contract,
            test_public_artifacts_carry_no_private_jwk_member,
            test_import_inert_and_material_is_fresh_per_call,
            test_no_stdout_stderr_no_file_writes_and_env_restored,
        ]
    )
