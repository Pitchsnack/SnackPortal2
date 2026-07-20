# Controlled Rollback Rehearsal (operator runbook)

**Scope:** **MANUAL_ONLY** / NON-PRODUCTION. This runbook governs the operator procedure for the controlled
rollback rehearsal: proving the B5-BLK-8 rollback **mechanism** — returning a durable/activated composition
to the deferred (in-memory) default whose construction performs no I/O — against a **disposable, physically
distinct three-database topology**, driven entirely **in-process** through the real composition root
(**composed-core**: Control Plane + Database Router; **no** Gateway, **no** Auth, **no** served HTTP edge,
**no** port). The rehearsal harness is
`backend/tests/control_plane/requires_pg/test_pg_controlled_rollback_rehearsal.py` (create → prove → dispose;
no standing database touched; registered as a justified MANUAL_ONLY exception in
`backend/tests/architecture/test_live_pg_workflow_runset_completeness.py` — the automatic live-pg workflow
loop is unchanged and never runs it). **An explicit human START-GATE (Dan) is required before any
execution** — this runbook alone authorizes nothing. This rehearsal **closes no blocker**: B5-BLK-8 remains
OPEN; the live blocker census remains **7 of 9 OPEN**; Production remains **NOT READY / DO-NOT-ACTIVATE**.

**References (normative — DO NOT restate):**

- `infrastructure/runbooks/b5_blk8_rollback_to_deferred_composition.md` — the reviewed rollback **semantics**
  (the deferred in-memory rollback target, the four gate §7 triggers, the D-24 non-destructive and D-30
  per-tenant-isolation disciplines, references-only failure recording, and the binding non-claims). This
  runbook references those and restates none of them.
- `infrastructure/runbooks/controlled_served_write_rehearsal.md` — the disposable-topology **discipline**
  (START-GATE preconditions, DDL blob-pin STOP-before-connect, deterministic teardown, and disposal /
  STOP-on-failure). This runbook references that and restates none of it. (Its authoring-era census line
  predates the current count; this runbook states the live **7 of 9 OPEN** and never inherits an older
  figure.)

Standing rules (inherited from `infrastructure/runbooks/README.md`): secret references only (D-14 — never a
descriptor, password, token, or credential in this document, a shell-history echo, or any evidence artifact);
fail-closed (any missing or ambiguous proof stops the procedure); **no runtime DDL** — DDL is applied only by
the explicit rehearsal harness under this procedure, to disposable databases only. The registry stores
`SecretRef` only and never a raw DSN; the Database Router alone resolves the tenant database identity; one
request → one active tenant → one physical tenant database; the target never reaches the adjacent tenant.

---

## 1. Named roles (record before execution)

| Role | Holder |
|---|---|
| Rehearsal commander | Dan or a Dan-designated operator (record the name) |
| Evidence recorder | (designate; may be the commander in a solo run) |
| **Rollback decision-maker** | **Dan** |
| **Final go/no-go decision-maker** | **Dan** (human; the explicit START-GATE) |

A solo run must explicitly record "Dan as solo operator" for the designate rows.

## 2. Preconditions (ALL must hold before any step below)

1. **Explicit human START-GATE.** Dan has authorized THIS rehearsal execution in writing. No standing
   authorization exists; each run needs its own gate.
2. **Disposable, non-production PostgreSQL only.** `SNACKPORTAL_TEST_DSN` must point at a throwaway local
   instance — NEVER production, shared staging, the standing Control database, or any tenant database. The
   harness creates and drops its own databases `sp2_rollback_control`, `sp2_rollback_target`, and
   `sp2_rollback_adjacent` (physically distinct databases, not schemas; synthetic data only).
3. **Control DDL blob pins.** The harness verifies the LF-normalized git-blob SHA-1 pins for control
   `001`–`009` (the `_ROLLBACK_BLOB_*` pins) **BEFORE any connection**. On ANY mismatch: STOP — do not
   connect, do not apply, do not "fix" the DDL in place; escalate for a governed DDL review.
4. **Credentials by reference only.** The admin DSN reaches the harness only through the `_pg` runner
   (`SNACKPORTAL_TEST_DSN`, by name); tenant DSNs exist only as harness-owned scratch `SecretRef` material
   (`tenant/<id>/dsn@1`) deleted at teardown; the Control-store DSN travels by reference
   (`control/control-store-dsn`). No secret value is printed, persisted, committed, or recorded.

## 3. Exact DDL apply matrix (explicit ordered lists — never a wildcard)

| Target | Exact ordered files | Never |
|---|---|---|
| disposable Control (`sp2_rollback_control`) | control `001`–`009` (in order, each once) | control `010`–`013` (routing / gateway op-audit), control `014`–`015` (import op-audit), and any audit-store DDL |
| each disposable tenant (`sp2_rollback_target`, `sp2_rollback_adjacent`) | the 14-file tenant template via the real applicator (provisioning `001`–`003` + lineage `001`–`003` + tenant `001`–`008`) | partial application; wildcard/glob/migration-runner sweeps; any standing/staging/production DB |

Rules: verify the §2.3 blob pins first (STOP on mismatch); `CREATE`/`DROP DATABASE` run on an autocommit
admin connection; no audit-store DDL (`010`–`015`) is applied by this rehearsal, and none of it is enrolled
in any standing apply order.

## 4. Composed-core topology (in-process; NO Gateway/Auth; NO ports)

The rehearsal composes two halves and drives them **in-process** — there is no served process, no socket,
and no loopback port:

- **The thing rolled back** — the `ControlPlane()` composition root. The durable/activated posture sets
  `SP2_CP_CONTROL_STORE=postgres` (control-store-standalone; the live side stays in-memory — RULE 2). The
  rolled-back posture unsets the four `SP2_CP_*` selectors so a fresh `ControlPlane()` composes the deferred
  in-memory default.
- **The isolation prover** — the Database Router, composed in-process over the durable Control Plane through
  a **harness-local in-process `ControlPlaneRoutingReadPort` bridge** (no served read edge). The Router is
  the sole selector of the tenant database identity.

## 5. §7 trigger injection

- **Preferred — secret-resolution failure.** A synthetic tenant `gamma` is seeded **Ready** in the registry
  with `assoc_store_ref='tenant/gamma/dsn'`, but **no** `tenant/gamma/dsn@1` secret file is written. A routed
  request for `gamma` resolves the Ready view, then the tenant SecretRef fails to resolve; the Router fails
  closed with no connection opened and no new pool key. The failure category and a reason **reference** are
  captured (never a secret value; D-14).
- **Fallback — distinctness regression.** A synthetic distinctness collision across the two disposable
  tenants over the disposable Control DB's ledger. Documented as the alternate; the harness injects the
  preferred trigger.

## 6. Selector-unset & re-composition step

After the trigger, the rehearsal unsets the four `SP2_CP_*` selectors and constructs a fresh
`ControlPlane()`. The re-composed plane is asserted to be the in-memory default (in-memory store,
provisioning operator, and distinctness ledger) whose **construction performs no I/O** (a recorder over the
shared driver module observes zero connect calls). No fail-closed exception type is required or asserted.

## 7. Evidence-bundle output

The harness writes **one** authoritative references-only JSON document **outside the repository**: a 22-field
rollback record (the 8A `docs/runtime/b5_blk8_rollback_evidence_template.md` shape — `ACTIVATION_MODE =
deferred-in-memory`; `FINAL_VERDICT ∈ {DO-NOT-ACTIVATE, ROLLBACK-PROVEN-LOCAL}`; `DISPOSAL_ASSERTION`
mandatory because disposable databases are used) plus an evidence index of 19-key DBR-AR-2E entries the
`ref:evidence#...` anchors resolve to. Every cell is substring-scanned for secret shapes before the document
is written; a printed line alone is not sufficient evidence.

## 8. Disposal (R-A) and STOP-on-failure

- **Shutdown/teardown (deterministic, `finally`-guaranteed, success or failure):** close every direct
  connection; restore every touched environment key; delete the scratch secret directory; sever pool-held
  connections via `pg_terminate_backend`; then dispose.
- **R-A — dispose the complete disposable topology:** `DROP DATABASE IF EXISTS` for
  `sp2_rollback_control`, `sp2_rollback_target`, and `sp2_rollback_adjacent`, then assert a **retained
  disposable datname count = 0**. No delete API, TRUNCATE recovery, trigger disable, or retained-database
  cleanup exists or may be invented. The rehearsal never deletes tenant business data (D-24), and the only
  `DROP DATABASE` targets are the three disposable databases above.
- **STOP-on-failure:** any blob-pin mismatch, assertion mismatch, unexpected status, or ambiguous evidence:
  STOP at that phase; let the harness `finally` complete the teardown + R-A disposal; capture the redacted
  `PASS`/failure output (references only); escalate to Dan and GPT. Do not improvise recovery, do not re-run
  with modified assertions, do not touch any non-disposable database.

## 9. Terminology (BINDING) — two distinct "rollbacks"

- **Composition rollback** (the gate §7 subject this rehearsal newly proves): returning the `ControlPlane()`
  composition to the **deferred (in-memory) default** whose construction performs no I/O. It is
  non-destructive (D-24) and per-tenant isolated (D-30).
- **R-A disposal** (§8): teardown of the **disposable topology** (the three `sp2_rollback_*` databases + the
  scratch secret directory).

These are DISTINCT. Keep them unambiguous in every run record — the served-write runbook uses "rollback" for
disposal, which this rehearsal must not conflate with the composition rollback it proves.

## 10. Forbidden (never part of any run or recovery)

```text
executing without an explicit human Dan START-GATE
pointing SNACKPORTAL_TEST_DSN at production, staging, or any standing/tenant database
applying control 010-015 or any audit-store DDL in this rehearsal
applying DDL to a standing, staging, or production database
wildcard / glob / migration-runner DDL application
storing a raw DSN in the registry or any evidence artifact
introducing a Gateway, Auth, served HTTP edge, or any loopback port into the composed-core plane
retaining any rollback database, secret file, or evidence bundle inside the repository after the run
TRUNCATE / DELETE / trigger disable on any tenant table, or DROP on any non-disposable database
treating rehearsal success as readiness for production or as blocker closure
```

## 11. Locked state (unchanged by this runbook and by any record built from it)

This rehearsal **closes no blocker**. **B5-BLK-8 remains OPEN.** The live blocker census remains **7 of 9
OPEN**. Production remains **NOT READY / DO-NOT-ACTIVATE**. It does not execute a rollback against
production and does not prove a production-scoped rollback; that proof is the later B5-BLK-8C stage, and any
blocker-status effect is a separate B5-BLK-8D decision. Only a later, Dan-authorized governance-effect
decision, resting on captured execution evidence, may change B5-BLK-8's status or the census.
