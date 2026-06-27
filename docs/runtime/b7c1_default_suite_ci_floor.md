# B-7C-1 — Default-Suite CI Floor

**PRD:** PRD 06 B-7C-1 (Default-Suite CI Floor). Regression hardening only — **no runtime behavior
change**, no PostgreSQL, no secrets, no live-PG workflow (that is B-7C-2).

## What B-7C-1 enforces in CI

Before B-7C-1, `.github/workflows/ci.yml` `validate` ran `pytest tests/architecture` only, so the entire
`tests/control_plane/**` default suite — including the B-7B selector / timestamp / fail-closed unit tests —
was **not** CI-enforced. B-7C-1 adds a single additive step to the existing `validate` job:

```yaml
- name: Full default test suite (PRD 06 B-7C-1; requires_pg excluded via addopts — no PostgreSQL)
  run: pytest
```

Effect:
- the **full default `pytest`** now runs in CI;
- **`tests/control_plane/**` are now CI-enforced**, including the existing B-7B
  `test_b7b_control_store_selector.py` / `…_audit_timestamp_normalization.py` /
  `…_fail_closed_no_partial_state.py` unit tests;
- the `requires_pg` live-PG harnesses remain **excluded** from the default suite (pyproject
  `addopts --ignore=tests/control_plane/requires_pg`) — **no PostgreSQL service, no `SNACKPORTAL_TEST_DSN`,
  no secret** is added by B-7C-1;
- the existing `ruff` / `ruff format` / `mypy` / `lint-imports` / `pytest tests/architecture` steps and the
  `secret-scan` (gitleaks, SHA-pinned) job, least-privilege `permissions`, and action versions are
  **unchanged**.

## New default-suite regression guards (no PostgreSQL)

- **Audit-before-state-change ordering lock** (`tests/architecture/test_b7c1_audit_ordering_static.py`):
  an AST guard asserting `self._audit.record(...)` precedes `self._store.put_tenant(...)` in every wired
  ordering site (`registry.register_tenant`, `registry._transition`, `provisioning._transition`,
  `provisioning.reassociate`) — formatting/comment-insensitive and refactor-proof. `lifecycle.py` is
  excluded (it is not in the `create_app()` composition root) and is locked out of the composition root by
  a companion assertion; if it is ever wired, that future governed change must reorder it and extend this
  guard.
- **DDL blob-drift guard** (`tests/architecture/test_b7c1_control_audit_ddl_blob_pins.py`): recomputes the
  LF-normalized git-blob SHA-1 of `002_provisioning_audit.sql` (`887d0cbc…`) and
  `003_provisioning_audit_append_only.sql` (`c787c537…`) and asserts both `requires_pg` harness pins match —
  catching DDL/pin drift in CI without a database. Never applies DDL; never connects.
- **Missing-table / required-audit-failure floor**
  (`tests/control_plane/test_b7c1_required_audit_failure_floor.py`): proves, with no live DB, that a
  required durable audit write failing as if `control_audit` were absent rejects the operation with **no
  committed partial state** at the call site, and that the adapter's `list_audit` raises (never returns
  `[]`) and `append_audit` propagates (no swallow).

## Boundaries (unchanged)

No runtime source change · no live-PG CI workflow / PostgreSQL service / `SNACKPORTAL_TEST_DSN` in CI · no
production activation · no runtime DDL · no frontend/Lovable change · no API-Gateway / Auth-Router /
Database-Router change · **B5-BLK-4 remains OPEN** · **Physical Multi-Database MVP mandatory** — B-7C-1 does
**not** prove tenant physical multi-database routing.

## What remains for B-7C-2

The live-PG durable-path CI workflow (ephemeral PostgreSQL service, path-filtered/scheduled/manual,
secret-free) and live-harness non-vacuity / robustness (`lock_timeout`) — the only thing that CI-enforces
the *live* guarantees — is deferred to **B-7C-2** and is out of scope here.
