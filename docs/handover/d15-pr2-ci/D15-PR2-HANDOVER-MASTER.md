# D15-PR2-HANDOVER-MASTER

**SnackPortal2 · Phase 3B — D15 Provisioning · PR #2 CI Remediation · Cross-Session Handover**
Generated under **PRD-D15-HO-04** (documentation-only). **No implementation, no CI fix, no merge, no deploy.**

> A new Claude session bootstraps from this package. Start here, then read the linked files in this folder.

## Mandatory architecture position

```text
Physical Multi-Database MVP is mandatory.
```

One Control Database **+** physically distinct Tenant Databases — not optional, not future-only. **Not** satisfied by a single shared database, shared-schema tenancy, `tenant_id`-only isolation, or workspace/portal/frontend/gateway/ownership database selection. Invariants that remain binding: One Request → One Active Tenant → One Database · Gateway ≠ Database Resolution · Database Router = sole database selector · Workspace/Portal/Ownership/Frontend ≠ Routing · Import ≠ Synchronization · Global Record ≠ Tenant Record.

## Executive summary

The approved D15 controlled-non-production implementation is **committed and pushed** on `feat/d15-provisioning-impl`, and **PR #2** (→ `main`) is open. The implementation was independently verified (**PRD-D15-VERIFY-01 = PASS WITH MINOR OBSERVATIONS; 0 Critical / 0 Major**). Two CI checks are red for **non-D15** reasons:

- **`secret-scan (pull_request)`** — a gitleaks-action@v2 setup issue, **not a secret leak**. First failure (missing `GITHUB_TOKEN`) was fixed in commit `a1a8b60`; it now fails with **`403 Resource not accessible by integration`** reading `/repos/Pitchsnack/SnackPortal2/pulls/2/commits` — a **token-permission gap**. The next fix (PRD-D15-CI-02) is a narrow `permissions:` block.
- **`validate (push)` and `validate (pull_request)`** — the **pre-existing `mypy .` baseline** (45 errors / 18 Phase 1–6 files, **0 D15**); present on `main` too. **Out of scope** for CI-02.

## Current PR state

```text
PR #2 — "D15 provisioning distinctness gate (controlled non-production)"
Branch: feat/d15-provisioning-impl   Base: main
Open. Mergeable, but MERGE REMAINS PROHIBITED.
```

## Current commit state

```text
a1a8b60db5cc38f3239deeafb02a8aac1ec7f4c0  ci: pass GITHUB_TOKEN to gitleaks-action (CI-only)   <- HEAD
fc0a0c53bfd4bce25eaf2e24538f6b0a66ab3b43  feat(control-plane): implement D15 provisioning distinctness gate
```
`main..HEAD` = these 2 commits only (handover-doc commits excluded by the earlier rebase). Working tree clean.

## Current check state

```text
ci / secret-scan (push)         : PASSING
ci / secret-scan (pull_request) : FAILING — 403 Resource not accessible by integration (token permissions)
ci / validate (push)            : FAILING — pre-existing mypy baseline (NOT D15)
ci / validate (pull_request)    : FAILING — pre-existing mypy baseline (NOT D15)
```

## Completed work

D15 architecture + approval chain, the implementation (PhysicalDistinctnessVerifier + gate + providers + IaC + tests + in-repo verification report), independent verification (PASS), branch rebase cleanup (D15-only), and the CI gitleaks `GITHUB_TOKEN` env fix. Details: `D15-PR2-COMPLETED-WORK.md`.

## Open items / drift

- **OPEN (next):** secret-scan(PR) 403 token-permission → fix in `PRD-D15-CI-02`.
- **OPEN (not D15):** `validate` mypy-45 baseline → separate burn-down/waiver decision.
- **OPEN (evidence):** live-PG distinctness evidence pending `SNACKPORTAL_TEST_DSN` (clean-skips).
- **CLOSED:** branch-base scope drift (rebased); gitleaks missing-token (a1a8b60).

Full log: `D15-PR2-DRIFT-LOG.md`.

## Next phase

```text
PRD-D15-CI-02 — resolve the secret-scan (pull_request) 403 with the minimum CI-only
workflow permission fix (add narrow read-only permissions to the secret-scan job).
```
Expected change + expected check results: `D15-PR2-NEXT-PHASE.md`.

## Constraints

Non-negotiable prohibitions for the next session (CI-02 scope is the secret-scan permissions fix ONLY): `D15-PR2-CONSTRAINTS.md`. **No merge, no deploy, no production, no app/D15-logic changes, no mypy remediation under CI-02, no frontend/Lovable.**

## Handover file index

- [D15-PR2-CURRENT-STATUS.md](D15-PR2-CURRENT-STATUS.md)
- [D15-PR2-COMPLETED-WORK.md](D15-PR2-COMPLETED-WORK.md)
- [D15-PR2-DRIFT-LOG.md](D15-PR2-DRIFT-LOG.md)
- [D15-PR2-NEXT-PHASE.md](D15-PR2-NEXT-PHASE.md)
- [D15-PR2-CONSTRAINTS.md](D15-PR2-CONSTRAINTS.md)
- [D15-PR2-NEW-SESSION-PROMPT.md](D15-PR2-NEW-SESSION-PROMPT.md)

## New-session instructions

Read this file, then `D15-PR2-NEW-SESSION-PROMPT.md`. Execute **only** `PRD-D15-CI-02` (the secret-scan permissions fix). Do not touch application/D15 code, do not remediate the mypy baseline, do not merge/deploy/provision. The D15 corpus (specs, PRDs, reviews, reports) lives **out-of-repo** at `D:\Pitchsnack\PRD\` (notably `7. Architecture implementation Authorisation\`); the in-repo D15 verification report is `docs/d15/PRD-D15-VERIFY-01-Verification-Report.md`.
