# SnackPortal2 — Local Development Runbook

**LOCAL / NON-PRODUCTION ONLY.** Nothing here authorizes a production deployment, a public
ingress, TLS termination, or a supervisor. Every credential this procedure creates is a
disposable local throwaway.

This is the supported way to run the **Option A rebuild** (D-46) — the FastAPI BFF plus the
thirteen internal services, against four physically separate PostgreSQL clusters — from a fresh
checkout.

Target experience, and what this document delivers:

```
fresh checkout -> configure -> start databases -> migrate -> seed -> start services
               -> verify 14 OpenAPI 3.1 contracts -> run a real tenant Startup flow
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

Everything below is run from the **repository root** unless a step says otherwise.

> **Ports this procedure uses.** BFF `127.0.0.1:8000`; PostgreSQL `127.0.0.1:5550-5553`.
> The 5550-5553 range is deliberately *not* 5540-5543, so this stack can run alongside the older
> `docker-compose.local.yml` fixture without a collision. Nothing else is published.

---

## 1. Clone / checkout

```bash
git clone https://github.com/Pitchsnack/SnackPortal2.git
cd SnackPortal2
```

Create the Python environment the operator command and the test suites use:

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -e "backend[dev]"
```

`-e backend[dev]` installs the backend package plus ruff, mypy, pytest, import-linter and httpx.

---

## 2. Copy the local env template

You do **not** fill it in by hand. Generate a filled, untracked copy with fresh random values:

```powershell
cd backend
..\backend\.venv\Scripts\python.exe -m tools.local.sp2_local init-env
cd ..
```

Or, equivalently, from the repository root:

```powershell
backend\.venv\Scripts\python.exe -m tools.local.sp2_local init-env
```

> The module is importable from either directory; the commands below use the repository root.

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
| `SP2_AUTHENTICATION_ISSUERS` | left empty | the production JWT posture; empty selects local tokens |
| `SP2_BFF_BASE_DOMAIN` | left empty | host-based tenant addressing off; `X-Tenant-Id` is the only carrier |

**Authentication.** With `SP2_AUTHENTICATION_ISSUERS` empty and the four local tokens set, the
Authentication Service selects `StaticTokenVerifier` — a **supported verifier that already
existed**, explicitly configured. It is not a bypass and not a new mechanism: with *both*
unset the service starts, reports healthy, and authenticates nobody. Setting the production
issuer configuration always wins over the local tokens.

The four local principals:

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
backend\.venv\Scripts\python.exe -m tools.local.sp2_local bootstrap
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
backend\.venv\Scripts\python.exe -m tools.local.sp2_local bootstrap --reset
```

---

## 6. Start the backend

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

## 7. Verify the backend

```powershell
backend\.venv\Scripts\python.exe -m tools.local.sp2_local verify
```

This checks four things and prints each:

1. the BFF answers `/health`, `/readiness` and `/openapi.json` **from the host**;
2. all **fourteen** services answer health, readiness and `/openapi.json` **from inside the
   private network** (probed from within the BFF container, because that is the only place they
   are reachable from), and every generated document is **OpenAPI 3.1.0**;
3. exactly one **application** service publishes a port, read from the *running* stack rather
   than from the manifest — the manifest already has a static gate, and this answers the
   different question of what is actually listening;
4. no internal service port answers on `127.0.0.1`.

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

## 8. Start the frontend

The frontend is the Lovable **`snack-cosmos`** repository — a **separate repository**, not a
directory of this one. `frontend/` here is an empty placeholder.

```bash
git clone https://github.com/Pitchsnack/snack-cosmos.git
cd snack-cosmos
bun install          # the repository has a bun.lock
bun run dev
```

Point its API client at the BFF. See
[`Stage6_Frontend_To_BFF_Integration.md`](Stage6_Frontend_To_BFF_Integration.md) for the exact
variable names, the values to use, and what must change — it is written against the real
`snack-cosmos` source, not from assumption.

---

## 9. Verify frontend-to-BFF

With the dev server running, in the browser's Network tab confirm that every API request goes to
the BFF's origin (`http://127.0.0.1:8000`, or the dev-server proxy path that forwards there) and
that **no request goes to a retired Gateway port** (`8080`, `8820`) or to Supabase.

A request that reaches the BFF without a bearer token is answered `401 unauthenticated` — that is
the correct response, not a misconfiguration.

---

## 10. Run one sample request

The supported check runs the whole flow and proves physical isolation:

```powershell
backend\.venv\Scripts\python.exe -m tools.local.sp2_local smoke
```

It creates a Startup in ACME through the BFF, reads it back, presents the same record reference
with the **ZETA** token (expecting `404` — a reference minted for another tenant is not found),
queries all three tenant databases directly, checks the Control database holds the ingress-edge
audit event and no tenant table, and then imports a global directory record and checks the
lineage row carries a real keyed D-23 marker.

By hand, if you prefer — take the ACME token from your untracked env file:

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

## 11. Inspect a tenant database

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
docker compose -f infrastructure/docker/docker-compose.rebuild.yml exec control-postgres psql -U sp2_local -d snackportal2_control -c "SELECT action, outcome, source_service, tenant_ref FROM control_ingress_audit ORDER BY 1;"
```

---

## 12. Stop the services

```bash
docker compose -f infrastructure/docker/docker-compose.rebuild.yml --env-file infrastructure/docker/.env.rebuild stop
```

`stop` leaves the containers and volumes in place; `start` brings them back with the data intact.

---

## 13. Stop the databases and remove the stack

```bash
docker compose -f infrastructure/docker/docker-compose.rebuild.yml --env-file infrastructure/docker/.env.rebuild down
```

Containers and the network are removed; **named volumes survive**, so your data does too.

---

## 14. Reset local data

Two levels, from cheapest to most complete:

**Schema-level** — keeps the containers, reapplies every migration from zero, reseeds:

```powershell
backend\.venv\Scripts\python.exe -m tools.local.sp2_local bootstrap --reset
```

**Volume-level** — destroys the clusters entirely:

```bash
docker compose -f infrastructure/docker/docker-compose.rebuild.yml --env-file infrastructure/docker/.env.rebuild down -v
```

Then repeat steps 4-6.

> **Regenerating the env file invalidates lineage.** Key rotation is **not designed** (it is
> explicitly out of Stage 6 scope). Changing `SP2_LINEAGE_KEY_<TENANT>` means every lineage row
> already written under the previous key can no longer be verified — the row keeps its marker,
> but the marker no longer recomputes. For a disposable local stack this is fine: if you run
> `init-env --force`, also run `bootstrap --reset`.

---

## 15. Troubleshooting

**`docker compose up` fails immediately naming a variable**
The manifest uses `${VAR:?message}` for everything a launch cannot proceed without, so the error
names the missing variable. Run `init-env`, or check you passed
`--env-file infrastructure/docker/.env.rebuild`.

**Every request returns `401 unauthenticated`**
The Authentication Service has no trust anchor and is running its fail-closed deny-all verifier.
Check that the four `SP2_LOCAL_TOKEN_*` values are set and that `SP2_AUTHENTICATION_ISSUERS` is
**empty** (a non-empty issuer configuration wins over the local tokens). Recreate the container
after changing them — the verifier is resolved once, at import.

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

---

## Appendix — the supported command set

| Command | What it does |
|---|---|
| `python -m tools.local.sp2_local init-env` | generate the untracked env file with fresh local values |
| `python -m tools.local.sp2_local migrate [--reset]` | apply the accepted migration chains to all four databases |
| `python -m tools.local.sp2_local seed` | write the minimum Control rows (idempotent) |
| `python -m tools.local.sp2_local bootstrap [--reset]` | migrate, then seed |
| `python -m tools.local.sp2_local verify` | 14 services healthy, OpenAPI 3.1, BFF-only ingress |
| `python -m tools.local.sp2_local smoke` | one real authenticated Startup flow + isolation evidence |
| `docker compose -f infrastructure/docker/docker-compose.rebuild.yml --env-file infrastructure/docker/.env.rebuild up -d --wait` | start everything |
| `... stop` / `... down` / `... down -v` | stop / remove / remove with volumes |

## Appendix — secret hygiene

- `infrastructure/docker/.env.rebuild` is **gitignored** and holds local throwaway values only.
- The committed template holds **placeholders only**, and its secret lines are empty.
- No DSN, password, token or lineage key is printed by any command in this runbook.
- `docker compose config` **does** render interpolated values, including the local password. It
  is a debugging command; do not paste its output anywhere.
- Never point any of these variables at a real database, a real identity provider, or a real
  secret. Nothing in this procedure is a production configuration.
