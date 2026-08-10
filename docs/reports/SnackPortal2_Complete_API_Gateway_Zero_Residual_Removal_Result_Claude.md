# SnackPortal2 — Complete API Gateway Zero-Residual Removal — Result

**Instruction:** `SnackPortal2_Complete_API_Gateway_Zero_Residual_Removal_GPT.md`
**Branch:** `experiment/complete-api-gateway-removal-mvp`
**Base:** `main` = `cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f` (unchanged)
**Date:** 2026-08-11 · **Author:** Claude (Opus 5)

---

## VERDICT

```text
COMPLETE API GATEWAY ZERO-RESIDUAL REMOVAL PASS WITH FROZEN HISTORICAL/DDL RESIDUALS
```

**The API Gateway is gone, not merely unlaunched.** The package, its two Gateway-only internal
transports, its port, its launcher entry, its environment family, its dispatcher, its tests and its
guards are deleted. 27 of 27 executed zero-residual checks pass, including a clean-subprocess
composition of both public edges that loads **zero** `api_gateway` modules and an executed
`import api_gateway` that fails with `ModuleNotFoundError`.

**Read the verdict with its two qualifiers, both of which are load-bearing.**

1. **Frozen residuals remain, by design and out of authority.** DDL 012 pins
   `CHECK (source_service = 'api_gateway')`. That literal therefore survives as one runtime
   constant, and the durable audit store's naming stays aligned with the frozen table
   `control_gateway_audit` and the frozen AW-1 SecretRef `control/gateway-audit-writer-dsn`. This
   task holds no DDL and no SecretRef authority; changing either name without the artifact would
   have created drift, not removed it. Full list in §15.

2. **⚠️ THE REMOVAL IS NOT ADOPTABLE UNTIL CONTRACTS ARE RATIFIED.** `IC-010 — API Gateway
   Contract` is **Final** and still says the Gateway is the *sole approved ingress* (§A), that
   *"No alternate flow is permitted"* (§C), and that portals MUST reach services *"only through the
   API Gateway"* (§I/§M/§N). IC-011 §Gate names it the *sole served ingress* as an EXPECTED
   condition and a non-Gateway served edge as a **STOP** condition — the two-public-edge topology
   trips that by construction. **This branch's code contradicts a Final contract.** I did not amend
   the contracts: CLAUDE.md says contracts precede code and amending a Final interface contract is
   a human governance act. The exact amendment set is §18. **This is the single blocker before any
   merge is even discussable**, and no gate result in this document substitutes for it.

Nothing was pushed, no PR was opened, nothing was merged, and `main` is byte-identical to its
pre-task state.

---

## 1. Exact branch / base / head identity

| Item | Value |
|---|---|
| worktree | `D:\Pitchsnack\SnackPortal2_pr111_verify` |
| branch | `experiment/complete-api-gateway-removal-mvp` |
| `git rev-parse main` | `cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f` |
| `git merge-base main HEAD` | `cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f` |
| HEAD **before** this task | `8719f4f3da7db5dffda99a6bca00edd078340d0d` |
| HEAD **after** this task | `2bdb58768` (this document is committed on top of it) |
| commits added | **4** — `172edf2d9` *delete the API Gateway completely (zero active residue)* and `2bdb58768` *close the defects an independent adversarial review found*, `c1923d46` *result document*, `e0d1f61` *close the four CONFIRMED verify-phase findings* |
| working tree | clean |

`8719f4f3` is the reference point used throughout this document: every "before" figure and every
recovered deleted file is `git show 8719f4f3:<path>`.

**Change composition of `172edf2d9`:** 140 files, **+2,701 / −22,976** — 66 deleted, 2 added, 2 renamed, 70 modified.
**`2bdb58768`:** 19 files, the adversarial corrections in §12.

---

## 2. Complete pre-removal Gateway reference census

Captured **before any edit**, case-insensitively over all tracked files, for every §4 pattern
(`api_gateway`, `API Gateway`, `gateway`, `8820`, `SP2_GW_`, `VITE_*GATEWAY*`, `create_gateway`,
`build_gateway`, `serve_gateway`, `Gateway`, `RouteDenied`, `ClmDurableAuditPartition`,
`GATEWAY_AUDIT`, `http_gateway_edge`):

> **3,440 matches across 276 tracked files** (of 613 tracked files total).

A six-way independent classification pass plus a completeness critic was run over that census
before deletion began. Its two most consequential findings shaped the plan:

* **ZERO production modules import `api_gateway`.** Verified with
  `git grep -nE "^[[:space:]]*(from|import)[[:space:]]+api_gateway" -- . ':!backend/api_gateway' ':!backend/tests/api_gateway'`
  — the only non-test hit was a **comment** at `http_dispatch_api.py:48`. The runtime blast radius
  of deletion was therefore nil; every consumer was a test.
* **One coupling was not legacy and dictated the ORDER of work.**
  `tests/gateway_free/test_response_contract_parity.py` — the *replacement* architecture's own
  guard — imported `api_gateway.portal` as its reference oracle. Deleting the package first would
  have destroyed the only automated proof that the response contract did not silently collapse
  (the previous experiment's §8 finding). The oracle was frozen into literals **first**; see §5.
* A **dynamic** `importlib.import_module("api_gateway.portal")` existed that no import-statement
  grep finds. Every post-deletion verification below therefore includes an `import_module` sweep.

### Classification of the census (§4 vocabulary)

| Classification | Disposition | Where the detail is |
|---|---|---|
| ACTIVE RUNTIME — REMOVE | 22 tracked `backend/api_gateway/**` files deleted | §3 |
| ACTIVE COMPOSITION — REMOVE | 2 Database-Router seam adapters + 4 builders + 4 selectors deleted | §3, §6 |
| ACTIVE CONFIG/ENV — REMOVE | 9 `SP2_GW_*` names, `pyproject` roots + 4 import-linter contracts, `_scan.SERVICE_PACKAGES`, 2 env profiles, the env template, 2 CI path triggers | §6, §8 |
| ACTIVE LAUNCHER/DEPLOYMENT — REMOVE | ports 8820/8002/8004, the Gateway `Start-StandingEdge`, `$gatewayEnv`, verify map, health probe, banner | §7 |
| ACTIVE TEST/GUARD — MIGRATE OR REMOVE | 29 Gateway test modules deleted; 3 guards deleted; 2 guards **created**; 14 guards retargeted | §4, §5 |
| ACTIVE MVP DOC — UPDATE | 13 documents rewritten or banner-flagged | §6 |
| SHARED SECURITY PROPERTY — REHOME | 24 controls; the blessed crypto fixture relocated | §10 |
| FROZEN DDL/HISTORICAL EVIDENCE — RESIDUAL | DDL 012/013, the AW-1 SecretRef, the `control_gateway_audit` naming, all completed reports | §15 |
| GOVERNANCE CONTRACT — RATIFICATION REQUIRED | IC-005 / IC-009 / IC-010 / IC-011 / IC-012 | §18 |
| UNRELATED — RETAIN | IC-006 *AI* Gateway (a different, deferred component) | §14 |

---

## 3. Every runtime file deleted

**`backend/api_gateway/**` — 22 tracked files, 3,347 lines (3,327 excluding the README).**

| Module | LOC | | Module | LOC |
|---|---:|---|---|---:|
| `main.py` | 610 | | `adapters/providers/http_authenticator.py` | 143 |
| `adapters/providers/http_gateway_edge.py` | 549 | | `adapters/providers/http_tenant_startup.py` | 134 |
| `gateway.py` | 477 | | `adapters/providers/http_router_dispatch.py` | 118 |
| `portal.py` | 256 | | `adapters/providers/durable_audit_emitter.py` | 117 |
| `models.py` | 210 | | `adapters/providers/http_control_plane_read.py` | 105 |
| `ports.py` | 188 | | `adapters/providers/http_import_initiation.py` | 101 |
| `carrier.py` | 100 | | `readiness.py` / `request_context.py` | 30 / 30 |
| `dispatch.py` | 76 | | `in_memory_audit_emitter.py` / `in_memory_metrics.py` | 26 / 25 |
| `README.md` | 20 | | 4 × `__init__.py` | 16 / 8 / 8 |

**Gateway-only Database Router seams — 494 lines** (§6 of the instruction; re-proved consumer-free
before deletion):

| File | LOC | Sole consumer before deletion |
|---|---:|---|
| `database_router/adapters/providers/http_dispatch_api.py` | 224 | the Gateway's `RouterDispatchPort` — and **no served Gateway route ever reached that fall-through** |
| `database_router/adapters/providers/http_tenant_startup_api.py` | 270 | the Gateway's `HttpTenantStartupPort`. This is the edge that read `target_tenant_ref` and `actor_ref` **from the request body** and was **unauthenticated** |

Removed with them from `database_router/main.py`: `build_dispatch_server_from_env`,
`build_tenant_startup_server_from_env`, `_dispatch_port_from_env`, `_tenant_startup_port_from_env`,
and the selectors `SP2_DBR_DISPATCH_HOST` / `_PORT` / `SP2_DBR_TENANT_STARTUP_HOST` / `_PORT`.
`build_tenant_startup_ops_from_env` — the **executor** seam — survives, because the public Startup
edge composes through it.

> **The known residual from the previous experiment is now closed.** That result recorded, in its
> §5.2, that "*not launched ≠ deleted*": the internal envelope edge's module, factory and serve
> entrypoint all remained and the launcher still started it on 8004. It is now deleted, and
> `test_a20d_the_internal_envelope_edge_IS_DELETED_not_merely_unlaunched` asserts the stronger claim
> on three independent oracles (file absent, `find_spec` fails, no builder on the composition root).

**Retained with justification (§6's "non-Gateway active consumer" rule):**
`import_service/adapters/providers/http_import_api.py` — the internal `POST /internal/import/initiate`
edge — is **Edge 9's application**, composed by `deployment/import_edge.py` under the ratified
D-44 / IC-012 §5. Its only *caller* was the Gateway's initiation client, so after removal it has no
MVP caller; it is not launched in the standing topology and Import stays outside the controlled
local MVP journey (IMPORT-A / D-3). Deleting it would dismantle a separately ratified architecture,
so it is retained and recorded rather than removed. It is an unauthenticated internal edge and must
stay loopback-only — see §16 finding class *unauth-edge*.

---

## 4. Every test file deleted or migrated

**Deleted with the component — `backend/tests/api_gateway/**`, 25 test modules + 2 helpers,
5,721 lines, ~262 tests.** The full list is in `git show --diff-filter=D --name-only 172edf2d9`.

**Deleted architecture guards (subject ceased to exist):**

| Guard | Why | Where its still-required properties went |
|---|---|---|
| `test_gateway_edge_boundaries.py` (531 LOC, 13 tests) | pinned the deleted served Gateway edge | **`test_public_edge_boundaries.py` (NEW, 14 tests)** — every property re-aimed at the two public edges |
| `test_phase7_api_gateway.py` (299 LOC, 7 tests) | package-scoped bans on a deleted package | **`test_public_edge_references_only.py` (NEW, 6 tests)** — the references-only census re-aimed at `EdgeAuditEvent`, `TrustedPrincipal`, `PublicRequest` and the two owner portals |
| `test_d15t1_dispatch_transport_static.py` (393 LOC, 9 tests) | pinned the D-15-T1b dispatch **wire**, both ends of which are deleted | withdrawn; the surviving property (one request → one physical tenant DB) is proved by A5/A6/A11 |

**Relocated before anything was deleted (§10's special requirement):**
`tests/api_gateway/crypto_fixture.py` — the **one blessed** JWT/crypto test module — and its test
moved to **`tests/shared/`**. Both containment allowlists
(`test_vendor_and_db_containment.py::JWT_CRYPTO_FIXTURE_ALLOW` and
`test_b5_5_smoke_c_spec_and_crypto_fixture.py`) and all **five** files that load it *by file path*
(not by import, so no import grep finds them) were updated in the same change, and the three
negative controls were re-pointed so the allowance still proves it is exactly one file.

**Live-PG harnesses whose exercise WAS the Gateway journey.** Five deleted, two made to refuse.
Each is a live proof that no longer exists — recorded here, not buried:

| Harness | Disposition | The live property that now has NO proof |
|---|---|---|
| `smoke_c_integrated_live_proof.py` + wrapper + guard | **deleted** | the integrated browser→Gateway→…→tenant-DB journey. **B5-BLK-4 has lost its harness.** |
| `b5_blk6_portal_binding_live_proof.py` + wrapper + guard | **deleted** | portal composition against a REAL Control DB (still pinned statically, no longer live) |
| `test_pg_clm_acme_dataplane_witness.py` + its 38-test guard | **deleted** | the live two-tenant ACME/ZETA data-plane witness |
| `test_pg_clm_2day_stage_b_rehearsal.py` | **deleted** | the CLM Stage B served-write rehearsal |
| `test_pg_controlled_served_write_rehearsal.py` | **deleted** | the controlled served-write rehearsal |
| `dbr_ar_2d_standing_witnesses.py::cmd_run` | **refuses** (file retained — its surface is pinned by the DBR-AR-2D/2E governance guards, which are not about the Gateway) | the DBR-AR-2D standing witness. The property itself is still proved in CI by `test_dbr_ar_2d_routing_audit_live_pg.py`, which never touched the Gateway. |
| `test_pg_import_copy_durable.py` | **refuses** (same reason) | the W1a durable import-copy live proof |
| `test_pg_composition_onboarding_07d.py` | D-15-T1b **section removed**, rest intact and still CI-enrolled | the dispatch transport pair (both ends deleted) |

A refusing harness cannot emit a false PASS — which is the failure mode that matters when a live
proof loses its subject. `test_v3_run_command_is_WITHDRAWN_with_the_gateway_topology` and
`test_the_w1a_live_proof_is_WITHDRAWN_with_the_gateway_topology` assert that each refusal is the
last statement and that no connection, composition or evidence write survives ahead of it.

**Retargeted (mechanical, successor is a drop-in):**
`test_pg_gateway_audit_durable.py` — the only live proof of DDL 012 — now drives
`shared.adapters.providers.edge_audit.HttpEdgeAudit` + `EdgeAuditEvent` instead of the Gateway's
emitter. Same wire, same ingest edge, same store, same DDL, same action strings.
**NOT RE-EXECUTED** (no live-PostgreSQL authority here); it is marked UNVERIFIED in its own header.

---

## 5. Every guard migrated or removed, and why

| Guard | Action | Property, and why it survives or does not |
|---|---|---|
| **`test_public_edge_boundaries.py`** | **NEW** | shared ASGI runtime only; per-edge import allow-set; **one `boundary.admit` site**; one route family each; bounded traversal-safe matcher; served methods read from DECORATORS; correlation accept/mint/echo at the shared gate; exact-origin CORS; `serialize_portal_dto` sole serializer; no leakage; no self-describing surface; one blessed serve entrypoint. Plus `test_no_public_edge_serves_import_or_directory` — a **recorded absence**, so "deliberately not served" stays distinguishable from "forgotten". |
| **`test_public_edge_references_only.py`** | **NEW** | the D-14 / IC-001 references-only census, re-aimed. Includes `PublicRequest` must never gain a prohibited carrier field (`body`/`query`/`cookies`) — the kernel cannot read what it is never handed. |
| `test_ic009_portal_binding_checks.py` | retargeted | §P.2/§P.4/§P.6/§P.7 + exact field-set closure + deterministic serialization, now bound to **two** owner portals. §P.1/§P.3 and the IC-007 classifier clauses **lost their runtime subject** with `/directory` and the dispatcher; the guard now asserts their absence and names the IC-009 amendment requirement. |
| `test_ic010_control_read_adapter_boundaries.py` | retargeted | two-kind equality now across the surviving Control-Plane layers; the bounded-client rules (timeout, one `urlopen`, no retry loop, no pagination vocabulary) re-aimed at the **three internal clients the MVP actually composes**. |
| `test_07e3b_auth_transport_boundaries.py` | retargeted | the IC-005 authenticate client moved to `shared/.../http_principal_authenticator.py`; the composition guard to `database_router/main.py`. New: the Database Router must never `import auth_router` in-process (IC-010 §H, now a hard ban). |
| `test_gateway_operational_audit_boundaries.py` | retargeted | DDL 012/013 pins untouched; emitter → `shared/.../edge_audit.py`; the fail-closed audit-before-hand-back property moved from the Gateway core to `PublicBoundary.emit` — and the detector now walks **into the class**, because `next(...)` over the module would have picked the abstract port method and passed vacuously on a `...` body. |
| `test_clm_2day_stage_b_runtime_boundaries.py` | retargeted | the update parser, the executor's sole mutable column and the five-class durable partition survive; the two Gateway-side pins are withdrawn with an asserted-absence record. The public-edge check is **strictly stronger** than the internal-edge one it replaces: it additionally requires `admit` + `require_tenant`. |
| `test_native_uvicorn_factories.py` | retargeted | nine edges → **eight**; both public edges enrolled; a zero-residual clause forbids any retired target appearing in either documented port map. |
| `test_standing_launcher_flags.py` | retargeted + **strengthened** | new `RETIRED_PORTS`/`RETIRED_MODULES` census and a hard ban on any `SP2_GW_*` in launcher code. |
| `test_07d3_multiinstance_readiness_static.py` | retargeted | three serve-loop blessings struck with their modules; a new probe proves a **struck blessing no longer exempts its old module**. |
| `test_deployment_composition_root_boundaries.py` | retargeted | the TOML byte-pin updated; the authorized/unauthorized partition is now asserted **exhaustively over the surviving packages** instead of by a fixed count — a count would have had to be edited to a number, which proves nothing. |
| `test_gateway_free_mvp_boundaries.py` | retargeted + **strengthened** | GF-1's positive control now imports a package that EXISTS (importing the deleted one would fail for the wrong reason and detect nothing), and a new `test_gf1_the_deleted_package_is_unimportable` executes the absence. |
| `test_vendor_and_db_containment.py`, `test_b5_5_smoke_c_spec_and_crypto_fixture.py` | retargeted | the one blessed crypto-fixture path and its three negative controls. |
| `test_phase3/4/5/6`, `test_dbr_composition_boundaries.py`, `test_auth_router_composition_boundaries.py`, `test_controlled_rollback_rehearsal_boundaries.py`, `test_import_write_path_boundaries.py`, `test_traceability.py`, `test_next_a_portability_boundaries.py`, `test_live_pg_workflow_runset_completeness.py`, `test_dbr_ar_2d_standing_witness_boundaries.py` | ban-list / census entries removed | **This is the class §9 warns about.** A deny-list naming a deleted package is dead weight, and the *non-vacuity probes* that planted `from api_gateway.main import build_gateway` would have kept "passing" while proving nothing — they parse a string, not the module. Every such probe was re-pointed at a **live** sibling service, so each guard still demonstrably bites. |

**Response-contract oracle, rewritten first (the ordering constraint from §2).**
`test_response_contract_parity.py` no longer imports the Gateway's DTOs; the exact field names,
ORDER, defaults, `display_ref` derivation and serialized **bytes** are transcribed as literals from
`api_gateway/portal.py` at `8719f4f3`, with a `test_the_frozen_oracle_is_non_vacuous` companion
planting three real regression shapes (dropped provenance field, reordered fields, changed default).
A literal oracle is strictly stronger than the import was: an import tracks whatever the Gateway's
DTO happened to say; a literal cannot move without a reviewed edit.

---

## 6. Every config / environment reference removed

| Surface | Before | After |
|---|---|---|
| `pyproject.toml` setuptools discovery | 7 packages incl. `api_gateway*` | **6** — the glob is gone, so an empty directory cannot silently re-enter the distribution |
| `pyproject.toml` import-linter `root_packages` | 8 | **7** |
| contract *"shared is a dependency leaf"* | forbids 6 services | forbids **5** |
| contract *"services are mutually independent"* | 6 modules | **5** |
| contract *"nothing may import the deployment root"* | 7 sources | **6** |
| contract *"the root may compose only Edge 9 services"* | forbids `api_gateway, auth_router, control_plane` | forbids **`auth_router, control_plane`** — still the **exact complement** of the authorized set over the surviving services, so the narrow grant did not widen |
| `tests/architecture/_scan.py::SERVICE_PACKAGES` | 6 | **5** |
| `SP2_GW_*` family | 9 names (`AUTH_ROUTER/CONTROL_READ/DB_ROUTER/TENANT_STARTUP/IMPORT/AUDIT_SINK_BASE_URL`, `EDGE_HOST/PORT/ALLOWED_ORIGINS`) — **all defined inside `api_gateway/`** | **0.** The public edges use `SP2_EDGE_AUTH_ROUTER_BASE_URL` (REQUIRED), `SP2_EDGE_AUDIT_SINK_BASE_URL` (optional, **no loopback default**), `SP2_EDGE_ALLOWED_ORIGINS` |
| `SP2_DBR_{DISPATCH,TENANT_STARTUP}_{HOST,PORT}` | 4 | **0** |
| `infrastructure/env/sp2-local-mvp.env.template` | `SP2_GW_AUDIT_WRITER_DSN_REF`, `SP2_GW_EDGE_ALLOWED_ORIGINS`, Gateway selector inventory | rewritten to `SP2_EDGE_*`; the AW-1 SecretRef **value** kept and labelled frozen |
| `infrastructure/env/profiles/{sp2-local-mvp,sp2-cloud-template}.profile.json` | `service_id: "api-gateway"` in both | removed from **both in the same commit** — a guard asserts the two tuples are equal |
| `.github/workflows/live-pg-durable-path.yml` | 2 × path triggers naming deleted modules (push + pull_request) | removed. A trigger on a file that cannot exist never fires, and leaving it advertises coverage that is gone |
| `snackportal2_backend.egg-info/top_level.txt` + the editable-install finder | listed `api_gateway` | regenerated via `pip install -e ".[dev]"`; **neither names it** |

**Active documents updated (13):** `docs/runbooks/backend_service_startup_fastapi.md` (rewritten:
banner, both port maps, env inventory, startup order, all commands, health checks, shutdown,
witness protocol), `docs/runbooks/b5_service_startup_order.md`,
`docs/runbooks/gateway_free_mvp_topology.md`, `docs/acceptance/SMOKE-C-SPEC-01.md`, `CLAUDE.md`,
and withdrawal banners on eight `infrastructure/runbooks/*` whose harnesses are deleted or refusing.
`infrastructure/runbooks/aw1_gateway_audit_writer.md` gained an emitter-changed/store-frozen note
that states explicitly which names must NOT be renamed and why.

**Prose that was safety-relevant, not cosmetic.**
`database_router/tenant_startup_ops.py:38` called the 512-byte / 500-char CLM bounds
*"defense-in-depth: the gateway validated these fail-closed already."* After removal they are the
**only** enforcement, and that sentence was an open invitation to a future "this is redundant"
deletion. It now reads *"SOLE enforcement since the API Gateway was deleted: nothing upstream
re-validates them."*

---

## 7. Launcher and process topology — before / after

`backend/tools/local/start-sp2-local.ps1` (parses clean under
`[System.Management.Automation.Language.Parser]::ParseFile`).

| | Before (`8719f4f3`) | After |
|---|---|---|
| edges started | 6 | **5** (4 by default — see the switch below) |
| ports | 8001, 8002, 8003, 8004, 8005, **8820** | 8001, 8003, 8005, **8830**, **8831** |
| public surfaces | 1 (8820) | **2** (8830 tenant Startup, 8831 Workspace) |
| retired, never bound | — | **8820, 8002, 8004** — and the collision precheck now *watches* all three and warns that a listener is a stale pre-removal process (8004 in particular served an unauthenticated envelope edge) |
| Gateway env | `$gatewayEnv` with 5 × `SP2_GW_*` | `$publicEdgeEnv` (`SP2_EDGE_AUTH_ROUTER_BASE_URL`, `SP2_EDGE_ALLOWED_ORIGINS`) + `$startupEdgeEnv` (adds the routing gate) + `$workspaceEdgeEnv` (adds the Control-store posture) |
| activation selectors | 4, incl. `SP2_GW_TENANT_STARTUP_BASE_URL` | **3.** The fourth has no successor **by construction** — see below |
| canonical uvicorn flags | 5, one template | **unchanged**, still one template, still `--host 127.0.0.1` |
| `UVICORN_*` / `SP2_*` child scrub | unconditional, exempt-free | **unchanged** |
| AW-1 start gate | presence check → `status` → ingest edge | **unchanged**; parameter renamed, SecretRef value frozen |

> **A governance consequence worth stating plainly.** Under the Gateway,
> `SP2_GW_TENANT_STARTUP_BASE_URL` let the topology run with the tenant data plane *unwired*. The
> public Startup edge holds `TenantStartupOperations` **in-process**, so composing that edge **is**
> the tenant data plane — there is no "started but unwired" posture for it. Rather than let the
> default posture silently become more privileged, `-EnableTenantDataPlane` now gates whether the
> Startup edge **starts at all**, and it remains off by default. The Gate-A default posture is
> therefore exactly what it was: no running process able to write tenant business data.

**Smoke/verification map:** nine edges on 8080–8088 → **eight on 8081–8088**, with **8080
deliberately left empty** because it was the historical Gateway port and the launcher warns on it.

---

## 8. Package / import graph — before / after

```text
BEFORE                                      AFTER
  shared ──┬─▶ (leaf: imports no service)     shared ──┬─▶ (leaf: imports no service)
  services: api_gateway, auth_router,         services: auth_router, database_router,
            database_router, control_plane,             control_plane, import_service,
            import_service, lineage_service             lineage_service
  deployment ──▶ import_service               deployment ──▶ import_service
             ──▶ database_router                         ──▶ database_router
             ──▶ lineage_service                         ──▶ lineage_service
             ──▶ shared                                  ──▶ shared
             ─╳─▶ api_gateway, auth_router,              ─╳─▶ auth_router, control_plane
                  control_plane                               (still the EXACT complement)
  9 native ASGI edges                         8 native ASGI edges
```

`lint-imports`: **4 contracts kept, 0 broken** — the same four, none weakened. The forbidden list on
the Edge-9 contract shrank only because the complement shrank; `test_detectors_are_non_vacuous` now
asserts the partition covers every surviving service package with no overlap, which is a property a
count could never express.

---

## 9. Final route ownership

| Route | Owner service | Public port | Authenticated by | Tenant derived from |
|---|---|---:|---|---|
| `GET /tenant/startups/<startup_ref>` | `database_router` | 8830 | `PublicBoundary.admit` → IC-005 port → Auth Router | `require_tenant` — the signed claim, one call site |
| `PATCH /tenant/startups/<startup_ref>` | `database_router` | 8830 | same | same |
| `GET /memberships` | `control_plane` | 8831 | same | n/a (control-scoped; the subject is the authenticated principal) |
| `GET /health`, `GET /readiness` | each edge | 8830 / 8831 | n/a — non-disclosing | n/a |
| `OPTIONS` preflight | each edge | 8830 / 8831 | n/a | n/a |
| `POST /import/<source_ref>` | — | — | **not served.** Outside the controlled local MVP journey (IMPORT-A / D-3) | — |
| `GET /directory/<kind>` | — | — | **not served.** Dead surface on `main` — no served Gateway route ever exposed it | — |
| generic `TENANT_OPERATION` hand-off | — | — | **removed.** Nothing dispatches | — |

No question has two answers, and no answer is "the Gateway".

---

## 10. Security-property migration table (§11)

| Required property | Where it lives now | Proved by |
|---|---|---|
| authentication before public business logic | `PublicBoundary.admit`, one site per edge | A1, A2, M3; `test_public_edge_boundaries` |
| membership / tenant authorization | Auth Router Stage 2, via the injected IC-005 port | A5, A6, A10 |
| tenant derived only from trusted state | `require_tenant`, the sole producer of a tenant id at the edge | A7–A9, GF-3, GF-3c, M1, M2 |
| caller-supplied tenant/actor non-authoritative | `PublicRequest` has **no body/query/cookie field at all** | GF-3 (literal AND keyword positions), A8, A9, `test_public_edge_references_only` |
| ACME/ZETA isolation | routed session provider, one tenant per accepted request | A5, A6, A11, M1 |
| one request → one active tenant → one physical DB | `TenantStartupOperations` → `RoutedSessionProvider` | A11, A11c–e, M12 |
| raw-target / route safety | `is_valid_tenant_startup_target`, decided against the RAW target | A12, M5, `test_public_edge_boundaries` |
| bounded request size | shared transport gate | A13, A13b |
| safe denial semantics | `PublicBoundaryDenied` → empty body | GF-5, A1, A2 |
| CORS | shared transport gate, exact-origin only | A16, M10 |
| bounded correlation id | shared transport gate, minted **once** | A17, M11 |
| response DTO contract | owner `portal.py` × 2, byte-identical to the frozen contract | `test_response_contract_parity` (5 tests incl. a non-vacuity companion) |
| audit event emission | `PublicBoundary.emit`, fail-closed | A18, A19, M9, `test_edge_success_emit_is_fail_closed` |
| fail-closed composition | both edges raise rather than compose unauthenticated | A14, A15, `test_partial_public_edge_composition_never_activates` |
| Workspace membership-read narrowing | `WorkspaceMembershipReadPort` — one method, self-scoped | GF-9a–d, `test_the_public_edges_read_port_is_one_read_method...` |
| service independence / DB containment | import-linter 4/4 + `test_vendor_and_db_containment` | executed |

**Names.** `GATEWAY_AUDIT_STORE_ACTIONS` → `EDGE_AUDIT_STORE_ACTIONS`;
`GATEWAY_AUDIT_SOURCE_SERVICE` → `EDGE_AUDIT_SOURCE_SERVICE`. `ClmDurableAuditPartition` and
`_CLM_DURABLE_ACTIONS` died with `api_gateway/main.py`; their successors
`DurableEdgeAuditPartition` / `DURABLE_EDGE_AUDIT_ACTIONS` already carried neutral names.
**Not one action string changed** — which is exactly what let the emitter move with no schema
migration and no DDL edit.

---

## 11. Zero-residual verification evidence (§15 A–H)

Executed after the final source change, by
`scratchpad/verify.py` (a standalone script, not a test the change could have been written to satisfy):

```text
27/27 checks PASSED
```

| §15 | Check | Result |
|---|---|---|
| **A** | `backend/api_gateway` / `backend/tests/api_gateway` do not exist | PASS ×2 |
| **B** | `git ls-files` returns **zero** files under both paths | PASS ×2 |
| **C1–C3** | clean subprocess composes **both** public edges from env; `sys.modules` census reports `api_gateway_modules: []` and `routes: 8` (non-vacuous — the apps really registered routes) | PASS |
| **C4** | `python -c "import api_gateway"` exits non-zero with `ModuleNotFoundError` | PASS |
| **D** | full tracked re-census of every §4 pattern | see §14 — every remaining match classified |
| **E1–E3** | no runtime module names `api_gateway` except the frozen DDL producer constant; that literal lives in **exactly one** module (`control_plane/gateway_audit.py`); DDL 012's CHECK untouched | PASS ×3 |
| **F** | no runtime module reads any `SP2_GW_*` selector | PASS |
| **G1–G4** | `pyproject` **code** names no `api_gateway`; `lint-imports` 4 kept / 0 broken; `SERVICE_PACKAGES` = 5; setuptools globs exclude it | PASS ×4 |
| **H1–H5** | both seam adapters deleted; **no orphan builder** (4 checked); **no orphan selector** (4 checked); the executor seam survives; **no runtime module executably references a removed seam** | PASS ×11 |

**On the AST, not on text.** H5 and E1 are measured by walking the AST for `Name` / `Attribute` /
imported-module references and for non-docstring string literals. A substring search would have
"failed" on the removal's own explanatory comments — a check that fails on its own documentation
measures nothing. The distinction is deliberate and is written into the script.

---

## 12. Adversarial review findings (§16)

An independent ten-skeptic adversarial review was run against the ten named residue claims, each
instructed to **refute** rather than confirm, with every candidate finding then handed to a separate
adversarial verifier instructed to default to REFUTED.

Ten independent skeptics, one per named claim in §16 of the instruction, each told to **refute**
rather than confirm and each with execution rights (pytest, ruff, mypy, `lint-imports`, clean
subprocesses) but read-only on tracked files. All ten returned, and the automated
verify pass completed: **49 candidate findings → 39 REFUTED, 6 ALREADY-DISCLOSED, 4 CONFIRMED**
(§12.4).

### 12.1 What the review could NOT break

This half matters as much as the findings, and is quoted from the skeptics' own refutations:

* **No route back to Gateway code exists.** *"REFUTED on every vector I could execute"* — a clean
  subprocess import fails with `ModuleNotFoundError`; `sys.meta_path` shows the editable finder
  **is** installed and still does not resolve it; no `.pth`, no `egg-info` entry, no orphan `.pyc`,
  no `importlib` string, no forwarding module.
* **The internal envelope edge is genuinely gone** — *"I could not break this and tried six ways"*:
  module file, importability, factory, serve entrypoint, launcher reference, runbook command.
* **No selector that used to be REQUIRED became optional.** An executed matrix over both edges with
  every `SP2_*` scrubbed: each missing selector produces `RuntimeError ... composition is INACTIVE`,
  never a composed edge.
* **All four import-linter contracts still bite.** A skeptic reproduced the baseline in a scratch
  copy, then planted one violating module per contract: *"Every one fired, and each time exactly ONE
  contract broke while the others stayed green."*
* **The crypto allowance really is one file.** An independent census using the guard's own helper
  found exactly two JWT/crypto importers repo-wide — the production verifier and
  `tests/shared/crypto_fixture.py`.
* **No `api_gateway` module loads in either composed edge**, and neither public edge loads the
  other's service package — verified by executing `create_app_from_env()` for real and censusing
  `sys.modules`.
* **Every runbook with copy-pasteable Gateway startup carries an accurate withdrawal banner** —
  checked by reading each header directly.

### 12.2 Confirmed findings, all corrected in `2bdb58768`

| # | Severity | Finding | Correction |
|---:|---|---|---|
| 1 | **MAJOR — found independently by THREE skeptics** | **`test_gf8` had gone VACUOUS.** It walked `_scan.py_files(BACKEND / "api_gateway")`, which yields nothing once the package is deleted, so the loop body never ran and the test passed with **zero assertions executed** — while being the baseline half of the entire GF-8/GF-8b privilege-regression argument | reads the Gateway's own sources back out of git at `8719f4f3`, and asserts it saw **≥15 modules** *before* asserting anything about them. **Proved by mutation:** pointing it at a Gateway-free commit fails it |
| 2 | MAJOR | **The crypto-fixture relocation had been silently REVERTED** inside `dbr_ar_2d_standing_witnesses.py` — by my own `git checkout` restoring that file after I wrongly deleted it | re-applied; the path now resolves |
| 3 | MAJOR | **The "no retry loop around the core call" ban was lost in migration.** The Gateway guard asserted `gateway.handle` was not inside a loop; the successor counted one `admit` site, which is not the same property. An automatic retry re-drives authentication *and* the executor — one accepted request becomes two tenant sessions | every function containing an `admit` call is now asserted loop-free, with a non-vacuity companion |
| 4 | MAJOR | **The public Startup edge's production docstring asserted, as current fact, that the internal envelope edge still existed** and was merely unlaunched — true when written, false after this task | rewritten to the stronger true claim, citing the three-oracle test |
| 5 | MAJOR | **Ports 8820 / 8002 / 8004 were demoted from a FATAL start refusal to an advisory warning.** They were in `$STANDING_PORTS` before; a stale pre-removal Gateway could have kept serving a browser while this topology started alongside it | the launcher **throws** again, and a new guard pins that it throws and that a retired port cannot be quietly moved to the advisory list |
| 6 | MAJOR | **`-EnableTenantDataPlane` — the Gate-B M14 control — was pinned by NO guard.** Inverting it, or deleting the `if`, would start a tenant-write-capable public edge by default with every other guard green | new guard walks back from the `Start-StandingEdge` call to its enclosing condition. **Proved by mutation:** replacing the gate with `$true` fails it |
| 7 | MAJOR | **The Edge 9 `forbidden_modules` list was named but not pinned** — a one-line deletion could empty the grant's complement while the contract's name stayed green | byte-pinned, like the independence contract beside it |
| 8 | MAJOR | **The activation-selector gate was bypassable with `.Add()`**, and **`$STANDING_BIND_HOST` could be reassigned later in the file** with every guard still green (the template interpolates the variable, not the literal) | both closed: `.Add(` is matched, and the bind host must be assigned exactly once |
| 9 | MAJOR | **A side-channel `Start-Process` could launch a deleted module** without going through `Start-StandingEdge`, which the retired-module census read | the module names and `api_gateway` are banned from launcher **code** outright (comments may still name them — that is how the retired map is documented) |
| 10 | **CRITICAL** | **The audit incident-response runbook told the operator to disable durable audit by unsetting `SP2_GW_AUDIT_SINK_BASE_URL`** — a variable that no longer exists. Mid-incident the operator would unset it, restart, and believe durable persistence had stopped while it continued | corrected to `SP2_EDGE_AUDIT_SINK_BASE_URL`, with the silent-no-op trap called out and the requirement to unset it on **both** edges |
| 11 | **CRITICAL** | **The three auto-imported governance documents still mandate the Gateway** and list *"The Gateway is the boundary"* as a **LOCKED INVARIANT**, and CLAUDE.md makes the Overview authoritative | **DRIFT banners, not edits.** CLAUDE.md instructs *flag DRIFT before acting*; reopening a locked invariant is Dan's sign-off, not a code change |
| 12 | MAJOR | **`D15-DISPATCH-SPEC-01` still declared itself "Normative" and "the T1 source of truth"** for a wire whose runtime *and* whose guard were both deleted | banner-flagged as the historical wire record it now is |
| 13 | MAJOR | **The runbook index published 8002/8004/8820 as the canonical standing map** and rated two WITHDRAWN documents as merely superseded | corrected; four rows re-rated ⛔ WITHDRAWN |
| 14 | MAJOR | **CLAUDE.md's only pointer to the removal record was a dangling path**, and **IC-005 (Final, 13 Gateway clauses) was omitted from the contracts needing ratification** | both fixed; the repo-resident copy of this document now exists at that path |
| 15 | MAJOR | **The CLM dataplane evidence template still required `SP2_GW_TENANT_STARTUP_BASE_URL` and the 8820/8002/8004 process map** | banner-flagged: no evidence may be recorded against it |
| 16 | MINOR | **Two migrated guards wrote probe files into the tracked source tree** during a normal `pytest` run | both use a temporary directory |
| 17 | MINOR | `backend/README.md` still listed `api_gateway/`; the startup runbook's §4 heading still read *"Database Router Dispatch (8083) and Tenant Startup (8084)"* — the exact map-confusion the runbook's own opening warns about | both corrected |
| 18 | MINOR | The retargeted audit guard's docstring still named a dead selector | corrected |

### 12.3 Findings deliberately NOT "fixed", and why

Each of these is real. None is a defect this task should patch, and burying them would be worse
than the finding.

| Finding | Why it stands |
|---|---|
| **The unauthenticated internal Import edge survives, write-capable** (`POST /internal/import/initiate`) | It is **Edge 9's application**, composed by `deployment/import_edge.py` under the ratified D-44 / IC-012 §5. Deleting it dismantles a separately ratified architecture that has nothing to do with the Gateway. It is **not launched** in the standing topology, binds loopback by default, and Import is outside the controlled local MVP journey. Recorded in §3, not silently retained. |
| **A migrated security property was lost: the authenticated import-initiation path** | Correct, and it is a *capability deferral*, not an oversight. The Gateway authenticated `POST /import/<source_ref>`; no public edge serves that route, so there is nothing to authenticate. `test_no_public_edge_serves_import_or_directory` asserts the absence so it cannot become an unguarded reintroduction. |
| **The unauthenticated audit-ingest edge (8005) accepts a forged success event** | Unchanged from `main`. It is an internal loopback ingest edge and always was; this task neither created nor widened it. |
| **The public tier now holds database credentials** | The known GF-8b regression. It is the dominant consequence of the removal, it is pinned by a test, and it is **Dan's decision**, not a bug to patch — §18 item 2. |
| **The Workspace edge still holds a secret store allow-listed for `bootstrap/trust-anchor`** | A residual gap in the GF-9 narrowing landed by the *previous* commit, not by this one. Reported so the narrowing is not read as complete. |
| **The loopback allowlist is not consulted on the canonical native startup path** | Pre-existing and already documented: on the native path the **command line** is the only place the bind host is enforced, which is exactly why the canonical-flags guards exist. |
| **`_jwt_crypto_allowed` also blesses `/adapters/providers/`** | By design — that is the production containment zone. The *test-side* allowance is one exact file, and a skeptic's independent census confirmed exactly one. |

### 12.4 Verify-phase outcome — the review completed after the first draft of this document

The automated adversarial **verify** pass (a second skeptic per finding, instructed to default to
REFUTED) finished after §12.1–12.3 were first written, and it removed the incompleteness caveat this
section originally carried. Final tally over the ten skeptics:

| Verdict | Count |
|---|---:|
| REFUTED | **39** |
| ALREADY-DISCLOSED | 6 |
| **CONFIRMED** | **4** |
| total candidate findings | 49 |

A 39/49 refutation rate is the calibration signal worth reading: the skeptics were not rubber-
stamping, and the four that survived independent re-derivation are all in the **guard-integrity**
class — the one §16 singles out as highest-risk. **None is a live exploit**; the shipped composition
is clean in every case. Each means a guard could be defeated silently. All four are fixed in
`e0d1f61`, each with an executed proof:

| # | Severity | Confirmed finding | Fix, and how it was proved |
|---:|---|---|---|
| C1 | **CRITICAL** | **GF-9's object-graph walk was blind through two doors.** `getattr(type(obj), "__slots__", ())` returns only the MOST-DERIVED class's slots, so a derived `__slots__ = ()` — the ordinary product of a "make this slotted" refactor — shadows a base's and hides whatever it holds. Separately, a `dict`/`list`/`tuple`/`set` **subclass** satisfied the `isinstance` check, had its contents extended, and then `continue`d — its `__dict__`, slots, closure and class attributes never read. The verifier hid a **real `ControlPlane`** behind an allow-listed type name through each door, mutated the real `ControlStoreMembershipReader`, and watched **all five GF-9 legs stay green** in all three postures | the walk now enumerates the **full MRO** for slots and no longer `continue`s out of container instances. **Reproduced against the repair:** the walk goes from 13 objects to 88, sees the smuggled `ControlPlane`, and the capability census fires with the whole provisioning/recovery surface. A new `test_gf9_reachability_sees_slotted_bases_and_container_subclasses` plants all three shapes |
| C2 | **CRITICAL** | **The straddle control was mutation-proved on the Startup edge only.** Both edges own their own `_raw_headers`, so the defect is per-edge: reintroducing `dict(request.headers)` in the **Workspace** edge would have turned a 403 isolation denial into a served 200 with nothing going red | **M12b** does to the Workspace edge exactly what M12 does to the Startup edge, and a new structural guard asserts *neither* `_raw_headers` builds a `dict` — so a third public edge inherits the check instead of needing someone to remember it |
| C3 | MAJOR | **Three of five documented transport bounds had zero coverage** — header count, total header bytes, and chunked `Transfer-Encoding`. A documented bound with no test is a claim, not a control | **A13c / A13d / A13e**. A13c carries a positive control (61 headers still serve) so it pins a *count*, not "large is refused"; A13d uses few-but-fat headers so only the byte bound can trip; all three assert `provider.opened == []` and `auth.calls == []` — refused **before** authentication |
| C4 | MINOR | **The launcher port census silently DROPPED any `Start-StandingEdge` whose `-Module` used single quotes**, so a sixth standing edge — including a resurrected Gateway on 8820 — was invisible to the port map, the retired-module ban and the map-equality check, all of which read that dict | the matcher accepts every form PowerShell takes, and an unparseable block is now a **hard failure, never a skip**. **Proved by mutation:** a single-quoted rogue Gateway edge on 8820 now fails two guards; before, it passed silently |

**One lesson worth carrying forward.** C1 is the *third* time this codebase has had a capability
smuggled past an object-graph walk — a closure cell the previous review found, and now a slotted
base and a container subclass. The pattern is not "someone forgot a case"; it is that a reachability
walk must enumerate **every** state-carrying channel Python has, and a deny-list of the ones the
author thought of will keep losing. Each newly-found channel now has a planted probe in
`test_gf9_reachability_sees_slotted_bases_and_container_subclasses`, so the next one is added to a
list that already exists rather than rediscovered by a reviewer.

---

## 13. Gate results (§17)

| Gate | Command | Result | Exit |
|---|---|---|---|
| full suite | `pytest -q` | **1788 passed**, 0 failed (baseline 2163 → −375, all deleted Gateway coverage) | 0 |
| architecture | `pytest tests/architecture -q` | **965 passed** | 0 |
| Gateway-free | `pytest tests/gateway_free -q` | **83 passed** | 0 |
| Workspace privilege narrowing | `pytest tests/gateway_free/test_workspace_privilege_narrowing.py -q` | **14 passed** | 0 |
| mutation / non-vacuity | `pytest tests/gateway_free/test_mutation_non_vacuity.py -q` | **15 passed** | 0 |
| adversarial boundary | `pytest tests/gateway_free/test_adversarial_boundary.py -q` | **43 passed** | 0 |
| new public-edge guards | `pytest tests/architecture/test_public_edge_*.py -q` | **20 passed** | 0 |
| lint | `ruff check .` | All checks passed | 0 |
| format | `ruff format --check .` | 345 files already formatted | 0 |
| types | `mypy .` (strict) | no issues in **344** source files | 0 |
| imports | `lint-imports` | **4 kept, 0 broken** | 0 |
| secrets | `gitleaks detect --log-opts cdb46fc9..HEAD` | **no leaks found**, 9 commits scanned | 0 |
| secrets (this commit) | `gitleaks detect --log-opts 8719f4f3..HEAD` | **no leaks found** | 0 |
| zero-residual battery | `verify.py` | **27/27 PASSED** | 0 |
| PowerShell parse | `Parser::ParseFile(start-sp2-local.ps1)` | **PS PARSE OK** | 0 |

**Secret-scan positive control:** the same scanner over the full working tree reports **4 findings**,
all inside the git-ignored `backend/.venv` third-party packages — so the clean commit-range result is
a real result, not a silent no-op.

**Test-count movement, stated honestly.** 2163 → 1788 is **−375**, and 1063 → 965 architecture tests
is **−98**. That is not a regression in coverage of the surviving system: 262 of those tests were
`tests/api_gateway/**` (a deleted component), and the rest were guards whose subject no longer
exists. **+29 tests were added** (two new public-edge guards, three guards the first adversarial round
required, and six the verify phase required), and 14 guards were re-aimed rather than dropped. Coverage of what remains went up, not down; the total went down because the
system got smaller.

---

## 14. All remaining `gateway` / `api_gateway` matches, classified

Final tracked re-census of every §4 pattern: **1,992 matches across 210 files** (from 3,440 / 276).

| Area | Files | Classification |
|---|---:|---|
| `backend/` | 65 | Comments and docstrings recording *what was removed and why*; the frozen DDL producer constant and the store naming bound to it (§15); guard identifiers that deliberately name the deleted thing in order to assert its **absence** (`RETIRED_PORTS`, `_WITHDRAWN_MODULES`, `_DELETED_GATEWAY_SURFACE`, `test_gf1_the_deleted_package_is_unimportable`); and non-vacuity probes that use the string as a sample. **Zero executable references** — proved by §11 E1/H5 on the AST. |
| `contracts/` | 6 | **GOVERNANCE CONTRACT — RATIFICATION REQUIRED.** IC-010 (22 hits), IC-005 (13), IC-009 (9), IC-012 (9), IC-011 (2), IC-002 (7), IC-001/IC-008 (1 each). IC-006 is the **AI** Gateway — a different, deferred component: **UNRELATED — RETAIN**. See §18. |
| `docs/` | 27 | Completed reports, decision history, acceptance records, handover snapshots, prior PRD evidence: **HISTORICAL EVIDENCE — RETAIN** (§14 of the instruction forbids rewriting them). The active runbooks in this set were rewritten or banner-flagged (§6). |
| `infrastructure/` | 17 | DDL 012/013 and the `control/README.md` entry for them: **FROZEN**. Runbooks for deleted/refusing harnesses: banner-flagged. `aw1_gateway_audit_writer.md`: frozen SecretRef + table, annotated. |
| `CLAUDE.md` | 1 | Updated: the removal is described, scoped to this branch, and the contract blocker is named. |
| `VITE_*GATEWAY*` | **0** | No frontend source exists in this repository — see §17. |

---

## 15. Frozen DDL / historical residuals (the only kind a PASS permits)

| Residual | Why it cannot be removed here | Where |
|---|---|---|
| `CHECK (source_service = 'api_gateway')` | **DDL. Out of authority.** Changing the constant without the DDL would make every durable audit write fail closed | `infrastructure/db/control/012_gateway_operational_audit.sql:69` |
| `EDGE_AUDIT_SOURCE_SERVICE = "api_gateway"` | the store-side producer constant the CHECK above pins. **Never a wire field** — nothing sends it, nothing reads it from a caller | `control_plane/gateway_audit.py:65` (the **only** runtime module holding the literal — asserted by §11 E2) |
| the `control_gateway_audit` table name, and the Python named for it (`gateway_audit.py`, `GatewayAudit*`, `PostgresGatewayAuditStore`, `http_gateway_audit_api.py`, the wire path `/internal/gateway-audit/events`) | the module is named for the frozen table it binds. Renaming the code around a frozen artifact creates drift between the two, it does not remove residue | `control_plane/**` |
| SecretRef `control/gateway-audit-writer-dsn` and `SNACKPORTAL_SECRET_CONTROL_GATEWAY_AUDIT_WRITER_DSN_V1` | **SecretRef. Out of authority** (§2 of the instruction) | AW-1 runbook, launcher parameters, env template |
| DDL 013 append-only triggers | same frozen family | `infrastructure/db/control/013_*.sql` |
| completed reports, decision history, acceptance records, handover snapshots | §14: historical evidence, must not be rewritten to erase a word | `docs/**` |

**No DDL file was read into a database, edited, or applied.** DDL 012/013 blob pins still match
their reviewed SHA-1s (`test_ddl_blob_pins_match_committed`, green).

---

## 16. Proof `main` is untouched, and no live/standing mutation occurred

| Requirement | State |
|---|---|
| `main` unchanged | ✅ `cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f` — identical to the pre-task reading; `git merge-base main HEAD` is the same SHA |
| commits are local only | ✅ one new commit `172edf2d9`; no `git push` was run; the branch has no remote-tracking ref |
| NO PR opened | ✅ no `gh` invocation, no GitHub API write |
| NOT merged | ✅ `git diff main..HEAD` is this branch only |
| working tree | ✅ clean |

| Prohibited act | Performed? |
|---|---|
| connect to standing PostgreSQL 5540–5543 | ❌ no psycopg connection opened; every `requires_pg` harness is excluded from the suite by `addopts` and none was run |
| connect to standing Keycloak 8814 | ❌ authentication is a double throughout; no OIDC/JWKS call |
| change Keycloak · create a PKCE session | ❌ |
| create or modify SecretRefs / credentials | ❌ — the AW-1 reference is *named* and deliberately unchanged |
| apply or edit DDL | ❌ — DDL 012's constraint is **reported**, and its blob pins verify unchanged |
| modify standing memberships / roles / grants | ❌ |
| start, stop or restart a standing service · run the governed launcher | ❌ — the launcher was **edited and syntax-parsed**, never executed |
| bind a fixed standing port | ❌ — the only sockets bound were ephemeral loopback (`port=0`) opened and closed by tests, plus deliberately-unbound loopback ports used to exercise connection-refused paths |

The one local mutation performed was `pip install -e ".[dev]"` **inside `backend/.venv`**, to
regenerate the editable-install finder so it no longer maps `api_gateway` to a path. That is a venv
artifact, not repository or standing state, and it closes a real residue class: a stale finder would
resurrect the package the moment an empty directory reappeared.

---

## 17. Frontend / API endpoint references (§13)

`VITE_*GATEWAY*` and any frontend Gateway base URL: **zero tracked matches in this repository.**
`frontend/` does not exist here; the Lovable UI lives in the separate `snack-cosmos` repository.

**The exact future cutover requirement, stated rather than assumed complete:**

* the frontend today has **one** backend base URL. It needs **two**: the tenant Startup edge and the
  Workspace edge are separate origins;
* both need the **same** exact-origin CORS allowlist configured server-side, and the failure mode of
  getting it right on only one is silent (preflight 204, no real request, nothing in any log);
* the reverse proxy needs two upstreams and two TLS terminations;
* `VITE_SP2_GATEWAY_BASE_URL` (or its equivalent) must be split, and the OIDC redirect origin must
  still agree byte-for-byte with the Keycloak client registration.

None of this was done, and nothing outside this repository was modified.

---

## 18. The exact next adoption blocker

> ### Ratify the contract amendments. Nothing else is close.

The code on this branch **contradicts a Final contract**. That is not a defect in the removal — it
is the governance step that must come first under CLAUDE.md's "contracts precede code", and it is
Dan's act, not mine. The required amendment set:

| Contract | Status | Clause | What must be decided |
|---|---|---|---|
| **IC-010** | **Final** | §A "sole approved ingress"; §C "**No alternate flow is permitted**"; §I portals "**only through the API Gateway**"; §M services reachable "only through the API Gateway"; §N "gateway-only ingress" | Replace the *component* with the *boundary*: an approved public edge is a service edge that links `shared.public_edge`, derives all authority from `TrustedPrincipal`, serves one route family it owns, and forwards no business request. §K/§O/§X isolation mechanics are untouched. |
| **IC-010** | Final | §J "the API Gateway is the **emitter**" | The **route-owning public edge** is the sole emitter of its own route's events. No audit class added, removed, renamed or re-homed. |
| **IC-010** | Final | §V "**Gateway-owned and typed**" composition | **Owner-owned and typed.** Every §V.1 condition and §V.2 prohibition unchanged; parity is proved byte-for-byte. |
| **IC-010** | Final | §H "the Database Router never authenticates" | **No change needed** — but worth redrafting to "performs no authentication" so consuming-vs-performing is explicit. |
| **IC-011** | Draft/Proposed | §Gate: "API Gateway as **sole served ingress**" is an EXPECTED condition; "a non-Gateway served edge → **STOP**" is a FAILURE condition | The two-public-edge topology trips this **by construction**. The hosted rollback gate cannot pass unamended. |
| **IC-009** | Final (R1) | §P.1 directory anonymity, §P.3 category→domain→database, the IC-007 four-prefix classifier | These clauses **lost their runtime subject** with `/directory` and the dispatcher. Decide: withdraw, or re-scope to the surviving surface. |
| **IC-012** | Draft/Proposed | §3 lists `api_gateway` among the unauthorized services; §Cross-ref asserts "the Gateway remains the sole served ingress" | Drop the deleted package from §3 and reconcile the cross-reference. |
| **IC-005** | Final | 13 Gateway references (mostly descriptive of the caller) | Re-read for accuracy once IC-010 is settled. |
| **Canonical Overview** | locked invariant **#7** | "**The Gateway is the boundary**" | This is a *locked* invariant. Changing it needs sign-off. |

**Then, and only then, in order:**

1. **Re-author the lost live proofs.** Five deleted and two refusing (§4). Most consequentially,
   there is **no live tenant-data-plane witness** and **no integrated Smoke C** for this topology.
   B5-BLK-4 has lost its harness.
2. **Decide the privilege question the previous experiment raised and this one did not resolve.**
   On `main` the only internet-facing process is structurally driver-free and credential-free.
   After removal, the Startup edge's process holds every tenant DSN plus a psycopg factory. The
   Workspace edge was narrowed to one read port (GF-9), but the Startup edge was not, and cannot be
   without a different design. This is pinned by GF-8/GF-8b and is unchanged by this task.
3. **Re-run the retargeted DDL-012 live proof** (`test_pg_gateway_audit_durable.py`) under a
   separate live authorization — it is currently UNVERIFIED against the new emitter.
4. **Widen DDL 012's `source_service` CHECK** so the last frozen residual can retire.
5. **Plan the frontend cutover** (§17).

---

## 19. Mandatory final posture

```text
API Gateway is ABSENT from the active Gateway-free MVP source/runtime/composition.
main remains untouched.
No push is authorized.
No PR is authorized.
No merge is authorized.
Only Dan may explicitly authorize the specific future PR merge.
No DDL change is authorized.
No live PostgreSQL change is authorized.
No Keycloak change is authorized.
No SecretRef/credential change is authorized.
No standing-runtime change is authorized.
Gate B remains NOT GRANTED.
Production remains NOT READY / DO-NOT-ACTIVATE.
```

> **A green gate is not merge authorization.** Every gate in §13 passes and every zero-residual
> check in §11 passes, and the removal is still **not adoptable**: a Final contract says the
> opposite of what the code now does. Present this result, obtain ratification of §18's amendment
> set, and obtain separate explicit authorization for any push, PR, or merge. Only a
> human-authorized merge may change `main`.

```text
COMPLETE API GATEWAY ZERO-RESIDUAL REMOVAL PASS WITH FROZEN HISTORICAL/DDL RESIDUALS
```
