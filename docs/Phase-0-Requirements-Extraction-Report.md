# SnackPortal2 — Option A Clean FastAPI Rebuild
# Phase 0 — Requirements & Existing-System Discovery

**Branch:** `phase/00-requirements-extraction`
**Base:** `main` @ `cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f`
**Date:** 2026-08-21
**Author:** Claude (Claude Code)
**Governing instruction:** `SnackPortal2_Phase0_New_Branch_Instructions_Claude_GPT.md` + `SnackPortal2_Option_A_Clean_FastAPI_Rebuild_Claude_GPT.md`
**Status:** **PARTIAL** — discovery is complete; one **blocking contract conflict (CONF-1)** and eleven further conflicts require Dan's decision before Phase 1 may lawfully begin.

> **Scope discipline.** This is discovery only. No implementation was created, no old code deleted, no branch merged, no old-branch work cherry-picked. The existing backend was read as a *requirements and validated-behaviour source*, never as architecture to preserve.

---

## 1. Repository ground truth

| Fact | Value |
|---|---|
| Repository | `https://github.com/Pitchsnack/SnackPortal2.git` (origin) |
| Working copy | `D:\Pitchsnack\SnackPortal2-phase-00` (git worktree) |
| Branch at session start | `phase/00-architecture-ratification` @ `5e8d9d92` |
| Working tree at session start | **clean** (no uncommitted work; nothing discarded) |
| `main` (local) | `cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f` |
| `origin/main` | `cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f` — **0 ahead / 0 behind**, local `main` is current |
| New branch | `phase/00-requirements-extraction`, created **from `main`**, HEAD == `main` verified |
| Old branch | `phase/00-architecture-ratification` **preserved untouched** at `5e8d9d92` (unmerged; not used as a base, not cherry-picked) |

**Deviation from Step 2, recorded.** The instruction says `git switch main`. This working copy is a *git worktree*; `main` is checked out in `D:\Pitchsnack\SnackPortal2`, so `git switch main` is impossible here by design. The new branch was instead created directly from `main` (`git switch -c phase/00-requirements-extraction main`). The resulting base commit is byte-identical to what Step 2 → Step 3 would have produced, and this was verified (`HEAD == main` → YES).

**Clean-baseline confirmation.** `main` carries **no** D-45, **no** IC-013, **no** IC-014 and **no** BFF language. Those artefacts exist only on the abandoned `phase/00-architecture-ratification` branch. The Phase 0 baseline is therefore genuinely clean of the old architecture-ratification direction. *(Note: any `CLAUDE.md` text referring to IC-013/IC-014/D-45 comes from that abandoned branch and is not true of this branch.)*

**Repository shape**

```
CLAUDE.md
backend/          19,085 lines production Python (7 packages) + 74,799 lines tests
contracts/        12 interface contracts (IC-001 … IC-012)
docs/             41 entries (decision packs, phase acceptance criteria, handovers, runbooks)
infrastructure/   29 SQL files, docker-compose local topology, IaC skeletons, 17 runbooks
```

There is **no `frontend/` directory** in this repository. The frontend is a separate repo (`snack-cosmos`), present locally only as detached working copies. See §9.

**Verified test baseline (executed on this branch, this tree):** `pytest -q` → **2054 passed in 91.63s**, 0 failed. Run with the main worktree's venv (`D:\Pitchsnack\SnackPortal2\backend\.venv`) with cwd inside the phase-00 tree; the phase worktree has no venv of its own.

---

## 2. Existing backend capability inventory

Seven runtime packages, all flat top-level, all `IMPLEMENTS_BEHAVIOR = True` except `shared`.

| Package | Core (non-adapter) | Adapters | Capability summary |
|---|---:|---:|---|
| `control_plane` | 25 files / 4,584 ln | 19 / 3,335 | Tenant registry & lifecycle, membership, federation config, Global Directory, onboarding orchestration, provisioning + physical-distinctness verification, recovery/deprovision/orphan scan, control audit, read API, bootstrap |
| `database_router` | 12 / 1,669 | 9 / 823 | Registry-authoritative tenant→DB resolution, readiness/schema gating, per-tenant credential resolution at connect time, keyed per-tenant pools, routing audit, CLM tenant-Startup bounded read/update executor |
| `auth_router` | 8 / 736 | 6 / 409 | Stage 1 stateless JWT validation (alg allowlist, claims, JWKS by port); Stage 2 tenant-context establishment from control-plane reads; auth audit; TTL cache |
| `import_service` | 7 / 866 | 10 / 549 | Import unit of work: validate → idempotent tenant upsert → lineage emit → checkpoint, all in one transaction; source adapters (Global Directory / CSV / JSON); durable import audit |
| `lineage_service` | 11 / 913 | 0 | Append-only lineage emit with per-tenant HMAC hash-chain; verification, query, search, provenance graph, segmentation, retention framework |
| `shared` | 16 / 1,369 | 6 / 334 | `RequestContext`, DTO/errors/health/audit/lineage/session ports, secret refs, portability profile/manifest/identity, ASGI runtime (the **sole** uvicorn import site), FastAPI edge helper |
| `api_gateway` | 10 / 1,993 | 11 / 1,334 | **Category D** — see §6 |
| `deployment` | 2 / 171 | 0 | **Category D** — IC-012 cross-service composition root for the old 9-edge topology |

**Runtime topology as built (the "nine native FastAPI/Uvicorn edges").** Nine `create_app_from_env()` factories:

| # | Edge | Module | Surface |
|---:|---|---|---|
| 1 | Public gateway edge | `api_gateway/adapters/providers/http_gateway_edge.py` | `GET /memberships`, `POST /import/{source_ref}`, `GET\|PATCH /tenant/startups/{startup_ref}`, `/health`, `/readiness` |
| 2 | Auth | `auth_router/.../http_authenticate_api.py` | `POST /internal/auth/authenticate` |
| 3 | Control read | `control_plane/.../http_read_api.py` | `GET /{target:path}` |
| 4 | Gateway audit ingest | `control_plane/.../http_gateway_audit_api.py` | `POST /internal/gateway-audit/events` |
| 5 | Import audit ingest | `control_plane/.../http_import_audit_api.py` | `POST /internal/import-audit/events` |
| 6 | Routing audit ingest | `control_plane/.../http_routing_audit_api.py` | `POST /internal/routing-audit/events` |
| 7 | Router dispatch | `database_router/.../http_dispatch_api.py` | `POST /internal/dispatch/route` |
| 8 | Tenant Startup ops | `database_router/.../http_tenant_startup_api.py` | `POST /internal/tenant/startups/{read,update}` |
| 9 | Import edge | `deployment/import_edge.py` | `POST /internal/import/initiate` |

**The entire public business surface is three operations.** `GET /memberships`, `POST /import/<ref>`, and `GET|PATCH /tenant/startups/<ref>`. Everything else is internal loopback. This is the single most important sizing fact in this report — see §13 RISK-1.

### Business capabilities, per Step 5's required list

| Required capability | Built? | Where |
|---|---|---|
| Startup behaviour | **Partial** | Global directory read (Control DB); tenant Startup **bounded** read + single-field update (`short_description`, ≤500 chars); import-created tenant copy. No create, no delete, no general edit. |
| Investor behaviour | **Schema only** | `investors` DDL + `DirectoryKind.INVESTOR`; **no service, no route, no import path** |
| Deal behaviour | **Schema only** | `deals` DDL; **no service, no route**. D-35 ratifies a Global Deal Directory that `DirectoryKind` does not implement |
| Contacts behaviour | **Schema only** | `startup_contacts` / `investor_contacts` / `startup_investors` DDL; **no service, no contract** |
| Authentication | **Built** | `auth_router` two-stage; OIDC + internal platform identities on one path (D-03/D-05) |
| Access Control | **NOT BUILT** | No permission engine exists anywhere in production code. See §11 |
| Tenant membership & role rules | **Built (storage + resolution)** | `control_plane/membership.py` (1:N, "roles stored, never evaluated"); resolved in auth Stage 2; six roles |
| Physical multi-DB behaviour | **Built** | Registry-authoritative routing; keyed per-tenant pools; physical-distinctness verification gate |
| Control DB vs Tenant DB responsibilities | **Built + contracted** | D-31/D-34/D-35: global directories + operational audit = Control DB; operational records + lineage = tenant DB |
| Database Router requirements | **Built** | The strongest component in the repo |
| Import behaviour | **Built** | Atomic provenance, idempotency, checkpoint/resume, validation floor |
| Lineage behaviour | **Built** | Append-only + HMAC chain + verification + graph + segmentation + retention framework |
| Sharing behaviour | **NOT BUILT** | IC-007 Draft/Proposed; zero code; zero DDL (deliberate) |
| Audit / activity | **Built (4 classes)** | Control/provisioning audit, routing audit, gateway audit, import audit — all append-only, references-only |
| AI Agent requirements | **NOT BUILT** | IC-006 is a TBD placeholder; D-02/D6 defer AI. Only `ai_agents` + `*_ai_ownership` DDL exist |

---

## 3. Business logic worth porting — **Category A**

**79 files / 10,137 lines** of framework-agnostic core (all non-adapter code outside `api_gateway` and `deployment`). These modules have no FastAPI, no web framework, and no HTTP dependency — they are pure domain logic behind ports. That is exactly why they are portable into the Option A layout with high confidence.

### A-1 — Database Router core (12 files / 1,669 ln) — **highest-value port**
`router.py`, `resolver.py`, `models.py`, `pool.py`, `cache.py`, `disclosure.py`, `session_provider.py`, `tenant_startup_ops.py`, `ports.py`, `_util.py`.

Directly satisfies the Option A Phase 5 contract:
- Registry-authoritative resolution; never hardcodes, never guesses a DB name, never spans tenants.
- The active tenant is taken from the signed claim and **never re-derived**.
- Readiness + schema-version gating before any bind.
- Credentials resolved at connect time from a `{store_ref, version}` reference, then discarded.
- Connection pools keyed on `(tenant_id, association_version)` — a cross-tenant borrow is *structurally* impossible, not merely checked.
- Canonical non-leaking denials via `disclosure.denial_for_state`; **no Control-DB fallback path exists**.

### A-2 — Authentication core (8 files / 736 ln)
`jwt_validation.py` (Stage 1: stateless, DB-free, alg allowlist, claim checks, signature delegated to a port), `tenant_context.py` (Stage 2: control-plane reads only; fail-closed; unknown tenant and non-member are indistinguishable), `authenticator.py`, `models.py`, `caching.py`.

Maps 1:1 onto Option A Phase 2. Already obeys the Phase 2 prohibitions: it does not authorize, does not choose a tenant DB, does not route.

### A-3 — Control Plane core (25 files / 4,584 ln)
Tenant registry + lifecycle state machine (`registry.py`, `lifecycle.py`, `records.py`), membership (`membership.py`), federation (`federation.py`), Global Directory (`directory.py`), onboarding orchestration (`onboarding.py`), provisioning + verification gate (`provisioning.py`, `verification.py`), **physical distinctness verification** (`distinctness.py`), recovery/deprovision/orphan scan (`recovery.py`, 784 ln), audit (`audit.py`, `events.py`), read API (`read_api.py`), router cache-invalidation signal (`router_signal.py`), bootstrap (`bootstrap.py`), schema compatibility (`schema_compat.py`).

`distinctness.py` deserves special mention: it proves a tenant DB is physically distinct from every other tenant DB *and* from the Control DB using layered evidence (`system_identifier` + database identity + provisioning-target validation + write-sentinel), and explicitly rejects `system_identifier` alone as insufficient. This is the mechanism that makes "physical isolation" a proven property rather than a claim. **Port it.**

### A-4 — Import core (7 files / 866 ln)
`service.py` (the unit of work: tenant upsert + lineage emit + checkpoint advance **in one transaction** — commit-together / rollback-together), `validation.py` (mandatory pre-write floor: structural + type validation, injection-safe sanitisation, PII classification; errors carry field name + reason, never values), `models.py`, `ports.py`.

### A-5 — Lineage core (11 files / 913 ln)
`emit.py`, `canonical.py` (**single source of truth** for the marker — versioned, v1 frozen), `verification.py`, `query.py`, `search.py`, `graph.py`, `segmentation.py`, `retention.py`, `models.py`.

`canonical.py` is a small module carrying a large invariant: emit, verification and tests all compute the integrity marker through one function, so field-order can never drift. Port it verbatim in spirit.

### A-6 — Shared kernel (16 files / 1,369 ln)
`context.py` (`RequestContext`), `dto.py`, `errors.py`, `health.py`, `audit.py`, `lineage.py`, `session.py`, `secrets.py`, `queue.py`, `logging.py`, `config.py`, `portability/*` (profile / manifest / identity — the vendor-neutrality guard rails).

Maps onto Option A's `src/snackportal2/shared/{config,errors,logging,correlation,security,types}`. Note: correlation IDs exist today as a `correlation_id` field threaded through contexts and audit records, not as a dedicated module — Option A's `shared/correlation/` is a *new* home for existing behaviour.

### A-7 — Cross-cutting behaviours worth porting as *rules*, not files
- **Fail-closed everywhere.** Every denial path in routing, auth, provisioning and import defaults to deny/not-ready. No code path degrades open.
- **References only (D-14).** No DSN, credential, token, PII or payload appears in any audit row, DTO, log line or context. Enforced by `test_no_secret_literals.py`.
- **Consistent denial.** Unknown tenant and unauthorised tenant are indistinguishable at the edge — no existence leak.
- **Driver containment.** `psycopg` appears only under `database_router/adapters/providers/**` and `control_plane/adapters/providers/**`; `uvicorn` appears in exactly one module. Enforced by `test_vendor_and_db_containment.py`.

---

## 4. Schemas / migrations worth preserving — **Category B**

**29 SQL files / 30 tables**, in four families. All are portable standard PostgreSQL (no extensions), idempotent (`IF NOT EXISTS` / `CREATE OR REPLACE`), and transaction-safe (no `CREATE DATABASE`, no `CREATE INDEX CONCURRENTLY`, no `VACUUM`) — they satisfy the Option A data-safety rules as written.

### B-1 — Tenant business schema (`infrastructure/db/tenant/`, 8 files, 14 tables) — **preserve**
`agents`, `ai_agents`, `startups`, `investors`, `deals`, `startup_ownership`, `investor_ownership`, `deal_ownership`, `startup_ai_ownership`, `investor_ai_ownership`, `deal_ai_ownership`, `startup_contacts`, `investor_contacts`, `startup_investors`.

Key properties to carry forward:
- **No `tenant_id` column anywhere.** Tenancy is physical; one database per tenant.
- `global_startup_id` / `global_investor_id` are **soft text references** to Control-DB directory records — no cross-database FK is possible or allowed. This is the schema-level expression of *Global Record ≠ Tenant Record*.
- **System Primary** singleton per tenant: partial unique index + two CHECKs + a protective trigger blocking DELETE and kind-flip. Unassigned ownership = **row absence**, never a row pointing at System Primary.
- Claim = first-writer-wins `INSERT`; PK on `{entity}_id` makes "at most one human owner" a physical invariant.
- Tag fields are `jsonb` arrays, never `text[]`.
- `startups_global_startup_id_key` (008) is a **plain** unique index — deliberately not partial, because `ON CONFLICT` column-arbiter inference will not accept a partial index. Preserve that reasoning.

**Status caveat:** the tenant family is **created, NOT applied** to live tenant databases. It is applied only by onboarding Step-2b sequencing or the live-PG proof harness.

### B-2 — Control schema (`infrastructure/db/control/`, 15 files, 9 tables) — **preserve, with two edits**
`control_tenants`, `control_memberships`, `control_federation`, `control_directory`, `control_distinctness_ledger`, `control_audit`, `control_routing_audit`, `control_gateway_audit`, `control_import_audit`.

- All four audit tables are **append-only enforced in the database** (trigger rejects UPDATE/DELETE + TRUNCATE), not merely by convention.
- `control_tenants` deliberately stores `created_at`/`updated_at` as `text` (ISO-8601), not `timestamptz`, to match the store adapter's string round-trip. Re-decide this consciously in the rebuild rather than inheriting it by accident.
- No FKs between control tables (deliberate — store parity).
- **Two required edits for Option A:** `control_gateway_audit` (012/013) is pinned by `CHECK (source_service = 'api_gateway')` — see CONF-3; and `control_directory` lacks the `owner_agent_ref` column that IC-008 mandates for global records — see CONF-10.

### B-3 — Lineage schema (`infrastructure/db/lineage/`, 3 files, 5 tables) — **preserve**
`lineage`, `lineage_segment`, `import_job`, `import_idempotency`, `import_checkpoint`. Tenant-resident. Append-only trigger + `lineage_writer` / `lineage_reader` role separation with explicit `REVOKE UPDATE, DELETE, TRUNCATE`. Five supporting indexes.

### B-4 — Provisioning schema (`infrastructure/db/provisioning/`, 3 files, 2 tables) — **preserve**
`schema_version`, `dv_sentinel.marker` (the distinctness write-sentinel), plus the provisioning role grant. Underpins B-1's application and A-3's distinctness proof.

**Data-safety position for Phase 1+.** The rebuild changes code, not data. All four families are already reversible-friendly and disposable-DB-testable (`infrastructure/docker/docker-compose.local.yml` stands up a 4-cluster control/ACME/ZETA/NOVA topology on stock `postgres:17`). No destructive production-data change is proposed by this report.

---

## 5. Tests worth recreating — **Category C**

**2,054 passing stdlib/pytest tests** plus **28 standalone live-PostgreSQL evidence harnesses** (excluded from the default run via `addopts`).

| Suite | Tests | Disposition |
|---|---:|---|
| `tests/architecture` | 1,036 | **Recreate selectively** — see below |
| `tests/control_plane` | 411 | **Recreate** — registry, lifecycle, onboarding, provisioning, distinctness, recovery, audit, read API |
| `tests/api_gateway` | 262 | **Do not port** (Category D) — *except* the isolation/fail-closed/dispatch semantics, which must be re-homed |
| `tests/database_router` | 140 | **Recreate wholesale** — the closest match to Option A Phase 5's mandated proof set |
| `tests/auth_router` | 84 | **Recreate** — JWT validation, tenant context, disclosure, internal identity |
| `tests/shared` | 46 | **Recreate** — portability profile/manifest/identity |
| `tests/import_service` | 33 | **Recreate** — idempotency, checkpoint/resume, atomic provenance, validation |
| `tests/lineage_service` | 29 | **Recreate** — canonical marker, verification, graph, segmentation, retention |
| `tests/deployment` | 13 | **Do not port** — bound to the old 9-edge composition root |

### C-1 — Tests that directly discharge Option A's own acceptance criteria
Option A Phase 5 demands proof of: ACME→ACME DB, ZETA→ZETA DB, NOVA→NOVA DB, unknown tenant denied, ambiguous tenant denied, unavailable DB → controlled failure, no Control-DB fallback. These already exist:
`tests/database_router/test_routing_determination.py`, `test_resolution_and_gating.py`, `test_connection_isolation.py`, `test_connection_lifecycle.py`, `test_credentials.py`, `test_disclosure.py`, `test_capacity_lane.py`, `test_cache.py`, `test_end_to_end.py`; and live: `tests/control_plane/requires_pg/test_b3a_multi_database_topology.py`.

### C-2 — Architecture guards worth recreating (the ones that encode invariants, not the old topology)
- `test_dependency_boundaries.py` — service independence DAG
- `test_vendor_and_db_containment.py` — psycopg/uvicorn/vendor containment
- `test_no_secret_literals.py` — references-only discipline
- `test_audit_class_homes.py` — the closed audit taxonomy and its contract homes
- `test_tenant_ddl_schema_guards.py`, `test_tenant_ddl_blob_drift.py` — tenant schema integrity
- `test_lineage_role_static_security.py`, `test_provisioning_role_static_security.py` — DB role privilege separation
- `test_traceability.py` — code↔contract traceability
- `test_next_a_portability_boundaries.py` — vendor-neutrality profile

### C-3 — Architecture guards that must **not** be recreated
Roughly 35 of the 73 architecture guards are pinned to the old topology or to now-superseded governance episodes: the `test_b5_*`, `test_clm_*`, `test_dbr_ar_2*`, `test_07*`, `test_gateway_*`, `test_ic010_*`, `test_phase7_api_gateway.py`, `test_standing_launcher_flags.py`, `test_native_uvicorn_factories.py`, `test_deployment_composition_root_boundaries.py` families. They are valid evidence for the *old* build and should be read for intent, then discarded.

### C-4 — Live-PostgreSQL harnesses worth recreating (28 files)
Most valuable: `test_pg_tenant_business_schema_07c.py` (tenant DDL applied end-to-end), `test_pg_distinctness.py` + `test_pg_distinctness_ledger.py` (physical distinctness), `test_pg_control_schema_mcc.py`, `test_pg_append_only.py` + `test_pg_privilege.py` (lineage immutability + role separation), `test_pg_import_copy_durable.py`, `test_b3a_multi_database_topology.py`.

---

## 6. Old architecture that must **not** be ported — **Category D**

### D-1 — The API Gateway (mandated classification)
**`backend/api_gateway/` — 21 files / 3,327 lines production + 29 files / 6,142 lines tests.** Category D per Step 5 and Step 7. Not to be recreated, and not to be renamed to *FastAPI Gateway*, *BFF Gateway*, *Service Gateway*, *Routing Gateway* or *Compatibility Gateway*.

**However — four behaviours currently live *only* inside the Gateway and are load-bearing invariants. They must be re-homed, not dropped.** Discarding the package without re-homing these silently deletes enforcement:

| Behaviour | Current home | Required new home |
|---|---|---|
| `assert_single_database` / one-request-one-category-one-database | `api_gateway/dispatch.py` | Access Control + BFF (Option A Phase 3/6) |
| `RequestContext` built **exclusively** from `AuthContext`; no inbound tenant/workspace parameter may reach the router | `api_gateway/request_context.py` | BFF (Phase 6) — this is D-33 §4.6, explicitly load-bearing |
| Carrier extraction + prohibited-carrier rejection (only `X-Tenant-Id` and subdomain recognised; cookies/query/workspace/local-storage prohibited as routing authority) | `api_gateway/carrier.py` | BFF (Phase 6) |
| The `§J` audit emit-set (CarrierMismatch, CarrierOnControlAnomaly, RouteDenied, IsolationAnomaly + three success-access actions) | `api_gateway/gateway.py` + audit emitter | Audit Service (Phase 8) |

The portal DTO catalogue (`api_gateway/portal.py`, 256 ln) is IC-009-owned content in a Category-D container — port the *DTO definitions*, discard the container.

### D-2 — The `deployment/` composition root
`backend/deployment/` (2 files / 171 ln) plus `tests/deployment/` (13 tests) and the IC-012 import-linter contracts that police it. Purpose-built for the old nine-edge topology; superseded by Option A's `src/snackportal2/services/*` layout.

### D-3 — The nine-edge internal HTTP topology
Eight internal loopback edges + `SP2_*` selector env vars + `shared/adapters/providers/fastapi_edge.py` + `asgi_runtime.py`. The *pattern* (one process per service, factory-based app construction, five pinned uvicorn flags) is worth keeping as an operational rule; the *specific wiring* is not.

### D-4 — The `main.py` composition-seam convention
Every existing `main.py` is a **dependency-injection composition seam with no FastAPI app** — `grep` confirms zero `app = FastAPI()`, zero `uvicorn.run`, zero `__main__` blocks across all six. Option A §4 requires the opposite. This is a naming collision that will confuse Phase 1 if not called out now: **do not port any existing `main.py`.**

### D-5 — The governed launcher
`backend/tools/local/start-sp2-local.ps1` (540 ln) — binds the Gateway on port 8820, wires nine `SP2_GW_*` selectors, and carries an 8080 collision advisory. Category D. *But* its five canonical uvicorn flags (`--factory --workers 1 --no-access-log --no-server-header --no-proxy-headers`) encode real security posture that Option A's `uvicorn.run(host="0.0.0.0", reload=True)` sample would regress — see CONF-9.

### D-6 — Gateway-specific runbooks and audit plumbing
`infrastructure/runbooks/{gateway_edge_v1_serve,gateway_operational_audit_live_proof,aw1_gateway_audit_writer}.md`; `api_gateway/adapters/providers/durable_audit_emitter.py`; the `control_gateway_audit` wire contract on the Control-Plane side.

---

## 7. Obsolete / deprecated material — **Category E**

| Item | Why |
|---|---|
| `backend/build/` | setuptools artefact left by `pip install .[dev]`; already `mypy`-excluded. Not source. |
| `backend/.mypy_cache/`, `.ruff_cache/`, `.import_linter_cache/` | Tooling caches committed into the tree |
| `SP2_ROGUE_KEY`, `SP2_NEW_KNOB`, `SP2_LOCAL_MVP_01`, `SP2_TENANT_T1` | Test/fixture-only env names with no production meaning |
| `docs/PROJECT-HANDOVER-PHASE-4.md`, `PROJECT-HANDOVER-PHASE-6.md` | Superseded by `PROJECT-HANDOVER-MASTER.md` |
| `docs/Phase-{1..6}-Acceptance-Criteria.md`, `Phase-1-{Implementation-Plan,Traceability-Matrix,Governance-Standards}.md` | Acceptance criteria for the *old* build phases; historically valuable, not normative for Option A |
| `infrastructure/runbooks/b5_*`, `clm_*`, `dbr_ar_2_*`, `controlled_*` (11 of 17) | Bound to superseded governance episodes and the old topology |
| `infrastructure/runtime/b5_activation_gate.template`, `b6_provisioning_audit_sink.template` | Gate templates for build phases that Option A replaces |
| `docs/SnackPortal2_PRD_Index.md` B-7 row | Describes the Gateway as the build target; stale under Option A |
| Stale `IMPLEMENTS_BEHAVIOR`/status prose in `CLAUDE.md` | `CLAUDE.md` on `main` still names the API Gateway as an architecture component and cites IC-010 as governing |

**Not obsolete despite appearances:** the `docs/D-*` decision packs. D-01 through D-44 are the *reasoning record* behind almost every invariant in §10 and §11. Read them; do not delete them.

---

## 8. Unclear items requiring Dan's decision — **Category F**

Twelve items. **CONF-1 is blocking.** The rest are scoping or conflict-resolution decisions that will change what Phase 1 builds.

### **CONF-1 — BLOCKING — a Final contract mandates the thing Option A forbids**
`contracts/IC-010-API-Gateway-Contract.md` is **Status: Final**. Its Purpose states: *"Define the **API Gateway** as the **sole approved ingress** into SnackPortal2 services."* Canonical Overview locked invariant **#7** states: *"The Gateway is the boundary — frontend → Gateway, never directly to DB/auth/router."* `CLAUDE.md` architecture constraint **#5** states: *"Contracts precede code. New behavior requires a contract (new or amended) first."*

Option A mandates `0 API Gateway runtime / 0 Gateway package / 0 Gateway routes`. **On `main`, no artefact supersedes IC-010 or retires invariant #7.** (The D-45 / IC-013 / IC-014 work that did exactly this exists only on the abandoned `phase/00-architecture-ratification` branch, which this instruction excludes as an implementation base.)

Under this repository's own governance, Phase 1 cannot lawfully begin until IC-010 is amended or superseded and invariant #7 is formally retired on the record.

**Options for Dan:**
- **(a) Contract-first gate (recommended).** Insert a Phase 0.5 on this branch that *freshly authors* — not cherry-picks — the IC-010 supersession, the BFF ingress contract, and the Access Control contract. Then Phase 1.
- **(b) Explicit governance waiver.** Ratify in writing that Option A supersedes IC-010 and invariant #7, and that contract reconciliation trails implementation. This knowingly suspends constraint #5.
- **(c) Selectively re-derive from the abandoned branch.** Read D-45/IC-013/IC-014 for content, re-author them on this branch. Requires your explicit request (Step 2 forbids cherry-picking without it).

### CONF-2 — IC-009 portal DTOs are contractually *gateway-composed*
IC-009 (**Final**) DTOs are composed under IC-010 §V Response Composition, and `api_gateway/portal.py` names `IC-009-R1` as the seam it serves. If the BFF composes them, IC-009's composing-seam identity must be re-pointed. **Decision:** amend IC-009's seam reference, or re-author the DTO catalogue under a new contract.

### CONF-3 — The Control database physically rejects a non-Gateway audit emitter
`infrastructure/db/control/012_gateway_operational_audit.sql:69` — `CHECK (source_service = 'api_gateway')`. A BFF-emitted audit row is rejected by PostgreSQL. Compounding: DDL 012/013 are **byte-pinned** by `test_b7c1_control_audit_ddl_blob_pins.py` and `test_b7c1r2_control_ddl_pin_completeness.py`, so the file cannot be edited without also retiring those guards. **Decision:** author control migration 016 (new table or relaxed CHECK) and retire the byte-pins, or accept the table as historical and give the Audit Service a new table.

### CONF-4 — Ownership cardinality and representation disagree three ways
| Source | Human owner | AI owner |
|---|---|---|
| IC-008 (**Final**) + D-36 | **exactly one** `owner_agent_ref` **on the record** | **at most one** nullable `owner_ai_agent_ref`, **NULL platform-wide until IC-006** |
| Tenant DDL `006_ownership.sql` | **at most one**, in a separate `{entity}_ownership` table (PK = entity id); exactly-one deferred to runtime | **zero or more distinct**, composite-PK `{entity}_ai_ownership` join tables |
| Canonical Overview invariant #3 | "exactly one human owner" | "**and one AI owner**" |

Three cardinalities, two representations (field vs join table), one of them (`invariant #3`) marked *locked*. **Decision:** which shape is normative for the rebuild? This determines the Startup/Investor/Deal schema in Phase 7.

### CONF-5 — Option A Phase 9 builds AI against a deferral and an empty contract
Phase 9 specifies an AI Agent Service with ten named skills. But **D-02** decided *"Defer AI to post-MVP"*, **D6** is formally Deferred with an explicit **do-NOT-build list** (do not create `control_ai_*`, do not wire `ai.invoke`, do not add AI outreach flows), and **IC-006** is a Draft placeholder in which *every* normative section — API contract, DTOs, authN, authZ — reads `TBD`. **Decision:** does Option A reopen D6? If yes, IC-006 must be authored before Phase 9, and the Part 4B governance gate ("compliance/permissions review is a prerequisite, not an afterthought") applies.

### CONF-6 — Option A Phase 8 builds Sharing against a Draft contract
IC-007 is **Draft / Proposed** with **no positive sharing capability**. IC-010's fifth dispatch category is explicitly *"authored-but-inert until IC-007 is Final."* Action Tracker #23 already names IC-007 promotion as a prerequisite. **Decision:** promote IC-007 to Final before Phase 8, or descope Sharing from the rebuild.

### CONF-7 — Contacts has no contract
Option A's service census names a Contacts Service. There is no Contacts contract (Action Tracker #22 already flags this). Only DDL `007_links.sql` exists — which explicitly states these are **contact records, not user tables**, and that `startup_users` / `investor_users` **must not** exist. **Decision:** author the Contacts contract before Phase 7.

### CONF-8 — `main.py` convention breaks the uvicorn containment guard
Option A §4 puts `app = FastAPI()` + `uvicorn.run(...)` in every service's `main.py` — 14 uvicorn import sites. The existing build deliberately confines uvicorn to **exactly one** module (`shared/adapters/providers/asgi_runtime.py`), enforced by `test_vendor_and_db_containment.py`, precisely so the concrete ASGI server stays inside a sanctioned containment zone. **Decision:** keep containment (app factory + external uvicorn CLI, as today) or accept 14 import sites and retire the guard.

### CONF-9 — The Option A startup sample is a security-posture regression
The sample is `uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)`. Today's governed launcher pins five flags because *"omitting one silently restores uvicorn's default"* — `access_log=True` and `server_header=True` both leak, and `0.0.0.0` is an all-interfaces bind versus today's loopback. **Decision (recommended: adopt the pins):** carry `--workers 1 --no-access-log --no-server-header --no-proxy-headers` and a loopback default into the new convention.

### CONF-10 — Global directory gaps
- **No Global Investor Contract** (Action Tracker #19) though `DirectoryKind.INVESTOR` exists in code.
- **D-35 ratified a Global Deal Directory** in the Control DB; `DirectoryKind` has no `DEAL` member and no DDL exists.
- **IC-008 mandates `owner_agent_ref` on every global directory record**; `control_directory` (DDL 007) has no such column.

**Decision:** author the missing contracts and the corresponding control migration, or descope.

### CONF-11 — IC-012 governs a composition root Option A replaces
IC-012 (Draft / Proposed) governs `backend/deployment/` as the one authorised cross-service composition root, machine-enforced by four import-linter contracts. Option A's layout replaces it. **Decision:** re-scope IC-012 to the new `deployment/`, or retire it.

### CONF-12 — Frontend/backend surface gap (a scoping decision, not a defect)
The frontend expects **86** server-function operations (§9). The backend serves **3**. Option A Phase 10 cutover assumes a parity that does not exist and cannot exist without building Investor, Deal, Contacts, Sharing, Notifications, Search, Documents and Preferences surfaces. **Decision:** define the Phase 10 cutover as *partial* (which screens cut over first), or accept that Phase 10 is gated on Phase 7+8 completing a much larger surface than the current backend implies.

---

## 9. Frontend / backend dependency inventory

The frontend is a **separate repository** (`snack-cosmos`), not present in this repo. Inventory taken from the local working copy `D:\Pitchsnack\snack-cosmos-gateA-postmerge`.

### 9-A — The real backend seam today: 3 operations
`src/lib/sp2/gateway-client.ts` calls exactly three paths:

| Frontend call | Backend route | DTO |
|---|---|---|
| `GET /memberships` | Gateway edge → MembershipsForPrincipal | `WorkspaceMembershipDTO` |
| `GET /tenant/startups/{ref}` | Gateway edge → DB Router tenant-startup read | `TenantStartupDetailDTO` |
| `PATCH /tenant/startups/{ref}` | Gateway edge → DB Router tenant-startup update | `TenantStartupUpdateRequestDTO`, `SHORT_DESCRIPTION_MAX = 500` |

Supporting modules: `auth-adapter.ts`, `keycloak-auth-adapter.ts`, `mock-auth-adapter.ts`, `mock-gateway.ts`, `auth-context.tsx`, `dto.ts`, `tenant-journey.ts`.

### 9-B — The interim Supabase seam: 21 modules / 86 exported server functions
This is the **behavioural requirement inventory** for the rebuild — what the product actually needs the backend to do.

| Module | Fns | Module | Fns |
|---|---:|---|---:|
| `deals.functions.ts` | 11 | `notifications.functions.ts` | 4 |
| `startups.functions.ts` | 10 | `preferences.functions.ts` | 4 |
| `investors.functions.ts` | 9 | `deal-introductions.functions.ts` | 4 |
| `deal-shares.functions.ts` | 8 | `auth.functions.ts` | 3 |
| `global-startups.functions.ts` | 7 | `search.functions.ts` | 3 |
| `users.functions.ts` | 4 | `startup-ownership.functions.ts` | 3 |
| `deal-documents.functions.ts` | 2 | `deal-ownership.functions.ts` | 2 |
| `investor-ownership.functions.ts` | 2 | `investor-users.functions.ts` | 2 |
| `startup-users.functions.ts` | 2 | `security.functions.ts` | 2 |
| `session-context.functions.ts` | 2 | `tenants.functions.ts` | 1 |
| `workspace.functions.ts` | 1 | | |

**Total: 86.** Every one of these is currently served by Supabase with logical (`tenant_id` + RLS) isolation — the confirmed DRIFT-01 that D3/D7 mark as interim.

### 9-C — Frontend-visible backend contracts that the rebuild must honour
- Auth is **Keycloak OIDC + PKCE** (`keycloak-auth-adapter.ts`), bearer-attached.
- The memberships envelope decode is **fail-closed** (corrected in `snack-cosmos` PR #4).
- `short_description` ≤ 500 chars is a *shared* constant — backend `tenant_startup_ops.py` and frontend `dto.ts` both enforce it.
- The frontend never talks to a database directly; the RPC seam is the cutover point.

---

## 10. Tenant / database invariants — evidence found

### INV-1 — `Authentication ≠ Access Control ≠ Tenant Routing ≠ Database Access`
**Three of four boxes exist and are cleanly separated. The Access Control box has never been built.**

| Box | Evidence |
|---|---|
| Authentication | `auth_router/__init__.py:7` — *"no database routing, no tenant-DB access, and **no permission evaluation**"*; `tenant_context.py` — *"MUST NOT read tenant databases, route, or store sessions"* |
| Access Control | **NO EVIDENCE.** No permission/authorization/policy-engine class exists in production code (verified by exhaustive grep). `control_plane/membership.py` — *"Roles stored, **never evaluated**"* |
| Tenant Routing | `database_router/router.py` — *"performs NO authentication, authorization, import, or lineage… the single active tenant is taken from the signed claim — **never re-derived**"* |
| Database Access | `database_router/main.py` — *"This is the **ONLY** service permitted to open tenant databases"*; psycopg containment enforced by `test_vendor_and_db_containment.py` |

Machine-enforced by four import-linter contracts (`shared` is a leaf; services are mutually independent; nothing imports `deployment`; `deployment` may compose only the authorised set).

### INV-2 — `One Request → One Active Tenant → One Physical Database`
- `api_gateway/dispatch.py`: `decide()` resolves **exactly one** `DispatchCategory` → **one** `DatabaseDomain`; `assert_single_database()` is the hard check. Dispatch consumes *no* tenant/workspace/ownership selector — the route is never a client-controlled routing channel.
- `database_router/pool.py`: pools keyed on `(tenant_id, association_version)` — *"separate keyed pools make a cross-tenant borrow **structurally impossible**"*.
- **No Control-DB fallback exists.** `disclosure.denial_for_state` maps lifecycle → canonical denial; there is no code path from "tenant DB unavailable" to "use Control DB".
- MASTER_AGENT fan-out is structurally impossible: one signed active tenant, no API to address a second (IC-009 P.4).
- **Caveat:** the enforcement point lives in the Gateway (Category D). Re-home it — see §6 D-1.

### INV-3 — `Global Record ≠ Tenant Record`
- `control_plane/directory.py`: *"Global Record != Tenant Record. No tenant copies, no import processing, no synchronization, no lineage."*
- Tenant DDL 003/004: `global_startup_id` / `global_investor_id` are **soft text refs** — *"no cross-database FK is possible or allowed"*; *"tenant records are independent copies… tenant edits never mutate Control directory rows."*
- D-31: global directories reside in the Control DB, absolutely.

### INV-4 — `Import ≠ Synchronization`
- IC-010 Import Rule: *"MUST NOT introduce synchronization, automatic/scheduled/background/event-triggered/timer-driven re-import, shared ownership, or cross-database updates — regardless of how individually lawful each underlying call would be."*
- `import_service/service.py`: one explicit user-initiated unit of work; idempotent upsert + lineage + checkpoint in **one transaction**.
- D-34 governs re-import; tenant DDL 008 provides the unique arbiter so retries collapse into one tenant copy.
- Tests: `test_idempotency.py`, `test_checkpoint_resume.py`, `test_atomic_provenance.py`.

### INV-5 — `Sharing ≠ Ownership ≠ Tenant Transfer ≠ Deal Duplication`
**Preserved by absence, not by mechanism.** IC-007 Draft/Proposed; zero sharing code; zero sharing DDL (tenant DDL 005 states this explicitly and deliberately). IC-008 V7: *"Cross-tenant ownership is impossible."* Guard: `test_ic007_governed_sharing_contract_boundaries.py`. When Phase 8 builds Sharing, this invariant acquires its first real enforcement surface — and its first real risk.

### INV-6 — `AI Skill ≠ Permission ≠ Tenant Access ≠ Database Routing`
**No runtime evidence.** Artefacts only: tenant DDL 002 (`ai_agents` is tenant-local, mandatorily supervised, explicitly *not* a Control global registry, not seeded at bootstrap), `*_ai_ownership` tables, and IC-008's reserved `owner_ai_agent_ref` held NULL platform-wide. The Part 4B reservations (`control_ai_*` cluster, `CONTROL_AI` role, `ai.invoke` gate, AI audit class) are **named and deliberately unbuilt**. The separation is asserted by contract, never implemented or tested. See CONF-5.

---

## 11. Security responsibility boundaries

| Responsibility | Owner today | Owner under Option A | Gap |
|---|---|---|---|
| Token validation (signature, alg allowlist, claims) | `auth_router` Stage 1 | Authentication Service | Port |
| Tenant-context establishment from signed claim | `auth_router` Stage 2 | Authentication Service | Port |
| Carrier match / prohibited-carrier rejection | **Gateway** (`carrier.py`) | BFF | **Re-home** |
| `RequestContext` construction from `AuthContext` only | **Gateway** (`request_context.py`) | BFF | **Re-home** (D-33 §4.6, load-bearing) |
| Single-database assertion per request | **Gateway** (`dispatch.py`) | Access Control + BFF | **Re-home** |
| Role / permission evaluation | **NOBODY** | Access Control Service | **GREENFIELD** |
| Ownership evaluation | **NOBODY** (IC-008: ownership never authorizes) | Access Control Service | **GREENFIELD** |
| Record-residency evaluation | Implicit in routing | Access Control Service | **GREENFIELD** |
| AI permission / tool entitlement | **NOBODY** | Access Control Service | **GREENFIELD** |
| Tenant→physical-DB resolution | `database_router` | Database Router | Port |
| Tenant credential resolution | `database_router` at connect time | Database Router | Port |
| Physical distinctness proof | `control_plane/distinctness.py` | Control Plane | Port |
| Audit emission (4 classes, append-only) | Distributed across 4 services | Audit Service | Consolidate — see CONF-3 |
| Secret handling | `shared/secrets.py` + `EnvReferenceSecretStore`, references only (D-14) | shared/security | Port |

**The critical security finding.** Option A's Phase 3 Access Control Service is the largest genuinely greenfield component in the rebuild. Today, authorization is a *distributed implicit property*: identity checks in `auth_router`, membership storage in `control_plane`, edge role-gating in the Gateway, and residency enforcement as a side-effect of routing. Nothing evaluates a permission. Extracting this into a service that must answer Allowed/Denied over role + permission + membership + ownership + action + residency + AI entitlement is **new design work with no existing implementation to port from** — only IC-005, IC-008, IC-009 and D-32 as inputs.

A second, subtler point: the Gateway is not only a router — it is a **privilege boundary**. It is the only public surface, and it is what prevents the public tier from reaching tenant DSNs. Removing it without the BFF and Access Control Service standing in that position first would widen the blast radius, not narrow it. Option A's phase ordering (Authentication → Access Control → Router → *then* BFF) is correct on this point and should not be reordered.

---

## 12. Gateway dependency census

| Dimension | Count | Detail |
|---|---:|---|
| Gateway packages | **1** | `backend/api_gateway/` — 21 files, 3,327 lines |
| Gateway test files | **29** | `backend/tests/api_gateway/` — 6,142 lines, 262 tests |
| Gateway-named architecture guards | **8** | `test_gateway_edge_boundaries`, `test_gateway_operational_audit_boundaries`, `test_phase7_api_gateway`, `test_ic010_response_composition_contract`, `test_ic010_control_read_adapter_boundaries`, `test_aw1_gateway_audit_writer_boundaries`, `test_ic009_portal_binding_checks`, `test_b5_blk6_portal_binding_live_proof_boundaries` |
| Public Gateway routes | **5** | `/memberships`, `/import/{source_ref}`, `/tenant/startups/{startup_ref}`, `/health`, `/readiness` |
| Gateway ports bound | **1** | 8820 (standing); 8080 carried as a collision advisory |
| Gateway env selectors | **9** | `SP2_GW_{AUDIT_SINK_BASE_URL, AUTH_ROUTER_BASE_URL, CONTROL_READ_BASE_URL, DB_ROUTER_BASE_URL, EDGE_ALLOWED_ORIGINS, EDGE_HOST, EDGE_PORT, IMPORT_BASE_URL, TENANT_STARTUP_BASE_URL}` |
| Gateway launchers | **1** | `backend/tools/local/start-sp2-local.ps1` |
| Gateway runbooks | **3** | `gateway_edge_v1_serve.md`, `gateway_operational_audit_live_proof.md`, `aw1_gateway_audit_writer.md` |
| **Hard Python imports of `api_gateway` from other production packages** | **0** | Verified by exhaustive grep — **the package is import-isolated** |
| Database-level Gateway pins | **2** | DDL 012 `CHECK (source_service = 'api_gateway')`; DDL 013 append-only trigger on the same table |
| Wire-level Gateway couplings | **2** | `control_plane/.../http_gateway_audit_api.py` (accepts only the wired gateway-edge action set); `database_router/.../http_dispatch_api.py` (copies `DispatchCategory` verbatim from `api_gateway/models.py`) |
| `database_router` edges built *for* the Gateway | **1** | `http_tenant_startup_api.py` exists solely to serve the Gateway's tenant Startup seam |
| Documentation occurrences (`docs/`) | 430 lines / 73 files | Historical; retain, mark historical |
| Contract occurrences (`contracts/`) | 169 lines / 11 files | **Normative** — IC-010 is Final; see CONF-1 |

**The decisive census result:** **zero hard Python imports.** The Gateway is import-isolated behind ports, so deleting the package breaks no other service at import time. The real coupling is at four points, all addressable: (1) the **contract layer** (CONF-1, blocking), (2) the **database CHECK constraint** (CONF-3), (3) the **wire vocabularies** in two adapter modules, and (4) the **four load-bearing behaviours** that must be re-homed rather than dropped (§6 D-1).

---

## 13. Risks and migration concerns

**RISK-1 — Scope reality (highest).** Option A rebuilds **14 services**. Today's backend implements **7 packages serving 3 public operations**, and the frontend expects **86**. The rebuild is not a port; it is a port *plus* the majority of the product surface (Investor, Deal, Contacts, Sharing, Notifications, Search, Documents, Preferences), *plus* a greenfield Access Control Service, *plus* an AI Agent Service with no contract. The stated target of end-July 2026 in the Canonical Overview is already past. **Recommend an explicit re-plan before Phase 1.**

**RISK-2 — Silent invariant loss.** Four load-bearing behaviours live only in the Category-D Gateway (§6 D-1). "Delete the Gateway" without "re-home these four" is a security regression that no test would catch, because the tests that prove them are themselves Category D. **Mitigation:** make re-homing an explicit Phase-1 acceptance item, not a Phase-6 side-effect.

**RISK-3 — Governance inversion.** This repository's constraint #5 is *contracts precede code*. Option A proposes ten implementation phases against contracts that are Final-and-contradictory (IC-010), Draft (IC-007, IC-011, IC-012), or empty placeholders (IC-006). Proceeding without CONF-1 resolved means the rebuild's own governance model is violated from Phase 1 line 1.

**RISK-4 — Test-evidence cliff.** 2,054 tests pass today. A clean rebuild starts at 0 and, by Option A's own final-acceptance list, must end with architecture *and* business-behaviour tests passing. Roughly **1,036 architecture guards** encode invariants; about a third are topology-bound and worth discarding, but the remainder represent months of accumulated proof. Budget for re-authoring them, and re-author them *as the services land*, not at the end.

**RISK-5 — Data safety.** The tenant business schema is **created, not applied** — meaning tenant DDL has never run against a live production tenant DB. That is good news for the rebuild (no production tenant data to migrate for those 14 tables) but it also means the schema's live behaviour is proven only by the `requires_pg` harnesses, not by production use. Verify against disposable databases first (`docker-compose.local.yml` stands up the 4-cluster topology), exactly as Option A's data-safety section requires.

**RISK-6 — Two conflicting sources of truth on ownership** (CONF-4). Building Startup/Investor/Deal in Phase 7 against the wrong shape means re-doing the tenant schema and its ownership semantics later. Resolve before Phase 7.

**RISK-7 — Security posture drift** (CONF-9). The Option A startup sample would, if copied literally into 14 services, re-enable uvicorn access logs and `Server:` headers and bind all interfaces. Small change, wide blast radius.

**RISK-8 — Branch/worktree hygiene.** Nine git worktrees and multiple detached `snack-cosmos` copies exist on this machine. `phase/01-fastapi-runtime-foundation` already exists at `cdb46fc9d` (the same base as this branch) — confirm with Dan whether that is the intended Phase 1 home or a stale artefact before Phase 1 starts.

---

## 14. Recommended Phase 1 starting point

**Recommendation: insert a short contract-reconciliation gate (Phase 0.5) before any Phase 1 code, then start Phase 1 in a specific order.**

### Phase 0.5 — Contract reconciliation (blocking, ~1 focused session)
1. **Supersede IC-010** — author the successor that removes "sole approved ingress" and re-homes §E carrier rules, §G/§T `RequestContext` construction, §K/§O single-database assertion and §J audit emit-set to the BFF / Access Control / Audit services. Author it **fresh on this branch**; do not cherry-pick.
2. **Retire locked invariant #7** on the record in the Canonical Overview.
3. **Open the BFF ingress contract** and the **Access Control contract** — these are the two services with no contract and the most enforcement responsibility.
4. **Resolve CONF-4** (ownership shape) — it gates Phase 7 schema.
5. **Rule on CONF-5 and CONF-6** (does Option A reopen D6? is IC-007 promoted?) — these decide whether Phases 8 and 9 are in scope at all.

### Phase 1 — Clean FastAPI runtime foundation, in this order
1. **`shared/` first.** Seed from the existing `shared/` core (16 files / 1,369 ln): `context`, `errors`, `dto`, `health`, `audit`, `lineage`, `session`, `secrets`, `logging`, `config`, `portability`. Add the new `correlation/` module Option A calls for (correlation IDs exist today as a threaded field, not a module).
2. **Service skeletons for all 14**, each independently bootable with health/readiness. Decide CONF-8 first (uvicorn containment vs 14 import sites) — it changes what `main.py` looks like in every one of them.
3. **Baseline architecture tests immediately**, not later: the dependency DAG (import-linter, adapted from the four existing contracts), driver/vendor containment, references-only discipline, and a **zero-Gateway census guard** that fails on `api_gateway`, `gateway`, `http_gateway`, `gateway_edge` outside explicitly-marked historical documentation.
4. **Then the Database Router** (Option A Phase 5) — not because it is next in Option A's numbering, but because it is the one component that already fully satisfies its target contract, carries the strongest test evidence (140 tests + live-PG topology proof), and every other service depends on its session seam. Porting it early de-risks Phases 7 and 8. *(Authentication and Access Control still precede the BFF, per Option A's ordering, which is correct.)*

**Phase 1 acceptance, restated concretely:** every service boots independently; `grep -riE "api_gateway|gateway_edge|http_gateway"` over `src/` returns **0**; the four import-linter contracts pass; the four re-homed Gateway behaviours from §6 D-1 have named owners in the new code (even if not yet implemented).

---

## Summary table

| Category | Count / Scope | Notes |
|---|---:|---|
| **A. Business logic worth porting** | **79 files / 10,137 lines** (6 core packages) | Framework-agnostic domain cores: Database Router (12/1,669), Control Plane (25/4,584), Auth (8/736), Import (7/866), Lineage (11/913), shared (16/1,369). No FastAPI, no HTTP — ports only, so they lift cleanly. |
| **B. Schema / migration items** | **29 SQL files / 30 tables** | Tenant 8 files/14 tables · Control 15/9 · Lineage 3/5 · Provisioning 3/2. All portable standard PostgreSQL, idempotent, transaction-safe. Two required edits: DDL 012/013 gateway CHECK (CONF-3), `control_directory.owner_agent_ref` (CONF-10). Tenant family is **created, not applied**. |
| **C. Tests worth recreating** | **743 service tests** + a selected subset of the **1,036** architecture guards (~38 of 73 guard files) + **28 live-PG harnesses** | Recreate: DB Router 140, Control Plane 411, Auth 84, shared 46, Import 33, Lineage 29. Discard outright: 262 Gateway, 13 deployment, ~35 topology-bound guard files. |
| **D. Old architecture not to port** | **23 files / 3,498 lines** production (+ `fastapi_edge.py`, 105 ln) + **31 test files / 6,776 lines** + 9 env selectors + 1 launcher + 3 runbooks | `api_gateway/` (21/3,327) + `deployment/` (2/171); all `main.py` composition seams; the 9-edge internal topology. **0 hard Python imports** from other services — import-isolated. **4 load-bearing behaviours must be re-homed, not dropped.** |
| **E. Obsolete / deprecated** | **~25 items** | Build artefacts + 3 tool caches; 4 fixture-only env names; 2 superseded handovers; 9 old phase-acceptance docs; 11 of 17 runbooks; 2 runtime gate templates; stale `CLAUDE.md` / PRD-Index status prose. |
| **F. Unclear / requires review** | **12 conflicts — 1 BLOCKING** | CONF-1 IC-010 Final = "sole approved ingress" (**blocks Phase 1**) · CONF-2 IC-009 gateway-composed DTOs · CONF-3 DB `CHECK (source_service='api_gateway')` · CONF-4 ownership cardinality ×3 · CONF-5 AI vs D-02/D6 deferral + empty IC-006 · CONF-6 Sharing vs Draft IC-007 · CONF-7 no Contacts contract · CONF-8 uvicorn containment · CONF-9 `0.0.0.0`/`reload`/flag regression · CONF-10 global directory gaps · CONF-11 IC-012 scope · CONF-12 3-vs-86 frontend surface gap. |

---

## Closing statement

Phase 0 discovery is complete. The existing backend is a **strong requirements source and a weak architecture**: its domain cores, database schemas and invariant proofs are genuinely worth carrying forward, while its ingress topology, composition roots and Gateway are correctly classified as old architecture.

Two findings dominate everything else. First, **CONF-1**: a Final contract (IC-010) and a locked invariant (#7) currently mandate the very component Option A forbids, and nothing on `main` supersedes them — so under this project's own governance, Phase 1 cannot lawfully begin until that is resolved. Second, **the Access Control Service is genuinely greenfield**: nothing in the existing codebase evaluates a permission, so the single most security-critical service in the target architecture has no implementation to port from.

**No Phase 1 implementation has started. No old backend code was deleted. No merge has been performed. No branch was pushed.**
