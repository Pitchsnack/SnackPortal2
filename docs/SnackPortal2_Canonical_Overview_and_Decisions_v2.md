# SnackPortal2 — Canonical Overview & Decisions (v2)

> **⚠ AMENDED 2026-08-21 by [D-46](D-46-Option-A-Gateway-Free-Target-Architecture-Ratification.md) — Option A Gateway-Free Target Architecture Ratification.**
> The target architecture is now **`Frontend → FastAPI BFF → FastAPI Services`, with zero API Gateway in the target runtime.** Three effects on this document: **locked invariant #7** is revised from "the Gateway is the boundary" to "**the BFF is the boundary**" (substance preserved, holder changed); a **new invariant #9** records the four-way separation `Authentication ≠ Access Control ≠ Tenant Routing ≠ Database Access`; and **invariant #3's AI-owner clause is corrected** — **settled 2026-08-21 by [D-47](D-47-AI-Ownership-Cardinality-And-Service-Exposure-Model.md) §1** (Phase 0 finding CONF-4 closed): **at most one *current* AI Owner**, with additional AI Agents recorded as **contributors** via task history, provenance and audit, never as owners.
> **IC-010 is `Superseded`** by IC-013 (BFF Ingress) + IC-014 (Access Control). **Decision D4 ("build the Gateway next") is historically accurate but no longer the live plan** — the Option A rebuild replaces it; the *reasoning* behind D4 (the product waits on one governed doorway) is preserved and now points at the BFF. Elsewhere in this document, read "API Gateway" as "**the governed public ingress**", which is now the BFF. Everything else below — the product framing, the business model, D1/D2/D3/D5/D7/D8, the D6 deferral and its Part 4B reservations, the Lovable reconciliation, and the schema split — is **unchanged and still authoritative**.

> **What changed in v2.** Decisions D1–D4 and D7 are recorded as made; **D6 is now formally Deferred** (with a reservation spec in Part 4B). The Lovable project-state report has been folded in as confirmed drift plus a keep/replace rework list, and registered as session **S6** so it slots into the comparison.

**Version:** v2.2
**Date:** 2026-06-20
**Status:** 🟢 Overview fully locked — all decisions D1–D8 resolved (D6 deferred), all 4 business inputs filled · ⚠️ tight timeline: target before end of July 2026 (see Part 7 schedule note)

---

## DECISION LOG (quick reference)

| ID | Question | Status | Choice |
|---|---|---|---|
| D1 | Two-layer framing (product + platform)? | **Decided** | Yes — both layers |
| D2 | Physical multi-DB: now or later? | **Decided** | Build-now (backend-led) |
| D3 | How much does Lovable build? | **Decided** | UI surface only, behind the Gateway |
| D4 | API Gateway next? | **Decided** | Build the Gateway next |
| D5 | PRD numbering scheme | **Decided** | Two prefixed tracks: P- (product) / B- (backend) — see PRD Index |
| D6 | Control AI scope | **Deferred** | Keep ownership-AI; defer the active Control AI network to the Intelligence phase (door kept open — see Part 4B) |
| D7 | Supabase's role | **Decided** | Interim only |
| D8 | MVP recommendation/matching approach | **Decided** | Manual/assisted MVP, automate later (Option B) |

---

# PART 1 — THE OVERVIEW (canonical north star)

## In one paragraph

SnackPortal2 is a **multi-tenant venture collaboration network**: a platform where agents — and their AI counterparts — manage startups, investors, and deals across separate client organisations ("tenants"), share deals under controlled rules, and work through dedicated portals. It runs on a **vendor-neutral, physically separated multi-database backend** so the business is never locked into a single hosting or database provider.

## Layer 1 — The Product (what users get)
A workspace for venture deal-making. Agents manage startups, investors, and deals; share opportunities under strict rules; work through portals; and coordinate using built-in **collaboration tools** — email, chat/messaging, and **calendar / appointment booking** (with more tools, e.g. data rooms, alongside). Roles: Control (operator), Master Agents (oversee several tenants), Tenant Agents, plus Startup and Investor users. Built in **Lovable** (the frontend).

**Target customer:** Tier 1 venture capital and private equity firms that **originate and lead** investment rounds at pre-Series A and beyond. Each such firm is a tenant; its dealmakers are the agents. (This profile is why physical data isolation matters so much — see Part 6.)

## Layer 2 — The Platform (what's underneath)
A vendor-neutral backend: one central **Control database** (platform-wide records **plus the Control-owned global registry of startups and investors** — the master pool) + a **separate physical database per tenant** (independent copies of records, imported with lineage), chosen by a **Database Router**, fronted by an **API Gateway**, with Control Plane, Authentication, Import, and Lineage services. Governed by contracts/ADRs.

## How the two layers connect
One doorway only: the **FastAPI BFF**. *(Revised 2026-08-21 by **D-46**; previously the API Gateway — see locked invariant #7 and IC-013.)*
`Frontend (UI) → FastAPI BFF → backend services → Database Router → the correct tenant database.`
The BFF never picks the database (the Router does); the frontend never talks to a database directly; **Access Control decides what is allowed before the Router is reached**; one request serves one tenant → one database.

## Business model (how it earns)
SnackPortal2 is an **AI-as-a-Service platform with performance-aligned, dual-sided revenue** — it earns from both capital providers and capital seekers, mostly only when a deal actually happens:
- **VC success fees** — 2–7% of deal value, charged to the lead investor when they deploy capital into a **platform-recommended** startup (rate set by deal complexity and platform involvement). Realised only on actual investment.
- **Startup matching fees** — 2–7% of investment value, charged to startups for AI-powered investor discovery and matching.
- **Minimum retention fee** — a baseline annual commitment for platform access, priority support, and exclusive deal-flow privileges (the only subscription-like element; maps to the existing `tenant_subscription` table).

*Example:* a VC invests $10M into a platform-recommended startup → the platform captures $200K–$700K, plus a further 2–7% if the startup also used the matching service.

**This makes the AI recommendation/matching engine a revenue-critical capability — see the D6/D8 tension below.**

## Current build reality (as of the Lovable state report, 2026-06-20)
The honest snapshot has three parts at different stages:
- **Backend foundation (Phases 1–6): built and accepted** — including the physical-multi-database design (~88% aligned).
- ~~**API Gateway: not built** — scaffold-only, reviewed as READY_WITH_GUARDS; next document is PRD 04 V2.~~ **STALE — corrected by Phase 0 (2026-08-21).** The API Gateway core *was* built under PRD 04 V2/V3 (`IMPLEMENTS_BEHAVIOR = True`) and serves one of nine native FastAPI/Uvicorn edges; the public surface is **three operations**. Under **D-46** it is **old architecture, not to be ported**, and **IC-010 is Superseded** — the target ingress is the **FastAPI BFF** (IC-013).
- **Product frontend: ~70% of screens exist in Lovable**, but on an **interim** single-database Supabase backend that uses logical (not physical) tenant separation. That data layer is temporary and is replaced at the **BFF** cutover — **incremental and per-operation** (IC-013 §22), never big-bang, and never via the old Gateway as a bridge.

## Definition of done (two tiers)
**MVP launch-ready when** a VC/PE firm can be onboarded as a tenant **on its own physical database**, its agents can **manage, share, email, chat/message, and book meetings (calendar)** with startups/investors about deals **through the API Gateway**, and a **manually-matched, platform-recommended deal can be attributed and billed end-to-end.**

**Full product (AI-implementation phase):** **AI and AI agents plug into the MVP channels and tools** — adding AI-powered **find/discovery**, AI-assisted/automated **email outreach**, **AI chat agents**, and **AI scheduling**, plus the rest of the Control AI (Discovery, Recommendation, Communication AI; B-8 AI Gateway, B-12 Control AI).

*Build principle:* build the **email, chat/message, and calendar-booking tools now** (human-to-human) so the **AI agents plug into the existing channels/tools later** rather than forcing a rebuild. ("Find" = AI discovery/matching is AI-phase; basic keyword search already exists in Lovable.)

---

# PART 2 — LOCKED INVARIANTS (settled; do not reopen without sign-off)

1. **Product class** — multi-tenant venture/investor/deal collaboration network.
2. **Database shape** — one Control DB + one physical DB per tenant + a Database Router.
3. **Ownership rule** — every startup/investor/deal has **exactly one human owner** and **at most one *current* AI owner**. **Multiple AI Agents may contribute** to a record — recorded through **task history, provenance and audit** — but contribution is **never ownership** and never creates a second AI owner. *(**Ratified 2026-08-21 by [D-47](D-47-AI-Ownership-Cardinality-And-Service-Exposure-Model.md) §1**, closing Phase 0 finding CONF-4. The earlier wording "and one AI owner" was ambiguous and disagreed with both IC-008 and the tenant DDL; IC-008 prevails. "Current" is a cardinality bound, not a permanence claim — AI ownership may pass between agents over time, at most one holder at any instant, each succession audited. The AI-owner reference stays **NULL platform-wide until IC-006**. Option C — a separate, explicitly non-ownership AI-involvement relation — is **reserved** as an additive later decision.)*
4. **Sharing ≠ ownership** — sharing never transfers ownership, never moves tenant, never duplicates. *(Confirmed built in Lovable.)*
5. **Anti-vendor-lock-in** — no design that ties the business to one provider as the final architecture.
6. **Lovable owns the surface, not the plumbing** — UI only; not the Router, ingress, AI orchestration, or routing.
7. **The BFF is the boundary** — frontend → FastAPI BFF, never directly to DB/auth/access-control/router. *(**Revised 2026-08-21 by [D-46](D-46-Option-A-Gateway-Free-Target-Architecture-Ratification.md) §2.** Previously: "The Gateway is the boundary — frontend → Gateway, never directly to DB/auth/router." The **substance is preserved and unweakened** — one governed public ingress, no client path around it; only the component holding that position changes. Governed by **IC-013 — BFF Ingress Contract**; IC-010 is **Superseded**. The BFF is **not** a renamed Gateway: its operation surface is enumerated by contract, and a surface that merely relays a downstream body is forbidden.)*
8. **DEC-11 stays binding** — no ownership-audit data-location binding until the IC-002 extension lands.
9. **The four-way separation** — `Authentication ≠ Access Control ≠ Tenant Routing ≠ Database Access`. *(Added 2026-08-21 by **D-46 §3**. Access Control is a distinct contracted service — **IC-014** — and was never built; it is the one genuinely greenfield component of the Option A rebuild.)*

> ✅ **Invariant #3 — SETTLED 2026-08-21 by [D-47](D-47-AI-Ownership-Cardinality-And-Service-Exposure-Model.md) §1** (Phase 0 finding CONF-4 closed). Dan ratified **Option A**: IC-008 prevails — **at most one *current* AI Owner**, held as a **single reference on the record, never a set and never a join table**. Contribution by additional AI Agents is recorded through task history, provenance and audit, is **never an authorization input**, and never creates a second ownership. **Option C** (a separate, explicitly non-ownership AI-*involvement* relation) is **reserved** as a purely additive later decision if Phase 9 proves it necessary.
>
> ⚠ **Two divergences remain, recorded as Phase-7 work** (D-47 §1.4): the tenant DDL `006_ownership.sql` still implements the rejected zero-or-more join-table shape, and `test_tenant_ddl_schema_guards.py::test_ownership_pk_shapes` **actively asserts** it — so the DDL and that guard must change in the **same** commit. A third gap: the **"task history" record class named by the ruling exists in no contract or schema** (Phase 9 / IC-006).

---

# PART 3 — DECISIONS

**Made:**
- **D1 — Two-layer framing: YES.** SnackPortal2 is a product layer on a platform layer, joined at the Gateway.
- **D2 — Physical multi-DB: BUILD-NOW (backend-led).** Physical separation is mandatory; the product connects once the backend + Gateway are ready.
- **D3 — Lovable scope: UI SURFACE ONLY, behind the Gateway.** Keep ~70% of the screens; the data layer is interim and gets replaced. (Detail in Part 4.)
- **D4 — API Gateway: BUILD NEXT.** It's the doorway the product waits on; already reviewed (READY_WITH_GUARDS); next artifact is PRD 04 V2.
- **D7 — Supabase: INTERIM ONLY.** May back early Lovable UI; final business data lives behind the Gateway in the physical-multi-DB backend; plan the cut-over.

**Deferred (revisit at the Intelligence phase):**
- **D6 — Control AI scope: DEFERRED.** Keep the ownership-AI (the one-AI-owner-per-record rule, already built and locked as invariant #3). Defer the *active* Control AI network — the discovery/recommendation/relationship/analytics/compliance/communication agents from S1 — to a later Intelligence phase. The Lovable report confirms it isn't built (an AI key exists but nothing calls it), so deferring changes nothing today. To keep revisiting cheap, follow the reservation spec in **Part 4B**. Note: deferring D6 does **not** weaken any AI ownership that already exists.

- **D8 — MVP recommendation/matching: DECIDED — Option B (manual/assisted MVP, automate later).** At launch, humans (you/Control or agents) make the recommendations and investor↔startup matches; the platform **records the attribution** (which startup was recommended to which VC, and whether the investment closed) and **bills the success/matching fees** on that basis. The AI automation of this step ships later in the Intelligence phase (B-8/B-12), replacing the manual step without rebuilding — because the attribution data sits in the built **Lineage Service (B-6)** and the reserved `control_ai_recommendations` table from the start. Revenue flows from day one; "AI-as-a-Service" is partly human-assisted at launch.
  - **What D8 = B adds to the MVP build:** (1) a **manual recommendation + matching workflow** in the product (capture "platform recommended startup X to VC Y", track outcome); (2) a **fees/billing engine** for success fees + matching fees + the retention fee (the existing `tenant_subscription` table only covers retention); (3) design the recommendation/attribution records now in the *same shape* the AI will later populate, so the swap is clean.

**Still open:** none — all decisions D1–D8 resolved.

- **D5 — PRD numbering: DECIDED — two prefixed tracks.** Product PRDs are **P-1, P-2 …** and Backend/Platform PRDs are **B-1, B-2 …**, with the architecture baseline as **B-0**. This dissolves the old clashes (the two "PRD 8"s become P-8 Communication Hub and B-0 Physical Multi-DB; the two "PRD 1"s become P-1 Tenant Architecture and B-12 Control AI). Full mapping in the **PRD Index** file.

---

# PART 4 — LOVABLE RECONCILIATION (folded in from the state report)

## The confirmed drift: logical vs physical tenant separation
Lovable keeps every tenant's data in **one shared database**, separated by a `tenant_id` label on each row plus security rules (RLS). Your D2 choice requires the opposite: a **separate physical database per tenant**, chosen by the Database Router. So the isolation method that exists today is not the final one — this is the long-warned "DRIFT-01," now confirmed concretely.

**Why this is manageable, not alarming:** the frontend never writes to the database directly. Every business read/write goes through a clean server-function RPC layer, which is exactly the seam you re-point at the API Gateway later. The UI is largely portable.

## What's already aligned (good news)
- Dual Human + AI ownership is built and enforced (deal creation requires both owners).
- Deal sharing uses dedicated tables and never transfers ownership.
- The active Control AI is **not** built — matching the D6 deferral.

## Keep / replace rework list

| Layer in Lovable today | Disposition |
|---|---|
| UI: components, routes, hooks, design system (~70% of screens) | **KEEP** — portable |
| RPC seam (`src/lib/*.functions.ts` server functions) | **RE-POINT** at the API Gateway |
| Supabase clients + browser auth session + bearer attacher | **REPLACE** at cutover |
| Isolation: single DB + `tenant_id` + RLS + cohesion triggers | **REPLACE** with physical DB-per-tenant + Router |
| Schema (44 tables) | **REUSE** to seed backend schemas (split below) |
| Dual ownership + sharing logic | **KEEP the logic**, re-implement behind the backend |
| AI invocation / Control AI | **DEFER** (matches D6) |
| Automated tests | **NONE exist** — backend side will need them |

## The schema is an asset — Control DB vs Tenant DB split
Lovable's 44-table model maps almost directly onto your S4 Control/Tenant split:
- **Control DB (platform-wide):** tenants, tenant_features/settings/subscription, users, roles, user_roles, user_tenants, user_sessions, master_agent_tenants, workspace_context, security_events, audit_logs, notifications, saved_searches, **plus the GLOBAL registry: `global_startups` and `global_investors`** — the platform owner's (Control's) curated master pool, distinct from tenant copies. Governed by IC-001 (Global Startup Contract); **a Global Investor Contract is a gap to add.** Control + Control AI own these globally; importing one into a tenant creates an independent tenant copy (IC-003 Import) with lineage `source_global_id` (IC-004). This global pool is the **source inventory for the platform's recommendations/matching** (the revenue engine).
- **Tenant DB (per tenant):** startups + children, investors + children, deals + children (ownership, ai_ownership, tags, documents, activity). *(Tenant startups/investors are independent copies of global records — IC-002 Tenant Startup Contract; "Global Record ≠ Tenant Record", no auto-sync.)*
- **Open design question:** the cross-tenant sharing tables (`deal_shares`, `deal_share_targets`, `deal_introductions`) span tenants, so in a physical-DB world they can't live inside a single tenant DB — they belong in a Control-level sharing layer. Flag for the backend team.

---

# PART 4B — RESERVATIONS FOR THE DEFERRED CONTROL AI (D6)

> **Purpose.** D6 is deferred, not cancelled. These reservations keep the door open so adding the Control AI later is **additive, not a rewrite**. Reserve = leave room and a name for it; do **not** build it now.

## A. Database reservations (in the Control DB — not the tenant DBs)
The active Control AI is platform-level and cross-tenant, so its data belongs in the **Control database**. Reserve this `control_ai_*` table cluster (names from S1) as a planned-but-unbuilt group:

| Reserved table | Will hold (when built) |
|---|---|
| `control_ai_agents` | Registry of Control AI agents and their type/status |
| `control_ai_recommendations` | Recommendations produced (startups/investors to Master Agents) |
| `control_ai_research` | Discovery / research outputs |
| `control_ai_feedback` | Feedback collected from startups/investors |
| `control_ai_communications` | Record of AI-initiated contact |
| `control_ai_analytics` | Analytics outputs |
| `control_ai_audit_logs` | Audit trail of Control AI actions |

**Important physical-multi-DB rule for these tables:** because Control AI lives in the Control DB while operational records (startups/investors/deals) live in *separate* tenant DBs, these tables must reference those records by **soft ID columns** (e.g. `tenant_id`, `source_startup_id`), **not** hard foreign keys — you cannot enforce a foreign key across two physically separate databases. Reserve the columns; don't wire cross-DB FKs.

## B. Identity, permission, and audit reservations
- **Reserve a distinct Control-AI identity/role** (e.g. `CONTROL_AI`), separate from human `CONTROL`, so AI actions are attributable and separately gateable. (Lovable's role catalog already includes AI role variants — keep that slot, leave it unused.)
- **Reserve the `ai.invoke` permission** as the single gate for real model calls. It already exists in Lovable's permission model — keep it defined, leave it **unwired** to any model.
- **Reserve an audit-event class for AI-initiated actions.** This lines up with the already-pending "runtime audit-class home for IC-010 §J emit-set" (deferred to the IC-005/IC-002 audit extension) and with DEC-11 — so reserve the class now, bind it later. No new commitment today.

## C. Boundary reservation (keep it off the API Gateway being built next)
- **Reserve a separate "AI Gateway / model router"** as a *future, distinct* component. The API Gateway you build next (PRD 04 V2) is the frontend↔backend doorway and must **not** take on AI model routing. Control AI model calls will go through the future AI Gateway, not the request API Gateway. Reserving this keeps the near-term Gateway simple.

## D. Roadmap reservation
- **Name a future phase: "Intelligence / Control AI."** Record S1's agent hierarchy as its spec to revisit: Startup Discovery AI, Investor Discovery AI, Recommendation AI, Relationship AI, Analytics AI, Compliance AI, Communication AI.
- **Map AI to the MVP channels:** the **email + chat/message channels are built in the MVP** (human-to-human); the AI agents plug into them later — **find/discovery** → Discovery + Recommendation AI; **AI email outreach** and **AI chat** → Communication AI. Build the channels MVP-side so the agents plug in without a rebuild.
- **Reserve a governance gate before that phase starts** — because Control AI would contact real people and cross tenant boundaries, a compliance/permissions review is a prerequisite, not an afterthought.

## E. Do-NOT-build list (so the deferral stays clean)
- Do not create the `control_ai_*` tables yet.
- Do not wire `ai.invoke` to any model.
- Do not add AI-initiated communication or outreach flows.
- Do not let the API Gateway handle AI routing.

---

# PART 5 — SESSION REGISTER UPDATE: S6 (Lovable Frontend)

The Lovable report becomes your sixth session extract.

```
=== SESSION EXTRACT BLOCK ===
Session label: S6 — Lovable Frontend Build (current project state, read-only report)

What this covers: the actual built state of the Lovable frontend and its Supabase data layer.

OVERVIEW AS THIS SESSION STATES IT:
- Product is: a multi-tenant SaaS for a startup/investor/deal pipeline, with dual Human+AI ownership per record, deal sharing, warm introductions, role-based access, and audit logging.
- Primary objective treated as: deliver the working product UI plus its data layer on Lovable Cloud (Supabase).
- Scope/separation: isolation is LOGICAL (single shared database + tenant_id column + RLS), not physical.

KEY STATE / DECISIONS:
- ~70% of screens built; ~80% of data/backend touched.
- Stack: TanStack Start (React 19) + Lovable Cloud (Supabase Postgres/Auth/Storage); clean server-function RPC layer; RLS on all 44 tables.
- Dual ownership built and required; sharing via deal_shares/deal_share_targets; cross-tenant introductions.
- AI key present but unused; no AI invocation; no automated tests.

DRIFT FROM TARGET:
- Logical multi-tenancy (single shared DB) vs required physical multi-DB → DRIFT-01 confirmed.
- Lovable currently IS the backend (Supabase) — conflicts with "Lovable owns surface, not plumbing" until the Gateway cutover.

OPEN ITEMS:
- Replace isolation model and re-point server functions at the Gateway at cutover.
- Decide where cross-tenant sharing tables live in the physical model.
- Finish: notification delivery, AI invocation, document upload, access-management UI, invitations.
=== END BLOCK ===
```

## Where S6 lands in the comparison

| Topic | S6 (Lovable) position | vs the agreed target |
|---|---|---|
| Product framing | Multi-tenant venture deal platform | ✅ matches the product layer |
| Physical multi-DB | **Logical only (single DB + tenant_id + RLS)** | ❌ this is the drift |
| Control + Tenant DB | One shared DB, tenant_id column | ❌ to be split into Control + per-tenant DBs |
| Ownership rule | Dual Human + AI, enforced | ✅ matches |
| Deal sharing | Built, sharing ≠ transfer | ✅ matches |
| Lovable's role | Currently owns UI **and** backend | ⚠️ to become UI-only behind the Gateway |
| API Gateway | None — UI calls Supabase server functions | ⚠️ Gateway to be inserted (D4) |
| AI / Control AI | Not built (key unused) | ✅ matches the deferral (D6) |
| Status | ~70% screens; interim Supabase backend | — |

---

# PART 6 — MISSING INPUTS (still needed to fully lock the Overview)

1. **Client / who it's for** — ✅ **Your own venture.** SnackPortal2 is operated by you as **Control** (the platform operator), sold to **Tier 1 VC and PE firms that originate and lead investment rounds at pre-Series A and beyond.** Each firm is a tenant; its dealmakers are the agents. Decision-maker: you.
2. **Business / revenue model** — ✅ **Performance-aligned, dual-sided "AI-as-a-Service":** VC success fees (2–7% of deal value on platform-recommended investments) + startup matching fees (2–7%) + a minimum annual retention fee. Earns mostly on actual deals. *(Full detail in Part 1 → Business model. Raises a new decision — see D8.)*
3. **Definition of done** — ✅ Set, two tiers (see Part 1). **MVP** = firm onboarded on its own physical DB; agents manage/share **and email/chat** about deals via the Gateway; a manually-matched, recommended deal is attributed and billed end-to-end. **AI phase** = AI agents plug into those channels (find/discovery, AI email, AI chat).
4. **Target launch milestone** — ✅ **Before end of July 2026** (~6 weeks out). Hard date. ⚠️ Tight against committed scope — see the schedule note in Part 7.

---

# PART 7 — RECOMMENDED NEXT ACTIONS

1. **Build the API Gateway next** — author and review PRD 04 V2 (already your plan via D4). Keep it free of AI routing (Part 4B-C).
2. **Keep the Lovable UI; keep Supabase as interim** — and write down the cutover plan now so "interim" doesn't drift into "permanent."
3. **Reuse Lovable's 44-table schema** to seed the Control and per-tenant database schemas; resolve where cross-tenant sharing lives; **and apply the Part 4B reservations** (reserve the `control_ai_*` cluster, the `CONTROL_AI` role, the `ai.invoke` gate, and the AI-audit class) so the deferred Control AI stays additive.
4. **Close D5 (numbering)** — ✅ done (two tracks P-/B-, see PRD Index).
5. **Provide the Part 6 inputs** — ✅ all four filled.

## ⚠️ Schedule reality-check (target: before end of July 2026, ~6 weeks)
The committed MVP is large for the timeframe. To reach the definition of done it needs, on the **critical path**:
1. **API Gateway (B-7 / PRD 04 V2)** — author, review, build.
2. **Physical-DB provisioning + re-point Lovable's data layer** off the interim single-database Supabase (the logical→physical migration).
3. **Manual matching workflow + fees/billing engine** (the revenue path).
4. **Email + chat + calendar-booking tools** (currently gaps).

The tightest tension is **D2 (build-now physical multi-DB):** because the product must connect through the Gateway to *physical* tenant databases before launch, that migration sits on the critical path — it's the slowest item, and it's load-bearing.

If end-of-July is firm, options to make it feasible:
- **(a) Phase the launch** — go live with the revenue-critical core (onboard one tenant, manage/share deals, manual match, billing) and fast-follow the comms/calendar tools.
- **(b) Soft-launch the first tenant(s)** while the physical backend completes as a fast-follow — but weigh this against the physical-isolation selling point for competing VC firms (the whole reason for D2).
- **(c) Add delivery capacity** for the parallel workstreams (Gateway, migration, billing, tools).

*Recommended next step: build a week-by-week critical-path plan to test whether end-of-July is realistic and decide on phasing.*

---

*End. This v2 is the current north star. The PRD and all sessions trace back to it; the API Gateway is the next build; Lovable's UI is kept and its data layer is interim. Target: before end of July 2026.*
