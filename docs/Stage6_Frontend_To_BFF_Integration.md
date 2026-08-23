# Stage 6 — Frontend to BFF Integration

**Status:** transport **VERIFIED**; authenticated in-browser journey **BLOCKED** on a local
identity provider.

The frontend is the Lovable **`snack-cosmos`** repository — a **separate repository**, not a
directory of this one. `frontend/` here is an empty placeholder with zero tracked files, and there
is no submodule. Everything below is written against the real code at
`origin/main` = **`c34942ebb326c04c2b5023873e8ab97f83bbb96b`** ("Merge pull request #6 from
Pitchsnack/gate-a/fenv-b", 2026-08-06), which is the commit a local worktree was verified against.

---

## 1. The headline: no client code has to change

The target architecture is `Frontend → BFF` (D-46), not `Frontend → API Gateway`. The important
finding is that **the frontend's SP2 client is already wire-compatible with the BFF.**

`src/lib/sp2/gateway-client.ts` calls exactly three operations:

| Frontend call | Method + path it emits | BFF operation |
|---|---|---|
| `listMemberships` | `GET /memberships` | `listWorkspaceMemberships` |
| `getTenantStartup` | `GET /tenant/startups/{ref}` | `readActiveTenantStartup` |
| `updateTenantStartup` | `PATCH /tenant/startups/{ref}` | `updateActiveTenantStartup` |

It sends `Authorization: Bearer <token>` on every call and `X-Tenant-Id` when a tenant is in play.
Those are precisely the BFF's own carriers: the bearer credential it validates through the
Authentication Service, and the **one** recognized tenant carrier header. Nothing in the client
needs re-pointing at a different shape.

What was missing was purely **transport**: which origin those requests go to, and whether the
browser is allowed to make them.

---

## 2. What changed, and why

One file: `vite.config.ts`. Plus a documentation-only edit to `.env.example`.

### 2.1 A dev-server proxy, not CORS on the backend

```ts
vite: {
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/sp2-api": {
        target: process.env.VITE_SP2_BFF_PROXY_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/sp2-api/, ""),
      },
    },
  },
}
```

The frontend previously had **no dev proxy at all**, so the browser would call the BFF
cross-origin (dev server → `:8000`). That needs a CORS policy on the public ingress, and **the
Option A rebuild has no CORS middleware**.

Adding one was rejected deliberately. CORS on the BFF is a decision about *what the public ingress
permits* — a contract question about the one process facing the internet — not a local-launch
convenience. A proxy makes the call **same-origin**, so the question does not arise and nothing
about the deployed ingress is changed to suit a development machine.

It also removes a failure mode the frontend's own `.env.example` already warns about: a
one-character origin mismatch produces a **silent** browser-side CORS block. The preflight is
answered `204`, the browser then never sends the real request, and nothing appears in any server
log.

### 2.2 The dev-server port is pinned strictly

The default is `host: "::"`, `port: 8080`, with **no `strictPort`** outside a Lovable sandbox, so
Vite silently increments when the port is taken — and `8080` is inside the range the *retired*
local backend topology occupied. A silently-moved dev server breaks the fixed OIDC `redirect_uri`,
which is registered against one exact origin. Refusing to start is visible; moving is not.

### 2.3 `VITE_SP2_GATEWAY_BASE_URL` keeps its name

Set it to the **dev server's own origin plus the prefix**:

```
VITE_SP2_GATEWAY_BASE_URL=http://localhost:5173/sp2-api
```

It must remain an **absolute** `http(s)` URL. `resolveSp2BootstrapPosture()` parses it with
`parseAbsoluteHttpUrl`, and a bare path resolves to `fail_closed`.

The name was **not** changed. "Gateway" appears in 497 lines across 37 files — identifiers
(`SnackPortalGatewayClient`, `GatewayOutcome`, `getGatewayBaseUrl`), route paths (`/sp2-gateway`),
and user-visible strings. Renaming for correctness alone would be a large diff with no behavioural
gain, and Stage 6's brief is explicit about not creating churn. `.env.example` now states plainly
what the variable addresses, because the Gateway *semantics* it was named for no longer exist.

**Renaming remains outstanding work** — see §6.

---

## 3. What was verified, and how

Against the running Stage 6 backend stack (BFF on `127.0.0.1:8000`, four PostgreSQL clusters,
seeded Control database):

| Check | Result |
|---|---|
| `bun run dev` starts | **PASS** — Vite 7.3.2, `http://localhost:5173/`, strict port honoured |
| Every request origin | **PASS** — all requests to `localhost:5173`; a filter for any other origin returned **no network requests recorded** |
| Retired Gateway used? | **NO** — nothing to `:8080`, `:8820`, or any Gateway path |
| Supabase reached? | **NO** — no request to any Supabase origin |
| Browser → BFF liveness | **PASS** — `fetch('/sp2-api/health')` → `200 {"status":"ok","service":"bff","version":"1.0.0"}`; the BFF identifies itself as the responder |
| Browser → BFF, unauthenticated | **PASS** — `fetch('/sp2-api/memberships')` → `401 {"status":401,"code":"unauthenticated"}`, the BFF's canonical envelope. No CORS block. |
| Authenticated `GET /memberships` through the proxy | **PASS** — `200`, and **byte-identical** to the same request made directly against `:8000` |
| Authenticated `GET /tenant/startups/{ref}` through the proxy | **PASS** — `200`, contract-pinned eight-field shape |
| Console errors | only the expected `401` from the deliberate unauthenticated probe |

The two authenticated calls used a Stage 6 local development token. That proves the whole
transport path — browser origin → dev-server proxy → BFF → Authentication → Access Control →
Database Router → Startup Service → ACME PostgreSQL — carries real traffic.

---

## 4. What is BLOCKED, and exactly why

**The in-browser authenticated journey does not run.** Navigating to `/sp2-gateway` renders:

> **Configuration unavailable** — The Gateway is not configured for this environment and no real
> authentication adapter has been provided. This journey is unavailable until the controlled-local
> Keycloak and Gateway are wired.

This is the route **behaving as designed**, not a defect introduced by Stage 6.
`resolveSp2BootstrapPosture()` has exactly three outcomes:

| Posture | Condition |
|---|---|
| `real` | base URL **and** all of issuer / clientId / redirectUri present and valid |
| `dev_mock` | **every** real-integration variable absent, and not production |
| `fail_closed` | anything in between — partial configuration is forbidden |

Setting the base URL without the OIDC quartet is therefore `fail_closed` **by design**: mixed
mock/real configuration is explicitly prohibited, and that prohibition is correct.

**The missing piece is an identity provider.** The Stage 6 local stack has four PostgreSQL
clusters and fourteen services; it has no Keycloak. The frontend's only real auth adapter is
`KeycloakSnackPortalAuthAdapter` — Authorization Code + PKCE against a Keycloak issuer.

Stage 6 deliberately did **not** close this gap, for three reasons:

1. **It would add a subsystem, not configuration.** A local Keycloak needs a realm, a public
   client, registered redirect URIs, and protocol mappers emitting a `role` claim carrying a
   `PlatformRole` value and an `active_tenant` claim — the two claims
   `snackportal2/services/authentication/verifier.py` requires. That is identity-provider design
   work, not local runtime packaging.
2. **The tenant-scoped half is unresolved in the frontend itself.** The route's `real` branch sets
   `demoStartupRef: ""` with the comment *"Tenant-scoped auth remains unsupported … the tenant
   journey fails closed before any startup load."* Even with a working Keycloak, the tenant
   Startup journey would not complete without frontend work.
3. **The brief forbids inventing an auth path.** "Do not invent a new authentication architecture
   … Stage 6 must not add an unauthenticated developer backdoor." Injecting a token into the
   frontend to bypass the adapter would be exactly that.

### What would close it

Both halves are **supported configuration**, not new mechanisms:

- **Backend.** Set `SP2_AUTHENTICATION_ISSUERS` on the `authentication` service to
  `{"<keycloak-issuer>": {"audience": "...", "algorithms": ["RS256"], "public_key_pem": "..."}}`.
  This path already exists and takes precedence over the local static tokens, so a development
  posture cannot silently persist. Asymmetric algorithms only.
- **Frontend.** Provide the four `VITE_SP2_OIDC_*` values matching that realm **byte-for-byte**,
  with `redirect_uri` registered against `http://localhost:5173/sp2-gateway/callback`.
- **Keycloak.** Protocol mappers emitting `role` (one of the six `PlatformRole` values) and
  `active_tenant` (the tenant reference). A token missing either, or carrying an unrecognized
  role, authenticates nobody — by design.
- **Frontend, additionally.** Resolve tenant-scoped token minting and the empty `demoStartupRef`
  so the tenant journey can proceed past membership listing.

---

## 5. Local procedure

```bash
# 1. Backend stack up and seeded — see docs/Local_Development_Runbook.md
# 2. Frontend
cd <path-to>/snack-cosmos
bun install
cp .env.example .env.local        # then fill it in; .env.local is gitignored
#    VITE_SP2_GATEWAY_BASE_URL=http://localhost:5173/sp2-api
#    VITE_SUPABASE_URL / VITE_SUPABASE_PUBLISHABLE_KEY must be present or the app cannot boot:
#    src/integrations/supabase/client.ts THROWS when either is missing.
bun run dev
```

Then open `http://localhost:5173/sp2-gateway` and inspect the Network tab. Every request must
target `localhost:5173`; the API calls appear as `/sp2-api/*`.

---

## 6. Outstanding, and explicitly not Stage 6 work

These are recorded so they are decisions rather than omissions. None prevents the local backend
launch, and none is a Stage 6 blocker.

1. **A local identity provider** (§4). The single blocker for the in-browser journey.
2. **Gateway → BFF renaming.** 497 lines across 37 files, including identifiers, the
   `/sp2-gateway` route paths and user-visible strings. A deliberate, reviewable rename — not a
   side effect of a local-launch change.
3. **The interim Supabase data layer.** `test/architecture/supabase-allowlist.json` records
   **243/243** direct SDK call sites still active. Re-pointing is incremental and per-operation by
   contract (IC-013 §22), never big-bang — and the BFF serves 17 operations against a frontend
   that expects far more, so most screens have nothing to re-point to yet.
4. **Secret hygiene in the frontend repository's history.** A `.env` carrying live Supabase values
   was tracked until `add2e5f`. Untracking fixed the tree, not the history: the publishable key and
   project URL remain retrievable from earlier commits. That is a **frontend-repository** matter
   and is named here only so it is not lost.
5. **A `test:sp2` script.** Four test files exist under `test/sp2/` with no npm script and no CI
   job; only `test:arch` runs.

---

## 7. Repository facts, for the record

| | |
|---|---|
| Repository | `https://github.com/Pitchsnack/snack-cosmos.git` |
| Verified commit | `c34942ebb326c04c2b5023873e8ab97f83bbb96b` (= `origin/main` as last fetched 2026-08-06) |
| Local worktree used | `D:\Pitchsnack\snack-cosmos-gateA-postmerge` |
| Stage 6 branch | `stage/06-frontend-to-bff`, commit `c6c3202` — **local only, not pushed, not merged** |
| Stack | TanStack Start + React 19 + Vite 7, via `@lovable.dev/vite-tanstack-config` |
| Package manager | **bun** (`bun.lock`; CI pins bun 1.3.14) |
| Dev command | `bun run dev` → `vite dev` |
| Files changed | `vite.config.ts` (proxy + strict port), `.env.example` (documentation only) |

> Up-to-dateness against GitHub *right now* was not re-verified; the local refs were last fetched
> 2026-08-06. Confirm with `git fetch origin` before relying on the commit identity above.
