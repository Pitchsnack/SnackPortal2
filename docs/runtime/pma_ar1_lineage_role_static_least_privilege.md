# PMA-AR-1 — Lineage Role Static Least-Privilege Guard

**PRD:** PRD 06 PMA-AR-1. **Test-only** required-CI static security coverage — **no runtime, DDL, `pyproject`,
`ci.yml`, or live-PG workflow change**, no production database, no secrets. Adds the required-suite static
least-privilege guard for the lineage roles that PR #32 added for the provisioning role (`sp2_provisioner` /
AT2-AR-1) — closing the lineage half of the role-security gap.

## The gap it closes

`infrastructure/db/lineage/003_roles.sql` defines the least-privilege lineage roles. Before PMA-AR-1 they were
covered by:

- the **advisory** live-PG behavioral harness `backend/tests/lineage_service/requires_pg/test_pg_privilege.py`
  (runs only in the advisory `live-pg-durable-path.yml` workflow — not a required check; DRIFT-08/F-2); and
- the **required** blob-drift guard (ATR-1, `test_non_control_ddl_blob_drift.py`) which catches *unreviewed byte
  changes* to `003` but asserts nothing about its *security intent*.

So a future **reviewed** edit to `003` could weaken lineage-role privileges and only an advisory job would
notice. PMA-AR-1 adds a required-CI static early-warning that fails the default suite if the lineage roles drift
from least-privilege — the static complement to the live check, exactly mirroring provisioning's
AT-2 (live) + AT2-AR-1 (static) + AT-1 (blob-drift) trio.

## The lineage role model (what the guard enforces)

`003_roles.sql` uses a deliberately **table-scoped** privilege model:

| Role | Chain tables (`lineage`, `lineage_segment`) | Import bookkeeping (`import_job`, `import_idempotency`, `import_checkpoint`) | Attributes |
|---|---|---|---|
| `lineage_writer` | **append-only**: `SELECT, INSERT` only + explicit `REVOKE UPDATE, DELETE, TRUNCATE` | **not** append-only: `SELECT, INSERT, UPDATE` (job/idempotency), `SELECT, INSERT` (checkpoint) — upserted by the import coordinator | `NOLOGIN` |
| `lineage_reader` | `SELECT` only | `SELECT` only | `NOLOGIN` |

`DELETE`/`TRUNCATE` are granted to **no** role on any table — append-only is absolute, and the `002` trigger is
the runtime backstop. The per-tenant `LOGIN` credential is resolved from the D-14 secret store at connect time
and is never stored in these files.

**Key subtlety (why the guard is table-scoped):** `lineage_writer` *legitimately* holds `UPDATE` on the import
bookkeeping tables. A role-global "writer has no UPDATE" rule would false-fail on correct DDL — so append-only is
asserted **only on the chain tables**, and the import-table grants are preserved.

## The guard

`backend/tests/architecture/test_lineage_role_static_security.py` (pure stdlib; no PostgreSQL, no DSN, no driver,
no connection; default suite; standalone-runnable). It strips comments and string literals, extracts the
executable `CREATE/ALTER ROLE` statements (which work inside the `DO $$ … $$;` block — they end at the first `;`)
and the `GRANT`/`REVOKE` statements (split per table), and asserts:

- **T1** — both `lineage_writer` and `lineage_reader` are `NOLOGIN` and carry **no** forbidden attribute
  (`SUPERUSER`, `CREATEROLE`, `REPLICATION`, `BYPASSRLS`, `LOGIN`). `\bLOGIN\b` does not match `NOLOGIN`. The
  required envelope is `NOLOGIN` only — **not** `CREATEDB` (lineage roles differ from `sp2_provisioner`).
- **T2** — append-only floor on the **chain tables**: the chain set is derived from the writer's destructive
  `REVOKE` statements and cross-checked to `{lineage, lineage_segment}`; on each, `lineage_writer`'s grants are
  `⊆ {SELECT, INSERT}` **and** the explicit `REVOKE UPDATE, DELETE, TRUNCATE` floor is present.
- **T3** — `lineage_reader` is `SELECT`-only on every table.
- **T4** — `DELETE`/`TRUNCATE` are granted to **neither** lineage role on **any** table.
- **T5** — parse sanity (≥2 role statements, ≥1 `REVOKE`, ≥1 `GRANT`) so the regexes cannot pass vacuously.

Plus non-vacuity tests (synthetic strings only — no tracked-file mutation) proving each detector fails on a
planted regression (unsafe attribute; standalone `LOGIN`; missing `NOLOGIN`; destructive chain-table `GRANT`;
missing chain-table `REVOKE`; reader non-`SELECT` grant) **and** — the table-scoping proof — that the real
`GRANT … UPDATE ON import_job … TO lineage_writer` is **not** flagged, and that `COMMENT ON ROLE`/comment prose
never reaches the enforcement path.

## What it does NOT do

- It does **not** prove live PostgreSQL state and does **not** replace `test_pg_privilege.py` (the advisory live
  behavioral check).
- It does **not** assert the `002_append_only.sql` **trigger** (the runtime append-only backstop) — that is
  separately blob-pinned by ATR-1.
- It does **not** edit any DDL (the DDL is already safe/least-privilege as written).
- It does **not** prove tenant **physical multi-database routing**, does **not** close **B5-BLK-4** (which
  remains **OPEN**), and does **not** complete the **Physical Multi-Database MVP** (which remains **mandatory**).
  PMA-AR-1 must not be described as MVP progress.
- It closes **only** the lineage-role static least-privilege gap. **PMA-AR-2** (cross-family role-security
  coverage meta-guard), **PMA-PM-1** (static↔live forbidden-set consistency), and **PMA-AR-3** remain **open**.

## Boundaries

No runtime source change · no `infrastructure/db/**` `.sql`/README edit · no `pyproject` (addopts) change · no
`ci.yml` change · no `live-pg-durable-path.yml` change · no edit to `test_provisioning_role_static_security.py`
(idiom reused), `_scan.py`, or any PR #31/#32/#33 / B-7C guard · no production DB/DSN/secret · no Supabase
credential · no Database-Router / API-Gateway / Auth-Router / frontend change · **B5-BLK-4 OPEN** · **Physical
Multi-Database MVP mandatory** — PMA-AR-1 is required-CI static security hardening only.
