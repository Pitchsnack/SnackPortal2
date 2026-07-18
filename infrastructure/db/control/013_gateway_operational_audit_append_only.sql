-- SnackPortal2 — control_gateway_audit append-only enforcement (Gateway Audit V1a; IC-002 class 3b — API Gateway edge).
-- The DB itself rejects UPDATE / DELETE / TRUNCATE on control_gateway_audit, complementing the application-level append-only
-- contract (GatewayAuditStorePort exposes only append_gateway_audit — no read/update/delete/purge). Portable standard
-- PostgreSQL (PL/pgSQL trigger; PG 11+) — no vendor ledger / immutability feature. Mirrors the control_routing_audit and
-- control_audit append-only precedents (infrastructure/db/control/011_routing_audit_append_only.sql +
-- 003_provisioning_audit_append_only.sql).
--
-- DISTINCT from IC-004 / D-23 lineage: lineage is a separate tenant-DB subsystem with its own cryptographic hash-chain; this is
-- control-plane operational audit and carries NO hash-chain. No purge exception is added by V1a: the only sanctioned removal is
-- policy-driven expiry under the IC-001 retention policy (operator-authorized, audited), which is NOT implemented here.
--
-- Created, NOT applied: authored under PRD Gateway Operational Audit Persistence V1a (controlled non-production). Applying it is
-- done ONLY by the MANUAL_ONLY disposable proof (create -> prove -> drop; governed ops apply only — never runtime DDL). It is
-- deliberately NOT enrolled in the B5-4 standing-topology apply order.

CREATE OR REPLACE FUNCTION control_gateway_audit_append_only() RETURNS trigger
    LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'control_gateway_audit is append-only: % rejected', TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS control_gateway_audit_no_mutation ON control_gateway_audit;
CREATE TRIGGER control_gateway_audit_no_mutation
    BEFORE UPDATE OR DELETE ON control_gateway_audit
    FOR EACH ROW EXECUTE FUNCTION control_gateway_audit_append_only();

DROP TRIGGER IF EXISTS control_gateway_audit_no_truncate ON control_gateway_audit;
CREATE TRIGGER control_gateway_audit_no_truncate
    BEFORE TRUNCATE ON control_gateway_audit
    FOR EACH STATEMENT EXECUTE FUNCTION control_gateway_audit_append_only();
