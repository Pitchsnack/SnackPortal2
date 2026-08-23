-- SnackPortal2 — Migration M-1 (part 2): control_ingress_audit is append-only.
--
-- Same rule-based idiom as the legacy 003 / 011 / 013 append-only migrations, so the operational behaviour
-- an operator already knows is the behaviour they get. An audit trail that can be updated or deleted is not
-- an audit trail; enforcing that in the database rather than in application code means it holds against
-- every writer, including a future one nobody has written yet.
--
-- Idempotent and additive. Created, NOT applied.

CREATE OR REPLACE FUNCTION control_ingress_audit_append_only() RETURNS trigger
    LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'control_ingress_audit is append-only: % rejected', TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS control_ingress_audit_no_mutation ON control_ingress_audit;
CREATE TRIGGER control_ingress_audit_no_mutation
    BEFORE UPDATE OR DELETE ON control_ingress_audit
    FOR EACH ROW EXECUTE FUNCTION control_ingress_audit_append_only();

DROP TRIGGER IF EXISTS control_ingress_audit_no_truncate ON control_ingress_audit;
CREATE TRIGGER control_ingress_audit_no_truncate
    BEFORE TRUNCATE ON control_ingress_audit
    FOR EACH STATEMENT EXECUTE FUNCTION control_ingress_audit_append_only();
