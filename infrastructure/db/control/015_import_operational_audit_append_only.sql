-- SnackPortal2 — control_import_audit append-only enforcement (W1a; IC-003 "Import Audit").
-- The DB itself rejects UPDATE / DELETE / TRUNCATE on control_import_audit, complementing the application-level append-only
-- contract (ImportAuditStorePort exposes only append_import_audit — no read/update/delete/purge). Portable standard PostgreSQL
-- (PL/pgSQL trigger; PG 11+) — no vendor ledger / immutability feature. Mirrors the control_gateway_audit, control_routing_audit,
-- and control_audit append-only precedents (infrastructure/db/control/013_gateway_operational_audit_append_only.sql +
-- 011_routing_audit_append_only.sql + 003_provisioning_audit_append_only.sql).
--
-- DISTINCT from IC-004 / D-23 lineage: lineage is a separate tenant-DB subsystem with its own cryptographic hash-chain; this is
-- control-plane operational audit and carries NO hash-chain. No purge exception is added by W1a: the only sanctioned removal is
-- policy-driven expiry under the IC-001 retention policy (operator-authorized, audited), which is NOT implemented here.
--
-- Created, NOT applied: authored under PRD W1a (controlled non-production). Applying it is done ONLY by the MANUAL_ONLY
-- disposable proof (create -> prove -> drop; governed ops apply only — never runtime DDL). It is deliberately NOT enrolled in the
-- B5-4 standing-topology apply order.

CREATE OR REPLACE FUNCTION control_import_audit_append_only() RETURNS trigger
    LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'control_import_audit is append-only: % rejected', TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS control_import_audit_no_mutation ON control_import_audit;
CREATE TRIGGER control_import_audit_no_mutation
    BEFORE UPDATE OR DELETE ON control_import_audit
    FOR EACH ROW EXECUTE FUNCTION control_import_audit_append_only();

DROP TRIGGER IF EXISTS control_import_audit_no_truncate ON control_import_audit;
CREATE TRIGGER control_import_audit_no_truncate
    BEFORE TRUNCATE ON control_import_audit
    FOR EACH STATEMENT EXECUTE FUNCTION control_import_audit_append_only();
