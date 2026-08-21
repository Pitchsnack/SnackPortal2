# D-46 — Option A Gateway-Free Target Architecture Ratification

**Status:** ✅ Approved (Phase 0.5 — Contract Reconciliation)
**Date:** 2026-08-21
**Phase:** Architecture Planning · Contract-first governance
**Branch:** `phase/00.5-contract-reconciliation` (from `main` @ `cdb46fc9d`)
**Authority:** Dan's Option A directive (`SnackPortal2_Option_A_Clean_FastAPI_Rebuild_Claude_GPT.md`) + the Phase 0.5 instruction of 2026-08-21
**Trigger:** Phase 0 finding **CONF-1** — `IC-010` is **Final** and defines the API Gateway as the *"sole approved ingress"*, while the ratified Option A target mandates **zero API Gateway**. Nothing on `main` superseded it.
**Implements:** no runtime. This decision is **documentation, contracts and governance only.**

RFC-2119 keywords **MUST / MUST NOT / SHOULD / MAY** are used normatively.

---

## Numbering note — why this is D-46 and not D-45

`D-45` was allocated on the abandoned branch `phase/00-architecture-ratification` to a **different and contradictory** decision (the "FastAPI Implementation Proposal v2.2" ratification, which *retained* the Gateway runtime and re-scoped it to a BFF). That branch is not merged and is not the base for Option A. Authoring a second, contradictory `D-45` would put two incompatible decisions under one identifier in the project record.

**`D-45` is therefore deliberately skipped on `main` and is recorded as VOID / NOT ALLOCATED.** This decision takes **D-46**. Nothing from the abandoned branch is cherry-picked; every artefact in this phase is authored fresh.

---

## §1 — Decision (the ratified target)

The approved SnackPortal2 target architecture is:

```text
Frontend
   ↓
FastAPI BFF                      ← the single frontend-facing ingress
   │
   ├── FastAPI Authentication Service
   ├── FastAPI Access Control Service
   ├── FastAPI Control Plane
   ├── FastAPI Database Router
   ├── FastAPI Startup Service
   ├── FastAPI Investor Service
   ├── FastAPI Deal Service
   ├── FastAPI Sharing Service
   ├── FastAPI Import Service
   ├── FastAPI Lineage Service
   ├── FastAPI Contacts Service
   ├── FastAPI AI Agent Service
   └── FastAPI Audit Service
              ↓
      Control DB / Tenant DBs
```

The target runtime MUST contain:

```text
0 API Gateway runtime
0 API Gateway package
0 Gateway compatibility layer
0 Gateway launcher
0 Gateway routes
0 Gateway-specific configuration dependency
0 Gateway service dependency
```

**The BFF is not a renamed Gateway.** It is application-oriented frontend orchestration: it accepts frontend-facing requests, coordinates services, composes frontend responses, and propagates correlation context. It is **not** a generic proxy, **not** a routing gateway, and **not** a compatibility layer. The names *FastAPI Gateway*, *BFF Gateway*, *Service Gateway*, *Routing Gateway* and *Compatibility Gateway* are **prohibited**.

---

## §2 — CONF-1 resolved: IC-010 is superseded

**`IC-010 — API Gateway Contract` moves `Final` → `Superseded`**, superseded by **IC-013 — BFF Ingress Contract** and **IC-014 — Access Control Contract**.

IC-010's normative content is **not discarded** — it is **redistributed**. Every enforcement rule IC-010 placed at the Gateway edge survives at a named new home. The table in §4 is exhaustive: no IC-010 rule is dropped without an explicit disposition.

**Locked invariant #7 is retired.** The Canonical Overview's locked invariant #7 — *"The Gateway is the boundary — frontend → Gateway, never directly to DB/auth/router"* — is **superseded on the record** by:

> **#7 (revised) — The BFF is the boundary.** The frontend reaches backend services **only** through the FastAPI BFF, never directly to a database, the Authentication Service, the Access Control Service, or the Database Router. Internal service-to-service transport remains internal-only and is never client-reachable.

The *substance* of #7 — one governed public ingress, no client path around it — is **preserved and unweakened**. Only the identity of the component holding that position changes.

**Governance effect.** With IC-010 superseded and #7 revised, `CLAUDE.md` architecture constraint #5 (*contracts precede code*) is satisfied for Option A Phase 1: the target architecture now has contract authority. **This decision authorizes no implementation.** Phase 1 proceeds only under a separate, explicitly-authorizing execution instruction.

---

## §3 — The four-way separation is ratified

```text
Authentication  ≠  Access Control  ≠  Tenant Routing  ≠  Database Access
```

| Boundary | Question it answers | Owner | MUST NOT |
|---|---|---|---|
| Authentication | *Who are you?* | Authentication Service (IC-005) | authorize; choose a tenant; choose a database |
| Access Control | *What are you allowed to do?* | Access Control Service (**IC-014, new**) | authenticate; select a database; re-derive the active tenant; fail open |
| Tenant Routing | *Which active tenant and physical database may this request use?* | Database Router (IC-005/D-07) | authenticate; authorize; re-derive the tenant from anything but the signed claim |
| Database Access | *the physical connection* | Database Router **exclusively** | be performed by any other service |

Phase 0 established that **three of these four boxes exist today and are cleanly separated, and the Access Control box has never been built** — no permission engine exists anywhere in production code. IC-014 gives that box a contract for the first time.

The other ratified invariants are carried forward **unchanged and unweakened**:

```text
One Request → One Active Tenant → One Physical Database
Global Record ≠ Tenant Record
Import       ≠ Synchronization
Sharing      ≠ Ownership ≠ Tenant Transfer ≠ Deal Duplication
AI Skill     ≠ Permission ≠ Tenant Access ≠ Database Routing
```

Fail-closed remains absolute: if routing is invalid, missing or ambiguous, the request is denied. There is **no Control-DB fallback**, and no error path may downgrade to a less-isolated outcome.

---

## §4 — Re-homing map (normative — every IC-010 rule dispositioned)

This is the operative table of this decision. Phase 0 warned that four behaviours live **only** inside the Gateway and would be silently deleted with it, because the tests proving them are themselves category D. Each now has a named owner.

| IC-010 § | Rule | New home | Disposition |
|---|---|---|---|
| §A Purpose | "sole approved ingress" | **IC-013 §1** | **Changed** — the BFF is the single frontend-facing ingress. Substance preserved, holder changed. |
| §B Responsibilities | MAY authenticate/validate carriers/build context/dispatch/audit; MUST NOT select a DB, decide ownership, embed portal logic, run business logic | **IC-013 §3** | Carried forward, minus dispatch-as-proxy. The BFF *orchestrates*; it does not generically proxy. |
| §C Request Flow | the single approved per-request flow | **IC-013 §4** | **Changed** — an Access Control stage is inserted; see §5 below. |
| §D Authentication Boundary | auth is input, never routing logic; a valid token never selects a database | **IC-013 §4** + **IC-005** | Carried forward verbatim in substance. |
| §E Carrier Contract | exactly two recognized carriers (subdomain, `X-Tenant-Id`); cookies/query/portal/workspace/local-storage **prohibited as routing authority**; mismatch → 403 `carrier_mismatch` | **IC-013 §5** | **Re-homed — load-bearing.** One of the four Gateway-only behaviours. |
| §F Tenant Context | workspace derived from tenant context, never the reverse; `CarrierOnControlAnomaly` mandatory | **IC-013 §6** | Carried forward. |
| §G + §T Request Context | canonical `RequestContext`; **references only**; **constructed exclusively from `AuthContext`**; no inbound tenant/workspace parameter may reach the router | **IC-013 §7** | **Re-homed — load-bearing (D-33 §4.6 keystone).** One of the four. |
| §H Router Boundary | `→ Database Router` is the only approved routing boundary; the ingress never chooses a database; the router never authenticates | **IC-013 §8** + **IC-014 §7** | Carried forward, unweakened. |
| §I Portal Boundary | six portal classes reach backend services only through the governed ingress; no direct DB/Supabase/PostgREST access; portals display/discover/initiate only | **IC-013 §9** | Carried forward; "API Gateway" → "BFF". |
| §J Audit Contract | the emit-set (`CarrierMismatch`, `CarrierOnControlAnomaly`, `RouteDenied`, `IsolationAnomaly`) + success-access subclass + `share_*` subclass; references-only representation | **IC-013 §10** (emission) + **Audit Service** (durable sink) | **Re-homed — load-bearing.** One of the four. Emitter identity changes; classes, shapes and prohibitions are unchanged. See CONF-3 in §6. |
| §K Isolation | One Request = One Active Tenant = One Database; no request may access multiple tenant databases; breach → reject + `IsolationAnomaly` | **IC-014 §5** (decision) + **IC-013 §11** (enforcement at ingress) | **Re-homed — load-bearing.** One of the four (`assert_single_database`). |
| §L Error Handling | fail-closed denial set and semantics; no downgrade to a less-isolated outcome | **IC-013 §12** | Carried forward verbatim in substance. |
| §M Service Contract | services reachable only through the governed ingress for client ingress; internal transport is internal-only | **IC-013 §13** | Carried forward. |
| §N Future Channels | web/mobile/desktop/public API bind to the same rules identically | **IC-013 §14** | Carried forward. |
| §O Physical Multi-DB | Control DB and tenant DBs physically separate; no shared DB/schema/`tenant_id` isolation | **IC-013 §15** + **IC-014 §5** | Carried forward, **reinforced never weakened**. |
| §P Distinctness Hook | reserve support for D-15 distinctness verification | **Control Plane** (already implemented — `distinctness.py`) | Carried forward; the hook is already discharged. |
| §Q Dispatch Taxonomy | five categories; one request → one category → one database | **IC-013 §16** | **Changed** — restated as BFF *operation* categories; the isolation rule is unchanged. |
| §R Internal-Surface Protection | internal read APIs MUST NEVER be directly client-reachable | **IC-013 §13** | Carried forward — **critical**; this is the privilege-boundary rule. |
| §S Readiness Disclosure | minimally disclosing; no DB names, tenant counts, or topology | **IC-013 §17** | Carried forward; applies to **every** service's health/readiness under Option A §4. |
| §U IC-006/IC-007 Deferrals | AI and cross-tenant sharing not authorized | **IC-013 §18** | Carried forward; see CONF-5 / CONF-6 in §6. |
| §V Response Composition | arbitrary downstream body pass-through **forbidden**; contract-approved DTO composition permitted under §V.1 | **IC-013 §19** | Carried forward; the composing seam becomes the BFF. See CONF-2 in §6. |
| §W Acceptance Criteria | D-33 §10 criteria 4–6; D-37 §20 V1–V3 | **IC-013 §20** | Carried forward and re-pointed at the BFF. |
| §X Endpoint Dispatch vs DB Resolution | dispatch consumes no tenant/workspace/ownership selector; the route is never a client-controlled routing channel | **IC-013 §16** | Carried forward — **critical**. |
| Composition Boundary (D-44/IC-012) | the composition root is not an ingress | **IC-012** (amended) | See CONF-11 in §6. |

**Nothing in IC-010 is dropped.** Where a rule is marked *Changed*, the change is the holder or the stage list, never a relaxation.

---

## §5 — The revised request flow (normative)

IC-010 §C's flow had no authorization stage, because no authorization component existed. The ratified flow inserts one:

```text
Request
  → Authentication            (Authentication Service — who are you?)
  → Carrier Validation        (BFF — match-or-reject against the signed claim)
  → RequestContext Creation   (BFF — exclusively from AuthContext)
  → Access Control            (Access Control Service — allowed or denied?)
  → Tenant Routing            (Database Router — exactly one physical database)
  → Service
  → Response Composition      (BFF — contract-approved DTOs only)
```

**No alternate flow is permitted.** No stage may be skipped, reordered, or bypassed, and no path may reach a service or a database except through this flow.

**Ordering rules (normative):**
- Access Control runs **after** `RequestContext` construction and **before** Tenant Routing. It decides on references only; it never selects a database and never re-derives the active tenant.
- Carrier validation is **pre-context and pre-routing**. A carrier mismatch is denied before any `RequestContext` exists, before any classification, and before any Database Router or tenant-database contact.
- A denial at any stage terminates the flow. No partial access, no fallback, no default tenant.

---

## §6 — Disposition of the remaining Phase 0 conflicts

| # | Conflict | Disposition |
|---|---|---|
| **CONF-1** | IC-010 Final = "sole approved ingress" | **RESOLVED** — §2 above. IC-010 → Superseded; invariant #7 revised; IC-013 + IC-014 opened. |
| **CONF-2** | IC-009 portal DTOs are contractually *gateway-composed* | **RESOLVED** — IC-009 amended (insert-only): the composing seam is re-pointed from the API Gateway to the **BFF** under IC-013 §19. The DTO catalogue, field sets, provenance markers and `IC-009-R1` revision identity are **unchanged**. |
| **CONF-3** | Control DDL 012 pins `CHECK (source_service = 'api_gateway')` | **RESOLVED IN CONTRACT; MIGRATION SPECIFIED, NOT WRITTEN** — see §7. The database physically rejects a non-Gateway emitter, so a control migration is **required before any BFF audit emission**. Phase 0.5 is documentation-only, so the migration is *specified* here and authored under Phase 8. |
| **CONF-4** | Ownership cardinality disagrees three ways | ✅ **RESOLVED 2026-08-21 by [D-47](D-47-AI-Ownership-Cardinality-And-Service-Exposure-Model.md) — Dan ratified Option A.** At most one **current** AI Owner per record; multiple AI Agents may **contribute**, recorded through task history, provenance and audit, which never creates a second ownership; Option C reserved as additive. §8 below is superseded by D-47 §1. |
| **CONF-5** | Option A Phase 9 builds AI against the D-02/D-06 deferral and an all-TBD IC-006 | **PARTIALLY RESOLVED** — the Option A directive is Dan-authorized and **does reopen the AI deferral for the rebuild's Phase 9**; this is recorded. But **IC-006 remains an unusable placeholder** (every normative section reads TBD). **IC-006 MUST be authored to Draft-complete before Phase 9 begins** — recorded as a named prerequisite, not discharged here. The Canonical Overview Part 4B governance gate (a compliance/permissions review is a prerequisite, not an afterthought) **applies and is unwaived**. |
| **CONF-6** | Option A Phase 8 builds Sharing against a Draft IC-007 | **NOT RESOLVED — named prerequisite.** IC-007 MUST be promoted `Draft / Proposed` → `Final` before any Sharing Service work. Promotion is a governance act requiring Dan's ratification and is out of scope for a reconciliation phase. Action Tracker #23 stands. |
| **CONF-7** | Contacts Service has no contract | **NOT RESOLVED — named prerequisite.** A Contacts contract (next free number, **IC-015**) MUST be authored before Phase 7. Reserved here; not authored, because Contacts behaviour has no existing implementation to reconcile *from* — it is new product specification, not reconciliation. Action Tracker #22 stands. |
| **CONF-8** | `main.py` convention vs uvicorn containment | **RESOLVED** — IC-013 §21 ratifies the **app-factory** shape: each service exposes `create_app()` / `app`, and the concrete ASGI server stays confined to one shared runtime module. Option A §4's `uvicorn.run(...)` block is permitted **only** as a development convenience guarded by `if __name__ == "__main__":`, and MUST NOT be the production start path. This preserves the existing containment guard rather than retiring it. |
| **CONF-9** | `host="0.0.0.0"`, `reload=True`, missing uvicorn flags | **RESOLVED** — IC-013 §21 pins the serving posture: loopback default, `--workers 1`, `--no-access-log`, `--no-server-header`, `--no-proxy-headers`; `reload=True` development-only; `0.0.0.0` prohibited outside a deliberately-configured deployment binding. |
| **CONF-10** | Global directory gaps (no Global Investor contract; no `DEAL` kind; no `owner_agent_ref` on `control_directory`) | **PARTIALLY RESOLVED** — the `owner_agent_ref` gap is recorded as a required control migration in §7. The Global Investor contract and the D-35 Global Deal Directory implementation remain **named prerequisites** (Action Tracker #19); they are new specification, not reconciliation. |
| **CONF-11** | IC-012 governs a composition root Option A replaces | **RESOLVED** — IC-012 amended (insert-only): its principles (cross-service composition sits *above* services; nothing may import it; composition-only, no domain logic; narrow and exhaustive authority; an amendment is required to widen it) are **carried forward and re-scoped** to the Option A `deployment/` root. The specific `deployment.import_edge` binding and the Edge-9 package list are marked **historical**. |
| **CONF-12** | Frontend expects 86 operations; backend serves 3 | **ACKNOWLEDGED — scoping, not a contract defect.** IC-013 §22 defines the cutover as **incremental and partial by contract**: the BFF exposes operations as their owning services land, and the frontend's Supabase seam is retired per-operation, never big-bang. Full parity is **not** a Phase 10 precondition; a *governed, enumerated* cutover set is. |

---

## §7 — Required control-database migrations (specified, not authored)

Phase 0.5 authors no SQL. These are the migrations that MUST exist before the corresponding runtime work, recorded here so they cannot be forgotten:

**M-1 — Gateway audit source-service pin (blocks all BFF audit emission).**
`infrastructure/db/control/012_gateway_operational_audit.sql:69` carries `CHECK (source_service = 'api_gateway')`. PostgreSQL will reject any row emitted by a BFF. Additionally, DDL 012 and 013 are **byte-pinned** by `tests/architecture/test_b7c1_control_audit_ddl_blob_pins.py` and `test_b7c1r2_control_ddl_pin_completeness.py`, so the files cannot be edited without retiring those guards in the same change.

*Approved approach:* author a **new** append-only table for the BFF ingress-edge audit class rather than mutating 012/013. This leaves the existing table and its byte-pins intact as historical evidence, avoids a destructive change to an append-only audit store, and lets the two audit lineages coexist during cutover. The old table is retired only when the Gateway runtime is removed.

**M-2 — Global directory ownership column.**
IC-008 (Final) mandates exactly one `owner_agent_ref` on every Global Startup/Investor/Deal Directory record. `control_directory` (DDL 007) has no such column. A migration MUST add it before any Global Directory mutation operation is implemented.

Both migrations MUST be reversible, MUST be tested against disposable databases first, and MUST NOT be applied to production data without explicit human approval.

---

## §8 — CONF-4: ownership cardinality — ✅ RATIFIED

> **RESOLVED 2026-08-21. Dan ratified Option A.** See **[D-47 §1](D-47-AI-Ownership-Cardinality-And-Service-Exposure-Model.md)** for the normative rule; that section prevails over everything below.
>
> **The ratified rule:** at most one ***current*** AI Owner per record, held as a single reference — never a set, never a join table. **Multiple AI Agents may contribute**; contribution is recorded through **task history, provenance (IC-004) and operational audit (IC-002)**, is **never** an authorization input, and **never** creates a second AI ownership. Succession is permitted and audited (at most one holder at any instant). **Option C is reserved** as a purely additive later decision if Phase 9 proves it necessary. Activation is unchanged — `owner_ai_agent_ref` stays NULL platform-wide until IC-006.
>
> **Two divergences were created and are recorded, not resolved** (D-47 §1.4): the tenant DDL still implements the rejected join-table shape, and `test_tenant_ddl_schema_guards.py::test_ownership_pk_shapes` **actively asserts** it — so the DDL and that guard must change in the **same** Phase-7 commit. Additionally, the "task history" record class named by the ruling **has no contractual home yet**.
>
> *The options analysis below is retained as the decision record — it is what was decided from, not what is now in force.*

Three sources disagreed:

| Source | Human owner | AI owner | Representation |
|---|---|---|---|
| **IC-008 (Final)** + D-36 | **exactly one** `owner_agent_ref` | **at most one** nullable `owner_ai_agent_ref`, NULL platform-wide until IC-006 | **field on the record** |
| Tenant DDL `006_ownership.sql` | **at most one** (PK = entity id); exactly-one deferred to runtime | **zero or more distinct** | **join tables** |
| Canonical Overview invariant #3 | exactly one | "**and one** AI owner" | unspecified |

**Option A — Contract prevails (RECOMMENDED).** Adopt IC-008 as normative: exactly one human owner, at most one AI owner, both as references on the record. Rebuild the tenant schema accordingly.
*For:* IC-008 is Final and is the only source that reasons about *why* (D-36 rejected the alternatives on accountability grounds). Simplest to authorize against — one owner is one lookup. Preserves "AI-ready, not AI-required".
*Against:* discards the join-table shape; if Option A Phase 9 genuinely needs several AI agents acting on one record, this needs re-opening later.

**Option B — Schema prevails.** Adopt the join tables: at most one human owner, zero-or-more AI owners. Amend IC-008.
*For:* aligns with Phase 9's multi-skill AI agent model, where several agents plausibly touch one record.
*Against:* amends a Final contract on a hypothesis; "zero or more" weakens the accountability property D-36 was adopted to guarantee; makes every authorization check a set membership test.

**Option C — Split the concepts.** Ownership stays exactly-one human + at-most-one AI (IC-008, as the *accountability* record). AI *involvement* becomes a separate, explicitly non-ownership relation carried by the join tables.
*For:* both properties survive; accountability stays singular while AI participation stays plural; matches `AI Skill ≠ Permission`.
*Against:* two concepts to model, name and test; needs new contract text.

**Recommendation: Option A for the MVP rebuild, with Option C reserved** as the additive path if Phase 9 proves multiple AI agents must be attributed per record. Option A is the smallest lawful step and does not foreclose C.

**Outcome: Dan ratified Option A on 2026-08-21 — see D-47 §1.** The recommendation above was adopted, including the Option C reservation, with one refinement Dan added: the bound is *at most one **current*** AI Owner, and multiple AI Agents may contribute so long as contribution is recorded through task history, provenance and audit rather than as ownership.

---

## §9 — Non-overclaim

- **No runtime is implemented, changed, or removed by this decision.** The `api_gateway` package, its tests, its launcher and its runbooks are **untouched** on disk.
- **No old backend code is deleted.**
- **No branch is merged.**
- **No database migration is authored or applied.**
- **No blocker is closed.** Production remains **NOT READY / DO-NOT-ACTIVATE**.
- IC-013 and IC-014 open as **Draft / Proposed**, contract-first. They authorize no implementation; Phase 1 proceeds only under a separate, explicitly-authorizing execution instruction.
- The Physical Multi-Database MVP is **mandatory and unchanged**, reinforced and never weakened by this decision.
- Four items remain **named prerequisites, not discharged**: IC-006 to Draft-complete (before Phase 9), IC-007 to Final (before Phase 8), IC-015 Contacts (before Phase 7), Global Investor / Global Deal Directory contracts.
- **CONF-4 remains open** pending Dan's ratification (§8).

---

## §10 — Affected contracts

| Contract | Change |
|---|---|
| **IC-010** — API Gateway Contract | `Final` → **Superseded** (by IC-013 + IC-014). Insert-only supersession amendment; no normative text deleted. |
| **IC-013** — BFF Ingress Contract | **NEW** — `Draft / Proposed` (IC-013-DRAFT-1) |
| **IC-014** — Access Control Contract | **NEW** — `Draft / Proposed` (IC-014-DRAFT-1) |
| **IC-009** — Portal Contracts | Amended (insert-only) — composing seam re-pointed to the BFF; DTO catalogue unchanged; remains `Final`, revision `IC-009-R1` unchanged |
| **IC-005** — Authentication Routing | Amended (insert-only) — Access Control named as a distinct service; authentication's prohibitions restated; remains `Final` |
| **IC-012** — Service Composition & Deployment Root | Amended (insert-only) — principles carried forward and re-scoped; Edge-9 specifics marked historical; remains `Draft / Proposed` |
| **IC-001, IC-002, IC-003, IC-004, IC-008, IC-011** | **No change** — boundaries respected |
| **IC-006** | No change — remains `Draft`; named prerequisite for Phase 9 |
| **IC-007** | No change — remains `Draft / Proposed`; named prerequisite for Phase 8 |
| **IC-015** | **Reserved** — Contacts Service Contract; named prerequisite for Phase 7 |

---

## §11 — Sources

- `SnackPortal2_Option_A_Clean_FastAPI_Rebuild_Claude_GPT.md` (Dan-authorized Option A directive)
- `SnackPortal2_Phase0_New_Branch_Instructions_Claude_GPT.md`
- `docs/Phase-0-Requirements-Extraction-Report.md` (branch `phase/00-requirements-extraction` @ `5a2d106c3`) — the CONF-1…CONF-12 findings dispositioned above
- `contracts/IC-010-API-Gateway-Contract.md` (the superseded contract, read in full)
- `docs/SnackPortal2_Canonical_Overview_and_Decisions_v2.md` (locked invariant #7)
- `docs/Architecture-Decision-Register.md` (D-01 … D-44)
