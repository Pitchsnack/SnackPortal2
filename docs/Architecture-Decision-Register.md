# Architecture Decision Register

**Phase:** Architecture Planning · **Type:** Decision record (analysis only, no implementation)
**Purpose:** Canonical, at-a-glance list of approved cross-cutting architecture decisions for SnackPortal2. Full rationale and alternatives live in the linked source documents; this register is the authoritative record of *what was decided*.

## Register

| ID | Decision | Summary of approved outcome | Status | Date approved | Affected contracts |
|---|---|---|---|---|---|
| **D-01** | Bootstrap cycle (IC-001 ⇄ IC-005) | **A + B:** two-phase bootstrap — a control-plane-only **system identity** verified against a **static, infrastructure-owned trust anchor** (no Control-DB lookup); transition to full runtime auth + tenant routing only once the Control DB is online. Authentication separated from routing. | ✅ Resolved | 2026-06-05 | IC-001, IC-005 |
| **D-02** | AI Gateway in MVP? | **Defer AI to post-MVP.** IC-006 not required for v1; specify it later. Keep IC-004 lineage and the tenant schema **AI-ready** now so adoption is non-breaking. | ✅ Resolved | 2026-06-05 | IC-006 (deferred); IC-004, IC-002 (AI-ready design) |
| **D-03** | Identity model | **Hybrid:** internal platform identities for operators/staff **+** OIDC federation for external organizations (each external tenant org brings its own OIDC IdP). | ✅ Resolved | 2026-06-05 | IC-005; IC-002 (tenant↔org) |
| **D-04** | Tenant-per-principal model | **1:N membership with exactly one active tenant context per request.** Concurrent multi-tenant access within a request is prohibited; switching the active tenant re-scopes subsequent requests (sensitive, audited). | ✅ Resolved | 2026-06-05 | IC-005; IC-002 |
| **D-05** | Authentication scheme | **OIDC with stateless JWT validation.** No server-side session store, no Control-DB session dependency — preserves the D-01 separation of authentication from routing. Portable; explicitly **not** Supabase Auth. | ✅ Resolved | 2026-06-05 | IC-005 |
| **D-07** | Tenant id → physical DB mapping | **Registry-authoritative** binding in the Control DB (naming convention only as an overridable default); resolution cached with tenant-scoped invalidation; descriptor is a secret-store reference, never raw credentials. | ✅ Resolved | 2026-06-05 | IC-002; IC-005 (Database Router) |
| **D-13** | Connection pooling & tenant scale | **Lazy, bounded per-tenant pools with LRU idle eviction** as baseline; a **portable, self-hostable transaction pooler** as a future scale layer. Connections never reused across tenants. | ✅ Resolved | 2026-06-05 | IC-002; IC-005 (Database Router); IC-003 (import capacity) |
| **D-14** | Secret storage abstraction | **Pluggable, reference-based secret abstraction** (resolve/version/rotate) with cloud-native or self-hostable backends. Descriptors hold `{store-ref, version}` only; values never in DTOs/logs/responses/contracts. | ✅ Resolved | 2026-06-05 | IC-002; IC-005 (trust anchor/JWKS); IC-003 (source creds) |
| **D-15** | Tenant provisioning ownership | **IaC substrate orchestrated by an automated, audited control-plane provisioning workflow**; manual runbook is **break-glass only**. Provisioning identity is least-privilege, control-plane-scoped. | ✅ Resolved | 2026-06-05 | IC-002; infrastructure |
| **D-16** | Partial-fleet readiness | **Per-tenant independence**: platform stays globally ready; only affected tenants are not-ready. A derived **`degraded` signal is observability-only** and never denies healthy tenants. Global not-ready only on shared-dependency (Control DB) failure. | ✅ Resolved | 2026-06-05 | IC-002; IC-005 (routing); IC-003 |
| **D-17** | Schema migration coordination | **Expand/contract (backward-compatible) rolling migrations**, per-tenant, with **version-gated readiness** against a supported range; out-of-range tenants are not-ready until migrated. | ✅ Resolved | 2026-06-05 | IC-002; IC-005 (readiness gating); IC-003 |
| **D-08** | Compliance / regulatory driver | **Configurable multi-regime model** with a **SOC 2-style integrity floor** (append-only, tamper-evident, access-controlled, audited) + **per-tenant compliance parameters** (retention, residency). GDPR erasure reconciled via reference-only + referent deletion / crypto-erasure. | ✅ Resolved | 2026-06-05 | IC-004; IC-003; IC-006 (future); per-tenant (D-03/D-07) |
| **D-22** | Minimum lineage record | **Minimal core (MUST)** + a **reference/code-only extension envelope**; no payloads, PII, or secrets in any field. | ✅ Resolved | 2026-06-05 | IC-004; IC-003 (emits core); IC-006 (future) |
| **D-23** | Immutability enforcement | **Defense-in-depth:** DB-level append-only (privilege separation + reject UPDATE/DELETE) **+ per-tenant cryptographic hash-chaining** as the integrity marker. PostgreSQL-portable; no vendor ledger. | ✅ Resolved | 2026-06-05 | IC-004; IC-002 (chain-break/expiry audit); IC-003 |
| **D-24** | Retention & archival | **Per-tenant configurable** retention + archival within a **compliance floor/ceiling** (D-08); segmented verifiable archival; policy-driven expiry only, via tombstones, operationally audited. | ✅ Resolved | 2026-06-05 | IC-004; IC-002 (expiry audit); IC-003 |
| **D-25** | Unified provenance chain | **Unified per-tenant provenance graph** (parent references) for end-to-end traceability, with a **segmentable per-tenant integrity chain** (D-23). Graph never crosses tenants. | ✅ Resolved | 2026-06-05 | IC-004; IC-003; IC-006 (future) |
| **D-18** | Import source formats (v1) | **Pluggable source-adapter model**; v1 = **Global record + CSV/JSON** (client upload); API-pull deferred to a later adapter. Portable ingestion only (no provider bulk-load). | ✅ Resolved | 2026-06-05 | IC-003; IC-004 (`source_ref` shapes) |
| **D-19** | Import execution mode | **Hybrid:** asynchronous by default for bulk + bounded **synchronous fast-path** for small imports; durable tenant-scoped job record; progress via status; stateless re-auth on polls. | ✅ Resolved | 2026-06-05 | IC-003; IC-002 (tenant-scoped job state); IC-005 (stateless re-auth) |
| **D-20** | Import idempotency | **Operation-level idempotency key + per-record natural-key reconciliation** (upsert; no-op when unchanged); re-import appends lineage recording the outcome; never mutates Global. | ✅ Resolved | 2026-06-05 | IC-003; IC-004 (re-import appends) |
| **D-21** | Partial-failure semantics | **Batched/checkpointed atomic imports with resumability** (default); optional strict all-or-nothing; each committed batch carries its lineage (atomic provenance). | ✅ Resolved | 2026-06-05 | IC-003; IC-004 (lineage granularity) |
| **D-09** | PII handling policy (split) | **Import-ingress slice resolved** (IC-003): policy-driven per-tenant validation/sanitization/classification on a mandatory floor; PII/payloads/secrets never in lineage/audit/responses. **AI-egress slice open** (IC-006). | ⏳ Ingress Resolved; egress open | 2026-06-05 (ingress) | IC-003 (ingress); IC-006 (egress, open) |
| **D-06** | Tenant identifier carriage | **Signed JWT claim authoritative** with **carrier-match enforcement** (subdomain/header must match the claim; mismatch rejected) + membership check (D-04); tenant switch = new tenant-scoped token. | ✅ Resolved | 2026-06-05 | IC-005; IC-002 (membership) |
| **D-10** | Global ready vs degraded | **Three-state** readiness (ready / degraded / not-ready); **degraded is observability-only and never denies healthy tenants** (D-16); global not-ready reserved for Control-DB / Phase-0 failure. | ✅ Resolved | 2026-06-05 | IC-001; IC-005 (routing gates on Control DB) |
| **D-11** | Registry enumeration | **Hybrid:** warm bounded working set at startup + lazy-load on demand + background refresh; registry-authoritative (D-07) with invalidation on re-association. Ready = registry reachable, not fully enumerated. | ✅ Resolved | 2026-06-05 | IC-001; IC-005 (Database Router) |
| **D-12** | Control-DB schema mismatch | **Compatible-range (expand/contract)**; serve only within the supported range, else **global not-ready** (fail-safe); migration is a controlled, audited step (never implicit at startup). | ✅ Resolved | 2026-06-05 | IC-001; IC-005 (routing gates on compatibility) |
| **D-30** | Cross-tenant isolation enforcement | **Defense-in-depth:** authoritative claim + membership (D-04/D-06) → single-tenant routing (D-07) → per-tenant credentials + no cross-tenant connection reuse (D-13/D-14) → audit/anomaly detection. No cross-tenant joins ever. | ✅ Resolved | 2026-06-05 | IC-005; IC-002; IC-004; IC-003 |
| **JWT** | JWT lifecycle (D-05 detail) | **Short-lived access tokens + OIDC refresh at the IdP + JWKS/`kid` rotation + IdP refresh-token revocation + optional bounded control-plane `jti` denylist; no session store.** Validation DB-free; tenant claim bound. | ✅ Resolved | 2026-06-05 | IC-005 |
| **D-31** | Global Directory Residency | **Global Startup & Investor Directories reside in the Control Database** (Control Plane + Global Discovery Platform). Global directory records only in Control DB; tenant-owned copies only in tenant DBs; no tenant data in Control DB. Directory schema follows D-12; access governed by IC-005. | ✅ Approved | 2026-06-05 | IC-001 (amend), IC-003 (amend), IC-005 (clarify) |
| **D-32** | Role Hierarchy & Operating Model | **MVP roles:** CONTROL, MASTER_AGENT, TENANT_ADMIN, TENANT_AGENT, STARTUP_USER, INVESTOR_USER (roles, not permissions). MASTER_AGENT obeys one-request→one-active-tenant→one-DB; multi-membership ≠ multi-tenant access; no cross-tenant superuser. Assignments in Control-DB Tenant Registry. Cross-tenant collaboration → future IC-007. | ✅ Approved | 2026-06-05 | IC-005 (amend), IC-002 (minor) |

---

## Decision detail

### D-01 — Bootstrap Cycle Resolution
- **Decision:** Resolve the circular startup dependency by decoupling the authentication trust anchor from Control-DB-resident routing metadata, via a two-phase bootstrap (Phase 0 system identity → Phase 1 runtime).
- **Approved option:** **A + B** (bootstrap/system identity + static infra-owned trust-anchor config). Option C (OIDC IdP) is complementary as a Phase-1 backend; Option D (manual provisioning) retained only as one-time break-glass.
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-001, IC-005 (both updated and now **Reviewed**)
- **Source:** [D-01-Bootstrap-Cycle-Resolution.md](D-01-Bootstrap-Cycle-Resolution.md)

### D-02 — AI in MVP
- **Decision:** AI is **not** an MVP dependency; defer the AI Gateway (IC-006) to post-MVP.
- **Approved outcome:** Build multi-tenant core + import first; design IC-004 lineage and tenant schema to be AI-ready so IC-006 slots in later without rework.
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-006 (deferred); IC-004 and IC-002 (AI-ready design)
- **Source:** [D-02-to-D-05-Decision-Pack.md](D-02-to-D-05-Decision-Pack.md)

### D-03 — Identity Model
- **Decision:** **Hybrid identity model.**
  - Internal platform identities for operators/staff.
  - OIDC federation for external organizations.
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-005 (Authentication Requirements); IC-002 (tenant↔organization mapping; per-tenant IdP config)
- **Source:** [D-02-to-D-05-Decision-Pack.md](D-02-to-D-05-Decision-Pack.md)

### D-04 — Tenant-per-Principal Model
- **Decision:** **1:N membership, exactly one active tenant context per request.** Concurrent multi-tenant access within a request is forbidden; tenant switching re-scopes subsequent requests and is audited.
- **Rationale:** Preserves the architecture invariant — one request resolves to the Control DB or exactly one tenant DB, never spanning — keeping it compatible with physical multi-database isolation.
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-005 (Authorization Requirements); IC-002
- **Source:** [D-02-to-D-05-Decision-Pack.md](D-02-to-D-05-Decision-Pack.md)

### D-05 — Authentication Scheme
- **Decision:** **OIDC with stateless JWT validation.** No server-side session store; no Control-DB session dependency. Tenant context carried as a signed claim and re-validated at routing time.
- **Rationale:** Stateless validation keeps authentication DB-free, preserving the D-01 Phase-0/Phase-1 separation; standards-based and portable across clouds/self-hosted; not Supabase Auth.
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-005
- **Source:** [D-02-to-D-05-Decision-Pack.md](D-02-to-D-05-Decision-Pack.md)

### D-07 — Tenant Identifier → Physical Database Mapping
- **Decision:** Registry-authoritative mapping — the Control-DB registry is the single source of the tenant→database binding. A naming convention MAY serve only as a non-authoritative default the registry overrides.
- **Approved option:** A (registry-authoritative). Resolution is cached with tenant-scoped invalidation on re-association; the stored value is a secret-store reference, never raw credentials.
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-002 (Physical Database Association); IC-005 (Database Router resolution)
- **Source:** [D-07-D13-D14-D15-D16-D17-Tenant-Infrastructure-Decision-Pack.md](D-07-D13-D14-D15-D16-D17-Tenant-Infrastructure-Decision-Pack.md)

### D-13 — Connection Pooling & Tenant Scale
- **Decision:** Lazy, bounded per-tenant pools with LRU idle eviction as the baseline; a portable, self-hostable transaction pooler as a future scale layer.
- **Approved option:** B baseline + C as future scale layer. A connection is bound to exactly one tenant per request/transaction and never reused across tenants; import draws from separate bounded capacity.
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-002 (Connection Management & Scale); IC-005 (Database Router); IC-003 (import capacity)
- **Source:** [D-07-D13-D14-D15-D16-D17-Tenant-Infrastructure-Decision-Pack.md](D-07-D13-D14-D15-D16-D17-Tenant-Infrastructure-Decision-Pack.md)

### D-14 — Credential & Secret Storage Abstraction
- **Decision:** A single internal, reference-based secret-store abstraction (resolve/version/rotate) with pluggable backends — cloud-native where present, self-hostable elsewhere.
- **Approved option:** C (pluggable abstraction). Descriptors hold `{store-ref, version}` only; values are resolved in-memory at connect time and never appear in DTOs, logs, API responses, or contracts.
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-002; IC-005 (trust anchor / JWKS handling); IC-003 (import-source credentials); shared with IC-001 (D-01 trust anchor)
- **Source:** [D-07-D13-D14-D15-D16-D17-Tenant-Infrastructure-Decision-Pack.md](D-07-D13-D14-D15-D16-D17-Tenant-Infrastructure-Decision-Pack.md)

### D-15 — Tenant Provisioning Ownership
- **Decision:** IaC substrate orchestrated by an automated, audited control-plane provisioning workflow; manual runbook is break-glass only.
- **Approved option:** Hybrid (A substrate + B orchestration; C break-glass). The provisioning identity is least-privilege, control-plane-scoped, and audited; provisioning guarantees a physically separate database per tenant.
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-002 (Non-goals, Provisioning state, Audit); infrastructure
- **Source:** [D-07-D13-D14-D15-D16-D17-Tenant-Infrastructure-Decision-Pack.md](D-07-D13-D14-D15-D16-D17-Tenant-Infrastructure-Decision-Pack.md)

### D-16 — Partial-Fleet Readiness Behavior
- **Decision:** Strict per-tenant readiness independence; a derived `degraded` aggregate is observability-only.
- **Approved option:** A + B(observability only). The platform stays globally ready while individual tenants are not-ready; the `degraded` signal never denies healthy tenants; global not-ready is reserved for shared-dependency (Control DB / Phase-0) failure (D-10).
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-002 (Readiness, Failure Behavior); IC-005 (routing); IC-003
- **Source:** [D-07-D13-D14-D15-D16-D17-Tenant-Infrastructure-Decision-Pack.md](D-07-D13-D14-D15-D16-D17-Tenant-Infrastructure-Decision-Pack.md)

### D-17 — Schema Migration Coordination
- **Decision:** Expand/contract (backward-compatible) rolling migrations applied per tenant, complemented by version-gated readiness against a supported range.
- **Approved option:** B + C(range-gated). A tenant whose observed schema version is outside the supported range is not-ready until migrated; Control-DB/global schema coordination remains with IC-001.
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-002 (Readiness, Failure Behavior); IC-005 (readiness gating); IC-003
- **Source:** [D-07-D13-D14-D15-D16-D17-Tenant-Infrastructure-Decision-Pack.md](D-07-D13-D14-D15-D16-D17-Tenant-Infrastructure-Decision-Pack.md)

### D-08 — Compliance / Regulatory Driver
- **Decision:** Configurable multi-regime compliance model with a SOC 2-style integrity floor (append-only, tamper-evident, access-controlled, audited) plus per-tenant compliance parameters (retention, residency).
- **Approved option:** D (configurable multi-regime). GDPR right-to-erasure is reconciled with append-only via the reference-only model — erase the referent / crypto-erase, retaining non-personal provenance. **Business/legal still names the specific floor regime and per-tenant values.**
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-004 (Retention, Access Control, Immutability strength); IC-003; IC-006 (future); per-tenant via D-03/D-07
- **Source:** [D-08-D22-D23-D24-D25-Lineage-Decision-Pack.md](D-08-D22-D23-D24-D25-Lineage-Decision-Pack.md)

### D-22 — Minimum Lineage Record
- **Decision:** A fixed minimal core (MUST) plus a reserved, reference/code-only extension envelope; no payloads, PII, or secrets in any field.
- **Approved option:** C (core + envelope). Change-evidence references versions/markers rather than hashing raw payloads.
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-004 (Minimum Lineage Record); IC-003 (emits the core); IC-006 (future, ai-derivation)
- **Source:** [D-08-D22-D23-D24-D25-Lineage-Decision-Pack.md](D-08-D22-D23-D24-D25-Lineage-Decision-Pack.md)

### D-23 — Immutability Enforcement Mechanism
- **Decision:** Defense-in-depth — DB-level append-only (privilege separation + reject UPDATE/DELETE) plus per-tenant cryptographic hash-chaining as the integrity marker.
- **Approved option:** D (B+C). PostgreSQL-portable; no vendor ledger. Detected chain breaks are alarmed and operationally audited (IC-002); any keyed-hash key is a D-14 reference, never stored in lineage.
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-004 (Immutability); IC-002 (chain-break/expiry audit); IC-003 (append throughput)
- **Source:** [D-08-D22-D23-D24-D25-Lineage-Decision-Pack.md](D-08-D22-D23-D24-D25-Lineage-Decision-Pack.md)

### D-24 — Retention & Archival Policy
- **Decision:** Per-tenant configurable retention + archival within a compliance-driven floor/ceiling (D-08); segmented, verifiable archival; policy-driven expiry only.
- **Approved option:** C. Expiry/erasure use tombstone references so the integrity chain stays intact; expiry is operationally audited (IC-002); archive target is portable.
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-004 (Retention & Archival); IC-002 (expiry audit); IC-003 (growth)
- **Source:** [D-08-D22-D23-D24-D25-Lineage-Decision-Pack.md](D-08-D22-D23-D24-D25-Lineage-Decision-Pack.md)

### D-25 — Unified Provenance Chain
- **Decision:** A unified per-tenant provenance graph (parent references) for end-to-end traceability, with the D-23 integrity chain kept per-tenant and segmentable.
- **Approved option:** C. Provenance linkage (graph) is distinct from tamper-evidence ordering (chain); the graph never crosses tenants; ai-derivation nodes participate (AI-ready).
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-004 (provenance model); IC-003 (import roots); IC-006 (future, AI nodes)
- **Source:** [D-08-D22-D23-D24-D25-Lineage-Decision-Pack.md](D-08-D22-D23-D24-D25-Lineage-Decision-Pack.md)

### D-18 — Import Source Formats (v1)
- **Decision:** Pluggable source-adapter model; v1 supports the Global record + structured CSV/JSON (client upload); API-pull connectors deferred to a later adapter.
- **Approved option:** D. Copy/ownership/lineage semantics are source-agnostic; ingestion is portable (no provider bulk-load); adapters are reference/secret-clean.
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-003 (StartImport source surface); IC-004 (`source_ref` shapes)
- **Source:** [D-18-D19-D20-D21-D09-Import-Decision-Pack.md](D-18-D19-D20-D21-D09-Import-Decision-Pack.md)

### D-19 — Import Execution Mode
- **Decision:** Hybrid — asynchronous by default for bulk, with a bounded synchronous fast-path for small imports.
- **Approved option:** C. Durable, tenant-scoped import-job record + state machine; progress via GetImportStatus (non-sensitive counts); stateless re-auth on polls (D-05); per-tenant concurrency bounds (D-13/D-16).
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-003; IC-002 (tenant-scoped job state); IC-005 (stateless re-auth)
- **Source:** [D-18-D19-D20-D21-D09-Import-Decision-Pack.md](D-18-D19-D20-D21-D09-Import-Decision-Pack.md)

### D-20 — Import Idempotency
- **Decision:** Operation-level idempotency key + per-record natural-key reconciliation; default re-import = upsert by natural key, no-op when unchanged.
- **Approved option:** D. Re-import appends lineage recording the outcome (never mutates lineage or the Global record); operation-id exactly-once fallback where no natural key exists.
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-003; IC-004 (re-import appends; D-23/D-25)
- **Source:** [D-18-D19-D20-D21-D09-Import-Decision-Pack.md](D-18-D19-D20-D21-D09-Import-Decision-Pack.md)

### D-21 — Partial-Failure Semantics
- **Decision:** Batched/checkpointed atomic imports with resumability as default; optional strict all-or-nothing mode.
- **Approved option:** C (with optional D). Each batch commit carries its lineage in the same transaction (atomic provenance); re-import resumes from the last good checkpoint (D-20).
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-003; IC-004 (per-batch lineage granularity)
- **Source:** [D-18-D19-D20-D21-D09-Import-Decision-Pack.md](D-18-D19-D20-D21-D09-Import-Decision-Pack.md)

### D-09 — PII Handling Policy (split: ingress resolved / egress open)
- **Decision (ingress, resolved):** Policy-driven per-tenant ingress handling on a mandatory floor — validation + injection-safe sanitization + PII classification for every import; per-tenant minimization/tokenization driven by the D-08 compliance parameters; PII/payloads/secrets never enter lineage, audit, or responses.
- **Approved option:** D (ingress). Consumes the resolved D-08 model and its erasure reconciliation.
- **Open (egress):** PII redaction before AI egress remains owned by IC-006 (AI post-MVP, D-02).
- **Status:** ⏳ Ingress ✅ Resolved (2026-06-05); egress ⛔ Open
- **Affected contracts:** IC-003 (ingress); IC-006 (egress, future)
- **Source:** [D-18-D19-D20-D21-D09-Import-Decision-Pack.md](D-18-D19-D20-D21-D09-Import-Decision-Pack.md)

### D-06 — Tenant Identifier Carriage
- **Decision:** The active tenant is carried as an integrity-protected signed JWT claim, which is authoritative; subdomain/header MAY be used for addressing but MUST match the claim.
- **Approved option:** D (hybrid; signed claim authoritative). IC-005 rejects carrier/claim mismatches and verifies membership (D-04) before routing; a tenant switch issues a new tenant-scoped token (stateless).
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-005 (tenant-context establishment); IC-002 (membership)
- **Source:** [D-06-D10-D11-D12-D30-Finalization-Decision-Pack.md](D-06-D10-D11-D12-D30-Finalization-Decision-Pack.md)

### D-10 — Global Ready vs Degraded
- **Decision:** Three-state global readiness (ready / degraded / not-ready); degraded is observability-only and never denies healthy tenants.
- **Approved option:** B composed from C-dimensions. Global not-ready is reserved for shared-dependency (Control DB / Phase-0) failure; tenant-DB outages are per-tenant not-ready (D-16). Readiness is access-controlled and minimally disclosing.
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-001 (readiness); IC-005 (routing gates on Control DB)
- **Source:** [D-06-D10-D11-D12-D30-Finalization-Decision-Pack.md](D-06-D10-D11-D12-D30-Finalization-Decision-Pack.md)

### D-11 — Registry Enumeration Strategy
- **Decision:** Hybrid — warm a bounded working set at startup, lazy-load the rest on demand, background refresh.
- **Approved option:** C. Ready = registry reachable, not fully enumerated; registry-authoritative (D-07) with tenant-scoped invalidation on re-association.
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-001 (startup/readiness); IC-005 (Database Router resolution)
- **Source:** [D-06-D10-D11-D12-D30-Finalization-Decision-Pack.md](D-06-D10-D11-D12-D30-Finalization-Decision-Pack.md)

### D-12 — Control-DB Schema-Version Mismatch
- **Decision:** Compatible-range (expand/contract) for the Control DB; serve only within the supported range, else global not-ready (fail-safe).
- **Approved option:** B. Migration is a controlled, audited, separate step — never implicit at startup; enables zero-downtime control-plane rolling deploys.
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-001 (startup/readiness); IC-005 (routing gates on compatibility)
- **Source:** [D-06-D10-D11-D12-D30-Finalization-Decision-Pack.md](D-06-D10-D11-D12-D30-Finalization-Decision-Pack.md)

### D-30 — Cross-Tenant Isolation Enforcement
- **Decision:** Defense-in-depth across authorization, routing, the data layer, and audit.
- **Approved option:** D. Authoritative tenant claim + membership (D-04/D-06) → single-tenant routing (D-07) → per-tenant credentials + no cross-tenant connection reuse (D-13/D-14) → audit/anomaly detection. No cross-tenant joins or spanning queries — ever.
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-005 (owns enforcement); IC-002, IC-003, IC-004 (honor isolation)
- **Source:** [D-06-D10-D11-D12-D30-Finalization-Decision-Pack.md](D-06-D10-D11-D12-D30-Finalization-Decision-Pack.md)

### JWT Lifecycle (D-05 detail)
- **Decision:** Short-lived access tokens; OIDC refresh tokens managed at the IdP; JWKS with `kid` + overlap rotation; revocation via short-TTL + IdP refresh-token revocation, with an optional bounded control-plane `jti` denylist for emergencies; no session store.
- **Approved option:** As above. Validation is DB-free and strict (iss/aud/exp/kid; alg-confusion rejected); the tenant claim is bound (D-06) to prevent cross-tenant reuse (D-30); key material via the D-14 abstraction; any OIDC-standard self-hostable IdP (no Supabase Auth).
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-005
- **Source:** [D-06-D10-D11-D12-D30-Finalization-Decision-Pack.md](D-06-D10-D11-D12-D30-Finalization-Decision-Pack.md)

### D-31 — Global Directory Residency
- **Decision:** The Global Startup Directory and Global Investor Directory reside in the Control Database; the Control Database serves as both Control Plane and Global Discovery Platform.
- **Approved option:** B (Control DB hosts global directories). Residency is absolute: global directory records reside only in the Control DB; tenant-owned copies (including imported records) reside only in tenant DBs; no tenant-owned data resides in the Control DB; no global directory records reside in tenant DBs. Directory schema follows D-12; directory access is governed by IC-005 — authenticated, auditable, never exposing tenant-owned records.
- **Status:** ✅ Approved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-001 (amendment — Control DB scope + D-12 directory schema); IC-003 (amendment — Global record = Control-DB directory record); IC-005 (clarification only — directory access is a control-plane read governed by IC-005)
- **Source:** D-31 v1.1 (Global Directory Residency)

### D-32 — Role Hierarchy & Operating Model
- **Decision:** Adopt the MVP role hierarchy CONTROL, MASTER_AGENT, TENANT_ADMIN, TENANT_AGENT, STARTUP_USER, INVESTOR_USER — defining **roles, not permissions** (permissions remain contract-controlled under IC-005).
- **Approved option:** Roles mapped to D-03 (internal: CONTROL, MASTER_AGENT; federated: tenant/startup/investor users). MASTER_AGENT MUST obey one request → one active tenant → one database (D-04); multi-tenant membership does not permit multi-tenant access within a single request; the hierarchy does NOT imply cross-tenant superuser access (no privilege escalation across tenant boundaries). MASTER_AGENT ↔ tenant assignments are stored in the Control-DB Tenant Registry. Relationship Management / Operational Oversight are limited to the active tenant context; cross-tenant collaboration is deferred to future IC-007.
- **Status:** ✅ Approved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-005 (amendment — role model + anti-escalation); IC-002 (minor — assignment storage); IC-007 (future — cross-tenant collaboration)
- **Source:** D-32 v1.1 (Role Hierarchy & Operating Model)

---

## Open / not-yet-decided

**Resolved to date:** D-01–D-05 (foundational), D-07, D-13–D-17 (tenant infrastructure), D-08, D-22–D-25 (lineage), D-18–D-21 + D-09 (ingress) (import), D-06, D-10–D-12, D-30 + JWT lifecycle (finalization), and **D-31, D-32 (post-freeze amendments, Approved)**. See the register above.

Still open, tracked in [Contract-Gap-Analysis.md](Contract-Gap-Analysis.md):
- **IC-006 AI (post-MVP):** PII **egress** policy (D-09 egress), first provider (D-26), sync/queued (D-27), usage/cost (D-28), AI lineage (D-29).

> **The MVP architecture is frozen. IC-001 through IC-005 are `Final`.** **D-31** (Global Directory Residency) and **D-32** (Role Hierarchy & Operating Model) are **Approved** amendments adopted under the change-control rule and folded into IC-001 / IC-002 / IC-003 / IC-005; they extend the frozen architecture without reopening it. IC-006 remains **`Draft` (post-MVP)**; **IC-007 (Deal Collaboration & Cross-Tenant Sharing)** is a **`Deferred`** future contract. Remaining open decisions are the post-MVP IC-006 cluster (D-09 egress, D-26–D-29). **D-08** remains a standing business/legal action (name the compliance floor regime and per-tenant values); its *architecture* is fixed. Per the change-control rule, any change to frozen MVP behavior requires a contract amendment (register entry → contract → code).
