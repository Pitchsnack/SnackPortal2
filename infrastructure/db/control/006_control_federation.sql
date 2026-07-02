-- SnackPortal2 — Control-DB per-tenant federation config (IC-002 Tenant<->Org Mapping; IC-005; MCC Control DB
-- Schema, exec-auth V2 §9.3). The durable per-tenant OIDC federation-config store the wired control-plane
-- adapter backend/control_plane/adapters/providers/postgres_store.py ALREADY targets (put_federation /
-- get_federation): the adapter INSERTs the five wired columns with ON CONFLICT (tenant_id) DO UPDATE and
-- SELECTs them back into FederationConfig (backend/control_plane/records.py — storage only; jwks by
-- reference). This DDL closes the wired-but-DDL-less gap; the adapter is NOT modified.
--
-- TYPING RULE (MCC exec-auth V2 §9.3): all columns text — the UNMODIFIED adapter binds and reads Python str
-- with no normalization. No id / IDENTITY column: tenant_id is the natural key. NO cross-table FK to
-- control_tenants (MCC exec-auth V2 §11: in-memory/postgres store parity; no insert-order coupling).
--
-- References only (D-14): issuer/audience identifiers and a jwks REFERENCE key only — NO jwks material,
-- NO passwords, NO DSNs, NO raw secret values, NO JWT / session / API keys, NO cloud credentials, NO PII.
-- Portable standard PostgreSQL (AWS RDS / Azure Database for PostgreSQL / Cloud SQL / self-hosted) — no
-- extensions, no provider-proprietary features. Idempotent and additive (no destructive migration).
--
-- Created, NOT applied: authored under MCC (controlled non-production). Applying it to a live Control
-- database is ops/IaC (07D) or the MCC live-PG proof harness (test_pg_control_schema_mcc.py) — not runtime.

CREATE TABLE IF NOT EXISTS control_federation (
    tenant_id            text NOT NULL PRIMARY KEY,  -- natural key; the adapter's ON CONFLICT target; NO FK (V2 §11)
    oidc_issuer          text NOT NULL,              -- OIDC issuer identifier
    oidc_audience        text NOT NULL,              -- OIDC audience identifier
    jwks_ref             text NOT NULL,              -- jwks by REFERENCE only (never key material)
    claim_to_tenant_rule text NOT NULL               -- claim->tenant mapping rule reference
);
