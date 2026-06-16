# PRD-CI-EVIDENCE-01-E1 — Evidence Report

**Executed via:** `PRD-CI-EVIDENCE-01-E1-R1 — Durable CI Evidence Artifact Execution` (verified `PASS — E1-R1 VERIFIED FOR EXECUTION`)
**Base specification:** `PRD-CI-EVIDENCE-01-R1 Durable CI Evidence Capture Framework`
**Captured:** 2026-06-16T10:27:30Z · **Attester:** Claude Code (read-only git + gh; account Pitchsnack)
**Machine-readable record:** `docs/reports/ci-evidence/PRD-CI-EVIDENCE-01-E1-Evidence-Record.json`

> This E1 execution creates durable local + runtime evidence artifacts. **This evidence record is not yet asserted by any automated check** (validated for JSON well-formedness only); schema/record validation is routed to `PRD-CI-EVIDENCE-01-E2 — CI Evidence Schema and Record Guard`.

---

## A. Verdict

```
PASS WITH OBSERVATIONS
```

`verdict_reason_code` (overall): runtime success machine-confirmed; two non-blocking open ledger items (PR-event run keyed to pre-merge SHA; required-check enforcement unobservable → GOVERNANCE-01). Runtime-success evidence and required-check **enforcement** evidence are kept distinct; no GitHub runtime PASS is claimed beyond what the records support.

## B. Repository State (+ staleness)

```text
branch (work):        docs/ci-evidence-e1
attested HEAD:        431b71f3b3dc8406c81444dfc9652e8f03831570
origin/main:          431b71f3b3dc8406c81444dfc9652e8f03831570
staleness_status:     FRESH  (HEAD == origin/main)
63c6a91 ancestor:     YES
ci.yml blob:          142ae06bb3db2644970fe945a2d86e27e73ec4b5
guard blob:           33c855be948602df5dbb3b7acafb960847f72dda
```

## C. Evidence Files Created (exactly four; docs-only)

```text
docs/reports/ci-evidence/README.md
docs/reports/ci-evidence/templates/CI-Evidence-Record.schema.json
docs/reports/ci-evidence/PRD-CI-EVIDENCE-01-E1-Evidence-Record.json
docs/reports/ci-evidence/PRD-CI-EVIDENCE-01-E1-Evidence-Report.md
```

No file outside `docs/reports/ci-evidence/` was created or modified. No `ci.yml` / `.gitleaks.toml` / runtime / test / DB change.

## D. Local Git Evidence (Records A–D — OBSERVED_DIRECT)

| Record | Assertion | Result |
|---|---|---|
| A | HEAD == origin/main == 431b71f | OBSERVED_DIRECT ✓ |
| B | 63c6a91 is ancestor of HEAD | OBSERVED_DIRECT ✓ |
| C | ci.yml blob == 142ae06b… | OBSERVED_DIRECT ✓ |
| D | guard blob == 33c855be… | OBSERVED_DIRECT ✓ |

## E. Workflow Blob Evidence

ci.yml blob `142ae06bb3db2644970fe945a2d86e27e73ec4b5` and secret-scan regression-guard blob `33c855be948602df5dbb3b7acafb960847f72dda`, both bound to HEAD `431b71f` (Records C/D). These match the values attested by `PRD-CI-EVIDENCE-01-R1` §10.1.

## F. GitHub Runtime Evidence (Records E/F — OBSERVED_REPRODUCIBLE, GH_CLI_EVIDENCE)

Push run for the merge commit `431b71f`:

```text
run_id:        27563792239
run_url:       https://github.com/Pitchsnack/SnackPortal2/actions/runs/27563792239
event_type:    push        workflow_name: ci        status: completed
head_sha:      431b71f3b3dc8406c81444dfc9652e8f03831570
created_at:    2026-06-15T17:21:43Z   updated_at: 2026-06-15T17:22:10Z
validate     job 81482337752  -> success
secret-scan  job 81482337728  -> success
```

Reproducible read-only command: `gh run view 27563792239 --repo Pitchsnack/SnackPortal2 --json jobs`.
Scan non-vacuity (engine version + scanned range) is **NON-VACUITY-UNOBSERVABLE-WITH-CURRENT-CONFIG** — the default gitleaks-action log/JSON does not surface a scanned count; the mutating ci.yml emission edit is deferred to `PRD-CI-HARDEN-02` (RVR-NV-6).

## G. Push and Pull-Request Coverage (Record G — RVR-7)

```text
pull_request-event run:  27563507683
run_url:                 https://github.com/Pitchsnack/SnackPortal2/actions/runs/27563507683
head_sha:                63c6a913f0e27a45c3823b5fb2d1cbaae487c3e0  (PR #5 pre-merge head = hardening commit 63c6a91)
validate     job 81481348701 -> success
secret-scan  job 81481348863 -> success
```

**Observation (non-blocking, anticipated):** the PR-event run is keyed to the pre-merge head SHA `63c6a91` (an ancestor of the attested HEAD), not the merge SHA `431b71f` — merge commits do not have pull_request-event runs. The PR-event scan path (exercising `pull-requests: read`) is confirmed green.

## H. Required-Check Evidence (Record H — read-only status; enforcement → GOVERNANCE-01)

```text
gh api repos/Pitchsnack/SnackPortal2/branches/main/protection  ->  HTTP 403
  "Upgrade to GitHub Pro or make this repository public to enable this feature."
```

Required-check / branch-protection **enforcement** is **UNAVAILABLE** on this private-repo plan and cannot be observed. Per the read-vs-enforce boundary (R1 §3.1), ENFORCEMENT is routed to `PRD-CI-GOVERNANCE-01`. This is an open ledger item, not a runtime failure.

## I. Evidence Source and Strength Classification

```text
LOCAL_GIT_EVIDENCE  / OBSERVED_DIRECT        : Records A, B, C, D       (pass_gate_eligible = true)
GH_CLI_EVIDENCE     / OBSERVED_REPRODUCIBLE  : Records E, F, G          (pass_gate_eligible = true)
UNAVAILABLE_EVIDENCE/ UNAVAILABLE            : Record H                 (pass_gate_eligible = false)
```

No DERIVED_INFERENCE record grounds any PASS gate (R1 §8.1 rule honored).

## J. Open Observations (ledger)

1. **PR-event coverage SHA** — green PR-event run is on pre-merge `63c6a91`, not the merge SHA `431b71f` (anticipated; non-blocking).
2. **Required-check enforcement** — unobservable (branch-protection API HTTP 403, private-repo tier) → `PRD-CI-GOVERNANCE-01`.
3. **Secret-scan non-vacuity** — engine version + scanned range not surfaced by the default config → emission edit deferred to `PRD-CI-HARDEN-02` (RVR-NV-6).
4. **Automated assertion** — these artifacts are not yet asserted by any automated check → guard test routed to `PRD-CI-EVIDENCE-01-E2`.

## K. Zero-Secret Confirmation

No created file contains a real secret, token, password, DSN, or private key. The only token form present is the `${{ secrets.GITHUB_TOKEN }}` placeholder (and prohibition-prose words like "token"/"secret"/"password" in the README's must-not-contain list). A recursive secret-safety scan (`Get-ChildItem -Recurse -File | Select-String`) was run from the repo root over all four files before any push; matches are limited to that benign prohibition/placeholder prose. The read-only session OAuth token was never printed or stored.

## L. Scope Confirmation

Exactly the four `docs/reports/ci-evidence/` files were created. No `ci.yml`/`.gitleaks.toml`/workflow change; no `backend/tests/architecture/_evidence.py` or `test_evidence_capture.py` (deferred to E2); no runtime/DB/D15/API-Gateway/Database-Router/Lovable change. ATR-S1/S2/S3 and the regression guard are not weakened. Physical Multi-Database MVP remains mandatory.

## M. Final Status

```
PASS WITH OBSERVATIONS — durable CI evidence artifacts created; runtime validate + secret-scan
machine-confirmed green on 431b71f (push) and on the PR-event run for 63c6a91; required-check
enforcement and scan non-vacuity remain open ledger items routed to GOVERNANCE-01 / HARDEN-02.
```
