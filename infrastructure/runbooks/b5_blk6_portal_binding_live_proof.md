# B5-BLK-6C-C — Real Control-DB Portal-Composition Disposable Proof (operator runbook)

> ## ⛔ WITHDRAWN — the API Gateway has been DELETED
>
> The 6C-C portal-binding proof (`tests/control_plane/requires_pg/b5_blk6_portal_binding_live_proof.py` + its wrapper) was DELETED: it composed the Gateway and proved the Gateway-composed portal DTOs against a real Control DB. Response composition is now owner-resident (`control_plane/portal.py`, `database_router/portal.py`) and is pinned in the DEFAULT suite by `tests/architecture/test_ic009_portal_binding_checks.py` and `tests/gateway_free/test_response_contract_parity.py` — but there is no longer a LIVE Control-DB proof of it.
>
> Nothing in this document may be run, and no evidence produced by it before the removal may be
> cited as current. It is retained because the recorded scenario, its ordering rules and its
> evidence format are what a Gateway-free successor must reproduce.

**Scope:** NON-PRODUCTION / disposable-only (PRD B5-BLK-6C-C). This runbook documents the governed
operator procedure for the MANUAL_ONLY disposable proof that the API Gateway's composed CONTROL
portal read (startup directory, investor directory, MembershipsForPrincipal) works end-to-end over a
**real PostgreSQL Control database**: fresh disposable Control DB → control DDL 001-009 only →
direct-SQL seed → real `PostgresControlStore`-backed Control Plane → the existing loopback read edge
→ the production `HttpControlPlaneRead` adapter (env-selected via `SP2_GW_CONTROL_READ_BASE_URL`) →
the existing Gateway with `control_read` injected → mandatory `finally` teardown with a
zero-artifact census.

Standing rules (inherited from `infrastructure/runbooks/README.md`): secret references only (D-14 —
never a DSN, password, token, or credential in this document, a shell history echo, or any evidence
artifact); fail-closed (any missing or ambiguous proof stops the procedure); **no runtime DDL** —
the proof applies DDL only inside its own disposable database, through the accepted operator helper.

---

## 1. Preconditions (ALL must hold)

1. A **disposable local PostgreSQL cluster** (version 11+) you are authorized to create and drop
   databases on. Never a production, staging, or shared cluster.
2. `SNACKPORTAL_TEST_DSN` set to that cluster's admin connection (by name only — the value is never
   printed, logged, or committed; the proof sweeps its own transcript for leakage).
3. `psycopg` importable (the backend dependency set). A **partial** configuration — DSN without
   driver, or driver without DSN — FAILS CLOSED; the proof clean-skips only when nothing is set.
4. The four control-plane composition selectors are unset (or at their in-memory defaults) — the
   proof refuses to run under a live-composition environment and composes its plane by explicit
   store injection only.
5. No database named `sp2_b5_blk6_portal_proof` exists — the proof refuses a pre-existing name
   (it must prove the disposable name did not exist before creation).

## 2. Run (MANUAL_ONLY — never part of the default suite or the hosted live-pg workflow)

From `backend/`:

```text
python tests/control_plane/requires_pg/test_pg_b5_blk6_portal_binding_live_proof.py
```

The proof executes every scenario in one arc: startup/investor directory composition, live
read-through identity, non-empty and empty MembershipsForPrincipal (each emitting exactly one
`workspace_memberships_read` event, observed with an **in-memory** recorder), unsupported-kind and
client-kind fail-closed legs, ImportInitiation (**envelope only** — the Control-DB row census is
proven unchanged), TenantOperation (references-only dispatch against a stub router), the negative
IC-007 set, the pagination limitation (**one page** only — no cursor sent, `next_cursor` never
followed), and the malformed / oversized / unavailable failure legs (503, zero success events).

## 3. Teardown guarantee

Teardown always runs from the proof's `finally` block: connections released, backends terminated,
the disposable database dropped, and the `pg_database` census re-checked. A green run ends with:

```text
disposable database datname count == 0
```

Any other ending is a FAILED run: drop the disposable database manually, then re-run.

## 4. What a green run proves — and does NOT prove

Proves: the composed CONTROL portal read works against a real Control DB on the accepted
composition seams, applying control DDL 001-009 only, with correct audit cardinality and zero
retained artifact.

Does NOT prove (binding non-claims):

- no durable audit persistence and no operator audit retrieval (the success event is observed
  in-memory; the durable operational-audit home is separate governed work);
- no served northbound API Gateway ingress and no Lovable integration (B5-BLK-5 remains OPEN);
- no tenant-DB routing, no cross-cluster distinctness, no production database identity;
- no pagination beyond the single composed page (a pinned limitation, not a capability);
- no real import business write and no real tenant business result (envelope/dispatch proofs only);
- no positive IC-007 capability; no Global Deal directory;
- no blocker closure: **B5-BLK-6 remains OPEN**; only B5-BLK-6C-D may close it;
- production remains **NOT READY / DO-NOT-ACTIVATE**.

## 5. Guards

The proof family is pinned by `backend/tests/architecture/test_b5_blk6_portal_binding_live_proof_boundaries.py`
(DDL range, teardown census, MANUAL_ONLY registration, fail-closed wrapper, secret hygiene) and the
adapter residuals by `backend/tests/architecture/test_ic010_control_read_adapter_boundaries.py`
(two-kind set equality, timeout/size/one-request bounds, pagination non-claim).
