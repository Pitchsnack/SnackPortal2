# W1a Composed-Core Import Copy & Durable Import Audit (operator runbook)

**Scope:** NON-PRODUCTION / documentation only (W1a). This runbook documents the governed operator procedure
for exercising the reviewed W1a Import operational-audit DDL
(`infrastructure/db/control/014_import_operational_audit.sql` +
`015_import_operational_audit_append_only.sql`) and the enrolled tenant uniqueness index
(`infrastructure/db/tenant/008_startups_global_startup_id_unique.sql`) against **disposable** PostgreSQL
databases, verifying the composed-core import copy + its durable Import Audit, and handling incidents. W1a
delivers **the persistent write path + durable audit persistence only** — operator retrieval and the served
northbound `/import` (W1b) are out of scope. The control DDL is **created, NOT applied to any standing,
staging, or production database**, and is deliberately **NOT enrolled** in the B5-4 standing-topology apply
order; tenant `008` is enrolled in the provisioning template (every future provisioned tenant gets the
uniqueness from birth) but is **not applied to any standing/staging/production database by this slice**.
Applying any of these to a standing database is a separately governed, Dan-authorized standing-environment run
(not performed by this slice). The disposable proof that validates every step below is
`backend/tests/control_plane/requires_pg/test_pg_import_copy_durable.py` (create → prove → drop; no standing
database touched). **Production enablement remains unauthorized** (8 of 9 activation blockers OPEN; Production
NOT READY / DO-NOT-ACTIVATE).

Standing rules (inherited from `infrastructure/runbooks/README.md`): secret references only (D-14 — never a
descriptor, password, token, or credential in this document, a shell-history echo, or any evidence artifact);
fail-closed (any missing or ambiguous proof stops the procedure); **no runtime DDL** — DDL is applied only by
this explicit, operator-driven procedure. No runtime service ever applies DDL. The API Gateway holds no
database driver and no Control-DB descriptor; the Import Service holds no Control-DB descriptor; the Control
Plane is the sole Control-DB writer.

---

## 1. Preconditions (ALL must hold before any step below)

1. **Disposable, non-production PostgreSQL only.** `SNACKPORTAL_TEST_DSN` must point at a throwaway local
   instance or the ephemeral CI service — NEVER production, shared staging, the standing Control database, or
   any tenant database. The proof creates and drops its own databases `sp2_w1a_import_proof_control`,
   `sp2_w1a_import_proof_t1`, and `sp2_w1a_import_proof_t2`.
2. **Reviewed DDL blob IDs.** The reviewed LF-normalized git-blob SHA-1 pins are:
   - `014_import_operational_audit.sql` → `73436f9681163c8a86ee230f51206062b06735c5`
   - `015_import_operational_audit_append_only.sql` → `ba594e3cd6eb070790bde6015f5225960c0d62ed`
   - `008_startups_global_startup_id_unique.sql` → `20741db4dc6152bcdf9aaec029b9845a7bacb78e`

   The control pins are cross-checked in the default suite by
   `backend/tests/architecture/test_b7c1_control_audit_ddl_blob_pins.py`; the tenant pin by
   `backend/tests/architecture/test_tenant_ddl_blob_drift.py`; and all three, plus the composed-core
   boundaries, by `backend/tests/architecture/test_import_write_path_boundaries.py` and by the disposable
   proof's own STOP-before-connect check.
3. **Credentials by reference only.** The DSN reaches the proof only through the `_pg` runner
   (`SNACKPORTAL_TEST_DSN`, by name); its value is used in memory at connect time and never echoed, logged, or
   written. Tenant descriptors are resolved in-memory through a proof-local `SecretStore` (references only).
4. **Production enablement remains unauthorized** — this runbook never authorizes selecting the composed
   import execution port (`SP2_GW_IMPORT_BASE_URL`), the durable Import-audit sink
   (`SP2_IMPORT_AUDIT_SINK_BASE_URL`), or the served edges (`SP2_IMPORT_HOST`, `SP2_CP_IMPORT_AUDIT_HOST`) in
   production; enablement requires a separate human-governed production activation decision.

## 2. Apply (governed ops apply — never runtime DDL)

1. **Verify the blobs BEFORE any SQL**: recompute the LF-normalized git-blob SHA-1 of `014`, `015`, and `008`
   and compare each to the reviewed pins in §1.2. On ANY mismatch: STOP — do not connect further, do not apply,
   do not "fix" the DDL in place; escalate for a governed DDL review.
2. Against the disposable proof databases only: apply control `001`–`009` (unpinned base control schema) then
   exactly `014_import_operational_audit.sql` **first**, then exactly
   `015_import_operational_audit_append_only.sql` — the exact repository paths, each exactly once, in that
   order; and apply the enrolled 14-file tenant template (provisioning + lineage + tenant `001`–`008`) to each
   disposable tenant database. Never a wildcard, glob, directory scan, or migration-runner sweep; `014`/`015`
   are deliberately NOT enrolled in the B5-4 standing apply order.
3. **On any SQL error**: stop immediately; capture the error output as redacted evidence (no descriptor, no
   credential, no secret value); the files are idempotent (a reviewed re-run is the recovery path); escalate.
   Do not improvise recovery.

## 3. Verify (read-only + reject-expected probes)

1. **Catalog checks**: `control_import_audit` exists; exactly 12 columns in DDL order; identity PRIMARY KEY
   `id`; UNIQUE NOT NULL `audit_id`; `recorded_at` carries `DEFAULT now()`; the frozen `action` (five import
   actions), `event_version`, and `source_service = 'import_service'` CHECK constraints exist; both triggers
   (`control_import_audit_no_mutation`, `control_import_audit_no_truncate`) exist; each disposable tenant
   database carries the plain, non-partial `startups_global_startup_id_key` unique index.
2. **Composed path (through the real internal edges)**: `Gateway.handle(/import/<ref>)` → the served internal
   Import edge → `ImportService.start_import` → exactly one `DatabaseRouter.route()` → one physical tenant
   database → the startups upsert + atomic lineage + durable Import Audit. A fresh import answers `200 created`
   with the tenant row + lineage row present and exactly three durable audit rows; the identical replay answers
   `200 replayed` with no new tenant row and exactly two more audit rows; an unchanged re-copy answers `noop`.
3. **Physical isolation**: the other tenant database is untouched; a dual-carrier straddle is denied `403` with
   zero tenant rows and zero durable import audit.
4. **Database-authority canary probes**: a duplicate `global_startup_id` direct INSERT is rejected by the
   tenant `008` unique index; one UPDATE probe, one DELETE probe, and one TRUNCATE probe on
   `control_import_audit` are each REJECTED by the append-only triggers, with rows unchanged afterward.
5. **No secret-bearing output**: every evidence artifact carries references only — no descriptor, password,
   token, key material, hostname/topology detail, or stored-event dump.

## 4. Fail-closed behavior (durable mode)

The composed-core import path is audit-before-hand-back and fail-closed:

```text
Gateway IMPORT_INITIATION (composed) success
→ ImportService.start_import (atomic tenant copy + lineage + checkpoint)
→ BoundedImportAuditPolicy (exactly one bounded retry for transient unavailability, same audit_id)
→ DurableImportAuditEmitter → import-audit ingest edge → PostgresImportAuditStore → control_import_audit
→ on terminal sink unavailability: typed 503 unavailable (a served import success is NEVER handed back
  without durable completion confirmation; the applied operation is preserved; the same operation-key retry
  performs no duplicate write and returns 200 replayed only after durable confirmation; no queue/outbox)
```

## 5. Disable / incident response (allowed actions)

- **Unset the composed selectors** (`SP2_GW_IMPORT_BASE_URL`, `SP2_IMPORT_AUDIT_SINK_BASE_URL`) so the NEXT
  composition returns to the port-absent accepted-initiation envelope + in-memory no-sink posture — never a
  silent fallback while durable mode is selected.
- **Stop the ingest endpoint** — served composed imports then fail closed to the typed `503`
  (audit-before-hand-back); no success is served without durable completion confirmation.
- **Preserve rows** — audit rows and applied tenant rows are never altered, moved, or removed during an
  incident.
- **Capture evidence** (redacted, references only) and **alert operators**.

## 6. Forbidden (never part of any recovery)

```text
DROP
TRUNCATE
DELETE
disable trigger
rewrite audit rows
silently fall back after durable mode selection
apply 014/015/008 to a standing, staging, or production database
enroll 014/015 in the automatic standing apply order
```

Any destructive recovery requires a separate governed incident procedure; nothing in this runbook authorizes
one. Production enablement remains unauthorized; operator retrieval and the served northbound `/import` (W1b)
remain out of scope.
