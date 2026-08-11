# PRD 06 B-7 — Provisioning Audit Durable Store Blocker Note

**B-7 REDUCES `B6-BLK-2` but does NOT close `B5-BLK-4`.** B-7 authors the missing **DDL** for the existing `control_audit`
table (created-not-applied) — it does **not** apply the DDL, wire runtime, or provision a production sink. Conservative:
while any sub-blocker below is OPEN, B5-BLK-4 stays **OPEN**.

> Cross-references (read-only; **not edited by B-7**):
> - `docs/runtime/b5_activation_blockers.md` — row **B5-BLK-4** ("Provisioning audit sink not built (B-6 deferred)", Major,
>   Control Plane, **OPEN**).
> - `docs/runtime/b6_provisioning_audit_blockers.md` — **B6-BLK-2** ("Durable audit-table DDL not applied (future
>   `infrastructure/db/control/**`)"). B-7 **reduces** B6-BLK-2: the DDL is now **authored** (created-not-applied); applying +
>   wiring + production remain OPEN.

---

## B6-BLK-2 standing after B-7

| ID | Description | Severity | Owner | Evidence required | Status | Blocks activation |
|----|-------------|----------|-------|-------------------|--------|-------------------|
| **B6-BLK-2** | Durable audit-table DDL: B-7 **authors** `control_audit` DDL (created-not-applied); **applying** it remains a separate gate. | Major | Infra / Control Plane | Reviewed DDL **applied** (blob-pinned) in the target environment (live-PG exercise = B-7A). | **OPEN** (reduced) | YES |

## Remaining OPEN sub-blockers (keep B5-BLK-4 OPEN)

| ID | Description | Severity | Owner | Evidence required | Status | Blocks activation |
|----|-------------|----------|-------|-------------------|--------|-------------------|
| **B7-BLK-1** | DDL not applied (`002`/`003` created-not-applied). | Major | Infra / Control Plane | DDL applied + exercised live (B-7A). | OPEN | YES |
| **B7-BLK-2** | Runtime sink not wired (`postgres_store` durable adapter default-off; in-memory default). | Major | Control Plane | A separately-gated runtime-activation phase wires the durable store, preserving fail-closed. | OPEN | YES |
| **B7-BLK-3** | Production sink reference not configured. | Major | Infra | A production sink resolving `*_REF` references at connect time; references only. | OPEN | YES |
| **B7-BLK-4** | Fail-closed required-write not runtime-wired. | Major | Control Plane | Wiring honors the B-6 fail-closed contract. | OPEN | YES |
| **B7-BLK-5** | Retention / redaction / hash policies not production-approved (hash optional/forward). | Minor | Control Plane / Ops | Approved policies referenced by `*_REF`. | OPEN | YES |
| **B7-BLK-6** | Frontend / public-edge cutover not complete. | Major | Frontend / public edges | Lovable integrates only through the approved authenticated public edges — under **D-45** that is **two origins**, not one (IC-010 §Y). | OPEN | YES |

## Rules

```
B-7 supplies the control_audit DDL (created-not-applied) + docs + additive tests; it does NOT close B5-BLK-4.
While any B7-BLK-* / B6-BLK-2 above is OPEN, B5-BLK-4 stays OPEN and production runtime activation remains DO-NOT-ACTIVATE.
B-7 makes NO production-readiness claim. The B-5 register (b5_activation_blockers.md) remains the canonical activation gate.
```
