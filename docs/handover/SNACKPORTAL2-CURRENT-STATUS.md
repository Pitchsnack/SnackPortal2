# SNACKPORTAL2-CURRENT-STATUS

**Handover File B — program status at `main` @ `ab8a925` (2026-06-12)**

## Completed

| Area | Status | Evidence |
|---|---|---|
| Backend repository | ✅ Complete, on GitHub (private), CI workflow live | `0a1b45b`..`ab8a925`; 165 production .py files |
| Control Plane (Phase 2/4) | ✅ Built + verified | two-phase bootstrap, tenant registry (7-state lifecycle incl. Provisioning), Global Startup/Investor Directories, readiness, schema gating, control-plane audit |
| Authentication (Phase 3) | ✅ Built + verified | DB-free OIDC stateless JWT; signed tenant claim authoritative; carrier match-or-reject (403 `carrier_mismatch`, twice-tested) |
| Database Router (Phase 4) | ✅ Built + verified | registry-authoritative resolution; per-tenant pools never reused; connection-tenant binding re-checked (IsolationAnomaly); only service permitted tenant-DB access |
| Import Service (Phase 5) | ✅ Built + verified | one-directional import-copy; atomic provenance (data+lineage+checkpoint in one tenant transaction); idempotency (D-20); checkpoint resume |
| Lineage Service (Phase 6) | ✅ Built + verified | tenant-resident append-only hash-chain; live-PG evidence (trigger `P6A01`, UNIQUE(seq), advisory lock, privilege denial, recursive traversal) on PostgreSQL 17.10 |
| CI-gate remediation | ✅ `0c2133a` | packaging fixed; ruff 204→0; format applied; pytest 171 collected/166 passed; **mypy retains a deliberate 45-error inventory (burn-down not yet authorized → CI validate job red at the mypy step by design)** |
| Test state (fresh at `ab8a925`) | ✅ | 166/166 stdlib; 22/22 architecture gates; lint-imports 2/2; gitleaks clean |

## Governance

**D-33 through D-37: Approved** (2026-06-12), registered in `docs/Architecture-Decision-Register.md` with errata **D-33-E1 / D-34-E1**; D-34 amends D-20 in part; D-35 extends D-31 (both annotated). The Workspace concept, audit taxonomy + reference-only representation rule, Global Deal Directory (+ Tenant Anonymity Rule), ownership model (reference-only, AI-ready), and portal contract architecture (gateway-only data access) are all decided and register-tracked.

## Verification

| Review | Result |
|---|---|
| PRD-D33-D37-R1 (pre-approval, 5 agents) | 86/100 — GO WITH AMENDMENTS (all applied) |
| PRD-D33-D37-V2 (post-registration, 4 agents) | **92/100 PASS** — 2 Majors → remediated in Phase 2A |
| PRD-SP2-SESSION-R1 (end-of-session, 3 agents) | **95/100 PASS — GO**; zero ungoverned drift; implementation 7/7 Aligned |

## Reservations (placeholders in `contracts/`)

- **IC-008 — Ownership Contract** (reserved by D-36)
- **IC-009 — Portal Contracts** (reserved by D-37)
- **IC-010 — API Gateway Contract** (reserved 2026-06-12; *is* the "API Gateway contract" D-37/IC-009 require)

## Open Work (dependency order)

1. **Contract Amendments — Set A: IC-005 + IC-002** (next authorized; blocked by nothing)
2. **Set B: IC-001 + IC-003** (after A)
3. **IC-008 authoring** (after B)
4. **IC-010 — API Gateway Contract authoring** (inputs = A+B) → **API Gateway architecture/implementation** (design may start now; co-requisite: durable audit persistence)
5. **IC-009 — Portal Contracts authoring** (after IC-010)
6. **D-15 Provisioning Plan** — parallel-ready now; must add the physical-distinctness verification
7. Frontend integration — blocked by design until IC-009 + gateway exist
8. Carried backlog: mypy 45-error burn-down (turns CI green); D-08 business/legal retention values; durable operational-audit persistence; front-door docs refresh (CLAUDE.md / Project-Overview.md / old handover §11–§19 are stale); commit governance corpus into the repo; PgRoutedSession live-PG round-trip test; IC-006 (post-MVP AI) / IC-007 (deferred cross-tenant)
