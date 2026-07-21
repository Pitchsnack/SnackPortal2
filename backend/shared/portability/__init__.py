"""portability — stable logical identities, environment profiles, deployment manifests (SP2-NEXT-A-PORTABILITY).

Bounded portability layer of the Official Controlled Local MVP Environment
master plan (Arc 1 / NEXT-A): logical environment + database identities (O-1/O-2),
the provider-neutral environment-profile contract (O-3–O-5), and the
references-only deployment manifest (O-6). Admission per the Shared Package
Admission Policy (governance E): cross-cutting, owned by no single contract,
consumed by composition roots and operator tooling across services.

Pure standard library; vendor-neutral dependency leaf (imports no service
package, no vendor/cloud SDK); no I/O beyond explicit profile loading; no
environment reads; no runtime behavior. Nothing in this package activates
anything — the B-5 production posture remains NOT READY / DO-NOT-ACTIVATE and
no B5 blocker is closed by this package.
"""

from __future__ import annotations

from .identity import (
    CLOUD_TEMPLATE_ENVIRONMENT_ID,
    CLOUD_TEMPLATE_PROFILE_ID,
    CONTROL_LOGICAL_DATABASE_ID,
    LOCAL_PROFILE_ID,
    OFFICIAL_LOCAL_ENVIRONMENT_ID,
    REQUIRED_LOGICAL_DATABASE_IDS,
    RUNTIME_CAPABLE_ENVIRONMENT_TYPES,
    SUPPORTED_ENVIRONMENT_TYPES,
    TENANT_LOGICAL_DATABASE_IDS,
    EnvironmentType,
    LogicalIdentityError,
    is_physical_handle,
    validate_environment_id,
    validate_logical_database_id,
    validate_profile_id,
)
from .manifest import (
    MANIFEST_SCHEMA_ID,
    DeploymentManifest,
    ManifestValidationError,
    assert_consistent_with_profile,
    canonical_json,
    canonical_payload,
    manifest_digest,
    parse_manifest,
    validate_manifest,
)
from .profile import (
    PROFILE_SCHEMA_ID,
    UNSELECTED,
    DatabaseBinding,
    EnvironmentProfile,
    ProfileNotRuntimeCapableError,
    ProfileValidationError,
    ServiceEndpoint,
    assert_reference_safe,
    load_profile,
    load_profiles,
    parse_profile,
)

__all__ = [
    "CLOUD_TEMPLATE_ENVIRONMENT_ID",
    "CLOUD_TEMPLATE_PROFILE_ID",
    "CONTROL_LOGICAL_DATABASE_ID",
    "LOCAL_PROFILE_ID",
    "MANIFEST_SCHEMA_ID",
    "OFFICIAL_LOCAL_ENVIRONMENT_ID",
    "PROFILE_SCHEMA_ID",
    "REQUIRED_LOGICAL_DATABASE_IDS",
    "RUNTIME_CAPABLE_ENVIRONMENT_TYPES",
    "SUPPORTED_ENVIRONMENT_TYPES",
    "TENANT_LOGICAL_DATABASE_IDS",
    "UNSELECTED",
    "DatabaseBinding",
    "DeploymentManifest",
    "EnvironmentProfile",
    "EnvironmentType",
    "LogicalIdentityError",
    "ManifestValidationError",
    "ProfileNotRuntimeCapableError",
    "ProfileValidationError",
    "ServiceEndpoint",
    "assert_consistent_with_profile",
    "assert_reference_safe",
    "canonical_json",
    "canonical_payload",
    "is_physical_handle",
    "load_profile",
    "load_profiles",
    "manifest_digest",
    "parse_manifest",
    "parse_profile",
    "validate_environment_id",
    "validate_logical_database_id",
    "validate_manifest",
    "validate_profile_id",
]
