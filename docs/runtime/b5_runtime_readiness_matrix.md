# PRD 06 B-5 — Runtime Readiness Matrix

Maps each production-runtime readiness condition to the **existing** machinery that proves it (B-5 references, does not
reinvent) and to the blocker that holds it OPEN today. **Gate posture: NOT READY.**

| Readiness condition | Existing machinery (authority) | Current status | Blocker |
|---------------------|-------------------------------|----------------|---------|
| Runtime deferral intact (no accidental activation) | `main.py` `SP2_CP_*` + `NotImplementedError`; pinned by `test_b5_runtime_deferral_guard.py` + B-2 WP-H13 + `test_onboarding_orchestration.py` | Deferred (in_memory default) | B5-BLK-1 |
| Control DB provisioned + identity | D-15 provisioning workflow; `infrastructure/db/control/**` (reference DDL) | Not provisioned in prod | B5-BLK-2 |
| Tenant DB fleet provisioned + identity | D-15 provisioning workflow; `infrastructure/db/provisioning/**` + `lineage/**` | Not provisioned in prod | B5-BLK-2 |
| Physical distinctness (Control vs Tenant; Tenant vs Tenant) | **IC-010 §O** (physical multi-DB rule) + **§P** (distinctness verification hook); the durable distinctness ledger + provisioning distinctness gate (`provisioning.py`) | Proven locally (B-4/B-3A); not in prod | B5-BLK-2 |
| Tenant lifecycle == Ready | **IC-002** seven-state lifecycle; `ReadinessFramework` | n/a in prod | B5-BLK-2 |
| Secret references resolve (no values) | **D-14**; `SecretStore` / `EnvReferenceSecretStore` | Default env provider only | B5-BLK-3 |
| One request → one active tenant → one DB | **D-07 / D-30**; Database Router = sole selector (IC-010 §H/§M) | Library-level; runtime deferred | B5-BLK-1 |
| Sole ingress | **IC-010 §I**; API Gateway | Gateway built (Phase 7); runtime routing deferred | B5-BLK-1 |
| Schema / migration readiness | **D-17** expand/contract + version-gated readiness | No prod migration evidence | B5-BLK-7 |
| Provisioning audit sink | B-6 (deferred) | Not built | B5-BLK-4 |
| Rollback | isolated, non-destructive (D-30 / D-24) | No prod rollback evidence | B5-BLK-8 |
| Frontend integrates only via Gateway | IC-009 portals; Lovable UI-only | Interim Supabase/RLS (DRIFT-01) | B5-BLK-5, B5-BLK-6 |
| Monitoring / alerting | Ops | Not evidenced | B5-BLK-9 |

## Hard rule

```
A Tenant DB cannot be marked production-ready unless it is physically distinct from the Control DB and from every other
Tenant DB (IC-010 §O/§P). A single shared database + tenant_id is never acceptable.
```

B-5 documents this matrix; it does not change any "current status" to ready and does not activate runtime.
