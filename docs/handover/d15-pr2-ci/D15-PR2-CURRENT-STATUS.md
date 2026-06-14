# D15-PR2-CURRENT-STATUS

**As of:** 2026-06-15 · Documentation-only · No CI fix applied in this package.

## PR #2

```text
Title:  D15 provisioning distinctness gate (controlled non-production)
Branch: feat/d15-provisioning-impl
Base:   main
State:  OPEN. Mergeable, but MERGE REMAINS PROHIBITED.
```

## Commit list (`main..HEAD`)

```text
a1a8b60db5cc38f3239deeafb02a8aac1ec7f4c0  ci: pass GITHUB_TOKEN to gitleaks-action for pull_request scans  <- HEAD
fc0a0c53bfd4bce25eaf2e24538f6b0a66ab3b43  feat(control-plane): implement D15 provisioning distinctness gate
```
Only these 2 commits are on the PR (handover-doc commits were excluded by the prior `rebase --onto main`). Working tree clean.

## Check status

| Check | Status | Cause |
|---|---|---|
| `ci / secret-scan (push)` | **PASSING** | push event does not hit the PR token/permission path |
| `ci / secret-scan (pull_request)` | **FAILING** | `403 Resource not accessible by integration` reading PR commits (token permissions) |
| `ci / validate (push)` | **FAILING** | pre-existing `mypy .` baseline |
| `ci / validate (pull_request)` | **FAILING** | pre-existing `mypy .` baseline |

## Classification — secret-scan (pull_request) failure

```text
NOT a real secret finding.
No file path, no line number, no rule id for any secret.
History:
  1st failure: "GITHUB_TOKEN is now required to scan pull requests"  -> fixed by commit a1a8b60.
  current failure: "Resource not accessible by integration", HTTP 403.
  failing GitHub API URL: GET /repos/Pitchsnack/SnackPortal2/pulls/2/commits
Classification: GitHub Actions token PERMISSION issue (gitleaks-action@v2 needs read access to PR commits).
Expected fix (PRD-D15-CI-02): add narrow read-only permissions to the secret-scan job.
Corroboration of "no real secret": .gitleaks.toml only `[extend] useDefault=true`; the repo's own
tests/architecture/test_no_secret_literals passes; D15 diff scan found no credential/DSN/key/token value;
D-14 reference-only discipline (only {store_ref, version} references) is enforced.
```

## Classification — validate (push + pull_request) failure

```text
Pre-existing CI baseline, NOT D15-caused.
`mypy .` (strict) reports 45 errors in 18 Phase 1-6 files
  (auth_router; control_plane registry/read_api/postgres_store/http_read_api;
   database_router x5; import_service x2; lineage_service x6).
0 errors are from any D15 file. The same 45 errors exist on main, so main's validate is equally red.
The validate job fails at the `mypy .` step (step 4 of 6); ruff/format pass before it; lint-imports/pytest never run.
Out of scope for PRD-D15-CI-02; needs a separate mypy burn-down / baseline-waiver decision.
```

## Local gate (on the current HEAD, for reference)

```text
ruff check .            : PASS
ruff format --check .   : PASS (171 files)
lint-imports            : 2 contracts kept, 0 broken
pytest tests/architecture tests/control_plane : 75 passed
mypy .                  : 45 pre-existing errors / 18 files / 0 D15  (this is what reddens validate)
requires_pg live-PG     : clean-SKIP (no SNACKPORTAL_TEST_DSN)
```
