# B5-BLK-6 Closure Evidence Matrix (EFFECTED CLOSURE EVIDENCE)

> **Slice:** B5-BLK-6C-D — evidence-only runtime-binding closure.
> **Nature:** governance evidence assembly + text-drift guard. This document is documentation only:
> it changes no runtime behavior, no production source, no DDL, no database, and no blocker row.

## Governance status

```text
Governance status: EFFECTED CLOSURE EVIDENCE
B5-BLK-6 — CLOSED (B5-BLK-6 governance-effect closure, 2026-07-20, Dan-authorized)
Current blocker census is now 7 of 9 OPEN (B5-BLK-4 and B5-BLK-6 are the only CLOSED blockers)
Production remains NOT READY / DO-NOT-ACTIVATE
This document records the effected B5-BLK-6 runtime-binding closure
```

This matrix **assembles and cites** the already-accepted, already-merged 6A → 6B → 6C-A → 6C-B → 6C-C
runtime-binding evidence for B5-BLK-6 and **effects** — as this separately-authorized governance-effect
closure slice — the B5-BLK-6 reconciliation. It flips the live B5-BLK-6 register status to CLOSED and
recounts the live census to 7 of 9 OPEN. The single reconciliation item this slice effects is **R6-6**
(evidence assembly / reconciliation record, now EFFECTED); R6-1 through R6-4 are proven at the composed
Gateway core and served edge, and R6-5 is out of scope by the IC-007 contract.

## Accepted baseline identity (independently re-derived)

```text
Accepted main                : 4226d7f6506dfa01f40044620bb18cc33a2647d5
  parent-1                    : f59936b5d0da95c7a504dd51ba78dac97c850117  (PR #92 — Gateway Audit V1a)
  parent-2 / IC-007 head      : bfcdc1b18d4bf80d5b2214c338650dcc049ed9c0  (PR #93 — IC-007 contract)
PR #92 (Gateway Audit V1a)    : MERGED at f59936b5d0da95c7a504dd51ba78dac97c850117  (human merge)
PR #93 (IC-007 contract)      : MERGED at 4226d7f6506dfa01f40044620bb18cc33a2647d5  (human merge)
```

The Gateway Audit V1a and IC-007 arcs are separately governed and **closed as their own arcs**; neither
closes B5-BLK-6. The Gateway Audit V1a slice persists one gateway-edge success-access event through the
Control-Plane audit boundary; it is the **durable-audit** track and is distinct from the composed-core
in-memory audit binding cited in R6-3 below. The IC-007 arc moved the contract to **Draft / Proposed**;
it grants no positive sharing capability (see R6-5).

---

## Evidence rows R6-1 … R6-6

Each row records: the requirement, the accepted PR(s), the accepted merge / source SHA(s), the exact
source / proof path(s), the exact statement that may safely be made, the exact overclaim that must be
prohibited, the binding qualifier, and the status.

### R6-1 — IC-009 portal DTO composition is runtime-bound in the composed Gateway core

- **Accepted PRs:** PR #86 (6A) · PR #87 (6B)
- **Accepted merge / source SHAs:** `585ec8b` (merge #86) · `9eb892b` (merge #87) · `5b7da75`
  ("Bind IC-009 foundation-tier portal operations at the Gateway") · `1fb1a7c`
  ("Strengthen B5-BLK-6B portal guard coverage")
- **Source / proof paths:** `backend/api_gateway/gateway.py` · `backend/api_gateway/portal.py` ·
  `contracts/IC-010-API-Gateway-Contract.md`
- **SAFE statement:** IC-009 **foundation-tier** portal DTO composition (MembershipsForPrincipal, Global
  Directory Read, Import-Initiation envelope) is runtime-bound in the **composed Gateway core**.
- **PROHIBITED overclaim:** must NOT claim IC-009 is fully implemented; must NOT claim business-domain-tier
  tenant Startup/Investor/Deal records are bound; must NOT claim the served northbound edge is bound; must
  NOT claim any Lovable / portal frontend surface.
- **Qualifier:** foundation-tier / composed Gateway core.
- **Status:** PROVEN (composition, foundation-tier).

### R6-2 — Portal composition is proven against a real disposable Control DB

- **Accepted PR:** PR #90 (6C-C)
- **Accepted merge / source SHAs:** `663dc92` (merge #90) · `0b6d63e`
  ("Prove real Control-DB portal composition (B5-BLK-6C-C)")
- **Source / proof paths:**
  `backend/tests/control_plane/requires_pg/b5_blk6_portal_binding_live_proof.py` ·
  `infrastructure/runbooks/b5_blk6_portal_binding_live_proof.md`
- **SAFE statement:** the real `PostgresControlStore` → Control-Plane read edge → composed Gateway →
  `WorkspaceMembershipDTO` path is proven against a **fresh disposable PostgreSQL** Control DB, with
  zero retained artifact (teardown asserts the disposable database datname count is zero).
- **PROHIBITED overclaim:** must NOT claim production database identity, standing/production topology, or
  cross-cluster distinctness; the disposable-DB proof is not production readiness.
- **Qualifier:** disposable PostgreSQL proof, not production identity.
- **Status:** PROVEN (real PostgreSQL, disposable).

### R6-3 — `workspace_memberships_read` success audit is runtime-bound exactly once (empty success included); directory reads stay silent

- **Accepted PRs:** PR #88 (6C-A) · PR #89 (6C-B)
- **Accepted merge / source SHAs:** `15b69e4` (merge #88) · `6c7aacc` (merge #89) · `aa7e9f1`
  ("Reconcile B5-BLK-6 audit obligations (B5-BLK-6C-A)") · `062e359`
  ("Bind workspace_memberships_read success audit at the Gateway (B5-BLK-6C-B)")
- **Source / proof paths:** `backend/api_gateway/gateway.py` (the gated success-emit seam)
- **SAFE statement:** exactly one references-only `workspace_memberships_read` success event is emitted per
  successful self-scoped enumeration (the empty-success case included); directory reads remain audit-silent
  (Reserved) — observed with an **in-memory recorder**.
- **PROHIBITED overclaim:** must NOT claim durable or persisted operational audit, operator audit retrieval,
  or audit-sink availability; the durable audit sink is the separate Gateway Audit V1a/V1b arc.
- **Qualifier:** in-memory recorder; durable audit is a separate arc.
- **Status:** PROVEN (in-memory recorder).

### R6-4 — IC-007 cross-tenant isolation is runtime-bound (carrier-straddle denial; zero unauthorized dispatch)

- **Accepted PR:** PR #90 (6C-C)
- **Accepted merge / source SHAs:** `663dc92` (merge #90) · `0b6d63e`
  ("Prove real Control-DB portal composition (B5-BLK-6C-C)")
- **Source / proof paths:** `backend/api_gateway/gateway.py` (isolation enforcement at the composed core;
  6C-C `ic007-negatives` scenario set)
- **SAFE statement:** IC-007 cross-tenant **isolation enforcement** is runtime-bound at the composed core —
  a dual-carrier straddle resolves to `403 isolation_anomaly` with **zero unauthorized dispatch**, and the
  serialized directory DTO carries no tenant token.
- **PROHIBITED overclaim:** must NOT claim any positive cross-tenant sharing, introductions, or aggregation
  capability; must NOT claim served-edge isolation.
- **Qualifier:** composition-level isolation.
- **Status:** PROVEN (composition-level isolation).

### R6-5 — Positive IC-007 cross-tenant capability remains deferred and is not claimed

- **Accepted PR:** PR #93 (IC-007 contract arc) — contract lane only
- **Source / proof path:** `contracts/IC-007-Deal-Collaboration-Cross-Tenant-Sharing-Contract.md`
- **SAFE statement:** the IC-007 contract status is **Draft / Proposed**, while positive IC-007 runtime
  capability remains **Deferred** and **OUT OF SCOPE**. No positive IC-007 cross-tenant sharing capability
  exists; none is built, implemented, or claimed by this matrix.
- **PROHIBITED overclaim:** must NOT state that any positive IC-007 capability exists or has been made
  Final; must NOT read the Draft / Proposed contract as a runtime capability.
- **Qualifier:** Deferred; OUT OF SCOPE by contract.
- **Status:** OUT OF SCOPE BY CONTRACT (IC-007 = Draft / Proposed).

### R6-6 — Register, contract, ADR/index and evidence text reconciliation

- **Accepted PR:** this governance-effect closure slice (the effected 6C-D residual)
- **Source / proof path:** `docs/runtime/b5_blk6_closure_evidence_matrix.md`
- **SAFE statement:** this matrix **assembles** R6-1 … R6-5 against the landed proofs and **effects** the
  B5-BLK-6 reconciliation as the separately-authorized governance-effect closure slice: the live B5-BLK-6
  register status is CLOSED, the live census is recounted to 7 of 9 OPEN, and the DBR-AR-2 traceability row
  and coupled census guards are reconciled in lockstep.
- **PROHIBITED overclaim:** must NOT lift DO-NOT-ACTIVATE; must NOT claim B5-BLK-5 closure; must NOT claim
  any positive IC-007 capability or production readiness.
- **Qualifier:** effects the reconciliation; the runtime binding is already merged (adds no runtime code).
- **Status:** EFFECTED — the B5-BLK-6 runtime-binding reconciliation is effected by this slice.

---

## Four live locations (reconciled and effected by the B5-BLK-6 governance-effect closure)

The following four live statements previously asserted a "not runtime-bound" / open state, superseded by
the landed R6-1 … R6-4 runtime binding. **This governance-effect closure slice reconciles all four**,
flipping the live B5-BLK-6 register status to CLOSED and recounting the live census to 7 of 9 OPEN.

1. **`docs/runtime/b5_activation_blockers.md` — B5-BLK-6 row** (the blocker-register authority):
   now "IC-009 portal contracts and IC-007 cross-tenant contracts runtime-bound … CLOSED".
   - RECONCILED BY THE B5-BLK-6 GOVERNANCE-EFFECT CLOSURE
   - EFFECTED BY THIS CLOSURE SLICE
   - CURRENT LIVE STATUS NOW EFFECTED

2. **`docs/runtime/b5_activation_blockers.md` — B5-BLK-6 taxonomy** row:
   now "CLOSED (governance-effect closure, 2026-07-20, Dan-authorized) … IC-009 portal / IC-007 cross-tenant
   contracts runtime-bound".
   - RECONCILED BY THE B5-BLK-6 GOVERNANCE-EFFECT CLOSURE
   - EFFECTED BY THIS CLOSURE SLICE
   - CURRENT LIVE STATUS NOW EFFECTED

3. **`docs/runtime/b5_activation_blockers.md` — current standing decision** (census):
   now "Current standing decision: NOT READY (7 / 9 blockers OPEN; B5-BLK-4 CLOSED …; B5-BLK-6 CLOSED …)."
   The live census is recounted to 7 / 9 OPEN with B5-BLK-4 and B5-BLK-6 the only CLOSED blockers.
   - RECONCILED BY THE B5-BLK-6 GOVERNANCE-EFFECT CLOSURE
   - EFFECTED BY THIS CLOSURE SLICE
   - CURRENT LIVE STATUS NOW EFFECTED

4. **`docs/runtime/dbr_ar_2_production_activation_evidence.md` — B5-BLK-6 traceability row**:
   now "B5-BLK-6 | IC-009/IC-007 contracts runtime-bound | runtime-bound at the composed Gateway core +
   served edge (R6-1 to R6-4) | CLOSED …".
   - RECONCILED BY THE B5-BLK-6 GOVERNANCE-EFFECT CLOSURE
   - EFFECTED BY THIS CLOSURE SLICE
   - CURRENT LIVE STATUS NOW EFFECTED

---

## Separate-track declarations

```text
Gateway Edge is a separate served-ingress arc
Gateway Audit V1a/V1b is a separate durable-audit arc
W1/W1a is the separate persistent-write arc
Lovable cutover is B5-BLK-5 and remains separate
positive IC-007 runtime sharing remains deferred
local/disposable proof is not production readiness
```

- The **served northbound Gateway Edge** is a separate operational-ingress arc; the evidence in this matrix
  is proven at the **composed Gateway core**, not at the served edge.
- **Gateway Audit V1a/V1b** is a separate **durable-audit** arc; R6-3 here is an **in-memory recorder**
  binding, not a durable/persisted sink.
- **W1 / W1a** is the separate **persistent-write** arc; no authenticated persistent tenant write,
  idempotency, write-lineage, write-audit, or rollback is in scope for or claimed by 6C-D.
- **Lovable cutover** is **B5-BLK-5** and remains a separate track.
- **Positive IC-007** runtime sharing remains **Deferred** and out of scope (R6-5).
- **Local / disposable** proof is not production readiness; it does not establish production identity or
  standing topology.

---

## Effected governance decision (framing)

```text
EFFECTED GOVERNANCE DECISION — EFFECTED BY THIS DOCUMENT
```

GPT and Dan authorized this governance-effect closure slice. It effects the B5-BLK-6 reconciliation the
assembled R6-1 … R6-5 evidence supports: it flips the live B5-BLK-6 register status to CLOSED, recounts the
live census to 7 of 9 OPEN, reconciles the DBR-AR-2 activation-evidence traceability row, and updates the
coupled census-guard family in lockstep. It adds no runtime code (R6-1 … R6-4 binding is already merged),
changes no contract, no DDL, and no production state. **B5-BLK-5 remains OPEN and production remains NOT
READY / DO-NOT-ACTIVATE.**

---

## Non-claims

This document does **NOT** claim any of the following:

- It does NOT claim served northbound ingress is complete.
- It does NOT claim durable audit persistence is complete.
- It does NOT claim the persistent write path is complete.
- It does NOT claim the Lovable cutover is complete or that B5-BLK-5 is reconciled.
- It does NOT claim that any positive IC-007 cross-tenant capability exists; positive IC-007 sharing remains Draft / Proposed, unimplemented, and unauthorized.
- It does NOT claim production readiness and does NOT lift DO-NOT-ACTIVATE.
- It does NOT close B5-BLK-5 and does NOT touch any runtime source, DDL, contract, ADR, or tracker.

```text
B5-BLK-5 remains OPEN
B5-BLK-6 — CLOSED (governance-effect closure, 2026-07-20, Dan-authorized)
Live census is now 7 of 9 OPEN (B5-BLK-4 and B5-BLK-6 CLOSED)
Production remains NOT READY / DO-NOT-ACTIVATE
```

---

## Guard note

This matrix is pinned by the architecture text-drift guard
`backend/tests/architecture/test_b5_blk6_closure_evidence_matrix_boundaries.py`. That guard positively
requires the evidence references, the binding qualifiers, the four live-location labels, and the
effected-closure / 7-of-9-census framing, and it rejects the reverted proposal-only, current-open-B5-BLK-6,
and pre-closure-census framing as well as B5-BLK-5-closure, positive-IC-007-capability, and production-ready
wording. The guard is a static text scan; it binds no runtime, opens no socket, and touches no database.
