-- SnackPortal2 — Tenant-DB agents + System Primary constraints (PRD 07C V5 §9; exec-auth V2 §12.1).
-- FIRST file of the tenant business schema family (infrastructure/db/tenant/, applied 001->007). Lives in
-- EVERY physical tenant database (one DB per tenant — physical isolation; never a shared DB + tenant_id).
-- 07B.1 later sequences this family into the existing Step-2b atomic transaction (after the six 07B
-- templates) and seeds EXACTLY ONE System Primary row: this file authors the TABLE AND CONSTRAINTS ONLY —
-- it must never seed the row itself (07C V5 §9.3). The 07B.1 seed shape this table must accept verbatim:
--   INSERT INTO agents (agent_kind, agent_status, supervised_by_agent_id)
--   SELECT 'system_primary', 'active', NULL
--   WHERE NOT EXISTS (SELECT 1 FROM agents WHERE agent_kind = 'system_primary');
-- (id generated; display_name/created_at/updated_at defaulted; control_user_id nullable — the nine 07B.1
-- V2 §A.3 shape requirements are all satisfied here.)
--
-- SYSTEM PRIMARY (the per-tenant root/supervisor anchor): at most one row may carry
-- agent_kind='system_primary' (partial unique index); it must be unsupervised and active (CHECKs); and it
-- can neither be DELETEd nor have its kind flipped away (protective trigger below — a kind-flip or DELETE
-- would escape both CHECKs and the partial index and strand the tenant without its anchor). Status and
-- supervision mutations remain blocked by the CHECKs while its kind is unchanged. No human Agent is
-- required for fresh tenant readiness; no queue-manager exists (claim collision is 07C V5 §6.4:
-- first-writer-wins INSERT into the ownership tables; UNASSIGNED = ownership-row absence).
--
-- control_user_id is a SOFT text reference to a Control-DB principal (physically separate database — no
-- cross-database FK is possible or allowed). Typing note: tenant business tables use timestamptz — the MCC
-- all-text rule was specific to the unmodified PostgresControlStore string round-trip and does NOT apply
-- here (no runtime adapter reads tenant business tables yet).
--
-- References only (D-14): no secrets, DSNs, credentials, or PII. Portable standard PostgreSQL (AWS RDS /
-- Azure Database for PostgreSQL / Cloud SQL / self-hosted) — no extensions. Idempotent (IF NOT EXISTS /
-- CREATE OR REPLACE / DROP TRIGGER IF EXISTS) and transaction-safe (no CREATE DATABASE / CREATE INDEX
-- CONCURRENTLY / VACUUM) for the atomic Step-2b apply. Created, NOT applied: applied to live tenant DBs
-- only by 07B.1 sequencing or the 07C live-PG proof harness (test_pg_tenant_business_schema_07c.py).

CREATE TABLE IF NOT EXISTS agents (
    id                     bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    agent_kind             text        NOT NULL DEFAULT 'human'
                               CONSTRAINT agents_kind_check
                               CHECK (agent_kind IN ('human', 'system_primary')),
    agent_status           text        NOT NULL DEFAULT 'active'
                               CONSTRAINT agents_status_check
                               CHECK (agent_status IN ('active', 'inactive')),
    display_name           text        NOT NULL DEFAULT '',
    control_user_id        text,                                                  -- soft Control-DB principal ref; NULL for system_primary
    supervised_by_agent_id bigint      REFERENCES agents(id) ON DELETE RESTRICT,  -- nullable self-FK (supervision override)
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT agents_sp_unsupervised CHECK (
        agent_kind <> 'system_primary' OR supervised_by_agent_id IS NULL
    ),
    CONSTRAINT agents_sp_active CHECK (
        agent_kind <> 'system_primary' OR agent_status = 'active'
    )
);

-- System Primary singleton: at most one row may carry agent_kind='system_primary'.
CREATE UNIQUE INDEX IF NOT EXISTS ux_agents_single_system_primary
    ON agents ((true))
    WHERE agent_kind = 'system_primary';

-- System Primary immutability: block DELETE and any kind-flip away from system_primary (the two escapes
-- the CHECKs and partial index cannot stop). Idempotent: CREATE OR REPLACE + DROP TRIGGER IF EXISTS.
CREATE OR REPLACE FUNCTION agents_protect_system_primary() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' AND OLD.agent_kind = 'system_primary' THEN
        RAISE EXCEPTION 'system_primary agent cannot be deleted';
    END IF;

    IF TG_OP = 'UPDATE'
       AND OLD.agent_kind = 'system_primary'
       AND NEW.agent_kind <> 'system_primary' THEN
        RAISE EXCEPTION 'system_primary agent kind cannot be changed';
    END IF;

    RETURN COALESCE(NEW, OLD);
END;
$$;

DROP TRIGGER IF EXISTS trg_agents_protect_system_primary ON agents;

CREATE TRIGGER trg_agents_protect_system_primary
    BEFORE UPDATE OR DELETE ON agents
    FOR EACH ROW
    EXECUTE FUNCTION agents_protect_system_primary();
