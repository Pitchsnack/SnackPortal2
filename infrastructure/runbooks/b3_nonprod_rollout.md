# Runbook — Non-Production Substrate Rollout (PRD 06 B-3)

**Documentation only. Non-production only. Not executable in B-3.** This runbook describes how a future,
separately-gated, validator-backed phase would stand up the cloud-portable Physical Multi-Database **substrate**
in a disposable non-production environment. It applies no DDL and creates no cloud resources in B-3.

> **Prerequisite gate:** a future execution phase requires its own PRD + the appropriate START-GATE before any
> step below is run. Nothing here is authorized by PRD 06 B-3 (which is docs/scaffold-only).

## Scope boundary (read first)

```
This runbook provisions SUBSTRATE: a cluster, the singular Control DB, and cluster-scoped roles.
It does NOT create tenant databases. Per-tenant physical DB creation is the Control-Plane D-15 workflow
  (backend/control_plane/provisioning.py) — invoked at runtime, not by this runbook.
OpenTofu/Terraform (if later adopted) must NOT track tenant DBs as long-lived state.
```

## Steps (future phase; non-production)

1. **Ground & confirm environment.** Confirm the target is `local` or `nonprod` (never production). Record the
   environment alias. Resolve all `secret_ref` references from the D-14 secret store at connect time (never log
   the resolved values).
2. **Provision cluster substrate** (`modules/postgres-cluster`). Standard PostgreSQL within the D-17 supported
   range; non-public network boundary; vendor-neutral parameters; no Docker dependency.
3. **Provision the Control DB** (`modules/control-db`). Exactly one physically separate Control Database. Do
   **not** create tenant databases.
4. **Create cluster-scoped roles** (`modules/postgres-role`). `sp2_provisioner` (NOLOGIN, CREATEDB, least
   privilege) and the lineage roles. Login credentials remain in the D-14 secret store.
5. **Apply Control-DB DDL — SEPARATELY GATED (DB3-6).** Applying `infrastructure/db/control/**` (blob-pinned;
   control ledger `30956ff1e8`) to the Control DB is a distinct, gated step — **not** part of substrate
   provisioning and **not** part of B-3. Apply the reviewed bytes unchanged, idempotently.
6. **Tenant onboarding is out of scope here.** When a tenant is onboarded (later, runtime), the Control-Plane
   D-15 workflow creates the physically distinct tenant DB, invokes the `tenant-db-bootstrap` template
   (`provisioning/**` + `lineage/**`, blob-pinned), then performs Physical Distinctness Verification
   (DV-C1..C7, IC-010 §P) and the ledger collision check **before** declaring the tenant `Ready` (fail-closed).
7. **Capture evidence.** Fill `docs/infrastructure/b3_evidence_template.md` — references only, redacted, with the
   environment identity, DDL blob hashes, resources created / not created, and gate results.

## Fail-closed conditions (stop; do not declare readiness)

```
Control DB unreachable · secret reference unresolved · DDL version mismatch (D-17) ·
physical-distinctness failure or incomplete evidence (IC-010 §P) · database identity mismatch ·
registry/router mismatch (D-07)
```

## Invariants preserved

Physical Multi-Database MVP (one Control DB + one physical DB per tenant; no shared DB, no `tenant_id` model,
no clone-TEMPLATE DB) · Control Plane = lifecycle authority · Database Router = sole selector · API Gateway =
sole ingress · D-14 references only · vendor-neutral standard PostgreSQL · infrastructure independent of
`backend/`.
