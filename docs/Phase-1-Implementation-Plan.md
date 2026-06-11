# SnackPortal2 — Phase 1 Implementation Plan (as built)

**Build Phase:** 1 — Repository Setup · **Status:** Implemented (scaffolding only)
**Basis:** IC-001–IC-005 (Final); ADR D-01–D-32; Backend-Implementation-Roadmap.md; CLAUDE.md
**Governance:** PRD-P1-R1 (Approved w/ Observations) → PRD-P1-R2 (Fully Approved)

This plan records the structure, ports, boundaries, rules, and build order
delivered in Build Phase 1. It contains **no business logic and no contract
behavior**; every item traces to a Final contract or Approved decision.

> **As-built reconciliations** (from the execution authorization, no architecture
> change): (1) service packages are bare skeletons (entrypoint + health stub +
> traceability + README) — gateway middleware deferred; (2) vendor-neutral ports
> live in their shared domain module, `adapters/interfaces/` holds the generic
> adapter/registry contract, and `adapters/providers/` is the sole (empty)
> vendor-import zone.

## Folders
```
backend/
  shared/            # vendor-neutral leaf: ports + shapes (pure stdlib)
    adapters/
      interfaces.py  # generic ProviderAdapter + ProviderRegistry contracts
      providers/     # EMPTY vendor-import containment zone
  api_gateway/       # entry skeleton (IC-005)
  auth_router/       # skeleton (IC-005; Build Phase 3)
  database_router/   # skeleton (IC-005/IC-002; Build Phase 4)
  control_plane/     # skeleton (IC-001; Build Phase 2)
  import_service/    # skeleton (IC-003; Build Phase 5)
  lineage_service/   # skeleton (IC-004; Build Phase 6)
  tests/architecture/# governance validation (pytest or standalone)
infrastructure/      # env templates (references only); independent of backend
docs/                # plan, acceptance criteria, governance standards, traceability, coding standards
```

## Modules (shared)
| Module | Kind | Contract |
|---|---|---|
| `errors` | denial-semantics shapes | IC-002/IC-005/IC-001 |
| `context` | correlation/request context (secret-free) | IC-002/IC-003/IC-005 |
| `logging` | StructuredLogger port + redaction contract | D-14/D-09 |
| `dto` | cross-cutting DTO shapes | IC-005/D-06 |
| `health` | readiness/liveness shapes (3-state/2-state) | D-10/IC-001/IC-002 |
| `secrets` | SecretStore port + SecretRef/SecretValue | D-14 |
| `queue` | Queue port + JobEnvelope (dispatch-only) | D-19/D-13 |
| `audit` | OperationalAudit port (≠ lineage) | IC-002/IC-003 |
| `config` | ConfigLoader port (references only) | D-14/IC-001 |
| `adapters/interfaces` | ProviderAdapter + ProviderRegistry | F-1/anti-lock-in |
| `adapters/providers` | empty containment zone | F-1/D-14 |

## Package & interface boundaries
- `shared` owns cross-cutting ports/shapes only (admission policy, governance E).
- Each service owns its contract surface; Build Phase 1 ships only a skeleton.
- Ports are vendor-neutral; concrete adapters live only in `**/adapters/providers/**`.

## Dependency rules (enforced — see Coding-Standards.md)
1. `shared` imports no service. 2. No service imports another. 3. `api_gateway` no
DB/router import. 4. `auth_router` auth is DB-free. 5. DB drivers only in
`database_router/adapters/providers/**`. 6. Vendor SDKs only in
`**/adapters/providers/**`. 7. `infrastructure/` independent of `backend/`.
8. Secrets via SecretStore only. 9. Lineage ≠ operational audit.

## Build order (delivered)
1. Tooling + dependency contracts (`pyproject.toml`). 2. `shared` primitives
(errors/context/logging). 3. `shared` ports (secrets/queue/audit/config/health/dto)
+ adapter framework. 4. Service skeletons. 5. Architecture tests. 6. Docs.
7. CI validation rules.

See `Phase-1-Acceptance-Criteria.md` and `Phase-1-Traceability-Matrix.md`.
