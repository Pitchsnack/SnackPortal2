# PRD 06 B-5 — Production Runtime Activation Evidence Template (references-only)

A reusable, **references-only** evidence record for any future Production Runtime Activation Gate decision. **All fields
are redacted of secrets.** Copy per decision; fill the bracketed values; never enter a raw DSN, password, token, or
credential.

> **Redaction rule (D-14; IC-001 Global Audit Representation Rule):** record references (`ref:…`), aliases, and
> non-secret identities (e.g., `system_identifier`); never record DSNs, passwords, tokens, cloud credentials, or PII.

---

## 1. Identity & scope
```
PRD / phase            : PRD 06 B-5 — Production Runtime Activation Gate
baseline commit        : [origin/main @ ...]
target environment     : [local | non-production]   (production prohibited in the B-5 era)
gate decision          : [DO-NOT-ACTIVATE | ACTIVATE]   (default DO-NOT-ACTIVATE)
operator / approver    : [name/role]    date (UTC) : [YYYY-MM-DD]
```

## 2. Activation switch
```
RUNTIME_ACTIVATION_ENABLED : [false]   (must be explicitly true to activate; never defaulted true)
```

## 3. Database identity & physical distinctness (non-secret)
```
control DB identity    : [system_identifier / datname:oid]
tenant DB identities   : [per tenant: system_identifier / datname:oid]
distinctness proof     : [all physically distinct — Control vs each Tenant, Tenant vs Tenant; IC-010 §O/§P]
```

## 4. Registry & readiness (IC-002)
```
tenant registry        : [complete? per-tenant lifecycle state]
readiness (Ready?)     : [per activated tenant]
```

## 5. Secret references (keys only — never values)
```
CONTROL_DB_REF=ref:...   TENANT_DB_<TENANT>_REF=ref:...   JWT_ISSUER_REF=ref:...   OIDC_PROVIDER_REF=ref:...
AUDIT_SINK_REF=ref:...   ROLLBACK_PLAN_REF=ref:...
secret values stored?  : NO (resolved in-memory at connect time; D-14)
```

## 6. Routing & ingress boundaries
```
Database Router        : [proves one request → one active tenant → one database; sole selector — D-07/D-30]
API Gateway            : [sole ingress — IC-010 §I]
```

## 7. Migration / audit / rollback
```
migration readiness    : [schema version within supported range — D-17]
audit sink             : [available (B-6) | blocker B5-BLK-4]
rollback proof         : [isolated, non-destructive rollback to deferred composition proven]
```

## 8. Blockers
```
blocker register       : [b5_activation_blockers.md — list OPEN blockers; activation requires ALL closed]
```

## 9. Gates & CI
```
ruff/format | mypy | lint-imports | pytest architecture | pytest full | gitleaks | git diff --check | deferral lock
CI status              : [validate / secret-scan]
```

## 10. Outcome
```
invariants preserved   : [Physical Multi-DB / Control-Plane authority / Router-sole-selector / Gateway-ingress / D-14 /
                          fail-closed — confirm each]
human approval         : [recorded]
risk                   : [LOW / MED / HIGH + rationale]
final verdict          : [DO-NOT-ACTIVATE | ACTIVATE]   (ACTIVATE only with all blockers closed + approval)
```
