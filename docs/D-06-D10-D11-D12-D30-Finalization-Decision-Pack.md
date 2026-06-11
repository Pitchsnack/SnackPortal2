# Decision Pack — Finalization (D-06, D-10, D-11, D-12, D-30 + JWT Lifecycle)

**Type:** Architecture analysis only · **Phase:** Architecture Planning
**Purpose:** Resolve the remaining MVP architecture decisions required to move **IC-001** and **IC-005** from **Reviewed → Final**.
**Scope:** Analysis and recommendations only. No implementation code, schema, migrations, services, or infrastructure code.
**Date:** 2026-06-05 · See also: [IC-001](../contracts/IC-001-Global-Startup-Contract.md), [IC-005](../contracts/IC-005-Authentication-Routing-Contract.md), [Architecture-Decision-Register.md](Architecture-Decision-Register.md)

## Binding constraints (apply to every option below)
- **One request → one active tenant → one database**; **physical tenant isolation is non-negotiable**.
- **Registry-authoritative routing** (D-07); **OIDC + stateless JWT** (D-05); **no session store**; **no shared tenant databases**.
- **No Supabase Auth**; **no vendor-specific identity systems**; **cloud-portable** and **PostgreSQL-portable only**.

Any option breaching these is out of contract regardless of other merits.

## How these decisions relate
Two clusters. **IC-001 readiness cluster:** D-12 (Control-DB schema compatibility) and D-11 (registry enumeration) are inputs that compose into D-10 (global ready vs degraded). **IC-005 auth/routing cluster:** D-06 (tenant carriage) feeds D-30 (isolation enforcement) and the JWT lifecycle (a tenant switch issues a new token). **D-30 is the capstone**, binding D-04, D-05, D-06, D-07, D-13, D-14. Suggested order: **D-12 → D-11 → D-10**, then **D-06 → JWT lifecycle → D-30**.

---

# D-06 — Tenant Identifier Carriage

### 1. Description
How the tenant identifier is carried on a request so IC-005 can establish the single active tenant context and route to the correct tenant database — subdomain (host), HTTP header, or a signed JWT claim.

### 2. Why it matters
This determines the active tenant for **every** request and is the linchpin of routing and isolation. A spoofable or ambiguous carrier could route a request to the wrong tenant DB — the highest-severity isolation breach. It must be consistent with stateless JWT (D-05), one-active-tenant-per-request (D-04), and registry-authoritative routing (D-07).

### 3. Available options
- **A — Signed JWT claim:** tenant id is a claim inside the validated token (integrity-protected by signature).
- **B — HTTP header** (e.g., `X-Tenant-Id`): explicit, separate from the token.
- **C — Subdomain / host:** tenant encoded in the hostname.
- **D — Hybrid:** subdomain/header for addressing/UX, but the **signed claim is authoritative** and must match; mismatches rejected.

### 4. Pros
- **A:** tamper-evident; travels with auth; stateless; binds tenant to the authenticated principal.
- **B:** simple; any client; easy 1:N switching (D-04).
- **C:** clean per-tenant URLs; origin/cookie separation; B2B/branding fit.
- **D:** UX of subdomain/header **plus** claim authority; defense-in-depth (carrier must match claim).

### 5. Cons
- **A:** switching the active tenant (1:N) needs a new token scoped to that tenant; tenant not visible in URL.
- **B:** a header alone is attacker-controlled; **must** be cross-checked against authorized membership — cannot be the sole authority.
- **C:** host is also attacker-controllable unless verified against the token; per-tenant DNS/cert (wildcard helps); harder 1:N switching.
- **D:** must reconcile two places and define precedence.

### 6. Impact on IC-001
Minimal — carriage is a Phase-1 concern. IC-001 brings online the Control-DB registry (D-07) that the carried id resolves against; the control plane itself is addressed distinctly (no tenant).

### 7. Impact on IC-005
Core to tenant-context establishment. IC-005 MUST (a) extract the candidate tenant from the carrier, (b) verify the principal is an authorized member (D-04), and (c) ensure exactly one active tenant. With a signed claim, integrity is intrinsic; with header/subdomain, IC-005 MUST authorize and reject mismatches. Ties D-30.

### 8. Impact on Physical Multi-Database Architecture
The carried-and-authorized tenant id is what the Database Router resolves (registry-authoritative, D-07) to exactly one tenant DB. Carrier integrity directly protects one-request→one-DB; a spoofable sole-carrier is an isolation risk.

### 9. Security implications
The carrier MUST be integrity-protected or authorization-checked. A signed claim is tamper-evident; a header/subdomain alone is attacker-controlled and MUST never be trusted without verifying membership and matching a signed claim. This blocks the "valid token + swapped tenant header/host" attack — the key cross-tenant vector.

### 10. Recommendation
**Option D (hybrid) with the signed JWT claim authoritative.** Tenant id is carried as a **signed claim** (source of truth); a subdomain and/or header MAY be used for addressing but MUST match the claim, and IC-005 MUST reject mismatches and verify membership (D-04) before routing. A 1:N tenant switch issues a **new token scoped to the new active tenant** (stateless; no session store).

### 11. Open risks
Token re-issue on switch (UX/latency for 1:N; audited); wildcard cert/DNS if subdomains used; ensuring **every** path enforces the claim-vs-carrier match (no bypass). Ties D-04, D-30, JWT lifecycle.

---

# D-10 — Global Ready vs Degraded

### 1. Description
The platform-level readiness states at the global/control-plane level — what *ready*, *degraded*, and *not-ready* mean — given per-tenant independence is already settled (D-16).

### 2. Why it matters
Drives platform health signaling, load-balancer/orchestrator behavior, and alerting, and sets the boundary between "a tenant is down" (normal, D-16) and "the platform is down" (Control DB / Phase-0). Wrong definitions cause false outages or masked failures.

### 3. Available options
- **A — Binary** (ready / not-ready): ready iff Control DB up + Phase-1; per-tenant handled separately (D-16).
- **B — Three-state** (ready / degraded / not-ready): degraded = still serving healthy tenants but impaired.
- **C — Multi-dimensional:** separate control-plane, registry, and aggregate tenant-fleet signals, composed by consumers.

### 4. Pros
- **A:** simplest; unambiguous for load balancers.
- **B:** operational nuance/early warning while still serving; matches IC-001's existing "degraded" wording and D-16's degraded-as-observability.
- **C:** richest; different consumers (LB vs ops vs router) react appropriately; cleanly separates control-plane vs fleet health.

### 5. Cons
- **A:** hides partial impairment; coarse.
- **B:** must define "degraded" so it **never** rejects healthy tenants; threshold tuning.
- **C:** most complex; consumers must compose consistently.

### 6. Impact on IC-001
Finalizes IC-001's readiness semantics and the Phase-0/Phase-1 gate: **ready** = Phase-1 + Control DB healthy + schema compatible (D-12); **degraded** = serving but impaired (elevated tenant-DB failures or a non-critical control-plane dependency down); **not-ready** = Phase-0 / Control DB down / schema-incompatible (D-12). Integrates with D-11 and D-12.

### 7. Impact on IC-005
Routing needs the Control DB up (Phase-1) to resolve routing metadata. Global **not-ready** (Control DB down) is the legitimate global-down case (D-16). **Degraded MUST NOT cause IC-005 to refuse healthy-tenant routing.**

### 8. Impact on Physical Multi-Database Architecture
Reinforces D-16: tenant-DB outages = per-tenant not-ready, **never** global not-ready. Global not-ready is reserved for shared-dependency (Control DB / Phase-0) failure; the aggregate "degraded" is observability-only and never denies healthy tenants.

### 9. Security implications
Readiness endpoints can leak tenant counts / which tenants are down — must be **access-controlled and minimally disclosing** (IC-001's "who may observe readiness"). Degraded signals must not reveal sensitive topology to unauthenticated callers.

### 10. Recommendation
**Option B (three-state) composed from Option C's underlying dimensions.** Define ready / degraded / not-ready as above; **degraded is observability-only and never gates healthy-tenant routing** (consistent with D-16); expose minimal, access-controlled readiness.

### 11. Open risks
Degraded thresholds (hysteresis to avoid flapping); ensuring degraded never gates healthy tenants; readiness-endpoint information disclosure; orchestrator/LB mapping (degraded → still receive traffic). Ties D-16, D-11, D-12.

---

# D-11 — Registry Enumeration Strategy

### 1. Description
How/when the platform enumerates the tenant registry (which tenant DBs exist) — eagerly at startup (IC-001) or lazily on first request — under registry-authoritative routing (D-07) and potentially many tenants.

### 2. Why it matters
Affects startup time, memory, scale to large fleets, routing-data freshness, and how new/removed tenants are picked up. Eager enumeration of thousands of tenants slows startup; lazy risks first-request latency and staleness handling.

### 3. Available options
- **A — Eager:** enumerate the full registry at startup; cache all routing metadata.
- **B — Lazy:** resolve a tenant's metadata on first request, cache thereafter with TTL/invalidation.
- **C — Hybrid:** warm a bounded working set at startup; lazy-load the rest on demand; background refresh.

### 4. Pros
- **A:** simplest routing path (all in memory); no first-request penalty; validate all at startup.
- **B:** fast startup regardless of tenant count; scales to very large fleets; low memory.
- **C:** fast startup + warm common path; bounded memory; resilient.

### 5. Cons
- **A:** slow startup at scale; high memory; still needs runtime invalidation anyway; impractical for huge fleets.
- **B:** first-request latency; must distinguish "unknown" vs "not-yet-loaded"; invalidation on re-association (D-07) is critical; cold-start thundering herd.
- **C:** more complex; working-set policy; two code paths.

### 6. Impact on IC-001
Finalizes IC-001's startup behavior and the readiness definition: with lazy/hybrid, **ready = registry reachable, not fully enumerated** (feeds D-10). Ties D-12.

### 7. Impact on IC-005
The Database Router (D-07) consumes routing metadata; the strategy determines whether resolution is always in-cache (eager) or sometimes a registry lookup (lazy/hybrid). Routing MUST stay registry-authoritative with **invalidation on re-association** (consistency with IC-002's `ReassociateDatabase`).

### 8. Impact on Physical Multi-Database Architecture
With many physical tenant DBs, lazy/hybrid is the scalable model. Resolution must always be registry-authoritative (D-07), tenant-scoped, and invalidated so a relocated tenant DB is never routed stale (a correctness/isolation risk). One-request→one-DB is unaffected by strategy.

### 9. Security implications
Caching/enumeration must not leak tenant existence: a cold-load of an unknown tenant must be indistinguishable from known-but-unauthorized (consistent *not found* / *forbidden*, IC-002). **Stale cache → wrong-DB routing → isolation risk**, so invalidation is security-relevant.

### 10. Recommendation
**Option C (hybrid):** warm a bounded working set at startup; lazy-load the rest; background refresh; registry-authoritative with **mandatory tenant-scoped invalidation on re-association** (D-07 / IC-002). Scales to large fleets and keeps startup fast.

### 11. Open risks
Working-set policy (LRU / active tenants); cache TTL + invalidation correctness (stale = wrong DB); cold-start thundering herd; consistent unknown-vs-unauthorized semantics; memory bounds. Ties D-07, D-10, D-13.

---

# D-12 — Control-DB Schema-Version Mismatch

### 1. Description
How the platform detects and resolves a mismatch between the code's expected **Control-DB** schema version and the actual Control-DB schema, at startup and runtime. (Tenant-DB schema is D-17; this is the Control DB.)

### 2. Why it matters
The Control DB holds routing metadata, the tenant registry, federation config (D-03), and audit. If code and Control-DB schema disagree, routing/auth can misbehave catastrophically. The platform must **fail safe** and integrate with the Phase-0/Phase-1 bootstrap (D-01) and global readiness (D-10).

### 3. Available options
- **A — Strict exact-match:** require an exact Control-DB version; any mismatch → refuse to serve (not-ready).
- **B — Compatible-range (expand/contract):** code declares a supported Control-DB schema range; within range → ready; outside → not-ready. (Mirrors D-17, applied to the Control DB.)
- **C — Auto-migrate on startup:** the platform migrates the Control DB to the expected version at startup.

### 4. Pros
- **A:** simplest correctness guarantee; no ambiguity.
- **B:** enables zero-downtime rolling deploys of the control plane (old+new coexist during Control-DB migration); consistent with D-17; portable.
- **C:** convenient; self-healing.

### 5. Cons
- **A:** forces lockstep deploy + migration → downtime; brittle for an HA/multi-instance control plane.
- **B:** code must support a Control-DB schema range (expand/contract discipline); define floor/ceiling.
- **C:** **dangerous** — implicit DDL on the shared Control DB at startup, multi-instance races, rollback risk; migration should be a controlled, audited step, not a startup side effect.

### 6. Impact on IC-001
Finalizes IC-001's Control-DB schema check in the startup ordering: detected during Phase-1 bring-up (after the Control DB is reachable); on incompatibility → remain **not-ready** (D-10) and do not serve routing. A **check**, not an auto-migration. Ties D-01, D-10.

### 7. Impact on IC-005
IC-005 depends on Control-DB-resident routing/federation metadata; an incompatible schema means that data may be misread → IC-005 MUST NOT serve tenant routing until compatibility is confirmed. Stateless JWT **validation** (D-05) is DB-free and could still work, but **routing** gates on Control-DB compatibility.

### 8. Impact on Physical Multi-Database Architecture
The Control DB is the single global dependency; its schema compatibility gates **global** readiness (D-10), independent of tenant DBs (D-17 governs those). A Control-DB mismatch is a global not-ready condition, distinct from per-tenant issues.

### 9. Security implications
Serving with a mismatched Control-DB schema risks misrouting (wrong tenant DB) or misreading federation/auth config — isolation/auth failures. **Fail-safe (refuse) is the secure default.** Implicit auto-migrate (C) risks an attacker-influenced or buggy migration corrupting routing — avoid as implicit behavior.

### 10. Recommendation
**Option B (compatible-range, expand/contract) for the Control DB** — detect at startup **and** runtime; serve only within the supported range; outside → global not-ready (D-10). Migrations are a **controlled, audited, separate step** (explicitly **not** implicit at startup — reject Option C as implicit). Enables zero-downtime control-plane rolling deploys while failing safe.

### 11. Open risks
Control-DB backward-compatibility discipline; defining the supported range; multi-instance agreement on compatibility; never making migration an implicit startup side effect; runtime detection (not just startup). Ties D-01, D-10, D-17, D-11.

---

# D-30 — Cross-Tenant Isolation Enforcement

### 1. Description
The defense-in-depth mechanism that guarantees a request can **never** reach another tenant's database — across authentication/authorization, routing, and the data layer. The capstone protecting the core invariant.

### 2. Why it matters
Physical isolation is non-negotiable; this defines **how it is guaranteed in depth** so a bug or compromise at one layer cannot breach isolation. It is the highest-severity security property of the platform.

### 3. Available options (layers; the real choice is how many to combine)
- **A — Authorization-only:** IC-005 checks membership (D-04) and resolves the tenant; trust the router.
- **B — Routing-enforced:** the Database Router (D-07) binds the connection to exactly the resolved tenant DB; one active tenant per request.
- **C — Data-layer enforced:** per-tenant DB credentials (D-14) so a connection physically cannot reach another tenant's DB (separate DBs + separate creds).
- **D — Defense-in-depth:** all of the above + continuous audit/anomaly detection.

### 4. Pros
- **A:** simple.
- **B:** enforces one-request-one-DB at the router; catches authz gaps.
- **C:** strongest single guarantee — physical separation + distinct credentials means a buggy/leaked query cannot cross DBs.
- **D:** no single point of failure; a bug at one layer is caught by another; auditable; matches non-negotiable isolation.

### 5. Cons
- **A:** single point of failure (one authz bug = breach); insufficient.
- **B:** still relies on correct tenant resolution; needs the data layer behind it.
- **C:** relies on correct per-request credential selection (D-14); pooling (D-13) must never reuse a connection across tenants.
- **D:** most to build/verify; per-request overhead; complexity.

### 6. Impact on IC-001
Minor — the control plane is the global scope, but IC-001 must ensure the Phase-0 system identity can **never** resolve a tenant DB (already specified), and control-plane credentials are separated from per-tenant credentials (D-14).

### 7. Impact on IC-005
IC-005 owns the first layers: authenticate (D-05), authorize the tenant claim against membership (D-04/D-06), and route to exactly one tenant DB (D-07). D-30 makes IC-005 **enforce — not assume** — single-tenant binding and reject claim/carrier mismatches (D-06). This is IC-005's highest-severity requirement.

### 8. Impact on Physical Multi-Database Architecture
This operationalizes physical isolation: separate tenant DBs (no shared DB) + per-tenant credentials (D-14) + registry-authoritative routing (D-07) + per-tenant pools that never cross tenants (D-13). Physical separation is the **last line of defense** — even a routing bug cannot cross into another DB when credentials are per-tenant and DBs are separate. No cross-tenant joins/spanning queries — ever.

### 9. Security implications
The core guarantee: (1) a forged/swapped tenant claim is rejected (signature + membership, D-06); (2) the router binds one tenant per request; (3) per-tenant credentials make cross-DB access physically impossible; (4) pools never reuse across tenants (D-13); (5) cross-tenant-adjacent events are audited/anomaly-detected. No single bug breaches isolation.

### 10. Recommendation
**Option D — defense-in-depth across all four layers**, mandated as IC-005's isolation contract: **AuthN/AuthZ** (D-05 + signed tenant claim D-06 + membership D-04; reject mismatches) → **Routing** (one resolved tenant DB per request, D-07; enforced not assumed) → **Physical/data layer** (separate DBs + per-tenant credentials D-14; no cross-tenant connection reuse D-13) → **Audit/detection** (tenant switches and cross-tenant-adjacent attempts audited). No cross-tenant joins/spanning queries — ever.

### 11. Open risks
Per-request authz/credential overhead (perf); **pool-reuse bugs (D-13) — the subtle isolation hazard**; ensuring no path bypasses the router (no hardcoded DBs, D-07); credential-selection correctness (D-14); audit/anomaly tuning; the "valid token, swapped carrier" attack (D-06 mismatch rejection). Ties D-04, D-05, D-06, D-07, D-13, D-14.

---

# JWT Lifecycle — TTL, Refresh, Key Rotation, Revocation

### 1. Description
The access-token **TTL**, **refresh** mechanism, signing-**key rotation**, and **revocation** strategy for the OIDC stateless model (D-05) — with **no server-side session store** and **no Control-DB session dependency**.

### 2. Why it matters
TTL/refresh trade security (short-lived = smaller breach window) against UX/IdP load. Key rotation is essential hygiene. **Revocation is the hard part:** stateless JWTs cannot be "deleted" like sessions, so exposure must be bounded by short TTLs + IdP-side refresh revocation (with an optional minimal denylist). It also interacts with D-06 (a tenant switch issues a new token) and D-30 (a revoked/invalid token must not route).

### 3. Available options (by sub-topic)
- **TTL:** (a) long-lived (hours); (b) **short-lived (minutes) + refresh**.
- **Refresh:** **OIDC refresh tokens managed at the IdP** (stateless for the resource server) — no platform session store.
- **Key rotation:** **JWKS with `kid` + overlap window** (standard OIDC; zero-downtime).
- **Revocation:** (a) pure short-TTL (wait out expiry); (b) short-TTL + **refresh-token revocation at the IdP**; (c) optional **bounded, short-lived control-plane denylist by `jti`** for emergency immediate revocation.

### 4. Pros
- **Short TTL:** small breach window; revocation largely solved by expiry.
- **IdP refresh:** standard; stateless for the resource server; no platform session store.
- **JWKS/`kid` + overlap:** zero-downtime rotation; standard; portable across any OIDC IdP.
- **IdP refresh-revocation:** revoking the refresh token cuts future access with no platform state.
- **Optional denylist:** immediate revocation for emergencies.

### 5. Cons
- **Short TTL:** more refresh traffic (IdP load); clients must handle refresh.
- **Pure-TTL revocation:** a stolen access token is valid until expiry (bounded by a short TTL).
- **Denylist:** reintroduces shared state (the thing D-05 avoided) — must be minimal, optional, control-plane-scoped, portable; replication/staleness.
- **IdP refresh dependency:** the IdP must be available for refresh (a Phase-1 dependency, not Phase-0).

### 6. Impact on IC-001
None/minimal — JWT lifecycle is Phase-1 runtime auth. The Phase-0 system identity (D-01) uses the static trust anchor, separate from end-user JWT lifecycle. Signing-key / JWKS material is referenced via the D-14 abstraction, never embedded in tokens.

### 7. Impact on IC-005
Finalizes IC-005's token model: short-lived access tokens validated statelessly via JWKS (`kid`), refreshed at the IdP, keys rotated with overlap, revocation via short-TTL + IdP refresh revocation (optional bounded control-plane denylist for emergencies — minimal, **not** a session store). A tenant switch (D-06/D-04) obtains a new tenant-scoped token. A revoked/expired/invalid token MUST NOT route (D-30).

### 8. Impact on Physical Multi-Database Architecture
JWT validation is **DB-free** — no tenant DB or session store is consulted to validate, preserving the D-01 separation and D-05 statelessness. Any optional denylist is **control-plane-scoped** (never per-tenant, never a tenant DB), preserving isolation and the no-shared-tenant-DB rule. Routing happens only after valid auth + authorization.

### 9. Security implications
Short TTL bounds stolen-token exposure; JWKS rotation limits key-compromise blast radius; IdP refresh-revocation cuts access; the optional denylist covers the inherent "revoke now" gap of stateless JWTs. Validation MUST be strict: `iss`/`aud`/`exp`/`kid`, reject algorithm-confusion, and bind the tenant claim (D-06) to prevent cross-tenant token misuse (D-30). No secrets in tokens.

### 10. Recommendation
- **TTL:** short-lived access tokens (target band ~5–15 minutes; the exact value is operational tuning, not architecture).
- **Refresh:** OIDC refresh tokens managed at the IdP (no platform session store); silent refresh.
- **Key rotation:** JWKS with `kid` and an overlap window (zero-downtime); keys sourced via the D-14 abstraction; any OIDC-standard, self-hostable IdP (no Supabase Auth, no vendor lock-in).
- **Revocation:** primary = short-TTL + refresh-token revocation at the IdP; **optional** bounded, short-lived **control-plane** denylist (by `jti`, expiring at access-TTL) for emergency immediate revocation — explicitly **not** a session store and never per-tenant.

### 11. Open risks
Exact TTL (security vs IdP load); the optional denylist reintroducing shared state (keep minimal/optional/portable); IdP availability for refresh (Phase-1 dependency); strict validation (alg/iss/aud/exp/kid; alg-confusion); tenant-claim binding (D-06/D-30); clock skew. Ties D-05, D-06, D-30, D-14.

---

## Consolidated recommendations (at a glance)

| ID | Decision | Recommended | Primary driver |
|---|---|---|---|
| **D-06** | Tenant carriage | **Signed claim authoritative + optional matching subdomain/header; mismatch = reject** | Integrity of the active-tenant decision |
| **D-10** | Global ready/degraded | **Three-state; degraded = observability-only, never denies healthy tenants** | Isolation-aware health (with D-16) |
| **D-11** | Registry enumeration | **Hybrid: warm working set + lazy load; invalidate on re-association** | Scale + freshness |
| **D-12** | Control-DB schema mismatch | **Compatible-range (expand/contract); fail-safe to not-ready; migration is a controlled step** | Zero-downtime + fail-safe |
| **D-30** | Isolation enforcement | **Defense-in-depth: authz + routing + per-tenant credentials + audit** | Non-negotiable physical isolation |
| **JWT** | Token lifecycle | **Short TTL + IdP refresh + JWKS/`kid` rotation + TTL/IdP revocation (optional emergency denylist)** | Stateless, portable, revocable-enough |

**Decision order:** D-12 → D-11 → D-10 (IC-001 readiness cluster), then D-06 → JWT lifecycle → D-30 (IC-005 auth/routing cluster). Approving these resolves the last MVP architecture decisions and unblocks **IC-001 and IC-005 → Final** (the JWT-lifecycle items also retire IC-005's residual spec TBDs). All recommendations preserve *one request → one active tenant → one database*, non-negotiable physical isolation, registry-authoritative routing (D-07), OIDC + stateless JWT (D-05) with no session store, no shared tenant databases, no Supabase Auth / no vendor identity lock-in, and cloud/PostgreSQL portability.
