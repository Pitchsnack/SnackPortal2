# Controlled Served-Write Rehearsal (operator runbook)

**Scope:** **MANUAL_ONLY** / NON-PRODUCTION. This runbook governs the operator procedure for the controlled
served-write rehearsal: joining the **W1b served Gateway Edge** (`POST /import/<source_ref>`) to the **W1a
real-PostgreSQL composed import path** inside one test-owned higher deployment root, against a **disposable
physical three-database topology only**. The rehearsal harness is
`backend/tests/control_plane/requires_pg/test_pg_controlled_served_write_rehearsal.py` (create → prove → drop;
no standing database touched; registered as a justified MANUAL_ONLY exception in
`backend/tests/architecture/test_live_pg_workflow_runset_completeness.py` — the automatic live-pg workflow
loop is unchanged and never runs it). **An explicit human START-GATE (Dan) is required before any
execution** — this runbook alone authorizes nothing. This is **not a production activation**: no standing,
staging, or production database is named, read, or touched; DDL `014`/`015` are **NOT enrolled** in the
standing apply order; standing application would be a separately governed, Dan-authorized run. **Production
remains NOT READY / DO-NOT-ACTIVATE** (8 of 9 activation blockers OPEN); executing this rehearsal closes no
blocker.

Standing rules (inherited from `infrastructure/runbooks/README.md`): secret references only (D-14 — never a
descriptor, password, token, or credential in this document, a shell-history echo, or any evidence artifact);
fail-closed (any missing or ambiguous proof stops the procedure); **no runtime DDL** — DDL is applied only by
the explicit rehearsal harness under this procedure. The API Gateway holds no database driver and no
Control-DB descriptor; the registry stores `SecretRef` only and never a raw DSN; the Database Router alone
resolves the tenant database identity; one request → one signed active tenant → one physical tenant database;
alpha never reaches beta.

---

## 1. Named roles (record before execution)

| Role | Holder |
|---|---|
| Rehearsal commander | Dan or a Dan-designated operator (record the name) |
| Gateway operator | (designate; may be the commander in a solo run) |
| Database operator | (designate; may be the commander in a solo run) |
| Evidence recorder | (designate; may be the commander in a solo run) |
| Rollback decision-maker | **Dan** |
| Final go/no-go decision-maker | **Dan** (human; the explicit START-GATE) |

A solo run must explicitly record "Dan as solo operator" for the designate rows.

## 2. Preconditions (ALL must hold before any step below)

1. **Explicit human START-GATE.** Dan has authorized THIS rehearsal execution in writing. No standing
   authorization exists; each run needs its own gate.
2. **Disposable, non-production PostgreSQL only.** `SNACKPORTAL_TEST_DSN` must point at a throwaway local
   instance — NEVER production, shared staging, the standing Control database, or any tenant database. The
   harness creates and drops its own databases `sp2_rehearsal_control`, `sp2_rehearsal_alpha`, and
   `sp2_rehearsal_beta` (physically distinct databases, not schemas; no shared-schema simulation; no
   cross-database foreign keys; synthetic data only).
3. **Rehearsal DDL blob IDs.** The LF-normalized git-blob SHA-1 pins verified by the harness BEFORE any
   connection:
   - `014_import_operational_audit.sql` → `73436f9681163c8a86ee230f51206062b06735c5`
   - `015_import_operational_audit_append_only.sql` → `ba594e3cd6eb070790bde6015f5225960c0d62ed`
   - tenant `008_startups_global_startup_id_unique.sql` → `20741db4dc6152bcdf9aaec029b9845a7bacb78e`
     (applied via the enrolled 14-file template; pinned by the default-suite tenant DDL guards)

   On ANY mismatch: STOP — do not connect further, do not apply, do not "fix" the DDL in place; escalate for
   a governed DDL review.
4. **Credentials by reference only.** The admin DSN reaches the harness only through the `_pg` runner
   (`SNACKPORTAL_TEST_DSN`, by name); tenant DSNs and lineage chain keys exist only as harness-owned scratch
   `SecretRef` material (`tenant/<id>/dsn@1`, `tenant/<id>/chainkey@1`) deleted at teardown; the Control-store
   DSN travels by reference (`control/control-store-dsn`). No secret value is printed, persisted, committed,
   or served.
5. **Production enablement remains unauthorized** — this runbook never authorizes selecting the served-edge
   composition selectors (`SP2_GW_*`, `SP2_IMPORT_*`, `SP2_CP_*`, `SP2_AR_*`, `SP2_DBR_*`) in production;
   enablement requires a separate human-governed production activation decision.

## 3. Exact DDL apply matrix (explicit ordered lists — never a wildcard)

| Target | Exact ordered files | Never |
|---|---|---|
| disposable Control (`sp2_rehearsal_control`) | control `001`–`009` (in order), then exactly `014`, then exactly `015` — each exactly once | control `010`–`013` (routing / gateway op-audit — not on the import path); any standing/staging/production DB |
| each disposable tenant (`sp2_rehearsal_alpha`, `sp2_rehearsal_beta`) | the enrolled 14-file template via the real applicator (provisioning `001`–`003` + lineage `001`–`003` + tenant `001`–`008`), one atomic transaction + System Primary seed | partial application; wildcard/glob/migration-runner sweeps |

Rules: verify the §2.3 blob pins first (STOP on mismatch); single transaction per database where lawful
(`CREATE`/`DROP DATABASE` are non-transactional and run on an autocommit admin connection); `014`/`015` are
never applied to a standing, staging, or production database and stay OUT of the standing apply order.

## 4. Process and port map (all loopback, ephemeral; test-owned daemon threads)

| # | Served process | Factory (existing production seam) | Composition selectors |
|---|---|---|---|
| 1 | Control-Plane read edge | `control_plane.main.build_read_server_from_env()` | `SP2_CP_READ_HOST=127.0.0.1`; `SP2_CP_CONTROL_STORE=postgres` (standalone); DSN by reference `SP2_CP_CONTROL_STORE_DSN_REF` (default `control/control-store-dsn`) |
| 2 | Import-audit ingest edge | `control_plane.main.build_import_audit_server_from_env()` | `SP2_CP_IMPORT_AUDIT_HOST=127.0.0.1`; same reference-only store binding |
| 3 | Auth authenticate edge | `auth_router.main.build_authenticate_server_from_env()` | `SP2_AR_CONTROL_PLANE_READ_BASE_URL` → edge 1; `SP2_AR_ISSUERS` (rehearsal-scoped RS256 JWKS) |
| 4 | Database-Router dispatch edge | `database_router.main.build_dispatch_server_from_env()` | `SP2_DBR_ROUTING_READ_BASE_URL` → edge 1; `SNACKPORTAL_TENANT_SECRET_DIR` (scratch, deleted at teardown) |
| 5 | Import initiate edge | `import_service.main.build_import_server_from_env(session_provider=…, lineage=…, directory_read=…)` | `SP2_IMPORT_HOST=127.0.0.1`; `SP2_IMPORT_AUDIT_SINK_BASE_URL` → edge 2; the three cross-package ports injected by the harness (DAG independence) |
| 6 | **Gateway Edge (W1b, served)** | `api_gateway.main.build_gateway_edge_server_from_env()` | `SP2_GW_AUTH_ROUTER_BASE_URL` → 3; `SP2_GW_CONTROL_READ_BASE_URL` → 1; `SP2_GW_DB_ROUTER_BASE_URL` → 4; `SP2_GW_IMPORT_BASE_URL` → 5; `SP2_GW_EDGE_HOST=127.0.0.1` |

All port knobs stay unset (ephemeral `0`). The golden request is driven by a **real stdlib HTTP client**
against edge 6; the harness never calls the gateway core in-process. Every selector value is non-secret
internal routing config; malformed values raise `ValueError` before any socket bind (fail closed).

## 5. Synthetic contract (exact; references only)

```text
source_ref              = rehearsal-startup-001
active tenant           = alpha        (sp2_rehearsal_alpha)
negative tenant         = beta         (sp2_rehearsal_beta — must remain physically untouched)
operation_key           = op-rehearsal-0001
correlation_id          = corr-rehearsal-0001
display_name            = Rehearsal Synthetic Co
expected first result   = HTTP 200, outcome created, tenant_record_ref alpha:startups:rehearsal-startup-001,
                          lineage_ref = import_id
expected replay         = HTTP 200, outcome replayed, same operation_key, no duplicate startup row,
                          no duplicate created-lineage effect
```

## 6. Run (operator procedure)

1. Confirm §1 roles recorded and the §2 preconditions (including the Dan START-GATE for THIS run).
2. Execute standalone:
   `python backend/tests/control_plane/requires_pg/test_pg_controlled_served_write_rehearsal.py`
   (with `SNACKPORTAL_TEST_DSN` unset or psycopg absent it clean-skips — exit 0, no DB touched).
3. The harness runs the golden probes G1–G14 and failure probes F1–F12 (§7/§8) in one pass and always ends
   with deterministic shutdown + R-A disposal (§9), after success OR failure.
4. The evidence recorder captures the printed `PASS: REH-*` phase lines (references only) as the run record.

## 7. Golden-path probes (G1–G14, encoded by the harness)

served POST accepted with correlation echo (G1); authentication succeeds (G2); signed-context tenant
authority — the audit target references the signed tenant, never the path (G3); carrier match (G4); exactly
one routed DB identity — a single routed pool key `(alpha, 1)` and router-audit consistency across fresh and
replay (G5); exactly one physical tenant DB opened, proven by safe `current_database()` identity readback and
an untouched beta (G6); one alpha startups row (G7); one alpha created-lineage row (G8); exactly three durable
`control_import_audit` rows — `ImportRequested`/`ImportStarted`/`ImportCompleted` (G9); references-only
`ImportResultDTO` with outcome `created` (G10); replay returns `replayed` (G11); no duplicate startup,
lineage, or completion effect — exactly two more audit rows (G12); correlation and import references reconcile
across response, lineage, and audit (G13); all served processes shut down cleanly with sockets released (G14).

## 8. Failure-path probes (F1–F12, encoded by the harness)

missing bearer → 401 (F1); tenantless CONTROL principal → 403 at gateway authorization/routing (F2); carrier
mismatch vs the signed tenant → 403 (F3); malformed `source_ref` → 404 pre-core (F4); non-empty body → 413
pre-core (F5); missing Import port → 503, never a fake 200 (F6); unknown tenant → fail closed (F7); missing
secret reference → fail closed 503 (F8); alpha DB unavailable → 503 with no beta fallback (F9); audit
persistence unavailable → no false success, durable confirm only after restore (F10); replay does not
duplicate (F11); an alpha request never reaches beta — dual-carrier straddle denied, beta physically untouched,
no routed key and no routing-audit reference to beta (F12).

## 9. Evidence rules, shutdown order, and rollback (R-A)

- **References-only evidence.** Every evidence artifact carries references only — no descriptor, password,
  bearer credential, key material, hostname/topology detail, or stored-event dump. The harness asserts stored
  audit cells contain no descriptor/password/bearer substring.
- **Direct-SQL-only audit inspection.** There is no served audit-retrieval edge; tenant rows, lineage, and
  `control_import_audit` are inspected only by read-only, references-only `SELECT` against the disposable
  databases (never any other database).
- **Shutdown order (deterministic, `finally`-equivalent, success or failure):** stop every served process
  (`shutdown()`, then `server_close()`, then a bounded thread join, newest first); close every direct
  connection; restore every touched environment key; delete the scratch secret directory; sever pool-held
  connections via `pg_terminate_backend`; then dispose.
- **R-A — dispose the complete disposable topology (the ONLY rollback):** `DROP DATABASE IF EXISTS` for
  `sp2_rehearsal_alpha`, `sp2_rehearsal_beta`, then `sp2_rehearsal_control`, and assert a zero retained-name
  census. No delete API, lineage deletion, audit deletion, trigger disable, TRUNCATE recovery, or
  retained-database cleanup exists or may be invented.

## 10. STOP-on-failure rules

Any blob-pin mismatch, gate mismatch, probe mismatch, unexpected status, or ambiguous evidence: **STOP** the
procedure at that probe; let the harness `finally` complete the shutdown + R-A disposal; capture the redacted
`PASS`/failure output (references only); escalate to Dan and GPT. Do not improvise recovery, do not re-run
with modified assertions, do not touch any non-disposable database.

## 11. Forbidden (never part of any run or recovery)

```text
executing without an explicit human Dan START-GATE
pointing SNACKPORTAL_TEST_DSN at production, staging, or any standing/tenant database
applying control 010-013 in this rehearsal
applying 014/015/008 to a standing, staging, or production database
enrolling 014/015 in the automatic standing apply order
wildcard / glob / migration-runner DDL application
storing a raw DSN in the registry or any evidence artifact
calling the gateway core in-process for the golden request
retaining any rehearsal database, secret file, or served process after the run
DROP / TRUNCATE / DELETE / trigger disable on any non-disposable database
inventing a single-import reversal or delete API
treating rehearsal success as production readiness or blocker closure
```

Production remains **NOT READY / DO-NOT-ACTIVATE**; B5-BLK-5 and B5-BLK-6 remain OPEN; only a separate,
Dan-authorized decision may change any blocker or activation state.
