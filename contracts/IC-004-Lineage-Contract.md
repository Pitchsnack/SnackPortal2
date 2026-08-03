# IC-004 — Lineage Contract

**Status:** Final · **Phase:** Architecture Planning · **Type:** Specification only (no implementation)
**Decision basis:** Applies approved decisions **D-01–D-05, D-07, D-13–D-17** and the lineage decisions **D-08, D-22–D-25** ([Architecture-Decision-Register.md](../docs/Architecture-Decision-Register.md)).
**Status note:** All lineage architecture decisions are resolved and incorporated. **Final** for MVP architecture. **D-08 carries a standing business/legal action** to name the specific compliance floor regime and per-tenant parameters (retention values, residency); the *mechanism* is fixed and does not reopen the architecture.
Requirement keywords **MUST / MUST NOT / SHOULD / MAY** are used in the RFC-2119 sense.

## Purpose
Define the contract for **data lineage**: how the origin, transformations, and provenance of tenant data are captured, referenced, queried, and retained so that any tenant record can be traced back to its source. Lineage is captured **per tenant, inside that tenant's physically separate database**, and is **distinct from operational/control-plane audit** (which is IC-002). The model is **AI-ready** (D-02) without specifying or requiring any AI implementation.

## Core Invariants & Principles (preserved — MUST hold)
1. **Global Record ≠ Tenant Record.** Control-plane/global records (tenant registry, operational audit) are separate from tenant-resident lineage. Lineage *about a tenant's data* lives only in that tenant's database; the Control DB MUST NOT hold tenant-data lineage, and global records MUST NOT embed it.
2. **Import ≠ Synchronization.** Lineage records an import as a **discrete, one-directional sourced event**. It MUST NOT model an ongoing two-way sync or a live link back to the source. Re-imports append new lineage entries (chained), never mutate prior ones.
3. **One request → one active tenant → one database** (D-04). Every lineage read/write occurs within exactly one active tenant context, in that tenant's database only.
4. **No shared tenant databases.** Lineage is never stored in a shared multi-tenant table or store.
5. **Secret values never appear in lineage records.**
6. **References, not raw values.** Sources, targets, actors, credentials, configs, and payloads are captured as **stable references** — never raw credentials, tokens, or data payloads.

## Lineage Principles
- **Provenance over payload:** lineage records *what happened, to which record, from where, by whom* — by reference, not by copying data or secrets.
- **Tenant-resident:** provenance of tenant data is stored with that tenant (Principle 1).
- **Append-only truth:** lineage is an immutable, append-only history (see *Immutability*).
- **Uniform across origins:** import (now) and AI-derivation (later) emit lineage through the **same** model (Principle: AI-ready, D-02).
- **Independent per tenant** (D-16): a tenant's lineage availability is independent of other tenants.

## Scope
- The **minimum lineage record** and the events that MUST emit lineage.
- **Source/target reference** model (references only).
- **Actor identity** and **tenant context** capture (D-03, D-04, D-05, D-07).
- **Import lineage** (handoff from [IC-003](IC-003-Import-Contract.md)) and **AI-ready** lineage structure (D-02; no AI implementation).
- **Append-only/immutability**, **retention/archival**, **access control**, **cross-tenant isolation**, **failure behavior**.
- Relationship to operational audit (IC-002) and to readiness/migration (D-16, D-17).

## Non-goals
- Performing imports or transformations (see [IC-003](IC-003-Import-Contract.md); [IC-006](IC-006-AI-Gateway-Contract.md) later).
- **Operational/control-plane audit of tenant lifecycle** — that is IC-002 (*Global Record ≠ Tenant Record*).
- General application logging unrelated to data provenance.
- Defining any AI provider, prompt, or output behavior (D-02 deferred; IC-006).
- Any implementation, schema migration, or storage code.

## Minimum Lineage Record
> Specifies **D-22** (approved): a fixed minimal core plus a reference/code-only extension envelope. Field shapes only — **no code, no payloads, no secrets.** Every field that points outside the record is a **reference**.

| Field | Required | Meaning |
|---|---|---|
| `lineage_id` | MUST | Stable, unique identifier (tenant-scoped). |
| `tenant_id` | MUST | The single active tenant (D-04); MUST equal the database the record resides in. |
| `event_type` | MUST | `import` \| `transform` \| `correction` \| `ai-derivation` (the last reserved, AI-ready). |
| `occurred_at` | MUST | When the event happened (plus `recorded_at` if capture differs). |
| `actor_ref` | MUST | Reference to the responsible identity (see *Actor Identity*) — never a token/credential. |
| `source_ref` | MUST (for sourced events) | Reference to the origin (import source descriptor + record key/offset) — never the payload or source credentials. |
| `target_ref` | MUST | Reference to the affected tenant record(s) in the active tenant DB. |
| `operation` | MUST | What was done (`created` / `updated` / `derived` / …) — described, not the data. |
| `schema_version` | MUST | Tenant schema version at capture (ties D-17). |
| `integrity_marker` | MUST | Append-only / tamper-evidence marker (see *Immutability*). |
| `derivation_ref` | MAY | Reference to the producing process (import job id; AI operation ref later). |
| `parent_lineage_ref` | MAY | Prior lineage entry, forming the provenance chain. |
| `correlation_id` | MAY | Request/operation correlation. |

A record MUST NOT contain raw imported payloads, secret values, or raw credentials under any field.

Per **D-22**, a reserved **reference/code-only extension envelope** MAY carry compliance- or AI-specific metadata (e.g., purpose/jurisdiction codes per D-08; AI process references) **without contract change**. The envelope is held to the same rule — references and codes only, never payloads, PII, or secrets. Change-evidence references versions/markers rather than hashing raw payloads.

## Source and Target References
- **`source_ref`** identifies *where data came from* (e.g., an import source descriptor reference plus a record key/offset). It MUST NOT contain the source connection's credentials (those are D-14 secret references held elsewhere) nor the raw imported payload.
- **`target_ref`** identifies the affected tenant record(s) within the **active tenant database** only.
- All references are stable identifiers resolvable in their proper scope and MUST NOT encode secrets.
- Any import-source connection secret is referenced via the **D-14** reference-based abstraction and MUST NOT appear in lineage.

## Actor Identity Requirements
Per the **hybrid identity model** (D-03) and **OIDC stateless JWT** authentication (D-05):
- Every lineage record MUST capture an **`actor_ref`** — an identity reference (e.g., the authenticated subject) for an **internal platform identity** (operator) or a **federated external-org principal**. It MUST NEVER store a token, JWT, or credential.
- For automated, system-originated events (e.g., a scheduled import), the actor is the responsible **service/control-plane identity**.
- The **Phase-0 bootstrap system identity** (D-01) MUST NEVER appear as a tenant-data lineage actor — it cannot touch tenant databases.
- AI-derived events (later) capture the invoking principal **plus** an AI-process reference (`derivation_ref`) — AI-ready, no AI specifics here.

## Tenant Context Requirements
- Lineage is written within **exactly one active tenant context** (D-04) into that tenant's database, resolved **registry-authoritatively** (D-07).
- The record's `tenant_id` MUST equal the resolved tenant database; cross-tenant lineage writes are prohibited.
- No lineage operation may span tenants or databases (Invariant 3).

## Import Lineage Requirements
> Handoff from [IC-003](IC-003-Import-Contract.md).
- Every import that creates or updates tenant data MUST emit a lineage record (`event_type = import`) capturing at least `source_ref`, `target_ref`, `actor_ref`, `occurred_at`, `operation`, `derivation_ref` (the import job), and `schema_version`.
- **Import ≠ Synchronization** (Invariant 2): the record is a discrete sourced ingestion event; it MUST NOT imply continuous two-way sync. **Re-imports append new lineage** (chained via `parent_lineage_ref`) and MUST NOT mutate prior entries.
- Idempotent re-import (IC-003 idempotency, **D-20**, open) MUST still produce attributable lineage reflecting the de-duplication outcome (applied vs. no-op) without misleading duplication; exact semantics defer to IC-003.
- Import source credentials and raw payloads MUST NOT be stored in lineage (references only).

## AI-Ready Lineage Requirements (no AI implementation)
> Per **D-02** (AI deferred post-MVP, architecture AI-ready). This section adds **structural readiness only**.
- The model MUST accommodate AI-derived events **without change**: the reserved `event_type = ai-derivation`, a `derivation_ref` to an AI operation, and `parent_lineage_ref` chaining derived data to its inputs.
- A single provenance **graph** spans `import → transform → ai-derivation` within the **same tenant** (**D-25**, approved): `parent_lineage_ref` links events end-to-end. The graph **never crosses tenants**, and the D-23 integrity chain is kept per-tenant and segmentable — provenance linkage is distinct from tamper-evidence ordering.
- **No** AI provider, prompt, model, or output content is specified or stored here.
- PII/redaction for AI egress is **out of scope** (D-09; IC-006); the chain need only be able to record *that* an AI derivation occurred, by reference.

## Immutability / Append-Only Model
> Specifies **D-23** (approved): defense-in-depth enforcement.
- Lineage records are **append-only and immutable**: once written, a record MUST NOT be updated or deleted in normal operation (the sole exception is policy-driven retention/archival expiry, below).
- **Corrections are appends:** a correcting record is added that references the corrected entry (`parent_lineage_ref`) — history is never mutated.
- **Enforcement is defense-in-depth (D-23):** **(1)** DB-level append-only — privilege separation plus rejection of `UPDATE`/`DELETE` on lineage; **(2)** **per-tenant cryptographic hash-chaining** as the `integrity_marker`, where each record hashes its content plus the prior record's hash, making any tampering or deletion detectable. Preventive **and** detective. Any keyed-hash key is a **D-14** reference, never stored in lineage. Detected chain breaks MUST be alarmed and operationally audited (IC-002).
- Enforcement MUST remain **standard-PostgreSQL/portable** (no provider-proprietary immutability features).

## Retention and Archival Considerations
> Specifies **D-24** (approved mechanism); retention *values* derive from the **D-08** compliance floor/ceiling (business/legal).
- Retention and archival are **per-tenant configurable within a compliance-driven floor/ceiling** (D-24, D-08). Hot lineage lives in the tenant DB; archival is to a **portable** cold tier that preserves immutability and **chain verifiability** — the D-23 integrity chain is **segmented/checkpointed** so archived or expired segments remain verifiable. The retention *values* (floor/ceiling, residency) derive from the named compliance regime — a standing **D-08** business/legal action.
- Archival MUST preserve immutability, references, and attributability, and MUST remain isolation-preserving (per-tenant).
- **Policy-driven expiry/deletion is the only sanctioned removal** and MUST itself be operationally audited (IC-002), clearly distinguished from prohibited mutation. Expiry and **right-to-erasure** are reconciled with append-only via the reference-only model: **erase the referent data (or crypto-erase) and leave a tombstone reference**, so non-personal provenance and chain integrity are preserved — the chain is never silently broken.
- Retention MAY vary per tenant (e.g., per organization/compliance) and is stored per tenant (no shared store).

## Access Control
- Reading lineage is a **tenant-scoped, authenticated, authorized** operation — **OIDC stateless JWT** (D-05), **hybrid identity** (D-03), within **exactly one active tenant** (D-04).
- Only principals authorized for that tenant may read its lineage; **cross-tenant lineage reads are prohibited**.
- Lineage can reveal sensitive operational detail; access SHOULD be least-privilege and itself auditable.
- The **Phase-0 system identity** (D-01) MUST NEVER read tenant lineage.

## Cross-Tenant Isolation
- A tenant's lineage resides **solely in that tenant's physical database** (Invariants 1 & 4); the Control DB holds none of it.
- No query may join or span tenants' lineage. Cross-tenant provenance analysis, if ever required, MUST be performed as **explicit, audited, per-tenant** control-plane reads — never a spanning query (consistent with IC-002).
- A single active tenant per request governs every lineage read/write (D-04).

## Audit Requirements
- **Lineage (data provenance, tenant-resident)** and **operational audit (control-plane actions, IC-002)** are **distinct** (Invariant 1) and one is not a substitute for the other.
- Administrative actions **on lineage itself** — policy-driven expiry, archival, access-policy changes — MUST be recorded in **operational audit** (IC-002), not silently performed.
- Failed/denied lineage reads SHOULD be auditable.

## Multi-Database Compatibility
- Lineage is stored **per tenant in that tenant's physically separate PostgreSQL database**; never shared (Invariant 4).
- Access uses **registry-authoritative** resolution (D-07) and the **per-tenant pooled connection** model (D-13) — a connection is never reused across tenants.
- Must run on **standard PostgreSQL** (AWS RDS / Azure / Google Cloud SQL / self-hosted); no provider-proprietary features (including for append-only/immutability or change-data-capture).
- The lineage schema participates in **expand/contract migrations with version-gated readiness** (D-17): a tenant outside the supported schema range is not-ready, and lineage capture for it follows readiness rules.
- **Per-tenant independence** (D-16): one tenant's lineage store being unavailable MUST NOT affect others; any `degraded` signal is observability-only.

## Composition Boundary (D-44 / IC-012)
> **References-only cross-reference. No lineage semantic is altered by this section.**
- The `LineageEmitPort` implementation consumed by the Import edge is **injected by the `deployment` cross-service composition root** (D-44; IC-012 §7), built from this service's own published seam (`lineage_service.emit.LineageEmit`) over the **tenant-scoped, reference-only** secret store with the `"tenant"` key prefix — the composed-core convention that keeps the chain per-tenant and never crossing tenants (D-25; *Cross-Tenant Isolation*).
- **Lineage semantics remain wholly owned by `lineage_service`.** The *Minimum Lineage Record*, *Source and Target References*, *Actor Identity Requirements*, *Tenant Context Requirements*, *Import Lineage Requirements*, the per-tenant cryptographic hash chain and *Immutability / Append-Only Model* (D-23), *Retention and Archival Considerations* (D-24), unified provenance (D-25), *Access Control*, *Cross-Tenant Isolation*, and *Failure Behavior* are all unchanged. The composition root MUST NOT reimplement, wrap with behaviour, filter, reorder, suppress, synthesize, or interpret any lineage record (IC-012 §7/§17).
- No lineage double, no-op emitter, or test substitute is ever composed on the production path (IC-012 §11).
- This section grants **no lineage field, no emission rule, no access capability, and no DDL**.

## Anti-Vendor-Lock-In Requirements
- **No Supabase-specific** lineage/storage logic and no Supabase Auth (access is OIDC via IC-005).
- **No Lovable-specific** runtime dependencies.
- **No provider-proprietary PostgreSQL** features (including CDC or proprietary immutability); portable across RDS / Azure / Cloud SQL / self-hosted.
- Secret references use the portable **D-14** abstraction; no secrets in lineage.
- AI-ready structure MUST NOT bind to any specific AI provider (D-02; IC-006 later).

## Failure Behavior
- **Atomic provenance:** because lineage lives in the same tenant database as the data, a lineage record for a data-mutating event SHOULD be written **in the same transaction** as the change, so committed data can never exist without its provenance. A required-lineage operation (e.g., import) MUST NOT silently commit data while failing to record lineage.
- **Tenant DB / lineage store unavailable:** the tenant is **not-ready** (D-16); operations on it are denied (consistent with IC-002), so no orphaned data-without-lineage arises. Other tenants are unaffected.
- **Read failures:** defined denial semantics; a read MUST NEVER fall back to another tenant.
- **Phase 0** (D-01): no tenant lineage is accessible.
- **Append-only violations:** any attempt to update/delete a lineage record (outside sanctioned expiry) MUST be rejected and SHOULD be flagged and operationally audited.
- **Secrets/payloads:** writing a secret value or raw payload into lineage is a contract violation; the model is reference-only by construction (Invariants 5 & 6).

## Lineage Decisions (resolved)
The lineage decisions that previously gated this contract are now approved and incorporated above (see [Architecture-Decision-Register.md](../docs/Architecture-Decision-Register.md)):
- **D-08** — configurable multi-regime compliance model, SOC 2-style floor + per-tenant parameters (*Retention and Archival*, *Access Control*). **Standing business/legal action:** name the specific floor regime and per-tenant values.
- **D-22** — minimal core record + reference/code-only extension envelope (*Minimum Lineage Record*).
- **D-23** — defense-in-depth immutability: DB append-only + per-tenant cryptographic hash-chaining (*Immutability / Append-Only Model*).
- **D-24** — per-tenant configurable retention/archival within a compliance floor/ceiling; segmented verifiable archival; expiry via tombstones (*Retention and Archival*).
- **D-25** — unified per-tenant provenance graph + segmentable integrity chain (*AI-Ready Lineage Requirements*, *Immutability*).

No lineage architecture decisions remain open for this contract. Cross-references owned elsewhere: IC-003 import idempotency (**D-20**) shapes re-import lineage semantics; AI PII/redaction (**D-09**, IC-006) shapes AI lineage when AI is built (D-02, post-MVP).

> **Status:** IC-004 is **Final** for MVP architecture. All lineage architecture decisions are resolved; the standing **D-08** business/legal parameters and downstream IC-003 / IC-006 cross-references are non-architecture and do not reopen the contract.
