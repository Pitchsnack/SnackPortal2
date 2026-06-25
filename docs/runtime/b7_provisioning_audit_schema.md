# PRD 06 B-7 — Provisioning Audit Schema (live table + forward-contract extension)

This doc has two **explicitly separated** parts: (1) the **live `control_audit` columns** the `002` DDL defines (the wired
table), and (2) a **forward-contract extension proposal** (the richer field set) that is **not** the wired table and is not
authored as DDL in B-7.

---

## 1. Live `control_audit` columns (what `002_provisioning_audit.sql` defines)

Grounded on `postgres_store.py` (the adapter's INSERT/SELECT) and `records.py` (`ControlAuditRecord`). The DDL is
**adapter-INSERT-compatible**:

| column | type | null? | source |
|--------|------|-------|--------|
| `id` | `bigint` (GENERATED ALWAYS AS IDENTITY) | DB-generated | not inserted by the adapter; `ORDER BY id ASC` |
| `actor` | `text` | NOT NULL | `ControlAuditRecord.actor` |
| `tenant_id` | `text` | **NULLABLE** | `ControlAuditRecord.tenant_id` (Optional) |
| `action` | `text` | NOT NULL | events.py vocabulary (plain text; no CHECK) |
| `from_state` | `text` | **NULLABLE** | `ControlAuditRecord.from_state` (Optional) |
| `to_state` | `text` | **NULLABLE** | `ControlAuditRecord.to_state` (Optional) |
| `ts` | `timestamptz` | NOT NULL | `ControlAuditRecord.timestamp` (`now_iso()` ISO-8601 → timestamptz) |
| `correlation_id` | `text` | NOT NULL | `ControlAuditRecord.correlation_id` |

The Optional record fields are NULLABLE so the wired `append_audit()` never fails a NOT NULL constraint.

## 2. Event vocabulary mapping (maps to events.py — no parallel catalog)

`action` values come from the **frozen** `events.py` vocabulary (the sole source of truth, guarded by
`EXPECTED_EVENT_ACTIONS`). The DDL uses a plain `text` column with **no** SQL `CHECK`/enum. The machine-readable map below is
asserted by the contract test (every right-hand name must be a member of the live `events.py` action set):

```
<!-- B7-EVENT-MAP:START -->
requested            -> DatabaseProvisionRequested
succeeded            -> DatabaseProvisionSucceeded
failed               -> DatabaseProvisionFailed
associated           -> DatabaseAssociated
secret-reference     -> SecretReferenceRegistered
distinctness-passed  -> DistinctnessVerificationPassed
distinctness-failed  -> DistinctnessVerificationFailed
isolation-anomaly    -> IsolationAnomaly
<!-- B7-EVENT-MAP:END -->
```
(Registration, routing-eligibility, suspension/decommission events also remain part of the frozen vocabulary and are emitted
by the existing control plane; B-7 does not redefine them.) No `tenant.provision.*` catalog. Rollback events are a forward
proposal only.

## 3. Forward-contract extension proposal (NOT the wired table; NOT authored as DDL in B-7)

A **richer 28-field** reference-field model is a documented **forward-contract extension proposal** — adopting it requires a
future *governed* `records.py` + `events.py` + migration change (a separate gate). It is **not** the wired `control_audit`
table (§1) and is **not** in `002`. Proposed forward fields (references only; not yet live):

```
audit_event_id · event_version · occurred_at / recorded_at · actor_type · database_target_ref · operation_phase ·
request_id · source_service · decision_ref · readiness_gate_ref · outcome · error_class · redacted_error_message ·
evidence_ref · payload_ref · redaction_policy_ref · retention_policy_ref · hash_policy_ref · previous_event_hash · event_hash
```

`previous_event_hash` / `event_hash` are **optional / forward only** and appear **only** in this extension — never in the
live `control_audit` table — and must **not** be modelled on or conflated with IC-004 / D-23 lineage's hash-chain.
