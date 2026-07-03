-- SnackPortal2 — Tenant-DB AI Agents (PRD 07C V5 §9.4; exec-auth V2 §12.2).
-- Tenant-local operational AI actors. ai_agents lives in EACH physical tenant database; it is NOT a Control
-- global registry table, is NOT seeded by 07B.1, and no AI Agent is required on fresh tenant bootstrap.
-- System Primary has no required AI Agent relationship in 07C / 07B.1.
--
-- supervising_agent_id is a MANDATORY intra-tenant FK to agents(id) (every AI Agent is supervised); it is
-- creation-workflow-supplied (deliberately NOT defaulted — 07C V5 §9.4). Whether the supervisor is a human
-- Agent is a runtime authorization concern, not a DDL concern. parent_ai_agent_id / hierarchy_depth defer
-- to 07C.2 (Roles, Permissions, Portfolio & AI Workflow).
--
-- References only (D-14): no secrets/DSNs/PII. Portable standard PostgreSQL, no extensions. Idempotent +
-- transaction-safe for the atomic Step-2b apply. Created, NOT applied (07B.1 sequencing / 07C harness only).

CREATE TABLE IF NOT EXISTS ai_agents (
    id                   bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ai_agent_name        text        NOT NULL DEFAULT '',
    ai_agent_type        text        NOT NULL DEFAULT 'general',
    agent_status         text        NOT NULL DEFAULT 'active'
                             CONSTRAINT ai_agents_status_check
                             CHECK (agent_status IN ('active', 'inactive')),
    supervising_agent_id bigint      NOT NULL REFERENCES agents(id) ON DELETE RESTRICT,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now()
);
