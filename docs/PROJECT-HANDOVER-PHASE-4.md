# SnackPortal2 — Project Handover (entering Build Phase 4)

**Date:** 2026-06-06 · **Type:** Handover document (no code, no repository changes)
**Prepared at:** end of Build Phase 3 (Authentication Layer), PMO-accepted
**Audience:** the team/session that will run **Build Phase 4 — Database Router**

This document is self-contained. It summarizes the frozen architecture, what is
built, the current repository state, and exactly what Phase 4 needs to begin.

---

## 1. Architecture baseline

SnackPortal2 is a multi-tenant platform on **physical multi-database isolation**.

- **Two planes.** A single **Control Database** (tenant registry, membership, federation
  config, Global Startup/Investor Directories, operational audit) and **one physically
  separate PostgreSQL database per tenant** (tenant-owned data + lineage). The Control DB
  never holds tenant-owned data; tenant DBs never hold control-plane state.
- **Core invariant.** *One request → one active tenant → one database.* No cross-tenant
  joins or spanning queries, ever.
- **Bootstrap (D-01).** Two-phase: Bootstrap Phase 0 (control-plane, DB-free system
  identity vs. static trust anchor) → Bootstrap Phase 1 (runtime) once the Control DB is
  online, schema-checked, and the registry is available. **Authentication is separated
  from routing.**
- **Identity & auth (D-03/D-05/D-06).** Hybrid identity (internal platform identities +
  per-org OIDC federation); OIDC **stateless JWT**, no session store; the **signed tenant
  claim is authoritative** with carrier-match.
- **Isolation (D-30).** Defense-in-depth: authoritative claim + membership → single-tenant
  routing → per-tenant credentials + no cross-tenant connection reuse → audit/anomaly.
- **Portability.** Cloud-portable standard PostgreSQL only (AWS RDS / Azure / Cloud SQL /
  self-hosted). No Supabase/Lovable/provider-proprietary business logic.
- **Engineering DAG (enforced by CI/arch tests).** `shared` is a dependency leaf; no
  service imports another (transport calls only); vendor SDKs only under
  `**/adapters/providers/**`; DB drivers only under `database_router/adapters/providers/**`;
  secrets by reference only (D-14); lineage (IC-004) ≠ operational audit (IC-002).
- **Stack.** FastAPI + Python backend; PostgreSQL; React/TypeScript (Lovable) frontend.

**The MVP architecture is frozen.** Any change to frozen behavior requires a contract
amendment first (register entry → contract → code).

---

## 2. Completed phases

| Phase | Component | Governance cycle | Status |
|---|---|---|---|
| **1** | Repository Setup | R1 (Approved w/ Obs) → R2 (Fully Approved) → E1 | ✅ COMPLETE, PMO-accepted |
| **2** | Control Plane | R1 (Approved w/ Obs) → R2 (Ready) → E1 (Revised) | ✅ COMPLETE, PMO-accepted |
| **3** | Authentication Layer | R1 (Approved w/ Obs) → R2 (Ready) → E1 | ✅ COMPLETE, PMO-accepted |

Each phase executed "COMPLETE/READY WITH OBSERVATIONS"; observations were disclosures, not
defects. Every phase followed the same discipline: **review → remediation → execution →
verification → PMO acceptance**.

**Phase 2 delivered:** two-phase bootstrap, three-state readiness, schema-compatibility
(detect-only), tenant registry (RegisterTenant/GetTenantStatus/Suspend/Decommission;
**no tenant reaches Ready in Phase 2**), membership (storage-only), federation config
(storage-only), Global Discovery Platform, operational audit — all behind a `ControlStore`
port (in-memory adapter).

**Phase 3 delivered:** a two-stage authenticator — Stage 1 stateless **DB-free** JWT
validation (policy vendor-neutral; signature behind a `SignatureVerifier` port), Stage 2
tenant-context establishment via a **transport `ControlPlaneReadPort`** (no in-process
`control_plane` import) with carrier-match, membership/role, consistent denial, fail-closed,
and caching; internal identities via a platform OIDC issuer (same flow); audited.

---

## 3. Repository state

```
backend/
  shared/            built  — stdlib ports/shapes (RequestContext now has optional `role`)
  control_plane/     BUILT  — Phase 2 (frameworks + in-memory ControlStore)
  auth_router/       BUILT  — Phase 3 (two-stage authenticator)
  api_gateway/       skeleton (IMPLEMENTS_BEHAVIOR=False)
  database_router/   skeleton  ← Phase 4 target
  import_service/    skeleton (Phase 5)
  lineage_service/   skeleton (Phase 6)
  tests/architecture (6 guards) + tests/control_plane (7) + tests/auth_router (6)
infrastructure/      env templates (references only)
docs/                governance standards + Phase-1/2/3 acceptance criteria + traceability + this handover
```

- **Test status:** all suites **PASS** (architecture 6, control_plane 7, auth_router 6),
  run live via stdlib `python` (standalone-runnable; also pytest-shaped).
- **Environment caveats:** **not a git repository**; **Python 3.8** only; `pytest`, `ruff`,
  `mypy`, `import-linter`, `gitleaks`, `pyjwt`, `cryptography` are **not installed**. The
  architecture/behavior tests are pure-stdlib by design; production providers (PyJWT
  verifier, HTTP control-plane read, urllib client) compile but are **not exercised** here.
- **Declared runtime deps** (in `pyproject.toml`, not installed): `pyjwt`, `cryptography`
  (used only by `auth_router/adapters/providers/pyjwt_verifier.py`).

---

## 4. Open observations

| # | Observation | Note |
|---|---|---|
| O-1 | Live toolchain never executed | ruff/mypy/import-linter/gitleaks are configured, not run (no git; tools uninstalled). Architecture-critical checks verified via stdlib suites. |
| O-2 | First inter-service transport dependency | `auth_router → control_plane` read API is wired via port + HTTP client but exercised only with a test double — **no real Control Plane Read API endpoint exists yet**. |
| O-3 | First runtime third-party deps declared | `pyjwt`/`cryptography` confined to one provider; not installed in this env. |
| O-4 | `shared/context.RequestContext` gained optional `role` | Additive, backward-compatible; no Phase-1/2 regression (confirmed). |
| O-5 | Control-DB persistence is in-memory | `ControlStore` port with in-memory adapter; concrete PostgreSQL provider deferred. |

None are blocking; all are disclosures carried forward for Phase 4 to resolve.

---

## 5. Deferred items

- **Concrete PostgreSQL Control-DB persistence provider** (replaces the in-memory `ControlStore`).
- **Control Plane Read API endpoint** (control_plane serving federation/membership/role/
  tenant-state over transport for auth_router; currently a double).
- **DB-driver containment decision** — where the Control-DB driver lives vs. the
  `database_router/adapters/providers/**` rule.
- **Tenant lifecycle operations** `VerifyTenant` / `ActivateTenant` / `ReactivateTenant` /
  `ReassociateDatabase` — defined but raise `PhaseFourDeferred` (need tenant-DB connectivity).
- **No tenant reaches `Ready`** until Phase 4 verification exists.
- **JTI denylist storage** — `JtiDenylistPort` defined; no storage (optional/deferred).
- **Per-tenant DB credential resolution** — a new D-14 SecretStore provider (tenant creds),
  distinct from the Phase-2 trust-anchor-only resolver.
- **Post-MVP:** IC-006 (AI Gateway) — Draft; IC-007 (cross-tenant collaboration) — Deferred.
- **Standing business/legal:** D-08 — name the specific compliance floor regime + per-tenant values.
- **Tooling:** `git init` + install dev/runtime deps to run the full CI gate end-to-end.

---

## 6. Approved contracts

| ID | Title | Status |
|---|---|---|
| **IC-001** | Global Startup | 🔒 Final (amended by D-31) |
| **IC-002** | Tenant Startup | 🔒 Final |
| **IC-003** | Import | 🔒 Final |
| **IC-004** | Lineage | 🔒 Final |
| **IC-005** | Authentication Routing | 🔒 Final (amended by D-31/D-32) |
| **IC-006** | AI Gateway | 📄 Draft — post-MVP (deferred, D-02) |
| **IC-007** | Deal Collaboration / Cross-Tenant Sharing | ⏸ Deferred — future |

**Phase-4 primary contracts:** IC-005 (routing), IC-002 (tenant DB association + readiness),
IC-001 (registry from the control plane).

---

## 7. Approved ADRs (D-01 → D-32)

All resolved/approved (the MVP architecture is frozen). Compact register:

- **D-01** two-phase bootstrap · **D-02** defer AI post-MVP · **D-03** hybrid identity ·
  **D-04** 1:N membership, one active tenant/request · **D-05** OIDC stateless JWT (no session store)
- **D-06** signed tenant claim authoritative + carrier-match · **D-07** registry-authoritative
  tenant→DB mapping · **D-08** configurable multi-regime compliance (SOC2 floor) · **D-09**
  PII (ingress resolved / egress open) · **D-10** three-state global readiness
- **D-11** hybrid registry enumeration (invalidate on re-association) · **D-12** Control-DB
  compatible-range schema (fail-safe) · **D-13** lazy bounded per-tenant pools + LRU ·
  **D-14** pluggable reference-based secret store · **D-15** IaC + control-plane provisioning
- **D-16** per-tenant readiness independence (degraded = observability-only) · **D-17**
  expand/contract migrations + version-gated readiness · **D-18** pluggable source adapters
  (v1 Global + CSV/JSON) · **D-19** hybrid import execution · **D-20** import idempotency
- **D-21** batched/checkpointed/resumable imports · **D-22** minimal lineage core + envelope ·
  **D-23** defense-in-depth immutability (append-only + per-tenant hash-chaining) · **D-24**
  per-tenant retention/archival · **D-25** unified per-tenant provenance graph
- **D-30** defense-in-depth cross-tenant isolation · **D-31** Global Directories reside in
  Control DB · **D-32** role hierarchy (CONTROL, MASTER_AGENT, TENANT_ADMIN, TENANT_AGENT,
  STARTUP_USER, INVESTOR_USER) + anti-escalation · **JWT lifecycle** (under D-05)

**Open (post-MVP, IC-006 cluster):** D-26–D-29 + the D-09 egress slice.
**Phase-4-critical ADRs:** **D-07, D-11, D-13, D-14, D-16, D-17, D-30.**

---

## 8. Known risks

| ID | Risk | Severity | Mitigation / owner |
|---|---|---|---|
| R-1 | **Cross-tenant connection reuse** — a routing/pooling bug could let one request reach another tenant's DB | **High** (Phase 4 critical correctness point) | Single-tenant binding + per-tenant credentials + never-reuse guard + isolation audit (D-30/D-13); cover with explicit arch + behavior tests |
| R-2 | In-memory Control-DB store blocks multi-process deploy | Medium | Land PostgreSQL Control-DB provider + real Control Plane Read API (O-2/O-5) before separate-service topology |
| R-3 | DB-driver containment ambiguity (Control-DB driver vs. `database_router/providers` rule) | Medium | Decide containment location in P4-R1/R2; update the vendor/DB-containment arch test accordingly |
| R-4 | Per-tenant credential resolution not yet built (only trust-anchor resolver exists) | Medium | Add a D-14 SecretStore provider for tenant DB credentials; references only, resolved in-memory at connect time |
| R-5 | Atomic provenance sequencing (Phase 5 ↔ Phase 6) | Medium (later) | Lineage write path must precede tenant-data commit; co-develop Phases 5/6 |
| R-6 | Per-tenant hash-chaining serialization under concurrency | Medium (Phase 6) | Serialize chain-head writes (SERIALIZABLE/advisory lock/single-writer) |
| R-7 | Full CI gate never run end-to-end (no git/tools) | Low | `git init` + install dev deps; run ruff/mypy/import-linter/gitleaks/pytest |

No Critical or unmitigated High risks are outstanding for completed phases.

---

## 9. Phase 4 prerequisites

**Objective (Build Phase 4 — Database Router):** implement registry-authoritative resolution,
per-tenant connection management, per-tenant credentials, and enforced single-tenant binding
(IC-005/IC-002; D-07/D-13/D-14/D-16/D-17/D-30).

**Process inputs**
- Begin with **PRD-P4-R1** (readiness review) → remediation (P4-R2) → execution (P4-E1),
  per the established cadence.
- Governing docs to load: **IC-005, IC-002, IC-001**; ADRs **D-07, D-11, D-13, D-14, D-16,
  D-17, D-30**; Phase-1 Governance Standards; the Phase-2 and Phase-3 implementation reports;
  this handover.

**Technical prerequisites / first decisions**
1. **PostgreSQL Control-DB provider** behind the existing `ControlStore` port (replaces in-memory).
2. **Control Plane Read API** endpoint(s) for `auth_router` (federation/membership/role/tenant-state).
3. **DB-driver containment location** (resolve R-3) and update the arch guard.
4. **Per-tenant connection manager** — lazy, bounded, LRU; per-tenant credentials via a new
   D-14 provider; **connections never reused across tenants** (R-1).
5. **Consume the auth output** — Phase 4 takes `RequestContext{active_tenant_id, principal_ref,
   role}` from auth_router and resolves the registry-authoritative `database_association_ref`
   (D-07); route only to `Ready`, in-range tenants (D-16/D-17).
6. **Activate deferred lifecycle ops** — `VerifyTenant`/`ActivateTenant`/`ReactivateTenant`/
   `ReassociateDatabase` (now that tenant-DB connectivity exists), with D-11 cache invalidation.

**Environment setup (recommended)**
- `git init`; `pip install .[dev]` plus `pyjwt cryptography`; provision a local PostgreSQL
  (portable) for Control-DB + tenant-DB integration; then run the full CI gate
  (ruff / mypy / import-linter / gitleaks / pytest) end-to-end.

**Guardrails for Phase 4 (must not violate):** no cross-tenant joins or connection reuse; one
active tenant per request; secrets by reference only; database access only through the
Database Router; routing logic stays out of `auth_router` and `api_gateway`.

---

*End of handover. Session memory (`snackportal2-build-status`, `snackportal2-prd-review-style`)
is current through Phase 3 for continuity.*
