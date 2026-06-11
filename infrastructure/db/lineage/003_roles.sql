-- SnackPortal2 — lineage privilege separation (Build Phase 6; D-23 / PRD-P6-R2 A.2).
-- Least-privilege roles for defense-in-depth append-only. NOLOGIN group roles; the per-tenant
-- LOGIN credential is resolved from the D-14 secret store at connect time and is NEVER stored
-- in these files (no passwords here). Provisioning (D-15) grants the tenant login role
-- membership in lineage_writer. DELETE/TRUNCATE are granted to NO role — append-only is
-- absolute; the trigger (002) is the backstop even against a mis-granted role.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'lineage_writer') THEN
        CREATE ROLE lineage_writer NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'lineage_reader') THEN
        CREATE ROLE lineage_reader NOLOGIN;
    END IF;
END
$$;

-- Append-only writer: INSERT + SELECT on the chain; never UPDATE/DELETE/TRUNCATE.
GRANT SELECT, INSERT ON lineage          TO lineage_writer;
GRANT SELECT, INSERT ON lineage_segment  TO lineage_writer;
REVOKE UPDATE, DELETE, TRUNCATE ON lineage         FROM lineage_writer;
REVOKE UPDATE, DELETE, TRUNCATE ON lineage_segment FROM lineage_writer;

-- Read-only consumer (query/verify/graph/search).
GRANT SELECT ON lineage         TO lineage_reader;
GRANT SELECT ON lineage_segment TO lineage_reader;

-- Import bookkeeping is NOT append-only (upserted by the import coordinator).
GRANT SELECT, INSERT, UPDATE ON import_job, import_idempotency TO lineage_writer;
GRANT SELECT, INSERT          ON import_checkpoint              TO lineage_writer;
GRANT SELECT ON import_job, import_idempotency, import_checkpoint TO lineage_reader;
