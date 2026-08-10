# Running the SnackPortal2 backend services — native FastAPI / Uvicorn startup

**Governance status:** controlled non-production. `main` is **NOT READY / DO-NOT-ACTIVATE**; 7 of 9
B5 blockers remain OPEN. Nothing in this runbook authorises a production deployment, a public
ingress, TLS termination, or a supervisor.

**Canonical operator startup method:**

```text
uvicorn <module>:create_app_from_env --factory --host <host> --port <port> \
  --workers 1 --no-access-log --no-server-header --no-proxy-headers
```

All **eight** HTTP edges start this way. Normal standing operation no longer requires
`python -c "from ... import serve_*; serve_*()"`.

> ## ⚠️ THE API GATEWAY HAS BEEN DELETED
>
> There is no `api_gateway` package, no port **8820**, and no `SP2_GW_*` selector. The Database
> Router dispatch edge (**8002**) and the internal tenant-Startup envelope edge (**8004**) went with
> it — both existed only to carry a Gateway request into a service.
>
> Each MVP route family is now served by the service that owns its records, behind the shared
> `shared.public_edge` boundary linked **in-process**:
>
> ```text
> browser ─┬─▶ tenant Startup edge  8830   (database_router)  ──▶ one tenant database
>          └─▶ Workspace edge       8831   (control_plane)    ──▶ the Control database
> ```
>
> **There are now TWO public surfaces, not one.** The reverse proxy needs two upstreams and two TLS
> bindings, and the same exact-origin CORS allowlist must be set on both. If you find something
> listening on 8820, 8080, 8002 or 8004, it is a **stale process from a pre-removal worktree** — the
> governed launcher warns about exactly this.

**Supersedes** `docs/runbooks/b5_service_startup_order.md` for the served topology (that document
predates the FastAPI migration and describes the services as plain `HTTPServer`, and it still
instructs an operator to start the deleted API Gateway). Its startup *order* still holds for the
edges that survive; its runtime description and its Gateway step do not.

---

## 1. Prerequisites

| Requirement | Detail |
|---|---|
| Python | 3.10+ (repo floor; the local fixture runs 3.12) |
| Install | from `backend/`: `pip install -e ".[dev]"` — required after any package change |
| Working directory | **`backend/`** for every command. Uvicorn puts the current directory on the import path; running from elsewhere will not resolve the target module. **But see the editable-install hazard below — a wrong working directory does not always fail.** |
| PostgreSQL | Control DB always; per-tenant DBs for any tenant-touching edge (§8) |
| Terminals | **One edge per terminal / OS process.** Each command blocks. |

Each command below is shown as a single logical line. In PowerShell use a backtick (`` ` ``) line
continuation; in bash use a backslash (`\`).

> ⚠️ **Editable-install hazard: a `uvicorn` process can silently serve code from a DIFFERENT worktree.**
> `pip install -e ".[dev]"` writes `__editable___snackportal2_backend_0_0_0_finder.py` into the venv's
> site-packages. That finder pins all eight backend packages to **hard-coded absolute paths** — the
> paths of whichever worktree the install was run from — and appends itself to `sys.meta_path`. If the
> venv is reused from a different checkout (or from a `cd` outside `backend/`), imports resolve to the
> original tree. **There is no error and no log line.** During the FastAPI migration the standing
> topology ran for days against a pre-merge worktree this way.
>
> Before trusting any standing run or any verification evidence, confirm the resolution from a neutral
> directory:
>
> ```bash
> cd / && python -c "import database_router, control_plane, deployment; print(control_plane.__file__)"
> ```
>
> If that path is not the worktree you intend to serve, re-run `pip install -e ".[dev]"` **from that
> worktree's `backend/`** before starting anything. The governed launcher additionally derives its
> backend root from its own `$PSScriptRoot`, so it cannot default to a foreign tree — but it cannot
> repair a venv whose finder already points elsewhere.

---

## 2. HTTP port maps — TWO DISJOINT MAPS, DO NOT MIX THEM

There are two port assignments in this repository and they are **not** interchangeable. Confusing them
is the single most likely operator error on this runbook, and nothing at runtime would reveal it: two
copies of an edge can be listening at once, the frontend talks to one, and no log line mentions the
other.

### 2.1 STANDING LOCAL MVP map — the one a running local environment uses

Five edges. Started by the governed launcher `backend/tools/local/start-sp2-local.ps1`, which pins
these ports and the canonical flags.

| Port | Edge | Reachability | Module target |
|---:|---|---|---|
| 8001 | Auth Router | internal | `auth_router.adapters.providers.http_authenticate_api:create_app_from_env` |
| 8003 | Control Plane Read | internal | `control_plane.adapters.providers.http_read_api:create_app_from_env` |
| 8005 | Operational audit ingest | internal | `control_plane.adapters.providers.http_gateway_audit_api:create_app_from_env` |
| **8830** | **tenant Startup edge** | **PUBLIC** | `database_router.adapters.providers.http_public_startup_edge:create_app_from_env` |
| **8831** | **Workspace edge** | **PUBLIC** | `control_plane.adapters.providers.http_public_workspace_edge:create_app_from_env` |

**Retired ports — never bind these.** `8820` (API Gateway), `8002` (Database Router dispatch) and
`8004` (internal tenant-Startup envelope) belonged to deleted modules. A listener on any of them is a
stale pre-removal process; 8004 in particular served an **unauthenticated** envelope edge.

The 8005 ingest edge keeps its `http_gateway_audit_api` module name because it writes the Control-DB
table `control_gateway_audit` (DDL 012/013), whose name and `source_service = 'api_gateway'` CHECK are
**frozen and separately governed** — renaming the module without the DDL would only create drift.

Three edges are deliberately **absent** from the standing topology: Import Service, Import Audit
ingest, and Routing Audit ingest. Import is outside the controlled local MVP journey (IMPORT-A / D-3),
and `SP2_IMPORT_AUDIT_SINK_BASE_URL` and `SP2_DBR_ROUTING_AUDIT_BASE_URL` must remain **UNSET** for it.

**The public Startup edge is the tenant data plane.** It holds `TenantStartupOperations` in-process,
so there is no "started but unwired" posture for it the way `SP2_GW_TENANT_STARTUP_BASE_URL` used to
provide. The launcher therefore gates whether that edge starts at all behind `-EnableTenantDataPlane`
(off by default, Gate-B class M14).

### 2.2 ISOLATED SMOKE / VERIFICATION map — 8081–8088, never standing

Eight edges. This map exists for exactly one thing: the standalone eight-edge process smoke
(`backend/tests/deployment/native_uvicorn_process_smoke.py`, which hard-codes it). It starts every
edge, probes it, terminates it, and checks for orphans. **No standing environment uses these ports.**

| Port | Edge | Module target |
|---:|---|---|
| 8081 | Control Plane Read | `control_plane.adapters.providers.http_read_api:create_app_from_env` |
| 8082 | Auth Router | `auth_router.adapters.providers.http_authenticate_api:create_app_from_env` |
| 8083 | Public tenant Startup edge | `database_router.adapters.providers.http_public_startup_edge:create_app_from_env` |
| 8084 | Public Workspace edge | `control_plane.adapters.providers.http_public_workspace_edge:create_app_from_env` |
| 8085 | Operational audit ingest | `control_plane.adapters.providers.http_gateway_audit_api:create_app_from_env` |
| 8086 | Import Audit ingest | `control_plane.adapters.providers.http_import_audit_api:create_app_from_env` |
| 8087 | Routing Audit ingest | `control_plane.adapters.providers.http_routing_audit_api:create_app_from_env` |
| 8088 | Import Service | `deployment.import_edge:create_app_from_env` |

> ⚠️ **8080 is deliberately left empty.** Earlier revisions of this runbook presented the 8080–8088
> map as *the* port map and ended their standing startup order at `API Gateway :8080`, while the
> actual standing Gateway ran on 8820 — an operator following that verbatim started a **second**
> Gateway. Both ports are now retired, 8080 is assigned to nothing, and the governed launcher's
> precheck warns about a listener on either.

Six of the eight edges are **internal-only** and must bind loopback. The two PUBLIC edges (the tenant
Startup edge and the Workspace edge) are the only surfaces a frontend may reach; they also bind
loopback by default, and exposure plus TLS termination is a deliberate act at a reverse proxy
(deployment scope).

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

### Control Plane Read (standing **8003** / smoke 8081)

No upstream HTTP dependency. Uses the Control DB posture above.

> ⚠️ **`SP2_CP_CONTROL_STORE` defaults to `in_memory`.** Starting this edge without setting it to
> `postgres` composes successfully and serves from a **non-durable, test-only** store — no error is
> raised. Nothing written through it survives a restart, and it is not the Control database. Always
> set `SP2_CP_CONTROL_STORE=postgres` for standing operation, and verify it before treating any read
> as authoritative. This is Control Plane posture behaviour that the application factory
> deliberately does not override.

**The standing profile requires BOTH, together:**

| Variable | Standing requirement |
|---|---|
| `SP2_CP_CONTROL_STORE` | **`postgres`.** UNSET ⇒ the in-memory test-only store. SET-but-blank ⇒ `ValueError` (fail closed — the blank-value addendum; a blank value is a dropped configuration relay, not a request for the default). Any unsupported token ⇒ `ValueError`. |
| `SP2_CP_CONTROL_STORE_DSN_REF` | **A non-empty secret REFERENCE.** Never a DSN value. |

**Two branches flip together.** The store *and* the per-request unit-of-work factory each read this
selector independently (`control_plane/main.py` `_build_store` and `_build_store_factory`). They are
both routed through the one `control_store_selector()` normalization so they cannot diverge — but a
reader auditing only one of them will draw the wrong conclusion about the other.

> **A listening socket on 8003 is not evidence that the Control database is reachable, or even that it
> is being consulted.** The store is lazy-connect and the reference resolves at first store use. Verify
> the posture — do not infer it from a bound port or from a `200` on a read that an in-memory store can
> answer just as happily.

### Lazy fail-closed: which edges refuse to start, and which fail on first request

| Behaviour | Edges |
|---|---|
| **Refuse to start** when their activation selector is absent | both PUBLIC edges, Auth Router, Import Service |
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

### Audit ingest edges (standing: operational audit **8005** only / smoke: 8085 / 8086 / 8087)

Control DB posture only. These edges are **durable by construction**: their store composition has no
in-memory branch and never consults `SP2_CP_CONTROL_STORE`.

> ⚠️ **Correction — "fails closed on a blank reference" is true only for a WHITESPACE-ONLY value.**
> The composition reads `(os.environ.get(REF) or DEFAULT).strip()`, so:
>
> | `SP2_CP_CONTROL_STORE_DSN_REF` | Effective reference |
> |---|---|
> | unset | **the DEFAULT `control/control-store-dsn`** — silently |
> | empty string `""` | **the DEFAULT `control/control-store-dsn`** — silently |
> | whitespace-only `"  "` | `ValueError` (fail closed) |
> | a value | that value |
>
> That matters because, by standing convention, `control/control-store-dsn` resolves to the
> **`sp2_local` superuser** DSN. An ingest edge started with no reference at all therefore does not
> refuse to run — it silently binds the most privileged credential in the environment. The governed
> launcher closes this by scoping the ingest process's environment (AW-1 Q8: no `SNACKPORTAL_SECRET_*`
> other than the writer's own, no `SNACKPORTAL_SECRET_DIR`, no libpq `PG*`), so the edge binds, then
> fails closed at first store use rather than writing as a superuser.

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

### The two PUBLIC edges (standing **8830** / **8831**; smoke 8083 / 8084)

Base URLs below are given in the **standing** map (§2.1). Both edges consume the SAME authentication
and CORS selectors — deliberately one name for one thing.

| Variable | Required | Meaning |
|---|---|---|
| `SP2_EDGE_AUTH_ROUTER_BASE_URL` | **yes, both edges** | `http://127.0.0.1:8001`. The IC-005 authenticate base URL. Unset ⇒ no boundary composes ⇒ **no public edge composes at all** (a hard `RuntimeError`, never a silent unauthenticated edge). Malformed ⇒ `ValueError` before any socket. |
| `SP2_EDGE_ALLOWED_ORIGINS` | **yes for any browser client** | Comma-separated **exact** origins (`http://127.0.0.1:5173`). Unset ⇒ empty allowlist ⇒ every cross-origin request denied, **silently**: the preflight `OPTIONS` answers `204`, the browser never sends the real request, and no server log records anything. The `localhost` spelling does not match a `127.0.0.1` origin. **Set it on BOTH edges** — that is the new failure mode two public surfaces introduce. |
| `SP2_EDGE_AUDIT_SINK_BASE_URL` | **REQUIRED for standing operation** | `http://127.0.0.1:8005`. Unset ⇒ the in-memory no-sink emitter ⇒ **no durable audit row is ever written**, silently. There is deliberately no loopback default. See the note below. |
| `SP2_DBR_ROUTING_READ_BASE_URL` | **yes, Startup edge** | `http://127.0.0.1:8003`. Unchanged — the routing-association read the Database Router already required. It is also the ROUTER gate: with it set, the edge composes `TenantStartupOperations` in-process, which **is** the tenant data plane. |
| `SP2_DBR_PUBLIC_STARTUP_HOST` / `_PORT` | no | Startup-edge bind knobs; defaults `127.0.0.1` / ephemeral. Ignored on the native path (the CLI supplies both). |
| `SP2_CP_PUBLIC_WORKSPACE_HOST` / `_PORT` | no | Workspace-edge bind knobs; same defaults, same native-path caveat. |
| `SP2_CP_CONTROL_STORE` (+ `_DSN_REF`) | for durable | Unchanged Control-Plane posture, and it governs the Workspace edge too. **Unset still composes the in-memory test-only store** — a listening Workspace edge is not by itself evidence that the physical Control database is behind it. |

> **`SP2_EDGE_AUDIT_SINK_BASE_URL` is required for the controlled local MVP.** Durable operational
> audit is *in* the journey. Two distinct behaviours must not be conflated:
>
> * **Unset** is **silent**. The edge composes an in-memory emitter, serves normally, and writes
>   nothing durable. Nothing anywhere reports a degraded posture.
> * **Set but unreachable** is **loud**. Refused / unreachable / timed-out ⇒
>   `EdgeAuditTransportError("unavailable")` ⇒ exactly one bounded retry ⇒ re-raise ⇒ typed `503`.
>   This is audit-before-hand-back and it is deliberate: a served success is never handed back without
>   durable persistence confirmation. **Do not "fix" it into a fallback.**
>
> Scope, so no acceptance wording overclaims: durable coverage is the **five**
> `DURABLE_EDGE_AUDIT_ACTIONS` classes only. `IsolationAnomaly` and `CarrierOnControlAnomaly` stay
> in-memory **by design**. "All public-edge audit is durable" is false and must not be written into
> any evidence artifact. The emitter moved from the Gateway to the route-owning edge; not one action
> string changed, which is what keeps DDL 012's frozen CHECK satisfied without a schema migration.
>
> **Activating this selector produces persistent standing state (Gate-B class M11).** The governed
> launcher carries the value behind an explicit opt-in switch and ships it off by default.

### Standing selectors an operator most often forgets — and what each silently costs

Names and shapes only. Every one of these fails **quietly**: the process starts, the socket binds, and
the degraded behaviour is indistinguishable from the healthy one without an explicit check.

| Absent selector | Silent consequence |
|---|---|
| `SP2_EDGE_ALLOWED_ORIGINS` **on one of the two edges** | That edge denies every cross-origin request while the other works. The frontend shows a half-broken workspace with no server-side trace — the failure mode two public surfaces added. |
| `SP2_CP_CONTROL_STORE` | The Control Plane serves from the non-durable in-memory store. `/memberships` answers `200` with a set that never touched the Control database. |
| `SP2_EDGE_AUDIT_SINK_BASE_URL` | No durable audit row is written for any action class. |
| `SNACKPORTAL_TENANT_SECRET_DIR` | Tenant DSNs resolve only from process environment variables; the file form is unavailable. Unresolved references fail at first routed request, not at startup. |

### Legacy bind selectors

`SP2_*_HOST` / `SP2_*_PORT` (e.g. `SP2_CP_READ_HOST`, `SP2_AR_AUTHENTICATE_PORT`) belong to the
**retained compatibility** `serve_*` / `AsgiEdgeServer` path only. The native path takes host and
port from the Uvicorn command line and ignores them. Do not set them for standing operation.

---

## 5. Startup order

A service's bound URL becomes the next service's selector value. Starting out of order is not fatal
— the socket binds — but downstream calls answer a bounded `503` until the dependency is up.

### 5.1 STANDING order (five edges) — what the governed launcher does

```text
1. PostgreSQL topology (Control 5540 + tenant DBs 5541/5542/5543) + Keycloak 8814
2. Control Plane Read        :8003   ─┬─> feeds 8001 and 8830
3. Operational audit ingest  :8005   ──  durable sink; start before its producers
4. Auth Router               :8001   ──  feeds BOTH public edges
5. Workspace edge     PUBLIC :8831   (needs 8001; 8003 posture for durable reads)
6. tenant Startup edge PUBLIC:8830   (needs 8001 + 8003; only with -EnableTenantDataPlane)
7. Frontend                  :5173
```

Import Service, Import Audit ingest, and Routing Audit ingest are **not** started (§2.1).

### 5.2 ISOLATED SMOKE order (eight edges, 8081–8088)

```text
1.  PostgreSQL topology (Control 5540 + tenant DBs)
2.  Control Plane Read      :8081   ─┬─> feeds 8082, 8083, 8084, 8088
3.  Operational audit       :8085   ─┐
4.  Import Audit            :8086   ─┼─ durable sinks; start before their producers
5.  Routing Audit           :8087   ─┘
6.  Auth Router             :8082   ──  feeds BOTH public edges
7.  Import Service          :8088
8.  Public Startup edge     :8083   (needs 8082 + 8081)
9.  Public Workspace edge   :8084   (needs 8082)
```

**This is not a standing startup instruction** — the standing public edges are 8830 / 8831 (§5.1).

The three audit edges depend only on the Control DB, so they may start any time after step 1; they
are placed before their producers so no durable event is emitted at a sink that is not yet listening.

The Import Service composes its **own** in-process Database Router; its HTTP dependency is the
Control Plane Read edge for routing and directory reads.

---

## 6. Canonical startup commands

Two command sets, one per map. Run each from `backend/`, in its own terminal, with that edge's
environment set. PowerShell syntax; substitute a backslash for the backtick on bash.

> **For standing operation, prefer the governed launcher** `backend/tools/local/start-sp2-local.ps1`.
> It composes every command below from a single template, so a flag cannot go missing on one edge, and
> it scrubs `UVICORN_*` / `SP2_*` out of each child window (see §6.3). §6.1 is what it emits — recorded
> here so an operator can start one edge by hand and match the governed posture exactly.

### 6.1 STANDING LOCAL MVP — five commands

**S1 — Control Plane Read (8003)**

```powershell
uvicorn control_plane.adapters.providers.http_read_api:create_app_from_env `
  --factory --host 127.0.0.1 --port 8003 `
  --workers 1 --no-access-log --no-server-header --no-proxy-headers
```

**S2 — Operational audit ingest (8005)**

```powershell
uvicorn control_plane.adapters.providers.http_gateway_audit_api:create_app_from_env `
  --factory --host 127.0.0.1 --port 8005 `
  --workers 1 --no-access-log --no-server-header --no-proxy-headers
```

**S3 — Auth Router (8001)**

```powershell
uvicorn auth_router.adapters.providers.http_authenticate_api:create_app_from_env `
  --factory --host 127.0.0.1 --port 8001 `
  --workers 1 --no-access-log --no-server-header --no-proxy-headers
```

**S4 — Workspace edge (8831) — PUBLIC**

```powershell
uvicorn control_plane.adapters.providers.http_public_workspace_edge:create_app_from_env `
  --factory --host 127.0.0.1 --port 8831 `
  --workers 1 --no-access-log --no-server-header --no-proxy-headers
```

**S5 — tenant Startup edge (8830) — PUBLIC**

```powershell
uvicorn database_router.adapters.providers.http_public_startup_edge:create_app_from_env `
  --factory --host 127.0.0.1 --port 8830 `
  --workers 1 --no-access-log --no-server-header --no-proxy-headers
```

> The four non-`--factory` flags matter more on these two edges than anywhere else in the system:
> they terminate requests from a browser, and on the native path the command line is the **only**
> place `--no-proxy-headers` / `--no-server-header` / `--no-access-log` / `--host 127.0.0.1` are
> enforced. Starting a public edge without them silently restores uvicorn's defaults
> (`proxy_headers=True`, `server_header=True`, `access_log=True`).

### 6.2 ISOLATED SMOKE / VERIFICATION — the eight 8081–8088 commands

**These are not standing commands** — the standing public edges are 8830 / 8831. The whole set is
normally run for you by `python tests/deployment/native_uvicorn_process_smoke.py`.

**1 — Control Plane Read (8081)**

```powershell
uvicorn control_plane.adapters.providers.http_read_api:create_app_from_env `
  --factory --host 127.0.0.1 --port 8081 `
  --workers 1 --no-access-log --no-server-header --no-proxy-headers
```

**2 — Operational audit ingest (8085)**

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

**6 — Import Service (8088)** — authority: **IC-012 §5** (D-44); the canonical Edge 9 native factory.

```powershell
uvicorn deployment.import_edge:create_app_from_env `
  --factory --host 127.0.0.1 --port 8088 `
  --workers 1 --no-access-log --no-server-header --no-proxy-headers
```

**7 — Public tenant Startup edge (8083)**

```powershell
uvicorn database_router.adapters.providers.http_public_startup_edge:create_app_from_env `
  --factory --host 127.0.0.1 --port 8083 `
  --workers 1 --no-access-log --no-server-header --no-proxy-headers
```

**8 — Public Workspace edge (8084)**

```powershell
uvicorn control_plane.adapters.providers.http_public_workspace_edge:create_app_from_env `
  --factory --host 127.0.0.1 --port 8084 `
  --workers 1 --no-access-log --no-server-header --no-proxy-headers
```

### 6.3 The five flags are load-bearing, not cosmetic

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

> ⚠️ **Omitting `--host` does not merely default to loopback — it opens the `UVICORN_*` envvar
> surface.** Uvicorn's CLI is `@click.command(context_settings={"auto_envvar_prefix": "UVICORN"})`.
> Click resolves an explicit CLI option **before** its environment variable, so a flag you pass wins —
> but a flag you *omit* falls through to the envvar. `UVICORN_HOST=0.0.0.0` exported anywhere in the
> shell that launches these edges therefore binds every one of them to **every interface**, with no
> error and no log line. The same applies to `UVICORN_WORKERS`, `UVICORN_ACCESS_LOG` and
> `UVICORN_PROXY_HEADERS` — and to `UVICORN_RELOAD`, `UVICORN_APP_DIR`, `UVICORN_INTERFACE`,
> `UVICORN_LIFESPAN` and the `UVICORN_SSL_*` / `UVICORN_LIMIT_*` family, which have **no** CLI
> counterpart in the canonical command at all. Passing all five flags closes the first group; only
> removing the prefix from the child environment closes the second, which is what the governed
> launcher does.

### 6.4 `--no-access-log` silences `uvicorn.access`, not `uvicorn.error`

The flag maps to `access_log=False`, which suppresses the `uvicorn.access` logger. The startup banner
(`Started server process`, `Waiting for application startup`, `Application startup complete`,
`Uvicorn running on http://127.0.0.1:<port>`) is emitted on `uvicorn.error` and **still reaches
stderr**. The CLI exposes no `log_config=None` counterpart, so this asymmetry is not closable from the
command line.

Consequences, both of which have bitten:

* A verification witness must **not** treat the banner as an access-log leak. It carries no request
  target, no tenant reference, and no query string — it is not the class of disclosure `--no-access-log`
  exists to prevent.
* Conversely, the banner's presence is **not** evidence that `--no-access-log` was applied. Check for
  the absence of per-request lines, not for silence.

### Known delta from the compatibility runtime: ASGI lifespan

The shared `asgi_runtime` sets `lifespan="off"`; the Uvicorn CLI defaults to `lifespan="auto"`, so a
natively started edge logs `Application startup complete`. No edge registers a startup or shutdown
event handler, so nothing runs — but the two paths are not byte-identical here, and no canonical flag
restores `off`. Tracked as a known gap, not a silent equivalence.

---

## 7. Health and smoke checks

The two PUBLIC edges expose operational routes, **each on its own port** — there is no single
northbound surface to probe any more, and checking one says nothing about the other.

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8831/health
```

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8830/health
```

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8831/readiness
```

(Use 8083 / 8084 only while the isolated smoke map is up.)

A `200` from `/health` proves that edge **composed** — not that any database is reachable, and not
that the *other* public edge is up. The Control Plane read edge and the audit ingest edge bind
reference-only secrets and resolve them lazily at first store use, so a bad or absent reference
surfaces on the first real request.

For the six internal edges, confirm the socket is listening and the closed surface holds. Every
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

Every factory that **gates on an activation selector** fails closed before anything is served: both
PUBLIC edges, the Auth Router and the Import edge refuse to start when their selector is absent. For
a public edge that is the load-bearing case — an unset `SP2_EDGE_AUTH_ROUTER_BASE_URL` must never
yield an edge that serves without authenticating, so it yields no application at all.

> ⚠️ **"There is no fallback to an in-memory backend" is not true without qualification, and this
> runbook used to assert it absolutely — while §4 documented two such fallbacks a few screens earlier.**
> The accurate statement is:
>
> | Case | Behaviour |
> |---|---|
> | An **unsupported** selector token (`SP2_CP_CONTROL_STORE=mysql`) | `ValueError` — fail closed |
> | A **set-but-blank** `SP2_CP_CONTROL_STORE` | `ValueError` — fail closed (the Gate-A blank-value addendum) |
> | An **unset** `SP2_CP_CONTROL_STORE` | **in-memory, test-only store — serves normally, silently** |
> | An **unset** `SP2_EDGE_AUDIT_SINK_BASE_URL` | **in-memory emitter — no durable audit row, silently** |
> | An **unset** `SP2_IMPORT_AUDIT_SINK_BASE_URL` | **in-memory sink** (documented as intended at §4; tracked as the IC-012 M-2 open divergence — IC-012 §11 forbids exactly this, IC-012 remains Draft / Proposed, and Import stays outside the controlled local MVP journey) |
>
> The distinction that matters operationally: an *unsupported* value is loud, a *missing* value is
> silent. Neither of the silent cases is a defect to be "fixed" by adding a fallback — two of the three
> **are** the fallback. They are configuration obligations, listed in §4.

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
* Stop in **reverse startup order** (the two PUBLIC edges first, Control Plane Read last) so no edge
  is serving requests that depend on a dependency already gone.
* Confirm the ports are released before restarting — **both** of them:

```bash
netstat -ano | grep -E "127.0.0.1:(8830|8831)"
```

(Use `8083` / `8084` only when tearing down the isolated smoke map. If anything is still listening on
**8820**, **8080**, **8002** or **8004**, that is a stale pre-removal process — those modules no
longer exist in this tree.)

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

> **`port=0` is the default on every `build_*_server` / `make_server` / `serve_*` seam**, which binds
> an **ephemeral** port that the blocking entrypoints do not print. A process started that way looks
> healthy and is unreachable. `serve_read_api` previously defaulted to `port=8080` instead — the only
> `8080` literal in production source — so a no-argument compatibility invocation bound the **Control
> Plane read** edge on the Gateway's documented port, and a client aimed at the Gateway hit the
> Control-Plane catch-all. That default is now `0`, matching every sibling.

---

## 13. Fresh standing-restart witness protocol (design; execution is a separate authorized act)

This is the protocol a future verifier follows to establish that the standing topology is running
**from an accepted SHA with the governed posture** — the thing a prior "six edges are up" observation
did not establish. It is recorded here so the criteria are fixed *before* anyone runs it.

Each item is a **falsifiable observation**, not an inference:

| # | Claim | How it is established | What must NOT be accepted as proof |
|---|---|---|---|
| W-1 | Five edges started from the accepted SHA | `git -C <worktree> rev-parse HEAD` recorded at launch, **plus** the neutral-directory import check from §1 proving the venv resolves to that same worktree | "the worktree is checked out at the SHA" — the editable finder can still point elsewhere |
| W-2 | The canonical flags are active | The launcher's single command template, plus per-edge observation that no request line appears on stderr under load | The startup banner (§6.4) — it is `uvicorn.error` and is expected |
| W-3 | The public edges are on 8830 **and** 8831 | Bound-socket census over the whole standing set, **plus** a negative check that nothing is listening on **8820 / 8080 / 8002 / 8004** | A successful `/health` on one public edge — it says nothing about the other, and a stale Gateway is invisible to it |
| W-4 | No `Server:` disclosure | `curl -s -D - -o /dev/null <edge> \| grep -i "^server:"` prints nothing, on **every** edge | Checking one public edge only |
| W-5 | No access-log request leakage | Drive at least one request per edge, then confirm no per-request line reached stderr | Absence of output while idle |
| W-6 | The Auth Router did not wedge | It answers after the console window has produced output and after a Windows console selection is made and cleared (the QuickEdit pause condition) | A single early probe |
| W-7 | No temporary-worktree dependency | The recorded worktree is the durable one, not a verification worktree | — |
| W-8 | Store posture is what it claims | Explicitly record `SP2_CP_CONTROL_STORE` and `SP2_EDGE_AUDIT_SINK_BASE_URL` for each process, and whether the public Startup edge was started at all | A listening socket, or a `200` on any read |

**W-8 is the one that has previously been skipped, and it is the one that invalidates everything
downstream.** An in-memory Control Plane answers `/memberships` with `200` and an empty set exactly as
a durable one does when the principal has no membership row.

---

## 14. Authenticated `/memberships` journey witness protocol (design; requires a separate authorization)

The intended chain, stated in full so a partial one cannot be mistaken for it:

```text
Browser -> Workspace edge 8831 -> Auth Router 8001 -> Control Plane 8003
        -> the REAL Control-DB membership store -> browser render
```

Binding conditions:

1. **The password is entered by Dan.** No verifier handles, reads, echoes, transcribes, or stores it.
2. **No membership row is created to make the witness pass.** If the result is an empty set, that is
   the result. Creating the row first is a Gate-B mutation (class M6) and it destroys the evidence.
3. **The Control Plane must be on the durable store, proven per W-8, before the run.** This is the
   historical trap: an earlier run of this journey produced an empty membership set that had **two
   independent explanations** — the authenticated principal genuinely held no membership row, *and*
   the Control Plane was on the non-durable in-memory store and was never reading the Control database
   at all. Neither was distinguished at the time. A witness that cannot separate them proves nothing.
4. **Record the actual result**, including an empty set, and state which of the two explanations was
   excluded and how.
5. This is **not** the historical Stage-0 in-memory Control Plane path. Evidence from that path may not
   be cited here.

The witness proves the **control-plane read path** only. It says nothing about the tenant data plane.
The CLM ACME dataplane witness that used to cover it drove `Gateway 8820 -> Tenant Startup 8004`, and
both of those processes were deleted; a **Gateway-free successor witness has not been authored**, so
there is currently NO live tenant-data-plane proof for this topology. Note also that with the public
Startup edge not started (`-EnableTenantDataPlane` off) the data plane is not merely unproven — it is
not running.
