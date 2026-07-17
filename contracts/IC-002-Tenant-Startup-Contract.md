# IC-002 — Tenant Startup Contract

**Status:** Final · **Phase:** Architecture Planning · **Type:** Specification only (no implementation)
**Decision basis:** Incorporates approved decisions **D-01–D-05** and the tenant-infrastructure decisions **D-07, D-13–D-17** ([Architecture-Decision-Register.md](../docs/Architecture-Decision-Register.md)).
**Status note:** All tenant-startup architecture decisions are resolved and incorporated; the previously-pending cross-contract items — the secret-store abstraction (D-14) and tenant-identifier carriage (D-06, owned by IC-005) — are now resolved. **Final** for MVP architecture; residual items are implementation/operational and do not reopen the architecture.
**Amendment (2026-06-12, PRD-CAP-01A):** implementing **D-33** as corrected by **D-33-E1** — the *Tenant Workspace* terminology alias (vocabulary only; the Core Invariants are untouched verbatim), the **MembershipsForPrincipal** operation added to the API Contract (D-33-E1 Item 2; implementation deferred to the API Gateway / frontend-integration execution PRD), and the D-33 audit events named under *Audit Requirements*.
**Amendment (2026-07-06, PRD 07D-2b.2-A):** adding the **recovery-core lifecycle vocabulary** — the `Quarantined` lifecycle state (isolation-class safety hold; evidence-preserving; non-routable → *unavailable*; sole egress `Decommissioned`); the `Verifying|Provisioning|Failed → Quarantined` transitions and the removal of the `Ready → Decommissioned` direct transition (a `Ready` tenant is `Suspended` first); a new *Recovery & Compensation* section (retry-resume eligibility, ownership-proof-gated de-provisioning with no silent DROP and Control-DB-non-droppable rules, read-only orphan scan, and the `ReassociateDatabase` current-state guard); the four operations `RecoverTenant` / `QuarantineTenant` / `DeprovisionTenantDatabase` / `ScanForOrphans` in the API Contract and the IC-005 authentication enumeration; and recovery-class *Audit Requirements*. **Additive; the four Core Invariants are untouched verbatim.** This amendment PRECEDED implementation (contracts precede code): the `Quarantined` code path, the recovery operations, the reassociate guard, and the registry decommission catch-up (`allowed_from += Failed, Quarantined`) **landed** in PRDs **07D-2b.2a / 07D-2b.2b** (merged to `main` at `39ee332`). No DDL, DTO field, or durable quarantine-reason column is introduced (the quarantine reason lives in the audit/event trail).
**Amendment (2026-07-17, PRD B5-BLK-6C-A):** implementing Dan's **Option A** audit-obligation reconciliation (`DECIDE B5-BLK-6C-A OPTION A`). The existing *MembershipsForPrincipal* audit MUST (D-33 workspace-related audit events) is **preserved and homed**: the *Audit-Section Extension* gains the gateway-edge **success-access subclass (3b)** — action `workspace_memberships_read`, **API Gateway emitter**, **Control-DB operational audit** home, references-only minimum shape — mandating **exactly one** event per successful self-scoped enumeration, **including a successful empty enumeration**. The four gateway-edge denial/anomaly classes and the router-edge routing-decision subclass (3a) are unchanged. **Additive; the four Core Invariants are untouched verbatim.** Contract-only (contracts precede code): runtime emission remains pending **B5-BLK-6C-B**; B5-BLK-6C-A adds no runtime implementation and closes no blocker.
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
| **Quarantined** | Isolation-class safety hold: verification detected an isolation anomaly, recovery/compensation classified the tenant's database as unsafe (non-empty orphan, fingerprint mismatch), or compensation failed. The tenant and any associated physical database are **preserved as evidence**; tenant-scoped requests denied. **No automatic path back to service.** | No (explicit deny) |
| **Decommissioned** | Offboarded; removed from active routing; data retained/archived per policy. | No |

**Allowed transitions:**
- `Registered → Provisioning → Verifying → Ready`
- `Verifying → Failed` (unreachable or schema-incompatible)
- `Verifying → Quarantined` (isolation-class anomaly detected during verification — automatic, control-plane-classified)
- `Failed → Verifying` (retry after remediation)
- `Provisioning → Quarantined` and `Failed → Quarantined` (audited control-plane quarantine: unsafe-content classification during recovery/scan, or failed compensation)
- `Ready → Suspended` and `Suspended → Verifying → Ready` (reactivation re-verifies)
- `Registered | Provisioning | Suspended | Failed | Quarantined → Decommissioned`
- **`Quarantined` has exactly one egress: `Quarantined → Decommissioned`. There is NO transition from `Quarantined` toward `Verifying` or `Ready`, ever.** The prior `Ready → Decommissioned` direct transition is **REMOVED** — a `Ready` tenant MUST be `Suspended` before decommissioning.

Re-driven onboarding of a tenant still in `Provisioning` is a resumption **within** the first transition chain, not a new transition. Automatic resumption is permitted ONLY from `Provisioning` (see *Recovery & Compensation*); `Failed` requires an explicit, audited recovery operation; `Quarantined` MUST NOT resume.

Every transition MUST be control-plane-authorized and audited (see *Audit Requirements*). Transitions MUST be idempotent where re-issued with the same target state.

## Tenant Readiness States
- **Readiness is a derived signal:** a tenant is **ready** only in the `Ready` state; all other states are **not-ready**.
- IC-005 routing MUST treat the readiness signal as authoritative and MUST route only to `Ready` tenants.
- Not-ready states MUST be distinguishable to callers with defined semantics: `Provisioning`/`Verifying` → *retry later*; `Suspended` → *administratively disabled*; `Failed` | `Quarantined` → *unavailable*; `Decommissioned`/unknown → *not found*. These MUST NOT leak another tenant's existence or internal detail beyond what the caller is authorized to know. `Quarantined` deliberately reuses the `Failed` *unavailable* class; no internal quarantine or isolation-incident detail is disclosed to callers (no new denial class is introduced).
- *Non-normative (implementation status): the as-built Database Router today maps any unrecognized lifecycle state to the fail-closed retry-later denial; tightening `Quarantined` to the *unavailable* denial above is a deferred router-side slice. This contract defines the target semantic now — the interim fail-closed behavior is not a contract deviation.*
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
- **Quarantined tenant:** a tenant enters `Quarantined` when (a) verification classifies an isolation-class anomaly, (b) recovery or orphan classification finds the associated database unsafe to touch (content beyond the bootstrap schema, or identity/fingerprint conflict), or (c) a compensation (de-provisioning) attempt fails. **Isolation-class anomalies MUST quarantine automatically at classification time**, so that a tenant resting in `Failed` is by construction non-anomalous; a recovery operation MUST nonetheless re-classify from the audit trail before resuming (defence in depth for records predating this rule). Quarantine is **evidence-preserving**: the registry record and the physical database (if any) MUST be retained unmodified for investigation. All tenant-scoped requests MUST be denied with the *unavailable* semantic. Exiting quarantine is a manual, audited decommissioning decision — **never** an automatic retry, re-verification, or compensation.

## Recovery & Compensation
*Added 2026-07-06 under PRD 07D-2b.2-A. Additive: the Core Invariants and all prior sections are unchanged. Defines the contract semantics for resuming interrupted onboarding, recovering failed tenants, quarantining unsafe tenants, and reclaiming orphaned tenant databases. Implementation landed in PRDs 07D-2b.2a / 07D-2b.2b (merged `main` `39ee332`; see the header Amendment note).*

**Retry-resume eligibility.**
- `Provisioning` (interrupted before verification): automatic resumption by re-driving the onboarding sequence is permitted — provisioning MUST be existence-checked and schema application MUST be idempotent and atomic, so a resumed run converges without duplicating effects.
- `Failed`: resumption ONLY via an explicit, audited **RecoverTenant** operation, which MUST re-classify the failure from the audit trail before re-entering `Verifying`. Isolation-class history MUST route to `Quarantined` instead — never resume.
- `Ready`: re-onboarding is a no-op (idempotency; no state change, no re-provision).
- `Quarantined` / `Suspended` / `Decommissioned`: onboarding and recovery MUST be refused (fail closed). `Suspended` reactivation remains the existing `ReactivateTenant` path.

No recovery or compensation operation MAY set `Ready` directly; recovery re-enters `Verifying` and readiness is decided **solely by the verification gate** (preserving the sole-readiness-writer rule).

**Compensation (tenant-database de-provisioning).** De-provisioning a tenant database is an explicit, audited control-plane operation. It MUST NEVER run implicitly (**no silent DROP** on any failure path). Before any destructive action the control plane MUST establish an **ownership proof** comprising at least: (1) the authoritative registry record exists and its lifecycle state is one of `Provisioning | Failed | Quarantined`; (2) the target database name is **recomputed** from the tenant identifier by the registry-authoritative rule (D-07; never caller-supplied), lies inside the tenant-database namespace, and is distinct from the Control database; (3) the recorded database-association reference has the canonical tenant shape; (4) the database content is verified **empty or bootstrap-only**; (5) no other tenant's recorded distinctness evidence identifies the same physical database. Failure of ANY element fails closed: no DROP, a failure audit record, and quarantine of the tenant where applicable, with manual/operator follow-up. A database with content beyond bootstrap MUST NOT be dropped — it is preserved as evidence and the tenant quarantined. **The Control database MUST never be a de-provisioning target** (element 2). Compensation is never automatic.

*"Bootstrap-only"* means the database contains only platform-applied bootstrap schema, seed, and verification artifacts — nothing else.

*As-built content census (07D-2b.2b).* The bootstrap-only check surfaces **all physically-stored content** so nothing beyond bootstrap can hide: ordinary tables are row-counted, while materialized views, foreign tables, and large objects are surfaced as **evidence** (never counted as bootstrap-safe), and any allowed-name relation that is not a countable ordinary table fails closed as evidence. Bootstrap-only therefore admits only the platform-applied `schema_version` rows, exactly one `system_primary` seed agent, zero rows in the business/lineage/ownership/link tables, and unrestricted verification-sentinel rows. The census runs under the control-plane inspection identity and **assumes catalog-wide row visibility** (an RLS-bypassing / superuser-equivalent admin role); a row-restricted identity could under-count and is out of scope for this proof. Audit records for these operations carry references only under the [IC-001](IC-001-Global-Startup-Contract.md) Global Audit Representation Rule (no secrets or PII).

**Orphan detection.** Detecting candidate orphans (physical databases without a `Ready` owner, registry records without databases, association/identity mismatches) MUST be a **read-only** scan that produces a report; the scan itself changes no state and drops nothing. Acting on a finding is always a separate, explicit, audited operation under the rules above. A database with **no registry record** MUST never be touched (it may be foreign).

**Registry state vs physical existence.** The lifecycle state is the Control-DB registry's authoritative view (D-07); physical-database existence is *evidence*, observed by verification and the scan. Divergence between the two is classified under this section — it never silently mutates lifecycle state, and compensation never deletes the registry record (`Decommissioned` retains it per the existing retention rule).

**Re-association guard.** `ReassociateDatabase` MUST validate the tenant's **current** lifecycle state BEFORE entering `Verifying`; it MUST be refused for `Quarantined` and `Decommissioned` tenants (fail closed). Re-association MUST NOT be an escape hatch from `Quarantined` toward `Ready`.

## Multi-Database Isolation Guarantees
- One physically separate PostgreSQL database per tenant; never shared (Invariant 4).
- One request → one active tenant (Invariant 1) → one database (Invariant 2); no cross-tenant routing and no spanning queries (Invariant 3).
- The **bootstrap system identity** (D-01, Phase 0) is control-plane-scoped and MUST NEVER resolve or open a tenant database.
- Tenant database access MUST use that tenant's own credentials, resolved via the **D-14 reference-based secret-store abstraction** (never raw credentials); a control-plane connection MUST NOT be reused to read or write tenant data.
- A failure or compromise of one tenant's database MUST be contained to that tenant.
- **Cross-tenant aggregation is not a routing operation.** If ever required, it MUST be performed as explicit, audited, per-tenant control-plane reads — never a cross-database join and never a single spanning request.

## Authentication Dependencies on IC-005
- IC-002 **consumes**, and does not define, authentication. Per IC-005:
  - **Tenant lifecycle/management operations** (register, verify, activate, suspend, reactivate, decommission, re-associate, recover, quarantine, de-provision, orphan-scan) are **control-plane operations** authenticated via **internal platform identities** (D-03) under the runtime model (OIDC + stateless JWT, D-05). They are control-plane-authorized, not tenant-federated.
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
- **Recovery-class operations** — `QuarantineTenant`, `RecoverTenant`, and `DeprovisionTenantDatabase` — MUST be audited under the rules above (actor, tenant id, action, from-state → to-state where applicable, timestamp, correlation id; references only; append-only). Operations with duration MUST emit a **start** record and **exactly one terminal** (completed/failed) record per attempt. De-provisioning audit fulfils the existing D-15 provisioning/de-provisioning obligation above. *(Non-normative: the operational event vocabulary — `TenantQuarantined`; `OnboardingRecovery{Started,Completed,Failed}`; `TenantDeprovision{Requested,Completed,Failed}` — is governed by its own frozen-vocabulary guards and the D-15/B-6 audit event catalogue, not by this contract.)*
- Tenant-lifecycle audit is **operational/control-plane audit**, distinct from data-provenance lineage ([IC-004](IC-004-Lineage-Contract.md)); it is control-plane-scoped and MUST NOT be written into tenant databases.
- Audit storage MUST remain standard-PostgreSQL/portable; its exact location is a control-plane detail (related to D-14 for any referenced secrets).
- **D-33 workspace-related audit events** *(added 2026-06-12, PRD-CAP-01A)* — the following control-plane audit obligations, aligned with the **Control-DB operational-audit model approved by D-34** and bound by its **Global Audit Representation Rule** (references only — never names, emails, PII, or payloads):
  - **Workspace switch** = the IC-005 tenant switch — an audited operation (event owned by IC-005; named here because the workspace alias presents it).
  - **Carrier mismatch** — audited rejection (403 `carrier_mismatch`; event owned by IC-005).
  - **Tenantless-CONTROL carrier anomaly** — the mandatory `CarrierOnControlAnomaly` event (D-33-E1 Item 1; specified in IC-005 *Workspace Terminology & Carriers*).
  - **MembershipsForPrincipal** calls MUST be audited (actor, subject principal reference, timestamp, correlation id — references only). *Homed 2026-07-17 under B5-BLK-6C-A (Dan-authorized Option A): this obligation is bound by the gateway-edge success-access subclass **(3b)** in the *Audit-Section Extension* below — action `workspace_memberships_read`; API Gateway emitter; Control-DB operational audit.*
  - *Scope note:* the broader audit-section extension required by D-34/D-36 (administrative/runtime/export/ownership audit classes and Control-DB audit retention) is a **separate pending amendment** tracked in the register's closing note (Contract Amendment Inventory R2) — it is **not** executed by PRD-CAP-01A.

## Audit-Section Extension (D-34/D-36 — Inventory R2)
*Added under PRD 05, completing the audit homes that `Audit Requirements` (scope note) deferred. Additive: Core Invariants and all prior Audit Requirements are unchanged. Every shape below obeys the **Global Audit Representation Rule** (contract law at [IC-001](IC-001-Global-Startup-Contract.md), D-34-R2 §7): **references only** — never names, emails, PII, payloads, secrets, or tenant business content. Identity is resolved at presentation time via D-03.*

**Residency rule (binding on this section).** Operational/control-plane audit is **Control-DB resident** (D-34-R2 O1). **Ownership audit follows record residency** (IC-008 Audit Residency Rule): global-record ownership events → Control DB; tenant-record ownership events → that tenant's DB. **No audit record spans or joins databases, and no audit-persistence path performs a cross-Control/tenant read** (Core Invariants 1–4); persistence is each-DB-local.

**Class homes (completing the D-34-R2 §6 taxonomy).**

**(1) Administrative Audit — Control-DB resident.** Two distinct record shapes:
- **Lifecycle Audit Record** (tenant lifecycle transitions, database (re)association, provisioning — already required by *Audit Requirements* above; restated here only to fix the class home). Fields: `audit_id`, `actor_ref`, `tenant_ref`, `action`, `outcome`, `from_state`, `to_state`, `timestamp`, `correlation_id`. *`from_state`/`to_state` are lifecycle **state labels** (governance metadata, not PII), consistent with the existing Lifecycle Audit Record (DTO Contract) and the Representation Rule.* Append-only.
- **Ownership/Administrative Audit Record** (ownership transfers of **Control-domain / global** records — IC-008 *Ownership Audit Rule*). Fields: `audit_id`, `record_ref`, `ownership_ref` (prior→new as references), `actor_ref`, `tenant_ref` (where applicable), `action` ∈ {assign, transfer, re-own}, `outcome`, `timestamp`, `correlation_id`. **No state fields.** Shape aligns with [IC-008](IC-008-Ownership-Contract.md) *Ownership Audit Record*. Append-only.

**(2) Tenant-resident Ownership Audit — tenant-DB resident.** Ownership events on **tenant-resident** records (initial assignment, transfer, lapsed-eligibility re-owning — IC-008 *Ownership Audit Rule*, D-36-R2 §7). Resident in the **record's own tenant database**; **never crosses residency** (D-36-R2 V9). Shape = the IC-008 *Ownership Audit Record* (`audit_id`, `record_ref`, `ownership_ref`, `actor_ref`, `action` ∈ {assign, transfer, re-own}, `outcome`, `timestamp`, `correlation_id`); **`tenant_ref` is implicit in residency** — the hosting tenant DB fixes the tenant — and need not be stored separately (IC-008:113). Governance metadata, **distinct from IC-004 lineage and tenant business data**; MUST NOT be written outside its own tenant DB.

**(3) Runtime Operational Audit — Control-DB resident.** `RouteDenied`, `CarrierMismatch`, `CarrierOnControlAnomaly`, `IsolationAnomaly` — the runtime anomaly/denial classes emitted at the request edge (emission owned by IC-005/IC-010 — see IC-005 *Runtime Operational Audit Emission*; this section is their **residency/retention home**). Fields: `audit_id`, `action` ∈ {RouteDenied, CarrierMismatch, CarrierOnControlAnomaly, IsolationAnomaly}, `correlation_id`, `outcome`, `actor_ref` (optional), `tenant_ref` (optional), `carrier_ref` (optional; **opaque, length-bounded** carrier identifier per IC-005:116 — never parsed/resolved), `timestamp`. Control-DB resident; emitted **once per correlation id** (single-edge — IC-010 §J). *(Field set matches the as-built `GatewayAuditEvent`, `backend/api_gateway/models.py` / `gateway.py:85–94`.)*

**(3a) Runtime Operational Audit — Database Router edge (router-edge routing-decision subclass; added 2026-07-13, DBR-AR-2A).** Additive subclass **within class 3** (Runtime Operational Audit). The gateway-edge event set in (3) above is **unchanged and remains gateway-owned**; this subclass homes the **router-edge routing-decision events**, whose emission edge is reconciled in [IC-005](IC-005-Authentication-Routing-Contract.md) *Runtime Operational Audit Emission*:
- **Events (exact, frozen vocabulary):** `action` ∈ {`Route`, `RouteControl`, `RouteDenied`, `IsolationAnomaly`} — **the Database Router is the sole emitter** of this subclass, emitting **exactly one event per completed or denied `route()` invocation** (including the pre-target denials `tenant_routing_unavailable` and `no_active_tenant`). Semantics: `Route` = tenant route resolved and handed back under one-request/one-tenant/one-database; `RouteControl` = Control-domain route resolved, no tenant database connection; `RouteDenied` = router-edge denial carrying exactly one code from the canonical router public-code vocabulary; `IsolationAnomaly` = authenticated/resolved tenant divergence or equivalent routing-isolation anomaly (D-30 L3/L4).
- **Event identity is (edge/subclass, action).** `RouteDenied` and `IsolationAnomaly` appear in both the gateway-edge set (3) and this router-edge subclass as **different events on different edges**. **No event is emitted by more than one component.** Gateway-edge events and Database-Router-edge events are different subclasses with different sole emitters. The Authentication Router is **not an emitter of record** for any class-3 event (detection and signalling only — IC-005).
- **Fields (router-minted; as-built `RoutingAuditEvent`, `backend/database_router/models.py`):** required `event_id` (router-minted UUID; the idempotency identity), `event_version` (integer, additive-only evolution), `occurred_at` (UTC ISO-8601, informational only — timestamps never define durable ordering), `correlation_id`, `actor_ref`, `action`, `outcome` (`success` / `denied:<public_code>` / `anomaly:<code>`), `source_service`, `source_version`; optional references-only `request_ref`, `tenant_ref` (as-built `target_ref`), `resolved_tenant_ref`, `public_code` (null on success — success events never carry a denial code), `error_class` (bounded internal vocabulary), `association_store_ref` + `association_version` (the D-14 reference — never a resolved value), `lane`. `recorded_at` is **store-assigned at persistence time** (a future durable-store field, never router-minted). No hash-chain field.
- **Representation Rule (references only):** an event never carries raw DSNs or connection strings, secret values, key material, JWTs or token-shaped strings, bearer tokens, authorization headers, request/response bodies, tenant business content or tenant result data, names/emails/PII, database hostnames, physical database names, connection topology, or live connection/routing objects (or any serialization of them).
- **Residency & storage:** Runtime operational audit remains **Control-DB resident**. The exact storage implementation remains a Control Plane detail. **DBR-AR-2A adds no durable persistence** — the as-built emission is in-memory only; the durable record is governed by `docs/runtime/dbr_ar_2_durable_routing_audit_contract.md` (DBR-AR-2 remains a separate open follow-on). Tenant lifecycle, provisioning, readiness, ownership, import, lineage, and routing authority are unchanged by this subclass.

**(3b) Runtime Operational Audit — Gateway-edge success-access subclass (`workspace_memberships_read`; added 2026-07-17, B5-BLK-6C-A, Dan-authorized Option A).** Additive subclass **within class 3** (Runtime Operational Audit; Control-DB resident), homing the audit MUST that *Audit Requirements* (D-33 workspace-related audit events) states for **MembershipsForPrincipal**. It is a **separate success-access subclass**: the four gateway-edge denial/anomaly classes remain exactly the historic four — `RouteDenied`, `CarrierMismatch`, `CarrierOnControlAnomaly`, `IsolationAnomaly` — unchanged, and the router-edge routing-decision subclass (3a) is unchanged.
- **Mandate (exactly one event).** A successful self-scoped **MembershipsForPrincipal** enumeration MUST emit **exactly one** references-only operational audit event with `action == "workspace_memberships_read"`. A successful **empty** enumeration is still a successful enumeration and MUST emit the event. Never zero events, never two, never one event per returned membership record, never one event per tenant — the audit records the operation, not the number or contents of returned memberships.
- **Emitter.** **The API Gateway is the emitter**; it is the **sole emitter of this success event** (single edge). The Auth Router remains detection and signalling only. The Database Router's router-edge subclass (3a) is unaffected.
- **Home.** The event resides in **Control-DB operational audit** as a Gateway-edge success-access subclass. It is a success-access event and MUST NOT be relabelled or classified as a denial, anomaly, or routing event.
- **Shape (minimum, references only).** `audit_id`, `action`, `actor_principal_ref`, `subject_principal_ref`, `correlation_id`, `occurred_at`, `outcome`, `event_version` — with `action == "workspace_memberships_read"`, `actor_principal_ref` == the authenticated actor, `subject_principal_ref` == the enumerated subject, `outcome == "success"`, `event_version == 1`. For the currently bound self-scoped operation, `actor_principal_ref == subject_principal_ref`; the CONTROL-on-behalf-of-subject form is contract-preserved but is not runtime-bound by B5-BLK-6B and is not implemented by B5-BLK-6C-A.
- **Prohibited event content.** Tenant database identity, database name, DSN, secret, credential, connection string, raw membership rows, tenant business data, provider body, router internals, stack trace. The event MUST NOT contain the returned tenant-membership collection.
- **Non-emission.** A denied, unauthenticated, unavailable, malformed, or isolation-anomaly request does not emit this success event (401 unauthenticated, 403 forbidden, 403 `isolation_anomaly`, 404 not found, 503 `unavailable`, malformed Control-Plane response, timeout, internal exception); existing denial/anomaly audit semantics remain separate and unchanged.
- **Runtime status (contracts precede code).** B5-BLK-6C-A authorizes and defines the later **B5-BLK-6C-B** runtime implementation. B5-BLK-6C-A does not itself implement or prove runtime emission — the `workspace_memberships_read` event is not yet emitted by the current runtime; runtime binding follows in B5-BLK-6C-B. B5-BLK-6C-A adds no runtime implementation and closes no blocker; **B5-BLK-6 remains OPEN**. Self-scoping, the references-only rule, tenant isolation, and one request → one active tenant → one database are not weakened.

**(4) Export Audit — tenant scope (Control-DB resident operational events).** Tenant-initiated export **operational events** — `action` ∈ {ExportRequested, ExportCompleted, ExportFailed}. Fields: `audit_id`, `actor_ref`, `tenant_ref`, `record_ref` (optional), `action`, `outcome`, `timestamp`, `correlation_id`. **The exported content is NEVER audited** (Representation Rule rule 3): no `payload`/`content` field exists. These operational events are **Control-DB resident** (control-plane operational audit). *Any tenant-record-residency governance aspect of export, if ever needed, is deferred to the export feature contract and is out of scope here* — this section homes only the operational events, with a single deterministic residency (no persistence-time residency choice).

**(5) Import Audit — runtime extension.** The import lifecycle events `ImportRequested / Completed / Failed` remain homed in [IC-003](IC-003-Import-Contract.md) *Audit Requirements* and are **not redefined or duplicated here**. This section records only that a **runtime/operational** surfacing of import (e.g., a route-level denial during import dispatch) falls under **Runtime Operational Audit** (class 3) — no new import event is introduced.

**Retention.** Control-DB-resident audit follows the platform retention policy already contract law at [IC-001](IC-001-Global-Startup-Contract.md) (Inventory R2 item 4; D-24-segmented; concrete values under D-08; default retain-all). **Tenant-resident ownership audit** follows the **tenant's own** D-24 segmented retention under per-tenant D-08 parameters; mirroring the IC-001 Control-DB rule, **erasure of tenant business data never compels erasure of the reference-only governance metadata that references it** (the audit record holds references only, never the erased content). Retention values are business/legal parameters, not architecture.

**DEC-11 resolution.** With the tenant-resident ownership-audit class now contractually homed (class 2 above), the blocker recorded as **DEC-11** — *"the API Gateway PRD must not bind ownership-audit DTO residency until the IC-002 ownership-audit-section extension lands"* (ADR IC-009-ADOPT) — is **resolved by the landing of this section.** Binding the IC-009 `AuditEventDTO` residency to this home is a downstream portal/gateway execution item; this section makes that binding *permissible*, it does not perform it.

**Execution-deferred (contracts precede code).** Audit **persistence** (the Control-DB and tenant-DB audit stores), the gateway's audit **sink** wiring (today a no-sink port), and any emission **tests** beyond those already passing are **execution-PRD items** — none authorized here.

## API Contract
> Specification of **operations and semantics** only — no transport code. The surface is a **control-plane API** (REST/HTTP-style); concrete method/path bindings are a minor remaining detail. Denial semantics MUST distinguish *forbidden* (authz), *not found* (unknown/decommissioned), *not ready* (provisioning/verifying), *administratively disabled* (suspended), and *unavailable* (failed/quarantined).

| Operation | Purpose | Caller (authz) | Result / state effect | Idempotent |
|---|---|---|---|---|
| **RegisterTenant** | Create the authoritative tenant record + associations | Control-plane operator (internal identity) | `→ Registered` | Yes (by tenant id) |
| **GetTenantStatus** | Return lifecycle state + readiness | Control-plane / authorized member | none | Yes |
| **MembershipsForPrincipal** | Enumerate a subject principal's tenant memberships — self by default; CONTROL may specify another subject (the workspace-selector source, D-33) | The principal itself (**self-scoped**) or CONTROL; **audited** | none — returns **membership records only** (tenant id, role, display ref), **never tenant-DB data** | Yes |
| **VerifyTenant** | Run connectivity + schema-version checks | Control-plane operator | `Verifying → Ready` or `→ Failed` | Yes |
| **ActivateTenant** | Promote a verified tenant to routable | Control-plane operator | `→ Ready` | Yes |
| **SuspendTenant** | Administratively disable; preserve data | Control-plane operator | `Ready → Suspended` | Yes |
| **ReactivateTenant** | Re-verify and restore service | Control-plane operator | `Suspended → Verifying → Ready` | Yes |
| **DecommissionTenant** | Offboard; remove from routing; retain/archive | Control-plane operator | `Registered \| Provisioning \| Suspended \| Failed \| Quarantined → Decommissioned` (a `Ready` tenant is `Suspended` first — see *Allowed transitions*) | Yes |
| **ReassociateDatabase** | Point a tenant at a restored/relocated DB | Control-plane operator | `→ Verifying` (then `Ready`); **refused for `Quarantined`/`Decommissioned`** (see *Recovery & Compensation* — Re-association guard) | Yes |
| **RecoverTenant** | Explicitly recover a `Failed` tenant: re-classify from audit, then re-verify | Control-plane operator | `Failed → Verifying → Ready/Failed`; anomaly-class history → `Quarantined` | Yes |
| **QuarantineTenant** | Place an unsafe tenant in the evidence-preserving hold | Control-plane operator (also set **automatically** on isolation-class anomaly) | `Provisioning \| Failed → Quarantined` (`Verifying → Quarantined` on the automatic edge) | Yes |
| **DeprovisionTenantDatabase** | Ownership-proof-gated compensation (drop an empty/bootstrap-only tenant DB) | Control-plane operator | no lifecycle transition on the success path; failure → `Quarantined`. MUST satisfy the *Recovery & Compensation* ownership-proof preconditions | Yes (absent target → no-op) |
| **ScanForOrphans** | Read-only orphan/divergence report | Control-plane operator | none (report only) | Yes |

*`MembershipsForPrincipal` (added 2026-06-12 per D-33-E1 Item 2) is **contract-owned here**; its implementation is deferred to the API Gateway / frontend-integration execution PRD — contracts precede code.*
*The `MembershipsForPrincipal` operation's runtime binding landed under B5-BLK-6B; the mandated `workspace_memberships_read` success-audit emission is defined by B5-BLK-6C-A (Dan-authorized Option A — Audit-Section Extension class 3b) and its runtime binding follows in **B5-BLK-6C-B**. B5-BLK-6C-A adds no runtime implementation.*
*`RecoverTenant` / `QuarantineTenant` / `DeprovisionTenantDatabase` / `ScanForOrphans` (added 2026-07-06 per PRD 07D-2b.2-A) are **contract-owned here**; their implementation **landed** in PRDs 07D-2b.2a / 07D-2b.2b (merged `main` `39ee332`).*

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
