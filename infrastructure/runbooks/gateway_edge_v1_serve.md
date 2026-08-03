# Runbook — Served API Gateway Edge V1

**Scope:** operating the served northbound API Gateway HTTP edge introduced by *Served API Gateway
Edge V1* and extended by *W1b* (`backend/api_gateway/adapters/providers/http_gateway_edge.py` +
`backend/api_gateway/main.py` env seam). This is the first externally-reachable
authentication/isolation boundary for the Gateway (Tier 1). It exposes **two** business routes —
`GET /memberships` (self-scoped `MembershipsForPrincipal`) and `POST /import/<source_ref>` (the
bounded, traversal-safe served import route — W1b) — plus the operational `GET /health`,
`GET /readiness`, and the `OPTIONS /memberships` / `OPTIONS /import/<source_ref>` CORS preflights.
Every other path is `404` and every non-allowed method is `405`, decided before the Gateway core is
ever reached.

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
| `SP2_GW_IMPORT_BASE_URL` | Import Service initiate transport (`http://host[:port]`) — **required for real served import writes** | unset → import port absent; a served `POST /import` composes an `ImportInitiationDTO` envelope that the edge fails closed to `503` (never a fake success) |
| `SP2_GW_EDGE_HOST` | bind host | `127.0.0.1` (internal loopback) |
| `SP2_GW_EDGE_PORT` | bind port | `0` (ephemeral) |
| `SP2_GW_EDGE_ALLOWED_ORIGINS` | exact-origin CORS allowlist (comma-separated) | empty → deny all cross-origin |

- A **malformed** transport URL or a malformed `SP2_GW_EDGE_PORT` raises `ValueError` **before any
  socket bind** (fail closed; no silent fallback, no in-memory stub).
- The three transport selectors are **non-secret internal routing config** (never a credential).
- `SP2_GW_IMPORT_BASE_URL` is **not** part of the activation gate (the edge still binds without it); it
  is required only for **real** served import writes — unset, a `POST /import` fails closed to `503`
  (the port-absent `ImportInitiationDTO` envelope is never served as success).

## 3. Run

```
# from backend/, with the three transport selectors + edge knobs exported
python -c "from api_gateway.adapters.providers.http_gateway_edge import serve_gateway_edge; serve_gateway_edge()"
```

- `serve_gateway_edge` composes via the env seam, serves on the **calling thread** (`serve_forever`
  once), and always closes the socket in `finally`. `KeyboardInterrupt` (Ctrl+C) and any serve-time
  exception propagate unswallowed after the socket is closed.
- If the composition is inactive, `serve_gateway_edge` raises a deterministic `RuntimeError` and binds
  no socket.

## 4. Request contract (summary)

| Route | Success | Denials / rejections |
|---|---|---|
| `GET /memberships` | `200 application/json` = `serialize_portal_dto(WorkspaceMembershipDTO)`; empty list is a lawful `200`; `Cache-Control: no-store`; `x-correlation-id` echoed | `401` unauthenticated · `403` forbidden/carrier_mismatch/isolation_anomaly · `503` unavailable — all **empty body, no detail** |
| `POST /import/<source_ref>` | `200 application/json` = `serialize_portal_dto(ImportResultDTO)` for a real, durably-audited import (`created`/`replayed`/`noop`); body-less request; `Cache-Control: no-store`; `x-correlation-id` echoed | `401` unauthenticated · `403` forbidden / carrier_mismatch / tenant_context_required / zero-record · `404` bad target · `405` bad method · `413`/`400` bounds · `503` unavailable **or** a port-absent `ImportInitiationDTO` envelope (fail-closed) — all **empty body, no detail** |
| `OPTIONS /import/<source_ref>` | `204` + exact-origin CORS headers (`POST, OPTIONS`; `x-operation-key` allowed) when the origin is allowlisted | denied/absent origin → `204` with no permissive headers |
| `GET /health` | `200` liveness (operational only) | — |
| `GET /readiness` | `200` in-process state only | — |
| `OPTIONS /memberships` | `204` + exact-origin CORS headers when the origin is allowlisted | denied/absent origin → `204` with no permissive headers |
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
- provide a durable Gateway operational-audit sink or operator retrieval (separate governed work);
- terminate TLS, run a supervised service, or expose any route beyond `MembershipsForPrincipal` and the
  W1b served import route (`POST /import/<source_ref>`);
- serve a **real** import write without `SP2_GW_IMPORT_BASE_URL` — a port-absent import fails closed to
  `503`, never a fake success (W1b is transport-only: no DDL, no migration, no Import Service
  persistence change, and it closes no B5 blocker).
