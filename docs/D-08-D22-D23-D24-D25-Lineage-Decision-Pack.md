# Decision Pack — Lineage (D-08, D-22, D-23, D-24, D-25)

**Type:** Architecture analysis only · **Phase:** Architecture Planning
**Purpose:** Resolve the remaining **IC-004** lineage decisions before promoting IC-004 from **Draft → Reviewed**.
**Scope:** Analysis and recommendations only. No implementation code, schema, migrations, backend services, or infrastructure code.
**Date:** 2026-06-05 · See also: [IC-004](../contracts/IC-004-Lineage-Contract.md), [Architecture-Decision-Register.md](Architecture-Decision-Register.md), [Contract-Gap-Analysis.md](Contract-Gap-Analysis.md)

## Binding constraints (apply to every option below)
- **Global Record ≠ Tenant Record**; **Import ≠ Synchronization**.
- **One request → one active tenant → one database**; **no shared tenant databases**.
- **Secrets never appear in lineage**; **references only, never raw payloads**.
- **PostgreSQL portable**; **no vendor-specific immutability features**.
- **AI is post-MVP, but lineage must remain AI-ready** (D-02).

Any option breaching these is out of contract regardless of other merits.

## How these decisions relate
**D-08** is the upstream business/legal **driver**: it sets the *values* for **D-24** (retention) and the required *strength* for **D-23** (immutability). **D-22** (the record) underpins everything; **D-25** (provenance graph) and **D-23** (integrity chain) are related but distinct concepts. Suggested order: **D-08 → D-22 → D-25 → D-23 → D-24**. Of these, **only D-08 genuinely requires business/legal sign-off**; D-22–D-25 are architecture decisions recommended decisively below.

---

# D-08 — Compliance / Regulatory Driver

### 1. Decision description
Which compliance/regulatory regime(s) drive lineage requirements? This business/legal input sets retention duration (D-24), immutability strength (D-23), and access rigor.

### 2. Why it matters
It is the upstream driver for D-23/D-24 and access control. Too weak risks non-compliance; too strong wastes effort and cost. Architecture must accommodate the chosen regime **portably** and per tenant (external orgs differ, D-03).

### 3. Available options
- **A — GDPR-class first** (EU data protection): data-subject rights incl. **erasure**, purpose limitation, residency.
- **B — Security-integrity baseline** (SOC 2-style): tamper-evidence, access control, retention; no erasure mandate.
- **C — Sector-specific heavy** (HIPAA / financial / SOX): long mandated retention, strong immutability, detailed audit.
- **D — Configurable multi-regime baseline:** a strong common floor + **per-tenant** regime parameters (retention, residency).

### 4. Pros and cons
| Option | Pros | Cons |
|---|---|---|
| A — GDPR-first | Covers EU orgs; privacy-by-design; solves erasure early | **Right-to-erasure vs append-only** is a real conflict to reconcile; may over-index on one regime |
| B — SOC 2 baseline | Aligns naturally with append-only + tamper-evidence + access (what lineage already is); lighter | Insufficient alone for regulated sectors or EU privacy specifics |
| C — Sector-specific | Meets the hardest mandates; de-risks regulated customers | Heaviest; likely premature if those customers aren't in MVP; cost |
| D — Configurable multi-regime | Fits multi-tenant reality (per-org compliance varies); strong floor + per-tenant params; future-proof | Must define floor + parameter surface; business must still name the floor |

### 5. Impact on IC-004
Sets retention values (D-24) and immutability strength (D-23). The **reference-only, secrets-never** model already advances GDPR (no payloads/PII copied into lineage). Key reconciliation: because lineage stores **references not payloads**, **erasing the referenced data** can satisfy erasure while lineage retains **non-personal provenance metadata** — append-only history is preserved.

### 6. Impact on IC-003 Import
Determines what import must attribute for auditability and reinforces that import lineage stores **no payloads/PII** (already mandated) — which aligns cleanly with GDPR-class data minimization.

### 7. Impact on future IC-006 AI Gateway
Drives AI-provenance/egress obligations (recording *that* data was sent to an AI provider; residency for AI). The AI-ready chain must record an AI derivation by reference for audit; long-retention regimes retain AI-derivation lineage too. PII egress policy is downstream (D-09).

### 8. Impact on physical multi-database architecture
Per-tenant physical isolation supports **per-tenant compliance and residency** (a tenant DB can sit in a required region, ties D-07 placement). Configurable per-tenant retention/residency maps cleanly to one-DB-per-tenant; erasure is per-tenant scoped.

### 9. Recommended option
**D — configurable multi-regime baseline** with a **security-integrity floor (SOC 2-style: append-only, tamper-evident, access-controlled, audited)** plus **per-tenant configurable retention/residency** for GDPR/sector needs. **Design the erasure-vs-immutability reconciliation now** (reference-only + erase-the-referent / crypto-erasure), since GDPR-class orgs are likely. **Business/legal MUST name the floor regime and any must-support regimes** — architecture cannot decide compliance.

### 10. Open risks
Right-to-erasure vs append-only (must design crypto-erasure / referent deletion); per-region residency (placement, D-07); under/over-scoping the regime; per-tenant parameter sprawl; **legal sign-off required**. Sets D-23/D-24 values.

---

# D-22 — Minimum Lineage Record

### 1. Decision description
The minimal field set every lineage record MUST contain (proposed in IC-004); this formalizes it.

### 2. Why it matters
Too sparse → can't trace provenance or satisfy audit/compliance; too rich → risk of capturing payloads/PII/secrets (constraint breach) and bloat. It is the contract every emitter (import now, AI later) must satisfy uniformly.

### 3. Available options
- **A — Minimal core:** the proposed set (`lineage_id`, `tenant_id`, `event_type`, `occurred_at`, `actor_ref`, `source_ref`, `target_ref`, `operation`, `schema_version`, `integrity_marker`; optional `derivation_ref` / `parent_lineage_ref` / `correlation_id`).
- **B — Extended:** add classification/sensitivity tags, jurisdiction, processing-purpose, before/after value hashes.
- **C — Core + reserved extension envelope:** fixed mandatory core + a typed, **reference/code-only** extension area for regime/AI metadata (no payloads).

### 4. Pros and cons
| Option | Pros | Cons |
|---|---|---|
| A — Minimal core | Lean; clearly excludes payloads/secrets; uniform; AI-ready via `event_type`/`derivation_ref` | May lack regime attributes (purpose, jurisdiction) some compliance needs |
| B — Extended | Richer audit/compliance out of the box | Bigger surface; **value hashes risk re-identification/PII inference**; scope-creep toward payload-ish data |
| C — Core + envelope | Stable core + room for regime/AI metadata without contract change; payloads kept out by typing the envelope | Envelope needs governance to prevent payload/secret leakage |

### 5. Impact on IC-004
This is IC-004's central data model. The core ties `schema_version` to D-17 and `integrity_marker` to D-23. If change-evidence is wanted, **reference versions/markers rather than hashing payloads** (hashing raw payloads risks re-identification and edges toward storing data).

### 6. Impact on IC-003 Import
Import MUST populate the core for every sourced event (`source_ref`, `derivation_ref` = job, `operation`, `actor_ref`); the extension envelope is optional for import-specific codes. No payloads.

### 7. Impact on future IC-006 AI Gateway
Reserved `event_type = ai-derivation` + `derivation_ref` + envelope (model/process **references**, never prompt/output content) accommodate AI with no contract change — pure AI-readiness.

### 8. Impact on physical multi-database architecture
The record is tenant-resident with identical structure across all tenant DBs (no shared table). The envelope must use **standard PostgreSQL types** (portable). `schema_version` participates in per-tenant migration (D-17).

### 9. Recommended option
**C — the proposed minimal core (MUST) + a reserved, reference/code-only extension envelope** for compliance/AI metadata. Forbid payloads, PII, and secrets in **any** field including the envelope. Avoid raw payload value-hashes (re-identification risk); reference versions instead.

### 10. Open risks
Extension-envelope governance (must enforce reference/code-only, not a payload dumping ground); value-hash re-identification if added; ensuring every emitter satisfies the core; cross-emitter (import vs AI) consistency. Ties to D-08 (which attributes) and D-23 (`integrity_marker`).

---

# D-23 — Immutability Enforcement Mechanism

### 1. Decision description
*How* append-only/immutability is enforced and made tamper-evident — DB-level, application-level, cryptographic chaining, or a combination — all PostgreSQL-portable, **no vendor-specific features**.

### 2. Why it matters
Sets the strength of the integrity guarantee (preventive vs detective), portability, performance, and compliance sufficiency (D-08). Vendor proprietary ledgers are banned, so the mechanism must be portable.

### 3. Available options
- **A — Application-level only:** the app refuses updates/deletes; relies on code + access control.
- **B — Database-level constraints:** privilege separation + triggers/rules rejecting `UPDATE`/`DELETE` on lineage (append-only in-DB), standard PostgreSQL.
- **C — Cryptographic hash-chaining:** each record's `integrity_marker` hashes its content + the prior record's hash; any tampering is detectable; portable (stored as ordinary data).
- **D — Defense-in-depth (B + C):** preventive DB append-only **and** detective chaining, with least-privilege roles.

### 4. Pros and cons
| Option | Pros | Cons |
|---|---|---|
| A — App-only | Simplest; portable | Weakest; a DB actor or bug bypasses it; not tamper-evident; likely insufficient for regulated D-08 |
| B — DB-level | Preventive at the data layer; standard PostgreSQL; resists app bugs | A privileged role can still alter (needs privilege separation); not inherently tamper-evident after the fact; trigger overhead |
| C — Crypto chaining | Strong **tamper-evidence**; portable; independently verifiable; great for compliance | Detective not preventive; chain verification cost; must define break-handling |
| D — Defense-in-depth | Preventive + detective + least-privilege; strongest, still portable | Most to operate; chaining + trigger overhead |

### 5. Impact on IC-004
Defines `integrity_marker` semantics and gives the append-only guarantee teeth. Corrections-as-appends already specified. A keyed-hash variant would reference its key via **D-14** (never store the key in lineage).

### 6. Impact on IC-003 Import
High-volume import appends must stay performant: prefer **per-tenant** chains and batch appends. Interacts with **atomic provenance** (same-transaction lineage) and chain ordering — flag for IC-003.

### 7. Impact on future IC-006 AI Gateway
AI-derivation appends use the same mechanism unchanged; strong immutability supports auditability of AI-driven changes.

### 8. Impact on physical multi-database architecture
**Per-tenant chains** (each tenant DB has its own) preserve isolation and per-tenant independence (D-16) — no cross-tenant chain. Standard PostgreSQL only (no vendor ledger). Migration (D-17) must preserve chain continuity.

### 9. Recommended option
**D — defense-in-depth:** DB-level append-only (privilege separation + reject `UPDATE`/`DELETE`) **plus** **per-tenant cryptographic hash-chaining** as the `integrity_marker`. Preventive + detective, fully portable, no vendor features. Detected chain breaks MUST be alarmed and operationally audited (IC-002). Any keyed-hash key is a D-14 reference, never in lineage.

### 10. Open risks
Sequential per-tenant chaining vs high-volume import throughput (segment/batch; per-tenant parallelism is fine); privileged-role bypass (separate the lineage-writer role; restrict superuser); chain-break response process; migration must not break the chain (D-17); keyed-hash key management (D-14). Strength tie to D-08.

---

# D-24 — Retention and Archival Policy

### 1. Decision description
How long lineage is retained, where/how it is archived, and what (if anything) may be expired — given D-08 sets values and append-only forbids casual deletion.

### 2. Why it matters
Sets storage growth/cost, compliance sufficiency, and the **only sanctioned exception** to append-only (policy expiry). Must reconcile retention with immutability and any erasure obligation (D-08).

### 3. Available options
- **A — Indefinite retention** (never delete).
- **B — Fixed global window + archival tier** (hot → cold/archive after N, expire after M).
- **C — Per-tenant configurable retention + archival** within a compliance-driven floor/ceiling (fits D-03 + D-08).

(Erasure cross-cuts all: because lineage is reference-only, **erase the referent**; non-PII provenance metadata persists or is crypto-erased.)

### 4. Pros and cons
| Option | Pros | Cons |
|---|---|---|
| A — Indefinite | Maximal auditability; trivially consistent with append-only | Unbounded cost; conflicts with data-minimization/erasure (GDPR) |
| B — Fixed window + archive | Bounded cost; clear policy; tiering balances access vs cost | One-size may not fit diverse orgs; expiry must reconcile with immutability/audit |
| C — Per-tenant configurable | Fits multi-tenant compliance; per-org retention/residency; honors minimization | Config governance; must enforce floor (compliance min) and ceiling (minimization max) |

### 5. Impact on IC-004
Provides the values/mechanism for the Retention section. **Policy-driven expiry is the only sanctioned removal**, MUST be operationally audited (IC-002), and MUST preserve chain integrity (D-23): **segment/checkpoint** the hash chain so archived/expired segments stay verifiable and expiry is not mistaken for tampering.

### 6. Impact on IC-003 Import
Import volume drives lineage growth → retention/archival sizing. Re-import chains (Import ≠ Sync) accumulate; archival must keep chains verifiable.

### 7. Impact on future IC-006 AI Gateway
AI-derivation lineage is equally subject to retention; long-retention regimes retain AI provenance; archival must keep AI-derivation references intact.

### 8. Impact on physical multi-database architecture
Per-tenant DBs → **per-tenant retention/archival** naturally; the archive target must be **portable** (no vendor-proprietary archive); per-tenant independence (D-16) means archiving one tenant doesn't affect others; residency keeps the archive in-region per tenant (D-07).

### 9. Recommended option
**C — per-tenant configurable retention + archival within a compliance-driven floor/ceiling (D-08).** Hot lineage in the tenant DB; archive to a **portable** cold tier that preserves immutability + chain verifiability (segment/checkpoint per D-23). **Policy-driven expiry only, operationally audited.** Reconcile erasure via reference-only + referent deletion / crypto-erasure, using **tombstone references** so the chain stays intact (never silently break it).

### 10. Open risks
Reconciling expiry/erasure with the append-only chain (segmentation/tombstones/crypto-erasure — must be distinguishable from tampering); archival portability (no vendor lock-in); per-tenant floor/ceiling governance; storage growth from high-volume import; **legal sign-off on values (D-08).**

---

# D-25 — Unified Provenance Chain

### 1. Decision description
Should provenance be a **single unified per-tenant chain/graph** spanning `import → transform → ai-derivation` (proposed yes), or **separate per-origin chains**? Defines whether `parent_lineage_ref` links across event types.

### 2. Why it matters
Determines whether a derived/AI record can be traced back through transforms to its imported source in one structure — central to lineage value and compliance. Also interacts with D-23 (one chain vs many) and AI-readiness.

### 3. Available options
- **A — Unified per-tenant chain/graph:** all event types link via `parent_lineage_ref` into one traceable structure.
- **B — Separate chains per origin/type:** no cross-type links.
- **C — Unified provenance *graph* + segmented integrity *chain*:** `parent_lineage_ref` gives end-to-end traceability; the D-23 tamper-evidence chain is per-tenant and may be segmented (time-window) for archival/throughput.

### 4. Pros and cons
| Option | Pros | Cons |
|---|---|---|
| A — Unified chain | Full end-to-end traceability; best compliance/value; AI-ready | A strict single linear hash-chain across all events can bottleneck high-volume/concurrent appends; cross-type ordering tricky |
| B — Separate chains | Simpler per type; less contention | Breaks end-to-end traceability; poor for AI provenance and compliance |
| C — Graph + segmented integrity | End-to-end traceability **and** practical, scalable tamper-evidence; archival-friendly (D-24) | Two related concepts (provenance links vs integrity chain) to define clearly |

### 5. Impact on IC-004
This is the provenance-graph decision. Keep `parent_lineage_ref` as a **unified per-tenant provenance graph** (full traceability) while the D-23 integrity chain is per-tenant and segmentable — distinguishing **provenance linkage** (graph) from **tamper-evidence ordering** (chain). The reserved `ai-derivation` participates in the same graph.

### 6. Impact on IC-003 Import
Import events are graph roots/sources; re-imports append as new nodes chained via `parent_lineage_ref` (Import ≠ Sync). Bulk import = many roots; graph + segmented integrity handles volume.

### 7. Impact on future IC-006 AI Gateway
AI-derivation nodes link to their input nodes (which may trace back to import), giving **AI output → source** traceability with no contract change — the core AI-readiness payoff.

### 8. Impact on physical multi-database architecture
The graph is **per-tenant, within one tenant database** — it MUST NOT span tenants (no cross-tenant joins; Global ≠ Tenant). Cross-tenant provenance is impossible by design. Segmentation aids per-tenant archival (D-24) and migration (D-17). Standard PostgreSQL self-referential references (no vendor graph features).

### 9. Recommended option
**C — unified per-tenant provenance graph (via `parent_lineage_ref`) for end-to-end traceability, with the D-23 integrity chain kept per-tenant and segmentable.** Confirms D-25 "yes, unified" while staying scalable and archival-friendly. The graph never crosses tenants.

### 10. Open risks
Cleanly separating provenance-linkage from integrity-chaining (else confusion); graph cycles/orphans (enforce acyclic, valid parent refs); cross-type ordering; keeping the graph within one tenant DB (isolation); deep-chain query performance. Ties to D-23 (segmentation), D-24 (archival), D-02/IC-006 (AI nodes).

---

## Consolidated recommendations (at a glance)

| ID | Decision | Recommended | Primary driver |
|---|---|---|---|
| **D-08** | Compliance driver | **Configurable multi-regime, SOC 2-style floor + per-tenant params**; design GDPR erasure reconciliation now (**business/legal to name the floor**) | Multi-tenant compliance reality |
| **D-22** | Minimum record | **Minimal core (MUST) + reference/code-only extension envelope** | Provenance sufficiency without payloads/PII |
| **D-23** | Immutability mechanism | **Defense-in-depth: DB append-only + per-tenant crypto hash-chaining** | Preventive + detective, portable |
| **D-24** | Retention/archival | **Per-tenant configurable within compliance floor/ceiling; segmented, verifiable archival; expiry-only via tombstones** | Cost + compliance + immutability |
| **D-25** | Provenance chain | **Unified per-tenant provenance graph + segmentable integrity chain** | End-to-end traceability, AI-ready |

**Decision order:** D-08 (business/legal) → D-22 → D-25 → D-23 → D-24. **D-08 is the only item requiring business/legal sign-off**; D-22–D-25 are architecture and recommended decisively. Approving these resolves IC-004's open decisions and unblocks **IC-004 Draft → Reviewed**, after which **IC-003 Import** has both upstream contracts ready. All recommendations preserve *Global Record ≠ Tenant Record*, *Import ≠ Synchronization*, *one request → one active tenant → one database*, *no shared tenant databases*, secrets-never/references-only, PostgreSQL portability, no vendor-specific immutability, and AI-readiness.
