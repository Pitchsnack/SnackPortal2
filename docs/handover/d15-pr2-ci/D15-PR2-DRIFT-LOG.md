# D15-PR2-DRIFT-LOG

Drift and baseline items for PR #2. Two CLOSED, three OPEN. None is a D15 architecture/spec violation.

## CLOSED — Branch scope drift (branch cut from docs branch, not main)

```text
Drift:      feat/d15-provisioning-impl was originally cut from docs/handover-ho-03, not main.
Risk:       A direct PR into main would have included handover-doc commits and overstated PR scope.
Resolution: PRD-D15-PR-01-R1 -> rebased onto main via `git rebase --onto main 7a1649b`;
            confirmed main..HEAD contains only D15 implementation files (handover commits excluded).
Status:     CLOSED.
```

## CLOSED — Gitleaks missing token

```text
Drift:      secret-scan (pull_request) failed: "GITHUB_TOKEN is now required to scan pull requests".
Risk:       A red CI check could be misread as a secret finding.
Resolution: PRD-D15-CI-01 -> added `env: GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}` to the gitleaks step
            (commit a1a8b60). No real secret added. CI-config only.
Status:     CLOSED.
```

## OPEN — Gitleaks token permission (403) — NEXT ACTION

```text
Drift:      secret-scan (pull_request) now fails: "Resource not accessible by integration" (HTTP 403)
            when gitleaks reads PR commits.
            Failing API: GET /repos/Pitchsnack/SnackPortal2/pulls/2/commits
Risk:       PR check remains red even though there is NO real secret finding.
Required:   Execute PRD-D15-CI-02 (new session). Add narrow read-only permissions to the secret-scan job:
                permissions:
                  contents: read
                  pull-requests: read
Classification: GitHub Actions token PERMISSION issue (CI-config), not a secret leak.
Status:     OPEN.
```

## OPEN (not D15-caused) — mypy validate baseline

```text
Baseline:   ci / validate (push) and (pull_request) fail because `mypy .` reports 45 pre-existing errors
            in 18 Phase 1-6 files. 0 errors from D15 files. Same baseline exists on main.
Risk:       validate checks stay red even though D15 adds 0 mypy errors.
Required:   Separate future PRD — mypy baseline burn-down, baseline waiver, or CI strategy decision.
            DO NOT remediate under PRD-D15-CI-02.
Status:     OPEN (not D15-caused).
```

## OPEN — Live PostgreSQL distinctness evidence gap

```text
Gap:        The live-PG distinctness test exists (tests/control_plane/requires_pg/test_pg_distinctness.py)
            but clean-skips because SNACKPORTAL_TEST_DSN is not configured.
Risk:       Live PostgreSQL proof of distinctness remains pending.
Required:   Capture later using pgpass / env var / temporary local test role with CREATE/DROP DATABASE.
            DO NOT paste DB passwords into chat.
Status:     OPEN.
```
