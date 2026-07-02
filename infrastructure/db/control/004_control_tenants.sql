-- SnackPortal2 — Control-DB tenant registry (IC-002 Tenant Descriptor; MCC Control DB Schema, exec-auth V2 §9.1).
-- The durable registry of tenants the wired control-plane adapter backend/control_plane/adapters/providers/
-- postgres_store.py ALREADY targets (put_tenant / get_tenant / list_tenant_ids): the adapter INSERTs the nine
-- wired columns with ON CONFLICT (tenant_id) DO UPDATE and SELECTs them back into the frozen TenantRecord
-- (backend/control_plane/records.py). This DDL closes the wired-but-DDL-less gap; the adapter is NOT modified.
--
-- TYPING RULE (MCC exec-auth V2 §9.1; the PRD 06 B-7B str<->datetime lesson): every wired column is text
-- because the UNMODIFIED adapter binds Python str on write and reads values straight back into str-typed
-- TenantRecord fields with NO normalization on this path. created_at / updated_at are text, NOT timestamptz
-- (timestamptz would return datetime on SELECT and break the str contract); expected_schema_version is text,
-- NOT integer (non-numeric versions like 'v1' must round-trip); lifecycle_state stores the
-- TenantLifecycleState enum .value string; assoc_store_ref / assoc_version are the two reference columns the
-- adapter derives from TenantRecord.database_association_ref (SecretRef {store_ref, version} — D-14
-- references only, never a credential). No id / IDENTITY column: tenant_id is the natural key.
--
-- tenant_type (MCC Option C): discriminates 'customer' tenants from the single 'control_internal' tenant
-- (Control's own internal operating tenant/workspace identity anchor — D-33). DEFAULT 'customer' keeps the
-- UNMODIFIED adapter working: its INSERT omits tenant_type (default applies) and its SELECT never reads it.
-- The partial unique index enforces AT MOST ONE control_internal row (same partial-unique singleton idiom the
-- later 07C V4 System Primary uses). Runtime tenant_type plumbing is DEFERRED (not MCC); access semantics for
-- the Control Internal Tenant are a separate future PRD (MCC exec-auth V2 §10). Control Global Registry !=
-- Control Internal Tenant (DRIFT-05): no operational records live here — this is lifecycle metadata only.
--
-- References only (D-14): identity/lifecycle references — NO passwords, NO DSNs / connection strings, NO raw
-- secret values, NO JWT / session / API keys, NO cloud credentials, NO PII, NO tenant business payloads.
-- Portable standard PostgreSQL (AWS RDS / Azure Database for PostgreSQL / Cloud SQL / self-hosted) — no
-- extensions, no provider-proprietary features. Idempotent and additive (no destructive migration); no
-- cross-table FK (MCC exec-auth V2 §11: in-memory/postgres store parity; no insert-order coupling).
--
-- Created, NOT applied: authored under MCC (controlled non-production). Applying it to a live Control
-- database is ops/IaC (07D) or the MCC live-PG proof harness (test_pg_control_schema_mcc.py) — not runtime.

CREATE TABLE IF NOT EXISTS control_tenants (
    tenant_id               text NOT NULL PRIMARY KEY,   -- natural key; the adapter's ON CONFLICT target
    organization_ref        text NOT NULL,               -- organization reference (never a credential)
    lifecycle_state         text NOT NULL,               -- TenantLifecycleState.value string (no SQL enum/CHECK; records.py is the vocabulary authority)
    expected_schema_version text NOT NULL,               -- str in TenantRecord; may be non-numeric — text, NOT integer
    assoc_store_ref         text NOT NULL,               -- SecretRef.store_ref (reference key only; never the secret value)
    assoc_version           text NOT NULL,               -- SecretRef.version
    federation_config_ref   text NOT NULL,               -- federation config reference (see 006_control_federation.sql)
    created_at              text NOT NULL,               -- ISO-8601 str; text NOT timestamptz (unmodified-adapter str round-trip)
    updated_at              text NOT NULL,               -- ISO-8601 str; text NOT timestamptz
    tenant_type             text NOT NULL DEFAULT 'customer'
        CONSTRAINT control_tenants_tenant_type_check
        CHECK (tenant_type IN ('customer', 'control_internal'))
);

-- Control Internal Tenant singleton: at most one row may carry tenant_type='control_internal'.
CREATE UNIQUE INDEX IF NOT EXISTS ux_control_tenants_single_control_internal
    ON control_tenants ((true))
    WHERE tenant_type = 'control_internal';
