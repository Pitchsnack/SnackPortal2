# Runbook — Served API Gateway Edge V1

> ## ⚠️ STATUS: PARTIALLY SUPERSEDED — read this box before running anything below
>
> | | |
> |---|---|
> | **Current for** | the edge's request contract, bounds, CORS, auth, and denial semantics (§1, §2, §4, §5, §6) |
> | **SUPERSEDED for** | how to **start** the edge. `docs/runbooks/backend_service_startup_fastapi.md` is the canonical startup runbook. §3 below is the retained **compatibility** path, not the standing one. |
> | **Standing Gateway port** | **8820** — not the ephemeral port §3 binds, and not 8080 |
> | **Was previously wrong here** | §3 shipped a copy-pasteable command that binds an **ephemeral** port nobody prints; §7 affirmatively denied that any route existed beyond memberships and import, while the edge has served `GET`/`PATCH /tenant/startups/<startup_ref>` — a **write** path with a 16384-byte body — since the D-42 CLM slice. Both are corrected in place below. |
>
> Corrected under Gate A. If you are here to start the edge, go to
> `docs/runbooks/backend_service_startup_fastapi.md` §6.1 instead.

**Scope:** operating the served northbound API Gateway HTTP edge introduced by *Served API Gateway
Edge V1*, extended by *W1b* (served import) and by the *D-42 CLM* slice (served tenant Startup
read/write) — `backend/api_gateway/adapters/providers/http_gateway_edge.py` +
`backend/api_gateway/main.py` env seam. This is the first externally-reachable
authentication/isolation boundary for the Gateway (Tier 1), and the **only** externally reachable
surface in the topology.

It exposes **three** business route families:

| Family | Routes | Writes? |
|---|---|---|
| Memberships | `GET /memberships` (self-scoped `MembershipsForPrincipal`) | no |
| Import (W1b) | `POST /import/<source_ref>` | yes, when `SP2_GW_IMPORT_BASE_URL` is set |
| **Tenant Startup (D-42 CLM)** | **`GET /tenant/startups/<startup_ref>`** and **`PATCH /tenant/startups/<startup_ref>`** | **yes — PATCH carries a 16384-byte body** |

plus the operational `GET /health`, `GET /readiness`, and the `OPTIONS` CORS preflight for each of the
three business families. Every other path is `404` and every non-allowed method is `405`, decided
before the Gateway core is ever reached.

> **If you are threat-modelling or writing a firewall rule from this document, the tenant Startup
> family is the one that matters.** It is a live write surface on the only externally reachable edge.
> An earlier revision of §7 stated that no such route existed.

> **Production posture: NOT READY / DO-NOT-ACTIVATE.** This runbook makes the edge *runnable* in a
> controlled environment. It does not authorize production activation, close any B5 blocker, cut over
> Lovable, or terminate TLS in-process.

---

## 1. What the edge is (and is not)

- **Is:** a thin FastAPI edge that converts an HTTP request into the
  existing framework-neutral `InboundRequest`, calls `Gateway.handle` exactly once (through the one
  shared `_invoke_core` site) for a valid `/memberships` or `/import/<source_ref>` request, and
  serializes a success DTO with the core-owned `serialize_portal_dto`.
- **Is not:** an authenticator, authorizer, route classifier, tenant selector, database router, DTO
  composer, or audit sink. All of those remain inside the composed Gateway core. The edge owns
  transport only: the route/method allowlist, request bounds, correlation accept/mint/echo, and CORS.
- **One server per OS process.** The edge declares routes only; the concrete ASGI server (uvicorn)
  is constructed in exactly one place — `shared/adapters/providers/asgi_runtime.py` — and
  `serve_gateway_edge` runs its request loop once, on the calling thread. The edge starts no thread,
  daemon, subprocess, or supervisor of its own; request concurrency belongs to the ASGI event loop.
- **Closed surface.** OpenAPI/docs (`/openapi.json`, `/docs`, `/redoc`) are disabled and
  slash-redirects are off, so the served surface is exactly the allowlisted routes and nothing else.
  Request logging is disabled and the `server` response header is suppressed.

## 2. Environment composition (gate-first)

The edge activates **only** on a complete real Gateway composition. All three transport selectors
must resolve, or the seam returns `None` (serve-inert; nothing is bound):

| Variable | Purpose | Unset behavior |
|---|---|---|
| `SP2_GW_AUTH_ROUTER_BASE_URL` | Auth Router transport (`http://host[:port]`) | seam → `None` (serve-inert) |
| `SP2_GW_CONTROL_READ_BASE_URL` | Control-Plane read transport (`http://host[:port]`) | seam → `None` (serve-inert) |
| `SP2_GW_DB_ROUTER_BASE_URL` | Database Router dispatch transport (`http://host[:port]`) | seam → `None` (serve-inert) |
| `SP2_GW_IMPORT_BASE_URL` | Import Service initiate transport (`http://host[:port]`) — **required for real served import writes**. **Must remain UNSET for the controlled local MVP journey** (IMPORT-A / D-3). | unset → import port absent; a served `POST /import` composes an `ImportInitiationDTO` envelope that the edge fails closed to `503` (never a fake success) |
| `SP2_GW_TENANT_STARTUP_BASE_URL` | Tenant Startup transport (`http://host[:port]`) — **required for the CLM tenant data plane** | unset → `build_tenant_startup_from_env` returns `None` → **every `TENANT_OPERATION` keeps the pre-CLM router handoff**. The route still answers; the answer does not come from the CLM tenant-Startup path. See the warning below. |
| `SP2_GW_AUDIT_SINK_BASE_URL` | durable Gateway operational-audit ingest (`http://host[:port]`) | unset → in-memory emitter → **no durable audit row**, silently |
| `SP2_GW_EDGE_HOST` | bind host — **compatibility path only** | `127.0.0.1` (internal loopback) |
| `SP2_GW_EDGE_PORT` | bind port — **compatibility path only** | `0` (**EPHEMERAL** — see §3) |
| `SP2_GW_EDGE_ALLOWED_ORIGINS` | exact-origin CORS allowlist (comma-separated) | empty → deny all cross-origin, **silently** (preflight answers `204`, the browser never sends the real request, no server log records it) |

> ⚠️ **`SP2_GW_TENANT_STARTUP_BASE_URL` unset is the most misleading state on this edge.** The
> `/tenant/startups/<ref>` routes remain registered and keep answering, so a request looks serviced —
> but the CLM tenant-Startup path was never composed and the physical tenant database was never
> reached. Any evidence collected in that state is **not** tenant data-plane evidence, however
> plausible the response looks. A witness must assert this selector is composed **before** treating
> anything as a data-plane result.

> **`SP2_GW_EDGE_HOST` / `SP2_GW_EDGE_PORT` are legacy bind selectors.** They belong to the retained
> compatibility `serve_*` / `AsgiEdgeServer` path only. The canonical native path takes host and port
> from the uvicorn command line and **ignores them**. Do not set them for standing operation.

- A **malformed** transport URL or a malformed `SP2_GW_EDGE_PORT` raises `ValueError` **before any
  socket bind** (fail closed; no silent fallback, no in-memory stub).
- The three transport selectors are **non-secret internal routing config** (never a credential).
- `SP2_GW_IMPORT_BASE_URL` is **not** part of the activation gate (the edge still binds without it); it
  is required only for **real** served import writes — unset, a `POST /import` fails closed to `503`
  (the port-absent `ImportInitiationDTO` envelope is never served as success).

## 3. Run

### 3.1 Canonical — use this

```powershell
# from backend/, with the three transport selectors exported
uvicorn api_gateway.adapters.providers.http_gateway_edge:create_app_from_env `
  --factory --host 127.0.0.1 --port 8820 `
  --workers 1 --no-access-log --no-server-header --no-proxy-headers
```

`8820` is the governed **standing** Gateway port (CLM-SS-1 decision D-1). The five flags are
load-bearing, not cosmetic — see `docs/runbooks/backend_service_startup_fastapi.md` §6.3, which is the
authority for this command and for the whole standing topology. For a local environment, prefer the
governed launcher `backend/tools/local/start-sp2-local.ps1`, which starts all six standing edges with
this posture.

### 3.2 Compatibility path — retained, and a documented trap

```
# from backend/, with the three transport selectors + edge knobs exported
python -c "from api_gateway.adapters.providers.http_gateway_edge import serve_gateway_edge; serve_gateway_edge()"
```

> ⚠️ **As written, this binds a port you cannot find.** `SP2_GW_EDGE_PORT` defaults to `0`, which
> binds an **ephemeral** port, and the blocking entrypoint **never prints the bound address**. The
> process starts, reports nothing, looks perfectly healthy, and is unreachable — including to your own
> smoke check, which will read as "the Gateway is down". If you use this path at all, set
> `SP2_GW_EDGE_PORT` explicitly first.

- `serve_gateway_edge` composes via the env seam, serves on the **calling thread** (`serve_forever`
  once), and always closes the socket in `finally`. `KeyboardInterrupt` (Ctrl+C) and any serve-time
  exception propagate unswallowed after the socket is closed.
- If the composition is inactive, `serve_gateway_edge` raises a deterministic `RuntimeError` and binds
  no socket.
- This path is **not** the standing path. It is retained for existing tests, the rehearsal harness, and
  rollback, and its retirement is separately governed.

## 4. Request contract (summary)

| Route | Success | Denials / rejections |
|---|---|---|
| `GET /memberships` | `200 application/json` = `serialize_portal_dto(WorkspaceMembershipDTO)`; empty list is a lawful `200`; `Cache-Control: no-store`; `x-correlation-id` echoed | `401` unauthenticated · `403` forbidden/carrier_mismatch/isolation_anomaly · `503` unavailable — all **empty body, no detail** |
| `POST /import/<source_ref>` | `200 application/json` = `serialize_portal_dto(ImportResultDTO)` for a real, durably-audited import (`created`/`replayed`/`noop`); body-less request; `Cache-Control: no-store`; `x-correlation-id` echoed | `401` unauthenticated · `403` forbidden / carrier_mismatch / tenant_context_required / zero-record · `404` bad target · `405` bad method · `413`/`400` bounds · `503` unavailable **or** a port-absent `ImportInitiationDTO` envelope (fail-closed) — all **empty body, no detail** |
| `OPTIONS /import/<source_ref>` | `204` + exact-origin CORS headers (`POST, OPTIONS`; `x-operation-key` allowed) when the origin is allowlisted | denied/absent origin → `204` with no permissive headers |
| `GET /health` | `200` liveness (operational only) | — |
| `GET /readiness` | `200` in-process state only | — |
| `OPTIONS /memberships` | `204` + exact-origin CORS headers when the origin is allowlisted | denied/absent origin → `204` with no permissive headers |
| **`GET /tenant/startups/<startup_ref>`** | `200 application/json` = `serialize_portal_dto(TenantStartupDetailDTO)` — the **eight** contract-pinned fields of the adopted IC-009 CLM shape, references only, nullable fields rendered as `null` (`dataclasses.asdict` omits nothing); `Cache-Control: no-store`; `x-correlation-id` echoed | `401` unauthenticated · `403` forbidden / `tenant_access_denied` / carrier_mismatch · `404` bad target **or** unknown `startup_ref` · `405` bad method · `503` unavailable — all **empty body, no detail** |
| **`PATCH /tenant/startups/<startup_ref>`** | `200 application/json` = the updated record. **This is a WRITE to a physical tenant database.** Exactly one allow-listed content field (`short_description`, UTF-8, ≤ 500 chars) | as `GET`, plus `413`/`400` when the body exceeds **16384 bytes** (`_MAX_PATCH_BODY_BYTES`) |
| **`OPTIONS /tenant/startups/<startup_ref>`** | `204` + exact-origin CORS headers when the origin is allowlisted | denied/absent origin → `204` with no permissive headers |
| everything else | — | `404` route not exposed · `405` method not allowed · `413`/`400` bounds |

- **Auth:** bearer-only (`Authorization: Bearer <token>`); no cookies → CSRF not applicable to this V1.
- **Correlation:** `x-correlation-id` accepted when a bounded, safe-charset value (≤ 128); otherwise a
  fresh `uuid4` is minted. The value used is always echoed.
- **Bounds (conservative, review-pinned):** request-target ≤ 2048 bytes; ≤ 64 headers; ≤ 16 KiB total
  header bytes; **no request body** on the exposed GETs.
- **CORS:** exact-origin allowlist only; `Access-Control-Allow-Credentials: false`; never a wildcard;
  denied origins receive no CORS headers (the browser blocks the response).

### 4a. Served import route (W1b)

- **Route:** `POST /import/<source_ref>` (+ `OPTIONS` preflight). `<source_ref>` is a bounded,
  traversal-safe suffix: **1–512 UTF-8 bytes** of one or more `/`-separated segments, each
  `[A-Za-z0-9][A-Za-z0-9._-]*` (e.g. `/import/g1`, `/import/global-startup/rec-9`). Bare `/import`, a
  trailing slash, an empty segment, a `.`/`..` segment, a percent-encoded or backslash form, or any
  `?query`/`#fragment` is rejected **pre-core with `404`**. This is a bounded parameterized matcher,
  never a wildcard/prefix router.
- **Body-less:** no request body (`_MAX_BODY_BYTES = 0`); a non-empty or chunked body is `413` pre-core.
- **Authority:** `Authorization: Bearer <token>` is required; the **active tenant and actor are taken
  only from the signed authenticated context** — never from the path, body, query, cookie, or carrier.
  Optional headers: `x-operation-key` (operation-level idempotency, D-20; forwarded when present, else
  gateway-minted), `x-correlation-id` (accepted/minted/echoed), `X-Tenant-Id` (carrier-match only).
- **Outcomes:** `200` + `ImportResultDTO` (`created`/`replayed`/`noop`) for a real import; `403` for a
  zero-record import or a `tenant_context_required`/`carrier_mismatch` denial; `401` for a missing/bad
  bearer; `503` for any engine/transport failure. Every denial/rejection is **empty body, no detail**.
- **Port-absent fake-success prevention:** with `SP2_GW_IMPORT_BASE_URL` unset the Gateway composes an
  accepted-initiation `ImportInitiationDTO` envelope (no real write). The edge **never** serves that as
  success — only a real `ImportResultDTO` is a served import success — so it fails closed to `503`. Real
  served import writes therefore **require** `SP2_GW_IMPORT_BASE_URL`.
- **References-only:** the success body carries references only (source ref, signed tenant, tenant
  record ref, lineage/import id) — never a tenant row, source record, DB name, DSN, secret, or router
  detail.

### 4b. Served tenant Startup family (D-42 CLM) — the live write surface

- **Routes:** `GET` and `PATCH /tenant/startups/<startup_ref>` (+ `OPTIONS` preflight). `<startup_ref>`
  is **ONE** bounded segment of 1–512 UTF-8 bytes matching `[A-Za-z0-9][A-Za-z0-9._:-]*`. Bare
  `/tenant/startups`, a trailing slash, an empty / multi-segment / `.` / `..` / percent-encoded /
  backslash form, or any `?query` / `#fragment` is rejected **pre-core with `404`**. The FastAPI path
  template is reach-only: matching it merely routes a candidate to the handler, which then
  **re-validates against the RAW request target** (`_is_valid_tenant_startup_target`).
- **Body bound:** `PATCH` carries a body bounded at exactly **`_MAX_PATCH_BODY_BYTES = 16384`** bytes
  (IC-010 CLM), forwarded **raw** to the core and never interpreted at the edge. `GET` is body-less.
- **Authority:** bearer-only. The active tenant and actor come **only** from the signed authenticated
  context — never from the path, body, query, cookie, or carrier. `X-Tenant-Id` is a **match-only
  carrier**, never a selector; a mismatch emits `AuditAction.CARRIER_MISMATCH` with an opaque
  `carrier_ref` capped at 64 characters.
- **Isolation:** `TenantContextResolver.resolve` denies with `forbidden("tenant_access_denied")` when
  the tenant is unknown **or** the principal is not a member. The two deny **identically**, so there is
  no existence leak. The Gateway emits `AuditAction.ROUTE_DENIED` and serves `403` with an empty body.
  Authorisation on this path is by **MEMBERSHIP, not by role**.
- **Composition gate:** the whole family is gated on `SP2_GW_TENANT_STARTUP_BASE_URL`. See §2.
- **Two ambiguities an operator must not resolve by guessing.** `503` is **four-ways ambiguous** (dead
  tenant-Startup upstream, dead Auth Router, dead durable audit sink, or an unhandled edge exception)
  and `404` is **two-ways ambiguous** (bounded-matcher rejection pre-core vs a genuine unknown
  `startup_ref`). Record which upstream was probed and its liveness at the moment of the call, and pair
  every `404` with a positive control.
- **Audit-coupled fail-closed:** with a durable sink selected, a sink outage turns a legitimate `200`
  into a `503` and a legitimate `403` into a `503`. Evidence collected during a sink outage
  misrepresents the data plane as broken.

## 5. TLS / reverse proxy

The Python edge **does not terminate TLS** and binds loopback by default. Deploy it behind a reverse
proxy / load balancer that terminates TLS. The edge **does not** trust `X-Forwarded-*` / `Host` as a
tenant selector or security decision; no trusted-proxy handling is configured in V1.

## 6. Observability

Per-request metrics are recorded by the Gateway core's non-disclosing `MetricsPort` (operational
labels only). The edge's own request logging (`log_message`) is silenced. No bearer token, cookie,
request/response payload, provider body, DSN, secret, raw exception, tenant identity, or database name
appears in any response, header, or log.

## 7. Explicit non-claims

This edge does **not**:

- activate production or change any activation-blocker state (production remains **NOT READY /
  DO-NOT-ACTIVATE**; B5-BLK-5 and B5-BLK-6 remain **OPEN**);
- prove a real Control-DB composition (it is transport-tested with an in-memory read port; the
  real-PG proof is the separately-accepted B5-BLK-6C-C work);
- cut over Lovable or remove any interim data bypass (B5-BLK-5);
- terminate TLS or run a supervised service;
- expose any business route beyond the **three** families enumerated in the Scope section: memberships,
  the W1b served import route (`POST /import/<source_ref>`), and the D-42 CLM tenant Startup family
  (`GET`/`PATCH /tenant/startups/<startup_ref>`);
- serve a **real** import write without `SP2_GW_IMPORT_BASE_URL` — a port-absent import fails closed to
  `503`, never a fake success (W1b is transport-only: no DDL, no migration, no Import Service
  persistence change, and it closes no B5 blocker);
- reach the **CLM tenant data plane** without `SP2_GW_TENANT_STARTUP_BASE_URL` — unset, every
  `TENANT_OPERATION` keeps the pre-CLM router handoff, and the physical tenant database is never
  contacted;
- prove the tenant data plane. `Database Router → SecretRef → ACME physical tenant database → Startup
  GET/PATCH` is **UNPROVEN**. The proof protocol is
  `infrastructure/runbooks/clm_acme_dataplane_witness.md`; nothing in this runbook establishes it.

> **A note on the earlier §7 wording.** This section previously stated that the edge exposed no route
> beyond memberships and import. That was true when it was written and false from the D-42 CLM slice
> onward. It is corrected above rather than annotated, because the falsified form is the kind an
> operator acts on: it hides a live write path on the only externally reachable edge.
