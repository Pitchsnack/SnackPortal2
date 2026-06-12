# IC-002 — Tenant Startup Contract

**Status:** Final · **Phase:** Architecture Planning · **Type:** Specification only (no implementation)
**Decision basis:** Incorporates approved decisions **D-01–D-05** and the tenant-infrastructure decisions **D-07, D-13–D-17** ([Architecture-Decision-Register.md](../docs/Architecture-Decision-Register.md)).
**Status note:** All tenant-startup architecture decisions are resolved and incorporated; the previously-pending cross-contract items — the secret-store abstraction (D-14) and tenant-identifier carriage (D-06, owned by IC-005) — are now resolved. **Final** for MVP architecture; residual items are implementation/operational and do not reopen the architecture.
**Amendment (2026-06-12, PRD-CAP-01A):** implementing **D-33** as corrected by **D-33-E1** — the *Tenant Workspace* terminology alias (vocabulary only; the Core Invariants are untouched verbatim), the **MembershipsForPrincipal** operation added to the API Contract (D-33-E1 Item 2; implementation deferred to the API Gateway / frontend-integration execution PRD), and the D-33 audit events named under *Audit Requirements*.
Requirement keywords **MUST / MUST NOT / SHOULD / MAY** are used in the RFC-2119 sense.

## Purpose
Define how an **individual tenant** is registered, brought online, and made routable: associating the tenant with its own physically separate database, verifying availability and schema compatibility, and exposing a readiness signal that the Authentication and Database Routers (IC-005) consume. Tenant startup is strictly a **Phase-1** activity (post-Control-DB; see [IC-001](IC-001-Global-Startup-Contract.md) and D-01); no tenant can be resolved during Phase 0.

## Core Invariants (preserved — MUST hold at all times)
1. **One request → one active tenant.** Every request carries exactly one active tenant context (D-04).
2. **One active tenant → one database.** That context resolves to exactly one physically separate tenant database.
3. **No cross-tenant routing.** A request MUST NOT span tenants or tenant databases; the active tenant is fixed for the request's duration.
4. **No shared tenant databases.** Each tenant has its own physical database; tenants MUST NOT share a database or schema.

These invariants bind every section below. Any behavior that would violate them is out of contract.

## Workspace Terminology (D-33 — alias only)
*Added 2026-06-12 under PRD-CAP-01A (D-33, as corrected by D-33-E1).* The **active tenant context (D-04)** gains the presentation-layer alias **Tenant Workspace**; **Control Workspace** denotes control-plane scope — a CONTROL-role principal with **no** tenant claim, which can never reach a tenant database. The alias is vocabulary only: the four **Core Invariants above are untouched verbatim**, and no behavior of this contract changes. **Workspace switching is the IC-005 tenant switch** — obtaining a **new scoped token** (audited) — never a header mutation, session mutation, or context mutation. The workspace definition, exact carrier enumeration, prohibited carriers (cookies/query strings), and the carrier-on-CONTROL anomaly rule are owned by [IC-005](IC-005-Authentication-Routing-Contract.md) (*Workspace Terminology & Carriers*).

## Scope
- Tenant **registration** in the Control-DB tenant registry and the tenant **lifecycle** state machine.
- Tenant **readiness** determination (connectivity + schema-version compatibility) and the readiness signal routing depends on.
- **Tenant-to-organization mapping** and per-tenant identity-federation configuration (D-03).
- **Physical database association** (recorded as a reference; credentials are never held in this contract's payloads).
- Failure behavior, isolation guarantees, audit, and the dependencies this contract has on IC-005.

## Non-goals
- Global/control-plane startup (see [IC-001](IC-001-Global-Startup-Contract.md)).
- **Provisioning the physical database itself** — creating/destroying the PostgreSQL instance is an infrastructure concern. Per **D-15**, provisioning is owned by an **IaC substrate orchestrated by an automated, audited control-plane workflow** (manual runbook = break-glass only); IC-002 *observes and associates*, it does not implement provisioning.
- Defining the authentication mechanism or routing logic — those are owned by [IC-005](IC-005-Authentication-Routing-Contract.md); IC-002 *consumes* them.
- Data import into a tenant (see [IC-003](IC-003-Import-Contract.md)).
- Any implementation, migration, or provisioning code.

## Tenant Lifecycle
The Control DB holds the authoritative lifecycle state for each tenant. States:

| State | Meaning | Routable? |
|---|---|---|
| **Registered** | Tenant record exists in the Control-DB registry; no verified database association yet. | No |
| **Provisioning** | Awaiting the physical database to be made available (provisioned per D-15 — IaC substrate + automated control-plane workflow). | No |
| **Verifying** | Database associated; connectivity and schema-version compatibility being checked. | No |
| **Ready** | All checks passed; eligible for routing and serving. | **Yes** |
| **Suspended** | Administratively disabled; data preserved; tenant-scoped requests denied. | No (explicit deny) |
| **Failed** | Verification failed — database unreachable or schema-incompatible; awaiting remediation. | No (explicit deny) |
| **Decommissioned** | Offboarded; removed from active routing; data retained/archived per policy. | No |

**Allowed transitions:**
- `Registered → Provisioning → Verifying → Ready`
- `Verifying → Failed` (unreachable or schema-incompatible)
- `Failed → Verifying` (retry after remediation)
- `Ready → Suspended` and `Suspended → Verifying → Ready` (reactivation re-verifies)
- `Ready | Suspended | Failed → Decommissioned`

Every transition MUST be control-plane-authorized and audited (see *Audit Requirements*). Transitions MUST be idempotent where re-issued with the same target state.

## Tenant Readiness States
- **Readiness is a derived signal:** a tenant is **ready** only in the `Ready` state; all other states are **not-ready**.
- IC-005 routing MUST treat the readiness signal as authoritative and MUST route only to `Ready` tenants.
- Not-ready states MUST be distinguishable to callers with defined semantics: `Provisioning`/`Verifying` → *retry later*; `Suspended` → *administratively disabled*; `Failed` → *unavailable*; `Decommissioned`/unknown → *not found*. These MUST NOT leak another tenant's existence or internal detail beyond what the caller is authorized to know.
- Readiness MUST be re-evaluated on (re)verification and MAY be re-checked on a defined health cadence. Partial-fleet behavior follows **D-16**: each tenant's readiness is **independent** (see *Failure Behavior*).

## Tenant Registration
- Registration creates the **authoritative tenant record** in the Control-DB tenant registry (a Phase-1, control-plane operation).
- The record MUST capture at minimum: a stable, opaque **tenant identifier**; the **organization mapping**; the **identity-federation configuration reference** (external orgs, D-03); the **physical-database association reference**; the **expected schema version**; the current **lifecycle state**; and audit metadata.
- Registration MUST be performed by an authorized control-plane operator using an **internal platform identity** (D-03), or via a controlled onboarding flow that resolves to such an identity. Tenants MUST NOT self-register into a routable state without control-plane authorization.
- Registration **records intent and association only** — it MUST NOT provision the physical database (that is infra-owned, D-15). A newly registered tenant begins not-ready and becomes routable only after successful verification.
- The tenant identifier MUST be stable for the tenant's lifetime and MUST NOT encode secrets. Per **D-07**, database resolution is **registry-authoritative**; any naming convention is only a non-authoritative default the registry overrides — the identifier MUST NOT be the sole binding to a database.

## Tenant-to-Organization Mapping
Reflecting the **hybrid identity model** (D-03):
- **External tenants** correspond to an **organization that federates via its own OIDC IdP**. The Control-DB registry stores, per tenant: organization identifier, OIDC **issuer** and **audience**, a **JWKS reference** (the IdP's public keys are public; no secret is stored inline), and the **claim → tenant resolution rule** that IC-005 uses to establish tenant context.
- **Internal operators** authenticate with **internal platform identities** (not federated) and are **not tenant-bound**; their access to any tenant is via authorized, audited membership.
- **Cardinality:** one organization ↔ one tenant ↔ one physical database (**1:1:1**) for external orgs. This does **not** conflict with D-04: D-04's 1:N is *principal → tenants* (a person/operator may be a member of many tenants), while *organization → tenant* remains 1:1.
- Per-tenant federation configuration is **owned by this registry and consumed by IC-005** at authentication time; IC-002 does not perform authentication itself.

## Physical Database Association
- Each tenant MUST be associated with **exactly one physically separate PostgreSQL database** (Invariants 2 & 4). Shared schemas or shared databases are prohibited.
- The association MUST be recorded in the Control-DB registry as a **connection descriptor reference** — a pointer (`{store-ref, version}`) into the **pluggable, reference-based secret-store abstraction** (**D-14**). **Credentials MUST NOT be stored in the registry or appear in any IC-002 payload, log, or response;** values are resolved in-memory at connect time only.
- Per **D-07**, the Control-DB registry is the **authoritative source** of the tenant→database association; the Database Router MUST resolve via the (cached) registry and MUST NOT use hardcoded tenant database references. A naming convention MAY act only as a non-authoritative default the registry overrides. The resolution cache MUST be tenant-scoped and invalidated on re-association.
- Association is stable in normal operation. **Re-association** (e.g., restore, relocation) MUST be an audited control-plane operation that re-enters `Verifying` before the tenant returns to `Ready`.

## Connection Management & Scale
Per **D-13**:
- The Database Router obtains connections from a **connection manager holding lazy, bounded per-tenant pools with LRU idle eviction** — pools exist only for active tenants, keeping total connections within each PostgreSQL instance's ceiling.
- A **portable, self-hostable transaction pooler** MAY be introduced as a future scale layer when tenant density requires it; it MUST remain provider-neutral.
- A connection MUST be bound to **exactly one tenant** for the duration of a request/transaction and MUST NEVER be reused across tenants (Invariants 1–3).
- Import and other heavy workloads (IC-003) SHOULD draw from **separate, bounded capacity** so they cannot starve interactive traffic.
- The fleet-wide tenant/connection ceiling is a capacity-planning input governed by this decision together with provisioning (D-15).

## Failure Behavior
- **Database unreachable or schema-incompatible:** the tenant MUST NOT be promoted to `Ready`; it enters/stays `Failed`; routing to it is denied with the *unavailable* semantic. Per **D-17**, schema is coordinated via **expand/contract rolling migrations** with **version-gated readiness**: a tenant whose `observed_schema_version` is outside the supported range is **not-ready** until migrated.
- **Blast-radius containment:** a single tenant's startup or runtime failure MUST NOT affect the control plane or any other tenant (a direct consequence of physical isolation). The platform remains globally available (IC-001 Phase 1) while individual tenants are not-ready.
- **Suspended tenant:** all tenant-scoped requests MUST be denied with the *administratively disabled* semantic, distinct from *not found* and *unavailable*. Data MUST be preserved.
- **Phase 0 (D-01):** no tenant can be resolved at all; any attempt to route to a tenant before Phase 1 MUST be denied.
- **Partial fleet availability (D-16):** each tenant's readiness is evaluated **independently** — the platform stays globally available while individual tenants are not-ready. A derived **`degraded` signal is observability/alerting only and MUST NOT deny healthy tenants.** Global not-ready is reserved for shared-dependency (Control DB / Phase-0) failure (D-10).

## Multi-Database Isolation Guarantees
- One physically separate PostgreSQL database per tenant; never shared (Invariant 4).
- One request → one active tenant (Invariant 1) → one database (Invariant 2); no cross-tenant routing and no spanning queries (Invariant 3).
- The **bootstrap system identity** (D-01, Phase 0) is control-plane-scoped and MUST NEVER resolve or open a tenant database.
- Tenant database access MUST use that tenant's own credentials, resolved via the **D-14 reference-based secret-store abstraction** (never raw credentials); a control-plane connection MUST NOT be reused to read or write tenant data.
- A failure or compromise of one tenant's database MUST be contained to that tenant.
- **Cross-tenant aggregation is not a routing operation.** If ever required, it MUST be performed as explicit, audited, per-tenant control-plane reads — never a cross-database join and never a single spanning request.

## Authentication Dependencies on IC-005
- IC-002 **consumes**, and does not define, authentication. Per IC-005:
  - **Tenant lifecycle/management operations** (register, verify, activate, suspend, reactivate, decommission, re-associate) are **control-plane operations** authenticated via **internal platform identities** (D-03) under the runtime model (OIDC + stateless JWT, D-05). They are control-plane-authorized, not tenant-federated.
  - **Runtime tenant-scoped requests** are authenticated by IC-005 using **OIDC with stateless JWT validation** (D-05); the **single active tenant context** is established by IC-005 from a signed claim and re-validated at routing time (no server-side session store; no Control-DB session dependency — preserving the D-01 separation).
- The **per-tenant OIDC federation configuration** stored by this contract (see *Tenant-to-Organization Mapping*) is the data IC-005 uses to authenticate external-org principals.
- The Phase-0 bootstrap system identity MUST NEVER be accepted for tenant-scoped requests.

## Routing Dependencies on IC-005
- IC-005's **Authentication Router** establishes the single active tenant context (D-04); IC-005's **Database Router** resolves that context to exactly one tenant database using the Control-DB registry association supplied by this contract.
- Routing MUST succeed only for tenants whose readiness signal is `Ready`. Not-ready states MUST yield the defined denial/retry semantics above.
- Routing MUST honor all Core Invariants: no cross-tenant routing, no spanning, exactly one database per request.
- IC-002 supplies the **registry/readiness data**; the **routing logic itself is owned by IC-005**.

## Audit Requirements
- Every lifecycle transition and every database (re)association MUST produce an audit record containing: **actor** (control-plane identity), **tenant id**, **action**, **from-state → to-state**, **timestamp**, **reason/correlation id**.
- **All tenant provisioning events must be audit logged.** Per **D-15** this includes provisioning/de-provisioning of a tenant database, credential creation/rotation (recorded as references, never values), and the resulting registration — each with actor, tenant id, action, timestamp, and correlation id.
- Audit records MUST be **append-only** and attributable; they MUST NOT be silently mutable.
- `Suspend`, `Decommission`, and `Re-associate` are sensitive and MUST always be audited; failed/denied lifecycle attempts SHOULD also be recorded.
- Tenant-lifecycle audit is **operational/control-plane audit**, distinct from data-provenance lineage ([IC-004](IC-004-Lineage-Contract.md)); it is control-plane-scoped and MUST NOT be written into tenant databases.
- Audit storage MUST remain standard-PostgreSQL/portable; its exact location is a control-plane detail (related to D-14 for any referenced secrets).
- **D-33 workspace-related audit events** *(added 2026-06-12, PRD-CAP-01A)* — the following control-plane audit obligations, aligned with the **Control-DB operational-audit model approved by D-34** and bound by its **Global Audit Representation Rule** (references only — never names, emails, PII, or payloads):
  - **Workspace switch** = the IC-005 tenant switch — an audited operation (event owned by IC-005; named here because the workspace alias presents it).
  - **Carrier mismatch** — audited rejection (403 `carrier_mismatch`; event owned by IC-005).
  - **Tenantless-CONTROL carrier anomaly** — the mandatory `CarrierOnControlAnomaly` event (D-33-E1 Item 1; specified in IC-005 *Workspace Terminology & Carriers*).
  - **MembershipsForPrincipal** calls MUST be audited (actor, subject principal reference, timestamp, correlation id — references only).
  - *Scope note:* the broader audit-section extension required by D-34/D-36 (administrative/runtime/export/ownership audit classes and Control-DB audit retention) is a **separate pending amendment** tracked in the register's closing note (Contract Amendment Inventory R2) — it is **not** executed by PRD-CAP-01A.

## API Contract
> Specification of **operations and semantics** only — no transport code. The surface is a **control-plane API** (REST/HTTP-style); concrete method/path bindings are a minor remaining detail. Denial semantics MUST distinguish *forbidden* (authz), *not found* (unknown/decommissioned), *not ready* (provisioning/verifying), *administratively disabled* (suspended), and *unavailable* (failed).

| Operation | Purpose | Caller (authz) | Result / state effect | Idempotent |
|---|---|---|---|---|
| **RegisterTenant** | Create the authoritative tenant record + associations | Control-plane operator (internal identity) | `→ Registered` | Yes (by tenant id) |
| **GetTenantStatus** | Return lifecycle state + readiness | Control-plane / authorized member | none | Yes |
| **MembershipsForPrincipal** | Enumerate a subject principal's tenant memberships — self by default; CONTROL may specify another subject (the workspace-selector source, D-33) | The principal itself (**self-scoped**) or CONTROL; **audited** | none — returns **membership records only** (tenant id, role, display ref), **never tenant-DB data** | Yes |
| **VerifyTenant** | Run connectivity + schema-version checks | Control-plane operator | `Verifying → Ready` or `→ Failed` | Yes |
| **ActivateTenant** | Promote a verified tenant to routable | Control-plane operator | `→ Ready` | Yes |
| **SuspendTenant** | Administratively disable; preserve data | Control-plane operator | `Ready → Suspended` | Yes |
| **ReactivateTenant** | Re-verify and restore service | Control-plane operator | `Suspended → Verifying → Ready` | Yes |
| **DecommissionTenant** | Offboard; remove from routing; retain/archive | Control-plane operator | `→ Decommissioned` | Yes |
| **ReassociateDatabase** | Point a tenant at a restored/relocated DB | Control-plane operator | `→ Verifying` (then `Ready`) | Yes |

*`MembershipsForPrincipal` (added 2026-06-12 per D-33-E1 Item 2) is **contract-owned here**; its implementation is deferred to the API Gateway / frontend-integration execution PRD — contracts precede code.*

## DTO Contract
> Data **shapes** described as fields only — no code, **no secrets in any payload**. Database credentials are never present; only references to secret-store entries are.

**Tenant Descriptor:** `tenant_id` (opaque, stable), `organization_ref`, `lifecycle_state`, `expected_schema_version`, `database_association_ref` (reference, not credentials), `federation_config_ref`, `created_at`, `updated_at`.

**Tenant Status / Readiness:** `tenant_id`, `lifecycle_state`, `readiness` (`ready` | `not-ready`), `observed_schema_version`, `last_checked_at`, `last_error_summary` (non-sensitive).

**Tenant–Organization Mapping:** `tenant_id`, `organization_id`, `oidc_issuer`, `oidc_audience`, `jwks_ref` (public keys; reference), `claim_to_tenant_rule`.

**Physical Database Association:** `association_ref`, `tenant_id`, `db_descriptor_ref` (secret-store reference `{store-ref, version}` per D-14 — **never** the credentials), `engine` (PostgreSQL), `provisioning_owner` (IaC + control-plane workflow, D-15), `association_state`.

**Lifecycle Audit Record:** `audit_id`, `tenant_id`, `actor`, `action`, `from_state`, `to_state`, `timestamp`, `reason`, `correlation_id` (append-only).

**Principal Membership Record (D-33):** `tenant_id`, `role`, `display_ref` — membership data only; never tenant-DB data; no secrets, names, or other PII (display naming is resolved by reference).

## Anti-Vendor-Lock-In Requirements
- **No Supabase-specific** tenant logic, no RLS-as-business-logic, and no Supabase Auth (authentication is OIDC via IC-005, D-05).
- **No Lovable-specific** runtime dependencies.
- **No provider-proprietary PostgreSQL** features in tenant startup or verification; tenants MUST run on AWS RDS / Azure Database for PostgreSQL / Google Cloud SQL / self-hosted interchangeably.
- The tenant registry, tenant→database association, and audit storage MUST be provider-neutral; any secret-store abstraction MUST be portable (D-14).
- OIDC federation MUST use the open standard with a self-hostable, swappable IdP.

## Tenant-Infrastructure Decisions (resolved)
The decisions that previously gated this contract are now approved and incorporated above (see [Architecture-Decision-Register.md](../docs/Architecture-Decision-Register.md)):
- **D-07** — registry-authoritative tenant→database mapping (*Physical Database Association*).
- **D-13** — lazy bounded per-tenant pools + LRU, portable transaction pooler as a future scale layer (*Connection Management & Scale*).
- **D-14** — pluggable, reference-based secret-store abstraction; values never in payloads/logs/responses (*Physical Database Association*, *Multi-Database Isolation Guarantees*).
- **D-15** — IaC substrate + automated control-plane provisioning workflow, manual break-glass only (*Non-goals*, *Audit Requirements*).
- **D-16** — per-tenant readiness independence; `degraded` is observability-only (*Failure Behavior*).
- **D-17** — expand/contract rolling migrations with version-gated readiness (*Failure Behavior*, *Tenant Readiness States*).

No tenant-infrastructure architecture decisions remain open for this contract. Cross-contract spec items — tenant-identifier carriage (**D-06**) and cross-tenant isolation enforcement (**D-30**) — are owned by IC-005 and tracked in [Contract-Gap-Analysis.md](../docs/Contract-Gap-Analysis.md).
