# PRD 06 B-3A — Local Docker Multi-Database Test Environment (design)

**Phase:** PRD 06 B-3A — controlled non-production, local Docker proof. **Baseline:** `origin/main @ a5e9777`.
**Status:** local fixture + harness extension only. No DDL applied; no runtime activation; no cloud/production; the
B-3 cloud-portable IaC is unchanged and remains Docker-free.

## 1. What B-3A proves beyond B-4

B-4 already proved (live, against real PostgreSQL): durable distinctness ledger record/read, cross-instance/restart
durability, and the full fail-closed matrix (missing table RAISES, not `{}`). **B-3A adds** a reproducible
**multi-instance, multi-tenant topology** fixture and exercises the existing harness across the fleet:

```
four physically separate PostgreSQL clusters → four distinct system_identifiers
one Control DB + three tenant DBs, each its own database/credential-reference/identity
one-request→one-DB demonstrated at the adapter/registry level (NOT the live runtime router)
fail-closed when a target is missing
```

It does **not** re-prove B-4 and does **not** activate runtime (the live runtime Database Router/Control-Plane is B-5).

## 2. Why four Docker services, not one service with four databases

Physical distinctness verification (DV-C1) keys on the PostgreSQL **`system_identifier`** — a per-**cluster** value.

```
Four separate clusters (this design)   → four DISTINCT system_identifiers → proves CLUSTER-level physical separation.
One cluster with four databases        → ONE shared system_identifier (distinct datname:oid only) → proves database-
                                         level separation only; WEAKER, and NOT representative of MVP isolation.
```

B-3A therefore uses four separate containers/clusters. A cloned PostgreSQL `TEMPLATE` database is **not** used (it
would risk blurring physical distinctness and provider portability).

## 3. How B-3A supports the Physical Multi-Database MVP

```
Control DB physically separate from every Tenant DB (IC-010 §O).
One physical database per tenant; no shared DB, no tenant_id-isolation substitute.
Each tenant DB selected via a distinct connection REFERENCE (D-07 registry-authoritative; D-14 references only).
The fixture's DSNs feed the existing requires_pg harness; the harness asserts distinctness + fail-closed.
```

## 4. Why B-3A does not activate runtime

`backend/control_plane/main.py` keeps its `NotImplementedError` deferral; the default ledger is in-memory; the durable
/ real adapters are opt-in. B-3A proves distinctness **adapter-direct / via the harness pointed at the local
instances** — exactly as B-4 exercised the ledger adapter. Runtime activation (flipping `main.py` wiring) is **B-5**.

## 5. Why B-3A does not replace the B-3 cloud-portable IaC

B-3 established a Docker-free, vendor-neutral cloud-portable IaC substrate (`infrastructure/iac/**`). B-3A's Docker
fixture is a **local test convenience only** — never the production path, never the portability mechanism, never a
dependency of the cloud-portable IaC or the backend application (CLAUDE.md #4). The two are separate trees
(`infrastructure/docker/**` vs `infrastructure/iac/**`).

## 6. Driver containment

The harness extension obtains the PostgreSQL driver via `importlib` (mirroring
`backend/tests/control_plane/requires_pg/_pg.py`), never a static `import psycopg`. This keeps it within the Driver
Containment Standard enforced by `tests/architecture/test_vendor_and_db_containment.py` (which permits `psycopg` only
under `database_router/adapters/providers/` and `control_plane/adapters/providers/`).

## 7. Secret hygiene (D-14)

No password value appears in any committed file. `docker-compose.local.yml` interpolates `POSTGRES_PASSWORD` from an
untracked `.env.local`; the committed `.env.local.template` carries placeholders and `*_REF=ref:local/...` references
only. The four `SP2_B3A_*_DSN` values exist only in the local shell at run time; the harness prints database names and
`system_identifier`s, never DSNs or passwords.

## 8. How a future B-5 may consume this proof

B-5 (production runtime activation) is separate and governed. It may reference B-3A's topology proof as evidence that
the Physical Multi-Database substrate behaves as required, but B-5 must run its own phrase-gated process; B-3A grants
it nothing.

## 9. DDL

B-3A applies **no DDL**. The reviewed, governed DDL under `infrastructure/db/**` (control ledger blob `30956ff1e8`;
seven pinned files — see `b3_ddl_target_mapping.md`) is untouched. Local DDL smoke testing is a later, separately-gated
phase.

## 10. Governing references

IC-002 (tenant lifecycle/readiness) · IC-010 §O (physical multi-DB mandatory) / §P (distinctness hook) / §H,§M (router
boundary) / §I (gateway sole ingress) · D-07 (registry-authoritative) · D-14 (secret references) · D-15 (provisioning
ownership) · D-17 (schema/version range) · D-30 (cross-tenant isolation) · CLAUDE.md #4 (infra independent of backend).
