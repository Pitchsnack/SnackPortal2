# SnackPortal2 — Action Tracker

> Use this to track progress. Flip a Next item's status to ✅ as you finish it. The Next list is ordered roughly by sequence/priority.

**Updated:** 2026-06-20 · **Status key:** ✅ done · 🟡 in progress · ⬜ to do · ⏸ deferred · ❓ needs your input

> All 7 decisions resolved (6 decided, 1 deferred). Remaining work is build + inputs.
>
> 🎯 **Target launch: before end of July 2026 (~6 weeks).** ⚠️ Tight vs scope — critical path = API Gateway → physical-DB migration → matching/billing → comms/calendar tools. Consider phasing (see Overview Part 7).

---

## A. Decisions (D1–D7)

| ID | Decision | Status | Outcome |
|---|---|---|---|
| D1 | Two-layer framing (product + platform)? | ✅ | Yes — both layers |
| D2 | Physical multi-DB: now or later? | ✅ | Build-now (backend-led) |
| D3 | How much does Lovable build? | ✅ | UI surface only, behind the Gateway |
| D4 | API Gateway next? | ✅ | Build the Gateway next |
| D5 | PRD numbering scheme | ✅ | Two prefixed tracks (P- product / B- backend) — see PRD Index |
| D6 | Control AI scope | ⏸ | Deferred to Intelligence phase (reservations set) |
| D7 | Supabase's role | ✅ | Interim only |
| D8 | MVP recommendation/matching approach | ✅ | Manual/assisted MVP, automate later |

---

## B. Previous actions (completed)

| # | Action | Status | Outcome / artifact |
|---|---|---|---|
| 1 | Consolidate uploaded files | ✅ | 8 files → 5 distinct sessions (+ 2 dups, 1 template) |
| 2 | Build session comparison matrix | ✅ | `SnackPortal2_Session_Comparison` (+ plain-language edition) |
| 3 | Add glossary + plain-English verdicts | ✅ | Easier-to-read comparison doc |
| 4 | Identify cross-session tensions / drift | ✅ | 6 tensions ranked (3 High) |
| 5 | Draft two-layer canonical Overview | ✅ | `Canonical_Overview_and_Decisions` |
| 6 | Decide D1 (two-layer framing) | ✅ | Yes |
| 7 | Decide D2 (multi-DB timing) | ✅ | Build-now |
| 8 | Decide D4 (Gateway priority) | ✅ | Build next |
| 9 | Create Lovable read-only state questionnaire | ✅ | `Lovable_State_Questionnaire` |
| 10 | Receive + analyse Lovable state report | ✅ | Confirmed logical-vs-physical drift; keep/replace list |
| 11 | Decide D3 (Lovable scope) | ✅ | UI-only behind Gateway |
| 12 | Decide D7 (Supabase role) | ✅ | Interim only |
| 13 | Defer D6 (Control AI) + write reservation spec | ✅ | Part 4B reservations |
| 14 | Register Lovable as session S6 | ✅ | Added to comparison |
| 15 | Produce consolidated Overview v2.1 | ✅ | `Canonical_Overview_and_Decisions_v2` (north star) |

---

## C. Next actions (upcoming)

| # | Action | Priority | Status | Depends on |
|---|---|---|---|---|
| 1 | ~~Close D5~~ — chose two prefixed tracks (P-/B-) | High | ✅ | see PRD Index |
| 2 | Provide missing input: **client / decision-maker** | High | ❓ | — |
| 3 | Provide missing input: **revenue / business model** | High | ❓ | — |
| 4 | Provide missing input: **definition of done** | High | ❓ | — |
| 5 | Provide missing input: **target launch date** | Med | ❓ | — |
| 6 | **Author PRD 04 V2** API Gateway Implementation PRD | High | ⬜ | move to fresh session |
| 7 | Independently review PRD 04 V2 before execution | High | ⬜ | #6 |
| 8 | Execute V2 (exact phrase only; create PR; no Claude merge; post-merge verify) | High | ⬜ | #7 |
| 9 | Write the **Supabase → Gateway cutover plan** | Med | ⬜ | D4/D7 (done) |
| 10 | Map Lovable's 44-table schema → Control DB vs Tenant DB; place cross-tenant sharing tables | Med | ⬜ | — |
| 11 | Apply **Part 4B reservations** (`control_ai_*`, `CONTROL_AI` role, `ai.invoke` gate, AI audit class, separate AI Gateway) | Med | ⬜ | #10 |
| 12 | Extract the remaining un-extracted chats (up to 3 of 8) | Med | ⬜ | — |
| 13 | **Collaboration tools (human-to-human): email + chat/message + calendar/appointment booking** — MVP (P-16); design so AI plugs in later | High | ⬜ | in DoD; new/gaps per S6 |
| 13b | AI find/discovery + AI email/chat + AI scheduling agents plug into the tools | — | ⏸ | deferred (B-8/B-12) |
| 13c | Finish remaining Lovable gaps: doc upload, access-mgmt UI, invitations | Low | ⬜ | (AI invocation ⏸ under D6) |
| 14 | Lock the Overview fully once inputs land | Med | ⬜ | #2–#5 |
| 15 | Build **manual recommendation + matching workflow** (capture "recommended startup X to VC Y" + outcome) — MVP feature for revenue | High | ⬜ | D8 |
| 16 | Build **fees/billing engine** — success fees + matching fees + retention fee (extend beyond `tenant_subscription`) | High | ⬜ | #15 |
| 17 | Design recommendation/attribution records in the **same shape the AI will later populate** (ties to Lineage B-6 + `control_ai_recommendations`) | Med | ⬜ | #15 |
| 18 | Build the **Control global registry** (`global_startups`, `global_investors`) in the Control DB — the master pool that powers recommendations/matching | High | ⬜ | B-0; revenue source |
| 19 | Add a **Global Investor Contract** (you have IC-001 Global Startup but no global-investor contract) | Med | ⬜ | contract gap |
| 20 | Reconcile the contract list: add **IC-009 / IC-010** (and the new global-investor contract) to CLAUDE.md's contract list | Low | 🟡 | IC-009/IC-010/IC-011/IC-012 now listed; **IC-013/IC-014 added and IC-015 reserved** under D-46 (Phase 0.5). The **Global Investor Contract (#19) is still missing** — that part remains open. |
| 21 | **Phase 0 — Option A requirements & existing-system discovery** | High | ✅ | Branch `phase/00-requirements-extraction` @ `5a2d106c3` — `docs/Phase-0-Requirements-Extraction-Report.md`. Classified the backend A–F; API Gateway = category D; 12 conflicts recorded. **Unmerged, awaiting Dan.** |
| 22 | **Phase 0.5 — Contract Reconciliation** | High | ✅ | Branch `phase/00.5-contract-reconciliation` — **D-46** ratifies the Gateway-free target; **IC-010 `Final` → `Superseded`**; **IC-013** (BFF Ingress) + **IC-014** (Access Control) opened Draft / Proposed; IC-005 / IC-009 / IC-012 amended insert-only; locked invariant #7 revised. No runtime change; the `api_gateway` package is untouched on disk. **Unmerged, awaiting Dan's review.** |
| 23 | ~~RATIFY CONF-4 — ownership cardinality~~ | High | ✅ | **Dan ratified Option A, 2026-08-21 — [D-47](D-47-AI-Ownership-Cardinality-And-Service-Exposure-Model.md) §1.** At most one *current* AI Owner per record; contribution ≠ ownership (task history / provenance / audit); Option C reserved. IC-008 amended; invariant #3 corrected. |
| 23a | **Reconcile tenant DDL `006_ownership.sql` + `test_ownership_pk_shapes` IN THE SAME COMMIT** — the guard at `test_tenant_ddl_schema_guards.py:219` **asserts** the composite PK the ratification rejects, so changing one without the other either blocks the schema change or silently weakens the guard | **High** | ⬜ | Phase 7 (D-47 §1.4 DIV-1 + DIV-2) |
| 23b | **Specify the "task history" record class** — named by D-47 R-4 but exists in **no contract or schema**; until specified, contribution is recordable only via IC-004 provenance + IC-002 audit, and no new class may be invented at implementation time | Med | ⬜ | Phase 9 / IC-006 (D-47 §1.4 DIV-3) |
| 23c | ~~**Deployment-manifest exposure check**~~ | **High** | ✅ | **Done 2026-08-23** on `rebuild/fastapi-openapi-first`. `infrastructure/docker/docker-compose.rebuild.yml` is the manifest; `backend/tests/snackportal2/test_deployment_exposure.py` is the check. Scoped to **application** services (a local PostgreSQL fixture is not an application ingress), parsed with a self-tested scanner so it cannot pass by failing to parse, and it proves the Access Control Service publishes nothing separately. |
| 23d | **Add an IC-008 cardinality guard** — measured this session: blanking `IC-008` entirely leaves **all 1036 guards passing**, so the just-ratified ownership contract has **zero** automated protection, while the DDL contradicting it **is** guarded. Enforce the corrected shape from the authoritative side | Med | ⬜ | Phase 7, alongside 23a (Phase 0.5 report §6.1) |
| 24 | Promote **IC-007** `Draft / Proposed` → `Final` before any Sharing Service work | High | ⬜ | named prerequisite for Option A Phase 8 (D-46 §6, CONF-6) |
| 25 | Author **IC-006** to Draft-complete (every normative section is currently `TBD`) before any AI Agent Service work; the Part 4B governance gate applies and is unwaived | High | ⬜ | named prerequisite for Option A Phase 9 (D-46 §6, CONF-5) |
| 26 | Author **IC-015 — Contacts Service Contract** (reserved, unauthored) | Med | ⬜ | named prerequisite for Option A Phase 7 (D-46 §6, CONF-7) |
| 27 | ~~Author control migration **M-1**~~ | High | ✅ | **Authored 2026-08-23** at `backend/migrations/control/016_bff_ingress_audit.sql` + `017_..._append_only.sql`. New table `control_ingress_audit` carries the **inverse** constraint (`source_service <> 'api_gateway'`), so it and DDL 012 are disjoint by construction. 012/013 + byte-pins untouched. **Created, not applied.** |
| 28 | Author control migration **M-2** — `control_directory.owner_agent_ref`, per IC-008's global-ownership mandate | Med | ⬜ | D-46 §7, CONF-10 |
| 29 | Author the **D-35 Global Deal Directory** (`DirectoryKind` has STARTUP + INVESTOR only; no `DEAL` kind, no DDL) | Med | ⬜ | D-46 §6, CONF-10 |
| 30 | **Phase 1+ — Option A clean FastAPI rebuild** (14 bootable services, shared foundation, OpenAPI-first contracts, zero-Gateway census) | High | ✅ | **Authorized and executed 2026-08-23** under the *3-Day OpenAPI-First FastAPI Rebuild* plan, on branch `rebuild/fastapi-openapi-first` (base `51d640d37`, worktree `D:\Pitchsnack\SnackPortal2-fastapi-rebuild`). All 14 services bootable with their own `main.py` + `app = FastAPI()`; all generate OpenAPI 3.1 and pass a standing contract gate. **Unmerged, unpushed, awaiting Dan.** |
| 31 | **D-48 — Tenant Connection Ownership** | High | ✅ | **Ratified by Dan 2026-08-23** at the rebuild's Day-1 checkpoint. IC-013 §8 amended: the Database Router keeps **resolution authority**; **connection custody** moves to tenant-resident domain services under a short-lived single-tenant grant. The BFF and Access Control are **permanently excluded** from the grant allowlist, enforced at configuration time. |
| 32 | Promote **IC-013** and **IC-014** `Draft / Proposed` → `Final` | High | ⬜ | Both now have a full implementation and an acceptance-test set behind them; they are still formally Draft. |
| 33 | Author the **per-feature tenant business-record grant contracts** (Investor, Deal, Contacts) | Med | ⬜ | IC-009 §C states the matrix *shape* is contractable now but the per-feature *grant* "does not yet exist" and is not an IC-009 deliverable. Tenant Startup read/update has one (D-42 CLM); Investor/Deal/Contacts do not. |
| 34 | Author the **record-assignment model** for `STARTUP_USER` / `INVESTOR_USER` | Med | ⬜ | IC-009 §C scopes them to *assigned* tenant records, and no assignment model exists. The rebuild denies those cells rather than approximating them. |
| 35 | **Stage 4 — Live PostgreSQL & Migration Verification** | High | 🟡 | **PARTIAL, 2026-08-23**, on `rebuild/fastapi-openapi-first` (`a013667de` → `18bfbf6c7`, three local commits, **unpushed**). 218 live tests pass against four physically distinct disposable PostgreSQL 17.10 clusters. **M-1 applied and verified** (disjoint from DDL 012 in both directions; append-only holds). Control chain 17 files, tenant chain 14 files ×3, fresh-DB reproducibility PASS. Physical ACME/ZETA/NOVA isolation proven at the databases via `pg_stat_database.sessions`; no Control-DB fallback. D-48 C-1…C-4 PASS, with the BFF/Access Control exclusion enforced at **configuration time** (the router refuses to start). Real eleven-service BFF→PostgreSQL e2e PASS. All 14 OpenAPI 3.1 gates PASS and **byte-identical with PostgreSQL configured**. Full suite 2253, ruff/mypy/lint-imports green. Report: `Treebranch2/PRD/PFD1/Claude_Stage4_Live_PostgreSQL_Verification_FINAL_Status_Report.md`. **Awaiting Dan.** |
| 35a | **Import Service has no PostgreSQL store** — Stage 4 blocker B-1 | **High** | ⬜ | `import_service/main.py` composes `InMemoryImportStore()` unconditionally, so a successful import writes **no tenant row**. Writing the adapter entails an IC-004 lineage row, which needs the **D-23 per-tenant HMAC chain key** — the rebuild has no secret-material surface, no configuration and no contract for one, and import-linter forbids reusing the legacy `lineage_service`. Second-order: **the rebuild has no lineage write path at all**. Needs a Dan decision on chain-key management before any adapter is written. |
| 35b | **`year_founded` contract/column type mismatch** — Stage 4 finding F-3 | Med | ⬜ | `StartupCreateRequest.year_founded` is `Optional[str]` (max 8) but tenant DDL 003 types the column `integer`, so a non-numeric value passes validation and returns **500 `internal_error`** rather than the 422 the route already declares. Narrowing it changes the published OpenAPI schema, which Stage 4 §9 makes a STOP-and-report. Behaviour pinned by a characterization test. **Dan's decision.** |

---

## D. How to use this tracker
- When you finish a Next item, change its status to ✅ and (optionally) move it up to section B.
- Section A is the decision scoreboard — only **D5** is still open.
- Carry this file between sessions alongside the v2.1 Overview so any session can see exactly where things stand.
