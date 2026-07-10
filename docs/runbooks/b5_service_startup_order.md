# B5 Service Startup Order — Runbook (B5-2)

**Scope.** B5-2 provides **blocking serve entrypoints only**. This runbook explains how to start the
three internal backend services manually, in the correct order, each in its own process. It does not
deploy, supervise, or monitor anything.

```text
No health endpoint exists.
No supervisor is provided.
No Docker/service deployment is created.
No physical database is provisioned.
No Smoke C proof is performed.
```

## 1. What B5-2 gives you

Three blocking entrypoints, each composing its service from environment configuration via the merged
env-composition seams and then serving a **single-threaded** plain `HTTPServer` on the calling thread:

| Service | Entrypoint | Composition seam | Bind knobs |
|---|---|---|---|
| Control-plane read edge | `control_plane.adapters.providers.http_read_api.serve_read_api(host, port)` (07E-1 precedent; function args) | `create_app()` (env-composed via the `SP2_CP_*` selectors; `build_read_server_from_env` is the B5-1 env-knob seam) | function args (or `SP2_CP_READ_HOST` / `SP2_CP_READ_PORT` via the B5-1 seam) |
| Auth Router authenticate edge | `auth_router.adapters.providers.http_authenticate_api.serve_authenticate_api()` (B5-2) | `build_authenticate_server_from_env` | `SP2_AR_AUTHENTICATE_HOST` / `SP2_AR_AUTHENTICATE_PORT` |
| Database Router dispatch edge | `database_router.adapters.providers.http_dispatch_api.serve_dispatch_api()` (B5-2) | `build_dispatch_server_from_env` | `SP2_DBR_DISPATCH_HOST` / `SP2_DBR_DISPATCH_PORT` |

The API Gateway has **no inbound HTTP edge** (ingress is deployment-owned, IC-010): it is driven
**in-process** (`Gateway.handle`) by its caller and composes its two transport clients from
`SP2_GW_AUTH_ROUTER_BASE_URL` / `SP2_GW_DB_ROUTER_BASE_URL`.

## 2. Startup order (dependency chain)

```text
1. Control-plane read edge
2. Auth Router          (needs the read-edge URL)
3. Database Router      (needs the read-edge URL)
4. in-process API Gateway caller   (needs the Auth Router + Database Router URLs)
```

Why this order — each URL feeds the next service's composition:

```text
read-edge URL      -> SP2_AR_CONTROL_PLANE_READ_BASE_URL   (Auth Router -> control-plane reads)
read-edge URL      -> SP2_DBR_ROUTING_READ_BASE_URL        (Database Router -> routing reads)
Auth Router URL    -> SP2_GW_AUTH_ROUTER_BASE_URL          (Gateway -> authenticate transport)
Database Router URL-> SP2_GW_DB_ROUTER_BASE_URL            (Gateway -> dispatch transport)
```

## 3. Ports

- **Use fixed, non-ephemeral ports for standing manual runs** (e.g. one distinct loopback port per
  service). Downstream services need a **stable URL** at composition time.
- Port `0` (ephemeral) is test/composition-friendly — the OS picks a free port and the factory
  reports it in `base_url` — but it is **unsuitable** for standing runs: the blocking entrypoints do
  not print the bound URL, and a restart changes the port under every downstream consumer.

## 4. Process model — one service per process

Every server here is an intentionally **single-threaded** plain `HTTPServer` (one in-flight request
each; no `ThreadingHTTPServer`, no production threads). Each service **must run in its own
operating-system process**: hosting two of these servers in one process cannot work (the first
`serve_forever` blocks the only thread), and the Auth Router calls the read edge **during** request
handling — a shared process would deadlock.

## 5. Manual start (documented `python -c` invocations; no `[project.scripts]`)

Run each from `backend/` in its **own terminal/process**, with that service's environment set. Env
var **names and `<placeholder>` tokens** only are shown — substitute your own local values at run
time, and never put secret values (or any real configuration values) in files or command lines
checked into the repo.

**Terminal 1 — control-plane read edge** (set the `SP2_CP_*` store posture selectors as required;
the all-in-memory default needs none; pick a fixed free `<read-port>` on the loopback host):

```text
python -c "from control_plane.adapters.providers.http_read_api import serve_read_api; serve_read_api('127.0.0.1', <read-port>)"
```

**Terminal 2 — Auth Router** — set `SP2_AR_CONTROL_PLANE_READ_BASE_URL` to the read-edge URL
(`http://127.0.0.1:<read-port>`), `SP2_AR_ISSUERS` to the issuer trust-anchor JSON, and the bind
knobs `SP2_AR_AUTHENTICATE_HOST` (loopback) / `SP2_AR_AUTHENTICATE_PORT` (a fixed free
`<auth-port>`), then:

```text
python -c "from auth_router.adapters.providers.http_authenticate_api import serve_authenticate_api; serve_authenticate_api()"
```

**Terminal 3 — Database Router** — set `SP2_DBR_ROUTING_READ_BASE_URL` to the read-edge URL
(`http://127.0.0.1:<read-port>`) and, for real tenant dispatch, the tenant DSN secret resolution
env (`SNACKPORTAL_TENANT_SECRET_DIR` or per-ref `SNACKPORTAL_TENANT_SECRET_*` — names shown here,
values supplied locally only), plus the bind knobs `SP2_DBR_DISPATCH_HOST` (loopback) /
`SP2_DBR_DISPATCH_PORT` (a fixed free `<dispatch-port>`), then:

```text
python -c "from database_router.adapters.providers.http_dispatch_api import serve_dispatch_api; serve_dispatch_api()"
```

**Process 4 — gateway caller** (in-process): set `SP2_GW_AUTH_ROUTER_BASE_URL` to
`http://127.0.0.1:<auth-port>` and `SP2_GW_DB_ROUTER_BASE_URL` to
`http://127.0.0.1:<dispatch-port>`, then compose via
`api_gateway.main.build_authenticator_from_env` / `build_router_dispatch_from_env` and drive
`Gateway.handle` from the calling program.

## 6. Fail-closed configuration behavior

- **Inactive selector** (`SP2_AR_CONTROL_PLANE_READ_BASE_URL` / `SP2_DBR_ROUTING_READ_BASE_URL`
  unset or empty): the entrypoint raises a deterministic `RuntimeError` and exits — **no socket is
  bound and nothing is served**. There is no silent fallback to a default composition.
- **Malformed configuration** (bad URL scheme, invalid issuer config, out-of-range port): the
  composition seam raises `ValueError` **before** any socket binds.
- A service that starts before its dependency is reachable will bind and serve, but requests fail
  closed (`503 unavailable`) until the dependency URL answers — start in the §2 order to avoid this.

## 7. Orderly shutdown

Stop services in the **reverse** order (gateway caller → Database Router → Auth Router → read edge).
Send `Ctrl+C` (SIGINT) to the service process: `KeyboardInterrupt` propagates out of
`serve_forever` **unswallowed**, and the entrypoint's `finally` always runs `server_close()`,
releasing the listening socket. In-flight requests on these single-threaded servers complete or fail
closed; there is no drain phase, retry loop, or signal framework.

## 8. No-overclaim status

```text
B5-BLK-4 OPEN.
Physical Multi-Database MVP mandatory and NOT complete.
Smoke C deferred / HARD-GATE.
```

B5-2 makes the services *runnable*; it does not stand up the physical Control/tenant databases
(B5-4), fix the live-wire denial semantics (B5-3), provide the RS256 token fixture or the Smoke C
specification (B5-5), or execute Smoke C.
