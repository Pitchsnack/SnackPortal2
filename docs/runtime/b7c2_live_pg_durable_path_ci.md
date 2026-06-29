# B-7C-2 — Live-PG Durable Path CI

**PRD:** PRD 06 B-7C-2. **Advisory** CI infrastructure + live-test evidence only — **no runtime, DDL, `requires_pg`
harness, `ci.yml`, or `pyproject` change**, no production database, no secrets.

## What it runs

`.github/workflows/live-pg-durable-path.yml` runs the PostgreSQL-dependent **durable-path harnesses** — which are
**excluded from the default suite** (`backend/pyproject.toml` `addopts --ignore=…/requires_pg`) — against an
**ephemeral, disposable** PostgreSQL service container, so they move from manual-only evidence to repeatable CI
evidence.

These harnesses are **standalone scripts**, not pytest tests: each takes a `conn`/`admin_dsn` argument supplied by
`_pg.run()` in its `__main__` block (there is no pytest fixture). The workflow therefore invokes each via
`python <file>` — **not** `pytest` — and applies a **non-vacuity gate** (below).

**Run set (9 harnesses):**

- `tests/control_plane/requires_pg/` — `test_pg_distinctness.py`, `test_pg_distinctness_ledger.py`,
  `test_pg_control_audit_ddl.py`, `test_pg_control_store_runtime_wiring.py`, `test_pg_provisioning_ddl.py`
- `tests/lineage_service/requires_pg/` — `test_pg_append_only.py`, `test_pg_chain_serialization.py`,
  `test_pg_privilege.py`, `test_pg_traversal.py`

**Excluded:** `test_pg_distinctness`'s sibling `test_b3a_multi_database_topology.py` is **NOT** run here — it
requires **four physically distinct clusters** (`SP2_B3A_CONTROL_DB_DSN` / `_ACME_` / `_ZETA_` / `_NOVA_`) and
asserts four distinct `system_identifier`s, which a single ephemeral service cannot represent. It is the physical
multi-DB **topology** proof that **B-7C-2 explicitly does not make** (see *What it does NOT do*).

## Non-vacuity gate (fail-closed)

`_pg.run()` prints `SKIP …` and **exits 0** when the DSN or driver is absent — so a green job could otherwise have
exercised nothing. For each harness the workflow therefore **fails the job** unless it: exits 0, **and** emits real
PASS evidence (`PASS:` lines and/or an `ALL … PASSED` sentinel), **and** prints **no** `SKIP`, **and** prints no
`FAIL:`/`ERROR:`. A clean SKIP is treated as a non-vacuity failure.

## Safety model (secret-free)

- **DSN:** `SNACKPORTAL_TEST_DSN = postgresql://postgres@localhost:5432/postgres` — set only in the workflow env. It
  is **NOT** a repository / organization / environment secret, carries **no password**, and **must NEVER point at
  production or Supabase**. It is used **by name only** by the harnesses (its value is never logged).
- **`POSTGRES_HOST_AUTH_METHOD=trust`** is safe **only** because the service is an **ephemeral, single-job,
  localhost-only** container that holds no real data and is destroyed with the job. The connecting `postgres`
  superuser is required because the harnesses span SCHEMA (scratch schemas), DATABASE (the provisioning operator
  creates/drops disposable databases), and ROLE (`SET LOCAL ROLE`) DDL — all on the disposable service only.
- **No production DDL:** DDL is applied **only** to the ephemeral service by the harnesses; the repo's `.sql` files
  are read-only (and, for the control DDL, git-blob-pinned by the existing default-suite guards).
- **`PGOPTIONS`** sets `lock_timeout`/`statement_timeout` so the job fails fast instead of hanging.
- The workflow declares its **own** `permissions: contents: read` and uses **no** `pull_request_target` (so the
  default-suite secret-scan workflow guard, which forbids that trigger across all workflows, stays green).

## Triggers & status

`workflow_dispatch` (manual; with an optional default-`false` `inject_bad_dsn` negative-control toggle) +
`schedule` (weekly) + **path-filtered** `push`/`pull_request` on `infrastructure/db/**`,
`backend/tests/**/requires_pg/**`, and the workflow file itself. The default `ci.yml` workflow is **unchanged** (its
triggers stay un-narrowed; path-filtering lives only here).

**This job is ADVISORY / not a required status check** (DRIFT-08: branch protection is unavailable on this private
repo). It runs and reports, but governance enforcement remains process-level (Guard 7 / governed cycle).

## What it does NOT do

- It does **not** prove tenant **physical multi-database routing** (`test_b3a_*` is excluded; one ephemeral service
  is one cluster).
- It does **not** close **B5-BLK-4** (which remains **OPEN**).
- It does **not** complete the **Physical Multi-Database MVP** (which remains mandatory).
- It did **not**, at B-7C-2 time, add a blob-drift guard for the **lineage** DDL:
  `tests/lineage_service/requires_pg/_pg.py` *applies* `infrastructure/db/lineage/{001,002,003}.sql` live in CI.
  *(Superseded: **ATR-1 is now CLOSED** — PR #31 added the required-suite lineage blob-drift guard
  `backend/tests/architecture/test_non_control_ddl_blob_drift.py`.)*
- It did **not**, at B-7C-2 time, assert that the provisioning DDL is exercised by a live harness.
  *(Superseded by ATR-4: `infrastructure/db/provisioning/{001,002,003}.sql` is now applied live by
  `tests/control_plane/requires_pg/test_pg_provisioning_ddl.py` — the 5th control_plane harness in the run set
  above.)*

## Boundaries

No runtime source change · no `ci.yml` change · no `pyproject` (addopts) change · no DDL edit/application outside the
ephemeral CI database · no `requires_pg` harness change · no production DB/DSN/secret · no Supabase credential · no
frontend/Lovable change · no API-Gateway / Auth-Router / Database-Router change · **B5-BLK-4 OPEN** · **Physical
Multi-Database MVP mandatory** — B-7C-2 is CI evidence hardening only.
