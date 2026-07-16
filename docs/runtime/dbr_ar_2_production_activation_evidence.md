# DBR-AR-2 — Production Activation Evidence (DBR-AR-2E V1 consolidation)

**Slice:** PRD DBR-AR-2E V1 — production activation evidence consolidation (documentation, evidence index,
and architecture guard only). **Authorization:** Dan START-GATE, 2026-07-16 (V2 execution START-GATE).
**Baseline:** `HEAD == main == origin/main == 62e361be1fb90c3ab6ef2d36d8a048699d6e5e3f` (tree
`45d0680947669eb8d53f57dc373f9373955c1aac`), verified live before any change.
**Machine-readable index:** `docs/runtime/dbr_ar_2_production_activation_evidence_index.json` (exact
nineteen-key records; deterministic ordering; references only).
**Guard:** `backend/tests/architecture/test_dbr_ar_2e_activation_evidence_boundaries.py`.

This record truthfully consolidates what exists and what is missing for durable routing-audit
production activation. It fabricates no evidence, invents no identity, and changes no blocker,
no gate document, no runtime behavior, no DDL, and no database state.

---

## 1. Conclusion (binding)

```text
Outcome A — REMAIN NOT READY / DO-NOT-ACTIVATE
```

DBR-AR-2E evidence consolidation is delivered when this PR merges.
DBR-AR-2 — CLOSED (Dan-authorized governance decision, 2026-07-16); this closure closes zero B5 activation blockers, the blocker census remains nine with 8 of 9 OPEN, and production remains NOT READY / DO-NOT-ACTIVATE.
DBR-AR-2E closes zero activation blockers.
The B5 activation-blocker census remains nine.
Eight of nine blockers remain OPEN.
No production activation decision is made.
No production access or production mutation occurred.
The separate Dan-authorized DBR-AR-2 closure decision is recorded in §13 (2026-07-16).
A separate production activation decision would still be required.

DBR-AR-2E closes zero B5 activation blockers. The activation-blocker census remains nine. The
open-blocker count remains 8 of 9. Production remains NOT READY /
DO-NOT-ACTIVATE.

## 2. Scope — the exact nine-file implementation surface

New: `docs/runtime/dbr_ar_2_production_activation_evidence.md` (this record) ·
`docs/runtime/dbr_ar_2_production_activation_evidence_index.json` ·
`backend/tests/architecture/test_dbr_ar_2e_activation_evidence_boundaries.py`.
Narrow edits: `docs/runtime/dbr_ar_2_durable_routing_audit_contract.md` ·
`infrastructure/runbooks/dbr_ar_2_durable_routing_audit.md` ·
`backend/tests/architecture/test_dbr_ar_2_readiness_contract.py` ·
`backend/tests/architecture/test_dbr_ar_2c_composition_boundaries.py` ·
`backend/tests/architecture/test_dbr_ar_2d_live_proof_boundaries.py` ·
`backend/tests/architecture/test_dbr_ar_2d_standing_witness_boundaries.py`.
No other tracked file changes. The three B5 gate documents, the blocker register, and the B5
evidence template are byte-identical (guard-pinned by blob identity); no runtime source, DDL,
environment selector, workflow, or deployment file changes. (The subsequent DBR-AR-2 closure
decision — §13 — later edited the three B5 gate documents and the coupled guards within its own
sixteen-file documentation + architecture-guard surface; the blob pins were re-stamped there.)

## 3. Commit and environment binding

- Every repository-file evidence row binds to the baseline commit `62e361be1fb90c3ab6ef2d36d8a048699d6e5e3f`
  and tree `45d0680947669eb8d53f57dc373f9373955c1aac`, or — for the nine in-PR files — to the sentinel
  `THIS-PR` (binding completes at the merge commit).
- Standing-environment rows bind to the retained local standing environment: container reference
  `sp2_b3a_control` (loopback `127.0.0.1:5540`), database `snackportal2_control_local` — local fixture
  identities already present in committed documentation; they are NOT production identities.
- Production identities do not exist and none is fabricated; any future production identity must be a
  reference only (D-14).
- The retained pre-apply backup appears ONLY as sha256
  `e5d9a901e807712a93fd5ce66e0c5563d8515eab32e20a7ac47a3b7b4b750671` plus a redacted outside-repository
  reference (runbook §7); no path, DSN, credential, or dump content is recorded.

## 4. Prior-arc provenance matrix (re-derived live, not trusted from reports)

| Arc | PR | Merge commit | Accepted head | What it proved |
|---|---|---|---|---|
| DBR-AR-2 V1 contract | #78 | `efaafc30a21dd779a283547e8f540f828874255a` | `a835c161911edc9297cd260b0de48acfce99e618` | implementation contract + readiness guard (contract capture only) |
| DBR-AR-2A | #79 | `a8b4b0edae0d4a7000a0287f209168e028b28a4f` | `6d5fa60646180c83b00982c8d91587bfb267d65b` | immutable router-edge event model, port, exact vocabulary, exactly-one-event semantics |
| DBR-AR-2B | #80 | `41d30430da53c097cd1c9960815f3495c56bb23f` | `8ddcbb0dc7027903c88b6059340c370842bb2d00` | Control-Plane-owned durable store, DDL 010/011 (created-not-applied), append-only enforcement, idempotent `event_id`, strict internal ingest, uncomposed router client |
| DBR-AR-2C | #81 | `322f588c8a8e477d49bf4f2b644fefedf1f9709e` | `0b15fda4c062127c31156c776dcf8c70954a494b` | explicit opt-in composition, audit-before-hand-back, bounded retry, fail-closed condition-1, no-silent-fallback durable mode |
| DBR-AR-2D V2 | #82 | `e981d3a8e6034d9f70976a3d35a60c2aa462a935` | `a401addafb5742c4571fa766a5fe8cf85dc77e79` | disposable PostgreSQL live proof + hosted CI proof (create → prove → drop), restart durability |
| DBR-AR-2D V3 | #83 | `62e361be1fb90c3ab6ef2d36d8a048699d6e5e3f` | `a525ebe58b72e2364a76be94f49225bb511ddc58` | retained standing witnesses: manual backup-first blob-verified 010→011 apply to the retained local Control DB only; exactly four durable evidence rows; auth-edge zero-row rule; standing topology preserved |

Every merge above is a human two-parent merge (`is_bot=false`); the #83 merge tree equals the accepted
head tree byte-for-byte. The exact-baseline hosted CI (validate · secret-scan · live-pg) is green.

## 5. Blocker traceability — the nine-blocker register (`docs/runtime/b5_activation_blockers.md`)

| Blocker | Requirement | Evidence | Current status | Residual risk | Next required action | Owner | Governing artifact |
|---|---|---|---|---|---|---|---|
| B5-BLK-1 | runtime wiring activated only by decision | deferral pinned (`NotImplementedError`; regression lock) | OPEN | activation without decision | separately-authorized runtime-activation phase | Control Plane | `b5_production_runtime_activation_gate.md` |
| B5-BLK-2 | production Control + tenant DB fleet with identity proof | none — B-3 docs/scaffold-only; D-15 IaC never executed against production | OPEN | no production topology exists | provision fleet + identity/distinctness proof | Infra / Control Plane | `b5_activation_blockers.md` |
| B5-BLK-3 | production-grade secret store resolving `*_REF` | D-14 reference abstraction only (env/file providers) | OPEN | no production secret backend | wire a production-grade pluggable store | Infra | `b5_activation_blockers.md` |
| B5-BLK-4 | provisioning audit sink available and wired | B-6/B-7/B-7A/B-7B + standing wiring (B5-4/B5-4A/Smoke C V2); AT-D15T1-3 satisfied | CLOSED (B5-E, 2026-07-12, Dan-authorized) — evidence-bound governance decision | gate §5 audit-sink condition still binds at activation time | none (closed); condition re-checked at activation | Control Plane | B5-E record in the three gate docs |
| B5-BLK-5 | Lovable integrates only through the API Gateway | interim Supabase/RLS (DRIFT-01) | OPEN | frontend bypasses the gateway | execute the cutover plan | Frontend / Gateway | `b5_activation_blockers.md` |
| B5-BLK-6 | IC-009/IC-007 contracts runtime-bound | not runtime-bound | OPEN | portal/cross-tenant behavior unbound | bind contracts under the Gateway | Architecture | `b5_activation_blockers.md` |
| B5-BLK-7 | production migration / DDL readiness (D-17) | none for production; local DDL discipline proven | OPEN | unproven production schema path | version-gated readiness evidence | Infra / Control Plane | `b5_activation_blockers.md` |
| B5-BLK-8 | proven isolated non-destructive production rollback | none for production; local selector-unset disable proven | OPEN | unrecoverable activation | rollback proof in the deployment era | Control Plane | `b5_activation_blockers.md` |
| B5-BLK-9 | production monitoring / alerting | none; two in-memory counters only; no threshold/owner/escalation | OPEN | silent production failure | monitoring + alerting evidence | Ops | `b5_activation_blockers.md` |

No blocker disappears, no open blocker closes, and no partial evidence is upgraded by this record.
The B5-BLK-4 closure above cites the recorded B5-E governance decision; it is not a claim made by
this consolidation.

## 6. DBR-AR-2 mapping — no register blocker ID exists

DBR-AR-2 is not an entry in the B5 activation-blocker register; DBR-AR-2E closes zero blockers.
The register census is exactly `B5-BLK-1` through `B5-BLK-9`; DBR-AR-2 (durable routing audit) is a
separately tracked Database Router follow-on outside that census ("it was not part of the B5-BLK-4
closure evidence bar" — the B5-E record), governed by `dbr_ar_2_durable_routing_audit_contract.md`.
The separate Dan-authorized DBR-AR-2 closure decision (2026-07-16 — §13) changed neither the
blocker census nor the open count; the CI guards now pin the exact closure record. Durable routing
audit is not a
gate §5 activation condition today (contract §18.3); whether it becomes one is decided at the
separate activation review — that question remains open and is NOT decided by this consolidation
nor by the closure decision (§13).

## 7. PAE-01 … PAE-16 dispositions (canonical; truthful; nothing inferred)

### PASS

```text
PAE-01  Prior arc integrity and provenance
PAE-03  DDL provenance and 010→011 procedure
PAE-04  No runtime DDL / no tenant application
PAE-09  Fail-closed routing and no fallback
PAE-14  Standing-proof preservation and no rerun
PAE-15  Blocker mapping and DBR-AR-2 closure decision
PAE-16  Separation from overall production readiness
```

### NOT AVAILABLE

```text
PAE-02  Production target identity references
PAE-05  Least-privilege writer role and grants
PAE-06  Secret rotation and revocation operations
PAE-07  Production network and TLS controls
PAE-08  Tested production backup and restore
PAE-10  Health, metrics, thresholds, alerts, and escalation
PAE-11  Operational incident-query/access/export evidence
PAE-12  Retention, archival, legal hold, and deletion values
PAE-13  Production canary, change window, disable authority, and post-activation checks
```

No `FAIL` and no `NOT APPLICABLE` disposition exists: nothing contradicts, and every item is a real
requirement of an eventual activation. Every `NOT AVAILABLE` is a live-derived absence: no production
environment, target, writer role, TLS control, monitoring stack, retention value, or canary authority
exists yet (B5-BLK-2/3/7/8/9 OPEN; contract §18.2/§18.4 open governance decisions). Per-item source
binding lives in the machine-readable index.

## 8. Standing-environment evidence binding (read-only; no rerun)

The retained standing Control DB (`snackportal2_control_local`) carries exactly the accepted
DBR-AR-2D V3 evidence, re-verified read-only before and after this consolidation: the exact
20-column `control_routing_audit` schema, exactly 3 CHECK constraints, exactly 2 append-only
triggers plus the trigger function, exactly four evidence rows with four distinct event ids
(`Route` alpha→alpha · `Route` beta→beta · `RouteDenied` `denied:not_ready` dormant ·
`IsolationAnomaly` `anomaly:tenant_binding` alpha→beta), zero rows for the S3 auth-edge correlation,
no fifth row, and `recorded_at` frozen in the single 2026-07-14 15:21:58 UTC witness batch
(full-row digest `md5 = c0fd5261d8a8bc3a40ea733c8bb0a525`, `ORDER BY id`). DDL 010/011 exist in no
tenant, staging, or production target; the automatic standing apply order remains exactly 001–009;
the hosted live-PG loop remains exactly 14 harnesses; the standing witness harness remains a
MANUAL_ONLY exception. The evidence-generating standing scenario was NOT rerun and no database row
was written or altered by this slice.

## 9. Contradiction scan

One pre-existing documentation gap was found by the readiness review (F-2 / MC-4) and is resolved
inside this surface without inventing evidence: contract §15 pointed at a runbook-documented
incident-query procedure and an operator-tuned threshold value that the runbook did not carry. The
runbook now documents the references-only incident-query discipline (runbook §8) and the truthful
threshold posture (runbook §9: a production alert threshold, monitoring owner, and escalation chain
are not defined; PAE-10 remains NOT AVAILABLE; no threshold may be inferred from the standing
environment), and the contract's stale forward pointer is corrected. No status, count, scope, or
posture contradiction exists across the contract, runbook, README, evidence template, gate
documents, guards, workflow, blocker register, or the accepted report corpus. No document overstates
DBR-AR-2 closure and no document overstates the production activation posture.

## 10. Carried items (recorded, not implemented)

**ATR-2B-1** — HTTP transport hardening for the ingest adapter (unsupported-method refusal shape /
default-HTML / `Server:` header). Status: OPEN · SEPARATELY GOVERNED · NOT IMPLEMENTED BY DBR-AR-2E.
The merged 2B refusal shape is unchanged and guard-pinned in four architecture guards.

**OBS-V3-PM-1** — Status: OPEN · SEPARATELY GOVERNED · NON-BLOCKING FOR THE DELIVERED STANDING
EVIDENCE · NOT IMPLEMENTED BY DBR-AR-2E.
OBS-V3-PM-1 proposes stronger AST-level and reviewed-blob pinning for the already-executed
standing-witness operator harness. The standing evidence itself was independently verified directly
against PostgreSQL. DBR-AR-2E carries this observation but does not implement it.

## 11. What this consolidation does NOT do

No production or staging system was accessed; no production secret was obtained; no DDL was created
or applied; no database row, role, grant, network, TLS, secret, backup, monitoring, alerting,
deployment, or traffic state was changed; the standing evidence scenario was not rerun; no runtime
source, workflow, environment selector, or B5 gate document changed; no later slice beyond 2E is
named or begun; and no memory, handover, or tracker file was updated. This record never calls the
consolidated evidence anything other than what it is: the honest index of what exists, whose
conclusion is Outcome A — REMAIN NOT READY / DO-NOT-ACTIVATE.

## 12. Next governed step

The next governed step is the next Dan-authorized governed slice; production activation remains a separate human-governed decision and is not authorized by DBR-AR-2E or by the DBR-AR-2 closure. The closure record is §13.

## 13. DBR-AR-2 closure record (Dan-authorized governance decision, 2026-07-16)

**Authorization:** Dan explicitly authorized DBR-AR-2 Closure Decision V1 execution (V2 execution
START-GATE, 2026-07-16), on the accepted readiness verdict `ACCEPT WITH MECHANICS CLARIFICATIONS`
and the authorized candidate outcome `Outcome A — CLOSE DBR-AR-2`, at the proven baseline
`f5420cce004bee93126449b94ec7e9b68f3a3822` (the PR #84 merge).

**Decision (the only sanctioned closure sentence):**

DBR-AR-2 — CLOSED (Dan-authorized governance decision, 2026-07-16); this closure closes zero B5 activation blockers, the blocker census remains nine with 8 of 9 OPEN, and production remains NOT READY / DO-NOT-ACTIVATE.

**Slice ladder (all delivered, human-merged, arc-closed):**

- DBR-AR-2A — CLOSED (event contract and port; PR #79, human-merged 2026-07-12).
- DBR-AR-2B — CLOSED (durable storage capability; PR #80, human-merged 2026-07-12).
- DBR-AR-2C — CLOSED (composition and failure semantics; PR #81, human-merged 2026-07-14).
- DBR-AR-2D — CLOSED (disposable/hosted proof V2 + retained standing witnesses V3; PRs #82/#83, human-merged 2026-07-14 and 2026-07-16).
- DBR-AR-2E — CLOSED (production-activation evidence consolidation; PR #84, human-merged 2026-07-16; Outcome A — REMAIN NOT READY / DO-NOT-ACTIVATE).

**Preserved state:** Physical Multi-Database MVP — ACCEPTED AT DATABASE GRANULARITY (B5-E,
2026-07-12). B5-BLK-4 remains the only closed activation blocker. The B5 blocker census remains 9;
activation blockers OPEN remain 8 of 9. Production remains NOT READY / DO-NOT-ACTIVATE. The Lovable
cutover remains OPEN. DDL 010/011 remain created-not-applied outside the retained local standing
Control database and un-enrolled from the automatic apply order (001–009). The hosted live-PG loop
remains exactly 14 harnesses; the standing witness harness remains a MANUAL_ONLY exception. No
DBR-AR-2 successor slice exists or is authorized. The PAE dispositions are unchanged (7 PASS /
9 NOT_AVAILABLE; zero FAIL).

**Closure surface:** exactly sixteen tracked files (nine documentation files + six architecture
guards + the standing operator harness), documentation + architecture-guard change only — zero
runtime, DDL, workflow, deployment, database, production, or staging changes; the B5
gate-document blob pins are re-stamped to the closure-updated texts and the DDL 010/011 blob pins
are unchanged.

**§18 dispositions (preserved open; none resolved by this closure):**

- §18.2 retention/legal hold/deletion values — OPEN, separately governed under the D-08 process (the IC-001 retain-all default is operative).
- §18.3 gate-condition decision — OPEN; durable routing audit is not a gate §5 activation condition today; decided at the separate activation review.
- §18.4 writer-role DDL — OPEN, separately governed deployment-era scope (PAE-05 NOT AVAILABLE); the contract's original authoring-time "2B scope" tag is corrected in the contract §18.
- §18.6 API Gateway class-3 durable wiring — OPEN, separately governed, not in the contract §16 matrix, not implemented by this closure; the `source_service` CHECK rejects `api_gateway` by design until that wiring's own governed slice.
- §18.7 optional sink-availability administrative events — OPEN, optional, separately governed, not required for closure.

Reconciled wording tensions (no production evidence invented): the contract §13 tamper-control
sentence now scopes the delivered control to the DB-level trigger (the writer role remains
undelivered — PAE-05 NOT AVAILABLE); the contract §18.4 authoring-time "2B scope" tag is corrected
to separately governed; the contract §17 2E-row objective is superseded by the merged 2E status
(contract §1/§21 — evidence consolidated, production-environment durability NOT AVAILABLE
(PAE-02/PAE-08), gate-condition question re-deferred to the separate activation review).

**Closure-proof composition (MC-CD-6):**

- Proof 3 (unknown tenant; zero dispatch): the live durable `not_found` denial row
  (`backend/tests/control_plane/requires_pg/test_dbr_ar_2d_routing_audit_live_pg.py`), PLUS the
  unit proof of zero connection-factory opens
  (`backend/tests/database_router/test_dbr_ar_2a_event_contract.py` — `factory.opens == []`), PLUS
  the structural resolve-before-acquire proof (`backend/database_router/router.py` — the
  resolve-stage denial precedes `_acquire`), PLUS the standing S4 `pool_view()` before==after
  equality (`backend/tests/control_plane/requires_pg/dbr_ar_2d_standing_witnesses.py`).
- Proof 5 (restart survival): a fresh `PostgresRoutingAuditStore` and a fresh ingest server over
  the same PostgreSQL database re-read the full rows and answer `DUPLICATE_MATCH` on replay (the
  2D V2 harness); PostgreSQL itself was not restarted; the 2026-07-14 → 2026-07-16 cross-session
  standing re-read with the exact frozen full-row digest is the cross-session durability witness.
- Proof 11 (cross-tenant reads denied): structural absence of any read surface
  (`__abstractmethods__` is exactly the append method —
  `backend/tests/database_router/test_dbr_ar_2b_routing_audit_store.py`) plus the ingest 405
  refusal of GET/PUT/DELETE/PATCH/OPTIONS
  (`backend/tests/control_plane/test_dbr_ar_2b_routing_audit_ingest.py`).

**Stale authoring-time prose carve-out (MC-CD-7):** `backend/database_router/main.py` (the module
docstring's authoring-time DBR-AR-2 status parenthetical) and `backend/control_plane/main.py` (the
routing-audit seam comment's authoring-time DBR-AR-2 status sentence) retain their authoring-time
wording by design: they are non-authoritative for governance, non-executable comment/docstring
prose, unpinned by any guard, and their hygiene edit is separately governed (the
`b5_activation_blockers.md` authoring-time-wording idiom, extended to these two locations by
name). This closure PR does not edit them.

**Standing-witness harness lockstep (MC-CD-8):** the operator harness
`backend/tests/control_plane/requires_pg/dbr_ar_2d_standing_witnesses.py` evolves ONLY its
status/verdict text to the post-closure contract sentences; it remains MANUAL_ONLY, is not
enrolled in any CI loop, was not executed during this arc, and every frozen expectation is
preserved (four rows, zero S3 rows, no fifth row, 20 columns, 3 CHECK constraints, 2 append-only
triggers, apply order 001–009, local-Control-only DDL 010/011, frozen digest and recorded_at
batch). The read-only wrapper `test_pg_dbr_ar_2d_standing_witnesses.py` is outside this closure's
authorized surface; its V3W-4 posture-line expectation (which already required lockstep
maintenance after the 2E contract evolution) remains separately governed verification hygiene.

**Re-carry list (MC-CD-10 — re-carried, not resolved):** ATR-2B-1 · OBS-V3-PM-1 · OBS-2E-PM-1
through OBS-2E-PM-6 · OBS-2E-POST-1 · OBS-2E-POST-2 · OBS-2E-POST-3 · writer-role DDL (§18.4) ·
retention/legal-hold/deletion values (§18.2) · the §18.3 gate-condition decision · §18.6 API
Gateway class-3 wiring · §18.7 optional admin events · older-handover regeneration (folders
43/45) · commit-graph maintenance. OBS-2E-POST-1 sequencing note: any future closure-vocabulary
hardening must target the new post-closure canonical sentence and must not reopen DBR-AR-2.
External stale wording outside the authorized surface (the two carved-out `main.py` prose
locations above and the read-only wrapper's posture-line pin) is separately governed
documentation hygiene.
