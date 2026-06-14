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
