"""Provider-neutral environment-profile contract (SP2-NEXT-A-PORTABILITY O-3/O-4/O-5, §8.1–8.3).

A profile selects *where things live* for one environment — endpoint references,
logical database bindings, provider selectors, TLS/discovery posture — and never
*what the system does*: business rules, tenant authority, ownership, sharing,
import/lineage semantics, routing invariants, audit representation, and API
contracts are out of a profile's reach by construction (master plan §10.3).

Reference grammar (references only, D-14):
  * ``ref:<store-ref>@<version>``  — secret-resolvable reference; maps 1:1 onto
    ``shared.secrets.SecretRef(store_ref, version)`` and the committed
    ``infrastructure/env`` template convention. Database endpoints resolve this
    way, so no host, port, DSN, or credential ever appears in a profile.
  * ``service://<service-id>``     — logical service endpoint reference.
  * ``config://<key>``             — non-secret operator-configuration reference.

Pure stdlib; no I/O beyond an explicit ``load_profile(path)``; no environment
reads; no runtime behavior. Loading or validating a profile activates nothing —
the B-5 production posture remains NOT READY / DO-NOT-ACTIVATE.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Set, Tuple

from .identity import (
    CLOUD_TEMPLATE_PROFILE_ID,
    LOCAL_PROFILE_ID,
    OFFICIAL_LOCAL_ENVIRONMENT_ID,
    REQUIRED_LOGICAL_DATABASE_IDS,
    RUNTIME_CAPABLE_ENVIRONMENT_TYPES,
    SUPPORTED_ENVIRONMENT_TYPES,
    EnvironmentType,
    LogicalIdentityError,
    validate_environment_id,
    validate_logical_database_id,
    validate_profile_id,
)

PROFILE_SCHEMA_ID = "sp2-environment-profile/v1"

# --- Reference grammars (references only; D-14) --------------------------------

SECRET_REFERENCE_RE = re.compile(r"^ref:[A-Za-z0-9][A-Za-z0-9/_-]*@[A-Za-z0-9._-]+$")
SERVICE_REFERENCE_RE = re.compile(r"^service://[a-z][a-z0-9-]*$")
CONFIG_REFERENCE_RE = re.compile(r"^config://[a-z][a-z0-9-]*(/[a-z0-9-]+)*$")

# Provider/posture selectors are opaque vendor-neutral tokens; the concrete
# adapter is bound at a composition root (shared.adapters), never here.
SELECTOR_RE = re.compile(r"^[a-z][a-z0-9-]*$")
UNSELECTED = "unselected"  # the only admissible value for a provider selector that deliberately chooses nothing (cloud template, O-5)

# Provider-choosing selector fields: a runtime-capable profile must choose real
# providers; the non-operational cloud template must choose none (O-5 / AC-2).
PROVIDER_SELECTOR_FIELDS: Tuple[str, ...] = (
    "secret_provider",
    "monitoring_exporter",
    "service_discovery_mode",
    "runtime_health_integration",
)
POSTURE_SELECTOR_FIELDS: Tuple[str, ...] = ("tls_mode",)

# --- Business-rule firewall (§8.1 "no business-rule overrides") -----------------
# A profile carrying ANY of these keys — at any nesting depth — is rejected
# outright. The vocabulary mirrors the master plan §10.3 prohibition list.

FORBIDDEN_PROFILE_KEYS = frozenset(
    {
        "business_rules",
        "routing",
        "routing_rules",
        "routing_overrides",
        "ownership",
        "ownership_rules",
        "sharing",
        "sharing_rules",
        "tenant_authority",
        "import_semantics",
        "import_rules",
        "lineage_semantics",
        "lineage_rules",
        "audit_representation",
        "authentication_rules",
        "authorization_rules",
        "api_contracts",
        "contract_overrides",
        "blocker_overrides",
        "invariant_overrides",
    }
)

_REQUIRED_TOP_LEVEL_KEYS: Tuple[str, ...] = (
    "schema",
    "profile_id",
    "environment_id",
    "environment_type",
    "logical_databases",
    "service_endpoints",
    "secret_provider",
    "artifact_destination_ref",
    "backup_destination_ref",
    "monitoring_exporter",
    "alert_destination_ref",
    "tls_mode",
    "service_discovery_mode",
    "runtime_health_integration",
)

# --- Raw-secret / physical-endpoint rejection (§8.1, AC-6) ----------------------
# Patterns are checked against every string value in a profile. Error messages
# name the field and the violation KIND only — the offending value is never
# echoed (no leakage through validation errors).

_RAW_SECRET_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("dsn", re.compile(r"postgres(ql)?://", re.IGNORECASE)),
    ("url-credentials", re.compile(r"://[^/@\s]+:[^/@\s]+@")),
    ("password-assignment", re.compile(r"(?i)\b(password|passwd|pwd)\s*[=:]")),
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("token", re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}")),
    ("bearer-token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{16,}")),
)
_PHYSICAL_ENDPOINT_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("ipv4-literal", re.compile(r"\b\d{1,3}(\.\d{1,3}){3}\b")),
    ("loopback-host", re.compile(r"(?i)\blocalhost\b|::1")),
    ("host-port", re.compile(r":\d{2,5}(?=/|$)")),
    # A drive letter followed by \ (or by a single /, so URI '://' schemes never match).
    ("windows-path", re.compile(r"[A-Za-z]:(?:\\{1,2}|/(?!/))")),
)


class ProfileValidationError(ValueError):
    """The profile document violates the provider-neutral profile contract (fails closed)."""


class ProfileNotRuntimeCapableError(RuntimeError):
    """A non-operational profile (e.g. the cloud template) was asked for runtime capability."""


def assert_reference_safe(field: str, value: str) -> None:
    """Reject raw secrets, DSNs, and physical endpoints in any profile/manifest value.

    Deliberately never includes the offending value in the error (secret-safe
    diagnostics; master plan §15.2).
    """
    for kind, pattern in _RAW_SECRET_PATTERNS:
        if pattern.search(value):
            raise ProfileValidationError(f"{field}: value matches forbidden raw-secret pattern '{kind}' — references only (D-14)")
    for kind, pattern in _PHYSICAL_ENDPOINT_PATTERNS:
        if pattern.search(value):
            raise ProfileValidationError(
                f"{field}: value matches forbidden physical-endpoint pattern '{kind}' — endpoints are configuration, never identity (D-14)"
            )


# --- Shapes --------------------------------------------------------------------


@dataclass(frozen=True)
class DatabaseBinding:
    """One logical database bound to a secret-resolvable endpoint reference (never an endpoint value)."""

    logical_id: str
    endpoint_ref: str


@dataclass(frozen=True)
class ServiceEndpoint:
    """One backend service bound to a logical service reference."""

    service_id: str
    endpoint_ref: str


@dataclass(frozen=True)
class EnvironmentProfile:
    """Validated provider-neutral environment profile (O-3). Construct via parse_profile/load_profile."""

    profile_id: str
    environment_id: str
    environment_type: str
    logical_databases: Tuple[DatabaseBinding, ...]
    service_endpoints: Tuple[ServiceEndpoint, ...]
    secret_provider: str
    artifact_destination_ref: str
    backup_destination_ref: str
    monitoring_exporter: str
    alert_destination_ref: str
    tls_mode: str
    service_discovery_mode: str
    runtime_health_integration: str

    def logical_database_ids(self) -> Tuple[str, ...]:
        return tuple(binding.logical_id for binding in self.logical_databases)

    @property
    def is_runtime_capable(self) -> bool:
        """True only for environment types that may ever reach a running composition (never the cloud template)."""
        return self.environment_type in RUNTIME_CAPABLE_ENVIRONMENT_TYPES

    def assert_runtime_capable(self) -> None:
        """Fail closed when a non-operational profile is offered to any runtime path (AC-2).

        Passing this check activates nothing: the B-5 production activation gate
        is a separate, unchanged mechanism (NOT READY / DO-NOT-ACTIVATE).
        """
        if not self.is_runtime_capable:
            raise ProfileNotRuntimeCapableError(
                f"profile '{self.profile_id}' (environment_type '{self.environment_type}') is non-operational and cannot activate runtime"
            )


# --- Parsing / validation -------------------------------------------------------


def _forbidden_keys_anywhere(node: object) -> List[str]:
    """Collect FORBIDDEN_PROFILE_KEYS present at any nesting depth, sorted (deterministic)."""
    found: Set[str] = set()

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, sub in value.items():
                if isinstance(key, str) and key in FORBIDDEN_PROFILE_KEYS:
                    found.add(key)
                walk(sub)
        elif isinstance(value, list):
            for sub in value:
                walk(sub)

    walk(node)
    return sorted(found)


def _require_str(data: Mapping[str, object], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value:
        raise ProfileValidationError(f"{key}: must be a non-empty string")
    return value


def _parse_entry(field: str, index: int, raw: object, id_key: str) -> Tuple[str, str]:
    if not isinstance(raw, dict):
        raise ProfileValidationError(f"{field}[{index}]: must be an object")
    keys = set(raw.keys())
    expected = {id_key, "endpoint_ref"}
    if keys != expected:
        unknown = sorted(keys - expected)
        missing = sorted(expected - keys)
        raise ProfileValidationError(f"{field}[{index}]: unknown keys {unknown}, missing keys {missing} (deterministic rejection)")
    entry_id = raw[id_key]
    endpoint_ref = raw["endpoint_ref"]
    if not isinstance(entry_id, str) or not isinstance(endpoint_ref, str):
        raise ProfileValidationError(f"{field}[{index}]: {id_key} and endpoint_ref must be strings")
    return entry_id, endpoint_ref


def parse_profile(data: Mapping[str, object]) -> EnvironmentProfile:
    """Validate a profile document and return the frozen profile (fails closed on any violation)."""
    if not isinstance(data, dict):
        raise ProfileValidationError("profile document must be a JSON object")

    forbidden = _forbidden_keys_anywhere(data)
    if forbidden:
        raise ProfileValidationError(f"profile carries business-rule/override keys (prohibited at any depth): {forbidden}")

    keys = set(data.keys())
    known = set(_REQUIRED_TOP_LEVEL_KEYS)
    unknown = sorted(keys - known)
    if unknown:
        raise ProfileValidationError(f"unknown profile fields (deterministic rejection, sorted): {unknown}")
    missing = sorted(known - keys)
    if missing:
        raise ProfileValidationError(f"missing required profile fields (sorted): {missing}")

    schema = _require_str(data, "schema")
    if schema != PROFILE_SCHEMA_ID:
        raise ProfileValidationError(f"schema: expected '{PROFILE_SCHEMA_ID}'")

    profile_id = _require_str(data, "profile_id")
    environment_id = _require_str(data, "environment_id")
    environment_type = _require_str(data, "environment_type")
    try:
        validate_profile_id(profile_id)
        validate_environment_id(environment_id)
    except LogicalIdentityError as exc:
        raise ProfileValidationError(str(exc)) from exc
    if environment_type not in SUPPORTED_ENVIRONMENT_TYPES:
        raise ProfileValidationError(f"environment_type: unsupported value (supported, sorted: {sorted(SUPPORTED_ENVIRONMENT_TYPES)})")

    raw_databases = data["logical_databases"]
    if not isinstance(raw_databases, list) or not raw_databases:
        raise ProfileValidationError("logical_databases: must be a non-empty array")
    bindings: List[DatabaseBinding] = []
    seen_db: Set[str] = set()
    for index, raw in enumerate(raw_databases):
        logical_id, endpoint_ref = _parse_entry("logical_databases", index, raw, "logical_id")
        try:
            validate_logical_database_id(logical_id)
        except LogicalIdentityError as exc:
            raise ProfileValidationError(str(exc)) from exc
        if logical_id in seen_db:
            raise ProfileValidationError(f"logical_databases: duplicate logical_id '{logical_id}'")
        seen_db.add(logical_id)
        if not SECRET_REFERENCE_RE.fullmatch(endpoint_ref):
            raise ProfileValidationError(
                f"logical_databases[{index}].endpoint_ref: must be a 'ref:<store-ref>@<version>' secret reference (D-14)"
            )
        bindings.append(DatabaseBinding(logical_id=logical_id, endpoint_ref=endpoint_ref))
    missing_db = sorted(set(REQUIRED_LOGICAL_DATABASE_IDS) - seen_db)
    if missing_db:
        raise ProfileValidationError(f"logical_databases: missing required logical database ids (sorted): {missing_db}")
    extras = seen_db - set(REQUIRED_LOGICAL_DATABASE_IDS)
    bad_extras = sorted(x for x in extras if not x.startswith("tenant-"))
    if bad_extras:
        raise ProfileValidationError(f"logical_databases: additional ids must be tenant-scoped ('tenant-…'), got (sorted): {bad_extras}")

    raw_services = data["service_endpoints"]
    if not isinstance(raw_services, list) or not raw_services:
        raise ProfileValidationError("service_endpoints: must be a non-empty array")
    services: List[ServiceEndpoint] = []
    seen_svc: Set[str] = set()
    for index, raw in enumerate(raw_services):
        service_id, endpoint_ref = _parse_entry("service_endpoints", index, raw, "service_id")
        if not SELECTOR_RE.fullmatch(service_id):
            raise ProfileValidationError(f"service_endpoints[{index}].service_id: must be a kebab-case token")
        if service_id in seen_svc:
            raise ProfileValidationError(f"service_endpoints: duplicate service_id '{service_id}'")
        seen_svc.add(service_id)
        if not SERVICE_REFERENCE_RE.fullmatch(endpoint_ref):
            raise ProfileValidationError(f"service_endpoints[{index}].endpoint_ref: must be a 'service://<service-id>' reference")
        services.append(ServiceEndpoint(service_id=service_id, endpoint_ref=endpoint_ref))

    selectors: Dict[str, str] = {}
    for field in PROVIDER_SELECTOR_FIELDS + POSTURE_SELECTOR_FIELDS:
        value = _require_str(data, field)
        if not SELECTOR_RE.fullmatch(value):
            raise ProfileValidationError(f"{field}: must be a kebab-case vendor-neutral selector token")
        selectors[field] = value

    artifact_destination_ref = _require_str(data, "artifact_destination_ref")
    backup_destination_ref = _require_str(data, "backup_destination_ref")
    alert_destination_ref = _require_str(data, "alert_destination_ref")
    if not CONFIG_REFERENCE_RE.fullmatch(artifact_destination_ref):
        raise ProfileValidationError("artifact_destination_ref: must be a 'config://…' reference")
    if not CONFIG_REFERENCE_RE.fullmatch(backup_destination_ref):
        raise ProfileValidationError("backup_destination_ref: must be a 'config://…' reference")
    if not SECRET_REFERENCE_RE.fullmatch(alert_destination_ref):
        raise ProfileValidationError("alert_destination_ref: must be a 'ref:<store-ref>@<version>' secret reference (D-14)")

    for key, value in data.items():
        if isinstance(value, str):
            assert_reference_safe(key, value)
    for index, binding in enumerate(bindings):
        assert_reference_safe(f"logical_databases[{index}].endpoint_ref", binding.endpoint_ref)
        assert_reference_safe(f"logical_databases[{index}].logical_id", binding.logical_id)
    for index, service in enumerate(services):
        assert_reference_safe(f"service_endpoints[{index}].endpoint_ref", service.endpoint_ref)

    profile = EnvironmentProfile(
        profile_id=profile_id,
        environment_id=environment_id,
        environment_type=environment_type,
        logical_databases=tuple(bindings),
        service_endpoints=tuple(services),
        secret_provider=selectors["secret_provider"],
        artifact_destination_ref=artifact_destination_ref,
        backup_destination_ref=backup_destination_ref,
        monitoring_exporter=selectors["monitoring_exporter"],
        alert_destination_ref=alert_destination_ref,
        tls_mode=selectors["tls_mode"],
        service_discovery_mode=selectors["service_discovery_mode"],
        runtime_health_integration=selectors["runtime_health_integration"],
    )
    _validate_cross_rules(profile)
    return profile


def _validate_cross_rules(profile: EnvironmentProfile) -> None:
    """Profile-level coherence rules binding identity, type, and provider selection."""
    if profile.is_runtime_capable:
        unselected = sorted(field for field in PROVIDER_SELECTOR_FIELDS if getattr(profile, field) == UNSELECTED)
        if unselected:
            raise ProfileValidationError(f"runtime-capable profile must select real providers; '{UNSELECTED}' in (sorted): {unselected}")
    else:
        selected = sorted(field for field in PROVIDER_SELECTOR_FIELDS if getattr(profile, field) != UNSELECTED)
        if selected:
            raise ProfileValidationError(
                f"non-operational profile must not choose providers (O-5); concrete selection in (sorted): {selected}"
            )
    if profile.profile_id == LOCAL_PROFILE_ID:
        if profile.environment_id != OFFICIAL_LOCAL_ENVIRONMENT_ID:
            raise ProfileValidationError(
                f"'{LOCAL_PROFILE_ID}' must carry the official local environment id '{OFFICIAL_LOCAL_ENVIRONMENT_ID}'"
            )
        if profile.environment_type != EnvironmentType.CONTROLLED_LOCAL_MVP.value:
            raise ProfileValidationError(f"'{LOCAL_PROFILE_ID}' must have environment_type '{EnvironmentType.CONTROLLED_LOCAL_MVP.value}'")
    if profile.profile_id == CLOUD_TEMPLATE_PROFILE_ID and profile.environment_type != EnvironmentType.CLOUD_TEMPLATE.value:
        raise ProfileValidationError(f"'{CLOUD_TEMPLATE_PROFILE_ID}' must have environment_type '{EnvironmentType.CLOUD_TEMPLATE.value}'")
    if profile.environment_type == EnvironmentType.CLOUD_TEMPLATE.value and profile.environment_id == OFFICIAL_LOCAL_ENVIRONMENT_ID:
        raise ProfileValidationError("a cloud template must not claim the official local environment id")


def load_profile(path: Path) -> EnvironmentProfile:
    """Load and validate one profile document from an explicit path (no implicit repo-layout assumption)."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileValidationError(f"{path.name}: not valid JSON ({exc.msg} at line {exc.lineno})") from exc
    if not isinstance(document, dict):
        raise ProfileValidationError(f"{path.name}: profile document must be a JSON object")
    return parse_profile(document)


def load_profiles(paths: Sequence[Path]) -> Tuple[EnvironmentProfile, ...]:
    """Load several profiles, enforcing unique profile_id and unique environment_id across the set (§8.1)."""
    profiles: List[EnvironmentProfile] = []
    seen_profile_ids: Set[str] = set()
    seen_environment_ids: Set[str] = set()
    for path in paths:
        profile = load_profile(path)
        if profile.profile_id in seen_profile_ids:
            raise ProfileValidationError(f"duplicate profile_id across profile set: '{profile.profile_id}'")
        if profile.environment_id in seen_environment_ids:
            raise ProfileValidationError(f"duplicate environment_id across profile set: '{profile.environment_id}'")
        seen_profile_ids.add(profile.profile_id)
        seen_environment_ids.add(profile.environment_id)
        profiles.append(profile)
    return tuple(profiles)
