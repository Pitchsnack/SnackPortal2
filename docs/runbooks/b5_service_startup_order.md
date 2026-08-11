# B5 Service Startup Order — Runbook (B5-2)

> ## ⚠️ SUPERSEDED FOR THE SERVED TOPOLOGY — do not start services from this document
>
> `docs/runbooks/backend_service_startup_fastapi.md` is the canonical startup runbook. This document
> predates the FastAPI/Uvicorn migration, the served API Gateway edge, and the tenant-Startup edge.
>
> **And it now describes processes that no longer exist.** On this branch the API Gateway (8820),
> the Database Router dispatch edge (8002) and the internal tenant-Startup envelope edge (8004) have
> been DELETED; the MVP route families are served by two PUBLIC edges on 8830 / 8831. Any step below
> that starts one of the removed processes cannot succeed, and the ordering it implies is wrong.
>
> | Still valid here | Superseded here |
> |---|---|
> | The **dependency order** (§2) and why each URL feeds the next composition | Every runtime description: these edges are no longer plain stdlib `HTTPServer` processes |
> | The fail-closed configuration semantics (§6) | The three `python -c … serve_*()` commands (§5) — retained **compatibility path only**, never standing |
> | The one-service-per-process rule (§4) | Everything about the API Gateway (§1) — the component is **DELETED** (D-45); the externally reachable surfaces are the **two approved public edges** on 8830 / 8831 |
> | The no-overclaim status (§8) | The three-service census — the served topology is **six** standing edges |
>
> The supersession notice previously existed only in the *superseding* document, which an operator
> opening this file never sees. That is corrected here, in place.

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
env-composition seams and then serving on the calling thread.

> **Runtime correction.** When this was written each entrypoint served a plain stdlib `HTTPServer`.
> Since the FastAPI/Uvicorn migration every edge is a **FastAPI application served by Uvicorn** — an
> ASGI event loop, not a stdlib handler class, and not one-request-at-a-time. The retained
> `serve_*()` seams below still block on the calling thread and still bind exactly one socket per
> process, so the **process model** described in §4 is unchanged; the **runtime description** is not.
> The authorized process model remains one uvicorn worker and one OS process per edge.

| Service | Entrypoint | Composition seam | Bind knobs |
|---|---|---|---|
| Control-plane read edge | `control_plane.adapters.providers.http_read_api.serve_read_api(host, port)` (07E-1 precedent; function args) | `create_app()` (env-composed via the `SP2_CP_*` selectors; `build_read_server_from_env` is the B5-1 env-knob seam) | function args (or `SP2_CP_READ_HOST` / `SP2_CP_READ_PORT` via the B5-1 seam) |
| Auth Router authenticate edge | `auth_router.adapters.providers.http_authenticate_api.serve_authenticate_api()` (B5-2) | `build_authenticate_server_from_env` | `SP2_AR_AUTHENTICATE_HOST` / `SP2_AR_AUTHENTICATE_PORT` |
| Database Router dispatch edge | `database_router.adapters.providers.http_dispatch_api.serve_dispatch_api()` (B5-2) | `build_dispatch_server_from_env` | `SP2_DBR_DISPATCH_HOST` / `SP2_DBR_DISPATCH_PORT` |

> ### ⛔ WITHDRAWN WITH ITS SUBJECT: everything §1 says about the API Gateway
>
> When B5-2 was written the API Gateway was driven **in-process** (`Gateway.handle`) by its caller and
> had no listening socket. It later gained a served edge — and under **D-45** (2026-08-11) the component
> is **deleted** outright, so neither statement describes anything that exists.
>
> **The externally reachable surfaces are the two approved public edges (8830 / 8831), and they are the only ones in
> the topology.** It serves `GET /memberships`, `POST /import/<source_ref>`, and — since the D-42 CLM
> slice — `GET`/`PATCH /tenant/startups/<startup_ref>`, the last of which is a **write** path into a
> physical tenant database. Standing port **8820**.
>
> An operator following the uncorrected sentence would not start the northbound Gateway at all, and
> would not know one exists. See `infrastructure/runbooks/gateway_edge_v1_serve.md` for the request
> contract and `docs/runbooks/backend_service_startup_fastapi.md` §6.1 for how to start it.

Historically (B5-2), the Gateway composed its two transport clients from
`SP2_GW_AUTH_ROUTER_BASE_URL` / `SP2_GW_DB_ROUTER_BASE_URL` and was driven in-process. The served edge
adds `SP2_GW_CONTROL_READ_BASE_URL` as a third required transport, plus the optional
`SP2_GW_TENANT_STARTUP_BASE_URL`, `SP2_GW_AUDIT_SINK_BASE_URL` and `SP2_GW_IMPORT_BASE_URL` selectors.

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

**One service per operating-system process. That rule is unchanged and still binding** — it is the
authorized process model (one uvicorn worker, one OS process per edge; no application-created worker,
subprocess, or reload supervisor). Hosting two of these servers in one process cannot work: on the
retained `serve_*()` path the first `serve_forever` blocks the only thread, and the Auth Router calls
the read edge **during** request handling, so a shared process would deadlock.

> **Runtime correction.** The original text described each server as an intentionally single-threaded
> plain `HTTPServer` with one in-flight request each and no `ThreadingHTTPServer`. The
> *single-process, no-application-threads* half of that is still enforced. The *one-request-at-a-time*
> half is not: a Uvicorn-served FastAPI edge handles concurrent requests on its ASGI event loop. Do
> not rely on serialized request handling as a safety property anywhere.

## 5. Manual start — COMPATIBILITY PATH ONLY, not the standing method

> ⚠️ **The three `python -c … serve_*()` commands below are the retained compatibility path.** They are
> kept for existing tests, the rehearsal harness, and rollback. **Do not use them for standing
> operation.** The canonical standing commands are in
> `docs/runbooks/backend_service_startup_fastapi.md` §6.1 (`uvicorn <module>:create_app_from_env
> --factory --host 127.0.0.1 --port <governed port> --workers 1 --no-access-log --no-server-header
> --no-proxy-headers`), and a local environment should use the governed launcher
> `backend/tools/local/start-sp2-local.ps1`.
>
> Two specific hazards on this path: every `build_*_server` / `serve_*` seam defaults to **`port=0`
> (ephemeral)** and none of them prints the bound address, so an unparameterized invocation produces a
> healthy-looking unreachable process; and these seams do **not** apply the five canonical uvicorn
> flags, because they do not go through the uvicorn CLI at all.

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
Send `Ctrl+C` (SIGINT) to the service process. On the retained compatibility path `KeyboardInterrupt`
propagates out of `serve_forever` **unswallowed** and the entrypoint's `finally` always runs
`server_close()`, releasing the listening socket; there is no drain phase, retry loop, or signal
framework. On the canonical Uvicorn path, Ctrl+C stops accepting, **drains in-flight requests**, and
exits — see `docs/runbooks/backend_service_startup_fastapi.md` §11 for the standing shutdown order.

## 8. No-overclaim status

```text
B5-BLK-4 OPEN.
Physical Multi-Database MVP mandatory and NOT complete.
Smoke C deferred / HARD-GATE.
```

B5-2 makes the services *runnable*; it does not stand up the physical Control/tenant databases
(B5-4), fix the live-wire denial semantics (B5-3), provide the RS256 token fixture or the Smoke C
specification (B5-5), or execute Smoke C.
