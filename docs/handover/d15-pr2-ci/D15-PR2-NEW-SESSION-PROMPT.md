# D15-PR2-NEW-SESSION-PROMPT

*Paste the following into a new Claude session working in `D:\Pitchsnack\SnackPortal2`.*

---

You are continuing SnackPortal2 Phase 3B. The approved D15 controlled-non-production implementation is committed and pushed on `feat/d15-provisioning-impl`, and PR #2 (→ `main`) is open and independently verified (PRD-D15-VERIFY-01 = PASS WITH MINOR OBSERVATIONS; 0 Critical / 0 Major).

**Read first:** `docs/handover/d15-pr2-ci/D15-PR2-HANDOVER-MASTER.md`, then the rest of that folder (CURRENT-STATUS, COMPLETED-WORK, DRIFT-LOG, NEXT-PHASE, CONSTRAINTS). Treat that package as the orientation source of truth.

**Mandatory architecture position:** Physical Multi-Database MVP is mandatory (one Control DB + physically distinct Tenant DBs). One Request → One Active Tenant → One Database; Gateway ≠ Database Resolution; Database Router = sole selector; Workspace/Portal/Ownership/Frontend ≠ Routing; Import ≠ Synchronization; Global Record ≠ Tenant Record.

**Current state:** branch `feat/d15-provisioning-impl`, HEAD `a1a8b60` (commits: `fc0a0c5` D15 impl + `a1a8b60` CI gitleaks GITHUB_TOKEN fix), working tree clean. CI: `secret-scan (push)` PASS; `secret-scan (pull_request)` FAILS with `403 Resource not accessible by integration` reading `/repos/Pitchsnack/SnackPortal2/pulls/2/commits` (token permissions — NOT a secret leak); `validate (push)` and `validate (pull_request)` FAIL on the pre-existing mypy baseline (45 errors / 18 Phase 1–6 files / 0 D15).

**Your task: execute PRD-D15-CI-02 ONLY** — the minimum CI-only fix for the secret-scan pull_request 403. Add a **narrow read-only `permissions:` block** to the `secret-scan` job in `.github/workflows/ci.yml` (keep the existing `env: GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}`):

```yaml
  secret-scan:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: read
    steps:
      ...
```

Then: verify `git diff` shows **only** `ci.yml`; (optionally) run `ruff check .`, `ruff format --check .`, `lint-imports`, `pytest tests/architecture tests/control_plane`; commit a CI-only message; push to `feat/d15-provisioning-impl` (PR #2 auto-updates); report the new commit hash and expected check status.

**Expected after fix:** `secret-scan (pull_request)` → PASS; `secret-scan (push)` → still PASS; `validate (push/pull_request)` → still FAIL (known mypy baseline; do NOT remediate here).

**Do NOT:** merge PR #2 · deploy · provision databases · perform any production action / rollout · live tenant onboarding · use/paste real secrets or DB passwords · modify application code or D15 implementation logic · modify contracts or ADRs · remediate the mypy baseline under CI-02 · start frontend/Lovable · start API Gateway or Database Router implementation · start AI Gateway/agent orchestration.

After committing and pushing the CI-only fix, report the result and stop.
