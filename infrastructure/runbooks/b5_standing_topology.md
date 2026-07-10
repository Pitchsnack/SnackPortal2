# B5-4 — Standing Local Physical Topology (operator runbook)

**Scope:** LOCAL / NON-PRODUCTION ONLY (PRD B5-4). This runbook documents how an operator establishes,
verifies, and tears down the governed B5-4 **standing local topology** using the operator harness
`backend/tests/control_plane/requires_pg/b5_standing_topology.py` (the executable lives under the
backend test/ops zone — `infrastructure/` stays free of backend imports per the repo's independence rule;
this document is the runbook only).

**What it establishes (a precondition fixture — see No-overclaim below):**

- one standing **Control DB** with control DDL `001–009` applied by the explicit `apply` command
  (never at runtime — `create_app()` applies no DDL);
- two deterministic B5-4 tenants — `b5_standing_alpha` and `b5_standing_beta` — onboarded through the
  **real env-composed all-Postgres path** (`Register → Provision → Apply → Verify → Ready`) onto two
  physically distinct tenant databases (`sp2_tenant_b5_standing_alpha`, `sp2_tenant_b5_standing_beta`)
  at **database granularity** on the admin DSN's cluster (cluster-level distinctness stays
  deployment/IaC scope);
- canonical secret references `tenant/<id>/dsn@1` in the registry, with matching **DSN secret files
  outside the repository** under `$SNACKPORTAL_TENANT_SECRET_DIR/tenant/<id>/dsn@1` — one file serves
  BOTH the Control-Plane and Database-Router secret adapters (the shared env/file convention).

---

## 1. Prerequisites

1. The **B-3A local fixture** control instance is up (see `infrastructure/docker/runbooks/local_start.md`):
   the control cluster listens on `127.0.0.1:5540`, database `snackportal2_control_local`, superuser
   `sp2_local`, password ONLY in the untracked `infrastructure/docker/.env.local`.
   (Only the `control-postgres` service is required for this runbook; tenant databases are created on the
   SAME cluster at database granularity by the real provisioning operator.)
2. A backend development environment (Python + `psycopg` installed), run **from `backend/`**.
3. A tenant-secret directory that is **absolute and OUTSIDE the repository worktree** — e.g.
   `%LOCALAPPDATA%\snackportal2\tenant-secrets` (Windows) or `~/.local/state/snackportal2/tenant-secrets`
   (POSIX). The harness REFUSES repo-contained or relative paths.

## 2. Configuration (existing conventions only — no new variable names)

Set these in the shell session only (never committed, never echoed). `<LOCAL_PW>` is the throwaway
local password from your untracked `.env.local`.

POSIX:

```bash
export SNACKPORTAL_SECRET_CONTROL_CONTROL_STORE_DSN_V1="postgresql://sp2_local:<LOCAL_PW>@127.0.0.1:5540/snackportal2_control_local"
export SNACKPORTAL_SECRET_CONTROL_PROVISIONING_ADMIN_DSN_V1="postgresql://sp2_local:<LOCAL_PW>@127.0.0.1:5540/snackportal2_control_local"
export SNACKPORTAL_TENANT_SECRET_DIR="$HOME/.local/state/snackportal2/tenant-secrets"
```

Windows (PowerShell):

```powershell
$env:SNACKPORTAL_SECRET_CONTROL_CONTROL_STORE_DSN_V1 = "postgresql://sp2_local:<LOCAL_PW>@127.0.0.1:5540/snackportal2_control_local"
$env:SNACKPORTAL_SECRET_CONTROL_PROVISIONING_ADMIN_DSN_V1 = "postgresql://sp2_local:<LOCAL_PW>@127.0.0.1:5540/snackportal2_control_local"
$env:SNACKPORTAL_TENANT_SECRET_DIR = "$env:LOCALAPPDATA\snackportal2\tenant-secrets"
```

Notes:

- The two DSNs are resolved **by reference** (`control/control-store-dsn`, `control/provisioning-admin-dsn`)
  through the existing `EnvReferenceSecretStore` convention; the file form under `$SNACKPORTAL_SECRET_DIR`
  works equally. The harness never prints a DSN — every emitted identity is redacted to
  scheme+host+port+database.
- The four `SP2_CP_*` selectors are set to `postgres` **in-process** by the effectful commands (the
  sanctioned all-Postgres composition); you do not need to export them.

## 3. Procedure (run from `backend/`)

```bash
python tests/control_plane/requires_pg/b5_standing_topology.py plan     # read-only intent; no connection
python tests/control_plane/requires_pg/b5_standing_topology.py apply    # DDL (twice: re-apply proof) + secrets + real onboarding
python tests/control_plane/requires_pg/b5_standing_topology.py apply    # idempotent no-op convergence (Ready -> already_onboarded)
python tests/control_plane/requires_pg/b5_standing_topology.py status   # fail-closed verification; non-zero unless complete
```

`status` verifies, read-only: control DDL census (tables, both indexes, both append-only triggers, the
CAS `version` column) · both registry rows Ready with canonical `tenant/<id>/dsn@1` associations · two
distinct physical tenant databases · complete tenant schema census in both (all bootstrap tables +
exactly one System-Primary agent + `schema_version = 1`) · secret files present · BOTH secret-store
adapters (Control-Plane and Database-Router twins) resolve each tenant to its **own** database.

The standing fixture is intended to REMAIN available after establishment (B5-5 / Smoke C preparation).
Do not tear it down unless directed.

## 4. Teardown (explicit, bounded, idempotent)

```bash
python tests/control_plane/requires_pg/b5_standing_topology.py teardown --confirm-b5-teardown
```

Semantics (SUPPORTED lifecycle reconciliation only — nothing is invented):

- registry rows are reconciled through the amended-IC-002 transitions the registry actually supports —
  `Ready → Suspended` (`suspend_tenant`) then `→ Decommissioned` (`decommission_tenant`), with the
  `disable_routing` companion (drops routing evidence, invalidates) — and are **RETAINED** as terminal,
  audited rows. There is deliberately NO registry-row deletion (the ControlStore port has none).
- exactly the two recomputed B5-4 tenant databases are dropped through the existing identifier-guarded
  `PostgresProvisioningOperator.deprovision` (drop-if-exists — rerunning is a no-op). No inventory is
  listed; no other database can be touched.
- exactly the two secret files are removed (missing files are a no-op).
- a tenant caught mid-flight (`Verifying`) fails the run closed — retry later.
- **NOT removed** (shared / out of the harness's ownership): the Control DB and its DDL, the durable
  audit trail, and the cluster roles created by the tenant DDL templates (`sp2_provisioner`,
  `lineage_writer`, `lineage_reader`).

**Terminal consequence (by design):** `Decommissioned` has no exit. After a teardown, `apply` for the
same tenant ids on the same standing Control DB fails closed. Re-establishing the fixture requires the
full-fixture reset below.

## 5. Full-fixture reset (the separate, documented reset path)

The bounded teardown never touches the Control DB. To reset the WHOLE local fixture (e.g. to re-apply
after a teardown):

1. Tear down the B-3A containers and volumes — follow `infrastructure/docker/runbooks/local_teardown.md`
   (`docker compose … down -v` removes the disposable data volumes, Control DB included).
2. Bring the fixture back up (`local_start.md`), then re-run §3 (`plan → apply → status`).
3. Remove any leftover tenant-secret files under `$SNACKPORTAL_TENANT_SECRET_DIR/tenant/` for the two
   B5-4 ids if a fresh secret root is wanted (the next `apply` rewrites them atomically anyway).

## 6. Secret hygiene (D-14)

- Secret files hold the raw tenant DSN and live ONLY under the operator-provided directory outside the
  repo; writes are atomic (`os.replace`) and owner-only (`0600`) where the OS supports it (on Windows
  the mode bits are advisory — keep the directory under your user profile).
- No DSN, password, or secret value is ever printed by any command, stored in the registry (references
  only), or committed anywhere. The committed repo carries only placeholder examples (`<LOCAL_PW>`).

## 7. Related proofs and CI disposition

- The DISPOSABLE proof of this harness is `backend/tests/control_plane/requires_pg/test_pg_b5_standing_topology.py`
  (scratch Control DB + scratch tenants + tmp secret dir; sentinel-survival and refusal legs; run
  standalone with `SNACKPORTAL_TEST_DSN`). It is a justified MANUAL_ONLY exception of the live-PG
  run-set completeness guard this slice — loop enrollment is a `.github` edit and is a tracked follow-up.
- Architecture pins: `backend/tests/architecture/test_b5_standing_topology_boundaries.py`.

## 8. No-overclaim (required status)

This runbook and harness establish a **local precondition fixture** only. They do NOT constitute
Smoke C, a served-request proof, cluster-level distinctness, production deployment readiness, or
physical-database proof, and they change no runtime activation posture.

```text
B5-BLK-4 OPEN.
Physical Multi-Database MVP mandatory and NOT complete.
Smoke C deferred / HARD-GATE.
```
