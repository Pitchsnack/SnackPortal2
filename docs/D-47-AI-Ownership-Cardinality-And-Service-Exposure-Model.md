# D-47 — AI Ownership Cardinality & Service Exposure Model

**Status:** ✅ Approved (Dan, 2026-08-21) — Phase 0.5 finalization
**Date:** 2026-08-21
**Phase:** Architecture Planning · Contract-first governance
**Branch:** `phase/00.5-contract-reconciliation`
**Authority:** Dan's ratification instruction of 2026-08-21 ("Phase 0.5 architecture direction is accepted for finalization")
**Closes:** Phase 0 finding **CONF-4** (ownership cardinality) and finalizes **CONF-9** (service startup/exposure)
**Implements:** no runtime. Documentation and contracts only.

RFC-2119 keywords **MUST / MUST NOT / SHOULD / MAY** are used normatively.

---

## §1 — Decision 1: AI ownership cardinality — **Option A ratified**

> **The SnackPortal2 MVP shall support at most one *current* AI Owner per record.**
> **Multiple AI Agents may contribute to a record, but contribution is recorded through task history, provenance and audit, and does not create multiple AI ownership.**
> **The additive multi-owner Option C is reserved** for a later decision if Option A Phase 9 proves it necessary.

### §1.1 — What was contested (CONF-4)

| Source | Human owner | AI owner | Representation |
|---|---|---|---|
| **IC-008 (Final)** + D-36 | exactly one `owner_agent_ref` | **at most one** nullable `owner_ai_agent_ref` | **field on the record** |
| Tenant DDL `006_ownership.sql` | at most one (PK = entity id) | **zero or more distinct** | **composite-PK join tables** |
| Canonical Overview invariant #3 | exactly one | "**and one** AI owner" | unspecified |

Three cardinalities, two representations, one of them (invariant #3) marked *locked*.

### §1.2 — The ratified rule (normative)

**R-1 — Cardinality.** Every governed record has **exactly one** human Owning Agent (`owner_agent_ref`, unchanged) and **at most one *current*** Owning AI Agent (`owner_ai_agent_ref`).

**R-2 — Representation.** AI ownership is a **single reference on the record**, never a set and never a join table. A decision path, query, or DTO that iterates a collection of AI owners is a contract violation.

**R-3 — "Current" is a cardinality bound, not a permanence claim.** AI ownership **MAY** pass from one AI Agent to another over time; **at most one holds it at any instant**. Each succession is an **audited ownership transfer** under IC-008's *Ownership Transfer* rules, with history retained in the audit/provenance record. It is **never** a widening to two concurrent AI owners.

**R-4 — Contribution ≠ Ownership.** Any number of AI Agents **MAY** contribute to a record. A contribution record:
- MUST be a **task-history**, **provenance (IC-004 lineage)**, or **operational-audit (IC-002)** record;
- MUST NOT be an ownership record, MUST NOT populate `owner_ai_agent_ref`, and MUST NOT be counted as ownership by any consumer;
- **MUST NOT be an authorization input** (IC-014 §7). This follows *a fortiori* from IC-008 Ownership Principle 1 — if owning a record grants nothing, contributing to one grants strictly less.

**R-5 — Prohibited by this ratification.** Two or more concurrent AI owners on one record · a co-owner or secondary-owner reference · an ownership-shaped join table for AI ownership · any representation permitting a *set* of AI owners · inventing a new record class at implementation time to carry contribution (see §1.4).

**R-6 — Activation is unchanged.** This decision settles **cardinality**, not **activation**. `owner_ai_agent_ref` remains **nullable, optional, reserved, and NULL platform-wide until IC-006** defines the AI-agent identity namespace and its resolution path (IC-008 V10 stands). A populated AI-owner reference before IC-006 is an error condition, not a grant.

**R-7 — Option C reserved.** A separate, explicitly **non-ownership** AI-*involvement* relation remains available as a purely **additive** later decision, should Phase 9 prove it necessary. Reserving it authorizes nothing, creates no field or table, and does not weaken R-1…R-5 in the meantime. Should it later be adopted, it arrives as an *involvement* relation and MUST NOT become an authorization input without an IC-014 amendment.

### §1.3 — Why Option A (recorded rationale)

The decision preserves the property D-36 was adopted to guarantee. D-36 rejected its alternatives specifically on **accountability** grounds: O1 (no ownership) had no accountable party, and O2 (human-only) ignored the business intent that AI agents become first-class owners. A *set* of AI owners reintroduces the O1 problem in a subtler form — when several parties own a record, none is singularly accountable for it.

Option A also keeps authorization cheap and legible: one owner is one lookup, not a set-membership test on every check. And it forecloses nothing — Option C remains available as a strictly additive step, so the plural case can be supported later **without** rewriting the ownership model, only by adding a relation beside it.

### §1.4 — Known divergences created by this ratification (recorded, not resolved)

**DIV-1 — The tenant DDL still implements the rejected shape.** `infrastructure/db/tenant/006_ownership.sql` defines `startup_ai_ownership`, `investor_ai_ownership` and `deal_ai_ownership` as composite-PK join tables permitting zero-or-more AI agents per record. This now diverges from R-1/R-2.

**DIV-2 — A guard actively enshrines the rejected shape.** `backend/tests/architecture/test_tenant_ddl_schema_guards.py::test_ownership_pk_shapes` (line 219) asserts:

```python
assert re.search(rf"PRIMARY KEY \({entity}_id, ai_agent_id\)", text), (
    f"{entity}_ai_ownership must have composite PRIMARY KEY ({entity}_id, ai_agent_id)"
)
```

That assertion **requires** the zero-or-more shape. Any DDL change satisfying R-2 will fail this guard, so the guard and the DDL MUST be changed **in the same commit** — otherwise either the schema change is blocked or the guard is silently weakened.

**Disposition of DIV-1 and DIV-2: named Phase-7 work.** Neither was changed here. Phase 0.5 is documentation and contracts; the DDL is schema and the guard is test code, and Dan's instruction is explicit that Phase 1 has not begun. **No DDL and no test was modified by this decision.**

**DIV-3 — "Task history" has no contractual home.** R-4 names three record classes for contribution. Provenance (IC-004) and operational audit (IC-002) exist. **A *task-history* record class does not exist in any contract or schema.** Until it is specified, contribution is recordable **only** through IC-004 provenance and IC-002 operational audit, and **no new record class may be invented at implementation time to fill the gap.** Specifying it attaches to IC-006 / the AI Agent Service and is a **named prerequisite** for Phase 9.

---

## §2 — Decision 2: Service startup & exposure model

> **For local development, internal FastAPI services must default to loopback/private exposure rather than public exposure. Only the BFF is permitted to be the governed public application ingress. `reload=True` is local-development only. Containerized internal services may bind internally as necessary, but their ports must not be publicly published.**

### §2.1 — The controlling distinction: BIND vs PUBLISH

A process **binds** an address inside whatever network namespace it runs in. A deployment **publishes** a port outward, to the host or the internet. **These are separate controls**, and conflating them produces errors in both directions:

- *False alarm:* a container binding `0.0.0.0` **inside its own namespace** is normal and necessary — that binding reaches only the container network. A rule that forbids it outright would be unimplementable and would be ignored.
- *Real hole:* a service correctly bound to a private interface, then **published** by one line in a compose file, is publicly reachable no matter how careful the application code is.

This decision therefore governs **both, separately** — which supersedes the earlier, cruder formulation in the first draft of IC-013 §21 ("`0.0.0.0` is prohibited outside a deliberately-configured deployment binding"). That wording targeted the wrong layer.

### §2.2 — The ratified rules (normative — IC-013 §21.1 E-1…E-7)

| # | Rule |
|---|---|
| **E-1** | **Only the BFF is a public ingress.** No other backend service may be publicly reachable, in any environment. |
| **E-2** | **Local development: loopback/private by default.** Internal services default to `127.0.0.1` or another private interface. `0.0.0.0` MUST NOT be an internal service's default bind in local development. A wider bind requires an explicit, deliberate setting — it is never what happens by omission. |
| **E-3** | **Containers: bind internally, publish never.** A containerized internal service MAY bind `0.0.0.0` **within its container**. Its port **MUST NOT be published** to the host or any public network — no `ports:` mapping, no `-p`/`--publish`. Container-network reachability only. **Only the BFF's port may be published.** |
| **E-4** | **`reload` is local-development only.** Never in a shared, hosted, containerized, staging, or production environment. |
| **E-5** | **Serving flags are a set:** `--factory --workers 1 --no-access-log --no-server-header --no-proxy-headers`. Omitting one silently restores a uvicorn default; a partial application is a violation. |
| **E-6** | **Exposure MUST be verifiable as a deployment property.** Phase-1 acceptance MUST include a **deployment-manifest check** proving that across every compose file, Kubernetes manifest, environment template and launcher script, **exactly one service publishes a port, and it is the BFF**. |
| **E-7** | **Precedence.** Where any template, compose file, launcher, runbook or sample conflicts with E-1…E-6, the contract prevails and the artefact is the defect. Option A §4's `uvicorn.run(host="0.0.0.0", …, reload=True)` sample is **superseded**: illustrative only, never to be copied as written. |

### §2.3 — Why E-6 exists

E-1 and E-3 are violated by **configuration**, not by code. An application-layer test can prove a service *binds* correctly and still miss that a compose file *publishes* it. A code-only acceptance set therefore cannot discharge this decision — the manifest check is not optional polish, it is the only place the rule is actually enforceable.

This is the same lesson Phase 0 recorded about the Gateway: removing it removed a **network position**, and a network position is defended by deployment configuration, not by application logic.

---

## §3 — Contracts amended by this decision

| Contract | Change | Status after |
|---|---|---|
| **IC-008** — Ownership | Insert-only amendment ratifying Option A; *AI Ownership Rule* gains the cardinality ratification, the contribution-≠-ownership rule, the succession rule, the task-history gap, and the Option C reservation. Human ownership and all five Ownership Principles untouched. | `Final` (unchanged) |
| **IC-013** — BFF Ingress | §21 gains **§21.1 Exposure Model (E-1…E-7)**, replacing the earlier bind-only wording; §13 deployment obligation re-pointed at §21.1; §20 gains the **exposure proof** acceptance criterion; §24 gains prohibitions 15–18. | `Draft / Proposed` (unchanged) |
| **IC-014** — Access Control | §7 replaces the interim CONF-4 holding rule with the ratified rule, and states that **contribution records are never authorization inputs**; §12 re-points exposure at IC-013 §21.1. | `Draft / Proposed` (unchanged) |
| **D-46** | §6 CONF-4 row and §8 updated to **RESOLVED**, pointing here. | ✅ Approved (unchanged) |
| IC-001–IC-005, IC-009–IC-012 | **No change** — boundaries respected | unchanged |

---

## §4 — Remaining prerequisites after this decision

| # | Prerequisite | Blocks | Owner |
|---|---|---|---|
| P-1 | **Reconcile tenant DDL `006_ownership.sql` + `test_ownership_pk_shapes` together** (DIV-1 + DIV-2) — the guard asserts the shape the contract now rejects, so both change in one commit | Phase 7 | implementation |
| P-2 | **Specify the task-history record class** (DIV-3) — named by R-4, exists nowhere | Phase 9 | IC-006 / AI Agent Service |
| P-3 | **IC-006 → Draft-complete** (every normative section reads `TBD`); Part 4B governance gate unwaived | Phase 9 | contract |
| P-4 | **IC-007 → `Final`** | Phase 8 | contract |
| P-5 | **IC-015 — Contacts Service Contract** (reserved, unauthored) | Phase 7 | contract |
| P-6 | **Global Investor Contract**; **D-35 Global Deal Directory** | Global directory work | contract |
| P-7 | **Migration M-1** — new append-only table for BFF ingress-edge audit; DDL 012's `CHECK (source_service='api_gateway')` physically rejects a BFF row | **all** BFF audit emission | migration |
| P-8 | **Migration M-2** — `control_directory.owner_agent_ref` per IC-008's global-ownership mandate | Global Directory mutation | migration |
| P-9 | **Deployment-manifest exposure check** (E-6) | Phase 1 acceptance | implementation |

---

## §5 — Non-overclaim

- **No runtime code was modified.** `git diff main -- backend/` is empty.
- **No DDL was authored or changed.** DIV-1 is recorded, not fixed.
- **No test was changed, weakened, or retired.** DIV-2 is recorded, not fixed.
- **No branch was merged; nothing was pushed.**
- **No blocker was closed.** Production remains **NOT READY / DO-NOT-ACTIVATE**.
- **Phase 1 has not begun** and is not authorized by this decision.
- IC-013 and IC-014 remain **`Draft / Proposed`**; IC-008 remains **`Final`**.
- The Physical Multi-Database MVP is **mandatory and unchanged**.

---

## §6 — Sources

- Dan's ratification instruction, 2026-08-21
- `docs/D-46-Option-A-Gateway-Free-Target-Architecture-Ratification.md` §8 (the options this decision selects from)
- `docs/Phase-0-Requirements-Extraction-Report.md` (CONF-4, CONF-9) — branch `phase/00-requirements-extraction` @ `5a2d106c3`
- `contracts/IC-008-Ownership-Contract.md`; `docs/D-36-Ownership-Architecture.md` (the accountability rationale)
- `infrastructure/db/tenant/006_ownership.sql`; `backend/tests/architecture/test_tenant_ddl_schema_guards.py:219` (the recorded divergences)
