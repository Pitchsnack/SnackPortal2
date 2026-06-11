# SnackPortal2 — Phase 1 Acceptance Criteria

**Build Phase:** 1 — Repository Setup · **Source:** PRD-P1-R2 §C (Fully Approved)
Each criterion: **ID · Description · Verification Method · Pass/Fail Condition.**
Automated checks live in `backend/tests/architecture/` + `pyproject.toml`
(`[tool.importlinter]`) + `.gitleaks.toml` + `.github/workflows/ci.yml`.

## Repository Structure
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-RS-1 | 7 packages + `infrastructure/` + `docs/` present | inventory | all present |
| AC-RS-2 | No `ai_gateway` / no cross-tenant package | inventory | absent (D-02; IC-007) |
| AC-RS-3 | Each service independently runnable (entrypoint + health stub) | structural review | independent (IC-002) |
| AC-RS-4 | `infrastructure/` imports no application code | import scan | zero edges (CLAUDE.md 4) |

## Dependency Rules
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-DR-1 | `shared` imports no service | import-linter / `test_dependency_boundaries` | no edge |
| AC-DR-2 | No service imports another | import-linter / arch test | no edge |
| AC-DR-3 | `api_gateway` imports no DB driver / `database_router` | arch test | none |
| AC-DR-4 | `auth_router` auth path is DB-free | import scan | none (D-01/D-05) |
| AC-DR-5 | DB drivers only in `database_router/adapters/providers/**` | `test_vendor_and_db_containment` | none elsewhere |
| AC-DR-6 | Lineage and operational audit distinct | structural review | separate (IC-004 Inv.1) |
| AC-DR-7 | No import cycles | import-linter contracts | acyclic |

## Security
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-SEC-1 | No secret-shaped literal in source/templates | gitleaks / `test_no_secret_literals` | zero (D-14) |
| AC-SEC-2 | No DTO/log/audit field carries a secret/token/payload | shape review | reference-only |
| AC-SEC-3 | Correlation/RequestContext carry no secret/token | shape review | none |
| AC-SEC-4 | Readiness/error comply with Disclosure Standard | review vs governance I | compliant |

## SecretStore
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-SS-1 | SecretStore port is sole path to a secret value | import scan | no non-adapter backend read |
| AC-SS-2 | Descriptors are `{store_ref, version}`; no raw-credential DTO field | shape review | none (D-14) |
| AC-SS-3 | Zero functional providers (port + optional NotConfigured stub) | `providers/` inventory | empty |

## Queue
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-Q-1 | Queue port is dispatch-only (no state schema) | port review | dispatch-only (D-19) |
| AC-Q-2 | No tenant job state in a shared/queue store | review vs governance F | tenant-resident |
| AC-Q-3 | No vendor queue provider shipped | `providers/` inventory | none |

## Adapter
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-AD-1 | Vendor SDK imports only under `**/adapters/providers/**` | `test_vendor_and_db_containment` | enforced |
| AC-AD-2 | Business modules don't import `providers/**` | review / scan | none |
| AC-AD-3 | Ports are vendor-neutral | review | clean |
| AC-AD-4 | Provider selection config-driven via composition root | review | single wiring point |

## CI
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-CI-1 | CI defines lint/format/type/secret-scan/cycle/import-boundary/vendor-import rules, blocking | CI config review | all present |

## Documentation
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-DOC-1 | Traceability matrix maps every module → IC/D | completeness check | no gaps |
| AC-DOC-2 | Coding-standard covers DAG, secret hygiene, naming, disclosure, lineage≠audit | review | present |
| AC-DOC-3 | Governance package recorded in `docs/` | presence | present |

## Traceability
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-TR-1 | No orphan module (each cites a contract) | `test_traceability` + matrix | none |
| AC-TR-2 | No undocumented dependency | import-graph vs DAG | match |
| AC-TR-3 | No contract conflict | review | none |

## No-Business-Logic
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-NBL-1 | Services contain only scaffolding (entrypoint/health/traceability/README) | review + `test_traceability` | scaffolding only |
| AC-NBL-2 | No contract behavior implemented | review vs IC operations | none |

## No-Database-Access
| ID | Description | Verification | Pass |
|---|---|---|---|
| AC-NDB-1 | No DB driver imported (providers empty in P1) | `test_vendor_and_db_containment` | none |
| AC-NDB-2 | No SQL/schema/migration present | scan | none |
