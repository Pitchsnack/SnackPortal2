-- SnackPortal2 — Tenant-DB ownership tables (PRD 07C V5 §6.4/§11; exec-auth V2 §12.6). Option A cardinality.
--
-- OWNERSHIP SEMANTICS (07C V5 §6.4 — the section 07B.1 V2 cites):
--   * PHYSICAL INVARIANT: at most one owning HUMAN Agent per entity — {entity}_ownership has PRIMARY KEY
--     ({entity}_id). Runtime entity-creation workflows later make ownership exactly-one.
--   * UNASSIGNED = ROW ABSENCE: an entity with no {entity}_ownership row is UNASSIGNED and belongs
--     conceptually to the System Primary bucket. System Primary NEVER appears as agent_id in ownership
--     rows — the bucket is represented by row absence, not by rows pointing at System Primary.
--   * CLAIM = INSERT (first-writer-wins): the first successful INSERT for a given {entity}_id wins; a
--     concurrent second claim fails on the primary key. REASSIGNMENT = a later governed UPDATE path through
--     API Gateway / authorization logic — not a schema loophole, not part of 07C.
--   * NO reservation table, NO claim-lock table, NO queue-manager, NO background claim worker.
--   * AI ownership: zero or more DISTINCT AI Agents per entity — {entity}_ai_ownership has composite
--     PRIMARY KEY ({entity}_id, ai_agent_id); a duplicate same-AI pair fails.
--   * Fresh bootstrap (07C V5 §11.3): exactly one system_primary Agent (seeded by 07B.1), zero human
--     Agents, zero AI Agents, zero ownership rows.
--
-- All FKs are intra-tenant (same physical database), explicit ON DELETE RESTRICT. References only (D-14).
-- Portable standard PostgreSQL, no extensions. Idempotent + transaction-safe. Created, NOT applied.

-- ---- human ownership: at most one owning human Agent per entity (PK = entity id) ------------------------

CREATE TABLE IF NOT EXISTS startup_ownership (
    startup_id  bigint      PRIMARY KEY REFERENCES startups(id) ON DELETE RESTRICT,
    agent_id    bigint      NOT NULL REFERENCES agents(id) ON DELETE RESTRICT,
    assigned_at timestamptz NOT NULL DEFAULT now(),
    assigned_by text
);

CREATE TABLE IF NOT EXISTS investor_ownership (
    investor_id bigint      PRIMARY KEY REFERENCES investors(id) ON DELETE RESTRICT,
    agent_id    bigint      NOT NULL REFERENCES agents(id) ON DELETE RESTRICT,
    assigned_at timestamptz NOT NULL DEFAULT now(),
    assigned_by text
);

CREATE TABLE IF NOT EXISTS deal_ownership (
    deal_id     bigint      PRIMARY KEY REFERENCES deals(id) ON DELETE RESTRICT,
    agent_id    bigint      NOT NULL REFERENCES agents(id) ON DELETE RESTRICT,
    assigned_at timestamptz NOT NULL DEFAULT now(),
    assigned_by text
);

-- ---- AI ownership: zero-or-more distinct AI Agents per entity (composite PK) ----------------------------

CREATE TABLE IF NOT EXISTS startup_ai_ownership (
    startup_id  bigint      NOT NULL REFERENCES startups(id) ON DELETE RESTRICT,
    ai_agent_id bigint      NOT NULL REFERENCES ai_agents(id) ON DELETE RESTRICT,
    role        text,
    assigned_at timestamptz NOT NULL DEFAULT now(),
    assigned_by text,
    PRIMARY KEY (startup_id, ai_agent_id)
);

CREATE TABLE IF NOT EXISTS investor_ai_ownership (
    investor_id bigint      NOT NULL REFERENCES investors(id) ON DELETE RESTRICT,
    ai_agent_id bigint      NOT NULL REFERENCES ai_agents(id) ON DELETE RESTRICT,
    role        text,
    assigned_at timestamptz NOT NULL DEFAULT now(),
    assigned_by text,
    PRIMARY KEY (investor_id, ai_agent_id)
);

CREATE TABLE IF NOT EXISTS deal_ai_ownership (
    deal_id     bigint      NOT NULL REFERENCES deals(id) ON DELETE RESTRICT,
    ai_agent_id bigint      NOT NULL REFERENCES ai_agents(id) ON DELETE RESTRICT,
    role        text,
    assigned_at timestamptz NOT NULL DEFAULT now(),
    assigned_by text,
    PRIMARY KEY (deal_id, ai_agent_id)
);
