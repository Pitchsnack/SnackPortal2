# PRD 06 B-5 — Production Activation Blocker Register

**Gate posture: NOT READY.** Production runtime activation is **blocked** while any blocker below is OPEN. Default is
conservative: missing evidence ⇒ OPEN ⇒ activation blocked. This register is grounded in the **actual** current state
(current baseline `origin/main @ fff215b5bd004760ea0d81915c3d93ca128673ed`, re-grounded 2026-07-12); production is far off by design.

| ID | Description | Severity | Owner | Evidence required | Status | Blocks activation |
|----|-------------|----------|-------|-------------------|--------|-------------------|
| **B5-BLK-1** | `backend/control_plane/main.py` runtime wiring is deferred (`NotImplementedError`; default `in_memory`). The durable/real adapters exist (B-2/B-4) but are not constructed at runtime. | Critical | Control Plane | A separately-authorized runtime-activation phase that flips the deferral under the gate, with the regression lock consciously updated. | OPEN | YES |
| **B5-BLK-2** | No production Control DB / Tenant DB fleet provisioned. B-3 was docs/scaffold-only; D-15 IaC has not been executed against production. | Critical | Infra / Control Plane | Provisioned, physically-distinct Control + per-tenant DBs in the target environment, with identity proof. | OPEN | YES |
| **B5-BLK-3** | No production secret store wired. The D-14 reference-based abstraction exists; the default provider is `EnvReferenceSecretStore`. | Critical | Infra | A production-grade pluggable secret store resolving `*_REF` references at connect time; references only. | OPEN | YES |
| **B5-BLK-4** | Provisioning audit sink — B-6 machinery built on `main` (#21 / #23 / #25); not yet wired into the production runtime path, and the durable routing audit (DBR-AR-2) is still absent. | Major | Control Plane | B-6 audit sink available **and** wired for the target (production) environment, or an explicit approved waiver; closure is a separate Dan-authorized decision. | OPEN | YES |
| **B5-BLK-5** | Frontend on interim Supabase/RLS; Lovable → API-Gateway cutover pending (DRIFT-01). | Major | Frontend / Gateway | Lovable integrates only through the API Gateway; no direct frontend DB/Supabase calls. | OPEN | YES |
| **B5-BLK-6** | IC-009 portal contracts and IC-007 cross-tenant contracts not runtime-bound. | Major | Architecture | Portal/cross-tenant contracts bound to runtime behavior under the Gateway. | OPEN | YES |
| **B5-BLK-7** | Production migration / DDL readiness evidence missing (D-17). | Major | Infra / Control Plane | Reviewed DDL applied (blob-pinned) within the supported schema range; version-gated readiness proven. | OPEN | YES |
| **B5-BLK-8** | Production rollback evidence missing. | Major | Control Plane | A proven, isolated, non-destructive rollback to the deferred composition. | OPEN | YES |
| **B5-BLK-9** | Production monitoring / alerting evidence missing. | Minor | Ops | Monitoring + alerting in place for the activated runtime path. | OPEN | YES |

## Rules

```
A blocker is closed ONLY when its required evidence is captured (see b5_activation_evidence_template.md) and approved.
While any blocker is OPEN, the Production Runtime Activation Gate decision is DO-NOT-ACTIVATE (NOT READY).
B-5 changes none of these to closed: B-5 builds the gate; it does not activate runtime or provision production.
```

**Current standing decision: NOT READY (9 / 9 blockers OPEN).**

## Evidence re-grounding (2026-07-12, baseline `fff215b5bd004760ea0d81915c3d93ca128673ed`)

The B5 runtime-readiness arc has landed on `main` — **B5-1 (#69), B5-2 (#70), B5-3 (#71), B5-4 (#72),
B5-5 (#73), B5-4A (#74)** and **Smoke C V2 including Fix R3 (#75)**. This changes the *evidence status*
below; it does **not** flip any blocker to closed. Governing scope statement:

```text
Smoke C V2 including Fix R3 supplies database-granularity evidence.
It does not itself close B5-BLK-4.
```

Database granularity = distinct physical databases on one local admin cluster — **not** cluster-level /
multi-cluster distinctness, **not** production deployment, and **not** MVP completion.

### Evidence now satisfied (landed on `main`; local scope only)

| Evidence | Taxonomy | Landed |
|---|---|---|
| Environment-composed Control-Plane read server (`build_read_server_from_env`) | SATISFIED — MERGED AND VERIFIED | B5-1 / PR #69 |
| Runnable Auth Router + Database Router lifecycle entrypoints | SATISFIED — MERGED AND VERIFIED | B5-2 / PR #70 |
| Live-wire denial semantics (404 → None; `/federation` route) | SATISFIED — MERGED AND VERIFIED | B5-3 / PR #71 |
| Standing Control DB + two physically distinct tenant databases | SATISFIED AT DATABASE GRANULARITY | B5-4 / PR #72 |
| Smoke C specification (SMOKE-C-SPEC-01) + real RS256 token fixture | SATISFIED — MERGED AND VERIFIED | B5-5 / PR #73 |
| Standing authentication memberships + non-Ready `b5_standing_dormant` tenant | SATISFIED — MERGED AND VERIFIED | B5-4A / PR #74 |
| Integrated authenticated routing through all real seams — alpha → alpha DB only, beta → beta DB only, dormant → `tenant_not_ready`, unknown → `tenant_access_denied`, denials perform zero dispatch / pool / tenant-DB connection, before-state == after-state | SATISFIED AT DATABASE GRANULARITY | Smoke C V2 + Fix R3 / PR #75 |

### Blocker evidence taxonomy (every blocker REMAINS OPEN — the gate stays DO-NOT-ACTIVATE)

| Blocker | Evidence taxonomy | Re-grounded note |
|---|---|---|
| **B5-BLK-1** | OPEN — GOVERNANCE DECISION REQUIRED | The composed runtime path is proven locally (Smoke C V2, database granularity), but `main.py`'s in-memory default deferral is intact by design; flipping it is a separately-authorized decision. |
| **B5-BLK-2** | OPEN — DEPLOYMENT EVIDENCE REQUIRED | Physical distinctness proven **at database granularity** locally (B5-4/B5-4A/Smoke C V2); production fleet + cluster-level distinctness not provisioned. |
| **B5-BLK-3** | OPEN — DEPLOYMENT EVIDENCE REQUIRED | D-14 reference secret-store + local file/env materialization exercised locally; a production-grade store is not wired. |
| **B5-BLK-4** | OPEN — GOVERNANCE DECISION REQUIRED | B-6 provisioning audit sink (#21), B-7 durable store (#23) and B-7B runtime wiring (#25) landed on `main` — **evidence that now supports a future closure review, not closure**. The durable **routing** audit (DBR-AR-2) remains a separate open follow-on, and closure is a **separate Dan-authorized decision**. **Smoke C V2 including Fix R3 does not close B5-BLK-4.** |
| **B5-BLK-5** | OPEN — PRODUCT/INTEGRATION TRACK | Lovable interim Supabase/RLS; API-Gateway cutover pending (DRIFT-01) — separate track. |
| **B5-BLK-6** | OPEN — PRODUCT/INTEGRATION TRACK | IC-009 portal / IC-007 cross-tenant contracts not runtime-bound — separate track. |
| **B5-BLK-7** | OPEN — DEPLOYMENT EVIDENCE REQUIRED | Production migration / DDL readiness evidence still missing (D-17). |
| **B5-BLK-8** | OPEN — DEPLOYMENT EVIDENCE REQUIRED | Production rollback evidence still missing. |
| **B5-BLK-9** | OPEN — DEPLOYMENT EVIDENCE REQUIRED | Production monitoring / alerting evidence still missing. |

**B5-BLK-4 remains OPEN — a separate, Dan-authorized closure decision is required. The Physical
Multi-Database MVP remains mandatory and NOT complete.** The next step is that separate closure review;
this re-grounding does not perform or bypass it. No blocker above is CLOSED, COMPLETE, or RESOLVED.
