# IC-013 — BFF Ingress Contract

**Status:** Draft / Proposed · **Revision:** IC-013-DRAFT-1 · **Phase:** Architecture Planning · **Type:** Contract-first specification (no implementation)
**Opened:** 2026-08-21 by **D-46** (Option A Gateway-Free Target Architecture Ratification), Phase 0.5 — Contract Reconciliation.
**Supersedes (jointly with IC-014):** **IC-010 — API Gateway Contract** (`Final` → `Superseded`).
**Authored fresh.** No text is cherry-picked from the abandoned `phase/00-architecture-ratification` branch. Where a rule is carried forward from IC-010 it is restated here in full, with the IC-010 section noted for traceability.

Requirement keywords **MUST / MUST NOT / SHOULD / MAY** are used in the RFC-2119 sense.

---

## §0 — What this contract is, and what it is not

This contract defines the **FastAPI BFF** — the single frontend-facing ingress of the Option A target architecture — and the **independently-bootable service shape** every backend service adopts.

**The BFF is not a Gateway.** It is application-oriented frontend orchestration: it serves the frontend's use cases, composes the frontend's responses, and coordinates the services needed to do so. It is **not** a generic reverse proxy, **not** a routing gateway, **not** a compatibility shim, and **not** a renamed `api_gateway`.

**Prohibited names for this component:** *API Gateway*, *FastAPI Gateway*, *BFF Gateway*, *Service Gateway*, *Routing Gateway*, *Compatibility Gateway*. The word "gateway" MUST NOT appear in the BFF's package name, module names, route paths, configuration keys, or environment-variable prefixes.

**The distinction that makes this real, not cosmetic.** A gateway is *operation-agnostic*: it forwards whatever arrives at whatever path, and its surface grows by configuration. The BFF is *operation-enumerated*: every surface it exposes is a named frontend use case, declared in this contract's operation set (§16), backed by a Pydantic request/response model, and composed from typed service results. **A BFF surface that merely relays a downstream body is, by this definition, a gateway route and is forbidden (§19).** Adding a surface is a contract change, not a config change.

---

## §1 — Purpose

Define the **FastAPI BFF** as the **single frontend-facing ingress** into SnackPortal2 services: the one boundary at which frontend requests are authenticated, carrier-validated, given a `RequestContext`, authorized, routed to exactly one physical database, and turned into a contract-approved response.

*(Carries forward IC-010 §A. The substance — one governed public ingress, no client path around it — is preserved and unweakened; only the holder changes.)*

**Revised locked invariant #7** (D-46 §2): *The BFF is the boundary.* The frontend reaches backend services **only** through the BFF — never directly to a database, the Authentication Service, the Access Control Service, or the Database Router.

---

## §2 — Position in the target architecture

```text
Frontend
   ↓
FastAPI BFF                                   ← this contract
   ├── Authentication Service   (IC-005)      — who are you?
   ├── Access Control Service   (IC-014)      — what are you allowed to do?
   ├── Database Router          (IC-005/D-07) — which one physical database?
   ├── Control Plane            (IC-001/IC-002)
   ├── Startup / Investor / Deal / Contacts Services
   ├── Sharing (IC-007) · Import (IC-003) · Lineage (IC-004)
   ├── AI Agent Service         (IC-006)
   └── Audit Service
              ↓
      Control DB / Tenant DBs
```

The target runtime MUST contain **0 API Gateway runtime, 0 Gateway package, 0 Gateway compatibility layer, 0 Gateway launcher, 0 Gateway routes, 0 Gateway-specific configuration dependency, 0 Gateway service dependency.**

---

## §3 — BFF Responsibilities *(carries IC-010 §B)*

The BFF **MAY**:
- consume Authentication Service outputs (IC-005) — it does not itself authenticate;
- validate carriers under match-or-reject (§5);
- construct the canonical `RequestContext` from `AuthContext` **only** (§7);
- call the Access Control Service for an allow/deny decision (§4, IC-014);
- coordinate one or more backend services to fulfil **one enumerated frontend operation** (§16);
- compose contract-approved DTO responses from typed service results (§19);
- propagate correlation context to every service it calls;
- emit ingress-edge operational audit events (§10).

The BFF **MUST NOT**:
- select a database — by user preference, header, cookie, query-string, workspace, or **any** client-controlled value;
- re-derive the active tenant from anything other than the signed claim;
- make authorization decisions itself (it **asks** IC-014; it does not evaluate roles, permissions, ownership or residency);
- perform ownership decisions (IC-008: ownership is reference-only and never routes or authorizes);
- embed portal or presentation-layer business decisions (D-37);
- perform business logic of any kind;
- relay an arbitrary downstream response body (§19);
- expose an internal service surface to a client (§13).

Authority for authentication, authorization, routing, residency and ownership remains in the dedicated services, never in the BFF's discretion. **The BFF is an enforcement and composition boundary, not a decision-maker.**

---

## §4 — Request Flow Contract *(revises IC-010 §C — an Access Control stage is inserted)*

The single approved per-request flow is:

```text
Request
  → Authentication            (Authentication Service — IC-005)
  → Carrier Validation        (BFF — §5, match-or-reject)
  → RequestContext Creation   (BFF — §7, exclusively from AuthContext)
  → Access Control            (Access Control Service — IC-014, allow/deny)
  → Tenant Routing            (Database Router — exactly one physical database)
  → Service invocation
  → Response Composition      (BFF — §19)
```

**No alternate flow is permitted.** No stage may be skipped, reordered, or bypassed, and no path may reach a service or a database except through this flow.

**Normative ordering rules:**
1. **Carrier validation is pre-context and pre-routing.** A carrier mismatch is denied before any `RequestContext` exists, before classification, and before **any** Database Router or tenant-database contact.
2. **Access Control runs after `RequestContext` construction and before Tenant Routing.** It decides on references only. It MUST NOT select a database and MUST NOT re-derive the active tenant.
3. **Authentication is input, never routing logic** *(IC-010 §D)*. A valid token establishes *who* the principal is and *which tenant claim* it carries. **A valid token never, by itself, selects or changes the target database.**
4. **A denial at any stage terminates the flow** — no partial access, no fallback, no default tenant, no downgrade to a less-isolated outcome.

---

## §5 — Carrier Contract *(RE-HOMED from IC-010 §E — load-bearing)*

> *One of the four behaviours Phase 0 identified as living only inside the Gateway. Deleting the Gateway without this section would silently remove tenant-carrier enforcement.*

The BFF recognizes **exactly two** tenant carriers, both subordinate to the signed claim under match-or-reject:
- the **tenant subdomain** (host-based addressing); and
- the HTTP header **`X-Tenant-Id`** — the **only** recognized carrier header (case-insensitive).

All other headers are unrecognized as tenant carriers and MUST be ignored.

**Prohibited as routing authority** — MUST be stripped or ignored at the BFF and **never read by any backend component for any purpose**, including token issuance: **cookies, query-string parameters, portal state, workspace state, and client local storage.** None of these may carry tenant or workspace identity.

The BFF MUST pass any recognized carrier into the IC-005 carrier-match check and reject a mismatch with **403 `carrier_mismatch`**. The carrier is **match-or-reject only** and is **never authorization**; the signed tenant claim remains the sole routing authority.

A carrier-mismatch denial MUST emit the `CarrierMismatch` audit event (§10) and MUST NOT be handed back without its durable evidence record (audit-before-hand-back).

---

## §6 — Tenant Context Contract *(carries IC-010 §F)*

Per **D-33**, the BFF establishes the tenant context carried in the `RequestContext`.

- **Workspace is derived from the tenant context; the tenant context is never derived from workspace.** `workspace_type` (Tenant Workspace vs Control Workspace) is a presentation-layer label computed *from* the signed claim. It is never a routing input, never a database selector, and never an authority of its own.
- For a **tenantless CONTROL token accompanied by a recognized tenant carrier**, the carrier is ignored (claim-only) **and** the BFF MUST emit the `CarrierOnControlAnomaly` audit event (D-33-E1 Item 1; §10).

---

## §7 — Request Context Contract *(RE-HOMED from IC-010 §G + §T — load-bearing, D-33 §4.6 keystone)*

> *One of the four Gateway-only behaviours. This is the single rule that prevents a client from injecting a tenant.*

The BFF constructs the **canonical `RequestContext`** — the one structure the Access Control Service, the Database Router, audit and service invocation consume **without any additional tenant resolution**.

**Canonical fields:** `correlation_id`, `principal_ref`, `role`, `tenant_context` (the signed active-tenant claim, or *tenantless-CONTROL* for the Control Workspace), `workspace_type`.

**Normative rules:**
- **Constructed exclusively from `AuthContext`.** The BFF MUST construct the `RequestContext` **exclusively** from the Authentication Service's output. **No inbound tenant or workspace parameter** — header beyond the carrier-match check, cookie, query-string, path segment, request body, host, or portal/workspace/local-storage state — may set any context field or reach the Database Router. The **only** permitted use of a recognized carrier is feeding it into the IC-005 carrier-match check, which rejects on mismatch.
- **References only.** The `RequestContext` MUST NOT contain names, emails, or any PII/identity payload, and MUST NOT contain a token, secret, credential, DSN, or physical-database identifier. Identity is resolved at presentation time via the D-03 identity model, never carried in the context.
- **The Database Router never re-derives the tenant.** It binds exactly one database from the context's signed tenant claim.

**Testable criterion (inherited from D-33 §10 criterion 6, IC-010 §W):** an architecture test MUST prove the BFF constructs `RequestContext` only from `AuthContext`, and that no inbound tenant/workspace parameter reaches the router.

---

## §8 — Database Router Boundary *(carries IC-010 §H)*

`BFF → Database Router` is the **only approved routing boundary**.

- **The BFF never chooses a database.** It hands the `RequestContext` to the Database Router, which resolves exactly one physical database registry-authoritatively from the signed claim (D-07/D-30).
- **The Database Router never authenticates and never authorizes.** Authentication and authorization are complete before the router is reached; the router consumes the already-authenticated, already-authorized context only.
- **No component between or around the BFF and the router may introduce an alternative database-selection path.**
- The Database Router remains the **only** service permitted to open a tenant database.

---

## §9 — Portal Boundary *(carries IC-010 §I)*

Per **D-37**, the six portal classes — **Control · Master Agent · Tenant · Startup · Investor · AI (Reserved)** — and any future channel MUST access backend services **only through the BFF**.

**Explicitly prohibited:** direct database access (Control DB or any tenant DB); direct Supabase data access of any kind (RLS-as-authorization, PostgREST, Supabase data SDKs); portal-side routing; portal-side synchronization.

Portals **display, discover, and initiate**. They never determine database, tenant, authentication, authorization, ownership, routing, or residency. The Master Agent Portal's cross-tenant capabilities remain **IC-007-reserved** — the BFF grants no cross-tenant authority (§18).

---

## §10 — Audit Contract *(RE-HOMED from IC-010 §J — load-bearing)*

> *One of the four Gateway-only behaviours. The emitter identity changes; the classes, shapes and prohibitions do not.*

**The BFF is the sole emitter of ingress-edge operational audit.** The **Audit Service** is the durable sink; the durable home remains **Control-DB operational audit**.

**Denial / anomaly classes (exactly four — unchanged from IC-010 §J, none added, removed or renamed):**
`CarrierMismatch` · `CarrierOnControlAnomaly` · `RouteDenied` · `IsolationAnomaly`

**Success-access subclass (carried forward):** a successful self-scoped **MembershipsForPrincipal** enumeration MUST emit **exactly one** references-only event with `action == "workspace_memberships_read"`. A successful **empty** enumeration is still a successful enumeration and MUST emit the event. Never zero, never two, never one per returned record — the event records the operation, not the number or contents of what was returned.

**Tenant-record success-access set (carried forward):** `tenant_startup_read`, `tenant_startup_update`.

**Governed-sharing subclass (carried forward, inert):** `share_proposed`, `share_approved`, `share_granted`, `share_read`, `share_revoked`, `share_expired`, `share_suspended`, `share_denied`, `forward_attempt_denied` — **authored-but-inert until IC-007 is Final** (§18).

**Global Audit Representation Rule (contract law at IC-001 — unchanged):** every ingress-edge audit record is **references only** — `actor_ref`, `subject_ref`, `tenant_ref`, `record_ref`, `carrier_ref`, plus action / outcome / timestamp / correlation metadata.

**Prohibited in any audit event:** names, emails, PII, business payloads, field content, raw rows, tenant business data, tenant database identity, database name, DSN, secret, credential, connection string, token, provider body, router internals, stack trace.

**Migration dependency (normative).** Control DDL 012 pins `CHECK (source_service = 'api_gateway')`, so the existing `control_gateway_audit` table will **physically reject** a BFF-emitted row. **No BFF audit emission may be implemented until migration M-1 (D-46 §7) lands.** The approved approach is a **new** append-only table for the BFF ingress-edge class, leaving DDL 012/013 and their byte-pins intact as historical evidence.

---

## §11 — Isolation Contract *(RE-HOMED from IC-010 §K — load-bearing; decision authority in IC-014 §5)*

> *One of the four Gateway-only behaviours — the `assert_single_database` check.*

```text
One Request → One Active Tenant → One Physical Database
```

- **No request may access multiple tenant databases.** A single request resolves to the Control DB **or** exactly one tenant DB — never both, never several.
- **Cross-tenant operations are prohibited.** Any cross-tenant capability is IC-007-deferred (§18).
- A **MASTER_AGENT multi-membership fan-out is structurally impossible**: there is one signed active tenant and no API to address a second (IC-009 §P.4). The BFF MUST NOT offer an operation that accepts a second tenant.
- **Never** `ACME request → ACME DB + ZETA DB`. **Never** `ACME DB unavailable → use Control DB`. There is **no Control-DB fallback**.
- Any detected breach attempt MUST be rejected and MUST emit `IsolationAnomaly` (§10).

**Division of authority.** The Access Control Service **decides** whether the request's single resolution domain is lawful (IC-014 §5). The BFF **enforces** that exactly one domain was decided, and refuses to invoke a service when it was not. Neither may be omitted: a decision without enforcement is advisory, and enforcement without a decision is a guess.

---

## §12 — Error Handling Contract *(carries IC-010 §L)*

The BFF MUST be **fail-closed**. Each of the following yields **Request Rejected** — no fallback, no default tenant, no partial access:

| Condition | Outcome |
|---|---|
| Invalid / missing (where required) / mismatched carrier | **403 `carrier_mismatch`** |
| Invalid tenant context (unresolvable or inconsistent claim) | reject |
| Unauthenticated principal | **401** |
| Unauthorized principal (not a member of the claimed tenant; or denied by IC-014) | **403** |
| Unknown tenant | consistent-denial **not found** semantic (IC-002) — never leaking another tenant's existence |
| Tenant not ready / administratively disabled / unavailable | IC-002 readiness semantics |

**Consistent denial is mandatory:** unknown tenant and unauthorized tenant MUST be indistinguishable to the caller. **No error path may downgrade to a less-isolated outcome.** Denial responses carry canonical codes only — never tenant counts, database identifiers, topology, secret state, or internal failure reasons.

---

## §13 — Service Contract & Internal-Surface Protection *(carries IC-010 §M + §R — critical)*

> *This is the privilege-boundary rule. The BFF is the only public surface; every other service sits behind it.*

- All backend services MUST be reachable **only through the BFF** for **frontend/client ingress**.
- **Internal service surfaces MUST NEVER be directly client-reachable.** Internal read APIs and service-to-service transport MUST NOT be exposed to portal or client network zones.
- Services MAY call one another over sanctioned internal transport under static cross-service import constraints that enforce **service independence** (import-linter). This internal graph is **internal-only** and is **not a portal ingress path**; it never offers a client or portal a way around the BFF.
- **A service MUST NOT import another service's internal repository or application implementation.** Shared technical code and explicit service clients/interfaces are permitted.
- **Deployment obligation (normative).** Because removing the Gateway removes a **network position**, the BFF MUST occupy that position before any service is exposed. **The BFF is the sole governed public application ingress; no other backend service may be publicly reachable in any environment.** The exposure rules that make this enforceable — loopback/private by default in local development, bind-internally-but-never-publish for containers, and a deployment-manifest check — are **normative at §21.1 (E-1…E-7)**. A deployment in which a service other than the BFF is publicly reachable violates this contract **regardless of what any application-layer check does**.

---

## §14 — Future Channels Rule *(carries IC-010 §N)*

All client channels — **web, mobile, desktop, public API** — bind to the same BFF rules identically: BFF-only ingress, the carrier contract, residency, isolation, audit, and fail-closed denial. No channel may bypass these rules; channel-specific routing or data paths are prohibited.

*(New **portal classes** still require a new ADR and an IC-009 amendment — D-37 §6. This rule binds channels, not portal classes.)*

---

## §15 — Physical Multi-Database Rule *(carries IC-010 §O — reinforced, never weakened)*

The **Control Database** and the **Tenant Databases** remain **physically separate** PostgreSQL databases.

The BFF MUST NOT introduce — directly, or by enabling any client / portal / workspace / ownership path — a **shared database**, a **shared schema**, or a **`tenant_id` isolation** architecture. One request resolves to the Control DB **or** exactly one tenant DB; no BFF behaviour may blur that boundary.

**Global Record ≠ Tenant Record.** A Global→Tenant import creates a new independent tenant record with its own identity, ownership, activity and history. Lineage records provenance only. **Import ≠ Synchronization**: the BFF MUST NOT introduce synchronization, or automatic / scheduled / background / event-triggered / timer-driven re-import — regardless of how individually lawful each underlying call would be (IC-003, D-34).

The Physical Multi-Database MVP is **mandatory** and is reinforced by this contract.

---

## §16 — Operation Taxonomy · Dispatch vs Database Resolution *(carries IC-010 §Q + §X)*

**The BFF surface is enumerated, not generic.** Every exposed operation MUST be a named frontend use case with a declared Pydantic request model and response model. Adding an operation is a contract change.

Each request resolves to **exactly one** operation category, and each category to **exactly one** database domain:

| Category | Domain |
|---|---|
| Tenant Operation | TENANT |
| Global Directory Read | CONTROL |
| MembershipsForPrincipal | CONTROL |
| Import Initiation | TENANT |
| Governed Sharing *(inert until IC-007 Final — §18)* | CONTROL |

**One request → one category → one database.** No category, and **no combination of categories**, may straddle the Control DB and a tenant DB, or span two tenant DBs, within one request. A Global Directory Read and a Tenant Operation are therefore **distinct requests**, never a single straddling one.

**Dispatch vs Database Resolution — the terminology split *(IC-010 §X, critical)*:**
- **Operation selection (BFF).** The BFF selects the operation by **request path / operation only**. It consumes **no** tenant, workspace, or ownership value as a selector. **The route is never a client-controlled routing channel.**
- **Database resolution (Database Router only).** Resolving to exactly one physical database from the signed claim is the **exclusive** responsibility of the Database Router.

**The BFF MAY select operations; the BFF MUST NOT resolve databases.**

---

## §17 — Readiness Disclosure Contract *(carries IC-010 §S — now applies to every service)*

Every service's liveness / readiness / version disclosure MUST be **minimally disclosing**.

**Prohibited in any health, readiness, or version response:** database names, tenant-database details, tenant counts or identities, infrastructure topology, secret state, and internal failure reasons.

The **degraded** state exposes operational status only; degraded is observability/alerting-only and MUST NOT deny routing to healthy tenants (D-16).

Under Option A every service exposes liveness/readiness, so this rule binds **all fourteen services**, not only the ingress.

---

## §18 — Deferrals *(carries IC-010 §U — status updated by D-46 §6)*

- **AI routing, AI ownership and AI operations** remain governed by **IC-006**, which is a `Draft` placeholder whose normative sections are all TBD. The Option A directive reopens the AI deferral **for the rebuild's Phase 9**, but **IC-006 MUST be authored to Draft-complete before Phase 9 begins** (D-46 §6, CONF-5). The BFF exposes **no AI behaviour** under this revision. The D-36 `owner_ai_agent_ref` slot stays NULL until IC-006 (IC-008).
- **Cross-tenant operations and Master-Agent cross-tenant workflows** remain governed by **IC-007** (`Draft / Proposed`). **IC-007 MUST be promoted to `Final` before any Sharing Service work** (D-46 §6, CONF-6). No BFF path provides cross-tenant access, sharing, introductions, or collaboration under this revision. The §16 Governed Sharing category and the §10 `share_*` audit subclass are **authored-but-inert**.

---

## §19 — Response Composition Contract *(carries IC-010 §V — composing seam re-pointed)*

- **ARBITRARY DOWNSTREAM BODY PASS-THROUGH — FORBIDDEN.**
- **BFF-COMPOSED, CONTRACT-APPROVED DTO RESPONSE — PERMITTED**, under the conditions below only.

This is the rule that keeps the BFF from degenerating into a proxy. A surface that relays a downstream body **is a gateway route** and is forbidden.

**Permitted composition requires all of:**
1. **Adopted-contract DTOs only.** Every composed type is defined by an adopted contract (IC-009-R1 for portal DTOs). The composer MUST refuse any type absent from the approved catalogue.
2. **BFF-owned typed composition.** The BFF composes the response itself from **typed service results**, never by forwarding bytes.
3. **Deterministic serialization**, with contract-and-revision traceability naming the contract the seam serves.
4. **Order preservation.** Where a service returns a deterministically ordered result, the BFF MUST NOT re-sort it.
5. **§12 denial semantics unchanged.** On any denial the BFF returns the §12 denial and **no DTO**.
6. **The composer selects no database** and performs no business logic.
7. **One request → one approved operation → one database** (§11/§16).

**Pydantic is the DTO layer (Option A §7).** Business Use Case → FastAPI route → Pydantic input/output model → application service → domain/data. **A second API/DTO specification layer MUST NOT be introduced** without a proven requirement recorded as a contract amendment.

**Relationship to IC-009.** IC-009 remains the normative portal DTO catalogue at revision **IC-009-R1**; its DTO shapes, field sets and provenance markers are **unchanged**. Only the identity of the composing seam moves from the API Gateway to the BFF (IC-009 amendment of 2026-08-21).

---

## §20 — Acceptance Criteria *(carries IC-010 §W, re-pointed at the BFF)*

When the BFF is built under a separate, explicitly-authorizing execution instruction, it MUST satisfy:

- **D-33 §10 criterion 4** — an authenticated request with a mismatched subdomain/header is rejected end-to-end through the BFF.
- **D-33 §10 criterion 5** — a workspace switch issues a new scoped token and emits the audit event; the old context cannot be reused to reach the new workspace's data.
- **D-33 §10 criterion 6** — an architecture test proves the BFF constructs `RequestContext` **only** from `AuthContext`; no inbound tenant/workspace parameter reaches the router.
- **D-37 §20 V1** — the portal/BFF never determines database routing.
- **D-37 §20 V2** — the portal/BFF never determines tenant routing.
- **D-37 §20 V3** — data is accessed only through the BFF, verified by a **frontend-repository audit**: no database client, no Supabase data SDK, no PostgREST usage.
- **Zero-Gateway census.** A repository census MUST return **0** occurrences of `api_gateway`, `API Gateway`, `http_gateway`, `gateway_edge`, gateway launcher and gateway config in the new runtime. Historical documentation MAY retain the word only when clearly marked historical and intentionally preserved.
- **Re-homing proof.** Architecture tests MUST prove each of the four re-homed behaviours (§5, §7, §10, §11) is present and enforced at its new home.
- **Exposure proof (§21.1 E-6).** A **deployment-manifest check** MUST prove that across every compose file, Kubernetes manifest, environment template and launcher script, **exactly one service publishes a port, and it is the BFF**. A source-level check MUST additionally prove that no internal service defaults its bind to `0.0.0.0`, and that `reload` is never enabled outside a local-development path. These are **configuration** properties, so a code-only test set cannot discharge them.

These are acceptance criteria for the future implementation, not obligations this contract implements.

---

## §21 — Service Shape & Serving Posture *(new — resolves CONF-8 and CONF-9)*

Every backend service — the BFF included — MUST:
- live in its own package with its own entry module;
- start and stop **independently**;
- have a **configurable port**;
- expose **liveness and readiness** (§17);
- have its own tests.

**Startup convention (normative — resolves CONF-8).** The approved shape is the **simple one**: each service has its own `main.py` defining its own `app = FastAPI()`.

```python
import uvicorn
from fastapi import FastAPI

app = FastAPI()

if __name__ == "__main__":              # local development convenience — PERMITTED
    uvicorn.run(
        "main:app",
        host="127.0.0.1",               # loopback default — §21.1 E-2
        port=8000,                      # configurable
        reload=True,                    # local development ONLY — §21.1 E-4
    )
```

**A service-level `import uvicorn` is permitted.** So is the `if __name__ == "__main__":` development block above. Neither is a contract violation.

**Explicitly NOT mandated by this contract:**
- a **shared uvicorn runtime module** that every service must route through;
- a mandatory **`create_app()` factory**;
- a mandatory **`--factory`** invocation;
- any rule that a service-level uvicorn import is always a violation.

A service **MAY** use an application factory, and a deployment **MAY** invoke it with `--factory`, where that suits the service. Those are **options, not obligations**. This contract does not replace the simple `main.py + app = FastAPI()` model with a more complex runtime architecture by implication, and no such design is in force unless Dan separately and explicitly ratifies it.

**Production startup MAY use an external ASGI server command** (e.g. `uvicorn <module>:app --host … --port …`). `reload=True` remains **development-only** in every case (§21.1 E-4).

### §21.1 — Exposure Model *(normative — ratified by D-47; resolves CONF-9)*

> **The controlling distinction is BIND versus PUBLISH.** A process *binds* an address inside whatever network namespace it runs in. A deployment *publishes* a port outward, to the host or to the internet. These are separate controls, and conflating them produces both false alarms (a container binding `0.0.0.0` inside its own namespace is normal and necessary) and real holes (a service correctly bound to a private interface, then published to the world by a compose file). **This contract governs both, separately.**

**E-1 — Only the BFF is a public ingress.** The **FastAPI BFF is the sole governed public application ingress**. No other backend service — Authentication, Access Control, Control Plane, Database Router, Startup, Investor, Deal, Sharing, Import, Lineage, Contacts, AI Agent, Audit — may be a public ingress, in any environment. This restates §13 and is the rule the other clauses serve.

**E-2 — Local development: loopback/private by default.** When run directly on a developer machine, every **internal** service MUST default to **loopback (`127.0.0.1`) or an otherwise private interface**. `0.0.0.0` MUST NOT be the default bind for an internal service in local development. A developer who deliberately needs a wider bind must set it explicitly; it is never what happens by omission.

**E-3 — Containerized internal services: bind internally, publish never.** A containerized internal service **MAY** bind whatever address its container network namespace requires — including `0.0.0.0` **within the container** — because that binding reaches only the container network. **Its port MUST NOT be published to the host or to any public network.** Concretely: no `ports:` mapping and no `-p` / `--publish` for an internal service; container-network reachability only (`expose` / service-name DNS on a private network). **Only the BFF's port may be published.**

**E-4 — `reload` is local-development only.** `reload=True` (and `--reload`) is permitted **only** on a developer machine. It MUST NOT be enabled in any shared, hosted, containerized, staging, or production environment.

**E-5 — Served-invocation hygiene flags are a set, not a menu.** A **served** invocation (an external ASGI server command in any shared, hosted, containerized, staging, or production environment) MUST pin all four:

| Flag | Why omitting it is a defect |
|---|---|
| `--workers 1` | one OS process per service — the authorized process model |
| `--no-access-log` | uvicorn's default access log records request detail |
| `--no-server-header` | otherwise every response discloses `Server: uvicorn` (§17) |
| `--no-proxy-headers` | forwarded headers are not a trusted input |

**Omitting one silently restores a uvicorn default.** A partial application is a violation, not a partial success.

`--factory` is **not** in this set: it is a start-path choice (§21 above), not a hygiene control, and is required only where a service actually exposes a factory. This clause binds the **served** path; the local-development `__main__` block of §21 is not a served invocation and is not bound by it.

**E-6 — Exposure is a deployment property, and MUST be verifiable as one.** Because E-1 and E-3 are violated by *configuration* rather than by code, application-layer checks cannot enforce them. The Phase-1 acceptance set MUST therefore include a **deployment-manifest check** proving that, across every compose file, Kubernetes manifest, and launcher script, **exactly one service publishes a port, and it is the BFF**. A deployment in which an internal service is publicly reachable violates this contract **regardless of what any application-layer check reports**.

**E-7 — Precedence.** Where any environment template, compose file, launcher, runbook, or sample code conflicts with E-1…E-6, **this section prevails** and the artefact is the defect. Option A §4's `uvicorn.run(host="0.0.0.0", …, reload=True)` sample is **superseded by this section**: it is illustrative only and MUST NOT be copied into any service as written.

**Technology (Option A §3).** Python · FastAPI · Pydantic · Uvicorn only. Every backend HTTP service MUST be FastAPI. A separate Node backend, a custom REST framework, or a duplicate request/response DTO framework MUST NOT be introduced.

---

## §22 — Frontend Cutover *(new — addresses CONF-12)*

Phase 0 established that the frontend expects **86** server-function operations while the built backend serves **3**. Full parity is **not** achievable as a single step and is **not** a precondition of this contract.

**Normative cutover rules:**
1. **Incremental by contract.** The BFF exposes operations as their owning services land. Each newly exposed operation is added to the §16 enumeration by contract amendment.
2. **Per-operation retirement.** The frontend's interim Supabase seam is retired **per operation**, never big-bang. An operation is cut over only when its BFF surface exists, is authorized through IC-014, and routes through the Database Router.
3. **No Gateway as an intermediate compatibility layer.** The old API Gateway MUST NOT be used as a runtime bridge during cutover (Option A Phase 10).
4. **Interim state is bounded and visible.** While any operation still uses the Supabase seam, that operation is **not** compliant with §9 or IC-013 §15, and MUST be listed in a governed, enumerated cutover set. The interim exception is tracked, never permanent (D3/D7).
5. **Cutover completion criterion.** Cutover is complete when the frontend-repository audit (§20, D-37 §20 V3) returns zero database clients, zero Supabase data SDK usage, and zero PostgREST usage.

---

## §23 — Anti-Vendor-Lock-In Requirements

- **No Supabase** logic at or behind the BFF: no Supabase Auth, no Supabase data SDK, no PostgREST, no RLS-as-authorization.
- **No Lovable** or other frontend-platform runtime dependency in the BFF boundary.
- Authentication is OIDC via IC-005 with any self-hostable, swappable IdP. The only legitimate non-BFF traffic is vendor-neutral OIDC token issuance at the IdP.
- The BFF, `RequestContext`, and audit are portable, standard-PostgreSQL-compatible, and provider-neutral.
- FastAPI, Pydantic, Starlette and uvicorn are open-source and vendor-neutral; ASGI is a standard interface. No cloud or hosting provider is assumed.
- All database usage remains **cloud-portable standard PostgreSQL** (AWS RDS / Azure Database for PostgreSQL / Google Cloud SQL / self-hosted). No provider-specific extensions.

---

## §24 — Prohibitions (consolidated)

The BFF MUST NOT:
1. be named, or be renamed to, any form of "Gateway" (§0);
2. select or resolve a database (§3, §8, §16);
3. authenticate (that is IC-005) or evaluate authorization itself (that is IC-014) (§3, §4);
4. re-derive the active tenant from anything but the signed claim (§7);
5. accept a tenant or workspace value from a header beyond the carrier check, a cookie, a query string, a path segment, a body, or client storage (§5, §7);
6. relay an arbitrary downstream response body (§19);
7. expose an internal service surface to a client (§13);
8. offer an operation that addresses two tenants, or straddles Control and tenant databases (§11, §16);
9. fall back to the Control DB when a tenant DB is unavailable (§11);
10. fail open, or downgrade any denial to a less-isolated outcome (§12);
11. carry a token, secret, credential, DSN, PII, or physical-database identifier in a context, DTO, log line, or audit record (§7, §10);
12. introduce a shared database, shared schema, or `tenant_id` isolation architecture (§15);
13. introduce synchronization or any automatic/scheduled/background re-import (§15);
14. expose AI or cross-tenant sharing behaviour under this revision (§18);
15. permit any service other than itself to be a public ingress, or any internal service's port to be published to a host or public network (§13, §21.1 E-1/E-3);
16. default an internal service's bind to `0.0.0.0` in local development (§21.1 E-2);
17. enable `reload` in any shared, hosted, containerized, staging, or production environment (§21.1 E-4);
18. use a **served** invocation with fewer than all four hygiene flags (§21.1 E-5).

---

## §25 — Not implemented · Implementation prohibited

**No BFF behaviour is implemented by this contract.** No runtime is created, changed, or removed; the existing `api_gateway` package remains untouched on disk. No database migration is authored or applied. **No production-readiness claim is made. Documentation and contract reconciliation do not by themselves discharge runtime, migration, deployment, or implementation acceptance criteria.** Production remains **NOT READY / DO-NOT-ACTIVATE**.

Implementation proceeds only under a separate, explicitly-authorizing execution instruction (register entry → contract → code), inheriting the §20 acceptance criteria.

---

## §26 — Traceability

| Source | Relationship |
|---|---|
| **D-46** | Opens this contract; §4 re-homing map is normative |
| **IC-010** | **Superseded** by this contract + IC-014. Sections carried forward: §A→§1, §B→§3, §C→§4, §D→§4, §E→§5, §F→§6, §G/§T→§7, §H→§8, §I→§9, §J→§10, §K→§11, §L→§12, §M/§R→§13, §N→§14, §O→§15, §Q/§X→§16, §S→§17, §U→§18, §V→§19, §W→§20 |
| **IC-014** | Co-successor — owns the authorization decision this contract's §4 flow calls and §11 enforces |
| **IC-005** | Authentication authority; carrier match-or-reject; role hierarchy (D-32) |
| **IC-009** | Portal DTO catalogue (IC-009-R1) — composing seam re-pointed here by the 2026-08-21 amendment |
| **IC-001 / IC-002** | Global directory; tenant lifecycle, readiness and consistent-denial semantics; audit class homes |
| **IC-003 / IC-004** | Import and lineage boundaries (§15) |
| **IC-007 / IC-006** | Deferrals (§18) |
| **IC-012** | Composition root — not an ingress; re-scoped by the 2026-08-21 amendment |
| **D-06 / D-30 / D-33 / D-34 / D-37 / D-07** | Carrier authority, isolation enforcement, workspace architecture, operational audit, portal architecture, registry-authoritative routing |
