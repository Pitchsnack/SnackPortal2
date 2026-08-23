"""Day 1.6 — the BFF ingress pipeline and the re-homed carrier contract.

Two of the four behaviours Phase 0 found living only inside the Gateway are exercised here:
the carrier contract (IC-013 §5) and RequestContext construction (§7). The other two —
ingress audit emission (§10) and the single-database assertion (§11) — are exercised through
the pipeline's audit and isolation assertions below.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from snackportal2.services.bff import main as bff_main
from snackportal2.services.bff.carrier import NON_CARRIER_HEADERS, carrier_from_header, carrier_from_host, recognized_carrier
from snackportal2.services.bff.clients import DenyAllAccessControl, DenyAllAuthentication, UnavailableRouting
from snackportal2.services.bff.pipeline import (
    ACTION_CARRIER_MISMATCH,
    ACTION_CARRIER_ON_CONTROL_ANOMALY,
    ACTION_ISOLATION_ANOMALY,
    ACTION_ROUTE_DENIED,
    IngressPipeline,
)
from snackportal2.services.bff.ports import AuthenticationResult, AuthorizationResult, CarrierVerdict
from snackportal2.shared.errors import AppError
from snackportal2.shared.operations import BffOperation
from snackportal2.shared.security import AuthContext, RequestContext
from snackportal2.shared.types import DatabaseDomain, PlatformRole

from ._openapi_rules import assert_document

# --- Carrier contract (IC-013 §5) --------------------------------------------------------

def test_x_tenant_id_is_the_only_recognized_carrier_header() -> None:
    assert carrier_from_header({"X-Tenant-Id": "acme"}) == "acme"
    assert carrier_from_header({"x-tenant-id": "acme"}) == "acme"
    for header in NON_CARRIER_HEADERS:
        assert carrier_from_header({header: "acme"}) is None, header + " was read as a tenant carrier"


def test_prohibited_carriers_are_not_carriers() -> None:
    """Cookies, query parameters, portal state and local storage are never routing authority.

    They are absent from the extractor's inputs entirely, which is stronger than filtering
    them out: there is no parameter through which one could arrive.
    """
    import inspect

    parameters = set(inspect.signature(recognized_carrier).parameters)
    assert parameters == {"headers", "host", "base_domain"}
    for prohibited in ("cookie", "cookies", "query", "params", "workspace", "portal", "storage"):
        assert prohibited not in parameters


def test_a_malformed_carrier_value_is_treated_as_absent() -> None:
    for hostile in ("", "  ", "a" * 200, "acme/../zeta", "acme zeta", "acme\nzeta"):
        assert carrier_from_header({"X-Tenant-Id": hostile}) is None


def test_subdomain_addressing_requires_an_explicitly_configured_base_domain() -> None:
    assert carrier_from_host("acme.example.com") is None
    assert carrier_from_host("acme.example.com", "example.com") == "acme"
    assert carrier_from_host("www.example.com", "example.com") is None
    assert carrier_from_host("example.com", "example.com") is None
    assert carrier_from_host("a.b.example.com", "example.com") is None


def test_two_disagreeing_carriers_are_a_conflict_not_a_precedence_contest() -> None:
    observation = recognized_carrier({"X-Tenant-Id": "zeta"}, "acme.example.com", "example.com")
    assert observation.conflict is True
    assert observation.value is None

    agreeing = recognized_carrier({"X-Tenant-Id": "acme"}, "acme.example.com", "example.com")
    assert agreeing.conflict is False
    assert agreeing.value == "acme"


# --- Pipeline doubles ----------------------------------------------------------------------

class _Authentication:
    def __init__(self, result: Optional[AuthenticationResult]) -> None:
        self._result = result
        self.carriers_seen: List[Optional[str]] = []

    def authenticate(self, credential: str, carrier: Optional[str], correlation_id: str) -> Optional[AuthenticationResult]:
        del credential, correlation_id
        self.carriers_seen.append(carrier)
        return self._result


class _AccessControl:
    def __init__(self, result: AuthorizationResult) -> None:
        self._result = result
        self.calls: List[Tuple[str, Optional[str]]] = []

    def decide(
        self, context: RequestContext, operation: BffOperation, record_ref: Optional[str] = None
    ) -> AuthorizationResult:
        self.calls.append((operation.value, context.tenant_context))
        return self._result


class _Routing(UnavailableRouting):
    def __init__(self) -> None:
        self.resolutions = 0

    def resolve(self, context: RequestContext) -> object:
        self.resolutions += 1
        raise AssertionError("the router must not be reached on a denied request")


class _Audit:
    def __init__(self) -> None:
        self.events: List[Dict[str, Optional[str]]] = []

    def emit(
        self,
        action: str,
        outcome: str,
        correlation_id: str,
        actor_ref: str,
        subject_ref: Optional[str] = None,
        tenant_ref: Optional[str] = None,
        record_ref: Optional[str] = None,
        carrier_ref: Optional[str] = None,
    ) -> None:
        self.events.append(
            {
                "action": action,
                "outcome": outcome,
                "correlation_id": correlation_id,
                "actor_ref": actor_ref,
                "tenant_ref": tenant_ref,
                "record_ref": record_ref,
                "carrier_ref": carrier_ref,
            }
        )


def _auth_result(tenant: Optional[str], verdict: CarrierVerdict, role: PlatformRole = PlatformRole.TENANT_AGENT) -> AuthenticationResult:
    return AuthenticationResult(
        auth_context=AuthContext(correlation_id="c-1", principal_ref="p-agent", role=role, active_tenant_ref=tenant),
        carrier_verdict=verdict,
    )


def _pipeline(
    auth: object, access: object, audit: object, routing: object = None, base_domain: str = ""
) -> IngressPipeline:
    return IngressPipeline(
        authentication=auth,  # type: ignore[arg-type]
        access_control=access,  # type: ignore[arg-type]
        routing=routing if routing is not None else UnavailableRouting(),  # type: ignore[arg-type]
        audit=audit,  # type: ignore[arg-type]
        base_domain=base_domain,
    )


def _expect_denial(pipeline: IngressPipeline, **kwargs: object) -> AppError:
    try:
        pipeline.establish(**kwargs)  # type: ignore[arg-type]
    except AppError as error:
        return error
    raise AssertionError("expected a fail-closed denial")


# --- Flow order and fail-closed behaviour --------------------------------------------------

def test_a_missing_credential_is_a_canonical_401_before_anything_else() -> None:
    auth = _Authentication(None)
    audit = _Audit()
    error = _expect_denial(_pipeline(auth, DenyAllAccessControl(), audit), credential=None, headers={}, host="", correlation_id="c-1")
    assert (error.status, error.code.value) == (401, "unauthenticated")
    assert auth.carriers_seen == [], "authentication was called for a request with no credential"


def test_an_unconfigured_bff_authenticates_nobody() -> None:
    audit = _Audit()
    error = _expect_denial(
        _pipeline(DenyAllAuthentication(), DenyAllAccessControl(), audit),
        credential="anything",
        headers={},
        host="",
        correlation_id="c-1",
    )
    assert error.status == 401


def test_a_carrier_mismatch_is_denied_and_audited_before_any_context_exists() -> None:
    auth = _Authentication(_auth_result("acme", CarrierVerdict.MISMATCH))
    audit = _Audit()
    routing = _Routing()
    error = _expect_denial(
        _pipeline(auth, DenyAllAccessControl(), audit, routing),
        credential="token",
        headers={"X-Tenant-Id": "zeta"},
        host="",
        correlation_id="c-1",
    )
    assert (error.status, error.code.value) == (403, "carrier_mismatch")
    assert [event["action"] for event in audit.events] == [ACTION_CARRIER_MISMATCH]
    assert audit.events[0]["carrier_ref"] == "zeta"
    assert routing.resolutions == 0, "the router was contacted on a carrier mismatch"


def test_two_disagreeing_carriers_are_denied_as_a_mismatch() -> None:
    auth = _Authentication(_auth_result("acme", CarrierVerdict.MATCHED))
    audit = _Audit()
    error = _expect_denial(
        _pipeline(auth, DenyAllAccessControl(), audit, base_domain="example.com"),
        credential="token",
        headers={"X-Tenant-Id": "zeta"},
        host="acme.example.com",
        correlation_id="c-1",
    )
    assert error.code.value == "carrier_mismatch"
    assert [event["action"] for event in audit.events] == [ACTION_CARRIER_MISMATCH]


def test_a_carrier_on_a_control_principal_is_an_anomaly_not_a_denial() -> None:
    """IC-013 §6 / D-33-E1: the carrier is ignored (claim-only) and the anomaly is recorded."""
    auth = _Authentication(_auth_result(None, CarrierVerdict.CONTROL_ANOMALY, PlatformRole.CONTROL))
    audit = _Audit()
    established = _pipeline(auth, DenyAllAccessControl(), audit).establish(
        credential="token", headers={"X-Tenant-Id": "acme"}, host="", correlation_id="c-1"
    )
    assert established.context.tenant_context is None, "a carrier became the active tenant"
    assert [event["action"] for event in audit.events] == [ACTION_CARRIER_ON_CONTROL_ANOMALY]
    assert audit.events[0]["outcome"] == "anomaly"


def test_the_request_context_is_built_only_from_the_signed_claim() -> None:
    auth = _Authentication(_auth_result("acme", CarrierVerdict.MATCHED))
    established = _pipeline(auth, DenyAllAccessControl(), _Audit()).establish(
        credential="token",
        headers={"X-Tenant-Id": "acme", "X-Workspace": "zeta", "Cookie": "tenant=zeta"},
        host="zeta.example.com",
        correlation_id="c-1",
    )
    assert established.context.tenant_context == "acme"
    assert established.context.principal_ref == "p-agent"


# --- Access Control precedes routing (IC-014 §3) -----------------------------------------------

def test_a_denied_request_never_reaches_the_router() -> None:
    auth = _Authentication(_auth_result("acme", CarrierVerdict.MATCHED))
    audit = _Audit()
    routing = _Routing()
    pipeline = _pipeline(auth, _AccessControl(AuthorizationResult(False, "access_denied", None)), audit, routing)
    established = pipeline.establish(credential="t", headers={}, host="", correlation_id="c-1")

    try:
        pipeline.authorize(established.context, BffOperation.READ_TENANT_STARTUP)
    except AppError as error:
        assert (error.status, error.code.value) == (403, "access_denied")
    else:
        raise AssertionError("a denied decision did not deny the request")

    assert routing.resolutions == 0, "the router was contacted after a denial"
    assert [event["action"] for event in audit.events] == [ACTION_ROUTE_DENIED]


def test_allowed_without_a_resolved_domain_is_an_isolation_anomaly() -> None:
    """The BFF enforces that exactly one domain was decided (IC-013 §11).

    An allow that names no domain is not a lawful decision, and honouring it would mean
    invoking a service without knowing which database the request may reach.
    """
    auth = _Authentication(_auth_result("acme", CarrierVerdict.MATCHED))
    audit = _Audit()
    pipeline = _pipeline(auth, _AccessControl(AuthorizationResult(True, None, None)), audit)
    established = pipeline.establish(credential="t", headers={}, host="", correlation_id="c-1")

    try:
        pipeline.authorize(established.context, BffOperation.READ_TENANT_STARTUP)
    except AppError as error:
        assert error.code.value == "isolation_violation"
    else:
        raise AssertionError("an allow with no domain was honoured")
    assert [event["action"] for event in audit.events] == [ACTION_ISOLATION_ANOMALY]


def test_a_domain_disagreeing_with_the_operation_is_an_isolation_anomaly() -> None:
    """A tenant operation allowed for the Control domain is refused, not reconciled."""
    auth = _Authentication(_auth_result("acme", CarrierVerdict.MATCHED))
    audit = _Audit()
    pipeline = _pipeline(auth, _AccessControl(AuthorizationResult(True, None, DatabaseDomain.CONTROL)), audit)
    established = pipeline.establish(credential="t", headers={}, host="", correlation_id="c-1")

    try:
        pipeline.authorize(established.context, BffOperation.READ_TENANT_STARTUP)
    except AppError as error:
        assert error.code.value == "isolation_violation"
    else:
        raise AssertionError("a straddling decision was honoured")
    assert [event["action"] for event in audit.events] == [ACTION_ISOLATION_ANOMALY]


def test_an_allowed_request_returns_the_single_agreed_domain() -> None:
    auth = _Authentication(_auth_result("acme", CarrierVerdict.MATCHED))
    audit = _Audit()
    pipeline = _pipeline(auth, _AccessControl(AuthorizationResult(True, None, DatabaseDomain.TENANT)), audit)
    established = pipeline.establish(credential="t", headers={}, host="", correlation_id="c-1")
    assert pipeline.authorize(established.context, BffOperation.READ_TENANT_STARTUP) is DatabaseDomain.TENANT
    assert audit.events == [], "an allowed request emitted a denial or anomaly event"


# --- The BFF application -------------------------------------------------------------------

def test_bff_openapi_meets_the_standing_rules() -> None:
    assert_document(
        bff_main.app.openapi(),
        service="bff",
        expected_paths=["/health", "/readiness"],
        expected_schemas=["HealthResponse", "ReadinessResponse"],
    )


def test_the_bff_never_names_itself_a_gateway() -> None:
    """IC-013 §0 prohibits the name in package, module, route, config key and env prefix.

    Deliberately scoped to *identifiers*, not to prose. The contract prohibits the word in
    the BFF's package name, module names, route paths, configuration keys and
    environment-variable prefixes — not in a docstring that explains why the BFF is not one.
    A blanket text search would forbid the explanation along with the thing.
    """
    import ast
    import pathlib

    package = pathlib.Path(bff_main.__file__).parent
    for path in sorted(package.glob("*.py")):
        assert "gateway" not in path.name.casefold(), path.name + " is a prohibited module name"
        tree = ast.parse(path.read_text(encoding="utf-8"))

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                assert "gateway" not in node.name.casefold(), path.name + " defines " + node.name
            elif isinstance(node, ast.Name):
                assert "gateway" not in node.id.casefold(), path.name + " uses the identifier " + node.id
            elif isinstance(node, ast.Attribute):
                assert "gateway" not in node.attr.casefold(), path.name + " uses the attribute " + node.attr
            elif isinstance(node, ast.arg):
                assert "gateway" not in node.arg.casefold(), path.name + " has a parameter named " + node.arg

        # Route paths and configuration/environment string constants, as opposed to prose.
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
                if any(name.isupper() for name in targets) and isinstance(node.value, ast.Constant):
                    value = node.value.value
                    if isinstance(value, str):
                        assert "gateway" not in value.casefold(), path.name + " configures " + repr(value)
            if isinstance(node, ast.Call):
                for argument in node.args:
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                        if argument.value.startswith("/"):
                            assert "gateway" not in argument.value.casefold(), path.name + " routes " + argument.value
