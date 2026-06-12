# SNACKPORTAL2-CONSTRAINTS

**Handover File D — mandatory architectural constraints (as of `ab8a925`, 2026-06-12)**
These are non-negotiable. Any change to any of them requires a governance amendment FIRST (register entry → contract → code). **Constraint 1 is the most important requirement of SnackPortal2.**

| # | Constraint | Governing sources |
|---|---|---|
| **1** | **The Physical Multi-Database MVP is mandatory.** One Control Database + one physically separate PostgreSQL database per tenant. Never a shared database. | PRD 8B Option B; IC-001/IC-002; D-30/D-31; verified P-matrix 10/10 |
| **2** | **One Request = One Database.** One request → one active tenant → exactly one database (Control DB *or* one tenant DB, never both, never several). | IC-002 invariants 1–3; D-04; `router.py` ("never re-derived") |
| **3** | **Global Record ≠ Tenant Record.** Import is a discrete one-directional copy — never synchronization, never write-back; copies diverge independently. | IC-003 invariants; D-20 (as amended in part by D-34); D-35 |
| **4** | **Ownership ≠ Authorization.** Ownership never grants permissions, visibility, or access; it never routes. Reference-only representation (`owner_agent_ref` / nullable `owner_ai_agent_ref` — NULL until IC-006). | D-36 (Principles 3–5, Representation Rule) |
| **5** | **Workspace = Signed Tenant Context.** The UI representation of the signed JWT tenant claim; switching = new scoped token (audited). Never a filter, header-authority, cookie, query-string, claim of its own, or database concept. | D-33 (+D-33-E1); IC-005/D-06 |
| **6** | **No tenant_id isolation model.** `tenant_id` exists only in governed non-isolation roles (registry key, claim identifier, pool key, audit reference) — never row-filtering over a shared store. | PRD 8B supersession of PRD 1 §6/§10; audited (318 occurrences classified, zero filtering) |
| **7** | **No shared tenant tables.** No table, schema, or store spans tenants; lineage/provenance graphs never cross tenants. | IC-002 Invariant 4; IC-004 Invariant 4; D-25 |
| **8** | **No Supabase business logic.** No Supabase RLS-as-authorization, no Supabase data SDK/PostgREST in any portal or service; no Lovable runtime dependence; vendor SDKs only inside sanctioned adapter zones. CI-enforced ban lists. | CLAUDE.md constraints; D-05; D-37 §5; architecture tests |
| **9** | **Portals access data only through the API Gateway.** No portal-side database connections of any kind; portals display/discover/initiate and never determine database, tenant, authentication, ownership, routing, or residency. | D-37 §§3–5; IC-009/IC-010 placeholders |
| **10** | **Physical database separation is the security boundary.** Defense-in-depth rides on it (claim → routing → per-tenant credentials/connections → audit), but the boundary itself is physical. Per-tenant credentials by reference only (D-14); connections never reused across tenants. | D-30; D-13/D-14; IC-002 |

## Standing operational conditions (current phase)

- **No client, frontend, or network exposure of any backend surface** until the IC-005/IC-002 amendments and the IC-010 API Gateway exist — edge enforcement is library-internal today.
- **Current contract text remains authoritative until the pending amendments land** (e.g., re-import upsert default per D-20 stays conformant until the IC-003 amendment).
- **Contracts precede code; no implementation without an authorizing execution PRD.** Review/verification PRDs are documentation-only.
- **Audit is reference-only platform-wide** (actor/user/tenant/ownership/record refs — never names, emails, PII, payloads); **lineage is tenant-resident and append-only, absolutely.**
- **No approved ADR may be silently replaced** — every supersession is explicit, cited, and registered (D-34 V8).
- Cloud-portable standard PostgreSQL only (AWS RDS / Azure / Cloud SQL / self-hosted); infrastructure independent of application code.
