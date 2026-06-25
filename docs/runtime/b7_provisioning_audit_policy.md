# PRD 06 B-7 — Provisioning Audit Policies (references only; created-not-applied)

Policy **references** for the durable `control_audit` store. All are reference-only (D-14); none are wired or applied in B-7.

---

## 1. Append-only policy

The `control_audit` table is **insert-only**: corrections are new rows, failures are new rows, (future) rollback events are
new rows; there is **no** status-overwrite, no UPDATE path, no DELETE path. Retention is **not** expressed as direct DELETE
logic in B-7. DB-level enforcement is the `003_provisioning_audit_append_only.sql` trigger (created-not-applied; mirrors the
lineage append-only precedent). Least-privilege (a writer role with INSERT+SELECT, no UPDATE/DELETE/TRUNCATE grant) is a
forward proposal following `infrastructure/db/lineage/003_roles.sql`.

## 2. Retention policy (reference only; forward)

Retention is a `*_REF` reference, not direct delete logic:
```
retention_policy_ref = ref:retention-policy
```
Production-approved retention is a forward gate (see blockers).

## 3. Redaction policy (reference only)

Payloads/evidence are references / redacted; raw secrets are forbidden (the store records references, never values):
```
redaction_policy_ref = ref:redaction-policy
payload_ref          = ref:payload
evidence_ref         = ref:evidence
```

## 4. Hash policy (OPTIONAL / forward only — NOT lineage)

A hash policy is **optional and forward only** and lives in the forward-contract extension
(`b7_provisioning_audit_schema.md` §3), **not** in the live `control_audit` table. The provisioning-audit hash option must
**not** be modelled on or conflated with IC-004 / D-23 **lineage** (the hash-chained tenant-DB provenance subsystem,
`infrastructure/db/lineage/001_lineage_schema.sql`). `control_audit` carries no hash-chain.
```
hash_policy_ref = ref:hash-policy   # optional / forward; applies only IF hash-chaining is later enabled; NOT lineage
```

No raw DSNs, passwords, tokens, private keys, cloud credentials, or production secret values appear in any policy reference.
