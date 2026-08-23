"""Day 1.3 — Access Control Service.

This file is the IC-014 §13 acceptance set, worked through item by item. It is deliberately
heavier than the other service test modules: Access Control is the one genuinely greenfield
component of the rebuild, it has no existing implementation whose behaviour could be
trusted, and every one of its failure modes is a silent one — an authorizer that wrongly
says yes looks exactly like an authorizer that is working.
"""

from __future__ import annotations

import ast
import pathlib

from fastapi.testclient import TestClient

from snackportal2.services.access_control import main as ac_main
from snackportal2.services.access_control import policy
from snackportal2.services.access_control.membership import DenyAllMemberships, StaticMemberships, build_membership_port
from snackportal2.services.access_control.policy import Decision, Permission, decide, resolve_single_domain
from snackportal2.shared.operations import SHARING_INERT_OPERATIONS, BffOperation, domain_of, unmapped_operations
from snackportal2.shared.security import AuthContext, RequestContext
from snackportal2.shared.types import DatabaseDomain, PlatformRole

from ._openapi_rules import assert_document

_MEMBERS = StaticMemberships({"p-agent": {"acme"}, "p-admin": {"acme", "zeta"}})


def _context(role: PlatformRole, tenant: str | None, principal: str = "p-agent") -> RequestContext:
    return RequestContext.from_auth_context(AuthContext(correlation_id="c-1", principal_ref=principal, role=role, active_tenant_ref=tenant))


def _decide(operation: BffOperation, context: RequestContext, **kwargs: object) -> policy.AccessDecision:
    return decide(operation, context, is_member=_MEMBERS.is_member, **kwargs)  # type: ignore[arg-type]


# --- Taxonomy completeness ---------------------------------------------------------------


def test_every_operation_is_classified_and_carries_a_required_permission() -> None:
    """An unclassified operation would be unauthorizable and, worse, unroutable."""
    assert unmapped_operations() == []
    missing = [op.value for op in BffOperation if op not in policy.REQUIRED_PERMISSION]
    assert missing == [], "operations with no required permission: " + repr(missing)


# --- §13.3 No-fall-through proof ----------------------------------------------------------


def test_allowed_is_returned_from_exactly_one_place_in_decide() -> None:
    """§8.2: a path that could produce Allowed by omission is a contract violation.

    Proven structurally rather than behaviourally. A behavioural test can only probe the
    inputs someone thought of; this counts the ways the function is *capable* of saying
    yes, and there must be exactly one.
    """
    source = pathlib.Path(policy.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "decide")
    allow_sites = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Attribute) and node.attr == "ALLOWED" and isinstance(node.value, ast.Name)
    ]
    assert len(allow_sites) == 1, "decide() can produce ALLOWED from " + str(len(allow_sites)) + " places"


def test_the_single_allow_site_is_the_last_statement_of_decide() -> None:
    """Allowed is reachable only by surviving every check, not by an early exit."""
    tree = ast.parse(pathlib.Path(policy.__file__).read_text(encoding="utf-8"))
    function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "decide")
    last = function.body[-1]
    assert isinstance(last, ast.Return), "decide() does not end in a return"
    assert any(isinstance(node, ast.Attribute) and node.attr == "ALLOWED" for node in ast.walk(last)), (
        "the final statement of decide() is not the allow site"
    )


# --- §13.1 Separation proofs ---------------------------------------------------------------

_AC_PACKAGE = pathlib.Path(ac_main.__file__).parent


def _imports(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_access_control_imports_no_database_driver() -> None:
    """§2/§12: it holds no connection, no DSN, and no driver — not even transitively by import."""
    for path in sorted(_AC_PACKAGE.glob("*.py")):
        for name in _imports(path):
            assert not name.startswith(("psycopg", "sqlalchemy", "asyncpg", "sqlite3")), path.name + " imports a database driver: " + name


def test_access_control_validates_no_token() -> None:
    """§2: it consumes an already-established RequestContext; it never authenticates."""
    for path in sorted(_AC_PACKAGE.glob("*.py")):
        for name in _imports(path):
            assert not name.startswith(("jwt", "jose", "authlib")), path.name + " imports a token library: " + name


def test_access_control_imports_no_other_service_implementation() -> None:
    for path in sorted(_AC_PACKAGE.glob("*.py")):
        for name in _imports(path):
            assert "services." not in name or "services.access_control" in name, path.name + " imports another service: " + name


# --- §13.2 Fail-closed proof (by fault injection, not inspection) -----------------------------


def test_a_raising_membership_lookup_yields_denied() -> None:
    def explode(principal_ref: str, tenant_ref: str) -> bool:
        raise RuntimeError("control plane is down")

    outcome = decide(BffOperation.READ_TENANT_STARTUP, _context(PlatformRole.TENANT_AGENT, "acme"), is_member=explode)
    assert outcome.decision is Decision.DENIED
    assert outcome.domain is None


def test_an_unconfigured_membership_lookup_denies_every_tenant_operation() -> None:
    port = build_membership_port(env={})
    assert isinstance(port, DenyAllMemberships)
    outcome = decide(BffOperation.READ_TENANT_STARTUP, _context(PlatformRole.TENANT_AGENT, "acme"), is_member=port.is_member)
    assert outcome.decision is Decision.DENIED


def test_a_malformed_request_context_is_denied() -> None:
    broken = _context(PlatformRole.TENANT_AGENT, "acme").model_copy(update={"principal_ref": ""})
    assert _decide(BffOperation.READ_TENANT_STARTUP, broken).decision is Decision.DENIED


def test_a_malformed_context_is_denied_even_when_no_later_check_would_catch_it() -> None:
    """Isolates the context-integrity branch (§8.2).

    The previous test would still pass with that branch deleted, because the membership
    check would independently reject an empty principal. This one uses a CONTROL-domain
    operation the role is fully permitted to perform, so the context check is the only
    thing standing between a malformed context and Allowed.
    """
    for update in ({"principal_ref": ""}, {"correlation_id": ""}):
        broken = _context(PlatformRole.CONTROL, None, principal="p-control").model_copy(update=update)
        outcome = _decide(BffOperation.LIST_MEMBERSHIPS, broken)
        assert outcome.decision is Decision.DENIED, "malformed context allowed with " + repr(update)


def test_an_operation_outside_the_enumerated_surface_is_denied() -> None:
    """§5.2: the permission set is closed. Removing a mapping must deny, not default-allow."""
    original = dict(policy.REQUIRED_PERMISSION)
    try:
        policy.REQUIRED_PERMISSION = {  # type: ignore[assignment]
            op: perm for op, perm in original.items() if op is not BffOperation.READ_TENANT_STARTUP
        }
        assert _decide(BffOperation.READ_TENANT_STARTUP, _context(PlatformRole.TENANT_AGENT, "acme")).decision is Decision.DENIED
    finally:
        policy.REQUIRED_PERMISSION = original  # type: ignore[assignment]


# --- §13.4 Membership proof --------------------------------------------------------------------


def test_a_principal_whose_claim_names_a_tenant_they_do_not_belong_to_is_denied() -> None:
    """And denied with no resolved domain, so nothing downstream has anywhere to connect."""
    outcome = _decide(BffOperation.READ_TENANT_STARTUP, _context(PlatformRole.TENANT_AGENT, "zeta"))
    assert outcome.decision is Decision.DENIED
    assert outcome.domain is None


def test_a_member_with_the_permission_is_allowed_and_resolves_one_tenant_domain() -> None:
    outcome = _decide(BffOperation.READ_TENANT_STARTUP, _context(PlatformRole.TENANT_AGENT, "acme"))
    assert outcome.decision is Decision.ALLOWED
    assert outcome.domain is DatabaseDomain.TENANT


def test_membership_alone_does_not_grant_a_permission() -> None:
    """§5.3: membership establishes tenant access, not what may be done there.

    ``p-admin`` is a member of acme, but carries the STARTUP_USER role, which holds no
    tenant-record permission. Both checks are required; neither substitutes for the other.
    """
    outcome = _decide(BffOperation.READ_TENANT_STARTUP, _context(PlatformRole.STARTUP_USER, "acme", principal="p-admin"))
    assert outcome.decision is Decision.DENIED


# --- §13.5 Single-domain proof ---------------------------------------------------------------


def test_a_tenant_operation_can_never_resolve_to_the_control_domain() -> None:
    """ "ACME DB unavailable -> use Control DB" is not a policy this engine can express."""
    tenant_operations = [op for op in BffOperation if domain_of(op) is DatabaseDomain.TENANT]
    assert tenant_operations, "no tenant operations to test"
    for operation in tenant_operations:
        for tenant in (None, "", "acme", "zeta"):
            resolved = resolve_single_domain(operation, _context(PlatformRole.TENANT_AGENT, tenant))
            assert resolved in (None, DatabaseDomain.TENANT), operation.value + " resolved to " + repr(resolved)


def test_a_tenant_operation_without_a_signed_claim_is_an_isolation_denial() -> None:
    """No default tenant, no Control fallback — the request simply has no domain."""
    outcome = _decide(BffOperation.READ_TENANT_STARTUP, _context(PlatformRole.CONTROL, None, principal="p-control"))
    assert outcome.decision is Decision.DENIED
    assert outcome.code.value == "isolation_violation"


def test_a_control_operation_inside_a_tenant_workspace_resolves_control_only() -> None:
    """A global directory read and a tenant operation are distinct requests, never one."""
    resolved = resolve_single_domain(BffOperation.READ_GLOBAL_STARTUP_DIRECTORY, _context(PlatformRole.TENANT_AGENT, "acme"))
    assert resolved is DatabaseDomain.CONTROL


def test_control_holds_no_tenant_record_permission_at_all() -> None:
    """IC-009 §C: a tenantless CONTROL token can never reach a tenant DB."""
    control_permissions = policy.ROLE_PERMISSIONS[PlatformRole.CONTROL]
    tenant_permissions = {policy.REQUIRED_PERMISSION[op] for op in BffOperation if domain_of(op) is DatabaseDomain.TENANT}
    overlap = control_permissions & tenant_permissions
    assert overlap == set(), "CONTROL holds tenant-record permissions: " + repr(sorted(p.value for p in overlap))


# --- §13.6 Consistent denial -----------------------------------------------------------------


def test_unknown_tenant_and_unauthorized_tenant_are_indistinguishable() -> None:
    unknown = _decide(BffOperation.READ_TENANT_STARTUP, _context(PlatformRole.TENANT_AGENT, "no-such-tenant"))
    unauthorized = _decide(BffOperation.READ_TENANT_STARTUP, _context(PlatformRole.TENANT_AGENT, "zeta"))
    assert unknown.decision is unauthorized.decision
    assert unknown.code is unauthorized.code
    assert unknown.domain is unauthorized.domain is None


# --- §13.7 Ownership is not authorization ------------------------------------------------------


def test_owning_a_record_does_not_grant_a_permission_the_role_lacks() -> None:
    outcome = _decide(
        BffOperation.UPDATE_TENANT_STARTUP,
        _context(PlatformRole.STARTUP_USER, "acme"),
        owner_agent_ref="p-agent",
    )
    assert outcome.decision is Decision.DENIED


def test_ownership_reference_never_widens_an_existing_grant() -> None:
    """Ownership is read and then discarded; the decision is identical with and without it."""
    context = _context(PlatformRole.TENANT_AGENT, "acme")
    without = _decide(BffOperation.READ_TENANT_STARTUP, context)
    with_owner = _decide(BffOperation.READ_TENANT_STARTUP, context, owner_agent_ref="someone-else")
    assert without.decision is with_owner.decision


# --- §13.8 Determinism --------------------------------------------------------------------------


def test_identical_inputs_yield_identical_decisions() -> None:
    context = _context(PlatformRole.TENANT_AGENT, "acme")
    results = {(_decide(BffOperation.READ_TENANT_STARTUP, context).decision) for _ in range(25)}
    assert results == {Decision.ALLOWED}


# --- §13.10 AI inertness -------------------------------------------------------------------------


def test_ai_invoke_is_defined_and_granted_to_nobody() -> None:
    assert Permission.AI_INVOKE in set(Permission)
    for role, granted in policy.ROLE_PERMISSIONS.items():
        assert Permission.AI_INVOKE not in granted, role.value + " has been granted ai.invoke"


def test_control_ai_is_not_a_platform_role() -> None:
    """The reserved role must not be bindable, because a bindable role is a grantable one."""
    assert "CONTROL_AI" not in {role.value for role in PlatformRole}


def test_ai_invoke_is_refused_even_if_a_role_is_granted_it() -> None:
    """The ``ai.invoke`` guard must hold independently of the grant table (§9).

    Same reasoning as the sharing guard: ``ai.invoke`` is ungranted today, so a test that
    only checks the grant table would pass with the guard removed. IC-006 will eventually
    add grants; the guard has to be what refuses until then, and that has to be provable now.
    """
    original_perms = dict(policy.REQUIRED_PERMISSION)
    original_roles = dict(policy.ROLE_PERMISSIONS)
    try:
        policy.REQUIRED_PERMISSION = {  # type: ignore[assignment]
            **original_perms,
            BffOperation.READ_TENANT_STARTUP: Permission.AI_INVOKE,
        }
        policy.ROLE_PERMISSIONS = {  # type: ignore[assignment]
            **original_roles,
            PlatformRole.TENANT_AGENT: original_roles[PlatformRole.TENANT_AGENT] | {Permission.AI_INVOKE},
        }
        outcome = _decide(BffOperation.READ_TENANT_STARTUP, _context(PlatformRole.TENANT_AGENT, "acme"))
        assert outcome.decision is Decision.DENIED, "ai.invoke was honoured once granted"
    finally:
        policy.REQUIRED_PERMISSION = original_perms  # type: ignore[assignment]
        policy.ROLE_PERMISSIONS = original_roles  # type: ignore[assignment]


def test_a_tenant_domain_without_a_tenant_reference_is_denied_at_the_second_gate() -> None:
    """Defence in depth for the isolation boundary, made load-bearing.

    ``resolve_single_domain`` already refuses a tenant operation with no signed claim, so
    the second check inside the tenant branch is unreachable in normal operation. It exists
    because that first check is one edit away from being wrong, and an isolation boundary is
    the wrong place to have exactly one guard. Forcing the first check to answer TENANT
    proves the second one actually catches it.
    """
    original = policy.resolve_single_domain
    try:
        policy.resolve_single_domain = lambda operation, context: DatabaseDomain.TENANT  # type: ignore[assignment]
        outcome = _decide(BffOperation.READ_TENANT_STARTUP, _context(PlatformRole.TENANT_AGENT, None))
        assert outcome.decision is Decision.DENIED
        assert outcome.code.value == "isolation_violation"
    finally:
        policy.resolve_single_domain = original  # type: ignore[assignment]


def test_a_populated_ai_owner_reference_never_produces_allowed() -> None:
    """IC-008 V10 / IC-014 §7: pre-IC-006 a populated AI owner is an error, never a grant."""
    outcome = _decide(
        BffOperation.READ_TENANT_STARTUP,
        _context(PlatformRole.TENANT_AGENT, "acme"),
        owner_ai_agent_ref="ai-agent-1",
    )
    assert outcome.decision is Decision.DENIED


def test_ownership_references_are_single_valued_not_collections() -> None:
    """§7: a decision path that iterates a collection of owners is a contract violation."""
    from snackportal2.services.access_control.models import AccessDecisionRequest

    for field in ("owner_agent_ref", "owner_ai_agent_ref"):
        annotation = str(AccessDecisionRequest.model_fields[field].annotation)
        assert "List" not in annotation and "list" not in annotation, field + " is a collection: " + annotation


# --- Governed sharing is authored-but-inert (IC-013 §18 / IC-014 §10) --------------------------------


def test_every_sharing_operation_is_denied_for_every_role() -> None:
    assert SHARING_INERT_OPERATIONS, "the sharing taxonomy is empty; the inertness test proves nothing"
    for operation in SHARING_INERT_OPERATIONS:
        for role in PlatformRole:
            outcome = _decide(operation, _context(role, "acme"))
            assert outcome.decision is Decision.DENIED, operation.value + " allowed for " + role.value


def test_sharing_stays_inert_even_if_a_sharing_permission_is_granted() -> None:
    """The inert guard must be what holds, not the accident of an empty grant table.

    Today no role holds ``share.propose``, so the test above would still pass with the
    inert guard deleted. When IC-007 is promoted to Final somebody will add those grants —
    and at that moment the guard becomes the only thing between a Draft contract and a live
    cross-tenant capability. This test grants the permission now so the guard is load-bearing
    today rather than the day it matters.
    """
    original = dict(policy.ROLE_PERMISSIONS)
    try:
        policy.ROLE_PERMISSIONS = {  # type: ignore[assignment]
            **original,
            PlatformRole.TENANT_AGENT: original[PlatformRole.TENANT_AGENT] | {Permission.SHARE_PROPOSE, Permission.SHARE_READ},
        }
        for operation in SHARING_INERT_OPERATIONS:
            outcome = _decide(operation, _context(PlatformRole.TENANT_AGENT, "acme"))
            assert outcome.decision is Decision.DENIED, operation.value + " became reachable once granted"
    finally:
        policy.ROLE_PERMISSIONS = original  # type: ignore[assignment]


# --- HTTP surface + OpenAPI gate -------------------------------------------------------------------


def test_access_control_openapi_meets_the_standing_rules() -> None:
    assert_document(
        ac_main.app.openapi(),
        service="access_control",
        expected_paths=["/health", "/readiness", "/decisions"],
        expected_schemas=["AccessDecisionRequest", "AccessDecisionResponse", "RequestContext", "BffOperation"],
        required_security_schemes=["InternalServiceBearer"],
    )


def test_decision_endpoint_requires_the_internal_credential() -> None:
    client = TestClient(ac_main.app, raise_server_exceptions=False)
    response = client.post("/decisions", json={})
    assert response.status_code == 401


def test_denial_over_http_is_a_two_hundred_carrying_denied() -> None:
    """The BFF must be able to tell "the answer is no" from "the authorizer is unreachable"."""
    client = TestClient(ac_main.app, raise_server_exceptions=False)
    response = client.post(
        "/decisions",
        headers={"Authorization": "Bearer internal-service-credential"},
        json={
            "context": {
                "correlation_id": "c-1",
                "principal_ref": "p-agent",
                "role": "TENANT_AGENT",
                "tenant_context": "acme",
                "workspace_type": "TENANT_WORKSPACE",
            },
            "operation": "read_tenant_startup",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "denied"
    assert body["resolved_domain"] is None


def test_decision_response_carries_no_identity_or_database_information() -> None:
    """§13.9 reference-only proof."""
    from snackportal2.services.access_control.models import AccessDecisionResponse

    assert set(AccessDecisionResponse.model_fields) == {"decision", "denial_code", "resolved_domain"}
