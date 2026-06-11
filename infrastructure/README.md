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
