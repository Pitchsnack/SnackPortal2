"""D15 provisioning operational-audit event vocabulary (D15-ARCH-SPEC-01 §14.3).

Stable action names for the reference-only operational audit emitted via
`ControlPlaneAudit.record(...)`. Audit authority: IC-002 Audit Requirements -> D-34
Operational Audit -> IC-001 Reference-Only Representation -> IC-010 §J. These are event
*names* only; they define NO lifecycle state (lifecycle stays governed by IC-002).

Records carry references only (actor_ref, tenant_ref, action, from/to state, timestamp,
correlation id) — never names, emails, PII, identity/authorization payloads, business
payloads, copied data, secrets, or credentials (IC-001 Global Audit Representation Rule).
"""

from __future__ import annotations

# Registration / provisioning
TENANT_REGISTERED = "TenantRegistered"
DATABASE_PROVISION_REQUESTED = "DatabaseProvisionRequested"
DATABASE_PROVISION_SUCCEEDED = "DatabaseProvisionSucceeded"
DATABASE_PROVISION_FAILED = "DatabaseProvisionFailed"
DATABASE_ASSOCIATED = "DatabaseAssociated"
SECRET_REFERENCE_REGISTERED = "SecretReferenceRegistered"

# Tenant schema application (D15-ARCH-SPEC-01 §8 Step 2b; PRD 07B) — applying the existing
# provisioning + lineage DDL to a freshly provisioned tenant database, before verification.
TENANT_SCHEMA_APPLICATION_STARTED = "TenantSchemaApplicationStarted"
TENANT_SCHEMA_APPLICATION_SUCCEEDED = "TenantSchemaApplicationSucceeded"
TENANT_SCHEMA_APPLICATION_FAILED = "TenantSchemaApplicationFailed"

# Physical Distinctness Verification (§9)
DISTINCTNESS_VERIFICATION_STARTED = "DistinctnessVerificationStarted"
DISTINCTNESS_VERIFICATION_PASSED = "DistinctnessVerificationPassed"
DISTINCTNESS_VERIFICATION_FAILED = "DistinctnessVerificationFailed"
VERIFICATION_INCOMPLETE = "VerificationIncomplete"
ISOLATION_ANOMALY = "IsolationAnomaly"

# Routing eligibility (provisioning-side; the Database Router remains the sole selector)
ROUTING_ENABLED = "RoutingEnabled"
ROUTING_DISABLED = "RoutingDisabled"
ROUTER_CACHE_INVALIDATED = "RouterCacheInvalidated"
REGISTRY_MAPPING_CHANGED = "RegistryMappingChanged"

# Suspension / reactivation / decommissioning (provisioning-side behavior)
TENANT_SUSPENDED = "TenantSuspended"
TENANT_REACTIVATED = "TenantReactivated"
TENANT_DECOMMISSION_STARTED = "TenantDecommissionStarted"
TENANT_DECOMMISSION_COMPLETED = "TenantDecommissionCompleted"

# Recovery / quarantine (IC-002 Recovery & Compensation; PRD 07D-2b.2a). The {Started} vs
# {Requested} asymmetry below is intentional: OnboardingRecovery* wraps BOTH the automatic
# fence-dispatch resume from Provisioning and the explicit RecoverTenant operation, while
# TenantDeprovision* marks an explicit request-shaped compensation operation.
TENANT_QUARANTINED = "TenantQuarantined"
ONBOARDING_RECOVERY_STARTED = "OnboardingRecoveryStarted"
ONBOARDING_RECOVERY_COMPLETED = "OnboardingRecoveryCompleted"
ONBOARDING_RECOVERY_FAILED = "OnboardingRecoveryFailed"

# Compensation vocabulary (PRD 07D-2b.2a added the NAMES ONLY, keeping the frozen vocabulary in
# lockstep with the amended IC-002; the governed de-provisioning behavior that emits them landed
# in PRD 07D-2b.2b — RecoveryCompensationService.deprovision_tenant_database in recovery.py now
# emits them). This family SUPERSEDES the B-6 forward-proposal DatabaseProvisionRollback* naming
# (docs/runtime/b6_provisioning_audit_events.md).
TENANT_DEPROVISION_REQUESTED = "TenantDeprovisionRequested"
TENANT_DEPROVISION_COMPLETED = "TenantDeprovisionCompleted"
TENANT_DEPROVISION_FAILED = "TenantDeprovisionFailed"
