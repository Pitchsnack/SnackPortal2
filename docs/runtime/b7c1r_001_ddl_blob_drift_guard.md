# B-7C-1R — 001 DDL Blob-Drift Guard (B7C1-AR-1 closure)

**PRD:** PRD 06 B-7C-1R. Default-suite test hardening only — **no runtime, CI-workflow, or DDL change**, no
PostgreSQL, no secrets.

## What B-7C-1R adds

B-7C-1 added a default-suite DDL blob-drift guard
(`tests/architecture/test_b7c1_control_audit_ddl_blob_pins.py`) for the **control_audit** DDL (`002`/`003`).
Post-merge verification (B7C1-AR-1) found that a third live-PG harness —
`tests/control_plane/requires_pg/test_pg_distinctness_ledger.py` (B-4) — also git-blob-pins
`infrastructure/db/control/001_distinctness_ledger.sql`, but that DDL was **not** covered by the default
suite (so `001` drift would surface only on a manual live run).

B-7C-1R extends the same guard to cover **001**:

- `test_distinctness_ledger_ddl_blob_matches_pin` — asserts the LF-normalized git-blob SHA-1 of
  `001_distinctness_ledger.sql` equals the known pin **`30956ff1e85e8dab1c9f55cbfc121ee9212f3ca0`**.
- `test_distinctness_harness_pin_matches_current_ddl` — asserts `test_pg_distinctness_ledger.py`'s pin
  literal **`_REVIEWED_DDL_BLOB`** equals the recomputed `001` blob.

`001` is checked **separately** from `002`/`003`: the distinctness harness pins under the variable name
`_REVIEWED_DDL_BLOB`, not the control_audit harnesses' `_REVIEWED_002_BLOB`/`_REVIEWED_003_BLOB` — so it is
**not** folded into the 002/003 harness loop. The `002`/`003` coverage is unchanged.

## Effect

A future change to any of `001`/`002`/`003` now fails the **default-suite** CI gate (the full `pytest`
step added by B-7C-1) until the DDL guard pin **and** the corresponding `requires_pg` harness pin are
updated in lockstep — without a live database. The guard never applies DDL, never connects to PostgreSQL,
and reads the `requires_pg` harnesses read-only (the harnesses themselves are unmodified).

## Boundaries (unchanged)

No runtime source change · no CI-workflow change · no live-PG workflow / PostgreSQL service /
`SNACKPORTAL_TEST_DSN` · no DDL edit/application · no production activation · no frontend/Lovable change ·
no API-Gateway / Auth-Router / Database-Router change · **B5-BLK-4 remains OPEN** · **Physical Multi-Database
MVP mandatory** — B-7C-1R does **not** prove tenant physical multi-database routing.

## Completeness (B-7C-1R2)

This guard's `001`/`002`/`003` coverage is itself completeness-protected: the default-suite meta-guard
`tests/architecture/test_b7c1r2_control_ddl_pin_completeness.py` (PRD 06 B-7C-1R2) fails CI if a future
`infrastructure/db/control/004_*.sql` or a new `requires_pg` `_REVIEWED_*_BLOB` pin is added without
extending this guard — see `docs/runtime/b7c1r2_ddl_pin_completeness_meta_guard.md`.

## Next

The live durable-path CI workflow (ephemeral PostgreSQL, path-filtered/scheduled/manual, secret-free) is
**B-7C-2** and is out of scope here.
