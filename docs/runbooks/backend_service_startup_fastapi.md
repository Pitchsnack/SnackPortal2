# Running the SnackPortal2 backend services — native FastAPI / Uvicorn startup

**Governance status:** controlled non-production. `main` is **NOT READY / DO-NOT-ACTIVATE**; 7 of 9
B5 blockers remain OPEN. Nothing in this runbook authorises a production deployment, a public
ingress, TLS termination, or a supervisor.

**Canonical operator startup method:**

```text
uvicorn <module>:create_app_from_env --factory --host <host> --port <port> \
  --workers 1 --no-access-log --no-server-header --no-proxy-headers
```

All **nine** HTTP edges start this way. Normal standing operation no longer requires
`python -c "from ... import serve_*; serve_*()"`.

**Supersedes** `docs/runbooks/b5_service_startup_order.md` for the served topology (that document
predates the served Gateway edge, the tenant-Startup edge, and the FastAPI migration, and describes
the services as plain `HTTPServer`). Its startup *order* still holds; its runtime description does not.

---

## 1. Prerequisites

| Requirement | Detail |
|---|---|
| Python | 3.10+ (repo floor; the local fixture runs 3.12) |
| Install | from `backend/`: `pip install -e ".[dev]"` — required after any package change |
| Working directory | **`backend/`** for all nine commands. Uvicorn puts the current directory on the import path; running from elsewhere will not resolve the target module. |
| PostgreSQL | Control DB always; per-tenant DBs for any tenant-touching edge (§8) |
| Terminals | **One edge per terminal / OS process.** Each command blocks. |

Each command below is shown as a single logical line. In PowerShell use a backtick (`` ` ``) line
continuation; in bash use a backslash (`\`).

---

## 2. HTTP port map

| Port | Edge | Module target |
|---:|---|---|
| 8080 | API Gateway (only northbound surface) | `api_gateway.adapters.providers.http_gateway_edge:create_app_from_env` |
| 8081 | Control Plane Read | `control_plane.adapters.providers.http_read_api:create_app_from_env` |
| 8082 | Auth Router | `auth_router.adapters.providers.http_authenticate_api:create_app_from_env` |
| 8083 | Database Router Dispatch | `database_router.adapters.providers.http_dispatch_api:create_app_from_env` |
| 8084 | Tenant Startup API | `database_router.adapters.providers.http_tenant_startup_api:create_app_from_env` |
| 8085 | Gateway Audit ingest | `control_plane.adapters.providers.http_gateway_audit_api:create_app_from_env` |
| 8086 | Import Audit ingest | `control_plane.adapters.providers.http_import_audit_api:create_app_from_env` |
| 8087 | Routing Audit ingest | `control_plane.adapters.providers.http_routing_audit_api:create_app_from_env` |
| 8088 | Import Service | `deployment.import_edge:create_app_from_env` |

Every edge except the API Gateway is **internal-only** and must bind loopback. The API Gateway is the
only surface a frontend may reach, and TLS terminates at a reverse proxy (deployment scope).

### Why the Import Service target lives under `deployment`

`ImportService` needs a `RoutedSessionProvider` (implemented only by `database_router`) and a
`LineageEmitPort` (implemented only by `lineage_service`). The import-linter *service independence*
contract forbids `import_service` from importing either, and a routed tenant session is a live
transactional database handle that cannot cross a wire. `deployment/` is the composition root that
sits above every service — it may import them; nothing may import it. It owns no business logic,
no route, no contract, and no schema; it only wires objects together.

> **Governing authority.** The `deployment` package is ratified architecture:
> **D-44 — Deployment Cross-Service Composition Root (Edge 9 Import Edge)** (Approved 2026-08-03) and
> **IC-012 — Service Composition & Deployment Root Contract** (IC-012-DRAFT-1). **IC-012 §5** is the
> authority for the Edge 9 startup target below. The authorized import set is narrow and exhaustive
> (IC-012 §3) — `import_service`, `database_router`, `lineage_service`, `shared`; `api_gateway`,
> `auth_router`, and `control_plane` are **not** authorized. Nothing may import the root (IC-012 §4),
> and both directions are machine-enforced by import-linter plus
> `backend/tests/architecture/test_deployment_composition_root_boundaries.py` (IC-012 §13/§14).

---

## 3. PostgreSQL port map

| Port | Database | Used by |
|---:|---|---|
| 5540 | Control | Control Plane Read, all three audit ingest edges |
| 5541 | Tenant ACME | Database Router / Tenant Startup / Import (routed per request) |
| 5542 | Tenant ZETA | as above |
| 5543 | Tenant NOVA | as above |

**Never mix the HTTP and PostgreSQL port roles.** No edge ever binds a 55xx port, and no
`SP2_*_BASE_URL` may point at one.

---

## 4. Environment variable inventory

Values below are **names and shapes only**. Never commit real secrets, DSNs, bearer tokens, or
passwords, and never paste them into a shared terminal transcript (§10).

### Control DB posture — Control Plane Read + all three audit edges

| Variable | Required | Meaning |
|---|---|---|
| `SP2_CP_CONTROL_STORE` | yes for durable | `in_memory` (default, **test-only**) or `postgres` |
| `SP2_CP_CONTROL_STORE_DSN_REF` | no | Secret **reference** for the Control DSN. Default `control/control-store-dsn`. Never a DSN value. |
| `SNACKPORTAL_SECRET_<REF>_V1` | yes for durable | Where the referenced Control DSN is resolved from. Derived from the ref: non-alphanumerics uppercased to `_`. |

### Control Plane Read (8081)

No upstream HTTP dependency. Uses the Control DB posture above.

> ⚠️ **`SP2_CP_CONTROL_STORE` defaults to `in_memory`.** Starting this edge without setting it to
> `postgres` composes successfully and serves from a **non-durable, test-only** store — no error is
> raised. Nothing written through it survives a restart, and it is not the Control database. Always
> set `SP2_CP_CONTROL_STORE=postgres` for standing operation, and verify it before treating any read
> as authoritative. This is Control Plane posture behaviour that the application factory
> deliberately does not override.

### Lazy fail-closed: which edges refuse to start, and which fail on first request

| Behaviour | Edges |
|---|---|
| **Refuse to start** when their activation selector is absent | API Gateway, Auth Router, Dispatch, Tenant Startup, Import Service |
| **Start, then fail closed on first request** if the store cannot be resolved | Control Plane Read, all three audit ingest edges |

The second group binds a reference-only secret and resolves it lazily at first store use (never at
composition), so a listening socket is **not** proof that its database is reachable. Always run the
smoke checks in §7 after starting them.

### Auth Router (8082)

| Variable | Required | Meaning |
|---|---|---|
| `SP2_AR_CONTROL_PLANE_READ_BASE_URL` | **yes** | `http://127.0.0.1:8081` — activation selector; unset ⇒ startup failure |
| `SP2_AR_ISSUERS` | **yes when active** | JSON object mapping issuer → `{issuer, audience, allowed_algs, jwks, tenant_claim}`. The `issuer` field must equal its map key. |

### Database Router Dispatch (8083) and Tenant Startup (8084)

| Variable | Required | Meaning |
|---|---|---|
| `SP2_DBR_ROUTING_READ_BASE_URL` | **yes** | `http://127.0.0.1:8081` — activation selector; unset ⇒ startup failure |
| `SNACKPORTAL_TENANT_SECRET_DIR` | **yes** | Infra-owned absolute path holding per-tenant credential **references** |
| `SP2_DBR_ROUTING_AUDIT_BASE_URL` | no | `http://127.0.0.1:8087` — durable routing audit; unset keeps the in-memory sink |
| `SP2_DBR_ROUTING_AUDIT_TIMEOUT_SECONDS` | no | Bounded transport timeout |

### Audit ingest edges (8085 / 8086 / 8087)

Control DB posture only. Each fails closed on a blank `SP2_CP_CONTROL_STORE_DSN_REF`.

### Import Service (8088)

| Variable | Required | Meaning |
|---|---|---|
| `SP2_DBR_ROUTING_READ_BASE_URL` | **yes** | `http://127.0.0.1:8081` — the composed Database Router's routing reads |
| `SP2_IMPORT_DIRECTORY_READ_BASE_URL` | **yes** | `http://127.0.0.1:8081` — Global-directory reads |
| `SNACKPORTAL_TENANT_SECRET_DIR` | see note | One of the two tenant-credential sources; resolves the routed session **and** the lineage chain |
| `SP2_IMPORT_AUDIT_SINK_BASE_URL` | no | `http://127.0.0.1:8086` — durable Import audit; unset keeps the in-memory sink |

> **Tenant credentials have two valid sources.** `EnvTenantSecretStore` resolves a reference by
> consulting `SNACKPORTAL_TENANT_SECRET_<REF>_V<n>` **first**, then a file named `<ref>@<version>`
> under `SNACKPORTAL_TENANT_SECRET_DIR`. Either is sufficient; the directory is not demanded at
> startup. An unresolved reference fails closed at first use, not at composition — so a listening
> Import edge is not proof its tenant credentials resolve. Run the §7 checks.

### API Gateway (8080)

| Variable | Required | Meaning |
|---|---|---|
| `SP2_GW_AUTH_ROUTER_BASE_URL` | **yes** | `http://127.0.0.1:8082` |
| `SP2_GW_CONTROL_READ_BASE_URL` | **yes** | `http://127.0.0.1:8081` |
| `SP2_GW_DB_ROUTER_BASE_URL` | **yes** | `http://127.0.0.1:8083` |
| `SP2_GW_TENANT_STARTUP_BASE_URL` | no | `http://127.0.0.1:8084` — unset keeps the pre-CLM router handoff |
| `SP2_GW_IMPORT_BASE_URL` | no | `http://127.0.0.1:8088` — unset keeps the accepted-initiation envelope |
| `SP2_GW_AUDIT_SINK_BASE_URL` | no | `http://127.0.0.1:8085` — unset keeps the in-memory no-sink default |
| `SP2_GW_EDGE_ALLOWED_ORIGINS` | no | Comma-separated **exact** origins. Unset ⇒ empty allowlist ⇒ every cross-origin request denied. No wildcard is ever honoured. |

All three required Gateway transports must be set together: a partial composition never activates.

### Legacy bind selectors

`SP2_*_HOST` / `SP2_*_PORT` (e.g. `SP2_CP_READ_HOST`, `SP2_AR_AUTHENTICATE_PORT`) belong to the
**retained compatibility** `serve_*` / `AsgiEdgeServer` path only. The native path takes host and
port from the Uvicorn command line and ignores them. Do not set them for standing operation.

---

## 5. Startup order

A service's bound URL becomes the next service's selector value. Starting out of order is not fatal
— the socket binds — but downstream calls answer a bounded `503` until the dependency is up.

```text
1.  PostgreSQL topology (Control 5540 + tenant DBs)
2.  Control Plane Read      :8081   ─┬─> feeds 8082, 8083, 8084, 8088
3.  Gateway Audit           :8085   ─┐
4.  Import Audit            :8086   ─┼─ durable sinks; start before their producers
5.  Routing Audit           :8087   ─┘
6.  Auth Router             :8082
7.  Database Router Dispatch:8083
8.  Tenant Startup API      :8084
9.  Import Service          :8088
10. API Gateway             :8080   (last — needs 8082 + 8081 + 8083)
11. Frontend
```

The three audit edges depend only on the Control DB, so they may start any time after step 1; they
are placed before their producers so no durable event is emitted at a sink that is not yet listening.

The Import Service composes its **own** in-process Database Router (it does not call `:8083`); its
HTTP dependency is the Control Plane Read edge for routing and directory reads.

---

## 6. The nine canonical startup commands

Run each from `backend/`, in its own terminal, with that edge's environment set. PowerShell syntax;
substitute a backslash for the backtick on bash.

**1 — Control Plane Read (8081)**

```powershell
uvicorn control_plane.adapters.providers.http_read_api:create_app_from_env `
  --factory --host 127.0.0.1 --port 8081 `
  --workers 1 --no-access-log --no-server-header --no-proxy-headers
```

**2 — Gateway Audit ingest (8085)**

```powershell
uvicorn control_plane.adapters.providers.http_gateway_audit_api:create_app_from_env `
  --factory --host 127.0.0.1 --port 8085 `
  --workers 1 --no-access-log --no-server-header --no-proxy-headers
```

**3 — Import Audit ingest (8086)**

```powershell
uvicorn control_plane.adapters.providers.http_import_audit_api:create_app_from_env `
  --factory --host 127.0.0.1 --port 8086 `
  --workers 1 --no-access-log --no-server-header --no-proxy-headers
```

**4 — Routing Audit ingest (8087)**

```powershell
uvicorn control_plane.adapters.providers.http_routing_audit_api:create_app_from_env `
  --factory --host 127.0.0.1 --port 8087 `
  --workers 1 --no-access-log --no-server-header --no-proxy-headers
```

**5 — Auth Router (8082)**

```powershell
uvicorn auth_router.adapters.providers.http_authenticate_api:create_app_from_env `
  --factory --host 127.0.0.1 --port 8082 `
  --workers 1 --no-access-log --no-server-header --no-proxy-headers
```

**6 — Database Router Dispatch (8083)**

```powershell
uvicorn database_router.adapters.providers.http_dispatch_api:create_app_from_env `
  --factory --host 127.0.0.1 --port 8083 `
  --workers 1 --no-access-log --no-server-header --no-proxy-headers
```

**7 — Tenant Startup API (8084)**

```powershell
uvicorn database_router.adapters.providers.http_tenant_startup_api:create_app_from_env `
  --factory --host 127.0.0.1 --port 8084 `
  --workers 1 --no-access-log --no-server-header --no-proxy-headers
```

**8 — Import Service (8088)** — authority: **IC-012 §5** (D-44); the canonical Edge 9 native factory.

```powershell
uvicorn deployment.import_edge:create_app_from_env `
  --factory --host 127.0.0.1 --port 8088 `
  --workers 1 --no-access-log --no-server-header --no-proxy-headers
```

**9 — API Gateway (8080)**

```powershell
uvicorn api_gateway.adapters.providers.http_gateway_edge:create_app_from_env `
  --factory --host 127.0.0.1 --port 8080 `
  --workers 1 --no-access-log --no-server-header --no-proxy-headers
```

### The four flags are load-bearing, not cosmetic

On the native path the Uvicorn CLI builds its **own** server configuration; it does not execute the
shared `asgi_runtime` module where these properties are otherwise pinned. Uvicorn's defaults are
`access_log=True`, `server_header=True`, `proxy_headers=True`. Omitting a flag therefore silently
re-enables the behaviour:

| Flag | Omitting it causes |
|---|---|
| `--no-access-log` | Every request line — targets, tenant references, query strings — written to stderr |
| `--no-server-header` | `Server: uvicorn` disclosed on every response |
| `--no-proxy-headers` | `X-Forwarded-*` trusted from any caller |
| `--workers 1` | More than one OS process per edge, outside the authorised process model |

`--reload`, multiple workers, gunicorn, and background supervisors are **not authorised** under this
startup model.

`--host 127.0.0.1` is equally load-bearing: eight of the nine edges are internal-only (IC-010 §R/§M).
On the compatibility path the loopback restriction was enforced by the composition seam's host
allow-list; on the native path the bind address comes from this command line, so **the command line
is the only place it is enforced**. Never document or run one of these with `--host 0.0.0.0`.

### Known delta from the compatibility runtime: ASGI lifespan

The shared `asgi_runtime` sets `lifespan="off"`; the Uvicorn CLI defaults to `lifespan="auto"`, so a
natively started edge logs `Application startup complete`. No edge registers a startup or shutdown
event handler, so nothing runs — but the two paths are not byte-identical here, and no canonical flag
restores `off`. Tracked as a known gap, not a silent equivalence.

---

## 7. Health and smoke checks

Only the API Gateway exposes operational routes:

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/health
```

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/readiness
```

For the eight internal edges, confirm the socket is listening and the closed surface holds. Every
edge must refuse the docs/OpenAPI surface — both of these must answer `404` and publish no schema:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8082/docs
```

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8082/openapi.json
```

Confirm no runtime disclosure — this must print nothing:

```bash
curl -s -D - -o /dev/null http://127.0.0.1:8082/internal/auth/authenticate | grep -i "^server:"
```

A full nine-edge process smoke — start, probe, terminate, orphan check — is available as a
standalone harness:

```bash
python tests/deployment/native_uvicorn_process_smoke.py
```

---

## 8. PostgreSQL requirements

* The Control Plane Read edge and all three audit ingest edges need the **Control DB** reachable and
  its schema applied. Stores are lazy-connect: a bad DSN reference surfaces on first request, not at
  startup.
* The Database Router, Tenant Startup, and Import edges route to **per-tenant physical databases**.
  One request resolves to exactly one tenant database; a query may never span tenants.
* Apply DDL out of band. **No edge applies DDL at startup**, and none may.
* `SNACKPORTAL_TEST_DSN` is a **test** variable. It must never be reused as runtime configuration,
  and it must be unset when running the static gates.

---

## 9. Configuration failure examples

Every factory fails closed **before** anything is served. There is no fallback to an in-memory
backend: a misconfigured process refuses to start rather than quietly serving from a non-durable store.

**Missing activation selector**

```text
RuntimeError: create_app_from_env: authenticate composition is INACTIVE —
SP2_AR_CONTROL_PLANE_READ_BASE_URL is unset/empty (fail closed: no application composed)
```

**Malformed selector URL**

```text
ValueError: unsupported SP2_DBR_ROUTING_READ_BASE_URL='ftp://x'; expected an internal
http://host[:port] control-plane routing-read base URL (fail closed — no silent fallback)
```

**Missing issuer trust anchors**

```text
ValueError: SP2_AR_CONTROL_PLANE_READ_BASE_URL is active but SP2_AR_ISSUERS is unset/empty;
an active control-plane read selector requires issuer trust anchors (fail closed)
```

**Missing routing selector (Import)**

```text
RuntimeError: create_app_from_env: Import composition is INACTIVE — SP2_DBR_ROUTING_READ_BASE_URL is
unset/empty, so no real Database Router can be composed (fail closed: no application composed;
the Import path must never run without registry-authoritative routing)
```

**Unresolvable tenant credential reference** — surfaces on the first routed request, not at startup:

```text
LookupError: unresolved tenant secret reference: tenant/<id>/dsn@1
```

**Blank Control-store secret reference (audit edges)**

```text
ValueError: blank SP2_CP_CONTROL_STORE_DSN_REF; the durable Gateway-audit store requires the
control-store secret REFERENCE (references only — never a raw descriptor value)
```

**Port already in use** surfaces from Uvicorn as `[Errno 10048]` / `address already in use` — check
the port map in §2 before assuming a configuration fault.

Note that failure messages never echo the offending configured value for host/secret selectors.

---

## 10. Secret handling rules

* **References only.** Composition roots hold a secret *reference* (`SP2_CP_CONTROL_STORE_DSN_REF`,
  the per-tenant `tenant/<id>/dsn` refs) and never a resolved DSN. Resolution is lazy and happens at
  first store use.
* **Never** place a DSN, password, bearer token, JWT, or private key in this runbook, in a command
  line, in a committed file, or in a shell history that is shared.
* Per-tenant credentials live under `SNACKPORTAL_TENANT_SECRET_DIR`, owned by infrastructure. The
  provider refuses any reference outside the `tenant/` prefix.
* Access logging stays **off** so credentials in targets or headers are never written to stderr.
* Rotate by publishing a new secret version; the reference is stable, the value is not.
* If a secret is ever printed or committed, treat it as compromised and rotate it — do not merely
  delete the line.

---

## 11. Shutdown

* **Ctrl+C** in the edge's terminal. Uvicorn stops accepting, drains in-flight requests, and exits.
* Stop in **reverse startup order** (API Gateway first, Control Plane Read last) so no edge is
  serving requests that depend on a dependency already gone.
* Confirm the port is released before restarting:

```bash
netstat -ano | grep "127.0.0.1:8080"
```

* No supervisor restarts anything; a stopped edge stays stopped.
* Databases are separate — stopping an edge never stops PostgreSQL, and no edge shutdown step
  touches tenant data.

---

## 12. Compatibility path (retained, not canonical)

The `serve_*()` / `AsgiEdgeServer` lifecycle is **retained temporarily** for existing tests, the
rehearsal harness, and rollback. It still supports `server_address`, port `0`, `serve_forever()`,
`shutdown()`, and `server_close()`. Do not use it for standing operation, and do not remove it —
its retirement is out of scope here and may happen only after the native path is independently
accepted.
