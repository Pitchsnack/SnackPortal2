-- SnackPortal2 — Tenant-DB deals (PRD 07C V5 §10.3; exec-auth V2 §12.5).
-- Tenant-local operational deal records. Deals live ONLY in the owning tenant's physical database and are
-- NEVER stored in the Control Global Registry (the registry holds global directory metadata, not
-- operational deals). Cross-tenant deal sharing (deal_shares / deal_share_targets / deal_introductions and
-- any Control shared-deal inbox) is OUT OF SCOPE until IC-007 lands — no sharing DDL exists here.
--
-- startup_id is a mandatory intra-tenant FK (a deal always attaches to a startup); investor_id is nullable
-- (a deal may be unmatched). deal_name defaults to '' — context-derived naming is a runtime concern, not
-- DDL. stage/status carry no CHECK vocabularies (runtime records-authority precedent). References only
-- (D-14). Portable standard PostgreSQL, no extensions. Idempotent + transaction-safe. Created, NOT applied.

CREATE TABLE IF NOT EXISTS deals (
    id          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    startup_id  bigint      NOT NULL REFERENCES startups(id) ON DELETE RESTRICT,
    investor_id bigint      REFERENCES investors(id) ON DELETE RESTRICT,   -- nullable: deal may be unmatched
    deal_name   text        NOT NULL DEFAULT '',
    stage       text,
    amount      numeric,
    currency    text,
    status      text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
