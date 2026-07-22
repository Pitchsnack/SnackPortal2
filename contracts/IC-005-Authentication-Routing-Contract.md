# IC-005 — Authentication Routing Contract

**Status:** Final · **Phase:** Architecture Planning · **Type:** Specification only (no implementation)
**Status note:** All architecture decisions governing authentication and routing are resolved and recorded in [Architecture-Decision-Register.md](../docs/Architecture-Decision-Register.md) — through D-06 (tenant carriage), D-30 (isolation enforcement), the JWT lifecycle, plus the **D-32** role hierarchy and the **D-31** directory-authorization clarification. **Final** for MVP architecture; residual items are implementation/operational (exact token TTL, optional denylist enablement, DNS/cert, concrete permission sets) and do not reopen the architecture.
**Amendment (2026-06-12, PRD-CAP-01A):** added *Workspace Terminology & Carriers* implementing **D-33** as corrected by **D-33-E1** — workspace definition, exact carrier enumeration, prohibited carriers, and the mandatory carrier-on-CONTROL anomaly audit. No normative change to token validation, JWKS, roles, or denial semantics; no frozen invariant altered.
**Amendment (2026-07-17, PRD B5-BLK-6C-A):** implementing Dan's **Option A** audit-obligation reconciliation — *Runtime Operational Audit Emission* gains the **gateway-edge success-access subclass** (`workspace_memberships_read`; API Gateway sole emitter; Control-DB home, IC-002 class 3b), and the *Directory-read access audit — Reserved* rule is made explicit: it reaches directory reads only and does not shelter MembershipsForPrincipal. The four gateway-edge denial/anomaly classes and the router-edge routing-decision subclass are unchanged. No normative change to token validation, JWKS, roles, or denial semantics; no frozen invariant altered. Runtime emission remains pending **B5-BLK-6C-B**; B5-BLK-6C-A adds no runtime implementation and closes no blocker.

## Purpose
Define the contract for the **Authentication Router**: how incoming requests are authenticated, how tenant context is established, and how authenticated requests are routed to the correct tenant (or control plane) via the Database Router.

## Two-Phase Authentication Model (resolves D-01)

Authentication is **separated from tenant routing** to break the IC-001 ⇄ IC-005 bootstrap cycle. Per [D-01-Bootstrap-Cycle-Resolution.md](../docs/D-01-Bootstrap-Cycle-Resolution.md), the approved resolution is **A + B**.

- **Phase 0 — bootstrap.** Recognizes **only** the bootstrap **system identity**, verified **cryptographically/statically with no Control-DB dependency** against a trust anchor in static, infrastructure-owned configuration (resolution B; secrets referenced, never inlined). Authorized for control-plane operations only. **All tenant-scoped requests are denied**, and the system identity can **never** resolve to a tenant database.
- **Phase 1 — runtime.** The full model: end-user principals are authenticated via **OIDC with stateless JWT validation** (D-05) under the **hybrid identity model** (D-03), and requests are routed to the Control Database or exactly one tenant database — **exactly one active tenant context per request** (D-04) — using routing metadata held in the Control Database.

**Authentication vs. routing.** Authenticating a caller is a trust decision and does **not** require Control-DB-resident data. The rule that "routing metadata lives in the Control Database" applies to **Phase-1 tenant routing only** — never to authenticating the control plane.

**Transition trigger (owned by [IC-001](IC-001-Global-Startup-Contract.md)).** Phase 0 → Phase 1 occurs once the Control Database is available, schema-checked, and routing metadata is loaded. Phase 0 is closed once Phase 1 is active. Tenant routing is unavailable until Phase 1.

## Scope
- Authentication mechanism(s) and token/credential expectations.
- Establishing tenant context from an authenticated request.
- Routing decision: control plane vs. specific tenant.
- Failure/denial semantics (unauthenticated, wrong tenant, unknown tenant).
- Relationship to the API Gateway and Database Router.
- Two-phase authentication (Phase 0 bootstrap system identity / Phase 1 runtime) and the separation of authentication from tenant routing.
- Tenant routing available only after the Control Database is online (Phase 1).

## Non-goals
- Authorization policy decisions per feature (each contract states its own authz requirements).
- Tenant/global startup (see [IC-001](IC-001-Global-Startup-Contract.md), [IC-002](IC-002-Tenant-Startup-Contract.md)).
- Any implementation, middleware, or auth-server code.

## API Contract Placeholder
> Tenant context is carried as an **authoritative signed JWT claim** (D-06). Auth failures use standard semantics — **401** (unauthenticated), **403** (authenticated but not a member / carrier-claim mismatch). Concrete endpoints and shapes are **implementation bindings** (no transport code here) — **except the recognized tenant-carrier channels, which are contract-enumerated** (D-33; see *Workspace Terminology & Carriers*).

## DTO Contract Placeholder
> Shapes (fields only, no code, **no tokens or secrets**): **authenticated principal** (subject/identity reference, source = internal | federated, D-03), **tenant context** (active `tenant_id` from the signed claim, D-06), **auth error** (non-sensitive code: unauthenticated / forbidden / tenant-mismatch). Tokens, JWTs, and secrets never appear in payloads.

## Authentication Requirements
This contract **owns** the platform authentication mechanism across both phases.
- **Phase 0** authenticates the bootstrap **system identity** against a static, infrastructure-owned **trust anchor**, verified **without any database lookup**. Control-plane only.
- **Phase 1 — hybrid identity model (D-03, approved):**
  - **Internal platform identities** for operators/staff.
  - **OIDC federation** for external organizations (each external tenant organization brings its own OIDC IdP).
- **Authentication scheme (D-05, approved): OIDC with stateless JWT validation.** Tokens are validated cryptographically (issuer/audience + signature against the IdP's published keys). **No server-side session store** and **no Control-DB session dependency** — authentication requires no database lookup, preserving the D-01 separation of authentication from routing.
- Portability: any OIDC-standard, self-hostable IdP; explicitly **not** Supabase Auth.
Token TTL, refresh, key rotation, and revocation are specified in **JWT Lifecycle** below. Per-tenant OIDC federation configuration (issuer / audience / JWKS reference) is stored in the **Control-DB registry** (IC-002) and resolved at authentication time; secrets are **D-14 references**, never inlined.

## Authorization Requirements
The bootstrap system identity is **control-plane-scoped only and MUST NOT resolve to any tenant database**; Phase 0 denies all tenant-scoped requests.

**Tenant membership & context (D-04, approved):** a principal may belong to **many tenants (1:N)**, but **every request carries exactly one active tenant context.** Concurrent multi-tenant access within a single request is prohibited; changing the active tenant re-scopes subsequent requests and is a sensitive, audited operation. In Phase 1, tenant-scope authorization is enforced at routing time so a principal can never reach a tenant they do not belong to, and never more than one tenant's database per request.

Per-feature authorization is delegated to each feature contract (this contract owns authentication + tenant-scope authorization). The **active-tenant switch** mechanism is specified in *Tenant Identifier Carriage* (D-06): a switch obtains a new tenant-scoped token and is audited.

## Role Hierarchy & Operating Model (D-32)
This contract defines the MVP **roles** (not permissions; permissions remain contract-controlled). Roles map to the hybrid identity model (D-03):

| Role | Identity (D-03) | Scope |
|---|---|---|
| **CONTROL** | Internal platform | Control plane / global (operates on the Control Database) |
| **MASTER_AGENT** | Internal platform | Operating role across **assigned** tenants — one active tenant per request |
| **TENANT_ADMIN** | Federated (OIDC) | Within the assigned tenant |
| **TENANT_AGENT** | Federated (OIDC) | Within the assigned tenant |
| **STARTUP_USER** | Federated (OIDC) | Authorized startup functions within tenant scope |
| **INVESTOR_USER** | Federated (OIDC) | Authorized investor functions within tenant scope |

**Anti-privilege-escalation (applies to MASTER_AGENT and all roles):**
- The hierarchy conveys **operational authority only** and **does NOT imply cross-tenant superuser access**.
- **MASTER_AGENT MUST always obey** `One Request → One Active Tenant → One Database` (D-04).
- **Multi-tenant membership does NOT permit multi-tenant access within a single request** — a principal who is a member of many tenants still operates within exactly one active tenant context per request.
- No role (including CONTROL/MASTER_AGENT) may bypass tenant isolation: all tenant-data access requires tenant-scoped auth (D-04 / D-05 / D-06) and single-tenant routing + per-tenant credentials (D-30); CONTROL operating on the Control Database does **not** grant tenant-data access; the Phase-0 system identity (D-01) never resolves a tenant database.
- **MASTER_AGENT ↔ tenant assignments** are stored in the Control-DB Tenant Registry (membership, IC-002).
- **Relationship Management and Operational Oversight are limited to the active tenant context.** Cross-tenant collaboration / introductions / sharing are **out of MVP** and governed by **future IC-007**.

This section defines roles only — **no permission matrix**; per-feature permissions remain governed by the relevant contracts under IC-005.

## Global Directory Authorization (D-31 clarification)
Access to the Global Startup/Investor Directories (hosted in the Control Database per D-31) is a **control-plane read, governed by IC-005**: it MUST be authenticated, MUST be auditable, and MUST **never expose tenant-owned records**. This is an existing control-plane path — no change to D-05 / D-06 / D-07 / D-30.

## Tenant Identifier Carriage (D-06)
The active tenant is carried as an **integrity-protected signed JWT claim**, which is **authoritative** (D-06). A subdomain and/or HTTP header MAY be used for addressing/UX, but IC-005 MUST:
- treat the **signed claim as the source of truth**, and **reject any request whose subdomain/header does not match the claim**;
- verify the authenticated principal is an **authorized member** of that tenant (D-04) before routing;
- enforce **exactly one active tenant context per request** (D-04).

This blocks the "valid token + swapped tenant header/host" cross-tenant attack. A **tenant switch** (1:N membership) is performed by obtaining a **new token scoped to the new active tenant** — stateless, no session store — and is an audited operation.

The exact recognized carrier channels, the prohibited carrier channels, and the workspace vocabulary that presents this mechanism are specified in *Workspace Terminology & Carriers* (D-33) below.

## Workspace Terminology & Carriers (D-33, as corrected by D-33-E1)
*Added 2026-06-12 under PRD-CAP-01A; wording refined per PRD-CAP-01A-R1. Terminology, carrier enumeration, and one mandatory audit obligation (D-33-E1 Item 1) — no normative change to token validation, JWKS, roles, or denial semantics; the D-06 mechanism above is unchanged.*

**Workspace definition.** A **Workspace** is the **UI representation of a signed tenant context** — presentation vocabulary for an already-authenticated routing context, never a mechanism of its own:
- **Tenant Workspace** ↔ the signed active-tenant claim (D-06) ↔ exactly one physically separate tenant database.
- **Control Workspace** ↔ a CONTROL-role principal with **no** tenant claim ↔ control-plane scope only; it can never reach a tenant database.

**Workspace is NOT:** a routing input; a database selector; an authorization source; an HTTP header, cookie, or query-string value with authority; a tenant filter; a JWT claim of its own; a database or schema; or server-side session state.

**Routing authority.** The **signed tenant claim is the sole routing authority** (D-06). The UI derives the current workspace *from* the token — never the reverse. No workspace value participates in database selection, directly or indirectly.

**Workspace switching.** Selecting a different workspace is the existing IC-005 **tenant switch**: obtain a **new token scoped to the new active tenant** (or a tenantless CONTROL token for the Control Workspace) — stateless, audited. A workspace switch is **never** a header mutation, session mutation, or in-place context mutation.

**Recognized carriers (exact enumeration).** Exactly **two** carrier channels are recognized for tenant addressing/UX, both subordinate to the signed claim under **match-or-reject**:
1. the **tenant subdomain** (host-based addressing; the concrete DNS/certificate scheme remains a deployment binding);
2. the HTTP request header **`X-Tenant-Id`** — the **only** recognized carrier header (name fixed by this amendment, the naming act D-33 §7 assigns to it; the D-06 decision pack's illustrative `X-Tenant-Id` is the only prior occurrence in the governed corpus; HTTP header-name case-insensitivity applies).

**All other headers are unrecognized as tenant carriers and MUST be ignored** for carriage purposes.

**Carrier mismatch (restated).** Where the token carries a tenant claim, every recognized carrier value MUST match it or the request is rejected — **403 `carrier_mismatch`** (existing contract law; implemented and verified by two complementary tests). For tokens with **no** tenant claim, the tenantless-CONTROL rule below governs.

**Prohibited carriers.** **Cookies and query-string parameters MUST NOT carry tenant or workspace identity.** Any inbound tenant/workspace cookie or query-string parameter MUST be stripped/ignored at the API Gateway and MUST NOT be read by any backend component for **any** purpose, including token issuance (ordinary non-identity cookies and query parameters are outside this rule's scope). *Rationale:* a cookie attaches ambient, client-controlled authority to every request (CSRF-class risk); query strings leak into logs and referrers.

**Tenantless-CONTROL carrier rule (D-33-E1 Item 1 — mandatory).** When a recognized tenant carrier accompanies a **tenantless CONTROL token**, routing behavior is unchanged — the carrier is **ignored; the claim alone governs** (control-plane scope) — **and the platform MUST emit an anomaly-audit event** (action `CarrierOnControlAnomaly`) recording, **by reference only** (D-34 Global Audit Representation Rule): principal reference, the carrier-asserted tenant identifier (recorded as an **opaque, length-bounded string** solely for anomaly attribution — never parsed, resolved, or treated as a trusted identifier), correlation id, timestamp. This event is control-plane **operational audit** (Control-DB resident per D-34). **Execution-PRD acceptance items (code lands only with the IC-005-amendment execution PRD — contracts precede code):** (a) the anomaly-audit emission — **owned by the API Gateway as the sole single-edge emitter** of the gateway-edge class-3 events (IC-010 §J; see *Runtime Operational Audit Emission* below); the `auth_router` **detects and surfaces** the tenantless-CONTROL condition but does **not** itself emit; (b) a regression test locking the tenantless-CONTROL carrier-ignored behavior, parallel to `test_carrier_mismatch_audited`.

**Gateway obligation (forward-binding, D-33 §4.6).** When the API Gateway is implemented (contract: IC-010), it MUST construct the Database Router's request context **exclusively** from the Authenticator's output, MUST pass any recognized carrier into the carrier-match check, and MUST NOT read any workspace header, cookie, or query-string as a tenant selector.

## Runtime Operational Audit Emission (D-34-R2 §6 — Inventory R2)
*Added under PRD 05. Homes the **emission edge** for the Runtime Operational Audit class; the class's **Control-DB residency, shape, and retention** home is [IC-002](IC-002-Tenant-Startup-Contract.md) *Audit-Section Extension* (class 3). Reference-only per the Global Audit Representation Rule ([IC-001](IC-001-Global-Startup-Contract.md), D-34-R2 §7). No change to token validation, JWKS, roles, or denial semantics.*

**Classes & shape.** `RouteDenied` (authorization/readiness denial at dispatch), `CarrierMismatch` (403 carrier/claim mismatch), `CarrierOnControlAnomaly` (recognized tenant carrier on a tenantless CONTROL token — mandatory, D-33-E1 Item 1), `IsolationAnomaly` (any detected attempt to cross the one-database boundary). Each event is **Control-DB resident** (home: IC-002 class 3) and reference-only: `action`, `correlation_id`, `outcome`, `actor_ref` (optional), `tenant_ref` (optional), `carrier_ref` (optional; for CarrierOnControlAnomaly/IsolationAnomaly — an **opaque, length-bounded** carrier identifier per the *Tenantless-CONTROL carrier rule* above, never parsed/resolved/trusted), `timestamp`. *(These four events are the **gateway-edge subclass** of IC-002 class 3; the **router-edge routing-decision subclass** is defined below — added 2026-07-13, DBR-AR-2A.)*

**Sole emitter; single edge.** When the API Gateway (IC-010) is present, **the gateway is the sole emitter** of these gateway-edge events, emitting each **once per correlation id** (IC-010 §J single-edge). The Authentication Router's role is **detection and signalling only**: it produces the authenticated context (and the tenantless-CONTROL condition) the gateway reads; it does **not** itself emit these events. **No event is emitted by more than one component.**

**Reconciliation of the tenantless-CONTROL anomaly.** The *Tenantless-CONTROL carrier rule* above keeps both substantive guarantees: `CarrierOnControlAnomaly` remains **mandatory** and **emitted exactly once** (now at the gateway edge — IC-010 §J / as-built), and the carrier-ignored routing behavior remains locked by a regression test. Consistent with the reworded acceptance item (a) of that rule, emission is the **gateway's** (single edge, gateway-edge subclass); the `auth_router` surfaces the condition but does not emit.

**Router-edge routing-decision subclass (added 2026-07-13, DBR-AR-2A).** **The Database Router is the sole emitter** of the router-edge routing-decision subclass of IC-002 class 3 ([IC-002](IC-002-Tenant-Startup-Contract.md) *Audit-Section Extension*, class 3 — Database Router edge): `Route`, `RouteControl`, `RouteDenied`, `IsolationAnomaly` at router granularity, emitting **exactly one event per completed or denied `route()` invocation** (including the pre-target denials `tenant_routing_unavailable` and `no_active_tenant`). Event identity is **(edge/subclass, action)**: the gateway-edge and router-edge sets are **different subclasses with different sole emitters**, so the shared action names `RouteDenied` and `IsolationAnomaly` denote different events at different edges. **No event is emitted by more than one component.** The Authentication Router remains **detection and signalling only** and does not become the emitter of record for any class-3 event. The Database Router performs **no authentication** — routing-decision events record the routing outcomes of already-authenticated requests; authentication remains upstream at the auth/gateway edge (IC-010 §H).

**Denial-edge precision.** `tenant_access_denied` / `tenant_not_ready` arise at the **auth/gateway edge** (the `auth_router` detects and surfaces them; the API Gateway records them as gateway-edge class-3 `RouteDenied`); such requests never reach the Database Router's `route()`. `not_found` / `not_ready` — and the rest of the canonical router public-code vocabulary — arise at the **router edge** and are recorded by the Database Router as router-edge `RouteDenied`.

**Gateway-edge success-access subclass — `workspace_memberships_read` (added 2026-07-17, B5-BLK-6C-A, Dan-authorized Option A).** A **separate success-access subclass** of IC-002 class 3 (home: [IC-002](IC-002-Tenant-Startup-Contract.md) *Audit-Section Extension*, class **3b** — Control-DB resident). The four gateway-edge denial/anomaly classes remain exactly the historic four — `RouteDenied`, `CarrierMismatch`, `CarrierOnControlAnomaly`, `IsolationAnomaly` — unchanged, and the router-edge routing-decision subclass is unchanged. A successful self-scoped **MembershipsForPrincipal** enumeration MUST emit **exactly one** references-only operational audit event with `action == "workspace_memberships_read"`. A successful **empty** enumeration is still a successful enumeration and MUST emit the event. Never zero events, never two, never one event per returned membership record, never one event per tenant — the audit records the operation, not the number or contents of returned memberships. **The API Gateway is the emitter**; it is the **sole emitter of this success event** (single edge). The Auth Router remains detection and signalling only. The event resides in **Control-DB operational audit**. It is a success-access event and MUST NOT be relabelled or classified as a denial, anomaly, or routing event. A denied, unauthenticated, unavailable, malformed, or isolation-anomaly request does not emit this success event; existing denial/anomaly audit semantics remain separate and unchanged. Minimum shape (references only): `audit_id`, `action`, `actor_principal_ref`, `subject_principal_ref`, `correlation_id`, `occurred_at`, `outcome`, `event_version` — with `action == "workspace_memberships_read"`, `outcome == "success"`, `event_version == 1`; for the currently bound self-scoped operation, `actor_principal_ref == subject_principal_ref`. The CONTROL-on-behalf-of-subject form is contract-preserved but is not runtime-bound by B5-BLK-6B and is not implemented by B5-BLK-6C-A. The event MUST NOT contain the returned tenant-membership collection (raw membership rows are prohibited content). **Runtime status:** B5-BLK-6C-A authorizes and defines the later **B5-BLK-6C-B** runtime implementation; it does not itself implement or prove runtime emission — the event is not yet emitted by the current runtime. B5-BLK-6C-A adds no runtime implementation and closes no blocker; **B5-BLK-6 remains OPEN**.

**Directory-read access audit — Reserved.** IC-005's *Global Directory Authorization* (D-31) requires directory access be auditable; whether each directory **read** emits a per-read access-audit event is **Reserved** (IC-001: directory views *"if ever recorded"*) and is **not** mandated by this amendment. If later elected, it homes as a Control-DB operational-audit subclass under the same Representation Rule. **Reconciled 2026-07-17 under B5-BLK-6C-A (Dan-authorized Option A):** Per-read Global Directory access audit is **Reserved**. It is not required by B5-BLK-6. It is not emitted by the current runtime. It may be elected only through a later governed contract decision. This reservation applies to the **startup directory read** and the **investor directory read**; it reaches **directory reads only** and does **not** shelter or reach **MembershipsForPrincipal**, whose success audit is **mandated** (see the success-access subclass above). IC-010 §R is reconciled to this Reserved policy and no longer mandates a per-read directory access audit. This reservation does not authorize or imply Global Deal directory support, a positive IC-007 capability, tenant attribution, cross-tenant fan-out, frontend cutover, or production activation.

## Cross-Tenant Isolation Enforcement (D-30)
Isolation is enforced **defense-in-depth** across four layers; no single failure may breach it:
1. **AuthN/AuthZ** — OIDC stateless JWT (D-05) + authoritative signed tenant claim (D-06) + principal membership check (D-04); mismatches rejected.
2. **Routing** — the Database Router binds **exactly one** resolved tenant database per request (registry-authoritative, D-07); one-request→one-DB is **enforced, not assumed**.
3. **Physical / data layer** — separate tenant databases (no shared DB) with **per-tenant credentials** (D-14); a connection is **never reused across tenants** (D-13). Physical separation is the last line of defense — even a routing bug cannot cross into another tenant's database.
4. **Audit / detection** — tenant switches and cross-tenant-adjacent attempts are audited and anomaly-detected.

**No cross-tenant joins or spanning queries — ever.** Any cross-tenant aggregation is performed as explicit, audited, per-tenant control-plane reads.

## JWT Lifecycle (D-05 detail)
Per the OIDC stateless model (D-05) — **no session store, no Control-DB session dependency**:
- **TTL** — **short-lived access tokens** (operational target on the order of minutes), bounding stolen-token exposure.
- **Refresh** — **OIDC refresh tokens managed at the IdP** (silent refresh); the platform holds no session state.
- **Key rotation** — **JWKS with `kid` and an overlap window** for zero-downtime rotation; key material is referenced via the D-14 abstraction; any OIDC-standard, self-hostable IdP (no Supabase Auth, no vendor lock-in).
- **Revocation** — primary is **short-TTL + refresh-token revocation at the IdP**; an **optional, bounded, short-lived control-plane denylist (by `jti`, expiring at access-TTL)** provides emergency immediate revocation — explicitly **not** a session store and **never per-tenant**.
- **Validation** — strict `iss` / `aud` / `exp` / `kid` checks, algorithm-confusion rejected, and the **tenant claim bound** (D-06) so a token cannot be reused across tenants (D-30). Validation is **DB-free**, preserving the D-01/D-05 separation. A revoked / expired / invalid token MUST NOT route.

## Multi-Database Compatibility
- The router resolves authenticated requests to either the Control Database or exactly one tenant database — never both, never spanning tenants.
- Routing metadata lives in the Control Database and is used for **Phase-1 tenant routing only**; it is not required to authenticate the control plane. Tenant data is never used for auth routing.
- Tenant routing is available only after the Control Database is online (Phase 1); during Phase 0 no tenant database can be resolved.
- The bootstrap system identity can never resolve to a tenant database (isolation invariant).
- Isolation is enforced **defense-in-depth (D-30)**: per-tenant credentials (D-14), connections never reused across tenants (D-13), and no cross-tenant joins or spanning queries — ever.
- Must work against standard PostgreSQL backends (AWS RDS / Azure / Google Cloud SQL / self-hosted).

## Anti-Vendor-Lock-In Requirements
- **No Supabase Auth or Supabase-specific authentication logic.**
- No Lovable-specific authentication/runtime dependencies.
- Auth must not depend on a single cloud provider's identity service in a non-portable way.

## Resolved Decisions
- **D-06** — tenant identifier carried as an authoritative signed claim with carrier-match enforcement (*Tenant Identifier Carriage*).
- **D-30** — defense-in-depth cross-tenant isolation enforcement (*Cross-Tenant Isolation Enforcement*).
- **JWT lifecycle** — short TTL, IdP refresh, JWKS/`kid` rotation, IdP/optional-denylist revocation, no session store (*JWT Lifecycle*).
- Unknown / suspended-tenant routing semantics follow **IC-002** readiness (*not found* / *administratively disabled* / *unavailable* / *retry later*).
- **D-32** — MVP role hierarchy (CONTROL, MASTER_AGENT, TENANT_ADMIN, TENANT_AGENT, STARTUP_USER, INVESTOR_USER); roles not permissions; anti-privilege-escalation; cross-tenant collaboration deferred to IC-007 (*Role Hierarchy & Operating Model*).
- **D-31** — Global Directory authorization governed by IC-005 (control-plane read; authenticated/auditable; never exposes tenant-owned records) (*Global Directory Authorization*).
- **D-33** (as corrected by **D-33-E1**) — Workspace = UI representation of the signed tenant context; exact carrier enumeration (tenant subdomain + `X-Tenant-Id`); cookie/query-string carriage prohibited; mandatory carrier-on-CONTROL anomaly audit (*Workspace Terminology & Carriers*).
- (Earlier) **D-03** hybrid identity; **D-04** 1:N, one active tenant per request; **D-05** OIDC + stateless JWT. See [Architecture-Decision-Register.md](../docs/Architecture-Decision-Register.md).

## Implementation Notes (non-architecture)
These do **not** reopen the architecture:
- Exact access-token TTL value and clock-skew tolerance (operational tuning).
- Whether to enable the optional emergency `jti` denylist, and its (control-plane) storage choice.
- Wildcard certificate / DNS management if subdomains are used for addressing.

## 07E-3a auth transport wire contract capture (governance; PRD-07E-3a, 2026-07-08)

*Insert-only governance note. References the internal gateway↔auth-router authentication transport wire captured for future runtime work (07E-3b). No normative change to the authentication model — token validation, JWKS, OIDC, the JWT lifecycle, roles, tenant-context, carrier, or denial semantics above are unchanged.*

- **IC-005 remains the authority** for authentication semantics (Phase 0/1, OIDC stateless JWT validation, roles D-32, tenant carriage D-06, carrier match-or-reject D-33, denial semantics). This note adds nothing normative.
- `docs/auth/AUTH-TRANSPORT-SPEC-01-Gateway-AuthRouter-Wire-Contract.md` captures the **internal API Gateway ↔ Auth Router** authentication transport wire (the authentication analogue of the D-15-T1a dispatch capture in IC-010).
- The **Auth Router validates the inbound authentication artifact** (Stage 1: DB-free JWT validation; Stage 2: tenant/membership/role/readiness resolution via the approved control-plane read) and **resolves references**. The API Gateway performs neither stage and consumes the result as input (IC-010 §D).
- The Auth Router returns **only the 4-field `AuthContext` / `AuthResult` shape** (`correlation_id`, `principal_ref`, `active_tenant_id`, `role`) — references only. CONTROL context is derived (`active_tenant_id` is null), never a carried field.
- The Auth Router **does not return** tokens, JWKS/key material, secrets, credentials, the inbound authorization header, PII (email/name/display name/profile), business payloads, database material (DSN/database name/handle), membership lists, permission matrices, or authorization decisions. The inbound bearer credential is validated server-side and is **never logged, never returned, and never forwarded to the Database Router**.
- Consistent with the *Runtime Operational Audit Emission* reconciliation above, the API Gateway remains the sole single-edge audit emitter for the gateway-edge class-3 events *(per the DBR-AR-2A amendment, the Database Router is the sole emitter of the router-edge routing-decision subclass)*; the Auth Router detects and surfaces the authenticated context (and the tenantless-CONTROL condition) but does not itself emit.
- **Runtime implementation remains deferred to 07E-3b** (the gateway authenticator transport client + the Auth Router authentication server). This note authorizes no runtime code, no server, no token validation, and no database access. **B5-BLK-4 remains OPEN; Physical Multi-Database MVP is mandatory and NOT complete.**

## R1 Principal-Only Bootstrap & OIDC Transition (B5-BLK-5 R1, D-41)

*Added under D-41 (B5-BLK-5 R1). Additive only — no normative change to the Two-Phase Authentication Model, D-05 OIDC stateless JWT validation, JWKS, the D-32 role hierarchy, D-06 tenant carriage, the D-33 carrier match-or-reject rule, the Runtime Operational Audit Emission section above, or any denial semantics. The carrier remains match-only; workspace switch remains deferred (out of R1 scope). This section states the R1 principal-only bootstrap context, its single eligible route, and the OIDC transition and lifecycle-ownership homing that R1 requires.*

- **Principal-only authenticated context.** A valid **tenantless** OIDC access token authenticates a **principal** and establishes a **principal-only context**: the existing four-field references-only `AuthContext { correlation_id, principal_ref, active_tenant_id, role }` with **`active_tenant_id = null` and `role = null`**. Both fields are lawfully null; `role` is server-derived **only** when a tenant is active (the tenantless branch performs no Control-DB membership/role lookup). No new field is introduced. This context is available to **any** authenticated principal (a CONTROL operator is one case; a not-yet-scoped member is another), broadening the D-33 "Control Workspace ↔ CONTROL principal" framing to a general principal-only bootstrap context without weakening it.
- **`active_tenant_id` and `role` nullability.** A principal-only context carries `active_tenant_id = null` **and** `role = null`. This is not a CONTROL-only condition: it is the lawful bootstrap shape for any tenantless principal, and role authority is never inferred from a null tenant.
- **R1 eligible route — `GET /memberships` only.** The self-scoped **MembershipsForPrincipal** read (`GET /memberships`) accepts the principal-only context: it is a Control-DB read whose subject is exclusively `AuthResult.principal_ref` (never a client-supplied selector), returning the references-only membership set `{ tenant_id, role, display_ref }`; an empty membership set is a lawful success. It requires neither an active tenant nor a role.
- **Tenant-route rejection (fail-closed).** No **tenant-scoped** operation accepts the principal-only context. A tenant-domain request under a tenantless context is denied **fail-closed** (`403`, tenant context required); the context never falls back to a default tenant and never routes to a tenant database.
- **Asymmetric-only algorithm posture.** OIDC access tokens are validated with **asymmetric algorithms only** — `allowed_algs ⊆ {RS256, RS384, RS512, ES256}`; `HS*` and `none` are rejected at configuration. The tenant-claim key is `tenant`. (This pins at the contract level the algorithm set and claim key the JWT Lifecycle section already implies.)
- **Tenant claim optional for bootstrap.** The tenant claim is **optional** for the principal-only bootstrap context: a token with no `tenant` claim is authenticated and yields `active_tenant_id = null`. A token that **does** carry a `tenant` claim continues to bind that tenant under the existing D-06 match-or-reject rule (unchanged).
- **Supabase JWT rejection.** The Auth Router validates OIDC tokens (Stage 1, DB-free) and resolves the principal-only or tenant-bound context (Stage 2); it **never accepts a Supabase JWT** (Supabase `HS256` is structurally excluded by the asymmetric-only pin). Consistent with the sole-single-edge-emitter reconciliation in *Runtime Operational Audit Emission* above, the Auth Router remains **detection and signalling only** and **does not itself emit** any operational-audit event.
- **Gateway no-mint / no-exchange.** The API Gateway performs **no token mint and no token exchange**; it consumes the authenticated context as input (IC-010 §D) and resolves no database. A successful self-scoped `GET /memberships` enumeration emits exactly one references-only `workspace_memberships_read` success-access event; the **API Gateway is its sole emitter** (the emission edge and Control-DB home are unchanged from *Runtime Operational Audit Emission* above).
- **Keycloak as the controlled R1 provider (not provider-locking).** For R1's controlled proof, **Keycloak** is the selected OIDC provider (standard Authorization Code + PKCE, public browser client, short-lived in-memory access token as Bearer to the Gateway, IdP-owned refresh), trusted via a **static `SP2_AR_ISSUERS`** entry `{ issuer, audience, allowed_algs ⊆ {RS256, RS384, RS512, ES256}, jwks, tenant_claim: "tenant" }`. This selects a concrete provider for the controlled R1 login/session proof **only**; it **does not make Keycloak the permanent production IdP**, and the contract remains provider-neutral (any OIDC-standard, self-hostable IdP satisfies it). No provider-specific workspace-switch capability is assumed.
- **Lifecycle ownership.** **IdP-owned:** login, session restoration, refresh, logout, invite credential, forgot-password, password reset, account recovery. **SnackPortal2 Control authority:** membership invitation authority, and membership and role authority. (Logout is IdP RP-initiated with an optional Control `jti` denylist; invite = SnackPortal2-owned membership + IdP-owned credential; reset/recovery = IdP-owned.)
- **Stabilization and retirement boundary references.** R1 lands under **stabilize-first / retire-later**: **R1A** adds the OIDC + Gateway memberships path behind an explicit selector and removes **no** direct-Supabase or dependency occurrence; **R1B** retires exactly the ratified R1 occurrence set only after the controlled proof gates pass. Pre-retirement rollback is a **selector flip** to the legacy path; post-retirement rollback is **fail-closed unavailable** (never an ordinary restoration of removed occurrences or active IDs). The workspace-switch protocol, tenant-scoped token issuance, and every R2 directory item are **out of R1** and remain separately governed.
