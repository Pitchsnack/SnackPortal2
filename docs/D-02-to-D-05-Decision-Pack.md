# Decision Pack — D-02 through D-05

**Type:** Architecture analysis only · **Phase:** Architecture Planning
**Status of affected contracts:** IC-001 and IC-005 are **Reviewed** (D-01 resolved & incorporated), **not Final**. These four decisions must be settled before finalization.
**Scope:** Analysis and recommendations only. No implementation, API, database, or infrastructure code.
**Date:** 2026-06-05 · See also: [Contract-Gap-Analysis.md](Contract-Gap-Analysis.md), [D-01-Bootstrap-Cycle-Resolution.md](D-01-Bootstrap-Cycle-Resolution.md)

## How these decisions relate

D-03 → D-04 → D-05 form a dependent chain: **who** authenticates (identity model) constrains **how many tenants** a principal may reach, which constrains the viable **auth scheme**. They should be decided in that order and kept mutually consistent (e.g. B2B federation ⇒ OIDC). **D-02 (AI in MVP)** is largely independent and primarily a product/scope call with a security tail (data egress). All four interact with already-registered decisions **D-14** (credential storage) and **D-30** (cross-tenant isolation enforcement).

---

# D-02 — AI in MVP

### 1. Decision description
Is the AI Gateway (IC-006) in scope for the MVP, or deferred to a later release?

### 2. Why it matters
It sets MVP scope, timeline, and the platform's **largest data-egress security surface** (tenant data leaving the isolation boundary to an external provider). If AI ships in v1, IC-006 must be finalized and IC-004 (Lineage) must capture AI-driven changes from day one; provider abstraction and possibly async/queue infrastructure become launch requirements.

### 3. Available options
- **Option 1 — AI in MVP:** IC-006 is a v1 feature.
- **Option 2 — AI post-MVP:** defer IC-006; ship multi-tenant core + import first.
- **Option 3 — Thin slice in MVP:** a single-provider, synchronous, assistive capability behind a per-tenant feature flag, with full multi-provider abstraction deferred (but the abstraction boundary still defined).

### 4. Pros and cons
| Option | Pros | Cons |
|---|---|---|
| 1 — In MVP | Ships the differentiator early; forces egress controls + lineage to be designed properly up front | Largest scope; highest egress risk at launch; needs provider abstraction + cost/budget controls immediately |
| 2 — Post-MVP | Smallest, fastest, safest MVP; defers egress risk; lets core + import stabilize | Delays differentiator; risk core/lineage decisions don't anticipate AI unless designed AI-ready |
| 3 — Thin slice | Demonstrates value with bounded risk; flagged per-tenant rollout | Still incurs redaction/egress design; scope-creep risk; lock-in debt if abstraction is skipped |

### 5. Impact on IC-001
Minimal. AI is tenant-scoped and control-plane-agnostic, so **no Phase-0 impact**. If AI ships in MVP, Phase-1 readiness *may* include verifying AI Gateway/provider-credential availability — otherwise none.

### 6. Impact on IC-005
Low/indirect. AI calls authenticate via the normal **Phase-1** model and must already carry tenant context; no new scheme and no change to the two-phase model.

### 7. Impact on physical multi-database architecture
AI-driven writes target only the resolved tenant DB via the Database Router; AI usage/cost metering is per-tenant (cross-tenant aggregation, if needed, belongs in the Control DB — a design choice). No shared multi-tenant AI table. **Key tension:** physical isolation does **not** protect data once it egresses to an external provider — redaction at the tenant boundary is required regardless of which option is chosen.

### 8. Recommended option
**Option 2 (defer to post-MVP) as the default**, *unless* AI is the explicit headline value proposition — in which case **Option 3 (thin slice)** with strict provider abstraction and boundary redaction. In **either** case, design IC-004 lineage and the tenant schema to be **AI-ready now** so adding IC-006 later is non-breaking. Switch from 2 → 3 only on an explicit product decision that AI is core to launch.

### 9. Open risks
Deferring risks retrofitting lineage/egress controls later; including risks PII egress, cost overruns, and provider lock-in. This is fundamentally a **product/business** call (is AI core?) with architecture consequences — it should not be decided implicitly by engineering.

---

# D-03 — Identity Model

### 1. Decision description
Who are the principals the platform authenticates: internal staff/operators only, external end customers directly, or B2B organizations that bring their own SSO/IdP?

### 2. Why it matters
It is the defining input to Phase-1 authentication in IC-005: it sets the principal population, the principal↔tenant relationship, whether federation is required, onboarding/offboarding, and the attack surface. It directly constrains D-04 and D-05.

### 3. Available options
- **Option A — Internal-only:** principals are internal staff/operators; tenants are managed on customers' behalf (no customer login).
- **Option B — External customers (direct):** end customers log in; the platform owns the identity/credential store.
- **Option C — B2B / federated SSO:** each tenant is an organization that brings its own OIDC/SAML IdP; the platform federates.

### 4. Pros and cons
| Option | Pros | Cons |
|---|---|---|
| A — Internal-only | Smallest surface; simplest; fastest MVP | No customer self-service; likely needs to evolve to B/C later (migration cost) |
| B — External direct | Enables self-service SaaS; platform controls UX | Platform now owns credentials (MFA, reset, compliance burden); larger surface; partial lock-in risk if tied to a managed auth service |
| C — B2B federated | Enterprise-friendly; offloads credential management; clean per-tenant org model | Most complex; per-tenant IdP config; federation + first-user bootstrap per tenant |

### 5. Impact on IC-001
Low directly. The Phase-0 **bootstrap system identity is internal/system regardless** of the end-user model, so D-01's resolution is unaffected. If Option C, the Control DB stores per-tenant IdP configuration, loaded at/after the Phase-1 transition.

### 6. Impact on IC-005
**High — this is the defining input.** Internal-only ⇒ simple internal auth; External ⇒ platform-owned credential flows; B2B ⇒ federation, per-tenant IdP trust, issuer/audience validation, and mapping a federated identity to (tenant, principal). It also determines how tenant context is derived (token claim vs. subdomain).

### 7. Impact on physical multi-database architecture
**Option C maps most cleanly:** one organization = one tenant DB, with per-tenant IdP config in the Control DB. **Internal-only** means cross-tenant operators — high-privilege principals whose every request must be explicitly routed and isolation-checked (higher cross-tenant risk). **External direct** requires a principal→tenant mapping in the Control DB and strict prevention of reaching another tenant's DB.

### 8. Recommended option
**Architect for Option C (B2B federated), optionally as a hybrid with internal/system operators.** Federation avoids owning credentials and aligns with the per-tenant physical-DB and anti-lock-in goals. If MVP must be lean, **start internal-only (A) but design IC-005 so federation slots in without rework.** Avoid Option B (platform-owned password store) unless the product genuinely requires direct consumer login.

### 9. Open risks
Picking internal-only now and needing customer login later is costly; Option B carries compliance/security burden and partial lock-in; federation adds complexity and a per-tenant first-admin bootstrap (a tenant-scoped echo of D-01). Must stay consistent with D-04 and D-05.

---

# D-04 — Tenant-per-Principal Model

### 1. Decision description
May one authenticated principal access exactly one tenant, or many — and if many, one-at-a-time per session or concurrently within a single session?

### 2. Why it matters
It governs tenant-context establishment and routing in IC-005, the strength of isolation guarantees, and the blast radius of any auth/routing bug. Concurrent multi-tenant access dramatically raises cross-tenant exposure risk.

### 3. Available options
- **Option A — Strict 1:1:** a principal belongs to exactly one tenant.
- **Option B — 1:N, one-at-a-time:** a principal may belong to many tenants but a session is scoped to one; switching re-scopes the session.
- **Option C — Concurrent multi-tenant:** a principal acts across multiple tenants within one session without re-scoping.

### 4. Pros and cons
| Option | Pros | Cons |
|---|---|---|
| A — Strict 1:1 | Strongest isolation; simplest routing (tenant implied); maps cleanly to physical-per-tenant DB | No multi-org users; operators need separate accounts per tenant |
| B — 1:N one-at-a-time | Supports multi-org users/operators while each request stays single-tenant; explicit selection | Session re-scoping complexity; tenant switch is a sensitive operation; stale-context risk |
| C — Concurrent | Powerful for cross-tenant ops/reporting | Highest leakage risk; breaks the per-request single-tenant invariant; hard to audit |

### 5. Impact on IC-001
Low. Control-plane operators act in Phase 0 / control-plane scope and never perform tenant routing. Even if C were allowed at runtime, the risk lives in IC-005 routing, not in startup; the tenant registry merely enumerates.

### 6. Impact on IC-005
**High.** Option A derives tenant from the principal; B and C require explicit tenant selection with re-validation on every request. IC-005's invariant — *resolve to exactly one tenant DB, never spanning* — is naturally satisfied by A and B; **C violates the per-request single-tenant assumption** unless every operation is explicitly tenant-tagged and still routed one DB at a time.

### 7. Impact on physical multi-database architecture
**This is the critical alignment point.** The architecture's invariant is "one request → Control DB or exactly one tenant DB, never spanning." A and B preserve it per request. **C threatens it** — concurrent cross-tenant access either degenerates to sequential single-tenant routing (fine) or demands a forbidden cross-DB operation (not fine). Any cross-tenant reporting must be done via the control plane as explicit, audited, per-tenant queries — never a spanning query.

### 8. Recommended option
**Option B — one tenant per session with explicit switching; principals may belong to many.** It preserves the per-request single-tenant isolation invariant (compatible with physical multi-DB) while supporting operators and multi-org users. **Forbid Option C for tenant data operations** (now and likely permanently). Option A is acceptable only if the product truly has no multi-org users; B is the safe superset.

### 9. Open risks
Tenant-switch as a leak vector (stale context, pooled connections bound to the wrong tenant); many-tenant operator accounts as high-value targets; the standing temptation to add C "for convenience" and erode isolation. Ties to D-03 (operators/B2B) and **D-30** (cross-tenant isolation enforcement).

---

# D-05 — Authentication Scheme

### 1. Decision description
Which concrete **Phase-1** authentication scheme does IC-005 adopt: self-issued JWT, OIDC via an external/self-hosted IdP, or server-side sessions? (Portable; explicitly **not** Supabase Auth.)

### 2. Why it matters
It is the mechanism behind the entire Phase-1 model: how principals prove identity, how tenant context is carried, statelessness vs. server state, token lifetime/revocation, and portability. It must remain consistent with D-03 (who logs in) and D-04 (one/many tenants).

### 3. Available options
- **Option A — Self-issued JWT:** the platform issues and validates signed tokens; stateless validation via a signing key.
- **Option B — OIDC via external/self-hosted IdP:** the platform validates IdP-issued tokens via JWKS; federation-ready.
- **Option C — Server-side sessions:** opaque session id backed by a server/Control-DB session store.

### 4. Pros and cons
| Option | Pros | Cons |
|---|---|---|
| A — Self-issued JWT | Stateless, DB-free validation; scalable; tenant context as a claim | Hard revocation (needs short TTL + refresh/denylist); platform owns key rotation **and** credential verification unless paired with an IdP |
| B — OIDC IdP | Federation/SSO-ready (fits D-03 C); DB-free JWKS validation; standards-based and portable | Adds an IdP as an operational dependency with its own availability/bootstrap; per-tenant IdP config for multi-org |
| C — Server-side sessions | Easy revocation; opaque tokens; mature pattern | **Stateful** — a session store dependency; if stored in the Control DB it re-couples auth to the Control DB (fights the D-01 resolution); weaker multi-region story |

### 5. Impact on IC-001
**Medium.** A and B keep authentication **DB-free**, preserving the Phase-0/Phase-1 separation that resolved D-01 — strongly preferred. Option **C with a Control-DB-backed session store re-tangles runtime auth with the Control DB**, partially undoing D-01 (Phase 0 must still use the system identity, never sessions).

### 6. Impact on IC-005
This is the core mechanism IC-005 will specify: token format, validation, where tenant context lives (claim vs. server session), refresh/revocation. **B aligns with D-03 Option C** (federation); **A aligns with internal/direct**; **C changes the statelessness assumption** the rest of the design leans on.

### 7. Impact on physical multi-database architecture
Authentication must not require a tenant-DB lookup (it precedes routing). **Stateless A/B keep validation independent of any DB**, and tenant context travels as a signed claim that the Database Router uses to select the tenant DB. A session store (C) cannot live in tenant DBs (which tenant, pre-auth?), so it would live in the Control DB — making auth depend on Control-DB availability, in tension with D-01. **Strong architectural argument for stateless A/B.**

### 8. Recommended option
**Option B (OIDC via a portable, self-hostable IdP) as the strategic target** — stateless (preserves the D-01 separation), federation/SSO-ready (fits D-03), standards-based and portable, and avoids the platform owning credentials. If MVP lands internal-only, **start with self-issued JWT (A), designed to be swappable for OIDC.** **Avoid Control-DB-backed sessions (C).** Either A or B carries tenant context as a signed claim. Explicitly **not** Supabase Auth.

### 9. Open risks
Key/JWKS rotation and a revocation strategy (short TTL + refresh); if B, the IdP's own availability and first-admin bootstrap (a mini-D-01) and per-tenant federation config; **tenant-claim integrity** — a forged or swapped tenant claim must be impossible, which requires signature verification **plus** a server-side authorization check at routing time (**D-30**). Ties to D-03, D-04, D-14, D-30.

---

## Consolidated recommendations (at a glance)

| ID | Decision | Recommended | Primary driver |
|---|---|---|---|
| D-02 | AI in MVP | **Defer (Option 2)** unless AI is the headline feature → then **thin slice (3)**; design lineage/schema AI-ready now | Scope + egress risk |
| D-03 | Identity model | **Architect for B2B federated (C)**, hybrid with internal operators; lean MVP may start internal-only (A) | Fits per-tenant DB + anti-lock-in |
| D-04 | Tenant-per-principal | **One-at-a-time, 1:N (Option B)**; forbid concurrent multi-tenant (C) for data | Preserves single-tenant-per-request invariant |
| D-05 | Auth scheme | **OIDC self-hostable IdP (B)** target; **self-issued JWT (A)** acceptable interim; avoid sessions (C) | Stateless, preserves D-01, portable |

**Suggested decision order:** D-03 → D-04 → D-05 (dependent chain), then D-02 independently. Consistency rule: if D-03 = B2B federated, D-05 should be OIDC (B); if D-03 = internal-only, D-05 may be self-issued JWT (A) as an interim.
