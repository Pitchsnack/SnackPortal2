# PMA-AR-2 — Role-Security Coverage Meta-Guard

**PRD:** PRD 06 PMA-AR-2. **Test-only** required-CI meta-guard — **no runtime, DDL, `pyproject`, `ci.yml`, or
live-PG workflow change**, no production database, no secrets. Ensures security-sensitive role-bearing DDL cannot
exist without an explicit required-suite **static role-security (least-privilege) guard**, and that those guards
stay **collected** by the required default suite.

## The gap it closes

Two role-security static guards exist — `test_provisioning_role_static_security.py` (AT2-AR-1, `sp2_provisioner`)
and `test_lineage_role_static_security.py` (PMA-AR-1, `lineage_writer`/`lineage_reader`). Before PMA-AR-2 nothing
asserted, at the **program level**, that *every* role-bearing DDL family stays represented by a required-suite
static role-security guard, nor that those guards stay collected by the required suite. A future PR could:

- add role-bearing DDL with no static guard;
- rename/remove a role-security guard;
- de-collect a guard from the required suite (e.g. a `pyproject` `testpaths`/`addopts` change);

while the docs still claimed required-CI coverage. PMA-AR-2 closes that coverage / registry / required-CI
durability gap. It is the **role-security analogue of PM-AR-1** (`test_required_ci_ddl_coverage_meta_guard.py`,
which does the same for DDL *blob-drift* coverage) — **complementary, not a duplicate** (different concern).

## Covered role families (the live registry)

| Family | Role-defining DDL | Roles | Static guard |
|---|---|---|---|
| provisioning | `infrastructure/db/provisioning/003_provisioning_role.sql` | `sp2_provisioner` | `backend/tests/architecture/test_provisioning_role_static_security.py` |
| lineage | `infrastructure/db/lineage/003_roles.sql` | `lineage_writer`, `lineage_reader` | `backend/tests/architecture/test_lineage_role_static_security.py` |

These are the **only** two role-bearing DDL families in the repo (control/* and the other provisioning/lineage
templates contain no role statements). No unguarded role-bearing DDL exists.

## The guard

`backend/tests/architecture/test_role_security_coverage_meta_guard.py` (pure stdlib; no PostgreSQL, no DSN, no
driver, no connection; default suite; standalone-runnable). It reads guard **source text** only — it never
imports/executes the guards or runs DDL, and runs no `pytest --collect-only` subprocess. It asserts:

- **INV-A (bidirectional, file-level).** The set of `infrastructure/db/**/*.sql` files that contain an executable
  role-DEFINING statement (or role-MEMBERSHIP grant) equals the set registered in the coverage registry (∪ an
  explicit excluded-with-reason set). An **unknown** role-bearing file (new, unregistered) and a **stale** registry
  entry (file gone / no longer role-bearing) both FAIL.
- **INV-B (per family).** Each family's static guard exists under `backend/tests/architecture/`, is named
  `test_*.py`, has ≥1 top-level `def test_` and no module-level skip, and its source text anchors every registered
  role name AND its DDL path basename (so a guard drifted off its family FAILs).
- **INV-C (collection durability).** A read-only static parse of `backend/pyproject.toml` confirms `testpaths`
  covers `tests/architecture` and the `addopts --ignore` set does NOT cover `tests/architecture` or any registry
  guard path; and the meta-guard itself + every registry guard live under `tests/architecture` and are `test_*.py`.

### Detection trigger (precise)

A DDL file is "role-bearing" (requires a static role-security guard) iff, after stripping `--`/`/* */` comments
and neutralizing single-quoted string literals, it contains:

- a **role-DEFINING** statement: `CREATE`/`ALTER`/`DROP` `ROLE`/`USER`; or
- a **role-MEMBERSHIP** grant: `GRANT <role> TO <role>` (no `ON`).

**Table-privilege** `GRANT … ON <table> TO role` / `REVOKE … ON <table> FROM role` do **not** trigger a new family
(they assign privileges to a role *defined elsewhere* — that defining file is already a family). Comments and
`COMMENT ON ROLE` / string-literal prose are stripped, so they never create a false coverage requirement.

Plus non-vacuity tests (synthetic strings only — no tracked-file mutation) proving each detector/inv fails on a
planted regression: unknown/stale registry (RED-1/2/3), missing guard file (RED-4), guard mis-located/mis-named/
no-`test_` (RED-5/6/7), role/DDL not anchored in guard text (RED-8/9), comment-only & literal CREATE ROLE not
detected (RED-10/11), `--ignore=tests/architecture` trips INV-C (RED-12), and a table-privilege GRANT is **not** a
family trigger (RED-13).

## What it does NOT do

- It does **not** re-assert least-privilege (the individual AT2-AR-1 / PMA-AR-1 guards do that) — it is a
  **coverage/registry/collection** meta-guard.
- It does **not** prove static↔live consistency with `test_pg_privilege.py` (that is **PMA-PM-1**, open).
- It does **not** run live PostgreSQL, edit DDL, or duplicate PM-AR-1 (blob-drift coverage).
- Its collection check is a **strong static proxy**: it parses `pyproject.toml` but cannot catch a `conftest.py`
  `collect_ignore` or an unrelated collection error — those remain outside its reach.
- It does **not** prove tenant **physical multi-database routing**, does **not** close **B5-BLK-4** (which remains
  **OPEN**), and does **not** complete the **Physical Multi-Database MVP** (which remains **mandatory**). PMA-AR-2
  must not be described as MVP progress.

## Follow-ups it closes vs leaves open

- **Closes:** `PMA-AR-1-PMV-3` (role-security guard registry / meta-completeness — this *is* it),
  `PMA-AR-1-AR-10` (lineage guard-existence meta-check — subsumed by INV-B), and `PMA-AR-1-PMV-1` (required-CI
  collection durability) **for the role-security guards** (via INV-C).
- **Leaves open:** `AT5-AR-14` / `AT5-AR-6` (collection durability + existence of the AT-5 docs↔workflow guard —
  a different guard), blob-drift guard collection durability (PM-AR-1 / b7c1r2 guards), `PMA-PM-1`, `PMA-AR-3`,
  `PMA-AR-1-AR-1..9`, the AT5-AR cluster, F-2/DRIFT-08, B5-BLK-4. A future **program-wide** "every required-CI
  guard stays collected" meta-guard would consolidate INV-C + AT5-AR-14 + blob-drift collection.

## Boundaries

No runtime source change · no `infrastructure/db/**` `.sql`/README edit · no `pyproject` (addopts) **edit**
(read-only input) · no `ci.yml` change · no `live-pg-durable-path.yml` change · no edit to
`test_provisioning_role_static_security.py` / `test_lineage_role_static_security.py` /
`test_required_ci_ddl_coverage_meta_guard.py` (PM-AR-1) / `_scan.py` / any B-7C / PR #31–#34 guard · no production
DB/DSN/secret · no Supabase credential · no Database-Router / API-Gateway / Auth-Router / frontend change ·
**B5-BLK-4 OPEN** · **Physical Multi-Database MVP mandatory** — PMA-AR-2 is required-CI coverage hardening only.
