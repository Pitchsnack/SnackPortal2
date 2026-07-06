-- SnackPortal2 — Control-DB Physical Distinctness fingerprint uniqueness (PRD 07D-2c; D15-ARCH-SPEC-01 §6.1; IC-010 §P).
-- Storage-layer serialization of the D15 readiness gate's tenant-vs-tenant fingerprint rule: two
-- DISTINCT tenants MUST NOT share the physical-database fingerprint
-- (system_identifier, database_identity). The gate's application-level sequence — inventory read
-- (CHECK, `evidence_excluding`) then evidence write (ACT, `record_evidence`) — is not atomic, so
-- without this constraint two concurrent onboardings (or a reassociate racing an onboard) against
-- the same physical database could each pass the check before either records, leaving two tenants
-- Ready on ONE physical database. This unique index makes the ACT step the atomic arbiter at the
-- Control database: the losing writer surfaces SQLSTATE 23505, which the durable ledger adapter
-- maps onto the typed collision refusal the gate routes to the ALREADY-CONTRACTED anomaly path
-- (IC-010 §P; existing reason `tenant_collision`; IC-002 isolation-anomaly auto-quarantine).
-- Zero new events; zero contract changes.
--
-- Same-tenant re-record is unaffected: the adapter upsert resolves same-tenant writes via the
-- (tenant_id) conflict arbiter, and updating a tenant's own row never collides with itself.
--
-- FAIL-CLOSED NOTE: if a pre-existing live inventory already holds duplicate fingerprints across
-- distinct tenants, creating this index FAILS. That failure is itself evidence of an isolation
-- anomaly and requires operator investigation before this constraint can be applied — never
-- delete or rewrite ledger rows to force creation (evidence is preserved, fail closed).
--
-- References only (D-14; IC-001 Global Audit Representation Rule): the indexed columns are the
-- existing reference-only identity/comparison keys — no credentials, no DSNs, no PII. Portable
-- standard PostgreSQL (AWS RDS / Azure Database for PostgreSQL / Cloud SQL / self-hosted) — no
-- extensions, no provider-proprietary features. Idempotent and additive (IF NOT EXISTS; no
-- destructive migration; 001 is NOT amended). Created, NOT applied: applying it to a live
-- Control database is the 07D-2c live-PostgreSQL exercise (test_pg_distinctness_ledger.py).

CREATE UNIQUE INDEX IF NOT EXISTS control_distinctness_fingerprint_unique
    ON control_distinctness_ledger (system_identifier, database_identity);
