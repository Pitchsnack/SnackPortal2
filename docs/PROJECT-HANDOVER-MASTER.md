# SnackPortal2 — PROJECT HANDOVER (MASTER)

**Type:** Authoritative, self-contained project handover · **Scope:** entire SnackPortal2 backend program (Phases 1–6)
**Status of this doc:** Single Source of Truth (see §22). Documentation only — no code.
**Prepared:** end of Build Phase 6 (Lineage Service), after **PRD-P6-V1 = PASS WITH OBSERVATIONS** (live-PostgreSQL Objective-N executed on PG 16.14).
**Audience:** a brand-new Claude session, a new ChatGPT session, a new developer, or a future architecture review — with **no dependency on prior chat history.**

---

## 1. Executive Summary

**Project purpose.** SnackPortal2 is a multi-tenant SaaS platform for startup↔investor discovery and deal workflows ("PitchSnack"). The backend is a **physically isolated multi-database** platform: a single **Control Database** (global/control-plane state + a Global Discovery Platform of Startup/Investor directories) and **one physically separate PostgreSQL database per tenant** (tenant-owned data + per-tenant lineage). The frontend is **Lovable-generated React/TypeScript**; the backend is **FastAPI/Python** (Claude Code is the backend implementation owner — Lovable does not implement the backend).

**Current project maturity.** Architecture is **FROZEN** for MVP. The **backend platform foundation is built and verified through Build Phase 6.** Contracts IC-001…IC-005 are **Final**; ADRs **D-01…D-32 Approved**. AI (IC-006) is deferred post-MVP; cross-tenant collaboration (IC-007) is deferred.

**Current implementation status.** Six build phases implemented and verified:
Repository Setup → Control Plane → Authentication Layer → Database Router → Import Service → **Lineage Service**. The lineage write-path slice co-developed with Phase 5; the full Lineage Service (query / search / verification / provenance-graph / retention & archival framework / DB-level append-only enforcement) was implemented in Phase 6 and independently verified.

**Current accepted baseline.** **Phases 1–6 are COMPLETE + ACCEPTED.** Phase 6 (Lineage Service) was IMPLEMENTED (PRD-P6-E1) and INDEPENDENTLY VERIFIED (PRD-P6-V1 = PASS WITH OBSERVATIONS); **PMO ACCEPTED the live-PostgreSQL Objective-N evidence (PG 16.14) and Phase 6.** Test suite: **52 test files (48 pure-stdlib green + 4 live-PostgreSQL), 170 test functions, 0 failures.** Live PostgreSQL 16.14 evidence for the append-only / uniqueness / advisory-lock / recursive-traversal / privilege guarantees was executed and passed. (See §10, §11, §18.)

---

## 2. Program Status

Governance cadence per phase: **Rn (readiness review) → remediation → En (execution) → Vn (independent verification) → PMO acceptance.**

| Phase | Component | Review (Rn) | Remediation | Execution (En) | Verification (Vn) | Acceptance |
|---|---|---|---|---|---|---|
| **1** | Repository Setup | R1, R2 (Approved) | applied | E1 done | (folded into E1) | ✅ COMPLETE + ACCEPTED |
| **2** | Control Plane | R1, R2 | applied | E1 (Revised) | (folded) | ✅ COMPLETE + ACCEPTED |
| **3** | Authentication Layer | R1, R2 | applied | E1 done | (folded) | ✅ COMPLETE + ACCEPTED |
| **4** | Database Router (+ CP completion) | R1 (Approved w/ Obs), R2 (Ready w/ Obs) | applied | E1 done | **V1 = PASS w/ Obs** | ✅ COMPLETE + ACCEPTED |
| **5** | Import Service (+ Phase-6 lineage write-path slice) | R1 (Approved w/ Obs), R2 (Ready w/ Obs) | applied | E1 done | **V1 = PASS w/ Obs** | ✅ COMPLETE + ACCEPTED |
| **6** | Lineage Service | **R1 = APPROVED WITH OBSERVATIONS** (11 obs P6-OBS-1..11) | **R2 = READY FOR EXECUTION WITH OBSERVATIONS** (all 11 closed; no contract amendment) | **E1 = COMPLETE WITH OBSERVATIONS** | **V1 = PASS WITH OBSERVATIONS** (live-PG Objective-N executed + PMO-accepted) | ✅ **COMPLETE + ACCEPTED** |

No Critical or High findings outstanding in any phase.

---

## 3. Approved Architecture

### 3.1 Overall architecture
Physical multi-database isolation. **Core invariant: one request → one active tenant → one database.** No cross-tenant joins or spanning queries, ever. Two planes:
- **Control Plane / Control Database** — tenant registry, membership/role registry, OIDC federation config, three-state global readiness, Global Discovery Platform (Global Startup & Investor Directories), operational audit. **Never holds tenant-owned data.**
- **Tenant Databases** — one physically separate PostgreSQL DB per tenant: tenant-owned copies + per-tenant lineage + import bookkeeping. **Never holds control-plane state; never shared.**

### 3.2 Service boundaries
| Service | Owns | Does NOT own |
|---|---|---|
| `api_gateway` | request entry, validation, correlation IDs, rate limiting, audit initiation (skeleton: `IMPLEMENTS_BEHAVIOR=False`) | business logic, routing, DB access |
| `auth_router` | OIDC stateless JWT validation, tenant-context resolution (signed claim authoritative + carrier-match), membership/role surfacing, auth audit | DB access, routing logic, permission matrix |
| `database_router` | registry-authoritative routing, per-tenant pooling, per-tenant credential resolution, single-tenant binding enforcement, routed sessions (write + read seams) | auth, import, lineage business logic |
| `control_plane` | two-phase bootstrap, registry, readiness, schema-compat, membership/federation, Global Directory, provisioning workflow, verification probe, operational audit | tenant-data access, auth runtime, routing logic |
| `import_service` | import coordination/idempotency/checkpointing/validation/source adapters, atomic provenance orchestration, import audit | auth, authz, routing, credential resolution, lineage persistence/hash-chaining |
| `lineage_service` | lineage persistence, query, search, verification, provenance-graph traversal, retention/archival framework, operational audit for lineage events | auth, authz, routing, import coordination/execution, synchronization, business ownership |
| `shared` | vendor-neutral ports/shapes (leaf, pure stdlib) | any service import; any vendor SDK |

### 3.3 Dependency DAG (enforced by architecture tests)
```
                         ┌─────────────┐
                         │   shared    │   (leaf: stdlib only; imports NO service)
                         └─────────────┘
              ▲      ▲       ▲       ▲        ▲        ▲
              │      │       │       │        │        │   (each service imports shared only)
   ┌──────────┴┐ ┌───┴────┐ ┌┴──────────┐ ┌──┴───────┐ ┌┴────────────┐ ┌┴──────────────┐
   │api_gateway│ │auth_   │ │database_  │ │control_  │ │import_      │ │lineage_       │
   │           │ │router  │ │router     │ │plane     │ │service      │ │service        │
   └───────────┘ └────────┘ └───────────┘ └──────────┘ └─────────────┘ └───────────────┘
```
**Rules:** No service imports another service (collaboration is **transport calls** over the network, or **shared-port injection** at a composition root). Vendor SDKs only under `**/adapters/providers/**`. Database drivers only under `database_router/adapters/providers/**` and `control_plane/adapters/providers/**`. Secrets by reference only (D-14). No import cycles.

### 3.4 Request flow (Phase 1 runtime)
```
Client ──HTTP──> API Gateway ──> Auth Router ──> Database Router ──> Tenant DB (or Control DB)
                  (validate,      (OIDC JWT      (registry-auth     (one bound connection,
                   correlation,    validate;      resolve; readiness  per-tenant credentials,
                   rate-limit)     signed tenant   + schema gating;    never reused cross-tenant)
                                   claim auth.;    single-tenant bind)
                                   carrier-match)
        Services (import/lineage) run on the routed session injected at the composition root.
```

### 3.5 Authentication flow (IC-005, D-01/D-03/D-05/D-06/D-30)
```
Bootstrap Phase 0 (pre-Control-DB):
  system identity ──verify vs static trust anchor (NO DB lookup)──> control-plane ops only
  (all tenant-scoped requests DENIED; system identity can never resolve a tenant DB)

Bootstrap Phase 1 (runtime, after Control DB online + schema-checked + routing metadata loaded):
  request + JWT ──> [validate iss/aud/exp/kid; reject alg-confusion; DB-free] 
               ──> [signed tenant claim = source of truth]
               ──> [carrier-match: subdomain/header MUST match claim, else 403]
               ──> [membership check (D-04): principal is a member of the active tenant]
               ──> RequestContext{ active_tenant_id, principal_ref, role } (no token/secret)
```

### 3.6 Routing flow (IC-005, D-07/D-11/D-13/D-14/D-16/D-17/D-30)
```
RequestContext ──> determine target:
   active_tenant present ──> TENANT route
   no tenant + role=CONTROL ──> CONTROL route (Control DB)
   no tenant + not CONTROL ──> 403
TENANT route ──> RoutingResolver (registry-authoritative, TTL+version cache, invalidate on re-assoc)
            ──> readiness gate (only Ready) + schema-version gate (in supported range)
            ──> ConnectionPoolManager (lazy bounded per-(tenant,assoc_version) pools, LRU)
            ──> resolve per-tenant credential via SecretStore at connect time (D-14)
            ──> bind ONE TenantConnection; verify conn.tenant_id == active tenant (else anomaly+deny)
            ──> RouteResult{connection, lane}; release() returns it to its lane pool
Lanes: INTERACTIVE (default reads) | BULK (import + heavy workloads) — separate bounded capacity (D-13)
```

### 3.7 Import flow (IC-003, D-18..D-21, D-09 ingress)
```
StartImport(req) ──> open BULK routed session (single active tenant)
  begin job (idempotency: operation_key; replay completed; resume incomplete)   [tenant-resident]
  collect from source adapter (GlobalDirectory via transport read | CSV | JSON)  [D-18]
  validate + sanitize + PII-classify each record (mandatory floor)               [D-09]
  for each batch:  BEGIN
     upsert tenant copy by natural key (idempotent)                              [D-20]
     lineage_service.emit(session, intent)  ← same transaction                   [IC-004 atomic provenance]
     append checkpoint
     COMMIT  (data + lineage + checkpoint commit/rollback TOGETHER)              [D-21]
  finalize job; operational audit Requested/Started/Completed/Failed/Resumed (≠ lineage)
```

### 3.8 Lineage flow (IC-004, D-22..D-25, D-08, D-14)
```
WRITE (emit, on the caller's routed session):
  [optional lock_chain()] ──> read per-tenant chain head (latest seq) ──> seq+1, prev_marker, segment_id
  build D-22 core record (references only) ──> integrity_marker = HMAC(chain_key, canonical(record, prev_marker))
  append (INSERT-only); LineageWritten operational audit
  chain_key = D-14 SecretRef (lineage/{tenant}/chainkey) — never stored in lineage

READ (tenant-scoped, INTERACTIVE lane, injected LineageReadSession):
  query: get-by-id / by target_ref / by derivation_ref / events  (keyset pagination by seq)
  search: equality filters + pagination
  verify: recompute markers via single-source canonicalizer; check prev_marker linkage + seq contiguity
          ──> VerificationReport (hashes/seq/ids only); LineageVerified | ChainBroken (alarm) audit
  graph: parent_lineage_ref ancestor/descendant traversal (recursive CTE; depth/node bounds)
  retention: per-tenant policy (Control-DB registry); SAFE DEFAULT = retain-all; expiry DISABLED until D-08
  segmentation: read-only segment summaries + continuity; ArchivePrepared audit
Append-only enforced defense-in-depth: DB trigger+privilege (preventive) + hash-chain (detective).
```

---

## 4. Approved Contracts

| ID | Title | Purpose | Scope | Status | Implemented in |
|---|---|---|---|---|---|
| **IC-001** | Global Startup | Bring up Control DB, gateway, auth router, DB router into known-good state; two-phase bootstrap; three-state global readiness; Control-DB schema compat; Global Discovery Platform residency | Cold-start sequence, readiness signaling, registry discovery handoff, directory hosting | 🔒 **Final** (amended by D-31) | Phase 2 |
| **IC-002** | Tenant Startup | Register a tenant, associate its physical DB, verify availability + schema, expose readiness routing consumes; lifecycle state machine; per-tenant federation config | Registration, lifecycle, readiness, org-mapping, DB association (by reference), audit | 🔒 **Final** | Phase 2 (registry) + Phase 4 (verify/activate/reassociate lifecycle) |
| **IC-003** | Import | Copy a Global record (or external source) into a tenant DB as a tenant-owned copy; one-directional, never sync; emit lineage; operational audit | Global→tenant copy, auth/readiness preconditions, lineage handoff, failure/idempotency | 🔒 **Final** | Phase 5 |
| **IC-004** | Lineage | Capture/reference/query/retain provenance of tenant data, per-tenant, append-only, hash-chained, distinct from operational audit; AI-ready | Min record, references, actor/tenant capture, immutability, retention, access control, isolation | 🔒 **Final** (Phase-6 primary) | Phase 6 (write slice in Phase 5) |
| **IC-005** | Authentication Routing | Authenticate requests, establish tenant context, route to Control vs exactly one tenant DB; two-phase model; role hierarchy; defense-in-depth isolation | AuthN mechanism, tenant carriage, routing decision, denial semantics, JWT lifecycle, roles | 🔒 **Final** (amended by D-31/D-32) | Phase 3 (auth) + Phase 4 (routing) |
| IC-006 | AI Gateway | AI-assisted features | — | 📄 **Draft — post-MVP (D-02)** | Not built (lineage/schema kept AI-ready) |
| IC-007 | Deal Collaboration / Cross-Tenant Sharing | Cross-tenant introductions/sharing | — | ⏸ **Deferred** | Not built |

---

## 5. Approved ADR Register (D-01 … D-32)

All Approved; MVP architecture frozen. (Full rationale: `docs/Architecture-Decision-Register.md` + the decision-pack docs.)

| ID | Decision summary | Status | Impact (contracts) |
|---|---|---|---|
| **D-01** | Bootstrap cycle: **A+B** two-phase bootstrap — control-plane system identity verified vs static trust anchor (no DB lookup) → runtime after Control DB online. AuthN separated from routing. | ✅ | IC-001, IC-005 |
| **D-02** | Defer AI (IC-006) to post-MVP; keep IC-004 lineage + tenant schema **AI-ready**. | ✅ | IC-006 (deferred); IC-004, IC-002 |
| **D-03** | Hybrid identity: internal platform identities + OIDC federation for external orgs. | ✅ | IC-005; IC-002 |
| **D-04** | 1:N membership, **exactly one active tenant per request**; concurrent multi-tenant access prohibited. | ✅ | IC-005; IC-002 |
| **D-05** | OIDC + **stateless JWT** validation; no session store; DB-free validation. | ✅ | IC-005 |
| **D-06** | Tenant carried as **authoritative signed JWT claim** + carrier-match (subdomain/header must match). | ✅ | IC-005; IC-002 |
| **D-07** | **Registry-authoritative** tenant→DB mapping; cached, invalidated on re-association; descriptor is a secret-ref. | ✅ | IC-002; IC-005 |
| **D-08** | **Configurable multi-regime** compliance: SOC 2-style integrity floor + per-tenant retention/residency. GDPR erasure via reference-only + referent/crypto-erase. **Values are a standing business/legal action.** | ✅ (architecture) | IC-004; IC-003 |
| **D-09** | PII handling **split**: ingress resolved (validate + sanitize + classify floor); AI-egress open (IC-006). | ⏳ ingress ✅ / egress open | IC-003; IC-006 |
| **D-10** | **Three-state** global readiness (ready/degraded/not-ready); degraded is observability-only. | ✅ | IC-001 |
| **D-11** | Hybrid registry enumeration: warm working set + lazy load + bg refresh; ready = registry reachable, not fully enumerated. | ✅ | IC-001; IC-005 |
| **D-12** | Control-DB schema: **compatible-range** (expand/contract); out-of-range → global not-ready (fail-safe). | ✅ | IC-001 |
| **D-13** | **Lazy bounded per-tenant pools + LRU**; portable transaction pooler as future scale layer; connections never reused across tenants. | ✅ | IC-002; IC-005; IC-003 |
| **D-14** | **Pluggable reference-based secret abstraction**; descriptors are `{store_ref, version}`; values never in DTOs/logs/responses/contracts. | ✅ | IC-002; IC-005; IC-003 |
| **D-15** | Tenant provisioning: **IaC + automated, audited control-plane workflow**; manual runbook = break-glass only. | ✅ | IC-002; infrastructure |
| **D-16** | **Per-tenant readiness independence**; degraded never denies healthy tenants; global not-ready only on shared-dependency failure. | ✅ | IC-002; IC-005; IC-003 |
| **D-17** | **Expand/contract rolling migrations** per tenant + **version-gated readiness**. | ✅ | IC-002; IC-005; IC-003 |
| **D-18** | Pluggable import source adapters; **v1 = Global record + CSV/JSON**; portable ingestion (no provider bulk-load). | ✅ | IC-003; IC-004 |
| **D-19** | Hybrid import execution: async-default + bounded sync fast-path; durable tenant-scoped job. | ✅ | IC-003; IC-002; IC-005 |
| **D-20** | Import idempotency: **operation-key + per-record natural-key reconciliation** (upsert; no-op when unchanged). | ✅ | IC-003; IC-004 |
| **D-21** | **Batched/checkpointed atomic imports with resumability**; per-batch lineage (atomic provenance). | ✅ | IC-003; IC-004 |
| **D-22** | **Minimal lineage core** (MUST fields) + reference/code-only extension envelope; no payloads/PII/secrets. | ✅ | IC-004; IC-003 |
| **D-23** | Immutability **defense-in-depth**: DB append-only (privilege + reject UPDATE/DELETE) **+** per-tenant cryptographic hash-chaining. PostgreSQL-portable; no vendor ledger. | ✅ | IC-004; IC-002; IC-003 |
| **D-24** | **Per-tenant retention/archival** within compliance floor/ceiling; segmented verifiable archival; **policy-driven expiry only via tombstones**, audited. | ✅ | IC-004; IC-002; IC-003 |
| **D-25** | **Unified per-tenant provenance graph** (parent refs) + **segmentable** integrity chain; never crosses tenants; AI-ready. | ✅ | IC-004; IC-003 |
| **D-30** | **Defense-in-depth cross-tenant isolation**: authoritative claim+membership → single-tenant routing → per-tenant creds + no cross-tenant reuse → audit/anomaly. No cross-tenant joins ever. | ✅ | IC-005; IC-002/003/004 |
| **JWT** | JWT lifecycle: short-TTL access tokens; OIDC refresh at IdP; JWKS/`kid` rotation; optional bounded control-plane `jti` denylist; no session store; DB-free validation. | ✅ | IC-005 |
| **D-31** | **Global Directory Residency**: Global Startup & Investor Directories reside **only** in the Control DB; tenant copies only in tenant DBs; no tenant data in Control DB. Directory access governed by IC-005. | ✅ (amendment) | IC-001, IC-003, IC-005 |
| **D-32** | **Role hierarchy**: CONTROL, MASTER_AGENT, TENANT_ADMIN, TENANT_AGENT, STARTUP_USER, INVESTOR_USER (roles, not permissions). MASTER_AGENT obeys one-request→one-tenant; no cross-tenant superuser. | ✅ (amendment) | IC-005, IC-002, IC-007 (future) |

**Open (post-MVP only):** IC-006 cluster — D-09 egress, D-26 (first AI provider), D-27 (sync/queued), D-28 (usage/cost), D-29 (AI lineage). **D-08 values** remain a standing business/legal action (architecture fixed).

---

## 6. Repository Architecture

### 6.1 Folder structure
```
SnackPortal2/
├─ CLAUDE.md                     project guide (note: predates implementation; treat repo as source of truth)
├─ .github/  .gitignore  .gitleaks.toml
├─ backend/
│  ├─ pyproject.toml             deps (pyjwt, cryptography, psycopg[binary]); dev: ruff, mypy, pytest, import-linter; importlinter contracts
│  ├─ shared/                    LEAF (pure stdlib ports/shapes)
│  │   ├─ session.py             Lane; RoutedTenantSession (upsert/append/get/latest); RoutedSessionProvider;
│  │   │                         LineageReadSession (page/traverse/close); LineageReadSessionProvider   [P6 additive]
│  │   ├─ lineage.py             LineageIntent; LineageEmitPort
│  │   ├─ secrets.py             SecretRef/SecretValue/SecretStore (D-14)
│  │   ├─ context.py             RequestContext (correlation/tenant/principal/role; no secrets)
│  │   ├─ audit.py               OperationalAudit / OperationalAuditEvent (≠ lineage)
│  │   ├─ errors.py  queue.py  health.py  dto.py  config.py  logging.py
│  │   └─ adapters/{interfaces.py, providers/{env_reference_secret_store.py}}
│  ├─ control_plane/             bootstrap, registry, readiness, schema_compat, membership, federation,
│  │                             directory, lifecycle, verification, read_api, audit
│  │   └─ adapters/providers/    in_memory_store.py; postgres_store.py; postgres_probe.py; http_read_api.py
│  ├─ auth_router/               jwt_validation, tenant_context, authenticator, caching, models, ports
│  │   └─ adapters/providers/    pyjwt_verifier.py; http_control_plane_read.py; in_memory_audit_sink.py
│  ├─ database_router/           resolver, cache, pool, router, disclosure, models, ports,
│  │   │                         session_provider.py (PgRoutedSession: write vocab + page/traverse/lock_chain;
│  │   │                         PgRoutedSessionProvider: open_session + open_read_session)
│  │   └─ adapters/providers/    psycopg_connection.py; env_tenant_secret_store.py; http_routing_read.py; in_memory_audit_sink.py
│  ├─ import_service/            service.py (coordinator), validation.py, models.py, ports.py
│  │   └─ adapters/providers/    csv_source.py; json_source.py; global_directory_source.py; http_directory_read.py; in_memory_audit_sink.py
│  ├─ lineage_service/           canonical.py, emit.py, query.py, verification.py, graph.py, search.py,
│  │                             retention.py, segmentation.py, models.py, main.py, __init__.py   [P6 full build]
│  ├─ api_gateway/               main.py (skeleton; IMPLEMENTS_BEHAVIOR=False)
│  └─ tests/
│     ├─ architecture/           _scan.py; test_dependency_boundaries; test_no_secret_literals;
│     │                          test_vendor_and_db_containment; test_traceability; test_phase2..6_*
│     ├─ control_plane/ auth_router/ database_router/ import_service/   (behavior suites)
│     └─ lineage_service/        _doubles.py; test_canonical/emit/query/verification/graph/search/retention/segmentation
│        └─ requires_pg/         _pg.py; test_pg_append_only/chain_serialization/traversal/privilege  (live-PG)
├─ contracts/                    IC-001..IC-007 (.md)
├─ docs/                         ADR register, decision packs, governance standards, roadmap,
│                                Phase-1..6 acceptance criteria, handovers (incl. THIS master)
├─ infrastructure/
│  ├─ env/                       env templates (references only; no secrets)
│  └─ db/lineage/                001_lineage_schema.sql, 002_append_only.sql, 003_roles.sql, README.md   [P6]
└─ frontend/                     Lovable-generated React/TypeScript (product UI; out of backend scope)
```

### 6.2 Service ownership — see §3.2.

### 6.3 Shared contracts (in `shared/`, vendor-neutral)
`RoutedTenantSession` + `RoutedSessionProvider` (write seam); `LineageReadSession` + `LineageReadSessionProvider` (read seam, P6 additive); `LineageIntent` + `LineageEmitPort`; `SecretStore`/`SecretRef`/`SecretValue`; `RequestContext`; `OperationalAudit`; `Queue`/`JobEnvelope`; health/readiness shapes; `DenialReason`. Admission policy: a `shared` member is a cross-cutting port used by ≥2 services or a contract-agnostic primitive — **never** a single contract's DTO, never carries secrets/payloads.

### 6.4 Provider model (port/adapter)
`business → Port ← Adapter`. Ports are vendor-neutral and live in their domain module (or `shared/adapters/interfaces.py`). Concrete adapters live **only** under `**/adapters/providers/**`. Vendor SDKs / DB drivers are confined to provider zones. Provider selection is **config-driven at a single composition root** per service; adding/swapping a provider requires zero change to the port or business logic.

### 6.5 Composition-root model
Each service has one composition root (`main.py`) that wires config-selected providers to ports and injects shared ports (e.g., a `RoutedTenantSession` / `LineageReadSessionProvider` / `OperationalAudit`) into the business objects. Cross-service collaboration is **injection at the root** or **transport calls** — never an in-process service-to-service import.

---

## 7. Database Architecture

### 7.1 Physical Multi-Database MVP
```
                         ┌──────────────────────────────────────────────┐
                         │              CONTROL DATABASE                 │
                         │  (Control Plane + Global Discovery Platform)  │
                         │  • tenant registry + lifecycle state          │
                         │  • membership + role assignments (D-32)        │
                         │  • OIDC federation config (issuer/aud/jwks ref)│
                         │  • Global Startup Directory                   │
                         │  • Global Investor Directory      (D-31)      │
                         │  • operational/control-plane audit (≠ lineage)│
                         │  • NO tenant-owned data                       │
                         └──────────────────────────────────────────────┘
                                          │ registry-authoritative resolution (D-07)
                  ┌───────────────────────┼───────────────────────┐
                  ▼                       ▼                       ▼
        ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐
        │  TENANT DB  (t1)  │  │  TENANT DB  (t2)  │  │  TENANT DB  (tN)  │
        │  • tenant copies  │  │      …            │  │      …            │
        │  • lineage chain  │  │                   │  │                   │
        │  • import_job/    │  │                   │  │                   │
        │    idempotency/   │  │ physically        │  │ never shared;     │
        │    checkpoint     │  │ separate;         │  │ never joined      │
        │  • per-tenant     │  │ own credentials   │  │ across tenants    │
        │    creds (D-14)   │  │                   │  │                   │
        └───────────────────┘  └───────────────────┘  └───────────────────┘
```

### 7.2 Control Database
Holds **only** control-plane state + the Global Directories (D-31). Schema participates in **compatible-range** checks (D-12). Hosts federation config IC-005 consumes. Never opened by the Phase-0 system identity for tenant data.

### 7.3 Tenant Databases
One physically separate PostgreSQL DB per tenant. Resolved registry-authoritatively (D-07); accessed via per-(tenant, association_version) pools (D-13) with per-tenant credentials resolved at connect time (D-14). Schema is version-gated (D-17).

### 7.4 Database Router
The **only** tenant-DB accessor. Resolves routing, gates readiness/schema, binds exactly one connection, enforces single-tenant binding (rejects mis-bound connections), and exposes routed sessions (write `RoutedTenantSession`; read `LineageReadSession`) that map a portable tabular/keyset vocabulary to **standard parameterized PostgreSQL**.

### 7.5 Lineage storage (tenant-resident; `infrastructure/db/lineage/`)
```
lineage (append-only):
  seq BIGINT NOT NULL, lineage_id TEXT PK, segment_id BIGINT DEFAULT 1,
  event_type, occurred_at, actor_ref, source_ref, target_ref, operation, schema_version,
  derivation_ref?, parent_lineage_ref? (FK→lineage.lineage_id), correlation_id?,
  marker_version SMALLINT DEFAULT 1, integrity_marker TEXT, prev_marker TEXT DEFAULT '',
  CONSTRAINT lineage_seq_unique UNIQUE(seq)            ← chain-fork fail-closed
  indexes: (target_ref,seq) (derivation_ref,seq) (event_type,seq) (segment_id,seq) (parent_lineage_ref)
lineage_segment (archival summary): segment_id PK, first_seq, last_seq,
  opening_prev_marker, closing_marker, record_count, archived_ref?
Append-only enforcement (002): trigger lineage_append_only() RAISES SQLSTATE 'P6A01' on
  BEFORE UPDATE OR DELETE (row) and BEFORE TRUNCATE (statement).
Roles (003): lineage_writer (INSERT,SELECT; no UPDATE/DELETE/TRUNCATE), lineage_reader (SELECT).
  DELETE/TRUNCATE granted to NO role (append-only absolute). Login creds via D-14 (not in DDL).
Integrity marker = HMAC-SHA256(chain_key, canonical(record, prev_marker)); chain_key = D-14 ref.
```

### 7.6 Import storage (tenant-resident)
`import_job (job_id PK, operation_key, tenant_id, state, correlation_id)`; `import_idempotency (operation_key PK — exactly-once, job_id, status, applied/noop/rejected)`; `import_checkpoint (job_id, batch_seq PK, last_offset, applied_count, status, updated_at)`. Tenant data tables (e.g. `tenant_copy`) are tenant-schema-specific (out of lineage scope).

### 7.7 Authentication storage
**None on the data path.** OIDC stateless JWT validation is DB-free (D-05). Per-tenant OIDC federation config (issuer/audience/JWKS ref/claim rule) lives in the **Control-DB registry** and is consumed at authentication time. Optional bounded control-plane `jti` denylist is the only optional auth-adjacent store (not a session store, never per-tenant) — deferred (port only).

---

## 8. Anti-Vendor-Lock-In Requirements

| Standard | Requirement | Enforced where |
|---|---|---|
| **No Lovable lock-in** | Backend business logic must not depend on Lovable runtime/platform | `tests/architecture/test_vendor_and_db_containment` (ban-list incl. `lovable`); CLAUDE.md constraints; code review |
| **No Supabase lock-in** | No Supabase Auth, Supabase APIs, or RLS-as-business-logic | ban-list incl. `supabase`; auth is OIDC (IC-005); `test_vendor_and_db_containment` |
| **No cloud lock-in** | No provider-proprietary SDKs/features in business logic; portable across AWS RDS / Azure / Cloud SQL / self-hosted | ban-list incl. `boto3/botocore`, `azure`, `google.cloud/auth`; vendor SDKs only under `**/adapters/providers/**` |
| **Provider abstraction** | Single internal abstraction per external dependency (secrets, queue, DB, IdP) | `shared/adapters/interfaces.py` + per-domain ports; `R-CI-4` port-purity check |
| **Port/adapter pattern** | Adapters are the ONLY place a vendor SDK is imported; business modules never import `providers/**` | `R-CI-1/R-CI-3`; `test_vendor_and_db_containment`; `test_dependency_boundaries` |
| **Database portability** | Standard PostgreSQL only; no proprietary extensions/bulk-load/CDC/immutability features | DB drivers confined to two provider zones; DDL uses portable PL/pgSQL + standard constraints; `R-CI-7` |
| **Authentication portability** | Any OIDC-standard, self-hostable IdP; JWKS/`kid` rotation; not Supabase Auth | IC-005; `pyjwt_verifier` provider behind a `SignatureVerifier` port |
| **Secret hygiene** | References only (`{store_ref, version}`); values resolved in-memory at use; never in DTOs/logs/audit/lineage | D-14; `test_no_secret_literals`; gitleaks (`.gitleaks.toml`); `*_REF` template rule |

---

## 9. Phase Completion Reports

### Phase 1 — Repository Setup (COMPLETE + ACCEPTED)
**Deliverables:** vendor-neutral repo layout (7 packages + infrastructure + docs); shared ports/shapes (stdlib); empty vendor-containment zone; architecture test harness; env templates (references only); CI portability rules; governance + traceability docs. **Evidence:** `docs/Phase-1-Acceptance-Criteria.md`; architecture guards green. **Acceptance:** ✅ (scaffolding only; no business logic).

### Phase 2 — Control Plane (COMPLETE + ACCEPTED)
**Deliverables:** two-phase bootstrap (Phase-0 DB-free system identity vs trust anchor; Phase-0 closure + break-glass disable); three-state readiness; Control-DB schema-compat (detect-only); tenant registry (Register/GetStatus/Suspend/Decommission; **no tenant reaches Ready in Phase 2**); membership + federation config (storage only); Global Discovery Platform; operational audit. Persistence behind `ControlStore` port (in-memory adapter; Postgres provider added later, run live in Phase 6 work). **Evidence:** `docs/Phase-2-Acceptance-Criteria.md`; control_plane + architecture suites green. **Acceptance:** ✅ COMPLETE WITH OBSERVATIONS (Postgres ControlStore exercised only vs live DB at the time).

### Phase 3 — Authentication Layer (COMPLETE + ACCEPTED)
**Deliverables:** two-stage authenticator — (1) DB-free JWT validation (strict iss/aud/exp/kid; alg-confusion rejected; PyJWT behind `SignatureVerifier` port); (2) tenant-context via transport control-plane read (carrier-match D-06, membership/role D-04/D-32, consistent denial, fail-closed, caching). Output `RequestContext` (+ role). JTI denylist = port only (deferred). **Evidence:** `docs/Phase-3-Acceptance-Criteria.md`; auth_router + architecture suites green. **Acceptance:** ✅ COMPLETE WITH OBSERVATIONS.

### Phase 4 — Database Router + Control-Plane production completion (COMPLETE + ACCEPTED)
**Deliverables:** registry-authoritative resolver + TTL/version cache + readiness/schema gating; lazy bounded per-(tenant,version) pools + LRU + **no cross-tenant reuse**; per-tenant credentials via SecretStore at connect; single-tenant binding enforcement + isolation anomaly audit; caller-controlled transactions (IC-003/4-ready). Control-plane lifecycle Verify/Activate/Reactivate/Reassociate via control-plane verification probe (no control_plane→database_router edge); real-HTTP routing read loopback. DB-driver containment amended to two provider zones. **Evidence:** `docs/Phase-4-Acceptance-Criteria.md`; **PRD-P4-V1 = PASS WITH OBSERVATIONS**. **Acceptance:** ✅.

### Phase 5 — Import Service (+ Phase-6 lineage write-path slice) (COMPLETE + ACCEPTED)
**Deliverables:** import coordinator (operation+natural-key idempotency D-20; batched/checkpointed/resumable D-21; ingress validation+PII floor D-09; pluggable adapters Global/CSV/JSON D-18) → **atomic provenance** (tenant copy + lineage emit + checkpoint in ONE routed-session transaction); bulk capacity lane; operational audit. `lineage_service/emit.py` write slice (D-22 core + per-tenant HMAC hash-chain D-23). Two new shared ports (`session.py`, `lineage.py`). Global Directory read endpoints + real-HTTP loopback. **Evidence:** `docs/Phase-5-Acceptance-Criteria.md`; **PRD-P5-V1 = PASS WITH OBSERVATIONS**. **Acceptance:** ✅.

### Phase 6 — Lineage Service (IMPLEMENTED + VERIFIED; eligible for PMO acceptance)
**Deliverables:** full Lineage Service — `canonical.py` (single-source HMAC content, frozen v1, `marker_version`; closes P6-OBS-3), `emit.py` refactored onto canonical (+ `segment_id`/`marker_version`, optional `lock_chain`, `LineageWritten` audit; back-compatible), `query.py` (keyset pagination/filtering), `verification.py` (recompute + prev/seq continuity → `VerificationReport`; `LineageVerified`/`ChainBroken` audit), `graph.py` (ancestor/descendant traversal, depth/node bounds), `search.py`, `retention.py` (safe default retain-all; expire/crypto_erase/delete RAISE until D-08), `segmentation.py` (read-only summaries + continuity + `ArchivePrepared`), `models.py` DTOs, `main.py` builders. **Additive read seam** in `shared/session.py` + `database_router/session_provider.py` (write seam untouched). **DB-level append-only DDL** in `infrastructure/db/lineage/` (closes V-OBS-1 + V-OBS-4). Phase-6 architecture guard. `docs/Phase-6-Acceptance-Criteria.md`. **Evidence:** R1 = APPROVED WITH OBSERVATIONS; R2 = READY FOR EXECUTION WITH OBSERVATIONS (all 11 obs closed, no contract amendment); E1 = COMPLETE WITH OBSERVATIONS (48 stdlib green); **V1 = PASS WITH OBSERVATIONS with live-PostgreSQL Objective-N executed** (see §10). **Acceptance:** ✅ COMPLETE + ACCEPTED — PMO accepted the live-PostgreSQL Objective-N evidence and Phase 6.

---

## 10. Verification Evidence

### PRD-P5-V1 (Import Service) — PASS WITH OBSERVATIONS
Independent re-run + source audit confirmed: import owns no auth/authz/routing/credential-resolution/lineage-persistence/hash-chaining/synchronization; Global record ≠ Tenant record; import ≠ sync; **atomic provenance verified** (data + lineage + checkpoint commit/rollback together); no router bypass, no lineage bypass, no dependency drift. Observations carried: **V-OBS-1** (DB-level append-only deferred to Phase 6 — now closed), V-OBS-2 (per-run applied/noop counts), V-OBS-3 (dangling in_progress on early failure; no data written), V-OBS-4 (concurrent idempotency needs DB unique constraint — now provided), V-OBS-5 (psycopg/live-DB + tooling carried).

### PRD-P6-V1 (Lineage Service) — PASS WITH OBSERVATIONS
Fresh-eyes re-run (in the canonical OneDrive copy) + source/DDL grep audit + **executed live PostgreSQL 16.14 evidence**.

**PostgreSQL evidence (Objective N) — executed on PG 16.14, db `snackportal2`, via `psql` (pgpass auth):**
| Check | Result |
|---|---|
| N1 UPDATE on lineage | `ERROR: P6A01: lineage is append-only: UPDATE rejected` |
| N2 DELETE on lineage | `ERROR: P6A01: … DELETE rejected` |
| N3 TRUNCATE on lineage | `ERROR: P6A01: … TRUNCATE rejected` |
| N4 duplicate `seq` (fork) | `ERROR: 23505 duplicate key … lineage_seq_unique` (Key (seq)=(1) already exists) |
| N5 advisory lock | `pg_advisory_xact_lock` acquired & held in txn |
| N6 recursive-CTE traversal | ancestors(G)=`G,C,R`; descendants(R)=`R,C,G` |
| N7 privilege | `lineage_writer` UPDATE → `ERROR: 42501 permission denied`; writer INSERT allowed |
| immutability proof | row count + operations unchanged after all mutation attempts |

**Append-only proof:** DB trigger (preventive, `P6A01`) + privilege (`42501`) + hash-chain (detective) — defense-in-depth verified. **Atomic provenance proof:** Phase-5 `import_service/test_atomic_provenance` green (commit/rollback together); emit contract unchanged. **Dependency proof:** grep — `lineage_service` imports no `database_router`/`control_plane`/`import_service`/`auth_router`/`api_gateway`, no DB driver, no secret literals; `hmac`/`hashlib`/`\x1f` only in `canonical.py`; `test_dependency_boundaries` + `test_phase6_lineage_service` green. **Regression proof:** control_plane 10/10, auth_router 6/6, database_router 9/9, import_service 6/6; all 9 architecture guards green; **48 stdlib files / 170 test fns / 0 fail; 4 `requires_pg` files** (run live above).
**Residual (Low, non-blocking):** N8 psycopg/`PgRoutedSession` application read path not exercised (32-bit Python can't load 64-bit libpq); D-08 retention values pending; external tooling gate (ruff/mypy/import-linter/gitleaks/pytest) not run.

---

## 11. Current Backend Status

| Category | Items |
|---|---|
| **Implemented** | shared ports/shapes; control_plane (Phase 2 + Phase 4 lifecycle); auth_router (Phase 3); database_router (Phase 4 + Phase 5/6 session seams); import_service (Phase 5); **lineage_service (full Phase 6)**; infrastructure lineage DDL. api_gateway = skeleton. |
| **Accepted** | **Phases 1–6 COMPLETE + ACCEPTED** (PMO accepted Phase 6 + the live-PG Objective-N evidence). |
| **Verified** | Phase 4 V1, Phase 5 V1, **Phase 6 V1** (all PASS WITH OBSERVATIONS); live-PostgreSQL 16.14 Objective-N evidence executed + PMO-accepted. |
| **Outstanding** | N8 psycopg app-path run on 64-bit Python; external tooling gate run; D-08 values; `git init`. (Phase 6 PMO acceptance — DONE.) |
| **Deferred** | api_gateway full behavior; IC-006 AI Gateway (post-MVP); IC-007 cross-tenant collaboration; JTI denylist storage; transaction-pooler scale layer (D-13); retention **expiry/archival jobs** (mechanism + safe default built; activation gated on D-08). |

---

## 12. Outstanding Work (future phases / tracks)

| Item | Priority | Dependencies | Recommended order |
|---|---|---|---|
| ✅ **PMO acceptance of Phase 6** | DONE | P6-V1 | complete |
| **External CI/tooling gate** (ruff, mypy, import-linter, gitleaks, pytest) + `git init` | P1 | install dev deps | 1 (next) |
| **N8 closeout** — run `requires_pg` harness verbatim on 64-bit Python + psycopg | P1 | 64-bit Python | 3 (alongside 2) |
| **D-08 business/legal values** — name compliance floor regime + per-tenant retention floor/ceiling + residency | P1 | business/legal sign-off | 4 (unblocks expiry/archival) |
| **Retention expiry + archival jobs** (D-24) — tombstone + crypto-erase + cold-tier movement | P2 | D-08 values | 5 |
| **API Gateway full behavior** (rate limiting, audit initiation, ingress) | P2 | Phases 1–6 | 6 |
| **Provisioning automation** (D-15 IaC + control-plane workflow) | P2 | infrastructure | 6 (parallel) |
| **Investor/Startup Portal backend surfaces** (product features riding on the platform) | P2 | product specs (gap — see §16) | 7 |
| **IC-006 AI Gateway** (post-MVP) | P3 | D-09 egress, D-26..D-29 | later |
| **IC-007 Cross-tenant collaboration** | P3 | new contract | later |

---

## 13. Known Risks

| Severity | Risk | Mitigation |
|---|---|---|
| **Critical** | *(none)* | — |
| **High** | *(none)* | — |
| **Medium** | Chain-head concurrency under heavy parallel append | `UNIQUE(seq)` fails a fork closed (verified on PG); optional advisory lock serializes; checkpoint/resume re-drives — design landed. |
| **Medium** | Retention/erasure vs append-only (when D-08 enables expiry) | Expiry acts on referent + tombstone; never mutates/deletes a lineage row; chain stays verifiable; audited. |
| **Low** | psycopg/`PgRoutedSession` app path unexercised (32-bit Python) | DB guarantees proven via psql; app marker-recompute proven by stdlib suite; run harness on 64-bit Python to close N8. |
| **Low** | External tooling gate never run end-to-end (no git; tools uninstalled) | `git init` + install dev deps; run ruff/mypy/import-linter/gitleaks/pytest. |
| **Low** | Two project copies may diverge (see §19) | Operate only in the OneDrive copy; retire/sync the other. |
| **Low** | D-08 values unset | Safe default retain-all; expiry disabled until values named. |

---

## 14. Technical Debt

- **Tooling gaps:** ruff, mypy, import-linter, gitleaks, pytest, psycopg, pyjwt, cryptography **not installed**; repo is **not a git repository**; only interpreter is **Python 3.8.2 32-bit** (blocks psycopg ↔ 64-bit PostgreSQL). The architecture/CI *rules* exist (`pyproject.toml [tool.importlinter]`, `.gitleaks.toml`, `.github/`), but are not run end-to-end.
- **Retention values:** D-08 floor regime + per-tenant retention/residency unset (standing business/legal action). Retention mechanism + safe default built; expiry/archival jobs not yet built.
- **Future migrations:** tenant-DB lineage/import schema delivered as portable SQL in `infrastructure/db/lineage/`; expand/contract migration *automation* (D-17) and provisioning workflow (D-15) not yet built. Tenant *data* schemas (e.g. `tenant_copy`) are tenant/product-specific and undefined here.
- **Infrastructure gaps:** no IaC for DB provisioning; no container/compose for a portable PostgreSQL test harness in CI; Postgres providers (`postgres_store`, `postgres_probe`, `psycopg_connection`, `PgRoutedSession`) compile but the **psycopg** path is unexercised by automated tests (only psql-driven evidence so far).

---

## 15. Architecture Drift Risks

| Potential drift | How to detect | How to prevent |
|---|---|---|
| Service-to-service in-process import | `test_dependency_boundaries`, `test_phase*_*` guards; import-linter `independence` contract | Collaborate via shared-port injection or transport only; keep guards in CI |
| Vendor SDK / DB driver leaking outside provider zones | `test_vendor_and_db_containment` (ban-list + zone allow-set) | Adapters only under `**/adapters/providers/**`; review |
| Secret/payload in DTO/log/audit/lineage | `test_no_secret_literals`, gitleaks, shape review | References only (D-14); `*_REF` template rule |
| Canonicalization re-implemented (false chain-break alarms) | `test_phase6_lineage_service.test_canonicalization_is_single_source` (`hmac`/`hashlib`/`\x1f` only in `canonical.py`) | One `canonical.py`; emit/verify/tests import it |
| Lineage gaining an UPDATE/DELETE path | session port has no update/delete verb; DB trigger `P6A01`; `requires_pg` | Keep append-only verbs; keep trigger + role grants |
| Cross-tenant query/aggregation | per-tenant routed session; D-30 guards; no spanning SQL | Always one active tenant per request; cross-tenant only as audited per-tenant control-plane reads |
| Frozen seam re-architected | seam-evolution recorded as additive (e.g. `LineageReadSession`); contract change-control | Extend additively; raise a contract/governance amendment before changing frozen behavior |

---

## 16. MVP Requirements

| Area | Requirement (status) |
|---|---|
| **Physical Multi-Database MVP** | Control DB + one physically separate PostgreSQL DB per tenant; no shared tenant DB. **BUILT.** |
| **Tenant Isolation** | One request → one active tenant → one DB; per-tenant credentials; no cross-tenant connection reuse; no cross-tenant joins (D-30). **BUILT + verified.** |
| **Control Plane** | Two-phase bootstrap, registry, three-state readiness, schema-compat, membership/federation, Global Directory, provisioning workflow interface, operational audit. **BUILT** (provisioning automation pending). |
| **Authentication** | OIDC stateless JWT, hybrid identity, signed-claim + carrier-match, role hierarchy (D-32), defense-in-depth isolation. **BUILT.** |
| **Import** | Global→tenant copy, pluggable adapters (Global/CSV/JSON), idempotent, batched/resumable, ingress validation/PII floor, atomic provenance. **BUILT.** |
| **Lineage** | Per-tenant append-only hash-chained provenance; query/search/verify/graph; retention/archival framework; DB-level append-only. **BUILT + verified.** |
| **Investor Portal requirements** | Federated `INVESTOR_USER` role operating within tenant scope; consumes platform (auth/routing/import/lineage) via the API gateway; reads Global Investor Directory (control-plane read, IC-005). **Detailed product feature specs are NOT in the backend contracts — they are frontend/product scope (Lovable) and must be defined separately (GAP).** |
| **Startup Portal requirements** | Federated `STARTUP_USER` role within tenant scope; reads Global Startup Directory; same platform consumption. **Same gap: product specs undefined in backend contracts.** Cross-tenant introductions/sharing are **deferred to IC-007.** |

> **Note for product/business:** the backend platform foundation supports the portals (roles, directories, tenant isolation, import, lineage), but **portal feature requirements themselves are not yet captured as contracts/PRDs.** Define them (product specs → contract/PRD) before building portal-specific backend surfaces.

---

## 17. Future Roadmap

**Recommended next phases (after PMO accepts Phase 6):**
1. **Hardening & CI** — `git init`; install dev/runtime deps; run ruff/mypy/import-linter/gitleaks/pytest; run `requires_pg` on 64-bit Python (close N8); stand up a portable PostgreSQL test service in CI.
2. **Compliance enablement** — land D-08 values; build retention expiry + archival jobs (D-24) on the existing mechanism.
3. **Provisioning & gateway** — D-15 IaC + automated control-plane provisioning workflow; complete API Gateway behavior.
4. **Product layer** — capture Investor/Startup Portal requirements as contracts/PRDs; build portal-specific backend surfaces on the platform.
5. **Post-MVP** — IC-006 AI Gateway (D-09 egress, D-26..D-29); IC-007 cross-tenant collaboration.

---

## 18. Current Acceptance Baseline (exact)

> **Phases 1–6: COMPLETE + ACCEPTED.**
> **Phase 6 (Lineage Service): IMPLEMENTED (PRD-P6-E1) and INDEPENDENTLY VERIFIED (PRD-P6-V1 = PASS WITH OBSERVATIONS, live-PostgreSQL 16.14 Objective-N evidence executed). PMO ACCEPTED the Objective-N evidence and Phase 6.**
> Contracts IC-001…IC-005 **Final**; ADRs D-01…D-32 **Approved**; IC-006 Draft/post-MVP; IC-007 Deferred.
> Test baseline: **52 test files (48 pure-stdlib green + 4 live-PostgreSQL), 170 test functions, 0 failures.**
> No Critical or High findings outstanding. Residual observations are Low/non-blocking (N8 psycopg app-path; D-08 values; external tooling gate).
> **Phase 6 is PMO-ACCEPTED** (the PostgreSQL Objective-N evidence was accepted). The Phases 1–6 backend core is feature-complete and accepted.

---

## 19. Instructions For Next Claude Session

**Read this document first** (`docs/PROJECT-HANDOVER-MASTER.md`) — it is the authoritative source of truth. Then, only if needed for the specific task: `contracts/IC-004` (+ IC-001/002/003/005), `docs/Architecture-Decision-Register.md`, `docs/Phase-6-Acceptance-Criteria.md`, and the source seams (`backend/shared/session.py`, `backend/lineage_service/*`, `backend/database_router/session_provider.py`).

**Working directory (critical):** read and write code at **`C:\Users\dan\OneDrive\PitchSnack\SnackPortal2`** (the canonical copy). A second copy exists at `C:\Users\dan\SnackPortal2` (harness cwd) — treat it as secondary; do not split work across both.

**Save locations:**
- Code → `C:\Users\dan\OneDrive\PitchSnack\SnackPortal2`.
- Generated deliverable docs (review findings / execution / verification reports) → `C:\Users\dan\OneDrive\PitchSnack\PRD\`.
- Input PRD prompts are @-referenced from the Desktop tree `…\Loveable\1. SnackPortal2\PRD\…` (and a `GPT PRD\` subfolder for GPT-authored PRDs).
- When a path is being corrected, write to the **exact** path given; do not run speculative `mkdir` or guess subfolders.

**Environment facts:**
- **Python 3.8.2 (32-bit)** is the only interpreter — `psycopg` cannot run here (needs 64-bit to load PostgreSQL 16's 64-bit `libpq`). Use **`psql`** for live-PostgreSQL work (`C:\Program Files\PostgreSQL\16\bin`).
- **PostgreSQL 16.14** is available locally; database **`snackportal2`**; auth via **pgpass** (`C:\Users\dan\AppData\Roaming\postgresql\pgpass.conf`, user `postgres`). **Never echo, print, log, or store the password.** Connect with `psql -h localhost -p 5432 -U postgres -d snackportal2 -w`.
- Run the stdlib suite from `…/SnackPortal2/backend` by executing each `tests/**/test_*.py` with `python` (each is standalone via `_h.run`/`_scan.run`). `requires_pg` tests SKIP cleanly without `SNACKPORTAL_TEST_DSN` + psycopg.
- **Not a git repository** (no commits expected unless asked).

**What to do first:** **Phase 6 is PMO-ACCEPTED (Phases 1–6 complete).** Pick the next item from §12/§17 (likely the CI/tooling hardening track + N8 closeout, or D-08 enablement) and run it through the **Rn→remediation→En→Vn** cadence. If a new PRD is provided, follow it literally (respect its prohibition list); produce the exact deliverable shapes; do not exceed authorized scope.

---

## 20. Project Continuity Rules

1. **Contracts precede code.** Behavior must trace to a Final contract (IC-00x) + Approved ADR (D-xx). New behavior needs a contract/PRD first.
2. **Honor PRD scope literally.** Review/verification PRDs are documentation-only — no code/schema/migration/test changes. Implementation happens only under an Execution (En) PRD that authorizes it. Authorization does not carry between PRDs.
3. **Be a genuine reviewer.** Surface real findings with severity; never rubber-stamp; never exceed scope.
4. **Cite governance** (IC-00x / D-xx) on every item; map deliverables to the exact requested shapes (matrices, ID'd risk registers, acceptance criteria, enum verdicts).
5. **One active tenant per request, always.** No cross-tenant joins or spanning queries — ever.
6. **References only.** No secrets/tokens/payloads/PII in DTOs, logs, audit, lineage, or responses.
7. **Preserve the DAG.** No service-to-service imports; shared is a leaf; vendor SDKs/DB drivers only in provider zones.
8. **Keep the architecture tests green** as the executable definition of the architecture; extend guards when adding capability.
9. **Operate in the canonical OneDrive copy**; keep deliverables in the PRD folder; never print the DB password.

---

## 21. Change Governance Rules

1. **MVP architecture is FROZEN.** Any change to frozen behavior or a Final contract requires a **governance amendment first**: register entry (new/updated ADR) → contract amendment → code. (Precedent: D-31, D-32 were post-freeze Approved amendments folded into IC-001/002/003/005.)
2. **Stable seams are additive-only.** `RoutedTenantSession`, `LineageEmitPort`, `LineageIntent`, and the tenant-DB `lineage` shape are stable seams. Extend additively (e.g., the Phase-6 `LineageReadSession` was added without touching the write seam). Record seam evolution as additive; do not re-architect.
3. **No silent divergence.** If implementation must diverge from a contract, **update the contract first**, then the code.
4. **Append-only is absolute.** Lineage rows are never updated/deleted (DB trigger + privilege + hash-chain). The only sanctioned removal is policy-driven expiry of *referents* (tombstone + crypto-erase), audited — never mutation of a lineage row.
5. **Portability is non-negotiable.** Standard PostgreSQL only; no vendor lock-in; provider/port pattern enforced.
6. **D-08 values are business/legal**, not an architecture decision — do not invent them; gate expiry/retention activation on them.

---

## 22. Single Source Of Truth Declaration

> **`docs/PROJECT-HANDOVER-MASTER.md` is the authoritative reference for the SnackPortal2 backend program.**
> It supersedes prior phase handovers for orientation purposes (those remain valid historical records). It is sufficient for a new Claude session, a new ChatGPT session, a new developer, or a future architecture review to continue work **with no dependency on prior conversation history.**
> Where this document and the live repository disagree, **the repository is the source of truth for code**, and the **Final contracts + Approved ADRs are the source of truth for intended behavior** — update this document to match when they change.

---

*End of master handover. Build Phase 6 is IMPLEMENTED + INDEPENDENTLY VERIFIED (PRD-P6-V1 = PASS WITH OBSERVATIONS, live-PostgreSQL Objective-N executed) and **PMO-ACCEPTED**. Phases 1–6 backend core is feature-complete and accepted. No code, schema, migration, or repository change was made in producing this document.*
