-- SnackPortal2 — Control-DB tenant registry optimistic-concurrency version (PRD 07D-2e; IC-002; R-2c-LWW).
-- Adds the explicit lifecycle write-version column the CAS write path predicates on:
-- `compare_and_swap_tenant` UPDATEs `control_tenants` WHERE tenant_id AND version = <expected>,
-- incrementing `version` in place — so a lifecycle write based on a stale read matches ZERO rows
-- and is refused (typed store error) instead of silently overwriting a newer concurrent write
-- (e.g. a legitimate SuspendTenant committing inside a verify() window — the R-2c-LWW residual).
--
-- Explicit column by design (07D-2e D-2e-1): NOT the PostgreSQL `xmin` system column (provider-
-- coupled, wraps) and NOT a state-predicate-only CAS (fragile against same-state siblings).
-- bigint monotonic counter, DEFAULT 0 so every pre-existing row (and every INSERT that omits it)
-- starts at version 0 — matching the TenantRecord.version=0 default in records.py. This is the
-- TenantRecord's own write-version; it is UNRELATED to assoc_version (the SecretRef association
-- version, a text reference field).
--
-- References only (D-14): a counter — NO credentials, NO DSNs, NO PII, NO business payloads.
-- Portable standard PostgreSQL (AWS RDS / Azure Database for PostgreSQL / Cloud SQL /
-- self-hosted) — no extensions, no provider-proprietary features, no system-column dependency,
-- no cross-table FK. Idempotent and additive (IF NOT EXISTS; no destructive rewrite; 004 is NOT
-- amended). Created, NOT applied: applying it to a live Control database is the 07D-2e
-- live-PostgreSQL exercise (test_pg_control_schema_mcc.py / test_pg_control_store_runtime_wiring.py).

ALTER TABLE control_tenants
    ADD COLUMN IF NOT EXISTS version bigint NOT NULL DEFAULT 0;
