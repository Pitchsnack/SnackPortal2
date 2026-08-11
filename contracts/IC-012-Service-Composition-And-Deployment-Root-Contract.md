# IC-012 — Service Composition & Deployment Root Contract

**Status:** Draft / Proposed · **Phase:** Build under contract-first governance · **Type:** Contract-first specification
**Opened:** by **D-44 — Deployment Cross-Service Composition Root (Edge 9 Import Edge)**. **Revision:** IC-012-DRAFT-1.
**Amendment (2026-08-11, D-45 — Gateway-Free Controlled Local MVP Ingress Architecture; ratified by Dan):** `api_gateway` is removed from every **active service list** in this contract (§2, §3, §4, §13, §18) because **the package was deleted, not because the D-44 grant widened**. The authorized set in §3 is **unchanged and still exhaustive** (`import_service`, `database_router`, `lineage_service`, `shared`); the un-authorized forward set is still the **exact complement** of that grant over the surviving service packages. §15's IC-010 cross-reference is reconciled to the ratified public-edge boundary. **No composition authority is granted, widened, or relaxed by this amendment**, and every §4 prohibition, §5.1 governance gate, §8–§12 rule, §13 enforcement requirement and §14 guard check is preserved verbatim.
RFC-2119 keywords **MUST / MUST NOT / SHOULD / MAY** are used normatively.

> **Contract-first, no positive capability.** This contract **specifies and constrains a structural boundary**. It grants no route, no DTO, no error code, no cross-tenant capability, no audit class, and no DDL. It changes no import, lineage, routing, or authentication semantics. It grants **no blanket cross-service composition authority** — only the specific composition named in §3. IC-012 becomes **Final** only after independent verification and human merge. **Production remains NOT READY / DO-NOT-ACTIVATE.**

## §1 — Purpose of the deployment composition root
The `deployment` package is the **single authorized cross-service composition root** of the SnackPortal2 backend: the one place where objects owned by **different** services are wired together into a runnable application. Its entire reason for existing is that **cross-service object-graph assembly is not a service concern** — it is a deployment concern that sits above every service.

**Service-local composition is expressly preserved and is NOT centralized here.** Every service keeps its own composition root — its `main`/composition seam (`<service>.main.build_*_from_env`) and its own native ASGI application factory — and continues to own the assembly of its own objects. IC-012 neither replaces, deprecates, supersedes, nor constrains those seams. The governing rule is:

```
service-local composition   →  remains owned by each service
cross-service composition   →  deployment only
```

- There MUST be exactly **one** *cross-service* composition-root package. A second cross-service composition root MUST NOT be introduced. This says nothing about, and takes nothing from, the service-local composition roots, which remain plural by design — one per service.
- The root MUST be **import-time inert**: importing `deployment` or any module within it MUST read no environment variable, open no connection, bind no socket, execute no DDL, materialize no secret, and start nothing. Composition happens only when a factory is **called**.
- The root MUST re-use each service's **own published composition seam** rather than re-deriving wiring, so there is exactly one source of truth for every dependency.

## §2 — Why cross-service composition belongs ABOVE the services
Each service package (`auth_router`, `control_plane`, `database_router`, `import_service`, `lineage_service`) is **mutually independent**, and `shared` is a dependency leaf that imports none of them. That DAG is the structural guarantee behind physical tenant isolation: no service can reach another's internals, so no service can quietly acquire a second service's database authority. Within its own boundary each service composes itself freely; the DAG constrains only what crosses a boundary.

`ImportService` depends on two **ports** whose only implementations live in other services — `RoutedSessionProvider` (`database_router`) and `LineageEmitPort` (`lineage_service`). There are exactly three ways to satisfy that, and two are prohibited:

1. **`import_service` imports `database_router` and `lineage_service`** — PROHIBITED. It collapses the independence DAG, and it hands the Import service a direct route to the Database Router's internals, defeating the isolation guarantee the DAG exists to provide.
2. **`import_service` fetches a session over HTTP** — IMPOSSIBLE and PROHIBITED. See §8: a routed session is a live transactional handle, not a serializable value.
3. **A root ABOVE both services injects the implementations into the service that declares the ports** — ADOPTED. Dependency direction points inward to the ports; the concrete cross-service wiring lives at the outermost layer, where deployment knowledge belongs. Services stay mutually blind to one another; only the root knows they coexist.

Option 3 is the only one that satisfies the ports without weakening any boundary, so **cross-service** composition MUST occur above the services and MUST NOT occur inside any of them. Composition that does **not** cross a service boundary is unaffected by this clause and stays where it is.

## §3 — Exact allowed dependency direction (normative)
The authorized cross-package production dependencies of the composition root are **exactly** the following — the set the implemented and proven Edge 9 composition strictly requires, and no more:

```
deployment ──> import_service     # Edge 9: the service that DECLARES the two ports
deployment ──> database_router    # Edge 9: the only implementation of RoutedSessionProvider
deployment ──> lineage_service    # Edge 9: the only implementation of LineageEmitPort
deployment ──> shared             # dependency leaf
```

This list is **exhaustive and closed**. The following are **NOT authorized** and MUST NOT appear:

```
deployment ─╳─> auth_router
deployment ─╳─> control_plane
```

> **D-45 note (no widening).** This list previously also named `deployment ─╳─> api_gateway`. That
> package was **deleted** under D-45, so the complement shrank; **the authorized set above did not
> move**. The un-authorized list remains the **exact complement** of the §3 grant over every
> surviving service package, and widening it still requires the §5.1 amendment path.

- Each authorized edge is authorized **because Edge 9 strictly requires it**. `deployment.import_edge` imports exactly `database_router.main`, `database_router.session_provider`, `database_router.adapters.providers.env_tenant_secret_store`, `import_service.main`, `import_service.adapters.providers.http_import_api`, and `lineage_service.emit` — and nothing else. `auth_router` and `control_plane` are **not required by it** and are therefore **not granted**. *(Before D-45 this sentence also named `api_gateway`; that package no longer exists.)*
- This contract confers **no blanket cross-service composition authority**. Widening the authorized set — for any service, for any reason — requires an IC-012 amendment under **§5.1**.
- `deployment` MUST NOT be imported by anything (see §4).
- The root's cross-service imports SHOULD be **function-local** (inside the factory), so the module stays inert per §1 and driver-bearing provider modules load only when a real composition is requested.

## §4 — Exact prohibited reverse-import direction (normative)
All of the following MUST hold and MUST NOT be relaxed, exempted, or allow-listed:

```
import_service    ↛ database_router
import_service    ↛ lineage_service
database_router   ↛ import_service
lineage_service   ↛ import_service
shared            ↛ any service
shared            ↛ deployment
auth_router       ↛ deployment
control_plane     ↛ deployment
database_router   ↛ deployment
import_service    ↛ deployment
lineage_service   ↛ deployment
```

Rationale for `services ↛ deployment`: without it, the root becomes a **legal back-channel** — service A could reach service B through `deployment`, and the service-independence contract would never observe the chain. The forbidden direction is therefore load-bearing, not cosmetic.

**Forward direction is equally normative.** The un-authorized forward edges named in §3 — `deployment ↛ auth_router`, `deployment ↛ control_plane` — are prohibited on the same footing as the reverse edges above, and are machine-enforced by their own contract (§13).

The pre-existing service-independence contract remains in force **verbatim and unweakened**. IC-012 adds constraints; it removes none.

## §5 — Authority for `deployment.import_edge:create_app_from_env`
- `deployment.import_edge:create_app_from_env` is the **canonical native ASGI application factory for Edge 9** (the Import Service HTTP edge). Canonical operator startup:
  `uvicorn deployment.import_edge:create_app_from_env --factory --host <host> --port <port> --workers 1 --no-access-log --no-server-header --no-proxy-headers`
- It MUST take **no arguments**. Host and port belong to the runtime process, not to the application: the factory MUST bind no socket and own no address.
- It MUST return a composed `FastAPI` application **and nothing else**.
- It MUST build the application through the Import service's own public application seam (`import_service.adapters.providers.http_import_api.create_app`), so the route set and every fail-closed handler have exactly **one** definition shared with the retained injected-composition path.
- It MUST NOT parse any environment selector that an owning service already parses, and MUST NOT introduce a second composition architecture **for the Import edge**. The retained service-local injected seam (`import_service.main.build_import_server_from_env`) is **not** a second architecture: it consumes the same ports and the same application seam, invoked service-locally with the ports supplied to it.
- This section authorizes **exactly one** cross-service edge factory: the Edge 9 factory named above. It authorizes no other, present or future. See §5.1.

### §5.1 — Future cross-service deployment modules (governance gate — normative)
IC-012 **does not pre-authorize** sibling modules, and conformance to this contract is **not** authorization. A future cross-service `deployment` module — or any widening of the §3 authorized import set — MAY be added **only after all of the following**:

1. it is **demonstrated that service-local composition cannot satisfy the need** — i.e. the required ports genuinely have no single owning service, and the need is not met by that service's own composition root;
2. the **service-independence DAG is preserved** — no service gains an import of another service, and nothing gains an import of `deployment`;
3. **IC-012 is amended** to authorize the **specific** new composition, naming the module, the exact service packages it may import, and the necessity finding from (1);
4. the **architecture guards and import-linter contracts are updated** where required, so the new authorization is machine-enforced rather than merely written.

Where the change is **materially architectural**, an **ADR / Architecture-Decision-Register amendment** is required **in addition to** the IC-012 amendment.

Absent such an amendment, `deployment` MUST contain exactly the modules named in §16 and MUST import exactly the packages named in §3.

## §6 — How `RoutedSessionProvider` is supplied to `ImportService`
- The root MUST obtain the real `DatabaseRouter` from the Database Router's own seam, `database_router.main.build_router_from_env`, and MUST wrap it in `database_router.session_provider.PgRoutedSessionProvider`.
- The root MUST NOT construct routing transports, secret stores, connection factories, pools, or routing-audit selections by hand; those are the Database Router's own composition and MUST remain so.
- The root **introduces no routing authority**. It selects no database, resolves no tenant, and holds no DSN. The Database Router remains the **sole** database selector (IC-010 §H/§K/§O; D-07), and one routed tenant session still resolves to **exactly one** physical tenant database.
- A `None` router (routing selector unset/empty) MUST fail closed per §11. There is no in-memory session-provider substitute.

## §7 — How `LineageEmitPort` is supplied to `ImportService`
- The root MUST obtain the lineage emitter from the Lineage service's own seam, `lineage_service.emit.LineageEmit`, constructed over the tenant-scoped, reference-only secret store with the `"tenant"` key prefix (the composed-core convention: the chain is per-tenant and never crosses tenants — D-25, IC-004 *Cross-Tenant Isolation*).
- **Lineage semantics are NOT the root's.** The minimum lineage record, the per-tenant cryptographic hash chain, append-only enforcement, retention, and every emission rule remain wholly owned by `lineage_service` per IC-004. The root MUST NOT reimplement, wrap with behaviour, filter, reorder, suppress, synthesize, or interpret any lineage record.
- No lineage double, no-op emitter, or test substitute MUST ever be composed on the production path (§11).

## §8 — Why a live RoutedSession / transactional DB handle MUST remain in-process
A routed tenant session is **not data** — it is a live, stateful, transactional handle bound to an open connection against exactly one physical tenant database. It therefore:

- MUST be constructed **in the same process** that consumes it, and MUST be consumed within that process;
- MUST NOT be serialized, proxied, tunneled, or carried over HTTP or any other wire, in whole or by reference.

Reasons, each independently sufficient:

1. **It is not serializable.** Transaction state, cursors, and an open socket cannot be represented in a DTO; any wire representation would necessarily be a *credential or DSN*, which §9 prohibits.
2. **Transaction integrity.** Import writes are batched/checkpointed atomic units with per-batch lineage (D-21). Splitting a transaction across a network hop makes atomicity and rollback unprovable and would break the import failure semantics of IC-003.
3. **Isolation.** Exposing a session over a wire creates a second, unrouted path to a tenant database, bypassing the Database-Router-only rule and the "one request → one active tenant → one database" invariant (D-30, IC-010 §K/§O).
4. **Secret discipline.** Any wire form leaks or implies credentials, violating the reference-only SecretRef rule (D-14, §9).

Consequently, "compose over HTTP instead of in-process" is **not an available alternative** for Edge 9, which is precisely why the composition root is necessary.

## §9 — SecretRef and database-routing boundaries
- **Reference-only secrets.** The tenant secret store is **reference-only and lazy**: constructing it resolves nothing. Descriptors carry `{store-ref, version}` only; raw credential values MUST NOT appear in the root, in DTOs, in logs, in responses, or in any contract (D-14).
- **No pre-resolution at composition.** The root MUST NOT pre-check per-tenant credentials at composition time. The store accepts a per-reference environment variable **or** a file under the tenant secret directory and resolves lazily by reference at first use; demanding a directory at composition would duplicate the provider's knowledge and would wrongly reject a valid environment-variable-only deployment. The fail-closed guarantee is unchanged — the provider raises on an unresolved reference — it simply lands on the first request, exactly as for every other reference-only store in the backend.
- **No routing authority in the root.** The root holds no DSN, no tenant→database mapping, no naming convention, and no override. Registry-authoritative resolution (D-07) stays inside the Database Router.
- **No cross-tenant reach.** The root composes one application; it creates no cross-tenant connection, no shared pool across tenants, and no cross-tenant query path.

## §10 — Transaction / session residency
- Every routed session MUST be **acquired, used, committed or rolled back, and released within the process that composed it**.
- Session and transaction lifetime MUST remain owned by the Database Router's provider and the Import service's unit-of-work; the composition root MUST NOT open, hold, extend, share, cache, or reuse a session, and MUST NOT retain a reference to one after the factory returns.
- Connections MUST NOT be reused across tenants (D-13/D-30). The root introduces no pool, no cache, and no session registry.

## §11 — Fail-closed startup behavior
The Import edge MUST fail closed, **before anything is served**, when it cannot compose the real production path (IC-010 §L):

- routing selector (`SP2_DBR_ROUTING_READ_BASE_URL`) unset/empty → the factory MUST raise (`RuntimeError`); no application is composed and no socket is served;
- directory-read selector (`SP2_IMPORT_DIRECTORY_READ_BASE_URL`) unset/empty → the factory MUST raise (`ValueError`, from the Import seam);
- any malformed required startup selector or composition value → the factory MUST raise.

This does not alter the lazy SecretRef resolution rule in §9; an unresolved per-tenant SecretRef may fail at first use as governed there.

There MUST be **no fallback** to an in-memory session provider, a lineage double, or a non-durable audit sink. The standing Import path MUST always write through the real Database Router to a real physical tenant database, with real lineage and a real durable audit trail. Degraded composition is prohibited, not merely discouraged.

## §12 — Anti-vendor-lock-in requirements
- The root MUST remain **cloud-neutral and vendor-neutral**: no cloud SDK, no provider-managed identity, no proprietary secret manager, no managed-database client, no PaaS-specific hook, no Supabase surface, no Lovable runtime feature.
- The concrete ASGI server MUST NOT be imported here. `uvicorn` remains confined to its single sanctioned containment module; the root produces an **ASGI application**, which is a standard interface, and is startable by any conformant ASGI server.
- The root MUST remain compatible with self-hosted, AWS, Azure, and Google Cloud PostgreSQL deployments interchangeably; it MUST rely on no provider-specific extension or proprietary feature.
- The root MUST NOT encode environment-specific topology (hostnames, regions, account identifiers, provider resource names). All environment input arrives through the services' own portable env seams.

## §13 — Import-linter enforcement requirements
- `deployment` MUST be listed in `[tool.importlinter] root_packages` so the package is **analyzed and policed**, not merely unlisted. An unlisted package is invisible to the graph and could silently become a back-channel.
- A dedicated `forbidden` contract MUST name every service package and `shared` as `source_modules` and `deployment` as the sole `forbidden_module` — the reverse direction of §4.
- A second dedicated `forbidden` contract MUST name `deployment` as the sole `source_module` and **every surviving service package outside the §3 authorized set** — today exactly `auth_router` and `control_plane` — as `forbidden_modules` — the **un-authorized forward direction** of §3, so the narrow authorization is machine-enforced and cannot be widened by editing code alone. Widening it requires the §5.1 amendment path.
- The pre-existing service-independence contract MUST remain **unchanged and unweakened**: no service may be removed from it, no `ignore_imports` exemption may be added for `import_service → database_router` or `import_service → lineage_service`, and its module list MUST NOT be narrowed. `deployment` MUST NOT be added to it.
- `lint-imports` MUST report **0 broken contracts**. The check MUST run in CI and MUST be executed via the `lint-imports` entry point.

## §14 — Architecture guard requirements
A dedicated AST/text guard under `backend/tests/architecture/` MUST enforce, independently of import-linter:

1. **Cross-service singularity** — `deployment` is the only production package containing a module that imports more than one service package; no module outside `deployment` does so. Service-local composition modules are expressly **out of scope** of this check: a service composing its own objects is not a cross-service composition root and MUST NOT be flagged.
2. **Direction** — no module under any service package or `shared` contains an import of `deployment` (including aliased, deferred, function-local, `importlib`, or `__import__` forms).
3. **Import-time inertness** — every cross-service import in `deployment` is function-local; module scope performs no environment read, no connection, no socket bind, no DDL, and no secret materialization.
4. **Composition-only** — no module in `deployment` contains SQL text, DDL, a DSN literal, a raw credential, an HTTP route declaration, an authorization or role decision, a tenant-selection decision, or lineage record construction (§17).
5. **Seam reuse** — the Edge 9 factory composes via the owning services' published seams and via `http_import_api.create_app`; it does not construct transports, pools, or the application by hand.
6. **Factory shape** — `create_app_from_env` takes no parameters, returns a `FastAPI` app, and binds no host/port.
7. **No server binding** — `deployment` imports no concrete ASGI server (§12).
8. **Text-drift** — the IC-012 §3/§4 direction tables and this section's guard list are pinned against drift, matching the repository's existing contract-text-drift guard precedent.
9. **Authorized composition set** — no module in `deployment` imports any service package outside the exhaustive §3 authorized set; specifically, no import of `auth_router` or `control_plane` appears in any form, and the module census of `deployment` matches §16. This check backstops the import-linter contract in §13 and makes an un-amended widening fail twice.

## §15 — Contract impact
- **IC-003 (Import) — amended, references-only.** A cross-reference recording that the Import edge's `RoutedSessionProvider` and `LineageEmitPort` are supplied by the deployment composition root. **No import semantic changes**: execution model (D-19), idempotency and natural-key reconciliation (D-20), re-import governance (D-20/D-34), partial-failure and batching semantics (D-21), ingress validation and PII handling (D-09 ingress), the API contract, the DTO contract, and the audit requirements are all unchanged. The composed `ImportService`, its ports, routes, and durable audit sink are the same ones the injected composition produced.
- **IC-004 (Lineage) — amended, references-only.** A cross-reference recording that the `LineageEmitPort` implementation is injected by the composition root with the per-tenant `"tenant"` key prefix. **No lineage semantic changes**: the minimum lineage record, source/target references, actor identity, tenant-context requirements, the per-tenant hash chain and append-only model (D-23), retention/archival (D-24), unified provenance (D-25), cross-tenant isolation, and failure behaviour remain wholly owned by `lineage_service`.
- **IC-010 (Public Edge Ingress Contract) — amended, references-only.** A cross-reference in §H (Database Router Boundary), §K (Isolation) and §O (Physical Multi-Database Rule) recording that composition **supplies** the Database Router but **selects no database**. **Reconciled 2026-08-11 (D-45):** the **approved authenticated public edges** are the sole served client ingress (IC-010 §A.2); the Edge 9 Import edge this root composes is an **internal, non-public** edge and is **not** a client ingress path (IC-010 §R/§M). The Database Router remains the sole database selector; one request → one active tenant → one database is unchanged. **No route, no route family, no carrier, no `public_code`, and no audit class is added** (§Q taxonomy unchanged; §J unchanged).
- **IC-001, IC-002, IC-005, IC-006, IC-007, IC-008, IC-009, IC-011 — no change.** The root adds no global-directory behaviour, no tenant-startup behaviour, no authentication or routing authority, no AI capability, no sharing capability, no ownership rule, no portal DTO or route, and no rollback-proof term.
- **ADR impact:** **D-44 (new).** No existing decision is amended, superseded, or reopened. D-07, D-13, D-14, D-21, D-25, and D-30 are **relied upon and preserved**, not modified.

## §16 — Exact package / module placement (normative)
```
backend/deployment/__init__.py       # package docstring = the boundary statement (§§1–5.1, §17)
backend/deployment/import_edge.py    # Edge 9 factory: create_app_from_env
```
- The root MUST be `backend/deployment/` — a **sibling of the service packages**, not nested inside any of them. Nesting it under a service would make the root that service's property and re-create the very dependency it exists to avoid.
- `deployment*` MUST be included in the package discovery `include` list so the root ships with the distribution.
- The Edge 9 factory MUST be `backend/deployment/import_edge.py`, exposing exactly `create_app_from_env` in `__all__`.
- **The module census above is exhaustive and is not open-ended.** Additional cross-service edge modules are **NOT pre-authorized** by this contract. One MAY be added only through the **§5.1** governance gate — necessity demonstrated, DAG preserved, IC-012 amended to authorize that specific module and its exact imports, guards/import-linter updated, plus an ADR/register amendment where the change is materially architectural. If ever authorized, such a module lives as a sibling (`deployment/<edge>_edge.py`) and is bound by every clause of this contract.
- Sub-packages, shared helper layers, and utility modules within `deployment` SHOULD be avoided; if added, they remain bound by every clause of this contract.

## §17 — Composition-only scope (exclusions — normative)
`deployment` contains **cross-service composition and nothing else**. It MUST NOT contain:

- **domain logic** — no entities, no value objects, no domain services, no invariants;
- **business rules** — no validation, no eligibility, no pricing, no workflow, no state machine;
- **SQL** — no query, no DDL, no migration, no schema statement, no DSN literal;
- **authorization policy** — no role, permission, membership, or access decision;
- **tenant-selection policy** — no tenant resolution, no tenant→database mapping, no routing override, no fallback selection;
- **routing authority** — no database selection of any kind; the Database Router remains the sole selector (§6);
- **lineage semantics** — no lineage record construction, interpretation, filtering, suppression, or chain manipulation;
- and additionally: no HTTP route, no DTO, no error code, no persistence, no audit class, no secret value, no scheduling, and no concrete ASGI server.

Its only permitted act is to **call published composition seams and pass the resulting objects to one another**. Nothing in this section restricts what a service may do inside its own service-local composition root.

## §18 — Services remain mutually independent (restatement — normative)
The introduction of `deployment` **does not** create, imply, or permit any dependency between services. `auth_router`, `control_plane`, `database_router`, `import_service`, and `lineage_service` remain **mutually independent**, and `shared` remains a dependency leaf importing none of them. In particular `import_service ↛ database_router` and `import_service ↛ lineage_service` remain absolute. Each service also retains full ownership of its **own** composition — IC-012 takes no service-local authority away. `deployment` is not a shared library, not a service, not a mediator, and not a message path: it is a one-way, top-of-DAG assembler with a narrow, enumerated import set that every service is structurally forbidden to see.

## §19 — Guard
`backend/tests/architecture/` MUST hold the guard specified in §14, and `pyproject.toml` MUST hold the import-linter contracts specified in §13. Both MUST pass in CI before IC-012 may move from Draft / Proposed to Final.
