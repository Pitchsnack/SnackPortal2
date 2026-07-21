"""SP2-NEXT-A-PORTABILITY — logical identity tests (O-1/O-2, AC-3/AC-4). Default suite; no DB, no network, no runtime."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402,F401  (bootstraps backend on sys.path)

from shared.portability import identity  # noqa: E402


def test_required_logical_database_ids_exact() -> None:
    assert identity.CONTROL_LOGICAL_DATABASE_ID == "control"
    assert identity.TENANT_LOGICAL_DATABASE_IDS == ("tenant-acme", "tenant-zeta", "tenant-nova")
    assert identity.REQUIRED_LOGICAL_DATABASE_IDS == ("control", "tenant-acme", "tenant-zeta", "tenant-nova")


def test_official_identities_exact() -> None:
    assert identity.OFFICIAL_LOCAL_ENVIRONMENT_ID == "SP2-LOCAL-MVP-01"
    assert identity.LOCAL_PROFILE_ID == "sp2-local-mvp"
    assert identity.CLOUD_TEMPLATE_PROFILE_ID == "sp2-cloud-template"


def test_environment_type_vocabulary_closed() -> None:
    assert identity.SUPPORTED_ENVIRONMENT_TYPES == frozenset({"controlled-local-mvp", "cloud-template"})
    assert identity.RUNTIME_CAPABLE_ENVIRONMENT_TYPES == frozenset({"controlled-local-mvp"})


def test_required_ids_pass_validation() -> None:
    for logical_id in identity.REQUIRED_LOGICAL_DATABASE_IDS:
        identity.validate_logical_database_id(logical_id)
    identity.validate_environment_id(identity.OFFICIAL_LOCAL_ENVIRONMENT_ID)
    identity.validate_environment_id(identity.CLOUD_TEMPLATE_ENVIRONMENT_ID)
    identity.validate_profile_id(identity.LOCAL_PROFILE_ID)
    identity.validate_profile_id(identity.CLOUD_TEMPLATE_PROFILE_ID)


def test_physical_handles_rejected_as_logical_ids() -> None:
    # Every operational-handle family of the current fixture must fail identity validation (AC-4).
    rejected = (
        "sp2_b3a_control",  # container name (underscores + b3a marker)
        "sp2_b3a_tenant_acme_data",  # volume name
        "snackportal2_control_local",  # physical database name
        "snackportal2-b3a-local",  # compose project name
        "5540",  # port
        "tenant-5540",  # port smuggled into a kebab id
        "127.0.0.1",  # host literal
        "localhost",
        "DESKTOP-EXAMPLE01",  # Windows hostname shape (uppercase fails grammar)
        "d:/example/data",  # drive path
        "tenant_acme",  # underscore form
        "Tenant-Acme",  # case
        "",
    )
    for value in rejected:
        try:
            identity.validate_logical_database_id(value)
        except identity.LogicalIdentityError:
            continue
        assert False, f"physical/malformed value accepted as logical database id: {value!r}"


def test_is_physical_handle_detects_marker_families() -> None:
    assert identity.is_physical_handle("sp2_b3a_control")
    assert identity.is_physical_handle("snackportal2-b3a-local")
    assert identity.is_physical_handle("snackportal2_tenant_acme_local")
    assert identity.is_physical_handle("127.0.0.1")
    assert identity.is_physical_handle("localhost")
    assert identity.is_physical_handle("port-5541-handle")
    assert identity.is_physical_handle("C:\\Users\\Example")
    assert not identity.is_physical_handle("control")
    assert not identity.is_physical_handle("tenant-acme")


def test_environment_id_grammar_rejects_malformed() -> None:
    for value in ("sp2-local-mvp", "LOCAL-MVP-01", "SP2_LOCAL_MVP_01", "SP2-", "SP2-local-mvp-01", ""):
        try:
            identity.validate_environment_id(value)
        except identity.LogicalIdentityError:
            continue
        assert False, f"malformed environment id accepted: {value!r}"


def test_profile_id_grammar_rejects_malformed() -> None:
    for value in ("SP2-LOCAL-MVP", "local-mvp", "sp2_local_mvp", "sp2-", ""):
        try:
            identity.validate_profile_id(value)
        except identity.LogicalIdentityError:
            continue
        assert False, f"malformed profile id accepted: {value!r}"


if __name__ == "__main__":
    _h.run(
        [
            test_required_logical_database_ids_exact,
            test_official_identities_exact,
            test_environment_type_vocabulary_closed,
            test_required_ids_pass_validation,
            test_physical_handles_rejected_as_logical_ids,
            test_is_physical_handle_detects_marker_families,
            test_environment_id_grammar_rejects_malformed,
            test_profile_id_grammar_rejects_malformed,
        ]
    )
