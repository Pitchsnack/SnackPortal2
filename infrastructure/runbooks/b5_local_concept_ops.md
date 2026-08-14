# B5 Local-Concept Bounded Operations (operator runbook)

**Labels:** `MANUAL_ONLY` · `LOCAL-CONCEPT-ONLY` · `NON-PRODUCTION` · `DAN START-GATE REQUIRED` · `DO-NOT-ACTIVATE`

**Scope:** the reviewed, **non-executable** operator procedure for the local-concept bounded operations wrapper
`backend/tests/control_plane/requires_pg/b5_local_concept_ops.py` — a thin **Option B** wrapper that fills only
the four local-concept gaps (topology-wide **backup**, safe **restore-validation** into a fresh disposable
database, deterministic synthetic **seed**, and approved **artifact placement**) over the existing governed
provisioning path. It introduces no new database architecture, migration source, secret backend, routing path,
or composition root. This runbook authorizes nothing on its own; every effectful command requires an explicit
human **DAN START-GATE**. This stage **closes no blocker**: the live blocker census remains **7 of 9 OPEN**;
Production remains **NOT READY / DO-NOT-ACTIVATE**.

**References (normative — DO NOT restate):**

- `infrastructure/runbooks/b5_standing_topology.md` — the standing four-cluster topology `plan`/`apply`/`status`/
  `teardown` procedure. This wrapper reuses only its **status surface and idioms**; it never adopts the
  `b5_standing_alpha`/`b5_standing_beta` tenant set and never invokes `apply` or `teardown`. This runbook
  references it and restates none of it.
- `infrastructure/runbooks/controlled_rollback_rehearsal.md` — the disposable-topology discipline (START-GATE
  preconditions, deterministic disposal, `finally`/STOP-on-failure, single-final-write evidence). This runbook
  references it and restates none of it.
- `infrastructure/runbooks/README.md` — the standing rules inherited below.

**Standing rules (inherited from `infrastructure/runbooks/README.md`):** secret **references only** (D-14 —
never a DSN, password, token, or credential in this document, a shell echo, or any manifest/evidence artifact);
**fail-closed** (any missing or ambiguous proof stops the procedure); **no runtime DDL** (this wrapper embeds
no schema DDL and applies none — the canonical control/tenant DDL is applied only by the existing standing
path); **LOCAL-CONCEPT-ONLY** — a hosted or production target is never permitted here.

---

## 1. The four governance stages (keep DISTINCT — never conflate)

```text
STATIC IMPLEMENTATION    authoring + static/architecture validation only (this stage; NO runtime)
LOCAL RUNTIME EXECUTION  Docker + PostgreSQL backup/restore-validate/seed, ONLY after the Dan START-GATE
HOSTED PROOF             a hosted, physically-separated proof — a separate, later, separately-authorized stage
PRODUCTION ACTIVATION    NOT READY / DO-NOT-ACTIVATE — never released by any local-concept evidence
```

Local evidence produced by this wrapper is **LOCAL-CONCEPT-ONLY**. It **cannot close a hosted or a production
requirement**, and no local run may be presented as hosted or production proof.

## 2. Authoritative local topology (record before any execution)

Exactly four physically separate local clusters at their compose database identities
(`infrastructure/docker/docker-compose.local.yml`). The descriptive witness roles are test labels only and
**never** rename a database identity.

| Role | Compose service | Database identity | Port | Witness role |
|---|---|---|---:|---|
| Control | `control-postgres` | `snackportal2_control_local` | 5540 | control |
| ACME | `tenant-acme-postgres` | `snackportal2_tenant_acme_local` | 5541 | Tenant Alpha witness |
| ZETA | `tenant-zeta-postgres` | `snackportal2_tenant_zeta_local` | 5542 | Tenant Beta witness |
| NOVA | `tenant-nova-postgres` | `snackportal2_tenant_nova_local` | 5543 | Adjacent witness |

The retained standing tenants `b5_standing_alpha` and `b5_standing_beta` are **not** part of this set. This
wrapper must never rename, disturb, or restore over them.

## 3. Approved artifact root (record before any execution)

```text
D:\Pitchsnack\SP2-Local-Concept
```

The **prohibited** short path `D:\SP2-Local-Concept` is never substituted. The approved root and its eight
destinations (`01-Execution-Reports` … `08-Temporary-Logs`) **already exist**; the operator **verifies** them,
**tolerates a pre-existing empty root**, and **never creates, recreates, deletes, or assumes ownership** of the
root. No runtime artifact is ever written into the Git repository.

**Active PostgreSQL storage stays on Docker-managed internal volumes** (`/var/lib/postgresql/data` on named
volumes). No `D:` path is ever used as a live PostgreSQL data directory.

## 4. Preconditions (ALL must hold before any runtime step)

1. **Explicit human START-GATE.** Dan has authorized THIS execution in writing. No standing authorization
   exists; each run needs its own gate.
2. **Local, non-production Docker/PostgreSQL only.** The four compose clusters point ONLY at throwaway local
   instances — never production, shared staging, or any standing database beyond the authoritative four.
3. **Credentials by reference only.** Each cluster's admin descriptor is resolved in-memory by reference
   through the existing `EnvReferenceSecretStore` env/file convention (`localconcept/<role>/dsn@1`). No literal
   DSN is configured, no new environment variable is introduced, and no secret value is printed, persisted,
   committed, or recorded.
4. **Artifact root verified.** The approved root and its eight destinations resolve exactly (§3); the operator
   fails closed otherwise.

## 5. Operator surface (bounded)

The wrapper exposes ONLY:

```text
plan  backup  restore-validate  seed  status
```

It never exposes `apply`, `teardown`, `serve`, `activate`, `deploy`, `promote`, `production`, or `hosted`. The
standing `apply`/`teardown` remain the `b5_standing_topology.py` operator's responsibility; this wrapper invokes
only that operator's `status` surface, by subprocess, and never calls `apply` or `teardown` implicitly.

## 6. Backup (design; runtime is HELD)

- Enumerate exactly Control, ACME, ZETA, and NOVA; one custom-format `pg_dump` per database.
- Write dumps only under `03-Database-Backups`; **refuse overwrite**; record SHA-256 for every dump.
- Emit one references-only batch manifest carrying: environment class `LOCAL-CONCEPT-ONLY`, source commit,
  source tree, PostgreSQL version, database role, database name, cluster system identity, timestamp, dump
  format, dump filename, byte size, SHA-256, success/failure, references-only error detail, and posture
  `DO-NOT-ACTIVATE`.
- Credentials pass to `pg_dump` **only through the child-process environment**; no raw DSN in argv; no DSN,
  password, JWT, key, or customer data in the command line, manifest, logs, report, or evidence.

**RUNTIME — `HOLD / WAIT — DO NOT EXECUTE` (release only under the Dan START-GATE):**

```text
HOLD / WAIT — DO NOT EXECUTE
python tests/control_plane/requires_pg/b5_local_concept_ops.py backup --batch <fresh_safe_name>
```

## 7. Restore-validation (new-but-bounded; runtime is HELD)

Actual `pg_restore` **into a database** is **new** behavior in this repository (the tree previously carried only
the `pg_restore --list` readability witness). It is bounded to a **newly created disposable validation
database** whose name begins `sp2_local_restore_validation_`, created via the canonical
`PostgresProvisioningOperator` (safe-identifier guarded), and disposed in `finally`.

Sequence: approved dump → SHA-256 vs the batch manifest → `pg_restore --list` readability → create the
disposable validation database → real `pg_restore` INTO it → schema + sentinel + distinguishable-identity
verification → dispose in `finally` → assert a retained `sp2_local_restore_validation_*` count of **zero** →
write the single references-only evidence bundle **last**.

**Direct restore over `snackportal2_control_local`, `snackportal2_tenant_acme_local`,
`snackportal2_tenant_zeta_local`, `snackportal2_tenant_nova_local`, `b5_standing_alpha`, or `b5_standing_beta`
is prohibited** and is refused before any restore process is invoked.

**RUNTIME — `HOLD / WAIT — DO NOT EXECUTE` (release only under the Dan START-GATE):**

```text
HOLD / WAIT — DO NOT EXECUTE
python tests/control_plane/requires_pg/b5_local_concept_ops.py restore-validate --role <Control|ACME|ZETA|NOVA> --batch <name> --suffix <a-z0-9x8..32>
```

## 8. Synthetic seed (design; runtime is HELD)

- Deterministic, idempotent, clearly synthetic, non-sensitive, safe to rerun and remove; every identifier
  prefixed `sp2-local-concept-`.
- Minimum proof set: one Control global-directory record; independent ACME and ZETA tenant copies of that
  record; a Control→Tenant lineage soft reference with **no automatic synchronization** ("Global Record !=
  Tenant Record"); and adjacent **NOVA isolation** (read-only; never seeded).
- **The System-Primary seed is never modified** (asserted a singleton before and after; the tenant `agents`
  immutability trigger also protects it).
- Fixtures live under `06-Synthetic-Data`. Fixture-loading behavior is authored; fixtures are **neither created
  nor loaded** until the runtime START-GATE.

**RUNTIME — `HOLD / WAIT — DO NOT EXECUTE` (release only under the Dan START-GATE):**

```text
HOLD / WAIT — DO NOT EXECUTE
python tests/control_plane/requires_pg/b5_local_concept_ops.py seed
```

## 9. Status (read-only) and plan (read-only)

`status` delegates the standing-topology verification by subprocess (status-only argv), verifies the artifact
root and its eight destinations, and asserts a retained validation-database census of zero. `plan` prints the
sanitized intent (no connection, no mutation). Both are read-only, but during this STATIC stage even these are
`HOLD / WAIT — DO NOT EXECUTE` until the Dan START-GATE, because they connect to local PostgreSQL.

```text
HOLD / WAIT — DO NOT EXECUTE
python tests/control_plane/requires_pg/b5_local_concept_ops.py status
```

## 10. Disposal and STOP-on-failure

- **`restore-validate` disposal (deterministic, `finally`-guaranteed, success or failure):** drop the disposable
  validation database via the canonical identifier-guarded operator; assert a retained
  `sp2_local_restore_validation_*` count of zero. The single success-evidence bundle is written **only after**
  disposal and the zero-count assertion both succeed, so a failed run or a failed disposal can never retain a
  false-PASS record.
- **STOP-on-failure:** any checksum mismatch, unreadable dump, restore failure, verification mismatch, or
  ambiguous evidence stops the procedure; let the `finally` complete disposal; capture the redacted references-
  only output; escalate to Dan and GPT. Do not improvise recovery, do not re-run with modified assertions, and
  do not touch any non-disposable database.

## 11. Forbidden (never part of any run or recovery)

```text
executing any runtime command without an explicit human Dan START-GATE
pointing any cluster at production, shared staging, or a standing database beyond the authoritative four
embedding or applying schema DDL, a new migration order, a new composition root, or a new secret backend
introducing a new environment variable, or writing a secret/DSN into argv, a manifest, logs, or evidence
restoring over snackportal2_control_local / _tenant_acme_local / _tenant_zeta_local / _tenant_nova_local
restoring over b5_standing_alpha or b5_standing_beta
using any artifact root other than D:\Pitchsnack\SP2-Local-Concept, or the short D:\SP2-Local-Concept
using any D: path as a live PostgreSQL data directory, or writing a runtime artifact into the repository
invoking standing apply or teardown, or exposing serve/activate/deploy/promote/production/hosted
modifying the System-Primary seed, or seeding the adjacent NOVA cluster
treating any local-concept run as hosted proof, production proof, readiness, or blocker closure
```

## 12. Locked state (unchanged by this runbook and by any record built from it)

This wrapper **closes no blocker**. The live blocker census remains **7 of 9 OPEN**. Production remains **NOT
READY / DO-NOT-ACTIVATE**. This is a LOCAL-CONCEPT-ONLY capability; it does not prove a hosted or production
outcome. Only a later, separately-authorized, Dan-gated governance decision, resting on captured hosted/
production evidence, may change any blocker status or the census.
