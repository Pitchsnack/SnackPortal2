# PRD 06 B-7 — Provisioning Audit Durable Store Evidence Template (references-only)

A reusable, **references-only** evidence record for any future provisioning-audit durable-store decision. **All fields are
redacted of secrets.** Copy per decision; fill the bracketed values; never enter a raw DSN, password, token, or credential.

> **Redaction rule (D-14; IC-001):** record references (`ref:…`) and non-secret identities; never DSNs, passwords, tokens,
> cloud credentials, or PII.

---

## 1. Identity & scope
```
PRD / phase            : PRD 06 B-7 — Provisioning Audit Durable Store
baseline commit        : [origin/main @ ...]
target environment     : [local | non-production]   (production prohibited in the B-7 era)
DDL artifact           : infrastructure/db/control/002_provisioning_audit.sql  (created, NOT applied)
append-only trigger    : infrastructure/db/control/003_provisioning_audit_append_only.sql  (created, NOT applied)
operator / approver    : [name/role]    date (UTC) : [YYYY-MM-DD]
```

## 2. Adapter compatibility (non-secret)
```
control_audit columns  : [id (DB-generated) · actor · tenant_id(NULL) · action · from_state(NULL) · to_state(NULL) · ts(timestamptz) · correlation_id]
adapter INSERT match   : [postgres_store.append_audit columns ⊆ DDL columns — confirmed]
no parallel 28-field table : [confirmed]
```

## 3. Contract proofs
```
created-not-applied    : [002/003 headers state "Created, NOT applied"]
append-only            : [no UPDATE/DELETE path; 003 trigger rejects UPDATE/DELETE/TRUNCATE]
references-only        : [no raw secret literals in DDL/docs — text-inspect + gitleaks]
event vocabulary       : [B7-EVENT-MAP names ⊆ events.py; no SQL CHECK/enum]
not lineage            : [IC-002/D-34 distinct from IC-004/D-23 — confirmed]
```

## 4. Gates & CI
```
local : ruff/format | mypy | lint-imports | pytest architecture | pytest full | B-7 tests | gitleaks | git diff --check
CI    : validate (pytest tests/architecture) | secret-scan (gitleaks)
counts: [arch / full / mypy — additive, explained]
```

## 5. Outcome
```
invariants preserved   : [Physical Multi-DB / Control-Plane authority / references-only / append-only / audit ≠ lineage]
blocker standing       : [B6-BLK-2 reduced (DDL authored); B5-BLK-4 remains OPEN]
DDL applied?           : NO (created-not-applied)   runtime wired? : NO
human approval         : [recorded]
risk                   : [LOW / MED / HIGH + rationale]
final verdict          : [READY FOR PRE-MERGE VERIFICATION | NOT READY]
```
