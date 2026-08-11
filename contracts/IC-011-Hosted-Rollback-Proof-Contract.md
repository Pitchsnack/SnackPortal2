# IC-011 — Hosted Rollback Proof Contract

**Status:** Draft / Proposed · **Phase:** Architecture Planning · **Type:** Contract-first specification (no implementation)
**Opened:** 2026-07-21 by **D-40 — Hosted Non-Production Rollback Proof** (Dan-authorized contract-authoring START-GATE), transitioning the B5-BLK-8 rollback proof from the accepted local, composed-core rehearsal (B5-BLK-8A / B5-BLK-8B) to a **hosted, non-production** rollback-proof design. **Revision:** IC-011-DRAFT-1.
**Amendment (2026-08-11, D-45 — Gateway-Free Controlled Local MVP Ingress Architecture; ratified by Dan):** §3's component-named topology rule — which made one named component the sole served ingress and treated every other served edge as a STOP condition — is **replaced**. The gate no longer names a component; it names an **approval property**. Only **architecture-approved public edge modules** may be served to client traffic, and the gate STOPs on an unapproved edge, an internal edge exposed publicly, a reintroduced generic dispatcher/proxy, a public route not owned by its serving service, or missing authentication / public-boundary enforcement. **Nothing else in IC-011 changes:** the hosted-staging / pre-production-only classes, the LIVE PRODUCTION prohibition, the physical multi-database topology, authentication-separate-from-routing, the Database-Router-sole-selector rule, the SecretRef-only registry, the rollback targets, the triggers, the evidence discipline, the verdict vocabulary, and the B5-BLK-8-stays-OPEN blocker rule are all preserved verbatim.
RFC-2119 keywords **MUST / MUST NOT / SHOULD / MAY** are used normatively.

> **Contract-first, no positive capability.** This is a **Draft / Proposed** contract. It **specifies and reserves**; it grants nothing, wires nothing, and provisions nothing. **No hosted environment, harness, IaC, workflow, database, or secret is created by this contract.** IC-011 becomes **Final** only after independent verification and human merge, and even then a hosted rollback proof executes only under a separate, explicitly-authorizing execution PRD and an explicit human START-GATE (Dan). The change-control order is **register → contract → code**. **B5-BLK-8 remains OPEN. The live blocker census remains 7 of 9 OPEN. Production remains NOT READY / DO-NOT-ACTIVATE.**

## Purpose (§1)
Govern the **hosted, non-production rollback proof** — the B5-BLK-8C stage that demonstrates the B5-BLK-8 rollback **mechanism** in a hosted (not local, not production) environment: a request served through the real ingress that induces a bounded, governed failure and is rolled back to a known-safe composition, proven physically isolated, non-destructive, and references-only. This contract specifies the environment, topology, authority, targets, triggers, evidence, and verdicts of that proof. It is the design authority for the hosted runbook `infrastructure/runbooks/b5_blk8c_hosted_rollback_proof.md` and the hosted extension of the evidence template `docs/runtime/b5_blk8_rollback_evidence_template.md`.

## Environment class (§2 — hosted, non-production only)
- **Hosted staging or hosted pre-production only.** The proof MUST run in a **HOSTED STAGING** or **HOSTED PRE-PRODUCTION** environment. These are the only two permitted hosted target classes.
- **LIVE PRODUCTION is prohibited.** A **LIVE PRODUCTION** target is prohibited. No live customer traffic, no live production database, and no production activation is in scope. A production-scoped rollback proof requires a separate, later, explicitly-authorized PRD.
- **Synthetic or approved non-production data only.** All records exercised MUST be **synthetic or approved non-production data**. No live customer row data is present or captured.

## Topology (§3 — physical multi-database, real ingress)
The hosted proof MUST compose the real, physically-separated multi-database topology behind the real served ingress:

- **One hosted Control DB.** Exactly **one hosted Control DB** holds the registry, routing metadata, and the Control-resident audit sink.
- **At least two physically distinct hosted Tenant DBs.** The proof MUST use **at least two physically distinct hosted Tenant DBs** (separate physical databases, never schemas), so isolation and adjacency can be proven.
- **Approved public edge modules as the only served ingress (amended 2026-08-11, D-45).** **Only architecture-approved public edge modules may be served to client traffic.** The set of approved public edges is the closed set ratified in [IC-010](IC-010-API-Gateway-Contract.md) §A.2; no other served edge, port, or bypass reaches the backend during the proof. Each served edge MUST satisfy IC-010 §A.1 in full — shared public-boundary security kernel, Auth-Router-delegated authentication, authority derived only from authenticated trusted state, one owned route family, no generic dispatch, fail-closed validation before business/database work, its own audit evidence, and one request → one active tenant → one database. **The proof STOPs on:** an **unapproved public edge**; an **internal edge exposed publicly**; a **generic dispatcher / proxy reintroduced as public ingress** (under any name); a **public route not owned by its serving service**; or **missing authentication / public-boundary enforcement**. *(Serving more than one approved public edge is expected under D-45 and is not, by itself, a STOP condition; serving an **unapproved** one always is.)*
- **Authentication separate from routing.** **Authentication is separate from routing** (D-01): the Authentication Router validates identity and never selects a database.
- **Database Router as sole database selector.** The **Database Router** is the **sole database selector** (D-07/D-30). No component other than the Router resolves the tenant database identity.
- **SecretRef-only registry.** The registry stores **SecretRef only** (D-14) — a `ref:...` descriptor, never a raw DSN, password, token, or credential. A **production-grade SecretRef backend** (not a scratch file store) resolves references at connect time.
- **One request → one active tenant → one database.** Every served request resolves to **one request → one active tenant → one database**. Multi-tenant access within a request is prohibited.
- **No cross-tenant fallback.** On any failure the Router fails closed with **no cross-tenant fallback** — it never silently routes to a second tenant's database.
- **Adjacent Tenant unchanged.** An **adjacent Tenant** (a second hosted Tenant DB not targeted by the trigger) MUST be proven **unchanged** across the whole proof (before == after), demonstrating isolation (D-30).

## Rollback targets (§4 — binding)
- **Primary hosted success target: last-known-good durable composition.** The proof's success target is a rollback to the pinned **last-known-good durable composition** — the previously-proven-good served composition, restored from its pinned reference set, with served health re-verified.
- **Emergency fail-closed target: deferred in-memory composition.** If restoration to the last-known-good durable composition cannot be safely achieved, the emergency fail-closed target is the **deferred in-memory composition** — the strongest existing fail-closed posture (`backend/control_plane/main.py` default; construction performs no I/O).
- **Deferred in-memory does not earn the hosted-proven verdict.** A proof that lands only on the **deferred in-memory composition** MUST NOT earn `ROLLBACK-PROVEN-HOSTED-NONPRODUCTION`. It MUST produce `ROLLBACK-NOT-PROVEN` plus an emergency-safe-state record documenting the fail-closed landing.

## Triggers (§5 — bounded, governed)
The proof induces exactly one bounded, governed post-activation failure. The two authorized triggers are:

- **Preferred — `secret_resolution_failure`.** A synthetic tenant is registered Ready with a SecretRef that intentionally fails to resolve; the served request resolves the Ready view, then the SecretRef fails, and the Router fails closed with no connection opened, no new pool key, and no cross-tenant fallback. The failure category and a reason **reference** are captured (never a secret value; D-14).
- **Fallback — `distinctness_regression`.** A synthetic distinctness collision across the two hosted Tenant DBs over the hosted Control DB's ledger, documented as the alternate.

No trigger outside these two governed categories is introduced. Each maps to a gate §7 post-activation check (identity mismatch, distinctness regression, router anomaly, secret-resolution failure).

## Backup and evidence discipline (§6)
- **Backup and restoration checkpoint.** Before any trigger, the proof MUST record a **backup and restoration checkpoint** — a references-only, digest-anchored record of the pre-state and the pinned last-known-good reference set sufficient to restore. No path, DSN, credential, or dump content is recorded; only a `ref:...` reference and a digest.
- **Durable references-only evidence.** The proof produces **durable references-only evidence** — the hosted extension of the 8A evidence template. Every field is references only: no DSN, no password, no token, no key material, no PII, no tenant business data, and no live customer row data.
- **Named operator and approver.** The evidence MUST record a **named operator** and a **named approver** (`OPERATOR_IDENTITY`, `APPROVER_IDENTITY`) — references only.
- **Single final write.** The authoritative evidence document is written **exactly once**, **after** restoration and temporary-object cleanup, so a failed run or a failed cleanup can never retain a false-PASS record.

## Verdicts (§7 — bounded vocabulary)
- **Allowed hosted verdicts:** `ROLLBACK-PROVEN-HOSTED-NONPRODUCTION` (the rollback mechanism proven in a hosted non-production environment) and `ROLLBACK-NOT-PROVEN` (the proof did not complete, or landed only on the emergency deferred in-memory composition).
- **Reserved and prohibited in B5-BLK-8C:** `ROLLBACK-PROVEN-PRODUCTION-SCOPE`. A production-scoped rollback claim MUST NOT be produced by B5-BLK-8C under any circumstance.

## Blocker effect (§8 — evidence only)
- **B5-BLK-8C produces evidence only.** This stage produces hosted rollback-proof evidence and nothing more.
- **B5-BLK-8C cannot close B5-BLK-8.** A `ROLLBACK-PROVEN-HOSTED-NONPRODUCTION` verdict does **not** close B5-BLK-8 and does not change the blocker census.
- **Only B5-BLK-8D may decide blocker effect.** Any change to B5-BLK-8's status or the census is a separate, later, Dan-authorized **B5-BLK-8D** governance-effect decision resting on captured evidence. **B5-BLK-8 remains OPEN; the live blocker census remains 7 of 9 OPEN; production remains NOT READY / DO-NOT-ACTIVATE.**

## Governing references (§9)
IC-001 (audit references-only) · IC-002 (tenant lifecycle / readiness) · IC-005 (auth references; authentication separate from routing) · IC-010 §A.1/§A.2 (the approved-public-edge definition and the closed ratified set) / §I,§M (client ingress only through the route-owning public edge) / §H (Router boundary; the Database Router performs no identity authentication) · D-07 (registry-authoritative routing) · D-14 (SecretRef only) · D-24 (non-destructive retention) · D-30 (cross-tenant isolation) · **D-40** (this contract's governing decision) · **D-45** (the Gateway-free public-edge boundary this contract's §3 was amended to). The accepted local rollback scaffold (`infrastructure/runbooks/b5_blk8_rollback_to_deferred_composition.md`) and rehearsal (`infrastructure/runbooks/controlled_rollback_rehearsal.md`) are referenced as the local-proof predecessors; IC-011 governs the hosted stage only and restates neither.

## Guard (§10)
This contract is pinned by `backend/tests/architecture/test_b5_blk8c_hosted_rollback_contract_boundaries.py` — the Draft / Proposed contract-first posture, the hosted-staging / pre-production-only classes, the LIVE PRODUCTION prohibition, the physical multi-database topology, the **approved-public-edge-only served-ingress rule with its five STOP conditions** and the auth/routing-separation boundary, the SecretRef-only registry, the exact rollback targets, the exact triggers, the named operator and approver, the references-only single-final-write evidence discipline, the exact verdict vocabulary, and the B5-BLK-8-stays-OPEN-until-B5-BLK-8D blocker rule. The guard closes no blocker and implements nothing.
