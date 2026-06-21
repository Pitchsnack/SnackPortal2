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

## Scope boundary (PRD 06 B-2 — NOT authorized)

This template is **created, not applied**. It does **not** define and does **not** authorize:
applying the DDL to a live Control database, exercising the durable ledger against a real
cluster (that is the live-PostgreSQL exercise, **B-4**), production rollout, production secrets,
production infrastructure, IaC / migration-runner / CI/CD deployment (that is **B-3**), or any
audit-history sink (that is **B-6**). The control-plane runtime default remains the in-memory
distinctness ledger; the durable Control-DB ledger is opt-in and exercised live only in B-4.
