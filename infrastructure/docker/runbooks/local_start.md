# Runbook — Local Start & Identity Proof (PRD 06 B-3A)

**LOCAL / NON-PRODUCTION ONLY.** Brings up the four-instance topology and proves four physically distinct PostgreSQL
clusters. No DDL is applied; no production system is touched; no secret value is committed or printed.

## 0. Prereqs

```
Docker daemon running (docker info succeeds)            # if down, STOP — do not improvise
cp infrastructure/docker/.env.local.template infrastructure/docker/.env.local
# edit .env.local → set SP2_LOCAL_PG_PASSWORD to a throwaway LOCAL value (gitignored; never commit)
```

## 1. Validate & start

```
docker compose -f infrastructure/docker/docker-compose.local.yml --env-file infrastructure/docker/.env.local config
docker compose -f infrastructure/docker/docker-compose.local.yml --env-file infrastructure/docker/.env.local up -d
docker compose -f infrastructure/docker/docker-compose.local.yml ps
```

Wait for all four health checks to report healthy:

```
docker compose -f infrastructure/docker/docker-compose.local.yml ps --format '{{.Name}} {{.State}} {{.Status}}'
```

## 2. Identity proof (non-secret values only)

For each service, read the cluster identity (no password printed; auth via the container's trust for local exec):

```
docker compose -f infrastructure/docker/docker-compose.local.yml exec -T control-postgres \
  psql -U "$SP2_LOCAL_PG_USER" -d snackportal2_control_local \
  -c "SELECT system_identifier FROM pg_control_system();" -c "SELECT current_database();"
# repeat for tenant-acme-postgres / tenant-zeta-postgres / tenant-nova-postgres
```

**Expected:** four **distinct** `system_identifier` values and four distinct database names.
**FAIL** if all four share one cluster identity (that would mean shared hosting, not physical separation).

## 3. Harness proof (extends the existing requires_pg suite)

Set the four local DSNs in the shell only (never commit; never print), then run the topology test:

```
export SP2_B3A_CONTROL_DB_DSN="postgresql://$SP2_LOCAL_PG_USER:<LOCAL_PW>@127.0.0.1:5540/snackportal2_control_local"
export SP2_B3A_ACME_DB_DSN="postgresql://$SP2_LOCAL_PG_USER:<LOCAL_PW>@127.0.0.1:5541/snackportal2_tenant_acme_local"
export SP2_B3A_ZETA_DB_DSN="postgresql://$SP2_LOCAL_PG_USER:<LOCAL_PW>@127.0.0.1:5542/snackportal2_tenant_zeta_local"
export SP2_B3A_NOVA_DB_DSN="postgresql://$SP2_LOCAL_PG_USER:<LOCAL_PW>@127.0.0.1:5543/snackportal2_tenant_nova_local"
cd backend && python -m pytest tests/control_plane/requires_pg/test_b3a_multi_database_topology.py -q
```

The test skips cleanly if the `SP2_B3A_*` vars are unset; it never runs in the default suite; it prints no DSN or
password; it fails-closed if any target is missing and asserts four distinct `system_identifier`s.

## Notes

- Replace `<LOCAL_PW>` with the throwaway value from your untracked `.env.local`. Do not paste it into any committed file.
- No DDL is applied in B-3A. Applying the reviewed DDL is a later, separately-gated phase.
