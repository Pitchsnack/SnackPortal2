# module: control-db (substrate)

Provider-neutral interface for the **Control Database** as substrate — the **singular**, physically separate,
control-plane-owned global/cross-tenant database. **Scaffold only** (PRD 06 B-3): contract only; no executable
IaC, no DDL applied.

## Owns (substrate)

- One physically separate Control Database on the `postgres-cluster` substrate.
- The placeholder for control-plane-owned schema (applied later, separately gated): the durable distinctness
  ledger and other `control_*` tables. **B-3 applies no DDL** — see the DDL target mapping.

## Does NOT own

- **Tenant databases.** Those are per-tenant, physically separate, and created by the **Control-Plane D-15
  workflow** — never by this module. This module provisions exactly one database (the Control DB).
- Tenant business payloads. The Control DB stores **references and control-plane state only** (tenant registry,
  lifecycle/readiness state, the distinctness ledger inventory, provisioning/verification state, membership /
  federation / directory, reference-only audit) — **never** tenant startup/investor/deal records, raw DSNs,
  credentials, or PII (IC-002; IC-001 Global Audit Representation Rule; D-14).

## Inputs (references only)

```
environment        environment alias
cluster_ref        reference from the postgres-cluster module
database_alias      "control"
admin_secret_ref    secret reference for the Control-DB admin identity (resolved at connect time; never stored)
app_secret_ref      secret reference for the Control-DB application identity (resolved at connect time; never stored)
```

## Outputs (references only)

```
control_db_ref      opaque reference to the Control DB (registry-authoritative anchor; consumed by the
                    control-plane workflow and the Database Router resolution path)
schema_targets      pointer to infrastructure/db/control/** (the reviewed DDL to be applied in a later, gated phase)
```

## DDL it would eventually carry (applied later, NOT in B-3)

```
infrastructure/db/control/001_distinctness_ledger.sql   (control_distinctness_ledger; blob 30956ff1e8 — apply UNCHANGED)
```

Idempotent, additive, standard PostgreSQL. B-3 records the blob pin; a future gated phase applies the bytes
unchanged. See `docs/infrastructure/b3_ddl_target_mapping.md`.

## Boundary

There is exactly **one** Control DB. It is physically separate from every Tenant DB; a control-plane connection
is never reused to read or write tenant data (D-30). The Control DB holds the **registry** that makes the
tenant→database binding authoritative (D-07) — the Database Router resolves against it but selection remains the
Router's sole responsibility.
