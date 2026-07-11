# B5-4A V2 — Standing Authentication Fixture Extension (operator runbook)

**Scope:** LOCAL / NON-PRODUCTION ONLY (PRD B5-4A V2). This runbook documents how an operator extends the
**established** B5-4 standing local topology (see `b5_standing_topology.md`) with the **permanent** standing
authentication fixture rows, using the operator harness
`backend/tests/control_plane/requires_pg/b5_standing_auth_fixture.py` (the executable lives under the backend
test/ops zone — `infrastructure/` stays free of backend imports; this document is the runbook only).

## 1. Purpose (permanent, additive, governed)

Smoke C V2 must prove BOTH auth-boundary denial rows through the real standing Control DB and the real Auth
Router resolver:

- **unknown tenant** → `tenant_access_denied` — needs NO Control DB row at all;
- **known non-Ready tenant** → `tenant_not_ready` — needs a tenant row AND a membership row, because the
  live resolver checks **membership BEFORE readiness**: a non-member of any tenant (known or unknown) is
  denied `tenant_access_denied` with no existence leak, and only a member of a known non-Ready tenant can
  observe the non-Ready denial.

This extension therefore establishes exactly **four permanent rows** (and nothing else):

```text
membership: b5_standing_member -> b5_standing_alpha    (TENANT_AGENT)
membership: b5_standing_member -> b5_standing_beta     (TENANT_AGENT)
membership: b5_standing_member -> b5_standing_dormant  (TENANT_AGENT)
tenant:     b5_standing_dormant                        (Registered / non-Ready)
```

`b5_standing_member` is a principal **identifier** carried on the membership rows — it is not a separate
Control DB row. The fixture is **permanent by design**: the ControlStore port has no row deletion, the audit
history is append-only by database trigger, and no removal API exists or is invented. There is deliberately
**no teardown command and no delete path** in this harness.

## 2. What the dormant tenant is (and is not)

- Registered through the real `register_tenant` API only — it stays in lifecycle `Registered`, so the real
  Control Plane read edge serves `ready=false` and nothing can route to it (only `Ready` is routable; the
  Database Router's own defense-in-depth also refuses non-ready routing views).
- Its `database_association_ref` is the canonical reference `tenant/b5_standing_dormant/dsn@1`, kept
  **dangling by design**. A reference is a store LOCATION, not secret material: there is **no matching
  secret file** under the tenant-secret root, **no matching secret env key**, **no physical database**
  (`sp2_tenant_b5_standing_dormant` must remain absent), and **no tenant schema**. Nothing on the deny path
  ever resolves the reference.
- Exactly **one** permanent `RegisterTenant` audit row records its creation (`from_state` null →
  `to_state` `Registered`); memberships are unaudited by the current design, so no membership audit rows
  exist or are invented. The audit row is the durable provenance of the fixture and is intentionally
  undeletable through the append-only triggers.
- No federation row is created — the tenant row carries a federation reference string only, matching the
  two standing B5-4 tenants.

## 3. Prerequisites

1. The **B5-4 standing topology is established and healthy**: the B-3A control fixture container is up and
   `python tests/control_plane/requires_pg/b5_standing_topology.py status` (from `backend/`) reports
   **6/6 PASS**. Both `plan` and `apply` of this harness re-verify that first and refuse otherwise.
2. A backend development environment (Python + `psycopg` installed), run **from `backend/`**.
3. The same configuration as the B5-4 runbook §2 (existing conventions only — no new variable names): the
   control-store and provisioning-admin DSNs resolved **by reference** through the `EnvReferenceSecretStore`
   env/file convention, and `SNACKPORTAL_TENANT_SECRET_DIR` pointing at the canonical tenant-secret root
   (absolute, OUTSIDE the repository — refused otherwise). This harness only ever **reads** that root (to
   prove the dormant secret file is absent); it writes no file.

## 4. Composition posture (control-store-standalone)

The effectful/status commands compose the Control Plane with **only the durable control store enabled**
(`SP2_CP_CONTROL_STORE=postgres`, the sanctioned RULE-2 posture) and **force the three live-side selectors
to `in_memory` in-process**. Under that mixed effective posture the plane's onboarding/recovery surface is
replaced by fail-closed deny facades, so this operator is **physically incapable** of provisioning a tenant
database or applying a tenant schema — and it additionally refuses to run unless the durable store and the
onboarding deny-guard are actually composed. Writes go only through the two supported APIs
(`register_tenant`, `add_membership`); the only raw SQL anywhere is the single read-only `pg_database`
absence probe.

## 5. Procedure (run from `backend/`)

```bash
python tests/control_plane/requires_pg/b5_standing_auth_fixture.py plan     # read-only classification + intent
python tests/control_plane/requires_pg/b5_standing_auth_fixture.py apply    # additive convergence (fail-closed preflight)
python tests/control_plane/requires_pg/b5_standing_auth_fixture.py apply    # idempotent no-op proof (0 new rows, 0 new audit rows)
python tests/control_plane/requires_pg/b5_standing_auth_fixture.py status   # fail-closed verification; non-zero unless complete
```

- `plan` classifies each intended row as `ABSENT` / `EXACT` / `CONFLICTING` and reports whether apply would
  be additive or a no-op. Read-only; no mutation.
- `apply` requires the original B5-4 status 6/6, exact-preflights all four rows, and **fails closed before
  writing anything** on ANY conflict (both supported write APIs would otherwise silently mask drift — the
  membership write is an upsert and the registration silently returns an existing row, so drift must be
  refused, never "applied over"). Only absent rows are created. A second apply converges to zero new tenant
  rows, zero new membership rows, and zero new audit rows.
- `status` first re-verifies the ORIGINAL B5-4 topology (6/6, via a status-only subprocess — the two
  fixtures remain separately verifiable), then proves the extension obligations independently: the three
  memberships exact, the dormant row exact and `Registered`, `ready=false` through the real read service,
  the membership-gated non-Ready precondition, the exact dangling canonical reference, no dormant secret
  material (file, env key, or adapter-resolvable), no dormant physical database or tenant schema, exactly
  one `RegisterTenant` audit row, zero temporary smoke-run residue rows, and no unrelated standing rows.

## 6. Partial apply and conflict handling

- **Partial additive application is safely resumable:** every row is independently preflighted, so a rerun
  of `apply` creates only what is still missing and never duplicates anything (registration is idempotent
  by tenant id; an exact membership is left untouched).
- **Conflicts fail closed:** a `CONFLICTING` classification (wrong role, drifted dormant row, or duplicate
  audit provenance surfaced by `status`) stops the command with a non-zero exit and **zero writes**. There
  is no force flag and no overwrite path. Resolution of a genuinely conflicted standing Control DB is a
  governance decision (ultimately the B5-4 runbook's full-fixture reset re-establishes everything) — this
  harness never invents a mutation to "fix" drift.

## 7. Relationship to the original B5-4 topology

The original B5-4 standing topology (Control DB DDL, the two Ready tenants on their own physical databases,
secret files, adapter resolution) remains **separately owned and separately verified**: its own `status`
must stay 6/6 before and after this extension, and this harness invokes it read-only as a subprocess with
status-only argv (never imports it, and cannot reach its apply/teardown surface). The four extension rows
change nothing the B5-4 checks read.

## 8. Intended use (Smoke C V2) and standing status

Smoke C V2 (authored after this slice merges) will use `b5_standing_member` for the alpha and beta happy
paths and `b5_standing_member` + `b5_standing_dormant` for the non-Ready denial leg — with **no temporary
Control DB rows** and read-only standing Control DB / tenant DB use. Note the wire envelope collapses both
denial rows to the same 403 `forbidden`; the distinguishing code is pinned at the in-process/audit layer,
exactly as the Smoke C specification requires.

Smoke C has not yet run. This extension is a precondition fixture only — it is not Smoke C, not a
served-request proof, and not physical-database proof, and it changes no runtime activation posture.

```text
Smoke C not executed.
B5-BLK-4 OPEN.
Physical Multi-Database MVP mandatory and NOT complete.
```

## 9. Related proofs and CI disposition

- The live proof of this harness is `backend/tests/control_plane/requires_pg/test_pg_b5_standing_auth_fixture.py`
  (standing-fixture-bound: it exercises plan → apply → apply → status against the REAL standing Control DB
  additively and restores nothing because nothing disposable is created; it clean-skips without the standing
  configuration). It is a justified MANUAL_ONLY exception of the live-PG run-set completeness guard — loop
  enrollment is a `.github` edit outside this slice's authorized surface; tracked follow-up.
- Architecture pins: `backend/tests/architecture/test_b5_standing_auth_fixture_boundaries.py`.
