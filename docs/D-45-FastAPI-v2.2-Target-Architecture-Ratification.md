# D-45 — FastAPI Implementation Proposal v2.2 Target-Architecture Ratification

**Phase:** Architecture Planning (Phase 0) · **Type:** Architecture decision pack (analysis + governance only, no implementation)
**Opened by:** `Claude_Phase_0_Architecture_Ratification_GPT.md` (Phase 0 — Architecture Ratification & Contract Reconciliation)
**Source proposal:** `SnackPortal2_FastAPI_Implementation_Proposal_v2.2_GPT.md`
**Branch:** `phase/00-architecture-ratification` · **Merge authority:** Dan only
RFC-2119 keywords **MUST / MUST NOT / SHOULD / MAY** are used normatively.

> **Contract-first, no positive capability.** This pack ratifies a **target architecture** and opens the two contracts that target requires. It adds no route, no DTO, no error code, no audit class, no DDL, no permission, and no cross-tenant capability. **No runtime code is changed by D-45.** The API Gateway runtime is **retained in full**. Production remains NOT READY / DO-NOT-ACTIVATE.

---

## 1. Why this pack exists

The repository is contract-governed and already carries an accepted, verified backend: six service packages, nine FastAPI/Uvicorn HTTP edges, a `deployment` cross-service composition root, four import-linter contracts, and roughly a thousand architecture guards. FastAPI Implementation Proposal v2.2 describes a target that differs from it in naming, in topology, and in several security-relevant serving choices.

Resolving that divergence inside an implementation phase would mean discovering governance conflicts while editing runtime code. The governing rule is instead:

```
Contracts / Architecture  must agree with  Implementation Direction  before  Implementation Migration
```

D-45 is that agreement. Every ratification item below is stated as a **decision**, its **contract vehicle**, and the **phase** in which runtime work (if any) may follow.

---

## 2. What is NOT reopened

D-45 reopens no frozen invariant. The following remain in force verbatim and are load-bearing for every item below:

- **Physical multi-database isolation** — one Control DB plus one physically independent database per tenant (B-0; IC-002).
- **One Request to one Active Tenant to one Physical Database** (D-04/D-07/D-30; IC-005; IC-010 §H/§O). Never a silent Control-DB fallback; ambiguous or missing routing **fails closed**.
- **Database resolution is the Database Router's exclusive responsibility** (IC-010 §X). No other component selects a database, and no client-controlled value is ever a database selector.
- **The signed tenant claim is authoritative; carriers are match-or-reject** (D-06/D-33; IC-005). Cookies, query strings, portal state, workspace state and local storage are never tenant carriers.
- **Authentication is separated from tenant routing** (D-01 A+B; IC-005).
- **Ownership is reference-only and never routes or authorizes** (IC-008).
- **Reference-only audit representation** — no names, emails, PII, payloads, tokens or secrets in any context, audit or lineage record (D-34-R2).
- **Anti-vendor-lock-in** — cloud-portable PostgreSQL only; no vendor business logic.
- **Service independence** — no service package imports another; `shared` is a dependency leaf; `deployment` is the top of the DAG (IC-012).

The v2.2 four-way separation (Authentication, then Access Control, then Tenant Routing, then Database Access — each distinct from the others) is **adopted as-is** and is consistent with all of the above.

---

## 3. Ratification items

### R-1 — Single FastAPI ingress service; the BFF is the Gateway's successor role, not a second component

**Decision.** Ratify **exactly one approved ingress** into SnackPortal2, realised as a **FastAPI application inside this repository** and fronted by nothing else during development. The ingress role is renamed and re-scoped from *API Gateway* to **BFF (Backend-for-Frontend)** and gains the v2.2 frontend-orientation responsibilities (frontend-facing operations, orchestration across services, response aggregation, permission-aware UI responses, hiding backend topology). It is the **evolution of the existing `api_gateway` service**, not an additional hop in front of it.

**Why not deletion.** The v2.2 §53 prohibition is on introducing a *dedicated custom API Gateway product* or an *Enterprise Security Edge* as a development dependency. This repository has neither: `api_gateway` is a FastAPI service. What it actually is, is a **privilege boundary** — the single northbound surface, with the other eight edges bound to loopback and only it reachable by a frontend. Removing it without a replacement boundary would expose the internal edges (including the tenant-startup and dispatch surfaces) directly to the public tier. The ingress is therefore **preserved and renamed**, never removed.

**What the BFF inherits unchanged.** Every IC-010 enforcement rule carries over verbatim: carrier match-or-reject (§E), tenant-context derivation from the signed claim only (§F), `RequestContext` constructed exclusively from `AuthContext` (§G/§T), endpoint dispatch but never database resolution (§X), internal-surface protection (§R), fail-closed empty-body denials (§L), reference-only audit emission (§J), and the isolation contract (§K).

**What the BFF is additionally forbidden.** Per v2.2 §9 the BFF **MUST NOT** duplicate authentication logic, access-control rules, database-routing rules, or any domain rule. It orchestrates; it does not decide.

**Vehicle:** **IC-013 — BFF & Service Ingress Contract** (new, Draft / Proposed, IC-013-DRAFT-1) plus an insert-only IC-010 amendment recording the conditional supersession.
**Runtime phase:** the rename and re-scope are a later migration step. **Not Phase 0. Not Phase 1.**

### R-2 — Access Control is a distinct service with its own contract

**Decision.** Ratify a **FastAPI Access Control Service**, independently bootable, owning role, permission, membership-derived entitlement, ownership-derived permission, workspace-scoped capability, requested-action, AI-agent skill and AI-tool-entitlement decisions, returning an allow or a deny.

**Boundary that must not blur.** IC-005 retains **authentication** and **tenant-scope authorization** (the D-04 one-active-tenant membership law), because tenant-scope authorization is enforced at routing time and is part of the isolation mechanism. Access Control **MUST NOT** become the tenant-isolation mechanism, **MUST NOT** select or influence a database, and **MUST NOT** re-derive the active tenant. A deny from Access Control never widens what the signed claim permits, and an allow never widens it either.

**Gap this closes.** IC-005 delegates per-feature authorization to "each feature contract". No contract has ever owned the cross-cutting permission model. IC-014 is that home.

**Vehicle:** **IC-014 — Access Control Contract** (new, Draft / Proposed, IC-014-DRAFT-1) plus an insert-only IC-005 amendment cross-referencing it.
**Runtime phase:** Phase 3 per the phased branching instructions.

### R-3 — OpenAPI is ratified by surface class, not globally

**Decision.** Adopt v2.2 §38 (FastAPI-generated OpenAPI is the API documentation; no separately maintained REST catalogue) **subject to surface class**:

- **Internal edges** (every edge except the ingress) keep `openapi_url=None`, `docs_url=None` and `redoc_url=None`. These are closed, allowlisted, loopback-bound surfaces; publishing a machine-readable route and shape catalogue on them is precisely what IC-010 §R Internal-Surface Protection forbids. **This is not negotiable by convenience.**
- **The ingress (BFF)** MAY expose OpenAPI and interactive docs **in a development portability profile only** — never in the hosted or production profile, and never when the profile is not explicitly a development one.

**Consequence.** The v2.2 intent — no hand-maintained REST specification — is satisfied: schemas are generated from the code that serves them, and the internal topology is not published.

**Vehicle:** IC-013 (ingress rule) plus an insert-only IC-010 amendment restating §R unchanged for internal edges.

### R-4 — Pydantic is adopted forward, not retrofitted

**Decision.** Adopt v2.2 §15 and §16: FastAPI routes plus Pydantic models directly provide request validation, response schemas and OpenAPI, with **no** parallel custom request/response DTO framework. This applies to **new** services and **new** routes.

**Existing edges are exempt until separately migrated.** The nine existing edges deliberately (a) collapse request-validation failures to a fixed status with an **empty body**, because the FastAPI default validation report discloses the expected request shape, and (b) hand-serialize responses with `json.dumps` so the wire bytes stay byte-identical to the pre-FastAPI envelopes those edges are pinned against. Retrofitting a `response_model` onto them would change bytes on the wire and break those pins. Each such edge migrates only under its own authorized PRD, if at all.

**Dependency note.** `pydantic` is not currently a declared runtime dependency, and the declared dependency list is pinned exactly by an architecture guard. The phase that first uses Pydantic directly MUST add it to the `[project] dependencies` list and update that guard in the same authorized change.

**Vehicle:** the IC-013 API-shape rules; no amendment to any Final contract required.

### R-5 — `main.py` keeps its composition-seam meaning; the FastAPI app stays in the adapter zone

**Decision.** v2.2 §6 and §7 ask for one obvious startup file per service. The repository already satisfies the **substance** — every service composes itself, every edge has a no-argument ASGI application factory, and every edge boots independently on its own port with one worker and one operating-system process. The **naming** differs, and the difference is load-bearing:

- `<service>/main.py` is the service-local **composition seam** (`build_*_from_env`), a meaning fixed by IC-012 §1.
- The FastAPI application lives in `<service>/adapters/providers/http_*.py` as `create_app_from_env`, because the web-framework import belongs inside the `adapters/providers` containment zone that the hexagonal governance depends on.

Ratify: **`main.py` is the composition seam and MUST NOT become the module that constructs the FastAPI application object.** The v2.2 one-command-per-service convenience is satisfied instead by adding, in a later phase, an `if __name__ == "__main__":` entry to each `<service>/main.py` that starts that service's own factory through the single sanctioned ASGI runtime — so `python -m <service>.main` boots the service — with `uvicorn <module>:create_app_from_env --factory` remaining the canonical operator command.

**One service MAY own more than one ASGI edge.** v2.2 assumes one app per service; the repository has nine edges across six services (`control_plane` owns four, `database_router` owns two). Ratify the many-edges-per-service shape explicitly; it does not weaken independent bootability, which is a property of the **edge**, not of the package.

**Vehicle:** the IC-013 runtime-shape rules. **IC-012 is not amended** — no new cross-service composition module is created, and the §5.1 amendment gate remains the trigger for any future one.

### R-6 — Reload supervision is not ratified for any governed startup path

**Decision.** v2.2 §8 scopes development reload to developer convenience. Ratify exactly that scope and no more: the reload flag and its environment-variable equivalent **MUST NOT** appear in any documented startup command, in the governed launcher, in continuous integration, in any rehearsal harness, or in any hosted profile. A reload supervisor is an additional process outside the authorized one-worker, one-process model, and it re-enables a code-watching parent that the process census does not account for.

**Consequence.** The existing guards that forbid the reload flag in documented commands and in the launcher template are **correct as they stand and are not relaxed**. There is no conflict to resolve — only a scope to state.

**Vehicle:** the IC-013 runtime-shape rules; no guard change.

### R-7 — Package layout: **Option A** (retain the flat layout)

**Decision.** Retain the existing flat top-level package layout and implement the v2.2 behaviour within it. New services are added as **new top-level packages** alongside the existing six. Treat the v2.2 §18 `src/snackportal2/` tree as an organisational recommendation that is **already satisfied in substance**: `shared/` exists as a technical dependency leaf and each service is its own package.

**Why not a staged or full layout migration.** The flat layout is not incidental — it is enumerated in the setuptools package list, in the import-linter root packages, in all four import-linter contracts, in the architecture scanner's service census, in the normative module placement of IC-012 §16, in every documented startup command target, and in the governed launcher's module map. A `src/` migration is a repository-wide rename of every one of those pins with **no architectural gain**: it changes no boundary, no invariant, and no dependency direction. The risk is concentrated in exactly the artifacts that enforce isolation.

**Vehicle:** the IC-013 layout rule. No change to `pyproject.toml` in Phase 0.

### R-8 — Enterprise Security Edge stays a deployment concern

**Decision.** Ratify v2.2 §51: no off-the-shelf enterprise security product is a development dependency. This is already the built state — the ingress is a FastAPI service and TLS termination is a reverse-proxy and deployment concern. Any later enterprise product sits **in front of** the ingress and **MUST NOT** absorb the SnackPortal2 tenant, database-routing, ownership, or AI-authorization decisions.

**Vehicle:** the IC-013 deployment boundary; no change to any Final contract.

### R-9 — Target service census

Ratify the following as the target service set, with governing contracts. "New package" means the phase that creates it must also extend the setuptools package list, the import-linter root packages and independence contract, and the architecture scanner's service census in the same authorized change.

| Target service | Repository status | Governing contract | Package action |
|---|---|---|---|
| BFF (ingress) | exists as `api_gateway` | IC-013 (new), inheriting IC-010 | rename and re-scope, later phase |
| Authentication | exists as `auth_router` | IC-005 | none |
| Access Control | **absent** | IC-014 (new) | new package |
| Control Plane | exists | IC-001, IC-002 | none |
| Database Router | exists | IC-005, IC-002 | none |
| Import | exists | IC-003 | none |
| Lineage | exists | IC-004 | none |
| Startup | **absent** | IC-002, IC-008 | new package |
| Investor | **absent** | IC-002, IC-008; a Global Investor Contract is a known gap | new package |
| Deal | **absent** | IC-008; IC-007 (Draft) | new package |
| Sharing / Introduction | **absent** | IC-007 (Draft — must be Final first) | new package |
| Contacts | **absent** | **no contract exists** — a contract gap | new package |
| AI Agent | **absent** | IC-006 (Draft, deferred under D-02) | new package |
| Audit | in-service today, Control-DB homed | the IC-001/IC-002/IC-003/IC-010 audit taxonomy | decide at its phase |

Two of these are blocked on governance, not on code: **Sharing** cannot ship while IC-007 is Draft / Proposed, and **Contacts** has no contract at all. **AI Agent** remains deferred.

---

## 4. What D-45 explicitly does not authorize

- No runtime code change of any kind.
- No removal, rewrite, or relocation of the API Gateway runtime.
- No package move, rename, or creation.
- No import-linter configuration change.
- No new route, DTO, error code, permission, audit class, or DDL.
- No closure of any open blocker, and no change to the blocker census.
- No production, staging, standing-topology, database, identity-provider, or frontend change.

IC-013 and IC-014 are **authored-but-inert**: they become Final only after independent verification and explicit human merge, and neither grants a positive capability in this state.

---

## 5. Traceability

| Ratification item | Contract vehicle | Runtime phase |
|---|---|---|
| R-1 single FastAPI ingress / BFF role | IC-013 (new); IC-010 amendment | later migration phase |
| R-2 Access Control service | IC-014 (new); IC-005 amendment | Phase 3 |
| R-3 OpenAPI by surface class | IC-013; IC-010 amendment | Phase 1, ingress development profile |
| R-4 Pydantic forward-only | IC-013 | Phase 1 onward, new routes only |
| R-5 composition seam preserved | IC-013 | Phase 1, module entry points |
| R-6 reload unratified for governed paths | IC-013 | none |
| R-7 flat layout retained | IC-013 | none |
| R-8 enterprise edge deferred | IC-013 | Phase 10 |
| R-9 target service census | IC-013; IC-014; IC-007 (blocked); the Contacts contract gap | Phases 3 to 8 |
