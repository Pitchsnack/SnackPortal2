# Runbook — CLM 2-Day Stage B Controlled-Local Rehearsal (MANUAL_ONLY)

> ## ⛔ WITHDRAWN — the API Gateway has been DELETED
>
> The Stage B rehearsal harness (`tests/control_plane/requires_pg/test_pg_clm_2day_stage_b_rehearsal.py`) was DELETED: it composed `build_gateway_edge_server_from_env` and served the CLM journey through the Gateway edge. The Stage B RUNTIME boundaries it accompanied are still guarded in the default suite by `tests/architecture/test_clm_2day_stage_b_runtime_boundaries.py`, re-aimed at the public Startup edge.
>
> Nothing in this document may be run, and no evidence produced by it before the removal may be
> cited as current. It is retained because the recorded scenario, its ordering rules and its
> evidence format are what a Gateway-free successor must reproduce.

**Governing PRD:** `PRD_SnackPortal2_2_Day_Accelerated_Controlled_Local_MVP_Stage_B_Implementation_START_GATE_GPT.md` (D-42)
**Harness:** `backend/tests/control_plane/requires_pg/test_pg_clm_2day_stage_b_rehearsal.py`
**Posture:** DISPOSABLE, operator-run, **human START-GATE required (Dan)**. Closes no blocker. Production **NOT READY / DO-NOT-ACTIVATE**.

This rehearsal drives the single D-42 controlled-local journey end to end through the **real served
topology** using **synthetic local data only**. It is deliberately excluded from the automatic live-PG
CI loop (registered as a justified `MANUAL_ONLY_EXCEPTIONS` entry in
`backend/tests/architecture/test_live_pg_workflow_runset_completeness.py`).

## What it proves

```
controlled-local OIDC login (RS256, Keycloak-shaped issuer)
  -> principal-only Gateway authentication
  -> served GET /memberships                     (returns ACME only)
  -> backend-validated ACME selection            (signed tenant claim; D-04 membership)
  -> served GET /tenant/startups/<startup_ref>   (one synthetic ACME Startup; 8-field DTO)
  -> served PATCH /tenant/startups/<startup_ref> (bounded short_description update; re-read confirms)
  -> unauthorized ZETA access                    (fail-closed 403 empty-body; no ZETA data)
  -> four durable audit events                   (workspace_memberships_read, tenant_startup_read,
                                                  tenant_startup_update, RouteDenied)
  -> physical multi-database routing proof       (only the ACME DB touched; ZETA physically untouched)
  -> rollback and restore                        (before == after; exact original local ACME state)
```

## Safety preconditions (READ FIRST)

- `SNACKPORTAL_TEST_DSN` MUST point ONLY at a **disposable, non-production** PostgreSQL instance. It must
  **never** point at production, shared staging, the standing Control database, or any tenant database.
- The harness **creates and drops its own** scratch databases `sp2_clm_control` / `sp2_clm_acme` /
  `sp2_clm_zeta`, applies control DDL `001-009 + 012 + 013` (blob-pinned STOP-before-connect) and the
  14-file tenant template to them **only**, and disposes the complete topology in `finally`.
- No standing SnackPortal2 database is named, read, or touched. No `.github` workflow is changed. No repo
  DDL file is modified (read + blob-pinned only).
- Secrets travel by SecretRef / a scratch secret directory deleted in `finally`; no descriptor value is
  printed, logged, committed, or served. RS256 material comes only from
  `backend/tests/api_gateway/crypto_fixture.py`.

## Run

From `backend/`, with `SNACKPORTAL_TEST_DSN` exported to a disposable instance:

```bash
python tests/control_plane/requires_pg/test_pg_clm_2day_stage_b_rehearsal.py
```

- With `SNACKPORTAL_TEST_DSN` unset (or `psycopg` absent) the harness **clean-skips** (exit 0, no DB
  touched). It is **never** run under `pytest` (the `admin_dsn` parameter is filled by the `_pg` runner).
- On success it prints the `PASS: CLM-0 … CLM-13` phase lines and `ALL PASSED`. Any failure prints a
  `FAIL:` line and exits non-zero; the `finally` disposal still runs.

## Repeatability

The rehearsal is fully repeatable: every run recreates the disposable topology from scratch, seeds the
same synthetic contract, drives the identical journey, and disposes everything in `finally` (retained
scratch-database count asserted `== 0`). Re-running requires only the disposable `SNACKPORTAL_TEST_DSN`.

## No overclaim

This is a disposable controlled-local rehearsal, not production activation. It closes no B5 blocker (7 of
9 remain OPEN), standing-enrolls no DDL, and does not touch the retained standing topology. Production
remains **NOT READY / DO-NOT-ACTIVATE**.
