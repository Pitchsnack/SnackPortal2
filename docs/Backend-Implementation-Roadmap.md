# SnackPortal2 — Backend Implementation Roadmap

**Phase:** Architecture complete → Implementation planning · **Type:** Planning only (no code, no file contents)
**Date:** 2026-06-05 · **Implementation owner:** Claude Code (Lovable not permitted to implement the backend)
**Basis:** PRD 8C v1.4 (approved); IC-001–IC-005 **Final**; D-01–D-32 **Approved**; IC-006 (Draft/post-MVP), IC-007 (Deferred). See [Architecture-Decision-Register.md](Architecture-Decision-Register.md) and [Project-Overview.md](Project-Overview.md).

This roadmap sequences the backend build into six phases. It defines *what* each phase delivers and *what governs it* — it does not contain code or file contents. Every deliverable traces to a Final contract and Approved decisions.

---

## Cross-Cutting Rules (apply to every phase)
- **Contracts precede implementation.** Any needed divergence requires a contract amendment first (register entry → contract → code). The MVP architecture is frozen.
- **Physical isolation is non-negotiable:** one request → one active tenant → one database; no cross-tenant joins; no shared tenant databases.
- **Secrets never in DTOs, logs, responses, audit, or lineage** — references only, via the D-14 secret-store abstraction.
- **Vendor-neutral:** no Supabase Auth/Edge/runtime, no Lovable runtime, no provider-proprietary identity/queue/gateway. Portable across AWS / Azure / GCP / self-hosted (PostgreSQL-portable).
- **Verify against contracts** at the end of each phase (behavior conforms to the governing IC-00x / D-xx), not just "builds."

**Out of scope for these six phases:** IC-006 AI Gateway (post-MVP, D-02), IC-007 cross-tenant collaboration (Deferred), and tenant business-domain features (deals/relationships beyond the generic tenant-data model). The six phases build the **platform foundation** those later layers ride on.

---

## Phase 1 — Repository Setup
- **Objective:** Establish the vendor-neutral backend repository and the portability/abstraction scaffolding all later phases depend on. No business logic.
- **Contracts used:** All (IC-001–IC-005) as references; CLAUDE.md constraints.
- **Decisions applied:** D-14 (secret-store abstraction boundary), D-02 (AI-ready, not built), anti-vendor-lock-in (all).
- **Dependencies:** None (entry phase).
- **Deliverables:**
  - Service layout per PRD 8C (api-gateway, auth-router, database-router, control-plane, import-service, lineage-service, shared, plus top-level infrastructure kept independent of app code).
  - Vendor-neutral **abstraction boundaries** as interfaces only: secret store (D-14), queue, and provider adapters — no concrete provider bindings.
  - Environment/config templates (no secrets inlined; references only).
  - **Approved authenticated public edges** *(replaces the former "API Gateway skeleton" — **D-45**, 2026-08-11)*: one public edge per route-owning service behind the shared public-boundary security kernel (request entry, validation, correlation IDs, bounds, audit emission; **no business logic, no routing decision, no DB selection**). The closed ratified set is IC-010 §A.2.
  - Health/readiness interface placeholder; contract-traceability + coding-standard docs; CI scaffolding that asserts portability constraints.
- **Claude Code:** ✅ Generatable now. Fully ready; lowest risk; unblocks all later phases.

## Phase 2 — Control Plane
- **Objective:** Bring up the control plane per IC-001 — two-phase bootstrap, Control DB, tenant registry, global readiness, and the Global Discovery Platform. Never holds tenant data.
- **Contracts used:** IC-001 (primary); IC-002 (registry/provisioning interplay); IC-005 (federation config + membership/role registry storage).
- **Decisions applied:** D-01 (Phase 0 system identity + static trust anchor), D-12 (Control-DB schema compatible-range, fail-safe), D-11 (hybrid registry enumeration), D-10 (three-state readiness), D-31 (Global Startup/Investor Directories in Control DB), D-15 (IaC + control-plane provisioning), D-07 (registry-authoritative mapping data), D-03/D-32 (membership + role registry), D-14 (trust-anchor reference).
- **Dependencies:** Phase 1.
- **Deliverables:**
  - Control-plane service with the **Phase 0 → Phase 1 bootstrap** sequence (system-identity auth, no DB lookup → Control DB up + schema check → routing metadata loaded → Phase 1).
  - **Control-DB schema-compatibility** checker (D-12; fail-safe to global not-ready).
  - **Tenant Registry** + hybrid enumeration (warm working set + lazy load + background refresh; invalidation on re-association) (D-11/D-07).
  - **Three-state readiness** interface (ready/degraded/not-ready; degraded never denies healthy tenants) (D-10/D-16).
  - **Global Discovery Platform** storage + access scaffolding (Global Startup/Investor Directories) (D-31).
  - **Provisioning workflow** interface (IaC-orchestrated; break-glass disabled after first boot) (D-15) with **provisioning audit** (IC-002).
  - **Membership/role registry** (CONTROL, MASTER_AGENT, TENANT_ADMIN/AGENT, STARTUP/INVESTOR_USER; assignments in the registry) (D-32/D-03).
- **Claude Code:** ✅ Generatable (against IC-001). Concrete trust-anchor encoding and supported schema-range values are implementation choices via the D-14 abstraction.

## Phase 3 — Authentication Layer
- **Objective:** Implement the Authentication Router per IC-005 — DB-free OIDC stateless JWT validation, hybrid identity, signed-claim tenant carriage, JWT lifecycle, and the role model.
- **Contracts used:** IC-005 (primary); IC-001 (two-phase model); IC-002 (consumes federation config + membership).
- **Decisions applied:** D-05 (OIDC stateless JWT, no session store), D-03 (hybrid identity), D-06 (signed claim authoritative + carrier-match), D-32 (role model), JWT lifecycle (JWKS/`kid` rotation, IdP refresh, revocation), D-30 (authN layer of defense-in-depth), D-01 (separation preserved — validation DB-free).
- **Dependencies:** Phase 2 (federation config + membership registry), Phase 1.
- **Deliverables:**
  - Authentication service + **JWT validation layer** (strict `iss`/`aud`/`exp`/`kid`; algorithm-confusion rejected; signed; short-lived).
  - **JWKS/`kid` key-rotation** handling; IdP-refresh model; optional bounded control-plane `jti` denylist interface (no session store).
  - **Tenant-context resolver** (signed claim = source of truth; subdomain/header optional and must match; mismatch → 403) (D-06).
  - **Membership + role validation** (one active tenant per request; multi-membership ≠ multi-tenant access; anti-privilege-escalation) (D-04/D-32).
  - Authentication audit hooks (auth, tenant switch, denied access).
- **Claude Code:** ✅ Generatable (PRD 8C §18). Use portable OIDC/JWKS libraries; no vendor identity service.

## Phase 4 — Database Router
- **Objective:** Implement the Database Router per IC-005/D-07/D-13/D-30 — registry-authoritative resolution, per-tenant pooling, per-tenant credentials, and enforced single-tenant binding.
- **Contracts used:** IC-005 (routing); IC-002 (tenant DB association + readiness); IC-001 (registry from control plane).
- **Decisions applied:** D-07 (registry-authoritative; no guessing/naming-convention/hardcoded), D-13 (lazy bounded per-tenant pools + LRU), D-14 (per-tenant credentials by reference), D-30 (defense-in-depth: single-tenant binding, no cross-tenant connection reuse, audit), D-04 (one active tenant/request), D-11 (cache + invalidation on re-association), D-16/D-17 (readiness + schema-version gating at routing).
- **Dependencies:** Phase 2 (registry/readiness), Phase 3 (authenticated tenant context).
- **Deliverables:**
  - Database-router service + **registry-authoritative resolver** with tenant-scoped cache and invalidation on re-association.
  - **Per-tenant connection manager** (lazy/bounded/LRU; per-tenant credentials via D-14; never reused across tenants).
  - **Single-tenant binding enforcement** (one resolved DB per request) and **readiness/version gating** (route only `Ready`, in-range tenants) (D-16/D-17).
  - **Control DB Registry interface** and isolation **audit/anomaly hooks** (D-30 layer 4).
- **Claude Code:** ✅ Generatable (PRD 8C §18). Connection pooling is portable; the cross-tenant connection-reuse guard is the critical correctness point.

## Phase 5 — Import Layer
- **Objective:** Implement import per IC-003 — global-to-tenant copy, pluggable source adapters, hybrid execution, idempotency, batched partial-failure, ingress validation/PII, with atomic lineage emission.
- **Contracts used:** IC-003 (primary); IC-002 (tenant readiness); IC-005 (auth/routing, one active tenant); IC-004 (lineage emission handoff); IC-001/D-31 (Global record = Control-DB directory record).
- **Decisions applied:** D-18 (pluggable adapters; v1 Global + CSV/JSON), D-19 (hybrid async/sync), D-20 (idempotency: operation key + natural-key upsert), D-21 (batched/checkpointed/resumable), D-09 ingress (validate/sanitize/classify), D-31 (read Global from Control DB), D-22/D-23/D-25 (emit lineage core; re-import appends; provenance roots), D-13 (separate import capacity), D-16/D-17 (readiness/version gating).
- **Dependencies:** Phases 2–4 **and** the **Phase 6 lineage write path** (atomic provenance — see Sequencing Note).
- **Deliverables:**
  - Import service + **source-adapter abstraction** with v1 adapters: Global Directory read (D-31), CSV, JSON (portable ingestion only — no provider bulk-load).
  - **Hybrid execution** (async-default durable job + bounded sync fast-path) with `GetImportStatus` (non-sensitive counts) (D-19).
  - **Idempotency** (operation key + per-record natural-key upsert; no-op when unchanged) (D-20).
  - **Batched/checkpointed, resumable** engine; failed import never mutates Global; isolation on failure (D-21).
  - **Ingress validation + injection-safe sanitization + PII classification** (per-tenant minimize/tokenize) (D-09 ingress).
  - **Atomic lineage emission** per committed batch (writes tenant copy + lineage in the same tenant transaction); import operational audit. Reads Global from Control DB, writes tenant DB only.
- **Claude Code:** ✅ Generatable, in stages. Most logic-heavy; depends on Phases 2–4 + the lineage write path.

## Phase 6 — Lineage Layer
- **Objective:** Implement lineage per IC-004 — minimum record, append-only + per-tenant hash-chaining, unified provenance graph, retention/archival, tenant-resident and access-controlled.
- **Contracts used:** IC-004 (primary); IC-002 (tenant-resident storage + readiness); IC-005 (access control); IC-003 (import emits into it).
- **Decisions applied:** D-22 (minimum core + reference/code-only envelope), D-23 (DB-level append-only + per-tenant cryptographic hash-chaining), D-25 (unified per-tenant provenance graph), D-24/D-08 (per-tenant retention/archival within floor/ceiling; tombstone expiry), D-16 (per-tenant independence), D-17 (lineage schema migration), D-14 (keyed-hash key by reference).
- **Dependencies:** Phases 2–4 (tenant DBs, routing, auth). **Provides the lineage write path Phase 5 requires.**
- **Deliverables:**
  - Lineage service + **minimum lineage record** model (fields only; no payloads/PII/secrets) (D-22).
  - **Append-only enforcement** (DB-level privilege separation + reject UPDATE/DELETE) **+ per-tenant cryptographic hash-chaining** integrity marker (D-23).
  - **Unified per-tenant provenance graph** via parent references; never crosses tenants (D-25).
  - **Retention/archival** within the compliance floor/ceiling; policy-driven expiry via tombstones; chain stays verifiable (D-24/D-08).
  - **Access-controlled lineage read/query** (tenant-scoped, IC-005); audit integration for chain-break/expiry.
- **Claude Code:** ✅ Generatable. Hash-chaining + append-only enforcement are portable PostgreSQL + application logic.

---

## ⚠ Sequencing Note — Phases 5 ↔ 6 (atomic provenance)
IC-003/IC-004 require **atomic provenance**: an import writes the tenant copy and its lineage in the **same tenant transaction**, so committed data always has provenance. Therefore the **Phase 6 lineage write/emit path must be available before Phase 5 commits tenant data** — mirroring the architecture sequencing (lineage specified before import). Recommended: **co-develop Phase 6's write path with Phase 5**, or land Phase 6's emit path just ahead of Phase 5's commit path. (Lineage *query/retention* features can follow; the *write path* is the hard dependency.)

## Claude Code Generation Summary
| Phase | Claude Code generatable | Start readiness |
|---|---|---|
| 1 — Repository Setup | ✅ | Now (no upstream deps) |
| 2 — Control Plane | ✅ | After Phase 1 |
| 3 — Authentication Layer | ✅ | After Phase 2 |
| 4 — Database Router | ✅ | After Phases 2–3 |
| 5 — Import Layer | ✅ (staged) | After Phases 2–4 + Phase 6 write path |
| 6 — Lineage Layer | ✅ | After Phases 2–4 (build write path with/ahead of Phase 5) |

**All six phases are Claude Code-generatable** (Claude Code is the implementation owner per PRD 8C). They are generated **against the Final contracts**, in dependency order, each verified for contract conformance before the next begins. Where PRD 8C v1.4 abbreviates a decision (full JWT lifecycle, three-state readiness, per-tenant credentials), the Final contracts are authoritative and binding.

## Recommended Build Order
`Phase 1 → Phase 2 → Phase 3 → Phase 4 → (Phase 6 lineage write path) → Phase 5`, then complete Phase 6 query/retention. Implementation may begin with **Phase 1** immediately; this remains planning until you authorize code generation.
