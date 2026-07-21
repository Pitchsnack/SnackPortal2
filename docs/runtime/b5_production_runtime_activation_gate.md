# PRD 06 B-5 — Production Runtime Activation Gate (specification)

**Phase:** PRD 06 B-5 — controlled non-production. **Baseline (re-grounded 2026-07-12):** `origin/main @ fff215b5bd004760ea0d81915c3d93ca128673ed`. **Decision baseline (B5-E, 2026-07-12):** `origin/main @ 84882c77cfe409bab0af454b4411cf65795bcbfd`.
**Gate status: NOT READY (default).** **B-5 builds this gate as documentation + a reference template + a blocker
register + an evidence template + a readiness matrix + additive guard tests. B-5 does NOT activate runtime, does NOT
modify backend source, does NOT modify `backend/control_plane/main.py`, and does NOT wire a runtime switch.**

---

## 0. Re-grounding note — current baseline, B5 arc, IC-002 lifecycle (2026-07-12)

**Current verified baseline:** `HEAD == main == origin/main == fff215b5bd004760ea0d81915c3d93ca128673ed`.
This note re-grounds the gate specification below (originally authored at an earlier baseline). The gate's
fail-closed **NOT READY** production posture is **unchanged** — the re-grounding records the B5
runtime-readiness work that has since landed on `main`, distinguishes the evidence it supplies from the
evidence still owed, and keeps every activation blocker OPEN.

**B5 runtime-readiness arc (all merged to `main`; fully closed / arc-closed):**

| Slice | PR | Status |
|---|---|---|
| B5-1 — Control-Plane read-edge serve seam (`build_read_server_from_env`) | #69 | fully closed |
| B5-2 — serve-lifecycle entrypoints (`serve_authenticate_api` / `serve_dispatch_api`) | #70 | fully closed |
| B5-3 — live-wire denial semantics (404 → None; `/federation` route) | #71 | fully closed |
| B5-4 — standing local physical topology (Control DB + two Ready tenants at database granularity) | #72 | fully closed; standing topology retained |
| B5-5 — Smoke C specification (SMOKE-C-SPEC-01) + RS256 mint fixture | #73 | fully closed |
| B5-4A — standing authentication fixture (memberships + non-Ready `b5_standing_dormant`) | #74 | fully closed; standing auth fixture retained |
| Smoke C V2 — integrated live proof, **including Fix R3** target-branch cleanup | #75 | fully arc-closed |

**What Smoke C V2 (including Fix R3) proves — at database granularity, over the standing fixture:**

```text
fresh RS256 token
  -> API Gateway
  -> Auth Router
  -> Control Plane read edge
  -> Database Router
  -> exactly one physical tenant database
```

for **both** standing tenant databases (`sp2_tenant_b5_standing_alpha`, `sp2_tenant_b5_standing_beta`):
alpha routes only to alpha's database and beta only to beta's. The seven failure-mode rows also hold —
known non-Ready `b5_standing_dormant` → `tenant_not_ready`; unknown tenant → `tenant_access_denied`; wrong
tenant carrier → `carrier_mismatch`; bad signature / unknown `kid` / unknown issuer → 401; read edge stopped
→ `control_plane_unavailable` (503) — every denial performs **zero** tenant dispatch, **zero** pool
acquisition and **zero** tenant-database connection, and the complete before-state equals the after-state
exactly (**zero mutation**).

**Scope of that evidence (do not overclaim):**

```text
Smoke C V2 including Fix R3 supplies database-granularity evidence.
It does not itself close B5-BLK-4.
```

Database granularity means **distinct physical databases on one local admin cluster**. It is **NOT**
cluster-level / multi-cluster distinctness, **NOT** production deployment or supervision, and **NOT** an
MVP-completion claim. The following remain **OPEN** and separate:

- **B5-BLK-4** — **CLOSED (B5-E, 2026-07-12, Dan-authorized) — EVIDENCE-BOUND GOVERNANCE DECISION** — the
  separate Dan-authorized closure review has been performed and recorded (see the B5-E decision record below
  and `b5_activation_blockers.md`); the §5 audit-sink availability condition remains binding at activation time.
- **Physical Multi-Database MVP** — **ACCEPTED AT DATABASE GRANULARITY (B5-E, 2026-07-12, Dan-authorized)**;
  the IC-010 §O mandate remains mandatory and binding, and acceptance does not weaken it.
- **Durable routing audit (DBR-AR-2)** — see the DBR-AR-2 closure record below (Dan-authorized governance
  decision, 2026-07-16); routing/auth audit evidence in Smoke C V2 is in-memory only; durable routing-audit
  evidence exists for the disposable proof and the retained local standing environment (DBR-AR-2D), and
  production-environment durability evidence remains deployment-era scope (PAE-02/PAE-08).
- **Production deployment / supervision** — **OPEN** (deployment evidence required).
- **Lovable / API-Gateway cutover** — separate track (interim Supabase/RLS; B5-BLK-5 / B5-BLK-6).
- **AI Agent implementation** and **product billing / fees** — separate future tracks.

**B5-E closure decision record (2026-07-12).**

Decision baseline: `origin/main @ 84882c77cfe409bab0af454b4411cf65795bcbfd` (B5-E, 2026-07-12).

**Decision A (B5-E, 2026-07-12, Dan-authorized): B5-BLK-4 — CLOSED — EVIDENCE-BOUND GOVERNANCE DECISION.**
**Decision B (B5-E, 2026-07-12, Dan-authorized): Physical Multi-Database MVP — ACCEPTED AT DATABASE GRANULARITY.**

MVP acceptance at database granularity is not cluster-level proof, not production deployment, not production activation, not Lovable cutover, not billing completion, and not AI Agent completion.
The Physical Multi-Database MVP mandate (IC-010 §O) remains mandatory and binding; acceptance at database granularity does not weaken it.
Cluster-level distinctness remains deployment scope (AT-D15T1-4; held by B5-BLK-2).
DBR-AR-2 — CLOSED (Dan-authorized governance decision, 2026-07-16); this closure closes zero B5 activation blockers, the blocker census remains nine with 8 of 9 OPEN, and production remains NOT READY / DO-NOT-ACTIVATE.
DBR-AR-2 (durable routing audit) was a separate Database Router follow-on; it was not part of the B5-BLK-4 closure evidence bar (see the B5-E record) and its status was unchanged by the B5-E decision.
Production runtime activation remains NOT READY / DO-NOT-ACTIVATE — 7 of 9 activation blockers remain OPEN; the B5-E closure of B5-BLK-4 changes no other blocker and does not make the gate ready.
The gate §5 activation condition "provisioning audit sink available (B-6) — or an explicit, approved waiver" remains binding at activation time and is not waived by the B5-E closure.
Next step: the next Dan-authorized governed slice; every remaining activation blocker is deployment-scope (B5-BLK-2/3/7/8/9) or product/integration-track (B5-BLK-5/6), and the DBR-AR-2 durable-routing-audit follow-on is governed by its closure record (Dan-authorized governance decision, 2026-07-16) — no further DBR-AR-2 slice is authorized.
The 2026-07-12 re-grounding itself neither performs nor bypasses this decision; the decision is the separate B5-E record above.

**IC-002 tenant lifecycle — eight authoritative states** (copied from
`contracts/IC-002-Tenant-Startup-Contract.md`; the `Quarantined` state was added 2026-07-06 under PRD
07D-2b.2-A, so the lifecycle now enumerates **eight** authoritative states):

```text
Registered · Provisioning · Verifying · Ready · Suspended · Failed · Quarantined · Decommissioned
```

Only `Ready` is routable. Key transitions: `Registered → Provisioning → Verifying → Ready`;
`Verifying → Failed`; `Verifying → Quarantined` (automatic, on isolation-class anomaly);
`Failed → Verifying` (audited RecoverTenant); `Provisioning | Failed → Quarantined`;
`Ready → Suspended` and `Suspended → Verifying → Ready`;
`Registered | Provisioning | Suspended | Failed | Quarantined → Decommissioned`. **`Quarantined` has
exactly one egress — `Quarantined → Decommissioned` — and never returns toward `Verifying` / `Ready`; the
direct `Ready → Decommissioned` transition is removed (a `Ready` tenant is `Suspended` first).**

---

## 1. Purpose & owner

The Production Runtime Activation Gate is the **fail-closed decision point** that must be satisfied before SnackPortal2
may activate production-like runtime database routing (i.e., before the durable/real adapters are constructed at
runtime). Its purpose is to make it **impossible to accidentally treat SnackPortal2 as production-runtime-ready before
evidence exists**.

- **Owner:** the **Control Plane** (the lifecycle / readiness authority — IC-002). The gate consumes readiness signals;
  it never bypasses the Control Plane, the Database Router, or the API Gateway.
- **Default posture:** **NOT READY** / disabled. Activation is allowed only when every readiness condition is proven and
  every blocker is closed, under explicit human approval, in a non-production environment first.

---

## 2. The current live deferral this gate sits above (do not flip in B-5)

```
backend/control_plane/main.py keeps runtime wiring deferred (construction performs no I/O):
  SP2_CP_PROVISIONING_ADAPTER  default "in_memory"; any other value → raise NotImplementedError   (main.py:80-82)
  SP2_CP_DISTINCTNESS_LEDGER   default "in_memory"; any other value → raise NotImplementedError   (main.py:105-107)
```

"Runtime activation" = changing `main.py` so the durable/real adapters are constructed at runtime. **B-5 does not do
that.** The current `NotImplementedError` deferral is the **strongest existing fail-closed** — a future runtime gate
must be at least as strict (never silently activate). The deferral is pinned by the B-5 regression lock
(`backend/tests/control_plane/test_b5_runtime_deferral_guard.py`) and already covered by B-2/onboarding behavior tests
(see the readiness matrix).

---

## 3. Gate inputs

```
activation switch        RUNTIME_ACTIVATION_ENABLED (forward contract; default false; not wired in B-5)
database references      CONTROL_DB_REF, TENANT_DB_<TENANT>_REF (D-14 secret-store references; never values)
auth references          JWT_ISSUER_REF, OIDC_PROVIDER_REF (IC-005)
audit reference          AUDIT_SINK_REF (provisioning audit sink — B-6; a blocker until built)
rollback reference       ROLLBACK_PLAN_REF
control-plane signals    tenant lifecycle/readiness state (IC-002 8 states), distinctness evidence (IC-010 §P)
target environment       must be non-production for any B-5-era exercise
```

## 4. Gate outputs

```
decision   ACTIVATE / DO-NOT-ACTIVATE (default DO-NOT-ACTIVATE)
reason     the exact blocking condition(s) when DO-NOT-ACTIVATE
evidence   a references-only evidence record (see b5_activation_evidence_template.md)
```

## 5. Activation readiness conditions (ALL required; reference existing machinery — not reinvented)

A request to activate is READY only if **all** of the following are proven (see `b5_runtime_readiness_matrix.md`):

```
switch present and explicitly enabled (RUNTIME_ACTIVATION_ENABLED true) — never defaulted
Control DB reachable + identity proven; Tenant DB reachable + identity proven
each Tenant DB physically distinct from the Control DB and from every other Tenant DB (IC-010 §O/§P; distinctness ledger)
tenant registry complete; tenant lifecycle == Ready for each activated tenant (IC-002)
every secret reference resolves (D-14) — references only, resolved at connect time
Database Router proves one request → one active tenant → one database (D-07/D-30); it remains the sole selector
API Gateway remains the sole ingress (IC-010 §I)
schema/migration readiness within the supported range (D-17)
provisioning audit sink available (B-6) — or an explicit, approved waiver
rollback plan present and proven
human approval recorded
```

## 6. Blocker conditions (any one ⇒ DO-NOT-ACTIVATE / fail-closed)

```
switch missing/false/malformed/incomplete · Control/Tenant DB reference missing · registry/readiness incomplete ·
database-identity proof missing · secret reference unresolved · a Tenant DB not physically distinct ·
Database Router cannot prove one active tenant · API Gateway not sole ingress · DDL/migration status unknown ·
audit sink unavailable when required · rollback plan missing · human approval absent
```

The seeded, grounded blockers (all currently OPEN) are in `b5_activation_blockers.md`; with them open, the gate's
standing decision is **DO-NOT-ACTIVATE**.

## 7. Rollback conditions

Activation must be reversible: if any post-activation check fails (identity mismatch, distinctness regression, router
anomaly, secret-resolution failure), the gate requires immediate rollback to the deferred (in-memory) composition and
records the failure. Rollback never deletes tenant data (retention follows D-24); per-tenant rollback is isolated
(D-30).

## 8. Human approval & audit/evidence

Activation requires explicit human approval (Guard-7-style; recorded). All gate decisions produce a **references-only**
evidence record (`b5_activation_evidence_template.md`), redacted of DSNs/passwords/tokens (IC-001 Global Audit
Representation Rule; D-14).

## 9. Allowed vs forbidden target environments

```
Allowed (B-5 era):   local / non-production / production-like readiness only.
Forbidden (B-5 era): production. Real production activation requires a separate, later, explicitly-authorized PRD.
```

## 10. Relationships (boundaries)

```
to the live main.py deferral : the gate sits ABOVE it; B-5 leaves the NotImplementedError deferral active and pinned.
to a future runtime-gate impl : a later, separately-gated phase implements/wires the switch (wrapping/superseding the
                                SP2_CP_* mechanism while preserving fail-closed); B-5 wires nothing.
to B-6 (provisioning audit sink): the audit sink is a §5 input; its register blocker B5-BLK-4 was closed by the B5-E decision (2026-07-12) — the §5 availability condition remains binding; B-6 builds it separately.
to Lovable/API-Gateway cutover : out of scope; Lovable is UI-only and never accesses DBs directly; cutover is separate.
```

## 11. What B-5 explicitly does NOT do

```
B-5 does not activate runtime.                 B-5 does not modify backend/control_plane/main.py.
B-5 does not wire a runtime switch.            B-5 does not construct durable/real adapters at runtime.
The current fail-closed NotImplementedError deferral remains active and is pinned by the B-5 regression lock.
```

## 12. Governing references

IC-001 (audit references-only) · IC-002 (8-state lifecycle / readiness) · IC-005 (auth references) · IC-010 §O
(physical multi-DB mandatory) / §P (distinctness verification hook) / §H,§M (router boundary) / §I (gateway sole
ingress) · D-07 (registry-authoritative) · D-14 (secret references) · D-15 (provisioning ownership) · D-17 (schema
migration) · D-30 (cross-tenant isolation) · CLAUDE.md #4 (infrastructure independent of backend).

## 13. Separately-governed hosted non-production rollback-proof path (IC-011 / D-40)

Beyond the accepted local rollback scaffold (`infrastructure/runbooks/b5_blk8_rollback_to_deferred_composition.md`)
and the local composed-core rehearsal (`infrastructure/runbooks/controlled_rollback_rehearsal.md`), a **separately-governed
hosted non-production rollback-proof path** is reserved under **IC-011 — Hosted Rollback Proof Contract** and **D-40** (the
B5-BLK-8C stage). This path is documentation and governance only; B-5 wires nothing and executes nothing, and this gate
specification is not itself an execution authorization.

**Requirements (all mandatory; see IC-011 and `infrastructure/runbooks/b5_blk8c_hosted_rollback_proof.md`):**

```
IC-011 compliance
a named operator and a named approver are recorded (references only)
isolated traffic (one served request through the API Gateway; the adjacent tenant is never touched)
physical multi-database proof (one hosted Control DB + at least two physically distinct hosted Tenant databases)
a production-grade SecretRef backend (D-14 references only; never a raw descriptor, password, or token)
a pinned last-known-good reference set (the hosted success target is the last-known-good durable composition)
a backup and restoration checkpoint (references only; no path, descriptor, credential, or dump content recorded)
references-only evidence (the hosted extension of b5_blk8_rollback_evidence_template.md)
restoration and cleanup before the single final write
```

**Emergency fail-closed target.** If restoration to the last-known-good durable composition cannot be safely achieved, the
emergency fail-closed target is the **deferred in-memory composition**; that landing earns `ROLLBACK-NOT-PROVEN` plus an
emergency-safe-state record and never `ROLLBACK-PROVEN-HOSTED-NONPRODUCTION`.

**Locked state (unchanged by this path).** **LIVE PRODUCTION is prohibited.** The activation switch
(`RUNTIME_ACTIVATION_ENABLED`) remains unchanged and unset — this path adds no readiness and flips no switch. This hosted
rollback-proof path produces references-only evidence only; it changes no blocker status and no census. **B5-BLK-8 remains
OPEN.** Only a separate B5-BLK-8D decision may determine any blocker effect; B5-BLK-8C produces evidence and determines none.
The live blocker census remains **7 of 9 OPEN**. Production remains **NOT READY / DO-NOT-ACTIVATE**.
