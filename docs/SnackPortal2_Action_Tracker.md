# SnackPortal2 — Action Tracker

> ## ⚠️ DRIFT FLAG — `experiment/complete-api-gateway-removal-mvp` contradicts this document
>
> Next-action **#6 "Author PRD 04 V2 API Gateway Implementation PRD"**, **#7** and **#8** are for a component that branch DELETES. They are left ⬜ open here rather than closed or struck: whether the Gateway is built or removed is Dan's decision, and marking them done or dropped would prejudge it.
>
> **This document is NOT amended.** CLAUDE.md makes the Overview authoritative on scope and the
> locked decisions, and says to *flag DRIFT before acting* — which is what this banner is. Reopening
> a locked invariant or reversing a decision needs Dan's sign-off, not a code change. On `main`
> nothing here has moved.
>
> Full evidence: `docs/reports/SnackPortal2_Complete_API_Gateway_Zero_Residual_Removal_Result_Claude.md`.

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
| 20 | Reconcile the contract list: add **IC-009 / IC-010** (and the new global-investor contract) to CLAUDE.md's contract list | Low | ⬜ | doc gap |

---

## D. How to use this tracker
- When you finish a Next item, change its status to ✅ and (optionally) move it up to section B.
- Section A is the decision scoreboard — only **D5** is still open.
- Carry this file between sessions alongside the v2.1 Overview so any session can see exactly where things stand.
