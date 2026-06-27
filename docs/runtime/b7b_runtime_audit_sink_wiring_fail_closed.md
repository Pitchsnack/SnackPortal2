# B-7B — Fail-Closed Semantics + No Partial State

**PRD 06 B-7B.** Required durable audit writes are **fail-closed**: on failure the lifecycle
transition is rejected with **no committed partial state**, and **no exception is swallowed**.

## 1. Construction (lazy-connect)

`PostgresControlStore.__init__` opens no connection. `ControlPlane()` / `create_app()` perform no
PostgreSQL I/O even in durable mode. The connection opens on the **first** store operation.

## 2. First-use failure classes (all propagate; secret-free messages)

| Failure | Cause | Result |
|---|---|---|
| `PermissionError` | the control-store ref is not allow-listed | first op raises; never connects |
| `LookupError` | the ref is unresolvable (no env var / no secret file) | first op raises; never connects |
| connect error | DSN invalid / Control DB unreachable | first op raises (fail closed) |
| missing table | `control_audit` absent (no runtime DDL) | `list_audit` / `append_audit` raises — never returns `[]`, never auto-creates |

Error messages carry **no DSN, password, or secret material**; the resolved descriptor is dropped
immediately after the connect call (D-14).

## 3. No partial state (audit-before-irreversible-commit)

Required lifecycle transitions write the audit record **before** the irreversible state commit
(`put_tenant`). Call sites reordered in B-7B:

- `registry.py` — `register_tenant`, `_transition` (covers MarkProvisioning / Suspend / Decommission)
- `provisioning.py` — `_transition` (Verifying / Ready / Failed gate transitions), `reassociate`

Consequence: if the required durable audit write fails, the state change is **never committed** — the
operation is rejected and the tenant remains in its prior state. The in-memory default is unaffected
(its writes never fail). The correlation id is carried through to the (failed) audit write.

> Scope note: `lifecycle.py` (`TenantLifecycleService`, the deferred Phase-4 writer) is **not** wired
> into the `create_app()` composition root and is outside this change's authorized scope; a uniform
> ordering there would be a separate governed change. B-7B does not modify it.

## 4. No best-effort swallow

`ControlPlaneAudit.record()` calls `store.append_audit()` and lets exceptions propagate — there is no
best-effort path, and B-7B introduces none. Required provisioning/lifecycle audit writes never fall
back silently.

## 5. Evidence (mutation-form / non-vacuity)

- `tests/control_plane/test_b7b_fail_closed_no_partial_state.py` — a store whose `append_audit` fails
  causes `register_tenant` / `mark_provisioning` / gate `verify` to raise with the state **unchanged**
  (under the pre-B-7B ordering these assertions fail — proven by a controlled mutation during
  development). Plus adapter-level `PermissionError` / `LookupError` fail-closed with secret-free
  messages.
- Live: `tests/control_plane/requires_pg/test_pg_control_store_runtime_wiring.py` — unreachable DSN
  leaves **no orphan row**; `LookupError`, `PermissionError`, and missing-table all fail closed;
  append-only still rejects mutation.
