# B-7B — Runtime Audit-Sink Wiring (durable Control-Store selection)

**PRD:** PRD 06 B-7B (controlled non-production runtime audit-sink wiring).
**Status:** controlled non-production wiring; **default OFF** (in-memory). No production activation,
no runtime DDL application, no frontend/Lovable cutover, no API-Gateway cutover.

## What B-7B wires

B-7B lets the Control Plane *optionally* persist its operational audit (IC-002 / D-34) through the
durable PostgreSQL-backed **ControlStore** instead of the in-memory default. The audit sink is **one
consumer** of the `ControlStore` port — `ControlPlane.audit = ControlPlaneAudit(self.store)` — so B-7B
selects a **durable ControlStore**, *not* a separate audit-only sink. There is no new port and no
parallel audit store.

Selection is by a single env var (startup-only), default in-memory:

| `SP2_CP_CONTROL_STORE` | Result |
|---|---|
| unset / empty / `in_memory` | `InMemoryControlStore` — the default; construction performs **no I/O** |
| `postgres` | durable `PostgresControlStore`, resolved by **SecretRef** + **lazy-connect** |
| any other value | **raises** (`ValueError`) — fail closed |

The default path is byte-for-byte the prior behavior (in-memory; no database I/O).

## Lazy-connect — construction performs no I/O

`PostgresControlStore.__init__` opens **no** connection; it records its inputs only. `ControlPlane`
construction and `create_app()` therefore perform **no PostgreSQL I/O even when `postgres` is
selected** — the connection opens on the **first store operation** and **fails closed** there if the
descriptor is unresolvable, the DSN is invalid/unreachable, or the schema is absent. This preserves
the contractual "Construction performs no I/O" invariant. (See `..._fail_closed.md`.)

## Secret reference (D-14) — no DSN literal

The durable Control-DB descriptor is a **secret reference**, never a literal. The composition root
builds a `SecretRef(store_ref, "1")` (default `store_ref` = `control/control-store-dsn`, overridable
via `SP2_CP_CONTROL_STORE_DSN_REF`) and resolves it through a **separate** `EnvReferenceSecretStore`
whose allow-list is **widened to include that ref only**. The default trust-anchor-only secret store
used by Bootstrap (`self.secret_store`) is **preserved unchanged**. `SNACKPORTAL_TEST_DSN` is a
test-harness convention and is **never** reused as runtime configuration. (See `..._config.md`.)

## Timestamp normalization (B7B-D7) — both adapters return `str`

The B-7A forward defect (postgres `list_audit` returned the driver `datetime` while
`ControlAuditRecord.timestamp` is typed `str`) is **resolved**: `postgres_store.list_audit` normalizes
the driver `datetime` to a **UTC ISO-8601 `str`** on read (same instant), so both the in-memory and
postgres adapters return `str`. `records.py` is unchanged (normalize-on-read; minimal blast radius).

## Fail-closed required writes — no partial state

A failed **required** durable audit write rejects the lifecycle transition with **no committed partial
state**. This is implemented via call-site ordering (audit-before-irreversible-commit) in
`registry.py` and `provisioning.py`: the required audit write precedes `put_tenant`, so if the audit
write fails the state change is never committed. No exception is swallowed (audit failures already
propagate). (See `..._fail_closed.md`.)

## Boundaries (unchanged invariants)

- **No runtime DDL.** Durable mode never creates/applies DDL; a missing `control_audit` fails closed.
- **Driver containment.** The `psycopg`/provider import stays in `control_plane/adapters/providers/`;
  the composition root imports the provider **function-locally**.
- Provisioning/operational audit (IC-002/D-34) remains **distinct** from lineage (IC-004/D-23).
- Authentication ≠ Routing/Authorization; the Database Router stays the sole DB selector; the API
  Gateway stays the sole ingress; Lovable is UI-only and never touches a backend database.
- **Physical Multi-Database MVP is mandatory and is NOT future work.** B-7B does **not** prove tenant
  physical multi-database routing — it wires controlled durable Control-Store selection only.

## Evidence

Unit/contract: `tests/control_plane/test_b7b_control_store_selector.py`,
`..._audit_timestamp_normalization.py`, `..._fail_closed_no_partial_state.py`. Architecture:
`tests/architecture/test_b7b_runtime_audit_sink_wiring_boundary.py`. Live PostgreSQL (standalone):
`tests/control_plane/requires_pg/test_pg_control_store_runtime_wiring.py`. See
`..._evidence_template.md` and `..._blockers.md`.
