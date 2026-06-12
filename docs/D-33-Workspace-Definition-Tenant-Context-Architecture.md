# D-33 — Workspace Definition & Tenant Context Architecture

| | |
|---|---|
| **ADR ID** | D-33 (Architecture Decision Register series; next after D-32) |
| **Status** | **Proposed** — for separate review and approval per PRD-WA-01 §3 |
| **Authorized by** | PRD-WA-01 (as amended by PRD-WA-01-R1, Amendments A1–A5) |
| **Date** | 2026-06-11 |
| **Evidence base** | PRD 1A-R2 Verification Report; contracts IC-002/IC-005 (Final); backend `main` @ `0c2133a` |
| **Draft review** | Adversarially reviewed pre-delivery (independent conformance + completeness agents, 2026-06-12); 1 blocking + 10 minor findings incorporated in this revision |

---

## 1. Background

The product architecture (PRD 1A series) introduced the term **Workspace** for the context a user operates in ("Control Workspace → Control DB; ACME Workspace → ACME DB"). The term appears **nowhere** in the governed corpus: zero occurrences in contracts IC-001..IC-007, ADRs D-01..D-32, docs, or backend code (verified by repo-wide search, PRD 1A-R2 Question E). Meanwhile the backend already implements a complete, verified tenant-context mechanism without it:

- The **signed JWT tenant claim is the authoritative active-tenant identifier** (IC-005:83, D-06); any subdomain/header carrier that disagrees with it MUST be rejected (IC-005:84) — implemented at `auth_router/tenant_context.py:33` (`carrier_mismatch`, HTTP 403) and exercised by two complementary tests: `tests/auth_router/test_tenant_context.py::test_carrier_match_required` (valid claims + swapped carrier → 403 `carrier_mismatch` at the resolver) and `tests/auth_router/test_audit.py::test_carrier_mismatch_audited` (a *genuinely valid signed token* + swapped carrier through the full `Authenticator.authenticate` pipeline, asserting the CarrierMismatch audit event).
- **Tenant switch = new scoped token, audited** (IC-005:88, :55) — stateless, no session store.
- The Database Router consumes **only** the authenticated context: *"the single active tenant is taken from the signed claim resolved by Phase 3 — never re-derived"* (`database_router/router.py:10`); with no tenant claim, only the CONTROL role reaches control-plane scope, all others are denied `no_active_tenant` (`router.py:99-108`, D-32).

Left undefined, "Workspace" invites exactly the drift PRD 1A feared: a client-selected value (header, cookie, query string) becoming a routing input — which would re-create the *valid-token + swapped-carrier* cross-tenant attack that IC-005 §D-06 exists to block.

## 2. Problem Statement

Define what a **Workspace** is — and is not — in SnackPortal2, such that (a) the product language ("switch workspace", "Control workspace") gains a governed meaning, (b) no frontend or gateway implementation can ever treat a client-controlled workspace value as a routing input, and (c) the five frozen invariants are preserved unchanged.

## 3. Decision Options

| Option | Model | Assessment |
|---|---|---|
| **O1 — UI concept** (recommended) | Workspace = the user-facing representation of an already-authenticated database context: the signed active-tenant claim, or control-plane scope for CONTROL principals. | The only model compatible with IC-005/D-06 as written. Requires zero backend redesign — the mechanism exists and is test-verified. |
| **O2 — Routing concept** | Workspace is an input the Database Router consumes (header/cookie/query param/registry field). | **Rejected.** Recreates the swapped-carrier attack with a new name; contradicts IC-005:83-88 (signed claim is the sole source of truth) and the router's contract ("never re-derived"). Would weaken frozen invariants 4 and 5. |
| **O3 — Token concept** | Workspace becomes a second JWT claim parallel to the tenant claim. | **Rejected.** Two authoritative fields that can disagree = ambiguity = attack surface, and the tenant claim already *is* the token-level representation of the workspace. (A cosmetic display name MUST NOT be carried as a claim; the UI derives display names from the control-plane membership read.) |
| **O4 — Database concept** | Workspace maps to its own database or schema, distinct from tenant databases. | **Rejected.** Duplicates the tenant-database concept. Any workspace ≠ tenant-DB mapping breaks "one request → one active tenant → one database" (IC-002:98). Intra-tenant sub-contexts, if ever wanted, are ordinary application data *inside* the single tenant DB — not routing concepts (see Future Work). |

## 4. Recommended Decision

**Adopt O1.** Normatively:

1. **Definition.** `Workspace = the UI representation of a signed tenant context.` One workspace corresponds to exactly one routable context:
   - **Tenant Workspace** ↔ the signed active-tenant claim ↔ exactly one physically separate tenant database.
   - **Control Workspace** ↔ a CONTROL-role principal with **no** tenant claim ↔ control-plane scope only. The Control Workspace can never reach a tenant database (`router.py:99-108`: tenantless non-CONTROL → `forbidden("no_active_tenant")`; CONTROL → `RoutingTarget.CONTROL`). It is the UI surface for **platform administration** (including CONTROL-scoped directory administration). Global Directory **read** access is *not* bound to the Control Workspace: it remains an authenticated, audited control-plane read (IC-005/D-31) available to authorized principals from their own workspace context per role — tenant-scoped principals (e.g. STARTUP_USER, INVESTOR_USER) read the Global Discovery Platform from within their Tenant Workspace, which is what feeds the IC-003 discovery → import flow. Which portal surfaces host directory browsing is portal-boundary design deferred to **D-37**.
2. **Workspace is NOT:** a routing input; an HTTP header, cookie, or query-string value with authority; a tenant filter; a JWT claim of its own; a database or schema; or server-side session state.
3. **Workspace switching = token issuance.** Selecting a different workspace triggers the IC-005 tenant-switch flow: obtain a **new token scoped to the new active tenant** (or a tenantless CONTROL token for the Control Workspace). The switch is an audited operation. The UI derives the current workspace *from* the token — never the reverse.
4. **Workspace list = control-plane membership read.** The workspaces offered to a principal come from authenticated control-plane membership reads. The read API currently exposes only point reads (`is_member`, `get_role`, tenant state); a memberships-for-principal **enumeration** already exists internally (`control_plane/membership.py`, `MembershipRegistry.tenants_for`) but is not routed through the read dispatcher — the workspace selector therefore requires a small **additive** read-API endpoint at implementation time. Multi-tenant principals (1:N membership, D-03/D-04) switch **sequentially**; per D-32 even MASTER_AGENT obeys one-active-tenant-per-request. There is **no merged "all workspaces" view**: cross-tenant aggregation is prohibited as a routing or single-request operation (D-30; IC-002 isolation guarantees); the only contract-lawful mechanism is explicit, audited, **per-tenant** control-plane reads (IC-005:97; IC-002:102), and any aggregated product surface is out of MVP per D-32 and routes to IC-007.
5. **Carrier channels.** A subdomain or header MAY continue to exist for addressing/UX (D-06). Recognized carriers are: the subdomain and the explicitly named header(s) that the IC-005 amendment MUST enumerate — all other headers are unrecognized. Any inbound workspace **cookie** or **query-string** parameter MUST be stripped/ignored at the API Gateway and MUST NOT be read by any backend component for **any** purpose, including token issuance (§6 states the identical ruling). Every recognized carrier value MUST match the signed claim or the request is rejected (403 `carrier_mismatch`) — already contract law, already implemented, already tested. For a **tenantless CONTROL context** (Control Workspace), a recognized carrier asserting a tenant is **ignored** — routing consumes only the claim; this ratifies current implementation behavior (the resolver returns the tenantless context before the carrier check). Optional hardening (anomaly audit or rejection) is Future Work.
6. **Gateway obligation (forward-binding).** When the API Gateway is implemented (currently a Phase-1 scaffold; the 1A-R2 Critical-risk item), it MUST construct the router's `RequestContext` exclusively from the Authenticator's output (`AuthContext`), MUST pass any recognized carrier into the carrier-match check, and MUST NOT read any workspace header/cookie/query-string as a tenant selector (inbound workspace cookies/query-strings are stripped per §4.5). The **amended IC-005** (§7) is the governing reference for that wiring; this ADR records the decision.
7. **Frontend obligation (forward-binding).** The frontend (Lovable) treats workspace purely as presentation: the workspace selector calls the token-issuance flow; no client-side query may carry a tenant or workspace identifier as a data-access parameter; all data access goes through the API Gateway.

## 5. Consequences

- The product term "Workspace" becomes governed vocabulary with zero behavioral distance from the verified backend — **no change to the tenant-context or routing mechanism is required by this decision** (the only implementation-time addition is the small additive memberships-for-principal read endpoint, §4.4).
- The Lovable prototype's existing "workspace switching" (whatever it does today — unverifiable, not under source control) must be re-mapped onto token issuance during the Frontend Data-Access Refactor; any current filter- or header-based switching is non-conformant by definition.
- Per-workspace UX state (layout, preferences) is application data owned by the workspace's own database context (tenant DB for tenant workspaces; control DB for the Control Workspace) — never shared across workspaces.
- Cross-workspace product features (aggregated dashboards, cross-tenant introductions) are out of MVP (D-32) and route to IC-007; the only contract-lawful aggregation mechanism is explicit, audited, per-tenant control-plane reads — never a routing or single-request operation.

## 6. Security Considerations

- **Workspace Header / Cookie / Query String as routing inputs: assessed and PROHIBITED** (the PRD-WA-01 W01 security requirement). Header-as-carrier is permitted only under mandatory match-or-reject (D-06). Cookies and query-strings are prohibited outright — stripped/ignored at the gateway and never read by any backend component for any purpose, including token issuance (§4.5): a cookie attaches ambient, client-controlled authority to every request (CSRF-class risk), exactly the client-selected carrier class W01 required assessing; query strings leak into logs and referrers.
- The defended attack — valid token + swapped carrier — is verified blocked at unit level today by the two complementary tests cited in §1 (resolver-level 403 + full-pipeline audit). The residual risk identified by PRD 1A-R2 stands: enforcement is library-internal until the API Gateway wires the edge; connecting any frontend before then is a Critical-class risk. This ADR's §4.6 binds that future wiring.
- No new secrets, tokens, or stores are introduced; D-14 is untouched.

## 7. Contract Impact

| Contract | Impact | Nature |
|---|---|---|
| **IC-005** | Amend (small) | Add a *Workspace Terminology* clause: workspace = UI representation of the signed tenant context; recognized carriers (subdomain, named header) under existing match-or-reject; cookie/query-string carriage prohibited; workspace switch = the existing tenant-switch (new scoped token, audited). No normative change to validation, JWKS, roles, or denial semantics. |
| **IC-002** | Amend (editorial) | Cross-reference: "active tenant context (D-04)" gains the alias "Tenant Workspace"; Control Workspace defined as control-plane scope. The four core invariants are untouched verbatim. |
| IC-001, IC-003, IC-004 | None | — |
| IC-006, IC-007 | None (boundary noted) | Cross-workspace features remain IC-007-gated; AI surfaces IC-006-gated. |

The IC-005 clause MUST enumerate the exact recognized carrier header name(s); all other headers are unrecognized-and-ignored. Both amendments follow only after this ADR is Approved and entered in `docs/Architecture-Decision-Register.md` (register entry → contract amendment → code, per PROJECT-HANDOVER-MASTER.md §21 *Change Governance Rules* and PRD-WA-01-R1 Amendment A5).

## 8. Implementation Impact

**None now** (and none authorized — PRD-WA-01 prohibits implementation). When later phases land: the API Gateway implements §4.6; the frontend refactor implements §4.7; no Database Router, Auth Router, Control Plane, Import, or Lineage change is required — PRD 1A-R2 verified the mechanism complete and conformant at `0c2133a`.

## 9. Frozen Invariant Impact (required by PRD-WA-01-R1 §8)

| Invariant | Impact |
|---|---|
| Global Record ≠ Tenant Record | **None.** Workspace is presentation; record residency untouched. |
| Import ≠ Synchronization | **None.** |
| Control DB ≠ Tenant DB | **None — reinforced:** the Control Workspace is structurally incapable of reaching a tenant DB. |
| Authentication ≠ Routing | **None — reinforced:** workspace selection acts only at authentication (token issuance); routing continues to consume only the signed claim. |
| One Request → One Active Tenant → One Database | **None — reinforced:** one workspace ↔ one context; no merged views; sequential switching only. |

No invariant is weakened. Options O2/O3/O4 were rejected precisely because each would weaken at least one.

## 10. Verification Criteria (required by PRD-WA-01-R1 §8)

**Already verifiable today (green at `0c2133a`):**
1. Valid claims + swapped carrier → 403 `carrier_mismatch` at the resolver (`test_tenant_context.py::test_carrier_match_required`); genuinely valid signed token + swapped carrier through the full authenticate pipeline → CarrierMismatch audit event (`test_audit.py::test_carrier_mismatch_audited`).
2. Tenantless non-CONTROL context → `forbidden("no_active_tenant")`; CONTROL → control-plane scope only (existing router tests).
3. Repo-wide: no code path reads a workspace header/cookie/query-string **as a tenant selector or routing input**; the sole permitted read is passing a recognized carrier into the IC-005 carrier-match check, which must reject on mismatch (re-checkable in CI as an architecture test, consistent with criteria 4 and 6).

**Required when the API Gateway is implemented (future En/Vn):**
4. Integration test: authenticated request with mismatched subdomain/header is rejected end-to-end through the gateway.
5. Integration test: workspace switch issues a new scoped token and emits the audit event; the old context cannot be reused to reach the new workspace's data.
6. Architecture test: gateway constructs `RequestContext` only from `AuthContext`; no inbound tenant/workspace parameter reaches the router.

**Acceptance:** D-33 Approved and entered in `docs/Architecture-Decision-Register.md`; IC-005/IC-002 amendments merged; criteria 1–3 green in CI; criteria 4–6 adopted as acceptance criteria of the API Gateway execution PRD.

## 11. Future Work

- **Intra-tenant sub-workspaces** (projects/rooms inside one tenant): explicitly out of scope; if ever wanted, they are tenant-internal application data inside the single tenant DB with no routing or contract impact.
- **Workspace display metadata** (names, icons): control-plane membership read extension — product-level, no architecture impact.
- **Cross-workspace collaboration:** IC-007, when designed.
- **Optional jti denylist for instant workspace revocation:** already an IC-005 implementation note; unchanged by this ADR.
- **Carrier-on-CONTROL hardening:** optional anomaly audit or rejection when a recognized tenant carrier accompanies a tenantless CONTROL token (ratified behavior today: ignored, §4.5).
- **Memberships-for-principal read endpoint:** the small additive control-plane read-API extension needed by the workspace selector (§4.4) — to be carried by the API Gateway / frontend-integration execution PRD.
