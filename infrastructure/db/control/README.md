# db/control — Control-Database schema artifacts

Portable, dependency-free SQL templates for **control-plane-owned** tables in the **Control
Database** (the global/cross-tenant store; CLAUDE.md Multi-Database Model). This directory is
introduced by **PRD 06 B-2 (Durable Distinctness Ledger)** as the first additive Control-DB
schema artifact, authorized for **controlled non-production implementation only**.

**Independence rule (CLAUDE.md constraint 4):** these files are deployable on their own and do
**not** depend on `backend/` application code. Standard, cloud-portable PostgreSQL only (AWS RDS
/ Azure Database for PostgreSQL / Cloud SQL / self-hosted) — no provider-specific extensions.

**References only (D-14; IC-001 Global Audit Representation Rule):** no passwords, DSNs,
connection strings, raw secret values, JWT/API keys, cloud credentials, or PII appear here. The
Control-DB connection credential is resolved from the secret store at connect time (it is never
stored in a table or in these templates).

## Files (idempotent; additive)

> **Read the "Current standing state" section below before the table.** Each row's **Created, not
> applied** phrase records the posture *at the time that file was authored*, inside that file's own
> scope boundary. Several of these objects have since been applied to the retained **LOCAL standing
> Control database** by separately governed, Dan-authorized acts. The per-row wording is deliberately
> left as written — it is a frozen scope-boundary statement, not a live status field — so the current
> state is stated once, in one place, instead of being patched into fifteen cells that will drift again.

| File | Purpose | Spec anchor |
|------|---------|-------------|
| `001_distinctness_ledger.sql` | The durable, reference-only **distinctness ledger** (`control_distinctness_ledger`): the per-tenant Physical Distinctness evidence inventory the D15 readiness gate consults for tenant-vs-tenant collision detection. One latest row per tenant (inventory, not audit history). Columns mirror `DistinctnessEvidence` + `tenant_id` + `recorded_at`. | §9.2 input 8; IC-010 §P; D15-ARCH-SPEC-01 §6 |
| `002_provisioning_audit.sql` | The durable, append-only, reference-only **provisioning audit store** (`control_audit`): the audit-history table the wired adapter `postgres_store.py` already targets. Columns mirror `ControlAuditRecord` (adapter-INSERT-compatible: `id` DB-generated; `tenant_id`/`from_state`/`to_state` NULLABLE). Distinct from the `001` inventory and from IC-004/D-23 lineage. **Created, not applied.** | D-34; IC-002; IC-001; IC-010 §J; PRD 06 B-7 |
| `003_provisioning_audit_append_only.sql` | DB-level **append-only enforcement** for `control_audit`: a portable PL/pgSQL trigger rejecting UPDATE/DELETE/TRUNCATE (mirrors `lineage/002_append_only.sql`). **Created, not applied.** | D-34; PRD 06 B-7 |
| `004_control_tenants.sql` | The **tenant registry** (`control_tenants`): the wired-but-previously-DDL-less table `postgres_store.py` already targets (put/get_tenant). All-text typing (unmodified-adapter str round-trip), plus `tenant_type` (`'customer'` default / `'control_internal'`) with a partial-unique **Control Internal Tenant singleton** index. Runtime `tenant_type` plumbing deferred. **Created, not applied.** | IC-002; D-14; D-33; MCC exec-auth V2 §9.1 |
| `005_control_memberships.sql` | The **membership registry** (`control_memberships`): principal↔tenant eligibility rows the wired adapter targets (put/list_memberships). Composite PK `(principal_ref, tenant_id)`; no FK (store parity). **Created, not applied.** | D-04; D-32; MCC exec-auth V2 §9.2 |
| `006_control_federation.sql` | The **per-tenant OIDC federation config** (`control_federation`) the wired adapter targets (put/get_federation). PK `tenant_id`; jwks by reference only; no FK. **Created, not applied.** | IC-002; IC-005; MCC exec-auth V2 §9.3 |
| `007_control_directory.sql` | The **global discovery directory** (`control_directory`) the wired adapter targets — the contract-neutral Global Registry representation for the MVP (dedicated `global_startups`/`global_investors` deferred to a later Control Registry PRD). `attributes` is plain `jsonb`. Known runtime write defect documented as **MCC-AR-1** (adapter binds a plain dict; psycopg 3 needs `Jsonb(...)` — fix deferred, reads unaffected). **Created, not applied.** | D-31; IC-001; D-35-R2; MCC exec-auth V2 §9.4/§13 |
| `008_distinctness_fingerprint_unique.sql` | Storage-layer serialization of the D15 readiness gate's tenant-vs-tenant rule: two DISTINCT tenants must not share a physical-database fingerprint. Enrolled in the B5-4 standing apply order (001–009). | PRD 07D-2c; D15-ARCH-SPEC-01 §6.1; IC-010 §P |
| `009_control_tenants_cas_version.sql` | The explicit lifecycle write-version column `compare_and_swap_tenant` predicates on. Enrolled in the B5-4 standing apply order (001–009). | PRD 07D-2e; IC-002; R-2c-LWW |
| `010_routing_audit.sql` | The durable, append-only, reference-only **routing audit store** (`control_routing_audit`) for the Database Router edge. **NOT enrolled** in the standing apply order — see the DBR-AR-2D scope boundary below. | DBR-AR-2B; IC-010; IC-001 |
| `011_routing_audit_append_only.sql` | DB-level append-only enforcement for `control_routing_audit`. **NOT enrolled.** | DBR-AR-2B |
| `012_gateway_operational_audit.sql` | The durable, append-only, reference-only **Gateway operational-audit store** (`control_gateway_audit`) for the API-Gateway edge — the five durably-homed CLM action classes. **NOT enrolled**; applied only by a governed act (see below). | IC-010 §J; IC-002 (3b); D-42; Gateway Audit V1a |
| `013_gateway_operational_audit_append_only.sql` | DB-level append-only enforcement for `control_gateway_audit`. **NOT enrolled**; applied only by a governed act (see below). | Gateway Audit V1a |
| `014_import_operational_audit.sql` | The durable, append-only, reference-only **Import operational-audit store** (`control_import_audit`). **NOT enrolled, and ABSENT from every standing database** — Import is outside the controlled local MVP journey (IMPORT-A / D-3). | IC-003 "Import Audit"; IC-001; W1a |
| `015_import_operational_audit_append_only.sql` | DB-level append-only enforcement for `control_import_audit`. **NOT enrolled, and ABSENT from every standing database.** | W1a |

## Current standing state (the one live-status section; everything else here is scope boundary)

This section is the single place a reader should look for "what is actually in the retained **LOCAL**
standing Control database (`snackportal2_control_local`) right now". Nothing outside this section is a
status claim.

| Files | Enrolled in the automatic standing apply order? | Present in the LOCAL standing Control DB? | How it got there |
|---|---|---|---|
| `001`–`009` | **Yes** — `b5_standing_topology.py` `_CONTROL_DDL_ORDER` applies exactly 001–009 | Yes | The B5-4 standing-topology apply |
| `010` / `011` | **No** | Yes — **see the verification item below** | A separately governed, Dan-authorized **manual** apply under PRD DBR-AR-2D V3 (backup-first, blob-verified, each exactly once) |
| `012` / `013` | **No** | Yes — and the table carries pre-existing rows | A separately governed, Dan-authorized **manual** standing-environment apply, recorded in the CLM-SS-1 Stage-0 closure |
| `014` / `015` | **No** | **No** — `control_import_audit` is ABSENT | Never applied anywhere standing; Import is outside the controlled local MVP journey |

> **OPEN GATE-B-READINESS VERIFICATION ITEM (unresolved; do not treat the `010`/`011` presence claim
> as confirmed).** That row's provenance is a 2026-07-14 manual apply, but two artifacts describe the
> ~2026-07-21 standing event incompatibly: `backend/tests/control_plane/requires_pg/test_pg_clm_standing_auth_posture.py`
> says the standing Control **database** was replaced, while `docs/runtime/b5_activation_blockers.md`
> and `docs/runtime/b5_production_runtime_activation_gate.md` say the **subject state** was. Under the
> first reading `010`/`011` would no longer be present. **This cannot be settled read-only** — it
> needs a direct Control-database observation, which is a Gate-B act and was deliberately not
> performed. **The first Gate-B session must confirm this row by direct observation before relying on
> it**, and reconcile whichever of the three artifacts turns out to be wrong. Nothing in the current
> change depends on the answer: no code path, gate, or boundary reads this row.

Binding rules that hold in **every** window, for **every** file in this directory:

* **No runtime service ever applies DDL.** Not at startup, not on first request, not ever.
* **Enrolling any of `010`–`015` in an automatic standing apply order is forbidden in any gate.** The
  enrollment set is `001`–`009` and it is asserted structurally by four separate default-suite guards.
* **Every file remains created-not-applied for every tenant, staging, and production database.** The
  paragraph above concerns exactly one local, non-production, retained Control database.
* **Production enablement remains unauthorized.** Production is NOT READY / DO-NOT-ACTIVATE.
* A governed change to `010`–`015` must move its **blob pins in lockstep**. For `012`/`013` that is
  **six** sites, only **three** of which any automated check discovers — see
  `infrastructure/runbooks/gateway_operational_audit_live_proof.md` §1.2 for the enumeration.

## Scope boundary (PRD 06 B-2 — NOT authorized)

This template is **created, not applied**. It does **not** define and does **not** authorize:
applying the DDL to a live Control database, exercising the durable ledger against a real
cluster (that is the live-PostgreSQL exercise, **B-4**), production rollout, production secrets,
production infrastructure, IaC / migration-runner / CI/CD deployment (that is **B-3**), or the
provisioning audit store (the sink **contract** is **B-6**; the `control_audit` **table DDL** is
authored under **B-7**, created-not-applied — see below). The control-plane runtime default
remains the in-memory distinctness ledger; the durable Control-DB ledger is opt-in and exercised
live only in B-4.

## Scope boundary (MCC — Control-DB registry DDL)

`004_control_tenants.sql` – `007_control_directory.sql` are **created, not applied**. MCC authors the
missing DDL for the **existing wired** Control-store tables (the ones `postgres_store.py` already
INSERTs/SELECTs); it does **not** modify the adapter/records runtime (the `tenant_type` plumbing and the
**MCC-AR-1** directory-JSONB write fix are deferred), does **not** add cross-table FKs, does **not** author
tenant business schema / `agents` / dedicated `global_*` tables, does **not** define Control Internal Tenant
access semantics, and does **not** close B5-BLK-4. Applying + exercising the DDL live is the MCC proof
harness (`backend/tests/control_plane/requires_pg/test_pg_control_schema_mcc.py`, manual/local) or ops/IaC
(07D). Blob pins live in `tests/architecture/test_b7c1_control_audit_ddl_blob_pins.py` (in lockstep with the
harness pins).

## Scope boundary (DBR-AR-2D — disposable proof + V3 standing witnesses)

`010_routing_audit.sql` and `011_routing_audit_append_only.sql` (the DBR-AR-2B durable routing-audit
table + its append-only trigger) were **reviewed and exercised by the DBR-AR-2D disposable live proof**
(`backend/tests/control_plane/requires_pg/test_dbr_ar_2d_routing_audit_live_pg.py`): the harness pins both
files by LF-normalized git blob (`_REVIEWED_010_BLOB` / `_REVIEWED_011_BLOB`, STOP-before-connect on
mismatch), applies 010 then 011 to a proof-owned disposable database, proves the durable routing-audit
path end-to-end, and drops the proof database. Under **PRD DBR-AR-2D V3** (Dan START-GATE, 2026-07-14)
they were additionally **manually applied — backup-first, blob-verified, 010 then 011, each exactly
once — to the retained local standing Control DB ONLY** (`snackportal2_control_local`) by the standing
witness operator (`backend/tests/control_plane/requires_pg/dbr_ar_2d_standing_witnesses.py`, per the
operator runbook), which then delivered the contract §16 standing witnesses (exactly four durable
evidence rows). They remain **created, not applied for every tenant, staging, and production database**
and are deliberately **not enrolled in the B5-4 standing apply order**
(`b5_standing_topology.py` applies 001–009 only; the V3 apply was manual, never automatic).
Production enablement remains unauthorized until DBR-AR-2E.

## Scope boundary (PRD 06 B-7 — provisioning audit DDL)

`002_provisioning_audit.sql` and `003_provisioning_audit_append_only.sql` are **created, not
applied**. PRD 06 B-7 authors the missing DDL for the **existing** `control_audit` table (the one
`postgres_store.py` already writes to); it does **not** apply the DDL, wire runtime, provision a
production sink, or close B5-BLK-4. Applying + exercising the DDL against a live Control database is
the live-PostgreSQL exercise (**B-7A**), a separate later gated phase. The DDL introduces **no**
28-field parallel table and does **not** modify the adapter.
