-- SnackPortal2 — Migration M-1: BFF ingress-edge operational audit (D-46 section 7; IC-013 section 10).
--
-- WHY A NEW TABLE, NOT AN ALTERED ONE.
-- Control DDL 012 pins CHECK (source_service = 'api_gateway') on control_gateway_audit. That constraint
-- physically rejects a BFF-emitted row, so BFF audit emission is blocked until a table exists that will
-- accept one. D-46 section 7 approves a NEW append-only table and requires 012/013 and their byte-pins to be
-- left intact as the historical record of the retired Gateway's audit. This migration therefore adds; it
-- alters nothing and drops nothing.
--
-- The audit CLASSES are unchanged from IC-010 section J: the same four denial/anomaly actions, the same
-- success-access subclasses. Only the emitter changes, which is exactly what the source_service CHECK below
-- records. The nine share_* actions and forward_attempt_denied are authored-but-inert until IC-007 is Final
-- (IC-013 section 18) -- present in the vocabulary, emitted by nothing.
--
-- REFERENCES ONLY (IC-001 Global Audit Representation Rule; IC-013 section 10). Every column is a reference,
-- a code, or a timestamp. Prohibited here and forever: names, emails, PII, business payloads, field content,
-- raw rows, tenant business data, tenant database identity, database name, DSN, secret, credential,
-- connection string, token, provider body, router internals, stack trace.
--
-- Portable standard PostgreSQL (AWS RDS / Azure Database for PostgreSQL / Cloud SQL / self-hosted) -- no
-- extensions, no provider-proprietary features. Idempotent and additive.
--
-- Created, NOT applied. Applying this to a live Control database is ops/IaC, never runtime.

CREATE TABLE IF NOT EXISTS control_ingress_audit (
    id             bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- DB-generated; the emitter never supplies it
    event_id       text        NOT NULL UNIQUE,   -- server-minted uuid4; the idempotency key, so a retried emit is a no-op
    occurred_at    text        NOT NULL,          -- ISO-8601 UTC, set by the Audit Service; informational, never an ordering authority
    recorded_at    timestamptz NOT NULL DEFAULT now(),  -- DB-assigned at insert; never caller-supplied
    source_service text        NOT NULL CONSTRAINT control_ingress_audit_source_service_check
                               CHECK (source_service <> 'api_gateway'),
                               -- The inverse of DDL 012's constraint, and deliberately so. 012 accepts only
                               -- the retired Gateway; this table accepts only what is not it. The two tables
                               -- are therefore disjoint by construction: no row can be written to both, and
                               -- the historical record cannot be polluted by new emission.
    action         text        NOT NULL CONSTRAINT control_ingress_audit_action_check
                               CHECK (action IN ('CarrierMismatch', 'CarrierOnControlAnomaly', 'RouteDenied',
                                                 'IsolationAnomaly', 'workspace_memberships_read',
                                                 'tenant_startup_read', 'tenant_startup_update',
                                                 'share_proposed', 'share_approved', 'share_granted',
                                                 'share_read', 'share_revoked', 'share_expired',
                                                 'share_suspended', 'share_denied', 'forward_attempt_denied')),
    outcome        text        NOT NULL CONSTRAINT control_ingress_audit_outcome_check
                               CHECK (outcome IN ('allowed', 'denied', 'anomaly')),
    correlation_id text        NOT NULL,          -- request correlation reference
    actor_ref      text        NOT NULL,          -- acting principal reference (never a name, email, or credential)
    subject_ref    text,                          -- NULLABLE: the principal the action concerned, where different
    tenant_ref     text,                          -- NULLABLE: active tenant reference; null on the Control edge
    record_ref     text,                          -- NULLABLE: tenant-resident record reference; a reference, never field content
    carrier_ref    text                           -- NULLABLE: opaque carrier-asserted value, anomaly attribution only; never parsed or trusted
);

-- Read paths: by tenant (operational review) and by actor (self-scoped and delegated reads).
CREATE INDEX IF NOT EXISTS ix_control_ingress_audit_tenant ON control_ingress_audit (tenant_ref, id);
CREATE INDEX IF NOT EXISTS ix_control_ingress_audit_actor  ON control_ingress_audit (actor_ref, id);
CREATE INDEX IF NOT EXISTS ix_control_ingress_audit_corr   ON control_ingress_audit (correlation_id);
