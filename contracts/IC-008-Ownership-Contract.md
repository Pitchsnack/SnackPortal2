# IC-008 — Ownership Contract

**Status:** Final · **Phase:** Architecture Planning · **Type:** Specification only (no implementation)
**Authority source:** Authored 2026-06-13 under **PRD-CAP-01C** from the Reserved placeholder (reserved by **D-36 — Ownership Architecture**, Approved 2026-06-12; placeholder created under PRD-D33-D37-V2-R1 WP-C). Implements **D-36-R2** as registered, within D-30/D-31/D-32/D-34-R2 and the mandatory Physical Multi-Database MVP.
**Status note:** This contract completes the **contract-authoring** step of the D-33→D-36 chain. One load-bearing dependency remains pending and out of this PRD's scope: the **tenant-resident ownership-audit class** is carried by the **IC-002 audit-section extension** (Contract Amendment Inventory R2 — specified, not yet executed, no authoring vehicle named yet), so end-to-end ownership audit is not yet fully contract-homed. This contract defines the ownership **model**; the ownership **boundary** was already contract law (IC-003: *"the ownership boundary is enforced by physical database separation"*; *"ownership never transfers"*). No implementation is authorized by this contract — fields, workflows, audit persistence, and UI land only under later execution PRDs (contracts precede code).
Requirement keywords **MUST / MUST NOT / SHOULD / MAY** are used in the RFC-2119 sense.

## Purpose
Define **Ownership** in SnackPortal2: the accountable human **Owning Agent** (and the reserved, AI-ready **Owning AI Agent** reference) for governed records — what ownership is, what it is **not**, who may own what, how ownership is assigned at import, how it transfers, and how it is audited. Ownership is an **accountability designation, never a mechanism**: it confers responsibility, not power.

## Ownership Principles (D-36-R2 §4 + PRD-CAP-01C §7.B — binding on every section below)
*Principles 1, 3, 5 carry D-36-R2 §4 (≠ Authorization, ≠ Residency, ≠ Visibility); Principles 2 and 4 (≠ Routing, ≠ Authentication) are PRD-CAP-01C §7.B additions consistent with D-36-R2 §12.*
1. **Ownership ≠ Authorization.** Ownership never grants permissions, access, or capabilities; per-feature authorization remains governed by the relevant contracts under IC-005.
2. **Ownership ≠ Routing.** Ownership never participates in database selection; routing consumes only the signed tenant claim (IC-005/D-06). No code path may read an ownership field as a routing input.
3. **Ownership ≠ Residency.** Ownership never changes, or is changed by, the Control-DB/tenant-DB boundary; assigning or transferring ownership never moves a record.
4. **Ownership ≠ Authentication.** Ownership fields are not identities, credentials, or claims; they reference principals authenticated under IC-005/D-03.
5. **Ownership ≠ Visibility.** Visibility remains governed by permissions and contracts; owning a record discloses nothing beyond what authorization already permits.

## Ownership Scope
Ownership is defined for exactly three record kinds, in both residencies:
- **Startup records** — tenant-resident copies and Global Startup Directory records.
- **Investor records** — tenant-resident copies and Global Investor Directory records.
- **Deal records** — tenant-resident deals and Global Deal Directory records (D-35).

**No other ownership classes are introduced or permitted by this contract.** Ownership of infrastructure, tenants, databases, audit records, lineage, or directory metadata is out of scope and undefined.

## Non-goals
- AI behavior of any kind (IC-006 — Draft, post-MVP; see *AI Ownership Rule* for the reserved slot only).
- Cross-tenant ownership, sharing, or visibility (IC-007 — Deferred; see *Ownership Boundaries*).
- Ownership implementation: database schema, migrations, workflows, UI, audit persistence (execution PRDs, after this contract).
- Portal surfaces (IC-009/D-37), API Gateway behavior (IC-010), authentication behavior (IC-005).

## Human Ownership Rule (D-36-R2 §2)
- Every owned record has **exactly one human Owning Agent**, represented **only** by `owner_agent_ref`.
- **Tenant-resident records (per-entity mandate):** every tenant Startup, Investor, and Deal record MUST have exactly one `owner_agent_ref` (D-36-R2 V1–V3; effective for imported records per the *Import Ownership Rule*).
- **Global records (the reserved open decision — resolved here):** named ownership of Control-DB global records is **MANDATORY**: every Global Startup/Investor/Deal Directory record MUST have exactly one `owner_agent_ref`, held by a Control-domain principal (*Ownership Eligibility*). *Rationale:* the PRD 8A accountability intent (every Global Deal is a Control-managed opportunity — a curated record requires an accountable curator) and D-36-R2 O3's own basis (O1 was rejected for lacking accountability). D-36-R2 §6 made global ownership optional *"unless IC-008 makes it so"* — this contract makes it so. *Sequencing:* the mandate binds at implementation time; backfilling owners onto pre-existing directory records is a named execution-PRD item. *Creation (forward):* every operation that creates a Global Directory record MUST resolve exactly one eligible initial Owning Agent — by default the **creating principal when ownership-eligible for global records (CONTROL)**, otherwise an explicitly designated eligible CONTROL principal — or the creation is denied (fail-closed, preserving the mandate); mechanics are execution-deferred. (The `GlobalDirectory` mutation operation is itself uncontracted and Not-Implemented per D-34-E1; this rule binds it when it lands.)

### Representation Rule (mandatory)
Ownership is stored as **references only**. An ownership record/field MUST NOT contain: **name, email, display name, AI name, or any identity payload**. Human references resolve at presentation time through the **D-03 identity model** (*Reference Resolution*). This is the D-36-R2 §3 rule, bound platform-wide by the D-34-R2 §7 Global Audit Representation Rule for all ownership audit.

## AI Ownership Rule (D-36-R2 §2/§3 — AI-ready, not AI-required)
- Every owned record carries **zero or one** reserved AI-owner reference: `owner_ai_agent_ref`.
- The field is **nullable, optional, and reserved**: it MUST remain **NULL platform-wide until IC-006 defines the AI-agent identity namespace and its resolution path** (D-03 defines only human identities today — no valid AI reference target exists; D-36-R2 V10).
- **Prohibited:** a mandatory AI owner; a placeholder AI owner; a synthetic AI owner (any non-NULL value fabricated to satisfy a schema or workflow). Population rules, identity namespace, and resolution are **IC-006 future work** — not this contract.

## Ownership Eligibility (decided by this contract, per D-36-R2 §9)
Eligibility is expressed as **role-based reference** over the D-32 role model — never person-based logic; no new roles are introduced and the D-32 hierarchy is not expanded.

| Record residency | Ownership-eligible roles | Basis |
|---|---|---|
| **Tenant-resident** Startup / Investor / Deal | **MASTER_AGENT**, **TENANT_ADMIN**, **TENANT_AGENT** — each evaluated against the record's own tenant per the Ownership Domain Rule below | Operating/agent roles carry relationship accountability (PRD 8-series "Owning Agent"); D-32 |
| **Control-DB (global)** Startup / Investor / Deal Directory records | **CONTROL only** | D-36-R2 §5 restricts global owners to Control-domain (D-03 internal) principals — normative independently of this matrix; of the two internal roles, MASTER_AGENT is excluded because it is a tenant-operating role, while global directory curation is CONTROL-scoped platform administration (D-33 §4, Control Workspace definition) |
| Any | **STARTUP_USER / INVESTOR_USER — not eligible** | Served principals with scoped functions (D-32), not accountable operating agents |

### Ownership Domain Rule (D-36-R2 §5 — carried)
> **The owning principal MUST hold membership in the record's residency domain, evaluated per record.** For a tenant-resident record: the owner is a principal with membership in that tenant (a MASTER_AGENT with membership in tenants A and B may own records in each — each ownership reference is evaluated against its own record's tenant). For a Control-DB-resident global record: the owner MUST be a **Control-domain (D-03 internal) principal**.

Eligibility is evaluated at assignment and transfer time. A principal whose membership or role lapses no longer satisfies the rule: the record MUST be re-owned via a governed transfer as part of the relevant administrative workflow (membership termination, role change) — owned records are never left ownerless, and lapsed eligibility never silently revokes or reassigns anything (mechanics: execution-PRD item). This obligation is scoped to records in **active-service** tenants (and to Control-DB global records): ownership references in **Suspended** or **Decommissioned** tenants (IC-002 lifecycle) are preserved unchanged as historical data — no ownership event occurs there, and the obligation resumes only on return to service (Suspended → Verifying → Ready). Deletion or archival of a record is not an ownership event and emits no ownership audit.

## Import Ownership Rule (D-36-R2 §8)
- **Ownership never transfers from source to imported copy** (existing IC-003 law, restated): the Global record's owner is irrelevant to, and unaffected by, any import.
- The imported copy receives **new tenant-side ownership** within the importing tenant, assigned at import time.
- **Initial-owner rule (defined here, as D-36-R2 §8 requires):** every import that creates a tenant copy MUST resolve exactly one eligible initial Owning Agent — by default the **initiating human principal**, when ownership-eligible in the target tenant; otherwise an **explicitly designated eligible principal** carried with the import request (e.g., for system-originated imports, whose service identity can never own). An import that cannot resolve an eligible initial owner MUST be denied (fail-closed — preserving the per-entity mandate). **Mechanics are implementation-deferred** (PRD-CAP-01C §7.G note): how the designation is carried, validated, and surfaced is an execution-PRD item; the rule above is the contract.
- **Re-import outcomes (IC-003 Re-Import Governance).** Because IC-003's **Import New Copy** and **Replace Existing** each *create* a tenant copy, the Initial-owner rule above applies to the resulting copy — the new (or replacing) copy receives a **freshly-resolved eligible initial owner** (an **assignment**, never a silent carry-over or transfer; a silent owner change as a side effect of re-import is forbidden by the *Ownership Transfer Rule*). **Ignore** creates no copy and triggers no ownership event. This states the ownership outcome of IC-003-defined events; it does not redefine them.
- Initial assignment and every subsequent change are audited per the *Ownership Audit Rule*.

## Ownership Transfer Rule (D-36-R2 §7)
- **Ownership Transfer** is a **governed operation**: explicit, authorized, audited — never implicit, never bulk-silent, never a side effect of another operation.
- Authorization to transfer: the current Owning Agent, or a principal holding administrative authority over the record's residency domain (**TENANT_ADMIN** for tenant records; **CONTROL** for global records) — authorization semantics remain governed by IC-005 and the feature contracts (Principle 1).
- The new owner MUST satisfy *Ownership Eligibility* (including the Ownership Domain Rule) at transfer time.
- **Transfer changes nothing but the reference:** residency, routing, authorization, visibility, lineage, and the record's content are untouched. A transfer is metadata maintenance, not a data operation.

## Ownership Audit Rule (D-34-R2 + D-36-R2 §7)
Ownership events (initial assignment, transfer, lapsed-eligibility re-owning) are **Administrative Audit** events (D-34-R2 taxonomy).

> **Audit Residency Rule: ownership audit follows RECORD RESIDENCY, not ownership type.**
> - **Control-DB (global) record** ownership event → audited in the **Control DB** (D-34-R2 Administrative Audit). Administrative Audit is contractually homed in the **IC-002 audit section and its pending extension** (D-34-R2 §6 / IC-001's taxonomy table; tracked in Contract Amendment Inventory R2) — **not** in IC-001's *Operational Audit — Global Classes* section, which homes only the global Directory/Publication/Export classes. (The Global Audit Representation Rule that binds the record's *shape* is separately contract law at IC-001 — see below; that citation is distinct from this class-home.)
> - **Tenant-resident record** ownership event → audited in the **tenant DB** (the tenant-resident ownership-audit class; carried by the pending IC-002 audit extension per D-36-R2 §7 Audit Residency Rule — tracked in Contract Amendment Inventory R2).
> - **Imported record** (tenant-resident by definition) → audited in the **tenant DB**.

Ownership audit **never crosses residency boundaries** (D-36-R2 V9). Every ownership audit record obeys the **Global Audit Representation Rule** (D-34-R2 §7, contract law at IC-001): references only — `ownership_ref`, `actor_ref`, `record_ref`, `tenant_ref` where applicable, plus action/outcome/timestamp/correlation metadata; never names, emails, PII, or payloads.

## Ownership Boundaries
- **Cross-tenant ownership is prohibited:** a principal cannot own a record in a tenant where they hold no membership; no ownership construct spans tenants; no ownership reference in one tenant's database may point at another tenant's domain.
- **Ownership-based cross-tenant routing and ownership-based cross-tenant authorization are prohibited** (they are prohibited even within a tenant by Principles 1–2; a fortiori across tenants).
- **Required statement:** cross-tenant ownership belongs to **IC-007 — Deal Collaboration & Cross-Tenant Sharing** and is **out of scope** of this contract; any future IC-007 model MUST preserve D-36-R2 V7 (cross-tenant ownership impossible until then).
- These boundaries are enforced ultimately by **physical database separation** (the IC-003 ownership-boundary law; the mandatory Physical Multi-Database MVP) — ownership rides the boundary and never bridges it.

## Reference Resolution
`owner_agent_ref` and `owner_ai_agent_ref` are **identity references only** — opaque pointers into the D-03 identity model (human: internal or OIDC-federated; AI: undefined until IC-006). Display names, contact details, and any presentation of "who owns this" are resolved **at the presentation layer** through the identity model at read time, under the reader's own authorization. References MUST NOT be reverse-encoded — **no name, email, or identity data may be embedded in any reference value this contract defines**, comprising the ownership references (`owner_agent_ref`, `owner_ai_agent_ref`) and every ownership-audit reference (`ownership_ref`, `actor_ref`, `record_ref`, `tenant_ref`) — and MUST NOT be treated as authentication or authorization tokens.

## Record-Shape Amendments (routed through this contract, per D-36-R2 §14)
The following field obligations attach to the record shapes of the three owned kinds — defined **here** to avoid smearing ownership across IC-001/IC-002/IC-003 (whose texts are unchanged):
- **Tenant Startup / Investor / Deal record shapes:** `owner_agent_ref` (required), `owner_ai_agent_ref` (nullable, NULL until IC-006).
- **Global Startup / Investor / Deal Directory record shapes:** `owner_agent_ref` (required per the *Human Ownership Rule* global mandate), `owner_ai_agent_ref` (nullable, NULL until IC-006). Ownership fields are **governance metadata, not discovery metadata**: they are not part of the four IC-001 discovery-metadata categories, are never tenant-attributable content (the owner is a Control-domain principal — compatible with IC-001's Tenant Anonymity Rule), and whether they are surfaced to directory readers is a presentation/authorization question (Principle 5), deferred to IC-009/IC-010.
- Field addition follows D-17 expand/contract migration discipline at implementation time.

## API Contract
> Operations and semantics only — no transport code; concrete bindings are implementation details (execution PRDs, surfaced only via the IC-010 gateway).

| Operation | Purpose | Caller (authz) | Result / effect | Notes |
|---|---|---|---|---|
| **TransferOwnership** | Reassign a record's Owning Agent | Current owner, or domain administrator (TENANT_ADMIN / CONTROL per residency) | `owner_agent_ref` updated; **Administrative Audit** event in the record's own residency | Eligibility + Domain Rule re-evaluated; residency/routing/authorization untouched |
| *(reads)* | Ownership is read as part of the record | Per the record's own read authorization | none | No separate ownership query surface; no cross-tenant ownership enumeration exists |

Initial assignment at import is part of the IC-003 import operation (see *Import Ownership Rule*), not a separate API of this contract.

## DTO Contract
> Shapes as fields only — no code, no payloads, **no identity data**.

**Ownership fields (on owned record shapes):** `owner_agent_ref` (required; opaque identity reference), `owner_ai_agent_ref` (nullable; NULL until IC-006).

**Ownership Audit Record (Administrative Audit class):** `audit_id`, `record_ref`, `ownership_ref` (prior → new as references), `actor_ref`, `action` (assign | transfer | re-own), `outcome`, `timestamp`, `correlation_id` — references only, append-only, resident per the Audit Residency Rule. (`tenant_ref`, a permitted reference under the Global Audit Representation Rule, is implicit in the record's residency — the hosting database fixes the tenant — and need not be stored separately.)

## Multi-Database Compatibility
- Ownership fields live **inside the record's own database** (tenant fields in that tenant's DB; global fields in the Control DB) — never in a third store, never duplicated across databases, never joined across databases.
- No ownership operation spans databases: a transfer executes in the record's own residency under the one-request→one-database rule (IC-002 invariants).
- Standard PostgreSQL only; no provider-specific features.

## Anti-Vendor-Lock-In Requirements
- Ownership references bind to the **portable D-03 identity model** — never to a vendor identity service's proprietary identifiers in a non-portable way.
- No Supabase, Lovable, or provider-specific ownership logic; ownership fields and audit are plain, portable PostgreSQL data.

## Future Work (dependencies)
- **IC-006 — AI Gateway Contract:** AI-owner activation — the AI-agent identity namespace, reference resolution, and `owner_ai_agent_ref` population rules. Until then the slot stays NULL platform-wide.
- **IC-007 — Deal Collaboration & Cross-Tenant Sharing Contract:** any cross-tenant ownership model (must preserve D-36-R2 V7).
- **Execution PRDs (after this contract; none authorized by it):** ownership fields via D-17 migrations; assignment/transfer workflows incl. the import-time designation mechanics and lapsed-eligibility re-owning; ownership-audit persistence in both residencies; global-record owner backfill for the mandatory-global-ownership rule; verification items D-36-R2 V1–V10 (incl. V10's platform-wide NULL check on `owner_ai_agent_ref`).

## Resolved Decisions
- **D-36** (R2) — ownership model: exactly one human owner + reserved nullable AI slot; representation rule; Ownership Domain Rule; Audit Residency Rule; import-ownership rule (*all sections above*).
- **Decided by this contract** (authority delegated by D-36-R2 §6/§9): the **eligibility matrix** (*Ownership Eligibility*) and **mandatory named ownership of Control-DB global records** (*Human Ownership Rule*).
- **D-32** — role vocabulary consumed unchanged; **D-03** — identity model for resolution; **D-34-R2** — audit class + representation rule; **D-30/D-31** — isolation and residency untouched; **IC-003** — ownership boundary and never-transfers law restated, not redefined.
