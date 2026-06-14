# D15-PR2-CONSTRAINTS

**Non-negotiable for the next session. PRD-D15-CI-02 scope = the secret-scan pull_request permission fix ONLY.**

## Mandatory architecture position

```text
Physical Multi-Database MVP is mandatory.
Control Database + physically distinct Tenant Databases.
NOT satisfied by: single shared database MVP; shared-schema tenancy; tenant_id-only isolation;
workspace/portal/frontend/gateway/ownership database selection; cross-tenant request fan-out.
```

## Invariants (must remain true)

```text
One Request -> One Active Tenant -> One Database
Gateway != Database Resolution
Database Router = sole database selector
Workspace != Routing
Portal != Routing
Ownership != Routing
Frontend != Database Routing
Import != Synchronization
Global Record != Tenant Record
```

## Prohibitions (CI-02 and this handover)

```text
Do NOT merge PR #2.
Do NOT deploy.
Do NOT provision databases / create production databases / live tenant onboarding.
Do NOT perform any production action / production rollout.
Do NOT use, create, or paste real secrets or DB passwords.
Do NOT modify application code.
Do NOT modify D15 implementation logic.
Do NOT modify contracts or ADRs.
Do NOT remediate the mypy baseline under PRD-D15-CI-02 (separate future PRD).
Do NOT start frontend / Lovable work.
Do NOT start API Gateway implementation.
Do NOT start Database Router request-time implementation.
Do NOT start AI Gateway or agent orchestration.
Do NOT start cross-tenant reporting / search / aggregation.
```

## Allowed under PRD-D15-CI-02 (only)

```text
Edit .github/workflows/ci.yml to add NARROW read-only permissions to the secret-scan job
  (contents: read; pull-requests: read), keeping the existing GITHUB_TOKEN env.
Commit + push the CI-only change to feat/d15-provisioning-impl.
Report commit hash + expected check status. Then stop.
```

## Standing status

```text
Production rollout: PROHIBITED.
Merge:             PROHIBITED.
Live tenant onboarding: PROHIBITED.
api_gateway: remains scaffold (IMPLEMENTS_BEHAVIOR = False).
Database Router request-time resolution: NOT re-implemented by D15 (only eligibility + invalidation signal).
```
