# Gateway-free MVP topology (EXPERIMENT BRANCH ONLY)

> **Status: experimental.** This topology exists only on `experiment/complete-api-gateway-removal-mvp`.
> It is **not** the standing topology, it is **not** authorized to run against the standing
> PostgreSQL / Keycloak environment, and it closes no blocker. The governed standing map in
> `backend_service_startup_fastapi.md` is unchanged and remains authoritative for anything that
> actually runs. Production remains **NOT READY / DO-NOT-ACTIVATE**.

## 1. What changed

The API Gateway is removed from the MVP request path. Each MVP route family is served by the
service that already owns the records behind it, and each such edge enforces its own public
boundary in-process using the shared `shared.public_edge` kernel — a **library**, not a component.

```text
BEFORE (standing map, 6 edges, 1 public surface)
  browser ──▶ API Gateway 8820 ──┬──▶ Auth Router 8001 ──▶ Control Plane read 8003
                                 ├──▶ Control Plane read 8003        (memberships data)
                                 ├──▶ Tenant Startup API 8004 ──▶ one tenant database
                                 ├──▶ DB Router dispatch 8002        (never reached by a served route)
                                 └──▶ audit ingest 8005

AFTER (Gateway-free MVP, 5 edges, 2 public surfaces)
  browser ──┬─▶ Tenant Startup edge 8830 ─┬─▶ Auth Router 8001 ──▶ Control Plane read 8003
            │                             ├─▶ one tenant database        (IN-PROCESS)
            │                             └─▶ audit ingest 8005
            └─▶ Workspace edge 8831 ──────┬─▶ Auth Router 8001 ──▶ Control Plane read 8003
                                          ├─▶ Control DB                 (IN-PROCESS)
                                          └─▶ audit ingest 8005
```

## 2. Experimental port map

| Port | Edge | Reachability | Module target |
|---:|---|---|---|
| 8001 | Auth Router | internal | `auth_router.adapters.providers.http_authenticate_api:create_app_from_env` |
| 8003 | Control Plane Read | internal | `control_plane.adapters.providers.http_read_api:create_app_from_env` |
| 8005 | Operational audit ingest | internal | `control_plane.adapters.providers.http_gateway_audit_api:create_app_from_env` |
| 8830 | **Tenant Startup edge** | **public** | `database_router.adapters.providers.http_public_startup_edge:create_app_from_env` |
| 8831 | **Workspace edge** | **public** | `control_plane.adapters.providers.http_public_workspace_edge:create_app_from_env` |

**Deliberately absent, and why:**

| Removed | Standing port | Why it is not needed |
|---|---:|---|
| API Gateway | 8820 | No component dispatches across services any more. Each route family is served by its owner. |
| Tenant Startup API (internal envelope edge) | 8004 | The public tenant Startup edge holds `TenantStartupOperations` **in-process**, so nothing needs the envelope edge. ⚠️ **Not launched ≠ deleted:** the module and its factory remain, its composition gate is the *same* variable the public edge requires, and the standing launcher still starts it on 8004. Closing this for real needs the later cleanup PR. |
| Database Router dispatch | 8002 | Only the Gateway's `RouterDispatchPort` consumed it, and no served Gateway route ever reached that fall-through. It is dead weight in the MVP. |

## 3. Environment selectors

| Variable | Required | Meaning |
|---|---|---|
| `SP2_EDGE_AUTH_ROUTER_BASE_URL` | **yes**, both edges | The IC-005 authenticate base URL. Unset ⇒ no boundary composes ⇒ **no public edge composes at all**. Malformed ⇒ `ValueError` before any socket. |
| `SP2_EDGE_AUDIT_SINK_BASE_URL` | no | Durable operational-audit ingest. Unset keeps the in-memory no-sink default; set selects the durable partition behind the bounded one-retry policy. No loopback default. |
| `SP2_EDGE_ALLOWED_ORIGINS` | no | Exact-origin CORS allowlist (comma-separated). Unset ⇒ **every** cross-origin request is denied. |
| `SP2_DBR_ROUTING_READ_BASE_URL` | **yes**, Startup edge | Unchanged. The routing-association read the Database Router already required. |
| `SP2_DBR_PUBLIC_STARTUP_HOST` / `_PORT` | no | Bind knobs; default `127.0.0.1` / ephemeral. |
| `SP2_CP_PUBLIC_WORKSPACE_HOST` / `_PORT` | no | Bind knobs; default `127.0.0.1` / ephemeral. |
| `SP2_CP_CONTROL_STORE` | for durable | Unchanged Control-Plane posture. **Unset still composes the in-memory test-only store** — a listening workspace edge is not by itself evidence that the physical Control database is behind it. |

Both public edges still bind `127.0.0.1` by default: exposure is the operator's deliberate act at a
reverse proxy, never the consequence of an unset variable. TLS terminates at that proxy.

## 3a. Startup commands for the two PUBLIC edges (canonical flags are mandatory)

These edges terminate requests from a browser, so the four canonical uvicorn flags matter more
here than anywhere else in the system — and on the native path the command line is the **only**
place they are enforced. Uvicorn's own defaults are `proxy_headers=True`, `server_header=True`,
`access_log=True`; every one of those is wrong for a public edge:

* `--no-proxy-headers` — never let `X-Forwarded-*` reshape the request. The kernel already
  refuses to treat them as a tenant carrier, but the client address and scheme must not be
  rewritable by a caller either;
* `--no-server-header` — no version disclosure;
* `--no-access-log` — no per-request line, so a request target never reaches stderr;
* `--workers 1` — one server per operating-system process (AT-D15T1-10);
* `--host 127.0.0.1` — loopback bind. Exposure is a deliberate act at the reverse proxy, and an
  omitted `--host` falls through to `UVICORN_HOST`.

```text
uvicorn database_router.adapters.providers.http_public_startup_edge:create_app_from_env --factory --host 127.0.0.1 --port 8830 --workers 1 --no-access-log --no-server-header --no-proxy-headers
```

```text
uvicorn control_plane.adapters.providers.http_public_workspace_edge:create_app_from_env --factory --host 127.0.0.1 --port 8831 --workers 1 --no-access-log --no-server-header --no-proxy-headers
```

Both command blocks are pinned by `tests/architecture/test_gateway_free_mvp_boundaries.py`
(GF-7), which is the Gateway-free counterpart of the nine-edge census in
`test_native_uvicorn_factories.py` — that census is a hard-coded list and does not cover these
two edges, so without GF-7 the flags would be unguarded precisely where they matter most.

## 4. MVP route inventory

| Route | Owner | Classification |
|---|---|---|
| `GET /tenant/startups/<startup_ref>` | Database Router | **MVP REQUIRED — MOVED TO OWNING SERVICE** |
| `PATCH /tenant/startups/<startup_ref>` | Database Router | **MVP REQUIRED — MOVED TO OWNING SERVICE** |
| `GET /memberships` | Control Plane | **MVP REQUIRED — MOVED TO OWNING SERVICE** |
| `GET /health`, `GET /readiness` | each edge | **MVP REQUIRED** — per-edge, non-disclosing |
| `OPTIONS` preflights | each edge | **MVP REQUIRED** — per business target |
| `POST /import/<source_ref>` | — | **MVP NOT REQUIRED — DEFER.** Import is already outside the controlled local MVP journey (IMPORT-A / D-3); the standing map deliberately omits the Import Service and requires `SP2_GW_IMPORT_BASE_URL` to stay unset. |
| `GET /directory/<kind>` | — | **REMOVE FROM MVP.** The Gateway core classifies it, but no served Gateway route ever exposed it — it is dead surface on `main`, not a capability being dropped. |
| Generic `TENANT_OPERATION` router hand-off | — | **REMOVE FROM MVP.** Reachable only through the Gateway's dispatch fall-through, which no served route uses once the tenant Startup port is composed. |

## 5. What each public route owns

| Question | `GET`/`PATCH /tenant/startups/<ref>` | `GET /memberships` |
|---|---|---|
| who authenticates it | `shared.public_edge.PublicBoundary` → Auth Router (IC-005) | same |
| who authorizes tenant access | Auth Router Stage 2 (membership + readiness) | same |
| who derives tenant identity | `PublicBoundary.require_tenant`, from the signed claim only | n/a (control-scoped, self-scoped subject) |
| who owns HTTP validation | `database_router...http_public_startup_edge` | `control_plane...http_public_workspace_edge` |
| who maps the public response shape | `database_router.portal` | `control_plane.portal` |
| who records audit evidence | the edge, via `EdgeAuditPort` | the edge, via `EdgeAuditPort` |
| who selects the physical database | `TenantStartupOperations` → `RoutedSessionProvider` (D-07) | the Control Plane's own unit of work (Control DB) |

No question has two answers, and no answer is "the Gateway".
