# PRD 06 B-5 — Production Activation Blocker Register

**Gate posture: NOT READY.** Production runtime activation is **blocked** while any blocker below is OPEN. Default is
conservative: missing evidence ⇒ OPEN ⇒ activation blocked. This register is grounded in the **actual** current state
(`origin/main @ 9684919`); production is far off by design.

| ID | Description | Severity | Owner | Evidence required | Status | Blocks activation |
|----|-------------|----------|-------|-------------------|--------|-------------------|
| **B5-BLK-1** | `backend/control_plane/main.py` runtime wiring is deferred (`NotImplementedError`; default `in_memory`). The durable/real adapters exist (B-2/B-4) but are not constructed at runtime. | Critical | Control Plane | A separately-authorized runtime-activation phase that flips the deferral under the gate, with the regression lock consciously updated. | OPEN | YES |
| **B5-BLK-2** | No production Control DB / Tenant DB fleet provisioned. B-3 was docs/scaffold-only; D-15 IaC has not been executed against production. | Critical | Infra / Control Plane | Provisioned, physically-distinct Control + per-tenant DBs in the target environment, with identity proof. | OPEN | YES |
| **B5-BLK-3** | No production secret store wired. The D-14 reference-based abstraction exists; the default provider is `EnvReferenceSecretStore`. | Critical | Infra | A production-grade pluggable secret store resolving `*_REF` references at connect time; references only. | OPEN | YES |
| **B5-BLK-4** | Provisioning audit sink not built (B-6 deferred). | Major | Control Plane | B-6 audit sink available, or an explicit approved waiver for the target environment. | OPEN | YES |
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
