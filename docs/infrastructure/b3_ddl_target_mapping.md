# PRD 06 B-3 — DDL → Target-Database Mapping

**Phase:** PRD 06 B-3 (documentation only). **B-3 applies NO DDL.** This document maps the existing, reviewed,
governed DDL families (`infrastructure/db/**`) to their target database and object scope, records each file's
blob pin, and states that application is **deferred** to a later, separately-gated phase that must apply the
**bytes unchanged**.

**Baseline:** `origin/main @ f346cf0`. Blob hashes below were captured with
`git rev-parse HEAD:<path>` against this baseline. A future phase MUST re-verify them and apply unchanged.

## Mapping

| DDL file | Target DB | Object scope | Applied by B-3? | Deferred to | Blob pin (`f346cf0`) |
|----------|-----------|--------------|------------------|-------------|----------------------|
| `infrastructure/db/control/001_distinctness_ledger.sql` | **Control DB** | database-scoped (table `control_distinctness_ledger`) | **No** | gated Control-DB DDL step | `30956ff1e85e8dab1c9f55cbfc121ee9212f3ca0` |
| `infrastructure/db/provisioning/001_tenant_database.sql` | **each Tenant DB** | database-scoped (table `schema_version`) | **No** | tenant bootstrap (control-plane) | `d3073e82a6b9b5dc3bc9774201c6932c956a6897` |
| `infrastructure/db/provisioning/002_distinctness_sentinel.sql` | **each Tenant DB** | database-scoped (schema `dv_sentinel`, table `marker`) | **No** | tenant bootstrap (control-plane) | `04b1401de262320e140d79f5133051f41ff92693` |
| `infrastructure/db/provisioning/003_provisioning_role.sql` | **cluster** | **cluster-scoped role** (`sp2_provisioner`) | **No** | role substrate (postgres-role) | `2564826cc2d00b63b2edf0c7f88fc2c88bcc853b` |
| `infrastructure/db/lineage/001_lineage_schema.sql` | **each Tenant DB** | database-scoped (lineage chain + bookkeeping) | **No** | tenant bootstrap (control-plane) | `5891b5dbce621bffda2ca15ac29cf6621d1dd725` |
| `infrastructure/db/lineage/002_append_only.sql` | **each Tenant DB** | database-scoped (append-only trigger; SQLSTATE `P6A01`) | **No** | tenant bootstrap (control-plane) | `e32be83c37ac37c3f3a96a3b008bd1b1b1dc0521` |
| `infrastructure/db/lineage/003_roles.sql` | **cluster** + **each Tenant DB** | **cluster-scoped roles** (`lineage_writer`/`lineage_reader`) + per-DB `GRANT`s | **No** | role substrate + tenant bootstrap | `b962d4ca2b0cbfbb9ac1ce0b11e2bdfa4cab6a33` |

## Application order (per target; future phase, gated)

```
Control DB:   control/001
Cluster:      provisioning/003 (sp2_provisioner) ; lineage/003 (lineage_writer/reader role objects)
Each Tenant DB (control-plane bootstrap, in order):
              provisioning/001 → provisioning/002 → lineage/001 → lineage/002 → lineage/003 (per-DB GRANTs)
```

## Properties (verified against the reviewed DDL)

- **Idempotent:** `CREATE TABLE/SCHEMA IF NOT EXISTS`, guarded `DO $$ … pg_roles …` role creation, conditional
  seed `INSERT … WHERE NOT EXISTS`. Re-apply is a no-op.
- **Additive / non-destructive:** no destructive migration; teardown is out-of-band (see `b3_teardown.md`).
- **Standard PostgreSQL:** no extensions, no provider-proprietary features (runs on AWS RDS / Azure / Cloud SQL
  / self-hosted, PG 11+ for lineage; D-17 supported range otherwise).
- **References only (D-14):** no passwords, DSNs, secret values, or PII in any DDL file.

## Object-scope caveat (portability)

PostgreSQL **roles are cluster-global**, not per-database. On managed providers, `CREATE ROLE` / `CREATE
DATABASE` / `CREATEDB` require provider-privileged membership (`rds_superuser`, `cloudsqlsuperuser`, the Azure
admin role). A portable rollout applies cluster-scoped objects once per cluster and database-scoped objects per
database, **without** relying on any provider-proprietary feature.

## Ownership (D-15; DB3-8)

`control/**` is Control-DB substrate DDL (applied in a gated Control-DB step). `provisioning/**` + `lineage/**`
are applied to a tenant DB **by the Control-Plane provisioning workflow at tenant onboarding**, after the
workflow creates the physically distinct database — **not** by IaC, and **not** per-tenant Terraform state. The
Control-DB registry remains authoritative for the tenant→database binding (D-07).

> B-3 records this mapping and the blob pins. It applies no DDL. A future, separately-gated phase verifies each
> blob pin and applies the reviewed bytes unchanged.
