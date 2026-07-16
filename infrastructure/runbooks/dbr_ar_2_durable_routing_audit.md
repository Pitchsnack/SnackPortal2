# DBR-AR-2 — Durable Routing Audit (operator runbook)

**Scope:** NON-PRODUCTION / documentation only (PRD DBR-AR-2D V2). This runbook documents the governed
operator procedure for applying the reviewed routing-audit DDL
(`infrastructure/db/control/010_routing_audit.sql` + `011_routing_audit_append_only.sql`) to a **standing
Control database**, verifying the durable store, and handling incidents. It was delivered by the
DISPOSABLE-ONLY DBR-AR-2D sub-slice; executing it against the standing Control database is a
separately governed, Dan-authorized standing-environment run (not performed by the delivering slice).
The disposable/hosted proof that validated every step below is
`backend/tests/control_plane/requires_pg/test_dbr_ar_2d_routing_audit_live_pg.py` (create → prove → drop;
no standing database touched). Production enablement remains unauthorized until DBR-AR-2E.

Standing rules (inherited from `infrastructure/runbooks/README.md`): secret references only (D-14 —
never a DSN, password, token, or credential in this document, a shell history echo, or any evidence
artifact); fail-closed (any missing or ambiguous proof stops the procedure); **no runtime DDL** — DDL is
applied only by this explicit, operator-driven procedure. No runtime service ever applies DDL.

---

## 1. Preconditions (ALL must hold before any step below)

1. **Approved change window** for the target Control database.
2. **Reviewed commit and DDL blob IDs.** The reviewed LF-normalized git-blob SHA-1 pins are:
   - `010_routing_audit.sql` → `0c5eeecd5e20ef9fe4f11293b6c6561ae7cc897e`
   - `011_routing_audit_append_only.sql` → `cea40fc62c063e9f711fdb7ac90b00a8859586d4`
   These must equal the committed blobs at the checked-out commit AND the recomputed hashes of the files
   about to be applied (they are cross-checked in CI by
   `backend/tests/architecture/test_b7c1_control_audit_ddl_blob_pins.py`).
3. **Standing Control database backup/snapshot** taken and restore-verified per the deployment's backup
   procedure (the B5-BLK-2/B5-BLK-8 evidence stream owns backup scope).
4. **Correct Control database identity confirmed** by a read-only probe (database name + expected
   001–009 object census, e.g. `control_audit` present) — never by assumption.
5. **Credentials by reference only**: connect through the existing reference conventions
   (`control/control-store-dsn` via `SNACKPORTAL_SECRET_CONTROL_CONTROL_STORE_DSN_V1` or the file form) —
   the resolved descriptor is used in memory at connect time and never echoed, logged, or written.
6. **Operator authorization**: a Dan START-GATE naming this standing-environment run.
7. **Explicit proof that no tenant database is targeted**: the connection's `current_database()` is the
   Control database; tenant databases (`sp2_tenant_*`) are never connected to and never named in any
   statement of this procedure.
8. **DBR-AR-2E approval required before production enablement** — this runbook never authorizes
   selecting the durable composition in production; production enablement remains unauthorized.

## 2. Apply (governed ops apply — never runtime DDL)

1. **Verify the blobs BEFORE any SQL**: recompute the LF-normalized git-blob SHA-1 of both files and
   compare each to the reviewed pins in §1.2. On ANY mismatch: STOP — do not connect further, do not
   apply, do not "fix" the DDL in place; escalate for a governed DDL review.
2. Apply exactly `infrastructure/db/control/010_routing_audit.sql` **first**, then exactly
   `infrastructure/db/control/011_routing_audit_append_only.sql` — the exact repository paths, each
   exactly once, in that order. Never a wildcard, glob, directory scan, or migration-runner sweep; these
   two files are deliberately NOT enrolled in the B5-4 standing apply order.
3. **On any SQL error**: stop immediately; capture the error output as redacted evidence
   (SMOKE-C-SPEC-01 §7 rules — no DSN, no credential, no secret value); leave the database as-is (both
   files are idempotent — a reviewed re-run is the recovery path); escalate. Do not improvise recovery.
4. **Evidence capture**: record the commit SHA, both recomputed blob hashes, the apply timestamps, and
   the operator identity — references only.

## 3. Verify (read-only + reject-expected probes)

1. **Catalog checks**: `control_routing_audit` exists; exactly 20 columns in DDL order; identity
   PRIMARY KEY `id`; UNIQUE NOT NULL `event_id`; `recorded_at` carries `DEFAULT now()`; the frozen
   `action` and `source_service` CHECK constraints exist; both triggers
   (`control_routing_audit_no_mutation`, `control_routing_audit_no_truncate`) exist.
2. **Store behavior**: one submitted event answers `INSERTED`; the identical replay answers
   `DUPLICATE_MATCH` with no second row; a same-`event_id`/changed-payload replay answers the bounded
   `CONFLICT` (HTTP 409) with no row change.
3. **Persistence/reconstruction**: a fresh `PostgresRoutingAuditStore` + fresh ingest server against the
   same database re-reads the rows and answers `DUPLICATE_MATCH` on replay.
4. **Append-only canary probes**: issue one UPDATE probe, one DELETE probe, and one TRUNCATE probe and
   confirm each is REJECTED by the append-only triggers, with rows unchanged afterward.
5. **No secret-bearing output**: every evidence artifact carries references only — no DSN, password,
   token, key material, hostname/topology detail, or stored-event dump.

## 4. Canary (documentation only — production enablement remains unauthorized)

```text
ingest endpoint available
→ store health verified
→ enable durable selector
→ controlled canary
→ durable row verified
```

This sequence is documentation only; production enablement remains unauthorized until the DBR-AR-2E
evidence review (the activation gate posture is unchanged by this runbook).

## 5. Disable / incident response (allowed actions)

- **Unset the durable selector** (`SP2_DBR_ROUTING_AUDIT_BASE_URL`) so the NEXT composition returns to
  the prior in-memory posture — never a silent fallback while durable mode is selected (contract §11).
- **Stop the ingest endpoint** — allowed routes then fail closed per contract §11 condition 1; denial
  and anomaly records degrade per condition 3 (preserved outcome + counted loss).
- **Preserve rows** — audit rows are never altered, moved, or removed during an incident.
- **Capture evidence** (redacted, references only) and **alert operators** (any condition-1 denial and
  any condition-3 lost record alert immediately).

## 6. Forbidden (never part of any recovery)

```text
DROP
TRUNCATE
DELETE
disable trigger
rewrite audit rows
silently fall back after durable mode selection
```

Any destructive recovery requires a separate governed incident procedure; nothing in this runbook
authorizes one.

## 7. Standing execution record (DBR-AR-2D V3)

The separately governed, Dan-authorized standing-environment run named above was executed under
**PRD DBR-AR-2D V3** (Dan START-GATE, 2026-07-14) against the retained local standing Control
database only, by the standing witness operator
`backend/tests/control_plane/requires_pg/dbr_ar_2d_standing_witnesses.py` (`plan` → `apply
--backup-dir <outside-repo>` → `run` → `status`): every §1 precondition held (including the
secure full logical backup OUTSIDE the repository, sha256-recorded, `pg_restore --list`
readability-verified), the §2 apply followed the exact 010-then-011 order under the reviewed blob
pins, the §3 verification passed with the exact catalog census and the reject-expected canary
probes, and the standing witness produced exactly the four predeclared durable evidence rows.
The evidence-generating `run` is EXACTLY-ONCE: the operator refuses a second `apply` or `run`
(durable, cross-process refusal), and re-verification is the read-only
`test_pg_dbr_ar_2d_standing_witnesses.py` harness plus the operator `status` command. This record
changes no rule above: the automatic standing apply order remains 001–009, no tenant, staging, or
production database receives 010/011, no runtime service ever applies DDL, and production
enablement remains unauthorized until the DBR-AR-2E evidence review.

## 8. Incident query procedure (documentation only — references-only)

Scope: the OPERATOR incident-query discipline for the durable routing-audit store (contract
§13–§15). This section is documentation only: it names no production target or credential and
claims no production execution; operational production evidence remains `NOT AVAILABLE` (PAE-11),
and production enablement remains unauthorized.

1. **Authorization**: CONTROL-role operator authorization is required before any incident read;
   every incident read is itself an audited, control-plane-scoped operation (contract §13/§14).
2. **Lookup keys**: a query targets exactly one `correlation_id` or exactly one `tenant_ref`.
3. **One-tenant scope**: each query is scoped to a single tenant; cross-tenant aggregation is
   never performed by an incident query (per-tenant scoped reads only — contract §14).
4. **References-only output**: results carry references only — no raw payload, no PII, no
   credential, no DSN, no topology detail, and no exception text is exported or echoed.
5. **Evidence export**: operator-initiated only, audited under the Export Audit class shape
   (IC-002 class 4); exported evidence inherits the SMOKE-C-SPEC-01 §7 redaction rules.

## 9. Alert threshold posture (truthful — no invented value)

A production alert threshold, monitoring owner, and escalation chain are not defined.
PAE-10 remains NOT AVAILABLE.
No threshold may be inferred from the standing environment.
Condition-1 denials and condition-3 lost-record alerts alert immediately (contract §15); the
sustained transient-retry alert threshold is an operator-tuned value that does not exist yet and
is deployment-era scope (B5-BLK-9).

## 10. DBR-AR-2E consolidation record (2026-07-16)

The DBR-AR-2E V1 evidence consolidation (Dan START-GATE, 2026-07-16) indexes this runbook in
`docs/runtime/dbr_ar_2_production_activation_evidence.md` and its machine-readable index; it
changes no procedure above, closes zero B5 activation blockers, keeps the activation-blocker
census at nine, and concludes Outcome A — REMAIN NOT READY / DO-NOT-ACTIVATE. DBR-AR-2 remains
OPEN; production enablement remains unauthorized (a separate Dan-authorized DBR-AR-2 closure
decision and a separate production activation decision would still be required).
