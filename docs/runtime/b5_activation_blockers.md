# PRD 06 B-5 — Production Activation Blocker Register

**Gate posture: NOT READY.** Production runtime activation is **blocked** while any blocker below is OPEN. Default is
conservative: missing evidence ⇒ OPEN ⇒ activation blocked. This register is grounded in the **actual** current state
(re-grounded 2026-07-12 at `fff215b5bd004760ea0d81915c3d93ca128673ed`; decision baseline `origin/main @ 84882c77cfe409bab0af454b4411cf65795bcbfd`, B5-E closure decision 2026-07-12); production is far off by design.

| ID | Description | Severity | Owner | Evidence required | Status | Blocks activation |
|----|-------------|----------|-------|-------------------|--------|-------------------|
| **B5-BLK-1** | `backend/control_plane/main.py` runtime wiring is deferred (`NotImplementedError`; default `in_memory`). The durable/real adapters exist (B-2/B-4) but are not constructed at runtime. | Critical | Control Plane | A separately-authorized runtime-activation phase that flips the deferral under the gate, with the regression lock consciously updated. | OPEN | YES |
| **B5-BLK-2** | No production Control DB / Tenant DB fleet provisioned. B-3 was docs/scaffold-only; D-15 IaC has not been executed against production. | Critical | Infra / Control Plane | Provisioned, physically-distinct Control + per-tenant DBs in the target environment, with identity proof. | OPEN | YES |
| **B5-BLK-3** | No production secret store wired. The D-14 reference-based abstraction exists; the default provider is `EnvReferenceSecretStore`. | Critical | Infra | A production-grade pluggable secret store resolving `*_REF` references at connect time; references only. | OPEN | YES |
| **B5-BLK-4** | Provisioning audit sink — B-6 machinery built on `main` (#21 / #23 / #25), durable behavior live-proven (B-7A #24), runtime selector wiring landed (B-7B #25) and exercised over the standing Control DB (B5-4 #72 / B5-4A #74 / Smoke C V2 #75). The durable routing audit (DBR-AR-2) was a separate follow-on outside this row's evidence bar; see the DBR-AR-2 closure record below (Dan-authorized governance decision, 2026-07-16). | Major | Control Plane | Evidence captured at the pre-deployment stage: audit sink available and wired for the controlled non-production standing environment; AT-D15T1-3 HARD-GATE satisfied (Smoke C V2). Production-environment availability stays a gate §5 activation condition — not waived. | **CLOSED (B5-E, 2026-07-12, Dan-authorized) — EVIDENCE-BOUND GOVERNANCE DECISION** | NO (B5-E) — the gate §5 audit-sink condition still binds at activation time |
| **B5-BLK-5** | Frontend on interim Supabase/RLS; Lovable → API-Gateway cutover pending (DRIFT-01). | Major | Frontend / Gateway | Lovable integrates only through the API Gateway; no direct frontend DB/Supabase calls. | OPEN | YES |
| **B5-BLK-6** | IC-009 portal contracts and IC-007 cross-tenant contracts runtime-bound at the composed Gateway core and served edge (R6-1 to R6-4); positive IC-007 sharing out of scope by adopted contract (R6-5). | Major | Architecture | Portal/cross-tenant contracts bound to runtime behavior under the Gateway (met). | **CLOSED (B5-BLK-6 governance-effect closure, 2026-07-20, Dan-authorized) — RUNTIME-BINDING GOVERNANCE DECISION** | NO |
| **B5-BLK-7** | Production migration / DDL readiness evidence missing (D-17). | Major | Infra / Control Plane | Reviewed DDL applied (blob-pinned) within the supported schema range; version-gated readiness proven. | OPEN | YES |
| **B5-BLK-8** | Production rollback evidence missing. | Major | Control Plane | A proven, isolated, non-destructive rollback to the deferred composition. | OPEN | YES |
| **B5-BLK-9** | Production monitoring / alerting evidence missing. | Minor | Ops | Monitoring + alerting in place for the activated runtime path. | OPEN | YES |

## Rules

```
A blocker is closed ONLY when its required evidence is captured (see b5_activation_evidence_template.md) and approved.
While any blocker is OPEN, the Production Runtime Activation Gate decision is DO-NOT-ACTIVATE (NOT READY).
B-5 changes none of these to closed: B-5 builds the gate; it does not activate runtime or provision production.
```

**Current standing decision: NOT READY (7 / 9 blockers OPEN; B5-BLK-4 CLOSED per Decision A, B5-E, 2026-07-12; B5-BLK-6 CLOSED per the B5-BLK-6 governance-effect closure, 2026-07-20).**

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

> **⚠️ AUTHFIX-B correction (Gate A).** The row `Standing authentication memberships + non-Ready
> b5_standing_dormant tenant — SATISFIED` records what B5-4A / PR #74 delivered and is correct as
> merged history. It is **not** a statement of current standing state: that subject state was
> replaced around **2026-07-21** by the four-cluster standing fixture, and the harness that verified
> it is SUPERSEDED (AUTHFIX-B). No blocker status changes as a result of this note.

### Blocker evidence taxonomy (B5-BLK-4 CLOSED per B5-E and B5-BLK-6 CLOSED per the 2026-07-20 governance-effect closure; every remaining blocker REMAINS OPEN — the gate stays DO-NOT-ACTIVATE)

| Blocker | Evidence taxonomy | Re-grounded note |
|---|---|---|
| **B5-BLK-1** | OPEN — GOVERNANCE DECISION REQUIRED | The composed runtime path is proven locally (Smoke C V2, database granularity), but `main.py`'s in-memory default deferral is intact by design; flipping it is a separately-authorized decision. |
| **B5-BLK-2** | OPEN — DEPLOYMENT EVIDENCE REQUIRED | Physical distinctness proven **at database granularity** locally (B5-4/B5-4A/Smoke C V2); production fleet + cluster-level distinctness not provisioned. |
| **B5-BLK-3** | OPEN — DEPLOYMENT EVIDENCE REQUIRED | D-14 reference secret-store + local file/env materialization exercised locally; a production-grade store is not wired. |
| **B5-BLK-4** | SATISFIED BY GOVERNANCE DECISION — CLOSED (B5-E, 2026-07-12, Dan-authorized) | B-6 provisioning audit sink (#21), B-7 durable store (#23), B-7A live-PG exercise (#24) and B-7B runtime wiring (#25) landed on `main`; standing-environment wiring exercised (B5-4 #72 / B5-4A #74 / Smoke C V2 #75); AT-D15T1-3 HARD-GATE satisfied. That separate Dan-authorized closure review has now been performed and recorded as B5-E. The durable **routing** audit (DBR-AR-2) was a separate follow-on outside this row's evidence bar; see the DBR-AR-2 closure record below. **Smoke C V2 including Fix R3 does not itself close B5-BLK-4 — the closure is the separate B5-E governance decision.** |
| **B5-BLK-5** | OPEN — PRODUCT/INTEGRATION TRACK | Lovable interim Supabase/RLS; API-Gateway cutover pending (DRIFT-01) — separate track. |
| **B5-BLK-6** | CLOSED (governance-effect closure, 2026-07-20, Dan-authorized) | IC-009 portal / IC-007 cross-tenant contracts runtime-bound at the composed Gateway core and served edge (R6-1 to R6-4); positive IC-007 sharing out of scope by adopted contract (R6-5). |
| **B5-BLK-7** | OPEN — DEPLOYMENT EVIDENCE REQUIRED | Production migration / DDL readiness evidence still missing (D-17). |
| **B5-BLK-8** | OPEN — DEPLOYMENT EVIDENCE REQUIRED | Production rollback evidence still missing. |
| **B5-BLK-9** | OPEN — DEPLOYMENT EVIDENCE REQUIRED | Production monitoring / alerting evidence still missing. |

## B5-E closure decision record (2026-07-12)

Decision baseline: `origin/main @ 84882c77cfe409bab0af454b4411cf65795bcbfd` (B5-E, 2026-07-12).

**Decision A (B5-E, 2026-07-12, Dan-authorized): B5-BLK-4 — CLOSED — EVIDENCE-BOUND GOVERNANCE DECISION.**
**Decision B (B5-E, 2026-07-12, Dan-authorized): Physical Multi-Database MVP — ACCEPTED AT DATABASE GRANULARITY.**

MVP acceptance at database granularity is not cluster-level proof, not production deployment, not production activation, not Lovable cutover, not billing completion, and not AI Agent completion.
The Physical Multi-Database MVP mandate (IC-010 §O) remains mandatory and binding; acceptance at database granularity does not weaken it.
Cluster-level distinctness remains deployment scope (AT-D15T1-4; held by B5-BLK-2).
DBR-AR-2 — CLOSED (Dan-authorized governance decision, 2026-07-16); this closure closes zero B5 activation blockers, the blocker census remains nine with 8 of 9 OPEN, and production remains NOT READY / DO-NOT-ACTIVATE.
DBR-AR-2 (durable routing audit) was a separate Database Router follow-on; it was not part of the B5-BLK-4 closure evidence bar (see the B5-E record) and its status was unchanged by the B5-E decision.
Production runtime activation remains NOT READY / DO-NOT-ACTIVATE — 7 of 9 activation blockers remain OPEN; the B5-E closure of B5-BLK-4 changes no other blocker and does not make the gate ready.
The gate §5 activation condition "provisioning audit sink available (B-6) — or an explicit, approved waiver" remains binding at activation time and is not waived by the B5-E closure.
Historical slice documents (SMOKE-C-SPEC-01 §9, the B-6/B-7/B-7B blocker notes, runbook no-overclaim blocks, and contract status lines) retain their authoring-time open-status wording for B5-BLK-4 by design; the three live B5 gate documents are the blocker authority, and those frozen lines are superseded by the B5-E record.
Next step: the next Dan-authorized governed slice; every remaining activation blocker is deployment-scope (B5-BLK-2/3/7/8/9) or product/integration-track (B5-BLK-5/6), and the DBR-AR-2 durable-routing-audit follow-on is governed by its closure record (Dan-authorized governance decision, 2026-07-16) — no further DBR-AR-2 slice is authorized.
The 2026-07-12 re-grounding itself neither performs nor bypasses this decision; the decision is the separate B5-E record above.
