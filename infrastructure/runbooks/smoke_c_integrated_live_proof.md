# Smoke C V2 — Integrated Live Proof (operator runbook)

> ## ⚠️ HISTORICAL — AUTHFIX-B (Gate A)
>
> Every prerequisite and status claim in this document that depends on the **B5-4A standing
> authentication fixture** — in particular the `12/12` extension checks and the "before AND after
> 12/12" obligation — is **UNSATISFIABLE against the current standing environment** and must be read
> as historical. The `b5_standing_alpha` / `b5_standing_beta` / `b5_standing_dormant` subject state
> was replaced around **2026-07-21** by the four-cluster standing fixture. That red is standing and
> pre-existing; it is not caused by any later change.
>
> Nothing here is amended and no claim is deleted: Stage 0 forbids partial retirement of this family,
> and the procedure remains correct for the state it was written against. The accepted replacement for
> the fixture's subject-state verification is
> `backend/tests/control_plane/requires_pg/test_pg_clm_standing_auth_posture.py`.


**Scope:** LOCAL / NON-PRODUCTION ONLY (PRD Smoke C V2). This runbook documents how an operator executes
the **SMOKE-C-SPEC-01** integrated live local topology proof over the **established, permanent** B5-4/B5-4A
standing fixture, using the operator harness
`backend/tests/control_plane/requires_pg/smoke_c_integrated_live_proof.py` (the executable lives under the
backend test/ops zone — `infrastructure/` stays free of backend imports; this document is the runbook only).

## 1. What the proof is (and is not)

Smoke C V2 drives one real request path, end to end, over loopback ephemeral ports:

```text
InboundRequest -> Gateway.handle (IN-PROCESS, the real composed API Gateway)
  -> real Auth Router over the auth wire (PyJwtSignatureVerifier + the standing Control DB read edge)
  -> real Database Router over the dispatch wire (HttpRoutingRead + EnvTenantSecretStore + psycopg)
  -> exactly one standing physical tenant database
```

It executes **every binding SMOKE-C-SPEC-01 scenario** (nine rows: the alpha and beta happy paths plus the
seven failure-mode rows) and proves, per row, the exact gateway envelope AND — where the wire envelope
collapses — the binding internal auth-boundary code:

| Row | Gateway envelope | Internal code |
|---|---|---|
| alpha success | `200 ok` (dispatched) | routed to `sp2_tenant_b5_standing_alpha` only |
| beta success | `200 ok` (dispatched) | routed to `sp2_tenant_b5_standing_beta` only |
| known non-Ready `b5_standing_dormant` (+ standing membership) | `403 forbidden`, never routed | `tenant_not_ready` |
| unknown tenant | `403 forbidden` (never 503) | `tenant_access_denied` |
| wrong tenant carrier | `403 carrier_mismatch` | `carrier_mismatch` |
| invalid signature (wrong key) | `401 unauthenticated` | `bad_signature` |
| unknown `kid` | `401 unauthenticated` | `unknown_kid` |
| unknown issuer | `401 unauthenticated` | `unknown_issuer` |
| control plane unavailable (read edge stopped) | `503 unavailable` | `control_plane_unavailable` |

The proof is **zero-mutation by contract**: it writes nothing to the Control DB, nothing to any tenant DB,
nothing to the audit history, no secret material, and no repository artifact; the complete before-state must
equal the after-state exactly. Denied requests are proven to perform **zero tenant dispatch, zero pool
acquisition, and zero tenant DB connection**. Every RS256 token is minted at run time by the existing B5-5
fixture (`backend/tests/api_gateway/crypto_fixture.py`); no key or token is ever persisted or printed, and
DSNs are resolved by reference and never printed (redacted identities only, scheme+host+port+database).

The proof is NOT a production/deployment claim, NOT cluster-level distinctness (database granularity on the
local standing cluster only), and NOT a B5-BLK-4 closure: routing/auth audit evidence in this proof is
in-memory (DBR-AR-2, the durable routing-audit sink, remains a separate open follow-on).

## 2. Command surface (deliberately read-only)

There is **no apply command, no teardown command, and no delete/reset/mutation command** of any kind — the
proof reads the standing fixture and leaves it exactly as found. Nothing this harness does ever needs
cleanup. The only subprocess invocations are the two status-only standing-operator delegations (B5-4 and
B5-4A `status`) and one read-only `git rev-parse HEAD` so the evidence binds to the tested commit.

## 3. Prerequisites

1. The **B5-4 standing topology is established and healthy**: from `backend/`,
   `python tests/control_plane/requires_pg/b5_standing_topology.py status` reports **6/6 PASS**
   (see `infrastructure/runbooks/b5_standing_topology.md`).
2. The **B5-4A standing auth fixture is complete**: from `backend/`,
   `python tests/control_plane/requires_pg/b5_standing_auth_fixture.py status` reports the 6/6 delegation
   plus all **12 extension checks PASS** (see `infrastructure/runbooks/b5_standing_auth_fixture.md`) —
   the three `b5_standing_member` memberships and the permanent non-Ready `b5_standing_dormant` tenant.
3. A backend development environment (Python + `psycopg` installed), run **from `backend/`**.
4. The same configuration as the B5-4 runbook §2 (existing conventions only — no new variable names): the
   control-store and provisioning-admin DSNs resolved **by reference** through the `EnvReferenceSecretStore`
   env/file convention, and `SNACKPORTAL_TENANT_SECRET_DIR` pointing at the canonical tenant-secret root
   (absolute, OUTSIDE the repository — refused otherwise). This harness only ever **reads** that root.

## 4. Procedure (run from `backend/`)

```bash
python tests/control_plane/requires_pg/smoke_c_integrated_live_proof.py plan     # read-only intent + prerequisites
python tests/control_plane/requires_pg/smoke_c_integrated_live_proof.py run      # the integrated zero-mutation proof
python tests/control_plane/requires_pg/smoke_c_integrated_live_proof.py status   # read-only fail-closed verification
```

- `plan` re-verifies B5-4 6/6 and B5-4A 12/12 (status-only subprocess), lists the nine binding scenarios
  with their exact envelopes/codes, shows the sanitized topology intent (redacted identities; loopback
  ephemeral ports; secret **references** only), and states that no mutation is planned.
- `run` revalidates the prerequisites, captures the complete read-only before-state, composes the real
  services from the merged env-composition seams (`build_read_server_from_env` in the all-postgres posture,
  `build_authenticate_server_from_env`, `build_dispatch_server_from_env`, `build_gateway` with both
  `build_*_from_env` transports), hosts each single-threaded server on a test-owned daemon thread on a
  loopback ephemeral port, waits for readiness within a bounded timeout, executes the nine scenarios
  serially (the read edge is deliberately stopped before the final unavailability row), proves the
  alpha/beta database identities on the exact route-bound pooled connections, stops every server and
  thread in `finally`, drains all pools, proves port release, restores every touched environment key, and
  requires **before-state == after-state** exactly. Exit is non-zero unless every obligation holds.
- `status` re-verifies the prerequisites (B5-4/B5-4A delegation, spec + RS256 fixture pinned, standing
  alpha/beta/dormant rows, zero residue, no leftover in-process listener) and reports the last in-process
  proof evidence when `run` executed in the same process. Status **never** claims the proof passed merely
  because prerequisites are healthy.

## 5. Environment discipline

The run sets ONLY existing configuration names (the four `SP2_CP_*` selectors, `SP2_CP_READ_HOST`,
`SP2_AR_CONTROL_PLANE_READ_BASE_URL`, `SP2_AR_ISSUERS`, `SP2_DBR_ROUTING_READ_BASE_URL`, and the two
`SP2_GW_*` transport selectors), leaves every `*_PORT` knob unset (ephemeral OS-assigned ports on
`127.0.0.1` only), and restores every touched key in `finally` — no global environment leakage survives the
command. `SNACKPORTAL_TENANT_SECRET_DIR` and the DSN reference secrets are operator-provided standing
configuration; their values are never printed.

## 6. Related proofs and CI disposition

- The live proof of this harness is
  `backend/tests/control_plane/requires_pg/test_pg_smoke_c_integrated_live_proof.py` (standing-fixture-bound:
  it drives plan → run → status in-process, independently verifies every scenario, the zero-mutation
  contract, shutdown/port release, environment restoration, and secret hygiene; it clean-skips when nothing
  is configured and fails closed on a partial configuration). It is a justified MANUAL_ONLY exception of the
  live-PG run-set completeness guard — loop enrollment is a `.github` edit outside this slice's authorized
  surface; tracked follow-up.
- Architecture pins: `backend/tests/architecture/test_smoke_c_integrated_live_proof_boundaries.py`.

## 7. No-overclaim (required status)

A green run is the Smoke C V2 proof executed in the implementation environment — nothing more. It does not
close B5-BLK-4 (a separate, Dan-authorized decision), does not complete any MVP scope, and claims nothing
about production readiness or deployment.

```text
B5-BLK-4 OPEN.
Physical Multi-Database MVP mandatory and NOT complete.
```
