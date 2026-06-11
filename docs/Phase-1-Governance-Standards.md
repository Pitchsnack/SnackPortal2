# SnackPortal2 — Phase 1 Governance Standards

**Source:** PRD-P1-R2 (Fully Approved). Normative standards binding Build Phase 1
and the build phases that ride on it. Traces to D-14, anti-vendor-lock-in
(IC-001–005), D-19/D-13, D-10/D-16, IC-001/IC-002/IC-005.

---

## A. Adapter Boundary Standard (F-1)

**Definitions**
- **Port** — application-owned, vendor-neutral interface (what is needed). Imports
  only stdlib/portable shared types; never a vendor symbol. (D-14; Roadmap P1)
- **Adapter** — implements a Port for one backend; the ONLY place a vendor SDK may
  be imported. (D-14; anti-lock-in)
- **Provider Implementation** — a concrete, config-selected Adapter for one named
  backend; never referenced by name in business logic. (D-14; D-18)
- **Vendor-Specific** — bound to a provider/runtime (Supabase, Lovable, AWS/Azure/
  GCP SDKs, proprietary PG extensions, provider queues). Forbidden outside the
  adapter zone. (CLAUDE.md 1–2)
- **Vendor-Neutral** — depends only on open standards + platform ports; runs
  unchanged on AWS RDS / Azure / Cloud SQL / self-hosted. (CLAUDE.md 1; IC-005)

**Pattern** — Ports live in their shared domain module (e.g. `shared/secrets.py`)
or `shared/adapters/interfaces.py` (generic contracts). Concrete adapters live
ONLY under `**/adapters/providers/**`. Each service has one composition root that
binds a config-selected provider to a port.

**Dependency direction** — `business → Port ← Adapter`; only the composition root
selects a provider (by config). Adding/swapping a provider requires zero change to
the port or business logic.

## B. Vendor Import Governance (F-1)

**CI rules (encoded in `tests/architecture/` + `[tool.importlinter]` + gitleaks):**
- **R-CI-1** vendor SDK import allowed only if path matches `**/adapters/providers/**`.
- **R-CI-2** maintained vendor ban-list (supabase, lovable, boto3/botocore, azure,
  google.cloud/auth, …), banned except R-CI-1 path.
- **R-CI-3** no module outside a composition root imports `**/adapters/providers/**`.
- **R-CI-4** port purity: `interfaces` imports no vendor SDK / no `providers/**`.
- **R-CI-5** shared-is-leaf + service independence + cycle detection.
- **R-CI-6** secret-literal scan over source and templates; `*_REF` = reference only.
- **R-CI-7** best-effort ban on proprietary PostgreSQL extension / bulk-load idioms.

**Anti-lock-in validation:** D-14 (references only; values in-memory at use),
anti-lock-in (no Supabase/Lovable/proprietary; portable 4 targets), Roadmap P1
(interfaces only; providers empty). The single containment boundary makes
neutrality enforceable.

## E. Shared Package Admission Policy (F-3)

**May enter `shared/`:** cross-cutting **ports** used by ≥2 services; contract-
agnostic primitives (errors, secret-free context, redacting logging); cross-cutting
**DTO shapes** owned by no single contract; the config loader mechanism.
**Must stay in services:** any DTO that is one contract's I/O (Tenant Descriptor,
Lineage Record, Import Request/Status); per-service config schemas; all business
logic; all provider selection.
**Admission test:** a `shared` candidate must cite ≥2 consuming services and no
exclusive contract owner. No `shared` DTO carries secrets/tokens/payloads (D-14).

## F. Queue Governance (F-4)

- **Dispatch only.** Envelope = `{tenant_id, job_id, idempotency_key,
  correlation_id, state_ref}`; no payload/secrets/PII. (D-19)
- **Not a state store.** Authoritative durable job state is tenant-DB-resident,
  written via `database_router`; status reads tenant-DB state, not the queue.
- **Tenant state always tenant-resident** — only references transit; consumers
  re-establish the single active tenant context + re-auth statelessly. (D-04/D-05)
- **Portable** — any portable broker or DB-backed queue; no proprietary queue in
  business logic; import uses separate bounded capacity. (D-13)

## G. Rate-Limiting Governance (F-5)

- Model as a `RateLimiter` **port** behind the adapter boundary.
- Portable backends, config-selected: in-memory (**dev/single-instance only**) or a
  portable shared counter (Redis-protocol or PostgreSQL-backed) for multi-instance.
  No proprietary WAF/API-gateway limiter in business logic. (CLAUDE.md 1–2)
- Keys use opaque principal/tenant identifiers or IP — never secrets/PII.
- An `api_gateway` ingress concern, free of business logic and DB-of-record coupling.

## H. Naming & Terminology Standard (F-6, F-8)

Unqualified "Phase 1" is prohibited.
- **Build Phase 1…6** — construction stages (Roadmap).
- **Bootstrap Phase 0 / Bootstrap Phase 1** — runtime startup states (D-01).
- **Global Readiness** = `ready | degraded | not-ready` (D-10); **Tenant Readiness**
  = `ready | not-ready` (IC-002).
- **Tenant Lifecycle** = Registered/Provisioning/Verifying/Ready/Suspended/Failed/
  Decommissioned (IC-002).
- **Denial Semantics** = unauthenticated(401)/forbidden(403)/not-found/not-ready/
  administratively-disabled/unavailable.
- **Inter-service comms** = "transport call" (network; the only mechanism) vs
  "in-process import" (forbidden between services).

## I. Readiness & Disclosure Standard (F-9)

- **Liveness** — MAY be unauthenticated; static, non-disclosing; no tenant/DB detail.
- **Global Readiness** — three-state; access-controlled and minimally disclosing;
  no tenant counts/identities/DB topology to unauthorized callers; `degraded` never
  denies healthy tenants. (IC-001/D-10/D-16)
- **Tenant Readiness** — two-state; defined denial semantics; unknown vs
  not-yet-loaded vs unauthorized indistinguishable (consistent denial). (IC-002)
- **Error responses** — canonical denial codes; non-sensitive only; no stack traces,
  secrets, DB identifiers, or hostnames; 401 vs 403 (IC-005); `not-found` covers
  unknown and unauthorized-to-know (existence never confirmed).
- **No tenant/DB existence or topology leakage** — ever. (IC-002/D-30/D-14)
