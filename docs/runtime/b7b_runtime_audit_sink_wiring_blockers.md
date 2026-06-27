# B-7B — Blockers

**PRD 06 B-7B.** B-7B **reduces** — but does **not** close — the production-readiness blocker.

## B5-BLK-4 — **OPEN**

B5-BLK-4 (production runtime activation gate; see `b5_activation_blockers.md`) and the provisioning
audit-sink sub-blocker B6-BLK-2 (see `b6_provisioning_audit_blockers.md`) remain **OPEN**.

### What B-7B reduces (controlled non-production only)

- **runtime audit-sink wiring** — the Control Plane can now *select* the durable PostgreSQL ControlStore
  (audit is one consumer) behind explicit config, default OFF, lazy-connect.
- **fail-closed required-write behavior** — required durable audit writes fail closed with no committed
  partial state (runtime-proven in controlled non-production).
- **the B-7A timestamp forward defect** — `list_audit` now returns a type-stable `str` (same instant)
  for both adapters.

### What remains OPEN (NOT closed by B-7B)

- production sink readiness and **production activation** (production descriptors; the production
  runtime activation gate, B5-BLK-4);
- retention / redaction / hash-policy **production** approval;
- frontend / API-Gateway cutover;
- **Physical Multi-Database MVP proof** — mandatory and **NOT** future work. B-7B does **not** prove
  tenant physical multi-database routing; it wires controlled durable Control-Store selection for the
  Control Plane only. A single shared database + `tenant_id` is **not** an acceptable substitute. One
  Request → One Active Tenant → One Database; the Database Router is the sole DB selector; the API
  Gateway is the sole ingress; the Control Plane is the lifecycle/readiness authority.

## Cross-references (not modified by B-7B)

- `b5_activation_blockers.md` — production runtime activation gate (B5-BLK-4).
- `b6_provisioning_audit_blockers.md` — provisioning audit-sink sub-blocker (B6-BLK-2).
- `b7_provisioning_audit_blockers.md` — durable-store DDL blockers (created-not-applied).

These off-limits blocker docs are reconciled to record B-7B's reduced sub-items under a **separate
governed** doc change, not by B-7B (which must leave `b5_*` / `b6_*` / `b7_*` byte-unchanged).
