# CURRENT-STATUS

**Handover H2 — program & governance status at `main` @ `de3169a` (2026-06-13)**

## Program Status

| | |
|---|---|
| **Current branch** | `main` (tracking `origin/main`, github.com/Pitchsnack/SnackPortal2, private) |
| **Current commit** | `de3169a` — "PRD-IC010-01-R1: review remediation … in IC-010 (docs only)" |
| **Repository status** | Clean working tree; all work pushed |
| **Test status** | **166/166** stdlib tests pass; live-PostgreSQL lineage evidence on PG 17.10 (per-file `requires_pg` runners) |
| **Architecture gate status** | **22/22** architecture gates pass; import-linter 2/2; gitleaks clean |
| **Backend** | Frozen — byte-identical since `0c2133a`; every commit since is docs/contracts-only. `api_gateway` is a scaffold (`IMPLEMENTS_BEHAVIOR = False`, test-enforced); `frontend/` is empty by design |
| **CI note** | GitHub CI `validate` job is red **by design** at the `mypy` step (a deliberate 45-error inventory awaiting an authorized burn-down); all other gates green |

## Governance Status

### ADRs (architecture-defining set)

| ADR | Decision | Status |
|---|---|---|
| D-30 | Cross-tenant isolation (defense-in-depth; no cross-tenant joins) | ✅ Approved |
| D-31 | Global Directory Residency (Control DB) | ✅ Approved · **extended by D-35** (Deal Directory) |
| D-32 | Role hierarchy (CONTROL, MASTER_AGENT, TENANT_ADMIN/AGENT, STARTUP/INVESTOR_USER) | ✅ Approved |
| **D-33** | Workspace = UI representation of the signed tenant context | ✅ Approved · errata **D-33-E1** (mandatory carrier-on-CONTROL anomaly audit; MembershipsForPrincipal → IC-002) |
| **D-34** (R2) | Operational audit = Control DB / lineage = tenant DB; reference-only audit; user-controlled re-import (amends D-20 in part) | ✅ Approved · errata **D-34-E1** (publication/directory audit = Not Implemented) |
| **D-35** (R2) | Global Deal Directory (extends D-31); Tenant Anonymity + Publication Boundary Rules | ✅ Approved |
| **D-36** (R2) | Ownership (one human owner + reserved nullable AI ref; reference-only; ownership ≠ authorization/routing/residency; audit follows record residency) | ✅ Approved |
| **D-37** (R3) | Portals = presentation-layer contracts; gateway-only data access; reserves IC-009 | ✅ Approved |
| D-20 | Import idempotency | ✅ Resolved · **amended in part by D-34** (default-upsert re-import superseded by user-controlled) |

(D-01..D-29 + JWT lifecycle: Resolved 2026-06-05, foundational/frozen-MVP set. Authoritative register: `docs/Architecture-Decision-Register.md`.)

### Contracts

| Contract | Status |
|---|---|
| IC-001 Global Startup | **Final** · amended (CAP-01B: Global Deal Directory, Tenant Anonymity Rule, audit homes + Global Audit Representation Rule, retention) |
| IC-002 Tenant Startup | **Final** · amended (CAP-01A: Tenant Workspace alias, MembershipsForPrincipal, D-33 audit events) |
| IC-003 Import | **Final** · amended (CAP-01B: Global record ∨ Deal; D-20 amended-in-part; user-controlled re-import; sync prohibition; lineage preservation) |
| IC-004 Lineage | **Final** · unchanged (tenant-resident, append-only) |
| IC-005 Authentication Routing | **Final** · amended (CAP-01A: Workspace Terminology & Carriers; subdomain + `X-Tenant-Id`; mandatory `CarrierOnControlAnomaly`) |
| IC-006 AI Gateway | Draft — post-MVP (D-02) |
| IC-007 Deal Collaboration & Cross-Tenant Sharing | Deferred placeholder — prohibition in force |
| **IC-008 Ownership** | **Final** · authored (CAP-01C) |
| **IC-009 Portal Contracts** | **Reserved** (D-37) — authoring is Phase 3C |
| **IC-010 API Gateway Contract** | **Final** · authored (PRD-IC010-01-R1) |

### Reviews & Verification

| Date | Review | Result |
|---|---|---|
| 2026-06-12 | PRD-D33-D37-R1 (pre-approval, 5 agents) | 86/100 — GO w/ amendments (applied) |
| 2026-06-12 | PRD-D33-D37-V2 (post-registration, 4 agents) | **92/100 PASS** — Majors remediated |
| 2026-06-12 | PRD-SP2-SESSION-R1 (end-of-session, 3 agents) | **95/100 PASS — GO**; zero ungoverned drift |
| 2026-06-13 | CAP-01A / CAP-01B / CAP-01C R1 reviews (each set) | **PASS** — 0 Blockers, 0 Majors each |
| 2026-06-13 | **PRD-CAP-01-V1** (whole-package post-implementation, 6 adversarial reviewers) | **PASS, 99/100 — GO**; 0 Critical/0 Major; MVP PASS |
| 2026-06-13 | **PRD-IC010-01 review** (pre-authoring) → **§11 Independent Review** (4 adversarial reviewers) | APPROVE-W/-AMENDMENTS → **PASS**; all 14 invariant-disproof attempts failed |

**Governance corpus** (review/verification reports, authorizing PRDs, Inventory R2) currently lives **outside the repo** under `D:\Pitchsnack\PRD\` (folders `1. Workspace Architecture`, `2. Governance Chain Remediation`, `3. Contact Amendment Package`, `4. API Gateway`). Committing it into `docs/governance/` remains a tracked ride-along.
