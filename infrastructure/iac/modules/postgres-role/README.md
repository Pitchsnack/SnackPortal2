# module: postgres-role (substrate)

Provider-neutral interface for **cluster-scoped, least-privilege PostgreSQL roles**. **Scaffold only**
(PRD 06 B-3): contract only; no executable IaC, no DDL applied.

## Why this module is separate (object scope)

PostgreSQL **roles are cluster-global objects**, not per-database. Per-database `GRANT`s are applied to each
database at the right time (Control-DB setup; per-tenant bootstrap by the control-plane workflow). This module
covers only the **cluster-scoped role identities**; it does not own per-database grants or tenant lifecycle.

## Owns (substrate)

- The **D-15 provisioning identity** (`sp2_provisioner`, NOLOGIN group role with `CREATEDB`) — least-privilege,
  control-plane-scoped. (`infrastructure/db/provisioning/003_provisioning_role.sql`)
- The **lineage roles** (`lineage_writer` = INSERT/SELECT, `lineage_reader` = SELECT; `DELETE`/`TRUNCATE`
  granted to **no** role). (`infrastructure/db/lineage/003_roles.sql`)

## Does NOT own

- **Login credentials.** All roles' actual login secrets are resolved from the **D-14** secret store at connect
  time; `sp2_provisioner` is a NOLOGIN group role. No password is ever stored in IaC or here.
- Per-database `GRANT`s (applied per database, later, separately gated).
- Tenant database creation (Control-Plane D-15 workflow).

## Inputs (references only)

```
environment        environment alias
cluster_ref        reference from the postgres-cluster module
role_set           "provisioning" | "lineage"          (which cluster-scoped role template applies)
```

## Outputs (references only)

```
role_refs          opaque references to the created roles (consumed by control-db / tenant-db-bootstrap GRANT steps)
```

## DDL it would eventually carry (applied later, NOT in B-3)

```
infrastructure/db/provisioning/003_provisioning_role.sql   (sp2_provisioner; CLUSTER-scoped role)
infrastructure/db/lineage/003_roles.sql                    (lineage_writer / lineage_reader; CLUSTER-scoped roles
                                                            + per-DB GRANTs applied at the database level)
```

Idempotent (guarded role creation), least-privilege (D-15). B-3 records the blob pins; a future gated phase
applies the bytes unchanged.

## Portability

On managed providers, creating roles requires provider-privileged membership (`rds_superuser`,
`cloudsqlsuperuser`, the Azure admin role) — achieved without provider-proprietary features. Least-privilege is
preserved across all targets.
