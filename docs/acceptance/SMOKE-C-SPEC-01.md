# SMOKE-C-SPEC-01 — Smoke C Acceptance Specification (integrated live local topology proof)

> ## ⛔ ITS HARNESS IS WITHDRAWN — the API Gateway has been DELETED
>
> This specification is retained as the **historical acceptance record** it always was, and its text
> is unchanged: it still describes `Gateway.handle`, `gateway ingress` and
> `build_dispatch_server_from_env`, because that is what Smoke C V2 was specified against.
>
> The executable side is gone. `tests/control_plane/requires_pg/smoke_c_integrated_live_proof.py`,
> its wrapper and its boundary guard were deleted with the topology they drove, and the blessed
> RS256 fixture this spec depends on moved from `tests/api_gateway/crypto_fixture.py` to
> **`tests/shared/crypto_fixture.py`**.
>
> **B5-BLK-4 is not closed and no longer has a live harness.** A Gateway-free Smoke C successor must
> be specified and authored before any integrated live proof may be cited for this architecture.

**Spec id/version:** `SMOKE-C-SPEC-01` v1.0 · **Authored under:** PRD B5-5 (specification slice)
**Status:** SPECIFICATION ONLY — this document **does not execute Smoke C**. Smoke C execution is a
separately Dan-authorized acceptance PRD (Fable5) run over this spec. Until that run is accepted:

```text
B5-BLK-4 OPEN.
Physical Multi-Database MVP mandatory and NOT complete.
Smoke C deferred / HARD-GATE.
```

---

## 1. Authority and boundary

Smoke C is the integrated live local topology proof anchored to, and only to:

- **AT-D15T1-3** (`docs/d15/D15-DISPATCH-SPEC-01-Gateway-Router-Dispatch-Wire-Contract.md`,
  Appendix A): *e2e one-request→one-tenant→one-DB + DB-granularity distinctness through the wire* —
  HARD-GATE before B5-BLK-4.
- **IC-010 §I** (Portal Boundary): clients/portals reach backend services only through the API
  Gateway; no direct database access; ingress is not added by any smoke.
- **IC-010 §K** (Isolation Contract): One Request -> One Active Tenant -> One Database; no request
  may access multiple tenant databases.
- **IC-010 §O** (Physical Multi-Database Rule): the Control Database and the Tenant Databases remain
  physically separate PostgreSQL databases; nothing may blur that boundary.

**Boundary of proof (no-overclaim, binding):** Smoke C proves a **local** integrated request path at
**database granularity** on the B5-4 standing cluster (two physically distinct tenant *databases* on
the local control cluster). **Cluster-level distinctness remains deployment-only scope**
(AT-D15T1-4); Smoke C proves nothing about production readiness, deployment, supervision, TLS,
ingress, durability, or scale. Invariants preserved throughout: Authentication != Routing !=
Authorization != Database Access; Global Record != Tenant Record; One Request -> One Active Tenant ->
One Database.

## 2. Preconditions (all mandatory at evidence time)

1. **B5-1 through B5-5 merged and post-merge verified on `main`**; the tested commit SHA is recorded
   in the evidence record and every claim binds to exactly that commit.
2. **Healthy B5-4 standing topology** — the read-only status command reports 6/6 PASS
   (`python tests/control_plane/requires_pg/b5_standing_topology.py status`, run from `backend/`,
   per `infrastructure/runbooks/b5_standing_topology.md`):
   - one standing Control DB (`snackportal2_control_local`) with control DDL 001–009 applied by the
     governed ops path (never at runtime — `create_app()` applies **no runtime DDL**);
   - at least two Ready tenants — the deterministic `b5_standing_alpha` and `b5_standing_beta` —
     onboarded through the real env-composed path;
   - two distinct physical tenant databases with complete tenant schemas;
   - external tenant DSN secret files outside the repository under `SNACKPORTAL_TENANT_SECRET_DIR`;
     secrets stay reference-only on every wire and in every record.
3. **No teardown, apply, registry mutation, or fixture repair during evidence capture** — the status
   command is the only permitted fixture interaction, and it is read-only.
4. **Freshly generated key/token material only**: the RSA keypair and every RS256 token are minted
   at run time by the B5-5 fixture (`backend/tests/api_gateway/crypto_fixture.py`). No static key,
   no pre-minted token, no committed token-shaped literal of any form, no persisted private
   material — the private key exists in process memory only.

## 3. Execution topology (pinned)

```text
InboundRequest -> Gateway.handle (IN-PROCESS) -> real Auth Router over the auth wire
              -> real Database Router over the dispatch wire -> exactly one physical tenant DB
```

- **Gateway driven in-process** via `Gateway.handle` (the Smoke A/B precedent —
  `tests/api_gateway/test_gateway_auth_and_router_transport_smoke.py` and
  `test_gateway_auth_router_db_doubles_topology_smoke.py`). **No gateway ingress server is added**:
  client ingress is deployment-owned (IC-010 §I/§M/§R); adding one is out of scope and prohibited.
- **Control Plane read edge env-composed** via `build_read_server_from_env`
  (`SP2_CP_READ_HOST` / `SP2_CP_READ_PORT`, B5-1) over the standing Control DB in the all-postgres
  posture; its URL feeds `SP2_AR_CONTROL_PLANE_READ_BASE_URL` and `SP2_DBR_ROUTING_READ_BASE_URL`.
- **Auth Router env-composed** via `build_authenticator_from_env` +
  `build_authenticate_server_from_env` (`SP2_AR_ISSUERS` carrying the fixture's **runtime public
  JWK**; `SP2_AR_AUTHENTICATE_HOST`/`_PORT`), hosted through the B5-2 entrypoint
  `serve_authenticate_api`.
- **Database Router dispatch server env-composed** via `build_dispatch_server_from_env`, hosted
  through the B5-2 entrypoint `serve_dispatch_api`.
- **Per-server hosting**: each server is hosted independently — either as separate operator-run
  processes via the B5-2 blocking entrypoints (`serve_read_api` / `serve_authenticate_api` /
  `serve_dispatch_api`) or on test-owned daemon threads each hosting exactly one server (the Smoke A/B
  in-suite precedent).

  > **Startup-order reference corrected.** This clause pointed operators at
  > `docs/runbooks/b5_service_startup_order.md`, which is **superseded for the served topology** (it
  > predates the FastAPI migration and states that the API Gateway has no inbound HTTP edge). The
  > canonical startup runbook is `docs/runbooks/backend_service_startup_fastapi.md`; the standing local
  > map is 8001 / 8002 / 8003 / 8004 / 8005 / 8820, and the `8080–8088` map there is isolated
  > smoke/verification only. The B5-2 `serve_*` entrypoints named above remain the retained
  > **compatibility** path, which is what this spec was written against.
- **No application threading inside any server** (AT-D15T1-10 HARD-GATE): no server creates a thread,
  daemon, subprocess, worker, or reload supervisor of its own, and the authorized process model is one
  worker and one operating-system process per edge. **No runtime DDL** anywhere on the path.

  > **Runtime correction (post-FastAPI/Uvicorn migration).** This clause originally read: *"every
  > server is the plain **single-threaded** `HTTPServer` — no `ThreadingHTTPServer`, no
  > `ThreadingMixIn`, no asyncio/concurrency machinery."* Two of those three statements are now false.
  > Every edge is a FastAPI application served by Uvicorn: there is no `HTTPServer` and no
  > `ThreadingHTTPServer` on the served path, and the runtime is **asyncio** by construction. What
  > survives, and what the HARD-GATE actually protects, is the process model above — no
  > *application-created* concurrency, one worker, one process. The single-threaded per-request
  > serialization that the original wording implied is **not** a property of the current runtime and
  > must not be relied on as a safety argument anywhere.
  >
  > The spec's identity, granularity, evidence and failure-mode obligations are unaffected; only this
  > runtime description changed.

## 4. Happy-path proof obligations (per tenant, twice)

For **tenant A (`b5_standing_alpha`)** and **tenant B (`b5_standing_beta`)** separately, one request
each MUST evidence that it:

1. uses a **freshly minted real RS256 token** (fixture-minted; `kid` + issuer recorded — never the
   token);
2. **authenticates through the real Auth Router** over the auth wire (real
   `PyJwtSignatureVerifier`, real `SP2_AR_ISSUERS` trust anchors, real control-plane read of the
   standing registry);
3. selects **exactly one active tenant** (RequestContext built exclusively from AuthContext —
   IC-010 §G/§T);
4. **dispatches through the real Database Router** over the dispatch wire (references only — no
   gateway-computed tenant identifier crosses the dispatch wire; the router binds solely from the
   signed claim);
5. **reaches exactly one physical tenant database** — the run records the selected database
   identity in redacted form (e.g. a `current_database()` readback), never a DSN, user, or
   password;
6. returns the expected database identity **without DSN leakage** anywhere in output or evidence;
7. **does not touch the other tenant database** — other-database non-touch evidence is mandatory:
   a references-only connection census (per-tenant open/bind census, Smoke B `factory.opens`
   precedent adapted to the live adapters) MUST show zero opens/binds for the other tenant's
   database during the request.

**Database-granularity distinctness across the two runs is mandatory:** the two recorded database
identities MUST be distinct databases on the standing cluster, matching the registered
distinctness/lineage records of the B5-4 fixture.

## 5. Failure-mode proof obligations (exact current envelopes — never invented)

The auth transport sanitizes denial codes by status bucket at the wire
(`http_authenticate_api._map_denied`): granular reasons never leak past the gateway edge. Both
layers are therefore pinned — the observable gateway envelope AND the in-process/audit-layer code:

| Scenario | Gateway-observed envelope (binding) | Auth-boundary code (in-process/audit layer) |
|---|---|---|
| Unknown tenant (valid token, unknown or non-member tenant claim) | **403 `forbidden`** — MUST be 403; **never 503** (B5-3 LW-1 live/doubles parity: live read-edge 404 maps to `None`, not an error) | `tenant_access_denied` (unknown tenant and non-member deny identically — no existence leak) |
| Tenant not Ready | **403 `forbidden`** — and **never routed**: no dispatch call, no connection bind | `tenant_not_ready` |
| Wrong tenant carrier (carrier != signed claim) | **403 `carrier_mismatch`** (rejected before any control-plane read) | `carrier_mismatch` |
| Control Plane unavailable (read edge down) | **503 `unavailable`** (fail-closed; no fallback, no default tenant) | `control_plane_unavailable` |
| Invalid signature (wrong key / tampered token) | **401 `unauthenticated`** | `bad_signature` |
| Unknown `kid` | **401 `unauthenticated`** | `unknown_kid` |
| Unknown issuer | **401 `unauthenticated`** | `unknown_issuer` |

Every failure-mode run MUST additionally evidence that no tenant database connection was opened.
Router-side denials retain their existing D-15 mappings (`not_found` /
`administratively_disabled` / version-unsupported) and are not redefined here. Wrong-carrier
failure evidence requires B5-3 semantics (merged); signature-class evidence requires the B5-5
fixture (`kid_override` / second-keypair legs).

## 6. Audit disclosure (mandatory, verbatim obligations)

The evidence record MUST state explicitly:

- **routing audit evidence is in-memory in this proof** (the Database Router's operational audit
  sink is the in-memory adapter);
- **DBR-AR-2 (durable routing audit) remains open** — a separate Database Router PRD;
- the evidence **must not imply durable persistence** of any audit record;
- gateway audit events (`RouteDenied` / `CarrierMismatch` / `CarrierOnControlAnomaly` /
  `IsolationAnomaly`) and auth audit outcomes (`denied:<code>`) follow the Global Audit
  Representation Rule — **references only**, never a name, email, PII, token, or payload.

## 7. Evidence record format (deterministic, redacted)

One evidence record per run, containing exactly and only:

```text
spec id/version                    (SMOKE-C-SPEC-01 v1.0)
tested commit SHA + timestamp      (claims bind to exactly this commit)
standing-topology identity         (redacted: scheme+host+port+database form; no credentials)
tenant id                          (b5_standing_alpha | b5_standing_beta)
token kid and issuer               (never the token, never a key)
request correlation id
auth outcome + routing outcome     (status, public_code, dispatched)
selected database identity         (redacted; no DSN, no user, no password)
other-database non-touch assertion (per-tenant connection census result)
status/error envelope              (for failure-mode runs)
audit-sink disclosure              (in-memory; DBR-AR-2 OPEN)
gate outputs                       (the battery run at the tested commit)
cleanup/residue statement          (fixture left standing; no teardown performed)
known limitations                  (local, database-granularity, in-memory audit)
```

**Prohibited in any record or output:** private key material, any JWT or token-shaped string,
DSN, password, secret value, or unredacted connection string. All identities are redacted to the
B5-4 redaction convention (scheme+host+port+database; no userinfo, no query).

## 8. Acceptance and stop rules

Smoke C **fails closed** if any required evidence is missing, ambiguous, not bound to the tested
commit, or leaks credentials/tokens; if any happy-path or failure-mode obligation in §4/§5 is not
met; if the standing fixture was mutated during capture; or if any output violates §7.

**This specification does not close anything.** Passing Smoke C later satisfies evidence
obligations of AT-D15T1-3 at local database granularity; **B5-BLK-4 closure itself remains a
separate, Dan-authorized decision**, and B6-BLK-3/5/6 policy rows are not closed by any smoke. This
spec makes **no MVP-completion claim** (Lovable cutover, fees/billing, and product-track scope are
untouched), no cluster-level distinctness claim, and no production/deployment claim.

## 9. Standing status (required, unchanged by this spec)

```text
B5-BLK-4 OPEN.
Physical Multi-Database MVP mandatory and NOT complete.
Smoke C deferred / HARD-GATE.
```
