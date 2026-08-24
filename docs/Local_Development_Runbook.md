# SnackPortal2 — Local Development Runbook

**LOCAL / NON-PRODUCTION ONLY.** Nothing here authorizes a production deployment, a public
ingress, TLS termination, or a supervisor. Every credential this procedure creates is a
disposable local throwaway.

This is the supported way to run the **Option A rebuild** (D-46) — the FastAPI BFF plus the
thirteen internal services, against four physically separate PostgreSQL clusters — from a fresh
checkout.

Target experience, and what this document delivers:

```
fresh checkout -> configure -> start databases -> migrate -> seed
               -> start the identity provider and pin its key
               -> start services -> verify 14 OpenAPI 3.1 contracts
               -> start the frontend -> log in through a real browser
               -> run a real tenant Startup flow
               -> confirm the row is in the correct physical tenant database
```

---

## 0. Prerequisites

| Need | Version used to write this | Why |
|---|---|---|
| Docker Desktop (or Docker Engine + Compose v2) | 29.5.3 / Compose 5.1.4 | Runs the fourteen services and the four PostgreSQL clusters |
| Python | 3.12.10 (project floor is 3.10) | Runs the operator command and the test suites |
| Git | any | — |

Docker commands in this runbook are **cross-platform** — identical on Windows, macOS and Linux.
The Python commands are shown in the form that works in **Windows PowerShell**, which is the
active development environment; on macOS/Linux substitute `python` for
`.\.venv\Scripts\python.exe` and forward slashes for backslashes.

**Two working directories, and every command block below says which.**

| Run from | What |
|---|---|
| repository root | every `docker compose …` command |
| `backend/` | every `python -m tools.local.sp2_local …` command, and pytest |

The split is not arbitrary: `tools` is deliberately not installed into the environment (see §2),
so the operator command resolves it from the current directory. CI does the same — its `validate`
job sets `working-directory: backend`.

> **Ports this procedure uses.** BFF `127.0.0.1:8000`; PostgreSQL `127.0.0.1:5550-5553`; the local
> identity provider `127.0.0.1:8090`; the frontend dev server `localhost:5173`.
> The 5550-5553 range is deliberately *not* 5540-5543, so this stack can run alongside the older
> `docker-compose.local.yml` fixture without a collision. Nothing else is published — and the two
> things that *are* published beyond the BFF are not application services: a database and an
> identity provider a **browser** has to be redirected to.

---

## 1. Clone / checkout

```bash
git clone https://github.com/Pitchsnack/SnackPortal2.git
cd SnackPortal2
```

Create the Python environment the operator command and the test suites use:

```powershell
# from the REPOSITORY ROOT
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -e "backend[dev]"
```

`-e backend[dev]` installs the backend package plus ruff, mypy, pytest, import-linter and httpx.

---

## 2. Copy the local env template

You do **not** fill it in by hand. Generate a filled, untracked copy with fresh random values:

```powershell
cd backend
.venv\Scripts\python.exe -m tools.local.sp2_local init-env
```

> **The operator command runs from `backend/`, and only from there.** `tools` is deliberately
> excluded from `[tool.setuptools.packages.find]`, so it is never installed into the environment
> — that exclusion is what keeps an operator tool holding a database driver out of the service
> graph and out of the distribution. `python -m tools.local.sp2_local` therefore resolves `tools`
> from the current directory, and from the repository root it fails with
> `No module named 'tools'`.

This writes `infrastructure/docker/.env.rebuild` — **gitignored, never committed** — with 14
freshly generated local throwaway values. It refuses to overwrite an existing file unless you
pass `--force`.

**Why generated rather than copied.** The committed template
(`infrastructure/docker/.env.rebuild.template`) has **empty** secret lines on purpose. A
placeholder long enough to satisfy the 32-character lineage-key floor is a placeholder that
*works*, and would be left in place — every developer's chain keyed with a value that lives in
the repository. Empty instead, so the compose file's `${VAR:?...}` guards fail loudly and name
the variable.

---

## 3. Configure required values

`init-env` fills everything required. Read
[`infrastructure/docker/.env.rebuild.template`](../infrastructure/docker/.env.rebuild.template)
for what each group means. In short:

| Group | Set by `init-env` | Notes |
|---|---|---|
| Local PostgreSQL user/password | password only | user defaults to `sp2_local` |
| Host-side ports | no — defaults | `5550-5553`, only change with the compose file |
| `SP2_TENANT_STORAGE` | no — defaults to `postgres` | the only accepted value is the exact string `postgres` |
| Internal service credentials (6) | yes | one shared, plus one per tenant-resident service |
| Local development tokens (4) | yes | opaque tokens for the four synthetic local principals |
| Per-tenant lineage keys (3) | yes | minimum 32 characters, no shared fallback |
| Local identity passwords (5) | yes | Keycloak admin + one per synthetic identity |
| `SP2_LOCAL_IDP_ISSUER_ORIGIN` / `_PORT` | no — defaults | `http://localhost:8090` / `8090`; the two must agree |
| `SP2_AUTHENTICATION_ISSUERS` | left empty | written by `idp-up` in §6, never by hand |
| `SP2_BFF_BASE_DOMAIN` | left empty | host-based tenant addressing off; `X-Tenant-Id` is the only carrier |

**Authentication has two postures, and exactly one is live at a time.**

| `SP2_AUTHENTICATION_ISSUERS` | Verifier selected | Credentials that work |
|---|---|---|
| set (after §6) | `JwtTokenVerifier` — RS256 against the pinned realm key | real OIDC tokens from the local Keycloak |
| empty, local tokens set | `StaticTokenVerifier` | the four opaque `SP2_LOCAL_TOKEN_*` values |
| both unset | `DenyAllVerifier` | none — the service is healthy and authenticates nobody |

Both verifiers **already existed** in the Authentication Service (IC-005); this configures them.
Neither is a bypass, neither is reachable by omission, and the precedence is deliberate: a pinned
issuer always wins, so a stray development variable cannot widen the trust surface.

The four local static principals (the second posture only):

| Token variable | Principal | Role | Active tenant |
|---|---|---|---|
| `SP2_LOCAL_TOKEN_ACME_AGENT` | `local-agent-acme` | `TENANT_AGENT` | `acme` |
| `SP2_LOCAL_TOKEN_ZETA_AGENT` | `local-agent-zeta` | `TENANT_AGENT` | `zeta` |
| `SP2_LOCAL_TOKEN_NOVA_AGENT` | `local-agent-nova` | `TENANT_AGENT` | `nova` |
| `SP2_LOCAL_TOKEN_CONTROL` | `local-operator-control` | `CONTROL` | none (tenantless) |

The active tenant is the **signed claim** and the sole routing authority. No request parameter
can name a different one, which is why the ACME token can never read a ZETA record.

---

## 4. Start the databases

```bash
docker compose -f infrastructure/docker/docker-compose.rebuild.yml --env-file infrastructure/docker/.env.rebuild up -d --wait control-postgres acme-postgres zeta-postgres nova-postgres
```

Four **separate clusters**, not four databases in one — stronger than the contract requires, and
deliberate: a cross-tenant leak through a shared cluster (a `search_path` slip, a `dblink`, an
accidental fully-qualified name) is not merely forbidden, it is unreachable.

| Container | Database | Host port |
|---|---|---|
| `sp2_rebuild_control_pg` | `snackportal2_control` | `127.0.0.1:5550` |
| `sp2_rebuild_acme_pg` | `snackportal2_tenant_acme` | `127.0.0.1:5551` |
| `sp2_rebuild_zeta_pg` | `snackportal2_tenant_zeta` | `127.0.0.1:5552` |
| `sp2_rebuild_nova_pg` | `snackportal2_tenant_nova` | `127.0.0.1:5553` |

---

## 5. Migrate and bootstrap

```powershell
cd backend
.venv\Scripts\python.exe -m tools.local.sp2_local bootstrap
```

`bootstrap` = `migrate` then `seed`. Expected output:

```
Applying migrations (17 Control files, 14 tenant files x 3)
  -> control: applied 17 files, 001_distinctness_ledger.sql .. 017_bff_ingress_audit_append_only.sql
  -> acme: applied 14 files, 001_tenant_database.sql .. 003_roles.sql
  -> zeta: applied 14 files, ...
  -> nova: applied 14 files, ...
Seeding the Control database (local development identities only)
  -> 3 tenant registry rows (lifecycle ACTIVE, association assoc/<tenant> v1)
  -> 3 memberships, one principal per tenant and no principal in two
  -> 3 global directory records (fictional; no real company, no PII)
```

The chains are exactly the ones Stage 4 proved, in the same order, derived by globbing rather
than a hand-written list so a migration added later is picked up automatically:

```
Control:  infrastructure/db/control/001..015  +  backend/migrations/control/016, 017   (M-1)
Tenant:   infrastructure/db/provisioning/001..003
          infrastructure/db/tenant/001..008
          backend/migrations/tenant/            (currently empty)
          infrastructure/db/lineage/001..003
```

One transaction per file, so a mid-chain failure names the file that failed instead of rolling
back the evidence of the files that succeeded. No DSN or password is ever printed.

**What is seeded** — three record classes in the **Control** database only, all upserts, safe to
rerun. Nothing is written to a tenant database: tenant records are created *through the BFF*,
which is the only path that proves the request path works.

| Table | Rows | Content |
|---|---|---|
| `control_tenants` | 3 | `acme`, `zeta`, `nova`; lifecycle `ACTIVE`; association `assoc/<tenant>` version `1` |
| `control_memberships` | 3 | one synthetic principal per tenant; **no principal in two tenants** |
| `control_directory` | 3 | 2 global startups + 1 global investor, fictional, no PII |

To start over from an empty schema:

```powershell
cd backend
.venv\Scripts\python.exe -m tools.local.sp2_local bootstrap --reset
```

---

## 6. Start the identity provider

```powershell
cd backend
.venv\Scripts\python.exe -m tools.local.sp2_local idp-up
```

This one command does three things, and the order matters:

1. **Renders the realm.** `infrastructure/docker/keycloak/realm-sp2-local.template.json` is
   committed and carries password *placeholders*; the command substitutes the generated local
   passwords into `infrastructure/docker/keycloak/import/realm-sp2-local.json`, which is
   **gitignored** and is what the container mounts. A fresh checkout therefore reproduces realm,
   client, scopes, claim mappers and users without anyone clicking through an admin console.
2. **Starts Keycloak** and waits for its health check — which asks for the *realm*, not merely for
   the server, because a Keycloak that started and imported nothing passes a liveness probe and
   fails every login.
3. **Pins the trust anchor.** It reads that realm's own RS256 **public** key from the public realm
   endpoint and writes `SP2_AUTHENTICATION_ISSUERS` into your untracked env file. Asking the
   provider for the key — rather than generating one here — is what makes it impossible for the
   anchor and the signer to disagree.

Expected output ends with:

```
IDP: READY — http://localhost:8090/realms/sp2-local
        client sp2-local-web (public, Authorization Code + PKCE S256), audience snackportal2-bff
        redirect http://localhost:5173/sp2-gateway/callback
        sign in as: acme-agent, control-operator, nova-agent, zeta-agent
```

**The four local identities.** The Keycloak *user id* is the `sub` claim, and `sub` is the
principal reference the Control database's memberships are keyed by — which is why Stage 6A
changed no seed:

| Log in as | `sub` (principal) | `role` | Active tenant |
|---|---|---|---|
| `acme-agent` | `local-agent-acme` | `TENANT_AGENT` | `acme` |
| `zeta-agent` | `local-agent-zeta` | `TENANT_AGENT` | `zeta` |
| `nova-agent` | `local-agent-nova` | `TENANT_AGENT` | `nova` |
| `control-operator` | `local-operator-control` | `CONTROL` | none (tenantless) |

Their passwords are generated by `init-env` into `infrastructure/docker/.env.rebuild` under
`SP2_LOCAL_IDP_PASSWORD_<TENANT>` / `_CONTROL`. **No command in this runbook prints them.**

> **The active tenant is not in the principal token.** It arrives only on a token minted with the
> optional scope `sp2:tenant:<tenant>`, and requesting that scope is not permission to use it:
> membership is decided by the Access Control Service against the Control database. An ACME
> identity *can* ask Keycloak for a ZETA-scoped token; the BFF answers `403`.

> ⚠️ **This switches the Authentication Service's posture.** A pinned issuer WINS over the four
> opaque local tokens, deliberately — a deployment must never hold two live trust anchors. From
> here the `SP2_LOCAL_TOKEN_*` values authenticate nobody, and `smoke` notices and obtains a real
> OIDC token through the same Authorization Code + PKCE flow the browser uses.

To import the realm from scratch — which you need after `init-env --force`, because an
already-imported realm keeps its old passwords:

```powershell
cd backend
.venv\Scripts\python.exe -m tools.local.sp2_local idp-up --reset
```

The admin console is at `http://localhost:8090/admin/` (`SP2_LOCAL_IDP_ADMIN_USER`, default
`sp2-local-admin`). No documented step needs it; it exists for inspection.

---

## 7. Start the backend

```bash
docker compose -f infrastructure/docker/docker-compose.rebuild.yml --env-file infrastructure/docker/.env.rebuild up -d --wait
```

The first run builds the image (`backend/Dockerfile`); later runs reuse it. `--wait` blocks until
every health check passes, so a successful exit means the stack is actually up.

**Only the BFF is published**, on `127.0.0.1:8000`. The other thirteen services bind `0.0.0.0`
*inside their own container namespace* — which the exposure model explicitly permits, because
that binding reaches only the container network — and publish nothing. The distinction is
**BIND vs PUBLISH**; adding a `ports:` clause to any internal service is a contract violation,
not a convenience.

---

## 8. Verify the backend

```powershell
cd backend
.venv\Scripts\python.exe -m tools.local.sp2_local verify
```

This checks five things and prints each:

1. the BFF answers `/health`, `/readiness` and `/openapi.json` **from the host**;
2. all **fourteen** services answer health, readiness and `/openapi.json` **from inside the
   private network** (probed from within the BFF container, because that is the only place they
   are reachable from), and every generated document is **OpenAPI 3.1.0**;
3. exactly one **application** service publishes a port, read from the *running* stack rather
   than from the manifest — the manifest already has a static gate, and this answers the
   different question of what is actually listening;
4. no internal service port answers on `127.0.0.1`;
5. the identity provider serves the realm, advertises **PKCE S256**, stamps the issuer it was
   pinned to, and is the **only** issuer the Authentication Service trusts. An anchor for a
   different issuer authenticates nobody, and the symptom is a `401` that says nothing about why.

Expected: `14/14`, **80 operationIds, 80 unique**, `VERIFY: PASS`.

> Ports 8001-8005 are also the *legacy* standing topology's ports. If something answers there,
> `verify` says so rather than failing — this manifest publishes nothing on them, so an answer
> means an unrelated process. Check what it is.

The repository's own contract gates cover the same ground statically:

```powershell
cd backend
..\backend\.venv\Scripts\python.exe -m pytest tests/snackportal2 -q
```

---

## 9. Start the frontend

The frontend is the Lovable **`snack-cosmos`** repository — a **separate repository**, not a
directory of this one. `frontend/` here is an empty placeholder.

```bash
git clone https://github.com/Pitchsnack/snack-cosmos.git
cd snack-cosmos
bun install          # the repository has a bun.lock
cp .env.example .env.local
```

Then fill in `.env.local` — it is gitignored. Five SnackPortal2 values, and they must match the
realm §6 imported **byte for byte**:

```
VITE_SP2_GATEWAY_BASE_URL=http://localhost:5173/sp2-api
VITE_SP2_OIDC_ISSUER=http://localhost:8090/realms/sp2-local
VITE_SP2_OIDC_CLIENT_ID=sp2-local-web
VITE_SP2_OIDC_REDIRECT_URI=http://localhost:5173/sp2-gateway/callback
VITE_SP2_OIDC_POST_LOGOUT_REDIRECT_URI=http://localhost:5173/sp2-gateway
```

**All four OIDC values or none.** The bootstrap resolver has exactly three outcomes — `real`,
`dev_mock` (every real-integration variable absent), and `fail_closed` for anything in between.
Partial configuration is forbidden on purpose: mixed mock/real configuration is what lets a mock
answer a request someone believes went to the backend.

`VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` must also be present or the app cannot
boot at all — `src/integrations/supabase/client.ts` throws when either is missing. That is the
interim data layer (D-7), untouched by this procedure and unused by the tested Startup path.

```bash
bun run dev
```

The dev server is pinned to `localhost:5173` with `strictPort`, so it refuses to start rather
than silently moving — a moved dev server breaks the fixed OIDC `redirect_uri`, which is
registered against one exact origin.

See [`Stage6_Frontend_To_BFF_Integration.md`](Stage6_Frontend_To_BFF_Integration.md) for what
changed in the frontend and why — it is written against the real `snack-cosmos` source.

---

## 10. Log in through the browser

Open **`http://localhost:5173/sp2-gateway`** and walk the journey:

1. The panel says **Sign in** (not "Configuration unavailable" — that is the fail-closed state and
   means one of the five values above is missing or malformed). Click **Sign in**.
2. The browser is redirected to `http://localhost:8090/…` — the local Keycloak login page, titled
   *Sign in to SnackPortal2 local development*.
3. Sign in as **`acme-agent`** with `SP2_LOCAL_IDP_PASSWORD_ACME` from your untracked env file.
4. The callback returns to `/sp2-gateway`. **Memberships** lists `acme` with role `TENANT_AGENT` —
   that answer came from the Control database, through the BFF.
5. Click **Select**. A *second* Authorization Code + PKCE round runs with the optional scope
   `sp2:tenant:acme`, and its token carries the signed `active_tenant` claim. Keycloak's SSO
   session means no second password prompt.
6. **Startups — acme** lists that tenant's records. Pick one with **Open**, or type a name and
   **Create** — a create returns the record reference the *server* minted, and the journey opens
   it. The browser holds no hard-coded tenant record reference and never fabricates one.
7. Edit **Short description** and **Save**. That is a `PATCH` through the BFF, and it emits an
   ingress-edge audit event in the Control database.
8. **Sign out** ends the Keycloak session and returns to `/sp2-gateway`.

To see isolation from the browser: sign out, sign in as **`zeta-agent`**, select `zeta`, and the
Startups panel is empty. The ACME records are not merely hidden — they are in another database.

**What the Network tab must show.** Every application API request goes to
`http://localhost:5173/sp2-api/…`, the dev-server proxy that forwards to the BFF. Exactly one
request goes elsewhere: the OIDC token exchange to `http://localhost:8090`, which is the browser
talking to its identity provider and never passes through the BFF. **No request to a retired
Gateway port** (`8080`, `8820`), and none to Supabase on this path.

A request that reaches the BFF without a bearer token is answered `401 unauthenticated` — that is
the correct response, not a misconfiguration.

---

## 11. Run one sample request

The supported check runs the whole flow and proves physical isolation:

```powershell
cd backend
.venv\Scripts\python.exe -m tools.local.sp2_local smoke
```

It creates a Startup in ACME through the BFF, reads it back, presents the same record reference
with the **ZETA** identity (expecting `404` — a reference minted for another tenant is not found),
queries all three tenant databases directly, checks the Control database holds the ingress-edge
audit event and no tenant table, and then imports a global directory record and checks the
lineage row carries a real keyed D-23 marker.

**It follows whichever posture is live.** With a pinned issuer configured (§6) it obtains real
OIDC tokens through the *same* Authorization Code + PKCE flow the browser uses — same public
client, same redirect URI, same exchange; no password grant, no client secret, no admin API — and
first checks the claim contract:

```
0. Credentials — whichever posture the Authentication Service is actually in
  -> pinned issuer configured -> obtaining real OIDC tokens (Authorization Code + PKCE S256)
  -> ACME token claim names: sub, role, active_tenant, aud, iss, exp
  ->   sub=local-agent-acme  role=TENANT_AGENT  active_tenant=acme
  -> principal-only token (no tenant scope) carries active_tenant: None
```

With no pinned issuer it uses the four opaque local tokens instead.

By hand, if you prefer — take the ACME token from your untracked env file (static posture only):

```bash
curl -sS -X POST http://127.0.0.1:8000/tenant/startups \
  -H "Authorization: Bearer <SP2_LOCAL_TOKEN_ACME_AGENT>" \
  -H "Content-Type: application/json" \
  -d '{"display_name":"Example Ltd","short_description":"hello","investment_stage":"seed"}'
```

The response is the contract-pinned eight-field tenant Startup shape. It carries **no URL, no
email, no owner reference and no tenant identifier** — a website *is* accepted, normalized and
stored, it is simply never surfaced.

---

## 12. Inspect a tenant database

```bash
docker compose -f infrastructure/docker/docker-compose.rebuild.yml exec acme-postgres psql -U sp2_local -d snackportal2_tenant_acme -c "SELECT id, company_name, company_url, global_startup_id FROM startups ORDER BY id;"
```

Substitute `zeta-postgres` / `snackportal2_tenant_zeta` (and `nova`) to confirm the record is
**not** there. The Control database holds no tenant business records at all:

```bash
docker compose -f infrastructure/docker/docker-compose.rebuild.yml exec control-postgres psql -U sp2_local -d snackportal2_control -c "\dt"
```

The ingress-edge audit trail is Control-resident and append-only:

```bash
docker compose -f infrastructure/docker/docker-compose.rebuild.yml exec control-postgres psql -U sp2_local -d snackportal2_control -c "SELECT action, outcome, source_service, actor_ref, tenant_ref, record_ref FROM control_ingress_audit ORDER BY 1;"
```

After the browser journey the `actor_ref` values are the OIDC `sub` claims — `local-agent-acme`,
not a Keycloak UUID — because the realm pins each user's id to the principal reference the
Control database's memberships are keyed by. Every row carries `source_service = bff`, and the
table has no column that could hold a token, a password or a DSN.

---

## 13. Stop the frontend and the services

Stop the dev server with `Ctrl+C` in its terminal, then:

```bash
docker compose -f infrastructure/docker/docker-compose.rebuild.yml --env-file infrastructure/docker/.env.rebuild stop
```

`stop` leaves the containers and volumes in place; `start` brings them back with the data intact —
including the identity provider's realm and its signing key, so the pinned anchor stays valid.

---

## 14. Stop the databases and remove the stack

```bash
docker compose -f infrastructure/docker/docker-compose.rebuild.yml --env-file infrastructure/docker/.env.rebuild down
```

Containers and the network are removed; **named volumes survive**, so your data does too — and so
does the identity provider's realm, including the RSA key the pinned anchor was taken from.

---

## 15. Reset local data

Two levels, from cheapest to most complete:

**Schema-level** — keeps the containers, reapplies every migration from zero, reseeds:

```powershell
cd backend
.venv\Scripts\python.exe -m tools.local.sp2_local bootstrap --reset
```

**Volume-level** — destroys the clusters entirely:

```bash
docker compose -f infrastructure/docker/docker-compose.rebuild.yml --env-file infrastructure/docker/.env.rebuild down -v
```

Then repeat steps 4-7.

**Identity-provider level** — reimports the realm from scratch with the current passwords and
re-pins the trust anchor:

```powershell
cd backend
.venv\Scripts\python.exe -m tools.local.sp2_local idp-up --reset
```

> **Regenerating the env file invalidates lineage, and desynchronises the realm.** Key rotation is
> **not designed** (it is explicitly out of Stage 6 scope). Changing `SP2_LINEAGE_KEY_<TENANT>`
> means every lineage row already written under the previous key can no longer be verified — the
> row keeps its marker, but the marker no longer recomputes. And an *already-imported* realm keeps
> the passwords it was imported with, so new `SP2_LOCAL_IDP_PASSWORD_*` values will not work until
> the realm is reimported. If you run `init-env --force`, also run `bootstrap --reset` **and**
> `idp-up --reset`.
>
> **A volume-level reset changes the realm's signing key.** `down -v` destroys the identity
> provider's data, so the next start generates a new RSA key and every token it issues is signed
> with it. Run `idp-up` again — it re-reads the key and rewrites the anchor. Skipping it produces
> a successful login followed by `401` on every request.

---

## 16. Troubleshooting

**`docker compose up` fails immediately naming a variable**
The manifest uses `${VAR:?message}` for everything a launch cannot proceed without, so the error
names the missing variable. Run `init-env`, or check you passed
`--env-file infrastructure/docker/.env.rebuild`.

**Every request returns `401 unauthenticated`**
The Authentication Service is not accepting the credential you presented. Three causes, in order
of likelihood:

- *The anchor and the signer disagree.* The realm's key changed (a `down -v`, or a first launch)
  and `SP2_AUTHENTICATION_ISSUERS` still holds the old one. Run `idp-up`.
- *The container has not picked the anchor up.* The verifier is resolved **once, at import**, so
  the Authentication Service must be recreated after the variable changes. `idp-up` does that for
  you when the service is already running.
- *You are mixing postures.* A non-empty issuer configuration WINS over the four
  `SP2_LOCAL_TOKEN_*` values, so those tokens stop working the moment §6 runs. Use a real OIDC
  token (or clear the issuer variable and recreate the container).

With **neither** set, the service runs its fail-closed deny-all verifier: healthy, and
authenticating nobody.

**The browser shows "Configuration unavailable"**
That is the frontend's `fail_closed` posture, not a backend failure. It means the five
`VITE_SP2_*` values are partially set or one is malformed — all four OIDC values plus the base URL
must be present, and the base URL must be an absolute `http(s)` URL. Restart the dev server after
editing `.env.local`; Vite reads env at startup.

**Sign-in reaches Keycloak and is refused, or the callback fails**
The `redirect_uri` must match the realm registration byte for byte, including the `localhost`
spelling — `127.0.0.1:5173` is a different origin to a browser and is not registered. Confirm
the dev server really is on `5173` (it is `strictPort`, so it fails rather than moves).

**Login succeeds and every tenant request returns `403 access_denied`**
Authentication worked and authorization did not — the token's `sub` has no membership for the
tenant it named. `sub` is the Keycloak *user id*, which the realm pins to the principal reference
(`local-agent-acme`), so this means the realm and the seed have drifted. Run `seed`, and
`test_stage6_local_launch.py` if you changed either — it fails when they disagree.

**A tenant request returns `403 carrier_mismatch`**
The `X-Tenant-Id` header disagrees with the token's signed `active_tenant` claim. That is the
carrier check working: a carrier is match-or-reject only and never selects anything. Requesting a
`sp2:tenant:<other>` scope is likewise not permission to use it — membership decides.

**Every request returns `403 access_denied`**
Authentication worked and authorization did not. Almost always a missing membership: run `seed`,
and confirm the principal your token maps to has a `control_memberships` row for the tenant its
claim names. `test_stage6_local_launch.py` fails if the seed and the token map disagree, so this
should not survive a test run.

**Tenant operations return `503 tenant_unavailable`**
The Database Router resolved nothing. Three causes, in order of likelihood: the tenant is not
seeded (`lifecycle_state` must be exactly `ACTIVE`); the `SP2_TENANT_DSN_ASSOC_<TENANT>_1`
variable does not exist (the router derives that name from the seeded association — the two are
two halves of one fact); or the tenant cluster is not healthy.

**Import returns `503`**
Almost certainly a lineage key. Each tenant needs `SP2_LINEAGE_KEY_<TENANT>` of at least 32
characters. There is no default and no shared fallback: a tenant whose key is absent, empty or
placeholder-short cannot be imported into at all, rather than being written without provenance.

**Docker Desktop dies mid-build**
Check `backend/.dockerignore` exists. Without it the build context is ~1.1 GB (`backend/.venv`
alone is ~871 MB) and the daemon receives all of it before the first instruction runs — enough
to take the WSL engine down. With it, the context is ~48 kB.

**`ModuleNotFoundError: httpx` inside a container**
The image predates the runtime-dependency fix. Rebuild:
`docker compose -f infrastructure/docker/docker-compose.rebuild.yml build --no-cache`.

**Port 8000 or 5550-5553 already in use**
Something else is bound. Note that ports 8001-8005 belong to the *legacy* standing topology
(`backend/tools/local/start-sp2-local.ps1`) — do not run both stacks at once.

**`verify` cannot probe the private network**
It runs `docker compose exec` inside the BFF container. If the BFF is not healthy, fix that
first: `docker compose -f infrastructure/docker/docker-compose.rebuild.yml logs bff`.

**The Stage 4 live-PostgreSQL suite fails when pointed at THIS stack**

Do not point `tests/snackportal2/requires_pg` at the Stage 6 clusters. It needs four
**disposable** clusters that nothing else is touching, and it will report failures here that are
not defects. Two distinct causes, both measured:

- *The running services.* Several tests assert a session **delta** on `pg_stat_database.sessions`
  — "a denied request opened no tenant session", "an ACME request opened a session on ACME and on
  nothing else". Fourteen live services connecting to the same clusters make those deltas
  meaningless. Stopping the application services removed 4 of 7 failures.
- *This manifest's health checks.* The remaining 3 are caused by `pg_isready`, which opens a real
  session every `interval: 5s` on **every** cluster. Measured on a completely idle stack: **+4
  sessions per cluster over 15 seconds**, which is why the failures show `{'acme': 1, 'zeta': 1,
  'nova': 1}` — one on each, simultaneously. No application does that; a liveness probe does.

The health checks are kept, because they are what makes `up -d --wait` mean the stack is actually
up. Run the live suite the way it is designed to be run — against four throwaway clusters with no
other client and no health probe:

```bash
docker run -d --name sp2_disp_control -e POSTGRES_USER=sp2_disp -e POSTGRES_PASSWORD=<throwaway> -e POSTGRES_DB=snackportal2_control -p 127.0.0.1:5560:5432 postgres:17
# ... repeat for acme/zeta/nova on 5561/5562/5563
# then export SP2_STAGE4_CONTROL_DSN / _ACME_DSN / _ZETA_DSN / _NOVA_DSN and run:
python -m pytest tests/snackportal2/requires_pg -q      # 235 passed
docker rm -f sp2_disp_control sp2_disp_acme sp2_disp_zeta sp2_disp_nova
```

The supported local check for this stack is `sp2_local verify` and `sp2_local smoke`, which assert
against the databases directly and do not depend on session counts.

---

## Appendix — the supported command set

**Run every `python -m tools.local.sp2_local` command from `backend/`.** Run every
`docker compose` command from the repository root.

| Command | What it does |
|---|---|
| `python -m tools.local.sp2_local init-env` | generate the untracked env file with fresh local values |
| `python -m tools.local.sp2_local migrate [--reset]` | apply the accepted migration chains to all four databases |
| `python -m tools.local.sp2_local seed` | write the minimum Control rows (idempotent) |
| `python -m tools.local.sp2_local bootstrap [--reset]` | migrate, then seed |
| `python -m tools.local.sp2_local idp-up [--reset]` | render the realm, start the identity provider, pin its key as the trust anchor |
| `python -m tools.local.sp2_local verify` | 14 services healthy, OpenAPI 3.1, BFF-only ingress, IdP realm + anchor |
| `python -m tools.local.sp2_local smoke` | one real authenticated Startup flow + isolation evidence |
| `docker compose -f infrastructure/docker/docker-compose.rebuild.yml --env-file infrastructure/docker/.env.rebuild up -d --wait` | start everything |
| `... stop` / `... down` / `... down -v` | stop / remove / remove with volumes |

## Appendix — secret hygiene

- `infrastructure/docker/.env.rebuild` is **gitignored** and holds local throwaway values only.
- The committed template holds **placeholders only**, and its secret lines are empty.
- `infrastructure/docker/keycloak/realm-sp2-local.template.json` is **committed** and carries
  password *placeholders* (`__SP2_LOCAL_IDP_PASSWORD_*__`). The rendered realm — the one with real
  values — is written to `infrastructure/docker/keycloak/import/`, which is **gitignored**. The
  browser client is **public and has no secret**, so there is none to leak.
- `SP2_AUTHENTICATION_ISSUERS` holds a **public** key and an issuer URL. Not a secret, but written
  by `idp-up` rather than by hand, because it must match the running realm exactly.
- The frontend's `.env.local` is **gitignored**. Everything a `VITE_` variable holds ships to the
  browser, so nothing secret may go in one — the OIDC issuer, client id and redirect URI are all
  public values by design.
- No DSN, password, token or lineage key is printed by any command in this runbook.
- `docker compose config` **does** render interpolated values, including the local password. It
  is a debugging command; do not paste its output anywhere.
- Never point any of these variables at a real database, a real identity provider, or a real
  secret. Nothing in this procedure is a production configuration.
