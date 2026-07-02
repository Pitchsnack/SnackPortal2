-- SnackPortal2 — Tenant-DB startups (PRD 07C V5 §10.1; exec-auth V2 §12.3).
-- Tenant-local operational startup records. Each tenant's startups live ONLY in that tenant's physical
-- database — never in a shared DB (no tenant_id column anywhere in this family) and never in the Control
-- DB. global_startup_id is a SOFT text reference to a Control-DB Global Registry record
-- (control_directory, directory='GlobalStartupDirectory'); tenant records are independent copies —
-- "Global Record != Tenant Record" — and tenant edits never mutate Control directory rows. No
-- cross-database FK is possible or allowed.
--
-- Tag fields are jsonb arrays (never text[]) per 07C V5 §8.1. References only (D-14). Portable standard
-- PostgreSQL, no extensions. Idempotent + transaction-safe. Created, NOT applied.

CREATE TABLE IF NOT EXISTS startups (
    id                   bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    global_startup_id    text,                                       -- soft ref to Control global registry (no cross-DB FK)
    company_name         text        NOT NULL,
    company_type         text,
    email                text,
    company_url          text,
    headquarters_country text,
    headquarters_city    text,
    region               text,
    year_founded         integer,
    industry             text,
    investment_stage     text,
    short_description    text,
    product_overview     text,
    product_service_tags jsonb       NOT NULL DEFAULT '[]'::jsonb,
    market_tags          jsonb       NOT NULL DEFAULT '[]'::jsonb,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now()
);
