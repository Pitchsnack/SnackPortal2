# D15-PR2-NEXT-PHASE

## Next PRD

```text
PRD-D15-CI-02 — Secret-Scan Pull-Request Permission Remediation (CI workflow config only)
```

Execute it in a **new Claude session** after reading this handover folder.

## Objective

Resolve the `ci / secret-scan (pull_request)` **`403 Resource not accessible by integration`** failure (gitleaks-action@v2 cannot read PR commits) with the **minimum CI-only workflow permission fix**. Not a secret leak; no application/D15 code change.

## Authorized scope (CI-02)

```text
ONLY: edit .github/workflows/ci.yml to grant the secret-scan job narrow read-only permissions.
Commit + push the CI-only change to feat/d15-provisioning-impl.
Report the new commit hash and expected check status.
```

## Expected change

Add a narrow `permissions:` block to the `secret-scan` job (job-scoped, least privilege) in `.github/workflows/ci.yml`:

```yaml
  secret-scan:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: read
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Secret scan (gitleaks)
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Notes:
- Keep the existing `env: GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}` (from commit a1a8b60) — do not remove it.
- Prefer **job-scoped** permissions over workflow-wide. If a workflow-level `permissions:` is added instead, keep it equally narrow (`contents: read`, `pull-requests: read`) and do not broaden any other job.
- Verify the exact current YAML before editing; merge into any existing structure without removing settings.

## Expected result after the fix

```text
ci / secret-scan (pull_request)  -> should PASS (token can now read PR commits; no real secret exists).
ci / secret-scan (push)          -> should remain PASSING.
ci / validate (push)             -> still FAILING (known mypy baseline; NOT addressed by CI-02).
ci / validate (pull_request)     -> still FAILING (known mypy baseline; NOT addressed by CI-02).
```

## Steps for the new session

```text
1. Read docs/handover/d15-pr2-ci/* (start with D15-PR2-HANDOVER-MASTER.md).
2. Read PRD-D15-CI-02 (the authorizing PRD) and confirm scope = secret-scan permissions only.
3. Confirm branch = feat/d15-provisioning-impl; working tree clean; HEAD = a1a8b60 (or later).
4. Inspect .github/workflows/ci.yml; confirm no permissions block on secret-scan yet.
5. Add the narrow read-only permissions (above) to the secret-scan job ONLY.
6. Verify: git diff shows ONLY ci.yml; app/D15 code unchanged; no secrets added.
   (Optional local gate: ruff / ruff format / lint-imports / pytest tests/architecture tests/control_plane.)
7. Commit (CI-only message) + push to feat/d15-provisioning-impl. PR #2 auto-updates.
8. Report commit hash + expected check status. STOP. Do not merge/deploy/provision.
```

## Out of scope for CI-02

```text
mypy baseline remediation (separate PRD); application/D15 logic; contracts; ADRs;
merge; deploy; production; databases; frontend/Lovable; API Gateway / Database Router implementation.
```
