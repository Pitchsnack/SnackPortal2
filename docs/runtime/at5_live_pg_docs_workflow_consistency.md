# AT-5 — Live-PG Docs ↔ Workflow Consistency Guard

**PRD:** PRD 06 AT-5. **Documentation + one default-suite static guard only** — **no runtime, DDL, `pyproject`,
`ci.yml`, or live-PG workflow change**, no production database, no secrets. Reconciles the stale live-PG runtime
documentation and adds a required-CI guard so the docs and the live-PG workflow harness set cannot silently
drift apart again.

## The drift it closes

The advisory `live-pg-durable-path.yml` workflow runs a fixed set of `requires_pg` durable-path harnesses in a
`for h in … ; do` loop. After PR #30 (ATR-4) and PR #31 (ATR-1) the loop reached **9 harnesses** and the
provisioning/lineage gaps were closed — but the prose lagged:

- `b7c2_live_pg_durable_path_ci.md` still said **"Run set (8 harnesses)"**, omitted the provisioning harness,
  claimed provisioning was **"applied by no harness"**, and claimed **"ATR-1 remains OPEN and tracked, not
  fixed"**.
- `atr4_provisioning_ddl_live_harness_coverage.md`'s F-1 note **quoted** that stale `b7c2` wording, so it
  perpetuated the mismatch.

A future session could have read either doc and believed the durable path still had 8 harnesses or unfixed
gaps. AT-5 reconciles both docs to the current truth and guards the consistency in CI.

## Verified current truth

- live-PG durable path = **9 active harnesses** (5 `control_plane` + 4 `lineage_service`).
- the provisioning harness `test_pg_provisioning_ddl.py` is **included** (5th `control_plane` entry).
- `test_b3a_multi_database_topology.py` is **excluded** from the active loop (it needs four physically distinct
  clusters — the physical multi-DB **topology** proof the live-PG workflow explicitly does not make; it appears
  only in workflow *comments*).
- the live-PG workflow file is **unchanged** by AT-5 (read-only).

## What it changes

| File | Change |
|---|---|
| `docs/runtime/b7c2_live_pg_durable_path_ci.md` | **MODIFIED** — run set 8 → **9** + provisioning harness listed; "What it does NOT do" reconciled (ATR-1 marked **closed** by PR #31; provisioning marked applied by `test_pg_provisioning_ddl.py` per ATR-4). |
| `docs/runtime/atr4_provisioning_ddl_live_harness_coverage.md` | **MODIFIED** — F-1 note rewritten: the `b7c2` mismatch is **reconciled by AT-5** (no longer presents "8 harnesses" as current); the historical "8 → 9" transition is retained as history. |
| `backend/tests/architecture/test_live_pg_docs_workflow_consistency.py` | **NEW** — the required-CI consistency guard (below). |
| `docs/runtime/at5_live_pg_docs_workflow_consistency.md` | **NEW** — this note. |

## The guard

`backend/tests/architecture/test_live_pg_docs_workflow_consistency.py` (pure stdlib; no PostgreSQL, no DSN, no
driver, no connection) asserts:

- **T1** — the workflow `for h in … ; do` loop parses; it has exactly **9** harness entries; the provisioning
  harness is one of them; and `test_b3a` is **not** an active loop entry (the b3a check is scoped to the loop
  group, so the comment mention does not false-trip it).
- **T2** — the `b7c2` documented `Run set (N harnesses)` count equals the **parsed** workflow loop count (the
  doc count is tied to the workflow, not hard-coded), so an 8-vs-9 drift fails.
- **T3** — the `b7c2` "What it runs" section lists the provisioning harness filename.
- **T4** — the `b7c2` "What it does NOT do" section no longer presents the stale current-state claims
  (`ATR-1 remains OPEN` / provisioning `applied by no harness`).
- **T5** — the `atr4` F-1 note no longer frames the `b7c2` "8 harnesses" wording as current truth and carries a
  `reconciled by AT-5` marker.

Plus non-vacuity tests proving each detector fails on a synthetic regression (8-entry loop, missing
provisioning entry, injected b3a entry, 8-vs-9 doc mismatch, reintroduced stale ATR-1 claim) **and** that
explicitly-historical "8 harnesses" / "8 → 9" wording is **not** false-flagged.

**Design pins:** structural workflow parse (reuses the `for h in … ; do` loop regex idiom from
`test_atr4_provisioning_ddl_coverage.py` — that guard is the authority for "provisioning in loop" and is
**not** modified); section-scoped, whitespace-normalized negative doc checks (never a blanket grep); no
line-number dependence; no PyYAML. The provisioning-present check (T1) intentionally overlaps ATR-4's guard and
is retained for self-containment; AT-5's *new* value is the structural **count**, the **b3a-exclusion**, and the
**docs↔workflow count consistency**.

## What it does NOT do

- It does **not** edit the live-PG workflow (it reads it).
- It does **not** change the workflow's advisory status: the live-PG job remains **ADVISORY / not a required
  status check** (DRIFT-08 / F-2: branch protection unavailable on this private repo) — a separate, still-open
  follow-up.
- It does **not** prove tenant **physical multi-database routing** (`test_b3a_*` stays excluded; one ephemeral
  service is one cluster).
- It does **not** close **B5-BLK-4** (which remains **OPEN**).
- It does **not** complete the **Physical Multi-Database MVP** (which remains **mandatory**, not future work).
  AT-5 must not be described as MVP progress.

## Boundaries

No runtime source change · no `infrastructure/db/**` `.sql`/README edit · no `pyproject` (addopts) change · no
`ci.yml` change · no `live-pg-durable-path.yml` change · no edit to `test_atr4_provisioning_ddl_coverage.py`,
`_scan.py`, or any PR #31/#32/B-7C guard · no production DB/DSN/secret · no Supabase credential · no
Database-Router / API-Gateway / Auth-Router / frontend change · **B5-BLK-4 OPEN** · **Physical Multi-Database
MVP mandatory** — AT-5 is documentation + consistency-guard hardening only.
