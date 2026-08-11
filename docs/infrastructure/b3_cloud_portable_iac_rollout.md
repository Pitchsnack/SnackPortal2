# PRD 06 B-3 — Cloud-Portable IaC Rollout (design narrative)

**Phase:** PRD 06 B-3 — controlled non-production, **documentation + scaffold only**.
**Baseline:** `origin/main @ f346cf0`. **Status:** no executable IaC, no DDL applied, no cloud resources, no
runtime activation. Executable IaC / SQL runbooks are a later, separately-gated, validator-backed phase.

This document is the design narrative for the cloud-portable Physical Multi-Database substrate. The normative
module contracts live under `infrastructure/iac/modules/**`; the DDL→target mapping is
`b3_ddl_target_mapping.md`; the evidence template is `b3_evidence_template.md`.

## 1. Objective

Make the already-reviewed Physical Multi-Database substrate **deployable in a cloud-portable, vendor-neutral
way** — turning the governed `infrastructure/db/**` DDL templates and the D-15 control-plane provisioning
workflow into a **reproducible, reviewable rollout model** that runs identically on AWS RDS / Azure Database for
PostgreSQL / Google Cloud SQL / self-hosted. B-3 makes the rollout *portable and reviewable*; it does not
activate production (B-5) and is not the provisioning audit sink (B-6).

## 2. Architecture shape (preserved, not changed)

```
approved public edges (the only served client ingress — D-45)
  → Control Plane (lifecycle / readiness authority)
  → Database Router (sole DB selector; registry-authoritative, D-07)
  → Control DB registry  → exactly one physical Tenant DB
For each request: one active tenant · one database · no cross-tenant physical DB mixing (D-30).
```

## 3. The D-15 ownership boundary (the central design rule)

```
IaC substrate          = cluster/server, the singular Control DB, cluster-scoped roles, secret-reference
                         wiring, and the versioned tenant-DB bootstrap TEMPLATE (a DDL baseline).
Control-Plane workflow = per-tenant physical DB CREATION/teardown + bootstrap invocation + Physical
                         Distinctness Verification (automated, audited; D-15;
                         backend/control_plane/provisioning.py).
Database Router        = selection only; never creates/resolves during provisioning.
Manual runbook         = break-glass / first-boot / DR only (D-15 option C).
```

Consequence: tenant databases are **not** IaC state objects. Classic IaC drift detection applies to the
**substrate**, not the per-tenant DB fleet.

## 4. Portability model (DB3-1 / DB3-3)

- **Standard PostgreSQL only** — no provider-proprietary extensions/features; runs on AWS RDS / Azure / Cloud
  SQL / self-hosted; **no Docker dependency**.
- **Provider-neutral module boundaries** with provider specifics isolated behind a `provider_alias` (mirrors
  the backend `adapters/providers/` containment).
- **Tooling:** OpenTofu-compatible structure **or** SQL-runbook-first. **OpenTofu** is preferred over
  HashiCorp Terraform (BSL relicensing is itself lock-in). At authoring time neither was installed, so no
  executable IaC was committed — unvalidated infrastructure must not be committed.
- **Cluster vs. database object scope:** roles are cluster-global; databases/tables are database-scoped. On
  managed providers, role/database creation needs provider-privileged membership (`rds_superuser`,
  `cloudsqlsuperuser`, the Azure admin role) — achieved without provider-proprietary features.

## 5. Secret-reference model (D-14)

A single internal, **pluggable** reference-based secret-store abstraction (cloud-native where present —
AWS Secrets Manager / Azure Key Vault / GCP Secret Manager — self-hostable elsewhere). Descriptors hold
`{store-ref, version}`; values resolve in-memory at connect time and are never logged, stored, or committed.
This pluggability is the crux of portability: the same IaC works across clouds by swapping the secret-store
backend. No raw DSNs, passwords, tokens, or credentials appear anywhere in this layer.

## 6. DDL application model (DB3-6)

DDL application is **separately gated** and **does not run in B-3**. The model:

- **Idempotent** (the reviewed DDL uses `CREATE … IF NOT EXISTS`, guarded role creation, conditional seed
  `INSERT`); **ordered** (`001 → 002 → 003`); **additive / non-destructive**.
- **Target-scoped:** `control/**` → Control DB; `provisioning/**` + `lineage/**` → each Tenant DB; role
  objects are cluster-global. See `b3_ddl_target_mapping.md`.
- **Blob-pinned:** a future phase applies the reviewed bytes **unchanged** and verifies each file's blob hash.
- **D-17:** expand/contract migrations with version-gated readiness against a supported range.

## 7. Readiness & fail-closed (IC-010 §P; B-2/B-4)

A tenant reaches `Ready` (IC-002) only when reachability + schema-version compatibility (D-17) **and** Physical
Distinctness Verification (DV-C1..C7) **and** the distinctness-ledger collision check all pass — **fail-closed**.
`evidence_excluding` must never return an empty/partial inventory on error (that would hide a tenant-vs-tenant
collision; proven in B-4). B-3 documents this binding; it implements no runtime activation.

## 8. What B-3 delivered (this phase)

```
infrastructure/iac/**            module interface contracts + environment conventions + scoped .gitignore
infrastructure/runbooks/**       non-production rollout + teardown runbooks (documentation)
docs/infrastructure/**           this narrative + DDL target mapping + evidence template
infrastructure/README.md         additive pointer to the new IaC layer
```

No executable IaC, no DDL applied, no cloud resources, no runtime activation, no `main.py` change, no B-5/B-6,
no frontend cutover.

## 9. What remains (later, separately gated)

- Executable IaC (OpenTofu modules) and/or SQL runbooks, with `tofu fmt -check` / `tofu validate` once a
  validator is available.
- Non-production Control-DB DDL application (blob-pinned, idempotent), as a distinct gate.
- Tenant onboarding via the Control-Plane D-15 workflow against a non-production substrate.
- B-5 (production runtime activation) and B-6 (provisioning audit sink) — each separate and governed.

## 10. Governing references

IC-001 (audit references-only) · IC-002 (tenant lifecycle / readiness) · IC-010 §O (physical multi-DB
mandatory) / §P (distinctness hook) / §H,§M (router boundary) / §I (gateway sole ingress) · D-07
(registry-authoritative) · D-14 (secret references) · D-15 (provisioning ownership) · D-17 (schema migration) ·
D-30 (cross-tenant isolation) · CLAUDE.md constraint 4 (infrastructure independent of backend).
