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

## Local Docker multi-database test environment (PRD 06 B-3A — added)

**PRD 06 B-3A** adds a **local / non-production** Docker Compose fixture under `docker/` — four physically separate
PostgreSQL instances (one Control + three tenant) that demonstrate the Physical Multi-Database MVP topology locally and
feed the existing `requires_pg` distinctness harness. It is a **local test convenience only**: Docker is **substrate
only**, never production, never the portability mechanism, and **not** a substitute for the Docker-free cloud-portable
IaC under `iac/`. It applies **no DDL**, activates **no runtime**, and commits **no secret values** (the container
password is interpolated from an untracked `.env.local`; the committed `.env.local.template` holds placeholders and
`ref:` references only).

- `docker/` — `docker-compose.local.yml` (4 × `postgres:17`, 127.0.0.1:5540-5543), `.env.local.template`, `.gitignore`,
  and `runbooks/` (local start + teardown).
- `../docs/infrastructure/b3a_*.md` — B-3A design narrative + references-only evidence template.

## Runtime activation gate (reference-only) (PRD 06 B-5 — added)

**PRD 06 B-5** adds a **reference-only** runtime activation-gate template under `runtime/`. It is **not** production
config, **not** runtime-wired, and **not** secret-bearing: the activation switch is disabled by default
(`RUNTIME_ACTIVATION_ENABLED=false`) and all secret-bearing settings are `*_REF=ref:...` references only (D-14). B-5
**does not** activate runtime, **does not** modify `backend/control_plane/main.py`, and **does not** flip the live
`NotImplementedError` deferral. The gate specification, blocker register (NOT READY by default), evidence template, and
readiness matrix live under `../docs/runtime/b5_*.md`.

- `runtime/` — `b5_activation_gate.template` (forward contract; references only) + `README.md`.
