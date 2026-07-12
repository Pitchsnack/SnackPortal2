-- SnackPortal2 — control_routing_audit append-only enforcement (DBR-AR-2B; IC-002 class 3 — Database Router edge).
-- The DB itself rejects UPDATE / DELETE / TRUNCATE on control_routing_audit, complementing the application-level
-- append-only contract (RoutingAuditStorePort exposes only append_routing_audit — no read/update/delete/purge).
-- Portable standard PostgreSQL (PL/pgSQL trigger; PG 11+) — no vendor ledger / immutability feature. Mirrors the
-- control_audit append-only precedent (infrastructure/db/control/003_provisioning_audit_append_only.sql).
--
-- DISTINCT from IC-004 / D-23 lineage: lineage is a separate tenant-DB subsystem with its own cryptographic
-- hash-chain; this is control-plane operational audit and carries NO hash-chain (contract §13 — any hash policy is a
-- documented forward-contract extension only and is NOT lineage). No purge exception is added by DBR-AR-2B: the only
-- sanctioned removal is policy-driven expiry under the IC-001 retention policy (operator-authorized, audited), which
-- is NOT implemented here.
--
-- Created, NOT applied: authored under PRD DBR-AR-2B (controlled non-production). Applying it is a SEPARATE later
-- gated phase (DBR-AR-2D live proof; governed ops apply only — never runtime DDL). It is deliberately NOT enrolled in
-- the B5-4 standing-topology apply order.

CREATE OR REPLACE FUNCTION control_routing_audit_append_only() RETURNS trigger
    LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'control_routing_audit is append-only: % rejected', TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS control_routing_audit_no_mutation ON control_routing_audit;
CREATE TRIGGER control_routing_audit_no_mutation
    BEFORE UPDATE OR DELETE ON control_routing_audit
    FOR EACH ROW EXECUTE FUNCTION control_routing_audit_append_only();

DROP TRIGGER IF EXISTS control_routing_audit_no_truncate ON control_routing_audit;
CREATE TRIGGER control_routing_audit_no_truncate
    BEFORE TRUNCATE ON control_routing_audit
    FOR EACH STATEMENT EXECUTE FUNCTION control_routing_audit_append_only();
