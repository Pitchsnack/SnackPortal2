-- SnackPortal2 — Control-DB durable routing-audit store (IC-002 class 3 — Database Router edge; IC-001 Reference-Only; D-34-R2 O1; DBR-AR-2B).
-- The durable, append-only, reference-only table for the router-edge routing-decision events defined by
-- docs/runtime/dbr_ar_2_durable_routing_audit_contract.md (§7–§8) and IC-002 (3a): one row per completed or denied
-- Database Router route() decision (action ∈ Route / RouteControl / RouteDenied / IsolationAnomaly). It lives in the
-- CONTROL database (control-plane-owned), beside control_audit (002). The Control Plane remains the sole Control-DB
-- writer: rows arrive ONLY through the Control-Plane-owned store adapter (backend/control_plane/adapters/providers/
-- postgres_store.py PostgresRoutingAuditStore.append_routing_audit) behind the internal ingest edge. DISTINCT from
-- control_audit (002, provisioning lifecycle audit) and DISTINCT from tenant-data lineage (IC-004 / D-23, the
-- hash-chained provenance subsystem in the tenant DB). This is control-plane operational audit, NOT lineage: it
-- deliberately carries NO hash-chain column.
--
-- The columns mirror the Control-Plane-local RoutingAuditRecord (backend/control_plane/routing_audit.py) plus the two
-- store-assigned columns, matching the adapter:
--   INSERT INTO control_routing_audit (event_id, event_version, occurred_at, correlation_id, actor_ref, action,
--       outcome, source_service, source_version, request_ref, trace_ref, tenant_ref, resolved_tenant_ref,
--       public_code, error_class, association_store_ref, association_version, lane)   -- id / recorded_at NOT inserted
--   ON CONFLICT (event_id) DO NOTHING
-- `id` is DB-generated and is the durable total-ordering authority (reads ORDER BY id ASC — the B-7 precedent);
-- `recorded_at` is DB-assigned (DEFAULT now()); timestamps NEVER define total ordering (occurred_at is informational
-- only, router clock). `event_id` is the router-minted idempotency key: UNIQUE, duplicate insert is a no-op, and the
-- adapter exact-compares a conflicting replay and rejects same-ID/different-payload drift (contract §12). The action
-- and source_service CHECKs pin the CONTRACT-FROZEN router-edge vocabulary (IC-002 (3a): extension only by contract
-- amendment) — unlike 002, whose events.py vocabulary evolves application-side, this vocabulary is frozen contract
-- law, so the CHECK is a pin, not a parallel catalog. `trace_ref` is a reserved nullable column (contract §8): no
-- distributed-tracing machinery exists and it is NOT a DBR-AR-2B wire field.
--
-- References only (D-14; IC-001 Global Audit Representation Rule; contract §9): actor/tenant/correlation/association
-- references and event metadata only. NO passwords, NO DSNs / connection strings, NO raw secret values, NO JWT /
-- session / API keys, NO cloud credentials, NO PII, NO business payloads, NO tenant result data, NO request/response
-- bodies, NO database hostnames / physical database names / topology, NO serialized connection or routing objects.
-- association_store_ref + association_version are the D-14 reference pair — never a resolved value. No JSON/JSONB, no
-- arbitrary metadata column, no raw error text column, no foreign key to any tenant database, no cross-database
-- constraint, no retention duration (IC-001 platform retention policy governs; default retain-all; D-08 process).
-- Portable standard PostgreSQL (AWS RDS / Azure Database for PostgreSQL / Cloud SQL / self-hosted) — no extensions,
-- no provider-proprietary features. Idempotent and additive (no destructive migration).
--
-- Append-only by design: id is immutable; there is NO UPDATE path and NO DELETE path; corrections, failures, and
-- reversals are NEW rows. DB-level append-only enforcement is the companion 011_routing_audit_append_only.sql.
--
-- Created, NOT applied: this template is authored under PRD DBR-AR-2B (controlled non-production). Applying it to a
-- live Control database, and exercising the durable routing-audit store against a real cluster, is a SEPARATE later
-- gated phase (DBR-AR-2D live proof; governed ops apply only — never runtime DDL). It is deliberately NOT enrolled in
-- the B5-4 standing-topology apply order. The composed router default remains the in-memory sink (DBR-AR-2C owns
-- composition). Least-privilege writer-role DDL remains separately governed and is not delivered by DBR-AR-2B.

CREATE TABLE IF NOT EXISTS control_routing_audit (
    id                     bigint       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- DB-generated; adapter never inserts id; ORDER BY id ASC
    event_id               uuid         NOT NULL UNIQUE,  -- router-minted idempotency key; duplicate insert is a no-op
    event_version          integer      NOT NULL CONSTRAINT control_routing_audit_event_version_check CHECK (event_version > 0),
    occurred_at            timestamptz  NOT NULL,     -- router clock; informational only — never an ordering authority
    recorded_at            timestamptz  NOT NULL DEFAULT now(),  -- DB-assigned at insert; never caller-supplied
    correlation_id         text         NOT NULL,     -- request correlation reference
    actor_ref              text         NOT NULL,     -- authenticated subject reference (never a credential)
    action                 text         NOT NULL CONSTRAINT control_routing_audit_action_check
                                        CHECK (action IN ('Route', 'RouteControl', 'RouteDenied', 'IsolationAnomaly')),
    outcome                text         NOT NULL,     -- success / denied:<public_code> / anomaly:<code>
    source_service         text         NOT NULL CONSTRAINT control_routing_audit_source_service_check
                                        CHECK (source_service = 'database_router'),
    source_version         text         NOT NULL,     -- router build/version identifier
    request_ref            text,                      -- NULLABLE: RequestContext.request_id where present
    trace_ref              text,                      -- NULLABLE: reserved (contract §8); not a DBR-AR-2B wire field
    tenant_ref             text,                      -- NULLABLE: authenticated active tenant reference (null for CONTROL routes)
    resolved_tenant_ref    text,                      -- NULLABLE: tenant the router actually bound
    public_code            text,                      -- NULLABLE: canonical router-edge denial code; null on success
    error_class            text,                      -- NULLABLE: bounded internal vocabulary (contract §8)
    association_store_ref  text,                      -- NULLABLE: D-14 reference — never a resolved value
    association_version    text,                      -- NULLABLE: association reference version bound for this route
    lane                   text                       -- NULLABLE: interactive / bulk (D-13 capacity lane)
);
