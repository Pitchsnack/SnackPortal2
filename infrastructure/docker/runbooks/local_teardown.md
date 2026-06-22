# Runbook — Local Teardown (PRD 06 B-3A)

**LOCAL / NON-PRODUCTION ONLY.**

> ⚠ **PRODUCTION WARNING.** These commands target only the local `snackportal2-b3a-local` Compose project and its
> disposable local volumes. Never run teardown against any production or shared database. B-3A touches no production
> system.

## 1. Stop & remove containers (keep volumes)

```
docker compose -f infrastructure/docker/docker-compose.local.yml down
```

## 2. Remove volumes (DESTRUCTIVE — local disposable data only; explicit confirmation)

Run only after confirming the volumes are the B-3A-local disposable volumes:

```
docker compose -f infrastructure/docker/docker-compose.local.yml down -v
```

This removes `sp2_b3a_control_data`, `sp2_b3a_tenant_acme_data`, `sp2_b3a_tenant_zeta_data`,
`sp2_b3a_tenant_nova_data`. There is no production data in them.

## 3. Remove the local env file (untracked secrets)

```
rm -f infrastructure/docker/.env.local
unset SP2_B3A_CONTROL_DB_DSN SP2_B3A_ACME_DB_DSN SP2_B3A_ZETA_DB_DSN SP2_B3A_NOVA_DB_DSN
```

## 4. Verify clean

```
docker compose -f infrastructure/docker/docker-compose.local.yml ps          # no services
docker volume ls | grep sp2_b3a || echo "no B-3A volumes remain"
git status --porcelain                                                        # no .env.local, no runtime artifacts
```

Confirm: no containers remain · no B-3A volumes remain (if deletion was authorized) · no secrets written to the repo ·
working tree clean.
