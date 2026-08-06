# IC-003 — Import Contract

**Status:** Final · **Phase:** Architecture Planning · **Type:** Specification only (no implementation)
**Decision basis:** Applies the approved decisions in [Architecture-Decision-Register.md](../docs/Architecture-Decision-Register.md) (D-01–D-05, D-07, D-08, D-13–D-17, D-22–D-25, the import decisions D-18–D-21 + D-09 ingress, and the **D-31** Global Directory Residency amendment). Authoritative dependencies: **IC-002** (Final), **IC-004** (Final), **IC-005** (Final).
**Status note:** All cross-cutting, dependency, and import architecture decisions are resolved and incorporated. **Final** for MVP architecture. The **D-09 AI-egress** slice remains owned by IC-006 (AI post-MVP, D-02) and does not gate import.
**Amendment (2026-06-12, PRD-CAP-01B):** implementing **D-34-R2** and **D-35-R2** — the Global-record definition extended to include the **Global Deal Directory**; **D-20 amended in part** (user-controlled re-import replaces the default-upsert re-import semantics — see *Re-Import Governance*); synchronization prohibition made explicit; lineage-preservation rule; IC-004 actor-example harmonization. The import-copy invariants are unchanged and strengthened.
Requirement keywords **MUST / MUST NOT / SHOULD / MAY** are used in the RFC-2119 sense.

## Purpose
Define how data is imported into a tenant: **copying** from a **Global record** (or, later, an external source) into the tenant's own physically separate database as a **tenant-owned copy**, under exactly one active tenant context (IC-002, IC-005), emitting lineage per [IC-004](IC-004-Lineage-Contract.md). Import is a **discrete, one-directional copy — never synchronization**.

## Core Invariants & Principles (preserved — MUST hold)
1. **Global Record ≠ Tenant Record.** The Global record (global/control-plane scope) and an imported tenant record are distinct; the tenant copy is never the Global record.
2. **Import ≠ Synchronization.** Import is a bounded copy event, not an ongoing two-way (or one-way live) sync.
3. **Import creates a tenant-owned copy.** The result is owned and governed by the tenant.
4. **Tenant changes never affect the Global record.** No write-back; the tenant copy's lifecycle is independent.
5. **Global changes never affect imported Tenant records.** A prior import is a point-in-time snapshot; later Global edits do not propagate.
6. **One request → one active tenant → one database.** Every import runs in one active tenant context, writing only to that tenant's database.
7. **Lineage emitted according to IC-004.** Every data-bearing import emits provenance.

Also binding (architecture-wide): **no shared tenant databases**; **secrets never appear in payloads, lineage, audit, or responses**; **references only, never raw credentials or payloads**.

## Import Principles
- **Copy, not link:** import produces an independent tenant-owned copy; there is no live link to the source.
- **One-directional & discrete:** a bounded ingestion event, not continuous sync (Invariant 2).
- **Decoupled ownership:** after import, the tenant record evolves independently of the Global record (Invariants 4 & 5).
- **Provenance-bearing:** every data-bearing import emits lineage (IC-004) recording origin by reference.
- **Tenant-isolated:** import writes only to the single active tenant's database (Invariant 6).
- **Reference/secret hygiene:** source credentials and payloads are never stored in lineage, audit, or responses; secrets are referenced via the D-14 abstraction.

## Scope
- The **global-to-tenant import-copy** semantics and ownership decoupling.
- **Authentication, tenant-context, and readiness** preconditions for import.
- **Lineage emission** on import (handoff to IC-004) and **operational audit** of import actions.
- **Failure behavior, multi-database compatibility, anti-vendor-lock-in.**

## Non-goals
- **Synchronization, two-way replication, or live mirroring** (Invariant 2).
- Defining the Global record's own schema or lifecycle (global/control-plane concern).
- Tenant/global startup (IC-001, IC-002), the authentication mechanism (IC-005), or the lineage data model (IC-004) — all **consumed, not defined** here.
- AI-assisted transformation (IC-006; deferred post-MVP, D-02).
- Any implementation, ETL, or migration code.

## Global-to-Tenant Import-Copy Model
- The **Global record** (D-31, extended by D-35) is a record in the **Global Startup Directory**, the **Global Investor Directory**, or the **Global Deal Directory**, residing in the **Control Database** (the Global Discovery Platform). It is **never served directly as tenant data**. *(Definition replaced 2026-06-12 per D-35-R2 under PRD-CAP-01B: Global record = Startup ∨ Investor ∨ Deal directory record.)*
- Import **copies** selected Global data into the **single active tenant's** physically separate database, producing a **tenant-owned copy** (Invariant 3). The copy is a **point-in-time snapshot**.
- After import, the Global record and the tenant copy evolve **independently** (Invariants 4 & 5): tenant edits never write back to Global; later Global edits never propagate to the existing tenant copy.
- There is **no ongoing synchronization** (Invariant 2): a re-import is an explicit, **user-controlled** copy event (chained in lineage; see *Re-Import Governance*), not a sync.
- **Global Record ≠ Tenant Record** (Invariant 1): the imported tenant copy has its own identity in the tenant DB and MUST NOT be conflated with, or write to, the Global record.
- External sources MAY also feed imports through a **pluggable source-adapter model** (**D-18**); v1 supports the **Global record + structured CSV/JSON (client upload)**, with API-pull deferred to a later adapter. Regardless of origin, the **same copy / ownership / lineage** semantics apply, and ingestion is **portable** (no provider bulk-load).

## Ownership Rules
- Post-import, the tenant copy is **exclusively tenant-owned**: the tenant MAY read/update/delete it under tenant authorization without affecting the Global record (Invariant 4).
- The Global record is owned at global/control-plane scope; changes to it MUST NOT propagate to previously imported tenant copies (Invariant 5).
- **No write-back:** an import MUST read from Global and write to the tenant only; it MUST NOT modify the Global record.
- The ownership boundary is enforced by **physical database separation**: the Global record lives in global scope; the copy lives in the tenant DB; the two are never shared and never joined in a tenant-routed query.
- Re-import semantics are **user-controlled** (**D-20, as amended in part by D-34-R2** — see *Re-Import Governance* below; the former default-upsert re-import semantics are superseded); in all cases a re-import MUST NOT mutate the Global record and MUST emit lineage recording the outcome.

## Re-Import Governance (D-20, as amended in part by D-34-R2)
*Added 2026-06-12 under PRD-CAP-01B.*

**D-20 amendment statement (explicit).** **D-20 is amended in part by D-34-R2.**
- *Original position (D-20, Approved 2026-06-05):* re-import defaulted to **upsert by natural key** (no-op when unchanged).
- *New position (D-34-R2 §8, R3):* **user-controlled re-import** — no silent overwrite of tenant edits.
- *Retained from D-20, in force unchanged:* the operation-level **idempotency-key** mechanics, **natural-key reconciliation**, the **lineage-append** rule, and the **never-mutate-Global** rule. Only the **default overwrite-on-re-import semantics** are superseded.
- *As-built note:* the implemented natural-key-upsert default was contract-conformant until this amendment; from this amendment it is a **tracked remediation item for a future execution PRD** (contracts precede code — no code change is authorized by PRD-CAP-01B).

**Retry ≠ Re-import.** A **retry** of the same import operation (same idempotency key, D-20) remains idempotent and requires no user decision. A **re-import** — a new import operation whose natural key reconciles to an existing tenant copy — triggers the user-controlled flow below.

**User-controlled re-import (D-34-R2 §8).** When a re-import is detected, the initiating user chooses exactly one outcome — there is **no default**:
1. **Import New Copy** — creates an additional, distinct tenant copy; requires a distinct natural-key strategy (see *Natural-key semantics* below).
2. **Replace Existing** — explicit, consent-based replacement of the existing tenant copy; **never silent**; the new copy's lineage **chains to the prior record's provenance**.
3. **Ignore** — no tenant data changes; the decision is still lineage/audit-visible.

**No hidden overwrite. No automatic overwrite. No background overwrite.** This rule applies **platform-wide — to any initiator** (backend service, scheduler, control-plane operator, or portal), not only to portal-initiated imports.

**Synchronization prohibition (explicit).** The following are prohibited between a Global record and a tenant record, in either direction: **automatic sync, background sync, timer/scheduled sync, event-triggered sync, portal-driven sync** — and any other continuous or recurring propagation mechanism. Import remains a discrete, bounded, user-controlled copy event (Invariant 2); there is **no hidden synchronization** (anything else is D-34-R2's rejected R2 option by the back door).

**Future-merge constraints (D-34-R2 §8).** Any future merge workflow MUST be: **discrete**, **explicitly user-initiated per event**, **lineage-appending** (chained per IC-004/D-25), **never scheduled/automatic/continuous**, and **never writing back to the Global record**. No merge workflow is authorized by this contract.

**Lineage preservation (mandatory).** Every re-import outcome — including *Ignore* — appends lineage; **prior lineage and import history are never modified or deleted** (IC-004 append-only is absolute); lineage remains **tenant-resident** per IC-004 (unchanged); a *Replace Existing* event chains to the prior record's provenance via `parent_lineage_ref`.

**Natural-key semantics per directory kind (D-35-R2 §5).** Each Global directory kind (Startup, Investor, **Deal**) defines its D-20 reconciliation natural key as the **stable Global-record reference** of that kind. For **Import New Copy**, the additional copy carries a distinct tenant-side identity: reconciliation operates on (Global-record reference + copy-instance discriminator) so multiple coexisting copies are distinguishable and any later re-import targets a specific copy. The concrete discriminator mechanics are an **execution-PRD item** (deferral authority: D-34-R2 §8; the specify-before-implementation requirement is D-35-R2 §5 and is satisfied by this section). Where the user's re-import decision sits relative to the import-job lifecycle (the D-19 state machine) is likewise an execution-PRD item.

**IC-004 harmonization (without modifying IC-004).** IC-004's actor example — *"for automated, system-originated events (e.g., a scheduled import), the actor is the responsible service/control-plane identity"* (IC-004:73) — defines **actor attribution only**. It MUST NOT be read as authorizing recurring, scheduled, or automatic imports **of Global records**: under this contract, every Global-record import and re-import is a discrete, user-controlled event regardless of initiator. (Scheduled ingestion from **external, non-Global sources** via a future D-18 adapter, if ever introduced, is governed separately and is not a Global-record re-import — but any ingestion from **any** source whose natural key reconciles to an existing tenant copy is a re-import and follows the user-controlled rule above.)

## Authentication Requirements
> Consumes IC-005; does not define authentication.
- Import is authenticated via **OIDC stateless JWT** (D-05) under the **hybrid identity model** (D-03): the caller is an internal platform identity or a federated external-org principal authorized for the target tenant.
- The **single active tenant context** is established by IC-005 from a signed claim and re-validated at routing (D-04); import inherits exactly that context.
- The **Phase-0 bootstrap system identity** (D-01) MUST NEVER perform a tenant import.
- Import-source credentials (external API-pull sources, a later D-18 adapter) are referenced via the **D-14** secret abstraction — never inlined, logged, returned, or placed in lineage/audit.

## Tenant-Context Requirements
- An import executes within **exactly one active tenant context** (Invariant 6) and writes only to that tenant's database, resolved **registry-authoritatively** (D-07) via the Database Router.
- No import may span tenants or databases; there is no cross-tenant copy in a single operation.
- The principal MUST be an authorized member of the target tenant (D-04).
- Connections come from the **per-tenant pooled** model (D-13), and import draws from **separate, bounded capacity** so it cannot starve interactive traffic; a connection is never reused across tenants.

## Import Readiness Requirements
> Consumes IC-002 readiness; honors D-16 and D-17.
- Import MUST require the target tenant to be **`Ready`** (IC-002). Imports to `Provisioning`/`Verifying`/`Suspended`/`Failed`/`Quarantined`/`Decommissioned`/unknown tenants MUST be denied with IC-002's defined semantics (*retry later* / *administratively disabled* / *unavailable* / *not found*).
- **Schema-version gating (D-17):** import MUST target a tenant whose schema version is within the supported range; a tenant out of range is not-ready → import is deferred/denied until migrated. Imported data MUST be compatible with the tenant's schema version.
- **Per-tenant independence (D-16):** one tenant's import failure or backlog MUST NOT affect any other tenant; readiness and capacity are evaluated per tenant.
- Import is a **Phase-1, tenant-scoped activity** (D-01); no import is possible during Phase 0.

## Execution Model
Per **D-19**:
- Import is **asynchronous by default** for bulk, with a bounded **synchronous fast-path** for small imports (a size/row threshold decides).
- Async imports use a **durable, tenant-scoped import-job record** with a simple state machine (submitted → running → applied / failed); progress is exposed via `GetImportStatus` as **non-sensitive counts**.
- Status polls **re-authenticate statelessly** (OIDC JWT, D-05) and re-establish the same active tenant context (D-04); import MUST NOT require a persistent server session.
- **Per-tenant concurrency is bounded** (D-13 / D-16) so one tenant's large import cannot starve interactive traffic or other tenants; job/progress state is tenant-scoped (no shared store) and portable (no provider queue).

## Ingress Validation & PII Handling
Per **D-09 (ingress)** — this resolves the import-ingress slice; the **AI-egress** slice remains with IC-006 (D-02, post-MVP). Consumes the per-tenant compliance parameters from the resolved **D-08** model.
- Every import MUST pass **input validation + injection-safe sanitization** before any data is written to the tenant copy.
- Imported data MUST be **PII-classified**; per-tenant **minimization/tokenization** is applied per the tenant's compliance parameters (D-08). The mandatory floor is validate + sanitize + classify; minimize/tokenize are opt-in per tenant policy.
- A tenant-owned copy MAY legitimately hold PII under that tenant's policy; such PII lives **only** in the tenant DB (isolation), is access-controlled, retained, and erasable per D-24 / D-08 (erase referent / crypto-erase; non-personal provenance retained).
- **PII, payloads, and secrets MUST NEVER appear in lineage, audit, or responses** — only references, codes, and non-sensitive summaries. Tokenized values are referenced, never raw.
- Records failing validation/sanitization or PII policy are handled per the partial-failure semantics (D-21); error reports MUST be **non-sensitive**.

## Import Lineage Requirements
> Handoff to [IC-004](IC-004-Lineage-Contract.md); IC-004 owns the model, IC-003 emits.
- Every import that creates or updates tenant data MUST emit an IC-004 lineage record (`event_type = import`) capturing at least: `source_ref` (the **Global record reference** or external source descriptor + key/offset — never the payload or credentials), `target_ref` (the tenant copy), `actor_ref`, `occurred_at`, `operation`, `derivation_ref` (the import job), and `schema_version` (D-22).
- **Atomic provenance (IC-004):** lineage is written in the **same tenant transaction** as the copy — for batched imports (D-21), each committed batch carries its lineage atomically — so committed tenant data always has provenance (no data-without-lineage).
- **Re-import appends** (Invariant 2; D-23 append-only): re-imports add new lineage entries chained via `parent_lineage_ref` and MUST NOT mutate prior lineage. Every re-import outcome under *Re-Import Governance* (D-20, as amended in part by D-34-R2) emits attributable lineage reflecting the outcome (new copy / replaced / ignored — or no-op on an idempotent retry).
- Import events are **roots in the unified per-tenant provenance graph** (D-25); the graph never crosses tenants.
- No payloads or secrets in lineage (references only); import lineage retention follows the per-tenant compliance policy (D-24, D-08).

## Audit Requirements
- Import operations — initiation, completion, failure, denial — MUST be recorded in **operational audit** (control-plane/operational, distinct from data-provenance lineage; *Global Record ≠ Tenant Record*). Each record: actor, tenant id, action, **source reference**, outcome, timestamp, correlation id — all carried **as references** per the Global Audit Representation Rule (D-34-R2 §7; contractual home: IC-001).
- Audit records MUST NOT contain payloads or secrets (references only).
- **Two distinct records:** *lineage* = provenance of the tenant copy (tenant-resident, IC-004); *import audit* = operational record of the import action. Both are required; neither substitutes for the other.
- Failed and denied imports SHOULD be audited.

## Failure Behavior
- **Partial-failure semantics (D-21):** imports are **batched/checkpointed**, each batch atomic and **resumable**, with an optional strict all-or-nothing mode. Committed batches MUST have lineage (atomic provenance), a failed import MUST NOT modify the Global record (no write-back), and other tenants MUST be unaffected.
- **Tenant not ready / DB unavailable:** import is denied with IC-002 semantics; the target tenant and all others remain unaffected (D-16).
- **Source unavailable/invalid (external adapter, D-18):** import fails with a defined error; no committed batch is left without lineage; source credentials are never exposed.
- **Idempotency / retries (D-20):** operation-level idempotency keys + per-record natural-key reconciliation make retries safe; a re-run **resumes from the last good checkpoint** (D-21) and re-applies idempotently — never corrupting the tenant copy, never duplicating misleadingly, never mutating the Global record. *(Retry of the same operation only — a new operation reconciling to an existing copy is a re-import and follows* Re-Import Governance*.)*
- **Phase 0 (D-01):** no import is possible.
- **Isolation on failure:** a failing import is contained to the single active tenant (Invariant 6; physical isolation).
- Secrets and payloads MUST be structurally absent from lineage, audit, and responses (references only).

## Multi-Database Compatibility
- Import **writes only** to the target tenant's physically separate PostgreSQL database (no shared tenant DB) and **reads** the Global record from global/control-plane scope; the two are **never joined** in a tenant-routed query.
- Resolution is **registry-authoritative** (D-07); connections are **per-tenant pooled** (D-13).
- Standard PostgreSQL only (AWS RDS / Azure / Google Cloud SQL / self-hosted); **no provider-proprietary bulk-load** (e.g., cloud-bucket-to-DB COPY) and no proprietary pipelines — ingestion MUST be portable.
- The tenant schema participates in expand/contract migrations with version-gated readiness (D-17).
- Per-tenant independence (D-16) governs availability.

## Composition Boundary (D-44 / IC-012)
> **References-only cross-reference. No import semantic is altered by this section.**
- The Import edge's two cross-package collaborator ports — `RoutedSessionProvider` and `LineageEmitPort` — are **supplied by the `deployment` cross-service composition root** (D-44; IC-012 §3/§5/§6/§7), not constructed by `import_service`. `import_service` imports **neither** `database_router` **nor** `lineage_service`; the service-independence DAG is unchanged and unweakened (IC-012 §4/§18).
- Composition **selects no database**. The Database Router remains the sole database selector (D-07; IC-010 §H/§K/§O), and one routed tenant session still resolves to **exactly one** physical tenant database. A routed session is a live transactional handle: it is constructed and consumed **in-process** and never crosses HTTP or any other wire (IC-012 §8/§10).
- **Unchanged by this section:** the *Execution Model* (D-19), idempotency and natural-key reconciliation (D-20, as amended in part by D-34-R2), *Re-Import Governance*, partial-failure and batching semantics (D-21), *Ingress Validation & PII Handling* (D-09 ingress), *Import Lineage Requirements*, the *API Contract*, the *DTO Contract*, the *Audit Requirements*, and *Failure Behavior*. The composed `ImportService`, its ports, its routes, and its durable Import-audit sink are the same ones the injected composition produced.
- This section grants **no route, no DTO, no error code, no audit class, and no DDL**, and confers no import capability.

## Anti-Vendor-Lock-In Requirements
- **No Supabase-specific** import/storage logic and no Supabase Auth (authentication is OIDC via IC-005).
- **No Lovable-specific** runtime dependencies.
- **No provider-proprietary** PostgreSQL bulk-load, CDC, or import pipelines; portable across clouds and self-hosted.
- Source credentials use the portable **D-14** abstraction; no secrets in payloads/lineage/audit/responses.
- AI-assisted import transforms are out of scope (D-02; IC-006 later) and MUST NOT bind to any AI provider.

## API Contract
> Operations and semantics only — no transport code. The surface is a **tenant-scoped API** authenticated per IC-005. Execution is **hybrid** (async-default + bounded sync fast-path, D-19); re-submits are **idempotent** (operation key + natural-key reconciliation, D-20 **as amended in part by D-34-R2**) — a **new** operation whose natural key reconciles to an existing tenant copy is a re-import and follows the user-controlled *Re-Import Governance* flow. Denial semantics follow IC-002 readiness (*forbidden* / *not found* / *not ready* / *administratively disabled* / *unavailable*).

| Operation | Purpose | Caller (authz) | Result | Notes |
|---|---|---|---|---|
| **StartImport** | Initiate a global-to-tenant copy into the active tenant | Authorized tenant member / operator (IC-005) | Begins an import (async or sync fast-path, D-19); emits lineage per committed batch | Idempotent via operation key + natural-key (D-20, as amended — re-import detection triggers *Re-Import Governance*) |
| **GetImportStatus** | Report state/outcome of an import | Authorized tenant member / operator | Status + non-sensitive summary | — |

## DTO Contract
> Data **shapes** as fields only — **no code, no payloads, no secrets.** All external things are references.

**Import Request:** `tenant_id` (the active tenant), `source_ref` (Global record reference, or a pluggable-adapter source descriptor — v1: CSV/JSON, D-18), `mode` (async or sync fast-path, D-19), `idempotency_key` (operation-level, D-20), `correlation_id`. Source credentials are **never** present — only a D-14 reference.

**Import Status:** `import_id`, `tenant_id`, `state`, `outcome_summary` (non-sensitive counts), `last_error_summary` (non-sensitive), `correlation_id`.

**Lineage record:** defined by [IC-004](IC-004-Lineage-Contract.md); import emits the minimum core (D-22). Not redefined here.

## Import Decisions (resolved)
The import decisions that previously gated this contract are now approved and incorporated above (see [Architecture-Decision-Register.md](../docs/Architecture-Decision-Register.md)):
- **D-18** — pluggable source-adapter model; v1 = Global record + CSV/JSON (*Global-to-Tenant Import-Copy Model*).
- **D-19** — hybrid execution (async-default + bounded sync fast-path) (*Execution Model*).
- **D-20** — operation-level idempotency key + natural-key reconciliation (*Ownership Rules*, *Import Lineage*, *Failure Behavior*). **As amended in part by D-34-R2 (2026-06-12):** the default-upsert re-import semantics are superseded by **user-controlled re-import** (*Re-Import Governance*); the idempotency-key, natural-key-reconciliation, lineage-append, and never-mutate-Global mechanics remain in force.
- **D-21** — batched/checkpointed atomic imports with resumability (*Failure Behavior*, *Import Lineage*).
- **D-09 (ingress)** — policy-driven validation/sanitization/classification on a mandatory floor (*Ingress Validation & PII Handling*).
- **D-31** — the Global record is a Global Startup/Investor/Deal Directory record residing in the Control Database (D-31, extended by D-35; *Global-to-Tenant Import-Copy Model*); copy → tenant DB, *ownership never transfers*, *Global Record ≠ Tenant Record* and *Import ≠ Synchronization* preserved.
- **D-35** (R2) — the **Global Deal Directory** record is an importable Global record (`Global Deal → Import → Tenant Deal Copy` under the unchanged Import-Copy model); `Global Deal ≠ Tenant Deal`; deal natural-key semantics specified in *Re-Import Governance* (*Global-to-Tenant Import-Copy Model*, *Re-Import Governance*).
- **D-34** (R2) — **amends D-20 in part**: user-controlled re-import (Import New Copy / Replace Existing / Ignore), explicit synchronization prohibition, future-merge constraints, mandatory lineage preservation, platform-wide applicability, IC-004 actor-example harmonization (*Re-Import Governance*).

No import architecture decisions remain open for this contract. The **D-09 AI-egress** slice remains owned by IC-006 (AI post-MVP, D-02) and does not gate import.

> **Status:** IC-003 is **Final** for MVP architecture. All cross-cutting, dependency (IC-002 / IC-004 / IC-005), and import decisions are applied; only downstream/implementation-level concerns remain — not further import architecture decisions.
