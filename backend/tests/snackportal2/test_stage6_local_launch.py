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
