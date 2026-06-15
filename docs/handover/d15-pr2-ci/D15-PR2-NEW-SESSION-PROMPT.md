# D15-PR2-NEW-SESSION-PROMPT

*Copy the block below into a new Claude session working in `D:\Pitchsnack\SnackPortal2`.*
*(Updated 2026-06-15 to reflect HEAD `d3ed35c` and PR #2 carrying 3 commits.)*

```text
You are continuing SnackPortal2 — Phase 3B, D15 Provisioning Architecture — working in
D:\Pitchsnack\SnackPortal2 (Windows, PowerShell 5.1; Bash also available).

READ FIRST (in-repo, committed): docs/handover/d15-pr2-ci/D15-PR2-HANDOVER-MASTER.md,
then the rest of that folder (CURRENT-STATUS, COMPLETED-WORK, DRIFT-LOG, NEXT-PHASE,
CONSTRAINTS, NEW-SESSION-PROMPT). Treat that package as the orientation source of truth.
The D15 PRD/spec/review corpus lives OUT-OF-REPO at D:\Pitchsnack\PRD\ (esp.
"7. Architecture implementation Authorisation\"); the in-repo verification report is
docs/d15/PRD-D15-VERIFY-01-Verification-Report.md.

MANDATORY ARCHITECTURE POSITION (binding):
Physical Multi-Database MVP is mandatory (one Control DB + physically distinct Tenant DBs).
NOT satisfied by shared database / shared-schema / tenant_id-only isolation /
workspace|portal|frontend|gateway|ownership database selection / cross-tenant fan-out.
Invariants: One Request -> One Active Tenant -> One Database; Gateway != Database Resolution;
Database Router = sole DB selector; Workspace/Portal/Ownership/Frontend != Routing;
Import != Synchronization; Global Record != Tenant Record.

CURRENT STATE:
- Branch: feat/d15-provisioning-impl  Base: main  HEAD: d3ed35c  (working tree clean, in sync with origin)
- PR #2 OPEN -> https://github.com/Pitchsnack/SnackPortal2/pull/2  (DO NOT create a duplicate)
  Commits on the PR (3): fc0a0c5 (D15 implementation) + a1a8b60 (CI gitleaks GITHUB_TOKEN env)
  + d3ed35c (CI-remediation handover docs).
- D15 implementation is committed + independently verified: PRD-D15-VERIFY-01 =
  PASS WITH MINOR OBSERVATIONS (0 Critical / 0 Major; 17/17 checks; 13/13 boundaries HELD).
- CI checks:
    ci/secret-scan (push)         = PASS
    ci/secret-scan (pull_request) = FAIL: "Resource not accessible by integration" (HTTP 403)
        reading GET /repos/Pitchsnack/SnackPortal2/pulls/2/commits = gitleaks-action@v2 token
        PERMISSION gap (NOT a secret leak). <-- this is the next task.
    ci/validate (push) + (pull_request) = FAIL: pre-existing `mypy .` baseline (45 errors in
        18 Phase 1-6 files; 0 D15). Same on main. NOT in scope for the next task.

YOUR TASK — execute PRD-D15-CI-02 ONLY (minimum CI-only fix):
Add a narrow read-only permissions block to the secret-scan job in .github/workflows/ci.yml
(keep the existing `env: GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}`):
    secret-scan:
      runs-on: ubuntu-latest
      permissions:
        contents: read
        pull-requests: read
      steps: ...
Then: verify `git diff` shows ONLY ci.yml; commit a CI-only message (use a temp file +
`git commit -F` to avoid PowerShell quoting issues); push to feat/d15-provisioning-impl
(PR #2 auto-updates). Report the new commit hash + expected check status.
Expected after fix: secret-scan(PR) -> PASS; secret-scan(push) -> still PASS;
validate(push/PR) -> still FAIL (known mypy baseline; do NOT remediate here).

LOCAL GATE (read-only; run from backend\):
  cd backend; ruff check .; ruff format --check .; lint-imports;
  python -m pytest tests/architecture tests/control_plane;  mypy .  (expect 45 pre-existing, 0 D15)
Env notes: `gh` is NOT installed (git push works via cached HTTPS creds). PowerShell 5.1 has no
`??`/ternary and mangles `HEAD@{1}` unless quoted. SNACKPORTAL_TEST_DSN is unset, so the
requires_pg live-PG distinctness test clean-skips (live evidence still pending). Never paste
DB passwords/secrets into chat.

DO NOT: merge PR #2; deploy; provision databases; create production DBs; live tenant onboarding;
production rollout/secrets/infra; modify application code or D15 implementation logic; modify
contracts or ADRs; remediate the mypy baseline under CI-02; start frontend/Lovable; start API
Gateway or Database Router implementation; start AI Gateway / agent orchestration. Every
state-changing step is governed by an explicit PRD — confirm scope before acting.

After committing and pushing the CI-only fix, report the result and stop.
```
