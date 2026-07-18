# IC-007 — Deal Collaboration & Cross-Tenant Sharing Contract

**Status:** Draft / Proposed · **Phase:** Architecture Planning · **Type:** Contract-first specification (no implementation)
**Opened:** 2026-07-18 by **D-38 — Governed Sharing Placement, Authority & Dispatch** (Dan-authorized contract-authoring START-GATE), transitioning IC-007 from the **Deferred placeholder** (D-32; PRD 8C) to a **Draft / Proposed** governed-sharing contract. **Revision:** IC-007-DRAFT-1.
**Prior status:** Deferred (placeholder — no design, no implementation), 2026-06-05 → 2026-07-17.
RFC-2119 keywords **MUST / MUST NOT / SHOULD / MAY** are used normatively.

> **Contract-first, no positive capability.** This is a **Draft / Proposed** contract. It **specifies and reserves**; it grants nothing. **No positive sharing capability is implemented** and none is authorized by this draft. IC-007 becomes **Final** only after independent verification and human merge; the co-authored IC-009 / IC-010 amendments are **authored-but-inert until IC-007 is Final**. The change-control order is **register → contract → code**. Until IC-007 is Final and later implemented under a separate, explicitly-authorizing execution PRD, the MVP invariants stand: **one request → one active tenant → one database**, **no cross-tenant joins**, **physical tenant isolation**, **Global Record ≠ Tenant Record**. **Production remains NOT READY / DO-NOT-ACTIVATE.**

## Purpose (§1)
Govern **Governed Sharing** — controlled, audited cross-tenant sharing of records between tenants and via MASTER_AGENT, and Control-originated sharing into a tenant — as a capability that crosses the physical tenant-isolation boundary and therefore must be designed here, under its own decisions, before it may exist. Governed Sharing lets an authorized human grant a **bounded, references-only view** of a source record to a target, **without moving, copying, or re-owning** that record.

## Placement (§2 — Control-level references-only grants)
- **Control-level references-only grants.** A governed share is a **Control-level, references-only grant**. The authoritative Startup / Investor / Deal record and its business payload stay in their home residency (the source tenant DB, or the Control DB for a global source); only **opaque references** (`source_record_ref`, `owning_tenant_ref`, permission scope, lifecycle metadata) live in the grant.
- **Control DB is the sharing authority.** The **Control DB is the future sharing authority** and the system of record for the grant lifecycle. **The Control Plane is the sole Control-DB writer** of governed-sharing events (propose / approve / grant / revoke / suspend / expire).
- **No tenant sharing table.** There is **no tenant sharing table**; no `deal_shares` / `deal_share_targets` / `deal_introductions` (or any organizational-role table) is added to any tenant DDL (the live tenant-DDL guard already forbids them).
- **No cross-database FK.** There is **no cross-database FK**. A foreign key cannot span two physically separate PostgreSQL databases; the grant carries **soft references only**, validated at use time under the referencing side's own authorization.
- **One request → one category → one database.** Every governed-sharing operation resolves to the **Control DB only** — **one request → one category → one database**, never straddling the Control DB and a tenant DB, and never spanning two tenant DBs (IC-010 §K/§Q).

## Visibility (§3 — MVP references-only projection)
- **MVP visibility is the `SharedItemReferenceDTO`.** The target reads a **Control-composed, references-only `SharedItemReferenceDTO`** produced by a **single Control operation** (IC-009 normative home; IC-010 §V composition). It exposes only the approved reference scope (share reference, source record reference + kind, owner / owning-tenant references where authorized, target reference, permission scope, status, and effective / expiry / revocation references).
- The projection **MUST NOT** carry: tenant business payload, the source-tenant live record, cross-tenant live retrieval, database identity / name / DSN / topology, any secret / credential / raw provider body, or PII.
- **Deferred visibility mechanisms:** owner-published rich snapshot, temporary retrieval token, tenant-local projection, and automatic synchronization are **deferred**.
- **Import ≠ Sharing.** A target that needs its **own independent copy** uses **Import (IC-003)**, not Sharing. Import creates a new record with new tenant-side ownership and its own lineage, audited as an **Import** event — **never** a `share_*` event.

## Initial Categories (§4 — exactly four)
The initial governed-sharing contract covers **exactly four** categories:

| Category | Direction | Record kind |
|---|---|---|
| **intra-Master-Agent Deal sharing** | within one Master-Agent boundary | deal |
| **Master-Agent → Master-Agent Startup sharing** | MA → MA | startup |
| **Control → Master-Agent Startup sharing** | Control → MA | startup |
| **Control → Master-Agent Investor sharing** | Control → MA | investor |

**Deferred categories (out of the initial scope):** introduction, campaign distribution, forward / re-share, import-copy, ownership transfer, tenant transfer, sync, attribution. Ownership transfer is **IC-008 `TransferOwnership`, not Sharing**; import-copy is **Import (IC-003), not Sharing**; sync is prohibited; attribution rides Lineage (§7) and is not a sharing capability.

## Dual-Layer Authority Model (§5)
Governed Sharing is authorized across **two distinct layers that MUST NOT be conflated**.

### Layer A — platform security / workspace roles (six; the only token/JWT roles)
`CONTROL`, `MASTER_AGENT`, `TENANT_ADMIN`, `TENANT_AGENT`, `STARTUP_USER`, `INVESTOR_USER` (D-32). These are carried in the signed authentication context and govern authentication, workspace / tenant scope, platform route access, the Gateway authorization boundary, and one-active-tenant-per-request. **These six are the only token / JWT roles.**

### Layer B — tenant organizational roles (seven; references-only, Control-resident, NOT token roles)
`Owner`, `Head of Investment`, `Portfolio Manager`, `Investment Manager`, `Analyst`, `Marketing`, `Institutional Sales`. These are the tenant-internal seniority / supervision hierarchy of a venture firm. **Organizational roles are not JWT / token roles** and are **not** a tenant-DDL table; if ever persisted, their home is **Control-resident**, expressed as **references only** (`granting_role`, `approval_ref`) validated server-side at a share transition. This draft contracts Layer B **inside IC-007 only**, references-only, forward-referencing IC-005; it builds **no enforceable permission** and **does not amend IC-005** (the enforceable IC-005 permission-binding amendment is a later runtime slice).

Binding hierarchy:

```
Owner
├── Head of Investment
│   └── Investment Manager
│       └── Analyst
└── Portfolio Manager
    ├── Marketing
    └── Institutional Sales
```

Binding rules:
- **Owner is a per-tenant singleton.**
- **Owner-only organizational-role assignment.** **Only Owner** assigns or reassigns tenant organizational roles after bootstrap.
- **Initial-Owner designation (non-circular bootstrap).** The **first** Owner of a tenant is designated not by another Owner but by a **platform authority** — a `CONTROL` / `TENANT_ADMIN` principal (Layer A) — through the governed tenant-bootstrap process (the Control-DB Tenant Registry surface, D-32).
- An Agent **MAY** hold multiple organizational roles; role-derived supervision **MAY** carry a lawful explicit override; organizational authority **never** extends outside the active tenant and **never** replaces the platform security role.

### Combined authorization rule
A governed share action requires **all four**: an authenticated platform principal (Layer A) **+** a valid active workspace / tenant scope (one active tenant per request) **+** the platform feature permission for the operation (IC-005 per-feature layer) **+** the required tenant organizational approval (Layer B) where the share policy requires it.

### AI rule
**AI cannot authorize.** AI **MAY** assist or draft; AI **MUST NOT** independently propose-as-authority, approve, grant, revoke, forward, or suspend a share. Every authorization-changing transition requires the contracted **human** authority (reserved `CONTROL_AI` identity; `ai.invoke` unwired — D6 / Part 4B).

## Senior-Approval Contract (§6)
Live in the initial four-category scope (**investment branch**, plus the platform authorities):
- **Owner** — MAY approve **every** governed share in the tenant; MAY propose, grant, and revoke.
- **Head of Investment** — MAY approve **Startup and Deal** sharing **within the investment branch**.
- **Investment Manager** — MAY **propose** Startup and Deal shares; **requires Head of Investment or Owner approval**.
- **Analyst** — MAY draft / propose within permission scope; **Analyst never approves or grants**.

Contracted but **dormant until later categories open** (**portfolio branch**): Portfolio Manager, Marketing, and Institutional Sales, and the campaign-distribution / investor-facing-distribution share types. **Marketing and Institutional Sales never approve unilaterally** — they require Portfolio Manager or Owner approval when their categories open.

Platform / global authorities:
- **CONTROL** authorizes **Control → Master-Agent** Startup / Investor sharing (categories 3–4).
- **MASTER_AGENT** authorizes within its contracted boundary (categories 1–2) and retains **capability-level suspension authority**; **Owner** retains tenant-level override authority.
- **Forwarding is prohibited by default.** Forward / re-share is **prohibited by default** for every role; any forwarding grant is a separate, explicitly-authorized type **outside** this initial slice.

## Lifecycle & System-of-Record Model (§7)
```
append-only sharing-event ledger (Control DB)  — proposed → approved → granted → read → revoked → expired → suspended → denied
derived current-state projection               — computed from the event stream; never an in-place UPDATE/DELETE
D-23 append-only + hash-chain semantics        — every transition auditable by construction
idempotent proposal / transition replay        — deterministic key over (source_record_ref, target_ref, permission_scope, granting_principal_ref, proposal_nonce)
revocation / expiry / suspension               — make the derived current state non-granted; never mutate history
forwarding / re-sharing                        — prohibited by default; a new explicit forwarding grant is OUT of this slice
```

**System-of-record data model (references-only; exact columns finalized at implementation):** `share_id`, `share_type` {startup_share, investor_share, deal_share}, `source_record_ref` (opaque soft reference — **no cross-DB FK**), `source_record_kind` {startup, investor, deal}, `owning_tenant_ref` (soft ref, or CONTROL for a global source), `owner_agent_ref` (references-only; never PII), `owner_ai_agent_ref` (references-only; NULL until IC-006), `granting_principal_ref`, `granting_role` (the D-32 platform role exercised), `approval_ref` (references-only link to the Layer-B senior-approval record), `target_master_agent_ref` / `target_tenant_ref` / `target_principal_ref` (soft refs, where allowed), `permission_scope` (bounded read-scope descriptor), `status` {proposed, approved, granted, revoked, expired, suspended, denied}, `effective_at` / `expires_at` / `revoked_at` / `revoked_by_ref` / `suspended_by_ref`, `reason_ref`, `correlation_id`, `recorded_at`.

**Sharing never changes ownership, owning tenant, or authoritative record identity.** A share event **never** writes `owner_agent_ref` on the source, **never** changes `owning_tenant_ref`, and **never** creates a second authoritative record. Ownership stays exactly where **IC-008** put it (`TransferOwnership` is the sole ownership mutation; cross-tenant ownership prohibited; D-36-R2 preserved). **Data residency (D-08):** the reference-fork preserves residency; any richer exposure that would move tenant-attributable data across residency zones is **deferred** and must be decided under D-08 in a later IC-007 amendment.

## Audit & Attribution Contract (§8)
Every sharing transition emits **exactly one references-only, append-only** audit event (D-23; D-34-R2 Global Audit Representation Rule; IC-010 §J references-only). The **API Gateway is the sole emitter** (single edge). The durable store is the **Control-DB operational audit** (Control-resident — this **avoids the DEC-11 tenant-residency wall**; the class-home binding sequences under the pending IC-002 audit-section extension).

Contracted references-only event classes: `share_proposed`, `share_approved`, `share_granted`, `share_read`, `share_revoked`, `share_expired`, `share_suspended`, `share_denied`, `forward_attempt_denied`. Rules: append-only / hash-chain compatible; idempotent transition replay; `correlation_id` links the whole lifecycle; expiry and suspension are enforced and emitted **lazily at the single Gateway read/transition edge** (no background sweeper, no second emitter). **Attribution remains distinct from sharing and ownership** — the revenue-attribution record rides **Lineage (B-6)** + the reserved `control_ai_recommendations`-shaped Control table; sharing *records that a controlled introduction/recommendation occurred* and never transfers ownership. **No audit implementation is authorized by this draft.**

## Dispatch & Projection (§9 — IC-010 / IC-009)
- **IC-010 §Q gains one fifth category: "Governed Sharing" (Control-resident operations)**, opened **solely by IC-007 adoption** (the named trigger). It resolves to the **Control DB only**; the Gateway resolves no database and composes references-only DTOs under §V.1; IC-010 §V.4's blanket deferral clause is carved out **only** for the four adopted categories while every isolation mechanic is preserved.
- **IC-009** is the normative home of the references-only **`SharedItemReferenceDTO`** (DEC-4 owner-ref hiding; inert until IC-007 Final). The transition-result and list DTOs (`SharingTransitionResultDTO`, `SharingListItemDTO`) are references-only and each resolves to exactly one Control-DB operation.

## Status Lifecycle & Journey A (§10)
```
Deferred placeholder  →  Draft / Proposed (this draft; opened by D-38)  →  Final (only after independent verification + human merge)
```
No positive capability is authorized by draft creation alone. The **first bounded rehearsal** (after IC-007 is Final and separately implemented) is **Journey A — one Deal shared within one Master-Agent boundary**, which must prove: proposal · required approval · grant · bounded target read (references-only projection) · non-target denial (fail-closed) · revocation removes access · audit records every step · **ownership unchanged** · **tenant unchanged** · **no record duplication** · **one request → one active tenant → one database**. Journeys B (MA→MA) and C (Control→MA) are fast-follow.

## Dependencies
- **IC-008** (Ownership) — sharing never transfers ownership; `TransferOwnership` is the sole ownership mutation.
- **IC-009** (Portal Contracts) — normative home of `SharedItemReferenceDTO`; portal renders sharing state and computes no authority.
- **IC-010** (API Gateway) — the fifth "Governed Sharing" dispatch category; §V references-only composition; §J sharing-audit subclass.
- **IC-002 / IC-004 / IC-005** — tenant identity & membership; lineage / attribution provenance; identity, D-04 one-active-tenant, D-30 isolation, D-32 role hierarchy (the enforceable IC-005 permission binding is a later slice).
- **D-30 / D-31 / D-35 / D-36 / DEC-4 / DEC-11 / D-08** — isolation, directory residency, tenant anonymity, ownership, owner-ref hiding, audit-residency sequencing, data residency.

## Change Control
IC-007 is designed and approved through the standard change-control process — **register (D-38) → contract → code**. No silent edit of an adopted IC-007 is permitted; opening a deferred category (introduction / campaign distribution / forward-re-share / etc.) requires a further IC-007 + IC-009 + IC-010 amendment.

---

> **Non-claims.** This draft opens IC-007 to **Draft / Proposed** only. It does **not** make IC-007 Final, does **not** amend IC-005, does **not** implement any route, DTO, port, store, database table, DDL, or audit sink, does **not** create any positive sharing capability, and does **not** change any blocker or production posture. IC-007 remains **Draft / Proposed** until independent verification, human merge, post-merge verification, and GPT arc closure. **Production remains NOT READY / DO-NOT-ACTIVATE.**
