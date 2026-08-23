"""Day 1.2 — Authentication Service (IC-005).

Covers what the service must do (validate a credential, check the carrier) and, just as
importantly, what it must never do: authorize, route, or open a database.
"""

from __future__ import annotations

import ast
import json
import pathlib

from fastapi.testclient import TestClient

from snackportal2.services.authentication import main as auth_main
from snackportal2.services.authentication.models import CarrierCheck
from snackportal2.services.authentication.service import AuthenticationService, build_verifier, check_carrier
from snackportal2.services.authentication.verifier import (
    DenyAllVerifier,
    InvalidCredential,
    IssuerTrustAnchor,
    JwtTokenVerifier,
    StaticTokenVerifier,
    VerifiedIdentity,
)
from snackportal2.shared.types import PlatformRole

from ._openapi_rules import assert_document

_STATIC = json.dumps(
    {
        "acme-agent-token": {"principal_ref": "p-agent", "role": "TENANT_AGENT", "active_tenant": "acme"},
        "control-token": {"principal_ref": "p-control", "role": "CONTROL", "active_tenant": None},
    }
)


def _service() -> AuthenticationService:
    return AuthenticationService(StaticTokenVerifier.from_json(_STATIC))


# --- Verification --------------------------------------------------------------------

def test_valid_credential_yields_a_references_only_identity() -> None:
    response = _service().authenticate("acme-agent-token", None)
    assert response.principal_ref == "p-agent"
    assert response.role is PlatformRole.TENANT_AGENT
    assert response.active_tenant_ref == "acme"
    assert response.carrier_check is CarrierCheck.ABSENT
    # The credential is consumed, never echoed.
    assert "acme-agent-token" not in response.model_dump_json()


def test_unknown_credential_is_rejected() -> None:
    try:
        _service().authenticate("not-a-token", None)
    except InvalidCredential:
        return
    raise AssertionError("an unknown credential authenticated")


def test_no_configured_trust_anchor_authenticates_nobody() -> None:
    """With neither issuer nor static configuration set, the service is deny-all."""
    verifier = build_verifier(env={})
    assert isinstance(verifier, DenyAllVerifier)
    try:
        verifier.verify("anything-at-all")
    except InvalidCredential:
        return
    raise AssertionError("the unconfigured default verifier authenticated a credential")


def test_production_issuer_configuration_wins_over_the_development_map() -> None:
    """A stray development variable must not widen the trust surface in production."""
    env = {
        "SP2_AUTHENTICATION_ISSUERS": json.dumps(
            {
                "https://idp.example": {
                    "audience": "snackportal2",
                    "algorithms": ["RS256"],
                    "public_key_pem": "-----BEGIN PUBLIC KEY-----\nx\n-----END PUBLIC KEY-----",
                }
            }
        ),
        "SP2_AUTHENTICATION_STATIC_PRINCIPALS": _STATIC,
    }
    assert isinstance(build_verifier(env=env), JwtTokenVerifier)


def test_symmetric_algorithms_are_rejected_at_configuration_time() -> None:
    """A symmetric key would let the verifier mint the tokens it verifies."""
    anchor = IssuerTrustAnchor(
        issuer="https://idp.example",
        audience="snackportal2",
        algorithms=frozenset({"HS256"}),
        public_key_pem="secret",
    )
    try:
        JwtTokenVerifier({"https://idp.example": anchor})
    except ValueError:
        return
    raise AssertionError("a symmetric algorithm was accepted")


def test_static_configuration_rejects_an_unknown_role() -> None:
    """An unknown role must fail at configuration time, never default to a real one."""
    try:
        StaticTokenVerifier.from_json(json.dumps({"t": {"principal_ref": "p", "role": "CONTROL_AI"}}))
    except ValueError:
        return
    raise AssertionError("the reserved CONTROL_AI role was accepted as a token role")


# --- Carrier match (IC-013 §5 / IC-005) ------------------------------------------------

def test_carrier_verdicts() -> None:
    tenant_identity = VerifiedIdentity("p-agent", PlatformRole.TENANT_AGENT, "acme")
    control_identity = VerifiedIdentity("p-control", PlatformRole.CONTROL, None)

    assert check_carrier(tenant_identity, None) is CarrierCheck.ABSENT
    assert check_carrier(tenant_identity, "acme") is CarrierCheck.MATCHED
    assert check_carrier(tenant_identity, "zeta") is CarrierCheck.MISMATCH
    # Tenantless CONTROL: the carrier is ignored (claim-only) and the anomaly is reported so
    # the BFF can emit CarrierOnControlAnomaly (IC-013 §6, D-33-E1 Item 1).
    assert check_carrier(control_identity, "acme") is CarrierCheck.CONTROL_ANOMALY


def test_a_carrier_never_becomes_the_active_tenant() -> None:
    """Match-or-reject only: a carrier can agree with the claim, never replace it."""
    response = _service().authenticate("control-token", "acme")
    assert response.active_tenant_ref is None
    assert response.carrier_check is CarrierCheck.CONTROL_ANOMALY


# --- Separation of concerns -------------------------------------------------------------

_AUTH_PACKAGE = pathlib.Path(auth_main.__file__).parent


def _imported_modules(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_authentication_imports_no_database_driver_and_no_other_service() -> None:
    """IC-005: authentication never chooses a tenant database and never opens one."""
    forbidden = ("psycopg", "sqlalchemy", "asyncpg", "sqlite3")
    for path in sorted(_AUTH_PACKAGE.glob("*.py")):
        modules = _imported_modules(path)
        for name in modules:
            assert not name.startswith(forbidden), path.name + " imports a database driver: " + name
            assert "services." not in name or "services.authentication" in name or name.startswith("."), (
                path.name + " imports another service: " + name
            )


# --- OpenAPI gate ------------------------------------------------------------------------

def test_authentication_openapi_meets_the_standing_rules() -> None:
    assert_document(
        auth_main.app.openapi(),
        service="authentication",
        expected_paths=["/health", "/readiness", "/authenticate"],
        expected_schemas=["AuthenticationRequest", "AuthenticationResponse", "ErrorResponse", "CarrierCheck"],
        required_security_schemes=["InternalServiceBearer"],
    )


def test_authenticate_route_is_protected_and_health_is_not() -> None:
    schema = auth_main.app.openapi()
    assert schema["paths"]["/authenticate"]["post"]["security"] == [{"InternalServiceBearer": []}]
    assert "security" not in schema["paths"]["/health"]["get"]


def test_missing_service_credential_is_a_canonical_401() -> None:
    client = TestClient(auth_main.app, raise_server_exceptions=False)
    response = client.post("/authenticate", json={"credential": "acme-agent-token"})
    assert response.status_code == 401
    assert response.json() == {"status": 401, "code": "unauthenticated"}


def test_invalid_credential_over_http_discloses_nothing() -> None:
    client = TestClient(auth_main.app, raise_server_exceptions=False)
    response = client.post(
        "/authenticate",
        json={"credential": "definitely-not-valid"},
        headers={"Authorization": "Bearer internal-service-credential"},
    )
    assert response.status_code == 401
    assert response.json() == {"status": 401, "code": "unauthenticated"}
