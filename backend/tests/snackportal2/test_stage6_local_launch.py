"""Stage 6 — the local launch is described in four places, and they must agree.

A working local launch is spread across four artefacts that no single reader sees at once:

    infrastructure/docker/docker-compose.rebuild.yml    what runs, and how it is wired
    infrastructure/docker/.env.rebuild.template         what a developer must supply
    backend/tools/local/sp2_local.py                    what migrates, seeds and verifies
    backend/snackportal2/shared/config.py               what the services actually are

Every check here exists because a specific disagreement between two of them would leave the
stack *running* and *silently wrong* rather than broken. Three are worth naming:

* The seeded membership principal and the principal a local token maps to are written in two
  different files. If they drift, authentication succeeds, authorization denies, and the symptom
  is a 403 with no indication that a seed and a verifier map disagree about a name.

* The tenant DSN variable name is not free. The Database Router derives it from the association
  the Control registry returns, so the seed's ``assoc/<tenant>`` and the compose file's
  ``SP2_TENANT_DSN_ASSOC_<TENANT>_1`` are two halves of one fact. Rename either alone and that
  tenant becomes permanently unresolvable, reported as an ordinary outage.

* A variable the compose file requires but the template never mentions is a variable a developer
  cannot know to set. The failure is loud, but it arrives with no way to fix it.

Pure stdlib apart from importing the rebuild's own configuration, which is the point: the
service registry is the authority, and everything else is checked against it.

Runnable standalone:  python tests/snackportal2/test_stage6_local_launch.py
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
from typing import Any, Dict, List, Set

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BACKEND = _REPO_ROOT / "backend"
_DOCKER = _REPO_ROOT / "infrastructure" / "docker"

_COMPOSE = _DOCKER / "docker-compose.rebuild.yml"
_TEMPLATE = _DOCKER / ".env.rebuild.template"
_RUNBOOK = _REPO_ROOT / "docs" / "Local_Development_Runbook.md"

#: Stage 6A — the committed local identity-provider realm. Placeholders only; the file the
#: container imports is generated from it into an untracked directory.
_REALM_TEMPLATE = _DOCKER / "keycloak" / "realm-sp2-local.template.json"

_COMPOSE_TEXT = _COMPOSE.read_text(encoding="utf-8")
_TEMPLATE_TEXT = _TEMPLATE.read_text(encoding="utf-8")


def _tool() -> Any:
    """The operator tool, imported for its declared constants.

    Imported here rather than at module scope so a collection error in the tool cannot take the
    whole test module out; and by path insertion, because `tools` is deliberately not installed.
    """
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    import tools.local.sp2_local as module

    return module


def interpolated_variables(text: str) -> Set[str]:
    """Every ``${VAR}`` the compose file reads from the env file."""
    return set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", text))


def required_variables(text: str) -> Set[str]:
    """Every ``${VAR:?...}`` — the ones a launch hard-fails without."""
    return set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*):\?", text))


def template_keys(text: str) -> Dict[str, str]:
    """``KEY=VALUE`` pairs declared in the template, comments excluded."""
    values: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def service_environment(text: str, service: str) -> Dict[str, str]:
    """The ``environment:`` mapping of one compose service, as literal text per key.

    A small indentation scanner rather than a YAML library, for the same reason the exposure
    check uses one: this suite is stdlib-only, and adding a parser dependency to satisfy a
    handful of checks is a poor trade. It is self-tested against a planted document below.
    """
    lines = text.splitlines()
    environment: Dict[str, str] = {}

    in_services = False
    service_indent = 0
    in_target = False
    in_environment = False
    environment_indent = 0
    pending_key = ""

    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())

        if not in_services:
            if indent == 0 and stripped == "services:":
                in_services = True
            continue
        if indent == 0:
            break

        if service_indent == 0:
            service_indent = indent

        if indent == service_indent and stripped.endswith(":"):
            in_target = stripped[:-1].strip() == service
            in_environment = False
            pending_key = ""
            continue

        if not in_target:
            continue

        if not in_environment:
            if stripped.startswith("environment:"):
                in_environment = True
                environment_indent = 0
            continue

        if environment_indent == 0:
            environment_indent = indent
        if indent < environment_indent:
            in_environment = False
            continue

        if indent > environment_indent and pending_key:
            # A folded block scalar (`>-`) continuation line.
            environment[pending_key] += " " + stripped
            continue

        if ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            if key.startswith("<<"):
                continue
            environment[key] = "" if value in (">-", "|", ">") else value
            pending_key = key if value in (">-", "|", ">") else ""

    return environment


# --- the fourteen services -------------------------------------------------------------------


def test_the_manifest_and_the_service_registry_agree_on_every_service_and_port() -> None:
    from snackportal2.shared.config import SERVICE_REGISTRY

    for key, descriptor in SERVICE_REGISTRY.items():
        compose_name = key.replace("_", "-")
        environment = service_environment(_COMPOSE_TEXT, compose_name)
        assert environment, "service " + compose_name + " has no environment block in the manifest"

        prefix = "SP2_" + key.upper()
        assert environment.get(prefix + "_PORT", "").strip('"') == str(descriptor.default_port), (
            compose_name + " declares a port that disagrees with the service registry"
        )
        assert '"' + str(descriptor.default_port) + '"' in _COMPOSE_TEXT, "port " + str(descriptor.default_port) + " is unused"

        command = 'uvicorn", "snackportal2.services.' + key + ".main:app"
        assert command in _COMPOSE_TEXT, compose_name + " does not start its own module: " + command


def test_the_operator_tool_and_the_service_registry_agree() -> None:
    """The tool duplicates the service list on purpose; this is what makes that safe."""
    from snackportal2.shared.config import PUBLIC_INGRESS_SERVICE, SERVICE_REGISTRY

    module = _tool()
    tool_services = {name.replace("-", "_"): port for name, port in module.SERVICES}
    registry = {key: descriptor.default_port for key, descriptor in SERVICE_REGISTRY.items()}
    assert tool_services == registry, "the operator tool's service list has drifted from the registry"
    assert module.PUBLIC_SERVICE == PUBLIC_INGRESS_SERVICE.replace("_", "-"), "the tool names the wrong public ingress"


# --- migration chains -------------------------------------------------------------------------


def test_the_tool_applies_exactly_the_chains_the_stage_4_harness_proved() -> None:
    """Same files, same order. A second, divergent migration order is a second schema."""
    module = _tool()
    sys.path.insert(0, str(_BACKEND / "tests" / "snackportal2" / "requires_pg"))
    import _stage4_pg  # noqa: PLC0415

    tool_control = [path.name for path in module.control_chain()]
    tool_tenant = [path.name for path in module.tenant_chain()]
    harness_control = [path.name for path in _stage4_pg.control_chain()]
    harness_tenant = [path.name for path in _stage4_pg.tenant_chain()]

    assert tool_control == harness_control, "the tool's Control chain differs from the accepted one"
    assert tool_tenant == harness_tenant, "the tool's tenant chain differs from the accepted one"
    assert tool_control, "the Control chain is empty; this check would be vacuous"
    assert tool_tenant, "the tenant chain is empty; this check would be vacuous"

    # M-1 must be in the Control chain — the BFF's audit table lives there, and a chain that
    # merely globbed an empty directory would still satisfy the equality above.
    assert "016_bff_ingress_audit.sql" in tool_control, "migration M-1 is missing from the Control chain"
    assert "017_bff_ingress_audit_append_only.sql" in tool_control, "M-1's append-only rule is missing"


# --- the env template -----------------------------------------------------------------------


def test_the_template_declares_every_variable_the_manifest_requires() -> None:
    """A variable a launch hard-fails without, that the template never mentions, is unfixable."""
    declared = set(template_keys(_TEMPLATE_TEXT))
    required = required_variables(_COMPOSE_TEXT)
    assert required, "no required variables found in the manifest; this check would be vacuous"
    missing = sorted(required - declared)
    assert missing == [], "required by the manifest but absent from the template: " + repr(missing)


def test_the_template_declares_every_variable_the_manifest_interpolates() -> None:
    """Optional variables too: an undocumented knob is a knob nobody turns deliberately."""
    declared = set(template_keys(_TEMPLATE_TEXT))
    missing = sorted(interpolated_variables(_COMPOSE_TEXT) - declared)
    assert missing == [], "interpolated by the manifest but absent from the template: " + repr(missing)


def test_the_template_carries_no_usable_secret_value() -> None:
    """Every generated value is EMPTY in the committed template.

    Not merely "not a real secret". A placeholder long enough to satisfy the 32-character
    lineage-key floor would be a working key that lives in the repository, and would be left in
    place precisely because it works.
    """
    module = _tool()
    declared = template_keys(_TEMPLATE_TEXT)
    for name in module.GENERATED_VARIABLES:
        assert name in declared, "the tool generates " + name + " but the template does not declare it"
        assert declared[name] == "", "the committed template carries a value for " + name


def test_the_generated_env_file_is_untracked() -> None:
    """The template is the only env file in git."""
    ignore_rules = (_DOCKER / ".gitignore").read_text(encoding="utf-8")
    assert ".env.rebuild" in ignore_rules, "the generated env file is not gitignored"
    assert "!.env.rebuild.template" in ignore_rules, "the template is ignored and would never be committed"

    tracked = [path.name for path in _DOCKER.iterdir() if path.name.startswith(".env")]
    for name in tracked:
        if name.endswith(".template"):
            continue
        # A real env file may exist locally; it must not be a tracked one. Checked by the ignore
        # rules above rather than by shelling out to git, which the stdlib-only suite avoids.
        assert name in (".env.local", ".env.rebuild"), "unexpected env file present: " + name


# --- the seed, the tokens, and the router allowlist ------------------------------------------


def _static_principal_map() -> Dict[str, Dict[str, object]]:
    """The local principal map the manifest assembles, with the ``${TOKEN}`` names as keys."""
    raw = service_environment(_COMPOSE_TEXT, "authentication").get("SP2_AUTHENTICATION_STATIC_PRINCIPALS", "")
    assert raw, "the manifest declares no local principal map"
    # Replace each interpolation with the variable name, so the JSON is parseable and each entry
    # is still identified by the variable that supplies its token.
    parsed = json.loads(re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-[^}]*)?\}", r"\1", raw))
    assert isinstance(parsed, dict)
    return {str(key): dict(value) for key, value in parsed.items()}


def test_the_seeded_memberships_and_the_local_tokens_name_the_same_principals() -> None:
    """The drift that leaves the stack running and silently unauthorized."""
    module = _tool()
    principals = _static_principal_map()

    for variable, expected_principal in module.TOKEN_VARIABLES.items():
        assert variable in principals, "the manifest's principal map has no entry for " + variable
        assert principals[variable].get("principal_ref") == expected_principal, (
            variable + " maps to " + repr(principals[variable].get("principal_ref")) + ", the tool expects " + repr(expected_principal)
        )

    seeded = {principal for principal, _tenant, _role in module.SEED_MEMBERSHIPS}
    for variable, claims in principals.items():
        principal = str(claims.get("principal_ref"))
        tenant = claims.get("active_tenant")
        if tenant is None:
            # A tenantless CONTROL principal holds no membership by design, and seeding one would
            # be wrong: CONTROL authority is Control-resident and reaches no tenant database.
            assert claims.get("role") == "CONTROL", variable + " is tenantless but is not CONTROL"
            assert principal not in seeded, "a tenantless CONTROL principal must not hold a membership"
            continue
        assert principal in seeded, principal + " has a token but no seeded membership; every request would be denied"

    for principal, tenant, role in module.SEED_MEMBERSHIPS:
        matches = [claims for claims in principals.values() if claims.get("principal_ref") == principal]
        assert matches, principal + " is seeded but no token maps to it"
        assert matches[0].get("active_tenant") == tenant, principal + " is seeded into a different tenant than its token claims"
        assert role in {"MASTER_AGENT", "TENANT_ADMIN", "TENANT_AGENT"}, principal + " holds a role with no tenant-record permission"


def test_no_local_principal_is_a_member_of_two_tenants() -> None:
    """The isolation check needs a principal that genuinely cannot reach the other tenant."""
    module = _tool()
    seen: Dict[str, str] = {}
    for principal, tenant, _role in module.SEED_MEMBERSHIPS:
        assert principal not in seen, principal + " is seeded into two tenants; the isolation check proves nothing"
        seen[principal] = tenant
    assert len(set(seen.values())) == len(seen), "two local principals share a tenant"


def test_the_tenant_dsn_variable_names_match_the_seeded_associations() -> None:
    """The two halves of one fact: the seeded association, and the variable the router derives."""
    from snackportal2.services.database_router.resolver import EnvironmentTenantSecretStore

    module = _tool()
    router_environment = service_environment(_COMPOSE_TEXT, "database-router")
    version = str(module.ASSOCIATION_VERSION)

    for tenant_ref in module.TENANTS:
        expected = EnvironmentTenantSecretStore.variable_name("assoc/" + tenant_ref, version)
        assert expected in router_environment, (
            "the router will look up " + expected + " for tenant " + tenant_ref + ", and the manifest does not set it"
        )
        assert "@" + tenant_ref + "-postgres:5432/" in router_environment[expected], (
            expected + " does not point at the " + tenant_ref + " cluster"
        )


def test_only_the_database_router_holds_a_tenant_dsn() -> None:
    """It is the only service permitted to turn a reference into a credential."""
    from snackportal2.shared.config import SERVICE_REGISTRY

    for key in SERVICE_REGISTRY:
        if key == "database_router":
            continue
        environment = service_environment(_COMPOSE_TEXT, key.replace("_", "-"))
        offenders = sorted(name for name in environment if name.startswith("SP2_TENANT_DSN_"))
        assert offenders == [], key + " is given a tenant DSN: " + repr(offenders)


def test_the_grant_allowlist_excludes_the_bff_and_access_control_and_names_only_tenant_services() -> None:
    """D-48 C-1, checked against the manifest rather than only against the code that enforces it."""
    from snackportal2.services.database_router.grants import PERMANENTLY_EXCLUDED, TENANT_RESIDENT_SERVICES

    raw = service_environment(_COMPOSE_TEXT, "database-router").get("SP2_DATABASE_ROUTER_GRANTEES", "")
    assert raw, "the manifest declares no grant allowlist"
    grantees = json.loads(re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:\?[^}]*)?\}", r"\1", raw))

    for credential_variable, service_ref in grantees.items():
        assert service_ref not in PERMANENTLY_EXCLUDED, service_ref + " may never receive a tenant connection grant"
        assert service_ref in TENANT_RESIDENT_SERVICES, service_ref + " is not a tenant-resident service"
        assert credential_variable != "SP2_INTERNAL_SERVICE_CREDENTIAL", (
            "the shared internal credential is in the grant allowlist; the BFF holds that value, "
            "so the public ingress would be able to request a tenant connection"
        )

    bff_credential = service_environment(_COMPOSE_TEXT, "bff").get("SP2_BFF_SERVICE_CREDENTIAL", "")
    for credential_variable in grantees:
        assert credential_variable not in bff_credential, "the BFF is configured with a grantee credential"


def test_the_audit_write_scope_is_granted_to_exactly_one_emitter() -> None:
    """The BFF is the sole emitter of ingress-edge audit (IC-013 §10)."""
    raw = service_environment(_COMPOSE_TEXT, "audit").get("SP2_AUDIT_CREDENTIALS", "")
    assert raw, "the manifest declares no audit credential directory"
    directory = json.loads(re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:\?[^}]*)?\}", r"\1", raw))
    writers = [entry for entry in directory.values() if "audit:write" in entry.get("scopes", [])]
    assert len(writers) == 1, "expected exactly one audit writer, found " + str(len(writers))
    assert writers[0].get("emitter_ref") == "bff", "the audit writer is not the BFF"


def test_the_lineage_key_variables_reach_only_the_import_service() -> None:
    """One key per tenant, and only the service that writes lineage may hold any of them."""
    from snackportal2.shared.config import SERVICE_REGISTRY
    from snackportal2.shared.lineage_keys import EnvironmentLineageKeyResolver

    module = _tool()
    import_environment = service_environment(_COMPOSE_TEXT, "import-service")
    for tenant_ref in module.TENANTS:
        expected = EnvironmentLineageKeyResolver.variable_name(tenant_ref)
        assert expected in import_environment, "the Import Service is not given " + expected

    for key in SERVICE_REGISTRY:
        if key == "import_service":
            continue
        environment = service_environment(_COMPOSE_TEXT, key.replace("_", "-"))
        offenders = sorted(name for name in environment if name.startswith("SP2_LINEAGE_KEY_"))
        assert offenders == [], key + " is given a lineage chain key: " + repr(offenders)


# --- Stage 6A: the local identity provider ------------------------------------------------------
#
# The browser's login is described in four places too — the committed realm template, the compose
# service that imports it, the operator tool that renders it and pins the trust anchor, and the
# Control-database seed whose membership principals the token's `sub` must equal. The failure mode
# is the same shape as the one above and just as quiet: a realm that authenticates a user the
# Control database has never heard of produces a successful login followed by 403 on everything.


def _realm() -> Dict[str, Any]:
    """The committed realm template, parsed."""
    parsed = json.loads(_REALM_TEMPLATE.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def _client(realm: Dict[str, Any]) -> Dict[str, Any]:
    clients = [entry for entry in realm.get("clients", []) if entry.get("clientId")]
    assert len(clients) == 1, "expected exactly one client in the local realm, found " + str(len(clients))
    return dict(clients[0])


def _scope(realm: Dict[str, Any], name: str) -> Dict[str, Any]:
    matches = [entry for entry in realm.get("clientScopes", []) if entry.get("name") == name]
    assert len(matches) == 1, "expected exactly one client scope named " + name
    return dict(matches[0])


def _claims_emitted(scope: Dict[str, Any]) -> Dict[str, str]:
    """``claim name -> hardcoded value`` for the hardcoded mappers on one scope."""
    emitted: Dict[str, str] = {}
    for mapper in scope.get("protocolMappers", []):
        config = mapper.get("config", {})
        if mapper.get("protocolMapper") == "oidc-hardcoded-claim-mapper":
            emitted[str(config.get("claim.name"))] = str(config.get("claim.value"))
    return emitted


def test_the_realm_template_and_the_operator_tool_agree_on_every_identity_fact() -> None:
    """Realm name, client, audience, redirect and web origin are duplicated on purpose."""
    module = _tool()
    realm = _realm()
    client = _client(realm)

    assert realm["realm"] == module.IDP_REALM, "the realm template names a different realm than the tool"
    assert client["clientId"] == module.IDP_CLIENT_ID, "the realm registers a different client id than the tool uses"
    assert client["redirectUris"] == [module.IDP_REDIRECT_URI], "the registered redirect URI is not the one the tool sends"
    assert client["webOrigins"] == [module.FRONTEND_ORIGIN], "the registered web origin is not the frontend origin"
    assert module.IDP_REDIRECT_URI.startswith(module.FRONTEND_ORIGIN + "/"), "the redirect URI is not on the frontend origin"

    audiences = {
        mapper["config"]["included.custom.audience"]
        for mapper in _scope(realm, "sp2-principal")["protocolMappers"]
        if mapper.get("protocolMapper") == "oidc-audience-mapper"
    }
    assert audiences == {module.IDP_AUDIENCE}, "the realm stamps an audience the pinned anchor will not accept: " + repr(audiences)


def test_the_realm_emits_exactly_the_claims_the_authentication_service_reads() -> None:
    """`sub`, `role` and `active_tenant` — and nothing that carries a name, an email or PII.

    Declaring `clientScopes` REPLACES Keycloak's built-in set, so `sub` is NOT automatic here: it
    arrives via the built-in `basic` scope, which this realm does not have. A missing `sub` mapper
    produces a token the verifier rejects for a reason no log states.
    """
    from snackportal2.services.authentication.verifier import CLAIM_ACTIVE_TENANT, CLAIM_PRINCIPAL, CLAIM_ROLE
    from snackportal2.shared.types import PlatformRole

    module = _tool()
    realm = _realm()
    principal_scope = _scope(realm, "sp2-principal")
    mappers = {mapper["protocolMapper"] for mapper in principal_scope["protocolMappers"]}

    assert "oidc-sub-mapper" in mappers, "the realm emits no " + CLAIM_PRINCIPAL + " claim; the verifier requires it"
    assert "oidc-audience-mapper" in mappers, "the realm emits no audience claim"

    role_mappers = [m for m in principal_scope["protocolMappers"] if m["config"].get("claim.name") == CLAIM_ROLE]
    assert len(role_mappers) == 1, "expected exactly one " + CLAIM_ROLE + " mapper"
    assert role_mappers[0]["config"]["user.attribute"] == "sp2_role", "the role claim is not sourced from the users' own attribute"

    # The client's default scopes are exactly the SP2 one. `profile` and `email` are deliberately
    # absent: a references-only architecture must not receive a token carrying a person's name.
    assert _client(realm)["defaultClientScopes"] == ["sp2-principal"], "the client carries default scopes beyond the SP2 one"

    # Every tenant gets exactly one optional scope, emitting BOTH claims with the tenant's value:
    # `active_tenant` for the backend verifier, `tenant` for the browser adapter's claim binding.
    optional = set(_client(realm)["optionalClientScopes"])
    assert optional == {module.IDP_TENANT_SCOPE_PREFIX + ref for ref in module.TENANTS}, "tenant scopes and local tenants disagree"
    for tenant_ref in module.TENANTS:
        emitted = _claims_emitted(_scope(realm, module.IDP_TENANT_SCOPE_PREFIX + tenant_ref))
        assert emitted.get(CLAIM_ACTIVE_TENANT) == tenant_ref, "the " + tenant_ref + " scope does not emit the right active tenant"
        assert emitted.get("tenant") == tenant_ref, "the " + tenant_ref + " scope does not emit the browser's tenant claim"

    # A role the platform does not recognize authenticates nobody, so an unknown one here would
    # produce a user who can log in to Keycloak and to nothing else.
    known = {role.value for role in PlatformRole}
    for user in realm["users"]:
        declared = user["attributes"]["sp2_role"]
        assert declared and declared[0] in known, str(user["username"]) + " carries an unrecognized platform role"


def test_every_realm_user_is_a_principal_the_control_database_seed_knows() -> None:
    """The Keycloak user id IS the `sub` claim IS the seeded membership principal.

    This is why Stage 6A changed no seed: pinning the user id to the principal reference makes the
    OIDC identity and the membership row the same principal. If they drift, the browser logs in
    successfully and every tenant request is denied 403, with nothing naming the disagreement.
    """
    module = _tool()
    realm = _realm()

    by_principal = {str(user["id"]): user for user in realm["users"]}
    assert len(by_principal) == len(realm["users"]), "two realm users share an id, so two identities share a `sub`"

    seeded = {principal: tenant for principal, tenant, _role in module.SEED_MEMBERSHIPS}
    for principal, tenant in seeded.items():
        assert principal in by_principal, principal + " holds a seeded membership but no realm identity can present it"
        assert by_principal[principal]["attributes"]["sp2_role"] == ["TENANT_AGENT"], principal + " is not a tenant agent in the realm"
        # The tenant scope that would mint this principal's active tenant must exist.
        assert module.IDP_TENANT_SCOPE_PREFIX + tenant in {entry["name"] for entry in realm["clientScopes"]}

    # The tool's login-name map and the realm must describe the same four identities.
    assert {str(user["username"]) for user in realm["users"]} == set(module.IDP_IDENTITIES), "the tool and the realm list different logins"
    for username, (principal, _variable, tenant) in module.IDP_IDENTITIES.items():
        user = [entry for entry in realm["users"] if entry["username"] == username][0]
        assert str(user["id"]) == principal, username + " has a realm id that is not its principal reference"
        if tenant is None:
            # A tenantless CONTROL operator holds no membership, by design: CONTROL authority is
            # Control-resident and reaches no tenant database.
            assert user["attributes"]["sp2_role"] == ["CONTROL"], username + " is tenantless but is not CONTROL"
            assert principal not in seeded, "a tenantless CONTROL principal must not hold a membership"
        else:
            assert seeded.get(principal) == tenant, username + " is bound to a different tenant than its seeded membership"


def test_the_realm_template_carries_no_usable_credential() -> None:
    """Committed, therefore placeholders only — the same rule as the env template's empty lines."""
    module = _tool()
    text = _REALM_TEMPLATE.read_text(encoding="utf-8")
    realm = _realm()

    found = set(re.findall(r"__SP2_[A-Z0-9_]+__", text))
    assert found == set(module.IDP_PASSWORD_PLACEHOLDERS), "the template's placeholders and the tool's substitution map disagree"
    assert found, "no placeholders found; this check would be vacuous"

    declared = template_keys(_TEMPLATE_TEXT)
    for placeholder, variable in module.IDP_PASSWORD_PLACEHOLDERS.items():
        assert variable in module.GENERATED_VARIABLES, variable + " substitutes a realm password but is not generated"
        assert declared.get(variable) == "", "the committed env template carries a value for " + variable
        del placeholder

    # Every credential in the committed realm is a placeholder, never a value.
    for user in realm["users"]:
        for credential in user.get("credentials", []):
            assert credential["value"] in found, str(user["username"]) + " carries a credential value that is not a placeholder"

    # A public browser client has no secret, and none may appear here even as a field. Checked
    # STRUCTURALLY — over the JSON keys — rather than by searching the text for the word: the
    # client's own description says "there is no client secret", and a substring rule would both
    # flag that and miss a secret stored under a differently-named key.
    client = _client(realm)
    assert client["publicClient"] is True, "the browser client is not public"

    credential_keys = {"secret", "clientsecret", "privatekey", "password", "value"}
    offenders: List[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                here = path + "." + str(key)
                if str(key).lower().replace("_", "").replace("-", "") in credential_keys:
                    # The only permitted credential-shaped values are the placeholders.
                    if not (isinstance(value, str) and value in found):
                        offenders.append(here + "=" + repr(value)[:60])
                walk(value, here)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, path + "[" + str(index) + "]")

    walk(realm, "realm")
    assert offenders == [], "the committed realm carries credential-shaped values: " + repr(offenders)
    del text


def test_the_browser_client_permits_only_authorization_code_with_pkce() -> None:
    """PKCE is REQUIRED by the registration, not merely offered.

    Without `pkce.code.challenge.method`, a public client still accepts a plain code exchange, and
    an intercepted authorization code becomes sufficient on its own.
    """
    client = _client(_realm())
    assert client["attributes"]["pkce.code.challenge.method"] == "S256", "PKCE S256 is not required by the client registration"
    assert client["standardFlowEnabled"] is True, "the authorization-code flow is disabled"
    assert client["implicitFlowEnabled"] is False, "the implicit flow is enabled"
    assert client["directAccessGrantsEnabled"] is False, "the password grant is enabled on a browser client"
    assert client["serviceAccountsEnabled"] is False, "service accounts are enabled on a browser client"


def test_the_manifest_runs_the_identity_provider_the_tool_talks_to() -> None:
    """The compose service, its published port, and the realm its health check proves."""
    module = _tool()
    environment = service_environment(_COMPOSE_TEXT, module.IDP_SERVICE)
    assert environment, "the manifest declares no " + module.IDP_SERVICE + " service"

    assert "${SP2_LOCAL_IDP_ISSUER_ORIGIN:-" in environment.get("KC_HOSTNAME", ""), (
        "the identity provider's issuer origin is not pinned; `iss` would vary with the request host"
    )
    assert "SP2_LOCAL_IDP_ADMIN_PASSWORD" in environment.get("KC_BOOTSTRAP_ADMIN_PASSWORD", ""), (
        "the admin password is not read from the untracked env file"
    )

    # The health check must prove the REALM imported, not merely that a server answers: a Keycloak
    # that started and imported nothing passes a liveness probe and fails every login.
    assert "/realms/" + module.IDP_REALM in _COMPOSE_TEXT, "the manifest's health check does not name the realm"

    # The generated realm file is what the container mounts, and it is never committed.
    assert "./keycloak/import:/opt/keycloak/data/import:ro" in _COMPOSE_TEXT, "the generated realm directory is not mounted read-only"
    ignore_rules = (_DOCKER / ".gitignore").read_text(encoding="utf-8")
    assert "keycloak/import/" in ignore_rules, "the generated realm file is not gitignored"
    assert str(_REALM_TEMPLATE.name) not in ignore_rules, "the committed realm template is ignored and would never be committed"

    # The compose project name is used to remove the identity provider's named volume by name.
    assert "\nname: " + module.COMPOSE_PROJECT + "\n" in _COMPOSE_TEXT, "the tool's compose project name has drifted from the manifest"

    # Origin and published port are two halves of one fact.
    declared = template_keys(_TEMPLATE_TEXT)
    assert declared["SP2_LOCAL_IDP_ISSUER_ORIGIN"].endswith(":" + declared["SP2_LOCAL_IDP_PORT"]), (
        "the issuer origin and the published port disagree: "
        + declared["SP2_LOCAL_IDP_ISSUER_ORIGIN"]
        + " vs "
        + declared["SP2_LOCAL_IDP_PORT"]
    )


def test_only_the_identity_provider_publishes_outside_the_service_and_database_ports() -> None:
    """It publishes because a BROWSER must reach it — and it is not an application service."""
    from snackportal2.shared.config import SERVICE_REGISTRY

    module = _tool()
    declared = template_keys(_TEMPLATE_TEXT)
    idp_port = int(declared["SP2_LOCAL_IDP_PORT"])

    service_ports = {descriptor.default_port for descriptor in SERVICE_REGISTRY.values()}
    assert idp_port not in service_ports, "the identity provider is published on a service port"
    database_ports = {int(default) for _variable, default in module.PORT_VARIABLES.values()}
    assert idp_port not in database_ports, "the identity provider is published on a database port"

    # The exposure census classifies it as infrastructure by NAME, exactly as it does `postgres`.
    assert module.INFRASTRUCTURE_SERVICE.search(module.IDP_SERVICE), "the identity provider would be counted as an application ingress"


# --- the runbook -------------------------------------------------------------------------------


def test_the_runbook_exists_and_names_the_supported_commands() -> None:
    """A procedure that lives only in someone's shell history is not a procedure."""
    assert _RUNBOOK.exists(), "docs/Local_Development_Runbook.md is missing"
    text = _RUNBOOK.read_text(encoding="utf-8")
    for command in ("init-env", "bootstrap", "verify", "smoke", "down"):
        assert command in text, "the runbook does not document the " + command + " step"
    assert str(_COMPOSE.relative_to(_REPO_ROOT)).replace("\\", "/") in text, "the runbook does not name the compose file"


# --- non-vacuity ---------------------------------------------------------------------------------


def test_the_environment_scanner_reads_a_planted_document() -> None:
    """Every check above is built on this scanner; one that found nothing would make them all pass."""
    planted = (
        "name: probe\n"
        "services:\n"
        "  alpha:\n"
        "    image: x\n"
        "    environment:\n"
        '      A_ONE: "1"\n'
        "      A_TWO: ${FROM_ENV:?required}\n"
        "      A_FOLDED: >-\n"
        '        {"k":\n'
        '         "v"}\n'
        "    ports:\n"
        '      - "1:1"\n'
        "  beta:\n"
        "    image: x\n"
        "    environment:\n"
        '      B_ONE: "2"\n'
    )
    alpha = service_environment(planted, "alpha")
    assert alpha["A_ONE"] == '"1"', "the scanner misread a plain value: " + repr(alpha)
    assert alpha["A_TWO"] == "${FROM_ENV:?required}", "the scanner misread an interpolation"
    assert alpha["A_FOLDED"].replace(" ", "") == '{"k":"v"}', "the scanner cannot read a folded block scalar"
    assert "B_ONE" not in alpha, "the scanner leaked another service's environment"
    assert service_environment(planted, "beta") == {"B_ONE": '"2"'}, "the scanner misread the second service"
    assert service_environment(planted, "absent") == {}, "the scanner invented an environment for a missing service"

    assert required_variables(planted) == {"FROM_ENV"}
    assert interpolated_variables(planted) == {"FROM_ENV"}
    assert template_keys("# c\nA=1\n\nB=\n") == {"A": "1", "B": ""}


def _self_test() -> None:
    checks: List[object] = [
        test_the_manifest_and_the_service_registry_agree_on_every_service_and_port,
        test_the_operator_tool_and_the_service_registry_agree,
        test_the_tool_applies_exactly_the_chains_the_stage_4_harness_proved,
        test_the_template_declares_every_variable_the_manifest_requires,
        test_the_template_declares_every_variable_the_manifest_interpolates,
        test_the_template_carries_no_usable_secret_value,
        test_the_generated_env_file_is_untracked,
        test_the_seeded_memberships_and_the_local_tokens_name_the_same_principals,
        test_no_local_principal_is_a_member_of_two_tenants,
        test_the_tenant_dsn_variable_names_match_the_seeded_associations,
        test_only_the_database_router_holds_a_tenant_dsn,
        test_the_grant_allowlist_excludes_the_bff_and_access_control_and_names_only_tenant_services,
        test_the_audit_write_scope_is_granted_to_exactly_one_emitter,
        test_the_lineage_key_variables_reach_only_the_import_service,
        test_the_realm_template_and_the_operator_tool_agree_on_every_identity_fact,
        test_the_realm_emits_exactly_the_claims_the_authentication_service_reads,
        test_every_realm_user_is_a_principal_the_control_database_seed_knows,
        test_the_realm_template_carries_no_usable_credential,
        test_the_browser_client_permits_only_authorization_code_with_pkce,
        test_the_manifest_runs_the_identity_provider_the_tool_talks_to,
        test_only_the_identity_provider_publishes_outside_the_service_and_database_ports,
        test_the_runbook_exists_and_names_the_supported_commands,
        test_the_environment_scanner_reads_a_planted_document,
    ]
    for check in checks:
        check()  # type: ignore[operator]
    print("stage 6 local launch consistency: PASS (" + str(len(checks)) + " checks)")


if __name__ == "__main__":
    sys.path.insert(0, str(_BACKEND))
    _self_test()


__all__ = ["interpolated_variables", "required_variables", "service_environment", "template_keys"]
