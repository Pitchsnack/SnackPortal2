# infrastructure

Infrastructure-as-Code and environment templates for SnackPortal2.

**Independence rule (CLAUDE.md constraint 4):** this directory MUST be deployable
on its own and MUST NOT import or depend on `backend/` application code. It targets
AWS / Azure / GCP / self-hosted interchangeably (cloud-portable PostgreSQL only).

**Build Phase 1 scope:** environment **templates only** — references, never secret
values (D-14). No provisioning, deployment, release, or automation is defined here.

**Explicitly deferred (NOT Build Phase 1):**
- Tenant database provisioning IaC (D-15 — automated, audited control-plane
  workflow; manual runbook is break-glass only).
- Docker/Compose, Terraform, Kubernetes manifests for real environments.

See `env/` for the reference-only template convention.

## IaC substrate scaffold (PRD 06 B-3 — added)

**PRD 06 B-3 (Cloud-Portable IaC Rollout)** adds a **documentation + scaffold** layer under `iac/` describing the
provider-neutral substrate module interfaces, environment conventions, and rollout/teardown runbooks for the
Physical Multi-Database MVP. This is **scaffold only**: it commits **no executable IaC (no `.tf`/`.tofu`/HCL),
applies no DDL, and creates no cloud resources**. Executable IaC / SQL runbooks remain **deferred** to a later,
separately-gated, validator-backed phase (consistent with the deferral noted above).

- `iac/` — provider-neutral module interfaces (`modules/`) + environment conventions (`environments/`).
- `runbooks/` — non-production rollout and teardown runbooks (documentation).
- `docs/infrastructure/` — B-3 design narrative, DDL→target mapping (blob-pinned), and the evidence template.

The D-15 ownership boundary holds: **IaC provides substrate; the Control Plane owns tenant lifecycle** and
per-tenant physical database creation. `infrastructure/db/**` remains the governed DDL (apply/reference only).
