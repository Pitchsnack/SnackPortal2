# ARCHITECTURE-SUMMARY

**Handover H4 — approved architecture as of `de3169a` (2026-06-13)**
**The Physical Multi-Database MVP is mandatory.** Every structure below shows physically separate databases — the architecture's defining property.

## Core Architecture

```text
            clients / future portals (web · mobile · desktop · public API)
                                   │   (channel-agnostic; bind to identical contracts — D-37 §6)
                                   ▼
                        ┌────────────────────┐
                        │     API GATEWAY     │  ← sole approved ingress (IC-010, Final; scaffold today,
                        └─────────┬──────────┘     IMPLEMENTS_BEHAVIOR=False). Authenticates, validates
                                  ▼                 carriers, builds RequestContext exclusively from
                        ┌────────────────────┐      AuthContext, dispatches endpoints, emits audit.
                        │ AUTHENTICATION ROUTER│  ← OIDC stateless JWT (D-05); signed tenant claim
                        └─────────┬──────────┘      authoritative; carrier match-or-reject (D-06).
                                  ▼                  Never routes a database.
                        ┌────────────────────┐
                        │   DATABASE ROUTER   │  ← resolves exactly one physical DB from the signed
                        └─────────┬──────────┘      claim (registry-authoritative, D-07); never
              ┌───────────────────┼─────────────────┐   authenticates; "never re-derived".
              ▼                   ▼                 ▼
       ┌────────────┐     ┌────────────┐    ┌────────────┐
       │ CONTROL DB │     │  ACME DB   │    │  ZETA DB   │ … one physically separate DB per tenant
       ├────────────┤     ├────────────┤    ├────────────┤
       │ Registry   │     │ Startups   │    │ Startups   │
       │ Memberships│     │ Investors  │    │ Investors  │
       │ Global     │     │ Deals      │    │ Deals      │
       │  Startup/  │     │ Activity   │    │ Activity   │
       │  Investor/ │     │ Ownership* │    │ Ownership* │
       │  Deal Dirs │     │ Lineage    │    │ Lineage    │
       │ Operational│     │ (append-   │    │ (append-   │
       │  Audit     │     │  only)     │    │  only)     │
       └────────────┘     └────────────┘    └────────────┘
                            PHYSICALLY        PHYSICALLY
                             SEPARATE          SEPARATE
       (* ownership references decided by D-36/IC-008; fields land at a future execution PRD)
```

**One request → one active tenant → exactly one database** (Control DB **or** one tenant DB, never both). No query spans databases; no table is shared.

## Components

| Component | Role | Status |
|---|---|---|
| **Control DB** | Control plane (registry — 7-state lifecycle; memberships/roles; routing views, credentials by reference D-14) + **Global Discovery Platform** (Startup/Investor/**Deal** directories — D-31 extended by D-35) + reference-only operational audit | Schema/code built; no deployed instance |
| **Tenant DBs** | All tenant business data + tenant-resident audit classes + ownership references (pending IC-008 execution) + **append-only hash-chained lineage** (trigger + privilege + crypto enforced, live-PG verified) | Lineage/import DDL built; product schema pending |
| **Registry** | Authoritative tenant→physical-DB mapping (D-07); cached, invalidated on re-association; credentials by reference only | Built |
| **Authentication Router** | DB-free OIDC stateless JWT; tenant context from the signed claim only; carrier mismatch → 403 + audit; tenant/workspace switch = new scoped token | Built + verified |
| **Database Router** | Resolves tenant → one physical DB from the registry; readiness + schema gating; binds one connection per request; re-checks binding (IsolationAnomaly); **only service permitted tenant-DB access** | Built + verified |
| **API Gateway** | Sole portal-facing boundary; constructs RequestContext exclusively from AuthContext; enforces carrier rules; strips workspace cookies/query-strings; dispatches endpoints (never resolves databases) | **Contract Final (IC-010); behavior is scaffold by design** |
| **Import Service** | One-directional Global→tenant import-copy (never sync); atomic provenance; user-controlled re-import per IC-003 (as-built upsert is a tracked remediation item) | Built + verified |
| **Lineage Service** | Tenant-resident per-tenant hash-chain; append-only absolute; never crosses tenants | Built + verified (live PG 17.10) |

**Interaction rules:** services are mutually independent (import-linter-enforced service independence; `shared` is a stdlib-only leaf); cross-service calls go through internal transport ports (HTTP read APIs), never in-process imports, and are **internal-only / never client-reachable** (IC-010); DB drivers only inside sanctioned provider zones; vendor SDKs ban-listed (incl. `supabase`, `lovable`). Discovery reads hit the Control DB through the control-plane read path; imports are the only bridge from Global records to tenant copies.

## Mandatory Invariants

| Invariant | Meaning |
|---|---|
| **Authentication ≠ Routing** | Authentication establishes *who* + *which tenant claim*; the Database Router resolves the DB *from the signed claim*. A valid token never by itself selects a database. |
| **Workspace ≠ Routing** | Workspace is the UI representation of the signed tenant context — never a routing input, database selector, cookie, query-string, or claim of its own. Derived from the claim, never the reverse. |
| **Ownership ≠ Authorization** | Ownership is an accountability designation (reference-only); it never grants permissions, access, or capabilities. |
| **Ownership ≠ Residency** | Ownership never moves a record or changes the Control/tenant boundary; it never routes. |
| **Global Record ≠ Tenant Record** | Import is a discrete one-directional copy, never sync; copies diverge independently; no write-back. |
| **One Request → One Database** | Exactly one active tenant → exactly one database per request; no spanning, no cross-tenant query. |
| **Physical Multi-Database MVP** | One Control DB + one physically separate PostgreSQL database per tenant. Never a shared database, shared schema, or `tenant_id` row-filtering as isolation. **The defining, non-negotiable property.** |

Also binding: lineage is tenant-resident and append-only (absolutely); audit is reference-only platform-wide (actor/user/tenant/ownership/record refs — never names, emails, PII, or payloads); portals access data only through the API Gateway; cloud-portable standard PostgreSQL only.
