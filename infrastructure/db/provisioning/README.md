# db/provisioning — D15 tenant provisioning substrate

Portable, dependency-free SQL templates for the **D15 Provisioning Architecture**
(`D15-ARCH-SPEC-01`), authorized for **controlled non-production implementation only** by
**PRD-D15-IMPL-01 §22** (WP-1/WP-2 provisioning model; the Physical Distinctness Verifier's
write-sentinel store).

**Independence rule (CLAUDE.md constraint 4):** these files are deployable on their own and
do **not** depend on `backend/` application code. Standard, cloud-portable PostgreSQL only
(AWS RDS / Azure / GCP / self-hosted) — no provider-specific extensions.

**References only (D-14):** no passwords, descriptors, or secret values appear here. The
per-tenant login credential is resolved from the secret store at connect time; provisioning
roles are `NOLOGIN` group roles.

## Files (idempotent; apply in order to a freshly provisioned tenant database)

| File | Purpose | Spec anchor |
|------|---------|-------------|
| `001_tenant_database.sql` | Tenant-DB bootstrap: the `schema_version` table the control-plane verification probe reads. | §8 Step 2; IC-002; D-17 |
| `002_distinctness_sentinel.sql` | The control-owned `dv_sentinel` write-sentinel store used by Physical Distinctness Verification. Matches the evidence provider's idempotent DDL. | §6.5; §9.3 DV-C4 |
| `003_provisioning_role.sql` | Least-privilege, control-plane-scoped provisioning role template (D-15). | D-15 |

## Scope boundary (PRD-D15-IMPL-01 §22.5 — NOT authorized)

These templates support provisioning **throwaway verification databases** in an isolated,
disposable non-production environment. They do **not** define and do **not** authorize:
production rollout, live tenant onboarding, production secrets, production infrastructure,
Docker/Compose/Terraform/Kubernetes for real environments, or CI/CD deployment. Production
provisioning requires a separate downstream rollout PRD.
