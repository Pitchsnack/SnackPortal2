# Decision Pack — Tenant Infrastructure (D-07, D-13, D-14, D-15, D-16, D-17)

**Type:** Architecture analysis only · **Phase:** Architecture Planning
**Purpose:** Resolve the remaining tenant-infrastructure decisions blocking **IC-002** from moving Draft → Reviewed.
**Scope:** Analysis and recommendations only. No implementation code, migrations, backend services, or infrastructure code.
**Date:** 2026-06-05 · See also: [IC-002](../contracts/IC-002-Tenant-Startup-Contract.md), [Architecture-Decision-Register.md](Architecture-Decision-Register.md), [Contract-Gap-Analysis.md](Contract-Gap-Analysis.md)

## Binding constraints (apply to every option below)
- **Invariants preserved:** one request → one active tenant → one database; **no shared tenant databases**.
- **No Supabase-specific** and **no Lovable-specific** business logic.
- **PostgreSQL / cloud portable:** AWS RDS, Azure Database for PostgreSQL, Google Cloud SQL, and self-hosted — interchangeably.
- **Secrets:** secret *values* MUST NEVER appear in DTOs, logs, API responses, or contracts.
- **Connection descriptors are references only** (pointer to a secret-store entry), never raw credentials.

Any option that would breach these is out of contract regardless of other merits.

## How these decisions relate
Onboarding chain: **D-14 (secret abstraction)** and **D-07 (mapping)** are foundational; **D-15 (provisioning)** produces both; then runtime/ops: **D-13 (pooling)**, **D-16 (readiness)**, and lifecycle **D-17 (migrations)**. Suggested decision order: **D-14 → D-07 → D-15 → D-13 → D-16 → D-17**.

---

# D-07 — Tenant Identifier → Physical Database Mapping

### 1. Decision description
How is a tenant identifier resolved to its specific physical PostgreSQL database: authoritative **registry lookup** (Control DB), deterministic **naming convention**, or a **hybrid**?

### 2. Why it matters
This is the mechanism behind the Database Router. It governs relocation/restore/DR flexibility, security (name predictability), and whether physical placement is coupled to identity. A rigid mapping blocks moving a tenant DB without changing its identity.

### 3. Available options
- **A — Registry-authoritative:** the Control-DB registry holds the binding; the stored value is a **reference** to a secret-store connection descriptor (D-14). Fully indirected.
- **B — Naming-convention-only:** database/host derived deterministically from the tenant id; no per-tenant binding row.
- **C — Hybrid:** convention provides a default/bootstrap hint, but the registry is always authoritative and overrides it.

### 4. Pros and cons
| Option | Pros | Cons |
|---|---|---|
| A — Registry | Full relocation/DR flexibility; placement decoupled from identity; fits reference-only secrets cleanly | Resolution reads the registry (needs caching); Control DB is a hot dependency |
| B — Convention | Simple; no per-tenant row; deterministic | Couples identity to placement; brittle for restore/relocation; predictable names leak info; hard to vary per tenant |
| C — Hybrid | Sane default + registry override preserves flexibility | Two mechanisms; drift risk; must define "registry wins" precedence |

### 5. Impact on IC-002
Confirms the *Physical Database Association* section: the registry is the single authoritative source, `database_association_ref → db_descriptor_ref` (secret-store reference). Re-association updates the registry entry and re-enters `Verifying`.

### 6. Impact on IC-005
The Database Router resolves via the (cached) registry and MUST NOT hardcode tenant DBs. Routing remains one-request → one-DB. No change to authentication.

### 7. Impact on IC-003 Import
Import targets the **registry-resolved** DB, so a relocated/restored tenant imports to the correct database transparently. Option B would risk import breakage on relocation.

### 8. Impact on physical multi-database architecture
Option A best supports per-tenant placement (region/cloud), relocation, and DR while preserving *no shared DB*. Stale cache entries are the one isolation hazard — see risks.

### 9. Recommended option
**A — Registry-authoritative**, optionally with a naming convention used only as a non-authoritative bootstrap default (registry always wins ⇒ light C). Resolution is cached with explicit, tenant-scoped invalidation on re-association; the descriptor is always a secret-store reference, never raw credentials.

### 10. Open risks
Resolution-cache **staleness** (a stale mapping could route to the wrong/old DB — an isolation risk; mandate invalidation on `ReassociateDatabase`); Control DB as a hot resolution dependency (mitigate with cache + readiness); predictable-name info leak if a convention is used.

---

# D-13 — Connection Pooling and Tenant Scale Model

### 1. Decision description
How are connections pooled across many physically separate tenant databases, and what is the scaling ceiling as tenant count grows?

### 2. Why it matters
Physical-per-tenant DBs multiply connections; PostgreSQL has a hard per-instance connection ceiling. The model sets tenant density per node, cost, latency (cold pools), and whether the architecture scales to thousands of tenants.

### 3. Available options
- **A — Per-tenant in-process pools:** each app instance keeps a pool per active tenant.
- **B — Multiplexed manager with lazy, bounded per-tenant pools + LRU idle eviction:** pools held only for *active* tenants.
- **C — External portable pooler:** a self-hostable transaction-level pooler (PgBouncer-class, or equivalent) fronts tenant DBs; the app holds few connections.

### 4. Pros and cons
| Option | Pros | Cons |
|---|---|---|
| A — In-process | Simple; strong isolation | Doesn't scale: tenants × instances × pool size exhausts connections; idle waste |
| B — Lazy + LRU | Scales by holding pools only for active tenants; bounded; portable (app-level) | Cold-start latency after eviction; eviction tuning |
| C — External pooler | High density; offloads multiplexing | Extra component to secure (must be portable/self-hostable, not cloud-only); transaction-pooling limits; cross-tenant blast-radius risk if misconfigured |

### 5. Impact on IC-002
Connection management sits behind the registry-resolved, referenced descriptor. The pooling model bounds the **scale ceiling** IC-002 flags, and shapes how `Verifying`/health checks acquire connections.

### 6. Impact on IC-005
The Database Router obtains the connection for the **single active tenant** from the pool manager. Critical isolation rule: a request's connection MUST be bound to exactly that tenant — **no cross-tenant connection reuse**, especially within a transaction (a hard constraint on any shared pooler).

### 7. Impact on IC-003 Import
Imports are connection-heavy and may be long-running; transaction-level pooling (C) can conflict with long transactions/bulk loads. Import SHOULD get separate, bounded capacity so it cannot starve interactive traffic.

### 8. Impact on physical multi-database architecture
This is the central scaling tension of physical isolation. Connections must never blend tenants; eviction/multiplexing must be tenant-safe; the per-instance connection ceiling is the hard fleet-planning constraint.

### 9. Recommended option
**B as the app-level baseline** (lazy, bounded per-tenant pools with LRU idle eviction), **adding C (a portable, self-hostable transaction pooler) as a scaling layer when density demands it.** Avoid A. Enforce per-request tenant-bound connections and separate import capacity.

### 10. Open risks
Connection exhaustion at high tenant counts (set per-instance ceilings + fleet planning, ties to D-15); cold-start latency from eviction; transaction-pooler feature limits vs. import/long transactions; the pooler as a cross-tenant isolation hazard if misconfigured. Ties to D-16 (down-tenant pool behavior).

---

# D-14 — Credential and Secret Storage Abstraction

### 1. Decision description
Where/how are per-tenant DB credentials (and other secrets, e.g., the D-01 bootstrap trust anchor) stored, referenced, and rotated — via a portable abstraction — so values never appear in DTOs/logs/contracts and descriptors carry references only?

### 2. Why it matters
It directly enforces the secrets constraint, sets portability and rotation-without-downtime, bounds leak blast radius, and defines how `db_descriptor_ref` resolves at connect time.

### 3. Available options
- **A — Cloud-native per environment** (AWS Secrets Manager / Azure Key Vault / GCP Secret Manager) behind a thin neutral interface.
- **B — Single self-hostable secret manager** (Vault-class, or equivalent) used uniformly everywhere.
- **C — Pluggable abstraction:** one internal reference-based interface (resolve / version / rotate) with swappable backends — cloud-native where present, self-hostable elsewhere.

### 4. Pros and cons
| Option | Pros | Cons |
|---|---|---|
| A — Cloud-native | Managed; native IAM; rotation features | Different APIs per cloud (portability risk unless abstracted); no self-hosted path; lock-in risk |
| B — Self-hostable | Uniform everywhere incl. air-gapped; full control | You operate it (HA/backup, its own unseal/bootstrap — a mini-D-01) |
| C — Pluggable | Best portability; references-only by design; no vendor logic in app | Must design the interface (versioning, rotation, caching, failure); lowest-common-denominator features |

### 5. Impact on IC-002
Defines what `db_descriptor_ref` points to and how it resolves at connect time; guarantees "credentials never in payloads." Rotation must not require re-registration (may trigger a pool refresh, D-13).

### 6. Impact on IC-005
The Phase-0 trust anchor (D-01) and any signing/JWKS material use the same abstraction. Auth stays DB-free (D-05); **no secret ever appears in a JWT or response** — material is fetched by reference at the edges only.

### 7. Impact on IC-003 Import
Any import-source credentials MUST also be reference-only via this abstraction; import payloads and logs MUST NOT carry secrets. Import connects to the tenant DB using the same resolved, referenced credentials.

### 8. Impact on physical multi-database architecture
Per-tenant credentials = per-tenant secrets; the abstraction must scale to N tenants with per-tenant rotation and no cross-tenant impact. Reference indirection keeps the registry secret-free and enables relocation (D-07 A).

### 9. Recommended option
**C — a single internal, reference-based secret-store abstraction** (resolve-by-reference, versioned, rotatable) with pluggable backends; default to the environment's cloud-native manager where present, self-hostable elsewhere. Mandate: descriptors store `{store-ref, version}`, never values; resolution is in-memory at connect time and **never logged**.

### 10. Open risks
Secret-resolution caching (memory-only, short TTL, secure wipe — never disk/log); rotation coordination with live pools (dual-version graceful refresh); the secret store's own availability/unseal (mini-D-01); **accidental secret logging is the top risk** — enforce redaction at the logging boundary. Ties to D-13 (pool refresh) and D-01 (shared trust-anchor abstraction).

---

# D-15 — Tenant Provisioning Ownership

### 1. Decision description
Who owns creating/destroying the physical tenant database (plus its credential and registry entry): infrastructure/IaC, an automated control-plane provisioning workflow, or a manual operator runbook? IC-002 *observes and associates*; this decides who *provisions*.

### 2. Why it matters
Sets onboarding speed/automation, DR re-provisioning, and who holds the high-privilege ability to create databases (a major security/blast-radius question). It drives IC-002's `Provisioning → Verifying` transition.

### 3. Available options
- **A — Infrastructure/IaC-owned:** declarative (Terraform-class) creation; the control plane only observes/associates.
- **B — Automated control-plane provisioning workflow:** the platform programmatically creates DB + secret + registry entry via a privileged, audited, abstracted path.
- **C — Manual operator runbook:** a human creates the DB, stores the secret, registers the tenant.

### 4. Pros and cons
| Option | Pros | Cons |
|---|---|---|
| A — IaC | Declarative, reviewable, reproducible, portable; strong VCS audit; clean infra/app split | Onboarding tied to an apply (slower; not instant self-serve); DR needs the pipeline |
| B — Automated workflow | Fast self-serve onboarding at scale; programmatic DR | Control plane holds DB-creation privilege (high blast radius); must abstract cross-cloud creation; more to secure |
| C — Manual | Simple to start; tight human control of a sensitive action | Doesn't scale; error-prone; incompatible with automated multi-cloud/self-hosted at volume; poor DR |

### 5. Impact on IC-002
Drives the `Provisioning` state and the signal moving a tenant to `Verifying`. The contract stays "observe → associate → verify" regardless of who provisions; B simply automates create → write secret (D-14) → register (D-07) → verify.

### 6. Impact on IC-005
Minimal/indirect. The privileged provisioning identity (B) MUST be control-plane-scoped and never tenant-routable. No change to runtime auth/routing.

### 7. Impact on IC-003 Import
A tenant must be `Ready` (provisioned + verified) before import. Faster provisioning (B) shortens time-to-first-import; bulk onboarding + immediate import needs automation to avoid a bottleneck.

### 8. Impact on physical multi-database architecture
Provisioning is how each **physically separate** DB comes to exist — it MUST guarantee a separate DB per tenant (never reuse/share), create per-tenant credentials (D-14), and register the association (D-07), portably across RDS/Azure/Cloud SQL/self-hosted.

### 9. Recommended option
**Hybrid: IaC substrate (A) orchestrated by a thin, automated control-plane workflow (B)** that invokes portable provisioning primitives through a privileged, audited, abstracted path — not ad-hoc DB creation. Keep a **manual break-glass runbook (C) for first-boot/DR only** (echoes D-01 Option D). The provisioning identity is least-privilege, control-plane-scoped, and audited.

### 10. Open risks
Provisioning-identity blast radius (least-privilege, audited, ideally separated from runtime control plane); cross-cloud creation portability (abstract it; self-hosted path); **orphaned/partial provisioning** (DB created but registration failed → reconciliation needed); automated-creation cost runaway; DR re-provisioning correctness. Ties to D-14, D-07, D-16.

---

# D-16 — Partial-Fleet Readiness Behavior

### 1. Decision description
When some tenant databases are unavailable while others are healthy, how does the platform behave globally and per tenant? Defines the relationship between per-tenant readiness and overall platform readiness (relates to global D-10).

### 2. Why it matters
With physical-per-tenant DBs, partial outages are normal — one tenant down ≠ platform down. This decision is the operational expression of the isolation promise and governs blast-radius containment and what callers see.

### 3. Available options
- **A — Strict per-tenant independence:** platform stays globally `ready`; only affected tenants are `not-ready/Failed`; healthy tenants fully served.
- **B — Threshold-based degraded signal:** platform reports `degraded` (not down) when a configurable fraction/critical set is unavailable, **while still serving healthy tenants**.
- **C — Fail-closed/global:** beyond a threshold (or on shared-dependency failure) the platform marks itself globally not-ready.

### 4. Pros and cons
| Option | Pros | Cons |
|---|---|---|
| A — Independence | Maximizes isolation benefit; one tenant down never affects others; best availability | Needs strong per-tenant observability or a mass failure could hide |
| B — Threshold degraded | Aggregate early-warning for ops while preserving per-tenant service | Threshold tuning; must never deny healthy tenants |
| C — Fail-closed | Conservative; clear systemic signal | Penalizes healthy tenants for others' outages — violates isolation (wrong except for true shared-dependency failure) |

### 5. Impact on IC-002
Defines IC-002's readiness semantics under partial outage: per-tenant readiness is **independent**, computed on each tenant's own DB health. Any aggregate/`degraded` signal is **derived**, not per-tenant.

### 6. Impact on IC-005
Routing uses per-tenant readiness: serve healthy tenants, deny not-ready ones with the correct semantic — **regardless of other tenants**. IC-005 MUST NOT globally refuse routing because some other tenant is down (except the true Phase-0 / Control-DB-down case = D-10).

### 7. Impact on IC-003 Import
Imports for healthy tenants proceed; imports targeting a down tenant fail independently with `unavailable`/retry. One tenant's import backlog or failure MUST NOT block others.

### 8. Impact on physical multi-database architecture
This realizes independent failure domains — the core operational benefit of physical isolation. The only legitimate global-not-ready trigger is failure of a genuinely shared dependency (Control DB / Phase-0), never tenant-DB outages.

### 9. Recommended option
**A (strict per-tenant independence) as the behavior, plus B as an *observability-only* overlay** — a derived `degraded` aggregate for alerting that NEVER denies healthy tenants. Reserve global not-ready (C) strictly for shared-dependency failure (= D-10).

### 10. Open risks
**Silent mass-failure detection** (must alert on the aggregate even while serving — hence the B overlay); per-tenant health-check cost/cadence at scale (cheap, staggered checks); **flapping** tenants (debounce/hysteresis); ensuring the degraded signal can never be wired to deny healthy tenants. Ties to D-10, D-13 (health-check connections), D-15.

---

# D-17 — Schema Migration Coordination

### 1. Decision description
How are per-tenant schema migrations coordinated relative to a global/expected schema version across N independent tenant DBs (plus the Control DB), given the fleet cannot migrate atomically?

### 2. Why it matters
Tenants will sit at different versions mid-rollout. This sets deploy safety, whether `Verifying` blocks on version, rollout/rollback strategy, and downtime — the heart of operating physical multi-tenancy.

### 3. Available options
- **A — Strict lockstep:** migrate all tenant DBs together (maintenance window) before new code serves; single global version.
- **B — Expand/contract, per-tenant rolling:** backward-compatible migrations; code tolerates a version *range*; each tenant migrated independently; old + new code coexist during the window.
- **C — Version-gated readiness:** code checks each tenant's `observed_schema_version` against the supported range at readiness/routing; out-of-range tenants are `not-ready` until migrated.

### 4. Pros and cons
| Option | Pros | Cons |
|---|---|---|
| A — Lockstep | Simple single-version reasoning | Doesn't scale; downtime; big-bang risk; one slow tenant blocks the release |
| B — Expand/contract rolling | Low/zero downtime; per-tenant independence (fits isolation); rollback-friendly within the window | Code must support a version *range*; migrations must be backward-compatible; discipline required |
| C — Version-gated readiness | Safety net: never serve an incompatible schema | On its own causes outages for un-migrated tenants — best as a complement to B |

### 5. Impact on IC-002
Gives meaning to `expected_schema_version` vs `observed_schema_version` and the `Verifying` check: readiness accepts a **supported range**, not a single exact version; a tenant below the floor is `not-ready` until migrated. Per-tenant migration is an audited lifecycle operation.

### 6. Impact on IC-005
Routing honors readiness: a version-gated tenant (C) is not-ready → not routed, with retry semantics. No change to authentication; per-request single-tenant unaffected.

### 7. Impact on IC-003 Import
Import must target a schema it understands; a tenant mid-migration or below the supported range SHOULD be gated/deferred (consistent with readiness). Expand/contract means import must tolerate the version range or be version-aware, and SHOULD NOT run into a tenant being migrated.

### 8. Impact on physical multi-database architecture
Heterogeneous versions across independent DBs is the canonical physical-multi-DB challenge. **B is the only model that scales while preserving per-tenant independence** and availability. Control-DB/global schema coordination remains with IC-001.

### 9. Recommended option
**B (expand/contract, per-tenant rolling) complemented by C (version-gated readiness against a supported range).** Code supports a version window; tenants migrate independently and audited; readiness gates only truly-incompatible tenants. Reserve A (lockstep) for the Control DB or rare breaking changes under explicit windows.

### 10. Open risks
Discipline to keep migrations backward-compatible (expand/contract violations cause outages); **long-lived version skew** across the fleet (enforce a max-skew / contract deadline); partially-migrated tenants (per-tenant migration must be resumable + audited); coordinating import with in-flight migration; tooling to track per-tenant version across N DBs. Ties to D-16 (gated = not-ready), D-13 (migration connections), IC-001 (global version).

---

## Consolidated recommendations (at a glance)

| ID | Decision | Recommended | Primary driver |
|---|---|---|---|
| **D-07** | ID → DB mapping | **Registry-authoritative** (convention only as overridable default) | Relocation/DR flexibility; reference-only secrets |
| **D-13** | Pooling & scale | **Lazy bounded per-tenant pools + LRU**, add **portable transaction pooler** at density | Connection ceiling vs. tenant count |
| **D-14** | Secret storage | **Pluggable reference-based abstraction**, cloud-native or self-hostable backends | Portability + secrets-never-in-payloads |
| **D-15** | Provisioning | **IaC substrate + automated control-plane workflow**; manual = break-glass only | Automated, portable onboarding/DR |
| **D-16** | Partial-fleet readiness | **Per-tenant independence + degraded as observability only** | Isolation = independent failure domains |
| **D-17** | Schema migration | **Expand/contract rolling + range-gated readiness** | Scale without downtime; per-tenant independence |

**Decision order:** D-14 → D-07 → D-15 (onboarding chain), then D-13 → D-16 → D-17 (runtime/ops). Once approved, these resolve IC-002's *Residual Open Decisions* and unblock **IC-002 Draft → Reviewed**. All recommendations preserve *one request → one active tenant → one database*, *no shared tenant databases*, PostgreSQL/cloud portability, and reference-only (never raw) credentials.
