# SnackPortal2 — Contract Gap Analysis

**Phase:** Architecture Planning · **Type:** Analysis only (no implementation, API, database, or infrastructure code)
**Reviewed:** IC-001 … IC-006 · **Contract status (current):** IC-001–IC-005 = `Final` (MVP architecture frozen; amended by D-31/D-32); IC-006 = `Draft` (post-MVP); IC-007 = `Deferred` (future, cross-tenant)
**Date:** 2026-06-05

This report reviews the six interface contracts in `contracts/`. It is advisory: it identifies dependencies, gaps, priorities, a completion order, and a consolidated decision register. It does not change the contracts.

---

## A. Contract Dependency Map

"Depends on" = a contract cannot be **finalized or implemented** without the other being settled first.

| Contract | Depends on | Depended on by | Role |
|---|---|---|---|
| **IC-005** Authentication Routing | IC-001 (routing metadata lives in Control DB) | IC-001, IC-002, IC-003, IC-004, IC-006 | Foundational — auth + tenant resolution |
| **IC-001** Global Startup | IC-005 (control-plane auth) | IC-002, IC-005 | Foundational — control plane / Control DB |
| **IC-002** Tenant Startup | IC-001, IC-005 | IC-003, IC-004, IC-006 | Foundational — per-tenant resolution |
| **IC-004** Lineage | IC-002, IC-005 | IC-003, IC-006 | Shared — provenance sink |
| **IC-003** Import | IC-002, IC-004, IC-005 | — | Feature — data ingress |
| **IC-006** AI Gateway | IC-002, IC-004, IC-005 | — | Feature — AI boundary |

### Layered view

```
Layer 0 (foundational, mutually bootstrapping)
    IC-005  Authentication Routing  ⇄  IC-001  Global Startup
                                          │
Layer 1 (multi-tenant core)               ▼
    IC-002  Tenant Startup  ── requires ──┘  (+ IC-005)

Layer 2 (shared services)
    IC-004  Lineage   ── requires ── IC-002, IC-005

Layer 3 (feature contracts)
    IC-003  Import       ── requires ── IC-002, IC-004, IC-005
    IC-006  AI Gateway   ── requires ── IC-002, IC-004, IC-005
```

### ⚠ Critical finding — IC-001 ⇄ IC-005 bootstrap cycle
IC-001 says global-startup endpoints are authenticated "Aligns with IC-005," **but** IC-005 says its routing metadata "lives in the Control Database" — which IC-001 is responsible for bringing up. Each depends on the other to be ready first. This circular dependency must be resolved explicitly (e.g. a bootstrap/system identity that does **not** require the Control DB, or a defined ordering where the Control DB comes up unauthenticated on a trusted internal boundary). Until resolved, neither contract can be finalized. Tracked as **D-01**.

> **Update — 2026-06-05: ✅ RESOLVED (A+B approved).** Broken via a two-phase bootstrap — a control-plane-only **system identity** verified against a **static, infrastructure-owned trust anchor** (no Control-DB lookup), transitioning to full runtime auth + tenant routing only once the Control DB is online. See [D-01-Bootstrap-Cycle-Resolution.md](D-01-Bootstrap-Cycle-Resolution.md); IC-001 and IC-005 updated accordingly.

### Secondary finding — IC-004 is a hidden prerequisite
IC-004 (Lineage) is `Medium` priority for MVP (Section C) yet is **depended on by** both IC-003 and IC-006. Its *specification* must precede theirs even though its *implementation* may be deferred. See Section D.

---

## B. Contract Gap Analysis

Every contract is intentionally a placeholder template, so all four "Requirements/Contract" bodies are `TBD`. The gaps below are the **decisions** that must be made to lift each from `Draft` — not the missing prose.

### IC-001 — Global Startup
- **Business:** Platform availability target / SLA; blast-radius policy (does "control plane down" mean all tenants are unavailable?); who operates and observes the control plane.
- **Technical:** Eager vs. lazy tenant-registry enumeration; readiness/health protocol and signals; Control-DB schema-version check mechanism; retry/backoff when the Control DB is unreachable; config/environment-template format and precedence.
- **Architecture:** Definition of "degraded" (Control DB up, some tenant DBs down); startup ordering of Auth Router vs. Control DB (the **D-01** cycle); is the control plane a single process or distributed.
- **Security:** How a *system* identity authenticates before auth routing exists (D-01); Control-DB credential/secret sourcing; who may observe readiness (readiness can leak tenant existence/count).

### IC-002 — Tenant Startup
- **Business:** Tenant lifecycle ownership (who activates/suspends and on what trigger); per-tenant SLA; onboarding/offboarding policy.
- **Technical:** Tenant-id → physical-database mapping (registry lookup, naming convention, or both); per-tenant connection-pool strategy and ceiling; lazy vs. eager connect; per-tenant migration coordination vs. global schema version.
- **Architecture:** How "one tenant's failure must not affect others" is actually enforced; provisioning boundary (who *creates* the physical DB — infra vs. app); scale limits (max tenants / connections per node).
- **Security:** Per-tenant DB credential storage and rotation; prevention of tenant-id spoofing to reach another tenant's DB; guaranteed access denial for suspended tenants.

### IC-003 — Import
- **Business:** In-scope source formats for v1; volume/size limits; who may import; ownership/retention of imported data.
- **Technical:** Sync vs. async with progress reporting; idempotency-key strategy for safe re-import; partial-failure semantics (all-or-nothing vs. per-record); max payload / streaming.
- **Architecture:** Validation location (gateway vs. service); staging area vs. direct tenant write; backpressure/rate limiting; **portable** bulk-load (no provider-specific cloud-to-DB load).
- **Security:** Input validation/sanitization (injection); upload file-type/content scanning; authz scoped to a single tenant; PII classification at ingress.

### IC-004 — Lineage
- **Business:** Compliance/regulatory driver (audit, GDPR, contractual?) — this sets retention and immutability; retention duration; who may read lineage.
- **Technical:** Minimum lineage record (source, actor, timestamp, operation, target); append-only enforcement mechanism; query patterns and performance; archival tier.
- **Architecture:** Whether one provenance chain must span import (IC-003) and AI (IC-006); per-tenant storage model; immutability enforced at DB level vs. app level (DB-level must stay PostgreSQL-portable).
- **Security:** Tamper-evidence / immutability guarantees; access control to provenance (it can reveal sensitive operations); cross-tenant lineage isolation.

### IC-005 — Authentication Routing
- **Business:** Identity model — internal staff only, external customers, or B2B SSO? One tenant per principal or many (the contract's own open question)?
- **Technical:** Auth scheme (JWT / OIDC-external-IdP / session); where the tenant identifier is carried (subdomain, header, token claim); token lifetime/refresh; how unknown vs. suspended tenants are distinguished at routing.
- **Architecture:** Resolution of the **D-01** bootstrap cycle; responsibility split between the **approved authenticated public edges** and the Auth/DB Routers *(the ingress side of this split was settled by **D-45**, 2026-08-11 — the boundary is the route-owning public edge, not an API Gateway component)*; stateless vs. stateful sessions; multi-region routing.
- **Security:** **Highest-risk contract.** Token validation and replay protection; enforcement that a principal can never reach another tenant's DB; session fixation; external-IdP trust establishment; portable replacement for the explicitly-banned Supabase Auth.

### IC-006 — AI Gateway
- **Business:** Whether AI is in MVP scope at all (D-02); which provider(s) first; per-tenant cost ownership/budget; permitted AI operations; data-residency constraints.
- **Technical:** Sync vs. queued execution; provider-abstraction boundary; structured-output contract; usage/cost metering storage; rate limits.
- **Architecture:** Provider-agnostic abstraction design and provider failover; where AI-related persistence lives; portable queue/async infrastructure.
- **Security:** **Highest data-egress risk.** PII redaction *before* data leaves the tenant boundary; provider-credential isolation (never exposed to clients); prompt-injection and output-safety handling; whether prompts/responses are logged (sensitive); which AI ops must emit lineage.

---

## C. Contract Priority Assessment (MVP)

| Contract | Priority | Rationale |
|---|---|---|
| **IC-005** Authentication Routing | **Critical** | Nothing can be served securely without auth + tenant routing; gates tenant isolation. |
| **IC-001** Global Startup | **Critical** | Platform cannot boot or discover tenants without it. |
| **IC-002** Tenant Startup | **Critical** | The multi-tenant physical-isolation core; every feature runs inside a tenant. |
| **IC-003** Import | **High** | Primary path for getting data into the system — core MVP value. Can launch with a single format. |
| **IC-004** Lineage | **Medium** | Valuable/differentiating; MVP can ship with a minimal record or defer queries. **D-08 resolved (configurable multi-regime, SOC 2 floor); IC-004 now fully specified (`Reviewed`).** |
| **IC-006** AI Gateway | **Low (MVP)** | **D-02 resolved — AI deferred to post-MVP.** Not required for v1; specify IC-006 later. Keep IC-004 lineage + tenant schema AI-ready now. |

---

## D. Recommended Completion Order

Order to **fully specify** the contracts. This follows dependencies and risk, not raw MVP priority — note where the two diverge.

1. **IC-005 — Authentication Routing.** Foundational, highest security risk, unblocks everyone, and is half of the now-resolved D-01 bootstrap cycle (A+B). Settle the identity model here first.
2. **IC-001 — Global Startup.** The other half of the D-01 cycle (resolved — A+B); fold the two-phase bootstrap into the spec, then finalize control-plane bring-up.
3. **IC-002 — Tenant Startup.** The multi-tenant core; depends on 005 + 001. Locks the tenant-id → physical-DB mapping that import, lineage, and AI all assume.
4. **IC-004 — Lineage.** Specify *before* its producers so IC-003 and IC-006 know exactly what to emit. **This is the key sequencing call:** IC-004 is only Medium MVP priority but precedes High-priority IC-003 in *specification* order because both depend on it. Implementation can still be staged later.
5. **IC-003 — Import.** Depends on 002, 004, 005; first real data-bearing feature.
6. **IC-006 — AI Gateway.** Depends on 002, 004, 005; highest data-egress risk. **D-02 resolved → post-MVP**, so IC-006 is specified after the MVP contracts.

**Specification progress (current):** all five MVP contracts (IC-001–IC-005) are **`Final`** (amended by the Approved post-freeze decisions **D-31, D-32**); **IC-006** remains `Draft` (post-MVP, D-02); **IC-007 (Deal Collaboration & Cross-Tenant Sharing)** is a `Deferred` future contract. **All MVP architecture decisions are resolved; the MVP architecture is frozen** (see [Architecture-Decision-Register.md](Architecture-Decision-Register.md)).

> **Spec order vs. implementation order:** finalize specs as above. Since AI is post-MVP (D-02 resolved), implementation runs 005 → 001 → 002 → 003 with a *minimal, AI-ready* IC-004 emitted alongside 003; full lineage queries and IC-006 follow post-MVP.

---

## E. Decision Register

Consolidated open questions requiring a **business (B)**, **architecture (A)**, **technical (T)**, or **security (S)** decision. "Blocking" lists what cannot be finalized until the decision is made. Items D-01 / D-02 are cross-cutting and should be decided first.

| ID | Decision needed | Type | Affects | Blocking |
|---|---|---|---|---|
| **D-01** | Resolve the Control-plane ⇄ Auth bootstrap cycle: how does the control plane authenticate before auth-routing metadata (in the Control DB) is available? | A, S | IC-001, IC-005 | ✅ **Resolved — A+B approved** ([addendum](D-01-Bootstrap-Cycle-Resolution.md)) |
| **D-02** | Is the AI Gateway in MVP scope, or post-MVP? | B | IC-006 | ✅ **Resolved — defer AI to post-MVP** ([register](Architecture-Decision-Register.md)) |
| **D-03** | Identity model: internal staff only, external customers, or B2B SSO? | B | IC-005, IC-002 | ✅ **Resolved — hybrid: internal identities + OIDC federation** |
| **D-04** | One tenant per principal, or multi-tenant-per-principal access? | B, S | IC-005, IC-002 | ✅ **Resolved — 1:N membership, exactly one active tenant per request** |
| **D-05** | Authentication scheme: JWT, OIDC/external IdP, or session? (portable; not Supabase Auth) | T, S | IC-005 | ✅ **Resolved — OIDC + stateless JWT (no session store)** |
| **D-06** | Where is the tenant identifier carried — subdomain, header, or token claim? | A, T | IC-005, IC-002 | ✅ **Resolved — signed claim authoritative + carrier-match enforcement** |
| **D-07** | Tenant-id → physical-database mapping: registry lookup, naming convention, or both? | A | IC-001, IC-002, IC-005 | ✅ **Resolved — registry-authoritative mapping** ([register](Architecture-Decision-Register.md)) |
| **D-08** | Compliance/regulatory driver for lineage (audit, GDPR, contractual)? Sets retention + immutability. | B | IC-004 | ✅ **Resolved — configurable multi-regime, SOC 2 floor + per-tenant params** (business/legal names the floor) |
| **D-09** | Platform-wide PII handling policy (sanitization at import; redaction before AI egress). | B, S | IC-003, IC-006 | ⏳ **Ingress ✅ Resolved (IC-003)** — policy-driven validate/sanitize/classify; **egress open (IC-006)** |
| **D-10** | Definition of "global ready" vs. "degraded" when Control DB is up but some tenant DBs are down. | A | IC-001 | ✅ **Resolved — three-state; degraded observability-only** |
| **D-11** | Tenant-registry enumeration: eager at startup or lazy on first request? | T | IC-001 | ✅ **Resolved — hybrid: warm working set + lazy load** |
| **D-12** | Control-DB schema-version mismatch detection and resolution. | T | IC-001 | ✅ **Resolved — compatible-range; fail-safe not-ready** |
| **D-13** | Per-tenant connection-pool strategy and scale ceiling (max tenants/connections). | A, T | IC-002 | ✅ **Resolved — lazy bounded per-tenant pools + LRU; portable pooler later** |
| **D-14** | Per-tenant DB credential storage and rotation. | S | IC-002 | ✅ **Resolved — pluggable reference-based secret abstraction** |
| **D-15** | Provisioning ownership: who creates the physical tenant DB (infra vs. app)? | A | IC-002, infrastructure | ✅ **Resolved — IaC + automated control-plane workflow; manual break-glass only** |
| **D-16** | Tenant readiness behavior on partial tenant-DB availability. | A | IC-002 | ✅ **Resolved — per-tenant independence; `degraded` observability-only** |
| **D-17** | Per-tenant schema migration coordination vs. global schema version. | T | IC-001, IC-002 | ✅ **Resolved — expand/contract rolling migrations + version-gated readiness** |
| **D-18** | Import source formats in scope for v1 (CSV, JSON, API pull, upload). | B | IC-003 | ✅ **Resolved — pluggable adapter; v1 = Global + CSV/JSON** |
| **D-19** | Import execution: synchronous or asynchronous, and how is progress reported? | T | IC-003 | ✅ **Resolved — hybrid: async-default + bounded sync fast-path** |
| **D-20** | Import idempotency-key strategy for safe re-import. | T | IC-003 | ✅ **Resolved — operation key + natural-key reconciliation** |
| **D-21** | Import partial-failure semantics: all-or-nothing vs. per-record. | A, T | IC-003 | ✅ **Resolved — batched/checkpointed atomic + resumable** |
| **D-22** | Minimum lineage record fields (source, actor, timestamp, operation, target). | T | IC-004 | ✅ **Resolved — minimal core + reference/code-only extension envelope** |
| **D-23** | Lineage append-only/immutability and its enforcement mechanism (DB- vs. app-level). | A, S | IC-004 | ✅ **Resolved — defense-in-depth: DB append-only + per-tenant hash-chaining** |
| **D-24** | Lineage retention period and archival tier. | B | IC-004 | ✅ **Resolved — per-tenant configurable retention within compliance floor/ceiling** |
| **D-25** | Must one provenance chain span import (IC-003) and AI (IC-006)? | A | IC-004, IC-003, IC-006 | ✅ **Resolved — unified per-tenant provenance graph + segmentable integrity chain** |
| **D-26** | First AI provider(s) and the provider-abstraction boundary. | A, T | IC-006 | IC-006 |
| **D-27** | AI execution: synchronous or queued/asynchronous (portable infra). | A, T | IC-006 | IC-006 |
| **D-28** | Per-tenant AI usage/cost metering, budgets, and where stored. | B, T | IC-006 | IC-006 |
| **D-29** | Which AI operations must emit lineage, and at what granularity? | A | IC-006, IC-004 | IC-006 |
| **D-30** | Cross-tenant isolation enforcement mechanism at routing time (defense-in-depth). | S, A | IC-005, IC-002 | ✅ **Resolved — defense-in-depth (authz + routing + per-tenant creds + audit)** |
| **D-31** | Global Directory residency — where do the Global Startup/Investor Directories reside? | A | IC-001, IC-003, IC-005 | ✅ **Approved — reside in the Control Database (Global Discovery Platform); directory schema under D-12; access via IC-005** |
| **D-32** | Role hierarchy & operating model (CONTROL, MASTER_AGENT, TENANT_ADMIN, TENANT_AGENT, STARTUP_USER, INVESTOR_USER). | A, S | IC-005, IC-002 | ✅ **Approved — roles (not permissions); MASTER_AGENT one-active-tenant; no cross-tenant superuser; cross-tenant → IC-007** |

**Resolved decisions (25 full + D-09 ingress + JWT lifecycle + D-31, D-32 Approved):** D-01–D-05 (foundational), D-06 + D-30 + JWT lifecycle (auth/routing finalization), D-07, D-13–D-17 (tenant infrastructure), D-08, D-22–D-25 (lineage), D-18–D-21 + D-09 ingress (import), D-10–D-12 (startup finalization), and **D-31, D-32 (post-freeze amendments)**. See [Architecture-Decision-Register.md](Architecture-Decision-Register.md) — the authoritative record.

**Still open (4 full + D-09 egress slice):** D-26–D-29 + D-09 **egress** — all **IC-006 AI, post-MVP** (deferred per D-02). **No open MVP architecture decisions remain.** **IC-007 (Deal Collaboration & Cross-Tenant Sharing)** is a Deferred future contract (cross-tenant; not in MVP). **D-08 has a standing business/legal action** (name the compliance floor regime) — its *architecture* is resolved.

---

## Tracked open divergence — **IC-012 M-2** (opened 2026-08-06, Gate A; **DEFERRED**)

**Status: OPEN and DEFERRED. IC-012 remains `Draft / Proposed` (IC-012-DRAFT-1). It is NOT marked Final.**

**The divergence.** Four artifacts assert absolutely that Edge 9 has no non-durable audit fallback;
the code has one.

| Cite | Text |
|---|---|
| `contracts/IC-012-…md` §11 | "There MUST be **no fallback** to an in-memory session provider, a lineage double, or a non-durable audit sink. … Degraded composition is prohibited, not merely discouraged." |
| `docs/Architecture-Decision-Register.md` — **D-44 item 7, ratified** | "there is no in-memory session-provider, lineage, or audit fallback." |
| `backend/deployment/import_edge.py` docstring | the same absolute assertion |
| **Against:** `backend/import_service/main.py` | returns `None` when `SP2_IMPORT_AUDIT_SINK_BASE_URL` is unset → passed through → `audit = audit or InMemoryAuditSink()` |
| **And:** `docs/runbooks/backend_service_startup_fastapi.md` §4 | documents that fallback as **intended** — "unset keeps the in-memory sink" — while §9 of the same file asserted the opposite absolutely (§9 is corrected under Gate A) |

**Disposition: DEFERRED.** Reconciliation is a prerequisite of IC-012 Final under §19. Reasons:

1. **Import is outside the controlled local MVP journey.** Stage 0 returned IMPORT-A and D-3 decided
   that Import is not exercised, DDL 014/015 stay out of scope, and the standing composition must not
   set `SP2_GW_IMPORT_BASE_URL`. `SP2_IMPORT_AUDIT_SINK_BASE_URL` must likewise remain UNSET. The
   standing launcher starts six edges and names neither the Import edge nor the import-audit ingest.
2. **Contract amendment is not a Gate-A change class.** Narrowing §11 would be an unauthorized
   widening of this arc.
3. **Narrowing §11 also falsifies a ratified ADR.** D-44 item 7 is Approved, and D-44 was approved
   *"subject to one **non-semantic** IC-012 §11 wording clarification"*. A second §11 edit that
   **relaxes a MUST** is emphatically semantic and cannot ride that ratification.
4. **The stronger fix has a hard live prerequisite.** Making Edge 9 fail closed instead requires DDL
   014/015 applied and the import-audit ingest edge standing; `control_import_audit` is **ABSENT**
   live, so failing closed today would make Edge 9 **unstartable** — a regression, not a fix. It also
   cannot live in the composition root: IC-012 §5 forbids the root from parsing a selector the owning
   service already parses.
5. **Nothing is presently harmed.** IC-012 is Draft / Proposed, production is DO-NOT-ACTIVATE, no
   standing Import path runs, and the behaviour is pre-existing and unchanged by PR #111.

**Tamper-evidence.** The §11 sentence and its "degraded composition is prohibited" clause are now
pinned verbatim as `_IC012_ANCHORS` entries in
`backend/tests/architecture/test_deployment_composition_root_boundaries.py`. A future *silent*
narrowing of the contract — which would make this divergence disappear without anyone deciding to —
turns the default suite red instead. Removing the anchor is itself the governed act.

**Note for the record — the existing in-memory guard gives false assurance.**
`test_native_uvicorn_factories.py` scans only names used *inside* `create_app_from_env`; the fallback
happens two frames down in `import_service/main.py`. Any future "we have a guard for that" claim about
Edge 9 and in-memory sinks is wrong as written.
