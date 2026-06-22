# PRD 06 B-3 — Rollout Evidence Report Template (references-only)

A reusable, **references-only** evidence template for any future controlled non-production rollout/teardown of
the cloud-portable substrate. Aligned to the `docs/reports/ci-evidence/` convention. **All fields are redacted
of secrets.** Copy this template per execution; fill the bracketed values; never enter a raw secret/DSN/credential.

> **Redaction rule (D-14; IC-001 Global Audit Representation Rule):** never record passwords, raw DSNs,
> credentialed connection strings, cloud access keys, API tokens, JWTs, session tokens, or PII. Record
> **references** (`ref:…@version`) and **aliases** only.

---

## 1. Identity & scope

```
PRD / phase            : PRD 06 B-3 — Cloud-Portable IaC Rollout (controlled non-production)
baseline commit        : [origin/main @ ...]
branch                 : [branch name]
target environment     : [local | nonprod]   (NEVER production)
provider mode / alias  : [self-hosted | aws | azure | gcp]
operator               : [name/role]
date (UTC)             : [YYYY-MM-DD]
```

## 2. Resources

```
resources intended     : [cluster substrate / Control DB / cluster-scoped roles — list]
resources created      : [list, by alias only]
resources NOT created  : [tenant DBs (control-plane-owned) / production / cloud — confirm]
```

## 3. Secret references (keys only — never values)

```
secret refs used       : [ref:.../control-db-admin@v1, ref:.../tenant-db-admin@v1, ...]
secret values stored?  : NO (resolved in-memory at connect time; D-14)
```

## 4. DDL

```
DDL applied?           : [NO for B-3 scaffold; for a gated DDL step list files + blob pins applied unchanged]
DDL blob hashes        : [file → blob pin; must match b3_ddl_target_mapping.md / re-verified baseline]
control ledger pin     : 30956ff1e85e8dab1c9f55cbfc121ee9212f3ca0  (apply unchanged)
```

## 5. State

```
state backend          : [none committed; local/non-prod only — DB3-4]
committed state files? : NO (.tfstate/.tfvars never committed)
```

## 6. Commands & gates

```
commands run           : [git status / diff --name-only / diff --stat / gates / gitleaks / (tofu validate if available)]
ruff / format          : [clean?]
mypy                   : [0 / 211]
lint-imports           : [2 kept, 0 broken]
pytest architecture    : [120]
pytest full (no PG)    : [363]
gitleaks (local)       : [clean?]
IaC validators         : [N/A if tofu/terraform absent — report, do not fake]
```

## 7. Scope fence & guards

```
changed paths ⊆ allowlist? : [git diff --name-only confined to sanctioned paths — YES/NO]
secret/state guard         : [no raw DSNs/passwords/tokens/credentials; no committed state — confirm]
governed blobs unchanged   : [infrastructure/db/** intact; control ledger 30956ff1e8 — confirm]
```

## 8. Cleanup (teardown reports only)

```
no leftover tenant DBs     : [confirm]
no leftover Control-DB test objects : [confirm]
no leftover roles / state  : [confirm]
no secrets ever committed  : [gitleaks clean]
```

## 9. Outcome

```
invariants preserved   : [Physical Multi-DB / Control-Plane lifecycle / Router-sole-selector / Gateway-ingress /
                          D-14 / fail-closed / vendor-neutral / infra-independent — confirm each]
risk assessment        : [LOW / MED / HIGH + rationale]
final verdict          : [READY FOR REVIEW | READY WITH OBSERVATIONS | NOT READY]
```
