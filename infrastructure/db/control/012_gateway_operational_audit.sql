-- SnackPortal2 — Control-DB durable Gateway operational-audit store (IC-002 class 3b — API Gateway edge; IC-001 Reference-Only; Gateway Audit V1a + D-42 CLM Stage B).
-- The durable, append-only, reference-only table for the API-Gateway-edge operational-audit events defined by IC-010 §J,
-- IC-002 (3b), and the IC-010 CLM section (D-42): one row per emitted Gateway-edge event. V1a wired ONLY the
-- workspace_memberships_read success-access event (the self-scoped MembershipsForPrincipal success, IC-002 class 3b); the
-- D-42 CLM Stage B slice wires the IC-010 CLM audit evidence set — the two CLM tenant Startup success-access events
-- (tenant_startup_read / tenant_startup_update, with the nullable record_ref reference column) plus the EXISTING class-3
-- RouteDenied denial record. The table remains shaped for the WHOLE Gateway-edge class so the remaining denial/anomaly
-- events (CarrierMismatch / CarrierOnControlAnomaly / IsolationAnomaly) become a later
-- additive sibling to the SAME sink without a schema change. It lives in the CONTROL database (control-plane-owned), beside
-- control_audit (002) and control_routing_audit (010). The Control Plane remains the sole Control-DB writer: rows arrive ONLY
-- through the Control-Plane-owned store adapter (backend/control_plane/adapters/providers/postgres_store.py
-- PostgresGatewayAuditStore.append_gateway_audit) behind the internal loopback ingest edge. DISTINCT from control_audit (002,
-- provisioning lifecycle audit), DISTINCT from control_routing_audit (010, the Database Router edge), and DISTINCT from
-- tenant-data lineage (IC-004 / D-23, the hash-chained provenance subsystem in the tenant DB). This is control-plane
-- operational audit, NOT lineage: it deliberately carries NO hash-chain column.
--
-- The columns mirror the Control-Plane-local GatewayAuditRecord (backend/control_plane/gateway_audit.py) plus the two
-- store-assigned columns, matching the adapter:
--   INSERT INTO control_gateway_audit (audit_id, event_version, occurred_at, correlation_id, action, outcome, source_service,
--       actor_ref, subject_ref, tenant_ref, carrier_ref, record_ref)   -- id / recorded_at NOT inserted
--   ON CONFLICT (audit_id) DO NOTHING
-- `id` is DB-generated and is the durable total-ordering authority (reads ORDER BY id ASC — the B-7 precedent);
-- `recorded_at` is DB-assigned (DEFAULT now()); timestamps NEVER define total ordering (occurred_at is informational only,
-- gateway clock). `audit_id` is the gateway-minted idempotency key (uuid4().hex): UNIQUE, duplicate insert is a no-op, and the
-- adapter exact-compares a conflicting replay and rejects same-ID/different-payload drift. The action and source_service
-- CHECKs pin the CONTRACT-FROZEN Gateway-edge vocabulary (IC-010 §J AuditAction + the D-42 CLM success-access set; extension
-- only by contract amendment — the two tenant_startup_* actions were ratified by D-42 / the IC-010 CLM section) — the
-- action set is exactly the seven frozen AuditAction string values, and source_service is the ingest/store-side producer
-- constant 'api_gateway' (never a wire field).
--
-- References only (D-14; IC-001 Global Audit Representation Rule): actor/subject/tenant/carrier/correlation references and
-- event metadata only. NO passwords, NO DSNs / connection strings, NO raw secret values, NO JWT / session / API keys, NO cloud
-- credentials, NO PII, NO business payloads, NO returned membership collection, NO request/response bodies, NO database
-- hostnames / physical database names / topology, NO serialized connection or routing objects. carrier_ref is the opaque,
-- length-bounded carrier reference for anomaly attribution only (IC-005:116) — never parsed, resolved, or trusted. No
-- JSON/JSONB, no arbitrary metadata column, no raw error text column, no foreign key to any tenant database, no cross-database
-- constraint, no retention duration (IC-001 platform retention policy governs; default retain-all; D-08 process). Portable
-- standard PostgreSQL (AWS RDS / Azure Database for PostgreSQL / Cloud SQL / self-hosted) — no extensions, no
-- provider-proprietary features. Idempotent and additive (no destructive migration).
--
-- Append-only by design: id is immutable; there is NO UPDATE path and NO DELETE path; corrections, failures, and reversals are
-- NEW rows. DB-level append-only enforcement is the companion 013_gateway_operational_audit_append_only.sql.
--
-- Application posture — stated so that it is TRUE IN EVERY WINDOW. This template is authored under PRD Gateway Operational
-- Audit Persistence V1a (controlled non-production). It is applied ONLY by an explicit, governed, operator-driven act: never by
-- a runtime service, never by a migration runner, glob, or directory sweep, and never automatically. Exactly two such acts are
-- sanctioned — (a) the MANUAL_ONLY disposable proof (create -> prove -> drop), and (b) a separately governed, Dan-authorized
-- apply to the retained LOCAL standing Control database, which HAS TAKEN PLACE (recorded in the CLM-SS-1 Stage-0 closure; the
-- table carries pre-existing rows). It remains created-not-applied for every tenant, staging, and production database, and
-- production enablement remains unauthorized (Production NOT READY / DO-NOT-ACTIVATE). An earlier revision of this header read
-- "Created, NOT applied"; that sentence described one window only and must not be read as current standing state.
-- It is deliberately NOT enrolled in the B5-4 standing-topology apply order. The composed gateway audit default remains the
-- in-memory no-sink emitter (AD-1 Option A); durable mode is explicit and env-selected. Least-privilege writer-role DDL remains
-- separately governed and is not delivered by V1a.

CREATE TABLE IF NOT EXISTS control_gateway_audit (
    id             bigint       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- DB-generated; adapter never inserts id; ORDER BY id ASC
    audit_id       text         NOT NULL UNIQUE,  -- gateway-minted uuid4().hex idempotency key; duplicate insert is a no-op
    event_version  integer      NOT NULL CONSTRAINT control_gateway_audit_event_version_check CHECK (event_version > 0),
    occurred_at    timestamptz  NOT NULL,     -- gateway clock; informational only — never an ordering authority
    recorded_at    timestamptz  NOT NULL DEFAULT now(),  -- DB-assigned at insert; never caller-supplied
    correlation_id text         NOT NULL,     -- request correlation reference
    action         text         NOT NULL CONSTRAINT control_gateway_audit_action_check
                                CHECK (action IN ('CarrierMismatch', 'CarrierOnControlAnomaly', 'RouteDenied',
                                                  'IsolationAnomaly', 'workspace_memberships_read',
                                                  'tenant_startup_read', 'tenant_startup_update')),
    outcome        text         NOT NULL,     -- success / rejected / observed / denied:<code> (references only)
    source_service text         NOT NULL CONSTRAINT control_gateway_audit_source_service_check
                                CHECK (source_service = 'api_gateway'),
    actor_ref      text,                      -- NULLABLE: authenticated subject reference (never a credential)
    subject_ref    text,                      -- NULLABLE: self-scoped success subject reference (== actor_ref)
    tenant_ref     text,                      -- NULLABLE: authenticated active tenant reference (null for CONTROL edge)
    carrier_ref    text,                      -- NULLABLE: opaque, length-bounded carrier reference (anomaly attribution only)
    record_ref     text                       -- NULLABLE (D-42 CLM): tenant-resident record reference on the tenant Startup success events (a reference only — never field content)
);
