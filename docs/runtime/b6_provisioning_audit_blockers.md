# PRD 06 B-6 — Provisioning Audit Sink Blocker Note

**B-6 REDUCES but does NOT close `B5-BLK-4`.** B-6 delivers only the durable provisioning-audit-**sink CONTRACT** (+
reference template + additive tests). Runtime wiring, a durable audit-table (DDL), and a production sink remain **OPEN**
sub-blockers behind separate, governed gates. This note is **conservative**: while any sub-blocker is OPEN, B5-BLK-4
stays **OPEN**.

> Cross-reference (read-only; **not edited by B-6**): `docs/runtime/b5_activation_blockers.md` — row **B5-BLK-4**
> ("Provisioning audit sink not built (B-6 deferred)", Major, Control Plane, **OPEN**). B-6 does not edit that register;
> B5-BLK-4 is cleared only when its required evidence (a built + wired + durable production sink, or an approved waiver)
> is captured and approved in a later phase.

---

## B5-BLK-4 standing after B-6

| ID | Description | Severity | Owner | Evidence required | Status | Blocks activation |
|----|-------------|----------|-------|-------------------|--------|-------------------|
| **B5-BLK-4** | Provisioning audit sink not built (B-6 deferred). | Major | Control Plane | A built + wired + durable production sink (or an explicit approved waiver). B-6 supplies the **contract**, not the wiring. | **OPEN** (reduced) | YES |

## B-6 sub-blockers (decomposition of "what's still missing for a production sink")

These are the OPEN items that keep B5-BLK-4 OPEN. They are de-duplicated against the existing B-5 register (B5-BLK-1/2/3
runtime wiring & DB/secret provisioning are tracked there and not restated here).

| ID | Description | Severity | Owner | Evidence required | Status | Blocks activation |
|----|-------------|----------|-------|-------------------|--------|-------------------|
| **B6-BLK-1** | Durable sink not runtime-wired (contract only; parallels B-2 deferral). | Major | Control Plane | A separately-gated phase wires the sink, preserving fail-closed. | OPEN | YES |
| **B6-BLK-2** | Durable audit-table DDL not applied (future `infrastructure/db/control/**`). | Major | Infra / Control Plane | Reviewed DDL applied (blob-pinned) in the target environment. | OPEN | YES |
| **B6-BLK-3** | Production sink reference not configured. | Major | Infra | A production sink resolving `*_REF` references at connect time; references only. | OPEN | YES |
| **B6-BLK-4** | Fail-closed-on-required-write not runtime-enforced (documented contract only). | Major | Control Plane | Wiring honors the fail-closed contract (`b6_provisioning_audit_fail_closed_policy.md`). | OPEN | YES |
| **B6-BLK-5** | Retention policy not production-approved. | Minor | Control Plane / Ops | Approved retention policy referenced by `*_REF`. | OPEN | YES |
| **B6-BLK-6** | Redaction policy not production-approved. | Minor | Control Plane / Ops | Approved redaction policy referenced by `*_REF`. | OPEN | YES |
| **B6-BLK-7** | Hash policy not production-approved — **applies only IF hash-chaining is later enabled** (OPTIONAL/forward; NOT IC-004/D-23 lineage). | Minor | Control Plane | Approved hash policy, *if and only if* hash-chaining is adopted. | OPEN (conditional) | Only if enabled |

## Rules

```
B-6 supplies the sink CONTRACT + template + additive tests; it does NOT close B5-BLK-4.
While any B6-BLK-* above is OPEN, B5-BLK-4 stays OPEN and production runtime activation remains DO-NOT-ACTIVATE.
B-6 makes NO production-readiness claim. The B-5 register (b5_activation_blockers.md) remains the canonical activation gate.
```
