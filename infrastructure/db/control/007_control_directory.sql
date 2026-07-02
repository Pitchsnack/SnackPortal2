-- SnackPortal2 — Control-DB global discovery directory (D-31; IC-001 Global Startup Contract; MCC Control DB
-- Schema, exec-auth V2 §9.4). The durable Global Discovery Platform store the wired control-plane adapter
-- backend/control_plane/adapters/providers/postgres_store.py ALREADY targets (put_directory_record /
-- get_directory_record / list_directory): the adapter keys rows by (directory, record_id) with ON CONFLICT
-- DO UPDATE and reads them back into DirectoryRecord (backend/control_plane/records.py — "Global Record !=
-- Tenant Record"). `directory` holds the DirectoryKind enum .value string ('GlobalStartupDirectory' /
-- 'GlobalInvestorDirectory' — no SQL enum/CHECK; records.py is the vocabulary authority). This is the
-- contract-neutral, already-wired Global Registry representation for the MVP: dedicated global_startups /
-- global_investors tables are DEFERRED to a later named Control Registry PRD gated on the Global Investor
-- Contract (MCC exec-auth V2 change log; MCC V2 §10). This DDL closes the wired-but-DDL-less gap; the
-- adapter is NOT modified.
--
-- TYPING RULE (MCC exec-auth V2 §9.4): directory / record_id / display_name are text; attributes is plain
-- jsonb (no JSONB CHECK) — non-sensitive global reference data (Dict[str, str] in DirectoryRecord). No id /
-- IDENTITY column: (directory, record_id) is the natural composite key. NO cross-table FK (V2 §11).
--
-- KNOWN RUNTIME DEFECT (documented, NOT fixed here — MCC-AR-1): the wired put_directory_record binds a plain
-- Python dict for `attributes`; psycopg 3 has no default dumper for dict, so the WRITE raises at the driver
-- layer before any SQL reaches PostgreSQL. This is a pre-existing adapter defect independent of this DDL
-- (reads are unaffected: psycopg 3 natively loads jsonb -> dict). The fix (wrap with psycopg Jsonb(...)) is
-- follow-up "MCC-AR-1 — PostgresControlStore Directory JSONB Adapter Fix", deferred with the tenant_type
-- runtime plumbing; MCC proves this DDL by direct-SQL seed + unmodified-adapter READ, plus an
-- expected-failure probe in test_pg_control_schema_mcc.py.
--
-- References only (D-14; IC-001 Global Audit Representation Rule; D-35-R2 Tenant Anonymity): non-sensitive
-- global reference data only — NO tenant_id / tenant_name / tenant_reference columns, NO passwords, NO DSNs,
-- NO raw secret values, NO JWT / session / API keys, NO cloud credentials, NO PII. Portable standard
-- PostgreSQL (AWS RDS / Azure Database for PostgreSQL / Cloud SQL / self-hosted) — no extensions, no
-- provider-proprietary features. Idempotent and additive (no destructive migration).
--
-- Created, NOT applied: authored under MCC (controlled non-production). Applying it to a live Control
-- database is ops/IaC (07D) or the MCC live-PG proof harness (test_pg_control_schema_mcc.py) — not runtime.

CREATE TABLE IF NOT EXISTS control_directory (
    directory    text  NOT NULL,                        -- DirectoryKind.value string (no SQL enum/CHECK; records.py is the vocabulary authority)
    record_id    text  NOT NULL,                        -- stable identifier (future IC-003 import / IC-004 lineage source_ref)
    display_name text  NOT NULL,                        -- non-sensitive display name
    attributes   jsonb NOT NULL DEFAULT '{}'::jsonb,    -- non-sensitive global reference data (plain jsonb; no CHECK)
    PRIMARY KEY (directory, record_id)                  -- the adapter's ON CONFLICT target
);
