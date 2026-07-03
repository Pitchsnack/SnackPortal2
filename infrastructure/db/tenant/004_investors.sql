-- SnackPortal2 — Tenant-DB investors (PRD 07C V5 §10.2; exec-auth V2 §12.4).
-- Tenant-local operational investor records, physically isolated per tenant database (no tenant_id
-- column; never Control-DB-resident). global_investor_id is a SOFT text reference to a Control-DB Global
-- Registry record (control_directory, directory='GlobalInvestorDirectory'); tenant copies are independent
-- ("Global Record != Tenant Record"); no cross-database FK.
--
-- Tag fields are jsonb arrays (never text[]). References only (D-14). Portable standard PostgreSQL, no
-- extensions. Idempotent + transaction-safe. Created, NOT applied.

CREATE TABLE IF NOT EXISTS investors (
    id                     bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    global_investor_id     text,                                     -- soft ref to Control global registry (no cross-DB FK)
    investor_name          text        NOT NULL,
    investor_type          text,
    email                  text,
    website_url            text,
    headquarters_country   text,
    headquarters_city      text,
    region                 text,
    investment_stage_focus jsonb       NOT NULL DEFAULT '[]'::jsonb,
    industry_focus         jsonb       NOT NULL DEFAULT '[]'::jsonb,
    short_description      text,
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now()
);
