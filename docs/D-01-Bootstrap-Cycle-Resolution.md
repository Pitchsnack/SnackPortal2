# D-01 — Bootstrap Cycle Resolution

**Type:** Architecture Decision Addendum · **Phase:** Architecture Planning · **Status:** Proposed (awaiting sign-off)
**Decision ID:** D-01 (see [Contract-Gap-Analysis.md](Contract-Gap-Analysis.md))
**Affects:** IC-001 Global Startup, IC-005 Authentication Routing
**Related decisions:** D-03 (identity model), D-05 (auth scheme), D-10 (degraded definition), D-14 (credential storage)
**Scope:** Architecture decision only. No implementation code, migrations, services, or infrastructure code.

---

## 1. Problem Statement

The platform has a circular startup dependency between its two foundational contracts:

- **IC-001 (Global Startup)** is responsible for bringing the **Control Database** online and wants its control-plane/startup endpoints authenticated — and authentication is owned by IC-005.
- **IC-005 (Authentication Routing)** authenticates requests and routes them using **routing metadata that lives in the Control Database** — which is not available until IC-001 has finished.

So IC-001 needs IC-005 to authenticate its startup, while IC-005 needs the Control DB that IC-001 has not yet brought up. Neither can complete first under the contracts as currently drafted.

**Root cause:** the contracts conflate two distinct concerns —
1. **Authentication** ("who is this caller?") — a trust decision, and
2. **Tenant routing** ("which database does this request target?") — a data lookup against Control-DB-resident metadata.

The control plane needs (1) but does **not** need (2): control-plane operations target the Control DB itself, never a tenant DB. Every viable resolution below works by **decoupling the authentication trust anchor from Control-DB-resident routing metadata.**

## 2. Why This Is a Blocker

- **Foundational layer cannot be finalized.** IC-001 and IC-005 sit at Layer 0; every other contract (IC-002, IC-003, IC-004, IC-006) depends on them. They cannot leave `Draft` while the cycle is unresolved.
- **It is a design contradiction, not a detail.** No amount of endpoint/DTO specification fixes a circular ordering; it must be broken architecturally first.
- **Security-critical path.** Whatever breaks the cycle becomes the platform's earliest trust decision and a high-value attack surface; it must be designed deliberately, not improvised during implementation.
- **Portability at stake.** A careless fix (e.g. leaning on one cloud's identity service) would violate the multi-cloud / self-hosted portability constraint at the most fundamental layer.

---

## 3. Option A — Bootstrap / System Identity Independent of Control DB

Introduce a dedicated, non-human **system (bootstrap) identity** whose trust is anchored **out-of-band** and verifiable **without any database lookup** (e.g. asymmetric signature verified against a public key, or a credential delivered via a secret-store/instance-identity abstraction).

Formalize a **two-phase authentication model**:
- **Phase 0 (bootstrap):** only the system identity is recognized; verification is purely cryptographic/static; only control-plane/startup operations are permitted; **no tenant routing is possible.**
- **Phase 1 (runtime):** once the Control DB is up and routing metadata is loaded, the full IC-005 model takes over (end-user principals, tenant routing). Phase 0 is closed.

The system identity is **control-plane-scoped only** and can never resolve to a tenant DB.

## 4. Option B — Static Bootstrap Config File

Hold the bootstrap trust anchor and a **minimal seed** of auth/route rules in a versioned, infra-owned **static config** (config file and/or environment templates in `infrastructure/`). IC-005 defines a narrow, explicit fallback: during bootstrap it reads the seed from static config; once the Control DB is ready, the Control DB becomes the single source of truth. Config is read-only at runtime and never written by the application; secrets are **referenced** (secret-store handle), never inlined.

## 5. Option C — Dedicated Identity Provider First, Control DB Second

Introduce a standalone, **self-hostable OIDC-standard Identity Provider** as an explicit ordering dependency that starts **before** the Control DB. IC-005 authenticates by validating tokens against the IdP's published public keys (JWKS) — a stateless check needing **no Control DB**. The Control DB still holds *tenant routing* metadata, but control-plane bring-up does not need tenant routing, so the cycle is broken: authentication depends on the IdP, not the Control DB.

## 6. Option D — Manual First-Tenant / First-Boot Provisioning

A guarded, one-time, operator-driven **break-glass** step seeds the Control DB and creates the first control-plane admin identity out-of-band (maintenance mode), then is **disabled**. Steady-state boots use normal IC-005 authentication against the now-seeded Control DB.

---

## 7. Pros and Cons

### Option A — Bootstrap / System Identity
**Pros:** Breaks the cycle cleanly by separating authN trust from routing data; no human in the loop on every boot; fully automatable (fits Docker/K8s/Terraform deploys); portable when the secret source is abstracted; aligns with least privilege (control-plane-only identity).
**Cons:** Introduces a second auth path (Phase 0) that must be kept minimal and well-tested; the bootstrap credential must be stored and rotated securely; risk of the Phase-0 path becoming an under-monitored backdoor if not strictly closed in Phase 1.

### Option B — Static Bootstrap Config
**Pros:** Simplest; no extra service; universally portable (files/env); transparent and auditable in version control; works air-gapped/self-hosted.
**Cons:** Two sources of truth during bootstrap (config vs. Control DB) with drift risk; rotation requires redeploy; only expresses a minimal seed, not dynamic routing; tempting (and dangerous) to inline secrets.

### Option C — Dedicated IdP First
**Pros:** Standards-based, stateless authN decoupled from routing data; supports real end-user / SSO / B2B identity (serves D-03); token validation is DB-free.
**Cons:** Adds a new critical service to run, secure, and make HA — itself a startup/ordering dependency; the IdP has its own first-admin bootstrap problem, **relocating** rather than removing the chicken-and-egg; heavier than MVP needs.

### Option D — Manual Provisioning
**Pros:** Conceptually trivial; no standing bootstrap credential or extra service in steady state; tight control and strong audit over the most sensitive first-ever action.
**Cons:** Manual — incompatible with automated, ephemeral, auto-scaling, or disaster-recovery re-provisioning; human-error prone; doesn't help routine restarts if the Control DB is lost; the maintenance path is a severe backdoor risk if ever left enabled.

---

## 8. Security Risks

| Option | Principal risks |
|---|---|
| **A** | Bootstrap credential is a high-value target (compromise = control-plane access); replay if not short-lived/asymmetric; privilege creep beyond control-plane; Phase-0 path as a latent backdoor if not provably closed. |
| **B** | Secrets committed to files if discipline slips; config tampering; stale seed entries outliving their purpose; the fallback becoming a permanent shadow source of truth. |
| **C** | The IdP becomes a single point of total compromise; JWKS/key-rotation handling; strict issuer/audience validation required; a misconfigured trust = full authentication bypass. |
| **D** | The break-glass/maintenance path is the highest-risk surface — must be disabled-by-default, time-boxed, and audited; manual credential handling; risk of being left enabled in production. |

**Cross-cutting:** whatever breaks the cycle is the platform's earliest trust root — it must be least-privilege, audited, and (for Phase-0/break-glass paths) provably closed once runtime auth is active.

## 9. Portability Risks

| Option | Portability assessment |
|---|---|
| **A** | **Low** if the secret/trust-anchor source is abstracted across AWS/Azure/GCP/self-hosted. **Risk:** binding to one cloud's instance-identity/IAM service breaks portability — keep an env/secret-file fallback. |
| **B** | **Very low** — files/env are universal. **Risk:** only if the config format encodes provider-specific assumptions; keep it provider-neutral. |
| **C** | **Medium** — must choose a portable, self-hostable **OIDC-standard** IdP and avoid managed cloud-IdP lock-in. **Explicitly not Supabase Auth.** Standard OIDC keeps the IdP swappable. |
| **D** | **Low technically**, but operationally **awkward** across many environments and **incompatible with fully automated multi-cloud/self-hosted deploys** — which the infrastructure goals require. |

All options must remain standard-PostgreSQL compatible and introduce **no Supabase-specific and no Lovable-specific** logic. The Control DB + independent tenant DB model is preserved in every option (the bootstrap identity is control-plane-only and never resolves a tenant DB).

---

## 10. Recommended Option

**Primary: Option A** (bootstrap/system identity, verified without the Control DB), formalized as the **two-phase authentication model**, **using Option B as its storage mechanism** (trust anchor + minimal routing seed in static, infra-owned config/env that *references* a secret store — never inlines secrets).

- **Option C is complementary, not competing:** an OIDC IdP, if/when adopted (D-03/D-05), becomes a valid **Phase-1** end-user authN backend. It is not required to break the cycle and should not be added solely for that purpose in MVP, since it relocates the bootstrap problem into the IdP.
- **Option D is retained as a one-time greenfield provisioning + break-glass safeguard,** disabled after first boot — never the steady-state mechanism.

**Why A + B:** they break the cycle at its root cause by decoupling the *authentication trust anchor* from *Control-DB-resident routing metadata*, while staying fully PostgreSQL/cloud-portable, automatable across all target environments, and faithful to the physical multi-database model. C adds a standing service and relocates the problem; D alone cannot support automated multi-cloud/self-hosted deployment.

**Resulting boot sequence (conceptual):**
`load trust anchor + static seed (B)` → `control plane authenticates as system identity, Phase 0 (A)` → `Control DB brought up & schema-checked (IC-001)` → `routing metadata loaded` → `transition to Phase 1; close Phase 0 (A/IC-005)` → `runtime end-user auth + tenant routing`.

---

## 11. Required Changes to IC-001

- **Add a "Bootstrap Phases" concept:** define Phase 0 (pre-Control-DB) vs. Phase 1 (post-Control-DB) and the explicit readiness gate that transitions between them.
- **State the Phase-0 trust model:** control-plane startup authenticates as the **bootstrap system identity**, verified **without any DB lookup**, against a trust anchor sourced from static/secret-store config (Option B).
- **Specify startup ordering** to match the recommended boot sequence (trust anchor/seed → Phase-0 system-identity auth → Control DB up + schema check → routing metadata loaded → transition to Phase 1).
- **Add the isolation invariant:** the system identity is control-plane-scoped only and can **never** resolve or route to a tenant DB.
- **Define failure behavior** when the trust anchor or seed is missing/invalid (refuse to start; surfaces with D-10's "degraded" definition).
- **Constrain the Phase-0 path:** minimal, audited, and the manual break-glass (Option D) disabled after first boot; require a means to assert Phase 0 is closed in production.
- **Update Authentication & Authorization sections** to reference the Phase-0 model and least-privilege system identity (replacing the current bare "Aligns with IC-005").

## 12. Required Changes to IC-005

- **Define the two-phase authentication model explicitly:**
  - *Phase 0:* recognizes **only** the bootstrap system identity; cryptographic/static verification with **no Control-DB dependency**; authorized for control-plane operations only; **all tenant-scoped requests denied.**
  - *Phase 1:* full runtime model (end-user principals + tenant routing via Control-DB metadata).
- **Decouple authN from routing data in the wording:** clarify that "routing metadata lives in the Control Database" applies to **Phase-1 tenant routing only**, and is **not** required to authenticate the control plane.
- **Name the bootstrap trust-anchor source** (static/secret-store, Option B) and state it is verified without a DB lookup.
- **Specify the Phase 0 → Phase 1 transition trigger** (Control DB ready + routing metadata loaded, owned by IC-001) and that Phase 0 is closed once Phase 1 is active.
- **Add the isolation invariant:** the system identity can never resolve to a tenant DB; Phase 0 denies all tenant-scoped requests.
- **Reserve Option C as a Phase-1 backend:** note that an OIDC-standard, self-hostable IdP may serve as the Phase-1 authentication backend (pending D-05), kept portable and explicitly **not** Supabase Auth.

---

## 13. Open Questions

- **Trust-anchor location & abstraction:** where does the bootstrap trust anchor live, and which secret-store abstraction spans AWS / Azure / GCP / self-hosted? (ties to **D-14**)
- **Credential form & rotation:** is the bootstrap identity a static credential or a short-lived/asymmetric token, and what is its rotation policy?
- **Runtime IdP decision:** adopt an external OIDC IdP (Option C) for Phase-1 now or later, and which portable IdP? (ties to **D-03**, **D-05**)
- **Phase transition & re-entry:** exact Phase 0 → Phase 1 semantics, and whether Phase 0 can be re-entered if the Control DB is lost at runtime (ties to **D-10** degraded behavior).
- **Disaster recovery / re-provisioning:** how is a wiped or replaced Control DB re-seeded **automatically** without re-enabling the manual break-glass path?
- **HA / multi-node bootstrap:** how do multiple control-plane instances agree on the phase transition and avoid split-brain during bootstrap?
- **Provable closure:** how is the Phase-0 (and Option-D break-glass) path demonstrably disabled in production for audit?
