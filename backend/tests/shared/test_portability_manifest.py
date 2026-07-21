"""SP2-NEXT-A-PORTABILITY — deployment-manifest tests (§8.4, §9). Default suite; no DB, no Docker, no network, no runtime."""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any, Dict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402
import _portability_paths as _paths  # noqa: E402

from shared.portability import identity, manifest, profile  # noqa: E402

_COMMIT = "c765c7164075b648adeeb26fc7d856934a410e7c"
_DIGEST_A = "sha256:" + "a" * 64
_DIGEST_B = "sha256:" + "b" * 64
_IMG_SERVICE = "snackportal2/api-gateway:0.0.0@sha256:" + "c" * 64
_IMG_SERVICE_2 = "snackportal2/database-router:0.0.0@sha256:" + "d" * 64
_IMG_DB = "postgres:17@sha256:" + "e" * 64


def _local_manifest(**overrides: object) -> manifest.DeploymentManifest:
    fields: Dict[str, Any] = dict(
        environment_id=identity.OFFICIAL_LOCAL_ENVIRONMENT_ID,
        profile_id=identity.LOCAL_PROFILE_ID,
        host_or_platform_ref="config://host/sp2-local-host",
        operator_ref="config://operator/environment-owner",
        repository_commit=_COMMIT,
        configuration_digest=_DIGEST_A,
        service_image_refs=(_IMG_SERVICE, _IMG_SERVICE_2),
        database_image_refs=(_IMG_DB,),
        migration_digest=_DIGEST_B,
        logical_database_ids=identity.REQUIRED_LOGICAL_DATABASE_IDS,
        secret_provider_type="env-reference",
        backup_target_type="local-filesystem",
        monitoring_exporter_type="local-structured-log",
        started_at="2026-07-22T00:00:00Z",
    )
    fields.update(overrides)
    return manifest.DeploymentManifest(**fields)


def _expect_rejection(why: str, **overrides: object) -> manifest.ManifestValidationError:
    try:
        manifest.validate_manifest(_local_manifest(**overrides))
    except manifest.ManifestValidationError as exc:
        return exc
    raise AssertionError(f"invalid manifest accepted: {why}")


# ---------------------------------------------------------------------------
# Determinism (§8.4: deterministic serialization, reproducible digest, stable ordering)
# ---------------------------------------------------------------------------


def test_deterministic_serialization_independent_of_construction_order() -> None:
    a = _local_manifest()
    b = _local_manifest(
        service_image_refs=(_IMG_SERVICE_2, _IMG_SERVICE),  # reversed construction order
        logical_database_ids=tuple(reversed(identity.REQUIRED_LOGICAL_DATABASE_IDS)),
    )
    assert manifest.canonical_json(a) == manifest.canonical_json(b), "collection construction order leaked into the serialization"


def test_deterministic_digest_repeatable() -> None:
    m = _local_manifest()
    assert manifest.manifest_digest(m) == manifest.manifest_digest(m)
    assert manifest.manifest_digest(m) == manifest.manifest_digest(_local_manifest())


def test_digest_changes_when_a_field_changes() -> None:
    assert manifest.manifest_digest(_local_manifest()) != manifest.manifest_digest(_local_manifest(started_at="2026-07-22T00:00:01Z"))


def test_stable_key_ordering_and_compact_form() -> None:
    serialized = manifest.canonical_json(_local_manifest())
    payload = json.loads(serialized)
    assert list(payload.keys()) == sorted(payload.keys()), "canonical JSON keys are not sorted"
    assert ": " not in serialized and ", " not in serialized, "canonical JSON is not compact"
    assert serialized == serialized.encode("ascii", errors="strict").decode("ascii"), "canonical JSON is not ASCII-only"


def test_round_trip_parse_preserves_digest() -> None:
    m = _local_manifest()
    parsed = manifest.parse_manifest(manifest.canonical_payload(m))
    assert manifest.manifest_digest(parsed) == manifest.manifest_digest(m)


def test_unknown_manifest_fields_rejected_deterministically() -> None:
    payload = manifest.canonical_payload(_local_manifest())
    payload["zzz_extra"] = "x"
    payload["aaa_extra"] = "y"
    try:
        manifest.parse_manifest(payload)
    except manifest.ManifestValidationError as first:
        try:
            manifest.parse_manifest(payload)
        except manifest.ManifestValidationError as second:
            assert str(first) == str(second)
            assert str(first).index("aaa_extra") < str(first).index("zzz_extra")
            return
    assert False, "unknown manifest fields accepted"


# ---------------------------------------------------------------------------
# Secret safety (§9: secret-safe output; no credential leakage)
# ---------------------------------------------------------------------------


def test_secret_bearing_fields_rejected_without_echo() -> None:
    planted = "postgresql://sp2:pw@db.internal:5432/control"
    exc = _expect_rejection("raw DSN in host_or_platform_ref", host_or_platform_ref=planted)
    assert "pw@" not in str(exc) and "db.internal" not in str(exc), "manifest validation echoed the planted DSN"


def test_serialized_output_is_secret_free_for_valid_manifests() -> None:
    serialized = manifest.canonical_json(_local_manifest())
    for needle in ("password", "postgresql://", "127.0.0.1", "localhost", "BEGIN PRIVATE KEY"):
        assert needle not in serialized, f"secret-shaped content in canonical output: {needle!r}"


def test_raw_endpoint_values_rejected() -> None:
    _expect_rejection("bare host:port as platform ref", host_or_platform_ref="db.internal:5432")
    _expect_rejection("windows path as operator ref", operator_ref="C:\\SP2\\operator")
    _expect_rejection("free-text operator value", operator_ref="environment-owner")


# ---------------------------------------------------------------------------
# Field validation
# ---------------------------------------------------------------------------


def test_commit_and_digest_grammars_enforced() -> None:
    _expect_rejection("short commit", repository_commit="abc123")
    _expect_rejection("digest without algorithm tag", configuration_digest="a" * 64)
    _expect_rejection("bad migration digest", migration_digest="sha256:xyz")
    _expect_rejection("non-digest-pinned image", service_image_refs=("snackportal2/api-gateway:latest",))
    _expect_rejection("malformed started_at", started_at="2026-07-22 00:00:00")


def test_logical_database_ids_enforced() -> None:
    _expect_rejection("missing control", logical_database_ids=identity.TENANT_LOGICAL_DATABASE_IDS)
    _expect_rejection("duplicate id", logical_database_ids=identity.REQUIRED_LOGICAL_DATABASE_IDS + ("control",))
    _expect_rejection("container name as id", logical_database_ids=identity.REQUIRED_LOGICAL_DATABASE_IDS + ("sp2_b3a_control",))


# ---------------------------------------------------------------------------
# Profile support (§9: local and cloud template both supported)
# ---------------------------------------------------------------------------


def test_manifest_supports_local_profile() -> None:
    local = profile.load_profile(_paths.LOCAL_PROFILE_PATH)
    m = _local_manifest()
    manifest.assert_consistent_with_profile(m, local)


def test_manifest_supports_cloud_template_profile() -> None:
    cloud = profile.load_profile(_paths.CLOUD_TEMPLATE_PROFILE_PATH)
    m = _local_manifest(
        environment_id=cloud.environment_id,
        profile_id=cloud.profile_id,
        secret_provider_type=profile.UNSELECTED,
        monitoring_exporter_type=profile.UNSELECTED,
    )
    manifest.assert_consistent_with_profile(m, cloud)


def test_manifest_profile_mismatch_rejected() -> None:
    local = profile.load_profile(_paths.LOCAL_PROFILE_PATH)
    try:
        manifest.assert_consistent_with_profile(_local_manifest(secret_provider_type="other-provider"), local)
    except manifest.ManifestValidationError:
        return
    assert False, "manifest/profile provider mismatch accepted"


if __name__ == "__main__":
    _h.run(
        [
            test_deterministic_serialization_independent_of_construction_order,
            test_deterministic_digest_repeatable,
            test_digest_changes_when_a_field_changes,
            test_stable_key_ordering_and_compact_form,
            test_round_trip_parse_preserves_digest,
            test_unknown_manifest_fields_rejected_deterministically,
            test_secret_bearing_fields_rejected_without_echo,
            test_serialized_output_is_secret_free_for_valid_manifests,
            test_raw_endpoint_values_rejected,
            test_commit_and_digest_grammars_enforced,
            test_logical_database_ids_enforced,
            test_manifest_supports_local_profile,
            test_manifest_supports_cloud_template_profile,
            test_manifest_profile_mismatch_rejected,
        ]
    )
