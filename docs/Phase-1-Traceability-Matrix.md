# SnackPortal2 — Phase 1 Traceability Matrix

Module/artifact → governing contract(s)/decision(s). Satisfies AC-DOC-1 / AC-TR-1
(no orphan module). Build Phase 1 implements **no contract behavior**; mappings
indicate *governance*, not implemented features.

## Shared library
| Module | Governing |
|---|---|
| `shared/errors.py` | IC-002, IC-005, IC-001 (minimally disclosing) |
| `shared/context.py` | IC-002, IC-003, IC-005; D-14 (secret-free) |
| `shared/logging.py` | D-14, D-09 (redaction) |
| `shared/dto.py` | IC-005, D-06, D-03 |
| `shared/health.py` | IC-001/D-10, IC-002 (readiness); governance I |
| `shared/secrets.py` | D-14 |
| `shared/queue.py` | D-19, D-13; governance F |
| `shared/audit.py` | IC-002, IC-003; IC-004 (separation) |
| `shared/config.py` | D-14, IC-001 |
| `shared/adapters/interfaces.py` | F-1, anti-vendor-lock-in |
| `shared/adapters/providers/` | F-1, D-14 (empty containment zone) |

## Service skeletons
| Package | Governing | Deferred to |
|---|---|---|
| `api_gateway` | IC-005, IC-001 | (entry; later) |
| `auth_router` | IC-005; D-03, D-05, D-06, D-32 | Build Phase 3 |
| `database_router` | IC-005, IC-002; D-07, D-13, D-30 | Build Phase 4 |
| `control_plane` | IC-001; D-01, D-10, D-11, D-12, D-31 | Build Phase 2 |
| `import_service` | IC-003; D-18–D-21, D-09 | Build Phase 5 |
| `lineage_service` | IC-004; D-22–D-25 | Build Phase 6 |

## Governance / CI artifacts
| Artifact | Governing |
|---|---|
| `pyproject.toml` `[tool.importlinter]` | dependency DAG (rules 1–2, cycles) |
| `tests/architecture/test_dependency_boundaries.py` | shared-leaf, service independence |
| `tests/architecture/test_vendor_and_db_containment.py` | F-1; CLAUDE.md 1–2; no-DB-outside-router |
| `tests/architecture/test_traceability.py` | AC-TR-1 / AC-NBL |
| `tests/architecture/test_no_secret_literals.py` | D-14; AC-SEC-1 |
| `.gitleaks.toml`, `.github/workflows/ci.yml` | R-CI-1…R-CI-7 (validation only) |
| `infrastructure/env/*` | D-14 (references only); CLAUDE.md 4 |

## Intentionally absent
| Absent | Reason |
|---|---|
| `ai_gateway` / AI modules | D-02; IC-006 deferred post-MVP |
| cross-tenant module | IC-007 deferred; D-30 (no cross-tenant path) |
| concrete providers | Roadmap P1 (interfaces only); `providers/` empty |
| DB drivers / SQL / migrations | No database access in Build Phase 1 |
