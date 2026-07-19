-- SnackPortal2 — Control-DB durable Import operational-audit store (IC-003 "Import Audit"; IC-001 Reference-Only; W1a).
-- The durable, append-only, reference-only table for the Import-operational-audit events the Import Service emits (IC-003):
-- one row per emitted import event. W1a persists the WHOLE Import-operational-audit class — the five actions the Import
-- Service emits (ImportRequested / ImportStarted / ImportResumed / ImportCompleted / ImportFailed). It lives in the CONTROL
-- database (control-plane-owned), beside control_audit (002), control_routing_audit (010), and control_gateway_audit (012).
-- The Control Plane remains the sole Control-DB writer: rows arrive ONLY through the Control-Plane-owned store adapter
-- (backend/control_plane/adapters/providers/postgres_store.py PostgresImportAuditStore.append_import_audit) behind the internal
-- loopback ingest edge. DISTINCT from control_audit (002, provisioning lifecycle audit), DISTINCT from control_gateway_audit
-- (012, the API-Gateway edge), DISTINCT from control_routing_audit (010, the Database Router edge), and DISTINCT from
-- tenant-data lineage (IC-004 / D-23, the hash-chained provenance subsystem in the tenant DB). This is control-plane
-- operational audit, NOT lineage: it deliberately carries NO hash-chain column. LineageWritten is NOT an import-audit action
-- (the action CHECK below structurally rejects it) — the durable provenance evidence is the hash-chained lineage row itself.
--
-- The columns mirror the Control-Plane-local ImportAuditRecord (backend/control_plane/import_audit.py) plus the two
-- store-assigned columns, matching the adapter:
--   INSERT INTO control_import_audit (audit_id, event_version, occurred_at, correlation_id, action, outcome, source_service,
--       actor_ref, target_ref, source_ref)   -- id / recorded_at NOT inserted
--   ON CONFLICT (audit_id) DO NOTHING
-- `id` is DB-generated and is the durable total-ordering authority (reads ORDER BY id ASC — the B-7 precedent);
-- `recorded_at` is DB-assigned (DEFAULT now()); timestamps NEVER define total ordering (occurred_at is informational only,
-- emitter clock). `audit_id` is the emitter-minted idempotency key (uuid4().hex): UNIQUE, duplicate insert is a no-op, and the
-- adapter exact-compares a conflicting replay and rejects same-ID/different-payload drift. The action and source_service
-- CHECKs pin the CONTRACT-FROZEN Import-audit vocabulary — the action set is exactly the five IC-003 import actions, and
-- source_service is the ingest/store-side producer constant 'import_service' (never a wire field).
--
-- References only (D-14; IC-001 Global Audit Representation Rule; IC-003:131): actor/tenant/source references, action, outcome,
-- correlation reference, and event metadata only. NO passwords, NO DSNs / connection strings, NO raw secret values, NO JWT /
-- session / API keys, NO cloud credentials, NO PII, NO business payloads, NO imported source-record content, NO request/response
-- bodies, NO database hostnames / physical database names / topology, NO serialized connection or routing objects. target_ref is
-- the active tenant reference; source_ref is the import source reference (IC-003:131). No JSON/JSONB, no arbitrary metadata
-- column, no raw error text column, no foreign key to any tenant database, no cross-database constraint, no hash-chain column,
-- no retention duration (IC-001 platform retention policy governs; default retain-all; D-08 process). Portable standard
-- PostgreSQL (AWS RDS / Azure Database for PostgreSQL / Cloud SQL / self-hosted) — no extensions, no provider-proprietary
-- features. Idempotent and additive (no destructive migration).
--
-- Append-only by design: id is immutable; there is NO UPDATE path and NO DELETE path; corrections, failures, and reversals are
-- NEW rows. DB-level append-only enforcement is the companion 015_import_operational_audit_append_only.sql.
--
-- Created, NOT applied: this template is authored under PRD W1a (controlled non-production). Applying it to a live Control
-- database, and exercising the durable Import operational-audit store against a real cluster, is done ONLY by the MANUAL_ONLY
-- disposable proof (create -> prove -> drop; governed ops apply only — never runtime DDL). It is deliberately NOT enrolled in the
-- B5-4 standing-topology apply order. The composed import-audit default remains the in-memory no-sink emitter; durable mode is
-- explicit and env-selected. Least-privilege writer-role DDL remains separately governed and is not delivered by W1a.

CREATE TABLE IF NOT EXISTS control_import_audit (
    id             bigint       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- DB-generated; adapter never inserts id; ORDER BY id ASC
    audit_id       text         NOT NULL UNIQUE,  -- emitter-minted uuid4().hex idempotency key; duplicate insert is a no-op
    event_version  integer      NOT NULL CONSTRAINT control_import_audit_event_version_check CHECK (event_version > 0),
    occurred_at    timestamptz  NOT NULL,     -- emitter clock; informational only — never an ordering authority
    recorded_at    timestamptz  NOT NULL DEFAULT now(),  -- DB-assigned at insert; never caller-supplied
    correlation_id text         NOT NULL,     -- request correlation reference
    action         text         NOT NULL CONSTRAINT control_import_audit_action_check
                                CHECK (action IN ('ImportRequested', 'ImportStarted', 'ImportResumed',
                                                  'ImportCompleted', 'ImportFailed')),
    outcome        text         NOT NULL,     -- success / replayed / error:<code> (references only)
    source_service text         NOT NULL CONSTRAINT control_import_audit_source_service_check
                                CHECK (source_service = 'import_service'),
    actor_ref      text,                      -- NULLABLE: authenticated subject reference (never a credential)
    target_ref     text,                      -- NULLABLE: the active tenant reference (IC-003:131 tenant id)
    source_ref     text                       -- NULLABLE: the import source reference (IC-003:131)
);
