# IC-001 — Global Startup Contract

**Status:** Final · **Phase:** Architecture Planning · **Type:** Specification only (no implementation)
**Status note:** All architecture decisions governing global startup are resolved and recorded in [Architecture-Decision-Register.md](../docs/Architecture-Decision-Register.md) — through D-12, plus the **D-31** Global Directory Residency amendment. **Final** for MVP architecture; residual items are implementation/operational (DR re-seeding, multi-node HA transition, concrete encodings) and do not reopen the architecture.
**Amendment (2026-06-12, PRD-CAP-01B):** implementing **D-35-R2** (Global Deal Directory at all five touchpoints; discovery-metadata categories; Tenant Anonymity Rule; Publication Boundary Rule) and **D-34-R2** as corrected by **D-34-E1** (operational-audit taxonomy homes for the global classes; the Global Audit Representation Rule promoted to contract law). No startup, readiness, or bootstrap behavior changes; no frozen invariant altered.

## Purpose
Define how the platform initializes at the **global / control-plane level** before any tenant is served. Establishes the contract for bringing up the Control Database, API Gateway, Authentication Router, and Database Router into a known-good, ready-to-serve state.

## Bootstrap Phases (resolves D-01)

Startup proceeds in **two phases** to break the IC-001 ⇄ IC-005 bootstrap cycle. Per [D-01-Bootstrap-Cycle-Resolution.md](../docs/D-01-Bootstrap-Cycle-Resolution.md), the approved resolution is **A + B**: a bootstrap/system identity combined with a static, infrastructure-owned trust-anchor configuration.

- **Phase 0 — control-plane startup (pre-Control-DB).** The control plane authenticates as a single **bootstrap system identity**, verified **without any database lookup** against a trust anchor sourced from static, infrastructure-owned configuration (file and/or environment templates that *reference* a secret store; secrets are referenced, never inlined). Only control-plane/startup operations are permitted. **No tenant routing is possible during Phase 0**, and the system identity can never resolve or route to a tenant database.
- **Phase 1 — runtime (post-Control-DB).** Once the Control Database is online, schema-checked, and routing metadata is loaded, the platform transitions to the full runtime authentication and tenant-routing model owned by [IC-005](IC-005-Authentication-Routing-Contract.md). Phase 0 is closed once Phase 1 is active.

### Control DB startup ordering
1. Load the bootstrap trust anchor and the minimal static routing seed (infrastructure-owned config/env).
2. Control plane authenticates as the bootstrap system identity (Phase 0; cryptographic/static verification, no DB lookup).
3. Bring up the Control Database; verify connectivity and schema-version compatibility.
4. Load routing metadata from the Control Database.
5. Transition to Phase 1 and close Phase 0.

### Failure behavior
- If the trust anchor or static seed is **missing or invalid**, the control plane MUST refuse to start (there is no degraded Phase 0).
- If the Control Database is **unreachable or schema-incompatible**, startup remains in Phase 0, MUST NOT transition to Phase 1, and reports **not-ready** (per the D-10 three-state model; schema compatibility per D-12).
- The Phase 0 path MUST remain minimal and audited; the one-time manual break-glass provisioning (Option D) MUST be disabled after first boot, with a means to assert in production that Phase 0 is closed.

## Global Readiness (D-10)
The platform exposes a **three-state** global readiness signal:
- **Ready** — Phase 1 active, Control Database healthy, Control-DB schema compatible (D-12).
- **Degraded** — serving healthy tenants but impaired (an elevated rate of tenant-DB failures, or a non-critical control-plane dependency down). **Degraded is observability/alerting only and MUST NOT deny routing to healthy tenants** (consistent with per-tenant independence, D-16).
- **Not-ready** — Phase 0, Control Database unreachable, or Control-DB schema incompatible (D-12).

Global not-ready is reserved for **shared-dependency (Control DB / Phase-0) failure**; individual tenant-DB outages are per-tenant not-ready (D-16), never global. Readiness endpoints MUST be **access-controlled and minimally disclosing** (no leak of tenant counts/identities to unauthorized callers).

## Tenant Registry Enumeration (D-11)
Enumeration is **hybrid**: a bounded **working set** of tenant routing metadata is warmed at startup; the remainder is **lazy-loaded on first request** and cached, with **background refresh**. Therefore **global ready = registry reachable, not fully enumerated** (D-10). Resolution is **registry-authoritative** (D-07) and the cache MUST be tenant-scoped and **invalidated on re-association** (IC-002 `ReassociateDatabase`) so a relocated tenant DB is never routed stale. Unknown vs. not-yet-loaded tenants MUST be indistinguishable from known-but-unauthorized to callers (consistent denial semantics).

## Control-DB Schema Compatibility (D-12)
The control plane declares a **supported Control-DB schema range** (expand/contract). At startup and at runtime:
- **Within range** → may be Ready (D-10).
- **Outside range** (below floor or above ceiling) → **global not-ready** (fail-safe); the platform MUST NOT serve tenant routing on an incompatible Control-DB schema.

Control-DB migration is a **controlled, audited, separate step** — never an implicit startup side effect. This mirrors the tenant-DB approach (D-17) applied to the Control DB and enables zero-downtime control-plane rolling deploys.

## Global Discovery Platform (D-31, extended by D-35)
The Control Database is also the **Global Discovery Platform**. In addition to control-plane metadata, it hosts:
- **Global Startup Directory**
- **Global Investor Directory**
- **Global Deal Directory** *(added 2026-06-12 per D-35-R2 under PRD-CAP-01B; joins under D-31's identical, absolute residency terms — D-31 is extended, not reopened)*

Residency is absolute (D-31): **all Global Directories — Startup, Investor, and Deal — reside exclusively in the Control Database**; **tenant-owned records (including imported copies) reside only in tenant databases**; **no tenant-owned data resides in the Control Database**; and **no global directory records reside in tenant databases**. The Control Database remains outside tenant operations — one request still resolves to the Control DB **or** exactly one tenant DB, never both.

The Global Directory schema is part of the Control Database and therefore falls under **Control-DB schema compatibility (D-12)**. Directory access authorization is **governed by IC-005**: authenticated, auditable, and never exposing tenant-owned records.

### Global Deal Directory (D-35-R2)
A Global Deal Directory record is a **discovery record only** — a Control-managed opportunity consisting solely of approved global discovery metadata. It is **not**: a tenant deal, a pipeline record, commercial terms, or a negotiation record; it MUST NOT contain tenant-owned deal data, tenant-confidential data, tenant pipeline data, tenant negotiation data, or tenant commercial terms. `Global Deal ≠ Tenant Deal` — the existence of either never implies the other; after import (IC-003) they evolve independently. Deal **recommendation** is human/control workflows only (AI behavior is IC-006-gated); deal **discovery** creates no ownership, no import, and no synchronization.

### Discovery-Metadata Categories (D-35-R2 §4/§5)
A global directory record may consist **only** of these four categories — each **tenant-anonymous** under the Tenant Anonymity Rule below. *(Stated for **all** global directory records — a deliberate strengthening generalization of D-35-R2's deal/publication-record wording, consistent with D-31's global-reference-data-only residency.)*
- **Global Data** — data originating in Control scope (created or curated by control-plane workflows).
- **Reference Data** — data originating from public or external non-tenant sources.
- **Discovery Data** — non-sensitive attributes that identify and describe the opportunity or entity for search/browse/review.
- **Directory Data** — directory-management metadata (categorization, freshness, publication state).

Any **tenant-attributed** action record (import initiation, directory views if ever recorded) is **not** discovery metadata and flows exclusively through D-34-R2 audit governance (reference-only, access-controlled, never tenant-facing).

### Tenant Anonymity Rule (D-35-R2 — mandatory)
Global directory/publication records MUST NOT contain: `tenant_id`, `tenant_name`, `tenant_code`, `tenant_reference`, `membership_reference` — **or any field that references, names, or is attributable to any tenant or tenant activity** — unless explicitly governed by a future ADR. A curated or market opportunity MUST be publishable without revealing which tenant (if any) sourced, held, or pursued it.
*Scope note (per D-35-R2 §4):* this rule governs **directory/publication records** (the tenant-facing, cross-tenant-readable surface). It does **not** apply to **audit records**, which are governance metadata carrying `tenant_ref` by design under the Global Audit Representation Rule below (reference-only, access-controlled, never tenant-facing). The two record classes must never be conflated.
*Execution-PRD acceptance items (contracts precede code):* CI/unit enforcement of this rule on **every directory write/read path** — rejecting prohibited attribute keys and tenant-attributable values (`DirectoryRecord.attributes` is currently an unconstrained map).

### Publication Boundary Rule (D-35-R2 §4)
**Import is governed** (IC-003: Global → tenant copy). **Publication is not yet governed:** any operation that moves **tenant-resident information of any kind into any Global record, by any mechanism** (automated or manual, including re-keying by Control staff) MUST be **explicit, consent-based, audited, and separately governed by a future ADR**. **This contract authorizes no tenant-to-global publication.**

## Operational Audit — Global Classes & Platform Rules (D-34-R2, as corrected by D-34-E1)
*Added 2026-06-12 under PRD-CAP-01B. This section is the contractual home for the **global-scope** operational-audit classes; tenant-scoped classes are homed in IC-002/IC-003 as noted.*

**Taxonomy (D-34-R2 §6, as extended by D-34-E1 and PRD-CAP-01B §7.E).** Operational audit is Control-DB-resident (D-34-R2 O1); import lineage is tenant-resident (IC-004 — unchanged). Minimum classes:

| Class | Examples | Contractual home |
|---|---|---|
| **Administrative Audit** | tenant lifecycle, database registration, provisioning, ownership transfers of Control-domain records | IC-002 audit section (extension pending — Inventory R2) |
| **Directory Audit** | every `GlobalDirectory` mutation (create/update/remove of Startup/Investor/Deal directory records) | **This contract** |
| **Publication Audit** | directory publication, approval, withdrawal | **This contract** |
| **Export Audit — global scope** | directory export, control-plane reporting export | **This contract** |
| **Export Audit — tenant scope** | tenant-initiated export *operational events* (content never audited) | IC-002 audit extension (pending — Inventory R2) |
| **Import Audit** | ImportRequested / Completed / Failed | IC-003 *Audit Requirements* (already contracted) + IC-002 runtime extension (pending) |
| **Runtime Operational Audit** | RouteDenied, CarrierMismatch, `CarrierOnControlAnomaly`, IsolationAnomaly | IC-005 / IC-002 (D-33 events landed under PRD-CAP-01A; remainder pending) |

**Directory-mutation audit status (D-34-E1):** `GlobalDirectory` mutations are currently **unaudited** (Not Implemented — the D-34 §2 inventory row was corrected by D-34-E1). *Execution-PRD acceptance items (contracts precede code):* `GlobalDirectory` mutation audit events emitting reference-only records per the rule below, plus a test asserting the emission.

**Global Audit Representation Rule (D-34-R2 §7 — platform-wide, carried verbatim into contract law).** Normative for **every** audit class in this taxonomy and for all audit defined by D-33/D-35/D-36:
1. Audit records store **references only**: `actor_ref`, `user_ref`, `tenant_ref`, `ownership_ref`, `record_ref` (and correlation/action/outcome/timestamp metadata).
2. Audit records **never** store: names, emails, display names, identity payloads, PII, authorization payloads, record payloads, secrets, or tenant business content.
3. Audit records of tenant-context operations are **governance metadata about actions, not tenant data**; they are access-controlled, reference-only, and explicitly distinct from "Tenant Deal Activity" and any other tenant business records. Exported or published *content* never appears in any audit record.
4. Identity resolution happens at **presentation time** through the **D-03 identity model**; traceability: D-03 (identities), D-14 (secrets/reference discipline), D-34 (audit architecture), D-36 (ownership references).

**Control-DB audit retention (Inventory R2 item 4 / PRD-D33-D37-V2 Minor 2).** Control-resident audit records follow a **defined platform retention/expiry policy** mirroring the segmented D-24 pattern; concrete retention values are business/legal parameters governed under the D-08 process (default: retain-all until values are named). **Per-tenant D-08 compliance parameters do NOT govern Control-DB audit records** — even where such records carry a `tenant_ref`, they are platform governance metadata about actions, not tenant data (rule 3 above); their privacy exposure is bounded by the reference-only rule, and erasure of tenant data never requires erasure of governance metadata that references it.

## Scope
- Cold-start sequence of global services (Control DB connectivity, router registration, gateway readiness).
- Control Database availability and schema-version compatibility checks.
- Global configuration and environment template loading.
- Health/readiness signaling for the platform as a whole (not per-tenant).
- Tenant registry discovery (enumerating which tenant databases exist) — handoff to IC-002.
- Hosting the **Global Discovery Platform** (Global Startup/Investor/Deal Directories — D-31, extended by D-35) in the Control Database, including the global-scope operational-audit classes (D-34-R2).
- Two-phase startup: Phase 0 (control-plane, pre-Control-DB) and Phase 1 (runtime), and the transition gate between them.
- Phase 0 authentication of the bootstrap system identity against a static, infrastructure-owned trust anchor.

## Non-goals
- Per-tenant initialization (see [IC-002](IC-002-Tenant-Startup-Contract.md)).
- Data import flows (see [IC-003](IC-003-Import-Contract.md)).
- Runtime request authentication (see [IC-005](IC-005-Authentication-Routing-Contract.md)).
- Any implementation, migration, or bootstrapping code.

## API Contract Placeholder
> The control plane exposes **readiness** (three-state, D-10), **liveness**, and **control-plane status** endpoints — access-controlled and minimally disclosing. Semantics are specified above; concrete method/path/shape are **implementation bindings** (no transport code here).

## DTO Contract Placeholder
> Shapes (fields only, no code): **global readiness state** (`ready` | `degraded` | `not-ready`, D-10), **Control-DB schema descriptor** (observed + supported range, D-12), **registry summary** (enumeration/working-set status, D-11 — non-sensitive). No secrets; no tenant data.

## Authentication Requirements
Control-plane/global startup authenticates as the **bootstrap system identity** (Phase 0), verified **without any database lookup** against a trust anchor sourced from static, infrastructure-owned configuration (resolution B). This is a system identity, not an end-user. The full runtime authentication model is owned by [IC-005](IC-005-Authentication-Routing-Contract.md) and applies only in Phase 1.
The trust anchor is carried via the **pluggable, reference-based secret-store abstraction** (D-14) — referenced, never inlined. (The concrete trust-anchor encoding is an implementation detail.)

## Authorization Requirements
The bootstrap system identity is **control-plane-scoped only** and MUST NOT be able to resolve or route to any tenant database. Phase 0 permits only control-plane/startup operations and denies all tenant-scoped requests.
Observing readiness is **access-controlled and minimally disclosing** (D-10); triggering startup/lifecycle is restricted to control-plane operators (least-privilege). Concrete role definitions are implementation bindings.

## Multi-Database Compatibility
- Control Database is the only database touched during global startup; tenant databases are **discovered, not opened**, here.
- The bootstrap system identity (Phase 0) can never resolve or open a tenant database; tenant routing is unavailable until Phase 1.
- Must run on standard PostgreSQL (AWS RDS / Azure Database for PostgreSQL / Google Cloud SQL / self-hosted).
- Startup checks must not assume a single shared database with a `tenant_id` column.
- The Control Database additionally hosts the Global Startup/Investor/Deal Directories (Global Discovery Platform, D-31 extended by D-35) — global, **tenant-anonymous** reference data only; it never holds tenant-owned data. Directory schema is covered by D-12.

## Anti-Vendor-Lock-In Requirements
- No Supabase-specific startup logic or auth.
- No Lovable-specific runtime dependencies.
- No provider-proprietary PostgreSQL extensions in startup checks.

## Resolved Decisions
- **D-10** — three-state global readiness (*Global Readiness*).
- **D-11** — hybrid registry enumeration (warm working set + lazy load; invalidate on re-association) (*Tenant Registry Enumeration*).
- **D-12** — compatible-range Control-DB schema strategy, fail-safe to not-ready (*Control-DB Schema Compatibility*).
- (Earlier) **D-01** two-phase bootstrap; **D-14** trust anchor via the reference-based secret-store abstraction.
- **D-31** — Global Directory Residency: the Control Database hosts the Global Startup/Investor Directories as the Global Discovery Platform; directory schema under D-12; access governed by IC-005 (*Global Discovery Platform*).
- **D-35** (R2) — the **Global Deal Directory** joins the Global Discovery Platform under D-31's identical, absolute residency terms (extension, not reopening); discovery-metadata categories; **Tenant Anonymity Rule**; **Publication Boundary Rule** — no tenant-to-global publication authorized (*Global Discovery Platform*).
- **D-34** (R2, as corrected by D-34-E1) — operational-audit taxonomy with this contract as the home for the global classes (Directory / Publication / global-scope Export audit); the **Global Audit Representation Rule** as platform contract law; Control-DB audit retention governance (*Operational Audit — Global Classes & Platform Rules*).

## Implementation Notes (non-architecture)
These are operational/implementation details that do **not** reopen the architecture:
- Automatic re-seeding of a wiped/replaced Control DB without re-enabling the manual break-glass path (DR runbook).
- Multi-node/HA agreement on the Phase 0 → Phase 1 transition (split-brain avoidance) — a coordination concern at implementation time.
- The concrete trust-anchor encoding and the exact supported Control-DB schema-range values.
