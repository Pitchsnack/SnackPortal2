-- SnackPortal2 — tenant-DB lineage/import schema (Build Phase 6; IC-004 D-22/D-23/D-25).
-- Portable standard PostgreSQL (RDS / Azure / Cloud SQL / self-hosted). Applied per-tenant
-- as an expand/contract, version-gated migration (D-17). References/codes only — no payload,
-- PII, or secret columns (D-22). Apply order: 001 schema -> 002 append-only -> 003 roles.

-- The per-tenant provenance chain. One continuous chain; segment_id is a label over seq
-- ranges (D-25). seq is UNIQUE => a concurrent chain fork fails closed (PRD-P6-R2 B).
CREATE TABLE IF NOT EXISTS lineage (
    seq                 BIGINT      NOT NULL,
    lineage_id          TEXT        NOT NULL,
    segment_id          BIGINT      NOT NULL DEFAULT 1,
    event_type          TEXT        NOT NULL,   -- import | transform | correction | ai-derivation
    occurred_at         TEXT        NOT NULL,
    actor_ref           TEXT        NOT NULL,   -- identity reference, never a token/credential
    source_ref          TEXT        NOT NULL,   -- origin reference, never payload/credentials
    target_ref          TEXT        NOT NULL,   -- affected tenant record (this tenant DB)
    operation           TEXT        NOT NULL,
    schema_version      TEXT        NOT NULL,   -- ties D-17
    derivation_ref      TEXT,                   -- producing process (import job; AI op later)
    parent_lineage_ref  TEXT,                   -- provenance graph edge (D-25)
    correlation_id      TEXT,
    marker_version      SMALLINT    NOT NULL DEFAULT 1,  -- selects the canonicalizer (PRD-P6-R2 C)
    integrity_marker    TEXT        NOT NULL,   -- per-tenant HMAC hash-chain (D-23)
    prev_marker         TEXT        NOT NULL DEFAULT '',
    CONSTRAINT lineage_pk PRIMARY KEY (lineage_id),
    CONSTRAINT lineage_seq_unique UNIQUE (seq),                         -- fork fail-closed (R-B)
    CONSTRAINT lineage_parent_fk FOREIGN KEY (parent_lineage_ref)       -- acyclic by backward edges
        REFERENCES lineage (lineage_id)
);

-- Read access paths (keyset pagination by seq; graph traversal by parent).
CREATE INDEX IF NOT EXISTS lineage_target_seq_idx     ON lineage (target_ref, seq);
CREATE INDEX IF NOT EXISTS lineage_derivation_seq_idx ON lineage (derivation_ref, seq);
CREATE INDEX IF NOT EXISTS lineage_event_seq_idx      ON lineage (event_type, seq);
CREATE INDEX IF NOT EXISTS lineage_segment_seq_idx    ON lineage (segment_id, seq);
CREATE INDEX IF NOT EXISTS lineage_parent_idx         ON lineage (parent_lineage_ref);

-- Per-segment summary: retained hot even after a segment's rows are archived, so the chain
-- stays verifiable end to end (continuity = closing_marker(N) == opening_prev_marker(N+1)).
CREATE TABLE IF NOT EXISTS lineage_segment (
    segment_id          BIGINT      NOT NULL PRIMARY KEY,
    first_seq           BIGINT      NOT NULL,
    last_seq            BIGINT      NOT NULL,
    opening_prev_marker TEXT        NOT NULL,
    closing_marker      TEXT        NOT NULL,
    record_count        BIGINT      NOT NULL,
    archived_ref        TEXT                    -- portable cold-tier reference when archived
);

-- Import bookkeeping (tenant-resident; closes V-OBS-1/V-OBS-4). NOT append-only — these are
-- the import job/idempotency/checkpoint tables the Phase-5 atomic write path upserts/append.
-- Tenant DATA tables (e.g. tenant_copy) are tenant-schema-specific and out of lineage scope.
CREATE TABLE IF NOT EXISTS import_job (
    job_id          TEXT NOT NULL PRIMARY KEY,
    operation_key   TEXT NOT NULL,
    tenant_id       TEXT NOT NULL,
    state           TEXT NOT NULL,
    correlation_id  TEXT
);

CREATE TABLE IF NOT EXISTS import_idempotency (
    operation_key   TEXT NOT NULL PRIMARY KEY,   -- exactly-once under concurrency (D-20; V-OBS-4)
    job_id          TEXT NOT NULL,
    status          TEXT NOT NULL,
    applied         BIGINT NOT NULL DEFAULT 0,
    noop            BIGINT NOT NULL DEFAULT 0,
    rejected        BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS import_checkpoint (
    job_id          TEXT   NOT NULL,
    batch_seq       BIGINT NOT NULL,
    last_offset     BIGINT,
    applied_count   BIGINT,
    status          TEXT,
    updated_at      TEXT,
    CONSTRAINT import_checkpoint_pk PRIMARY KEY (job_id, batch_seq)
);
