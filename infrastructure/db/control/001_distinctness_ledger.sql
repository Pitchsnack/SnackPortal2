-- SnackPortal2 — Control-DB Physical Distinctness Ledger (D15; D15-ARCH-SPEC-01 §9.2 input 8; IC-010 §P; PRD 06 B-2).
-- The durable, reference-only inventory of per-tenant Physical Distinctness evidence that the
-- D15 readiness gate consults to detect tenant-vs-tenant collisions before a tenant becomes
-- routable. It lives in the CONTROL database (control-plane-owned), alongside the other
-- `control_*` tables. One row per tenant: the LATEST evidence — upserted when verification
-- passes (VERIFIED), deleted on fail / suspend / decommission. It is an INVENTORY, not an
-- audit-history trail; the provisioning audit sink is a separate concern (deferred).
--
-- The columns mirror the control-plane `DistinctnessEvidence` (backend/control_plane/
-- distinctness.py) — its seven reference-only fields plus `tenant_id` (the inventory key) and
-- `recorded_at` (freshness; set by the durable adapter at record time).
--
-- References only (D-14; IC-001 Global Audit Representation Rule): identity/comparison keys and
-- a non-sensitive secret-store REFERENCE key only. This table holds NO passwords, NO DSNs /
-- connection strings, NO raw secret values, NO JWT / session / API keys, NO cloud credentials,
-- NO PII, and NO tenant business payloads. Portable standard PostgreSQL (AWS RDS / Azure
-- Database for PostgreSQL / Cloud SQL / self-hosted) — no extensions, no provider-proprietary
-- features. Idempotent and additive (no destructive migration).
--
-- Created, NOT applied: this template is authored under PRD 06 B-2 (controlled non-production).
-- Applying it to a live Control database, and exercising the durable ledger against it, is the
-- live-PostgreSQL exercise (B-4) — not B-2.

CREATE TABLE IF NOT EXISTS control_distinctness_ledger (
    tenant_id          text        PRIMARY KEY,          -- inventory key (one latest row per tenant)
    system_identifier  text        NOT NULL,             -- DV-C1 — PostgreSQL cluster system identifier
    database_identity  text        NOT NULL,             -- DV-C2 — database-level identity (e.g. "datname:oid")
    observed_target    text        NOT NULL,             -- DV-C3/DV-C7 — provisioning target the connection reached
    secret_ref_key     text        NOT NULL,             -- non-sensitive secret-store reference key (store_ref); never the value
    sentinel_namespace text        NOT NULL,             -- DV-C4 — control-owned sentinel namespace
    sentinel_token     text,                             -- the unique write-sentinel proven (NULL if not proven)
    sentinel_written   boolean     NOT NULL,             -- True iff the sentinel was written + read back
    recorded_at        timestamptz NOT NULL DEFAULT now()  -- freshness; the adapter sets this at record time (UTC)
);
