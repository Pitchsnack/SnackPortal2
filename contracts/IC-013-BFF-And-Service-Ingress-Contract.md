# IC-013 — BFF & Service Ingress Contract

**Status:** Draft / Proposed · **Phase:** Architecture ratification (Phase 0) · **Type:** Contract-first specification (no implementation)
**Opened:** by **D-45 — FastAPI Implementation Proposal v2.2 Target-Architecture Ratification**. **Revision:** IC-013-DRAFT-1.
RFC-2119 keywords **MUST / MUST NOT / SHOULD / MAY** are used normatively.

> **Contract-first, no positive capability.** This contract **specifies and constrains a boundary and a runtime shape**. It grants no route, no DTO, no error code, no permission, no cross-tenant capability, no audit class, and no DDL. It changes no authentication, routing, import, lineage, or ownership semantics. It removes, relocates, renames, or disables **no** runtime code. IC-013 becomes **Final** only after independent verification and explicit human merge. **Production remains NOT READY / DO-NOT-ACTIVATE.**

---

## §1 — Purpose

Define the **BFF (Backend-for-Frontend)** as the **single approved ingress** into SnackPortal2, and define the runtime shape every SnackPortal2-owned FastAPI service MUST have.

The ratified development topology is:

```
Frontend
   -> FastAPI BFF
        -> Authentication Service
        -> Access Control Service
        -> Control Plane
        -> Database Router
        -> domain services
             -> Control DB / Tenant DBs
```

The BFF is **not a new hop placed in front of an existing gateway**. It is the ratified **successor role of the API Gateway service** described by IC-010 (D-45 R-1). Exactly one approved ingress exists before, during, and after that transition. Introducing a second ingress, or serving any internal edge to a public network, is prohibited by this contract.

## §2 — Singularity of ingress (normative)

- There MUST be exactly **one** approved ingress surface. A second ingress MUST NOT be introduced.
- Every service edge other than the ingress is **internal-only** and MUST bind a loopback interface. Internal edges MUST NOT be reachable from a public network.
- The ingress MUST be a SnackPortal2-owned FastAPI application. A dedicated third-party API-gateway product, an Enterprise Security Edge, and any non-FastAPI ingress framework are **NOT** development dependencies and MUST NOT be required for a developer to run the system (v2.2 §51, §53).
- A deployment MAY place an enterprise security product **in front of** the ingress. That product MUST NOT absorb, replace, or override any SnackPortal2 tenant, routing, ownership, access-control, or AI-authorization decision (§12).

## §3 — Inherited enforcement rules (normative, unchanged)

Every enforcement rule IC-010 places on the API Gateway applies to the BFF **verbatim and without weakening**. Where this contract and IC-010 both speak, IC-010's wording governs the rule and this contract governs only which component carries it.

- **Request flow (IC-010 §C).** Authentication, then carrier validation, then tenant-context validation, then `RequestContext` creation, then the Database Router, then the service. No stage may be skipped, reordered, or bypassed. No path may reach a service or a database except through this flow.
- **Endpoint dispatch, never database resolution (IC-010 §X).** The ingress dispatches to a service or endpoint by request path or operation. Resolving a request to exactly one physical database is the **exclusive** responsibility of the Database Router. The ingress never selects a database; the Database Router never authenticates.
- **Carriers (IC-010 §E; IC-005).** Exactly two tenant carriers are recognized — the tenant subdomain and the `X-Tenant-Id` header — both subordinate to the signed claim under match-or-reject. Cookies, query-string parameters, portal state, workspace state and client local storage MUST be stripped or ignored and MUST NOT be read by any backend component for any purpose.
- **Tenant context (IC-010 §F).** Workspace is derived from the tenant context; the tenant context is never derived from workspace.
- **`RequestContext` (IC-010 §G/§T).** Constructed **exclusively** from the Authenticator's output, references only, no PII or identity payload, no inbound tenant or workspace parameter reaching the router.
- **Internal-surface protection (IC-010 §R).** Internal edges expose closed route allowlists and disclose no routing shape.
- **Error handling (IC-010 §L).** Denials and refusals answer with a fixed status and an empty body. No stack trace, exception text, SQL, topology, credential state, or token may cross an edge.
- **Audit (IC-010 §J).** Reference-only emission; the audit classes and their homes are unchanged by this contract.
- **Isolation (IC-010 §K) and the physical multi-database rule (IC-010 §O).** One request resolves to at most one physical database; there is never a fallback to the Control DB for a tenant-scoped request.

**Nothing in IC-013 relaxes any of the above.** A conflict between IC-013 and an inherited rule resolves in favour of the inherited rule.

## §4 — BFF responsibilities (normative)

The BFF **MAY**:

- serve frontend-facing operations and frontend-oriented orchestration;
- coordinate calls across backend services and aggregate their results into a response shaped for a screen;
- carry application and session context for the duration of a request;
- render permission-aware responses, including the tri-state presentation (loading, allowed, denied) that avoids permission flicker;
- hide backend topology from the frontend;
- perform every inherited enforcement duty of §3.

The BFF **MUST NOT**:

- duplicate authentication logic (it consumes the Authentication Service's output);
- duplicate or evaluate access-control rules (it consumes the Access Control Service's decision — IC-014);
- duplicate or apply database-routing rules, or select a database;
- implement Startup, Investor, Deal, Sharing, Import, Lineage, Contacts, or Audit business rules;
- make ownership decisions (IC-008);
- authorize an AI-agent action;
- reach a database, a repository, or another service's internal implementation directly.

## §5 — Service clients (normative)

The BFF communicates with a backend service **only through that service's public FastAPI boundary**. It MUST NOT import another service's internal implementation modules, and MUST NOT bypass a service to reach its repository or database.

This restates, and does not weaken, the service-independence rule already machine-enforced by the import-linter independence contract and by IC-012 §18.

## §6 — Access Control separation (normative)

Authentication, access control, tenant routing, and database access are **four distinct responsibilities in four distinct components**:

```
Authentication  = who is the principal?
Access Control  = what is this principal allowed to do?
Tenant Routing  = which single active tenant and physical database may this operation use?
Database Access = the routed session itself
```

- Authentication is owned by IC-005 and MUST NOT choose the active tenant, select a database, or grant an application permission.
- Access Control is owned by IC-014 and MUST NOT select or influence a database, re-derive the active tenant, or become the tenant-isolation mechanism.
- Tenant routing and database resolution remain owned by IC-005 and the Database Router.

**Authenticated is not authorized, and authorized is not routed.**

## §7 — Independently bootable service shape (normative)

Every SnackPortal2-owned FastAPI service MUST provide, per HTTP edge it owns:

- a **no-argument ASGI application factory** that returns a composed FastAPI application and binds no socket;
- a **fail-closed** factory: a missing or malformed configuration selector raises before anything is served, and there is never a silent in-memory substitute;
- its own routes, its own configuration, its own startup checks, and its own port;
- **liveness** (is the process running) and **readiness** (is the edge able to accept business traffic) as distinct signals. A service MAY be running and not ready. A not-ready edge MUST NOT accept business traffic. Readiness disclosure remains minimally disclosing and MUST NOT reveal tenant or database existence or topology.

No edge may require the whole backend to start before its own process can boot.

## §8 — Composition seam and module entry point (normative)

- `<service>/main.py` is the service's **composition seam**. Its meaning is fixed by IC-012 §1 and is unchanged by this contract.
- The FastAPI application object MUST be constructed inside the service's `adapters/providers` zone, not in the composition seam, so the web-framework dependency stays inside the sanctioned containment zone.
- A service MAY additionally expose a module entry point so that invoking the composition seam as a module starts that service through the single sanctioned ASGI runtime. That entry point is a convenience; it MUST NOT become a second composition path, and it MUST call the same factory the canonical operator command calls.
- The canonical operator command remains a factory-mode invocation of the edge's application factory with an explicit host, an explicit port, exactly one worker, and the disclosure-suppressing flags the startup runbook pins.

## §9 — One service MAY own more than one edge (normative)

Independent bootability is a property of the **edge**, not of the package. A service package MAY own several HTTP edges, each with its own factory, its own port, and its own process. This is the built state and it is ratified as-is (D-45 R-5).

## §10 — Runtime supervision (normative)

- Exactly **one** worker and **one** operating-system process per edge.
- No application-created worker, subprocess, supervisor, or retry loop.
- **A reload supervisor MUST NOT appear in any documented startup command, in the governed launcher, in continuous integration, in any rehearsal harness, or in any hosted profile** (D-45 R-6). Development reload remains an ad-hoc developer convenience only and is never a governed path.

## §11 — API shape (normative)

- New services and new routes MUST use FastAPI routes with Pydantic models providing request validation, response schemas, and schema generation. A parallel custom request-DTO or response-DTO framework MUST NOT be introduced (v2.2 §15).
- Existing edges keep their present validation and serialization posture — fixed-status empty-body validation refusals, and hand-serialized response bytes — until each is separately migrated under its own authorized change. Retrofitting a response model onto an edge whose wire bytes are pinned is **not** authorized by this contract (D-45 R-4).
- Schema generation and interactive documentation are governed by surface class:
  - **internal edges** MUST keep schema generation and interactive documentation **disabled** (IC-010 §R);
  - **the ingress** MAY expose them **in a development portability profile only**, and MUST NOT expose them in a hosted or production profile (D-45 R-3).

## §12 — Deployment boundary (normative)

An enterprise security product, a reverse proxy, or a TLS terminator is a **deployment** concern placed in front of the ingress. It MUST NOT be required for local development, and it MUST NOT hold or evaluate any SnackPortal2 tenant, routing, ownership, access-control, or AI-authorization rule. Moving such a rule into a deployment product requires its own ratified decision.

## §13 — Repository layout (normative)

The backend retains its **flat top-level package layout**: `shared` as a technical dependency leaf, one package per service, and the `deployment` cross-service composition root above them. New services are added as new top-level packages.

A relocation of the package tree is **not authorized** by this contract. Any future relocation MUST separately re-pin the setuptools package list, the import-linter root packages and contracts, the architecture scanner's service census, the normative module placement of IC-012 §16, every documented startup command target, and the governed launcher's module map.

## §14 — Anti-vendor-lock-in requirements

- FastAPI, Uvicorn and Pydantic are open-source and vendor-neutral; ASGI is a standard interface. No cloud provider, hosting provider, or platform runtime may be required by any service.
- No Supabase-specific and no Lovable-specific business logic may exist in any service.
- All database usage remains standard, cloud-portable PostgreSQL.

## §15 — Enforcement requirements (for the phase that implements this contract)

When a phase implements any part of IC-013, that phase MUST also:

1. add each new service package to the setuptools package list, to the import-linter root packages, and to the import-linter service-independence contract, so a new package is **policed, not merely unlisted**;
2. add each new service package to the architecture scanner's service census and give it traceability metadata declaring its governing contracts;
3. pin every new edge's canonical startup command in the startup runbook, with an explicit host, an explicit port, one worker, and the disclosure-suppressing flags;
4. add a guard proving the new edge's factory binds no socket, fails closed, and shares one composition path with its service's seam.

None of these changes is authorized by IC-013 itself.

## §16 — Contract impact

- **IC-010** — amended by an insert-only note recording that its sole-ingress designation is **conditionally superseded by IC-013 when IC-013 becomes Final**, at which point the ingress role is carried by the BFF. Every IC-010 boundary rule, prohibition, and frozen invariant is **unchanged and inherited**. The API Gateway runtime is retained.
- **IC-005** — amended by an insert-only cross-reference recording that cross-cutting authorization is homed in IC-014. Authentication, token validation, carrier law, membership law, and active-tenant law are **unchanged**.
- **IC-012** — **not amended.** No new cross-service composition module is created; the §5.1 amendment gate remains the trigger for any future one.
- **IC-001, IC-002, IC-003, IC-004, IC-006, IC-007, IC-008, IC-009, IC-011** — no change.

## §17 — Exclusions (normative)

IC-013 does not authorize, and MUST NOT be read as authorizing:

- removing, rewriting, disabling, or relocating the API Gateway runtime;
- creating, renaming, or moving any package;
- changing the import-linter configuration;
- implementing the BFF, Authentication, Access Control, Database Router, or any domain service behaviour;
- exposing any new route, DTO, error code, permission, audit class, or DDL;
- closing any open blocker, or changing the blocker census.
