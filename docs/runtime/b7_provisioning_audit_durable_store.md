# PRD 06 B-7 — Provisioning Audit Durable Store (contract; created-not-applied)

**Status: DDL artifact (created, NOT applied) + docs + additive tests only.** B-7 authors the **missing DDL for the existing
`control_audit` table** — the table the wired durable adapter `backend/control_plane/adapters/providers/postgres_store.py`
already `INSERT`s into and `SELECT`s from — without applying DDL, wiring runtime, or activating production. It mirrors
`infrastructure/db/control/001_distinctness_ledger.sql` (the established "created, not applied" Control-DB convention).

---

## 1. What already exists (B-7 builds on it, does not re-author)

`PostgresControlStore.append_audit/list_audit` (`postgres_store.py:197-232`) already target `control_audit`:
```
INSERT INTO control_audit (actor, tenant_id, action, from_state, to_state, ts, correlation_id)   -- id is NOT inserted
SELECT  actor, tenant_id, action, from_state, to_state, ts, correlation_id FROM control_audit ORDER BY id ASC
```
The columns mirror `ControlAuditRecord` (`records.py`). The table had **no committed DDL** — that gap is exactly what B-7
fills. The runtime default remains the in-memory store; durable-store runtime wiring is **deferred** (parallels B-2's ledger).

## 2. What B-7 adds

```
infrastructure/db/control/002_provisioning_audit.sql   CREATE TABLE IF NOT EXISTS control_audit (...), created-not-applied,
                                                       adapter-INSERT-compatible (id DB-generated; tenant_id/from_state/to_state
                                                       NULLABLE; actor/action/ts/correlation_id NOT NULL; ts timestamptz).
infrastructure/db/control/003_provisioning_audit_append_only.sql   a portable PL/pgSQL append-only trigger (created-not-applied;
                                                       mirrors lineage/002_append_only.sql).
docs (this set) + additive guard tests.
```

## 3. Distinctness (do not conflate)

Provisioning audit (**IC-002 / D-34**) is operational lifecycle audit in the **Control DB**. It is **distinct** from:
- the **distinctness ledger** (`001`, a per-tenant *inventory*, not an audit-history trail); and
- tenant-data **lineage** (**IC-004 / D-23**), the hash-chained provenance subsystem in the *tenant* DB.

`control_audit` carries **no hash-chain**. Any optional/forward hash policy is a documented forward-contract extension (see
`b7_provisioning_audit_schema.md`) and is **not** IC-004/D-23 lineage.

## 4. Append-only & references-only

Append-only by design (immutable `id`; no UPDATE/DELETE path; corrections/failures/rollbacks are new rows; retention is not
direct DELETE in B-7). DB-level enforcement = the `003` trigger (created-not-applied). References only (D-14/IC-001): actor/
tenant/correlation references + event metadata; never raw DSNs/passwords/tokens/keys/credentials/PII/business payloads.

## 5. Deferred (separate, governed gates)

Applying `002`/`003` · wiring `control_audit` to runtime · the live-PostgreSQL exercise (**B-7A**) · a production sink. B-7
**reduces B6-BLK-2** (durable audit-table DDL now authored, created-not-applied) but **does not close B5-BLK-4** — see
`b7_provisioning_audit_blockers.md`. B-7 introduces **no** 28-field parallel audit table and does **not** modify the adapter.
