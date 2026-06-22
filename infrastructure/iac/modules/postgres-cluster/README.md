# module: postgres-cluster (substrate)

Provider-neutral interface for the **PostgreSQL cluster/server substrate** that hosts the physically
separate Control Database and the per-tenant Tenant Databases. **Scaffold only** (PRD 06 B-3): this README
defines the contract; no executable IaC is committed.

## Owns (substrate)

- A standard-PostgreSQL cluster/server instance (engine + version within the D-17 supported range), reachable
  on a defined network boundary.
- A vendor-neutral parameter baseline (no provider-proprietary extensions or features).

## Does NOT own

- Any database contents, schema, or data.
- Any tenant lifecycle. Tenant databases are created by the **Control-Plane D-15 workflow**, not here.
- Login credentials. Credentials are resolved from the **D-14** secret store at connect time (never stored).

## Inputs (references only)

```
environment        environment alias (e.g. "local" | "nonprod")
provider_alias     "aws" | "azure" | "gcp" | "self-hosted"   (selects a provider adapter; not a credential)
postgres_version   a value within the D-17 supported schema/engine range
network_boundary   reference to the non-public network boundary (no public exposure of tenant data paths)
admin_secret_ref   secret reference for the cluster admin identity (e.g. "ref:cluster-admin@v1"); resolved at
                   connect time, never persisted
```

## Outputs (references only)

```
cluster_ref        opaque reference to the provisioned cluster (consumed by control-db / postgres-role modules)
endpoint_alias     non-credentialed endpoint alias (host/port reference; never a credentialed DSN)
```

## Portability

Targets AWS RDS / Azure Database for PostgreSQL / Google Cloud SQL / self-hosted interchangeably. Cluster-level
privileged operations (`CREATE ROLE`, `CREATE DATABASE`) require provider-privileged membership on managed
services (e.g. `rds_superuser`, `cloudsqlsuperuser`, the Azure admin role) — these are achieved **without**
provider-proprietary features. See `docs/infrastructure/b3_ddl_target_mapping.md` for the cluster-vs-database
object-scope split.

## Boundary

The cluster is **shared hosting substrate**; physical isolation is achieved at the **database** level (one
physically separate database per tenant + a separate Control DB), never via a `tenant_id` column or a shared
schema (IC-010 §O). This module never blurs that boundary.
