"""D-42 CLM Stage B — targeted asymmetric OIDC posture tests (default suite; no DB, no socket).

Proves the controlled-local CLM OIDC posture end-to-end through the REAL production
validation stack (``JwtValidator`` + ``PyJwtSignatureVerifier`` + ``Authenticator`` +
``TenantContextResolver``) with real RS256 material from the single blessed crypto fixture:

* an RS256 token from the trusted issuer authenticates — tenantless -> the principal-only
  context; tenant-claim-bearing -> backend-validated membership (lawfulness decided
  exclusively by the backend, D-04);
* ``HS*`` is rejected at validation even under the trusted issuer (alg allowlist);
* ``alg: none`` is rejected;
* a Supabase-shaped HS256 token is structurally excluded (unknown issuer + symmetric alg);
* a signed tenant claim naming a tenant the principal is not a member of is denied
  fail-closed 403 with the consistent no-existence-leak semantic (the CLM ZETA denial);
* the composition boundary refuses any symmetric ``allowed_algs`` entry (fail closed).

RS256 minting comes ONLY from ``tests/shared/crypto_fixture.py`` (vendor containment);
the HS256/none negative tokens are stdlib-crafted (no jwt import here).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import pathlib
import sys
from typing import Any, Dict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _auth_doubles import FakeControlPlaneRead  # noqa: E402

from auth_router.adapters.providers.pyjwt_verifier import PyJwtSignatureVerifier
from auth_router.authenticator import Authenticator
from auth_router.jwt_validation import JwtValidator
from auth_router.main import _issuers_from_env
from auth_router.models import AuthDenied, IssuerConfig
from auth_router.tenant_context import TenantContextResolver
from control_plane.records import Role
from shared.audit import OperationalAudit

_ISSUER = "http://127.0.0.1:8814/realms/sp2-clm-local"
_AUDIENCE = "snackportal2-clm"
_PRINCIPAL = "clm-rehearsal-agent"
_ACME = "tenant-acme"
_ZETA = "tenant-zeta"
_SUPABASE_ISSUER = "https://xyzcompany.supabase.co/auth/v1"

_CRYPTO_FIXTURE = pathlib.Path(__file__).resolve().parents[1] / "shared" / "crypto_fixture.py"


def _fixture() -> Any:
    name = "clm_oidc_crypto_fixture"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _CRYPTO_FIXTURE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _NullAudit(OperationalAudit):
    def initiate(self, event: Any) -> None:
        return


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _stdlib_jwt(header: Dict[str, Any], payload: Dict[str, Any], *, secret: bytes = b"supabase-shared-secret") -> str:
    signing = _b64u(json.dumps(header).encode()) + "." + _b64u(json.dumps(payload).encode())
    signature = _b64u(hmac.new(secret, signing.encode("ascii"), hashlib.sha256).digest())
    return signing + "." + signature


def _authenticator(keypair: Any, read: FakeControlPlaneRead) -> Authenticator:
    fixture = _fixture()
    raw = fixture.issuer_env_json(keypair, issuer=_ISSUER, audience=_AUDIENCE)
    parsed = json.loads(raw)[_ISSUER]
    issuer_cfg = IssuerConfig(
        issuer=parsed["issuer"],
        audience=parsed["audience"],
        allowed_algs=tuple(parsed["allowed_algs"]),
        jwks=parsed["jwks"],
        tenant_claim=parsed["tenant_claim"],
    )
    validator = JwtValidator(PyJwtSignatureVerifier())
    resolver = TenantContextResolver(read)
    return Authenticator(validator, resolver, _NullAudit(), {_ISSUER: issuer_cfg})


def _read_with_acme_membership() -> FakeControlPlaneRead:
    read = FakeControlPlaneRead()
    read.set_tenant(_ACME, ready=True)
    read.set_tenant(_ZETA, ready=True)
    read.add_member(_PRINCIPAL, _ACME, Role.TENANT_AGENT)  # a member of ACME ONLY (never ZETA)
    return read


def _denied_code(authn: Authenticator, signed: str) -> str:
    try:
        authn.authenticate(signed, correlation_id="cid-1")
        raise AssertionError("authentication must be denied")
    except AuthDenied as denied:
        return denied.public_code


def test_rs256_principal_only_login_yields_tenantless_context() -> None:
    fixture = _fixture()
    keypair = fixture.generate_rs256_keypair()
    authn = _authenticator(keypair, _read_with_acme_membership())
    signed = fixture.mint_rs256_token(keypair, issuer=_ISSUER, audience=_AUDIENCE, subject=_PRINCIPAL, tenant=None)
    ctx = authn.authenticate(signed, correlation_id="cid-1")
    assert ctx.principal_ref == _PRINCIPAL
    assert ctx.active_tenant_id is None and ctx.role is None, "no tenant claim -> the principal-only context"


def test_rs256_acme_claim_is_backend_validated_and_carrier_matched() -> None:
    fixture = _fixture()
    keypair = fixture.generate_rs256_keypair()
    authn = _authenticator(keypair, _read_with_acme_membership())
    signed = fixture.mint_rs256_token(keypair, issuer=_ISSUER, audience=_AUDIENCE, subject=_PRINCIPAL, tenant=_ACME)
    ctx = authn.authenticate(signed, correlation_id="cid-1", carrier_tenant=_ACME)
    assert ctx.active_tenant_id == _ACME and ctx.role == Role.TENANT_AGENT.value
    # D-33 carrier match-or-reject: a mismatching carrier is rejected even with a lawful claim.
    assert _mismatch_code(authn, signed) == "carrier_mismatch"


def _mismatch_code(authn: Authenticator, signed: str) -> str:
    try:
        authn.authenticate(signed, correlation_id="cid-1", carrier_tenant=_ZETA)
        raise AssertionError("a mismatching carrier must be rejected")
    except AuthDenied as denied:
        return denied.public_code


def test_unauthorized_tenant_claim_is_denied_fail_closed_with_no_existence_leak() -> None:
    # The CLM ZETA denial: the token is IdP-minted and validly signed, but the principal is
    # not a member of the claimed tenant — lawfulness is decided exclusively by the backend.
    fixture = _fixture()
    keypair = fixture.generate_rs256_keypair()
    read = _read_with_acme_membership()
    authn = _authenticator(keypair, read)
    zeta_token = fixture.mint_rs256_token(keypair, issuer=_ISSUER, audience=_AUDIENCE, subject=_PRINCIPAL, tenant=_ZETA)
    assert _denied_code(authn, zeta_token) == "tenant_access_denied"
    # Consistent disclosure: an entirely UNKNOWN tenant denies with the SAME public code.
    ghost_token = fixture.mint_rs256_token(keypair, issuer=_ISSUER, audience=_AUDIENCE, subject=_PRINCIPAL, tenant="tenant-ghost")
    assert _denied_code(authn, ghost_token) == "tenant_access_denied", "unknown tenant and non-member deny identically"


def test_hs256_under_the_trusted_issuer_is_rejected_by_the_alg_allowlist() -> None:
    fixture = _fixture()
    keypair = fixture.generate_rs256_keypair()
    authn = _authenticator(keypair, _read_with_acme_membership())
    token = _stdlib_jwt(
        {"alg": "HS256", "typ": "JWT", "kid": keypair.kid},
        {"iss": _ISSUER, "aud": _AUDIENCE, "sub": _PRINCIPAL, "exp": 9999999999},
    )
    assert _denied_code(authn, token) == "alg_not_allowed", "HS* is rejected even under the trusted issuer"


def test_alg_none_is_rejected() -> None:
    fixture = _fixture()
    keypair = fixture.generate_rs256_keypair()
    authn = _authenticator(keypair, _read_with_acme_membership())
    signing = (
        _b64u(json.dumps({"alg": "none", "typ": "JWT"}).encode())
        + "."
        + _b64u(json.dumps({"iss": _ISSUER, "aud": _AUDIENCE, "sub": _PRINCIPAL, "exp": 9999999999}).encode())
    )
    assert _denied_code(authn, signing + ".") == "alg_none_rejected"


def test_supabase_shaped_jwt_is_structurally_excluded() -> None:
    # Supabase legacy JWTs are HS256 under a Supabase issuer: the issuer is not a trust
    # anchor (unknown_issuer) — and even a hypothetical anchor could never accept HS*
    # (asymmetric-only allowed_algs at composition + validation).
    fixture = _fixture()
    keypair = fixture.generate_rs256_keypair()
    authn = _authenticator(keypair, _read_with_acme_membership())
    token = _stdlib_jwt(
        {"alg": "HS256", "typ": "JWT"},
        {"iss": _SUPABASE_ISSUER, "aud": "authenticated", "sub": _PRINCIPAL, "role": "authenticated", "exp": 9999999999},
    )
    assert _denied_code(authn, token) == "unknown_issuer"


def test_composition_refuses_symmetric_allowed_algs_fail_closed(monkeypatch: Any) -> None:
    # SP2_AR_ISSUERS composition (auth_router/main.py): a symmetric or 'none' entry in
    # allowed_algs is refused BEFORE any socket — HS* and none are rejected at configuration
    # (IC-005 CLM: asymmetric-only; allowed_algs ⊆ {RS256, RS384, RS512, ES256}).
    def _entry(algs: list) -> str:
        config = {
            "issuer": _ISSUER,
            "audience": _AUDIENCE,
            "allowed_algs": algs,
            "jwks": {"k1": {"kty": "RSA"}},
            "tenant_claim": "tenant",
        }
        return json.dumps({_ISSUER: config})

    for bad in (["HS256"], ["RS256", "HS512"], ["none"], ["RS256", "none"]):
        monkeypatch.setenv("SP2_AR_ISSUERS", _entry(bad))
        raised = False
        try:
            _issuers_from_env()
        except ValueError:
            raised = True
        assert raised, f"allowed_algs {bad} must be refused at composition (fail closed)"
    monkeypatch.setenv("SP2_AR_ISSUERS", _entry(["RS256", "RS384", "RS512", "ES256"]))
    issuers = _issuers_from_env()
    assert set(issuers) == {_ISSUER}
    assert tuple(issuers[_ISSUER].allowed_algs) == ("RS256", "RS384", "RS512", "ES256")
