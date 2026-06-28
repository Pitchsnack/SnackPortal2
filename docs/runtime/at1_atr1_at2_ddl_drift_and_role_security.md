# AT-1 / ATR-1 / AT-2 — DDL Blob-Drift Guards & Provisioning Role Security

**PRD:** PRD 06 AT-1 + ATR-1 + AT-2. **Test-only** hardening — **no runtime, DDL, `pyproject`, `ci.yml`,
B-7C meta-guard, or live-PG workflow change**, no production database, no secrets. Closes the highest-value
test gaps surfaced by ATR-4 post-merge verification.

## The gaps it closes

ATR-4 added a live-PG harness for the provisioning DDL, but two required-CI gaps remained, plus a
security gap in the role check:

- **AT-1 — provisioning DDL had no *required-suite* drift guard.** The provisioning templates
  (`infrastructure/db/provisioning/{001,002,003}.sql`) are blob-pinned inside the ATR-4 live-PG harness, but
  that harness is `--ignore`'d by the default suite and runs only in the **advisory** live-PG workflow — so a
  provisioning DDL edit could avoid required-CI detection.
- **ATR-1 — lineage DDL had *no* drift guard at all.** `infrastructure/db/lineage/{001_lineage_schema,
  002_append_only,003_roles}.sql` are **applied live** by `tests/lineage_service/requires_pg/_pg.py::apply_schema`
  (used by all four lineage `requires_pg` harnesses) but were pinned by nothing.
- **AT-2 — `sp2_provisioner` was only *positively* asserted.** ATR-4 checked `rolcreatedb=true` /
  `rolcanlogin=false` but not the **negative** least-privilege attributes, so a privilege-escalation edit to
  `003_provisioning_role.sql` (e.g. an added `SUPERUSER`/`CREATEROLE`) would pass unnoticed.

## What was added (3 files)

| File | Purpose |
|---|---|
| `backend/tests/architecture/test_non_control_ddl_blob_drift.py` | **NEW** combined default-suite (required-CI) blob-drift guard — AT-1 (provisioning) + ATR-1 (lineage). Pure stdlib; no PostgreSQL/DSN/driver. |
| `backend/tests/control_plane/requires_pg/test_pg_provisioning_ddl.py` | **MODIFIED** (AT-2) — the live-PG provisioning harness now asserts the full `sp2_provisioner` least-privilege vector. Blob-pin lines unchanged. |
| `docs/runtime/at1_atr1_at2_ddl_drift_and_role_security.md` | **NEW** — this note. |

## AT-1 + ATR-1 — the default-suite guard

`test_non_control_ddl_blob_drift.py` recomputes the LF-normalized git-blob SHA-1 of each DDL file and is the
**single source of truth** in the required suite. Pins use `_PROVISIONING_DDL_SHA_BY_FILE` /
`_LINEAGE_DDL_SHA_BY_FILE` (deliberately **not** `_REVIEWED_*_BLOB`, so the Control-DB-only B-7C-1R2
meta-guard is untouched and not tripped).

**AT-1 (provisioning)** asserts: (T1) each `.sql` blob == its pin; (T2) directory completeness — the
`infrastructure/db/provisioning/*.sql` set on disk == the pinned set (a new/renamed/removed file fails);
(T3) harness cross-check — the ATR-4 harness's scalar pins `_PROVISIONING_DDL_SHA_001/002/003` == the guard
pin == the current blob (so a governed DDL change must update guard **and** harness in lockstep).

**ATR-1 (lineage)** asserts: (T4) each `.sql` blob == its pin; (T5) directory completeness for
`infrastructure/db/lineage/*.sql`; (T6) applied-set cross-check — the file set in the
`_pg.apply_schema()` for-loop tuple == the pinned set, **both directions** (a lineage DDL applied-but-unpinned,
or pinned-but-no-longer-applied, fails). Lineage harnesses pin nothing themselves — they only *apply* — so the
cross-check is against `_pg.py`, not a harness blob pin.

Plus non-vacuity tests proving each helper fails on a synthetic drift / extra / missing / unparseable input.
The B-7C-1R2 meta-guard **stays Control-DB-only by design**; provisioning/lineage completeness is provided by
this guard's own directory checks (T2/T5), not by broadening the meta-guard.

## AT-2 — `sp2_provisioner` least-privilege

After applying `003`, the harness now reads
`SELECT rolcreatedb, rolcanlogin, rolsuper, rolcreaterole, rolreplication, rolbypassrls FROM pg_roles` and
asserts the vector `(True, False, False, False, False, False)` — CREATEDB **on**; superuser / create-role /
replication / bypass-RLS / login all **off** — both after apply and after the idempotent re-apply. This is
behavioral DB evidence (not a text grep). The ATR-4 role lifecycle is preserved: `DROP ROLE IF EXISTS
sp2_provisioner` at start and in `finally`, with zero residue after the run. The DSN is used by name only; the
driver is reached via dynamic `importlib.import_module("psycopg")`; the blob-pin lines are unchanged.

## CI posture

- **AT-1 + ATR-1** run in the **default (required) suite** — provisioning and lineage DDL drift is now
  required-CI enforced (no PostgreSQL needed).
- **AT-2** is a live-PG harness assertion — it runs in the **advisory** `live-pg-durable-path` workflow
  (DRIFT-08: not yet a required check). The live-PG run count stays **9** (no workflow change).

## What it does NOT do

- It does **not** change any DDL, runtime/operator/`main.py`, `pyproject`, `ci.yml`, the B-7C meta-guards, or
  the live-PG workflow.
- It does **not** prove tenant **physical multi-database routing**.
- It does **not** close **B5-BLK-4** (which remains **OPEN**).
- It does **not** complete the **Physical Multi-Database MVP** (which remains **mandatory**, not future work).

## Boundaries

Test-coverage hardening only · no production DB/DDL/secrets · no Supabase · no Database-Router / API-Gateway /
Auth-Router / frontend change · **B5-BLK-4 OPEN** · **Physical Multi-Database MVP MANDATORY** · human merge only.
