# B5-BLK-8A — Production Rollback to the Deferred (In-Memory) Composition (operator runbook)

**Scope:** NON-PRODUCTION / MANUAL_ONLY — documentation-only evidence scaffold (PRD B5-BLK-8A).
Closes no blocker; B5-BLK-8 remains OPEN.

**Standing rules (inherited from `infrastructure/runbooks/README.md`):** secret references only
(D-14 — never a DSN, password, token, or credential in this document, a shell echo, or any evidence
artifact); fail-closed (any missing or ambiguous proof stops the procedure); **no runtime DDL**;
**no production execution** — production rollback is deferred to a later, separately-authorized phase.

---

## 1. Purpose & non-goals

This runbook documents the **reviewed, non-executable** operator procedure for rolling a runtime
activation back to the deferred (in-memory) composition, and it points at the references-only evidence
template `docs/runtime/b5_blk8_rollback_evidence_template.md` that a later, separately-authorized
rehearsal (B5-BLK-8B) fills exactly once.

**Non-goals — this slice performs none of them:** no executed rollback; no runtime source change; no
database, Docker, or secret access; no runtime DDL; **no blocker closure**; **no census change**; no
production. This scaffold is documentation plus an architecture guard only.

## 2. Rollback target — the deferred (in-memory) composition

Rollback returns the system to the **deferred (in-memory) composition** — the live default of
`backend/control_plane/main.py`, where the `SP2_CP_*` composition selectors are unset or set to
`in_memory`, **construction performs no I/O**, and references resolve per-operation and fail closed
(activation gate §2). This in-memory default is the strongest existing fail-closed posture: it
constructs no durable or real adapter and reaches no database. Rollback therefore means *returning to
this in-memory posture*, never advancing past it. (Authority: activation gate §2 and §7.)

## 3. Trigger conditions

Rollback is required when any **gate §7 post-activation check** fails. The four authoritative gate §7
post-activation triggers are:

- **identity mismatch**
- **distinctness regression**
- **router anomaly**
- **secret-resolution failure**

The following adjacent conditions may also motivate a rollback but are **labeled by their grounding**
and are never presented as gate §7 post-activation checks:

- **audit-sink unavailable** — gate §6 activation input.
- **migration/readiness failure** — gate §6 / §5 activation input.
- **monitoring or health regression** — B5-BLK-9 scope (not a gate §7 post-activation check).
- **operator-directed abort** — gate §8 human-approval discipline.

No trigger outside these grounded categories is introduced.

## 4. Rollback procedure (MANUAL_ONLY)

This procedure is **MANUAL_ONLY** — it is never wired into the default test suite, the hosted
live-PostgreSQL workflow, or any automated path. Deterministic steps:

1. **Detect the trigger** — observe one of the gate §7 post-activation checks failing.
2. **Record the failure** — capture the failure and its **trigger reason** into the references-only
   evidence record; see §6.
3. **Disable the activation switch** — unset the `SP2_CP_*` selectors (or set them to `in_memory`),
   returning composition to the deferred (in-memory) default; **construction performs no I/O**.
4. **Return to the deferred (in-memory) composition** — confirm the runtime constructs no durable or
   real adapter and reaches no database.
5. **Verify non-destructive isolation** — confirm the affected tenant's data is unchanged
   (`before == after`) and that adjacent tenants were never touched.
6. **Capture evidence** — populate the references-only template (§7).

The procedure is **per-tenant** and **isolated** (D-30) and applies **no runtime DDL**.

## 5. Non-destructive & isolation guarantees

- **D-24 — non-destructive.** Rollback is **non-destructive**: it **never deletes tenant business
  data**. Retention follows D-24 — policy-driven expiry only, via tombstones, operationally audited.
- **D-30 — per-tenant isolation.** Rollback is **per-tenant** and **isolated**:
  one request → one active tenant → one database; no cross-tenant connection reuse and no cross-tenant
  joins, ever.
- **D-14 — references only.** Every secret is expressed as a reference (`*_REF=ref:...`); no DSN,
  password, token, key material, PII, or tenant business data appears in this runbook or in any
  evidence record built from it.

## 6. Failure recording

On any trigger, the rollback **records the failure** and its **trigger reason** as a references-only
evidence entry (`FAILURE_RECORD_REF`, `ROLLBACK_TRIGGER`). The durable audit home for the failure
event is the separately-governed operational-audit surface; this scaffold names the reference only and
persists nothing.

## 7. Evidence capture

Each executed rollback — performed in B5-BLK-8B, never in B5-BLK-8A — produces exactly one record
built from `docs/runtime/b5_blk8_rollback_evidence_template.md`. Every field is references only; no raw
secret, DSN, PII, or tenant business data is ever captured.

## 8. What this runbook does and does NOT prove (binding non-claims)

**Proves:** a reviewed, safe, non-destructive, per-tenant-isolated rollback procedure and a
references-only evidence schema exist.

**Does NOT prove:** no rollback has been executed; no database or Docker execution occurred; this
scaffold is not a production proof and does not authorize activation. **B5-BLK-8 remains OPEN.** The
live blocker census remains **7 of 9 OPEN**. Production remains **NOT READY / DO-NOT-ACTIVATE**.

## 9. Guards

This scaffold is pinned by
`backend/tests/architecture/test_b5_blk8_rollback_evidence_scaffold_boundaries.py` — the MANUAL_ONLY /
non-production posture, the rollback-to-in-memory requirement, the four gate §7 triggers, the D-24 and
D-30 disciplines, failure recording, references-only secret hygiene, and the preserved
B5-BLK-8-OPEN / 7-of-9 / DO-NOT-ACTIVATE locked state. The guard closes no blocker.
