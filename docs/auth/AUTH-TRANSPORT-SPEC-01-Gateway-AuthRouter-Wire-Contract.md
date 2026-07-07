# AUTH-TRANSPORT-SPEC-01 — Gateway ↔ Auth Router Authentication Wire Contract

**Status:** Governance capture (07E-3a) · **Type:** Internal transport wire contract (no runtime code)
**PRD:** `PRD_07E_3a_V1_Auth_Wire_Contract_Capture_GPT.md` · **Readiness review:** `PRD_07E_3a_V1_Auth_Wire_Contract_Capture_Readiness_Review_Claude.md` (ACCEPT AS EXECUTION-READY)
**Date:** 2026-07-08 · **Baseline:** `f6bc82ef513e50e0a860f80816a8e2c225b2d777`
**Governed by:** IC-005 (Authentication Routing Contract), IC-010 (API Gateway Contract). This spec adds **no normative change** to either; it captures the internal transport that 07E-3b will implement. Analogue of `docs/d15/D15-DISPATCH-SPEC-01-Gateway-Router-Dispatch-Wire-Contract.md` (dispatch), on the authentication edge.

> **Governance-only.** This document defines a wire contract. It authorizes **no** runtime code, no HTTP server, no transport client, no token validation, and no database access. Runtime is deferred to **07E-3b**. **B5-BLK-4 remains OPEN; Physical Multi-Database MVP is mandatory and NOT complete.**

---

## Section A — Scope and non-goals

**Scope.** This wire contract governs **only** the internal API Gateway ↔ Auth Router **authentication transport**: how the gateway hands an inbound authentication artifact to the Auth Router for validation and receives a references-only authenticated-principal result used to build the router-handoff `RequestContext`.

**Explicitly out of scope (this spec governs none of these):**
- public login routes; password login; password reset; OAuth provider UX/redirects
- token issuance; token refresh; key rotation; JWKS distribution
- authorization decisions; any permission matrix
- database routing; database access; tenant-database selection
- frontend / Lovable behavior
- the gateway↔database-router **dispatch** wire (that is `D15-DISPATCH-SPEC-01`, unchanged here)

This spec is the authentication analogue of the dispatch wire capture and follows the same discipline: **contracts precede code**; the wire is frozen before the runtime transport pair is built.

## Section B — Internal-only transport

The authentication transport is **internal-only** and mirrors the D-15 dispatch-server posture:
- **loopback bind by default** (e.g., `127.0.0.1`), internal path only;
- **NOT portal-reachable, NOT a public ingress**, never exposed to the Lovable frontend, tenant users, or investor/startup users;
- reached by the gateway over a **transport port** — never an in-process import of `auth_router` (IC-010 §M; DAG independence).

Proposed internal path (07E-3b MAY refine if documented and consistent):
```
POST /internal/auth/authenticate
```

## Section C — Request envelope (Gateway → Auth Router)

The request carries only the minimum for the Auth Router to validate the inbound artifact and resolve the active context. Conceptual envelope (versioned, mirroring the D-15 `v:1` convention):

```json
{
  "v": 1,
  "authorization": "Bearer <opaque-credential — never logged, never returned>",
  "recognized_carriers": ["authorization"],
  "correlation_id": "<correlation-id>"
}
```

Maps to the already-built seam `AuthenticatorPort.authenticate(authorization, recognized_carriers, correlation_id)` (`backend/api_gateway/ports.py:26`) — use those existing names.

Rules:
1. The **bearer credential** is sent **only** from the API Gateway to the Auth Router, for validation.
2. The bearer credential is **validated only by the Auth Router**; the gateway performs **no** JWT / signature / OIDC validation (IC-010 §D; `ports.py:20-23`).
3. The bearer credential **MUST NEVER be logged** (by either side).
4. The bearer credential **MUST NEVER be returned** in the response.
5. The bearer credential **MUST NEVER be included in audit output**.
6. The bearer credential **MUST NEVER be forwarded to the Database Router**.
7. `recognized_carriers` is a reference list — **evidence of accepted credential carriers**, per the IC-005 recognized-carrier enumeration (D-33: `authorization` bearer + tenant subdomain + `X-Tenant-Id`) — **not** an authorization decision and never a tenant selector at the gateway.
8. `correlation_id` is **technical correlation metadata only**.

Because the request carries a live credential, this wire is **more sensitive than the references-only dispatch wire** and its internal-only posture (Section B) is load-bearing.

## Section D — Response envelope (Auth Router → Gateway)

The success response is **references-only** and is **exactly** the existing 4-field `AuthContext` / `AuthResult` shape (`backend/api_gateway/models.py:61-74`, mirroring `backend/auth_router/models.py` `AuthContext`):

```json
{
  "correlation_id": "<correlation-id>",
  "principal_ref": "<principal-ref>",
  "active_tenant_id": "<tenant-id-or-null>",
  "role": "<role-or-null>"
}
```

**No additional success fields are permitted in this slice.**

**Forbidden response fields (never present):**
`token`, `refresh_token`, `session_cookie`, `JWKS`, key material, `secret`, `credential`, authorization header, `email`, `name`, display name, `profile`, PII, business payload, `roles` (plural), `memberships`, permission matrix, `is_control_context`, `database_url`, `dsn`, `database_name`, `tenant_database_id`, secret reference value, `DispatchDecision`, `RouteOutcome`.

**CONTROL context is DERIVED by the runtime** from `active_tenant_id is null` (a tenantless CONTROL principal) — it is **never** carried as an `is_control_context` field (`backend/api_gateway/gateway.py:115`; `backend/auth_router/tenant_context.py:24-30`).

The gateway builds the router-handoff `RequestContext` **exclusively** from this response (`backend/api_gateway/request_context.py:18-30`; IC-010 §G/§T; IC-005 D-33 §4.6). `role` and `active_tenant_id` are references; the **Database Router** binds the database solely from the signed claim — the gateway resolves no database.

## Section E — Failure mapping

Bound to the **existing** gateway fail-closed convention (`backend/api_gateway/models.py:143-166`): `unauthenticated()`→(401, `unauthenticated`), `forbidden()`/`carrier_mismatch()`→(403), `unavailable()`→(503, `unavailable`). **No new `public_code` is introduced** by this wire.

| Condition | Public result |
|---|---|
| Missing auth artifact | 401 `unauthenticated` |
| Malformed auth artifact | 401 `unauthenticated` |
| Invalid signature / invalid token | 401 `unauthenticated` |
| Expired token | 401 `unauthenticated` |
| Authenticated but no valid active tenant / role / membership context | 403 `forbidden` |
| Carrier mismatch (recognized carrier ≠ signed claim) | 403 `carrier_mismatch` |
| Auth dependency unavailable | 503 `unavailable` |
| Tenant-state read unavailable | 503 `unavailable` |
| Malformed Auth Router response | 503 `unavailable` |
| Transport timeout / connection failure | 503 `unavailable` |

Fail-closed: no error path may downgrade to a less-isolated outcome, default tenant, or fallback; no rejection may leak tenant existence (IC-010 §L).

## Section F — Two-stage authority (Auth Router owns both stages)

The **Auth Router** owns authentication end-to-end:
- **Stage 1 — artifact validation.** OIDC stateless JWT validation (issuer/audience/exp/kid + signature), DB-free (IC-005; `backend/auth_router/jwt_validation.py`).
- **Stage 2 — context resolution.** Tenant/membership/role/readiness resolution via the approved control-plane read (`backend/auth_router/tenant_context.py`; `http_control_plane_read.py`), failing closed if that read is unavailable.

The **API Gateway** performs **neither** Stage 1 **nor** Stage 2; it receives only the resolved references. The Auth Router **does not emit** a Database Router `RequestContext`; the gateway constructs `RequestContext` exclusively from the Auth Router output, preserving IC-010 boundaries (and IC-005's sole-single-edge-emitter reconciliation — the gateway remains the sole audit emitter; the Auth Router detects/signals only).

## Section G — Never-cross rules

**Never cross Auth Router → API Gateway:**
raw token, authorization header, session cookie, JWKS, private key, secret, credential, password, database URL, DSN, database name, tenant database handle, database password, permission matrix, membership list, business payload, PII payload, email, display name, full profile.

**Never cross API Gateway → Auth Router:**
database routing decision, database handle, Database Router `DispatchDecision`, `RouteOutcome`, tenant database DSN, business payload unrelated to authentication.

**Never cross to Database Router (via `RequestContext`):**
raw token, authorization header, session cookie, PII payload, full profile, permission matrix. (`RequestContext` carries only its five reference fields; `shared/context.py:14-21`.)

## Section H — DAG / import boundaries

```
api_gateway  MUST NOT import auth_router
auth_router  MUST NOT import api_gateway
api_gateway  MUST NOT import database_router
auth_router  MUST NOT import database_router (unless already authorized by existing architecture)
```

Communication is over **transport ports only**; no in-process shortcuts. Enforced today by the import-linter *independence* contract (`backend/pyproject.toml`) and `backend/tests/architecture/test_phase7_api_gateway.py`; 07E-3b adds a module-scoped guard (Section I).

## Section I — 07E-3b runtime obligations (deferred; NOT authorized here)

The runtime follow-on (**07E-3b Runtime Auth Transport Pair**) MUST provide:
- gateway `http_authenticator` client (a stdlib/urllib transport client behind the existing `AuthenticatorPort`; **no** jwt/crypto/validation; maps the references-only response into `AuthResult`; collapses every failure to a fail-closed `RequestRejected` per Section E);
- `auth_router` `http_authenticate_api` server (internal-only, loopback, single-threaded stdlib; validates via the existing `auth_router` Authenticator; returns the 4-field response);
- a **module-scoped** architecture static guard (no `auth_router`/`database_router`/DB-driver/Supabase/`jwt`/crypto import in the gateway authenticator; no DSN; no token mint; no `DispatchDecision`; no `router.route(...)`; exact request/response envelope census; non-vacuity companions);
- behavioural **client** tests (vs a stub server) and **server** tests;
- fail-closed tests; references-only response validation;
- proofs: no JWT validation in the gateway; no database access in the gateway authenticator; **no token logging**; internal-only loopback exposure.

**Runtime implementation is explicitly deferred to 07E-3b and is NOT authorized by this spec.**

## Non-overclaim

This capture implements no authentication runtime, no HTTP server, no transport client, no token validation, no routing, and opens no database. It does not prove API Gateway completion, does not prove Physical Multi-Database MVP completion, and does not close B5-BLK-4. No IC-005 or IC-010 normative rule, prohibition, or frozen invariant is altered by this capture; the two contracts receive insert-only reference notes only.

## Forward testing / coverage requirements (owned by 07E-3b)

| Item | Classification | Owner |
|---|---|---|
| Runtime client/server behavioural tests | HARD-GATE before runtime | 07E-3b |
| Module-scoped no-JWT / no-import / no-DB static guard | HARD-GATE before runtime | 07E-3b |
| Internal-only loopback exposure proof | HARD-GATE before runtime | 07E-3b |
| Token redaction / no-token-log proof | HARD-GATE before runtime | 07E-3b |
| Live-PG DT-1..DT-8 | Not required (auth is DB-free) | — |

## STOP / governance note

STOP — AUTH-TRANSPORT-SPEC-01 is governance-only. No runtime code, no HTTP server, no transport client, no token validation, no database access is authorized by this document. Runtime is deferred to 07E-3b. B5-BLK-4 OPEN; Physical Multi-Database MVP mandatory and NOT complete.
