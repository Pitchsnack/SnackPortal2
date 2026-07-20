# B5-BLK-8A — Production Rollback Evidence Template (references only)

**Scope:** the references-only evidence record for one Dan-authorized, exactly-once execution of the
B5-BLK-8B rollback rehearsal — an isolated, non-destructive rollback to the deferred (in-memory)
composition. In B5-BLK-8A this template ships **blank** (bracketed placeholders); it is filled once,
later, by the separately-authorized rehearsal. It closes no blocker.

**Redaction rules (D-14; IC-001 Global Audit Representation Rule) — every field below is
REFERENCES ONLY:** no DSN, no password, no token-shaped string, no key material, no PII, no tenant
business data, and no connection-topology detail beyond a redacted scheme+host+port+database identity.
Reference fields use `ref:...` placeholders only; a raw secret value is never permitted in any cell.

---

## 1. Record

| Field | Value | Notes |
|---|---|---|
| `EXECUTION_ID` | `<free identifier>` | mandatory |
| `EXECUTION_DATE` | `<YYYY-MM-DD (UTC)>` | mandatory |
| `OPERATOR` | `<operator name/role — references only>` | mandatory; references only |
| `ENVIRONMENT_CLASS` | `<local \| non-production>` | mandatory; `production` PROHIBITED |
| `BASELINE_MAIN_SHA` | `<40-hex>` | mandatory |
| `ACTIVATION_MODE` | `deferred-in-memory` | mandatory; only value |
| `ROLLBACK_TRIGGER` | `<one enum value below>` | mandatory |
| `ROLLBACK_PLAN_REF` | `ref:...` | mandatory; references only |
| `PRE_ROLLBACK_STATE_REF` | `ref:...` | mandatory; references only |
| `POST_ROLLBACK_STATE_REF` | `ref:...` | mandatory; references only |
| `TENANT_SCOPE` | `<tenant id(s) — non-secret identity>` | mandatory; references only |
| `ADJACENT_TENANT_SCOPE` | `<adjacent tenant id(s), proven untouched>` | mandatory; references only |
| `BEFORE_DATA_DIGEST` | `<digest — e.g. sha256; non-secret>` | mandatory |
| `AFTER_DATA_DIGEST` | `<digest>` | mandatory |
| `ISOLATION_ASSERTION` | `<PASS \| FAIL>` | mandatory (D-30) |
| `NON_DESTRUCTIVE_ASSERTION` | `<PASS \| FAIL>` | mandatory (D-24; no tenant-data deletion) |
| `FAILURE_RECORD_REF` | `ref:...` | mandatory; references only |
| `AUDIT_RECORD_REF` | `ref:...` | mandatory; references only |
| `SECRET_REFERENCE_ONLY_ASSERTION` | `<PASS \| FAIL>` | mandatory (D-14) |
| `DEFERRED_COMPOSITION_ASSERTION` | `<PASS \| FAIL>` | mandatory; returned to the deferred (in-memory) composition |
| `DISPOSAL_ASSERTION` | `<PASS \| FAIL \| N/A>` | optional in 8A; mandatory in 8B when a disposable database is used |
| `FINAL_VERDICT` | `<DO-NOT-ACTIVATE \| ROLLBACK-PROVEN-LOCAL>` | mandatory; `ACTIVATE` PROHIBITED; default `DO-NOT-ACTIVATE` |

## 2. Enumerations

- `ENVIRONMENT_CLASS` = `local` | `non-production`. `production` is forbidden — there is no production
  environment in the B-5 era.
- `ACTIVATION_MODE` = `deferred-in-memory`.
- `ROLLBACK_TRIGGER` = `identity_mismatch` | `distinctness_regression` | `router_anomaly` |
  `secret_resolution_failure` | `audit_sink_unavailable` | `migration_readiness_failure` |
  `operator_directed_abort`.
- `ISOLATION_ASSERTION` = `PASS` | `FAIL`.
- `NON_DESTRUCTIVE_ASSERTION` = `PASS` | `FAIL`.
- `SECRET_REFERENCE_ONLY_ASSERTION` = `PASS` | `FAIL`.
- `DEFERRED_COMPOSITION_ASSERTION` = `PASS` | `FAIL`.
- `DISPOSAL_ASSERTION` = `PASS` | `FAIL` | `N/A`.
- `FINAL_VERDICT` = `DO-NOT-ACTIVATE` | `ROLLBACK-PROVEN-LOCAL`. `ACTIVATE` is forbidden.

## 3. Prohibited values (never permitted in any cell)

Raw DSN, password, token, key material, PII, tenant business data, `production` as
`ENVIRONMENT_CLASS`, and `ACTIVATE` as `FINAL_VERDICT`. Every reference field carries a `ref:...`
placeholder only; no raw secret value is ever written here.

## 4. Locked state (unchanged by this template and by any record built from it)

- **B5-BLK-8 remains OPEN.**
- The live blocker census remains **7 of 9 OPEN**.
- Production remains **NOT READY / DO-NOT-ACTIVATE**.

This template closes no blocker. Only a later, Dan-authorized governance-effect decision (B5-BLK-8D),
resting on captured execution evidence, may change B5-BLK-8's status or the census.
