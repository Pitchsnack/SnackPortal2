# PRD 06 B-6 — Provisioning Audit Sink Contract (reference-only)

**Status: CONTRACT + reference template + additive tests only.** B-6 does **not** activate runtime, does **not** apply
DDL, and does **not** modify the wired audit machinery (`backend/control_plane/audit.py`, `events.py`, `main.py`,
`records.py`, `provisioning.py` remain **off-limits**). This document specifies a durable, append-only, provider-neutral
**Provisioning Audit Sink** *layered on the existing control-plane audit* — it parallels B-2's durable ledger contract
(the runtime wiring is **deferred** to a later, separately-gated phase).

---

## 1. What already exists (B-6 builds on it, does not re-author)

`ControlPlaneAudit` (`backend/control_plane/audit.py`) already records provisioning lifecycle events:
`record(actor, tenant_id, action, from_state, to_state, correlation_id)` → `ControlAuditRecord` appended via
`ControlStore.append_audit()`; `events()` lists them. It is **append-only**, **references-only**, carries **no
hash-chain** and **no secrets**, and is **runtime-wired** (`main.py:21,59-60,71,87`). The action names come from the
**frozen** vocabulary in `backend/control_plane/events.py` (guarded by `EXPECTED_EVENT_ACTIONS` in
`tests/control_plane/test_onboarding_orchestration.py`).

**Audit authority chain:** IC-002 Audit Requirements → **D-34 Operational Audit** → IC-001 Reference-Only
Representation → **IC-010 §J**. The audit-class *homes* live in `contracts/**` (enforced by
`tests/architecture/test_audit_class_homes.py`). B-6 is the **persistence/durability of that existing D-34/IC-001/§J
class** — **not** a new audit class and **not** a parallel vocabulary.

## 2. Provisioning audit is DISTINCT from lineage (do not conflate)

Provisioning audit (**IC-002 / D-34**) records *operational lifecycle* events for tenant/database provisioning. It is
**distinct** from tenant-data **lineage** (**IC-004 / D-23**), which is the hash-chained provenance subsystem. The
existing provisioning audit is deliberately append-only **without** a hash-chain. Any optional/forward hash policy here
(see §5) is a tamper-evidence option for the audit sink and **must not** be modelled on, or conflated with, IC-004/D-23
lineage.

## 3. The sink contract

A **provider-neutral, append-only** sink interface layered on `ControlPlaneAudit`:

- **append-only** — records are appended; update and delete are forbidden (the existing `ControlAuditRecord` is a frozen
  dataclass and the store exposes only `append_audit` / `list_audit`).
- **references-only** — every field is a reference / redacted identifier (D-14, IC-001 Global Audit Representation
  Rule). Never a raw DSN, password, token, private key, cloud credential, unredacted connection string, or business
  payload.
- **durable** — persistence beyond the default in-memory store (the durable Control store is
  `adapters/providers/postgres_store.py`). **Runtime wiring is DEFERRED** (parallels B-2); the default stays in-memory.
- **fail-closed-on-required-write** — see §4.
- **audit-class home** — the existing D-34 / IC-001 / IC-010 §J home, *referenced* (not redefined; homes live in
  `contracts/**`).

## 4. Fail-closed-on-required-write (documented CONTRACT; not wired in B-6)

When provisioning audit is **REQUIRED** (`PROVISIONING_AUDIT_REQUIRED=true`), a failure to durably write a required
audit record **must fail closed** — i.e. block provisioning completion rather than complete un-audited. This is a
**documented contract that a future wiring honors**; **B-6 wires nothing**. The existing distinctness fail-closed
behavior is **unchanged**. `provisioning.py` and `main.py` remain off-limits in B-6. The full fail-closed condition set
is enumerated in `b6_provisioning_audit_fail_closed_policy.md` and summarized here:

```
missing/unresolved sink reference when audit is required · missing correlation id / tenant identity / db-target ref /
outcome · invalid event type · raw secret detected in payload · audit-write failure · append-only violation ·
hash-chain mismatch (only if hash-chaining is enabled) · sink unavailable at provisioning-completion.
```

## 5. Policies (reference keys only — see the template)

Retention, redaction, and (optional/forward) hash policies are expressed as **`*_REF` references** in
`infrastructure/runtime/b6_provisioning_audit_sink.template` (reference-only; not wired). The hash policy key is
**OPTIONAL / forward** and, as stated in §2, must not be conflated with IC-004/D-23 lineage.

## 6. Event catalog

The provisioning audit event set **maps to** the existing `events.py` vocabulary; see
`b6_provisioning_audit_events.md`. B-6 introduces **no** parallel `tenant.provision.*` scheme; genuinely-new events
(rollback family) are a **documented additive-extension proposal only** (a separate governed `events.py` +
`EXPECTED_EVENT_ACTIONS` change — not in B-6).

## 7. Boundaries (what the sink does NOT do)

The sink does **not** select tenant databases, authenticate, authorize, route, replace the Database Router or
Control-Plane readiness, apply DDL, activate runtime, or access Lovable/Supabase directly. It accepts only sanitized,
references-only event payloads. **Control Plane** owns lifecycle/readiness (the sink only observes/records); **Database
Router** is the sole DB selector; **API Gateway** is the sole ingress.

## 8. Deferred (separate, governed gates)

Runtime wiring of the sink · a durable audit-table DDL artifact (a future `infrastructure/db/control/**` item) · a
production sink. B-6 **reduces but does not close** `B5-BLK-4` — see `b6_provisioning_audit_blockers.md` and
`b5_activation_blockers.md`.
