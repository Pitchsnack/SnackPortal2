# environment example: local

Convention for a **disposable local PostgreSQL** target (e.g. PG 17.10). **Scaffold only** — references and
aliases, never values. Loopback only. **Docker is not required** (and must not become a dependency).

## Reference-only configuration shape (illustrative — NOT a committed values file)

```
environment      = local
provider_alias   = self-hosted
endpoint_alias   = loopback reference (host = local loopback; port reference) — NO credentialed DSN
control_db       database_alias = control · database_kind = control
secret_refs      control_db_admin = ref:local/control-db-admin@v1
                 control_db_app   = ref:local/control-db-app@v1
                 tenant_db_admin  = ref:local/tenant-db-admin@v1
state            none committed (DB3-4: local/non-production state only; never committed)
```

## Safety checklist

```
[x] loopback host only (no real/remote hostname)
[x] no real cloud account ID
[x] no real password / DSN / connection string with credentials
[x] no real tenant payload
[x] no committed state file
[x] secret material is a ref: reference resolved at connect time (D-14), never a value
```

## Notes

- `secret_ref` values above are **references** (`ref:...@version`), resolved in-memory from the D-14 pluggable
  secret store at connect time and never stored, logged, or committed.
- Per-tenant databases are **not** enumerated here — tenant creation is the Control-Plane D-15 workflow.
- This is a documentation convention; no executable IaC, no DDL application, and no database creation occur in
  PRD 06 B-3.
