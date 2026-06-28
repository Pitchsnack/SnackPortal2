# B-7C-1R2 — Control-DB DDL / Harness-Pin Completeness Meta-Guard (B7C1R-AR-1 closure)

**PRD:** PRD 06 B-7C-1R2. Default-suite test hardening only — **no runtime, CI-workflow, or DDL change**, no
PostgreSQL, no DSN, no secrets, no `requires_pg` harness edit.

## What B-7C-1R2 adds

B-7C-1/1R built a default-suite blob-drift guard
(`tests/architecture/test_b7c1_control_audit_ddl_blob_pins.py`) that pins the reviewed Control-DB DDL
(`001`/`002`/`003`) and cross-checks the live-PG harness pins — but it enumerates that coverage **by hand**.
Two silent-escape paths remained:

- a future `infrastructure/db/control/004_*.sql` would not be noticed (the guard checks `001`/`002`/`003` by
  name), so the new DDL would ship **unpinned** with CI still green; and
- a future `requires_pg` harness declaring a new `_REVIEWED_*_BLOB` pin would not be cross-checked (the guard
  uses a hardcoded harness list).

B-7C-1R2 adds a **completeness meta-guard**
(`tests/architecture/test_b7c1r2_control_ddl_pin_completeness.py`) that closes both — in the **default suite**,
with no database:

- **INV-A — DDL completeness (bidirectional):** the set of `infrastructure/db/control/*.sql` files on disk
  must equal the set of DDL files the blob-drift guard declares. A new `004_*.sql` (forward) or a
  deleted/renamed-but-still-pinned DDL (reverse) fails the default suite, each with a message naming the file.
- **INV-B — harness-pin completeness:** every reviewed pin in `requires_pg/` that is **Control-DB-associated**
  must be cross-checked by the blob-drift guard (its harness in the guard's harness set, its variable
  referenced by the guard). A new control harness/pin fails until the guard accounts for it.
- **INV-C — no silent out-of-scope pin:** the set of non-control pins is asserted empty on `main`, so a future
  non-control pin trips this guard for **conscious** classification.

## Design (the two corrections that make it sound)

- **Independent discovery is the authority.** The meta-guard globs the Control-DB DDL dir and scans
  `requires_pg/` itself; the blob-drift guard's declared coverage (parsed from its source) is the **subject
  under test**, not a trusted source — so a weak/incomplete guard list cannot fool it.
- **Control-association is structural, never value-matching.** A pin is Control-DB-associated iff its harness
  source contains the segment-literal sequence `"infrastructure" / "db" / "control"` (the pathlib idiom the
  harnesses use). This is **drift-independent**: a stale control pin stays in scope and fails, instead of
  being misclassified out-of-scope by a value coincidence. There is **no value allow-set**.

## Non-vacuity

The meta-guard's teeth are proved by permanent `tmp_path` negative-control tests
(`test_nv_*`) that point the parameterized discovery roots at a synthetic temp tree and assert each invariant
fails on a simulated `004`, a deleted DDL, an unaccounted control pin, and a non-`.sql` file. They **never**
write into `infrastructure/db/control/` or `tests/control_plane/requires_pg/`.

## Effect

Adding a Control-DB DDL (`004`+) or a new `requires_pg` reviewed pin now fails the **default-suite** CI gate
(the full `pytest` step added by B-7C-1) until the blob-drift guard — and the matching harness pin — are
extended in lockstep. No live database required; the guard never applies DDL, never connects to PostgreSQL,
and reads the blob-drift guard and the `requires_pg` harnesses **read-only**.

## Boundaries (unchanged)

No runtime source change · no CI-workflow change · no live-PG workflow / PostgreSQL service /
`SNACKPORTAL_TEST_DSN` · no DDL edit/application · no `requires_pg` harness edit · no production activation ·
no frontend/Lovable change · no API-Gateway / Auth-Router / Database-Router change · **B5-BLK-4 remains
OPEN** · **Physical Multi-Database MVP mandatory** — B-7C-1R2 does **not** prove tenant physical
multi-database routing and is CI regression-coverage hardening only.

## Next

The live durable-path CI workflow (ephemeral PostgreSQL, path-filtered/scheduled/manual, secret-free) is
**B-7C-2** and is out of scope here.
