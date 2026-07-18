# Gateway Operational Audit Persistence V1a — Durable Gateway Audit (operator runbook)

**Scope:** NON-PRODUCTION / documentation only (Gateway Audit V1a). This runbook documents the governed
operator procedure for exercising the reviewed Gateway operational-audit DDL
(`infrastructure/db/control/012_gateway_operational_audit.sql` +
`013_gateway_operational_audit_append_only.sql`) against a **disposable** PostgreSQL database, verifying
the durable store, and handling incidents. V1a delivers **durable persistence only** — operator retrieval
(V1b) is out of scope. The DDL is **created, NOT applied to any standing, staging, or production
database**, and is deliberately **NOT enrolled** in the B5-4 standing-topology apply order. Applying it to
a standing Control database is a separately governed, Dan-authorized standing-environment run (not
performed by this slice). The disposable proof that validates every step below is
`backend/tests/control_plane/requires_pg/test_pg_gateway_audit_durable.py` (create → prove → drop; no
standing database touched). **Production enablement remains unauthorized** (8 of 9 activation blockers
OPEN; Production NOT READY / DO-NOT-ACTIVATE).

Standing rules (inherited from `infrastructure/runbooks/README.md`): secret references only (D-14 — never
a DSN, password, token, or credential in this document, a shell-history echo, or any evidence artifact);
fail-closed (any missing or ambiguous proof stops the procedure); **no runtime DDL** — DDL is applied only
by this explicit, operator-driven procedure. No runtime service ever applies DDL. The API Gateway holds no
database driver and no Control-DB descriptor; the Control Plane is the sole Control-DB writer.

---

## 1. Preconditions (ALL must hold before any step below)

1. **Disposable, non-production PostgreSQL only.** `SNACKPORTAL_TEST_DSN` must point at a throwaway local
   instance or the ephemeral CI service — NEVER production, shared staging, the standing Control database,
   or any tenant database. The proof creates and drops its own database `sp2_gateway_audit_v1a_proof`.
2. **Reviewed DDL blob IDs.** The reviewed LF-normalized git-blob SHA-1 pins are:
   - `012_gateway_operational_audit.sql` → `5df1ae4edb7a943b33f36fc3800d81c8cb75804b`
   - `013_gateway_operational_audit_append_only.sql` → `199664d1afb9e6e0a37e8609f42e4e1528771472`

   These are cross-checked in the default suite by
   `backend/tests/architecture/test_b7c1_control_audit_ddl_blob_pins.py` and by the disposable proof's own
   STOP-before-connect check.
3. **Credentials by reference only.** The DSN reaches the proof only through the `_pg` runner
   (`SNACKPORTAL_TEST_DSN`, by name); its value is used in memory at connect time and never echoed,
   logged, or written.
4. **Production enablement remains unauthorized** — this runbook never authorizes selecting the durable
   audit composition (`SP2_GW_AUDIT_SINK_BASE_URL`) in production; enablement requires a separate
   human-governed production activation decision.

## 2. Apply (governed ops apply — never runtime DDL)

1. **Verify the blobs BEFORE any SQL**: recompute the LF-normalized git-blob SHA-1 of both files and
   compare each to the reviewed pins in §1.2. On ANY mismatch: STOP — do not connect further, do not
   apply, do not "fix" the DDL in place; escalate for a governed DDL review.
2. Apply exactly `infrastructure/db/control/012_gateway_operational_audit.sql` **first**, then exactly
   `infrastructure/db/control/013_gateway_operational_audit_append_only.sql` — the exact repository paths,
   each exactly once, in that order, against the disposable proof database only. Never a wildcard, glob,
   directory scan, or migration-runner sweep; these two files are deliberately NOT enrolled in the B5-4
   standing apply order.
3. **On any SQL error**: stop immediately; capture the error output as redacted evidence (no DSN, no
   credential, no secret value); the files are idempotent (a reviewed re-run is the recovery path);
   escalate. Do not improvise recovery.

## 3. Verify (read-only + reject-expected probes)

1. **Catalog checks**: `control_gateway_audit` exists; exactly 13 columns in DDL order; identity PRIMARY
   KEY `id`; UNIQUE NOT NULL `audit_id`; `recorded_at` carries `DEFAULT now()`; the frozen `action`,
   `event_version`, and `source_service` CHECK constraints exist; both triggers
   (`control_gateway_audit_no_mutation`, `control_gateway_audit_no_truncate`) exist.
2. **Store behavior (through the real HTTP wire)**: one submitted `workspace_memberships_read` success
   event answers `INSERTED`; the identical replay answers `DUPLICATE_MATCH` with no second row; a
   same-`audit_id`/changed-payload replay answers the bounded `CONFLICT` (HTTP 409) with no row change.
3. **Persistence/reconstruction**: a fresh `PostgresGatewayAuditStore` + fresh ingest server against the
   same database re-reads the rows and answers `DUPLICATE_MATCH` on replay.
4. **Append-only canary probes**: issue one UPDATE probe, one DELETE probe, and one TRUNCATE probe and
   confirm each is REJECTED by the append-only triggers, with rows unchanged afterward.
5. **No secret-bearing output**: every evidence artifact carries references only — no DSN, password,
   token, key material, hostname/topology detail, or stored-event dump.

## 4. Fail-closed behavior (durable mode)

The gateway durable path is audit-before-hand-back and fail-closed:

```text
Gateway MembershipsForPrincipal success
→ BoundedGatewayAuditPolicy (exactly one bounded retry for transient unavailability)
→ DurableAuditEmitter → ingest edge → PostgresGatewayAuditStore → control_gateway_audit
→ on terminal sink unavailability: typed 503 unavailable (a served success is NEVER handed back
  without durable persistence confirmation; no silent event loss, no queue/outbox)
```

## 5. Disable / incident response (allowed actions)

- **Unset the durable selector** (`SP2_GW_AUDIT_SINK_BASE_URL`) so the NEXT composition returns to the
  prior in-memory no-sink posture — never a silent fallback while durable mode is selected.
- **Stop the ingest endpoint** — served MembershipsForPrincipal successes then fail closed to the typed
  503 (audit-before-hand-back); no success is served without durable persistence.
- **Preserve rows** — audit rows are never altered, moved, or removed during an incident.
- **Capture evidence** (redacted, references only) and **alert operators**.

## 6. Forbidden (never part of any recovery)

```text
DROP
TRUNCATE
DELETE
disable trigger
rewrite audit rows
silently fall back after durable mode selection
apply 012/013 to a standing, staging, or production database
enroll 012/013 in the automatic standing apply order
```

Any destructive recovery requires a separate governed incident procedure; nothing in this runbook
authorizes one. Production enablement remains unauthorized; V1b operator retrieval remains out of scope.
