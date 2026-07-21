"""SP2-NEXT-A-PORTABILITY — profile contract + validation tests (§8.1–8.3, §9). Default suite; no DB, no network, no runtime."""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any, Dict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402
import _portability_paths as _paths  # noqa: E402

from shared.portability import identity, profile  # noqa: E402

# ---------------------------------------------------------------------------
# Committed-profile tests (§9 "Profile Tests")
# ---------------------------------------------------------------------------


def _local() -> profile.EnvironmentProfile:
    return profile.load_profile(_paths.LOCAL_PROFILE_PATH)


def _cloud() -> profile.EnvironmentProfile:
    return profile.load_profile(_paths.CLOUD_TEMPLATE_PROFILE_PATH)


def _local_doc() -> Dict[str, Any]:
    doc = json.loads(_paths.LOCAL_PROFILE_PATH.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    return doc


def test_local_profile_loads_and_identifies() -> None:
    p = _local()
    assert p.profile_id == identity.LOCAL_PROFILE_ID
    assert p.environment_id == identity.OFFICIAL_LOCAL_ENVIRONMENT_ID
    assert p.environment_type == "controlled-local-mvp"
    assert p.is_runtime_capable
    p.assert_runtime_capable()  # must not raise


def test_cloud_template_loads_and_identifies() -> None:
    p = _cloud()
    assert p.profile_id == identity.CLOUD_TEMPLATE_PROFILE_ID
    assert p.environment_type == "cloud-template"
    assert p.environment_id != identity.OFFICIAL_LOCAL_ENVIRONMENT_ID


def test_required_logical_ids_match_in_both_profiles() -> None:
    local, cloud = _local(), _cloud()
    assert sorted(local.logical_database_ids()) == sorted(identity.REQUIRED_LOGICAL_DATABASE_IDS)
    assert sorted(cloud.logical_database_ids()) == sorted(identity.REQUIRED_LOGICAL_DATABASE_IDS)
    assert sorted(local.logical_database_ids()) == sorted(cloud.logical_database_ids())


def test_profile_ids_differ() -> None:
    assert _local().profile_id != _cloud().profile_id


def test_invariant_contract_fields_remain_compatible() -> None:
    # The cloud template must carry the same contract fields and the same logical identity
    # model as local (O-5); only provider selection and posture may differ.
    local, cloud = _local(), _cloud()
    assert local.logical_database_ids() == cloud.logical_database_ids()
    assert tuple(s.service_id for s in local.service_endpoints) == tuple(s.service_id for s in cloud.service_endpoints)
    assert tuple(b.endpoint_ref for b in local.logical_databases) == tuple(b.endpoint_ref for b in cloud.logical_databases)


def test_local_physical_configuration_never_becomes_logical_identity() -> None:
    # The committed local profile must contain no port, host, IP, DSN, container name,
    # or Windows path anywhere — physical endpoints stay in operator configuration (O-4/AC-4).
    text = _paths.LOCAL_PROFILE_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "5540",
        "5541",
        "5542",
        "5543",
        "127.0.0.1",
        "localhost",
        "sp2_b3a_",
        "snackportal2_",
        "postgresql://",
        ":\\\\",
        "C:/",
    ):
        assert forbidden not in text, f"physical configuration leaked into the local profile: {forbidden!r}"
    for binding in _local().logical_databases:
        identity.validate_logical_database_id(binding.logical_id)


def test_cloud_template_cannot_activate_runtime() -> None:
    p = _cloud()
    assert not p.is_runtime_capable
    try:
        p.assert_runtime_capable()
    except profile.ProfileNotRuntimeCapableError:
        return
    assert False, "cloud template accepted as runtime-capable (AC-2 violated)"


def test_cloud_template_selects_no_provider() -> None:
    p = _cloud()
    for field in profile.PROVIDER_SELECTOR_FIELDS:
        assert getattr(p, field) == profile.UNSELECTED, f"cloud template chose a concrete provider in {field}"


def test_profile_set_loads_with_unique_ids() -> None:
    profiles = profile.load_profiles([_paths.LOCAL_PROFILE_PATH, _paths.CLOUD_TEMPLATE_PROFILE_PATH])
    assert len(profiles) == 2
    try:
        profile.load_profiles([_paths.LOCAL_PROFILE_PATH, _paths.LOCAL_PROFILE_PATH])
    except profile.ProfileValidationError:
        return
    assert False, "duplicate profile_id across the profile set was accepted"


# ---------------------------------------------------------------------------
# Validation-rejection tests (§9 "Validation Tests") — planted violations
# ---------------------------------------------------------------------------


def _expect_rejection(doc: Dict[str, Any], why: str) -> profile.ProfileValidationError:
    try:
        profile.parse_profile(doc)
    except profile.ProfileValidationError as exc:
        return exc
    raise AssertionError(f"invalid profile accepted: {why}")


def test_raw_password_rejected_and_not_echoed() -> None:
    doc = _local_doc()
    planted = "password=hunter2-super-secret"
    doc["artifact_destination_ref"] = planted
    exc = _expect_rejection(doc, "raw password value")
    assert "hunter2" not in str(exc), "validation error echoed the planted secret value"


def test_raw_dsn_rejected_and_not_echoed() -> None:
    doc = _local_doc()
    planted = "postgresql://sp2:pw@db.internal:5432/control"
    doc["logical_databases"][0]["endpoint_ref"] = planted
    exc = _expect_rejection(doc, "raw DSN endpoint")
    assert "pw@" not in str(exc) and "db.internal" not in str(exc), "validation error echoed the planted DSN"


def test_duplicate_database_id_rejected() -> None:
    doc = _local_doc()
    doc["logical_databases"].append({"logical_id": "tenant-acme", "endpoint_ref": "ref:db/tenant-acme/endpoint@1"})
    _expect_rejection(doc, "duplicate logical database id")


def test_missing_control_id_rejected() -> None:
    doc = _local_doc()
    doc["logical_databases"] = [entry for entry in doc["logical_databases"] if entry["logical_id"] != "control"]
    _expect_rejection(doc, "missing control logical id")


def test_missing_tenant_id_rejected() -> None:
    doc = _local_doc()
    doc["logical_databases"] = [entry for entry in doc["logical_databases"] if entry["logical_id"] != "tenant-nova"]
    _expect_rejection(doc, "missing tenant-nova logical id")


def test_unsupported_profile_type_rejected() -> None:
    doc = _local_doc()
    doc["environment_type"] = "production"
    _expect_rejection(doc, "unsupported environment type")


def test_business_rule_override_rejected_at_any_depth() -> None:
    top = _local_doc()
    top["routing"] = {"tenant-acme": "control"}
    _expect_rejection(top, "top-level business-rule override")

    nested = _local_doc()
    nested["logical_databases"] = list(nested["logical_databases"]) + [{"ownership_rules": {"ai_owner": "optional"}}]
    _expect_rejection(nested, "nested business-rule override")


def test_reference_safety_patterns_detect_planted_secrets() -> None:
    planted = (
        "postgresql://sp2:pw@db.internal:5432/control",  # dsn
        "https://user:token@example.internal/hook",  # url credentials
        "password=hunter2",  # password assignment
        "AKIA" + "A" * 16,  # aws access key shape (constructed so repo secret scans never see it verbatim)
        "-----BEGIN RSA " + "PRIVATE KEY-----",  # private key header (constructed)
        "xoxb-" + "0123456789-abcdef",  # token shape (constructed)
        "10.0.0.7",  # bare IP endpoint
        "db.internal:5432/control",  # host:port
        "C:\\SP2\\artifacts",  # windows path
    )
    for value in planted:
        try:
            profile.assert_reference_safe("field", value)
        except profile.ProfileValidationError as exc:
            assert value not in str(exc), "reference-safety error echoed the offending value"
            continue
        assert False, f"raw secret / physical endpoint not detected: {value!r}"


def test_unknown_fields_rejected_deterministically() -> None:
    doc = _local_doc()
    doc["zeta_extra"] = 1
    doc["alpha_extra"] = 2
    first = str(_expect_rejection(doc, "unknown fields"))
    second = str(_expect_rejection(doc, "unknown fields"))
    assert first == second, "unknown-field rejection is not deterministic"
    assert first.index("alpha_extra") < first.index("zeta_extra"), "unknown fields not reported in sorted order"


def test_missing_required_field_rejected() -> None:
    doc = _local_doc()
    del doc["secret_provider"]
    _expect_rejection(doc, "missing required field")


def test_runtime_capable_profile_must_select_providers() -> None:
    doc = _local_doc()
    doc["secret_provider"] = profile.UNSELECTED
    _expect_rejection(doc, "runtime-capable profile with unselected provider")


def test_cloud_template_must_not_select_providers() -> None:
    doc = json.loads(_paths.CLOUD_TEMPLATE_PROFILE_PATH.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    doc["secret_provider"] = "env-reference"
    _expect_rejection(doc, "cloud template choosing a concrete provider")


def test_cloud_template_must_not_claim_official_local_environment_id() -> None:
    doc = json.loads(_paths.CLOUD_TEMPLATE_PROFILE_PATH.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    doc["environment_id"] = identity.OFFICIAL_LOCAL_ENVIRONMENT_ID
    _expect_rejection(doc, "cloud template claiming SP2-LOCAL-MVP-01")


def test_physical_handle_as_logical_id_rejected() -> None:
    doc = _local_doc()
    doc["logical_databases"][1]["logical_id"] = "sp2_b3a_tenant_acme"
    _expect_rejection(doc, "container name offered as logical id")


def test_localhost_endpoint_ref_rejected() -> None:
    doc = _local_doc()
    doc["service_endpoints"][0]["endpoint_ref"] = "service://localhost"
    _expect_rejection(doc, "loopback host in a service reference")


if __name__ == "__main__":
    _h.run(
        [
            test_local_profile_loads_and_identifies,
            test_cloud_template_loads_and_identifies,
            test_required_logical_ids_match_in_both_profiles,
            test_profile_ids_differ,
            test_invariant_contract_fields_remain_compatible,
            test_local_physical_configuration_never_becomes_logical_identity,
            test_cloud_template_cannot_activate_runtime,
            test_cloud_template_selects_no_provider,
            test_profile_set_loads_with_unique_ids,
            test_raw_password_rejected_and_not_echoed,
            test_raw_dsn_rejected_and_not_echoed,
            test_duplicate_database_id_rejected,
            test_missing_control_id_rejected,
            test_missing_tenant_id_rejected,
            test_unsupported_profile_type_rejected,
            test_business_rule_override_rejected_at_any_depth,
            test_reference_safety_patterns_detect_planted_secrets,
            test_unknown_fields_rejected_deterministically,
            test_missing_required_field_rejected,
            test_runtime_capable_profile_must_select_providers,
            test_cloud_template_must_not_select_providers,
            test_cloud_template_must_not_claim_official_local_environment_id,
            test_physical_handle_as_logical_id_rejected,
            test_localhost_endpoint_ref_rejected,
        ]
    )
