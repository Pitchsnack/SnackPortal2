# PM-AR-1 / AT2-AR-1 / AT2-AR-2 — Required-CI DDL Coverage & Role-Security Guards (Phase A)

**PRD:** PRD 06 PM-AR-1 + AT2-AR-1 + AT2-AR-2 (Phase A of the PM-AR-1/AT2-AR-1/AT2-AR-2/AT-5 split).
**Test-only.** No runtime, DDL, `pyproject`, `ci.yml`, live-PG workflow, or B-7C meta-guard change. **AT-5
(docs-vs-workflow consistency + b7c2/atr4 reconciliation) is the separate, deferred Phase B and is NOT in this
change set.**

## What this adds (3 required-CI, pure-stdlib guards)

All three run in the **default (required) suite**, open no database, import no driver, and use no DSN/secret.

### PM-AR-1 — cross-family DDL-coverage meta-guard
`backend/tests/architecture/test_required_ci_ddl_coverage_meta_guard.py`. Program-level analogue of the
Control-DB-only B-7C-1R2 meta-guard. Keeps an explicit registry mapping each `infrastructure/db/<family>` to
its required-suite blob-drift guard:

| Family | Required-CI blob-drift guard |
|---|---|
| `control` | `test_b7c1_control_audit_ddl_blob_pins.py` (+ `test_b7c1r2_*` completeness) |
| `provisioning` | `test_non_control_ddl_blob_drift.py` |
| `lineage` | `test_non_control_ddl_blob_drift.py` |

- **INV-A (bidirectional):** on-disk families containing `*.sql` must equal the registry — a new unguarded
  `infrastructure/db/<newfamily>/*.sql`, or a stale registry key, FAILs.
- **INV-B (structural):** each registry guard exists and its source references the family's DDL dir via the
  `"infrastructure" / "db" / "<family>"` pathlib idiom — so a guard that no longer targets its family FAILs.
  (A bare "is the path referenced anywhere" check is deliberately avoided — boundary/secret tests reference the
  paths too and would mask a deleted blob-drift guard.)

### AT2-AR-1 — static least-privilege guard on `003_provisioning_role.sql`
`backend/tests/architecture/test_provisioning_role_static_security.py`. Required-CI early-warning complement to
the advisory live-PG AT-2 behavioral check. Extracts **only** the `CREATE ROLE sp2_provisioner` /
`ALTER ROLE sp2_provisioner` statements (regex `(?is)(?:CREATE|ALTER)\s+ROLE\s+sp2_provisioner\b[^;]*;`) and
checks privilege tokens there: `NOLOGIN` + `CREATEDB` required; `SUPERUSER`/`CREATEROLE`/`REPLICATION`/
`BYPASSRLS`/`LOGIN` forbidden (word-boundary tokens).

> **Parsing trap honored:** `003` contains "login credential" in a `--` header comment and in `COMMENT ON
> ROLE` — a whole-file `LOGIN` grep would false-positive. Extracting only the role statements excludes the
> comments. `\bLOGIN\b` also does not match inside `NOLOGIN` (no word boundary), so the required `NOLOGIN` and
> the forbidden `LOGIN` coexist safely. This is a static guard; it does **not** replace the live-PG AT-2
> behavioral check.

### AT2-AR-2 — lineage DDL applier-exclusivity guard
`backend/tests/architecture/test_lineage_ddl_applier_exclusivity.py`. Enforces that `_pg.py::apply_schema` is
the **sole** lineage DDL applier, keeping the ATR-1 applied-set cross-check (T6) authoritative. Asserts no
lineage `requires_pg` `test_*.py` harness references a `.sql` file, a `DDL_DIR` constant, or the lineage DDL
directory directly (`_pg.py` is the sanctioned applier and is exempt — it is not a `test_*.py` file).

## Gate posture

Required default suite. Adds new architecture tests; **mypy 0/231 → 0/234** (3 new `.py`); architecture/full
grow by the new test count. The existing guards (`test_b7c1_control_audit_ddl_blob_pins`,
`test_b7c1r2_control_ddl_pin_completeness`, `test_non_control_ddl_blob_drift`, `test_vendor_and_db_containment`)
are **unchanged** and still pass. The live-PG workflow is **untouched** (still 9 harnesses).

## What it does NOT do

- It does **not** edit any DDL, runtime source, `pyproject`, `ci.yml`, the live-PG workflow, the B-7C
  meta-guards, or the b7c2/atr4 docs (the latter two are Phase B / AT-5 reconciliation targets).
- It does **not** prove tenant **physical multi-database routing**.
- It does **not** close **B5-BLK-4** (which remains **OPEN**).
- It does **not** complete the **Physical Multi-Database MVP** (which remains **mandatory**, not future work).

## Boundaries

Test-coverage / guard hardening only · no production DB/DDL/secrets · no Supabase · no Database-Router /
API-Gateway / Auth-Router / frontend change · **B5-BLK-4 OPEN** · **Physical Multi-Database MVP MANDATORY** ·
human merge only. **AT-5 is deferred to Phase B.**
