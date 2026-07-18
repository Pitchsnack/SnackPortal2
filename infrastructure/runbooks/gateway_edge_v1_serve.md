# Runbook — Served API Gateway Edge V1

**Scope:** operating the served northbound API Gateway HTTP edge introduced by *Served API Gateway
Edge V1* (`backend/api_gateway/adapters/providers/http_gateway_edge.py` +
`backend/api_gateway/main.py` env seam). This is the first externally-reachable
authentication/isolation boundary for the Gateway (Tier 1). It exposes exactly one business route,
`GET /memberships` (self-scoped `MembershipsForPrincipal`), plus the operational `GET /health`,
`GET /readiness`, and the `OPTIONS /memberships` CORS preflight. Every other path is `404` and every
non-allowed method is `405`, decided before the Gateway core is ever reached.

> **Production posture: NOT READY / DO-NOT-ACTIVATE.** This runbook makes the edge *runnable* in a
> controlled environment. It does not authorize production activation, close any B5 blocker, cut over
> Lovable, or terminate TLS in-process.

---

## 1. What the edge is (and is not)

- **Is:** a thin, single-threaded stdlib `http.server` edge that converts an HTTP request into the
  existing framework-neutral `InboundRequest`, calls `Gateway.handle` exactly once for a valid
  `/memberships` request, and serializes a success DTO with the core-owned `serialize_portal_dto`.
- **Is not:** an authenticator, authorizer, route classifier, tenant selector, database router, DTO
  composer, or audit sink. All of those remain inside the composed Gateway core. The edge owns
  transport only: the route/method allowlist, request bounds, correlation accept/mint/echo, and CORS.
- **No web framework, no new dependency, no threading.** Plain `HTTPServer` +
  `BaseHTTPRequestHandler`, one server per OS process (AT-D15T1-10 single-threaded HARD-GATE).

## 2. Environment composition (gate-first)

The edge activates **only** on a complete real Gateway composition. All three transport selectors
must resolve, or the seam returns `None` (serve-inert; nothing is bound):

| Variable | Purpose | Unset behavior |
|---|---|---|
| `SP2_GW_AUTH_ROUTER_BASE_URL` | Auth Router transport (`http://host[:port]`) | seam → `None` (serve-inert) |
| `SP2_GW_CONTROL_READ_BASE_URL` | Control-Plane read transport (`http://host[:port]`) | seam → `None` (serve-inert) |
| `SP2_GW_DB_ROUTER_BASE_URL` | Database Router dispatch transport (`http://host[:port]`) | seam → `None` (serve-inert) |
| `SP2_GW_EDGE_HOST` | bind host | `127.0.0.1` (internal loopback) |
| `SP2_GW_EDGE_PORT` | bind port | `0` (ephemeral) |
| `SP2_GW_EDGE_ALLOWED_ORIGINS` | exact-origin CORS allowlist (comma-separated) | empty → deny all cross-origin |

- A **malformed** transport URL or a malformed `SP2_GW_EDGE_PORT` raises `ValueError` **before any
  socket bind** (fail closed; no silent fallback, no in-memory stub).
- The three transport selectors are **non-secret internal routing config** (never a credential).

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
- terminate TLS, run a supervised service, or expose any route beyond `MembershipsForPrincipal`.
