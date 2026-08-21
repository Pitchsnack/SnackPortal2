# SnackPortal2 — Option A Clean FastAPI Rebuild
# Phase 0.5 — Contract Reconciliation

**Branch:** `phase/00.5-contract-reconciliation`
**Base:** `main` @ `cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f`
**Date:** 2026-08-21
**Author:** Claude (Claude Code)
**Governing instruction:** Dan's Phase 0.5 instruction of 2026-08-21 + `SnackPortal2_Option_A_Clean_FastAPI_Rebuild_Claude_GPT.md`
**Status:** **PASS** — CONF-1 resolved; 8 of 12 conflicts closed; 4 recorded as named prerequisites or ratification items.

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

### Amended, insert-only (4 contracts)

| Contract | Change | Status after |
|---|---|---|
| **IC-010** | Supersession banner + status change. **No normative text deleted** — the contract is preserved verbatim below the banner for audit continuity. | `Final` → **`Superseded`** |
| **IC-009** | Composing seam re-pointed from the API Gateway to the BFF; `IC-010 §V` → `IC-013 §19`; `§Q` → `IC-013 §16`. **DTO catalogue, field sets, provenance markers, visibility matrix and revision `IC-009-R1` all unchanged.** | `Final` (unchanged) |
| **IC-005** | Access Control named as a distinct service; the new flow stage recorded; ingress and audit-emitter seam re-pointed. **No change to token validation, JWKS, claims, roles, carriers or denial semantics.** | `Final` (unchanged) |
| **IC-012** | Principles carried forward and re-scoped to the Option A `deployment/` root; Edge-9 specifics marked historical; §13 import-linter requirement survives in full. | `Draft / Proposed` (unchanged) |

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
| **CONF-4** | Ownership cardinality — three sources disagree | ❓ **RATIFICATION REQUIRED** — §7 below |
| **CONF-5** | AI Phase 9 vs the D-02/D6 deferral + all-TBD IC-006 | 🟡 **PARTIAL** — the Option A directive reopens the deferral for Phase 9; **IC-006 must reach Draft-complete first**; the Part 4B governance gate is unwaived |
| **CONF-6** | Sharing Phase 8 vs Draft IC-007 | ⬜ **NAMED PREREQUISITE** — IC-007 must be promoted to `Final`; that is a governance act requiring Dan |
| **CONF-7** | Contacts has no contract | ⬜ **RESERVED as IC-015**, unauthored — it is new product specification, not reconciliation |
| **CONF-8** | `main.py` convention vs uvicorn containment | ✅ **RESOLVED** — IC-013 §21 ratifies the app-factory shape; uvicorn stays confined to one shared runtime module; `uvicorn.run(...)` permitted only under `if __name__ == "__main__":` as a dev convenience, never the production start path |
| **CONF-9** | `0.0.0.0` / `reload=True` / missing flags | ✅ **RESOLVED** — IC-013 §21 pins loopback default, `--workers 1`, `--no-access-log`, `--no-server-header`, `--no-proxy-headers`; `reload` dev-only; `0.0.0.0` prohibited outside a deliberate deployment binding |
| **CONF-10** | Global directory gaps | 🟡 **PARTIAL** — `owner_agent_ref` recorded as migration **M-2**; Global Investor Contract and D-35 Global Deal Directory remain named prerequisites |
| **CONF-11** | IC-012 governs a root Option A replaces | ✅ **RESOLVED** — principles carried forward and re-scoped; Edge-9 specifics historical; §13 import-linter requirement survives |
| **CONF-12** | 3 backend operations vs 86 frontend expectations | ✅ **ADDRESSED** — IC-013 §22 makes cutover **incremental and per-operation by contract**; full parity is *not* a Phase 10 precondition, but a governed enumerated cutover set is; the old Gateway must not be used as a bridge |

**Closed: 8. Partial: 2. Named prerequisite: 1. Ratification required: 1.**

---

## 6. Verification

| Check | Result |
|---|---|
| Runtime code changed | **NONE** — `git status` shows zero `.py`, `.sql`, `.toml` or `.ps1` modifications |
| `api_gateway` package | **untouched on disk** — 21 files / 3,327 lines, byte-identical to `main` |
| Full test suite | **2054 passed**, 0 failed (matches the Phase 0 baseline exactly) |
| Guards non-vacuous | **Proven by mutation** — see below |
| Contracts restored after probe | **byte-identical** (`cmp` clean on all three) |

**The non-vacuity probe.** A passing suite after editing contract files means nothing unless the guards actually *read* those files. Nine architecture guards reference contracts by name, so I blanked `IC-010`, `IC-009` and `IC-005` and re-ran the architecture suite: **53 tests failed** (983 passed), including `test_ic010_response_composition_contract.py::test_6ca_nonvacuity_every_contract_anchor_is_load_bearing`. The files were then restored from scratchpad backups (not `git checkout`, which would have discarded the uncommitted amendments) and verified byte-identical with `cmp`, and the full suite re-run to 2054.

**Conclusion: the guards are load-bearing, and the insert-only amendment discipline preserved every anchor they assert on.** No guard needed to be weakened, retired, or edited.

---

## 7. Open item requiring Dan's decision — CONF-4

Three sources disagree on ownership, and the disagreement gates Phase 7 schema work:

| Source | Human owner | AI owner | Representation |
|---|---|---|---|
| **IC-008 (Final)** + D-36 | exactly one `owner_agent_ref` | **at most one** nullable `owner_ai_agent_ref`, NULL platform-wide until IC-006 | **field on the record** |
| Tenant DDL `006_ownership.sql` | at most one (PK = entity id) | **zero or more distinct** | **join tables** |
| Canonical Overview invariant #3 | exactly one | "**and one** AI owner" | unspecified |

**Option A — Contract prevails (recommended).** Adopt IC-008: exactly one human owner, at most one AI owner, both as record references.
**Option B — Schema prevails.** Adopt the join tables; amend IC-008.
**Option C — Split the concepts.** Ownership stays singular (the *accountability* record); AI *involvement* becomes a separate, explicitly non-ownership relation.

**Recommendation: Option A for the MVP rebuild, with Option C reserved** as the additive path if Phase 9 proves multiple AI agents must be attributed per record. Option A is the smallest lawful step and forecloses nothing. Full reasoning at **D-46 §8**.

Until this is ratified, IC-014 §7 instructs the Access Control Service to treat ownership as **at most one human owner reference** — the intersection of all three sources, and the only reading safe under every candidate outcome. Invariant #3's AI clause is flagged in the Canonical Overview as contested, not settled.

---

## 8. Named prerequisites before their Option A phases

| Prerequisite | Blocks | Why it was not done here |
|---|---|---|
| **IC-006 → Draft-complete** (every normative section currently reads `TBD`) | Phase 9 (AI Agent Service) | Authoring a full AI contract is new specification, not reconciliation. The Part 4B governance gate — a compliance/permissions review is a prerequisite, not an afterthought — applies and is unwaived. |
| **IC-007 → `Final`** | Phase 8 (Sharing Service) | Promoting a Draft contract to Final is a governance act requiring Dan's ratification. |
| **IC-015 — Contacts Service Contract** (reserved) | Phase 7 (Contacts) | Contacts has no existing implementation to reconcile *from* — only DDL. It is new product specification. |
| **Global Investor Contract**; **D-35 Global Deal Directory** | Global directory work | Same — new specification, not reconciliation. |
| **Migrations M-1, M-2** | M-1 blocks **all** BFF audit emission | Phase 0.5 is documentation-only; SQL is implementation. Both are specified at D-46 §7. |

---

## 9. Recommended next step

**Do not start Phase 1 yet.** Two things should happen first:

1. **Ratify CONF-4** (§7). It gates Phase 7 schema work, and deciding it late means re-doing the tenant schema and its ownership semantics.
2. **Review and merge Phase 0 and Phase 0.5.** Both branches are unmerged. Until they land on `main`, `IC-010` is still `Final` there and the CONF-1 blocker is formally still open on the mainline — the resolution exists only on this branch.

When Phase 1 is authorized, the recommended order from the Phase 0 report stands, now with contract backing:

1. **`shared/` first** — seeded from the existing shared kernel (16 files / 1,369 lines), plus the new `correlation/` module.
2. **14 service skeletons**, each independently bootable per **IC-013 §21** (app-factory shape, pinned serving posture, minimally-disclosing health/readiness per §17).
3. **Architecture guards immediately, not later** — the dependency DAG (re-expressed per IC-012 §13 against the new package graph), driver/vendor containment, references-only discipline, a **zero-Gateway census** (IC-013 §20), and the **four re-homing proofs** (§4 above).
4. **Then the Database Router** — the one component that already fully satisfies its target contract, with the strongest test evidence (140 tests + live-PG topology proof), and the service every other one depends on for its session seam.

Authentication and Access Control still precede the BFF, per Option A's ordering — which is correct, because the BFF must not occupy the public position before the services that guard it exist.

---

## 10. Non-overclaim

- **No FastAPI runtime implementation was started.**
- **No old backend code was deleted.** The `api_gateway` package, its 29 test files, its launcher and its runbooks are untouched and byte-identical to `main`.
- **No branch was merged. Nothing was pushed.**
- **No database migration was authored or applied.** M-1 and M-2 are specified only.
- **No blocker was closed.** Production remains **NOT READY / DO-NOT-ACTIVATE**.
- **No test was weakened, retired, or edited.** 2054 pass, unchanged from the Phase 0 baseline, and proven non-vacuous.
- IC-013 and IC-014 are **`Draft / Proposed`** and authorize no implementation. Phase 1 proceeds only under a separate, explicitly-authorizing instruction from Dan.
- The stale `phase/01-fastapi-runtime-foundation` worktree was **not touched**.
- Nothing was cherry-picked from `phase/00-architecture-ratification`; every artefact was authored fresh. `D-45` is recorded **VOID** on `main` to prevent two contradictory decisions sharing one identifier.
- The Physical Multi-Database MVP is **mandatory and unchanged**, reinforced and never weakened.
