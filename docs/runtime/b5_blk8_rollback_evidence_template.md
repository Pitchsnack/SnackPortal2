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

---

## 5. Hosted non-production extension (B5-BLK-8C — IC-011 / D-40)

**Scope:** the additional references-only fields for one Dan-authorized, exactly-once execution of the
**B5-BLK-8C hosted, non-production rollback proof** (governed by `contracts/IC-011-Hosted-Rollback-Proof-Contract.md`
and the runbook `infrastructure/runbooks/b5_blk8c_hosted_rollback_proof.md`). This extension **preserves the
accepted local schema above (§1–§4)** and adds the hosted fields below; it closes no blocker. Every field is
**references only** — no DSN, no password, no token, no key material, no PII, no tenant business data, and no live
customer row data.

| Field | Value | Notes |
|---|---|---|
| `ENVIRONMENT_CLASS` | `hosted-non-production` | mandatory in the hosted extension; `production` PROHIBITED |
| `HOSTED_TARGET_CLASS` | `<hosted-staging \| hosted-pre-production>` | mandatory; `live-production` PROHIBITED |
| `ROLLBACK_FROM_STATE_REF` | `ref:...` | mandatory; references only (the activated/durable pre-rollback state) |
| `LAST_KNOWN_GOOD_REVISION_REF` | `ref:...` | mandatory; references only (the pinned success target) |
| `CONTROL_DB_IDENTITY_REF` | `ref:...` | mandatory; the one hosted Control DB identity (references only) |
| `TENANT_DB_IDENTITY_REFS` | `ref:...` (≥2) | mandatory; ≥2 physically distinct hosted Tenant DB identities (references only) |
| `SECRET_BINDING_SET_DIGEST` | `<digest — e.g. sha256; non-secret>` | mandatory; digest of the SecretRef binding set (never the values) |
| `MIGRATION_SET_DIGEST` | `<digest>` | mandatory; digest of the applied migration set |
| `AUDIT_SINK_IDENTITY_REF` | `ref:...` | mandatory; the Control-resident audit sink identity (references only) |
| `SERVED_HEALTH_BASELINE_REF` | `ref:...` | mandatory; served-health baseline through **every** served approved public edge (**D-45**; references only) |
| `FAILURE_STATE_REF` | `ref:...` | mandatory; the induced governed-failure state (references only) |
| `POST_ROLLBACK_REF` | `ref:...` | mandatory; the post-rollback served state (references only) |
| `RESTORATION_REF` | `ref:...` | mandatory; the restoration / roll-forward reference (references only) |
| `CLEANUP_REF` | `ref:...` | mandatory; the temporary-object cleanup reference (references only) |
| `OPERATOR_IDENTITY` | `<operator name/role — references only>` | mandatory; references only |
| `APPROVER_IDENTITY` | `<approver name/role — references only>` | mandatory; references only |
| `EXECUTION_WINDOW` | `<UTC start–end>` | mandatory |
| `HOSTED_FINAL_VERDICT` | `<ROLLBACK-PROVEN-HOSTED-NONPRODUCTION \| ROLLBACK-NOT-PROVEN>` | mandatory; `ROLLBACK-PROVEN-PRODUCTION-SCOPE` PROHIBITED |

## 6. Hosted enumerations

- `ENVIRONMENT_CLASS` (hosted extension) = `hosted-non-production`. `production` is forbidden.
- `HOSTED_TARGET_CLASS` = `hosted-staging` | `hosted-pre-production`. `live-production` is forbidden.
- `HOSTED_FINAL_VERDICT` = `ROLLBACK-PROVEN-HOSTED-NONPRODUCTION` | `ROLLBACK-NOT-PROVEN`.
  - A landing on the **deferred in-memory composition** (the emergency fail-closed target, not the
    last-known-good durable composition success target) earns `ROLLBACK-NOT-PROVEN` plus an
    emergency-safe-state record; it never earns `ROLLBACK-PROVEN-HOSTED-NONPRODUCTION`.

## 7. Hosted prohibited values & single-final-write (never permitted / binding discipline)

- **Prohibited (kept prohibited):** `ACTIVATE` as any verdict, a `PRODUCTION READY` claim, `B5-BLK-8 CLOSED`,
  and `ROLLBACK-PROVEN-PRODUCTION-SCOPE`. None may appear as a value in any cell.
- **Single final write.** The authoritative hosted record is written **exactly once**, **after** restoration
  (H10) and temporary-object cleanup (H12), so a failed run or a failed cleanup can never retain a false-PASS
  record. The record lives **outside the repository**.
- **Locked state.** This hosted extension closes no blocker. **B5-BLK-8 remains OPEN.** The live blocker census
  remains **7 of 9 OPEN**. Production remains **NOT READY / DO-NOT-ACTIVATE**. Only a later, Dan-authorized
  **B5-BLK-8D** governance-effect decision may change B5-BLK-8's status or the census.
