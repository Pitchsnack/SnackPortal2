-- SnackPortal2 — Control-DB membership registry (D-04 1:N, D-32 roles; MCC Control DB Schema, exec-auth V2 §9.2).
-- The durable principal<->tenant membership store the wired control-plane adapter backend/control_plane/
-- adapters/providers/postgres_store.py ALREADY targets (put_membership / list_memberships): the adapter
-- INSERTs (principal_ref, tenant_id, role) with ON CONFLICT (principal_ref, tenant_id) DO UPDATE SET role and
-- SELECTs the same three columns back into MembershipRecord (backend/control_plane/records.py — eligibility,
-- not active selection). This DDL closes the wired-but-DDL-less gap; the adapter is NOT modified.
--
-- TYPING RULE (MCC exec-auth V2 §9.2): all columns text — the UNMODIFIED adapter binds Python str on write
-- (role as the Role enum .value string) and reconstructs Role(r[2]) on read (no SQL enum/CHECK; records.py is
-- the vocabulary authority). No id / IDENTITY column: (principal_ref, tenant_id) is the natural composite key.
-- NO cross-table FK to control_tenants (MCC exec-auth V2 §11): the in-memory store enforces no referential
-- integrity (store parity), and an FK would add insert-order coupling not needed to close the DDL gap.
--
-- References only (D-14): principal/tenant/role references — NO passwords, NO DSNs, NO raw secret values,
-- NO JWT / session / API keys, NO cloud credentials, NO PII. Portable standard PostgreSQL (AWS RDS / Azure
-- Database for PostgreSQL / Cloud SQL / self-hosted) — no extensions, no provider-proprietary features.
-- Idempotent and additive (no destructive migration).
--
-- Created, NOT applied: authored under MCC (controlled non-production). Applying it to a live Control
-- database is ops/IaC (07D) or the MCC live-PG proof harness (test_pg_control_schema_mcc.py) — not runtime.

CREATE TABLE IF NOT EXISTS control_memberships (
    principal_ref text NOT NULL,             -- principal reference (never a credential)
    tenant_id     text NOT NULL,             -- tenant reference; NO FK (store parity; MCC exec-auth V2 §11)
    role          text NOT NULL,             -- Role.value string (no SQL enum/CHECK; records.py is the vocabulary authority)
    PRIMARY KEY (principal_ref, tenant_id)   -- the adapter's ON CONFLICT target
);
