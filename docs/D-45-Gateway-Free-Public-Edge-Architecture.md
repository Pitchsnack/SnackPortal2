# D-45 — Gateway-Free Controlled Local MVP Ingress Architecture

**Status:** ✅ Approved (explicit human architecture decision by Dan) · **Date approved:** 2026-08-11
**Type:** Architecture decision record · **Scope:** Controlled Local MVP ingress architecture, at the design/governance level
**Branch of record:** `experiment/complete-api-gateway-removal-mvp` (this decision is recorded on that branch only; `main` is untouched)
**Governing contracts:** IC-010 (retargeted), IC-011, IC-009, IC-012, IC-005, IC-002, IC-001, IC-007, IC-008
**Supersedes in part:** Canonical Overview locked invariant **#7**; decision **D-4** ("build the API Gateway next"); the *name* used by D-37 §5 for the client-facing boundary
**Evidence:** `docs/reports/SnackPortal2_Complete_API_Gateway_Zero_Residual_Removal_Result_Claude.md`, `docs/reports/SnackPortal2_Complete_API_Gateway_Removal_MVP_Experiment_Result_Claude.md`, `docs/runbooks/gateway_free_mvp_topology.md`

> **This decision authorizes no merge, push, PR, live runtime change, DDL change, SecretRef change, credential change, or Keycloak change.** It ratifies the architecture at the design/governance level so the official documents describe what the Controlled Local MVP actually is. **Only Dan may explicitly authorize the specific future PR merge. Gate B remains NOT GRANTED. Production remains NOT READY / DO-NOT-ACTIVATE.**

---

## 1. Decision

> **The SnackPortal2 Controlled Local MVP removes the API Gateway component and uses explicitly approved, route-owning, authenticated public edges.**

The official architecture no longer requires the API Gateway as the sole ingress or as the security boundary for the Controlled Local MVP. The architectural boundary is:

> **An approved authenticated public edge owned by the service that owns the public route.**

### 1.1 The ratified topology

```text
Frontend
   ├──> Public Startup Edge
   │       ↓
   │     shared authenticated public boundary
   │       ↓
   │     Auth Router
   │       ↓
   │     Database Router / tenant operations
   │       ↓
   │     one physical tenant database
   │
   └──> Public Workspace Edge
           ↓
         shared authenticated public boundary
           ↓
         Auth Router
           ↓
         narrow membership-read capability
           ↓
         Control DB
```

There is **no API Gateway component in the active MVP architecture**.

### 1.2 What an approved public edge must be (normative — IC-010 §A.1)

An approved public edge MUST:

1. use the **shared public-boundary security kernel**;
2. **authenticate through the Auth Router contract**;
3. derive **actor and tenant authority only from authenticated trusted state**;
4. serve **only the route family owned by its service**;
5. **not** operate as a generic **proxy, BFF, or cross-service dispatcher**;
6. enforce **fail-closed request validation before business/database work**;
7. **emit the required audit evidence for its own route**;
8. preserve **one request → one authenticated active tenant → one physical tenant database** for tenant-scoped operations.

### 1.3 The closed set of approved public edges (IC-010 §A.2)

| Approved public edge | Owning service | Route family it owns |
|---|---|---|
| **Public Startup edge** | `database_router` | the CLM tenant Startup routes (Tenant Operations) |
| **Public Workspace edge** | `control_plane` | `GET /memberships` (MembershipsForPrincipal) |

**Any new public edge requires explicit architecture/governance approval** — a register entry plus an IC-010 amendment naming the edge, its owning service, and the exact route family it may serve. Conformance to §A.1 is **not** authorization on its own. **No generic replacement Gateway may be introduced under another name** ("MVP Gateway", "thin Gateway", "lightweight Gateway", "BFF", "proxy layer" — the prohibited shape is the shape, not the label).

---

## 2. Rationale

- the Gateway was **not required as a distinct component** for the MVP;
- **route-owning edges can enforce the required security properties** through the shared public-boundary kernel and the existing Auth Router;
- **generic cross-service dispatch is removed** — a request cannot be re-aimed at a service that does not own its records;
- **Startup and Workspace route ownership is explicit** — no route family has two possible answers to "who serves this?";
- the architecture is **simpler while retaining every required tenant/security invariant**;
- **Dan explicitly selected the Gateway-free architecture.**

---

## 3. Security invariants — ratified, not weakened

Removing the Gateway does **not** weaken any of these. They are now properties of the **approved public edges and route-owning services** rather than of an API Gateway component:

- Authentication ≠ Routing.
- Authentication ≠ Authorization.
- Authentication ≠ DB Access.
- One Request → One Active Tenant → One Database.
- The client does **not** authoritatively choose `target_tenant_ref`.
- The client does **not** authoritatively choose `actor_ref`.
- Tenant identity comes from authenticated trusted state.
- Public request parsing and validation **fail closed**.
- Request-size bounds remain enforced.
- CORS remains **exact-origin** and bounded.
- Correlation identifiers remain bounded and non-authoritative.
- Public DTOs remain **typed and contract-controlled**.
- Required audit evidence is emitted **before successful hand-back** where the applicable policy requires it.
- Database/service containment and **service independence** remain enforced.
- The Workspace public edge remains **narrowed to the minimum membership-read capability**.
- **No generic replacement Gateway** may be introduced under another name.

---

## 4. Accepted consequence (recorded, not hidden)

**The public Startup edge is permitted, for the Controlled Local MVP, to hold and use tenant database routing/credential capability**, subject to the already-tested tenant-isolation controls.

This is the dominant architectural consequence of the removal and it is a **deliberate, accepted trade**, not an oversight. Under the Gateway topology the internet-facing process was structurally driver-free and credential-free; under D-45 the `database_router`-owned public Startup edge holds the routed-session provider in-process. The compensating controls are: authentication at the shared boundary before any business work; tenant derived only from the signed claim at a single call site; one request → one accepted tenant → one routed session; per-tenant credentials never reused across tenants; and a guard pinning the privilege posture so a regression is visible.

**The Workspace edge is narrowed to the minimum membership-read capability** — one self-scoped read method, with an object-graph capability census pinning that narrowing.

---

## 5. Amendment scope / impact

**Contracts amended (documentation/governance only — no runtime change):**

| Contract | Change |
|---|---|
| **IC-010** | **Primary retargeting.** Title → *Public Edge Ingress Contract*. §A rewritten to the approved-public-edge ingress rule + the §A.1 eight-point definition + the §A.2 closed edge set. §C's bypass prohibition **reframed, not removed**. §X endpoint dispatch → route ownership. §Q dispatch taxonomy → public route-family taxonomy (five category names unchanged; each family gains an owner and a served/edge-dark status). §H gains "the Database Router does not perform identity authentication". §I/§M/§N client, service and channel ingress retargeted. §J: the route-owning public edge is the sole emitter for its own route; the subclass **label** "gateway-edge" → "public-edge". §V: "Gateway-owned" → "route-owner-owned". §R, §K, §L, §O, §S, §U, §W, the composition cross-reference, and the R1/CLM/D-43 sections retargeted. **New §Y — Frontend Integration Contract.** |
| **IC-011** | §3's "API Gateway as sole served ingress" → **only architecture-approved public edge modules may be served**, with five explicit STOP conditions. §9/§10 reconciled. |
| **IC-009** | Boundary, layered-on IC-010 summary, §F/§F.1, §H, §J/§J.1, §M, §R V3, §Q(e) and the CLM section retargeted. **New §P.0** gives the four lost-subject clauses explicit dispositions. |
| **IC-012** | `api_gateway` removed from §2/§3/§4/§13/§18 **because the package was deleted, not because the D-44 grant widened**; §15's IC-010 cross-reference reconciled. |
| **IC-005** | Every Gateway reference retargeted to the approved public edge; the audit subclass **label** renamed; the Auth Router's own responsibilities **untouched**; authentication **not** moved into the Database Router or Control Plane. |
| **IC-002** | Class 3 / 3b emitter and subclass label retargeted; the as-built type pointer refreshed to `EdgeAuditEvent`; the frozen storage artifacts named as frozen. |
| **IC-001 / IC-007 / IC-008** | Single-line naming reconciliations. |
| **IC-003 / IC-004 / IC-006** | **No change.** IC-006 is the **AI Gateway** — a different, deferred component, untouched by D-45. |

**Governance documents amended:** the Canonical Overview (locked invariant #7 — see §6), the Action Tracker, the PRD Index, `CLAUDE.md`, this register, and the hosted rollback runbook.

**Guards updated (re-encoded, never weakened):** the IC-010 response-composition contract guard, the B5-BLK-5 R1 contract guard, the CLM Stage-A contract guard, the IC-007 governed-sharing contract guard, the IC-012 composition-root text-drift pins, the IC-011 hosted-rollback contract guard, and the B5-BLK-6 closure-evidence-matrix guard. Where a guard encoded the old architecture decision it now encodes the ratified one; **no detector was removed and no non-vacuity probe was dropped.**

---

## 6. Locked-invariant change record (Canonical Overview invariant #7)

The Canonical Overview's Part 2 locked invariant #7 read:

> **The Gateway is the boundary** — frontend → Gateway, never directly to DB/auth/router.

It is **superseded by this explicit human architecture decision from Dan** and replaced by:

> **The authenticated public edge is the boundary.**
>
> Client traffic reaches only explicitly approved route-owning public edges. Internal service APIs, routers, audit-ingest APIs, database transports, and databases are never direct client ingress.

**This is a recorded supersession, not a silent edit.** The Overview retains the superseded text alongside the replacement, with the decision, its date, and its author named, so the reopening of a locked invariant remains auditable. **D-4** ("build the API Gateway next") is likewise superseded for the Controlled Local MVP by this decision.

---

## 7. Frozen / separately governed residuals

**Not changed by this decision, by design and out of authority:**

- **DDL 012** and **DDL 013**;
- `source_service = 'api_gateway'` (the DDL 012 producer constant);
- the `control_gateway_audit` table and the Python named for it;
- the existing Gateway audit-writer **SecretRef**;
- live audit schema and credentials.

The architecture documents state explicitly:

> The active runtime Gateway component has been removed. Gateway-named audit storage artifacts remain temporarily as frozen compatibility artifacts pending a separately authorized DDL/SecretRef migration.

**Those names are not evidence that an API Gateway runtime exists.**

---

## 8. Frontend integration contract (recorded, not executed)

The frontend lives in a separate repository and **is not changed by this decision**. The required integration contract is recorded at IC-010 §Y:

- there is **no single generic Gateway endpoint** — the frontend must not hold one backend base URL for business traffic;
- **Startup routes target the public Startup edge**;
- **Workspace/membership routes target the public Workspace edge**;
- both are **separate origins**, each needing its own exact-origin CORS allowlist, reverse-proxy upstream, and TLS termination — configuring only one fails **silently**;
- the OIDC redirect origin must still agree byte-for-byte with the IdP client registration.

**No frontend code change is authorized here.** B5-BLK-5 remains OPEN.

---

## 9. Deferred / separately governed

- **DDL 012/013 audit naming migration** (widening the `source_service` CHECK so the last frozen residual can retire);
- **Gateway audit SecretRef renaming/migration**;
- **a live two-tenant witness for the Gateway-free topology** — five live-PG harnesses were deleted and two now refuse; there is currently **no live tenant-data-plane witness and no integrated Smoke C** for this topology, and **B5-BLK-4 has lost its harness**;
- **re-running the retargeted DDL-012 live proof** (`test_pg_gateway_audit_durable.py` is UNVERIFIED against the new emitter);
- **the frontend cutover**;
- **any future production architecture decision.**

---

## 10. Non-overclaim

**This decision is a Controlled Local MVP architecture decision and is NOT production approval.**

D-45 **closes no blocker** and does not change the blocker census. **B5-BLK-5 remains OPEN. B5-BLK-8 remains OPEN. Gate B remains NOT GRANTED. Production remains NOT READY / DO-NOT-ACTIVATE.** The Physical Multi-Database MVP is mandatory and unchanged. No hosted or staging environment, database, DDL, SecretRef, credential, Keycloak configuration, or standing runtime is created or changed by this entry. **No push, PR, or merge is authorized; only Dan may explicitly authorize the specific future PR merge.**
