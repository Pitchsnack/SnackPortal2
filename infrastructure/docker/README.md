# infrastructure/docker — Local Multi-Database Test Environment (PRD 06 B-3A)

**LOCAL / NON-PRODUCTION ONLY.** A disposable Docker Compose fixture of **four physically separate PostgreSQL
instances** (one Control + three tenant) that demonstrates SnackPortal2's **Physical Multi-Database MVP** topology
locally, before any production runtime activation (B-5).

## What this is — and is NOT

```
IS:    a local, disposable topology proof — four separate clusters → four distinct system_identifiers.
IS:    a fixture whose DSNs feed the EXISTING B-4 requires_pg harness (extended, not replaced).
IS NOT production · IS NOT the cloud-portable IaC (that is B-3, and stays Docker-free) · IS NOT runtime activation.
IS NOT a tenant-DB lifecycle authority — real tenant DB creation is the D-15 Control-Plane workflow (not Docker).
```

Docker is **local substrate only**. It must never become production architecture, replace the cloud-portable IaC, or
become a dependency of the backend application (CLAUDE.md #4).

## Files

```
docker-compose.local.yml   4 stock postgres:17 services; 127.0.0.1-bound ports 5540-5543; named disposable volumes;
                           per-service health checks; password INTERPOLATED from an untracked .env.local (never hardcoded).
.env.local.template        committed: placeholders + D-14 *_REF=ref:local/... references only (NO secret values).
.gitignore                 keeps .env.local and runtime state/logs out of git.
runbooks/local_start.md    how to start + prove four distinct PostgreSQL identities.
runbooks/local_teardown.md how to tear down containers + volumes safely (local-only; production warnings).
```

## Topology

| Service | Container | Database | Port (127.0.0.1) | Volume |
|---------|-----------|----------|------------------|--------|
| control-postgres | sp2_b3a_control | snackportal2_control_local | 5540 | sp2_b3a_control_data |
| tenant-acme-postgres | sp2_b3a_tenant_acme | snackportal2_tenant_acme_local | 5541 | sp2_b3a_tenant_acme_data |
| tenant-zeta-postgres | sp2_b3a_tenant_zeta | snackportal2_tenant_zeta_local | 5542 | sp2_b3a_tenant_zeta_data |
| tenant-nova-postgres | sp2_b3a_tenant_nova | snackportal2_tenant_nova_local | 5543 | sp2_b3a_tenant_nova_data |

## Quick start

```
cp infrastructure/docker/.env.local.template infrastructure/docker/.env.local
# edit .env.local → set SP2_LOCAL_PG_PASSWORD to a throwaway LOCAL value (never commit it)
docker compose -f infrastructure/docker/docker-compose.local.yml --env-file infrastructure/docker/.env.local up -d
```

See `runbooks/local_start.md` for identity proof and `runbooks/local_teardown.md` for cleanup. No DDL is applied in
this phase; secrets are references only; no value is ever committed.
