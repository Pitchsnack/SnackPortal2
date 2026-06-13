# CONSTRAINTS

**Handover H7 — every active architectural constraint as of `de3169a` (2026-06-13)**
Non-negotiable. Any change requires a governance amendment FIRST (register entry → contract → code). **Constraint #1 is the single most important requirement of SnackPortal2.**

## Database

- **The Physical Multi-Database MVP is mandatory.** One Control Database + one physically separate PostgreSQL database per tenant.
- **Control DB is separate from Tenant DBs** — physically, always. One request resolves to the Control DB **or** exactly one tenant DB, never both.
- **No shared database.**
- **No shared schema** — no table/schema/store spans tenants; lineage/provenance graphs never cross tenants.
- **No `tenant_id` isolation architecture** — `tenant_id` exists only in governed non-isolation roles (registry key, claim identifier, pool key, audit reference); never row-filtering over a shared store.

## Gateway

- **The gateway never selects a database** — it builds the `RequestContext` exclusively from `AuthContext` and dispatches endpoints; the **Database Router** resolves the one physical DB from the signed claim.
- **The gateway never authenticates as a separate authority** — it consumes IC-005 outputs; authentication is input, not routing logic.
- **The Database Router never authenticates** — authentication is complete before the router is reached.
- **The Authentication Router never routes** a database — it establishes the signed tenant context only.
- Recognized tenant carriers are **exactly** the tenant subdomain and `X-Tenant-Id`, under match-or-reject (403 `carrier_mismatch`). Cookies, query strings, portal/workspace state, and local storage are **prohibited as routing authority** and stripped at the gateway.

## Portals

- **A portal is presentation only** — it displays, discovers, and initiates.
- **A portal never routes** — it never determines database, tenant, or routing.
- **A portal never selects a database** and never holds a database connection (no direct DB, no Supabase data access of any kind).
- **A portal never authenticates** as an authority — it consumes authenticated principals; the platform stays stateless JWT.
- Portals never synchronize (no automatic/scheduled/background/event/timer re-import); imports are discrete, user-initiated, one tenant copy at a time.

## Isolation, ownership, records, audit

- **One Request = One Active Tenant = One Database.** No request spans tenants or databases; no cross-tenant query, ever.
- **Ownership ≠ Authorization ≠ Routing ≠ Residency.** Ownership is reference-only (`owner_agent_ref`, nullable `owner_ai_agent_ref` — NULL until IC-006); it never grants permission, moves a record, or routes.
- **Global Record ≠ Tenant Record.** Import is a one-directional copy, never sync; no write-back; copies diverge independently.
- **Lineage is tenant-resident and append-only — absolutely.** The Control DB holds no tenant lineage.
- **Audit is reference-only platform-wide** — actor/user/tenant/ownership/record references only; never names, emails, PII, payloads, or tenant business content (D-34-R2 §7 Global Audit Representation Rule).
- **No tenant-owned data resides in the Control Database;** no global directory record resides in a tenant database (D-31, extended by D-35). Global directory records are **tenant-anonymous**.

## Portability & vendor

- **Cloud-portable standard PostgreSQL only** (AWS RDS / Azure Database for PostgreSQL / Google Cloud SQL / self-hosted, interchangeably).
- **No Supabase business logic** (no RLS-as-authorization, no data SDK/PostgREST), **no Lovable runtime dependence**; vendor SDKs only inside sanctioned adapter zones; CI ban-lists enforced.
- **Infrastructure independent of application code** — deployable on its own across clouds and self-hosted.

## Process

- **Register entry → contract → code**, always. No implementation without an authorizing execution PRD. Review/verification PRDs are documentation-only. Authorization does not carry between PRDs. **No approved ADR may be silently replaced.**
