# PRD 06 B-7A — Live PostgreSQL Control Audit DDL Exercise — Evidence

**Phase:** PRD 06 B-7A (controlled non-production live-PostgreSQL exercise of the created-not-applied `control_audit` DDL).
**Authorized by:** `PRD 06 B-7A — Execution Authorization R3 — Claude.md` (START-GATE phrase issued).
**Verdict:** `READY FOR PRE-MERGE VERIFICATION`.

> References-only / secret-safe (D-14): no DSN value, password, or credential appears here. `SNACKPORTAL_TEST_DSN` was used **by name only**; its value (and the in-memory unreachable DSN derived from it) was never printed, logged, or committed.

## Environment

| Field | Value |
|---|---|
| Baseline commit | `fc5c372` |
| Branch | `feat/prd-06-b7a-live-pg-control-audit-ddl` |
| PostgreSQL version | `server_version_num = 170010` (PostgreSQL 17.10) — satisfies the ≥ 11 gate |
| Connection | `SNACKPORTAL_TEST_DSN` env var (by name only; value never rendered); standalone `requires_pg` runner |
| Target isolation | throwaway scratch **schema** `sp2_b7a_control_audit_scratch` inside the non-production database referenced by `SNACKPORTAL_TEST_DSN` (DB name/value withheld); `search_path` set to the scratch schema alone |
| Production touched | **No** — non-production only; no CREATE/DROP DATABASE; `public`/real tables untouched |
| DDL files modified | **No** (read + blob-pinned only) |
| Runtime wired | **No** · Frontend/Lovable | **No** · B5-BLK-4 | **OPEN** |

## DDL blob verification (applied bytes == reviewed B-7 blobs, LF-normalized)

| File | Reviewed (R3 §10) | Computed at run | Match |
|---|---|---|---|
| `infrastructure/db/control/002_provisioning_audit.sql` | `887d0cbce636b7a4610272b584ad0aea61eb2294` | `887d0cbce636…` | ✅ |
| `infrastructure/db/control/003_provisioning_audit_append_only.sql` | `c787c5372c511dc1975d337cdfe871d2d849a2c4` | `c787c5372c51…` | ✅ |

## Results (all PASS — committed harness re-runs them deterministically)

| Check (R3 §) | Result |
|---|---|
| 16.1 PostgreSQL version gate (≥ 11) | ✅ `170010 >= 110000` |
| 16.2 table-absent precondition | ✅ `to_regclass('control_audit') IS NULL` before apply |
| 16.3a DDL blob pin (002 + 003) | ✅ both match the reviewed blobs |
| 16.3 DDL apply (002 → 003) | ✅ applied cleanly |
| 16.5 table shape | ✅ exact columns/order; `id bigint GENERATED ALWAYS AS IDENTITY` (identity_generation `ALWAYS`, default NULL); `actor/action/ts/correlation_id` NOT NULL; `tenant_id/from_state/to_state` NULLABLE; `ts timestamptz`; PK(`id`); **no CHECK** |
| 16.6 adapter-shape insert + DB-generated id | ✅ insert (id omitted) → `id=1` DB-generated; NULL `tenant_id/from_state/to_state` accepted; returned row matches |
| 16.12 timestamp compatibility | ✅ `now_iso()` bound at run time (both fractional and microseconds==0 forms) accepted; stored value round-trips timezone-aware; no assertion on fractional digits |
| 16.8 read-path ordering (`ORDER BY id ASC`) | ✅ 2 rows, strictly increasing DB-generated `id`, append order |
| 16.9 reference-only stored row | ✅ 2 rows; no DSN/password substring in any cell |
| 16.10/16.11 required-field rejection + no-partial-commit | ✅ NULL `actor`/`action`/`ts`/`correlation_id` each rejected; row count unchanged (no partial commit); connection usable after (autocommit isolation) |
| 16.13 append-only rejection | ✅ `UPDATE`/`DELETE`/`TRUNCATE` each raised; row + count unchanged; matched on rejection (no SQLSTATE assertion — `003` raises generic P0001, no `P6A01`) |
| 16.4 idempotency PROVEN | ✅ re-apply `002` preserves rows; re-apply `003` keeps append-only enforcing |
| 16.7 cross-instance durability | ✅ `append_audit` via store A (committed, discarded) → `list_audit` via fresh store B returns the row; type-stable fields (`actor`/`action`/`correlation_id`) match |
| 16.14a fail-closed: unreachable DSN | ✅ construction with an in-memory-derived unreachable DSN (port→1, `connect_timeout=2`; never printed) raised |
| 16.14b fail-closed: missing table | ✅ `list_audit()` against a dropped `control_audit` raised (did not return `[]` / fail-open) |
| 16.15 cleanup | ✅ `DROP SCHEMA … CASCADE` in `finally` (never DELETE/TRUNCATE); no residue |

Harness exit: `ALL B-7A CHECKS PASSED` / `ALL PASSED`.

## Fail-closed matrix (classification per R3 §16.14)

| Case | Class | Coverage |
|---|---|---|
| Unreachable DSN → adapter raises | adapter fail-closed | committed test (16.14a) |
| Missing `control_audit` → `list_audit()` raises (not `[]`) | adapter fail-closed | committed test (16.14b) |
| Missing `SNACKPORTAL_TEST_DSN` | clean SKIP (exit 0) | `_pg.available()` convention (standalone-only) |
| Invalid DDL blob pin | STOP precondition | committed test (16.3a asserts equality → would STOP on mismatch) |
| Append-only trigger missing / mutation succeeds | FAILURE condition (§23) | committed test (16.13 asserts rejection) |

## Forward defect (recorded — NOT fixed in B-7A; a B-7B runtime-wiring item)

`append_audit` binds a `now_iso()` **string** into the `ts timestamptz` column, but `list_audit` reconstructs `ControlAuditRecord(timestamp=<datetime>)` — the driver returns a `datetime` for `timestamptz` while `ControlAuditRecord.timestamp` is typed `str` (`backend/control_plane/records.py`). An adapter round-trip therefore does not return the written string. B-7A asserts only that the `str→timestamptz` **write** is accepted and round-trips timezone-aware; resolving the read-side type is deferred to B-7B.

## Scope confirmation

No runtime source modified · no DDL files modified · no production action · no runtime audit wiring · no frontend/Lovable change · **B5-BLK-4 remains OPEN** (this exercise reduces live-DDL evidence gaps; it does not close it). Changed files: the committed `requires_pg` harness, the B-7 boundary test's `_B7_TEST_FILES` (defense-in-depth append), and this evidence doc.
