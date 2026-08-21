# SnackPortal2 — Option A Clean FastAPI Rebuild
# Phase 0.5 — Contract Reconciliation

**Branch:** `phase/00.5-contract-reconciliation`
**Base:** `main` @ `cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f`
**Date:** 2026-08-21
**Author:** Claude (Claude Code)
**Governing instruction:** Dan's Phase 0.5 instruction of 2026-08-21 + `SnackPortal2_Option_A_Clean_FastAPI_Rebuild_Claude_GPT.md`
**Status:** **PASS** — finalized 2026-08-21 under **D-47**. CONF-1 resolved; **10 of 12 conflicts closed**; 2 remain as named prerequisites.
**Finalization (2026-08-21, D-47):** Dan accepted the Phase 0.5 direction and ratified the two items it left open — **CONF-4** (AI ownership cardinality → **Option A**) and the **service startup/exposure model** (CONF-9 finalized on the BIND-vs-PUBLISH distinction). See §11.

> **Scope discipline.** Documentation, contracts and governance only. **No FastAPI runtime implementation was started. No old backend code was deleted. No branch was merged. Nothing was pushed.** The stale `phase/01-fastapi-runtime-foundation` worktree was left untouched.

---

## 1. Repository ground truth

| Fact | Value |
|---|---|
| Branch created | `phase/00.5-contract-reconciliation`, **from `main`**, HEAD == `main` verified |
| Base commit | `cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f` |
| `main` vs `origin/main` | 0 ahead / 0 behind — local `main` current |
| Working tree at branch creation | clean |
| Phase 0 branch | `phase/00-requirements-extraction` @ `5a2d106c3` — preserved, unmerged |
| Abandoned ratification branch | `phase/00-architecture-ratification` @ `5e8d9d92` — untouched, **nothing cherry-picked** |
| Stale Phase 1 worktree | `phase/01-fastapi-runtime-foundation` @ `cdb46fc9d` — **untouched, treated as untrusted** |

*Note:* the Phase 0 report lives on the Phase 0 branch, not this one, because the instruction specified branching from `main`. It is referenced throughout and is not duplicated here.

---

## 2. What was produced

### New artefacts (3)

| File | What it is |
|---|---|
| `docs/D-46-Option-A-Gateway-Free-Target-Architecture-Ratification.md` | The anchor decision. Ratifies the Gateway-free target, supersedes IC-010, revises locked invariant #7, ratifies the four-way separation, and carries the **exhaustive section-by-section re-homing map** (§4) plus the disposition of all 12 Phase 0 conflicts (§6). |
| `contracts/IC-013-BFF-Ingress-Contract.md` | `Draft / Proposed`, IC-013-DRAFT-1. 26 sections. The single frontend-facing ingress; the enumerated operation surface; the four re-homed Gateway-only behaviours; the independently-bootable service shape and serving posture; the incremental cutover rules. |
| `contracts/IC-014-Access-Control-Contract.md` | `Draft / Proposed`, IC-014-DRAFT-1. 16 sections. The first governing specification for authorization in SnackPortal2 — the one genuinely greenfield service. |

### Added at finalization (D-47, 2026-08-21)

| File | What it is |
|---|---|
| `docs/D-47-AI-Ownership-Cardinality-And-Service-Exposure-Model.md` | Dan's two ratifications: AI ownership cardinality (Option A) and the service exposure model (BIND vs PUBLISH). Records three divergences it creates but does not resolve. |

### Amended, insert-only (5 contracts)

| Contract | Change | Status after |
|---|---|---|
| **IC-010** | Supersession banner + status change. **No normative text deleted** — the contract is preserved verbatim below the banner for audit continuity. | `Final` → **`Superseded`** |
| **IC-009** | Composing seam re-pointed from the API Gateway to the BFF; `IC-010 §V` → `IC-013 §19`; `§Q` → `IC-013 §16`. **DTO catalogue, field sets, provenance markers, visibility matrix and revision `IC-009-R1` all unchanged.** | `Final` (unchanged) |
| **IC-005** | Access Control named as a distinct service; the new flow stage recorded; ingress and audit-emitter seam re-pointed. **No change to token validation, JWKS, claims, roles, carriers or denial semantics.** | `Final` (unchanged) |
| **IC-012** | Principles carried forward and re-scoped to the Option A `deployment/` root; Edge-9 specifics marked historical; §13 import-linter requirement survives in full. | `Draft / Proposed` (unchanged) |
| **IC-008** *(D-47)* | AI-ownership cardinality ratified: at most one *current* AI Owner, single reference, never a set or join table; contribution ≠ ownership; succession audited; task-history gap recorded; Option C reserved. Human ownership and all five Ownership Principles untouched. | `Final` (unchanged) |
| **IC-013** *(D-47)* | New **§21.1 Exposure Model (E-1…E-7)** replacing the earlier bind-only wording; §13 re-pointed; §20 gains the exposure proof; §24 gains prohibitions 15–18. | `Draft / Proposed` (unchanged) |
| **IC-014** *(D-47)* | §7 interim holding rule replaced by the ratified cardinality + *contribution is never an authorization input*; §12 exposure re-pointed at IC-013 §21.1. | `Draft / Proposed` (unchanged) |

### Governance documents updated (5)

`docs/Architecture-Decision-Register.md` (D-45 VOID row + D-46 row + a post-D-46 addendum reconciling the closing note) · `docs/SnackPortal2_Canonical_Overview_and_Decisions_v2.md` (invariant #7 revised, #9 added, #3 flagged, the "one doorway" diagram updated, amendment banner) · `CLAUDE.md` (project status, contract list, service components, interim-exception wording) · `docs/SnackPortal2_Action_Tracker.md` (items 21–30) · `docs/SnackPortal2_PRD_Index.md` (B-7 retired; B-13/B-14/B-15/B-16 added).

---

## 3. CONF-1 — how it was resolved

**The conflict.** `IC-010` was **Final** and its Purpose read *"Define the **API Gateway** as the **sole approved ingress** into SnackPortal2 services."* Canonical Overview locked invariant **#7** read *"The Gateway is the boundary."* `CLAUDE.md` constraint **#5** requires contracts to precede code. Option A mandates zero API Gateway. Nothing on `main` superseded any of it — so under this project's own governance, Phase 1 could not lawfully begin.

**The resolution.**

1. **IC-010 → `Superseded`**, jointly by IC-013 and IC-014. It is retained as the historical record and the traceability source for its successors, and is no longer normative for implementation.
2. **Locked invariant #7 revised** — "the Gateway is the boundary" becomes "**the BFF is the boundary**". *The substance is preserved and unweakened*: one governed public ingress, no client path around it. Only the component holding that position changes.
3. **Every IC-010 section is redistributed, not discarded.** D-46 §4 is an exhaustive map: 23 sections, each with a named new home and an explicit disposition. Where a rule is marked *Changed*, the change is the holder or the stage list — never a relaxation.
4. **Governance effect.** With IC-010 superseded and #7 revised, constraint #5 is satisfied for Phase 1: the target architecture now has contract authority. D-46 itself **authorizes no implementation**.

**Why this is not a rename.** IC-013 §0 draws the distinction that makes the difference operative rather than cosmetic:

> A gateway is *operation-agnostic*: it forwards whatever arrives at whatever path, and its surface grows by configuration. The BFF is *operation-enumerated*: every surface is a named frontend use case, declared in the contract's operation set, backed by a Pydantic request/response model, and composed from typed service results. **A BFF surface that merely relays a downstream body is, by this definition, a gateway route and is forbidden.** Adding a surface is a contract change, not a config change.

The names *API Gateway*, *FastAPI Gateway*, *BFF Gateway*, *Service Gateway*, *Routing Gateway* and *Compatibility Gateway* are prohibited, and the word "gateway" MUST NOT appear in the BFF's package, modules, routes, config keys, or environment-variable prefixes.

---

## 4. The four re-homed security behaviours

Phase 0's most consequential warning was that four load-bearing behaviours live **only** inside the Gateway, and that deleting the package without re-homing them would be a security regression **no test would catch** — because the tests proving them are themselves category D. Each now has a named contractual owner:

| Behaviour | Was (Gateway) | Now |
|---|---|---|
| Carrier extraction + prohibited-carrier rejection — exactly two recognized carriers; cookies / query-string / portal / workspace / local-storage prohibited as routing authority | `api_gateway/carrier.py` (IC-010 §E) | **IC-013 §5** |
| `RequestContext` constructed **exclusively** from `AuthContext`; no inbound tenant/workspace parameter may reach the router (D-33 §4.6 keystone) | `api_gateway/request_context.py` (IC-010 §G/§T) | **IC-013 §7** |
| The ingress audit emit-set — four denial/anomaly classes + success-access subclasses, references-only | `api_gateway/gateway.py` (IC-010 §J) | **IC-013 §10** (emission) + Audit Service (durable sink) |
| Single-database assertion — one request → one active tenant → one physical database | `api_gateway/dispatch.py` `assert_single_database` (IC-010 §K) | **IC-014 §5.4** (decision) + **IC-013 §11** (enforcement) |

The last one is split deliberately. IC-013 §11 states the reason: *"a decision without enforcement is advisory, and enforcement without a decision is a guess."*

IC-013 §20 additionally requires **re-homing proof** — architecture tests that each of the four is present and enforced at its new home — as an acceptance criterion for the future implementation.

**One further protection was added, not carried forward.** Phase 0 observed that the Gateway is not only a router but a **privilege boundary**: it is the only public surface, and it is what keeps the public tier away from tenant DSNs. IC-013 §13 therefore adds a **deployment obligation**: *no backend service other than the BFF may be bound to a public interface.* A deployment in which another service is publicly reachable violates the contract regardless of what any application-layer check does.

---

## 5. Disposition of all twelve Phase 0 conflicts

| # | Conflict | Outcome |
|---|---|---|
| **CONF-1** | IC-010 Final = "sole approved ingress" | ✅ **RESOLVED** — §3 above |
| **CONF-2** | IC-009 DTOs contractually gateway-composed | ✅ **RESOLVED** — seam re-pointed to the BFF; catalogue and `IC-009-R1` unchanged |
| **CONF-3** | Control DDL 012 `CHECK (source_service='api_gateway')` | ✅ **RESOLVED in contract**; migration **M-1 specified, not authored** (D-46 §7) — a *new* append-only table is the approved approach, leaving 012/013 and their byte-pins intact |
| **CONF-4** | Ownership cardinality — three sources disagree | ✅ **RESOLVED 2026-08-21 (D-47 §1)** — Dan ratified **Option A**: at most one *current* AI Owner; contribution ≠ ownership; Option C reserved. §7 below records the outcome. |
| **CONF-5** | AI Phase 9 vs the D-02/D6 deferral + all-TBD IC-006 | 🟡 **PARTIAL** — the Option A directive reopens the deferral for Phase 9; **IC-006 must reach Draft-complete first**; the Part 4B governance gate is unwaived |
| **CONF-6** | Sharing Phase 8 vs Draft IC-007 | ⬜ **NAMED PREREQUISITE** — IC-007 must be promoted to `Final`; that is a governance act requiring Dan |
| **CONF-7** | Contacts has no contract | ⬜ **RESERVED as IC-015**, unauthored — it is new product specification, not reconciliation |
| **CONF-8** | `main.py` convention vs uvicorn containment | ✅ **RESOLVED** — IC-013 §21 ratifies the app-factory shape; uvicorn stays confined to one shared runtime module; `uvicorn.run(...)` permitted only under `if __name__ == "__main__":` as a dev convenience, never the production start path |
| **CONF-9** | `0.0.0.0` / `reload=True` / missing flags | ✅ **RESOLVED, then FINALIZED 2026-08-21 (D-47 §2)** — restated on the **BIND vs PUBLISH** distinction at **IC-013 §21.1 E-1…E-7**: only the BFF is a public ingress; loopback/private by default in local dev; containers may bind internally but **never publish**; `reload` local-dev only; the five uvicorn flags are a set; and a **deployment-manifest check** is required because the rule is violated by configuration, not code |
| **CONF-10** | Global directory gaps | 🟡 **PARTIAL** — `owner_agent_ref` recorded as migration **M-2**; Global Investor Contract and D-35 Global Deal Directory remain named prerequisites |
| **CONF-11** | IC-012 governs a root Option A replaces | ✅ **RESOLVED** — principles carried forward and re-scoped; Edge-9 specifics historical; §13 import-linter requirement survives |
| **CONF-12** | 3 backend operations vs 86 frontend expectations | ✅ **ADDRESSED** — IC-013 §22 makes cutover **incremental and per-operation by contract**; full parity is *not* a Phase 10 precondition, but a governed enumerated cutover set is; the old Gateway must not be used as a bridge |

**Closed: 10. Partial: 1 (CONF-10). Named prerequisite: 1 (CONF-6).** *(CONF-4 and CONF-9 closed by D-47; CONF-5's directive question is settled — only the IC-006 authoring prerequisite remains.)*

---

## 6. Verification

Re-run after the D-47 finalization edits:

| Check | Result |
|---|---|
| **Complete test suite** | **2054 passed**, 0 failed — identical to the Phase 0 baseline |
| **Architecture guards** | **1036 passed**, 0 failed |
| Runtime code changed | **NONE** — `git diff main -- backend/` is empty |
| DDL changed | **NONE** — DIV-1 recorded, not fixed |
| Tests changed | **NONE** — DIV-2 recorded, not fixed |
| `api_gateway` package | **untouched on disk** — byte-identical to `main` |
| Contracts restored after probes | **byte-identical** (`cmp` clean) |

### 6.1 — Guard coverage is real for three contracts, and absent for one

A passing suite after editing contract prose means nothing unless the guards actually *read* those files, so this was measured rather than assumed.

| Probe | Result | Reading |
|---|---|---|
| Blank `IC-005` + `IC-009` + `IC-010` | **53 failed**, 983 passed | ✅ **Guard-covered.** The insert-only amendments preserved every anchor these guards assert on — no guard was weakened, retired, or edited. |
| Blank `IC-008` | **1036 passed** — zero failures | ⚠️ **NOT guard-covered.** See below. |

**⚠️ Finding — the assurance posture on ownership is inverted.** `IC-008` can be deleted in its entirety without a single test noticing. Meanwhile the tenant DDL that *contradicts* it **is** guarded — `test_ownership_pk_shapes` actively asserts the composite-PK join-table shape (DIV-2).

So the artefact that is **authoritative** (the contract, just ratified by Dan) is **unenforced**, while the artefact that is **superseded** (the DDL's zero-or-more shape) is **machine-enforced**. Nothing is currently wrong in the repository as a result — no code reads either — but it means:

1. The D-47 ratification of IC-008 carries **no automated protection** against future drift.
2. When Phase 7 reconciles the DDL, the *only* mechanical signal will be the guard that encodes the **rejected** shape, which will fail and invite being weakened rather than corrected.

**Recommendation:** the Phase-7 commit that reconciles DIV-1/DIV-2 should also add an **IC-008 cardinality guard** — asserting the contract states at-most-one-current AI owner and that no `*_ai_ownership` composite-PK table survives — so the corrected shape is enforced from the authoritative side rather than only negated on the DDL side. Recorded as tracker item 23d.

**IC-013 and IC-014 are new and therefore unguarded by construction.** Their acceptance criteria (IC-013 §20, IC-014 §13) specify the guards that must exist once the services are built; none can exist before Phase 1.

---

## 7. CONF-4 — ✅ RATIFIED (D-47 §1)

**Dan ratified Option A on 2026-08-21.**

> **At most one *current* AI Owner per record.** Multiple AI Agents may **contribute** to a record, but contribution is recorded through **task history, provenance and audit** and does not create multiple AI ownership. **Option C is reserved** for a later decision if Phase 9 proves it necessary.

**What this settles.** IC-008 prevails over the tenant DDL and over the old wording of invariant #3. AI ownership is a **single reference on the record — never a set, never a join table.** *"Current"* is a **cardinality bound, not a permanence claim**: ownership may pass between AI Agents over time, at most one holder at any instant, each succession an audited transfer with history retained. **Contribution is never an authorization input** (IC-014 §7) — which follows *a fortiori* from Ownership Principle 1: if owning a record grants nothing, contributing to one grants strictly less. **Activation is unchanged** — this settles cardinality, not activation; `owner_ai_agent_ref` stays NULL platform-wide until IC-006.

**Contracts updated:** IC-008 (insert-only amendment + the *AI Ownership Rule* section), IC-014 §7 (the interim holding rule replaced by the ratified rule), D-46 §6/§8, Canonical Overview invariant #3, and the decision register.

### 7.1 — Three divergences created, recorded not resolved

| # | Divergence | Disposition |
|---|---|---|
| **DIV-1** | Tenant DDL `006_ownership.sql` still implements the rejected zero-or-more join-table shape (`startup_ai_ownership`, `investor_ai_ownership`, `deal_ai_ownership`, composite PK) | **Phase 7** |
| **DIV-2** | `backend/tests/architecture/test_tenant_ddl_schema_guards.py::test_ownership_pk_shapes` (line 219) **actively asserts** `PRIMARY KEY ({entity}_id, ai_agent_id)` — a guard that now **enshrines the shape the ratification rejects** | **Phase 7 — same commit as DIV-1** |
| **DIV-3** | The **"task history" record class named by the ruling exists in no contract and no schema.** Provenance (IC-004) and operational audit (IC-002) exist; task history does not | **Phase 9 / IC-006** |

**DIV-2 is the one to watch.** Because the guard *requires* the composite PK, any DDL change satisfying the ratified rule will fail it. The DDL and the guard must therefore change in the **same commit** — otherwise either the schema change is blocked, or someone quietly weakens the guard to unblock it. Neither was touched here: Phase 0.5 is documentation and contracts, and Dan's instruction is explicit that Phase 1 has not begun.

**DIV-3 has a fail-closed holding rule.** Until task history is specified, contribution is recordable **only** through IC-004 provenance and IC-002 operational audit, and **no new record class may be invented at implementation time** to fill the gap.

---

## 8. Remaining prerequisites

| # | Prerequisite | Blocks | Why not done here |
|---|---|---|---|
| **P-1** | **Reconcile tenant DDL `006_ownership.sql` + `test_ownership_pk_shapes` in one commit** (DIV-1 + DIV-2) | Phase 7 | DDL is schema and the guard is test code; Phase 0.5 is documentation and contracts |
| **P-2** | **Specify the "task history" record class** (DIV-3) | Phase 9 | New specification, not reconciliation; attaches to IC-006 / the AI Agent Service |
| **P-3** | **IC-006 → Draft-complete** — every normative section reads `TBD`; Part 4B governance gate unwaived | Phase 9 | Authoring a full AI contract is new specification |
| **P-4** | **IC-007 → `Final`** | Phase 8 | Promoting a Draft to Final is a governance act requiring Dan |
| **P-5** | **IC-015 — Contacts Service Contract** (reserved, unauthored) | Phase 7 | Contacts has only DDL — nothing to reconcile *from* |
| **P-6** | **Global Investor Contract**; **D-35 Global Deal Directory** | Global directory work | New specification |
| **P-7** | **Migration M-1** — new append-only table for BFF ingress-edge audit; DDL 012's `CHECK (source_service='api_gateway')` physically rejects a BFF row | **all** BFF audit emission | SQL is implementation |
| **P-8** | **Migration M-2** — `control_directory.owner_agent_ref` per IC-008's global-ownership mandate | Global Directory mutation | SQL is implementation |
| **P-9** | **Deployment-manifest exposure check** (IC-013 §21.1 E-6) — prove exactly one service publishes a port and it is the BFF | Phase 1 acceptance | Implementation work |

**Nothing now blocks Phase 1 on a *decision*.** Every remaining item is authoring or implementation work with a named owner and a named phase. P-9 is the only one that attaches to Phase 1 itself.

---

## 9. Recommended next step

**Do not start Phase 1 yet** — Dan's instruction stands, and one governance step remains:

**Review and merge Phase 0 and Phase 0.5.** Both branches are unmerged. Until they land on `main`, `IC-010` is still `Final` there, invariant #7 still names the Gateway, and the CONF-1 blocker is formally still open on the mainline — the resolution exists only on these branches. **This is now the sole remaining gate on Phase 1.**

When Phase 1 is authorized, the recommended order from the Phase 0 report stands, now with contract backing:

1. **`shared/` first** — seeded from the existing shared kernel (16 files / 1,369 lines), plus the new `correlation/` module.
2. **14 service skeletons**, each independently bootable per **IC-013 §21** (app-factory shape, pinned serving posture, minimally-disclosing health/readiness per §17).
3. **Architecture guards immediately, not later** — the dependency DAG (re-expressed per IC-012 §13 against the new package graph), driver/vendor containment, references-only discipline, a **zero-Gateway census** (IC-013 §20), the **four re-homing proofs** (§4 above), and the **deployment-manifest exposure check** (P-9 — the only Phase-1-scoped prerequisite, and one a code-only test set cannot discharge).
4. **Then the Database Router** — the one component that already fully satisfies its target contract, with the strongest test evidence (140 tests + live-PG topology proof), and the service every other one depends on for its session seam.

Authentication and Access Control still precede the BFF, per Option A's ordering — which is correct, because the BFF must not occupy the public position before the services that guard it exist.

---

## 10. Non-overclaim

- **No FastAPI runtime implementation was started.**
- **No old backend code was deleted.** The `api_gateway` package, its 29 test files, its launcher and its runbooks are untouched and byte-identical to `main`.
- **No branch was merged. Nothing was pushed.**
- **No database migration was authored or applied.** M-1 and M-2 are specified only.
- **No DDL and no test was changed by the D-47 finalization.** DIV-1 (the tenant DDL still carries the rejected shape) and DIV-2 (a guard asserts it) are **recorded as Phase-7 work**, not silently fixed.
- **No blocker was closed.** Production remains **NOT READY / DO-NOT-ACTIVATE**.
- **No test was weakened, retired, or edited.** 2054 pass and 1036 architecture guards pass, unchanged from the Phase 0 baseline. Guard coverage was **measured, not assumed** — and the measurement surfaced that IC-008 is unguarded (§6.1).
- IC-013 and IC-014 are **`Draft / Proposed`** and authorize no implementation. Phase 1 proceeds only under a separate, explicitly-authorizing instruction from Dan.
- The stale `phase/01-fastapi-runtime-foundation` worktree was **not touched**.
- Nothing was cherry-picked from `phase/00-architecture-ratification`; every artefact was authored fresh. `D-45` is recorded **VOID** on `main` to prevent two contradictory decisions sharing one identifier.
- The Physical Multi-Database MVP is **mandatory and unchanged**, reinforced and never weakened.

---

## 11. Service startup & exposure — finalized (D-47 §2)

Dan's ruling, applied at **IC-013 §21.1** as normative rules **E-1…E-7**:

> For local development, internal FastAPI services must default to loopback/private exposure rather than public exposure. Only the BFF is permitted to be the governed public application ingress. `reload=True` is local-development only. Containerized internal services may bind internally as necessary, but their ports must not be publicly published.

**This corrected a real weakness in my first draft.** IC-013 §21 originally said *"`0.0.0.0` is prohibited outside a deliberately-configured deployment binding"* — which targets the wrong layer. Dan's formulation separates **BIND** from **PUBLISH**, and that distinction is what makes the rule both implementable and effective:

- A container binding `0.0.0.0` **inside its own network namespace** is normal and necessary — that binding reaches only the container network. A blanket prohibition would have been unimplementable, and an unimplementable rule gets ignored.
- A service correctly bound to a private interface and then **published** by one line in a compose file is publicly reachable no matter how careful the application code is.

The rules as applied:

| # | Rule |
|---|---|
| **E-1** | Only the BFF is a public ingress — no other service, in any environment |
| **E-2** | Local development: loopback/private **by default**; `0.0.0.0` is never an internal service's default bind |
| **E-3** | Containers: **bind internally, publish never** — no `ports:`, no `-p`; only the BFF's port may be published |
| **E-4** | `reload` is local-development only |
| **E-5** | The five uvicorn flags are **a set, not a menu** — omitting one silently restores a uvicorn default |
| **E-6** | A **deployment-manifest check** is required at Phase-1 acceptance |
| **E-7** | The contract prevails over any conflicting template, compose file, launcher, runbook or sample — Option A §4's `uvicorn.run(host="0.0.0.0", …, reload=True)` sample is **superseded** |

**Why E-6 is not optional polish.** E-1 and E-3 are violated by **configuration**, not by code. An application-layer test can prove a service binds correctly and still miss a compose file that publishes it. The manifest check is the only place the rule is actually enforceable — which is the same lesson Phase 0 recorded about the Gateway: removing it removed a **network position**, and network positions are defended by deployment configuration, not application logic.

Consequential edits: IC-013 §13 (deployment obligation re-pointed), §20 (exposure proof added to acceptance), §24 (prohibitions 15–18); IC-014 §12 — with the note that a directly-reachable *authorizer* is the most consequential exposure failure in the topology, since it can be asked for a decision no BFF flow ever requested.
