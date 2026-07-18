-- SnackPortal2 — Tenant-DB startups.global_startup_id uniqueness (W1a; PRD 07C V5 §10.1 family).
-- A per-tenant UNIQUE index on startups.global_startup_id so the W1a composed-core import copy is a clean
-- idempotent upsert: INSERT ... ON CONFLICT ("global_startup_id") DO UPDATE (the import unit of work needs a
-- unique arbiter to de-duplicate re-imports/retries into a single tenant copy). global_startup_id stays a
-- SOFT text reference to a Control-DB Global Registry record (no cross-database FK; "Global Record != Tenant
-- Record"); tenant records remain independent copies.
--
-- PLAIN index (no WHERE predicate): a partial index would not satisfy ON CONFLICT column-arbiter inference at
-- runtime. NOT CONCURRENT: the tenant schema is applied inside the single atomic Step-2b transaction (CREATE
-- INDEX CONCURRENTLY cannot run in a transaction). NULLS DISTINCT (the PostgreSQL default) is preserved so the
-- nullable column stays lawful for any legacy row that carries no reference; imported rows always carry the
-- global_startup_id reference. No tenant_id column (tenancy is physical — one DB per tenant). Idempotent
-- (IF NOT EXISTS) + transaction-safe. Portable standard PostgreSQL, no extensions. Created, NOT applied.

CREATE UNIQUE INDEX IF NOT EXISTS startups_global_startup_id_key ON startups (global_startup_id);
