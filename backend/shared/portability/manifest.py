"""References-only deployment/environment manifest (SP2-NEXT-A-PORTABILITY O-6, §8.4).

A deployment manifest records *what was deployed where* for one environment as
references and digests only: no secrets, no raw DSNs, no private keys, no
business records, no PII (master plan §13.3/§24.1). It is deliberately testable
without Docker or database access — the manifest is pure data.

Determinism: ``canonical_json`` produces byte-identical output for equal
manifests regardless of construction order (sorted keys, canonicalized
collection ordering, compact separators, ASCII-only), and ``manifest_digest``
is the SHA-256 of exactly that canonical serialization.

Pure stdlib; no I/O; no environment reads; no runtime behavior. Producing a
manifest activates nothing (B-5 posture NOT READY / DO-NOT-ACTIVATE unchanged).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Dict, List, Mapping, Set, Tuple, Union

from .identity import (
    REQUIRED_LOGICAL_DATABASE_IDS,
    LogicalIdentityError,
    validate_environment_id,
    validate_logical_database_id,
    validate_profile_id,
)
from .profile import (
    CONFIG_REFERENCE_RE,
    SECRET_REFERENCE_RE,
    SELECTOR_RE,
    EnvironmentProfile,
    ProfileValidationError,
    assert_reference_safe,
)

MANIFEST_SCHEMA_ID = "sp2-deployment-manifest/v1"

_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
# Image references must be digest-pinned (master plan §13.1): name[:tag]@sha256:<64-hex>.
_IMAGE_REF_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]*(:[A-Za-z0-9._-]+)?@sha256:[0-9a-f]{64}$")
_STARTED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$")

_STRING_FIELDS: Tuple[str, ...] = (
    "environment_id",
    "profile_id",
    "host_or_platform_ref",
    "operator_ref",
    "repository_commit",
    "configuration_digest",
    "migration_digest",
    "secret_provider_type",
    "backup_target_type",
    "monitoring_exporter_type",
    "started_at",
)
_LIST_FIELDS: Tuple[str, ...] = ("service_image_refs", "database_image_refs", "logical_database_ids")
_ALL_FIELDS: Tuple[str, ...] = _STRING_FIELDS + _LIST_FIELDS


class ManifestValidationError(ValueError):
    """The manifest violates the references-only deployment-manifest contract (fails closed)."""


@dataclass(frozen=True)
class DeploymentManifest:
    """References-only record of one deployment of one environment (O-6 field set)."""

    environment_id: str
    profile_id: str
    host_or_platform_ref: str
    operator_ref: str
    repository_commit: str
    configuration_digest: str
    service_image_refs: Tuple[str, ...]
    database_image_refs: Tuple[str, ...]
    migration_digest: str
    logical_database_ids: Tuple[str, ...]
    secret_provider_type: str
    backup_target_type: str
    monitoring_exporter_type: str
    started_at: str


def _reference_safe(field: str, value: str) -> None:
    try:
        assert_reference_safe(field, value)
    except ProfileValidationError as exc:
        raise ManifestValidationError(str(exc)) from exc


def validate_manifest(manifest: DeploymentManifest) -> None:
    """Fail closed unless every field is a well-formed reference/digest and secret-free (§8.4)."""
    try:
        validate_environment_id(manifest.environment_id)
        validate_profile_id(manifest.profile_id)
    except LogicalIdentityError as exc:
        raise ManifestValidationError(str(exc)) from exc

    for field in ("host_or_platform_ref", "operator_ref"):
        value = getattr(manifest, field)
        if not isinstance(value, str) or not (CONFIG_REFERENCE_RE.fullmatch(value) or SECRET_REFERENCE_RE.fullmatch(value)):
            raise ManifestValidationError(f"{field}: must be a 'config://…' or 'ref:<store-ref>@<version>' reference — never a raw value")

    if not _COMMIT_RE.fullmatch(manifest.repository_commit):
        raise ManifestValidationError("repository_commit: must be a 40-hex commit SHA")
    for field in ("configuration_digest", "migration_digest"):
        if not _SHA256_DIGEST_RE.fullmatch(getattr(manifest, field)):
            raise ManifestValidationError(f"{field}: must be 'sha256:<64-hex>'")

    for field in ("service_image_refs", "database_image_refs"):
        refs = getattr(manifest, field)
        if not isinstance(refs, tuple) or not refs:
            raise ManifestValidationError(f"{field}: must be a non-empty tuple of digest-pinned image references")
        for index, ref in enumerate(refs):
            if not isinstance(ref, str) or not _IMAGE_REF_RE.fullmatch(ref):
                raise ManifestValidationError(f"{field}[{index}]: must be a digest-pinned image reference 'name[:tag]@sha256:<64-hex>'")

    if not isinstance(manifest.logical_database_ids, tuple) or not manifest.logical_database_ids:
        raise ManifestValidationError("logical_database_ids: must be a non-empty tuple")
    seen: Set[str] = set()
    for logical_id in manifest.logical_database_ids:
        try:
            validate_logical_database_id(logical_id)
        except LogicalIdentityError as exc:
            raise ManifestValidationError(str(exc)) from exc
        if logical_id in seen:
            raise ManifestValidationError(f"logical_database_ids: duplicate '{logical_id}'")
        seen.add(logical_id)
    missing = sorted(set(REQUIRED_LOGICAL_DATABASE_IDS) - seen)
    if missing:
        raise ManifestValidationError(f"logical_database_ids: missing required ids (sorted): {missing}")

    for field in ("secret_provider_type", "backup_target_type", "monitoring_exporter_type"):
        if not SELECTOR_RE.fullmatch(getattr(manifest, field)):
            raise ManifestValidationError(f"{field}: must be a kebab-case vendor-neutral selector token")

    if not _STARTED_AT_RE.fullmatch(manifest.started_at):
        raise ManifestValidationError("started_at: must be an ISO-8601 UTC instant 'YYYY-MM-DDThh:mm:ss[.ffffff]Z'")

    for field in _STRING_FIELDS:
        _reference_safe(field, getattr(manifest, field))
    for field in _LIST_FIELDS:
        for index, item in enumerate(getattr(manifest, field)):
            _reference_safe(f"{field}[{index}]", item)


def canonical_payload(manifest: DeploymentManifest) -> Dict[str, Union[str, List[str]]]:
    """Canonical dict form: schema-stamped, collection ordering canonicalized (sorted)."""
    validate_manifest(manifest)
    payload: Dict[str, Union[str, List[str]]] = {"schema": MANIFEST_SCHEMA_ID}
    for field in _STRING_FIELDS:
        payload[field] = getattr(manifest, field)
    for field in _LIST_FIELDS:
        payload[field] = sorted(getattr(manifest, field))
    return payload


def canonical_json(manifest: DeploymentManifest) -> str:
    """Deterministic serialization: sorted keys, compact separators, ASCII-only (§8.4)."""
    return json.dumps(canonical_payload(manifest), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def manifest_digest(manifest: DeploymentManifest) -> str:
    """Reproducible manifest digest: SHA-256 over exactly the canonical JSON serialization."""
    return "sha256:" + hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()


def parse_manifest(data: Mapping[str, object]) -> DeploymentManifest:
    """Parse + validate a manifest document (round-trips canonical_payload); unknown fields rejected deterministically."""
    if not isinstance(data, dict):
        raise ManifestValidationError("manifest document must be a JSON object")
    keys = set(data.keys())
    known = set(_ALL_FIELDS) | {"schema"}
    unknown = sorted(keys - known)
    if unknown:
        raise ManifestValidationError(f"unknown manifest fields (deterministic rejection, sorted): {unknown}")
    missing = sorted(known - keys)
    if missing:
        raise ManifestValidationError(f"missing required manifest fields (sorted): {missing}")
    schema = data["schema"]
    if schema != MANIFEST_SCHEMA_ID:
        raise ManifestValidationError(f"schema: expected '{MANIFEST_SCHEMA_ID}'")

    values: Dict[str, str] = {}
    for field in _STRING_FIELDS:
        value = data[field]
        if not isinstance(value, str) or not value:
            raise ManifestValidationError(f"{field}: must be a non-empty string")
        values[field] = value
    lists: Dict[str, Tuple[str, ...]] = {}
    for field in _LIST_FIELDS:
        raw = data[field]
        if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
            raise ManifestValidationError(f"{field}: must be an array of strings")
        lists[field] = tuple(raw)

    manifest = DeploymentManifest(
        environment_id=values["environment_id"],
        profile_id=values["profile_id"],
        host_or_platform_ref=values["host_or_platform_ref"],
        operator_ref=values["operator_ref"],
        repository_commit=values["repository_commit"],
        configuration_digest=values["configuration_digest"],
        service_image_refs=lists["service_image_refs"],
        database_image_refs=lists["database_image_refs"],
        migration_digest=values["migration_digest"],
        logical_database_ids=lists["logical_database_ids"],
        secret_provider_type=values["secret_provider_type"],
        backup_target_type=values["backup_target_type"],
        monitoring_exporter_type=values["monitoring_exporter_type"],
        started_at=values["started_at"],
    )
    validate_manifest(manifest)
    return manifest


def assert_consistent_with_profile(manifest: DeploymentManifest, profile: EnvironmentProfile) -> None:
    """Cross-check: the manifest must describe the same logical identity the profile declares (AC-3/AC-5)."""
    validate_manifest(manifest)
    if manifest.environment_id != profile.environment_id:
        raise ManifestValidationError(
            f"environment_id mismatch: manifest '{manifest.environment_id}' vs profile '{profile.environment_id}'"
        )
    if manifest.profile_id != profile.profile_id:
        raise ManifestValidationError(f"profile_id mismatch: manifest '{manifest.profile_id}' vs profile '{profile.profile_id}'")
    if sorted(manifest.logical_database_ids) != sorted(profile.logical_database_ids()):
        raise ManifestValidationError("logical_database_ids mismatch between manifest and profile")
    if manifest.secret_provider_type != profile.secret_provider:
        raise ManifestValidationError("secret_provider_type mismatch between manifest and profile")
    if manifest.monitoring_exporter_type != profile.monitoring_exporter:
        raise ManifestValidationError("monitoring_exporter_type mismatch between manifest and profile")
