# PRD-MYPY-BASELINE-EXEC-01-R2 — Verification Report

**Execution of:** PRD-MYPY-BASELINE-EXEC-01-R2 (Validate-Check Mypy Baseline Remediation)
**Branch:** `fix/mypy-baseline` (cut from `main` @ `f06d8f5`)
**Scope:** Repo-wide `mypy .` baseline remediation — type-only, behavior-preserving.
**Merge / deploy / provision / CI-edit / PR-#2-update:** NOT performed (prohibited by the PRD).

---

## Output A — Error Inventory (before-state)

```text
total errors before : 45
files affected       : 18
mypy source files    : 165 (main-based branch; D15 files absent — adds 0 errors)
D15-related count     : 0 (D15 provisioning files are absent on main; none touched)
pre-existing count    : 45 (all pre-D15 Phase 1–6 baseline debt)
branch used for measurement : fix/mypy-baseline (base main f06d8f5)
```

Baseline confirmed as the expected `45 errors in 18 files` — the §11 stop-gate did **not** trigger.

Category distribution (matches the PRD's expected categories; no `import-status`):

| Category | Count |
|---|---|
| `type-arg` | 23 |
| `no-untyped-def` | 10 |
| `arg-type` | 7 |
| `no-any-return` | 3 |
| `no-untyped-call` | 1 |
| `str-bytes-safe` | 1 |
| **Total** | **45** |

---

## Output B — Remediation Summary (per file)

| File | Service | Provider/adapters zone? | Errors fixed | Method | Behavior changed? |
|---|---|---|---|---|---|
| `lineage_service/segmentation.py` | lineage_service | no | 1 (`arg-type`) | `tenant_id=ctx.active_tenant_id or ""` (matches existing `retention.py:38` idiom) | no |
| `lineage_service/search.py` | lineage_service | no | 1 (`arg-type`) | same `or ""` idiom | no |
| `lineage_service/query.py` | lineage_service | no | 1 (`arg-type`) | same `or ""` idiom | no |
| `lineage_service/graph.py` | lineage_service | no | 1 (`arg-type`) | same `or ""` idiom | no |
| `lineage_service/verification.py` | lineage_service | no | 2 (`arg-type`) | `or ""` for tenant_id; `version: Optional[str]`→`str` (value already `str`) | no |
| `lineage_service/emit.py` | lineage_service | no | 1 (`arg-type`) | `version: Optional[str]`→`str` (value already `str`) | no |
| `database_router/ports.py` | database_router | no | 3 (`type-arg`) | `tuple[object, ...]` params; `-> list[dict[str, Any]]` | no |
| `database_router/pool.py` | database_router | no | 1 (`type-arg`) | `set[TenantConnection]` | no |
| `database_router/router.py` | database_router | no | 1 (`no-untyped-def`) | `association_ref: SecretRef` | no |
| `database_router/session_provider.py` | database_router | no | 3 (`no-untyped-def`, `type-arg` ×2) | `_where` return type; `List[Dict[str, Any]]` row annotations | no |
| `database_router/adapters/providers/psycopg_connection.py` | database_router | **yes** (driver/psycopg) | 3 (`type-arg`) | `tuple[object, ...]` params; `-> list[dict[str, Any]]` (mirrors the port) | no |
| `control_plane/read_api.py` | control_plane | no | 10 (`type-arg` ×9, `no-untyped-def`) | `dict[str, Any]` response/return types; `rec: DirectoryRecord` | no |
| `control_plane/registry.py` | control_plane | no | 1 (`type-arg`) | `allowed_from: set[TenantLifecycleState]` | no |
| `control_plane/adapters/providers/postgres_store.py` | control_plane | **yes** (driver/psycopg) | 1 (`type-arg`) | `row: Tuple[Any, ...]` (DB row) | no |
| `control_plane/adapters/providers/http_read_api.py` | control_plane | **yes** | 2 (`no-untyped-def`, `str-bytes-safe`) | `-> type[BaseHTTPRequestHandler]`; `cast(str, server.server_address[0])` (runtime-noop; output unchanged) | no |
| `import_service/service.py` | import_service | no | 8 (`no-untyped-def` ×6 + downstream `no-any-return`, `no-untyped-call`) | added parameter/return annotations to 6 internal methods | no |
| `import_service/adapters/providers/http_directory_read.py` | import_service | **yes** | 3 (`type-arg` ×2, `no-any-return`) | `dict[str, Any]`; typed local `payload: dict[str, Any]` for the JSON return | no |
| `auth_router/adapters/providers/http_control_plane_read.py` | auth_router | **yes** | 2 (`type-arg`, `no-any-return`) | `dict[str, Any]`; typed local `payload` for the JSON return | no |

**New helper/type files created:** none — every fix was in-place in the inventory files.

### Notes on behavior-neutrality
- **`arg-type` (`or ""`)**: `ctx.active_tenant_id` is `Optional[str]` because global/control-plane contexts have no tenant; lineage reads always run under a resolved tenant. The fix matches the **existing in-module pattern** at `lineage_service/retention.py:38`. Under the tenant-present invariant the value is unchanged; no `raise`-on-`None` was introduced (which would have required §12.2 stop-and-report).
- **`SecretRef` version**: `SecretStore.current_version()` is declared `-> str`; the local annotation `Optional[str]` was simply over-broad. Correcting it to `str` is a pure type fix — the runtime value was always a `str`.
- **`str-bytes-safe`**: `cast(str, server.server_address[0])` is a type-only narrowing (AF_INET host is `str`); the f-string output is byte-for-byte unchanged. No `!r`/decode that would alter formatting.
- **DB-row / transport dicts → `dict[str, Any]`**: matches the established house style (`List[Dict[str, Any]]` for DB rows; read-API bodies are JSON transport boundaries, per §12.3). `dict[str, object]` was deliberately **not** used as a known-shape type.

---

## Output C — Architecture Boundary Assessment (§15)

```text
Physical Multi-Database MVP remains mandatory.            ✔ (no DB-model change)
API Gateway remains scaffold.                             ✔ (untouched)
Database Router remains sole database selector.           ✔ (router logic unchanged; annotations only)
No cross-service imports are added.                       ✔ (lint-imports: 2 kept, 0 broken; services mutually independent)
Driver containment is preserved.                          ✔ (psycopg imports unmoved; only `from typing import Any` added in provider zones)
Audit reference-only discipline is preserved.             ✔ (audit call sites unchanged)
Secret-reference-only discipline is preserved.            ✔ (SecretRef/SecretStore usage unchanged; no raw secrets)
No raw secrets are introduced.                            ✔
D15 provisioning files are absent or untouched.           ✔ (absent on main; 0 in diff; 0 mypy errors)
No frontend / Lovable files are touched.                  ✔
No CI workflow files are touched.                         ✔ (.github/workflows unchanged; main's pre-fix ci.yml inherited as-is)
No production infrastructure is changed.                  ✔
No cross-tenant request fan-out is introduced.            ✔
```

---

## Output D — Verification Results (after remediation)

```text
ruff check .            : PASS  (All checks passed!)
ruff format --check .   : PASS  (160 files already formatted)
lint-imports            : PASS  (Contracts: 2 kept, 0 broken)
pytest tests            : PASS  (166 passed)
mypy .                  : PASS  (Success: no issues found in 165 source files)

before mypy count       : 45
after mypy count        : 0
before pytest count     : 166 passed, 0 skipped
after pytest count      : 166 passed, 0 skipped   (unchanged — no test edits, behavior-neutral)
```

**§13.1 diff-scope verification:** `git diff --name-only main...HEAD` = exactly the **18 inventory files** (all `backend/**` Python source) + this evidence report. No `.github/workflows`, no `backend/pyproject.toml`, no `tests/**`, no D15/provisioning files. **PASS.**

Note: the `requires_pg` live-PG harnesses are excluded from `pytest tests` at collection time via `addopts --ignore` (never collected, not runtime-skipped); `SNACKPORTAL_TEST_DSN` is unset and no live-PG was run.

---

## Output E — Evidence Report

```text
docs/reports/mypy/PRD-MYPY-BASELINE-EXEC-01-R2-Verification-Report.md   (this file)
```

---

## Output F — Commit / Push / PR Status

```text
commit hash  : (recorded at commit time on fix/mypy-baseline)
branch pushed: fix/mypy-baseline
PR           : made-ready (gh CLI not installed — no API-opened PR; title/body prepared below)
expected GitHub check status:
  - ci / validate (push)          : expected PASS  (mypy/tests/ruff/lint-imports pass locally)
  - ci / validate (pull_request)  : expected PASS
  - ci / secret-scan (push)       : expected PASS
  - ci / secret-scan (pull_request): expected FAIL — INHERITED from main (main lacks the
       GITHUB_TOKEN env + permissions block that live only on feat @ a1a8b60/85e3ad9).
       This is expected and unrelated to the mypy work; NOT a secret leak. Out of scope to fix here.
```

---

## Output G — Remaining Risks

```text
mypy errors                         : none (0)
test failures                       : none (166 passed)
architecture boundary failures      : none (lint-imports + arch tests pass)
secret-scan inherited CI failure    : EXPECTED on the PR (inherited pre-fix main ci.yml) — benign
actual secret finding               : none
live-PG evidence pending            : yes (requires_pg not run; SNACKPORTAL_TEST_DSN unset) — pre-existing, out of scope
production rollout pending          : yes (prohibited by this PRD)
PR #2 not yet updated from main     : yes (by design — PR #2 inherits this fix only after this PR merges to main)
```

---

## PR #2 Sequencing Note

This remediation is on a dedicated `main`-based branch, separate from PR #2 (`feat/d15-provisioning-impl`). After this PR is reviewed and merged into `main`, **PR #2 must inherit updated `main`** (preferred: merge `main` into `feat/d15-provisioning-impl`; do not rebase the pushed PR branch without separate authorization) before PR #2's own `validate` check can turn green. This PRD does **not** authorize updating PR #2.
