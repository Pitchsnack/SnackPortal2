# infrastructure/iac/modules — Provider-neutral substrate modules (interfaces)

Module **interfaces and boundaries** for the cloud-portable Physical Multi-Database substrate. **Scaffold
only** (PRD 06 B-3): each module is described as a README contract — inputs/outputs expressed as
**references**, not values — without binding SnackPortal2 to any one cloud provider and without committing
executable IaC.

## Module map and ownership boundary (DB3-8)

| Module | Owns (substrate) | Explicitly does NOT own |
|--------|------------------|--------------------------|
| `postgres-cluster/` | The PostgreSQL cluster/server substrate (engine version, networking boundary, parameter baseline) — vendor-neutral, standard PostgreSQL. | Any database contents; any tenant lifecycle. |
| `control-db/` | The **singular** Control Database as substrate (the physically separate global/cross-tenant DB). | Tenant databases (those are per-tenant, control-plane-created). |
| `postgres-role/` | **Cluster-scoped** least-privilege roles (e.g. the D-15 provisioning identity; lineage roles). | Per-database GRANTs at tenant-creation time (control-plane workflow); login credentials (D-14 secret store). |
| `tenant-db-bootstrap/` | The **versioned DDL baseline** (a *template of DDL templates*) applied to a freshly created physical tenant DB. | Creating, naming-authoritatively, or tracking tenant databases. **Creation is the Control-Plane D-15 workflow.** |

**The load-bearing rule (D-15; DB3-8):** IaC provides reusable **substrate** and a reusable **bootstrap
template**. The **Control Plane** performs tenant lifecycle and **per-tenant physical database creation /
teardown** (`backend/control_plane/provisioning.py` — the automated, audited provisioning workflow).
OpenTofu/Terraform must **not** enumerate or track each tenant database as long-lived state. The
**Database Router** selects exactly one physical database registry-authoritatively (D-07/D-30); it never
creates or resolves a database during provisioning.

## Reference-only interface vocabulary (D-14)

Module inputs/outputs use **references and aliases**, never values:

```
environment        e.g. "local" | "nonprod"            (environment alias; never a real account/host)
provider_alias     e.g. "aws" | "azure" | "gcp" | "self-hosted"  (selects a provider adapter; not a credential)
database_alias     e.g. "control" | "tenant"           (logical role of the database)
database_kind      "control" | "tenant"                (distinctness/topology class)
tenant_ref         opaque tenant reference             (registry-authoritative; naming is a non-auth default)
secret_ref         e.g. "ref:control-db-admin@v1"      ({store-ref, version}; resolved at connect time, never stored)
readiness_ref      reference to the readiness/distinctness evidence record (control-plane-owned)
```

No module input or output may carry a raw password, raw DSN, credentialed connection string, cloud access
key, API token, JWT, or session token. Secret material is resolved from the D-14 pluggable secret store
in-memory at connect time and is never persisted into IaC, state, logs, or reports.

## Portability

Every module targets **standard PostgreSQL** runnable on AWS RDS / Azure Database for PostgreSQL / Google
Cloud SQL / self-hosted — no provider-proprietary extensions or features, no Docker dependency. Provider
specifics (where unavoidable) are isolated behind the provider-neutral interface via a `provider_alias`,
not baked into the module contract.
