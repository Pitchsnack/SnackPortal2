# PRD 06 B-5 — Production Runtime Activation Gate (specification)

**Phase:** PRD 06 B-5 — controlled non-production. **Baseline:** `origin/main @ 9684919`.
**Gate status: NOT READY (default).** **B-5 builds this gate as documentation + a reference template + a blocker
register + an evidence template + a readiness matrix + additive guard tests. B-5 does NOT activate runtime, does NOT
modify backend source, does NOT modify `backend/control_plane/main.py`, and does NOT wire a runtime switch.**

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
control-plane signals    tenant lifecycle/readiness state (IC-002 7 states), distinctness evidence (IC-010 §P)
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
to B-6 (provisioning audit sink): the audit sink is an input + a blocker (B5-BLK-4); B-6 builds it separately.
to Lovable/API-Gateway cutover : out of scope; Lovable is UI-only and never accesses DBs directly; cutover is separate.
```

## 11. What B-5 explicitly does NOT do

```
B-5 does not activate runtime.                 B-5 does not modify backend/control_plane/main.py.
B-5 does not wire a runtime switch.            B-5 does not construct durable/real adapters at runtime.
The current fail-closed NotImplementedError deferral remains active and is pinned by the B-5 regression lock.
```

## 12. Governing references

IC-001 (audit references-only) · IC-002 (7-state lifecycle / readiness) · IC-005 (auth references) · IC-010 §O
(physical multi-DB mandatory) / §P (distinctness verification hook) / §H,§M (router boundary) / §I (gateway sole
ingress) · D-07 (registry-authoritative) · D-14 (secret references) · D-15 (provisioning ownership) · D-17 (schema
migration) · D-30 (cross-tenant isolation) · CLAUDE.md #4 (infrastructure independent of backend).
