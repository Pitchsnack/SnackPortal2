-- SnackPortal2 — control_audit append-only enforcement (PRD 06 B-7; D-34 / IC-002 operational audit).
-- The DB itself rejects UPDATE / DELETE / TRUNCATE on control_audit, complementing the application-level append-only contract
-- (ControlPlaneAudit + ControlStore expose only append/list). Portable standard PostgreSQL (PL/pgSQL trigger; PG 11+) — no
-- vendor ledger / immutability feature. Mirrors the lineage append-only precedent (infrastructure/db/lineage/002_append_only.sql).
--
-- DISTINCT from IC-004 / D-23 lineage: lineage is a separate tenant-DB subsystem with its own cryptographic hash-chain; this is
-- control-plane operational audit and carries NO hash-chain. Any optional/forward hash policy for control_audit is a documented
-- forward-contract extension only (see docs/runtime/b7_provisioning_audit_schema.md) and is NOT lineage.
--
-- Created, NOT applied: authored under PRD 06 B-7 (controlled non-production). Applying it is a SEPARATE later gated phase (B-7A).

CREATE OR REPLACE FUNCTION control_audit_append_only() RETURNS trigger
    LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'control_audit is append-only: % rejected', TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS control_audit_no_mutation ON control_audit;
CREATE TRIGGER control_audit_no_mutation
    BEFORE UPDATE OR DELETE ON control_audit
    FOR EACH ROW EXECUTE FUNCTION control_audit_append_only();

DROP TRIGGER IF EXISTS control_audit_no_truncate ON control_audit;
CREATE TRIGGER control_audit_no_truncate
    BEFORE TRUNCATE ON control_audit
    FOR EACH STATEMENT EXECUTE FUNCTION control_audit_append_only();
