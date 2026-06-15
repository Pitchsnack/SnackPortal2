-- SnackPortal2 — Physical Distinctness write-sentinel store (D15; D15-ARCH-SPEC-01 §6.5, §9.3 DV-C4).
-- A control-owned namespace into which the verifier writes a unique sentinel token and reads
-- it back, proving the provisioning process can write only to the intended database and that
-- the sentinel is visible only there. The `ns` (namespace) is a per-database VALUE; the table
-- holds NO business data, NO PII, and NO secrets (§6.5). This mirrors the idempotent DDL the
-- control-plane evidence provider applies at verification time. Portable standard PostgreSQL.

CREATE SCHEMA IF NOT EXISTS dv_sentinel;

CREATE TABLE IF NOT EXISTS dv_sentinel.marker (
    ns         text        PRIMARY KEY,
    token      text        NOT NULL,
    written_at timestamptz NOT NULL DEFAULT now()
);
