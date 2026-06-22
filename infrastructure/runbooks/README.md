# infrastructure/runbooks — non-production operational runbooks (B-3)

Operational **runbooks** for the cloud-portable substrate, **non-production only**. **Documentation only**
(PRD 06 B-3): these describe procedures; they are **not** executable, apply no DDL, and create no cloud
resources. They exist so a future, separately-gated execution phase has a reviewed, safe procedure to follow.

## Runbooks

| Runbook | Purpose |
|---------|---------|
| `b3_nonprod_rollout.md` | How a future phase would stand up the non-production substrate (cluster → Control DB → cluster-scoped roles), with the boundary that **tenant DB creation stays in the Control-Plane D-15 workflow**. |
| `b3_teardown.md` | How to tear down a disposable non-production substrate safely, with multi-DB isolation guarantees and production warnings. |

## Standing rules for every runbook

- **Non-production only.** Production is deferred to B-5; no runbook here targets production.
- **D-15 ownership:** runbooks provision **substrate**; per-tenant database creation/teardown is the
  Control-Plane workflow, not a runbook step.
- **Secret references only (D-14):** runbooks reference `secret_ref` aliases; they never embed DSNs, passwords,
  tokens, or credentials.
- **Fail-closed:** if any required proof (reachability, schema version, physical distinctness, secret
  resolution) is missing or ambiguous, the procedure stops and does not declare readiness.
- **No apply in B-3:** these are written, not run, in this phase.
