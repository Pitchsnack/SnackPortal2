# infrastructure/iac — Cloud-Portable IaC Substrate (scaffold)

Provider-neutral, cloud-portable Infrastructure-as-Code **substrate** for SnackPortal2's **Physical
Multi-Database MVP**. Introduced by **PRD 06 B-3 (Cloud-Portable IaC Rollout)** as a **documentation +
scaffold** layer — interfaces and boundaries, not executable infrastructure.

## Status (PRD 06 B-3 — controlled non-production)

```
Scope         documentation + scaffold ONLY
Committed     README / markdown describing module interfaces, boundaries, and conventions
NOT committed executable IaC (no .tf / .tofu / HCL), DDL, scripts that apply anything, secrets, or state files
NOT done      no cloud resources created, no DDL applied, no production, no runtime activation
```

Executable IaC (OpenTofu modules) and/or SQL runbooks are a **later, separately-gated, validator-backed
phase**. This phase establishes the **contracts and boundaries** future phases bind to (contracts precede
code — CLAUDE.md). At authoring time neither OpenTofu nor Terraform was installed in the build
environment, so no executable IaC was committed (it could not be validated, and unvalidated infrastructure
must not be committed).

## Non-negotiable rules this layer preserves

- **Independence (CLAUDE.md constraint 4):** everything here is deployable on its own and **does not import
  or depend on `backend/` application code**. It targets AWS RDS / Azure Database for PostgreSQL / Google
  Cloud SQL / self-hosted interchangeably — **standard PostgreSQL only**, no provider-proprietary features,
  no Docker dependency.
- **Secret references only (D-14):** no raw DSNs, passwords, connection strings, cloud credentials, API
  tokens, or secret values appear anywhere here. Descriptors carry `{store-ref, version}` references that
  are resolved in-memory at connect time and never logged, stored, or committed.
- **Physical Multi-Database MVP is mandatory (IC-010 §O):** one physically separate Control Database and one
  physically separate database **per tenant**. A single shared database with a `tenant_id` column is **not**
  an acceptable substitute, and a cloned PostgreSQL `TEMPLATE` database must **not** be used in any way that
  blurs physical distinctness.
- **D-15 ownership boundary:** **IaC provides reusable substrate; the Control Plane owns tenant lifecycle.**
  Per-tenant physical database creation/teardown is the automated, audited **Control-Plane provisioning
  workflow** (D-15) — **not** an IaC resource per tenant, and **not** something OpenTofu/Terraform tracks as
  long-lived state. The **Database Router** remains the sole database selector; the **approved authenticated public edges** (D-45) remain
  the sole ingress.

## Tooling stance (DB3-1 / DB3-3)

Provider-neutral by construction. Where IaC is eventually introduced, the preferred engine is **OpenTofu**
(the open-source, vendor-neutral fork) rather than HashiCorp Terraform, whose BSL relicensing is itself a
form of lock-in. A **SQL-runbook-first** approach is equally acceptable where it better matches the existing
`infrastructure/db/**` template convention. Provider-specific implementation, when unavoidable, sits behind
the provider-neutral module boundaries described under `modules/` (mirroring the backend
`adapters/providers/` containment pattern).

## Layout

```
iac/
├── README.md                       (this file)
├── .gitignore                      (state-file ignore patterns; defense-in-depth — no state is committed)
├── modules/                        (provider-neutral substrate module interfaces — README/markdown only)
│   ├── README.md
│   ├── postgres-cluster/           (cluster/server substrate)
│   ├── control-db/                 (the singular, control-plane-owned Control DB substrate)
│   ├── postgres-role/              (cluster-scoped least-privilege roles)
│   └── tenant-db-bootstrap/        (versioned DDL baseline applied per physical tenant DB — NOT a clone DB,
│                                    NOT the creator of tenant DBs)
└── environments/                   (environment conventions — non-production examples only)
    ├── README.md
    ├── local.example/
    └── nonprod.example/
```

## Related

- `infrastructure/db/**` — the reviewed, governed DDL templates this substrate would eventually apply
  (apply/reference only; **never edited by B-3**). See `docs/infrastructure/b3_ddl_target_mapping.md`.
- `infrastructure/runbooks/**` — non-production rollout and teardown runbooks.
- `docs/infrastructure/b3_cloud_portable_iac_rollout.md` — the B-3 design narrative.
- `docs/infrastructure/b3_evidence_template.md` — the references-only evidence-report template.
