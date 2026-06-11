-- SnackPortal2 — lineage append-only enforcement (Build Phase 6; D-23 preventive layer 1).
-- Closes V-OBS-1: the DB itself rejects UPDATE/DELETE/TRUNCATE on lineage, complementing the
-- per-tenant cryptographic hash-chain (detective layer 2). Portable standard PostgreSQL
-- (PL/pgSQL trigger; PG 11+) — no vendor ledger/immutability feature (PRD-P6-R2 A).
--
-- The SOLE sanctioned removal (D-24 policy expiry) acts on the *referent* (tenant data / its
-- key) and appends a tombstone — it NEVER updates or deletes a lineage row — so a missing or
-- altered lineage row is ALWAYS tampering, never legitimate expiry (PRD-P6-R2 F).

CREATE OR REPLACE FUNCTION lineage_append_only() RETURNS trigger
    LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'lineage is append-only: % rejected', TG_OP
        USING ERRCODE = 'P6A01';   -- a fired trigger is an integrity anomaly (audited: LineageMutationRejected)
END;
$$;

DROP TRIGGER IF EXISTS lineage_no_mutation ON lineage;
CREATE TRIGGER lineage_no_mutation
    BEFORE UPDATE OR DELETE ON lineage
    FOR EACH ROW EXECUTE FUNCTION lineage_append_only();

DROP TRIGGER IF EXISTS lineage_no_truncate ON lineage;
CREATE TRIGGER lineage_no_truncate
    BEFORE TRUNCATE ON lineage
    FOR EACH STATEMENT EXECUTE FUNCTION lineage_append_only();
