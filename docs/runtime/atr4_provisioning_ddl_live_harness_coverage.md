# ATR-4 — Provisioning DDL Live Harness Coverage

**PRD:** PRD 06 ATR-4. **Test-only** coverage for the provisioning DDL templates — **no runtime, operator,
`main.py`, deferral, DDL/README, `pyproject`, `ci.yml`, or meta-guard change**, no production database, no
secrets. Closes the harness side of the gap the B-7C-2 note recorded
(`b7c2_live_pg_durable_path_ci.md`: "`infrastructure/db/provisioning/*.sql` is applied by **no** harness").

## The gap it closes

The three provisioning templates in `infrastructure/db/provisioning/` were, before ATR-4, applied by **no
runtime code and no test**:

- `PostgresProvisioningOperator` performs only `CREATE DATABASE` / `DROP DATABASE`.
- The distinctness evidence provider (`postgres_distinctness.py`) applies its **own embedded** sentinel
  DDL, **not** the `002` file.
- The verification probe (`postgres_probe.py`) only **reads** `schema_version`.

So the templates were unexercised SQL. ATR-4 adds a live-PostgreSQL harness that proves they apply
cleanly, are idempotent, and satisfy the runtime's **behavioral** expectations.

## What it runs

`backend/tests/control_plane/requires_pg/test_pg_provisioning_ddl.py` — a **standalone** script (driven by
`_pg.run()` in its `__main__`, not a pytest test; the dir is `--ignore`'d by the default suite). It runs in
the **advisory** `live-pg-durable-path.yml` workflow against an **ephemeral, disposable** PostgreSQL
service (run loop **8 → 9** harnesses). With `SNACKPORTAL_TEST_DSN` unset (or psycopg absent) it
clean-skips (exit 0); the workflow's non-vacuity gate fails a clean SKIP, so a green job means real
evidence.

| Template | DB context | What the harness proves |
|---|---|---|
| `001_tenant_database.sql` | a **scratch DATABASE** (`sp2_atr4_prov_scratch`) | `schema_version` table is created; the **exact** control-plane probe `SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1` observes the seeded `'1'`; re-apply does not re-seed (idempotent). |
| `002_distinctness_sentinel.sql` | the **same scratch DATABASE** | `dv_sentinel.marker` is created; the **exact** verifier write `INSERT … ON CONFLICT (ns) DO UPDATE …` + readback round-trips; re-apply preserves rows (idempotent). 002 hard-codes the literal `dv_sentinel` schema, so a scratch *database* (not a scratch *schema*) isolates it. |
| `003_provisioning_role.sql` | a **cluster role** (`sp2_provisioner`) | the role is created with `rolcreatedb=true` and `rolcanlogin=false` (NOLOGIN + CREATEDB); re-apply preserves attributes (idempotent). Roles are cluster-scoped, so it is dropped at start and in `finally`. |

The three templates are **independent** (001/002 are database-scoped; 003 is a cluster role) — each is
asserted to apply cleanly + idempotently on its own; **no ordered dependency is asserted** (the README
"apply in order" is a convention, not a dependency).

## Default-suite coverage guard

`backend/tests/architecture/test_atr4_provisioning_ddl_coverage.py` (pure stdlib, no DB) keeps the
coverage CI-visible even though the harness itself is `--ignore`'d and the live-PG workflow is advisory.
It asserts: (a) the three `.sql` templates exist; (b) the harness exists and references all three
template filenames; (c) the harness is listed in the `live-pg-durable-path.yml` run loop. Includes
non-vacuity tests that prove the reference/loop detection actually fails on a synthetic regression.

## Design pins (why they matter)

- **Harness location** `tests/control_plane/requires_pg/` — already in `pyproject` `addopts --ignore`
  (two literal dirs, not a glob); a new `tests/provisioning/` tree would run in the default suite and
  ERROR.
- **Blob pins** named `_PROVISIONING_DDL_SHA_001/002/003` (LF-normalized git-blob SHA-1), **not**
  `_REVIEWED_*_BLOB` — so the Control-DB-only B-7C-1R2 pin-completeness meta-guard is not tripped.
- **Driver** reached via `importlib.import_module("psycopg")` after a DSN check — never a static
  `import psycopg` (the default-suite driver-containment guard AST-scans for static driver imports).
- **Behavioral, not string-coupling** — the probe query and sentinel write/readback are exercised as
  behavior; the provider's embedded DDL constants are **not** imported or compared.

## Safety model (secret-free)

- `SNACKPORTAL_TEST_DSN` is used **by name only**; its value is never printed or stored. A superuser/admin
  DSN is required (003 needs `CREATEROLE`; 001/002 need `CREATE`/`DROP DATABASE`). The ephemeral CI
  service is the `postgres` superuser under trust auth — safe **only** because it is ephemeral,
  localhost-only, single-job, and holds no real data.
- DDL is applied **only** to the ephemeral service; the repo's `.sql` files are read-only and git-blob
  pinned by the harness.
- The scratch DATABASE is `DROP DATABASE IF EXISTS`'d in `finally`; the cluster role is
  `DROP ROLE IF EXISTS`'d at start and in `finally`. 003's role is NOLOGIN — no password is created.

## What it does NOT do

- It does **not** activate runtime provisioning (the `main.py` deferral stays), wire the `postgres`
  adapter, or change any runtime/operator code.
- It does **not** prove tenant **physical multi-database routing/isolation** (that needs ≥2 distinct
  clusters — what `test_b3a_multi_database_topology.py` is for; one ephemeral service is one cluster).
- It does **not** close **B5-BLK-4** (which remains **OPEN**).
- It does **not** complete the **Physical Multi-Database MVP** (which remains **mandatory**, not future
  work). ATR-4 must not be described as MVP progress.

## Boundaries

No runtime/operator/`main.py`/deferral change · no `infrastructure/db/**` `.sql`/README edit · no
`pyproject` (addopts) change · no `b7c1r2` meta-guard or driver-containment guard change · no `ci.yml`
change · no production DB/DSN/secret · no Supabase credential · no Database-Router / API-Gateway /
Auth-Router / frontend change · **B5-BLK-4 OPEN** · **Physical Multi-Database MVP mandatory** — ATR-4 is
test-coverage hardening only.

> **Note (reconciled by AT-5):** the `b7c2_live_pg_durable_path_ci.md` mismatch this note originally flagged
> (it described an "8 harnesses" run set with provisioning applied by no harness) has been **reconciled by
> AT-5**: `b7c2` now states a **9-harness** run set that lists `test_pg_provisioning_ddl.py`, and the
> docs-vs-workflow harness count is held in lockstep by the required-CI guard
> `backend/tests/architecture/test_live_pg_docs_workflow_consistency.py`. The historical "8 → 9" transition
> (above) is retained as history.
