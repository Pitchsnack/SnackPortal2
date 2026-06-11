# Decision Pack — Import (D-18, D-19, D-20, D-21, D-09 ingress)

**Type:** Architecture analysis only · **Phase:** Architecture Planning
**Purpose:** Resolve the remaining **IC-003 Import** decisions before promoting IC-003 from **Draft → Reviewed**.
**Scope:** Analysis and recommendations only. No implementation code, schema, migrations, backend services, or infrastructure code.
**Date:** 2026-06-05 · See also: [IC-003](../contracts/IC-003-Import-Contract.md), [IC-004](../contracts/IC-004-Lineage-Contract.md), [Architecture-Decision-Register.md](Architecture-Decision-Register.md), [Contract-Gap-Analysis.md](Contract-Gap-Analysis.md)

## Binding constraints (apply to every option below)
- **Global Record ≠ Tenant Record**; **Import ≠ Synchronization**; **import creates a tenant-owned copy**.
- **Tenant changes never affect Global**; **Global changes never affect imported Tenant records**.
- **One request → one active tenant → one database**; **no shared tenant databases**.
- **Lineage emitted per IC-004**; **secrets never in payloads, lineage, audit, or responses**; **references only, never raw credentials or payloads**.
- **PostgreSQL portable**; **no provider-specific bulk-load or import pipeline**; **AI remains post-MVP** (this pack resolves the **ingress** slice of D-09 only; AI egress stays with IC-006).

Any option breaching these is out of contract regardless of other merits.

## How these decisions relate
**D-18** (formats) drives **D-09 ingress** (how those formats are validated/sanitized) and **D-21** (malformed-record handling). **D-19** (execution mode) frames **D-21** (batching) and **D-20** (retry idempotency); **D-20 and D-21 are tightly coupled** (resumable batches + idempotent re-runs). Suggested order: **D-18 → D-09 ingress → D-19 → D-21 → D-20**. None requires business sign-off beyond the **D-08** compliance parameters already resolved (D-09 ingress consumes them); **D-18 is partly a product/scope call**.

---

# D-18 — Import Source Formats in Scope for v1

### 1. Decision description
Which source formats/channels are supported for v1. The **Global-to-tenant copy** is the architectural core (internal); this decides which **external** sources also feed imports.

### 2. Why it matters
Sets the ingestion surface, the validation/sanitization burden (D-09 ingress), the upload-security surface, and effort. Too many formats blow up scope/security; too few limit value.

### 3. Available options
- **A — Global record only** (internal copy); no external formats in v1.
- **B — Global + structured files** (CSV/JSON via client upload).
- **C — Global + files + API pull** (connectors to external systems).
- **D — Pluggable source-adapter abstraction** with a small v1 set (Global + CSV/JSON), extensible without contract change.

### 4. Pros and cons
| Option | Pros | Cons |
|---|---|---|
| A — Global only | Smallest surface; fully internal; minimal ingestion risk; fastest | No external "bring your data" onboarding |
| B — + CSV/JSON | Covers the common case; structured/parseable; bounded | Upload scanning, size limits, malformed handling; PII at ingress (D-09) |
| C — + API pull | Powerful integrations | Source credentials (D-14 refs), connector upkeep, external availability; **risk of drifting into sync** (must stay Import ≠ Sync) |
| D — Adapter + small v1 set | Extensible without contract churn; v1 stays small | Must define the adapter boundary; governance to keep adapters portable + secret-clean |

### 5. Impact on IC-003
Defines the `StartImport` source surface. Copy/ownership/lineage semantics are **source-agnostic**, so adding formats never changes the invariants; validation/rejection scales with formats (ties D-21, D-09).

### 6. Impact on IC-004 Lineage
`source_ref` represents each source type **by reference** (Global record ref; file descriptor + key/offset; external API source descriptor) — never the payload or credentials. More source types = more `source_ref` shapes, all reference-only.

### 7. Impact on IC-002 Tenant Startup
None structural; import still requires a `Ready` tenant. High-volume formats (bulk CSV) interact with connection capacity (D-13) and schema-version gating (D-17).

### 8. Impact on IC-005 Authentication Routing
API-pull sources need **source credentials (D-14 references)**, but the import **caller** still authenticates via IC-005 (OIDC); source creds are separate from caller auth and never alter tenant-context establishment.

### 9. Impact on physical multi-database architecture
All formats write to the **one active tenant DB**; no shared DB. Ingestion MUST be **portable** — no provider bulk-load (even CSV uses portable client-side load, not cloud-bucket-to-DB). API pull MUST remain a discrete copy, never a live link (Import ≠ Sync).

### 10. Recommended option
**D — pluggable source-adapter abstraction with a minimal v1 set: the Global record + structured CSV/JSON (client upload).** Defer API-pull connectors to a later adapter to bound the ingestion-security surface. All adapters normalize to records, write the tenant copy, emit lineage, reference-only.

### 11. Open risks
Upload security (file-type/content scanning, size limits — ties D-09); malformed data (D-21); adapter governance (portability, no secrets); API-pull later must not drift into sync; format sprawl. Ties D-09, D-21, D-13.

---

# D-19 — Import Execution Mode: Synchronous vs Asynchronous + Progress

### 1. Decision description
Are imports synchronous (request blocks to completion) or asynchronous (submit → job id → poll/notify), and how is progress reported?

### 2. Why it matters
Sets UX, scalability (bulk can't block a request), connection-holding (D-13), failure/retry handling (D-20/D-21), and how status is exposed. Determines whether import competes with interactive traffic.

### 3. Available options
- **A — Synchronous only:** request blocks until done.
- **B — Asynchronous only:** submit → job id → poll status / notify; progress via status.
- **C — Hybrid:** small imports synchronous (bounded); large/bulk asynchronous; a size/row threshold decides.

### 4. Pros and cons
| Option | Pros | Cons |
|---|---|---|
| A — Sync | Simple; immediate result; easy error surfacing | Doesn't scale for bulk (long-held connections vs D-13 pools; timeouts); blocks |
| B — Async | Scales; decouples from request lifetime; progress; resilient to disconnect; fits separate import capacity (D-13) | More moving parts (durable job state, status/notify); eventual result |
| C — Hybrid | Best UX for small + scalable for large | Two paths to build/test; threshold tuning; consistent semantics across both |

### 5. Impact on IC-003
Defines `StartImport`/`GetImportStatus`. Async needs a **durable, tenant-scoped import-job record** (submitted → running → applied/failed), analogous to IC-002's lifecycle style; progress fields in Import Status are **non-sensitive counts**.

### 6. Impact on IC-004 Lineage
Timing, not content: lineage is written **as data is copied** (atomic provenance), per committed batch for async. Re-runs append (D-20); no lineage is emitted for uncommitted work.

### 7. Impact on IC-002 Tenant Startup
The import-job/progress state is **tenant-scoped** (no shared store). Long async imports hold per-tenant capacity (D-13); **per-tenant concurrency bounds** preserve independence (D-16) so one tenant's big import never starves others.

### 8. Impact on IC-005 Authentication Routing
Each status poll **re-authenticates** statelessly (OIDC JWT, D-05) and re-establishes the same tenant context (D-04). Async MUST NOT require a persistent server session (consistent with D-05's no-session-store).

### 9. Impact on physical multi-database architecture
Async writes target the one active tenant DB across batches; each batch commit is single-tenant. Job/progress state is tenant-scoped and portable (standard PostgreSQL); if a queue is used it MUST be portable/self-hostable — no provider queue.

### 10. Recommended option
**C — hybrid: asynchronous by default for bulk, with a bounded synchronous fast-path for small imports.** Durable tenant-scoped job record + simple state machine; progress via `GetImportStatus` (non-sensitive counts); stateless re-auth on polls; per-tenant concurrency bounds (D-13/D-16).

### 11. Open risks
Job-state location/portability (tenant DB vs control-plane; no shared store; no provider queue); per-tenant concurrency limits; progress accuracy; poll vs notify; never requiring a server session (D-05). Ties D-13, D-16, D-20, D-21.

---

# D-20 — Idempotency Strategy for Safe Re-Import

### 1. Decision description
How repeated/retried imports are made safe so a re-submit/retry does not duplicate, corrupt, or mis-attribute the tenant copy — given Import ≠ Sync and append-only lineage.

### 2. Why it matters
Retries and resubmits are inevitable (network, async). Without idempotency, re-import duplicates or double-counts tenant records. Must interact correctly with lineage (re-import **appends**, never mutates) and ownership (never write back to Global).

### 3. Available options
- **A — Client-supplied idempotency key:** dedup requests by (tenant, key) within a window.
- **B — Content/natural-key dedup:** upsert into the tenant copy by a natural key / content identity.
- **C — Operation-id exactly-once apply:** each import operation has a durable id; re-applying the same id is a no-op.
- **D — Combination:** operation-level key (A/C) for request retry-safety + per-record natural-key reconciliation (B) for content.

### 4. Pros and cons
| Option | Pros | Cons |
|---|---|---|
| A — Idempotency key | Standard; simple request-level dedup | Window/storage of seen keys; doesn't dedup content across differing keys |
| B — Natural-key | Dedups actual data (re-import updates/no-ops) | Requires a defined natural key per entity (schema-dependent, D-17); ambiguous without one |
| C — Operation-id | Clean async retry-safety; pairs with lineage | Needs a durable apply ledger; must define "same operation" |
| D — Combination | Strongest: retry-safe **and** content-deduped | Most to define; natural-key dependency remains |

### 5. Impact on IC-003
Defines `idempotency_key` + re-import semantics (new copy vs update vs no-op). MUST guarantee re-import never mutates Global (Invariant 4), never corrupts the tenant copy, never duplicates misleadingly.

### 6. Impact on IC-004 Lineage
Re-import **appends** lineage chained via `parent_lineage_ref` (D-23 append-only; D-25 graph) and records the outcome (applied vs no-op). A no-op re-import still emits an attributable "no change" entry — idempotency is **reflected, not hidden**. Data upsert is distinct from lineage mutation (lineage is never mutated).

### 7. Impact on IC-002 Tenant Startup
Idempotency state (seen keys / operation ledger) is **tenant-scoped** (no shared store). Natural-key reconciliation depends on the tenant's schema version (D-17).

### 8. Impact on IC-005 Authentication Routing
The key is request data, not auth; but the authenticated principal + tenant context (D-04/D-05) **scope** the key per tenant — a principal cannot replay a key into another tenant. No change to the auth mechanism.

### 9. Impact on physical multi-database architecture
Idempotency is **per-tenant within the one active tenant DB**; dedup/upsert touches only that DB; no cross-tenant dedup; portable (standard PostgreSQL upserts/constraints — no provider features). Any ledger is per-tenant/control-plane and isolated.

### 10. Recommended option
**D — operation-level idempotency key (request retry-safety) + per-record natural-key reconciliation (content de-dup).** Default re-import = **upsert by natural key**, **no-op when unchanged**, always **appending lineage** that records the outcome. Where an entity has no natural key, fall back to operation-id exactly-once (C). Never mutates Global.

### 11. Open risks
Natural-key definition per entity (schema-dependent, D-17; ambiguous keys); key storage/expiry window; ensuring no-op re-imports still emit attributable, non-duplicating lineage; keeping data-upsert distinct from append-only lineage; cross-submit content-dedup correctness. Ties D-21, D-23/D-25, D-17.

---

# D-21 — Partial-Failure Semantics

### 1. Decision description
When some records succeed and others fail (bad rows, constraint violations), is the import all-or-nothing (atomic rollback) or per-record (commit good, report bad)?

### 2. Why it matters
Sets transactional behavior, retry/idempotency interplay (D-20), lineage granularity (IC-004), and error-reporting UX, while preserving atomic provenance. Bulk imports with a few bad rows shouldn't necessarily fail wholesale — but partial commits complicate provenance and re-import.

### 3. Available options
- **A — All-or-nothing (atomic):** any failure rolls back the whole import.
- **B — Per-record best-effort:** commit valid records, reject/report invalid ones.
- **C — Batched/checkpointed:** process in batches; each batch atomic; failed batches reported; resumable.
- **D — Configurable per import** (caller chooses atomic or best-effort) within a default.

### 4. Pros and cons
| Option | Pros | Cons |
|---|---|---|
| A — All-or-nothing | Simplest provenance; clean retry (re-import whole); strong consistency | One bad row fails a huge import; poor UX for messy data |
| B — Per-record | Resilient to messy data; detailed per-record errors | Complex per-record provenance; partial state complicates idempotency (D-20) |
| C — Batched/checkpointed | Balances atomicity + resilience; resumable; bounded blast radius; fits async + atomic provenance per batch | Batch sizing; partial-success semantics; per-batch error reporting |
| D — Configurable | Flexible per use case | Two semantics to support/test; consistent lineage/idempotency across modes |

### 5. Impact on IC-003
Defines failure behavior + Import Status outcome (counts, non-sensitive errors). MUST preserve: committed tenant data always has lineage (atomic provenance); a failed import never mutates Global; isolation on failure.

### 6. Impact on IC-004 Lineage
Granularity: per-record (B) vs per-batch (C). **Atomic provenance** means each committed unit gets its lineage in the **same transaction** — C aligns cleanly (batch commit + its lineage are atomic). Lineage MUST reflect partial outcomes without implying full success.

### 7. Impact on IC-002 Tenant Startup
Schema-incompatible records fail per policy (ties D-17). Per-tenant independence (D-16) contains partial failures to the one tenant; batched commits load per-tenant connections (D-13).

### 8. Impact on IC-005 Authentication Routing
None structural; the whole import runs under one authenticated tenant context (D-04). Error reports MUST be **non-sensitive** (no payload/secret leakage in responses).

### 9. Impact on physical multi-database architecture
All commits (full / batch / record) target the one active tenant DB using **standard PostgreSQL transactions** (portable, no provider features); no cross-tenant; failed units affect neither Global nor other tenants.

### 10. Recommended option
**C — batched/checkpointed, each batch atomic, with per-batch error reporting and resumability**, as the default; optionally expose a strict all-or-nothing mode (toward D) for callers needing full atomicity. Pairs with async (D-19) and atomic provenance (each batch's lineage commits with the batch). Re-import (D-20) resumes from the last good checkpoint.

### 11. Open risks
Batch sizing (throughput vs blast radius); clear partial-success reporting (non-sensitive errors); resumability + idempotency interplay (D-20) to avoid double-applying a re-run batch; per-record vs per-batch lineage granularity; never committing data without lineage. Ties D-20, D-19, IC-004.

---

# D-09 (ingress) — Import-Ingress PII Handling and Sanitization

### 1. Decision description
How PII is handled and data sanitized **at import ingress** — validation, classification, sanitization/redaction — before/as data becomes a tenant-owned copy. (The **AI-egress** slice of D-09 stays with IC-006.)

### 2. Why it matters
Imported data may carry PII and malformed/malicious content. Ingress is the platform's data front door: it sets injection-safety, PII classification/handling (consumes the resolved **D-08** compliance model), and guarantees that PII/payloads/secrets never leak into lineage, audit, or responses.

### 3. Available options
- **A — Validate + sanitize, store as-is:** classify PII and sanitize for injection/format; the tenant owns and stores its PII; redaction applies only to lineage/audit/logs (which never hold PII).
- **B — + minimize:** drop/redact disallowed fields at ingress per per-tenant policy.
- **C — + tokenize/pseudonymize:** sensitive fields tokenized at ingress; store tokens + vault reference.
- **D — Policy-driven per-tenant:** A/B/C selectable per tenant compliance (D-08).

### 4. Pros and cons
| Option | Pros | Cons |
|---|---|---|
| A — Store as-is | Simplest; tenant legitimately owns its PII (its copy); redaction confined to lineage/audit/logs | PII sits in tenant DB (must be access-controlled, retained, erasable per D-08/D-24); no minimization |
| B — Minimize | Data minimization (GDPR-friendly); smaller PII footprint | Per-field policy; may drop wanted data; policy complexity |
| C — Tokenize | Strong privacy; sensitive values vaulted/referenced (fits references-only) | Heavy; token vault is another secret-bearing store (D-14-adjacent); reversibility/erasure complexity |
| D — Policy-driven | Fits multi-tenant compliance reality (D-08) | Config surface + governance |

### 5. Impact on IC-003
Defines ingress validation/sanitization rules and what is rejected (interacts with D-21: PII-policy or malformed records fail per policy). Reinforces: payloads/secrets/PII **never** in lineage/audit/responses — references/summaries only.

### 6. Impact on IC-004 Lineage
Lineage records the import **by reference** and MUST NOT contain PII or payloads. Sanitization/classification **outcomes** may be referenced (policy/codes); raw values never. With tokenization (C), lineage references tokens, not raw values — reinforcing IC-004's secrets-never/references-only rule.

### 7. Impact on IC-002 Tenant Startup
PII handling consumes per-tenant compliance parameters from the tenant registry (D-08) and per-tenant retention (D-24). Stored PII lives in the tenant DB (isolation); erasure is per-tenant (the D-08 right-to-erasure reconciliation: erase referent / crypto-erase, keep non-PII provenance).

### 8. Impact on IC-005 Authentication Routing
Only authorized principals import into the tenant (D-04); ingress sanitization is independent of the auth mechanism but **error reports MUST be non-sensitive**. Injection-safe sanitization protects the tenant DB regardless of caller.

### 9. Impact on physical multi-database architecture
Sanitized/tokenized data is written only to the one active tenant DB (no shared store); per-tenant isolation contains PII; portable (standard PostgreSQL; tokenization via portable references, not provider features). A tenant-owned copy MAY legitimately hold PII under that tenant's policy.

### 10. Recommended option
**D — policy-driven per-tenant ingress handling, on a mandatory baseline:** (1) input **validation + injection-safe sanitization** for every import; (2) **PII classification**; (3) **per-tenant minimization/tokenization** driven by the tenant's compliance parameters (D-08); (4) the absolute rule that **PII/payloads/secrets never enter lineage, audit, or responses** (references/summaries only). Default = validate + sanitize + classify; minimize/tokenize opt-in per tenant policy. **Full D-09 (incl. AI egress) remains owned by IC-006**; this resolves the ingress slice only.

### 11. Open risks
Injection/upload-content scanning rigor (ties D-18 uploads); PII-classification accuracy (false negatives leave PII unhandled); tokenization vault as a secret-bearing dependency (D-14); per-tenant policy governance + erasure reconciliation (D-08/D-24); sanitization failures must surface as partial-failure (D-21) **without** leaking sensitive detail in errors. Cross-ref: AI-egress PII (IC-006) remains open.

---

## Consolidated recommendations (at a glance)

| ID | Decision | Recommended | Primary driver |
|---|---|---|---|
| **D-18** | Source formats v1 | **Pluggable adapter; v1 = Global + CSV/JSON**; API-pull later | Bound ingestion-security surface; extensible |
| **D-19** | Execution mode | **Hybrid: async-default + bounded sync fast-path**; durable tenant-scoped job; stateless re-auth | Scale bulk without blocking; preserve D-05/D-13/D-16 |
| **D-20** | Idempotency | **Operation key + natural-key upsert**; no-op when unchanged; lineage records outcome | Safe retries; never duplicate or mutate Global |
| **D-21** | Partial failure | **Batched/checkpointed atomic + resumable**; optional strict all-or-nothing | Resilience + atomic provenance |
| **D-09 (ingress)** | PII at ingress | **Policy-driven per-tenant on a mandatory validate/sanitize/classify floor**; never in lineage/audit/responses | Compliance (D-08) + injection safety + secrets-never |

**Decision order:** D-18 → D-09 ingress → D-19 → D-21 → D-20 (D-20 and D-21 are coupled; D-09 depends on D-18). Approving these resolves IC-003's open decisions and unblocks **IC-003 Draft → Reviewed**. All recommendations preserve *Global Record ≠ Tenant Record*, *Import ≠ Synchronization*, *import creates a tenant-owned copy* with full ownership decoupling, *one request → one active tenant → one database*, *no shared tenant databases*, lineage-per-IC-004, secrets-never/references-only, PostgreSQL portability with no provider bulk-load, and AI-egress remaining post-MVP (IC-006).
