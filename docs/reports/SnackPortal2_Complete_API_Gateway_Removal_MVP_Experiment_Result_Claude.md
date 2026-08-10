# SnackPortal2 — Complete API Gateway Removal MVP Experiment — Result

**Instruction:** `SnackPortal2_Complete_API_Gateway_Removal_MVP_Experiment_GPT.md`
**Branch:** `experiment/complete-api-gateway-removal-mvp` · **Base:** `origin/main` = `cdb46fc9`
**Date:** 2026-08-10 · **Author:** Claude (Opus 5)

---

## VERDICT

> ## `COMPLETE API GATEWAY REMOVAL — EXPERIMENT INCONCLUSIVE`
>
> **A Gateway-free MVP was built and its request path is proven safe. It is not yet
> recommendable, because removing the Gateway also removes a privilege boundary that was
> never part of the brief — and that consequence is unmitigated.**

Both halves of that sentence are load-bearing, so state them separately.

**What the experiment proved.** The MVP runs with **no `api_gateway` module imported,
instantiated or launched** — proved by executing a clean subprocess and asking the interpreter
what it loaded, not by reading source. Nothing replaced the Gateway with a proxy under another
name: the two MVP route families are served by the services that already own their records, and
each enforces its own public boundary **in-process** through a shared library that import-linter
proves cannot reach any service. An independent adversarial review could not construct **any**
request — header, duplicate header, body, query, cookie, path, Host, absolute-form target — that
opened the wrong tenant database or changed the recorded actor.

**What stops it being a recommendation.** On `main` the only internet-facing process is the
Gateway, and it is *structurally incapable* of touching a database: driver containment permits
DB drivers only under `database_router/adapters/providers/` and
`control_plane/adapters/providers/`, and every Gateway selector is non-secret routing config.
Compromise it and you get no database access at all. After removal, both public processes are
composed **inside** those credential-holding zones — one holds every tenant DSN plus a psycopg
factory, the other holds the Control DB plus the provisioning-admin credential and the services
that create and drop tenant databases, to serve one read-only route.

**The Gateway was a privilege boundary as well as a request boundary.** In-process execution is
what removes the hop, and it is the same thing that collapses that tier. I did not see this
until an independent review pointed at it; it is now pinned by tests (GF-8/GF-8b) rather than
left as an omission. Resolving it is bounded, isolated, additional work — which is precisely
the condition §14 names for this verdict.

### Why this succeeded where the previous experiment did not

The previous experiment (`experiment/remove-api-gateway`, `009fa268`) concluded
`NOT VIABLE WITHOUT REPLACEMENT CONTROLS`, reasoning that the replacement controls had only
three possible homes:

> 1. Inside `database_router` — contract violation (measured).
> 2. A new component in front of the Startup API — that component *is* the API Gateway.
> 3. Nowhere — the naive result.

**That trichotomy is incomplete, and its first item was measured against the wrong
construction.** Option 1 was measured as broken because the probe added `import auth_router`
*in-process*. That is a violation — but it is not how the Gateway consumes authentication
either. The Gateway calls the Auth Router over the existing internal HTTP transport, and so does
this experiment. `lint-imports` reports **4 contracts kept, 0 broken**.

The missing fourth home:

> **4. In a shared, service-agnostic LIBRARY, linked in-process by each route-owning service.**

A gateway is a runtime component standing *between* a client and the service owning the data. A
linked library is *inside* it — there is no "between". And the distinction is machine-checkable,
not rhetorical: `shared` is a dependency leaf under an existing, unmodified import-linter
contract, so `shared/public_edge.py` structurally cannot import, name, reach or forward to any
service. A gateway's defining act is unavailable to it by construction.

---

## 1. Exact branch / base identity

Recorded **before any edit**, per §3:

| Item | Value |
|---|---|
| worktree | `D:\Pitchsnack\SnackPortal2_pr111_verify` |
| `git rev-parse origin/main` | `cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f` |
| `git rev-parse main` | `cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f` |
| `git ls-remote origin refs/heads/main` | `cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f` |
| `git rev-parse HEAD` (before) | `009fa268…` (the previous experiment — **not** used as a base) |
| `git status --porcelain` | *(empty — clean)* |
| gate `origin/main == main` | ✅ |
| gate `working tree clean` | ✅ |

Branch created **from `cdb46fc9`**. Independently re-verified after the fact:
`git merge-base main HEAD` = `cdb46fc9`; `git merge-base --is-ancestor 009fa268 HEAD` = **false**;
none of the previous experiment's files (`backend/experiments/`, `tests/experiment/`) exist in
this tree. It was read as evidence only, via `git show`.

**Commits (all local):**

| SHA | Subject |
|---|---|
| `b6697cbb` | Gateway-free MVP architecture (no production change) |
| `098a07ec` | prove the public response contract is byte-identical to the Gateway's |
| `105f5c32` | result document (repo-resident evidence copy) |
| `e86624d3` | remove standing-port literals from the composition tests |
| `3d4d8cd4` | fix defects found by an independent adversarial review |

---

## 2. Current MVP route inventory and classification

The Gateway's *core* classifies four path families; its *served edge* exposes far fewer. That
gap matters: two dispatch categories are **dead surface on `main`**, not capabilities dropped here.

| Route (as served on `main`) | Classification | Owner after removal |
|---|---|---|
| `GET /tenant/startups/<startup_ref>` | **MVP REQUIRED — MOVED TO OWNING SERVICE** | Database Router |
| `PATCH /tenant/startups/<startup_ref>` | **MVP REQUIRED — MOVED TO OWNING SERVICE** | Database Router |
| `GET /memberships` | **MVP REQUIRED — MOVED TO OWNING SERVICE** | Control Plane |
| `GET /health`, `GET /readiness` | **MVP REQUIRED** | each edge, per-edge |
| `OPTIONS` preflights | **MVP REQUIRED** | each edge |
| `POST /import/<source_ref>` | **MVP NOT REQUIRED — DEFER** | — |
| `GET /directory/<kind>` (core category only) | **REMOVE FROM MVP** | — |
| generic `TENANT_OPERATION` router hand-off | **REMOVE FROM MVP** | — |

**Evidence for the removals.** `_EXPOSED_ROUTES` (`http_gateway_edge.py:90-94`) is exactly
`{/memberships, /health, /readiness}` plus the two bounded parameterized families. **No
`/directory` route is registered**, so `GLOBAL_DIRECTORY_READ` (`dispatch.py:47`) and its
Control-Plane branch (`gateway.py:330-332`) are unreachable through the served edge on `main`.
The generic router hand-off (`gateway.py:432`) is likewise unreachable once the CLM
tenant-Startup port is composed, which the governed standing map does.

**Evidence for deferring import.** `docs/runbooks/backend_service_startup_fastapi.md:80-83`:
Import Service, Import Audit ingest and Routing Audit ingest are *deliberately absent* because
"Import is outside the controlled local MVP journey (IMPORT-A / D-3)". Deferring it changes
nothing that runs.

---

## 3. Proposed Gateway-free architecture

```text
BEFORE — 6 documented edges, 1 public surface, 4 internal hops per business request
  browser ──▶ API Gateway 8820 ──┬──▶ Auth Router 8001 ──▶ Control Plane read 8003
                                 ├──▶ Control Plane read 8003        (memberships data)
                                 ├──▶ Tenant Startup API 8004 ──▶ one tenant database
                                 ├──▶ DB Router dispatch 8002        (no served route reaches it)
                                 └──▶ audit ingest 8005

AFTER — 5 edges, 2 public surfaces, 3 internal hops per business request
  browser ──┬─▶ Tenant Startup edge 8830 ─┬─▶ Auth Router 8001 ──▶ Control Plane read 8003
            │                             ├─▶ Control Plane read 8003   (routing view, cold cache)
            │                             ├─▶ one tenant database       (IN-PROCESS)
            │                             └─▶ audit ingest 8005
            └─▶ Workspace edge 8831 ──────┬─▶ Auth Router 8001 ──▶ Control Plane read 8003
                                          ├─▶ Control DB                (IN-PROCESS)
                                          └─▶ audit ingest 8005
```

*(The routing-view read is drawn explicitly: `SP2_DBR_ROUTING_READ_BASE_URL` is required for the
Startup edge and `RoutingResolver.resolve` calls it on every cache miss. The 4→3 hop count is a
warm-cache steady-state count and says so.)*

**Ownership resolved (§4 candidate comparison).**

| Candidate | Verdict |
|---|---|
| **A — Tenant Startup edge becomes a real authenticated public MVP edge** | **ADOPTED** for the tenant route family. |
| **B — Database Router owns the authenticated Startup HTTP edge** | **ADOPTED**, with the `Authentication ≠ Routing` question answered rather than dodged (§5.3). The Database Router *consumes* IC-005 authentication through an injected transport port; it performs none. |
| **C — another existing domain service owns its own public route** | **ADOPTED** for `/memberships`: the Control Plane owns the records, so it serves them. |
| **New generic MVP/BFF/edge gateway** | **REJECTED and structurally prevented** (GF-2 + import-linter). |

---

## 4. Files changed

**21 files, +5,180 / −6 across five commits.** No file deleted; no Gateway source touched
(`git diff --stat cdb46fc9..HEAD -- backend/api_gateway/` is empty).

| File | Δ | Nature |
|---|---:|---|
| `backend/shared/public_edge.py` | +530 | **NEW** — the public-boundary security kernel (library) |
| `backend/shared/adapters/providers/public_edge_transport.py` | +193 | **NEW** — shared browser-facing transport gate |
| `backend/shared/adapters/providers/http_principal_authenticator.py` | +145 | **NEW** — IC-005 authenticate transport client |
| `backend/shared/adapters/providers/edge_audit.py` | +213 | **NEW** — in-memory + durable sinks, bounded retry, CLM partition |
| `backend/database_router/portal.py` | +111 | **NEW** — owner-resident IC-009-R1 DTO + bounded parser |
| `backend/database_router/adapters/providers/http_public_startup_edge.py` | +347 | **NEW** — the public tenant Startup edge |
| `backend/control_plane/portal.py` | +74 | **NEW** — owner-resident IC-009-R1 membership DTO |
| `backend/control_plane/adapters/providers/http_public_workspace_edge.py` | +263 | **NEW** — the public workspace edge |
| `backend/database_router/main.py` | +105 | composition seams + five selectors |
| `backend/control_plane/main.py` | +98 | composition seams + five selectors |
| `backend/tests/gateway_free/**` (6 files) | +1,797 | 63 tests |
| `backend/tests/architecture/test_gateway_free_mvp_boundaries.py` | +664 | 27 architecture guards |
| `backend/tests/architecture/test_07d3_multiinstance_readiness_static.py` | +26/−6 | **the only pre-existing test modified** — §5.7 |
| `docs/runbooks/gateway_free_mvp_topology.md` | +129 | the documented experimental topology (guard-bound) |
| `docs/reports/…Result_Claude.md` | +… | this document, repo-resident |

**Runtime LOC added: 2,079.** *(An earlier draft said 1,817 — that was the sum of the eight NEW
files and silently dropped the 203 lines added to the two composition roots, which are runtime
code. Corrected after review.)* **Test LOC added: 2,461.**

---

## 5. Architecture contracts changed

No contract file was edited. Contracts precede code; ratifying an amendment is Dan's decision.
What follows is the amendment set adoption would require, in the format §9 mandates.

### 5.1 IC-010 §A / §C / §I / §M / §N — the "sole ingress" family

**CURRENT.** §A "sole approved ingress"; §C "**No alternate flow is permitted**"; §I portals
"MUST access backend services **only through the API Gateway**"; §M all services "reachable
**only through the API Gateway** for client/portal ingress, *unless explicitly governed
otherwise*"; §N "all client channels … gateway-only ingress".

**PROPOSED.** The *boundary* is retained, the *component* is not. Every public request is still
authenticated, carrier-validated, given a tenant context from the signed claim, and turned into
a trusted context before any service logic — enforced by the route-owning service, in-process,
through one shared kernel. An "approved public edge" is a service edge that (a) links
`shared.public_edge`, (b) derives all tenant and actor authority from `TrustedPrincipal`,
(c) serves exactly one route family it owns, and (d) forwards no business request to any service.

**WHY SAFE.** These clauses protect a *property* — no client path reaches a service or a database
without authentication, carrier validation and one-tenant binding. They name a *component* only
because one component was how that property was achieved when they were written. The property is
preserved literally, now enforced by shared code that cannot be bypassed per-edge because there
is only one implementation of it. §K/§O/§X isolation mechanics survive untouched.

**NEW TEST.** GF-1/GF-1b (executed: zero `api_gateway` modules loaded), GF-2/2b/2c (library, one
route family per edge), GF-6 (no Gateway edge, no 8820), GF-7 (canonical flags on both public
edges), adversarial A1–A20.

**POST-MVP CONSEQUENCE.** Every new public route must be born inside its owning service and link
the kernel. There is no longer one place to add a cross-cutting concern, so rate limiting, WAF
and request signing must go into the shared kernel or the reverse proxy. Note also that the new
guards are a **hard-coded two-file census**: a third public edge would be unguarded until added.

### 5.2 IC-010 §R — Internal-Surface Protection: **PRESERVED**

The internal Auth Router (8001), Control-Plane read (8003) and audit ingest (8005) remain
internal, and neither public edge exposes any `/internal/...` target (A20c).

**What is NOT claimed.** An earlier draft said §R was "strengthened" because the unauthenticated
`POST /internal/tenant/startups/*` edge is "deleted, not fronted". That is false and has been
corrected. The MVP topology does not **launch** that edge — but the module, its factory and its
serve entrypoint all remain, its composition gate is the **same variable** the public edge
requires, and the standing launcher still starts it on 8004. *Not launched* is a topology choice;
*deleted* would need the later cleanup PR. Pinned by `test_a20d_KNOWN_RESIDUAL_…`, a test that
exists specifically to stop the weaker claim rotting into the stronger one.

### 5.3 IC-010 §H — "The Database Router never authenticates": **PRESERVED**

The instruction anticipated this rule might have to change. It does not.

The Database Router's *public edge adapter* consumes authentication through an injected port
reaching the Auth Router over the existing internal transport. The routing core receives a
completed trusted context and nothing else.

**MACHINE-CHECKED (GF-4/GF-4b).** No sibling service and no `jwt`/`jose`/`authlib`/`oauthlib`/
`oidc`/`cryptography` import anywhere in `database_router`. The four routing/resolution modules
contain no authentication identifier at all. The edge holds exactly **one** `boundary.admit` site
and **one** `require_tenant` site. The pre-existing separation guards are unmodified and green.

**POST-MVP CONSEQUENCE.** None for this rule. Worth redrafting to "performs no authentication"
rather than "is never reached by an authentication call", so consuming-vs-performing is explicit.

### 5.4 IC-010 §J — the audit emitter

**CURRENT.** "The API Gateway is the **emitter**"; "the **sole emitter** of this success event".
**PROPOSED.** The **route-owning public edge** is the sole emitter of its own route's events.
**WHY SAFE.** No audit class added, removed, renamed or re-homed — only the emitter changes.
GF-5b asserts the vocabulary **equals** `GATEWAY_AUDIT_STORE_ACTIONS` exactly, so the Control-DB
home and DDL 012's CHECK are untouched. "Single edge" is preserved literally.
**NEW TEST.** GF-5b, GF-5c, A18, A18b, A19.
**POST-MVP CONSEQUENCE.** DDL 012's `source_service` CHECK pins the literal `'api_gateway'`. It
is a store-side constant, never a wire field, so nothing here sends it — adoption needs that
CHECK widened. **No DDL applied or altered.**

### 5.5 IC-010 §V — response composition

**CURRENT.** "**Gateway-owned and typed** composition."
**PROPOSED.** **Owner-owned and typed**: the route's owner constructs its own adopted-contract
DTO from values it validated. Every other §V.1 condition and every §V.2 prohibition unchanged.
**WHY SAFE.** This clause *fixes* the previous experiment's §8 finding — that bypassing the
Gateway silently collapsed the eight-field `TenantStartupDetailDTO` into the five-field internal
envelope, losing the D-37 §10 provenance triple.
**NEW TEST.** `test_response_contract_parity.py` (5 tests): field names, field **order** and
defaults must equal the Gateway's; serialization must produce **identical bytes**; both served
responses are compared against the contract composition.
**POST-MVP CONSEQUENCE.** Two DTO definitions per shape exist until the Gateway is deleted. The
parity tests keep them from drifting.

### 5.6 Canonical Overview Part 2 — locked invariant #7

**CURRENT.** "**The Gateway is the boundary.**"
**PROPOSED.** "**The authenticated public edge is the boundary** — the frontend reaches only
route-owning public edges, never a database, an internal read API, or a router directly."
**POST-MVP CONSEQUENCE.** This is a **locked invariant**; changing it needs sign-off. This
experiment does not change it — it reports that adoption would.

### 5.7 The one pre-existing test modified

`test_07d3_multiinstance_readiness_static.py` maintains a census of modules permitted to contain
a `serve_forever` loop, keyed to the single named entrypoint each may use. Two entries were added
for the two new public edges.

This is a registration, not a weakening: the census exists to be the registry, its strength is
the *per-module rule*, and that rule is applied to the new entries by the same test
(`_single_blessed_serve_problems` runs over every entry). `ThreadingHTTPServer` stays banned
everywhere, the non-vacuity companion still flags an unauthorized reference, and the exhaustive
set literal is still asserted. A stale count in an adjacent comment was corrected.

Two further existing guards **caught real defects in this experiment's code and were obeyed, not
edited**: the loopback-literal guard rejected a `127.0.0.1` default inside the security kernel,
and the serve-loop census rejected the unregistered edges.

---

## 6. Security ownership matrix

Per §11 — no question has two answers, and no answer is "the Gateway".

| Question | `GET`/`PATCH /tenant/startups/<ref>` | `GET /memberships` |
|---|---|---|
| who authenticates it | `PublicBoundary.admit` → injected IC-005 port → Auth Router | same |
| who authorizes tenant access | Auth Router Stage 2 (membership + readiness) | same |
| who derives tenant identity | `PublicBoundary.require_tenant` — signed claim only, one call site | n/a (control-scoped; subject is the authenticated principal) |
| who owns HTTP validation | `database_router…http_public_startup_edge` | `control_plane…http_public_workspace_edge` |
| who maps the public response shape | `database_router.portal` | `control_plane.portal` |
| who records audit evidence | the edge, via `EdgeAuditPort` | same |
| who selects the physical database | `TenantStartupOperations` → `RoutedSessionProvider` (D-07) | the Control Plane's per-request unit of work |

**The load-bearing invariant.** `target_tenant_ref` and `actor_ref` are **not request inputs**.
GF-3 checks this in two positions, because the same word is lawful in one and fatal in the other:
as a **string literal** it would be a lookup key into caller-supplied data (banned outright —
the exact shape of the internal edge's defect); as a **keyword argument** it is an output handed
down to the executor, lawful only if its value comes from `principal.principal_ref` or
`require_tenant`'s result, asserted by AST dataflow.

`PublicRequest` — the kernel's view of a request — has **no body, query or cookie field at all**.
The cheapest way to guarantee the kernel never reads a prohibited carrier is not to hand it one.

**One field a client CAN influence, stated explicitly:** `correlation_id`. A bounded,
charset-restricted (`[A-Za-z0-9._-]{1,128}`) inbound `x-correlation-id` is accepted verbatim,
echoed, and recorded on that request's audit events. It carries no authority — it selects no
tenant, principal or database — and the charset makes log injection impossible, but an attacker
can choose the correlation value on their own evidence records. Same behaviour as the Gateway.

---

## 7. Gateway responsibility reduction

The previous experiment enumerated **33** responsibilities. Each is classified per §7.

### Serving edge (12)

| # | Responsibility | Classification | Where it lives now |
|---|---|---|---|
| 1 | Closed route + method allowlist | **MVP ESSENTIAL** | each edge's own routes (one family each) |
| 2 | Decisions against the RAW request target | **MVP ESSENTIAL** | `raw_request_target` |
| 3 | Query-string rejection | **MVP DEFENCE-IN-DEPTH** | shared gate — *reclassified by executed evidence, M6* |
| 4 | Bounded traversal-safe parameterized matcher | **MVP ESSENTIAL** | `is_valid_tenant_startup_target` (A12, M5) |
| 5 | Request bounds | **MVP ESSENTIAL** | shared gate (A13) |
| 6 | Correlation accept/mint/echo | **MVP ESSENTIAL** | shared gate (A17, M11, M11b) |
| 7 | Exact-origin CORS + preflights | **MVP ESSENTIAL** | shared gate (A16, M10) |
| 8 | `Cache-Control: no-store` | **MVP ESSENTIAL** | shared gate |
| 9 | No slash-redirect, no OpenAPI/docs | **MVP ESSENTIAL** | inherited from `new_edge_app` |
| 10 | Denial-fidelity terminal | **MVP ESSENTIAL** | each edge |
| 11 | Exactly ONE core call site | **OBSOLETE** | no core to call once; each edge has one `admit` site |
| 12 | Minimal header forwarding; `X-Forwarded-*` untrusted | **OBSOLETE** | nothing is forwarded (inbound half survives via #13) |

### Gateway core (17)

| # | Responsibility | Classification | Where it lives now |
|---|---|---|---|
| 13 | Carrier extraction | **MVP ESSENTIAL** | `recognized_carriers` (A7, M4) |
| 14 | Straddle check | **MVP ESSENTIAL** | `PublicBoundary.admit` (A11c, A11d, **M12**) |
| 15 | Authentication handoff to IC-005 | **MVP ESSENTIAL** | `PrincipalAuthenticatorPort` — *previously UNRESOLVED; resolved by the library home* |
| 16 | `CarrierOnControlAnomaly` | **MVP DEFENCE-IN-DEPTH** | `admit` (A10c) |
| 17 | Context built EXCLUSIVELY from `AuthContext` | **MVP ESSENTIAL** | `TrustedPrincipal` — *also previously UNRESOLVED; resolved* |
| 18 | Dispatch classification | **OBSOLETE** | nothing dispatches |
| 19 | `decide()` — TENANT requires a signed tenant | **MVP ESSENTIAL** | `require_tenant` (A10b, M2) |
| 20 | `assert_single_database()` | **MVP ESSENTIAL** | `require_tenant` (A11) |
| 21 | Bounded PATCH validation before any port call | **MVP ESSENTIAL** | owner parser (A13b, M7, M8) |
| 22 | Control-Plane read composition | **MOVED TO OWNING SERVICE** | Control Plane, in-process |
| 23 | Import composition + zero-record denial | **POST-MVP / DEFER** | outside the CLM journey |
| 24 | §L fail-closed mapping | **MVP ESSENTIAL** | `PublicBoundaryDenied` (GF-5) |
| 25 | Portal DTO composition incl. provenance triple | **MVP ESSENTIAL** | owner `portal.py`, byte-identical |
| 26 | Audit emission (7 classes, dedup, before-hand-back) | **MVP ESSENTIAL** | `PublicBoundary.emit` (A18, A19, M9) |
| 27 | Metrics recording | **POST-MVP / DEFER** | no MVP journey depends on it |
| 28 | Correlation minting inside the core | **OBSOLETE** | minted once, at the transport gate |
| 29 | Operation-key idempotency | **POST-MVP / DEFER** | import-only concern |

### Composition root (4)

| # | Responsibility | Classification | Where it lives now |
|---|---|---|---|
| 30 | Fail-closed env transport selectors | **MVP ESSENTIAL** | `internal_base_url_from_env` — **one** implementation instead of six near-copies |
| 31 | Composition-gate-first; `RuntimeError` when inactive | **MVP ESSENTIAL** | both edges (A14, A15) |
| 32 | Tenant-Startup transport selection | **OBSOLETE** | the executor is in-process |
| 33 | Durable audit partition | **MVP ESSENTIAL** | `edge_audit.py` (GF-5c) — *also previously UNRESOLVED; resolved* |

**Tally (33): 22 MVP ESSENTIAL · 2 MVP DEFENCE-IN-DEPTH · 3 POST-MVP/DEFER · 5 OBSOLETE ·
1 MOVED TO OWNING SERVICE.** So **24 controls are carried forward**, not the 21 an earlier draft
claimed (that draft said 19 ESSENTIAL / 4 DEFER / 2 MOVED and double-counted the reclassified
row; the errors happened to sum to 33). The corrected figure makes §7's own conclusion stronger,
not weaker: *more* of the Gateway's controls are still needed than I first stated. The difference
from the previous experiment is not that fewer controls are required — it is that they now have a
lawful home.

---

## 8. Test implementation

| Suite | Tests | LOC | What it proves |
|---|---:|---:|---|
| `test_adversarial_boundary.py` | 40 | 768 | the 20 required proofs (A1–A20, with sub-cases) + the workspace edge's boundary |
| `test_mutation_non_vacuity.py` | 13 | 431 | each load-bearing control fails under a real defect (M1–M12) |
| `test_env_composition.py` | 5 | 123 | the REAL transport clients compose from env and fail closed |
| `test_response_contract_parity.py` | 5 | 130 | byte-identical public responses vs the Gateway's DTOs |
| `_fakes.py` | — | 345 | two physically distinct tenant stores + an IC-005-shaped identity double |
| `test_gateway_free_mvp_boundaries.py` | 27 | 664 | GF-1…GF-8 with a non-vacuity probe each |
| **Total** | **90** | **2,461** | matches the suite delta exactly: 2144 − 2054 = 90 |

**Doubles and their limits, stated because the review found the first version overstated them.**
There are **three** doubles, not two: the identity provider (`FakeAuthRouter`), the database
(`TwoTenantProvider`), and the audit sink (`RecordingAudit`). Everything else is the real
runtime, served over real loopback sockets. Three known limits:

* `TwoTenantProvider` keys stores by `tenant_id` directly, so `provider.opened` proves *the right
  tenant id was requested*, not *the right database was resolved*. A defect in the registry
  association mapping would be invisible to it. Read A5/A6 as "no ACME tenant-id was passed";
* `FakeAuthRouter` has a single membership check, whereas the real `TenantContextResolver` makes
  two independent lookups and only then collapses them. "Unknown tenant and non-member are
  indistinguishable" is therefore true *by construction of the double*; that property belongs to
  `auth_router`'s own tests, and A10 now says so;
* A19's fail-closed proof rests on `RecordingAudit` raising. The composed default sink
  (`InMemoryEdgeAudit`) never raises, so with `SP2_EDGE_AUDIT_SINK_BASE_URL` unset — the
  documented default — that path cannot execute. A19 is a **kernel** property, not a deployed
  system property.

---

## 9. Adversarial and mutation results

### 9.1 The twenty required proofs

| # | Requirement | Test | Result |
|---|---|---|---|
| 1 | anonymous Startup GET denied | `a1` | ✅ 401, empty body, `opened == []` |
| 2 | anonymous Startup PATCH denied | `a2` | ✅ 401, no mutation |
| 3 | valid ACME principal reads ACME | `a3` | ✅ 200, one ACME session |
| 4 | valid ACME principal writes ACME | `a4` | ✅ write lands in ACME, ZETA untouched |
| 5 | valid ZETA principal cannot read ACME | `a5` | ✅ 404; **no ACME session opened** |
| 6 | valid ZETA principal cannot write ACME | `a6` | ✅ ACME record byte-unchanged |
| 7 | `X-Tenant-Id` cannot switch databases | `a7`, `a7b` | ✅ 403 `carrier_mismatch`, nothing opened |
| 8 | JSON `target_tenant_ref` cannot switch databases | `a8` | ✅ 403 pre-executor |
| 9 | JSON `actor_ref` cannot impersonate | `a9`, `a9b` | ✅ recorded actor is always the authenticated principal |
| 10 | non-member denial reveals nothing | `a10`, `a10b`, `a10c` | ✅ **scoped honestly** — the unknown-tenant leg is not provable through this double, and the test says so |
| 11 | one tenant DB session per accepted request | `a11`, `a11c`, `a11d`, `a11e` | ✅ incl. two genuine straddle shapes rejected **pre-authentication** |
| 12 | malformed reference fails before DB access | `a12` | ✅ 7 forms refused before authentication is attempted |
| 13 | oversized PATCH fails before mutation | `a13`, `a13b` | ✅ 413 pre-handler; over-bound value 403 pre-executor |
| 14 | missing auth configuration fails closed | `a14`, `a14b` | ✅ no boundary → no edge composes |
| 15 | missing routing configuration fails closed | `a15`, `a15b` | ✅ no composition, no socket |
| 16 | CORS permits only configured origins | `a16`, `a16b` | ✅ exact-origin only, never wildcard/credentialed |
| 17 | correlation id bounded and usable | `a17` | ✅ accepted/minted/echoed; reaches the audit record |
| 18 | minimum MVP audit evidence emitted | `a18`, `a18b` | ✅ exactly one event per operation, references only |
| 19 | audit failure follows the stated policy | `a19` | ✅ **fail-CLOSED** at the kernel — see the §8 limit |
| 20 | internal edge cannot bypass the boundary | `a20`, `a20b`, `a20c`, `a20d` | ✅ **rewritten after review** — see 9.3 |

### 9.2 Mutation results

Each mutation is applied to the **executed** decision function; every one was observed FAILING
before the fix that made it pass.

| # | Mutation | Detected? | Detector |
|---|---|---|---|
| M1 | `require_tenant` trusts the carrier | ✅ | ZETA principal reads ACME; `(t-acme, p-zeta)` in `opened` |
| M2 | `require_tenant` defaults a tenantless principal | ✅ | CONTROL principal opens a tenant DB |
| M3 | `admit` stops denying | ✅ | anonymous caller opens a tenant DB |
| M4 | carriers dropped before the authenticator | ✅ | disagreeing carrier accepted; evidence disappears |
| M5 | bounded matcher disabled | ✅ | unsafe-charset reference reaches a real tenant session |
| M6 | query-string rejection removed | **SURVIVED — reclassified** | see below |
| M7 | update parser accepts extra fields | ✅ (partial, and the partiality is the finding) | body channel re-opens; tenant still the signed claim |
| M8 | field length bound removed | ✅ | refusal moves from edge (403) to executor (503) |
| M9 | audit made fail-open | ✅ | record served with an empty evidence set |
| M10 | CORS widened to a wildcard | ✅ | wildcard grant reaches an unlisted origin |
| M11 | unbounded correlation id accepted | ✅ | 400-char caller id echoed verbatim |
| M12 | **headers collapsed into a mapping** | ✅ | **the straddle control goes dark** — see 9.3 |

**M5 required choosing the right probe.** An *over-bound* reference is re-validated by
`TenantStartupOperations` before it opens a session, so a session-based detector alone would have
missed the defect and a naive reading would conclude "the matcher is redundant". The probe is an
*unsafe-charset* reference, which the executor does **not** re-validate. Both halves are asserted.

**M6 is a negative result that changed a classification.** With the branch removed from the
executed middleware, neither MVP route becomes exploitable: on the parameterized route the
bounded matcher decides against the RAW target and `?` is outside its charset; on the static
route the query becomes reachable but no handler reads one, so `?p=<someone-else>` returns the
**caller's own** memberships. Recorded as **DEFENCE-IN-DEPTH** on executed evidence.

### 9.3 Independent adversarial review — what it found, and what changed

A seven-agent independent review was run against this experiment's own claims, instructed to
refute rather than confirm. It **could not construct a tenant-authority bypass** and found **no
standing-environment mutation** (verified with a C-level `sys.addaudithook` over the whole
suite). It found real defects. All are fixed in `3d4d8cd4`; the significant ones:

| Finding | Severity | Status |
|---|---|---|
| The straddle check was **structurally unreachable** for two `X-Tenant-Id` headers: the edges passed `dict(request.headers)`, which keeps only the first value | MAJOR | **FIXED** — raw ASGI header list; A11c/A11d/A11e + mutation M12 |
| **GF-1b was blind**: `sys.path.insert(0, "tests")` let EMPTY test stub packages shadow the production ones, so its `sys.modules` census could not see a dependency in a service `__init__.py`. Proved by A/B mutation | MAJOR | **FIXED** — appends instead; re-verified by executed mutation; new guard with a negative control |
| `test_a20c` probed with a body, so all five probes were 413'd pre-routing — the same status an existing route returns. It passed against an app with the internal envelope route **registered and leaking** | MAJOR | **FIXED** — body-less probes + positive control |
| `test_a20` asserted that a **docstring contained a word**; it passed while the internal edge ran alongside | MAJOR | **FIXED** — AST assertions, plus `a20d_KNOWN_RESIDUAL` |
| "the hazard is deleted rather than fronted" was **false** — the internal edge still composes under MVP env and the launcher still starts it on 8004 | MAJOR | **CORRECTED** everywhere; pinned by `a20d` |
| `test_a11b` was named for a straddle but tests a mismatch (and its own assertion proved authentication *was* reached) | MAJOR | **FIXED** — renamed; genuine straddles added |
| Requirement 10 is true by construction of the double | MAJOR | **RESCOPED** — A10 now states the limit |
| The two public edges sat **outside** the canonical-uvicorn-flag census — the only place `--no-proxy-headers` / `--no-server-header` / `--no-access-log` / `--host 127.0.0.1` are enforced | MAJOR | **FIXED** — command blocks in the topology doc + GF-7 |
| **The public tier goes from zero database credentials to all of them** | **CRITICAL** | **NOT FIXED — inherent.** Pinned by GF-8/GF-8b; drives the verdict and §13 risk 1 |
| Headline numbers overstated: LOC 1,817→2,079; "6→5 edges" is 5→5 for MVP-serving; §7 tally wrong in three buckets | MAJOR | **CORRECTED** in §4, §7, §10, §12 |
| `correlation_id` is client-supplied; post-admission denials carry no audit event; an empty `?` is served | MINOR ×3 | **CORRECTED** in the docstrings that overclaimed |

---

## 10. Comparison to current `main`

| Capability | Current Gateway architecture | Gateway-free MVP | Safe? | Simpler? | Evidence |
|---|---|---|---|---|---|
| documented runtime edges | 6 | **5** | = | yes | topology; GF-6 |
| **MVP-serving** edges | **5** (8002 is dead weight today) | **5** | = | **no change** | §2; M-1 |
| standing ports | 6 | 5 | = | yes | GF-6 |
| **public surfaces** | **1** | **2** | **worse** | **no** | §13 risks 1, 3 |
| **public tier DB credentials** | **none — structurally** | **all tenant DSNs + Control DB + provisioning admin** | **materially worse** | — | **GF-8/GF-8b** |
| internal hops per request (warm cache) | 4 | **3** | = | yes | §3 |
| route ownership | one component owns 3 families whose data it does not hold | each family owned by the service holding its records | = | yes | §6 |
| authentication path | browser → GW → AR → CP | browser → edge → AR → CP | = | = | A1–A3 |
| tenant derivation | `RequestContext` from `AuthContext` only | `TrustedPrincipal` from the auth port only | = | = | A7–A9; GF-3 |
| tenant isolation | one request → one category → one DB | one request → one authenticated tenant → one DB | = | yes (no category layer) | A5, A6, A11; M1 |
| DB routing | GW → HTTP → 8004 → router | edge → router (in-process) | = | yes | A11 |
| Startup GET / PATCH | served, 1 internal hop to data | served, 0 internal hops to data | = | yes | A3, A4 |
| memberships | GW composes from a CP read over HTTP | CP composes from its own unit of work | = | yes | W2, W3 |
| import | served route, port-gated | deferred (already outside the CLM journey) | = | yes | runbook §2.1 |
| audit | 7 classes, 5 durably homed, fail-closed | **identical**; emitter changes only | = | = | GF-5b/5c, A18, A19 |
| CORS | exact-origin, no wildcard | **identical**, shared implementation | = | = | A16, M10 |
| correlation | accept/mint/echo, bounded | **identical**, shared implementation | = | = | A17, M11 |
| response DTO | Gateway-composed, 8 fields | owner-composed, **byte-identical** | = | = | parity tests |
| startup fail-closed | gate-first, `RuntimeError` when inactive | **identical**, both edges | = | = | A14, A15 |
| env selectors | 6 near-duplicate implementations | **1** shared implementation | = | yes | A14b |
| runtime LOC | 3,327 (`api_gateway`) + 494 (2 internal edges) | **2,079** | = | **yes: −1,742**, or **−1,518** if the already-dead dispatch edge is not credited | §4 |
| architecture-test volume | 262 tests / 6,142 LOC | 90 tests / 2,461 LOC | — | **not a simplicity measure** — see below | §8 |
| operator complexity | 1 public TLS/CORS target; 6 processes | 2 public TLS/CORS targets; 5 processes | = | mixed | §13 |

*The test-volume row is not evidence of simplicity.* `tests/api_gateway` is the accumulated
coverage of a shipped component; 90 is what one experiment added. Fewer tests over a surface that
just acquired database credentials is a gap, not a saving. The row is retained for completeness
with its `Safe?` cell blank.

---

## 11. Routes and features deferred from the MVP

| Item | Disposition | Reason |
|---|---|---|
| `POST /import/<source_ref>` | **DEFER** | Already outside the controlled local MVP journey (IMPORT-A / D-3). |
| `GET /directory/<kind>` | **REMOVE** | No served Gateway route exposed it — dead surface on `main`. |
| generic `TENANT_OPERATION` hand-off | **REMOVE** | Reachable only through the dispatch fall-through. |
| Gateway request metrics | **DEFER** | Standing default is a no-sink; nothing depends on it. |
| `x-operation-key` idempotency | **DEFER** | Import-only concern (one call site, inside the import branch). |
| `CONTROL`-on-behalf-of-subject memberships | **DEFER** | Contract-preserved, never runtime-bound; the query selector is unreachable (W2). |
| Governed Sharing (IC-007) | **DEFER** | Authored-but-inert on `main`; unchanged. |

---

## 12. Runtime edges and ports before / after

| | Before | After |
|---|---|---|
| documented edges | 6 | **5** |
| **MVP-serving edges** | **5** | **5** |
| standing ports | 8001, 8002, 8003, 8004, 8005, **8820** | 8001, 8003, 8005, **8830**, **8831** |
| public | 8820 only | 8830, 8831 |
| internal | 8001, 8002, 8003, 8004, 8005 | 8001, 8003, 8005 |
| removed | — | **8820** (Gateway); **8004** (internal envelope edge — not launched, see §5.2); **8002** (dispatch — Gateway-only consumer, and already unreached today) |

---

## 13. Unresolved risks

1. **The public tier acquires every database credential (CRITICAL, verdict-driving).** On `main`
   the only internet-facing process is provably driver-free and credential-free; compromise it
   and you reach no database. After removal, the Startup edge's process holds `EnvTenantSecretStore`
   (every tenant DSN) and a psycopg factory; the workspace edge's process holds the Control DB
   store, the provisioning operator, the schema applicator and the recovery/compensation services
   that drop tenant databases — to serve one read-only route. **The Gateway was a privilege
   boundary, and in-process execution is what collapses it.** Pinned by GF-8/GF-8b. The bounded
   follow-up work: narrow the workspace edge to a store accessor rather than the whole
   `ControlPlane` (cheap, and it removes the provisioning/recovery capability from the public
   process), and decide deliberately whether a public process may hold tenant DSNs at all. I did
   not attempt the narrowing here: it needs a second Control-DB credential-binding path, and
   authoring one under time pressure is exactly the change that deserves its own review.
2. **No live proof.** §10 forbade it. Authentication is a double, databases are in-memory. A live
   two-tenant witness on the Gateway-free topology is a separate authorization item.
3. **Two public surfaces instead of one.** Two proxy targets, two TLS terminations, two CORS
   allowlists — and now two *different* credential sets.
4. **DDL 012's `source_service` CHECK pins `'api_gateway'`** and needs widening. No DDL applied.
5. **The frontend cutover is not done.** Lovable needs two base URLs where it has one.
6. **A re-entrant call graph.** The workspace edge authenticates via the Auth Router, which reads
   the Control Plane — so the Control Plane transitively calls itself across processes.
7. **The internal Control-Plane read edge remains unauthenticated** and serves
   `GET /memberships?p=<principal_ref>` from a query parameter. Unchanged from `main`; it must
   stay loopback-only. The public edge never exposes that parameter (W2).
8. **The internal envelope edge is not launched, but not deleted** (§5.2), and the standing
   launcher still starts it on 8004.
9. **Rate limiting, WAF and request signing have no home.** The Gateway would have been the
   natural place; now it is the shared kernel or the reverse proxy. Not decided.
10. **The new guards are a hard-coded two-file census.** A third public edge would be unguarded
    until explicitly added — where the Gateway's "exactly one core call site" was a single global
    property of a single component.

---

## 14. Files that could be deleted in a later authorized cleanup PR

**Only after adoption, in a separate authorized PR.** Nothing was deleted here.

**Runtime — 3,821 LOC:** all 21 `backend/api_gateway/**` modules (3,327);
`database_router/adapters/providers/http_dispatch_api.py` (224 — verified sole consumer is the
Gateway's `RouterDispatchPort`); `database_router/adapters/providers/http_tenant_startup_api.py`
(270 — the internal envelope edge; **deleting this is what turns "not launched" into "deleted"**).

**Tests — 6,142 LOC:** `backend/tests/api_gateway/**` (262 tests, 25 modules).
⚠️ `tests/api_gateway/crypto_fixture.py` is the **one blessed** JWT/crypto test module
(`test_vendor_and_db_containment.py:40`). It must be **relocated, not deleted**, with both
guards updated.

**Composition seams to remove:** `build_dispatch_server_from_env`,
`build_tenant_startup_server_from_env` in `database_router/main.py`.

**Guards requiring coordinated edits** (they name `api_gateway` literally): `pyproject.toml`
root packages and 3 of 4 import-linter contracts; `test_phase7_api_gateway.py`,
`test_gateway_edge_boundaries.py`, `test_gateway_operational_audit_boundaries.py` (delete);
`test_native_uvicorn_factories.py`; `test_standing_launcher_flags.py`; `test_07d3_…`;
`test_07e3b_…`; `test_d15t1_…`; `test_import_write_path_boundaries.py`;
`test_ic010_control_read_adapter_boundaries.py`; `test_ic009_portal_binding_checks.py`;
`test_clm_2day_stage_b_…`; `test_clm_dataplane_witness_…`; `test_b5_blk6_…` (×2);
`test_deployment_composition_root_boundaries.py` (byte-pins the TOML contract);
`test_traceability.py`; `test_vendor_and_db_containment.py`; `_scan.py` `SERVICE_PACKAGES`.

⚠️ About a dozen further guards would **go vacuous rather than fail** — dead ban-list entries in
`test_phase3/4/5/6`, `test_dependency_boundaries.py`, `test_dbr_composition_boundaries.py`,
`test_auth_router_composition_boundaries.py`. They would stay green while guarding nothing.

---

## 15. Recommendation and verdict

```text
COMPLETE API GATEWAY REMOVAL — EXPERIMENT INCONCLUSIVE
```

§14's criteria, honestly scored:

| # | Criterion | Status |
|---|---|---|
| 1 | no MVP runtime request depends on `api_gateway` | ✅ executed subprocess proof (GF-1, GF-1b) |
| 2 | no port 8820 Gateway edge required | ✅ GF-6 |
| 3 | Startup GET/PATCH authenticated and tenant-safe | ✅ A1–A7 |
| 4 | cross-tenant read/write mutations are caught | ✅ M1–M5, M12 |
| 5 | client tenant/actor fields non-authoritative | ✅ A7–A9, GF-3; no bypass found by an adversarial reviewer |
| 6 | each MVP route has a clear owning service | ✅ §6 — no shared ownership |
| 7 | minimum MVP audit/security evidence remains | ✅ GF-5, A18, A19 (with the §8 limit stated) |
| 8 | materially simpler than the Gateway design | 🟡 **simpler, but about half the advertised size** — 5→5 MVP-serving edges, −1,518 to −1,742 runtime LOC, 24 of 33 controls still needed |
| 9 | full isolated suite green | ✅ 2,144 passed / 0 failed |
| 10 | guards describe the new design, not weakened | ✅ 27 new guards; none weakened; 2 registrations; 2 existing guards obeyed after catching real defects |
| 11 | no new generic proxy under another name | ✅ GF-2 + import-linter "shared is a dependency leaf" KEPT |

**Every listed criterion is met or substantially met — and the verdict is still not VIABLE**,
because the criteria do not cover the change's dominant security consequence. Reporting
"recommend removal" while the public tier's privilege regression is unmitigated would be exactly
the overclaim §15 of the instruction warns against. §14's fourth verdict — *additional isolated
work is needed* — describes the situation precisely.

**Recommendation.** Do not adopt yet. Do not discard either: the hard part is done and it works.
Three things, in order:

1. **Decide the privilege question (Dan).** Is a public process allowed to hold tenant database
   credentials? If yes, adopt with the workspace-edge narrowing below. If no, the Gateway (or an
   equivalent credential-free tier) stays, and this experiment's value is the route-ownership and
   response-composition work, not the removal.
2. **One bounded piece of work:** narrow the workspace edge to a store accessor instead of the
   whole `ControlPlane`, removing provisioning and recovery from the public process.
3. **Then** ratify the IC-010 amendments (§5) and authorize a live two-tenant witness.

If those go against removal, keeping the Gateway remains entirely defensible. This experiment
shows removal is *possible and clean at the request layer* — not that it is *obligatory*.

### Gate results

| Gate | Command | Result | Exit |
|---|---|---|---|
| full suite | `pytest -q` | **2144 passed**, 0 failed (baseline 2054 → +90) | 0 |
| architecture | `pytest tests/architecture -q` | **1063 passed** (baseline 1036 → +27) | 0 |
| gateway-free | `pytest tests/gateway_free -q` | **63 passed** | 0 |
| lint | `ruff check .` | All checks passed | 0 |
| format | `ruff format --check .` | 407 files already formatted | 0 |
| types | `mypy .` (strict) | no issues in **405** source files | 0 |
| imports | `lint-imports` | **4 kept, 0 broken** | 0 |
| secrets | `gitleaks detect --log-opts cdb46fc9..HEAD` | **no leaks found** | 0 |

Secret-scan positive control: the same scanner over the full working tree reports 4 findings, all
inside the git-ignored `backend/.venv` third-party packages — so a clean commit-range result is a
real result, not a silent no-op.

---

## 16. Stop-state proof

| Requirement | State |
|---|---|
| `main` unchanged | ✅ `cdb46fc9d3b6e12c4926f23f2f6c7a9d7c56a81f` — identical to the pre-experiment reading and to `origin/main` |
| experiment branch has local commits | ✅ five, listed in §1 |
| NOT pushed | ✅ no `git push`; the branch has no remote-tracking ref (`git branch -vv`) |
| NO PR opened | ✅ no `gh pr create`, no GitHub API write |
| NOT merged | ✅ `git diff main..HEAD` is the experiment only |
| current Gateway code not deleted | ✅ `git diff --stat cdb46fc9..HEAD -- backend/api_gateway/` is empty |
| standing environment unmodified | ✅ see below |
| working tree | ✅ clean |

**No standing/live mutation (§10):**

| Prohibited | Performed? |
|---|---|
| connect to standing PostgreSQL 5540–5543 | ❌ no psycopg connection was opened |
| connect to standing Keycloak 8814 | ❌ authentication is a double; no OIDC/JWKS call |
| change Keycloak · create a PKCE session | ❌ no |
| create or modify SecretRefs · create credentials | ❌ no |
| apply DDL | ❌ no — DDL 012's constraint is *reported*, not altered |
| modify standing memberships | ❌ only per-test `InMemoryControlStore` rows |
| modify roles/grants | ❌ no |
| run the standing PATCH witness | ❌ no |
| restart standing services · run the governed launcher · run the old scratch launcher | ❌ no |

The only sockets bound were **ephemeral loopback ports (`port=0`) opened and closed by the tests
themselves**, plus loopback ports deliberately left *unbound* to exercise connection-refused
paths. No test names a fixed standing port. The independent review confirmed this by executing
the whole suite under a C-level `sys.addaudithook`, which in-test code cannot evade.

> **A positive experiment result is not merge authorization — and this is not a positive result.**
> Only Dan may decide whether to integrate this. Even after a successful experiment: present the
> result, obtain separate authorization before any push or PR, independently review the proposed
> architecture, and obtain explicit authorization for the specific PR merge. Only a
> human-authorized merge may change `main`. No Claude or GPT verdict, test result, or
> recommendation substitutes for that authorization.
