# D15-DISPATCH-SPEC-01 — Gateway↔Router Dispatch Wire Contract

**Family:** D-15 (Gateway↔Database-Router Dispatch Transport)
**Status:** Normative for D-15-T1 · **Type:** Governance / wire-contract capture (no runtime)
**Captured under:** PRD D-15-T1a (Dispatch Wire Contract Capture), 2026-07-07
**Baseline at capture:** `main == origin/main == 89a72bad7ecbeb7b2f8ab0d46a1d591e6ef670d0`
**Authority pins:** IC-010 §H/§X/§K/§O/§G/§M/§R/§P + IC-010 07E-2-C notes (§152-158) + this spec's IC-010 D-15-T1a decision-notes block
**Runtime owner:** D-15-T1b (transport pair) — **not implemented here**

> **Non-overclaim.** T1a is governance-only. It authorizes no runtime dispatch, no gateway HTTP ingress, no database-router dispatch server, no api_gateway transport client, no tenant DB routing, no live-PG proof, no tenant-vs-Control-DB distinctness proof, no body/payload pass-through, no B5-BLK-4 closure, and no Physical Multi-Database MVP completion claim. It records the wire contract so a later D-15-T1b runtime PRD can implement the dispatch transport pair safely.

---

## 1. Scope

This spec pins the **internal gateway↔database-router dispatch wire contract**:

- internal gateway → database-router dispatch transport (references-only routing proof);
- **route + immediate release** semantics (the router binds and releases the routed database target; it does not hold a connection across any downstream call);
- **no response-body pass-through**;
- **no tenant DB connection crossing into `api_gateway`**;
- **no live runtime implementation in T1a** — the transport pair, its guards, and its live proofs are D-15-T1b.

This spec is the T1 source of truth. Where it and a prior summary disagree, this spec (and the cited code) governs.

## 2. Transport boundary

- **Transport family:** internal stdlib HTTP (mirrors the existing `database_router/adapters/providers/http_routing_read.py` router→control-plane precedent; no new dependency).
- **Server side (T1b):** a database-router **internal dispatch endpoint** exposing `DatabaseRouter.route()` behind the gateway boundary.
- **Client side (T1b):** an `api_gateway` **internal dispatch client** implementing `RouterDispatchPort` as a transport adapter (references-only).
- **Method:** `POST` only.
- **Path:** `/internal/dispatch/route`.
- **Internal-only.** This surface MUST be internal-only and **never client/portal-reachable** (IC-010 §R Internal-Surface Protection; §M Service Contract). It is not a portal ingress path.
- **Runtime deferred to D-15-T1b.** T1a creates no server, no client, and no wiring.

## 3. T1 dispatch semantics

In D-15-T1, a successful dispatch means the router resolved routing **registry-authoritatively from the signed `RequestContext` claim** and, for a tenant route, bound and **immediately released** exactly one routed tenant database target:

- **TENANT route** — `dispatched=True` means the router bound exactly one tenant database target (via `DatabaseRouter.route(ctx)` → a bound `TenantConnection`) and **immediately released** it (`DatabaseRouter.release(result)`) before responding. No business work runs; no connection is held across any downstream call.
- **CONTROL route** — `dispatched=True` means routing resolved to the **Control domain** with **no tenant binding and no connection** opened (`route()` returns `RouteResult(target=CONTROL, connection=None)`; `release()` is a structural no-op). *(Improvement D2.)*

The dispatch server:
- does **not** execute business work;
- does **not** proxy or return service response bodies;
- does **not** hold tenant DB connections across a downstream service call;
- returns only the references-only response envelope in §7.

Body-era / business-response routing requires a later **IC-010 normative amendment** and is out of scope (§14).

## 4. Request envelope

Exactly:

```json
{
  "v": 1,
  "context": {
    "correlation_id": "...",
    "request_id": null,
    "active_tenant_id": null,
    "principal_ref": null,
    "role": null
  },
  "category": "TENANT_OPERATION"
}
```

**Rules.**
- `v` MUST be `1`. An unknown/absent version is rejected fail-closed.
- `context` MUST contain **exactly** the five `RequestContext` fields (`shared/context.py:14-21`): `correlation_id`, `request_id`, `active_tenant_id`, `principal_ref`, `role`. No more, no fewer.
- **Null semantics (improvement D1).** Only `correlation_id` is always present (non-null). `request_id`, `active_tenant_id`, `principal_ref`, and `role` are `Optional` and **MAY be `null`**. A **CONTROL** request carries `active_tenant_id = null` (with a CONTROL `role`) and is a valid Control route. T1b MUST accept valid nulls and MUST NOT treat a null `active_tenant_id` as malformed.
- `category` MUST be a `DispatchCategory` value string (one of `TENANT_OPERATION`, `GLOBAL_DIRECTORY_READ`, `MEMBERSHIPS_FOR_PRINCIPAL`, `IMPORT_INITIATION`).
- `category` is **advisory metadata only** (§6). It is not a database selector.
- **Unknown envelope keys → rejected fail-closed. Missing required keys → rejected fail-closed. Unknown version → rejected fail-closed.**

## 5. Explicitly NOT DispatchDecision

**`DispatchDecision` MUST NOT be serialized on the gateway↔router wire.**

Rationale (code-grounded):
- `DispatchDecision.target_tenant_id` (`api_gateway/models.py`) duplicates `RequestContext.active_tenant_id`; `api_gateway/dispatch.decide()` sets `target_tenant_id = context.active_tenant_id`.
- Sending a **gateway-computed DB selector** would create an appearance-of-selection hazard (IC-010 §X: the gateway MUST NOT resolve databases).
- Database-binding authority MUST remain with the **router** and the **signed `RequestContext` claim** (`router.route(ctx)` re-derives the target and "never re-derives the tenant" from anything but the claim).

## 6. Authority pin

> **The database router binds the database solely from the signed `RequestContext` claim. Gateway-provided category is advisory metadata only and MUST NOT be used as a database selector.**

Also binding:
- `api_gateway` MUST NOT resolve tenant databases (IC-010 §X/§H).
- `api_gateway` MUST NOT import `database_router` (DAG independence; IC-010 §M; enforced by `tests/architecture/test_phase7_api_gateway.py` `FORBIDDEN_SERVICES`).
- `database_router` remains the **only** service permitted to open tenant databases (`database_router/main.py`).
- `active_tenant_id` MUST come from the authenticated/signed routing context (IC-005/§G), **never** from request body, query, cookies, or inbound carriers (IC-010 §E).

## 7. Response envelope

Exactly:

```json
{
  "status": 200,
  "public_code": "ok",
  "dispatched": true
}
```

**Rules.**
- Response keys MUST be exactly `status`, `public_code`, `dispatched`.
- **No** `category` in the response (response `category` remains **gateway-owned**, derived from the gateway's own classification — never returned by the router).
- **No** `route_ref`, `body`, or `payload`.
- **No** DB handles, DB names, DSNs, secrets, credentials, topology, `TenantRoutingView`, or internal reason text.
- Unknown or extra response keys MUST be rejected by the `api_gateway` client and mapped fail-closed to `RouteOutcome(503, "unavailable", False)`.
- The client maps the response envelope to the existing references-only `RouteOutcome(status:int, public_code:str, dispatched:bool)` (`api_gateway/models.py`, landed 07E-2-X / PR #56).

## 8. RouteOutcome mapping table

Source-line traceability (improvement D4) in the right column.

| Router-side condition | Wire response | Gateway RouteOutcome | Source |
|---|---|---|---|
| Tenant route bound and released | `200 / ok / true` | `(200, "ok", True)` | `router.py:76-83` |
| Control route, no tenant connection | `200 / ok / true` | `(200, "ok", True)` | `router.py:58-60` |
| RoutingDenied: not_found | `404 / not_found / false` | `(404, "not_found", False)` | `models.py:72-74`; `disclosure.py:41,44`; `resolver.py:41` |
| RoutingDenied: forbidden *(reserved — see §9)* | `403 / forbidden / false` | `(403, "forbidden", False)` | `models.py:77-78` |
| RoutingDenied: no_active_tenant | `403 / no_active_tenant / false` | `(403, "no_active_tenant", False)` | `router.py:108` |
| RoutingDenied: administratively_disabled | `403 / administratively_disabled / false` | `(403, "administratively_disabled", False)` | `disclosure.py:37` |
| RoutingDenied: not_ready | `503 / not_ready / false` | `(503, "not_ready", False)` | `disclosure.py:43`; `models.py:81-83` |
| RoutingDenied: schema_out_of_range | `503 / schema_out_of_range / false` | `(503, "schema_out_of_range", False)` | `resolver.py:49` |
| RoutingDenied: unavailable | `503 / unavailable / false` | `(503, "unavailable", False)` | `disclosure.py:39`; `models.py:91-93` |
| RoutingDenied: tenant_routing_unavailable | `503 / tenant_routing_unavailable / false` | `(503, "tenant_routing_unavailable", False)` | `router.py:103` |
| RoutingDenied: control_plane_unavailable | `503 / control_plane_unavailable / false` | `(503, "control_plane_unavailable", False)` | `resolver.py:38` |
| RoutingDenied: connection_unavailable | `503 / connection_unavailable / false` | `(503, "connection_unavailable", False)` | `router.py:124` |
| RoutingDenied: routing_isolation_fault | `503 / routing_isolation_fault / false` | `(503, "routing_isolation_fault", False)` | `router.py:74` |
| Server exception (unhandled) | fixed `503`, empty body | `(503, "unavailable", False)` | fail-closed §11 |
| Server unreachable / timeout / connection refused | no trusted response | `(503, "unavailable", False)` | fail-closed §11 |
| Malformed JSON / non-JSON / extra-field response | rejected | `(503, "unavailable", False)` | fail-closed §11 |
| Unknown public_code | rejected | `(503, "unavailable", False)` | §9 |
| Wrong path or method | rejected | `(503, "unavailable", False)` | fail-closed §11 |

## 9. Closed public_code allowlist

The accepted response `public_code` set (exhaustive; enumerated from the router's actual denial surface — improvement D4):

```text
ok
not_found
forbidden
no_active_tenant
administratively_disabled
not_ready
schema_out_of_range
unavailable
tenant_routing_unavailable
control_plane_unavailable
connection_unavailable
routing_isolation_fault
```

**Reserved-not-currently-emitted (improvement D3).** As of `89a72ba`, the router emits every code above **except the bare `forbidden`** — the `forbidden()` constructor (`models.py:77-78`) is only called as `forbidden("no_active_tenant")` (`router.py:108`). `forbidden` is kept in the allowlist as a canonical, defensive 403 entry so a future router change that emits the bare code is pre-accepted rather than fail-closed-collapsed.

Any `public_code` **outside** this closed set MUST map fail-closed to:

```python
RouteOutcome(status=503, public_code="unavailable", dispatched=False)
```

## 10. Never-cross rules

The following MUST NEVER cross the gateway↔router boundary in **either** direction (request or response):

`TenantConnection`, `RouteResult`, DB connection handles, `TenantRoutingView`, `SecretRef`, `store_ref`, secret version, DSN, descriptor, credential, password, token, JWT, authorization header/value, database name, host, port, cluster topology, pool key, pool stats, lifecycle/internal reason beyond public codes, request body, response body, business payload, PII, vendor payload, cookies, query parameters, inbound carriers, `DispatchDecision`, gateway-computed tenant selector, `route_ref`, response `category`, stack trace, exception text, internal diagnostic detail.

The live `TenantConnection` bound by `route()` stays **router-side** and is released before the response; it is never serialized.

## 11. Fail-closed rules

- Server-side unhandled exceptions produce a **fixed `503` with empty body** (no internal detail).
- Client-side transport failure (unreachable/timeout/refused) → `RouteOutcome(503, "unavailable", False)`.
- Response shape mismatch (extra/missing keys, wrong types) → `RouteOutcome(503, "unavailable", False)`.
- Unknown `public_code` → `RouteOutcome(503, "unavailable", False)`.
- Non-`POST` method → refused; client treats as unavailable.
- Wrong path → refused; client treats as unavailable.
- No error path may expose internal details, and no error path may downgrade to a less-isolated outcome (IC-010 §L).

## 12. Future D-15-T1b required guards

- **G1** — wire-frame **references-only census** (no §10 type/field crosses the transport).
- **G2** — **dispatch-server edge guard** (internal-only; POST-only; `/internal/dispatch/route`; fixed-503 empty-body on exception; no leak).
- **G3** — `api_gateway` client **exact-shape / closed-code allowlist guard** (response keys exactly `{status,public_code,dispatched}`; `public_code ∈` §9 set; else fail-closed).
- **G4** — **authority-pin guard**: `category` never appears in any route-selection call; the router binds only from `ctx` (never from `category`/`DispatchDecision`).

## 13. Future D-15-T1b live proof requirements (DT-1..DT-8)

Not implemented in T1a:

- **DT-1** — e2e happy path through gateway client and router server.
- **DT-2** — one request → one tenant → one DB.
- **DT-3** — Control DB vs tenant DB physical distinctness at **database granularity**.
- **DT-4** — fail-closed on unavailable server.
- **DT-5** — invalid tenant → `not_found`, no topology leak.
- **DT-6** — suspended tenant → `administratively_disabled`.
- **DT-7** — raw HTTP response **byte-level leak scan** (no §10 material in the bytes).
- **DT-8** — release hygiene / no pool exhaustion / no idle-in-transaction leak.

## 14. Body pass-through gate

> **Full response-body pass-through is not approved in D-15-T1. Any future body-carrying gateway↔router path requires a separate IC-010 normative amendment before implementation.**

## 15. B5-BLK-4 and MVP non-overclaim

- T1a does **not** close B5-BLK-4.
- T1a does **not** prove Physical Multi-Database MVP complete.
- A future T1b live proof **may become one input** to B5-BLK-4 closure but is **not itself** the closure.

---

## Appendix A — Carry-forward Additional Testing Requirements (AT-D15T1-1..12)

| ID | Gap | Marker | Owner |
|---|---|---|---|
| AT-D15T1-1 | Wire sub-contract captured in this spec + IC-010 notes | HARD-GATE before T1b | D-15-T1a (this slice) |
| AT-D15T1-2 | Wire-frame references-only guard G1 + raw-byte leak scan DT-7 | HARD-GATE before live dispatch | D-15-T1b |
| AT-D15T1-3 | e2e one-request→one-tenant→one-DB + DB-granularity distinctness through the wire | HARD-GATE before B5-BLK-4 | D-15-T1b |
| AT-D15T1-4 | Cross-cluster physical distinctness through dispatch path | Deployment-only | D-15 deployment |
| AT-D15T1-5 | Pool-release hygiene under dispatch + pool-exhaustion fail-closed | SHOULD do soon | D-15-T1b |
| AT-D15T1-6 | Durable router operational-audit sink | SHOULD do soon | D-15-T2 / audit extension |
| AT-D15T1-7 | Control-plane→router invalidation endpoint | SHOULD do soon | D-15-T2 |
| AT-D15T1-8 | Closed public_code enum promoted into shared vocab | NICE / later | Guard-hardening pass |
| AT-D15T1-9 | Quarantined→unavailable disclosure tightening (no `Quarantined` state exists today) | NICE / later | Router-side slice |
| AT-D15T1-10 | Dispatch-server concurrency | HARD-GATE before any threaded server | 07E-concurrency |
| AT-D15T1-11 | Body pass-through law | HARD-GATE before any body crosses gateway | Future IC-010 amendment PRD |
| AT-D15T1-12 | Router live coverage beyond dispatch | SHOULD do soon | D-15 follow-on |

*End of D15-DISPATCH-SPEC-01.*
