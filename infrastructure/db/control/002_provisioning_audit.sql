-- SnackPortal2 — Control-DB provisioning audit store (D-34 Operational Audit; IC-002; IC-001 Reference-Only; IC-010 §J; PRD 06 B-7).
-- The durable, append-only, reference-only audit-history table for provisioning lifecycle events — the table the wired
-- control-plane adapter backend/control_plane/adapters/providers/postgres_store.py ALREADY targets (append_audit / list_audit).
-- It lives in the CONTROL database (control-plane-owned), alongside the other control_* tables. DISTINCT from the distinctness
-- ledger (001, a per-tenant inventory) and DISTINCT from tenant-data lineage (IC-004 / D-23, the hash-chained provenance
-- subsystem in the tenant DB). This is control-plane operational audit, NOT lineage.
--
-- The columns mirror ControlAuditRecord (backend/control_plane/records.py) EXACTLY, matching the live adapter:
--   INSERT INTO control_audit (actor, tenant_id, action, from_state, to_state, ts, correlation_id)   -- id is NOT inserted
--   SELECT actor, tenant_id, action, from_state, to_state, ts, correlation_id FROM control_audit ORDER BY id ASC
-- `id` is DB-generated (the adapter never binds it). `action` is a plain text column whose values come from the FROZEN
-- events.py vocabulary (EXPECTED_EVENT_ACTIONS) — there is deliberately NO SQL CHECK/enum here; events.py remains the sole
-- source of truth (a SQL CHECK would be a parallel catalog). The three Optional record fields (tenant_id, from_state,
-- to_state) are NULLABLE, so the wired append_audit() never fails a NOT NULL constraint.
--
-- References only (D-14; IC-001 Global Audit Representation Rule): actor/tenant/correlation references and event metadata only.
-- NO passwords, NO DSNs / connection strings, NO raw secret values, NO JWT / session / API keys, NO cloud credentials, NO PII,
-- NO business payloads. Portable standard PostgreSQL (AWS RDS / Azure Database for PostgreSQL / Cloud SQL / self-hosted) — no
-- extensions, no provider-proprietary features. Idempotent and additive (no destructive migration).
--
-- Append-only by design: id is immutable; there is NO UPDATE path and NO DELETE path; corrections, failures, and (future)
-- rollback events are NEW rows. DB-level append-only enforcement is the companion 003_provisioning_audit_append_only.sql.
--
-- Created, NOT applied: this template is authored under PRD 06 B-7 (controlled non-production). Applying it to a live Control
-- database, and exercising the durable audit store against a real cluster, is a SEPARATE later gated phase (live-PostgreSQL
-- exercise = B-7A) — NOT B-7. The control-plane runtime default remains the in-memory store.

CREATE TABLE IF NOT EXISTS control_audit (
    id              bigint        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- DB-generated; adapter never inserts id; ORDER BY id ASC
    actor           text          NOT NULL,     -- actor reference (never a credential)
    tenant_id       text,                        -- NULLABLE: some events carry no tenant
    action          text          NOT NULL,     -- events.py vocabulary; plain text, NO enum/CHECK
    from_state      text,                        -- NULLABLE
    to_state        text,                        -- NULLABLE
    ts              timestamptz   NOT NULL,     -- ControlAuditRecord.timestamp (now_iso() ISO-8601 string -> timestamptz)
    correlation_id  text          NOT NULL      -- request correlation reference
);
