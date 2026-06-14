# D15-PR2-COMPLETED-WORK

All items below are complete. The D15 corpus (specs/PRDs/reviews/reports) lives **out-of-repo** at `D:\Pitchsnack\PRD\` (esp. `6.0 Provisioning Architecture Speciication\` and `7. Architecture implementation Authorisation\`).

## 1. D15 architecture & approval chain

```text
D15-ARCH-SPEC-01 authored; D15-ARCH-SPEC-01-R1 executed; Output-D light re-review PASS -> approval-ready.
D15-ARCH-SPEC-01 §30 Formal Approval Note appended (approved as governing baseline).
PRD-D15-IMPL-01 authored (controlled non-production scope; WP-1..WP-12).
PRD-D15-IMPL-01-R1 independent review = PASS WITH MINOR AMENDMENTS (0 Critical / 0 Major / 9 Minor).
PRD-D15-IMPL-01-R2 executed the 9 Minor amendments; light re-verification PASS.
Final approval-readiness review (PRD-D15-APPROVAL-IR-01) = APPROVE WITH NON-BLOCKING OBSERVATIONS.
PRD-D15-IMPL-01 §22 formal sign-off: APPROVED for controlled non-production implementation only.
```

## 2. D15 implementation (committed: fc0a0c5)

```text
control_plane/distinctness.py        PhysicalDistinctnessVerifier (DV-C1..DV-C9 + DV-C7A); 4 result states;
                                     IsolationAnomaly; InMemoryDistinctnessLedger.
control_plane/provisioning.py        ProvisioningOperator port + ProvisioningVerificationService
                                     (Ready only after reachability + schema + distinctness; fail-closed);
                                     reassociate (re-verify + invalidate); disable_routing.
control_plane/events.py              §14.3 reference-only audit event vocabulary.
control_plane/router_signal.py       RouterInvalidationPort (signal only; no database_router import).
control_plane/adapters/providers/postgres_distinctness.py        PG evidence provider (driver-confined).
control_plane/adapters/providers/postgres_provisioning_operator.py  PG operator (non-prod throwaway DBs).
tests/control_plane/test_d15_distinctness_verifier.py (10) + test_d15_provisioning_gate.py (8) + _d15_doubles.py
tests/control_plane/requires_pg/{_pg.py,test_pg_distinctness.py}  live-PG evidence harness (clean-skips).
infrastructure/db/provisioning/{README,001_tenant_database,002_distinctness_sentinel,003_provisioning_role}.sql
docs/d15/PRD-D15-VERIFY-01-Verification-Report.md  in-repo verification report.
backend/pyproject.toml  (only: pytest addopts --ignore=tests/control_plane/requires_pg)
Covers WP-1..WP-12. Additive; no Phase 1-5 source modified; api_gateway stays scaffold; Database Router
request-time resolution NOT re-implemented (control_plane only sets eligibility + signals invalidation).
```

## 3. Verification (PRD-D15-VERIFY-01)

```text
Verdict: PASS WITH MINOR OBSERVATIONS. 0 Critical / 0 Major / 0 blocking; 4 non-blocking Observations.
17/17 required checks PASS; 13/13 boundaries HELD.
ruff PASS; ruff format PASS; lint-imports PASS; pytest tests/architecture tests/control_plane = 75 passed;
mypy = 45 pre-existing errors / 18 Phase 1-6 files / 0 D15.
Live-PG evidence pending (SNACKPORTAL_TEST_DSN not configured) -> requires_pg clean-skips.
Report committed in-repo at docs/d15/PRD-D15-VERIFY-01-Verification-Report.md.
```

## 4. PR branch cleanup (PRD-D15-PR-01-R1)

```text
The branch was originally cut from docs/handover-ho-03, so main..branch had 3 commits
(D15 impl + 2 docs-only handover commits a9133d0/7a1649b).
Rebased D15-only onto main via `git rebase --onto main 7a1649b` (rebase -i unavailable;
bare `git rebase main` would have been a no-op leaving the handover commits).
Result: 5f163b4 -> rebased to fc0a0c5; main..HEAD = D15-only; handover commits excluded.
Content byte-identical (old<->new tree diff showed only the dropped docs/handover/* files).
Branch pushed to origin (fresh, no force). PR #2 opened by user into main.
```

## 5. CI gitleaks token fix (PRD-D15-CI-01, committed: a1a8b60)

```text
secret-scan (pull_request) first failed: "GITHUB_TOKEN is now required to scan pull requests".
Fix: added `env: GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}` to the gitleaks step in .github/workflows/ci.yml.
CI workflow config only; no application/D15 code changed; not a secret leak (built-in Actions token expression).
Pushed (fc0a0c5..a1a8b60). This cleared the missing-token error and revealed the next-layer 403 permission
issue (see DRIFT-LOG / NEXT-PHASE).
```

## 6. PR creation status

```text
PR #2 is OPEN (feat/d15-provisioning-impl -> main), opened by the user/PMO from the compare URL.
Merge remains prohibited. Production rollout remains prohibited.
```
