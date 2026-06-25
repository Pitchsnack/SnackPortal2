# PRD 06 B-6 — Provisioning Audit Event Catalog (reconciled, not parallel)

**Catalog version:** v1. This catalog **maps** the provisioning audit event set to the **existing frozen vocabulary** in
`backend/control_plane/events.py` (D15-ARCH-SPEC-01 §14.3), guarded by `EXPECTED_EVENT_ACTIONS` in
`tests/control_plane/test_onboarding_orchestration.py`. B-6 introduces **no** parallel `tenant.provision.*` scheme and
**does not edit** `events.py`.

---

## 1. Mapping to the existing `events.py` vocabulary

Each provisioning phase maps to an existing CamelCase action name. The machine-readable block below is asserted by
`tests/control_plane/test_b6_provisioning_audit_contract.py` — **every right-hand name must be a member of the live
`events.py` action set.**

```
<!-- B6-EVENT-MAP:START -->
requested                -> DatabaseProvisionRequested
succeeded                -> DatabaseProvisionSucceeded
failed                   -> DatabaseProvisionFailed
associated               -> DatabaseAssociated
secret-reference         -> SecretReferenceRegistered
distinctness-started     -> DistinctnessVerificationStarted
distinctness-passed      -> DistinctnessVerificationPassed
distinctness-failed      -> DistinctnessVerificationFailed
verification-incomplete  -> VerificationIncomplete
isolation-anomaly        -> IsolationAnomaly
<!-- B6-EVENT-MAP:END -->
```

(Registration, routing-eligibility, and suspension/decommission events — `TenantRegistered`, `RoutingEnabled/Disabled`,
`RouterCacheInvalidated`, `RegistryMappingChanged`, `TenantSuspended/Reactivated`,
`TenantDecommissionStarted/Completed` — also remain part of the frozen vocabulary and are emitted by the existing
control plane; B-6 does not redefine them.)

## 2. Per-event fields (references only)

Every audit event carries **references only** (no raw secrets, no business payload):

```
event id / type / catalog version · timestamp · actor_ref · tenant_ref · db-target ref · operation / phase ·
decision / readiness-gate id · correlation / request id · source service · outcome · error class + redacted message ·
evidence ref · optional prev-hash / hash (OPTIONAL / forward; NOT IC-004/D-23 lineage)
```

**Never** a raw DSN, password, token, private key, cloud credential, unredacted connection string, or secret value
(IC-001 Global Audit Representation Rule, D-14). The live `ControlAuditRecord` carries the subset
`{actor, tenant_id, action, from_state, to_state, timestamp, correlation_id}`; B-6 does **not** add fields to
`records.py` — the richer set above is the **forward contract's** reference-field model.

## 3. Forward additive-extension proposal (NOT in B-6)

A **rollback** event family does **not** exist in `events.py` today. It is a **documented additive-extension proposal
only**, shipped later as a *separate* governed change to `events.py` **with** a matching `EXPECTED_EVENT_ACTIONS`
update — **never** in B-6, and never as a parallel dotted scheme. Proposed CamelCase names (not yet live):

```
<!-- B6-EVENT-FORWARD:START -->
rollback-started    -> DatabaseProvisionRollbackStarted
rollback-succeeded  -> DatabaseProvisionRollbackSucceeded
rollback-failed     -> DatabaseProvisionRollbackFailed
<!-- B6-EVENT-FORWARD:END -->
```

These names are intentionally **absent** from the live vocabulary; the contract test asserts they are NOT yet members
of `events.py` (i.e. B-6 did not smuggle them in). Adoption is a future phase gated separately.
