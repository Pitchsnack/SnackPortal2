# COMPLETED-WORK

**Handover H3 — completed work as of `de3169a` (2026-06-13)**

## Completed Backend Build Phases (frozen)

Phase 1 (repository/scaffolding) · Phase 2 (Control Plane) · Phase 3 (Authentication) · Phase 4 (Database Router) · Phase 5 (Import Service) · Phase 6 (Lineage Service) — all PMO-accepted and verified; live-PostgreSQL evidence on PG 17.10. CI-gate remediation at `0c2133a` (packaging, ruff 0, format, pytest collision fixed; mypy 45-error inventory deliberately retained). Backend has been **byte-identical since `0c2133a`** — all later work is docs/contracts-only.

Built and test-enforced services: `control_plane`, `auth_router`, `database_router`, `import_service`, `lineage_service`. Deliberate scaffold: `api_gateway` (`IMPLEMENTS_BEHAVIOR = False`). Deliberately empty: `frontend/`.

## Completed ADRs

| ADR | Title | Notes |
|---|---|---|
| **D-33** | Workspace Definition & Tenant Context Architecture | + errata D-33-E1 |
| **D-34** (R2) | Operational Audit Architecture & Re-Import Governance | + errata D-34-E1; amends D-20 in part |
| **D-35** (R2) | Global Deal Directory Architecture | extends D-31 |
| **D-36** (R2) | Ownership Architecture | reserves IC-008 |
| **D-37** (R3) | Portal Contract Architecture | reserves IC-009; requires the "API Gateway contract" (= IC-010) |

All Approved 2026-06-12, registered in `docs/Architecture-Decision-Register.md`. (Foundational set D-01..D-32 Resolved earlier.)

## Completed Contracts

| Contract | Completion |
|---|---|
| **IC-001** | Final · amended by CAP-01B |
| **IC-002** | Final · amended by CAP-01A |
| **IC-003** | Final · amended by CAP-01B |
| **IC-004** | Final · unchanged (reaffirmed) |
| **IC-005** | Final · amended by CAP-01A |
| **IC-008** | Final · authored by CAP-01C |
| **IC-010** | Final · authored by PRD-IC010-01-R1 |

(IC-006 Draft / IC-007 Deferred / IC-009 Reserved — not yet authored, by design.)

## Completed Amendment & Verification Packages

| Package | What it did | Outcome |
|---|---|---|
| **CAP-01A** | IC-005 + IC-002 amendments per D-33 / D-33-E1 (Workspace Terminology & Carriers; Tenant Workspace alias; MembershipsForPrincipal; audit events) | Executed + R1 review **PASS** |
| **CAP-01B** | IC-001 + IC-003 amendments per D-34-R2 / D-35-R2 (Global Deal Directory; Tenant Anonymity + Publication Boundary Rules; audit taxonomy + Global Audit Representation Rule; Global record ∨ Deal; D-20 amended-in-part; user-controlled re-import; sync prohibition; lineage preservation) | Executed + R1 review **PASS** |
| **CAP-01C** | IC-008 Ownership Contract authored per D-36-R2 (reference-only ownership; human-owner mandate; AI-ready nullable slot; eligibility matrix; import/transfer/audit rules; audit residency) | Executed + R1 review **PASS** |
| **PRD-CAP-01-V1** | Independent post-implementation verification of the whole package (A+B+C), 6 adversarial reviewers | **PASS, 99/100 — GO**; MVP PASS; 0 Critical/0 Major |
| **PRD-IC010-01-R1** | IC-010 API Gateway Contract authored (Reserved → Final), then §11 independent adversarial review | **PASS**; all 14 invariant-disproof attempts failed |

### Session commit ledger (`500940a`..`de3169a`)
`728c9f9`, `777dd72`, `b253fed` (CAP-01A) · `60798ba`, `72f1561`, `16739e9` (CAP-01B) · `a8d9346`, `0bdf064` (CAP-01C) · `a5693ae`, `de3169a` (IC-010). All docs/contracts-only.
