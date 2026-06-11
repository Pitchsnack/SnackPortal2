# Tenant-DB Lineage Schema & Append-Only Enforcement (Build Phase 6)

Portable, standard-PostgreSQL DDL applied **per tenant database** as an expand/contract,
version-gated migration (D-17). Closes **V-OBS-1**: the DB itself enforces append-only on the
lineage chain, complementing the per-tenant cryptographic hash-chain (D-23 defense-in-depth).
Infrastructure-owned (D-15), deployable independently of application code; no provider-
proprietary features (runs on AWS RDS / Azure / Cloud SQL / self-hosted, PG 11+).

## Apply order
1. `001_lineage_schema.sql` — `lineage` (chain) + `lineage_segment` (archival summary) +
   import bookkeeping tables. `seq BIGINT UNIQUE` (fork fail-closed), `parent_lineage_ref` FK
   (acyclic backward edges), `marker_version` (canonicalizer selector), keyset/graph indexes.
2. `002_append_only.sql` — trigger rejecting `UPDATE`/`DELETE`/`TRUNCATE` on `lineage`
   (SQLSTATE `P6A01`). Preventive layer 1 of D-23.
3. `003_roles.sql` — least-privilege `lineage_writer` (INSERT/SELECT only) and
   `lineage_reader` (SELECT). `DELETE`/`TRUNCATE` are granted to **no** role.

## Secrets
These files contain **no credentials**. The per-tenant LOGIN role's password is resolved
from the D-14 secret store at connect time and is never stored here. Provisioning (D-15)
grants the tenant login role membership in `lineage_writer`.

## Append-only vs. retention (D-24)
The append-only trigger is absolute. Policy-driven expiry (when D-08 values exist) acts on
the **referent** (tenant data / its encryption key) and appends a tombstone — it never
updates or deletes a `lineage` row. So a missing/altered lineage row is always tampering,
never legitimate expiry.

## Verification
`backend/tests/lineage_service/requires_pg/` exercises this schema against a live PostgreSQL
(append-only rejection, `UNIQUE(seq)` fork prevention, advisory-lock acquisition,
recursive-CTE traversal, privilege enforcement). Set `SNACKPORTAL_TEST_DSN` to run; the suite
skips cleanly otherwise. This is the binding P6-V1 acceptance evidence.
