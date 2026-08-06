# infrastructure/runbooks — non-production operational runbooks (B-3)

Operational **runbooks** for the cloud-portable substrate, **non-production only**. **Documentation only**
(PRD 06 B-3): these describe procedures; they are **not** executable, apply no DDL, and create no cloud
resources. They exist so a future, separately-gated execution phase has a reviewed, safe procedure to follow.

## Runbooks

Complete index. **Status is load-bearing** — several of these describe a runtime or a topology that has
since moved, and an operator who reads a superseded document as current can start the wrong thing.
Before Gate A this index listed 2 of 14 files, so most of them had no discoverable status at all.

**Status key:** 🟢 current · 🟡 current with corrections in-file · 🟠 superseded for part of its scope
(read the in-file banner) · ⚪ rehearsal / proof procedure, disposable targets only

| Runbook | Status | Purpose |
|---------|---|---------|
| `b3_nonprod_rollout.md` | 🟢 | How a future phase would stand up the non-production substrate (cluster → Control DB → cluster-scoped roles), with the boundary that **tenant DB creation stays in the Control-Plane D-15 workflow**. |
| `b3_teardown.md` | 🟢 | How to tear down a disposable non-production substrate safely, with multi-DB isolation guarantees and production warnings. |
| `aw1_gateway_audit_writer.md` | 🟢 | AW-1 least-privilege Gateway-audit writer: the two roles, the ingest process's environment whitelist, the `plan`/`apply`/`status` tooling, the start gate, and the credential contract. Tooling is a Gate-A deliverable; creating the roles and the credential is Gate-B M2. |
| `b5_standing_topology.md` | 🟢 | Standing B5-4 topology: Control DB + the two deterministic standing tenants; the governed control-DDL apply order (001–009 only). |
| `b5_standing_auth_fixture.md` | 🟠 | The B5-4 standing auth fixture. **Superseded by AUTHFIX-B** — its subject standing state was replaced around 2026-07-21. Read the in-file supersession banner before running it; a non-zero exit is expected and explicit. |
| `b5_blk6_portal_binding_live_proof.md` | ⚪ | B5-BLK-6 portal-binding live proof procedure. |
| `b5_blk8_rollback_to_deferred_composition.md` | ⚪ | B5-BLK-8B rollback rehearsal to the deferred composition. |
| `b5_blk8c_hosted_rollback_proof.md` | ⚪ | B5-BLK-8C hosted rollback proof (IC-011 / D-40). |
| `clm_2day_stage_b_rehearsal.md` | ⚪ | CLM Stage-B rehearsal. Its `sp2_clm_acme` / `sp2_clm_zeta` databases are **disposable**, created and dropped on ONE cluster — they are **not** the standing ACME/ZETA tenant databases on 5541/5542, and this rehearsal is never tenant data-plane evidence. |
| `controlled_rollback_rehearsal.md` | ⚪ | Controlled rollback rehearsal (disposable). |
| `controlled_served_write_rehearsal.md` | ⚪ | Controlled served-write rehearsal (disposable). |
| `dbr_ar_2_durable_routing_audit.md` | 🟢 | DBR-AR-2 durable routing audit: the governed operator procedure for DDL 010/011. |
| `gateway_edge_v1_serve.md` | 🟠 | The served API Gateway edge's request contract, bounds, CORS and denial semantics. **Superseded for startup** by `docs/runbooks/backend_service_startup_fastapi.md`; corrected under Gate A for the ephemeral-port trap and for the tenant-Startup write family it previously denied existed. |
| `gateway_operational_audit_live_proof.md` | 🟡 | Governed operator procedure for the Gateway operational-audit DDL 012/013 against a **disposable** database. Carries the current-standing-state note and the five-pin lockstep warning. |
| `import_copy_live_proof.md` | ⚪ | Import copy live proof (disposable). Import is outside the controlled local MVP journey (IMPORT-A / D-3). |
| `smoke_c_integrated_live_proof.md` | 🟠 | Smoke C integrated live proof. Its standing-state preconditions were superseded by AUTHFIX-B; read the in-file HISTORICAL annotations. |

### Runbooks that do NOT live here

| Runbook | Where | Why |
|---|---|---|
| `backend_service_startup_fastapi.md` | `docs/runbooks/` | **The canonical startup runbook.** Standing map 8001/8002/8003/8004/8005/**8820**; the `8080–8088` map is isolated smoke/verification only. |
| `b5_service_startup_order.md` | `docs/runbooks/` | 🟠 **Superseded for the served topology.** Predates the FastAPI migration and the served Gateway edge; its dependency *order* still holds, its runtime description does not. |
| `clm_acme_dataplane_witness.md` | here (added under Gate A) | The tenant data-plane proof protocol. Build-only under Gate A — the standing PATCH proof is not executed. |

## Standing rules for every runbook

- **Non-production only.** Production is deferred to B-5; no runbook here targets production.
- **D-15 ownership:** runbooks provision **substrate**; per-tenant database creation/teardown is the
  Control-Plane workflow, not a runbook step.
- **Secret references only (D-14):** runbooks reference `secret_ref` aliases; they never embed DSNs, passwords,
  tokens, or credentials.
- **Fail-closed:** if any required proof (reachability, schema version, physical distinctness, secret
  resolution) is missing or ambiguous, the procedure stops and does not declare readiness.
- **No apply in B-3:** these are written, not run, in this phase.
