# db/control — Control-Database schema artifacts

Portable, dependency-free SQL templates for **control-plane-owned** tables in the **Control
Database** (the global/cross-tenant store; CLAUDE.md Multi-Database Model). This directory is
introduced by **PRD 06 B-2 (Durable Distinctness Ledger)** as the first additive Control-DB
schema artifact, authorized for **controlled non-production implementation only**.

**Independence rule (CLAUDE.md constraint 4):** these files are deployable on their own and do
**not** depend on `backend/` application code. Standard, cloud-portable PostgreSQL only (AWS RDS
/ Azure Database for PostgreSQL / Cloud SQL / self-hosted) — no provider-specific extensions.

**References only (D-14; IC-001 Global Audit Representation Rule):** no passwords, DSNs,
connection strings, raw secret values, JWT/API keys, cloud credentials, or PII appear here. The
Control-DB connection credential is resolved from the secret store at connect time (it is never
stored in a table or in these templates).

## Files (idempotent; additive)

| File | Purpose | Spec anchor |
|------|---------|-------------|
| `001_distinctness_ledger.sql` | The durable, reference-only **distinctness ledger** (`control_distinctness_ledger`): the per-tenant Physical Distinctness evidence inventory the D15 readiness gate consults for tenant-vs-tenant collision detection. One latest row per tenant (inventory, not audit history). Columns mirror `DistinctnessEvidence` + `tenant_id` + `recorded_at`. | §9.2 input 8; IC-010 §P; D15-ARCH-SPEC-01 §6 |
| `002_provisioning_audit.sql` | The durable, append-only, reference-only **provisioning audit store** (`control_audit`): the audit-history table the wired adapter `postgres_store.py` already targets. Columns mirror `ControlAuditRecord` (adapter-INSERT-compatible: `id` DB-generated; `tenant_id`/`from_state`/`to_state` NULLABLE). Distinct from the `001` inventory and from IC-004/D-23 lineage. **Created, not applied.** | D-34; IC-002; IC-001; IC-010 §J; PRD 06 B-7 |
| `003_provisioning_audit_append_only.sql` | DB-level **append-only enforcement** for `control_audit`: a portable PL/pgSQL trigger rejecting UPDATE/DELETE/TRUNCATE (mirrors `lineage/002_append_only.sql`). **Created, not applied.** | D-34; PRD 06 B-7 |

## Scope boundary (PRD 06 B-2 — NOT authorized)

This template is **created, not applied**. It does **not** define and does **not** authorize:
applying the DDL to a live Control database, exercising the durable ledger against a real
cluster (that is the live-PostgreSQL exercise, **B-4**), production rollout, production secrets,
production infrastructure, IaC / migration-runner / CI/CD deployment (that is **B-3**), or the
provisioning audit store (the sink **contract** is **B-6**; the `control_audit` **table DDL** is
authored under **B-7**, created-not-applied — see below). The control-plane runtime default
remains the in-memory distinctness ledger; the durable Control-DB ledger is opt-in and exercised
live only in B-4.

## Scope boundary (PRD 06 B-7 — provisioning audit DDL)

`002_provisioning_audit.sql` and `003_provisioning_audit_append_only.sql` are **created, not
applied**. PRD 06 B-7 authors the missing DDL for the **existing** `control_audit` table (the one
`postgres_store.py` already writes to); it does **not** apply the DDL, wire runtime, provision a
production sink, or close B5-BLK-4. Applying + exercising the DDL against a live Control database is
the live-PostgreSQL exercise (**B-7A**), a separate later gated phase. The DDL introduces **no**
28-field parallel table and does **not** modify the adapter.
