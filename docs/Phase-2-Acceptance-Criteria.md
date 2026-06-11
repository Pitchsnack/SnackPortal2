# SnackPortal2 — Phase 2 Acceptance Criteria

**Build Phase:** 2 — Control Plane · **Source:** PRD-P2-E1 (Revised) §16
Each criterion: **ID · Description · Verification · Pass.** Automated checks:
`backend/tests/control_plane/` (behavior) + `backend/tests/architecture/` (boundaries).

## Bootstrap
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-B-1 | Phase 0 verifies system identity vs trust anchor with no DB access | `test_bootstrap` | ✓ |
| AC-B-2 | Phase 1 begins only after identity + Control DB reachable + schema compatible | `test_bootstrap` | ✓ |
| AC-B-3 | Phase 0 closed + break-glass disabled at transition (§14) | `test_bootstrap` | ✓ |

## Registry
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-R-1 | RegisterTenant→Registered; idempotent by tenant_id | `test_registry` | ✓ |
| AC-R-2 | Reference model stored; **no credentials/secrets** (D-14) | `test_registry` | ✓ |
| AC-R-3 | Phase 2 sets Registered/Provisioning/Suspended/Decommissioned only | `test_registry` | ✓ |
| AC-R-4 | **No tenant becomes Ready**; Verify/Activate/Reactivate/Reassociate deferred | `test_registry` | ✓ |

## Membership
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-M-1 | 1:N user→tenants; MASTER_AGENT multi-assignment (D-04/D-32) | `test_membership_federation` | ✓ |
| AC-M-2 | Roles stored, not evaluated; no authz/permission/JWT | `test_membership_federation` | ✓ |

## Federation
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-F-1 | Store issuer/audience/jwks_ref/claim rule; storage only | `test_membership_federation` | ✓ |
| AC-F-2 | No runtime validation / JWT / OIDC processing | `test_membership_federation` + `test_phase2_control_plane` | ✓ |

## Discovery
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-D-1 | Global Startup/Investor directories; Control-DB only; Global≠Tenant | `test_audit_directory` | ✓ |
| AC-D-2 | Stable identifiers for future IC-003/IC-004 | `test_audit_directory` | ✓ |

## Readiness
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-RD-1 | ready / degraded / not-ready (D-10) | `test_readiness_schema` | ✓ |
| AC-RD-2 | degraded observability-only; disclosure-safe reports | `test_readiness_schema` | ✓ |

## Schema Compatibility
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-SC-1 | Pass/Fail/Version Mismatch/Migration Required; detect-only | `test_readiness_schema` | ✓ |
| AC-SC-2 | Readiness mapping (Pass→ready-eligible; others→not-ready) | `test_readiness_schema` | ✓ |

## Audit
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-A-1 | Lifecycle/registration/association events audited (IC-002) | `test_audit_directory` | ✓ |
| AC-A-2 | No secrets/credentials; no lineage/hash-chaining (≠ IC-004) | `test_audit_directory` + `test_phase2_control_plane` | ✓ |

## Security / Isolation
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-S-1 | Trust anchor resolved by reference; SecretValue redacted (D-14) | `test_secret_provider` | ✓ |
| AC-S-2 | Provider = trust-anchor only; no KMS/Vault/cloud SDK (F-1) | `test_secret_provider` | ✓ |

## Cross-cutting
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-X-1 | No tenant database access (no DB driver imported) | `test_vendor_and_db_containment` + `test_phase2_control_plane` | ✓ |
| AC-X-2 | No authentication/JWT/OIDC runtime logic | `test_phase2_control_plane` | ✓ |
| AC-X-3 | No routing logic / no Database Router | inspection + `test_phase2_control_plane` | ✓ |
| AC-X-4 | Traceability: control_plane governed by IC-001/IC-002/IC-005 | `test_traceability` | ✓ |
| AC-X-5 | Dependency DAG intact (shared-leaf; no service-to-service) | `test_dependency_boundaries` | ✓ |
