# SnackPortal2 — Phase 3 Acceptance Criteria

**Build Phase:** 3 — Authentication Layer · **Source:** PRD-P3-E1 §19
Each criterion: **ID · Description · Verification · Pass.** Checks:
`backend/tests/auth_router/` (behavior) + `backend/tests/architecture/` (guards).

## JWT
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-JWT-1 | Valid signed token yields claims | `test_jwt_validation` | ✓ |
| AC-JWT-2 | Reject `alg=none` | `test_jwt_validation` | ✓ |
| AC-JWT-3 | Reject HS/RS confusion (issuer alg allowlist) | `test_jwt_validation` | ✓ |
| AC-JWT-4 | Require/resolve `kid`; reject unknown | `test_jwt_validation` | ✓ |
| AC-JWT-5 | iss/aud/exp/nbf + signature validation | `test_jwt_validation` | ✓ |

## OIDC
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-OIDC-1 | Validation is DB-free / stateless (no Control-DB, no Tenant-DB, no session) | inspection + `test_jwt_validation` | ✓ |
| AC-OIDC-2 | PyJWT verifier behind a port; dev IdP Keycloak/Dex; static JWKS test fixtures | inspection (providers) | ✓ |

## Membership
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-M-1 | Membership read via control-plane read port (no in-process import) | `test_phase3_auth_router` + inspection | ✓ |
| AC-M-2 | 1:N membership, one active tenant per request | `test_internal_identity` / `test_tenant_context` | ✓ |

## Roles
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-R-1 | D-32 role set; read-only, not evaluated | `models.Role` + `test_tenant_context` | ✓ |
| AC-R-2 | Role surfaced in context; no permission matrix | `test_end_to_end` + inspection | ✓ |

## Tenant Context
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-TC-1 | Active tenant from signed claim; carrier-match else 403 | `test_tenant_context` | ✓ |
| AC-TC-2 | Switch = new token; carrier-match | `test_audit` (switch) + inspection | ✓ |
| AC-TC-3 | CONTROL (no tenant claim) → no active tenant | `test_internal_identity` | ✓ |

## Disclosure
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-D-1 | Unknown / non-member / invalid indistinguishable | `test_tenant_context` | ✓ |
| AC-D-2 | 401 vs 403 semantics; no token/secret in context | `test_disclosure` | ✓ |

## Audit
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-A-1 | Success/failure/switch/carrier-mismatch audited | `test_audit` | ✓ |
| AC-A-2 | Never audit JWT contents/secrets/credentials | `test_audit` | ✓ |

## Security / Readiness
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-S-1 | Fail closed (Control-plane/membership/federation/JWKS unavailable) | `test_tenant_context` | ✓ |
| AC-S-2 | JTI denylist deferred (port only, no storage) | inspection (`ports.JtiDenylistPort`) | ✓ |

## Cross-cutting
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-X-1 | No tenant database access / no DB driver | `test_phase3_auth_router` + `test_vendor_and_db_containment` | ✓ |
| AC-X-2 | No routing logic / no Database Router | inspection | ✓ |
| AC-X-3 | No auth_router → control_plane in-process import (transport only) | `test_phase3_auth_router` + `test_dependency_boundaries` | ✓ |
| AC-X-4 | Traceability: auth_router governed by IC-005/IC-001/IC-002/D-xx | `test_traceability` | ✓ |
| AC-X-5 | No permission/authorization matrix | inspection | ✓ |
