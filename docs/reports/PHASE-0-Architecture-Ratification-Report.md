# Phase 0 — Architecture Ratification & Contract Reconciliation — Review Report

**Project:** SnackPortal2 · **Phase:** 0 · **Branch:** `phase/00-architecture-ratification` · **Base:** `main` @ `cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f`
**Instruction:** `Claude_Phase_0_Architecture_Ratification_GPT.md` · **Proposal under review:** `SnackPortal2_FastAPI_Implementation_Proposal_v2.2_GPT.md`
**Date:** 2026-08-20 · **Runtime code changed:** **NO** · **Merge authority:** Dan only · **Merge performed:** NO

---

## 0. Repository ground truth (established, not assumed)

Read in full before any edit: the v2.2 proposal, the phased branching instructions, `CLAUDE.md`, IC-001 through IC-012, `backend/pyproject.toml` (including the complete `[tool.importlinter]` block), all six service `main.py` composition modules, the nine ASGI edge modules, `shared/adapters/providers/fastapi_edge.py`, `shared/adapters/providers/asgi_runtime.py`, `docs/Architecture-Decision-Register.md`, `docs/runbooks/backend_service_startup_fastapi.md`, `.github/workflows/ci.yml`, and the architecture guard suite.

| Fact | Value |
|---|---|
| Service packages | 6 — `api_gateway`, `auth_router`, `control_plane`, `database_router`, `import_service`, `lineage_service` |
| Plus | `shared` (dependency leaf), `deployment` (cross-service composition root, IC-012) |
| HTTP edges | **9**, all FastAPI, each with a no-argument `create_app_from_env` factory |
| Edges per service | `control_plane` 4, `database_router` 2, `api_gateway` 1, `auth_router` 1, `deployment` 1 (Edge 9, Import) |
| `<service>/main.py` | **composition seam** (`build_*_from_env`) — **not** a FastAPI app, **not** executable |
| FastAPI construction | confined to `*/adapters/providers/http_*.py` via `shared...fastapi_edge.new_edge_app` |
| Uvicorn import | exactly **one** module, `shared/adapters/providers/asgi_runtime.py` |
| Canonical start | `uvicorn <module>:create_app_from_env --factory --host 127.0.0.1 --port <p> --workers 1 --no-access-log --no-server-header --no-proxy-headers` |
| OpenAPI / docs | **disabled on all nine edges** (`docs_url=None, redoc_url=None, openapi_url=None`) — IC-010 §R |
| Pydantic | **not used anywhere**; DTOs are frozen dataclasses; `pydantic` is not a declared dependency |
| Public surface | **1** — the API Gateway (standing `:8820`). The other eight bind loopback |
| import-linter | 8 root packages, **4 contracts**, 4 kept / 0 broken |
| Architecture guards | 1036 tests · full suite 2054 tests · both green at base |
| Last ADR decision | **D-44** (D-45 was free) |

**Ground-truth corrections found.** `CLAUDE.md` and the PRD Index both described the API Gateway as *scaffold-only, PRD 04 V2 not started*. That is stale: IC-010's own 2026-07-07 amendment records `IMPLEMENTS_BEHAVIOR = True` built under PRD 04 V2/V3, and the gateway serves a live FastAPI edge. Both documents were corrected — this was blocking, because a ratification that reasons from "the Gateway is a scaffold" reaches the opposite conclusion from one that reasons from "the Gateway is the only public surface and a privilege boundary".

---

## A. Architecture Conflict Matrix

Legend — **Conflict?** `NO` = already agrees · `NAME` = same substance, different naming · `YES` = genuine divergence · `GAP` = target component absent.

| Area | Current `main` | v2.2 target | Conflict? | Required ratification |
|---|---|---|---|---|
| Package layout | flat top-level packages: `shared`, six services, `deployment` | conceptual `src/snackportal2/{shared,services}/` | NAME | **R-7 — Option A**: retain flat layout, add new services as new top-level packages. The layout is pinned in setuptools, import-linter root packages + all 4 contracts, the scanner census, IC-012 §16, every runbook command and the launcher map; relocation improves no boundary. |
| API Gateway | `backend/api_gateway/`, built, **sole approved ingress** (IC-010 §A, Final), sole public surface | no dedicated custom API Gateway | **YES** | **R-1** — the ingress is **renamed and re-scoped to BFF**, not removed. IC-013 carries the designation; IC-010 amended insert-only with a *conditional* supersession; **runtime retained**. |
| BFF | **absent as a named role** (the Gateway performs ingress enforcement but no frontend orchestration or aggregation) | thin FastAPI BFF, the frontend's only door | **GAP** (role) | **R-1** — IC-013 §4 defines BFF responsibilities and the four things it must not duplicate. |
| Authentication | `auth_router`, IC-005 Final; OIDC stateless JWT; already separated from routing (D-01 A+B) | independently bootable FastAPI Authentication Service | NO | none — already ratified and built. |
| Access Control | **no service, no contract.** IC-005 delegates per-feature authz to "each feature contract"; no contract ever accepted it | independently bootable FastAPI Access Control Service | **GAP** | **R-2** — new **IC-014**; IC-005 amended with a references-only cross-reference. Tenant-scope authz **stays** in IC-005. |
| Control Plane | built, 4 edges, Control-DB owner | FastAPI Control Plane | NO | none. |
| Database Router | built, 2 edges; sole database selector (IC-010 §X) | FastAPI Database Router | NO | none — v2.2 §13/§14 restate existing law. |
| FastAPI app ownership | app built inside `adapters/providers` by a shared `new_edge_app` (fail-closed, empty-body, no docs) | `main.py` defines `app = FastAPI()` directly | **YES** | **R-5** — `main.py` stays the IC-012 §1 composition seam; the app object stays in the adapter containment zone. |
| Uvicorn startup ownership | one import site; `--factory` CLI is canonical; guards + runbook pin 5 flags; `--reload` forbidden in every governed path | `python main.py` with `uvicorn.run(reload=True)` | **YES** | **R-5** (later `__main__` entry so `python -m <service>.main` boots a service) + **R-6** (reload never enters a governed path; existing guards **not** relaxed). |
| Independent service boot | already true, per **edge**; 9 edges boot independently, 1 worker / 1 process | one bootable app per service | NAME | **R-5** — ratify explicitly that a service MAY own several edges; bootability is a property of the edge. |
| import-linter contracts | 4 contracts, 8 root packages, no `ignore_imports` | service independence + explicit clients only | NO | none in Phase 0. AMEND per new package, in the phase that creates it (**R-9**, IC-013 §15). |
| Shared package boundary | `shared` is a machine-enforced dependency leaf, technical code only | `shared/` technical only, no domain logic | NO | none — already stricter than v2.2 asks. |
| Startup service | absent (tenant Startup *routes* exist on the Database Router tenant-startup edge) | independently bootable Startup Service | **GAP** | **R-9** — new package; IC-002 + IC-008 govern. |
| Investor service | absent | independently bootable Investor Service | **GAP** | **R-9** — new package; **a Global Investor Contract is a known, still-open gap**. |
| Deal service | absent | independently bootable Deal Service | **GAP** | **R-9** — new package; IC-008 governs; IC-007 relevant. |
| Sharing service | absent | independently bootable Sharing Service | **GAP + BLOCKED** | **R-9** — **cannot be built while IC-007 is Draft / Proposed.** Governance gate, not a code gap. |
| Contacts service | absent | independently bootable Contacts Service | **GAP + NO CONTRACT** | **R-9** — **no contract exists for Contacts.** One must be authored before implementation. |
| AI Agent service | absent; `ai.invoke` reserved and unwired; IC-006 Draft | independently bootable AI Agent Service | **GAP + DEFERRED** | **R-9** — remains deferred (D-02 / Part 4B reservations); IC-014 reserves only the *decision shape*. |
| Audit service | not a separate service: Control-DB homed, three ingest edges, taxonomy split across IC-001/002/003/010 | independently bootable Audit Service | **YES (shape)** | **R-9** — extracting audit into its own service would relocate audit-class homes across four Final contracts. **Deliberately left undecided**; decide at its own phase. |
| API/DTO strategy | frozen dataclasses; hand-serialized bytes; validation errors collapsed to fixed status + **empty body** | Pydantic models provide validation, response schema, OpenAPI | **YES** | **R-4** — Pydantic **forward-only**. Existing edges' bytes are pinned; retrofitting `response_model` would change the wire. |
| OpenAPI | disabled on all nine edges (IC-010 §R) | every service exposes its own OpenAPI | **YES** | **R-3** — **by surface class**: internal edges stay closed; the ingress MAY expose in a development profile only. |
| Enterprise Security Edge | none; TLS at a reverse proxy (deployment scope) | none in development; optional in deployment | NO | **R-8** — ratify the existing posture. |

### Answer to instruction §7 (A or B)

**A — adapt the existing provider/runtime abstraction while adding independent service entrypoints.** Replacement of the runtime ownership model is **not** required and is **not** recommended.

Evidence: the repository already delivers every substantive v2.2 runtime property — one FastAPI app per edge, a no-argument fail-closed factory, an independent process per edge, an explicit port, one worker, and no cross-edge startup dependency. What differs is (i) which file the app object lives in and (ii) the absence of a `python main.py` convenience entry. Both are additive. Replacing the model would discard the fail-closed edge posture, the byte-pinned envelopes, the single Uvicorn containment site, and the five-flag disclosure suppression — all of which are load-bearing and none of which v2.2 asks to remove.

### Answer to instruction §8 (Option A / B / C)

**Option A — retain the current package layout and implement v2.2 behaviour within it.** Rationale in **R-7** above. No runtime package is moved in Phase 0, and none should be moved later without a separate ratified decision.

---

## B. Contract Inventory

| Artifact | Status before | Disposition | Reason |
|---|---|---|---|
| `contracts/IC-001` Global Startup | Final | **KEEP** unchanged | Bootstrap and global-directory residency untouched. |
| `contracts/IC-002` Tenant Startup | Final | **KEEP** unchanged | Tenant isolation, readiness, audit homes untouched. |
| `contracts/IC-003` Import | Final | **KEEP** unchanged | Import ≠ synchronization already matches v2.2 §28. |
| `contracts/IC-004` Lineage | Final | **KEEP** unchanged | Matches v2.2 §29. |
| `contracts/IC-005` Authentication Routing | Final | **AMEND — insert-only** | Cross-cutting authorization homed in IC-014. Authentication, token validation, carrier law, membership law, active-tenant law, JWT lifecycle **unchanged**; **tenant-scope authorization stays here**. |
| `contracts/IC-006` AI Gateway | Draft | **KEEP** unchanged | AI remains deferred; IC-014 reserves a decision *shape* only. |
| `contracts/IC-007` Sharing | Draft / Proposed | **KEEP** unchanged — **blocking** | The Sharing service in the ratified census cannot be built until IC-007 is Final. |
| `contracts/IC-008` Ownership | Final | **KEEP** unchanged | Ownership stays reference-only and never authorizes; IC-014 uses it as evidence only. |
| `contracts/IC-009` Portal | Final | **KEEP** unchanged | Portals remain presentation-layer. |
| `contracts/IC-010` API Gateway | Final | **AMEND — insert-only** | Conditional supersession of the §A ingress designation by IC-013; §R restated unchanged for internal edges. **Every rule inherited; runtime retained.** |
| `contracts/IC-011` Hosted Rollback | Draft / Proposed | **KEEP** unchanged | Out of scope. |
| `contracts/IC-012` Service Composition | Draft / Proposed | **KEEP — deliberately not amended** | No new cross-service composition module is created. §1 defines the `main` seam that R-5 preserves; §5.1 stays the gate for any future module. |
| `contracts/IC-013` BFF & Service Ingress | — | **NEW — Draft / Proposed** | The ingress designation, the BFF role and prohibitions, the service runtime shape, surface-class disclosure, layout, and the per-phase enforcement requirements. |
| `contracts/IC-014` Access Control | — | **NEW — Draft / Proposed** | The missing home for cross-cutting authorization, with the prohibitions that keep it out of the isolation path. |
| `docs/Architecture-Decision-Register.md` | D-44 last | **AMEND — additive** | D-45 register row + detail entry. |
| `docs/D-45-…-Ratification.md` | — | **NEW** | The full decision pack, R-1…R-9. |
| `CLAUDE.md` | stale Gateway status | **AMEND** | Corrected status; IC-013/IC-014 listed; target architecture pointer. |
| `docs/SnackPortal2_PRD_Index.md` | B-7 "scaffold; V2 next" | **AMEND** | Stale; corrected. |
| `docs/SnackPortal2_Action_Tracker.md` | — | **AMEND** | Phase 0 recorded; Contacts-contract and IC-007 gates added as tracked items. |
| `backend/pyproject.toml` | 4 import-linter contracts | **KEEP — unchanged** | See section F. |
| `docs/runbooks/backend_service_startup_fastapi.md` | 9 edges pinned | **KEEP — unchanged** | No edge added or removed. |
| `.github/workflows/ci.yml` | validate + secret-scan | **KEEP — unchanged** | No new tool or step needed. |

**Still-open contract gaps surfaced (not closed by Phase 0):** a **Contacts** contract does not exist; the **Global Investor Contract** does not exist; **IC-007** must reach Final before Sharing; **audit-as-a-service** placement is undecided.

---

## C. Ratification Patch — exact files changed

All contract edits are **insert-only**: `git diff --numstat` shows **0 deletions** across `contracts/` and `docs/Architecture-Decision-Register.md`.

| File | Change | Purpose |
|---|---|---|
| `docs/D-45-FastAPI-v2.2-Target-Architecture-Ratification.md` | **new** | The decision pack: R-1…R-9, what is not reopened, what is not authorized, traceability. |
| `docs/Architecture-Decision-Register.md` | +1 table row, +1 detail section | Register D-45 in house format (Decision / Reason / Amendment scope / Runtime status / Status / Affected contracts / Source). |
| `contracts/IC-013-BFF-And-Service-Ingress-Contract.md` | **new** | §1 purpose · §2 singularity of ingress · §3 inherited IC-010 rules · §4 BFF responsibilities and prohibitions · §5 service clients · §6 four-way separation · §7 bootable service shape · §8 composition seam vs app object · §9 many edges per service · §10 runtime supervision (no reload on governed paths) · §11 API shape and surface-class disclosure · §12 deployment boundary · §13 layout · §14 anti-vendor-lock-in · §15 enforcement requirements for the implementing phase · §16 contract impact · §17 exclusions. |
| `contracts/IC-014-Access-Control-Contract.md` | **new** | §1 the gap · §2 four-way separation · §3 decision inputs · §4 the eight prohibitions · §5 decision surface · §6 relationship to IC-005/008/010/013/006/002 · §7 service shape · §8 enforcement requirements · §9 exclusions. |
| `contracts/IC-010-API-Gateway-Contract.md` | +1 header amendment note, +1 trailing section | Record the **conditional** supersession of §A; restate §R unchanged for internal edges; state that the runtime is retained and every rule inherited. |
| `contracts/IC-005-Authentication-Routing-Contract.md` | +1 header amendment note, +1 trailing section | Cross-reference IC-014; state explicitly that **tenant-scope authorization does not move**. |
| `CLAUDE.md` | 2 edits | Correct the stale Gateway status; add IC-013/IC-014; point at D-45. |
| `docs/SnackPortal2_PRD_Index.md` | 1 edit | Correct the stale B-7 status. |
| `docs/SnackPortal2_Action_Tracker.md` | 1 edit (4 rows) | Record Phase 0; track the Contacts contract gap and the IC-007 gate. |
| `docs/reports/PHASE-0-Architecture-Ratification-Report.md` | **new** | This report. |

**Not changed:** any file under `backend/` (no runtime code, no `pyproject.toml`, no test, no guard), `infrastructure/`, `.github/`, and every runbook.

---

## D. Runtime Migration Plan

Staged so no step depends on a rewrite, and each is independently reviewable.

**M0 — Ratification (this phase).** Contracts and documents agree with the direction. No code. *Gate: Dan merges `phase/00-architecture-ratification`.*

**M1 — Runtime foundation gap-fill (Phase 1).** Additive only; see section E.

**M2 — Access Control service (Phase 3).** New `access_control` package: register in setuptools, import-linter root packages + independence contract, and the scanner census; traceability metadata naming IC-014; a fail-closed factory; a runbook command; guards proving it imports no database driver and has no fail-open branch. IC-014 promoted Draft → Final at merge.

**M3 — BFF orchestration on the existing ingress (Phase 4).** Add frontend orchestration, aggregation and permission-aware responses **to the existing `api_gateway` service**, and route its access decisions to the Access Control service. Every IC-010 enforcement path is untouched. **No rename yet.** IC-013 promoted Draft → Final at merge.

**M4 — Ingress rename (separate, mechanical, its own PR).** `api_gateway` → `bff` as a pure rename: package directory, setuptools list, import-linter root packages + all four contracts, scanner census, traceability metadata, runbook targets, the governed launcher module map, and the guard file names that reference it. Isolate this from behaviour change so its diff is reviewable as a rename. **Optional** — the role is ratified independently of the identifier, and skipping M4 costs nothing architecturally.

**M5 — Control Plane + Database Router conformance (Phase 5).** Already built; confirm readiness and fail-closed routing against IC-013 §7 and add anything missing. Expected to be small.

**M6 — Domain services (Phases 6–7).** Startup, Investor, Deal, Contacts, then Sharing/Introduction, Import, Lineage, Audit. Each new package repeats the M2 registration checklist. **Sharing is gated on IC-007 Final. Contacts is gated on a Contacts contract existing.**

**M7 — AI Agent foundation (Phase 8+).** Remains deferred. Requires the governance gate reserved in the canonical overview Part 4B before it starts.

**M8 — Enterprise deployment integration (Phase 10).** In front of the ingress only; absorbs no SnackPortal2 decision.

**Rule for every stage:** a package registration is never split from the change that creates the package — an unregistered package is invisible to the import-linter graph and can silently become a back-channel between two services.

---

## E. Phase 1 Revised Scope

The v2.2 §52 Phase 1 list ("repository structure; service `main.py` convention; Pydantic settings; logging; correlation; errors; health/readiness; OpenAPI") reads as greenfield. Against the real repository, **most of it already exists**. Phase 1 must therefore be a controlled gap-fill, not a rewrite.

**Already built — Phase 1 MUST NOT redo or restructure these:** repository structure and package boundaries; per-edge FastAPI apps and fail-closed factories; the single Uvicorn containment site; independent per-edge startup with one worker and one process; `shared/errors.py`, `shared/logging.py`, `shared/context.py` (correlation), `shared/health.py`, `shared/config.py`, `shared/portability/`; the nine pinned runbook commands and the governed launcher.

**In scope for Phase 1 (all additive):**

1. **Module entry points.** Add `if __name__ == "__main__":` to each `<service>/main.py` so `python -m <service>.main` starts that service through `shared...asgi_runtime`, calling the **same** factory the canonical command calls. The FastAPI app object does **not** move (IC-013 §8). Add a guard proving the entry point creates no second composition path.
2. **Pydantic settings — scoped.** Introduce Pydantic-based settings for **new** configuration surfaces only. Requires adding `pydantic` to `[project] dependencies` **and** updating the guard that pins the dependency list exactly, in the same change. Existing env parsing is not rewritten.
3. **Readiness parity.** Only `api_gateway` and `control_plane` carry a readiness module today. Give every edge a distinct liveness and readiness signal per IC-013 §7, minimally disclosing, never revealing tenant or database existence.
4. **Ingress OpenAPI, development profile only.** Enable schema generation and interactive documentation on the ingress **only** when the portability profile is explicitly a development one. Internal edges stay closed. Add a guard proving a hosted profile cannot enable it.
5. **Central service-port configuration.** One place that maps edge to port, consistent with the two disjoint port maps the runbook already pins (standing vs isolated smoke). Do not merge the two maps.
6. **Phase 1 tests** for each of the above, plus guards for items 1 and 4.

**Explicitly out of Phase 1 scope:** any new service package; any Authentication, Access Control, routing, domain or AI behaviour; the ingress rename; any package move; any change to the nine existing edges' request-validation or response-serialization posture; enabling reload on any governed path.

**Phase 1 is small.** That is the correct outcome of Phase 0: most of the foundation is built, and the honest scope is the delta.

---

## F. Test / Guard Impact

**Phase 0 impact: none.** No guard was added, changed, relaxed, or deleted. The four import-linter contracts are byte-unchanged and still report **4 kept / 0 broken**.

Import-linter disposition per instruction §10:

| Contract | Disposition | Reason |
|---|---|---|
| `shared is a dependency leaf` | **KEEP** | v2.2 §19 asks for exactly this; already stricter. |
| `services are mutually independent` | **KEEP** (AMEND later) | Encodes v2.2 §21. Each new service package must be **added** to it in the phase that creates it — widening the module list is a strengthening, not a relaxation. |
| `nothing may import the deployment composition root` | **KEEP** | Unrelated to the ratified change; the root stays the top of the DAG. |
| `the deployment root may compose only the authorized Edge 9 services` | **KEEP** | Narrow by design. Any widening needs an IC-012 §5.1 amendment — **not** a Phase 0 edit. |

**Guards that must change later — and only because the ratified architecture changes:**

| Guard / pin | Trigger | Change |
|---|---|---|
| `tests/architecture/test_traceability.py` (`BUILT_SERVICES`) | any new service package | add the package; declare `GOVERNING_CONTRACTS` and `IMPLEMENTS_BEHAVIOR`. |
| `tests/architecture/_scan.py` (`SERVICE_PACKAGES`) | any new service package | add it, so the repo-wide sweeps actually see it. |
| `test_b5_5_smoke_c_spec_and_crypto_fixture.py` (exact dependency list) | first direct Pydantic use | the list is asserted **exactly**; adding `pydantic` without updating it fails CI. |
| `test_native_uvicorn_factories.py` (`_EDGES`, `_SERVER_SEAMS`, runbook flags) | any new edge; module entry points | extend the census; the entry point must not create a second composition path. |
| `test_standing_launcher_flags.py` | any new standing edge | extend the launcher template and flag census. |
| `test_gateway_edge_boundaries.py`, `test_phase7_api_gateway.py`, `test_ic010_*`, `test_gateway_operational_audit_boundaries.py`, `test_aw1_gateway_audit_writer_boundaries.py` | **M4 rename only** | path and identifier updates. Behavioural assertions must survive the rename **verbatim** — if any has to be weakened to make the rename pass, the rename is wrong. |
| `shared/adapters/providers/fastapi_edge.py` docs/OpenAPI posture | ingress development-profile OpenAPI | must remain the default-off shape; the ingress opt-in is profile-gated, never a change to `new_edge_app`'s default. |
| `test_native_uvicorn_factories.py:261`, `test_standing_launcher_flags.py:205` (reload prohibition) | **none** | **Do not relax.** R-6 ratifies the prohibition rather than the flag. |

**Anti-pattern to refuse in every later phase:** loosening a guard so a migration passes. A guard that fails during migration is reporting that the migration changed a boundary, and the boundary is what the guard exists to hold.

---

## G. Phase 0 Review Report

```text
PHASE 0 REVIEW REPORT

Repository:            SnackPortal2 (worktree D:\Pitchsnack\SnackPortal2-phase-00)
Branch:                phase/00-architecture-ratification
Base commit:           cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f  (= main = origin/main)
Phase commit:          see section H
Remote branch pushed:  YES
Working tree clean:    YES (after commit)

Architecture conflicts found:
- API Gateway vs Gateway-free target: IC-010 §A designates the Gateway the SOLE approved ingress
  (Final). v2.2 requires no dedicated custom API Gateway. Resolved by RENAMING the ingress role to
  BFF rather than removing a component that is the only public surface and therefore a privilege
  boundary. Runtime retained.
- BFF role absent: no component owns frontend orchestration or aggregation.
- Access Control absent, with NO governing contract: IC-005 delegated per-feature authorization to
  "each feature contract" and no contract ever accepted it.
- main.py semantic collision: repo main.py is the IC-012 §1 composition seam; v2.2 main.py is the
  FastAPI app plus uvicorn.run.
- OpenAPI: disabled on all nine edges as an IC-010 §R security posture; v2.2 mandates it.
- Pydantic absent entirely; existing edges' wire bytes are pinned and cannot take a response_model.
- reload=True: forbidden by two guards and the runbook on every governed path.
- Package layout: flat vs src/snackportal2/.
- One-app-per-service assumption is false here: control_plane owns 4 edges, database_router owns 2.
- Six target services absent (Startup, Investor, Deal, Sharing, Contacts, AI Agent); Sharing is
  BLOCKED by IC-007 being Draft; Contacts has NO contract at all; AI Agent remains deferred.
- Stale ground truth in CLAUDE.md and the PRD Index ("API Gateway is scaffold-only").

Contracts changed:
- IC-013 — BFF & Service Ingress Contract          NEW    (Draft / Proposed, IC-013-DRAFT-1)
- IC-014 — Access Control Contract                 NEW    (Draft / Proposed, IC-014-DRAFT-1)
- IC-010 — API Gateway Contract                    AMENDED (insert-only; 0 deletions)
- IC-005 — Authentication Routing Contract         AMENDED (insert-only; 0 deletions)
- IC-012                                           DELIBERATELY UNCHANGED
- Architecture Decision Register                   D-45 added (row + detail)
- D-45 decision pack, CLAUDE.md, PRD Index, Action Tracker, this report

Runtime code changed:
NO   (zero files under backend/ modified; git diff over backend/ is empty)

Import-linter changes:
- NONE. 4 contracts unchanged, 4 kept / 0 broken. Later AMENDs are listed in section F and are
  authorized only by the phase that creates the package they cover.

Tests/validation run (toolchain: repo venv, matching CI steps):
- ruff check .              PASS  (all checks passed)
- ruff format --check .     PASS  (392 files already formatted)
- mypy .                    PASS  (no issues in 390 source files)
- lint-imports              PASS  (4 kept, 0 broken)
- pytest tests/architecture PASS  (1036 passed)
- pytest (full default)     PASS  (2054 passed)
- Baseline before changes was identical on every line: no regression, no new test, no relaxed guard.

Result:
PASS WITH ISSUES

Issues (all governance, none blocking this branch; each needs a Dan decision or a later phase):
1. Sharing service cannot be built while IC-007 is Draft / Proposed.
2. Contacts service has no governing contract at all — one must be authored.
3. Global Investor Contract still does not exist (pre-existing gap, tracker item 19).
4. Audit-as-a-separate-service is deliberately left undecided: extracting it would relocate audit
   class homes across four Final contracts.
5. The ingress rename (api_gateway -> bff) is ratified as OPTIONAL and deferred to its own PR;
   the role is ratified independently of the identifier.
6. Adding pydantic will break an exact-dependency-list guard unless updated in the same change.

Ready for human review:
YES

Merge performed:
NO
```

## H. Commit

| Field | Value |
|---|---|
| Branch | `phase/00-architecture-ratification` |
| Base | `cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f` |
| Commit | recorded in the branch history at push time |
| Files | 10 (4 new, 6 modified) — none under `backend/` |
| Deletions in `contracts/` | 0 |

**No merge authorization has been given, and none is inferred.** Phase 1 is not started.
