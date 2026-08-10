# SnackPortal2 — Complete API Gateway Removal MVP Experiment — Result

**Instruction:** `SnackPortal2_Complete_API_Gateway_Removal_MVP_Experiment_GPT.md`
**Branch:** `experiment/complete-api-gateway-removal-mvp` · **Base:** `origin/main` = `cdb46fc9`
**Date:** 2026-08-10 · **Author:** Claude (Opus 5)

---

## VERDICT

> ## `COMPLETE API GATEWAY REMOVAL — MVP ARCHITECTURE VIABLE`
>
> **Recommendation: the architecture is sound and materially simpler. Adopting it is a
> separate decision that requires contract amendments and a live proof — neither is done here.**

The MVP now runs with **no `api_gateway` module imported, instantiated or launched**, proved by
executing a clean subprocess and asking the interpreter what it loaded — not by reading source.
Nothing replaced the Gateway: the two MVP route families are served by the services that already
own the records behind them, and each enforces its own public boundary **in-process** using a
shared library that import-linter proves cannot reach any service.

### Why this succeeded where the previous experiment did not

The previous experiment (`experiment/remove-api-gateway`, `009fa268`) concluded
`NOT VIABLE WITHOUT REPLACEMENT CONTROLS`, on the reasoning that the replacement controls had
only three possible homes:

> 1. Inside `database_router` — contract violation (measured).
> 2. A new component in front of the Startup API — that component *is* the API Gateway.
> 3. Nowhere — the naive result.

**That trichotomy is incomplete, and its first item was measured against the wrong construction.**
Option 1 was measured as broken because the probe added `import auth_router` *in-process* to
`database_router`. That is indeed a violation — but it is not how the Gateway itself consumes
authentication. The Gateway calls the Auth Router over the existing internal HTTP transport, and
so does this experiment. `lint-imports` reports **4 contracts kept, 0 broken**.

The missing fourth home is the one this experiment tests:

> **4. In a shared, service-agnostic LIBRARY, linked in-process by each route-owning service.**

That distinction is not cosmetic, and it is the whole result. A gateway is a *runtime component
standing between a client and the service that owns the data*. A linked library is *inside* that
service — there is no "between". The difference is machine-checkable rather than rhetorical:
`shared` is a dependency leaf under an existing, unmodified import-linter contract, so
`shared/public_edge.py` **structurally cannot import, name, reach or forward to any service**. A
gateway's defining act is unavailable to it by construction.

### The honest qualifications, stated up front

1. **No live proof.** §10 forbade it. Authentication is a double that reproduces the real Auth
   Router's decision shape; the databases are two physically distinct in-memory stores. Nothing
   here proves behaviour against Keycloak 8814 or PostgreSQL 5540–5543. That is a separate
   future authorization item (§13 below).
2. **This is not merge authorization**, and no contract file was edited. Adoption requires
   IC-010 amendments that only Dan can ratify (§5 below).
3. **The public surface count goes UP, 1 → 2.** Total runtime edges go down (6 → 5) and internal
   hops go down (4 → 3), but there are now two things a reverse proxy must terminate and two
   CORS allowlists to keep correct. That is a real operator cost, recorded rather than buried.
4. **Import stays deferred, not solved.** It was already outside the controlled local MVP
   journey (IMPORT-A / D-3), so this experiment shrinks the surface honestly rather than
   claiming to have re-homed a route it did not build.

---

## 1. Exact branch / base identity

Recorded **before any edit**, per §3:

| Item | Value |
|---|---|
| worktree | `D:\Pitchsnack\SnackPortal2_pr111_verify` |
| `git rev-parse origin/main` | `cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f` |
| `git rev-parse main` | `cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f` |
| `git ls-remote origin refs/heads/main` | `cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f` |
| `git rev-parse HEAD` (before) | `009fa268…` (the previous experiment branch — **not** used as a base) |
| `git status --porcelain` | *(empty — clean)* |
| gate `origin/main == main` | ✅ satisfied |
| gate `working tree clean` | ✅ satisfied |

Branch created **from `cdb46fc9`**, not from `009fa268`:

```text
git checkout -b experiment/complete-api-gateway-removal-mvp cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f
```

The previous experiment was read as evidence only (`git show 009fa268`, never checked out, never
merged, never cherry-picked).

**Commits on this branch:**

| SHA | Subject |
|---|---|
| `b6697cbb` | experiment: Gateway-free MVP architecture (no production change) |
| `098a07ec` | experiment: prove the public response contract is byte-identical to the Gateway's |

---

## 2. Current MVP route inventory and classification

The Gateway's *core* classifies four path families, but its *served edge* exposes far fewer. That
gap matters: two of the Gateway's dispatch categories are **dead surface on `main`**, not
capabilities this experiment drops.

| Route (as served on `main`) | Classification | Owner after removal |
|---|---|---|
| `GET /tenant/startups/<startup_ref>` | **MVP REQUIRED — MOVED TO OWNING SERVICE** | Database Router |
| `PATCH /tenant/startups/<startup_ref>` | **MVP REQUIRED — MOVED TO OWNING SERVICE** | Database Router |
| `GET /memberships` | **MVP REQUIRED — MOVED TO OWNING SERVICE** | Control Plane |
| `GET /health`, `GET /readiness` | **MVP REQUIRED** | each edge, per-edge |
| `OPTIONS` preflights (per business target) | **MVP REQUIRED** | each edge |
| `POST /import/<source_ref>` | **MVP NOT REQUIRED — DEFER** | — |
| `GET /directory/<kind>` (core category only) | **REMOVE FROM MVP** | — |
| generic `TENANT_OPERATION` router hand-off | **REMOVE FROM MVP** | — |

**Evidence for the two removals.** `_EXPOSED_ROUTES` in `http_gateway_edge.py:90-94` is exactly
`{/memberships, /health, /readiness}` plus the two bounded parameterized families. **No
`/directory` route is registered at all**, so `DispatchCategory.GLOBAL_DIRECTORY_READ`
(`dispatch.py:47`) and its Control-Plane read branch (`gateway.py:330-332`) are unreachable
through the served edge on `main`. The generic router hand-off (`gateway.py:432`) is likewise
bypassed for every served tenant route once the CLM tenant-Startup port is composed, which the
governed standing map does.

**Evidence for deferring import.** `docs/runbooks/backend_service_startup_fastapi.md:80-83`:
Import Service, Import Audit ingest and Routing Audit ingest are *deliberately absent* from the
standing topology because "Import is outside the controlled local MVP journey (IMPORT-A / D-3)",
and `SP2_GW_IMPORT_BASE_URL` must remain unset. Deferring it here changes nothing that runs.

---

## 3. Proposed Gateway-free architecture

```text
BEFORE — 6 edges, 1 public surface, 4 internal hops per business request
  browser ──▶ API Gateway 8820 ──┬──▶ Auth Router 8001 ──▶ Control Plane read 8003
                                 ├──▶ Control Plane read 8003        (memberships data)
                                 ├──▶ Tenant Startup API 8004 ──▶ one tenant database
                                 ├──▶ DB Router dispatch 8002        (no served route reaches it)
                                 └──▶ audit ingest 8005

AFTER — 5 edges, 2 public surfaces, 3 internal hops per business request
  browser ──┬─▶ Tenant Startup edge 8830 ─┬─▶ Auth Router 8001 ──▶ Control Plane read 8003
            │                             ├─▶ one tenant database        (IN-PROCESS)
            │                             └─▶ audit ingest 8005
            └─▶ Workspace edge 8831 ──────┬─▶ Auth Router 8001 ──▶ Control Plane read 8003
                                          ├─▶ Control DB                 (IN-PROCESS)
                                          └─▶ audit ingest 8005
```

**Ownership resolved (§4 candidate comparison).**

| Candidate | Verdict |
|---|---|
| **A — Tenant Startup edge becomes a real authenticated public MVP edge** | **ADOPTED** for the tenant route family. |
| **B — Database Router owns the authenticated Startup HTTP edge** | **ADOPTED, with the `Authentication ≠ Routing` question answered rather than dodged** — see §5. The Database Router *consumes* IC-005 authentication through an injected transport port; it performs none. Machine-checked: no JWT/JWKS/OIDC/crypto import anywhere in `database_router`, and `router.py` / `resolver.py` / `session_provider.py` / `tenant_startup_ops.py` contain no authentication identifier at all. |
| **C — another existing domain service owns its own public route** | **ADOPTED** for `/memberships`: the Control Plane owns the membership records, so it serves them. |
| **New generic MVP/BFF/edge gateway** | **REJECTED and structurally prevented** — see §6 and GF-2. |

**What the shared library is, and why it is not a gateway.** `shared/public_edge.py` is the
public-boundary security kernel: carrier extraction, straddle rejection, authentication
*consumption*, the `TrustedPrincipal`, one-request→one-tenant binding, and references-only audit
with a fail-closed posture. It is a **library**: no port, no process, no deployable, no hop,
nothing traverses it. Each owning service imports it and enforces its own boundary in-process.

The anti-gateway proof is not an assertion, it is a pre-existing contract:

```text
shared is a dependency leaf (must not import any service)   KEPT
services are mutually independent (no service imports another)   KEPT
Contracts: 4 kept, 0 broken.
```

Because `shared` may not import any service, the kernel cannot classify a request onto a service,
cannot hold a service's address, and cannot forward anything anywhere. GF-2 adds the direct
checks (no transport identifier, no web-framework import, no `dispatch`/`route`/`forward`/`proxy`
definition, **zero route literals**) plus non-vacuity probes.

---

## 4. Files changed

**18 files, +4101 / −6.** No file was deleted; no Gateway source was touched.

| File | Δ | Nature |
|---|---:|---|
| `backend/shared/public_edge.py` | +507 | **NEW** — the public-boundary security kernel (library) |
| `backend/shared/adapters/providers/public_edge_transport.py` | +192 | **NEW** — shared browser-facing transport gate (bounds, CORS, correlation, raw-target) |
| `backend/shared/adapters/providers/http_principal_authenticator.py` | +145 | **NEW** — the IC-005 authenticate transport client (same wire as the Gateway's) |
| `backend/shared/adapters/providers/edge_audit.py` | +213 | **NEW** — in-memory + durable audit sinks, bounded retry, CLM partition |
| `backend/database_router/portal.py` | +111 | **NEW** — owner-resident IC-009-R1 tenant Startup DTO + bounded parser |
| `backend/database_router/adapters/providers/http_public_startup_edge.py` | +327 | **NEW** — the public tenant Startup edge |
| `backend/control_plane/portal.py` | +74 | **NEW** — owner-resident IC-009-R1 membership DTO |
| `backend/control_plane/adapters/providers/http_public_workspace_edge.py` | +248 | **NEW** — the public workspace edge |
| `backend/database_router/main.py` | +105 | composition seams + five new selectors |
| `backend/control_plane/main.py` | +98 | composition seams + five new selectors |
| `backend/tests/gateway_free/**` (6 files) | +1601 | 57 tests: adversarial, mutation, composition, contract parity |
| `backend/tests/architecture/test_gateway_free_mvp_boundaries.py` | +497 | 22 new architecture guards |
| `backend/tests/architecture/test_07d3_multiinstance_readiness_static.py` | +26/−6 | **the only pre-existing test modified** — see §5 |
| `docs/runbooks/gateway_free_mvp_topology.md` | +90 | the documented experimental topology (guard-bound) |

**Runtime LOC added: 1,817. Test LOC added: 2,098.**

---

## 5. Architecture contracts changed

No contract file was edited. Contracts precede code, and ratifying an amendment is Dan's
decision, not an experiment's. What follows is the amendment set that adoption would require,
in the format §9 mandates.

### 5.1 IC-010 §A / §C / §I / §M / §N — the "sole ingress" family

**CURRENT CONTRACT.**
§A: "Define the **API Gateway** as the **sole approved ingress** into SnackPortal2 services."
§C: "**No alternate flow is permitted.** Every client request traverses these stages in order…"
§I: portals "MUST access backend services **only through the API Gateway**".
§M: "All backend services … MUST be reachable **only through the API Gateway** for client/portal
ingress, *unless explicitly governed otherwise*."
§N: "all client channels … bind to the **same** gateway rules identically: gateway-only ingress."

**PROPOSED MVP CONTRACT.** The *boundary* is retained and the *component* is not. Every public
request is still authenticated, carrier-validated, given a tenant context from the signed claim,
and turned into a trusted context before any service logic — but that flow is enforced by the
route-owning service, in-process, through one shared kernel, rather than by one central component.
An "approved public edge" is a service edge that (a) links `shared.public_edge`, (b) derives all
tenant and actor authority from `TrustedPrincipal`, (c) serves exactly one route family it owns,
and (d) forwards no business request to any other service.

**WHY THE CHANGE IS SAFE.** §A/§C/§I/§M/§N protect a *property* — that no client path reaches a
service or a database without authentication, carrier validation, and one-tenant binding. They
name a *component* only because, when written, one component was how that property was achieved.
The property is preserved literally and is now enforced by shared code that cannot be bypassed
per-edge, because there is only one implementation of it. Every isolation mechanic named in
§K/§O/§X survives untouched. The security-critical direction of §M is *strengthened*: the
unauthenticated internal tenant-Startup edge is removed from the topology entirely.

**WHAT NEW TEST ENFORCES IT.** GF-1/GF-1b (executed: the composition loads zero `api_gateway`
modules), GF-2/GF-2b/GF-2c (the replacement is a library and serves one route family per edge),
GF-6 (the documented topology has no Gateway edge and no 8820), and adversarial A1–A20.

**POST-MVP CONSEQUENCE.** Every new public route must be born inside its owning service and must
link the kernel. There is no longer a single place to add a cross-cutting concern, so anything
genuinely cross-cutting (rate limiting, WAF, request signing) must go into the shared kernel or
the reverse proxy — a deliberate constraint, and the one that keeps a gateway from growing back.

### 5.2 IC-010 §R — Internal-Surface Protection: **PRESERVED AND STRENGTHENED, not changed**

§R requires that "Internal read APIs MUST NEVER be directly client-reachable". This is preserved:
the internal Auth Router (8001), the internal Control-Plane read (8003) and the audit ingest
(8005) remain internal, and neither public edge exposes any `/internal/...` target (test A20c).

It is *strengthened* because the internal `POST /internal/tenant/startups/{read,update}` edge —
whose `target_tenant_ref` and `actor_ref` are **request-body fields** and which performs no
authentication — is **absent from the MVP topology**. The public edge holds the executor
in-process, so the hazard is deleted rather than fronted (A20, A20b, GF-6).

### 5.3 IC-010 §H — "The Database Router never authenticates": **PRESERVED**

The instruction anticipated this rule might have to change. It does not.

**CURRENT CONTRACT.** "The Database Router never authenticates. Authentication is complete before
the router is reached; the router consumes the already-authenticated context only."

**WHAT ACTUALLY HAPPENS.** The Database Router's *public edge adapter* consumes authentication
through an injected `PrincipalAuthenticatorPort` that reaches the Auth Router over the existing
internal transport. The routing core still receives a completed, trusted context and nothing else.

**MACHINE-CHECKED (GF-4/GF-4b).** No sibling service and no `jwt` / `jose` / `authlib` /
`oauthlib` / `oidc` / `cryptography` import appears anywhere in `database_router`. The four
routing/resolution modules contain no authentication identifier at all — not `authenticate`, not
`Bearer`, not `Authorization`, not `jwks`, not `verify_signature`, not even `PublicBoundary`. The
edge holds exactly **one** `boundary.admit` call site and exactly **one** `require_tenant` call
site. The pre-existing guards that enforce the separation (`test_phase4_database_router`,
`test_dbr_composition_boundaries`, `test_07e3b_auth_transport_boundaries`) are unmodified and green.

**POST-MVP CONSEQUENCE.** None for this rule. The one drafting change worth making is to say
"performs no authentication" rather than "is never reached by an authentication call", so the
distinction between performing and consuming is explicit in the contract text rather than implied.

### 5.4 IC-010 §J — the audit emitter

**CURRENT.** "The API Gateway is the **emitter** of these events"; "it is the **sole emitter** of
this success event (single edge)."
**PROPOSED.** The **route-owning public edge** is the sole emitter of its own route's events.
**WHY SAFE.** No audit class is added, removed, renamed or re-homed — only the emitting component
changes. GF-5b asserts the public-edge action vocabulary **equals**
`control_plane.gateway_audit.GATEWAY_AUDIT_STORE_ACTIONS` exactly, so the Control-DB home and the
DDL 012 CHECK are untouched. "Single edge" is preserved literally: each event class is emitted by
exactly one edge, and the per-request de-duplication set is retained.
**NEW TEST.** GF-5b, GF-5c (the durable partition stays exactly the five CLM classes), A18, A18b
(exactly one event per successful enumeration, empty included), A19 (fail-closed).
**POST-MVP CONSEQUENCE.** DDL 012's `source_service` CHECK pins the literal `'api_gateway'`. It
is a store-side producer constant and is never a wire field, so nothing in this experiment sends
it — but adoption needs that CHECK widened to name the route-owning edges. **No DDL was applied
or altered.** This is listed as an unresolved item (§13).

### 5.5 IC-010 §V — response composition

**CURRENT.** "**Gateway-owned and typed** composition … the gateway MUST construct the DTO itself."
**PROPOSED.** **Owner-owned and typed** composition: the service that owns the route constructs
its own adopted-contract DTO from values it validated. Every other §V.1 condition is unchanged,
and every §V.2 prohibition is retained verbatim.
**WHY SAFE.** This is the clause that *fixes* the previous experiment's §8 finding. Its measured
result was that bypassing the Gateway silently collapsed the eight-field `TenantStartupDetailDTO`
into the five-field internal envelope, losing the D-37 §10 provenance triple. Keeping composition
— rather than relaying the envelope — is what prevents that, and it is now pinned by test.
**NEW TEST.** `test_response_contract_parity.py` (5 tests): field names, field **order** and
defaults must equal the Gateway's definitions; serialization must produce **identical bytes**; and
the **served** responses from both public edges are compared against the contract composition.
**POST-MVP CONSEQUENCE.** Two DTO definitions now exist per shape (Gateway's and owner's) until
the Gateway is deleted. The parity test is what keeps them from drifting in the interim.

### 5.6 Canonical Overview Part 2 — locked invariant #7

**CURRENT.** "**The Gateway is the boundary** — frontend → Gateway, never directly to DB/auth/router."
**PROPOSED.** "**The authenticated public edge is the boundary** — the frontend reaches only
route-owning public edges, never a database, an internal read API, or a router directly."
**WHY SAFE.** The frontend still never reaches a database, the Auth Router, or the Database
Router's routing core directly. Invariant #6 ("Lovable owns the surface, not the plumbing") is
untouched.
**POST-MVP CONSEQUENCE.** This is a **locked invariant**; changing it needs sign-off, and this
experiment does not change it. It is listed here because adoption would.

### 5.7 The one pre-existing test modified — and why it is a registration, not a weakening

`tests/architecture/test_07d3_multiinstance_readiness_static.py` maintains a census of modules
permitted to contain a `serve_forever` loop, keyed to the single named blocking entrypoint each
one is allowed. Two entries were added for the two new public edges.

This does not weaken the guard. The census exists precisely to be the registry of blessed serve
loops; its strength is the *per-module rule*, not the size of the set — and that rule is applied
to the new entries by the same test, which verifies each blessing against real code
(`_single_blessed_serve_problems`). `ThreadingHTTPServer` remains banned everywhere, the
non-vacuity companion still flags an unauthorized reference, and no other guard changed. A stale
count in an adjacent comment ("a total of THREE") was corrected to stop restating a number that
had already drifted.

Two further existing guards **caught real defects in this experiment's code and were obeyed, not
edited**: the loopback-literal guard rejected a `127.0.0.1` default inside the security kernel
(the default moved to the composition roots, which is the better design anyway), and the
serve-loop census rejected the unregistered edges.

---

## 6. Security ownership matrix

Per §11 — no question has two answers, and no answer is "the Gateway".

| Question | `GET`/`PATCH /tenant/startups/<ref>` | `GET /memberships` |
|---|---|---|
| who authenticates it | `shared.public_edge.PublicBoundary.admit` → injected IC-005 port → Auth Router | same |
| who authorizes tenant access | Auth Router Stage 2 (membership + readiness), inside the same call | same |
| who derives tenant identity | `PublicBoundary.require_tenant` — signed claim only, one call site | n/a (control-scoped; subject is the authenticated principal) |
| who owns HTTP validation | `database_router…http_public_startup_edge` (bounded matcher, bounded body, allowlisted field) | `control_plane…http_public_workspace_edge` |
| who maps the public response shape | `database_router.portal` | `control_plane.portal` |
| who records audit evidence | the edge, via `EdgeAuditPort`, evidence-before-hand-back | same |
| who selects the physical database | `TenantStartupOperations` → `RoutedSessionProvider` (D-07) | the Control Plane's own per-request unit of work |

**The load-bearing invariant.** `target_tenant_ref` and `actor_ref` are **not request inputs**.
They appear in no accepted body, header, query, or path; they are produced from `TrustedPrincipal`
immediately before the executor call. GF-3 checks this in two positions, because the same word is
lawful in one and fatal in the other:

* as a **string literal** it would be a lookup key into caller-supplied data — banned outright.
  This is the exact shape of the internal edge's defect, where `envelope["target_tenant_ref"]`
  made the tenant a body field;
* as a **keyword argument** it is an output handed down to the executor — lawful, but only if its
  value comes from `principal.principal_ref` or from `require_tenant`'s result, asserted by AST
  dataflow.

`PublicRequest`, the kernel's view of a request, deliberately has **no body, query or cookie
field at all**. The cheapest way to guarantee the kernel never reads a prohibited carrier is not
to hand it one.

---

## 7. Gateway responsibility reduction

The previous experiment enumerated **33** responsibilities across the Gateway's three layers.
Each is classified below per §7.

### Serving edge (12)

| # | Responsibility | Classification | Where it lives now |
|---|---|---|---|
| 1 | Closed route + method allowlist | **MVP ESSENTIAL** | each edge's own FastAPI routes (one family each) |
| 2 | Decisions against the RAW request target | **MVP ESSENTIAL** | `public_edge_transport.raw_request_target` |
| 3 | Query-string rejection | **MVP DEFENCE-IN-DEPTH** | shared transport gate — **reclassified by executed evidence, see M6** |
| 4 | Bounded traversal-safe parameterized matcher | **MVP ESSENTIAL** | `is_valid_tenant_startup_target` (A12, M5) |
| 5 | Request bounds (target/headers/TE/body) | **MVP ESSENTIAL** | shared transport gate (A13) |
| 6 | Correlation accept/mint/echo | **MVP ESSENTIAL** | shared transport gate (A17, M11) |
| 7 | Exact-origin CORS + preflights | **MVP ESSENTIAL** | shared transport gate (A16, M10) |
| 8 | `Cache-Control: no-store` | **MVP ESSENTIAL** | shared transport gate |
| 9 | No slash-redirect, no OpenAPI/docs | **MVP ESSENTIAL** | inherited from `new_edge_app` (unchanged) |
| 10 | Denial-fidelity terminal | **MVP ESSENTIAL** | each edge (fixed status, empty body) |
| 11 | Exactly ONE core call site | **OBSOLETE WHEN GATEWAY IS REMOVED** | there is no core to call once; each edge has one `admit` site (GF-4b) |
| 12 | Minimal header forwarding; `X-Forwarded-*` never trusted | **OBSOLETE** | nothing is forwarded — the edge executes in-process |

### Gateway core (17)

| # | Responsibility | Classification | Where it lives now |
|---|---|---|---|
| 13 | Carrier extraction (subdomain + `X-Tenant-Id` only) | **MVP ESSENTIAL** | `public_edge.recognized_carriers` (A7, M4) |
| 14 | Straddle check (>1 distinct carrier) | **MVP ESSENTIAL** | `PublicBoundary.admit` (A11b) |
| 15 | Authentication handoff to IC-005 | **MVP ESSENTIAL** | `PrincipalAuthenticatorPort` (A1, A2, M3) — *the previous experiment marked this UNRESOLVED; it is resolved by the library home* |
| 16 | `CarrierOnControlAnomaly` | **MVP DEFENCE-IN-DEPTH** | `PublicBoundary.admit` (A10c) |
| 17 | Context built EXCLUSIVELY from `AuthContext` | **MVP ESSENTIAL** | `TrustedPrincipal` (A7–A9, GF-3) — *also previously UNRESOLVED; resolved* |
| 18 | Dispatch classification by path/operation | **OBSOLETE** | nothing dispatches; each edge serves its own family |
| 19 | `decide()` — TENANT requires a signed tenant | **MVP ESSENTIAL** | `require_tenant` (A10b, M2) |
| 20 | `assert_single_database()` | **MVP ESSENTIAL** | `require_tenant` returns one tenant or raises (A11) |
| 21 | Bounded PATCH validation before any port call | **MVP ESSENTIAL** | `database_router.portal` parser (A13b, M7, M8) |
| 22 | Control-Plane read composition | **MOVED TO OWNING SERVICE** | Control Plane composes it in-process |
| 23 | Import-initiation composition + zero-record denial | **POST-MVP / DEFER** | import is outside the CLM journey |
| 24 | §L fail-closed mapping | **MVP ESSENTIAL** | `PublicBoundaryDenied`, unchanged vocabulary (GF-5) |
| 25 | Portal DTO composition incl. provenance triple | **MVP ESSENTIAL** | owner-resident `portal.py`, byte-identical (parity tests) |
| 26 | Audit emission (7 classes, dedup, before-hand-back) | **MVP ESSENTIAL** | `PublicBoundary.emit` (A18, A19, M9) |
| 27 | Metrics recording | **POST-MVP / DEFER** | not carried forward; no MVP journey depends on it |
| 28 | Correlation minting inside the core | **OBSOLETE** | minted once, at the transport gate |
| 29 | Operation-key idempotency (`x-operation-key`) | **POST-MVP / DEFER** | import-only concern |

### Composition root (4)

| # | Responsibility | Classification | Where it lives now |
|---|---|---|---|
| 30 | Fail-closed env transport selectors | **MVP ESSENTIAL** | `internal_base_url_from_env` — **one** implementation instead of six near-copies (A14b, composition tests) |
| 31 | Composition-gate-first; `RuntimeError` when inactive | **MVP ESSENTIAL** | both edges (A14, A15) |
| 32 | Tenant-Startup transport selection | **OBSOLETE** | the executor is in-process; there is no transport to select |
| 33 | Durable audit partition (5 classes, bounded retry) | **MVP ESSENTIAL** | `edge_audit.py`, unchanged semantics (GF-5c) — *also previously UNRESOLVED; resolved* |

**Tally (33): 19 MVP ESSENTIAL · 2 MVP DEFENCE-IN-DEPTH · 4 POST-MVP/DEFER · 5 OBSOLETE ·
2 MOVED/COMPOSED BY THE OWNER · 1 reclassified by executed evidence.**

Against the previous experiment's tally of **26 still required with no lawful home**, the
difference is not that fewer controls are needed — nearly the same set is needed. The difference
is that they now have a lawful home: a library, which the previous analysis did not consider.

---

## 8. Test implementation

| Suite | Tests | LOC | What it proves |
|---|---:|---:|---|
| `tests/gateway_free/test_adversarial_boundary.py` | 36 | 657 | the 20 required adversarial proofs (A1–A20, several with sub-cases) + the workspace edge's own boundary (W1–W4) |
| `tests/gateway_free/test_mutation_non_vacuity.py` | 11 | 379 | each load-bearing control fails under a real defect (M1–M11) |
| `tests/gateway_free/test_env_composition.py` | 5 | 120 | the REAL transport clients compose from env and fail closed when unreachable |
| `tests/gateway_free/test_response_contract_parity.py` | 5 | 127 | byte-identical public responses vs the Gateway's DTOs |
| `tests/gateway_free/_fakes.py` | — | 318 | two physically distinct tenant stores + an IC-005-shaped identity double |
| `tests/architecture/test_gateway_free_mvp_boundaries.py` | 22 | 497 | GF-1…GF-6 with a non-vacuity probe each |
| **Total** | **79** | **2,098** | matches the suite delta exactly: 2133 − 2054 = 79 |

**Doubles sit at exactly two places** — the identity provider and the database. Everything between
is the real runtime: the real kernel, the real transport gate, the real `TenantStartupOperations`
executor, the real owner-resident DTO composition, and the real FastAPI applications served over
real loopback sockets via `http.client`. The workspace edge runs against a **real**
`ControlPlane` + `InMemoryControlStore` with memberships added through the real registry API.

**The isolation oracle is `provider.opened`**, the record of every `(tenant_id, principal_ref)`
the routed session provider was asked to open. A status code alone is weak: a cross-tenant read
that returns `404` because the record happens to be missing looks identical to one that was never
attempted. The opened-session list distinguishes them.

---

## 9. Adversarial and mutation results

### 9.1 The twenty required proofs — all pass

| # | Requirement | Test | Result |
|---|---|---|---|
| 1 | anonymous Startup GET denied | `test_a1` | ✅ 401, empty body, `opened == []` |
| 2 | anonymous Startup PATCH denied | `test_a2` | ✅ 401, no mutation, `opened == []` |
| 3 | valid ACME principal can read ACME | `test_a3` | ✅ 200, `opened == [(t-acme, p-acme)]` |
| 4 | valid ACME principal can write ACME | `test_a4` | ✅ 200, write lands in ACME, ZETA untouched |
| 5 | valid ZETA principal cannot read ACME | `test_a5` | ✅ 404; **no ACME session opened** |
| 6 | valid ZETA principal cannot write ACME | `test_a6` | ✅ 404; ACME record byte-unchanged |
| 7 | `X-Tenant-Id` cannot switch databases | `test_a7`, `test_a7b` | ✅ 403 `carrier_mismatch`, `opened == []`; a *matching* carrier changes nothing |
| 8 | JSON `target_tenant_ref` cannot switch databases | `test_a8` | ✅ 403 pre-executor; ACME untouched |
| 9 | JSON `actor_ref` cannot impersonate | `test_a9`, `test_a9b` | ✅ 403; on an accepted request the recorded actor is the authenticated principal |
| 10 | unknown tenant / non-member reveal nothing | `test_a10`, `a10b`, `a10c` | ✅ identical 403 + empty body; CONTROL on a tenant route denied and audited |
| 11 | one tenant DB session per accepted request | `test_a11`, `a11b` | ✅ exactly one; a multi-tenant assertion opens none |
| 12 | malformed reference fails before DB access | `test_a12` | ✅ 7 malformed forms all refused **before authentication is even attempted** |
| 13 | oversized PATCH fails before mutation | `test_a13`, `a13b` | ✅ 413 pre-handler; over-bound field value 403 pre-executor |
| 14 | missing auth configuration fails closed | `test_a14`, `a14b` | ✅ no boundary → no edge composes; malformed URL raises before any socket |
| 15 | missing routing configuration fails closed | `test_a15`, `a15b` | ✅ no composition, no socket; a runtime routing failure is a detail-free 503 |
| 16 | CORS permits only configured origins | `test_a16`, `a16b` | ✅ exact-origin only, never wildcard, never credentialed; empty allowlist denies all |
| 17 | correlation id bounded and usable | `test_a17` | ✅ accepted/minted/echoed; reaches the audit record |
| 18 | minimum MVP audit evidence emitted | `test_a18`, `a18b` | ✅ exactly one event per operation, references only, no payload leak |
| 19 | audit failure follows the stated policy | `test_a19` | ✅ **fail-CLOSED**, explicitly: an unrecordable success is 503, an unrecordable denial is 503 |
| 20 | internal edge cannot bypass the boundary | `test_a20`, `a20b`, `a20c` | ✅ absent from the topology; **positive control reproduces the hazard**; no internal surface exposed |

### 9.2 Mutation results — the assertions are non-vacuous

Each mutation is applied to the **executed** decision function and the security property is
re-tested. Every one was observed FAILING before the fix that made it pass, which is the evidence
that the corresponding assertion has teeth.

| # | Mutation | Detected? | Detector |
|---|---|---|---|
| M1 | `require_tenant` trusts the carrier instead of the claim | ✅ | a ZETA principal reads ACME's record; `(t-acme, p-zeta)` appears in `opened` |
| M2 | `require_tenant` defaults a tenantless principal | ✅ | a CONTROL principal opens a tenant database |
| M3 | `admit` stops denying | ✅ | an anonymous caller opens a tenant database |
| M4 | carriers dropped before the authenticator | ✅ | a disagreeing carrier is accepted; the `CarrierMismatch` evidence disappears |
| M5 | bounded matcher disabled | ✅ | an unsafe-charset reference reaches a real tenant session |
| M6 | query-string rejection removed | **SURVIVED — reclassified** | see below |
| M7 | update parser accepts extra fields | ✅ | the body channel re-opens (the tenant still stays the signed claim) |
| M8 | 500-character field bound removed | ✅ | the refusal moves from the edge (403) to the executor (503) |
| M9 | audit made fail-open | ✅ | the record is served with an empty evidence set |
| M10 | CORS widened to a wildcard | ✅ | a wildcard grant reaches an unlisted origin |
| M11 | unbounded correlation id accepted | ✅ | a 400-character caller-supplied id is echoed verbatim |

**M5 required choosing the right probe, and the wrong choice would have produced a false
conclusion.** An *over-bound* (>512-byte) reference is re-validated by `TenantStartupOperations`
*before* it opens a session, so under the mutation it still opens no database — a session-based
detector alone would have missed the defect and a naive reading would have concluded "the matcher
is redundant". The probe used is an *unsafe-charset* reference, which the executor does **not**
re-validate: with the matcher disabled it reaches a real tenant session. Both halves are asserted
so the two independent controls stay distinguishable. This is the same trap the previous
experiment recorded as its disproved prediction #3, hit again from the other side.

**M6 is a negative result, and it changes a classification.** The query-string rejection was
expected to be MVP-essential. With the branch removed from the executed middleware, **neither MVP
route becomes exploitable**, because two independent controls already cover it: on the
parameterized tenant Startup route the bounded matcher decides against the RAW target and `?` is
outside its charset (still 404); on the static `/memberships` route the query does become
reachable, but no handler reads a query parameter — the subject is `TrustedPrincipal.principal_ref`
and nothing else, so `?p=<someone-else>` returns the **caller's own** memberships. Recorded as
**MVP DEFENCE-IN-DEPTH**, on executed evidence rather than assumption.

**M7 is a partial detection, and the partiality is itself the finding.** Making the parser
permissive re-opens the *channel* for `target_tenant_ref` / `actor_ref`, but the architecture
still refuses to *read* them: the write stays in ZETA and ACME is untouched. That separation is
why the strict parser is defence-in-depth while `TrustedPrincipal` is the primary control — and
it is the precise structural difference from the internal envelope edge, where the body field
*was* the authority.

---

## 10. Comparison to current `main`

| Capability | Current Gateway architecture | Gateway-free MVP | Safe? | Simpler? | Evidence |
|---|---|---|---|---|---|
| runtime edges | 6 | **5** | = | **yes** | topology doc; GF-6 |
| standing ports | 6 (8001/8002/8003/8004/8005/8820) | **5** (8001/8003/8005/8830/8831) | = | **yes** | GF-6 |
| public surfaces | 1 | **2** | = | **no — a real cost** | §13 risk 3 |
| internal hops per business request | 4 | **3** | = | **yes** | §3 |
| route ownership | one component owns 3 families it owns no data for | each family owned by the service holding its records | = | **yes** | §6 |
| authentication path | browser → GW → AR → CP | browser → edge → AR → CP | = | = | A1–A3; composition tests |
| tenant derivation | `RequestContext` from `AuthContext` only | `TrustedPrincipal` from the auth port only | = | = | A7–A9; GF-3 |
| tenant isolation | one request → one category → one DB | one request → one authenticated tenant → one DB | = | **yes** (no category layer) | A5, A6, A11; M1 |
| DB routing | GW → HTTP → 8004 → router | edge → router (in-process) | = | **yes** | A11 |
| Startup GET / PATCH | served, 2 internal hops to data | served, **0** internal hops to data | = | **yes** | A3, A4 |
| memberships | GW composes from a CP read over HTTP | CP composes from its own unit of work | = | **yes** | W2, W3 |
| import | served route, port-gated | **deferred** (already outside the CLM journey) | = | **yes** | runbook §2.1 |
| audit | 7 classes, 5 durably homed, fail-closed | **identical**, emitter changes only | = | = | GF-5b, GF-5c, A18, A19 |
| CORS | exact-origin, no wildcard, no credentials | **identical**, shared implementation | = | = | A16, M10 |
| correlation | accept/mint/echo, bounded | **identical**, shared implementation | = | = | A17, M11 |
| response DTO | Gateway-composed, 8 fields | owner-composed, **byte-identical** | = | = | parity tests (5) |
| startup fail-closed | gate-first, `RuntimeError` when inactive | **identical**, both edges | = | = | A14, A15 |
| env selectors | 6 near-duplicate implementations in one root | **1** shared implementation | = | **yes** | A14b |
| runtime LOC | 3,327 (`api_gateway`) + 494 (2 internal edges) | **1,817** | = | **yes: −2,004 net** | §12 |
| architecture-test complexity | 262 tests / 6,142 LOC in `tests/api_gateway` | 79 tests / 2,098 LOC | — | **yes** | §8 |
| operator complexity | 1 public TLS/CORS target; 6 processes | 2 public TLS/CORS targets; 5 processes | = | **mixed** | §13 |

---

## 11. Routes and features deferred from the MVP

| Item | Disposition | Reason |
|---|---|---|
| `POST /import/<source_ref>` | **DEFER** | Already outside the controlled local MVP journey (IMPORT-A / D-3); the standing map omits the Import Service and requires `SP2_GW_IMPORT_BASE_URL` unset. |
| `GET /directory/<kind>` | **REMOVE** | No served Gateway route ever exposed it — dead surface on `main`, not a capability being dropped. |
| generic `TENANT_OPERATION` router hand-off | **REMOVE** | Reachable only through the dispatch fall-through, which no served route uses in the CLM composition. |
| Gateway request metrics (`MetricsPort`) | **DEFER** | No MVP journey depends on it. Re-adding it means one shared-kernel hook, not a component. |
| `x-operation-key` idempotency | **DEFER** | Import-only concern. |
| `CONTROL`-on-behalf-of-subject memberships | **DEFER** | Contract-preserved but never runtime-bound; deliberately not built (the query selector is unreachable — W2). |
| Governed Sharing (IC-007) fifth category | **DEFER** | Authored-but-inert on `main`; unchanged. |

---

## 12. Runtime edges and ports before / after

| | Before | After |
|---|---|---|
| edges | 6 | **5** |
| standing ports | 8001, 8002, 8003, 8004, 8005, **8820** | 8001, 8003, 8005, **8830**, **8831** |
| public | 8820 only | 8830, 8831 |
| internal | 8001, 8002, 8003, 8004, 8005 | 8001, 8003, 8005 |
| removed | — | **8820** (Gateway), **8004** (unauthenticated internal tenant-Startup envelope edge), **8002** (DB Router dispatch — Gateway-only consumer) |

---

## 13. Unresolved risks

1. **No live proof (highest).** §10 forbade touching the standing environment, so authentication
   is a double and the databases are in-memory. Nothing here proves behaviour against Keycloak
   8814, a real PKCE session, or PostgreSQL 5540–5543. **Separate future authorization item:** a
   two-tenant live witness on the Gateway-free topology, mirroring
   `infrastructure/runbooks/clm_acme_dataplane_witness.md`, with W-8 store-posture verification.
2. **DDL 012's `source_service` CHECK pins the literal `'api_gateway'`.** It is a store-side
   producer constant, never a wire field, so nothing here sends it — but adoption requires a
   Control-DDL amendment to widen it. **No DDL was applied or altered.**
3. **Two public surfaces instead of one.** Two reverse-proxy targets, two TLS terminations, two
   CORS allowlists to keep in step. Mitigated by one shared implementation and one shared
   `SP2_EDGE_ALLOWED_ORIGINS`, but it is more for an operator to get right, and each additional
   route family that stays with its owner adds another.
4. **The frontend cutover is not done.** Lovable would need two base URLs where it has one. That
   is a real (small) frontend change and it is not part of this experiment.
5. **A re-entrant call graph.** The workspace edge authenticates via the Auth Router, which reads
   the Control Plane — so the Control Plane transitively calls itself across processes. It is the
   same depth as today (2 hops) and separate processes with separate pools, but it is a topology
   smell worth a deliberate look before adoption.
6. **The internal Control-Plane read edge remains unauthenticated** and serves
   `GET /memberships?p=<principal_ref>` — the subject comes from a query parameter. This is
   **unchanged from `main`** and is why it must stay loopback-only. The public edge never exposes
   that parameter (W2), but the internal hazard is not removed, only the tenant-data one is.
7. **`api_gateway` remains in the tree**, deliberately (§8 of the instruction). Until it is
   deleted, two definitions exist for each public DTO; the parity tests are what stop them
   drifting.
8. **Rate limiting, WAF and request signing have no home yet.** The Gateway would have been the
   natural place. Under this architecture they belong in the shared kernel or the reverse proxy —
   a decision that has not been made.

---

## 14. Files that could be deleted in a later authorized cleanup PR

**Only after adoption, and only in a separate authorized PR.** Nothing was deleted here.

**Runtime — 3,821 LOC:**

* `backend/api_gateway/**` — all 21 modules (3,327 LOC): `gateway.py`, `main.py`, `portal.py`,
  `dispatch.py`, `carrier.py`, `models.py`, `ports.py`, `request_context.py`, `readiness.py`,
  `__init__.py`, and all 11 modules under `adapters/providers/`.
* `backend/database_router/adapters/providers/http_dispatch_api.py` (224 LOC) — the internal
  dispatch edge. Verified sole consumer: the Gateway's `RouterDispatchPort`. No other service
  references it (`control_plane/main.py:769` is a docstring mention only).
* `backend/database_router/adapters/providers/http_tenant_startup_api.py` (270 LOC) — the
  internal envelope edge the public edge replaces.

**Tests — 6,142 LOC:** `backend/tests/api_gateway/**` (262 tests across 25 modules).
⚠️ `tests/api_gateway/crypto_fixture.py` is the **one blessed** JWT/crypto test module
(`test_vendor_and_db_containment.py:40`, `test_b5_5_smoke_c_spec_and_crypto_fixture.py:44`). It
must be **relocated, not deleted**, and both guards updated to its new path.

**Composition seams to remove:** `build_dispatch_server_from_env`,
`build_tenant_startup_server_from_env`, `build_tenant_startup_ops_from_env`'s server half in
`database_router/main.py`.

**Guards requiring coordinated edits (they name `api_gateway` literally):** `pyproject.toml`
`[tool.importlinter]` root packages and 3 of 4 contracts; `test_phase7_api_gateway.py` (delete);
`test_gateway_edge_boundaries.py` (delete); `test_gateway_operational_audit_boundaries.py`
(delete); `test_native_uvicorn_factories.py`; `test_standing_launcher_flags.py`;
`test_07d3_multiinstance_readiness_static.py`; `test_07e3b_auth_transport_boundaries.py`;
`test_d15t1_dispatch_transport_static.py`; `test_import_write_path_boundaries.py`;
`test_ic010_control_read_adapter_boundaries.py`; `test_ic009_portal_binding_checks.py`;
`test_clm_2day_stage_b_runtime_boundaries.py`; `test_clm_dataplane_witness_boundaries.py`;
`test_b5_blk6_closure_evidence_matrix_boundaries.py`;
`test_b5_blk6_portal_binding_live_proof_boundaries.py`;
`test_deployment_composition_root_boundaries.py` (byte-pins the TOML independence contract,
including the `"api_gateway",` line); `test_traceability.py`; `test_vendor_and_db_containment.py`;
`_scan.py` `SERVICE_PACKAGES`.

⚠️ Roughly a dozen further guards would **go vacuous rather than fail** — dead ban-list entries
in `test_phase3/4/5/6`, `test_dependency_boundaries.py`, `test_dbr_composition_boundaries.py`,
`test_auth_router_composition_boundaries.py`. They would stay green while guarding nothing. A
cleanup PR must remove those entries deliberately, not leave them as false comfort.

---

## 15. Recommendation and verdict

```text
COMPLETE API GATEWAY REMOVAL — MVP ARCHITECTURE VIABLE
```

All eleven §14 success criteria are satisfied:

| # | Criterion | Status |
|---|---|---|
| 1 | no MVP runtime request depends on `api_gateway` | ✅ executed subprocess proof (GF-1, GF-1b) |
| 2 | no port 8820 Gateway edge required | ✅ GF-6 |
| 3 | Startup GET/PATCH authenticated and tenant-safe | ✅ A1–A7 |
| 4 | cross-tenant read/write mutations are caught | ✅ M1 (and M2–M5) |
| 5 | client tenant/actor fields non-authoritative | ✅ A7–A9, GF-3 |
| 6 | each MVP route has a clear owning service | ✅ §6 — no shared ownership |
| 7 | minimum MVP audit/security evidence remains | ✅ GF-5, A18, A19 |
| 8 | materially simpler than the Gateway design | ✅ 6→5 edges, 4→3 hops, −2,004 runtime LOC, dispatch layer gone |
| 9 | full isolated suite green | ✅ 2,133 passed / 0 failed |
| 10 | guards describe the new design, not weakened | ✅ 22 new guards; no guard weakened; 2 registrations; 2 existing guards obeyed after catching real defects |
| 11 | no new generic proxy under another name | ✅ GF-2 + import-linter "shared is a dependency leaf" KEPT |

**Recommendation.** The architecture is viable, materially simpler, and strictly safer in one
concrete respect: it deletes the unauthenticated tenant-data edge rather than fronting it. I
recommend adopting it **only after** three things Dan owns:

1. **ratify the IC-010 amendments** in §5 (contracts precede code — none were edited here);
2. **authorize a live two-tenant witness** on the Gateway-free topology (risk 1);
3. **decide the two-public-surface trade-off** (risk 3) and the home for rate limiting / WAF
   (risk 8).

If any of those goes the other way, keeping the Gateway remains a perfectly defensible answer —
this experiment shows removal is *possible and clean*, not that it is *obligatory*.

### Gate results

| Gate | Command | Result | Exit |
|---|---|---|---|
| full suite | `pytest -q` | **2133 passed**, 0 failed (baseline 2054 → +79) | 0 |
| architecture | `pytest tests/architecture -q` | **1058 passed** (baseline 1036 → +22) | 0 |
| gateway-free | `pytest tests/gateway_free -q` | **57 passed** | 0 |
| lint | `ruff check .` | All checks passed | 0 |
| format | `ruff format --check .` | 407 files already formatted | 0 |
| types | `mypy .` (strict) | no issues in **405** source files | 0 |
| imports | `lint-imports` | **4 kept, 0 broken** | 0 |
| secrets | `gitleaks detect --log-opts cdb46fc9..098a07ec` | **no leaks found** (2 commits) | 0 |

Secret-scan positive control: the same scanner over the full working tree reports 4 findings, all
inside the git-ignored `backend/.venv` third-party packages — so a clean result on the commit
range is a real result, not a silent no-op.

---

## 16. Stop-state proof

| Requirement | State |
|---|---|
| `main` unchanged | ✅ `cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f` — identical to the pre-experiment reading and to `origin/main` |
| experiment branch has local commits | ✅ `b6697cbb`, `098a07ec` on `experiment/complete-api-gateway-removal-mvp` |
| NOT pushed | ✅ no `git push` was run; the branch has no remote-tracking ref |
| NO PR opened | ✅ no `gh pr create`, no GitHub API write |
| NOT merged | ✅ `main` is not an ancestor-modified ref; `git diff main..HEAD` is the experiment only |
| current Gateway code not deleted from `main` | ✅ no file deleted anywhere; `backend/api_gateway/**` untouched on both branches |
| standing environment unmodified | ✅ see below |
| working tree | ✅ clean (`git status --porcelain` empty) |

**No standing/live mutation (§10), item by item:**

| Prohibited | Performed? |
|---|---|
| connect to standing PostgreSQL 5540–5543 | ❌ no — no psycopg connection was opened; the data plane is two in-memory stores |
| connect to standing Keycloak 8814 | ❌ no — authentication is a double; no OIDC/JWKS call |
| change Keycloak | ❌ no |
| create a real PKCE session | ❌ no |
| create or modify SecretRefs | ❌ no |
| create credentials | ❌ no |
| apply DDL | ❌ no — DDL 012's `source_service` constraint is *reported* as an unresolved item, not altered |
| modify standing memberships | ❌ no — the only memberships created are in a per-test `InMemoryControlStore` |
| modify roles/grants | ❌ no |
| run the standing PATCH witness | ❌ no |
| restart standing SnackPortal2 services | ❌ no |
| run the governed standing launcher | ❌ no — `backend/tools/local/start-sp2-local.ps1` was never invoked |
| run the old scratch launcher | ❌ no |

The only sockets bound were **ephemeral loopback ports (`port=0`) opened and closed by the tests
themselves**, plus loopback ports deliberately left *unbound* to exercise connection-refused paths.

> **A positive experiment result is not merge authorization.**
> Only Dan may decide whether to integrate this. Even after a successful experiment: present the
> result, obtain separate authorization before any push or PR, independently review the proposed
> architecture, and obtain explicit authorization for the specific PR merge. Only a human-authorized
> merge may change `main`. No Claude or GPT verdict, test result, or recommendation substitutes for
> that authorization.
