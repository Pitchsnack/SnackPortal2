# B5-BLK-8C — Hosted Non-Production Rollback Proof (operator runbook)

**Labels:** `MANUAL_ONLY` · `HOSTED NON-PRODUCTION ONLY` · `DAN START-GATE REQUIRED` · `NO LIVE PRODUCTION`

**Scope:** the reviewed, non-executable operator procedure for the **B5-BLK-8C hosted, non-production rollback proof** — inducing one bounded, governed post-activation failure against a hosted, physically-separated multi-database topology behind the real approved public edges, and rolling back to the pinned **last-known-good durable composition** (emergency fail-closed target: the **deferred in-memory composition**). Governed by **IC-011 — Hosted Rollback Proof Contract** and **D-40**. This runbook authorizes nothing on its own; each execution requires an explicit human **DAN START-GATE**. This stage **closes no blocker**: **B5-BLK-8 remains OPEN**; the live blocker census remains **7 of 9 OPEN**; production remains **NOT READY / DO-NOT-ACTIVATE**. **LIVE PRODUCTION is prohibited.**

**References (normative — DO NOT restate):**

- `contracts/IC-011-Hosted-Rollback-Proof-Contract.md` — the hosted environment, topology, authority, targets, triggers, evidence, and verdict law. This runbook references it and restates none of it.
- `infrastructure/runbooks/b5_blk8_rollback_to_deferred_composition.md` — the reviewed rollback **semantics** (the deferred in-memory rollback target, the four gate §7 triggers, the D-24 non-destructive and D-30 per-tenant-isolation disciplines, references-only failure recording).
- `infrastructure/runbooks/controlled_rollback_rehearsal.md` — the accepted **local** composed-core rehearsal (the predecessor proof). The hosted stage is a distinct, separately-authorized proof.

**Standing rules (inherited from `infrastructure/runbooks/README.md`):** secret references only (D-14 — never a DSN, password, token, or credential in this document, a shell echo, or any evidence artifact); fail-closed (any missing or ambiguous proof stops the procedure); **no runtime DDL** outside the explicit, governed hosted apply; **HOSTED NON-PRODUCTION ONLY** — a **LIVE PRODUCTION** target is never permitted. The registry stores `SecretRef` only (a production-grade backend resolves it at connect time); the Database Router alone resolves the tenant database identity; one request → one active tenant → one database; the target never reaches the adjacent tenant.

---

## 1. Authority & environment (record before execution)

| Item | Value |
|---|---|
| **Operator** | a named operator (`OPERATOR_IDENTITY`; references only) |
| **Approver** | a named approver (`APPROVER_IDENTITY`; references only) |
| **DAN START-GATE** | required in writing per execution; no standing authorization exists |
| **Hosted target class** | `HOSTED STAGING` or `HOSTED PRE-PRODUCTION` (the only permitted classes; **LIVE PRODUCTION prohibited**) |
| **Data** | synthetic or approved non-production data only (no live customer row data) |
| **Success target** | last-known-good durable composition |
| **Emergency fail-closed target** | deferred in-memory composition (earns `ROLLBACK-NOT-PROVEN` + an emergency-safe-state record; never `ROLLBACK-PROVEN-HOSTED-NONPRODUCTION`) |

## 2. Entrypoint (MANUAL_ONLY)

Any executable proof step runs through the sanctioned standalone `_pg.run` entrypoint (`python backend/tests/control_plane/requires_pg/_pg.py ...`), **never** an ad-hoc `pytest` invocation that would error for a missing `admin_dsn` fixture — unless a separately authorized real pytest fixture exists. The hosted proof is **MANUAL_ONLY**: it is never wired into the default test suite, the hosted live-PostgreSQL workflow, or any automated path.

## 3. Phases H0–H13

Each phase records: **operator** (who acts), **control surface** (what they act through), **inputs**, **expected result**, **failure result** (fail-closed — STOP), **evidence** (references only), and **cleanup obligation**.

### H0 — Authority and identity lock
- **Operator:** named operator, under the DAN START-GATE. **Control surface:** this runbook + IC-011.
- **Inputs:** the written DAN START-GATE; `OPERATOR_IDENTITY`; `APPROVER_IDENTITY`; the chosen hosted target class.
- **Expected:** authority, operator, and approver recorded; target class ∈ {`HOSTED STAGING`, `HOSTED PRE-PRODUCTION`}.
- **Failure:** absent START-GATE, unnamed operator/approver, or a `LIVE PRODUCTION` target → STOP; nothing is provisioned.
- **Evidence:** `OPERATOR_IDENTITY`, `APPROVER_IDENTITY`, `EXECUTION_WINDOW`, `HOSTED_TARGET_CLASS`.
- **Cleanup:** none (no resource created).

### H1 — Environment and topology census
- **Operator:** named operator. **Control surface:** the hosted control plane inventory (references only).
- **Inputs:** the hosted Control DB identity reference; the ≥2 physically distinct hosted Tenant DB identity references.
- **Expected:** exactly one hosted Control DB and at least two physically distinct hosted Tenant DBs are present; **only architecture-approved public edge modules may be served to client traffic** (IC-011 §3 as amended by D-45; the closed set is IC-010 §A.2); the Database Router is the sole selector; authentication is separate from routing.
- **Failure:** fewer than two distinct Tenant DBs, or a routing/auth conflation → STOP. **Also STOP on** an unapproved public edge, an internal edge exposed publicly, a generic dispatcher / proxy reintroduced as public ingress, a public route not owned by its serving service, or missing authentication / public-boundary enforcement.
- **Evidence:** `CONTROL_DB_IDENTITY_REF`, `TENANT_DB_IDENTITY_REFS`.
- **Cleanup:** none.

### H2 — Backup / recovery checkpoint
- **Operator:** named operator. **Control surface:** the hosted backup facility (references only).
- **Inputs:** the pinned last-known-good reference set; the pre-state to checkpoint.
- **Expected:** a references-only, digest-anchored backup and restoration checkpoint exists; no path, DSN, credential, or dump content is recorded.
- **Failure:** no restorable checkpoint → STOP (a rollback proof without a restore point is refused).
- **Evidence:** `ROLLBACK_FROM_STATE_REF`, `LAST_KNOWN_GOOD_REVISION_REF`.
- **Cleanup:** the checkpoint is a hosted temporary object disposed at H12.

### H3 — Synthetic proof identities
- **Operator:** named operator. **Control surface:** the registry (SecretRef only) + Database Router.
- **Inputs:** a synthetic target tenant; a synthetic adjacent tenant; approved non-production data only.
- **Expected:** synthetic identities seeded; SecretRef descriptors are `ref:...` only; no live customer data present.
- **Failure:** any live or non-approved data, or a raw secret value → STOP.
- **Evidence:** `TENANT_SCOPE`, `ADJACENT_TENANT_SCOPE`.
- **Cleanup:** synthetic identities disposed at H12.

### H4 — Pre-state digests and served-health baseline
- **Operator:** named operator. **Control surface:** the served public edges' health paths + a digest tool.
- **Inputs:** the served composition; the target and adjacent tenant states.
- **Expected:** `BEFORE_DATA_DIGEST` for the target; an adjacent-tenant digest; a served-health baseline captured through **every** served public edge.
- **Failure:** an unhealthy baseline or an unreadable pre-state → STOP.
- **Evidence:** `BEFORE_DATA_DIGEST`, `SERVED_HEALTH_BASELINE_REF`, `SECRET_BINDING_SET_DIGEST`, `MIGRATION_SET_DIGEST`, `AUDIT_SINK_IDENTITY_REF`.
- **Cleanup:** none.

### H5 — Bounded trigger induction
- **Operator:** named operator. **Control surface:** the served approved public edges (the only served client ingress).
- **Inputs:** the preferred `secret_resolution_failure` trigger (or the documented `distinctness_regression` fallback), applied to the target tenant only.
- **Expected:** exactly one bounded, governed post-activation failure is induced against the target; the adjacent tenant is not touched.
- **Failure:** an out-of-scope trigger, or any effect on the adjacent tenant → STOP.
- **Evidence:** `ROLLBACK_TRIGGER`, `FAILURE_STATE_REF`.
- **Cleanup:** none (the induced failure is observed, not persisted).

### H6 — Governed failure observation
- **Operator:** named operator. **Control surface:** the Database Router fail-closed path + Control-resident audit sink.
- **Inputs:** the induced failure from H5.
- **Expected:** the Router fails closed — no connection opened, no new pool key, no cross-tenant fallback; the failure category and a reason **reference** are recorded (never a secret value).
- **Failure:** any cross-tenant fallback, opened connection, or leaked secret shape → STOP.
- **Evidence:** `FAILURE_RECORD_REF`, `AUDIT_RECORD_REF`.
- **Cleanup:** none.

### H7 — Rollback to last-known-good durable composition
- **Operator:** rollback decision-maker (Dan or a Dan-designated operator). **Control surface:** the hosted composition control + the pinned last-known-good reference set.
- **Inputs:** `LAST_KNOWN_GOOD_REVISION_REF`; the H2 checkpoint.
- **Expected:** the served composition is restored to the pinned **last-known-good durable composition**. If restoration cannot be safely achieved, the **emergency fail-closed target** is the **deferred in-memory composition**, and the verdict becomes `ROLLBACK-NOT-PROVEN` with an emergency-safe-state record.
- **Failure:** an unpinned or ambiguous last-known-good set → fail closed to the deferred in-memory composition; record `ROLLBACK-NOT-PROVEN`.
- **Evidence:** `POST_ROLLBACK_REF`.
- **Cleanup:** none.

### H8 — Served-path verification
- **Operator:** named operator. **Control surface:** the served approved public edges.
- **Inputs:** the restored composition.
- **Expected:** a served request through the route-owning public edge resolves one request → one active tenant → one database against the restored last-known-good composition; served health matches the H4 baseline on every served edge.
- **Failure:** a served regression, a wrong-database route, or a health mismatch → STOP; record `ROLLBACK-NOT-PROVEN`.
- **Evidence:** `SERVED_HEALTH_BASELINE_REF` (post), `POST_ROLLBACK_REF`.
- **Cleanup:** none.

### H9 — Adjacent and non-destructive verification
- **Operator:** named operator. **Control surface:** the Database Router + digest tool.
- **Inputs:** the adjacent tenant; the target `BEFORE_DATA_DIGEST`.
- **Expected:** `AFTER_DATA_DIGEST == BEFORE_DATA_DIGEST` for the target; the adjacent tenant is proven **unchanged** (before == after); rollback deleted no tenant business data (D-24); isolation held (D-30).
- **Failure:** any digest drift or adjacent-tenant change → STOP; `ISOLATION_ASSERTION = FAIL` / `NON_DESTRUCTIVE_ASSERTION = FAIL`.
- **Evidence:** `AFTER_DATA_DIGEST`, `ISOLATION_ASSERTION`, `NON_DESTRUCTIVE_ASSERTION`.
- **Cleanup:** none.

### H10 — Restoration / roll-forward
- **Operator:** named operator. **Control surface:** the hosted composition control.
- **Inputs:** the H2 checkpoint; the last-known-good reference set.
- **Expected:** the hosted environment is restored / rolled forward to its pinned pre-proof state; the served path is healthy.
- **Failure:** an incomplete restoration → STOP; escalate to the approver.
- **Evidence:** `RESTORATION_REF`.
- **Cleanup:** stages the H12 disposal.

### H11 — Final hosted census
- **Operator:** named operator. **Control surface:** the hosted control plane inventory.
- **Inputs:** the H1 census.
- **Expected:** the hosted topology matches the H1 census; no orphaned proof object remains except those disposed at H12.
- **Failure:** an unexpected residual object → STOP; escalate.
- **Evidence:** `POST_ROLLBACK_REF`, `RESTORATION_REF`.
- **Cleanup:** feeds H12.

### H12 — Temporary-object cleanup
- **Operator:** named operator. **Control surface:** the hosted lifecycle control.
- **Inputs:** the synthetic identities (H3), the checkpoint (H2), and any temporary proof object.
- **Expected:** every temporary proof object is disposed; a retained-temporary count of **0** is asserted; no standing, staging-shared, or production database is touched.
- **Failure:** any retained temporary object → STOP; escalate; do not write the authoritative evidence.
- **Evidence:** `CLEANUP_REF`.
- **Cleanup:** this phase **is** the cleanup; it is deterministic and completes before H13.

### H13 — Evidence finalization
- **Operator:** evidence recorder (may be the operator). **Control surface:** the references-only evidence template.
- **Inputs:** every reference captured in H0–H12.
- **Expected:** exactly **one** authoritative references-only evidence document is written **outside the repository**, **after** H10 restoration and H12 cleanup — the single-final-write discipline, so a failed run or failed cleanup can never retain a false-PASS record. `FINAL_VERDICT ∈ {ROLLBACK-PROVEN-HOSTED-NONPRODUCTION, ROLLBACK-NOT-PROVEN}`.
- **Failure:** any secret shape, live customer row data, or a premature write → STOP; discard; record `ROLLBACK-NOT-PROVEN`.
- **Evidence:** the finalized hosted record (the 8A template hosted extension).
- **Cleanup:** none (cleanup completed at H12; the evidence lives outside the repository).

## 4. Verdicts (from IC-011 §7)

- `ROLLBACK-PROVEN-HOSTED-NONPRODUCTION` — the hosted rollback mechanism proven against the last-known-good durable composition in a hosted non-production environment.
- `ROLLBACK-NOT-PROVEN` — the proof did not complete, or landed only on the emergency **deferred in-memory composition**.
- `ROLLBACK-PROVEN-PRODUCTION-SCOPE` is **reserved and prohibited** in B5-BLK-8C; it is never produced.

## 5. Forbidden (never part of any run or recovery)

```text
executing without an explicit human DAN START-GATE
selecting a LIVE PRODUCTION target, live customer traffic, or live customer row data
storing a raw DSN, password, token, or credential in the registry or any evidence artifact
serving any edge that is not an architecture-approved public edge module (IC-010 §A.2) — including an internal edge
exposed publicly, a reintroduced generic dispatcher/proxy under any name, or a public route not owned by its serving
service — or letting the Router select more than one database
any cross-tenant fallback, or any change to the adjacent tenant
deleting tenant business data, or any destructive recovery outside disposing temporary proof objects
writing the authoritative evidence before H10 restoration and H12 cleanup complete
claiming ROLLBACK-PROVEN-PRODUCTION-SCOPE, or treating a hosted proof as readiness for production or as blocker closure
```

## 6. Locked state (unchanged by this runbook and by any record built from it)

This proof **closes no blocker**. **B5-BLK-8 remains OPEN.** The live blocker census remains **7 of 9 OPEN**. Production remains **NOT READY / DO-NOT-ACTIVATE**. B5-BLK-8C **produces evidence only**; only a later, Dan-authorized **B5-BLK-8D** governance-effect decision may determine any blocker effect on B5-BLK-8's status or the census.

## 7. Guard

This runbook is pinned by `backend/tests/architecture/test_b5_blk8c_hosted_rollback_contract_boundaries.py` — the four labels, the hosted-staging / pre-production-only classes and LIVE PRODUCTION prohibition, the ordered H0–H13 phases, the exact rollback targets and triggers, the named operator and approver, the `_pg.run` entrypoint guidance, references-only secret hygiene, and the preserved B5-BLK-8-OPEN / 7-of-9 / DO-NOT-ACTIVATE locked state. The guard closes no blocker.
