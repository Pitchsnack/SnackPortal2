-- SnackPortal2 — tenant-database bootstrap (D15; D15-ARCH-SPEC-01 §8 Step 2; IC-002 / D-17).
-- Applied to a freshly provisioned, physically distinct tenant database. Establishes the
-- application schema-version marker that the control-plane verification probe reads
-- (SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1). Portable standard
-- PostgreSQL; no extensions; no secret values. Idempotent.

CREATE TABLE IF NOT EXISTS schema_version (
    version    text        NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);

-- Seed the initial supported version once (control plane gates readiness on the supported
-- range, D-17). Re-running is a no-op.
INSERT INTO schema_version (version)
SELECT '1'
WHERE NOT EXISTS (SELECT 1 FROM schema_version);
