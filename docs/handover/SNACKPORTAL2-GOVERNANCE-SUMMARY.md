# SNACKPORTAL2-GOVERNANCE-SUMMARY

**Handover File F — ADRs, contracts, reviews, verification (as of `ab8a925`, 2026-06-12)**
Authoritative register: `docs/Architecture-Decision-Register.md` (D-01..D-37). Implementation driver for pending amendments: **Contract Amendment Inventory R2**.

## ADR Status (the architecture-defining set)

| ADR | Decision | Status |
|---|---|---|
| D-30 | Cross-tenant isolation: defense-in-depth; no cross-tenant joins ever | ✅ Approved (2026-06-05) |
| D-31 | Global Directory Residency: Startup+Investor directories in Control DB; residency absolute | ✅ Approved · **extended by D-35** (Deal Directory, identical terms) |
| D-32 | Role hierarchy: CONTROL, MASTER_AGENT, TENANT_ADMIN/AGENT, STARTUP/INVESTOR_USER; one-tenant-per-request for all | ✅ Approved |
| D-33 | **Workspace = UI representation of the signed tenant context**; switch = new scoped token; carriers match-or-reject; cookies/query-strings stripped | ✅ Approved (2026-06-12) · errata **D-33-E1** (anomaly audit → mandatory amendment content; MembershipsForPrincipal → IC-002 owner) |
| D-34 | **Operational audit = Control DB; lineage = tenant DB**; reference-only audit representation rule (platform-wide); **user-controlled re-import — amends D-20 in part** | ✅ Approved · errata **D-34-E1** (publication audit = Not Implemented) |
| D-35 | **Global Deal Directory in Control DB** (extends D-31); Publication Boundary + **Tenant Anonymity Rule**; tenant→global publication prohibited pending governance | ✅ Approved |
| D-36 | **Ownership**: one human owner per tenant entity + reserved nullable AI-owner ref (NULL until IC-006); reference-only; ownership ≠ authorization/visibility/residency; ownership domain rule; **audit follows record residency**; reserves IC-008 | ✅ Approved |
| D-37 | **Portals = presentation-layer contracts**; gateway-only data access; no portal-side Supabase/DB access; Portal Import Rule; own-kind directory discovery; Master-Agent cross-tenant capabilities Reserved-pending-IC-007; reserves IC-009 | ✅ Approved |
| D-20 | Import idempotency (upsert default) | ✅ Resolved · **amended in part by D-34** (default overwrite-on-re-import superseded; as-built upsert conformant until the IC-003 amendment lands) |

(D-01..D-29 + JWT lifecycle: all Resolved 2026-06-05 — foundational/frozen-MVP set; see the register.)

## Contract Status

| Contract | Status |
|---|---|
| IC-001 Global Startup | Final · **amendment pending** (Deal Directory, anonymity rule, audit home incl. directory-mutation audit, retention) |
| IC-002 Tenant Startup | Final · **amendment pending** (workspace alias, MembershipsForPrincipal, audit-section extension) |
| IC-003 Import | Final · **amendment pending** (Global record ∨ Deal; user-controlled re-import refining D-20; merge constraints; deal natural keys) |
| IC-004 Lineage | Final · no change (one actor-example harmonization rides the IC-003 amendment) |
| IC-005 Authentication Routing | Final · **amendment pending** (Workspace Terminology; carrier enumeration; mandatory tenantless-CONTROL anomaly audit) |
| IC-006 AI Gateway | Draft — post-MVP (D-02); everything TBD |
| IC-007 Deal Collaboration & Cross-Tenant Sharing | Deferred placeholder — no design; prohibition in force |
| **IC-008 Ownership** | **Reserved** placeholder (D-36) |
| **IC-009 Portal Contracts** | **Reserved** placeholder (D-37) |
| **IC-010 API Gateway Contract** | **Reserved** placeholder — *is* the "API Gateway contract" required by D-37/IC-009; inputs = the IC-005/IC-002 amendments |

**Until the pending amendments land, current contract text remains authoritative for implementation** (register closing note).

## Verification History

| Date | Review | Result |
|---|---|---|
| 2026-06-05..06-10 | PRD-P1..P6 Rn/En/Vn cycles | All phases PMO-accepted; PRD-P6-V1 PASS w/ observations (live PG 16.14) |
| 2026-06-11 | Post-reset re-verification + live-PG re-run (PG 17.10, 64-bit Python) | All green; N8 substantively closed |
| 2026-06-11 | PRD-P6-V1-E1 CI remediation (`0c2133a`) | Gates green except deliberate mypy 45-inventory; real CI confirmed |
| 2026-06-12 | PRD 1A-R2 alignment & deployment verification | Backend 88% / Contracts 80% / Deployment 25% / Frontend 5% |
| 2026-06-12 | PRD-D33-D37-R1 independent review (pre-approval, 5 agents) | 86/100 — GO WITH AMENDMENTS (all applied) |
| 2026-06-12 | **PRD-D33-D37-V2** (post-registration, 4 agents) | **92/100 PASS** — GO WITH AMENDMENTS (MAJ-1/MAJ-2 → Phase 2A) |
| 2026-06-12 | Phase 1 + 2A governance remediation (`20368cf`, `ab8a925`) | All ACs pass |
| 2026-06-12 | **PRD-SP2-SESSION-R1** (end-of-session, 3 agents) | **95/100 PASS — GO** |

## Drift Assessment

**No architecture drift detected.** (PRD-SP2-SESSION-R1: Q1 YES; Q2–Q6 NO; drift classes D1–D10 all None; devolution analysis — 7 candidate paths, none traversable.)

**Deliberately Superseded Decisions (governed, citation-chained — NOT drift):** PRD 1's hybrid shared-database model, mandatory `tenant_id` columns, Supabase-first recommendation, and Lovable-owns-schema were superseded by the baseline corpus's own later decision (PRD 8A Option B → PRD 8B.0 "Physical Multi-Database from MVP") and carried into IC-001..IC-005, D-30/D-31, and D-33..D-37. The one ADR-level supersession (D-34 amending D-20's re-import default) is explicitly annotated in the register — the no-silent-supersession rule (D-34 V8) held.

**Actual Drift:** none in architecture. The only ungoverned inconsistency in the corpus is **stale front-door documentation** (CLAUDE.md "no implementation code yet"; Project-Overview.md "backend Empty"; old handover §11–§19) — a tracked docs-refresh item, architecture-neutral.

**Watch items (Minor, tracked):** physical distinctness of tenant DBs not yet platform-verified (→ D-15 execution); `DirectoryRecord.attributes` anonymity guard (→ IC-001 execution); in-memory audit sinks (→ post-amendment execution PRD); edge enforcement library-internal until the gateway (standing condition: no clients before IC-010).
