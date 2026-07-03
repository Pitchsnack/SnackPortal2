-- SnackPortal2 — Tenant-DB contact/link tables (PRD 07C V5 §12; exec-auth V2 §12.7).
-- CONTACT-record tables, deliberately NOT user tables: there is no tenant-local users table; authenticated
-- portal-user linking is future work. startup_users / investor_users MUST NOT exist (07C V5 AC — the
-- earlier *_users naming was rejected to avoid confusion with Control-DB principals). Contact records are
-- plain tenant-local business contacts (name / email / role title).
--
-- startup_investors is the tenant-local startup<->investor relationship link (composite PK). These tables
-- are tenant-local only: they create no cross-tenant sharing, no investor/startup portal access behavior,
-- and do not replace API Gateway authorization.
--
-- All FKs intra-tenant, ON DELETE RESTRICT. References only (D-14; contact emails are business contact
-- data, not credentials). Portable standard PostgreSQL, no extensions. Idempotent + transaction-safe.
-- Created, NOT applied.

CREATE TABLE IF NOT EXISTS startup_contacts (
    id           bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    startup_id   bigint      NOT NULL REFERENCES startups(id) ON DELETE RESTRICT,
    contact_name text        NOT NULL,
    email        text,
    role_title   text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS investor_contacts (
    id           bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    investor_id  bigint      NOT NULL REFERENCES investors(id) ON DELETE RESTRICT,
    contact_name text        NOT NULL,
    email        text,
    role_title   text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS startup_investors (
    startup_id   bigint      NOT NULL REFERENCES startups(id) ON DELETE RESTRICT,
    investor_id  bigint      NOT NULL REFERENCES investors(id) ON DELETE RESTRICT,
    relationship text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (startup_id, investor_id)
);
