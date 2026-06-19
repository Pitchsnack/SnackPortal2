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
| **D-20** | Import idempotency | **Operation-level idempotency key + per-record natural-key reconciliation** (upsert; no-op when unchanged); re-import appends lineage recording the outcome; never mutates Global. **Amended in part by D-34 (2026-06-12):** the default overwrite-on-re-import semantics are superseded by user-controlled re-import; idempotency, natural-key reconciliation, lineage-append, and never-mutate-Global remain in force. | ✅ Resolved — amended in part by D-34 | 2026-06-05 | IC-003 (amendment pending per D-34); IC-004 (re-import appends) |
| **D-21** | Partial-failure semantics | **Batched/checkpointed atomic imports with resumability** (default); optional strict all-or-nothing; each committed batch carries its lineage (atomic provenance). | ✅ Resolved | 2026-06-05 | IC-003; IC-004 (lineage granularity) |
| **D-09** | PII handling policy (split) | **Import-ingress slice resolved** (IC-003): policy-driven per-tenant validation/sanitization/classification on a mandatory floor; PII/payloads/secrets never in lineage/audit/responses. **AI-egress slice open** (IC-006). | ⏳ Ingress Resolved; egress open | 2026-06-05 (ingress) | IC-003 (ingress); IC-006 (egress, open) |
| **D-06** | Tenant identifier carriage | **Signed JWT claim authoritative** with **carrier-match enforcement** (subdomain/header must match the claim; mismatch rejected) + membership check (D-04); tenant switch = new tenant-scoped token. | ✅ Resolved | 2026-06-05 | IC-005; IC-002 (membership) |
| **D-10** | Global ready vs degraded | **Three-state** readiness (ready / degraded / not-ready); **degraded is observability-only and never denies healthy tenants** (D-16); global not-ready reserved for Control-DB / Phase-0 failure. | ✅ Resolved | 2026-06-05 | IC-001; IC-005 (routing gates on Control DB) |
| **D-11** | Registry enumeration | **Hybrid:** warm bounded working set at startup + lazy-load on demand + background refresh; registry-authoritative (D-07) with invalidation on re-association. Ready = registry reachable, not fully enumerated. | ✅ Resolved | 2026-06-05 | IC-001; IC-005 (Database Router) |
| **D-12** | Control-DB schema mismatch | **Compatible-range (expand/contract)**; serve only within the supported range, else **global not-ready** (fail-safe); migration is a controlled, audited step (never implicit at startup). | ✅ Resolved | 2026-06-05 | IC-001; IC-005 (routing gates on compatibility) |
| **D-30** | Cross-tenant isolation enforcement | **Defense-in-depth:** authoritative claim + membership (D-04/D-06) → single-tenant routing (D-07) → per-tenant credentials + no cross-tenant connection reuse (D-13/D-14) → audit/anomaly detection. No cross-tenant joins ever. | ✅ Resolved | 2026-06-05 | IC-005; IC-002; IC-004; IC-003 |
| **JWT** | JWT lifecycle (D-05 detail) | **Short-lived access tokens + OIDC refresh at the IdP + JWKS/`kid` rotation + IdP refresh-token revocation + optional bounded control-plane `jti` denylist; no session store.** Validation DB-free; tenant claim bound. | ✅ Resolved | 2026-06-05 | IC-005 |
| **D-31** | Global Directory Residency | **Global Startup & Investor Directories reside in the Control Database** (Control Plane + Global Discovery Platform). Global directory records only in Control DB; tenant-owned copies only in tenant DBs; no tenant data in Control DB. Directory schema follows D-12; access governed by IC-005. **Extended by D-35 (2026-06-12):** the Global Deal Directory joins under identical absolute-residency terms (not reopened). | ✅ Approved — extended by D-35 | 2026-06-05 | IC-001 (amend), IC-003 (amend), IC-005 (clarify) |
| **D-32** | Role Hierarchy & Operating Model | **MVP roles:** CONTROL, MASTER_AGENT, TENANT_ADMIN, TENANT_AGENT, STARTUP_USER, INVESTOR_USER (roles, not permissions). MASTER_AGENT obeys one-request→one-active-tenant→one-DB; multi-membership ≠ multi-tenant access; no cross-tenant superuser. Assignments in Control-DB Tenant Registry. Cross-tenant collaboration → future IC-007. | ✅ Approved | 2026-06-05 | IC-005 (amend), IC-002 (minor) |
| **D-33** | Workspace definition & tenant context | **Workspace = UI representation of a signed tenant context.** Tenant Workspace ↔ signed claim ↔ exactly one tenant DB; Control Workspace = CONTROL role, tenantless, control-plane scope only. Switching = new scoped token (audited). Carriers: subdomain/named header under match-or-reject; cookies/query-strings stripped at the gateway; workspace is never a routing input, filter, claim, or database. | ✅ Approved | 2026-06-12 | IC-005 (amend), IC-002 (amend) |
| **D-34** | Operational audit & re-import governance | **Operational audit = Control DB; import lineage = tenant DB** (IC-004 Invariant 1 reaffirmed). Audit taxonomy homed: IC-001 (global-directory publication/export classes), IC-002 (administrative/runtime/tenant-op classes) — all under the package-wide **reference-only audit representation rule** (refs only; never names/emails/PII/payloads). **Re-import = user-controlled (R3); amends D-20 in part** (default overwrite superseded); lineage preserved across every outcome; future merge constrained (discrete, user-initiated, lineage-appending, never automatic, never write-back). | ✅ Approved | 2026-06-12 | IC-001 (amend), IC-002 (extend), IC-003 (amend); D-20 (amended in part) |
| **D-35** | Global Deal Directory | **The Global Deal Directory resides in the Control DB**, extending D-31 under identical absolute residency (not reopened). Global Deal ≠ Tenant Deal; import-copy is the only bridge. **Publication Boundary + Tenant Anonymity Rules:** directory records carry approved global discovery metadata only — never tenant-owned **or tenant-attributable** data (no tenant_id/name/code/reference/membership-reference); tenant→global publication is ungoverned and therefore prohibited pending a future ADR. | ✅ Approved | 2026-06-12 | IC-001 (amend), IC-003 (amend — Global record incl. Deals); D-31 (extended) |
| **D-36** | Ownership architecture | **Exactly one human Owning Agent per tenant entity (Startup/Investor/Deal) + one reserved nullable AI-owner reference** (NULL until IC-006 defines an AI identity namespace). References only: `owner_agent_ref`/`owner_ai_agent_ref` — never names/emails/identity payloads. Ownership ≠ authorization ≠ visibility ≠ residency. **Ownership domain rule:** owner holds membership in the record's residency domain; global-record owners = Control-domain principals only. **Audit follows record residency** (tenant transfers → tenant DB; global → Control DB). Import never transfers ownership; copies get new tenant-side owners (initial assignment → IC-008). Reserves **IC-008 — Ownership Contract**. | ✅ Approved | 2026-06-12 | IC-008 (new, reserved), IC-002 (extend); IC-006/IC-007 (future) |
| **D-37** | Portal Contract Architecture | **Portals are presentation-layer contracts** (display/discover/initiate) that never determine database, tenant, authentication, authorization, ownership, routing, or residency. **Gateway-only data access** (no portal-side database or Supabase data access of any kind); record-residency retrieval; no cross-workspace client caching; **Portal Import Rule** (discrete, user-initiated only — no portal-side synchronization); own-kind global-directory access for STARTUP_USER/INVESTOR_USER (IC-005/D-31 reads); Master Agent cross-tenant capabilities **Reserved Pending IC-007**; six channel-agnostic portal classes; future portals need new ADRs. **Reserves IC-009 — Portal Contracts** (placeholder created). | ✅ Approved | 2026-06-12 | IC-009 (new, reserved); IC-001/IC-002/IC-003/IC-005 (no change); IC-006/IC-007/IC-008 (boundaries respected) |
| **IC-009-ADOPT** | IC-009 Portal Contracts adoption | **IC-009 promoted Reserved → Final** (revision **IC-009-R1**), built from the verified PRD 03 V2 §3 draft. Per-portal data + visibility contracts for the six D-37 portal classes. **Ratifies DEC-4** (owner references hidden from directory readers in MVP — IC-008 P5); **DEC-9** settled (workspace switch = new scoped token); **DEC-10** resolved (IC-001 four discovery-metadata categories). Adopts the §P verification criteria + §R D-37 §20 V1–V12 mapping as IC-009 acceptance criteria. **Carries DEC-11 forward:** the API Gateway PRD must not bind ownership-audit DTO residency until the IC-002 ownership-audit-section extension lands. Physical Multi-Database MVP unchanged. | ✅ Approved | 2026-06-17 | IC-009 (Reserved → Final, IC-009-R1); IC-002 (ownership-audit extension pending — DEC-11); IC-010/IC-005/IC-001/IC-008 (no change — boundaries respected) |

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
- **Status:** ✅ Resolved · **Date approved:** 2026-06-05 · **Amended in part by D-34 (2026-06-12):** the default overwrite-on-re-import is superseded by user-controlled re-import (R3); idempotency keys, natural-key reconciliation, lineage-append, and never-mutate-Global remain in force. Until the IC-003 amendment lands, the as-built upsert default remains contract-conformant.
- **Affected contracts:** IC-003; IC-004 (re-import appends; D-23/D-25)
- **Source:** [D-18-D19-D20-D21-D09-Import-Decision-Pack.md](D-18-D19-D20-D21-D09-Import-Decision-Pack.md); amendment: [D-34-Operational-Audit-Re-Import-Governance.md](D-34-Operational-Audit-Re-Import-Governance.md)

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
- **Status:** ✅ Approved · **Date approved:** 2026-06-05 · **Extended by D-35 (2026-06-12):** the Global Deal Directory joins under identical absolute-residency terms; D-31 is not reopened.
- **Affected contracts:** IC-001 (amendment — Control DB scope + D-12 directory schema); IC-003 (amendment — Global record = Control-DB directory record); IC-005 (clarification only — directory access is a control-plane read governed by IC-005)
- **Source:** D-31 v1.1 (Global Directory Residency); extension: [D-35-Global-Deal-Directory-Architecture.md](D-35-Global-Deal-Directory-Architecture.md)

### D-32 — Role Hierarchy & Operating Model
- **Decision:** Adopt the MVP role hierarchy CONTROL, MASTER_AGENT, TENANT_ADMIN, TENANT_AGENT, STARTUP_USER, INVESTOR_USER — defining **roles, not permissions** (permissions remain contract-controlled under IC-005).
- **Approved option:** Roles mapped to D-03 (internal: CONTROL, MASTER_AGENT; federated: tenant/startup/investor users). MASTER_AGENT MUST obey one request → one active tenant → one database (D-04); multi-tenant membership does not permit multi-tenant access within a single request; the hierarchy does NOT imply cross-tenant superuser access (no privilege escalation across tenant boundaries). MASTER_AGENT ↔ tenant assignments are stored in the Control-DB Tenant Registry. Relationship Management / Operational Oversight are limited to the active tenant context; cross-tenant collaboration is deferred to future IC-007.
- **Status:** ✅ Approved · **Date approved:** 2026-06-05
- **Affected contracts:** IC-005 (amendment — role model + anti-escalation); IC-002 (minor — assignment storage); IC-007 (future — cross-tenant collaboration)
- **Source:** D-32 v1.1 (Role Hierarchy & Operating Model)

### D-33 — Workspace Definition & Tenant Context Architecture
- **Decision:** Workspace = the UI representation of a signed tenant context. Tenant Workspace ↔ signed JWT claim ↔ exactly one tenant DB; Control Workspace = CONTROL-role principal, tenantless, control-plane scope only (structurally cannot reach a tenant DB). Workspace switching = obtaining a new tenant-scoped token (audited). Recognized carriers (subdomain, named header) operate under mandatory match-or-reject; inbound workspace cookies/query-strings are stripped at the API Gateway and never read by any backend component; workspace is never a routing input, filter, separate claim, or database concept.
- **Reason / Finding reference:** PRD 1A-R2 Question E (workspace concept absent from all governance); PRD-WA-01-R1 §9 additional requirements. **Review reference:** adversarially reviewed 2026-06-12 (conformance + completeness agents); PRD-D33-D37-R1 independent review verdict **Aligned** (strongest document in the package; zero principle violations).
- **Amendment scope / Impact:** governs all future gateway/frontend wiring (gateway builds RequestContext exclusively from AuthContext); zero backend behavior change; memberships-for-principal read endpoint required at implementation time (contract owner: IC-002 API table per the independent review).
- **Status:** ✅ Approved (PRD-D33-D36-P1-R1) · **Date approved:** 2026-06-12
- **Affected contracts:** IC-005 (Workspace Terminology amendment — must enumerate exact carrier header names + tenantless-CONTROL carrier rule + mandatory carrier-on-CONTROL anomaly audit); IC-002 (Tenant-Workspace alias + MembershipsForPrincipal operation)
- **Errata:** [D-33-E1](D-33-E1-Workspace-Architecture-Errata.md) (2026-06-12, per PRD-D33-D37-V2 MAJ-1 / PRD-D33-D37-V2-R1 WP-A) — resolves the ADR↔register↔inventory inconsistency: carrier-on-CONTROL anomaly audit is **mandatory** IC-005-amendment content (implementation at amendment execution); MembershipsForPrincipal's **contract owner is the IC-002 amendment** (implementation timing unchanged: gateway/frontend execution PRD); ADR header corrected to Approved. Scope: documentation chain only; no decision or behavior change.
- **Source:** [D-33-Workspace-Definition-Tenant-Context-Architecture.md](D-33-Workspace-Definition-Tenant-Context-Architecture.md)

### D-34 — Operational Audit Architecture & Re-Import Governance
- **Decision:** Operational audit resides in the Control DB; import lineage remains tenant-resident (IC-004 Invariant 1 reaffirmed, not reopened). Audit taxonomy: Administrative + Runtime Operational + tenant-scoped-operation classes homed in IC-002; global-directory Publication/Export classes homed in IC-001 — all bound by the package-wide **Global Audit Representation Rule** (audit records carry references only — actor_ref/user_ref/tenant_ref/ownership_ref/record_ref; never names, emails, display names, identity payloads, PII, authorization payloads, or tenant business content). Re-import becomes user-controlled (R3: Import New Copy / Replace Existing / Ignore / constrained Future Merge); lineage and import history preserved across every outcome.
- **Reason / Finding reference:** PRD 1A-R2 (operational audit vs lineage gap; re-import under-governed); PRD-D33-D37-R1 **MAJ-3** (representation rule was code-comment-only — now contract-normative) and **MAJ-4** (uncited D-20 supersession — now explicit). **Review reference:** D-34 Review Report + closure (2026-06-12); independent review verdict **Aligned**.
- **Amendment scope / Impact:** **amends D-20 in part** (default overwrite-on-re-import superseded; all other D-20 mechanics intact); as-built upsert remains contract-conformant until the IC-003 amendment lands, then becomes a tracked remediation item. No approved ADR may be silently replaced (standing verification criterion).
- **Status:** ✅ Approved (PRD-D33-D36-P1-R1) · **Date approved:** 2026-06-12
- **Affected contracts:** IC-001 (amend — publication/export audit home + representation rule); IC-002 (audit-section extension); IC-003 (amend — re-import semantics refining D-20); IC-004 (no change)
- **Errata:** [D-34-E1](D-34-E1-Capability-Inventory-Errata.md) (2026-06-12, per PRD-D33-D37-V2 Minor 3 / PRD-D33-D37-V2-R1 WP-B) — §2 inventory row corrected: publication audit is **Not implemented** (directory mutations unaudited; disproven by code); directory-mutation/publication audit becomes explicit IC-001-amendment + execution-PRD scope with a test. Scope: inventory correction only; no decision or audit-rule change.
- **Source:** [D-34-Operational-Audit-Re-Import-Governance.md](D-34-Operational-Audit-Re-Import-Governance.md)

### D-35 — Global Deal Directory Architecture
- **Decision:** The Global Deal Directory exists in the Control Database, completing the Global Discovery Platform (Startups, Investors, Deals) under D-31's identical absolute-residency terms (extension, not reopening). Global Deal ≠ Tenant Deal; import-copy is the only bridge; tenants' copies evolve independently. **Publication Boundary Rule:** directory records carry approved global discovery metadata only. **Tenant Anonymity Rule:** no publication record may contain tenant_id/tenant_name/tenant_code/tenant_reference/membership_reference or anything attributable to a tenant or tenant activity. Any movement of tenant-resident information into any Global record, by any mechanism, is prohibited pending explicit future governance.
- **Reason / Finding reference:** PRD 1A-R2 Question H (Deal Directory uncontracted); PRD-D33-D37-R1 **MAJ-1** (tenant-attribution gap — closed by the Tenant Anonymity Rule). **Review reference:** D-35 Review Report + closure (2026-06-12); independent review verdict **Aligned** (conditional hardening applied).
- **Amendment scope / Impact:** IC-003's Global-record definition extends to Deal records (making deal import contracted); discovery metadata defined as deal-attributed and tenant-anonymous; directory/audit record classes explicitly separated.
- **Status:** ✅ Approved (PRD-D33-D36-P1-R1) · **Date approved:** 2026-06-12
- **Affected contracts:** IC-001 (amend — directory addition at all touchpoints + category definitions + anonymity rule); IC-003 (amend — Global record incl. Deals + D-20 deal natural-key semantics); D-31 (extended); IC-002/IC-004/IC-005 (no change)
- **Source:** [D-35-Global-Deal-Directory-Architecture.md](D-35-Global-Deal-Directory-Architecture.md)

### D-36 — Ownership Architecture
- **Decision:** Every tenant-resident Startup/Investor/Deal has exactly one human Owning Agent plus one reserved, nullable Owning AI Agent reference (NULL until IC-006 defines an AI identity namespace). Representation is reference-only (`owner_agent_ref`/`owner_ai_agent_ref`, D-03 resolution at presentation time; never names/emails/identity payloads). Ownership ≠ authorization ≠ visibility ≠ residency. **Ownership domain rule:** the owning principal must hold membership in the record's residency domain, per record; Control-DB global-record owners are Control-domain (D-03 internal) principals only. **Audit Residency Rule:** ownership audit follows record residency (tenant-record transfers → tenant DB; global-record transfers → Control-DB Administrative Audit) and never crosses residency boundaries. Import never transfers ownership; imported copies receive new tenant-side ownership (initial assignment defined by IC-008).
- **Reason / Finding reference:** PRD 1A-R2 Question I (ownership pure business vision); PRD-D33-D37-R1 **MAJ-2** (transfer-audit residency — corrected by the Audit Residency Rule). **Review reference:** D-36 Review Report + closure (2026-06-12); independent review verdict Partially Aligned → corrections applied in R2.
- **Amendment scope / Impact:** reserves **IC-008 — Ownership Contract** (eligibility matrix, initial-owner-on-import, transfer workflow, record-shape amendments); tenant-resident ownership-audit class added to the IC-002 extension; cross-tenant ownership remains impossible (IC-007-reserved).
- **Status:** ✅ Approved (PRD-D33-D36-P1-R1) · **Date approved:** 2026-06-12
- **Affected contracts:** IC-008 (new — reserved); IC-002 (audit extension); IC-003/IC-004 (no change); IC-006/IC-007 (future extensions)
- **Source:** [D-36-Ownership-Architecture.md](D-36-Ownership-Architecture.md)

### D-37 — Portal Contract Architecture
- **Decision:** Portals are presentation-layer contracts only — they display, discover, and initiate, and never determine database, tenant, authentication, authorization, ownership, routing, or residency. All portal data access flows exclusively through the API Gateway (no portal-side database connections or Supabase data access of any kind; no RLS-as-logic); portal-visible data follows record residency; client caches never cross tenant or workspace boundaries (workspace switch invalidates the portal data context); imports via portals are discrete, explicitly user-initiated IC-003 operations (no portal-side synchronization, automatic re-import, or cross-database updates); portal DTOs carry provenance markers with the D-35 Tenant Anonymity Rule prevailing for directory records; audit per the D-34 representation rule. Six channel-agnostic portal classes (Control, Master Agent, Tenant, Startup, Investor, AI-Reserved); STARTUP_USER/INVESTOR_USER receive own-kind global-directory discovery (IC-005/D-31 reads); Master Agent cross-tenant capabilities are Reserved Pending IC-007; workspace switching (D-33) is a shell-level capability in every portal; future portal classes require new ADRs.
- **Reason / Finding reference:** PRD-D33-D37-R1 Independent Architecture Alignment Review **MAJ-5** (portal layer ungoverned — the package's final gap); PROJECT-HANDOVER-MASTER §16 portal-requirements GAP. **Review reference:** D-37 Review Report (B1–B5); D-37-R2 Closure & Alignment Review (independent verdicts: Overview alignment ALIGNED; multi-DB preservation P1–P9 demonstrated) with MAJ-A/B/C + MIN-1..5 fixes applied and mechanically closure-checked in R3.
- **Amendment scope / Impact:** completes the D-33→D-37 governance package; **reserves IC-009 — Portal Contracts** (placeholder created in `contracts/`, carrying the required per-role × per-directory visibility matrix and DTO/channel contracts); portal implementation remains blocked until IC-009 and the API Gateway contract exist; cross-tenant (IC-007), AI presentation (IC-006), and ownership mechanics (IC-008) remain deferred/reserved.
- **Status:** ✅ Approved (user/PMO) · **Date approved:** 2026-06-12
- **Affected contracts:** IC-009 (reserved → Final, IC-009-R1); IC-001/IC-002/IC-003/IC-005 (no change); IC-006/IC-007/IC-008 (boundaries respected)
- **Traceability (2026-06-12, per PRD-D33-D37-V2 MAJ-2 / PRD-D33-D37-V2-R1 WP-D):** the "API Gateway contract" this decision requires **is IC-010 — API Gateway Contract** (placeholder reserved in `contracts/`); all D-37/IC-009/register references to the API Gateway contract resolve to IC-010.
- **Source:** [D-37-Portal-Contract-Architecture.md](D-37-Portal-Contract-Architecture.md)

### IC-009-ADOPT — IC-009 Portal Contracts Adoption
- **Decision:** Promote **IC-009 — Portal Contracts** from the Reserved placeholder (reserved by D-37 §16, 2026-06-12) to a **Final governing contract** (revision **IC-009-R1**), per the contract-first sequence (D-37 §22 step 3: decision-register entry → Contract Amendment Package → promotion). The adopted text defines the per-portal data + visibility contracts for the six D-37 portal classes; portals display/discover/initiate and never determine database/tenant/auth/authorization/ownership/routing/residency.
- **Reason / Finding reference:** PRD 02 Frontend Integration Readiness (NO-GO — IC-009 = keystone blocker); D-37 §16 reservation. **Review reference:** PRD 03 V1 independent review (0 Crit/1 Major/5 Minor — folded); **PRD 03 V3 Adoption Review = PROCEED** (independent cold re-derivation, 0 blockers); **PRD 03 V4-R1 proposed-text review = READY TO APPLY** (0 Crit/0 Major/1 Minor); **PRD 03 V4 §13 + V4-R2 §8 deterministic fidelity gate = PASS** (text == V2 §3 + only the sanctioned transforms).
- **Amendment scope / Impact:** promotes `contracts/IC-009` Reserved → Final (single-file replacement with the V4 Proposed Contract Text). **Ratifies DEC-4** (owner refs hidden from directory readers in MVP). Adopts §P verification criteria + §R V1–V12 mapping as IC-009 acceptance criteria (future API-Gateway / frontend-integration PRDs). **DEC-11 carried forward** — ownership-audit DTO residency binding is BLOCKED until the IC-002 ownership-audit-section extension lands. Stale cross-references (IC-010:146 "(non-existent) content"; ADR:291/293/306) are reconciled by SEPARATE governed editorial amendments, never bundled into the IC-009 write.
- **Status:** ✅ Approved · **Date approved:** 2026-06-17
- **Affected contracts:** IC-009 (Reserved → Final, IC-009-R1); IC-002 (ownership-audit extension — pending, DEC-11). IC-010/IC-005/IC-001/IC-008 unchanged (boundaries respected).
- **Source:** PRD 03 V2 / V3 / V4 / V4-R1 / V4-R2 (`D:\Pitchsnack\PRD\11` and `\12. Backend CI-governance handover`).

---

## Open / not-yet-decided

**Resolved to date:** D-01–D-05 (foundational), D-07, D-13–D-17 (tenant infrastructure), D-08, D-22–D-25 (lineage), D-18–D-21 + D-09 (ingress) (import), D-06, D-10–D-12, D-30 + JWT lifecycle (finalization), **D-31, D-32 (post-freeze amendments, Approved)**, and **D-33–D-37 (Workspace-Architecture governance package, Approved 2026-06-12; D-34 amends D-20 in part; D-35 extends D-31; D-37 reserves IC-009 and completes the package)**. See the register above.

Still open, tracked in [Contract-Gap-Analysis.md](Contract-Gap-Analysis.md):
- **IC-006 AI (post-MVP):** PII **egress** policy (D-09 egress), first provider (D-26), sync/queued (D-27), usage/cost (D-28), AI lineage (D-29).

> **The MVP architecture is frozen. IC-001 through IC-005 are `Final`.** **D-31** (Global Directory Residency) and **D-32** (Role Hierarchy & Operating Model) are **Approved** amendments adopted under the change-control rule and folded into IC-001 / IC-002 / IC-003 / IC-005; they extend the frozen architecture without reopening it. **D-33–D-37** (Workspace, Operational Audit & Re-Import, Global Deal Directory, Ownership, Portal Contract Architecture) are **Approved** post-freeze governance decisions (2026-06-12), with errata **D-33-E1** and **D-34-E1** (2026-06-12, PRD-D33-D37-V2-R1 — documentation-chain corrections only) — register entries precede their contract amendments, which are **pending** per **Contract Amendment Inventory R2**: IC-005 + IC-002 (D-33, as corrected by D-33-E1), IC-001 + IC-002 + IC-003 (D-34/D-35), **IC-008 (new — reserved by D-36, placeholder in `contracts/`)**, **IC-009 (adopted Final 2026-06-17 as IC-009-R1 — see IC-009-ADOPT)**, **IC-010 — API Gateway Contract (new — reserved 2026-06-12; this is the "API Gateway contract" required by D-37/IC-009)**. Portal implementation remains blocked until IC-010 exists. Until those amendments land, current contract text remains authoritative for implementation. IC-006 remains **`Draft` (post-MVP)**; **IC-007 (Deal Collaboration & Cross-Tenant Sharing)** is a **`Deferred`** future contract. Remaining open decisions are the post-MVP IC-006 cluster (D-09 egress, D-26–D-29). **D-08** remains a standing business/legal action (name the compliance floor regime and per-tenant values); its *architecture* is fixed. Per the change-control rule, any change to frozen MVP behavior requires a contract amendment (register entry → contract → code).
