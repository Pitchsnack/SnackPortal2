# SnackPortal2 — Gateway-Free Architecture Contract Ratification — Result

**Instruction:** `SnackPortal2_Gateway_Free_Architecture_Contract_Ratification_GPT.md`
**Branch:** `experiment/complete-api-gateway-removal-mvp`
**Date:** 2026-08-11 · **Author:** Claude (Opus 5)
**Scope executed:** documentation / architecture contracts / governance records only

---

## VERDICT

```text
GATEWAY-FREE ARCHITECTURE CONTRACT RATIFICATION PASS WITH FROZEN RESIDUALS
```

**The official architecture now describes the Gateway-free design.** IC-010 is retargeted from the
*API Gateway Contract* to the **Public Edge Ingress Contract**; IC-011, IC-009, IC-012, IC-005,
IC-002, IC-001, IC-007 and IC-008 are reconciled; **D-45** is recorded as an explicit human
architecture decision; and Canonical Overview **locked invariant #7** is superseded **on the record**
rather than silently edited. Every gate is green: **1789 tests pass**, `lint-imports` **4 kept / 0
broken**, `ruff` clean, `mypy` clean on 344 files.

**The verdict carries "WITH FROZEN RESIDUALS" for two reasons, both deliberate and both out of this
task's authority:**

1. **The frozen DDL / SecretRef family** the instruction §7 forbids touching — DDL 012/013,
   `source_service = 'api_gateway'`, `control_gateway_audit`, and the AW-1 audit-writer SecretRef.
   Every currently-authoritative document that names them now states explicitly that they are
   **frozen compatibility artifacts pending a separately authorized migration** and are **not
   evidence that an API Gateway runtime exists**.

2. **Four byte-pinned B5 *production* activation-gate documents** still carry Gateway-named
   criteria. They are pinned SHA-for-SHA by `test_dbr_ar_2e_activation_evidence_boundaries.py`,
   whose own comment records that re-stamping those pins *"needed explicit authorization rather than
   being a mechanical edit."* Reconciling them is a **production**-governance act, and instruction
   §9 is explicit that D-45 must not be presented as production approval. I left them alone. The
   effect is **fail-safe**: the gate criterion *"API Gateway remains the sole ingress"* is
   unsatisfiable by construction, so the production gate stays **shut**. Full detail in §8.

Nothing was pushed, no PR was opened, nothing was merged, no DDL / SecretRef / credential /
Keycloak / live-PostgreSQL / standing-runtime change occurred, and **`main` is byte-identical to its
pre-task state.**

---

## 1. Exact branch / base / head

| Item | Value |
|---|---|
| worktree | `D:\Pitchsnack\SnackPortal2_pr111_verify` |
| branch | `experiment/complete-api-gateway-removal-mvp` |
| `git rev-parse main` | `cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f` (unchanged) |
| `git merge-base main HEAD` | `cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f` (identical — `main` is not an ancestor of any new work but the base is untouched) |
| HEAD **before** this task | `97769ddbbfee8bc44768744c1790f81b78b45688` |
| ratification commit | `a3a504b7740e3c46d4a04301a41c0a2daa58c100` — *D-45: ratify the Gateway-free architecture in the official contracts* (35 files, +1401 / −360) |
| HEAD **after** this task | the follow-up **SHA-stamp commit** that writes `a3a504b7` into this table. Its own SHA cannot appear inside itself; read it from `git log -1`. It changes this file only. |
| change composition | **35 files** — 33 modified, 2 added (`docs/D-45-…` + this result), 0 deleted |
| working tree after commit | clean |

`97769ddb` is the reference point throughout: every "before" reading is `git show 97769ddb:<path>`.

---

## 2. Authoritative documents inspected

A full tracked census of the §10 pattern list ran **before** and **after** the amendment set, over
every `*.md`, `*.sql`, `*.toml`, `*.json`, `*.yml` and `*.ps1` file `git ls-files` reports.

**Inspected and classified: 74 files carrying at least one match.** Of those:

| Bucket | Files | Treatment |
|---|---:|---|
| `contracts/` — the twelve interface contracts | 12 | read in full; **9 amended**, 3 unchanged |
| Auto-imported governance (Canonical Overview · Action Tracker · PRD Index · `CLAUDE.md`) | 4 | read in full; **all 4 amended** |
| `docs/Architecture-Decision-Register.md` | 1 | read in full; amended (D-45 row + detail + D-37 supersession-in-part + closing note) |
| Active runbooks (`docs/runbooks/`, `infrastructure/runbooks/`) | 14 | read; 2 amended, 12 already banner-flagged by the removal task |
| Active runtime governance (`docs/runtime/`) | 10 | read; **5 amended**, 1 historical-evidence, **4 frozen byte-pinned** (§8) |
| Standards / roadmap / gap analysis / IaC | 5 | read; **all 5 amended** |
| Historical evidence (`docs/reports/`, `docs/handover/`, `docs/PROJECT-HANDOVER-*`, `docs/Phase-*`, prior `docs/D-xx`, `docs/d15/`, `docs/auth/`) | 22 | read; **deliberately not rewritten** (§6 of the instruction) |
| Frozen DDL (`infrastructure/db/**`) | 4 | read; **untouched** |
| Build / CI / launcher (`pyproject.toml`, workflow, `start-sp2-local.ps1`) | 3 | read; already correct — their matches are comments recording the removal |

Also read in full for context: `docs/D-37-Portal-Contract-Architecture.md`,
`docs/D-33-*`, `docs/runbooks/gateway_free_mvp_topology.md`, and the two removal result reports.

---

## 3. Exact contracts amended

| Contract | Status | Amended? |
|---|---|---|
| **IC-010 — Public Edge Ingress Contract** *(was: API Gateway Contract)* | Final | ✅ **primary retargeting** |
| **IC-011 — Hosted Rollback Proof Contract** | Draft / Proposed | ✅ §3 gate rule + §9 + §10 |
| **IC-009 — Portal Contracts** | Final (IC-009-R1) | ✅ retarget + **new §P.0** |
| **IC-012 — Service Composition & Deployment Root** | Draft / Proposed | ✅ §2/§3/§4/§13/§14.9/§15/§18 |
| **IC-005 — Authentication Routing Contract** | Final | ✅ every Gateway reference retargeted |
| **IC-002 — Tenant Startup Contract** | Final | ✅ class 3 / 3a / 3b emitter + labels + as-built pointer |
| **IC-001 — Global Startup Contract** | Final | ✅ 2 naming lines |
| **IC-007 — Deal Collaboration & Cross-Tenant Sharing** | Draft / Proposed | ✅ 5 naming lines |
| **IC-008 — Ownership Contract** | Final | ✅ 2 naming lines |
| **IC-003 — Import Contract** | Final | — no match, no change |
| **IC-004 — Lineage Contract** | Final | — no change (its one hit is a link to IC-006) |
| **IC-006 — AI Gateway Contract** | Draft (post-MVP, D-02) | — **UNRELATED — RETAIN.** A different, deferred component. Zero matches on the ratification patterns. |

**Revision markers:** IC-009's served revision **remains IC-009-R1**; IC-011 remains
IC-011-DRAFT-1; IC-012 remains IC-012-DRAFT-1. No contract changed status tier.

---

## 4. Clause-by-clause old → new

### 4.1 IC-010 — the primary retargeting

| § | Old | New |
|---|---|---|
| **Title** | *IC-010 — API Gateway Contract* | *IC-010 — **Public Edge Ingress Contract***, with a retained-file-name note. The **number and file name are unchanged** so all 8 cross-references and 5 guard paths keep resolving. |
| **§A** | "the **API Gateway** as the **sole approved ingress**" | "**The sole approved client ingress is through explicitly governed authenticated public edges owned by the service responsible for the exposed route family.**" |
| **§A.1** *(new)* | — | The normative **eight-point definition** of an approved public edge, verbatim from the instruction §2. |
| **§A.2** *(new)* | — | The **closed ratified set** — public Startup edge (`database_router`), public Workspace edge (`control_plane`). "Any new public edge requires explicit architecture/governance approval." **No generic replacement Gateway under another name** ("MVP Gateway"/"thin Gateway"/"lightweight Gateway"/"BFF"/"proxy layer" named as the prohibited shape). |
| **§B** | "the gateway MAY … MUST NOT" | "an approved public edge MAY … MUST NOT", **plus** a new prohibition: it may not dispatch into another service's route family. |
| **§C** | "**No alternate flow is permitted.**" | Prohibition **reframed, not removed**: "**No client may bypass an approved public edge to reach internal service APIs, routing APIs, Control-Plane internal read APIs, audit-ingest APIs, database transports, or databases directly.**" |
| **§X** | "Endpoint dispatch (gateway)" | "**Route ownership (public edge)**" — the owning service is a **structural** property fixed at composition, not a per-request computation. Database resolution stays exclusively the Database Router's. |
| **§Q** | "Endpoint Dispatch Taxonomy" | "**Public Route-Family Taxonomy**". Five category names, their semantics, and *one request → one category → one database* are **unchanged**; each family gains an **owner** and a **served / edge-dark** status; new rule: *a route family has exactly one owner*, and *an edge-dark family is a recorded absence, not an omission*. |
| **§H** | "The Database Router never authenticates." | "**The Database Router does not perform identity authentication.** Public-edge authentication is delegated through the approved Auth Router contract, and routing logic receives only trusted authenticated context." Plus: owning a public edge grants a service **no** authentication authority and **no** import of another service. |
| **§I / §M / §N** | portals/services/channels reachable "**only through the API Gateway**" / "gateway-only ingress" | "**Client and portal traffic may reach backend business functionality only through the approved authenticated public edge that owns that route family.**" **Internal edges remain non-public** is stated explicitly in all three. |
| **§J** | "The gateway is the **emitter**" | "**The route-owning authenticated public edge is the sole emitter of the required public-request audit event for its route.**" Subclass label "gateway-edge" → "public-edge" — **label only**. Explicit: *no action string, class membership, exactly-once rule, residency, emitter count, or vocabulary changes; no class added, removed, renamed or re-homed.* |
| **§V** | "**Gateway-owned** and typed composition" · "GATEWAY-COMPOSED … DTO RESPONSE" | "**Route-owner-owned** and typed" · "**ROUTE-OWNER-COMPOSED**, CONTRACT-APPROVED DTO RESPONSE". **Every §V.1 condition and §V.2 prohibition preserved verbatim**; §V.2 additionally gains an explicit "expose **internal envelopes**" prohibition. |
| **§R** | "behind the gateway boundary" | "behind the public-edge boundary"; the directory-read authentication requirement is **strengthened** — it binds any future edge and is *"not relaxed by the family currently being edge-dark."* |
| **§Y** *(new)* | — | **Frontend Integration Contract**: no single generic endpoint; Startup routes → Startup edge; Workspace routes → Workspace edge; two origins, two CORS allowlists, two upstreams, two TLS terminations; silent-failure warning; OIDC redirect origin unchanged. Frontend cutover **NOT DONE**. |
| **§W** | V3 "only through the API Gateway" | V3 "**only through approved authenticated public edges**" |
| **§K/§L/§O/§S/§U/§P** | gateway-named | public-edge-named. §K gains: *two public edges do not weaken one-request-one-database*. §L gains the explicit size-bound / exact-origin-CORS / bounded-correlation-id restatement. §S gains a **no self-describing surface** rule. |
| **Composition Boundary (D-44)** | "The API Gateway remains the **sole served ingress**" | reconciled: the approved public edges are the sole served client ingress; **Edge 9 is an internal, non-public edge and is not a client ingress path**. |
| **D-15-T1a capture** | "Normative … the T1 source of truth" | **HISTORICAL — WITHDRAWN AS AN ACTIVE REQUIREMENT** (both wire ends deleted). Its *prohibitions* survive at §V.2, and the surviving property (*one request → one physical tenant DB*) is restated. |
| **07E-2-C note** | active | **PARTIALLY HISTORICAL** — prohibitions retained, the port widening withdrawn for want of a subject. |
| **07E-3a capture** | "internal API Gateway ↔ Auth Router" | **CURRENT, retargeted** — the transport **survives**; only its client changed (now the shared public-boundary kernel). |
| **R1 / CLM / D-43 sections** | gateway-named routes and emitters | public-edge-named. Every route, bound, DTO, field set, audit action, and denial semantic is **unchanged**. CLM gains a D-45 note: the route owner's `short_description` bounds are now the **sole** enforcement and may not be weakened as "redundant". |

### 4.2 IC-011

| Old | New |
|---|---|
| §3 "**API Gateway** is the **sole served ingress**" | "**Only architecture-approved public edge modules may be served to client traffic**" (IC-010 §A.2 is the closed set; each edge must satisfy §A.1 in full) |
| derived gate rule "a non-Gateway served edge → **STOP**" | five explicit STOP conditions: **unapproved public edge** · **internal edge exposed publicly** · **generic dispatcher / proxy reintroduced as public ingress** · **public route not owned by its serving service** · **missing authentication / public-boundary enforcement**. Serving *more than one approved* edge is explicitly **not** a STOP. |

Everything else in IC-011 — hosted-staging/pre-production classes, the LIVE PRODUCTION prohibition,
physical multi-DB topology, auth-separate-from-routing, Database-Router-sole-selector, SecretRef-only
registry, rollback targets, triggers, evidence discipline, verdict vocabulary, and the
B5-BLK-8-stays-OPEN rule — is **preserved verbatim**. The hosted runbook
`infrastructure/runbooks/b5_blk8c_hosted_rollback_proof.md` carries the same rule and the same five
STOP conditions into its H1 census.

### 4.3 IC-009 — including the four lost-subject dispositions (new §P.0)

Retargeted: Boundary, the layered-on IC-010 summary, §F (now with an **owner** and a **served /
edge-dark** column), §F.1, §H, §J, §J.1, §M, §R V3, §Q(d), the CLM section. §C gains a
served-surface note stating the directory columns are **edge-dark** — *"The matrix is unchanged and
remains contract law; it simply has no served directory surface to bind to."*

**§P.0 — the four dispositions** (each with a named re-binding trigger; each asserted absent by
`test_ic009_portal_binding_checks.py::test_the_withdrawn_ic009_surfaces_are_really_absent`):

| §P check | Subject | Disposition |
|---|---|---|
| **§P.1** directory-DTO tenant anonymity | the three directory / global-summary DTOs | **DEFERRED — UNBOUND.** `GET /directory/<kind>` is edge-dark. The D-35 Tenant Anonymity Rule and the field sets remain contract law and **re-bind automatically** when a directory route owner is approved. |
| **§P.3** one §Q category → one domain → one DB | a runtime dispatcher / classifier | **SUPERSEDED — RE-SCOPED, NOT WEAKENED.** No dispatcher exists; the mapping is **structural**. Re-scoped to: *every served route belongs to exactly one §Q family owned by exactly one public edge and resolves to exactly one database.* |
| **IC-007 four route prefixes** | the Gateway classifier | **WITHDRAWN — no classifier exists.** The four adopted Governed Sharing categories stay **authored-but-inert until IC-007 is Final**. |
| **import DTOs** | the served `/import` route | **DEFERRED — UNBOUND.** Import is outside the controlled local MVP journey; Edge 9 is internal and non-public. |

New change-control clause **§Q(e)** makes this the rule going forward: a removed subject requires an
explicit disposition with a named re-binding trigger, and **never** licenses inventing a replacement
capability or deleting the rule.

**Preserved unchanged:** every typed public DTO and its exact field set, the provenance markers, the
tenant-anonymity rule, deterministic serialization, denial sequencing, the IC-006/IC-007 deferrals,
and the served revision IC-009-R1.

### 4.4 IC-012

`api_gateway` removed from §2 (service list), §3 (`deployment ─╳─> api_gateway`), §4
(`api_gateway ↛ deployment`), §13 (import-linter `forbidden_modules`), §14.9 and §18 — **because the
package was deleted, not because the D-44 grant widened.** A normative note is added to §3:

> This list previously also named `deployment ─╳─> api_gateway`. That package was **deleted**, so the
> complement shrank; **the authorized set above did not move.** The un-authorized list remains the
> **exact complement** of the §3 grant over every surviving service package, and widening it still
> requires the §5.1 amendment path.

§15's IC-010 cross-reference is reconciled: the approved public edges are the sole served client
ingress, and **Edge 9 is internal and non-public**. **Edge 9 / import architecture is otherwise
untouched**, as §4.4 of the instruction required, and no DDL or live import behavior was edited.

### 4.5 IC-005

Every reference that named the API Gateway as the *caller* of authentication, the *stripper* of
prohibited carriers, or the *emitter* of the public-request audit event now names the approved public
edge. The subclass label "gateway-edge" → "public-edge" (label only, stated as such).

**Preserved exactly:** the Auth Router performs Stage-1 DB-free token validation and Stage-2
tenant/membership/role/readiness resolution; returns only the four-field references-only
`AuthContext`; remains **detection and signalling only**; and **authentication is not moved into the
Database Router or the Control Plane** — IC-005's §H-facing wording is now the instruction's preferred
form. Token validation, JWKS, OIDC, the JWT lifecycle, D-32 roles, D-06 carriage, the D-33 carrier
rule and every denial semantic are unchanged.

### 4.6 IC-002 / IC-001 / IC-007 / IC-008

IC-002: class 3 / 3a / 3b emitter and subclass labels retargeted; the as-built type pointer refreshed
from the deleted `api_gateway/models.py` to `backend/shared/public_edge.py::EdgeAuditEvent`
(a **source-pointer refresh only** — no field, action string, or shape change); the frozen storage
artifacts named as frozen; the historical DEC-11 quotation retained verbatim with a reading note.
IC-001 (2 lines), IC-007 (5 lines), IC-008 (2 lines): naming reconciliations only.

---

## 5. Locked invariant change record

**Canonical Overview, Part 2, locked invariant #7.**

| | Text |
|---|---|
| **Superseded (retained in the document for audit)** | *"**The Gateway is the boundary** — frontend → Gateway, never directly to DB/auth/router."* |
| **Ratified replacement** | *"**The authenticated public edge is the boundary.** Client traffic reaches only explicitly approved route-owning public edges. Internal service APIs, routers, audit-ingest APIs, database transports, and databases are never direct client ingress."* |
| **Changed by** | Explicit human architecture decision from **Dan**, **D-45**, 2026-08-11 |

**The supersession is recorded, not silent.** Three independent places carry it:

1. a **✅ RATIFIED banner** at the head of the Canonical Overview (replacing the prior ⚠️ DRIFT FLAG),
   with a three-row table showing superseded text beside ratified replacement — for invariant #7,
   the Part 1 *"One doorway only: the API Gateway"* framing, and **D4**;
2. **invariant #7 itself**, which quotes its own superseded text inline and names the decision, date
   and author;
3. the **Architecture Decision Register**'s D-45 entry, under an explicit
   *"Locked-invariant change record"* bullet.

**D4** ("build the API Gateway next") is likewise superseded for the MVP: its original text is
retained verbatim in Part 3 under a ⚠️ SUPERSEDED marker, and the decision-log row reads
`⊘ Superseded by D-45`. The Overview version moved **v2.2 → v2.3**.

---

## 6. Architecture decision record

| Artifact | Path |
|---|---|
| **The ADR** | `docs/D-45-Gateway-Free-Public-Edge-Architecture.md` **(new)** |
| Register row | `docs/Architecture-Decision-Register.md` — D-45 row in the Register table |
| Register detail | `docs/Architecture-Decision-Register.md` — `### D-45 — Gateway-Free Controlled Local MVP Ingress Architecture` |

The ADR carries all four sections the instruction §9 requires — **Decision**, **Rationale**,
**Accepted consequence**, **Deferred / separately governed** — plus the topology diagram, the
eight-point definition, the closed edge set, the ratified security invariants, the locked-invariant
change record, the frozen residuals, the frontend integration contract, and the non-overclaim block.

**Accepted consequence, recorded rather than buried:** *the public Startup edge is permitted, for the
Controlled Local MVP, to hold and use tenant database routing/credential capability, subject to the
already-tested tenant-isolation controls; the Workspace edge is narrowed to the minimum
membership-read capability.* The ADR states plainly that under the Gateway topology the
internet-facing process was structurally driver-free and credential-free, names the five compensating
controls, and calls it a deliberate accepted trade.

The register also records **D-37 as amended in part by D-45**: its §5 client-boundary *prohibition*
survives in full and is only **renamed** ("Gateway-only data access" → "approved-public-edge-only
data access").

---

## 7. Consistency-sweep results

The §10 pattern list — `API Gateway`, `api_gateway`, `Gateway is the boundary`,
`sole approved ingress`, `sole served ingress`, `gateway-only ingress`,
`only through the API Gateway`, `No alternate flow is permitted`, `Gateway-owned`,
`Gateway is the emitter` — swept case-insensitively over every tracked `*.md`, `*.sql`, `*.toml`,
`*.json`, `*.yml`, `*.ps1`.

**Result: 354 matching lines across 74 files. Every one classified. Zero `STALE — MUST FIX`.**

| Classification | Lines | Where, and why it is correct |
|---|---:|---|
| **CURRENT AND CORRECT** | 118 | The amended contracts' D-45 amendment notes and supersession trails; the Canonical Overview / Action Tracker / PRD Index / `CLAUDE.md` ratification banners and superseded-text-beside-replacement rows; the register's D-45 entry; `docs/runbooks/gateway_free_mvp_topology.md` (its subject **is** the removal); `pyproject.toml`, the CI workflow and `start-sp2-local.ps1` comments that record what was removed and why; the retired-port census that must name 8820 in order to refuse it. |
| **HISTORICAL** | 165 | `docs/reports/**` (the two removal result reports), `docs/handover/**`, `docs/PROJECT-HANDOVER-*`, `docs/Phase-1-*`, prior decision records `docs/D-33*` / `docs/D-33-E1` / `docs/D-37`, the `docs/d15/` and `docs/auth/` wire specs, `docs/reports/mypy/`, plus completed evidence records `docs/runtime/b5_blk6_closure_evidence_matrix.md` and `docs/runtime/dbr_ar_2_production_activation_evidence.md`. **Instruction §6: not rewritten.** Where an active document points at them, the pointer is labelled. |
| **HISTORICAL — WITHDRAWN, banner-flagged** | 42 | Twelve runbooks/specs whose harness or subject was deleted: `infrastructure/runbooks/{gateway_edge_v1_serve, smoke_c_integrated_live_proof, import_copy_live_proof, controlled_served_write_rehearsal, clm_acme_dataplane_witness, clm_2day_stage_b_rehearsal, b5_blk6_portal_binding_live_proof, dbr_ar_2_durable_routing_audit}.md`, `docs/acceptance/SMOKE-C-SPEC-01.md`, `docs/infrastructure/clm_dataplane_evidence_template.md`, `docs/runbooks/b5_service_startup_order.md`, `infrastructure/runbooks/README.md`. Each carries a ⛔/⚠️ withdrawal banner; **no evidence may be recorded against them**. |
| **FROZEN DDL / SECRET COMPATIBILITY** | 20 | `infrastructure/db/control/012_*.sql` + `013_*.sql` (untouched, blob pins green); `infrastructure/db/tenant/006_ownership.sql`, `007_links.sql`; `infrastructure/runbooks/aw1_gateway_audit_writer.md`; `infrastructure/runbooks/gateway_operational_audit_live_proof.md`; the `source_service = 'api_gateway'` producer constant and `control_gateway_audit` naming wherever an authoritative document must reference them. **Every such reference now says so explicitly.** |
| **FROZEN — byte-pinned B5 production-gate documents** | 8 | `docs/runtime/{b5_production_runtime_activation_gate, b5_activation_blockers, b5_runtime_readiness_matrix, b5_activation_evidence_template}.md`. **Deliberately not amended — see §8.** |
| **UNRELATED** | 1 | **IC-006 — AI Gateway Contract.** A different, deferred component (D-02). It carries **zero** matches on this pattern list; the one register/contract cross-reference to it is retained and is now explicitly annotated in IC-010 §U and Canonical Overview Part 4B-C as *not* the removed request-ingress component. |
| **STALE — MUST FIX** | **0** | — |

**Twelve authoritative documents were found STALE mid-sweep and fixed**, each a naming
reconciliation with no rule relaxed: `docs/Backend-Implementation-Roadmap.md`,
`docs/Coding-Standards.md`, `docs/Contract-Gap-Analysis.md`,
`docs/infrastructure/b3_cloud_portable_iac_rollout.md`,
`docs/runtime/b6_provisioning_audit_sink.md`,
`docs/runtime/b6_provisioning_audit_evidence_template.md`,
`docs/runtime/b7_provisioning_audit_blockers.md`,
`docs/runtime/b5_blk8_rollback_evidence_template.md`,
`docs/runtime/dbr_ar_2_durable_routing_audit_contract.md` (6 clauses),
`infrastructure/iac/README.md`, `infrastructure/runbooks/b3_nonprod_rollout.md`, and
`docs/runbooks/b5_service_startup_order.md` (whose banner asserted, as current fact, that the Gateway
*"has an inbound HTTP edge, and it is the only externally reachable surface"* — true when written,
false now).

### Naming-cleanup conformance (§5)

Active architecture text uses **authenticated public edge · public Startup edge · public Workspace
edge · shared public-boundary security kernel · route-owning service · internal edge**. The forbidden
vocabulary — **MVP Gateway · thin Gateway · lightweight Gateway · BFF · proxy layer** — appears
**nowhere** except where IC-010 §A.2 and the D-45 ADR *prohibit* it by name. A repository-wide check
for those five terms returns matches only inside those two prohibitions.

---

## 8. Historical / frozen residual classifications

### 8.1 Frozen DDL / SecretRef (instruction §7 — untouched by mandate)

| Residual | Location | Statement now carried in the authoritative documents |
|---|---|---|
| `CHECK (source_service = 'api_gateway')` | `infrastructure/db/control/012_gateway_operational_audit.sql` | IC-010 header + §D-43 section; IC-002 class 3 |
| DDL 013 append-only triggers | `infrastructure/db/control/013_*.sql` | same |
| `control_gateway_audit` table and the Python named for it | `control_plane/**` | IC-010 header; IC-002 class 3 |
| SecretRef `control/gateway-audit-writer-dsn` | AW-1 runbook, launcher, env template | IC-010 header; D-45 §7 |

Each authoritative home now states, in the instruction's own words:

> The active runtime Gateway component has been removed. Gateway-named audit storage artifacts remain
> temporarily as frozen compatibility artifacts pending a separately authorized DDL/SecretRef
> migration.

…and adds explicitly that **those names are not evidence that an API Gateway runtime exists**.
**DDL blob pins verified green** (`test_b7c1_control_audit_ddl_blob_pins.py`, 14 passed) — no DDL
file was read into a database, edited, or applied.

### 8.2 The byte-pinned B5 production-gate documents — the residual I chose not to close

`docs/runtime/b5_production_runtime_activation_gate.md` still contains, among five matches:

```text
API Gateway remains the sole ingress (IC-010 §I)
Database Router cannot prove one active tenant · API Gateway not sole ingress · …
```

Three sibling documents (`b5_activation_blockers.md`, `b5_runtime_readiness_matrix.md`,
`b5_activation_evidence_template.md`) carry one match each. **All four are pinned SHA-1-for-SHA-1**
by `_B5_GATE_BLOBS` in `backend/tests/architecture/test_dbr_ar_2e_activation_evidence_boundaries.py`.

**Why I did not amend them — three independent reasons, any one sufficient:**

1. **Out of authority.** The guard's own comment records that re-stamping those pins *"needed
   explicit authorization rather than being a mechanical edit."* No such authorization exists here.
2. **Out of scope.** These govern **production** activation. Instruction §9 is explicit: *"Do not
   describe the Controlled Local MVP decision as production approval."* Editing the production gate
   under a Controlled-Local-MVP decision would do exactly that.
3. **Fail-safe as they stand.** The criterion is **unsatisfiable by construction** on this topology,
   so the production gate stays **shut**. Leaving it makes production harder to reach, never easier.
   Amending it would be the only change that could relax a production gate — which is the one thing
   this task must not do.

**This is the load-bearing reason the verdict reads PASS WITH FROZEN RESIDUALS rather than PASS.**
Reconciling those four documents is listed in §12 as a separately governed item.

### 8.3 IC-010's file name

`contracts/IC-010-API-Gateway-Contract.md` is **deliberately retained** while the document's title
becomes *Public Edge Ingress Contract*. Eight documents and five architecture guards reference that
exact path; renaming it is cosmetic churn with real breakage risk and no governance value. The
contract's first block records the retention and the former title, and the guard now asserts **both**
the new title and the presence of the "formerly" note — so the supersession trail is machine-pinned.
A file rename is listed in §12.

---

## 9. Tests and gates run — exact results

| Gate | Command | Result | Exit |
|---|---|---|---|
| architecture suite | `pytest tests/architecture -q` | **966 passed** *(baseline 965; +1 = the new IC-011 non-vacuity companion)* | 0 |
| full suite | `pytest -q` | **1789 passed**, 0 failed *(baseline 1788)* | 0 |
| traceability / governance | included above (`test_traceability.py`, all contract text-drift guards) | passed | 0 |
| contract pins | `test_ic010_response_composition_contract.py` | **42 passed** | 0 |
| IC-011 hosted-rollback pins | `test_b5_blk8c_hosted_rollback_contract_boundaries.py` | **21 passed** *(20 + the new companion)* | 0 |
| Gateway-free architecture tests | `pytest tests/gateway_free -q` | **83 passed** | 0 |
| DDL blob pins | `test_b7c1_control_audit_ddl_blob_pins.py` | **14 passed** | 0 |
| imports | `lint-imports` | **4 kept, 0 broken** | 0 |
| lint | `ruff check .` | All checks passed | 0 |
| format | `ruff format --check .` | 345 files already formatted | 0 |
| types | `mypy .` (strict) | no issues in **344** source files | 0 |
| secrets | `gitleaks detect --log-opts 97769ddb..HEAD` | **no leaks found**, 1 commit scanned | 0 |

**Secret-scan positive control:** the same scanner over the full working tree reports **4 findings**,
all inside the git-ignored `backend/.venv` third-party packages — so the clean commit-range result is
a real result, not a silent no-op.

### 9.1 Guards updated — re-encoded, never weakened

Instruction §11: *"Where a guard encoded the old architecture decision, update it to encode the
ratified Gateway-free decision"* and *"Do not weaken a guard merely because an old Gateway-specific
contract changed."* Six guards were touched. **No detector was removed, no non-vacuity probe was
dropped, and two guards got strictly stronger.**

| Guard | What changed | Weakened? |
|---|---|---|
| `test_ic010_response_composition_contract.py` | §Q heading; the contract title anchor **plus a new assertion that the "formerly" note exists**; the §V composer anchors (gateway-owned → route-owner-owned); the 6C-A emitter anchor; the four-class separation anchor; `_J_HISTORIC_EMIT`; §Q's "dispatched to" → "belongs to" **plus a new "a route family has exactly one owner" anchor**. | **No — net stronger** (+2 anchors) |
| `test_audit_class_homes.py` | The two IC-002/IC-005 emitter anchors retargeted. The forbidden regex `_GATEWAY_ROUTER_EDGE_RE` **keeps every old `gateway` alternative and gains `public edge` / `public-edge` / `route-owning public edge`**, with **three new planted probes** proving the D-45 vocabulary trips the same detector. | **No — net stronger.** Without this, a rename would have silently disarmed the "no component may claim the router-edge subclass" prohibition. |
| `test_b5_blk8c_hosted_rollback_contract_boundaries.py` | **Rewritten.** The old test asserted the contract text contained `"api gateway"` **and** `"sole served ingress"` — both of which **still occur inside the amendment note that records the change**, so it would have kept passing while asserting nothing. Replaced by: the ratified rule required in **both** the contract and the runbook, **all five STOP conditions in both**, the isolation rule unchanged, **and a new detector that fails if the superseded component rule survives as an active requirement** — plus a new non-vacuity companion with five planted mutations. | **No — this closed a vacuous pass at a gate boundary** |
| `test_b5_blk5_r1_auth_memberships_contract_boundaries.py` | one anchor: "the gateway mints and exchanges no token" → "the public edge mints…" | No |
| `test_clm_2day_stage_a_contract_boundaries.py` | four anchors retargeted (mint, emitter, taxonomy-closure, comment) | No |
| `test_deployment_composition_root_boundaries.py` | `api_gateway ↛ deployment` dropped from the pinned §4 table **with an inline comment recording that the prohibition lost its subject and was not relaxed**; the §3 authorized set and the forward-forbidden complement are untouched | No |

### 9.2 Four statements the rewrite dropped, and restored

Mid-verification the guards caught four governance statements the IC-010 rewrite had silently
dropped — each still carried verbatim by IC-002, IC-005 or the register, so dropping it from IC-010
alone would have created a three-way inconsistency. All four were restored:

1. §J's B5-BLK-6C-A **runtime-status** sentence;
2. §Q's *"not runtime-bound by B5-BLK-6B and is not implemented by B5-BLK-6C-A"*;
3. §V.5's *"create a northbound HTTP ingress"* non-overclaim (restated for the closed edge set);
4. the CLM section's Stage-B sequencing statement and the "existing Tenant Operations **category**"
   naming.

**This is the value of the text-drift guards, and it is worth stating plainly: the guards, not the
review, caught all four.**

### 9.3 An independent anti-silent-drop control

Because the retargeting renames the actor everywhere, exact-string diffing proves nothing. A separate
script (`scratchpad/coverage.py`) extracted every **MUST / MUST NOT / prohibition / never** sentence
from each contract at `97769ddb`, normalised the rename vocabulary away, and scored each old sentence
against the best-matching new sentence by distinctive-token overlap — so a pure rename scores ~1.0
and a **dropped rule** scores near 0.

| Contract | Old normative sentences | New | Below threshold |
|---|---:|---:|---:|
| IC-010 | 110 | 122 | 6 — all verified by hand as sentence-split artifacts of retained rules |
| IC-009 | 42 | 47 | 1 — verified retained |
| IC-005 | 51 | 53 | **0** |
| IC-011 | 20 | 21 | **0** |
| IC-012 | 67 | 67 | **0** |
| IC-002 | 107 | 107 | **0** |

Two genuine tightenings came out of that pass and were applied: §R's directory-authentication
requirement now explicitly binds any future edge and is *not* relaxed by the family being edge-dark,
and §V.2's `RouteOutcome` bullet re-states *"a routing result carries no body."*

---

## 10. Proof no runtime / DDL / SecretRef / live change occurred

| Prohibited act | Performed? | Evidence |
|---|---|---|
| edit or apply DDL | ❌ | zero `*.sql` and zero `infrastructure/db/**` paths in `git status`; DDL blob pins green (14 passed) |
| change a SecretRef / credential | ❌ | zero `infrastructure/env/**`, `*.env*`, `*.profile.json` paths changed; the AW-1 reference is *named* and deliberately unchanged |
| change Keycloak / create a PKCE session | ❌ | no OIDC/JWKS call; authentication is a test double throughout |
| connect to standing PostgreSQL 5540–5543 | ❌ | no psycopg connection opened; every `requires_pg` harness is excluded from the suite by `addopts` and none was run |
| change backend production source | ❌ | every changed `backend/` path is under `backend/tests/architecture/` |
| start / stop / restart a standing service · run the governed launcher | ❌ | the launcher was neither edited nor executed this task |
| bind a fixed standing port | ❌ | the only sockets bound were ephemeral loopback (`port=0`) opened and closed by tests |
| modify standing memberships / roles / grants | ❌ | no database contact of any kind |
| touch the frontend repository | ❌ | `frontend/` does not exist here; §Y records the requirement and changes nothing |

**Files changed: 35 — 9 contracts, 16 docs/runbooks/governance records, 6 architecture guards,
1 new ADR, 1 new result document, `CLAUDE.md` and 2 infrastructure READMEs. Zero production modules.
Zero DDL. Zero configuration. Zero SecretRefs.**

---

## 11. Proof `main` remains untouched

| Requirement | State |
|---|---|
| `main` unchanged | ✅ `cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f` — identical to the pre-task reading |
| `git merge-base main HEAD` | ✅ `cdb46fc9…` — the same SHA; the base did not move |
| commits are local only | ✅ no `git push` was run; the branch has no remote-tracking ref |
| NO PR opened | ✅ no `gh` invocation, no GitHub API write |
| NOT merged | ✅ `git diff main..HEAD` is this branch only |
| working tree | ✅ clean after commit |

---

## 12. Remaining separately governed items

1. **The four byte-pinned B5 production-gate documents** (§8.2) — reconciling
   `"API Gateway remains the sole ingress"` requires re-stamping four blob pins and is a **production**
   governance act. Until then the production gate stays shut, which is the safe posture.
2. **DDL 012/013 audit-naming migration** — widen the `source_service` CHECK so the last frozen
   residual can retire; migrate `control_gateway_audit` and the AW-1 SecretRef name with it.
3. **Re-author the live proofs the removal cost** — five live-PG harnesses deleted, two refusing.
   There is **no live tenant-data-plane witness and no integrated Smoke C** for the Gateway-free
   topology, and **B5-BLK-4 has lost its harness**. Tracked as Action Tracker **#22**.
4. **Re-run the retargeted DDL-012 live proof** (`test_pg_gateway_audit_durable.py`) under separate
   live authorization — currently UNVERIFIED against the new emitter. Action Tracker **#23**.
5. **Frontend cutover to the two public-edge origins** (IC-010 §Y) — separate repository, separate
   authorization. **B5-BLK-5 remains OPEN.** Action Tracker **#21**.
6. **Rename `IC-010-API-Gateway-Contract.md`** — cosmetic housekeeping across 8 documents and 5
   guards (§8.3).
7. **A pre-existing runtime-status claim, out of scope, reported not fixed.** IC-002, IC-005 and
   IC-010 all still say the `workspace_memberships_read` event *"is not yet emitted by the current
   runtime."* That claim predates this task, is identical in all three homes, and is a
   B5-BLK-6C-B **runtime-status** question rather than a Gateway-naming one. Changing it would be an
   unrequested substantive amendment, so I preserved it verbatim and am reporting it here instead.
8. **Any future production architecture decision** — D-45 decides the Controlled Local MVP only.

---

## 13. The ratified Controlled Local MVP architecture — exact statement

```text
Frontend
   ├──> Public Startup Edge          (owned by database_router)
   │       ↓  shared authenticated public boundary
   │       ↓  Auth Router
   │       ↓  Database Router / tenant operations
   │       ↓  one physical tenant database
   │
   └──> Public Workspace Edge        (owned by control_plane)
           ↓  shared authenticated public boundary
           ↓  Auth Router
           ↓  narrow membership-read capability
           ↓  Control DB
```

**There is no API Gateway component in the active MVP architecture.** The architectural boundary is
**an approved authenticated public edge owned by the service that owns the public route.** An
approved public edge must: use the shared public-boundary security kernel; authenticate through the
Auth Router contract; derive actor and tenant authority only from authenticated trusted state; serve
only the route family owned by its service; not operate as a generic proxy, BFF, or cross-service
dispatcher; enforce fail-closed request validation before business/database work; emit the required
audit evidence for its own route; and preserve one request → one authenticated active tenant → one
physical tenant database for tenant-scoped operations.

**Every security invariant is ratified, not weakened** — they are now properties of the approved
public edges and route-owning services: Authentication ≠ Routing ≠ Authorization ≠ DB access; one
request → one active tenant → one database; the client never authoritatively chooses
`target_tenant_ref` or `actor_ref`; tenant identity from authenticated trusted state; fail-closed
parsing and validation; request-size bounds; exact-origin bounded CORS; bounded non-authoritative
correlation identifiers; typed contract-controlled public DTOs; required audit evidence before
successful hand-back; database/service containment and service independence; the Workspace edge
narrowed to the minimum membership-read capability; and **no generic replacement Gateway under
another name**.

---

## 14. Mandatory final posture

```text
The official Controlled Local MVP architecture is Gateway-free.
The authenticated public edge is the client security/request boundary.
The Startup and Workspace public edges are the only approved MVP public business-route ingress points.
Internal service edges remain non-public.
The API Gateway component is not part of the active MVP architecture.

No push is authorized by this instruction.
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

> **A ratified design is not a merge authorization, and it is not a production approval.** The
> official documents now describe the Gateway-free architecture that Dan chose, and the code on this
> branch no longer contradicts a Final contract — that was the single named blocker, and it is
> closed. What remains is a merge decision that only Dan may make, plus the separately governed items
> in §12.

```text
GATEWAY-FREE ARCHITECTURE CONTRACT RATIFICATION PASS WITH FROZEN RESIDUALS
```
