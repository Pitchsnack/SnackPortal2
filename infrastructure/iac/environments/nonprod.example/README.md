# environment example: nonprod

Convention for a **disposable / explicitly test-safe non-production** target. **Scaffold only** — references
and aliases, never values. This is the only environment class a future B-3 execution may ever touch;
**production is deferred to B-5 and must never be targeted by B-3.**

## Reference-only configuration shape (illustrative — NOT a committed values file)

```
environment      = nonprod
provider_alias   = self-hosted | aws | azure | gcp   (provider-neutral; selected per non-production target)
endpoint_alias   = non-public endpoint reference — NO credentialed DSN, NO real hostname/account ID
control_db       database_alias = control · database_kind = control
secret_refs      control_db_admin = ref:nonprod/control-db-admin@v1
                 control_db_app   = ref:nonprod/control-db-app@v1
                 tenant_db_admin  = ref:nonprod/tenant-db-admin@v1
state            none committed (DB3-4: no remote/production state backend; local/non-prod state only, never committed)
```

## Safety checklist

```
[x] disposable or explicitly test-safe
[x] non-public network boundary (no public exposure of tenant data paths)
[x] no real cloud account ID / provider credential
[x] no real password / DSN / connection string with credentials
[x] no real tenant payload
[x] no committed state file
[x] environment-scoped secret references (cannot resolve a production secret)
[x] database names make the non-production environment unambiguous
```

## Notes

- All secret material is a `ref:...@version` reference (D-14), resolved at connect time, never stored/committed.
- Per-tenant databases are created by the Control-Plane D-15 workflow, not enumerated as IaC state (DB3-8).
- No executable IaC, no DDL application, no cloud resource creation, and no runtime activation occur in
  PRD 06 B-3.
