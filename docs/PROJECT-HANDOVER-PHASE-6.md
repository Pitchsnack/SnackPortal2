# SnackPortal2 — Project Handover (entering Build Phase 6)

**Date:** 2026-06-06 · **Type:** Handover document (no code, no repository changes)
**Prepared at:** end of Build Phase 5 (Import Service), PRD-P5-V1 = **PASS WITH OBSERVATIONS**
**Audience:** the team/session that will run **Build Phase 6 — Lineage Service**

This document is self-contained. It summarizes the frozen architecture, what is built
through Phase 5, the current repository state, and exactly what Phase 6 needs to begin.

---

## 1. Current backend architecture baseline

SnackPortal2 is a multi-tenant platform on **physical multi-database isolation**.

- **Two planes.** A single **Control Database** (tenant registry, membership, federation
  config, Global Startup/Investor Directories, operational audit) and **one physically
  separate PostgreSQL database per tenant** (tenant-owned data + lineage). The Control DB
  never holds tenant-owned data; tenant DBs never hold control-plane state.
- **Core invariant.** *One request → one active tenant → one database.* No cross-tenant
  joins or spanning queries, ever.
- **Bootstrap (D-01).** Two-phase: Bootstrap Phase 0 (control-plane, DB-free system
  identity vs. static trust anchor) → Bootstrap Phase 1 (runtime). Authentication is
  separated from routing.
- **Identity & auth (D-03/D-05/D-06).** Hybrid identity; OIDC **stateless JWT**, no session
  store; the **signed tenant claim is authoritative** with carrier-match.
- **Isolation (D-30).** Defense-in-depth: authoritative claim + membership → single-tenant
  routing → per-tenant credentials + no cross-tenant connection reuse → audit/anomaly.
- **Atomic provenance (IC-003/IC-004).** Tenant data + lineage + checkpoint commit in **one
  routed-session transaction**. Lineage is **tenant-resident**, append-only, per-tenant
  hash-chained, and **distinct from operational audit (IC-002)**.
- **Engineering DAG (enforced by arch tests).** `shared` is a dependency leaf; **no service
  imports another** (transport calls or shared-port injection only); vendor SDKs only under
  `**/adapters/providers/**`; **database drivers only under** `database_router/adapters/providers/**`
  **and** `control_plane/adapters/providers/**`; secrets by reference only (D-14).
- **In-process collaboration model (Phase 5).** Import/lineage/router run a **single tenant
  transaction in one worker process** via **shared ports** (`RoutedTenantSession`,
  `LineageEmitPort`) injected at the composition root — *not* per-statement network hops.
  Service independence is a **source-dependency** rule, satisfied by injection.
- **Portability.** Cloud-portable standard PostgreSQL only (RDS / Azure / Cloud SQL /
  self-hosted). No Supabase/Lovable/provider-proprietary logic. **The MVP architecture is
  frozen**; any change to frozen behavior requires a contract amendment first.

---

## 2. Completed phases and acceptance status

| Phase | Component | Governance cycle | Status |
|---|---|---|---|
| **1** | Repository Setup | R1 → R2 → E1 | ✅ COMPLETE + ACCEPTED |
| **2** | Control Plane | R1 → R2 → E1 (Revised) | ✅ COMPLETE + ACCEPTED |
| **3** | Authentication Layer | R1 → R2 → E1 | ✅ COMPLETE + ACCEPTED |
| **4** | Database Router | R1 → R2 → E1 → **V1 (PASS w/ Obs)** | ✅ COMPLETE + ACCEPTED |
| **5** | Import Service (+ Phase-6 lineage write-path slice) | R1 → R2 → E1 → **V1 (PASS w/ Obs)** | ✅ COMPLETE + ACCEPTED |

Each phase followed the discipline **review (Rn) → remediation → execution (En) →
independent verification (Vn) → PMO acceptance**. No Critical or High findings outstanding.

---

## 3. Approved contracts and ADRs

| ID | Title | Status |
|---|---|---|
| IC-001 | Global Startup | 🔒 Final (amended by D-31) |
| IC-002 | Tenant Startup | 🔒 Final |
| IC-003 | Import | 🔒 Final |
| **IC-004** | **Lineage** | 🔒 **Final — Phase 6 primary contract** |
| IC-005 | Authentication Routing | 🔒 Final (amended by D-31/D-32) |
| IC-006 | AI Gateway | 📄 Draft — post-MVP (D-02) |
| IC-007 | Deal Collaboration / Cross-Tenant Sharing | ⏸ Deferred |

**ADRs D-01 → D-32 Approved** (MVP architecture frozen). **Phase-6-critical ADRs:**
**D-22** (minimum lineage record), **D-23** (append-only: DB-level + per-tenant
hash-chaining), **D-24** (retention/archival within a compliance floor/ceiling;
tombstone expiry), **D-25** (unified per-tenant provenance graph; segmentable chain),
**D-08** (compliance floor + per-tenant values — standing business/legal action),
**D-16** (per-tenant independence), **D-17** (lineage schema migration/version-gating),
**D-14** (keyed-hash key by reference), **D-02** (AI-ready, no AI built).

---

## 4. Current repository state

```
backend/
  shared/            BUILT  — ports/shapes incl. session.py (RoutedTenantSession/Provider/Lane),
                              lineage.py (LineageIntent/LineageEmitPort), secrets, context, errors,
                              audit, queue, health
  control_plane/     BUILT  — Phase 2 + Phase 4 completion (lifecycle, read_api incl. Global Directory,
                              Postgres ControlStore + verification probe providers [not run])
  auth_router/       BUILT  — Phase 3
  database_router/   BUILT  — Phase 4 (+ Phase 5 additive: session_provider.py, lane/bulk pool,
                              TenantConnection.execute/query)
  import_service/    BUILT  — Phase 5 (coordinator, validation floor, source adapters, directory client)
  lineage_service/   BUILT (WRITE-PATH SLICE ONLY) — emit.py: append + per-tenant hash-chain (D-22/D-23)
  api_gateway/       skeleton (IMPLEMENTS_BEHAVIOR=False)
  tests/             architecture (8) + control_plane (10) + auth_router (6) + database_router (9)
                     + import_service (6) + lineage_service (1)
infrastructure/      env templates (references only)
docs/                governance standards, ADR register, roadmap, Phase-1..5 acceptance criteria,
                     handovers (this = Phase 6)
```

- **Test status:** **40 test files (~136 tests) — ALL GREEN**, run live via stdlib `python`
  (standalone-runnable; also pytest-shaped). Includes real-HTTP loopback tests for the
  control-plane routing read and Global Directory read.
- **Environment caveats:** **not a git repository**; **Python 3.8** only; `pytest`, `ruff`,
  `mypy`, `import-linter`, `gitleaks`, `pyjwt`, `cryptography`, `psycopg` are **not
  installed**. Production providers (PyJWT verifier, HTTP clients, **psycopg ControlStore /
  probe / connection factory / `PgRoutedSession`**) compile but are exercised only against a
  live database — the stdlib suites use in-memory doubles.

---

## 5. Key implemented seams and ports (what Phase 6 consumes)

**shared/ (vendor-neutral, leaf):**
- `session.py` — `Lane` (INTERACTIVE/BULK), `RoutedTenantSession` (`begin/commit/rollback/close`
  + tabular vocab `upsert/append/get/latest`), `RoutedSessionProvider.open_session(...)`.
  **Phase 6 reads/queries lineage through this same session** (the read path).
- `lineage.py` — `LineageIntent` (D-22 core, references only), `LineageEmitPort.emit(session, intent)`.
- `secrets.py` (`SecretStore`/`SecretRef`/`SecretValue`), `context.py` (`RequestContext`),
  `errors.py` (`DenialReason`), `audit.py` (`OperationalAudit`), `queue.py` (`Queue`/`JobEnvelope`),
  `health.py` (readiness shapes).

**lineage_service/ (write-path slice — extend, do not rewrite):**
- `emit.py` `LineageEmit.emit(session, intent)` → appends to the `lineage` table with a
  per-tenant HMAC-SHA256 `integrity_marker` chained on `prev_marker`/`seq`; chain key resolved
  from a D-14 `SecretRef` (`lineage/{tenant}/chainkey`). **Owns hash-chaining (D-23 detective).**

**database_router/ (the only tenant-DB accessor):**
- `session_provider.py` `PgRoutedSession`/`PgRoutedSessionProvider` map the tabular vocab to
  **standard parameterized SQL**; bulk/interactive capacity lanes (D-13). `TenantConnection`
  exposes `execute/query` + caller-controlled transactions.

**control_plane/:** `ControlStore` port, `TenantDatabaseProbe`, `ControlPlaneReadService` +
dispatcher + HTTP (tenant-state/routing-view/membership/role/**Global Directory**).

**Tenant-DB table vocabulary already written by the import path (logical schema):**
`tenant_copy`, `import_job`, `import_checkpoint`, `import_idempotency`, **`lineage`**
(fields: `lineage_id, seq, event_type, occurred_at, actor_ref, source_ref, target_ref,
operation, schema_version, derivation_ref, parent_lineage_ref, correlation_id,
integrity_marker, prev_marker`).

---

## 6. Open observations carried forward (from PRD-P5-V1)

| # | Observation | Severity |
|---|---|---|
| V-OBS-1 | **DB-level append-only enforcement (D-23 preventive layer 1)** + tenant-DB DDL/migrations for the lineage/import tables are **not delivered** (migrations out of scope in Phase 5). The cryptographic hash-chain (detective layer 2) **is** implemented and tested. Real path assumes tables exist. | **Medium** (Phase-6 / schema-provisioning item) |
| V-OBS-2 | Import `applied`/`noop` status counts are **per-run** (a resumed import undercounts prior batches); data + lineage chain remain correct/contiguous. | Low |
| V-OBS-3 | An unsupported-source / early failure can leave a dangling `in_progress` job/idempotency row; **no tenant data written**, provenance intact. | Info |
| V-OBS-4 | Operation-key idempotency under truly concurrent submission relies on a tenant-DB **unique constraint** (part of the deferred DDL). | Info |
| V-OBS-5 | `PgRoutedSession`/psycopg paths exercised only vs. a live PostgreSQL; live CI tooling uninstalled (carried **R-P4-14**); D-09 minimize/tokenize values gated by standing **D-08**. | Low/carried |

---

## 7. Deferred items

- **Full Build Phase 6** (this is the next build): lineage **query/read API**, **search**,
  **retention/archival (D-24)**, **chain verification**, and **provenance-graph reads (D-25)**.
- **Tenant-DB lineage/import schema + DB-level append-only constraint** (D-23 layer 1;
  privilege separation + reject UPDATE/DELETE) — **V-OBS-1**.
- **D-08** standing business/legal action — name the compliance floor regime + per-tenant
  values (retention floor/ceiling, residency); enables the D-09 minimize/tokenize layer and
  D-24 retention values.
- **Concrete PostgreSQL exercise** — stand up a portable PostgreSQL and run the psycopg
  providers + `PgRoutedSession` end-to-end (currently in-memory-double-tested only).
- **JTI denylist storage** (optional, IC-005), **IC-006 AI** (post-MVP), **IC-007**
  (cross-tenant) — all out of MVP.
- **Tooling/CI:** `git init` + install dev/runtime deps; run ruff/mypy/import-linter/gitleaks/
  pytest end-to-end (carried **R-P4-14 / O-1**).

---

## 8. Known risks

| ID | Risk | Severity | Mitigation / owner |
|---|---|---|---|
| R-A | **Append-only preventive layer absent** until tenant-DB DDL lands (V-OBS-1) — lineage mutability not DB-enforced in the real path | Medium | Land the append-only GRANT/constraint with the Phase-6 lineage schema; detective hash-chain already alarms tampering |
| R-B | **Per-tenant chain-head serialization under concurrency** — concurrent appends could race the `seq`/`prev_marker` head | Medium (Phase 6) | Serialize chain-head writes (SERIALIZABLE / advisory lock / single-writer per tenant); design in PRD-P6-R1 |
| R-C | **Retention/erasure vs. append-only** (D-24 + right-to-erasure) — must reconcile expiry with immutability | Medium (Phase 6) | Tombstone references + crypto-erase of referents; retain non-personal provenance + chain verifiability; policy-driven expiry is the only sanctioned removal (audited) |
| R-D | Cross-tenant connection reuse (Phase-4 critical point) | Low (verified) | Per-tenant keyed pools + no-reuse guard + physical separation; P4-V1 verified |
| R-E | Full CI gate never run end-to-end (no git/tools); psycopg paths not exercised | Low | `git init` + install deps; provision local PostgreSQL |

No Critical or unmitigated High risks outstanding.

---

## 9. Phase 6 prerequisites

**Objective (Build Phase 6 — Lineage Service):** complete IC-004 on top of the existing
write-path slice — **tenant-resident lineage query/read** (access-controlled, IC-005),
**DB-level append-only enforcement (D-23)**, **retention/archival (D-24)**, **unified
per-tenant provenance graph reads (D-25)**, and **chain verification** — without breaking
the Phase-5 atomic write path.

**Process inputs**
- Begin with **PRD-P6-R1** (readiness review) → remediation (P6-R2) → execution (P6-E1) →
  independent verification (P6-V1), per the established cadence.
- Governing docs to load: **IC-004 (primary), IC-002, IC-005, IC-003**; ADRs
  **D-22, D-23, D-24, D-25, D-08, D-16, D-17, D-14, D-02**; Phase-1 Governance Standards;
  the PRD-P5-R2 standards (shared session/lineage ports) and PRD-P5-V1 report.

**Technical prerequisites / first decisions**
1. **Lineage read path** — query/read lineage **through the same `RoutedTenantSession`**
   (tenant-scoped, IC-005 access control; no new DB accessor); define the read DTOs +
   pagination; never cross tenants.
2. **DB-level append-only (D-23 layer 1)** + the **tenant-DB lineage/import schema/migrations**
   (closes V-OBS-1; expand/contract + version-gated readiness, D-17).
3. **Chain verification** — recompute/verify the per-tenant hash-chain; alarm + operationally
   audit (IC-002) detected breaks; resolve chain-head **concurrency serialization** (R-B).
4. **Retention/archival (D-24)** — per-tenant floor/ceiling (D-08 values), segmented verifiable
   archival, tombstone/crypto-erase expiry reconciled with append-only (R-C); expiry audited.
5. **Provenance graph (D-25)** — `parent_lineage_ref` traversal within one tenant; AI-ready
   (`event_type=ai-derivation` reserved; no AI built).

**Guardrails (must not violate):** lineage stays tenant-resident and per-tenant; reads are
tenant-scoped and authenticated; no cross-tenant provenance joins (explicit audited
per-tenant control-plane reads only if ever needed); import write path (Phase 5) must remain
green; no service-to-service source imports — extend via shared ports.

---

## 10. Recommended next artifact

**PRD-P6-R1 — Build Phase 6 Lineage Service Review** (review only; no implementation). It
should validate the Phase-6 design envelope against IC-004 + D-22/23/24/25/08/16/17, confirm
the read path reuses the routed session, and scope V-OBS-1 (append-only DDL) and R-B/R-C
(chain concurrency, retention/erasure) as in-scope.

---

## 11. Files/docs the next Claude session should read first

**Contracts (read first):** `contracts/IC-004-Lineage-Contract.md` (primary), then
`IC-002`, `IC-005`, `IC-003`, `IC-001`.
**Governance/decisions:** `docs/Architecture-Decision-Register.md` (esp. D-22–D-25, D-08, D-14,
D-16, D-17), `docs/D-08-D22-D23-D24-D25-Lineage-Decision-Pack.md`,
`docs/Backend-Implementation-Roadmap.md` (Phase 6 + the Phase 5↔6 sequencing note),
`docs/Phase-1-Governance-Standards.md`, `docs/Phase-5-Acceptance-Criteria.md`, **this handover**.
**Source seams (read before designing):** `backend/shared/session.py`, `backend/shared/lineage.py`,
`backend/lineage_service/emit.py`, `backend/control_plane/read_api.py`,
`backend/import_service/service.py`, `backend/tests/architecture/test_phase5_import_service.py`.
**Project guide:** `CLAUDE.md`. **Session memory:** `snackportal2-build-status` and
`snackportal2-prd-review-style` (current through Phase 5).

---

## 12. Explicit warning

> **Do NOT revisit or modify Phases 1–5 unless a conflict is discovered.** Phases 1–5 are
> COMPLETE + ACCEPTED and treated as the source of truth. Phase 6 is **additive**: extend the
> lineage write-path slice with read/verify/retention/graph capabilities via the existing
> shared ports. Any required change to frozen Phase 1–5 behavior or to a Final contract must
> first be raised as a **contract/governance amendment** (register entry → contract → code),
> not made inline. The shared `RoutedTenantSession`/`LineageEmitPort` and the tenant-DB
> `lineage` table shape are the stable seams; do not re-architect them.

---

*End of handover. Build Phase 5 is COMPLETE + ACCEPTED (PRD-P5-V1 = PASS WITH OBSERVATIONS).
Next: PRD-P6-R1 — Build Phase 6 Lineage Service Review. Session memory is current through
Phase 5 for continuity.*
