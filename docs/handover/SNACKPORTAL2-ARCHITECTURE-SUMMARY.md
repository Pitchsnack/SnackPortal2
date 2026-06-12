# SNACKPORTAL2-ARCHITECTURE-SUMMARY

**Handover File E — approved architecture (as of `ab8a925`, 2026-06-12)**
**The Physical Multi-Database MVP is mandatory.** Every diagram below shows physically separate databases — this is the architecture's defining property.

## The approved structure

```text
                         SnackPortal2 clients (future portals: web / mobile / API)
                                            │
                                            ▼
                                   ┌──────────────────┐
                                   │   API GATEWAY    │  ← sole portal-facing boundary (IC-010, reserved;
                                   └────────┬─────────┘     scaffold today — IMPLEMENTS_BEHAVIOR=False)
                                            ▼
                                   ┌──────────────────┐
                                   │  AUTHENTICATION  │  ← OIDC stateless JWT (D-05); signed tenant claim
                                   │      ROUTER      │     authoritative; carrier match-or-reject (D-06)
                                   └────────┬─────────┘
                                            ▼
                                   ┌──────────────────┐
                                   │  DATABASE ROUTER │  ← registry-authoritative; one DB bound per request;
                                   └────────┬─────────┘     per-tenant pools never reused (D-07/D-13/D-30)
                          ┌─────────────────┼──────────────────┬─────────────────┐
                          ▼                 ▼                  ▼                 ▼
                   ┌─────────────┐   ┌─────────────┐    ┌─────────────┐   ┌─────────────┐
                   │ CONTROL DB  │   │   ACME DB   │    │   ZETA DB   │   │   NOVA DB   │  … more tenant DBs
                   ├─────────────┤   ├─────────────┤    ├─────────────┤   ├─────────────┤
                   │ Tenant      │   │ ACME        │    │ ZETA        │   │ NOVA        │
                   │  Registry   │   │  Startups   │    │  Startups   │   │  Startups   │
                   │ Memberships │   │  Investors  │    │  Investors  │   │  Investors  │
                   │ Global      │   │  Deals      │    │  Deals      │   │  Deals      │
                   │  Startup/   │   │  Activity   │    │  Activity   │   │  Activity   │
                   │  Investor/  │   │  Ownership* │    │  Ownership* │   │  Ownership* │
                   │  (Deal*)    │   │  Lineage    │    │  Lineage    │   │  Lineage    │
                   │  Directories│   │  (append-   │    │  (append-   │   │  (append-   │
                   │ Operational │   │   only)     │    │   only)     │   │   only)     │
                   │  Audit      │   └─────────────┘    └─────────────┘   └─────────────┘
                   └─────────────┘      PHYSICALLY        PHYSICALLY        PHYSICALLY
                                         SEPARATE          SEPARATE          SEPARATE
                   (* = decided by D-35/D-36; implementation pending IC amendments / IC-008)
```

**One request → one active tenant → exactly one database.** The Control DB and every tenant DB are separate physical PostgreSQL databases; no query ever spans them; no table is shared.

## Components and interactions

| Component | Role | Status |
|---|---|---|
| **Control DB** | Control plane (tenant registry — 7-state lifecycle incl. Provisioning; memberships/roles; routing views with credentials **by reference only**, D-14) + **Global Discovery Platform** (Global Startup/Investor Directories; Deal Directory decided by D-35, pending IC-001 amendment) + operational audit (reference-only) | Schema/code built; no deployed instance yet |
| **Tenant DBs** | All tenant business data: startups, investors, deals, activity, tenant-resident audit classes, ownership references (pending IC-008), and **append-only hash-chained lineage** (DB-trigger + privilege + crypto enforced, live-PG verified) | Lineage/import DDL built (portable PG 11+); product schema pending |
| **API Gateway** | Sole portal-facing boundary; will construct the router's RequestContext **exclusively** from the Authenticator's output, enforce carrier rules at the edge, strip workspace cookies/query-strings | Scaffold (by design); contract = IC-010 (reserved); acceptance criteria already adopted (D-33 crit 4–6, D-37 V1–V3) |
| **Authentication Router** | DB-free OIDC stateless JWT validation; tenant context from the **signed claim only**; carrier mismatch → 403 + audit; tenant/workspace switch = new scoped token (D-33) | Built + verified |
| **Database Router** | Resolves tenant → physical DB from the Control-DB registry (cached, invalidated on re-association); readiness + schema gating; binds exactly one connection per request; re-checks connection↔tenant binding (IsolationAnomaly) | Built + verified; **the only service permitted tenant-DB access** |
| **Import Service** | One-directional Global→tenant **import-copy** (never sync): validates/sanitizes, writes the tenant copy + lineage + checkpoint **in one tenant transaction**; idempotent (D-20, as amended in part by D-34 → user-controlled re-import pending IC-003 amendment) | Built + verified |
| **Lineage Service** | Tenant-resident provenance: per-tenant keyed hash-chain, append-only absolute, segmented retention (D-24; values pending D-08), provenance graph never crosses tenants | Built + verified (live PG 17.10) |

**Interaction rules:** services are mutually independent (import-linter-enforced DAG; `shared` is a stdlib-only leaf); cross-service calls go through transport ports (HTTP read APIs), never in-process imports; DB drivers only inside two sanctioned provider zones; vendor SDKs ban-listed (incl. `supabase`, `lovable`). Discovery reads (any authorized workspace, per role) hit the Control DB through the control-plane read path — they never enter a tenant data path; imports are the only bridge from Global records to tenant copies.

## What does not exist on purpose

Portals/frontend (blocked until IC-009 + IC-010), gateway behavior, ownership fields (IC-008), Deal Directory implementation (IC-001/IC-003 amendments), AI anything (IC-006 Draft; AI-ready hooks only), cross-tenant sharing (IC-007 Deferred). Absence is the contracted state — building any of these without its contract is a violation, not progress.
