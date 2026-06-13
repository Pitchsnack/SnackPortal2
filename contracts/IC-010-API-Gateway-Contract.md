# IC-010 — API Gateway Contract

**Status:** Final · **Phase:** Architecture Planning · **Type:** Specification only (no implementation)
**Authored:** 2026-06-13 under **PRD-IC010-01-R1** (APPROVED FOR EXECUTION), converting the **Reserved placeholder** (reserved 2026-06-12 under PRD-D33-D37-V2-R1 Work Package D, resolving PRD-D33-D37-V2 **MAJ-2**) into a Final governing contract. Authority: **D-37 §5/§17/§22** — IC-010 *is* the "API Gateway contract" required as a hard prerequisite for portal implementation.
**Status note:** This contract defines the gateway **contract** — its boundaries, responsibilities, request flow, and prohibitions. It authorizes **no implementation**: the `api_gateway` package remains a scaffold (`IMPLEMENTS_BEHAVIOR = False`, architecture-test-enforced) until a separate, explicitly-authorizing execution PRD. It contracts the **edge enforcement** of the tenant-context guarantees that are library-internal today (the PRD 1A-R2 Critical-risk item); enforcement becomes real only when the gateway is built.
Requirement keywords **MUST / MUST NOT / SHOULD / MAY** are used in the RFC-2119 sense.

## Identification (traceability — resolves MAJ-2)
**IC-010 *is* the "API Gateway contract"** referenced as a hard prerequisite for portal implementation by: **D-37 §17 and §22** ("until IC-009, the API Gateway contract, and the amendment package exist"), the **IC-009** placeholder's Boundary ("until IC-009 is designed and approved and the API Gateway contract exists"), and the Architecture Decision Register's D-37 entry and closing note. All such references resolve here. This Identification block and the reservation lineage below are **preserved from the placeholder** per PRD-IC010-01-R1 §V.

**Reservation history.** Reserved 2026-06-12 (PRD-D33-D37-V2-R1 WP-D, MAJ-2) → Final 2026-06-13 (PRD-IC010-01-R1). The MAJ-2 traceability chain (the "API Gateway contract" dependency had no contractual vehicle until this number was reserved, then authored) is retained for audit continuity.

## Purpose (§A)
Define the **API Gateway** as the **sole approved ingress** into SnackPortal2 services. The gateway is the single portal-facing integration boundary (D-37 §5) at which client requests are authenticated, carrier-validated, given a tenant context, and turned into a canonical `RequestContext` that the Database Router consumes — `HTTP Request → Authentication → Tenant Context → RequestContext → Database Router → exactly one database`. The gateway is an **enforcement boundary, not a decision-maker**: it never selects a database, never decides ownership, never makes portal or business decisions.

## Gateway Responsibilities (§B)
The gateway **MAY**: authenticate (consume IC-005 outputs); validate carriers (IC-005 match-or-reject); resolve the tenant context from the **signed claim** (D-06/D-33); construct the canonical `RequestContext`; **dispatch** requests to the correct service/endpoint (see *Endpoint Dispatch vs Database Resolution*); and emit audit events (D-33/D-34, reference-only).

The gateway **MUST NOT**: select a database based on user preference, header, cookie, query-string, workspace, or any client-controlled value; perform ownership decisions (IC-008: ownership is reference-only and never routes/authorizes); perform portal decisions (D-37: portals are presentation-layer; the gateway does not embed portal logic); or perform business logic of any kind. Authority for authentication, routing, residency, ownership, and authorization remains in the dedicated components, never in the gateway's discretion.

## Request Flow Contract (§C)
The single approved per-request flow is:

```
Request → Authentication → Carrier Validation → Tenant Context Validation → RequestContext Creation → Database Router → Service → Response
```

**No alternate flow is permitted.** Every client request traverses these stages in order; no stage may be skipped, reordered, or bypassed, and no path may reach a service or a database except through this flow.

## Endpoint Dispatch vs Database Resolution (§X — route-terminology clarification)
"Route" is split into two **distinct, non-overlapping** responsibilities so the word can never become a client-controlled routing channel:
- **Endpoint dispatch (gateway).** The gateway dispatches an authenticated request to the correct **service/endpoint** by request path/operation. This is application-level dispatch; it consumes **no** tenant/workspace/ownership value as a selector.
- **Database resolution (Database Router only).** Resolving the request to **exactly one physical database** from the **signed tenant claim** is the **exclusive** responsibility of the Database Router (IC-005/D-07; `router.py` "the single active tenant is taken from the signed claim … never re-derived").

**The gateway MAY dispatch endpoints; the gateway MUST NOT resolve databases.** Database resolution remains exclusively the Database Router's responsibility. The gateway never chooses a database; the Database Router never authenticates.

## Authentication Boundary (§D)
Authentication is governed by **IC-005** (OIDC stateless JWT, D-05; signed tenant claim authoritative, D-06). The gateway treats authentication as **input**, never as routing logic. **Authentication does not select the database**: it establishes *who* the principal is and *which tenant claim* the token carries; the database is then resolved by the Database Router from that signed claim. A valid token never, by itself, selects or changes the target database.

## Carrier Contract (§E)
Per the amended **IC-005** (*Workspace Terminology & Carriers*), the gateway recognizes **exactly two** tenant carriers, both subordinate to the signed claim under match-or-reject:
- the **tenant subdomain** (host-based addressing); and
- the HTTP header **`X-Tenant-Id`** — the **only** recognized carrier header (case-insensitive). All other headers are unrecognized as tenant carriers and MUST be ignored.

The gateway MUST pass any recognized carrier into the IC-005 carrier-match check and reject mismatches (**403 `carrier_mismatch`**). **Prohibited as routing authority** — MUST be stripped/ignored at the gateway and never read by any backend component for any purpose (including token issuance): **cookies, query-string parameters, portal state, workspace state, and client local storage.** None of these may carry tenant or workspace identity.

## Tenant Context Contract (§F)
Per **D-33**, the gateway creates the `RequestContext` (see next section) carrying the principal, role, tenant context, and workspace type. **Workspace is derived from the tenant context; the tenant context is never derived from workspace.** The workspace_type (Tenant Workspace vs Control Workspace) is a presentation-layer label computed *from* the signed claim — it is never a routing input, a database selector, or an authority of its own (IC-005 *Workspace Terminology & Carriers*). For a tenantless CONTROL token accompanied by a recognized tenant carrier, the carrier is ignored (claim-only) **and** the gateway MUST emit the `CarrierOnControlAnomaly` audit event (D-33-E1 Item 1; *Audit Contract*).

## Request Context Contract (§G + §T)
The gateway defines the **canonical `RequestContext`** — the single structure the Database Router, audit, authorization, and service invocation consume **without any additional tenant resolution**. The router never re-derives the tenant; it binds exactly one database from the context's tenant claim.

**Canonical fields:** `correlation_id`, `principal_ref`, `role`, `tenant_context` (the signed active-tenant claim, or *tenantless-CONTROL* for the Control Workspace), `workspace_type`.

**Required rules:**
- **References only.** The `RequestContext` carries **references only** — it MUST NOT contain names, emails, or any PII/identity payload (consistent with the D-34-R2 §7 reference-only discipline). Identity is resolved at presentation time via the D-03 identity model, never carried in the context.
- **Constructed exclusively from `AuthContext`.** The gateway MUST construct the `RequestContext` **exclusively** from the Authenticator's output (`AuthContext`) — the D-33 §4.6 keystone. **No inbound tenant/workspace parameter** (header beyond the carrier-match check, cookie, query-string, portal/workspace/local-storage state) may reach the router. The only permitted use of a recognized carrier is feeding it into the IC-005 carrier-match check, which rejects on mismatch.

## Endpoint Dispatch Taxonomy (§Q)
The gateway dispatches client requests into these categories (operations and semantics only; concrete bindings are implementation details for the future execution PRD):
- **Tenant Operations** — tenant-scoped business operations under exactly one active tenant context (IC-002/IC-005), resolved by the Database Router to that tenant's database.
- **Global Directory Reads** — authenticated, audited **control-plane reads** of the Global Startup/Investor/Deal Directories (IC-005/D-31, D-35), available to authorized principals from their own workspace context per role (D-33); these are control-plane reads, never a tenant data path, and never expose tenant-owned records.
- **MembershipsForPrincipal** — the IC-002 workspace-selector read: **self-scoped or CONTROL**, audited, returning **membership records only** (tenant id, role, display ref), never tenant-DB data.
- **Import Initiation** — initiating an IC-003 import into the active tenant.

**One request → one category → one database.** A single request is dispatched to **exactly one** category and resolves (via the Database Router) to **exactly one** database. No category, and **no combination of categories**, may straddle the Control DB and a tenant DB, or span two tenant DBs, within one request (*Isolation Contract*). A Global Directory Read (Control DB) and a Tenant Operation (tenant DB) are therefore distinct requests, never a single straddling one.

**Import Rule.** Import initiation MUST follow the **D-37 §9 Portal Import Rule** and **IC-003**: discrete, **explicitly user-initiated** operations within the active tenant context only. The gateway MUST NOT introduce synchronization, automatic/scheduled/background/event-triggered/timer-driven re-import, shared ownership, or cross-database updates — regardless of how individually lawful each underlying call would be (D-34-R2 §8; IC-003 *Re-Import Governance*).

## Database Router Boundary (§H)
`Gateway → Database Router` is the **only approved routing boundary**. **Required rules:**
- **The gateway never chooses a database.** It hands the `RequestContext` to the Database Router, which resolves exactly one physical database registry-authoritatively from the signed claim (D-07/D-30).
- **The Database Router never authenticates.** Authentication is complete before the router is reached; the router consumes the already-authenticated context only.

No component between or around the gateway and router may introduce an alternative database-selection path.

## Internal-Surface Protection (§R)
The gateway MUST explicitly distinguish **client-reachable** surfaces from **internal-only** surfaces:
- **Internal read APIs MUST NEVER be directly client-reachable.** The internal control-plane read API and internal service transport ports MUST NOT be exposed to portal/client network zones; they sit behind the gateway boundary.
- **Gateway-fronted directory reads** (the Global Directory Reads dispatch category) MUST add **IC-005 authentication** plus a **reference-only access audit** (D-34-R2 §7) at the edge. A directory read that reaches the control plane through the gateway is authenticated and audited; the internal read path is never offered raw to a client.

*(This protects client ingress without forbidding the already-built internal service-to-service transport DAG — see *Service Contract*.)*

## Portal Boundary (§I)
Per **D-37**, the six portal classes — **Control · Master Agent · Tenant · Startup · Investor · AI (Reserved)** — and any future channel MUST access backend services **only through the API Gateway** (D-37 §5, the sole portal-facing integration boundary). **Explicitly prohibited:** direct database access (Control DB or any tenant DB), direct Supabase data access of any kind (RLS-as-authorization, PostgREST, Supabase data SDKs — D-37 §5), portal-side routing, and portal-side synchronization (D-37 §9). Portals **display, discover, and initiate**; they never determine database, tenant, authentication, authorization, ownership, routing, or residency (D-37 §3). The **Master Agent Portal's** cross-tenant capabilities remain **IC-007-reserved** — the gateway grants no cross-tenant authority (D-37 §7.2, §18; see *IC-006 / IC-007 Deferrals*).

## Audit Contract (§J)
Per **D-33** and **D-34-R2**, the gateway emits these audit events **where applicable**: `CarrierMismatch` (403 carrier/claim mismatch), `CarrierOnControlAnomaly` (recognized tenant carrier on a tenantless CONTROL token — mandatory per D-33-E1 Item 1), `RouteDenied` (authorization/readiness denial at dispatch), and `IsolationAnomaly` (any detected attempt to cross the one-database boundary). The gateway is the **emitter** of these events; the contractual **class home** for the runtime/operational-audit classes (`RouteDenied`, `CarrierMismatch`, `CarrierOnControlAnomaly`, `IsolationAnomaly`) is the **IC-005 / IC-002 audit extension** (D-34-R2 §6 — pending per Contract Amendment Inventory R2), while the reference-only **representation** rule is already contract law at **IC-001**. All gateway audit records MUST follow the **Global Audit Representation Rule** (D-34-R2 §7, contract law at IC-001): **references only** — `actor_ref`, `user_ref`, `tenant_ref`, `ownership_ref`, `record_ref` plus action/outcome/timestamp/correlation metadata — never names, emails, PII, payloads, or tenant business content.

## Isolation Contract (§K)
The gateway MUST enforce **One Request = One Active Tenant = One Database**. **Required rule:** **no request may access multiple tenant databases.** A single request resolves to the Control DB **or** exactly one tenant DB — never both, never several. **Cross-tenant operations are prohibited** (any cross-tenant capability is IC-007-deferred; *IC-006 / IC-007 Deferrals*). Any detected breach attempt is rejected and audited (`IsolationAnomaly`).

## Error Handling Contract (§L)
The gateway MUST be **fail-closed**: the following conditions all yield **Request Rejected** (no fallback, no default tenant, no partial access):
- **Invalid carrier** / **Missing carrier** (where a carrier is required) / **Carrier mismatch** → 403 `carrier_mismatch`;
- **Invalid tenant context** (unresolvable or inconsistent claim) → reject;
- **Unauthorized principal** (not a member of the claimed tenant) → 403;
- **Unknown tenant** → consistent-denial *not found* semantic (IC-002), never leaking another tenant's existence.

Denial semantics follow IC-005 (401 unauthenticated / 403 forbidden) and IC-002 readiness (*not found* / *not ready* / *administratively disabled* / *unavailable*). No error path may downgrade to a less-isolated outcome.

## Service Contract (§M)
All backend services — **Auth Router, Database Router, Import Service, Lineage Service, and future services** — MUST be reachable **only through the API Gateway** for **client/portal ingress**, *unless explicitly governed otherwise*. The **"explicitly governed otherwise"** clause covers the already-built **internal service-to-service transport**: services call one another over sanctioned internal transport ports (HTTP read APIs) under static cross-service import constraints that enforce **service independence** (import-linter). Per *Internal-Surface Protection*, these internal surfaces are **internal-only** and **MUST NEVER be directly client-reachable** — they sit behind the gateway boundary and are **not a portal ingress path**. The gateway governs the **client edge**; it does not forbid the internal transport graph, and that graph never offers a client or portal a way around the gateway.

## Readiness Disclosure Contract (§S)
Per **IC-001 / D-10**, the gateway's readiness/liveness disclosure MUST be **minimally disclosing**. The **degraded** state may expose **operational status only** (degraded is observability/alerting-only and MUST NOT deny routing to healthy tenants, D-16). **Prohibited in any readiness/health response:** database names, tenant-database details, tenant counts or identities, and infrastructure topology. Readiness endpoints are access-controlled (IC-001).

## Future Channels Rule (§N)
Per the **D-37 §6 Channel Rule**, all client channels — **web, mobile, desktop, public API** — bind to the **same** gateway rules identically: gateway-only ingress, the carrier contract, residency, isolation, and audit. No channel may bypass these rules; channel-specific routing or data paths are prohibited. (New *portal classes* still require new ADRs + IC-009 amendments — D-37 §6 Future Portal Expansion; this rule binds *channels*, not new portal classes.)

## IC-006 / IC-007 Deferrals (§U)
- **AI routing, AI ownership, and AI operations** remain governed by **IC-006** (AI Gateway, Draft, post-MVP, D-02) and are **not authorized** by this contract. The gateway exposes no AI behavior; the D-36 `owner_ai_agent_ref` slot stays NULL until IC-006 (IC-008).
- **Cross-tenant operations and Master-Agent cross-tenant workflows** remain governed by **IC-007** (Deal Collaboration & Cross-Tenant Sharing, deferred) and are **not authorized** by this contract. No gateway path provides cross-tenant access, sharing, introductions, or collaboration; the Master Agent Portal's such capabilities are IC-007-reserved (D-37 §7.2).

## Physical Multi-Database Rule (§O)
The **Control Database** and the **Tenant Databases** remain **physically separate** PostgreSQL databases. The gateway MUST NOT introduce — directly or by enabling any client/portal/workspace/ownership path — a **shared database**, a **shared schema**, or a **`tenant_id` isolation** architecture. One request resolves to the Control DB **or** exactly one tenant DB; no gateway behavior may blur that boundary. The Physical Multi-Database MVP is mandatory and is reinforced (never weakened) by this contract.

## Distinctness Verification Hook (§P — reserve support for D-15)
This contract **reserves support** for the D-15 Provisioning Plan's future verification that tenant databases are physically distinct: future provisioning verification **may require** **database-identity validation**, **physical-distinctness validation**, and **isolation verification** between the Control Database and the tenant databases (e.g., comparing PostgreSQL system identifiers; raising an `IsolationAnomaly` on collision). This contract **records the hook without defining implementation** — the mechanics belong to the D-15 execution PRD.

## Acceptance Criteria (adopted — for the future API Gateway execution PRD) (§W)
When the gateway is **built** (a separate, later execution PRD — none authorized here), it MUST satisfy the acceptance criteria **already adopted** for IC-010:
- **D-33 §10 criteria 4–6:** (4) an authenticated request with a mismatched subdomain/header is rejected end-to-end through the gateway; (5) a workspace switch issues a new scoped token and emits the audit event, and the old context cannot be reused to reach the new workspace's data; (6) an architecture test that the gateway constructs `RequestContext` only from `AuthContext` — no inbound tenant/workspace parameter reaches the router.
- **D-37 §20 V1–V3:** (V1) the portal/gateway never determines database routing; (V2) never determines tenant routing; (V3) data is accessed only through the API Gateway — **verified by a frontend-repository audit: no database client, no Supabase data SDK, no PostgREST usage.**
- The **Frontend Repository Audit** (D-37 §20 V3 / V13) is **reserved** as a future gateway-validation requirement.

These are **acceptance criteria for the future implementation**, not obligations this contract implements (contracts precede code).

## Multi-Database Compatibility
The gateway resolves (via the Database Router) to the Control Database **or** exactly one tenant database — never both, never spanning tenants. It introduces no provider-specific feature and runs against standard PostgreSQL backends (AWS RDS / Azure / Google Cloud SQL / self-hosted). Routing metadata and the registry remain control-plane concerns (D-07); the gateway carries none of it as client-controlled state.

## Anti-Vendor-Lock-In Requirements
- **No Supabase** gateway logic, no Supabase Auth, no Supabase data SDK/PostgREST/RLS-as-authorization at the edge or behind it (D-37 §5).
- **No Lovable** or other frontend-platform runtime dependency in the gateway boundary.
- Authentication is OIDC via IC-005 with any self-hostable, swappable IdP; the only legitimate non-gateway traffic is vendor-neutral OIDC token issuance at the IdP (D-37 §5).
- The gateway, request context, and audit are portable, standard-PostgreSQL-compatible, and provider-neutral.

## Resolved Decisions / Dependencies (traceability)
- **D-37** (R3) — portals are presentation-layer contracts; the API Gateway is the sole portal-facing boundary (§5); Portal Import Rule (§9); Channel Rule (§6); six portal classes (§6/§7); V1–V3 acceptance criteria (§20) (*Portal Boundary*, *Endpoint Dispatch Taxonomy*, *Future Channels Rule*, *Acceptance Criteria*).
- **D-33** (+ **D-33-E1**) — workspace = UI representation of the signed tenant context; carrier enumeration; mandatory `CarrierOnControlAnomaly`; §4.6 edge wiring (RequestContext exclusively from AuthContext); §10 criteria 4–6 (*Carrier Contract*, *Tenant/Request Context Contracts*, *Acceptance Criteria*).
- **IC-005** (amended) — authentication routing; recognized carriers; match-or-reject; the gateway consumes its outputs (*Authentication Boundary*, *Carrier Contract*).
- **IC-002** (amended) — `MembershipsForPrincipal` (self-or-CONTROL, references only) (*Endpoint Dispatch Taxonomy*).
- **IC-001** — Global Discovery Platform residency (D-31, extended by D-35); operational-audit homes + Global Audit Representation Rule; readiness disclosure (D-10) (*Endpoint Dispatch Taxonomy*, *Audit Contract*, *Readiness Disclosure Contract*).
- **IC-003** — import-copy + user-controlled re-import; the Portal Import Rule restated (*Endpoint Dispatch Taxonomy*).
- **IC-008** — ownership is reference-only and never routes/authorizes (*Gateway Responsibilities*, *IC-006 / IC-007 Deferrals*).
- **IC-009** (reserved) — **boundary respected, not depended on** (M1): the per-role × per-directory visibility matrix and portal DTO contracts remain IC-009's to author *after* IC-010; this contract bounds IC-009, never relies on its (non-existent) content.
- **D-30/D-31/D-32** — cross-tenant isolation; directory residency; role hierarchy — consumed unchanged.
- **D-15** — provisioning distinctness verification hook reserved (*Distinctness Verification Hook*).
- **IC-006 / IC-007** — AI and cross-tenant surfaces deferred (*IC-006 / IC-007 Deferrals*).

## Not implemented · Implementation prohibited
No gateway behavior is implemented by this contract. The `api_gateway` package remains a scaffold (`IMPLEMENTS_BEHAVIOR = False`, architecture-test-enforced). Implementation proceeds only under a separate, explicitly-authorizing execution PRD (register entry → contract → code), inheriting the *Acceptance Criteria* above. Per PRD-IC010-01-R1 §13, completion of IC-010 authorizes no gateway implementation, no D-15 provisioning implementation, no frontend integration, and no portal implementation.
