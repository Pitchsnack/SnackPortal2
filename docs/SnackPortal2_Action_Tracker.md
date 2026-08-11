# SnackPortal2 — Action Tracker

> ## ✅ RATIFIED — D-45 closes the Gateway question (`experiment/complete-api-gateway-removal-mvp`)
>
> The prior DRIFT flag on this document said next-actions **#6 / #7 / #8** were left ⬜ open because
> *"whether the Gateway is built or removed is Dan's decision, and marking them done or dropped would
> prejudge it."* **Dan has now decided (D-45, 2026-08-11): the API Gateway component is removed from
> the Controlled Local MVP architecture and the ratified boundary is the approved authenticated
> public edge owned by the service that owns the route.** Items #6/#7/#8 are therefore closed as
> **⊘ SUPERSEDED** below — not silently deleted, and not marked "done".
>
> The work that replaces them is tracked as new items **#21–#24**. See
> [D-45](D-45-Gateway-Free-Public-Edge-Architecture.md), the
> [Architecture Decision Register](Architecture-Decision-Register.md), and
> `docs/reports/SnackPortal2_Complete_API_Gateway_Zero_Residual_Removal_Result_Claude.md`.
>
> **D-45 is a Controlled Local MVP architecture decision, not a production approval.** No push, PR,
> merge, DDL, live-PostgreSQL, Keycloak, SecretRef, credential, or standing-runtime change is
> authorized by it; **only Dan may explicitly authorize the specific future PR merge**. Gate B
> remains NOT GRANTED; production remains NOT READY / DO-NOT-ACTIVATE. On `main` nothing here has
> moved.

> Use this to track progress. Flip a Next item's status to ✅ as you finish it. The Next list is ordered roughly by sequence/priority.

**Updated:** 2026-08-11 · **Status key:** ✅ done · 🟡 in progress · ⬜ to do · ⏸ deferred · ❓ needs your input · **⊘ superseded**

> All 7 decisions resolved (6 decided, 1 deferred). Remaining work is build + inputs.
>
> 🎯 **Target launch: before end of July 2026 (~6 weeks).** ⚠️ Tight vs scope — critical path = **public-edge frontend cutover (two origins) + re-authored live proofs** → physical-DB migration → matching/billing → comms/calendar tools. *(Was "API Gateway → …"; superseded by D-45.)* Consider phasing (see Overview Part 7).

---

## A. Decisions (D1–D7)

| ID | Decision | Status | Outcome |
|---|---|---|---|
| D1 | Two-layer framing (product + platform)? | ✅ | Yes — both layers |
| D2 | Physical multi-DB: now or later? | ✅ | Build-now (backend-led) |
| D3 | How much does Lovable build? | ✅ | UI surface only, behind the Gateway |
| D4 | API Gateway next? | ⊘ | **Superseded by D-45 (2026-08-11)** — the Gateway is not built; the approved public edges are the boundary |
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
| 6 | ~~**Author PRD 04 V2** API Gateway Implementation PRD~~ | — | **⊘ superseded by D-45** | closed by Dan's 2026-08-11 architecture decision; the Gateway is not built |
| 7 | ~~Independently review PRD 04 V2 before execution~~ | — | **⊘ superseded by D-45** | #6 |
| 8 | ~~Execute V2 (exact phrase only; create PR; no Claude merge; post-merge verify)~~ | — | **⊘ superseded by D-45** | #7 |
| 9 | Write the **Supabase → public-edge cutover plan** — **two origins**, not one (IC-010 §Y) | High | ⬜ | D-45; D7 |
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
| 20 | Reconcile the contract list: add **IC-009 / IC-010** (and the new global-investor contract) to CLAUDE.md's contract list | Low | ✅ | done — CLAUDE.md lists IC-001…IC-012 |
| 21 | **Frontend cutover to the two approved public-edge origins** (IC-010 §Y) — split the single base URL, configure exact-origin CORS on **both**, two proxy upstreams / TLS terminations, keep the OIDC redirect origin byte-identical | High | ⬜ | D-45; B5-BLK-5 |
| 22 | **Re-author the live proofs the Gateway removal cost** — five live-PG harnesses deleted, two refusing; there is **no live tenant-data-plane witness and no integrated Smoke C** for the Gateway-free topology, and **B5-BLK-4 has lost its harness** | High | ⬜ | D-45 |
| 23 | **Re-run the retargeted DDL-012 live proof** (`test_pg_gateway_audit_durable.py`) under separate live authorization — currently UNVERIFIED against the new emitter | Med | ⬜ | #22; separate live authorization |
| 24 | **Widen DDL 012's `source_service` CHECK** and migrate the frozen `control_gateway_audit` / AW-1 SecretRef naming, so the last frozen residual can retire | Med | ⬜ | separate DDL + SecretRef authorization |

---

## D. How to use this tracker
- When you finish a Next item, change its status to ✅ and (optionally) move it up to section B.
- Section A is the decision scoreboard — every decision D1–D8 is resolved; **D4 is superseded by D-45** (2026-08-11).
- Carry this file between sessions alongside the v2.1 Overview so any session can see exactly where things stand.
