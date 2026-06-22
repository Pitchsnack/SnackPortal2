# Runbook — Non-Production Substrate Teardown (PRD 06 B-3)

**Documentation only. Non-production only. Not executable in B-3.** Safe teardown of a **disposable
non-production** substrate. Applies to no production system.

> ⚠ **PRODUCTION WARNING.** This runbook is for disposable non-production only. **Never** run teardown against
> production or any database whose identity is not explicitly confirmed disposable. Production teardown is out of
> scope for the entire B-3 stream.

## Multi-database safety guarantees (read first)

```
Per-tenant teardown is PHYSICALLY ISOLATED: tearing down one tenant DB MUST NOT affect another (D-30).
Teardown is EXPLICIT and GUARDED — never automatic, never triggered by a routine apply.
Control-DB teardown is SPECIALLY PROTECTED: the Control DB holds the registry + distinctness ledger; losing it
  orphans the whole fleet. Treat as a separate, double-confirmed, last step.
Teardown is OUT-OF-BAND, not a DDL "down-migration": the reviewed DDL is additive/non-destructive.
Teardown NEVER deletes tenant business data as a side effect; tenant-data lifecycle follows retention (D-24),
  not IaC.
```

## Steps (future phase; non-production; reverse order of rollout)

1. **Confirm disposability.** Confirm the environment alias is `local`/`nonprod` and the target identity matches
   the recorded non-production substrate. If identity cannot be confirmed disposable, **STOP**.
2. **Tenant DBs (control-plane owned).** Any non-production tenant DBs are decommissioned via the Control-Plane
   D-15 workflow, one at a time, each physically isolated. This runbook does not bulk-drop tenant databases.
3. **Drop disposable DB substrate.** Remove the disposable non-production databases created for the exercise.
4. **Remove non-production roles.** Drop the non-production cluster-scoped roles created for the exercise.
5. **Control DB last (double-confirm).** Only after all dependents are gone, and only with explicit
   confirmation, remove the disposable non-production Control DB.
6. **Remove non-production state.** Delete local/non-production IaC state (never committed; DB3-4).

## Verification (record in the evidence report)

```
[ ] no leftover tenant DBs in the disposable target
[ ] no leftover Control-DB test objects
[ ] no leftover non-production roles
[ ] no IaC state file committed or left in the working tree
[ ] no secrets were ever stored in the repo (D-14) — gitleaks clean
[ ] environment confirmed non-production throughout
```

## Invariants preserved

No cross-tenant impact (D-30) · fail-closed (ambiguous identity → STOP) · D-14 references only · no production
operation · infrastructure independent of `backend/`.
