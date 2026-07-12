# PRD 06 B-5 — Runtime Readiness Matrix

Maps each production-runtime readiness condition to the **existing** machinery that proves it (B-5 references, does not
reinvent) and to the blocker that holds it OPEN today. **Gate posture: NOT READY.**

**Re-grounded 2026-07-12** at baseline `origin/main @ fff215b5bd004760ea0d81915c3d93ca128673ed`; decision baseline `origin/main @ 84882c77cfe409bab0af454b4411cf65795bcbfd` (B5-E, 2026-07-12). The B5
runtime-readiness arc (B5-1 #69, B5-2 #70, B5-3 #71, B5-4 #72, B5-5 #73, B5-4A #74, Smoke C V2 + Fix R3 #75)
has moved several conditions to **proven locally at database granularity** — distinct physical databases on
one local admin cluster, exercised end-to-end by Smoke C V2. That is **not** cluster-level distinctness,
**not** production deployment, and **not** MVP completion.

```text
Smoke C V2 including Fix R3 supplies database-granularity evidence.
It does not itself close B5-BLK-4.
```

**B5-E closure decision record (2026-07-12).**

Decision baseline: `origin/main @ 84882c77cfe409bab0af454b4411cf65795bcbfd` (B5-E, 2026-07-12).

**Decision A (B5-E, 2026-07-12, Dan-authorized): B5-BLK-4 — CLOSED — EVIDENCE-BOUND GOVERNANCE DECISION.**
**Decision B (B5-E, 2026-07-12, Dan-authorized): Physical Multi-Database MVP — ACCEPTED AT DATABASE GRANULARITY.**

MVP acceptance at database granularity is not cluster-level proof, not production deployment, not production activation, not Lovable cutover, not billing completion, and not AI Agent completion.
The Physical Multi-Database MVP mandate (IC-010 §O) remains mandatory and binding; acceptance at database granularity does not weaken it.
Cluster-level distinctness remains deployment scope (AT-D15T1-4; held by B5-BLK-2).
DBR-AR-2 (durable routing audit) remains OPEN — a separate Database Router follow-on; it was not part of the B5-BLK-4 closure evidence bar (see the B5-E record) and its status is unchanged by this decision.
Production runtime activation remains NOT READY / DO-NOT-ACTIVATE — 8 of 9 activation blockers remain OPEN; the B5-E closure of B5-BLK-4 changes no other blocker and does not make the gate ready.
The gate §5 activation condition "provisioning audit sink available (B-6) — or an explicit, approved waiver" remains binding at activation time and is not waived by the B5-E closure.
Next step: the next Dan-authorized governed slice; every remaining activation blocker is deployment-scope (B5-BLK-2/3/7/8/9) or product/integration-track (B5-BLK-5/6), and DBR-AR-2 is the named Database Router follow-on PRD.

IC-002 is the **eight-state** lifecycle (see
`b5_production_runtime_activation_gate.md` §0 and `contracts/IC-002-Tenant-Startup-Contract.md`).

| Readiness condition | Existing machinery (authority) | Current status | Blocker |
|---------------------|-------------------------------|----------------|---------|
| Runtime deferral intact (no accidental activation) | `main.py` `SP2_CP_*` + `NotImplementedError`; pinned by `test_b5_runtime_deferral_guard.py` + B-2 WP-H13 + `test_onboarding_orchestration.py` | Deferred (in_memory default) | B5-BLK-1 |
| Control DB provisioned + identity | D-15 provisioning workflow; `infrastructure/db/control/**` (reference DDL) | Not provisioned in prod | B5-BLK-2 |
| Tenant DB fleet provisioned + identity | D-15 provisioning workflow; `infrastructure/db/provisioning/**` + `lineage/**` | Not provisioned in prod | B5-BLK-2 |
| Physical distinctness (Control vs Tenant; Tenant vs Tenant) | **IC-010 §O** (physical multi-DB rule) + **§P** (distinctness verification hook); the durable distinctness ledger + provisioning distinctness gate (`provisioning.py`) | Proven locally at **database granularity** (B5-4/B5-4A/Smoke C V2); **not** cluster-level / production | B5-BLK-2 |
| Tenant lifecycle == Ready | **IC-002** eight-state lifecycle; `ReadinessFramework` | Ready proven for two standing tenants locally (B5-4); n/a in production | B5-BLK-2 |
| Secret references resolve (no values) | **D-14**; `SecretStore` / `EnvReferenceSecretStore` | Default env provider only | B5-BLK-3 |
| One request → one active tenant → one DB | **D-07 / D-30**; Database Router = sole selector (IC-010 §H/§M) | Proven end-to-end locally at database granularity (Smoke C V2); `main.py` runtime deferral intact | B5-BLK-1 |
| Sole ingress | **IC-010 §I**; API Gateway | Sole ingress in Smoke C V2 (local, database granularity); production runtime routing deferred | B5-BLK-1 |
| Schema / migration readiness | **D-17** expand/contract + version-gated readiness | No prod migration evidence | B5-BLK-7 |
| Provisioning audit sink | B-6 (now built) | Built on `main` (B-6 #21 / B-7 #23 / B-7B #25); standing-environment wiring exercised (B5-4 / B5-4A / Smoke C V2); production-environment availability stays a gate §5 activation condition; durable routing audit (DBR-AR-2) remains open — separate follow-on | B5-BLK-4 — CLOSED (B5-E, 2026-07-12) |
| Rollback | isolated, non-destructive (D-30 / D-24) | No prod rollback evidence | B5-BLK-8 |
| Frontend integrates only via Gateway | IC-009 portals; Lovable UI-only | Interim Supabase/RLS (DRIFT-01) | B5-BLK-5, B5-BLK-6 |
| Monitoring / alerting | Ops | Not evidenced | B5-BLK-9 |

## Hard rule

```
A Tenant DB cannot be marked production-ready unless it is physically distinct from the Control DB and from every other
Tenant DB (IC-010 §O/§P). A single shared database + tenant_id is never acceptable.
```

B-5 documents this matrix; it does not change any "current status" to ready and does not activate runtime.
