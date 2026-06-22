# module: tenant-db-bootstrap (versioned DDL baseline — NOT a tenant-DB creator)

Provider-neutral interface for the **versioned Tenant-DB bootstrap template** — the ordered set of DDL
templates applied to a **freshly created, physically distinct tenant database** to bring it to its baseline
schema. **Scaffold only** (PRD 06 B-3): contract only; no executable IaC, no DDL applied.

## What "template" means here (and what it is NOT)

```
"Template" = a VERSIONED SET OF DDL TEMPLATES applied, in order, to each new physical tenant database.
"Template" is NOT a cloned PostgreSQL TEMPLATE database (no CREATE DATABASE ... TEMPLATE clone). Cloning is
  forbidden: it risks provider portability constraints and can blur physical distinctness (IC-010 §O).
```

## The ownership boundary (D-15; DB3-8 — load-bearing)

This module is a **reusable bootstrap template that the Control-Plane provisioning workflow INVOKES**. It does
**not** create databases, does **not** name them authoritatively, and does **not** track them as IaC state.

```
Control Plane (D-15 automated, audited workflow)  →  creates the physically distinct tenant database, then
                                                      invokes this bootstrap template against it, then verifies
                                                      physical distinctness (IC-010 §P) before declaring Ready.
IaC (this module)                                 →  supplies the versioned DDL baseline only.
Database Router                                   →  selects the one tenant DB at request time (D-07/D-30); it
                                                      never creates or resolves during provisioning.
```

Tenant database **names** may follow the existing default convention `sp2_tenant_<tenant_ref>`
(`backend/control_plane/provisioning.py`), but the **Control-DB registry remains authoritative** (D-07);
naming is a non-authoritative default only.

## Inputs (references only)

```
environment        environment alias
tenant_ref         opaque tenant reference (registry-authoritative; naming default only)
target_db_ref      reference to the already-created physical tenant database (created by the control plane)
schema_version     a value within the D-17 supported range (expand/contract; version-gated readiness)
secret_ref         the tenant DB's own secret reference (D-14; resolved at connect time, never stored)
```

## Outputs (references only)

```
bootstrap_ref      reference to the applied baseline (consumed by the readiness/distinctness evidence record)
schema_targets     pointer to the ordered DDL families below
```

## DDL it would eventually apply, in order (applied later by the control-plane workflow, NOT in B-3)

```
infrastructure/db/provisioning/001_tenant_database.sql      (schema_version marker — IC-002 / D-17)
infrastructure/db/provisioning/002_distinctness_sentinel.sql (dv_sentinel.marker — IC-010 §P / DV-C4)
infrastructure/db/lineage/001_lineage_schema.sql            (lineage chain + bookkeeping)
infrastructure/db/lineage/002_append_only.sql               (UPDATE/DELETE/TRUNCATE-rejecting trigger; D-23)
infrastructure/db/lineage/003_roles.sql                     (per-DB GRANTs to the cluster-scoped lineage roles)
```

Idempotent, ordered, additive, standard PostgreSQL. Each file's blob pin is recorded in
`docs/infrastructure/b3_ddl_target_mapping.md`; a future gated phase applies the bytes unchanged.

## Readiness binding (documentation only)

A tenant reaches `Ready` (IC-002) only when reachability + schema-version compatibility (D-17) **and** Physical
Distinctness Verification (DV-C1..C7, IC-010 §P) **and** the distinctness-ledger collision check all pass —
**fail-closed**. This module supplies the baseline; the Control Plane performs verification. B-3 implements no
runtime activation.
