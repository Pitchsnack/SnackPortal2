# DBR-AR-2 V1 — Durable Routing Audit Contract (contract capture only)

**Phase:** DBR-AR-2 V1 — contract capture and readiness. **This V1 phase records a documented contract and a
guard test only.** DBR-AR-2 remains OPEN. This V1 records the implementation contract only. No durable routing-audit adapter, schema, production wiring or activation change is delivered by V1.

---

## 1. Status and baseline

**Baseline (verified live, 2026-07-12):** `HEAD == main == origin/main == ac6ca9da48837b5c06cf6a9f1663af73fedf1b74`.

Authoritative standing status (unchanged by this document):

- **Decision A (B5-E, 2026-07-12, Dan-authorized): B5-BLK-4 — CLOSED — EVIDENCE-BOUND GOVERNANCE DECISION.**
- **Decision B (B5-E, 2026-07-12, Dan-authorized): Physical Multi-Database MVP — ACCEPTED AT DATABASE GRANULARITY.**
- Production runtime activation remains NOT READY / DO-NOT-ACTIVATE — 8 of 9 activation blockers remain OPEN.
- DBR-AR-2 (durable routing audit) remains OPEN — a separate Database Router follow-on.
- The Lovable cutover remains OPEN (B5-BLK-5 / B5-BLK-6; separate track).
- The gate §5 activation condition "provisioning audit sink available (B-6) — or an explicit, approved waiver" remains binding at activation time and is not waived by anything in this document.

**DBR-AR-2A / DBR-AR-2B status (event contract and port; durable storage capability):**

- DBR-AR-2A — implemented.
- DBR-AR-2B — storage capability implemented when this PR merges: created-not-applied DDL, append-only enforcement, Control Plane store, internal ingest adapter, and uncomposed Database Router client.
- DBR-AR-2 — remains OPEN.
- DBR-AR-2C through DBR-AR-2E — not started.
- The DDL is not applied.
- Production composition is not implemented.
- Live durability is not yet proven.
- Least-privilege routing-audit writer-role DDL remains separately governed and is not delivered by DBR-AR-2B.
- Production activation remains NOT READY / DO-NOT-ACTIVATE.

This document changes no blocker, no blocker count, no decision, no gate posture, and no routing semantics. It is
the readiness-reviewed implementation contract that the DBR-AR-2 implementation slices (§16) must satisfy.

## 2. Problem statement

Every runtime routing-audit witness in the accepted MVP evidence chain is in-memory only:

- the Database Router emits `Route` / `RouteControl` / `RouteDenied` / `IsolationAnomaly` operational-audit
  events through the shared `OperationalAudit` port into `InMemoryAuditSink`
  (`backend/database_router/adapters/providers/in_memory_audit_sink.py`) — a process-lifetime Python list;
- the API Gateway emits the four IC-002 class-3 runtime operational events (`RouteDenied`, `CarrierMismatch`,
  `CarrierOnControlAnomaly`, `IsolationAnomaly`) into an in-memory emitter;
- the Auth Router's granular `denied:<code>` outcomes (including `tenant_access_denied`, `tenant_not_ready`)
  land in its own in-memory sink.

`database_router/main.py` states twice that the composed router is NOT production-durable and names DBR-AR-2 as
the follow-on. SMOKE-C-SPEC-01 §6 makes the in-memory disclosure mandatory in every evidence record. D-34 §2
registers the gap: service-emitted runtime events are "Implemented (emission); persistence incomplete — no
durable sink". A process restart erases the only witness of which tenant each request was routed to and why any
request was denied. DBR-AR-2 defines the durable, vendor-neutral, references-only record that closes this gap.

## 3. Current-state evidence (re-derived live at the baseline)

- **Emission sites (Database Router, `backend/database_router/router.py`):** `_ok` (action `Route` with the
  bound tenant, or `RouteControl` for the control target), `_denied` (action `RouteDenied`, outcome
  `denied:<public_code>`), `_anomaly` (action `IsolationAnomaly`, outcome `anomaly:tenant_binding`, D-30 L3).
  Denials perform zero pool acquisition and zero tenant-database connection beyond the failing step; the Smoke C
  harness asserts exactly 1 router event per successful dispatch and exactly 0 router events on every denial
  (its denial scenarios are denied at the auth boundary and never reach `route()`).
  Before DBR-AR-2A: two pre-target denials (`tenant_routing_unavailable`, `no_active_tenant`) had no router-edge audit event.
  After DBR-AR-2A: every completed or denied `route()` invocation produces exactly one router-edge in-memory event.
  Live durability is not yet proven.
- **Event shape today (`backend/shared/audit.py`):** frozen `OperationalAuditEvent` — `actor_ref`, `action`,
  `correlation_id`, `outcome`, `target_ref`; references only.
- **Router-edge denial vocabulary (`backend/database_router/models.py`, `disclosure.py`, `resolver.py`,
  `router.py`):** `not_found`, `no_active_tenant` (forbidden), `not_ready`, `schema_out_of_range`,
  `administratively_disabled`, `unavailable`, `control_plane_unavailable`, `connection_unavailable`,
  `tenant_routing_unavailable`, `routing_isolation_fault`. The auth/gateway-edge internal codes
  `tenant_access_denied` and `tenant_not_ready` arise upstream in `auth_router/tenant_context.py` and never
  reach `route()`; they are class-3 edge territory (see §7).
- **Contract law already binding:** IC-002 Audit-Section Extension class 3 (Runtime Operational Audit —
  Control-DB resident; field set `audit_id`, `action`, `correlation_id`, `outcome`, `actor_ref?`, `tenant_ref?`,
  `carrier_ref?`, `timestamp`; emitted once per correlation id, single-edge at the gateway per IC-005
  *Runtime Operational Audit Emission*); IC-001 Global Audit Representation Rule (references only); IC-001
  platform retention for Control-DB audit (default retain-all; concrete values under the D-08 process);
  D-34-R2 O1 (operational audit belongs to the Control DB); D-30 layer 4 (audit/anomaly detection is a mandated
  defense-in-depth layer); D-14 (secret references only; resolution in memory at connect time).
- **Precedent (B-6/B-7/B-7A/B-7B):** the Control Plane owns the only durable audit today — `control_audit` in
  the Control DB (DDL 002 created-not-applied + 003 append-only trigger; applied to the standing Control DB by
  the governed ops path), written through the `ControlStore` port with lazy connect, D-14 `SecretRef` DSN
  resolution, fail-closed first-use, and audit-before-irreversible-commit ordering (B7B-D5).
- **Boundaries:** import-linter enforces that the six services are mutually independent (no service imports
  another) and `shared` is a leaf; DB drivers are confined to `database_router/adapters/providers/**` and
  `control_plane/adapters/providers/**`; every server is a plain single-threaded `HTTPServer`
  (AT-D15T1-10 — no threading anywhere); no runtime DDL on any path; the audit-class taxonomy is closed and
  CI-enforced (`backend/tests/architecture/test_audit_class_homes.py`).
- **Guard pins:** the three B5 gate documents each pin the sentence "DBR-AR-2 (durable routing audit) remains
  OPEN — a separate Database Router follow-on" (guard G9), and SMOKE-C-SPEC-01 §6/§7 pin the in-memory
  disclosure.

## 4. Selected architecture

**Selected architecture: Option B — Control-Plane-owned durable routing-audit store behind a service boundary.**

The Database Router emits routing-audit events through a vendor-neutral, references-only transport port (a new
`RoutingAuditPort` client under `database_router/adapters/providers/**`) to a Control-Plane-owned, internal-only
audit-ingest edge; the Control Plane persists them to a new append-only routing-audit table in the Control
Database (a `control_*` table beside `control_audit`, defined by created-not-applied DDL and applied only by the
governed ops path). The Control Plane remains the sole writer of the Control Database. The record class is the
IC-002 class-3 Runtime Operational Audit family, extended (by the DBR-AR-2A contract amendment, §17) with the
router-edge routing-decision events; the Database Router is the single emission edge for the routing-decision
events and the API Gateway remains the sole single-edge emitter of the existing four class-3 events, so no event
class is emitted by more than one component.

Why this option, from live evidence:

- **Residency and ownership are already contract law:** runtime operational audit is Control-DB resident
  (IC-002 class 3; D-34-R2 O1) and "audit storage … its exact location is a control-plane detail" (IC-002
  Audit Requirements). A Control-Plane-owned store follows the law; every alternative fights it.
- **Single Control-DB writer, least privilege:** the Database Router today holds tenant credentials only. It
  gains no Control-DB credential under Option B; the write path stays inside the service that already owns
  `control_audit`, its DDL discipline, and its unit-of-work adapters.
- **Sanctioned interaction pattern:** the router already consumes a Control-Plane HTTP read edge through its own
  client (`HttpRoutingRead`) without importing `control_plane`; `control_plane/router_signal.py` documents the
  inverse port-plus-transport pattern. The audit path reuses the same seam shape.
- **B-7B precedent transfers directly:** durable store selection inside the owning service, lazy connect, D-14
  reference-only DSN resolution, fail-closed first use, no runtime DDL, append-only trigger enforcement.

## 5. Rejected alternatives

- **Option A — Database Router-owned durable store (REJECTED).** The router would hold a standing Control-DB
  write credential (privilege expansion in the single most credential-dense service), the Control DB would gain
  a second direct writer, and the routing-audit table schema would couple two services without an API. It also
  cuts against IC-002's "control-plane detail" location rule and splits Control-DB DDL ownership. No import
  violation, but a boundary erosion with no compensating benefit beyond one fewer edge.
- **Option C — external durable event sink (REJECTED).** IC-002 class 3 makes runtime operational audit
  Control-DB resident; an external sink breaks residency without a contract amendment that has no motivating
  need. It would add the first non-PostgreSQL runtime infrastructure against the cloud-portable-PostgreSQL-only
  constraint (CLAUDE.md architecture constraint 1) and has no repo precedent, no governed DDL story, and no
  standing-environment harness.
- **Option D — durable outbox/queue then forward (REJECTED for this arc).** A forwarder needs either a
  background thread (forbidden — AT-D15T1-10, single-threaded servers, no threading anywhere) or a new
  supervised process plus a second durable store whose own integrity would need the same guarantees. It also
  weakens the audit-before-hand-back ordering in §9: an event acknowledged into a local outbox is not yet in the
  audit store when the tenant connection is handed over. Recorded as a possible future scale layer only,
  reconsidered (if ever) under a later throughput PRD; it is NOT selected and NOT authorized by this contract.

## 6. Service ownership

- **Emit:** the Database Router is the single emission edge for routing-decision events (`Route`,
  `RouteControl`, `RouteDenied`, `IsolationAnomaly` at router granularity). The API Gateway remains the sole
  single-edge emitter of the existing class-3 events (IC-005); wiring the gateway emitter to this same durable
  sink is a later slice (§16). The Auth Router never emits (IC-005: detection and signalling only); its
  in-memory sink stays a diagnostic witness.
- **Own/write/persist:** the Control Plane owns the ingest edge, the store adapter, and the routing-audit table;
  it is the sole Control-DB writer.
- **Read/query:** control-plane-scoped, CONTROL-role, audited reads only (§13).
- **DDL:** authored created-not-applied under `infrastructure/db/control/**`; applied only by the governed ops
  path (never runtime DDL).
- **No cross-service import is authorized:** `database_router` does not import `control_plane` and
  `control_plane` does not import `database_router` (import-linter independence contract); the boundary is the
  references-only wire. No circular dependency exists: the router calls the Control Plane (routing-read, audit
  ingest); the Control Plane's future cache-invalidation signal to the router is fire-and-forget through its own
  port; neither handler calls back into the other synchronously.

## 7. Event coverage (decisions)

One durable record class: **routing-decision events**, single outcome event per `route()` decision.

| Condition | Decision | Event |
|---|---|---|
| Route allowed (tenant) | RECORD | `Route`, outcome `success`, with `tenant_ref`, `resolved_tenant_ref`, association reference + version, lane |
| Route allowed (control) | RECORD | `RouteControl`, outcome `success` (no tenant, no association) |
| Route denied (any router-edge denial) | RECORD | `RouteDenied`, outcome `denied:<public_code>`, `public_code` from the router-edge canonical vocabulary (§3) |
| Tenant not ready (router edge) | RECORD | `RouteDenied` with `public_code` = `not_ready` (IC-002 lifecycle gate; includes the dormant standing tenant) |
| Unknown tenant (router edge) | RECORD | `RouteDenied` with `public_code` = `not_found` (consistent denial; zero dispatch, zero pool acquisition, zero tenant-DB connection) |
| `tenant_access_denied` / `tenant_not_ready` (auth/gateway edge) | RECORD at the gateway edge | class-3 `RouteDenied` (gateway is the emitter of record; these requests never reach `route()`); durable wiring of the gateway emitter is slice scope (§16) |
| Authentication failure visible to the router | NOT A ROUTER EVENT | structurally impossible — the router never authenticates (IC-005/IC-010 §H); homed at the auth/gateway edge |
| Secret-reference resolution failure | RECORD | `RouteDenied`, `public_code` = `connection_unavailable`, optional `error_class` = `secret_resolution` (§8 note — never alters the public code) |
| Pool acquisition failure | RECORD | `RouteDenied`, `public_code` = `connection_unavailable`, optional `error_class` = `pool` |
| Tenant database connection failure | RECORD | `RouteDenied`, `public_code` = `connection_unavailable`, optional `error_class` = `connect` |
| Isolation anomaly (D-30 L3 tenant-binding fault) | RECORD | `IsolationAnomaly`, outcome `anomaly:tenant_binding` |
| Dispatch completion / dispatch error | RECORDED AS THE ROUTE EVENT | the current dispatch adapter binds and immediately releases within one `route()` decision, so the route event IS the dispatch record; distinct `DispatchCompleted` / `DispatchFailed` events are a reserved forward extension for a future dispatch-execution era, not recorded now |
| Audit-sink failure | NOT RECORDABLE IN THE FAILED SINK | surfaces as the §10 failure posture plus an operator alert; the Control Plane MAY additionally record sink-availability transitions as administrative audit (slice decision, §16) |

## 8. Event schema (required fields)

Field analysis for the durable routing-decision record (wire and store carry the same references-only shape):

| Field | Decision | Notes |
|---|---|---|
| `event_id` | REQUIRED | immutable UUID minted by the router at event creation; the deduplication / idempotency key; unique in the store |
| `event_version` | REQUIRED | integer, starts at 1; additive-only evolution |
| `occurred_at` | REQUIRED | UTC ISO-8601, router clock; informational only — never an ordering authority |
| `recorded_at` | REQUIRED (store-side) | set by the sink on insert; informational |
| `correlation_id` | REQUIRED | request correlation reference (present on every event today) |
| `request_ref` | OPTIONAL | the `RequestContext.request_id` where present |
| `trace_ref` | OPTIONAL (reserved) | no distributed-tracing machinery exists; column reserved, nullable |
| `actor_ref` | REQUIRED | authenticated subject reference (`principal_ref`, or the literal `<unknown>` sentinel) |
| `tenant_ref` | OPTIONAL | authenticated active tenant id (null for CONTROL routes) |
| `resolved_tenant_ref` | OPTIONAL | the tenant the router actually bound; divergence from `tenant_ref` is an `IsolationAnomaly`, so recording both makes the D-30 invariant auditable |
| `action` | REQUIRED | `Route` / `RouteControl` / `RouteDenied` / `IsolationAnomaly` (frozen vocabulary; extension only by contract amendment) |
| `outcome` | REQUIRED | `success` / `denied:<public_code>` / `anomaly:<code>` (mirrors the live emission strings) |
| `public_code` | OPTIONAL | canonical router-edge denial code (§3); null on success |
| `error_class` | OPTIONAL | bounded internal vocabulary {`secret_resolution`, `pool`, `connect`, `driver`} for `connection_unavailable` denials; Control-DB operator-scoped enrichment that never changes the public code or response disclosure |
| `association_store_ref` | OPTIONAL | the logical database identifier AND the secret reference: the D-14 `SecretRef.store_ref` of the tenant's database association — a reference, never a resolved value, never a DSN, never a hostname |
| `association_version` | OPTIONAL | the association reference version bound for this route |
| `lane` | OPTIONAL | `interactive` / `bulk` (D-13 capacity lane) |
| `source_service` | REQUIRED | `database_router` (later: `api_gateway` for class-3 events through the same sink) |
| `source_version` | REQUIRED | router build/version identifier (e.g. the liveness `build_phase` string) |
| latency / timing metadata | ASSESSED — OPTIONAL FORWARD | `duration_ms` is a reserved optional forward field; no timing claim is part of the MVP record |
| integrity / hash-chain metadata | ASSESSED — EXCLUDED | no hash chain (B-7 precedent; never conflated with IC-004/D-23 lineage); any hash policy is a forward-contract extension only |
| retry/idempotency key | FOLDED | `event_id` is the retry/idempotency key; no separate field |

## 9. Forbidden data

The following must NEVER appear in any routing-audit event, wire payload, stored row, error message, log line,
or evidence artifact (Global Audit Representation Rule, IC-001; D-14; SMOKE-C-SPEC-01 §7):

- raw DSNs and unredacted connection strings;
- passwords;
- private keys and any key material;
- JWTs and any token-shaped strings;
- bearer tokens;
- authorization headers;
- request/response bodies (full request or response bodies, in whole or in part);
- arbitrary user payload and tenant business content;
- tenant result data (tenant-database result rows or values);
- secret values of any kind (only D-14 references — `store_ref` + `version` — are recordable);
- unnecessary personal data (no names, no emails, no PII);
- database hostnames, physical database names, connection topology, and the router's live
  `TenantConnection` / `RouteResult` / `TenantRoutingView` objects or any serialization of them.

A raw secret detected in a submitted event is itself a fail-closed reject (the B-6 policy precedent, condition 8).

## 10. Timing and atomicity

- **Single outcome event per routing decision**, written **synchronously, before the routing result is handed
  back**: for an allowed tenant route the durable write happens after resolution, connection acquisition, and
  the D-30 L3 binding check, and **before** the `RouteResult` (and its live connection) is returned to the
  caller — audit-before-hand-back, the routing analogue of the B7B-D5 audit-before-irreversible-commit rule. For
  a denial the event is written before the denial response is returned (posture in §10 condition 3). No
  before-AND-after double write; no outbox.
- **What is atomic:** the single INSERT of one audit row into the Control Database commits atomically within
  that database.
- **What is NOT atomic — stated plainly:** No atomicity is claimed across the Control Database and any tenant
  database; there is no distributed transaction and no two-phase commit. The audit row and the caller's
  subsequent tenant-database work live in physically separate databases. The guarantee provided is
  ordering-based, not transactional: no tenant connection is handed to a caller before its route-success record
  is durably committed, and a duplicate-safe retry (§11) covers the write-succeeded-but-response-lost window. A
  durable `Route` success record therefore proves the routing decision and hand-off, not the caller's subsequent
  completion.

## 11. Failure semantics (explicit, per condition)

Routing-level posture; the production activation gate stays fail-closed regardless (§1).

| # | Condition | Classification | Behavior |
|---|---|---|---|
| 1 | Audit sink unavailable before dispatch | **FAIL CLOSED** (RETRYABLE by the caller) | the allowed route is NOT handed back: the acquired connection is discarded and the request is denied with a non-leaking 503-bucket denial (internal code `routing_audit_unavailable`; wire disclosure stays the sanitized status bucket). No allowed route ever proceeds un-audited. |
| 2 | Audit write fails after successful dispatch | **FAIL OPEN WITH ALERT** (bounded to the reserved forward dispatch-completion events; RETRYABLE via `event_id`) | structurally absent for the MVP route-decision event — the §9 ordering means the decision record precedes hand-back, so there is no post-dispatch decision write to fail. A future post-hoc `DispatchCompleted` event that cannot be written cannot un-dispatch; it retries idempotently, then alerts. |
| 3 | Denial event cannot be recorded | **FAIL OPEN WITH ALERT** (scoped strictly to denial records) | the denial response is still returned — blocking a denial on audit availability would only produce another denial while losing the disclosure discipline; the request is never upgraded to success. The invariant preserved: no ALLOWED route is ever un-audited; a lost denial record raises an operator alert. |
| 4 | Retry causes duplicate audit submission | **RETRYABLE** (idempotent, duplicate-tolerant) | `event_id` is unique in the store; a duplicate insert is a no-op success (§11). |
| 5 | Audit storage becomes read-only | **FAIL CLOSED**; restoration **OPERATOR DECISION REQUIRED** | writes fail → condition 1 applies to allowed routes; recovery (storage, role, disk) is an operator action, never automatic. |
| 6 | Audit queue is full | **FAIL CLOSED** (structurally: no queue exists) | Option D was rejected — there is no queue or outbox to fill; ingest-edge saturation or timeout is indistinguishable from condition 1 and takes the same posture. |
| 7 | Partial outage / network partition | **FAIL CLOSED** for allowed routes (RETRYABLE); alert | from the router the partition is indistinguishable from condition 1: one bounded idempotent retry, then deny allowed routes; denial records degrade per condition 3. |

Never permitted: silently failing open for an allowed route; downgrading any error to a less-isolated outcome
(IC-010 §L); leaking sink/topology/secret state through a denial (the internal code stays in the audit layer;
the wire carries the sanitized status bucket only).

## 12. Idempotency and ordering

- **Deduplication key:** `event_id` (router-minted UUID). The store enforces uniqueness; duplicate submission is
  idempotent — the insert of an already-present `event_id` succeeds as a no-op (duplicate-tolerant by design).
- **Retry behavior:** one bounded, synchronous, idempotent retry at the router on a transient transport failure;
  then the §10 posture applies. No unbounded buffering, no background retry loop (no threads).
- **Ordering guarantee:** the store's identity column is the total-order authority (reads `ORDER BY id` — the
  B-7 precedent). Per-correlation ordering follows insertion order. Timestamps (`occurred_at`, `recorded_at`)
  are informational and are never used for ordering — clock skew therefore cannot corrupt order (clock-skew
  handling: order by id, skew tolerated in timestamps).
- **Duplicate tolerance:** consumers deduplicate by `event_id`; the unique key makes duplicates impossible in
  the store itself.
- **Event versioning:** `event_version` integer; additive-only schema evolution; a reader must ignore unknown
  optional fields.
- **Replay:** re-submission of previously recorded events (same `event_id`) is a no-op; replay can never mutate
  or duplicate history.

## 13. Integrity and retention

- **Append-only, enforced at the database:** the routing-audit table mirrors the `control_audit` discipline —
  no UPDATE path, no DELETE path in any adapter port (append/list only), plus a portable PL/pgSQL trigger
  rejecting UPDATE, DELETE, and TRUNCATE (the 003 append-only precedent). Corrections, failures, and reversals
  are NEW rows.
- **Tamper evidence:** the DB-level trigger plus the forward least-privilege writer role (INSERT+SELECT only —
  the B-7 policy forward proposal) are the MVP tamper controls. **No hash chain:** any hash policy is an
  optional forward-contract extension and is never conflated with IC-004/D-23 lineage.
- **Retention:** governed by the IC-001 platform retention policy for Control-DB-resident audit (D-24-segmented
  pattern; policy-driven expiry is the only sanctioned removal and is itself audited; per-tenant D-08 parameters
  do NOT govern these records). **Concrete retention values are an open governance decision under the D-08
  process — default retain-all until values are named. This contract does not invent a duration.**
- **Archival / legal hold / deletion exceptions:** archival follows the segmented D-24 pattern under the same
  IC-001 policy; legal hold and any deletion exception are governance decisions under that policy (open, §17);
  no adapter-level delete exists to abuse.
- **Backup and restore:** Control-Database backup scope — a deployment concern owned by the same evidence
  stream as B5-BLK-2/B5-BLK-8; no separate audit-specific backup machinery.
- **Access logging:** reads of the routing audit are themselves control-plane-scoped audited operations (§13).

## 14. Access and privacy

- **Emit:** Database Router (routing-decision events) and — when its wiring slice lands — the API Gateway
  (class-3 events). No other emitter; the Auth Router never emits.
- **Write:** Control Plane only, through its store adapter with the forward least-privilege INSERT+SELECT role.
- **Read / query:** CONTROL-role, control-plane-scoped, audited reads. Reads are per-tenant scoped on any
  surface that filters by tenant; cross-tenant aggregation happens only as explicit, audited, per-tenant
  control-plane reads (IC-005). **A tenant principal has no read path to routing audit in the MVP; a tenant
  must never read another tenant's routing audit** — any future tenant-facing surface must be gateway-fronted,
  per-tenant scoped, itself audited, and separately contract-amended.
- **Export:** operator-initiated only, audited under the Export Audit class (IC-002 class 4 shape); exported
  evidence is references-only and inherits the SMOKE-C redaction rules.
- **Administer:** infrastructure via the governed ops DDL path only (never runtime DDL).
- **Purge:** only policy-driven expiry under the IC-001 retention policy (operator-authorized, audited); no
  ad-hoc purge path exists.
- **Privacy:** records are governance metadata under the Global Audit Representation Rule — reference-only,
  access-controlled, never tenant-facing; `tenant_ref` is carried by design (IC-001 audit-record exemption from
  the Tenant Anonymity Rule) and no unnecessary personal data is recorded (no names, no emails, no PII).

## 15. Operational observability

- **Health/readiness signal:** the ingest edge exposes the same static, non-disclosing liveness posture as the
  existing services (IC-010 §S: no database names, no tenant counts or identities, no topology).
- **Audit-write success/failure metric:** counters for durable-write success, duplicate no-op, transient retry,
  and terminal failure, exposed operator-side (slice 2C/2D mechanics).
- **Queue depth / lag:** none — there is no queue by design (§10 condition 6).
- **Alert thresholds:** any condition-1 fail-closed denial (allowed route denied for audit unavailability) and
  any condition-3 lost denial record alert immediately; sustained transient-retry rates alert at an
  operator-tuned threshold (runbook value).
- **Operator runbook:** a DBR-AR-2D deliverable (start/stop of the ingest edge, failure drill, recovery, and
  evidence capture), following the Smoke C runbook conventions.
- **Incident query procedure:** per-`correlation_id` and per-`tenant_ref` operator queries over the store,
  documented in the 2D runbook; every incident read is itself audited (§13).
- **Redaction rules:** records are born references-only, so evidence redaction follows SMOKE-C-SPEC-01 §7
  (no key material, no token-shaped strings, no DSN, no password, no secret value; identities redacted).

## 16. Live-proof matrix (required before implementation acceptance)

| # | Proof | Class |
|---|---|---|
| 1 | Successful route durably recorded (row present after `route()` returns; correct fields) | LIVE-POSTGRES + STANDING-ENVIRONMENT |
| 2 | Denied route durably recorded (denial row with canonical `public_code`) | LIVE-POSTGRES + STANDING-ENVIRONMENT |
| 3 | Unknown tenant recorded with zero tenant-DB dispatch (row present; zero pool delta; zero tenant-DB connection) | LIVE-POSTGRES |
| 4 | Dormant standing tenant recorded: router edge `not_ready`; auth edge `tenant_not_ready` (witnessed over the standing `b5_standing_dormant` fixture) | STANDING-ENVIRONMENT |
| 5 | Audit event survives process restart (router + ingest edge restarted; row persists) | LIVE-POSTGRES |
| 6 | Duplicate submission is idempotent (same `event_id` twice → one row) | UNIT + LIVE-POSTGRES |
| 7 | No credential / raw DSN / token / private key stored (content scan over live rows + static guard) | UNIT + ARCHITECTURE |
| 8 | One request → one tenant → one database still holds with the durable sink composed (alpha→alpha only, beta→beta only) | STANDING-ENVIRONMENT |
| 9 | Audit-sink failure follows the §10 posture (sink down → allowed route denied fail-closed; denial still served; alert) | INTEGRATION |
| 10 | Append-only enforced (UPDATE / DELETE / TRUNCATE rejected by the trigger) | LIVE-POSTGRES |
| 11 | Cross-tenant audit reads denied (no unscoped read path; per-tenant scoping enforced) | INTEGRATION + ARCHITECTURE |
| 12 | Standing topology unchanged by proof (before-state == after-state except the intended, explicitly accounted audit rows — the Smoke C zero-mutation witness re-scoped by its successor spec) | STANDING-ENVIRONMENT + MANUAL OPERATOR |
| 13 | Production activation remains blocked until this evidence is reviewed and accepted (gate posture unchanged; guard green) | ARCHITECTURE + HOSTED CI |

Standing checks in this V1 phase were read-only; no apply, no teardown, no Smoke C execution.

## 17. Implementation slice sequence (smallest safe follow-up PRs; none begin in V1)

| Slice | Objective | Authorized surface | Off-limits | Acceptance / test strategy | Live proof | Rollback | Depends on | Model |
|---|---|---|---|---|---|---|---|---|
| **DBR-AR-2A — event contract and port** | Amend IC-002 (class-3 extension: router-edge routing-decision events, field set of §8) + IC-005 (emission-edge reconciliation: router = single edge for routing-decision events; gateway sole edge for the four existing class-3 events) + evolve `test_audit_class_homes.py` in lockstep; define the router-side event model and port extension (no persistence) | `contracts/IC-002…`, `contracts/IC-005…`, `backend/database_router/` event model, `backend/tests/**` | adapters/providers persistence, DDL, `main.py` wiring, gateway code | contract text pins + unit tests over the event model; taxonomy guard updated in the same PR | none (contract + in-memory) | revert PR | this V1 | Fable5 REQUIRED |
| **DBR-AR-2B — durable adapter and schema/storage contract** | Created-not-applied DDL for the routing-audit table + append-only trigger (+ unique `event_id`), next free numbers under `infrastructure/db/control/**`, registered with the DDL blob/pin guards; Control-Plane store method (append-only write behind a dedicated store port — no list/read/query/export/purge surface in 2B; those remain separately governed); internal-only ingest-edge adapter; router-side transport client | `infrastructure/db/control/**`, `backend/control_plane/**`, `backend/database_router/adapters/providers/**`, tests | applying DDL, runtime wiring, activation | blob-pinned DDL; adapter unit tests; fail-closed first-use tests; guard battery | B-7A-style live-PG exercise of the new DDL (separately gated) | revert PR (DDL created-not-applied) | 2A | Fable5 REQUIRED |
| **DBR-AR-2C — composition and failure semantics** | Env-selected composition (gate-first router-side selector for the ingest base URL; ValueError-before-socket edge knobs; lazy adapter import — the merged seam shape); audit-before-hand-back ordering in `route()`; §10 postures incl. the non-leaking condition-1 denial; bounded idempotent retry | `backend/database_router/**`, `backend/control_plane/main.py` seam, tests | activating production, changing denial disclosure, threading | seam-shape guards; §10 posture tests incl. sink-down injection; mutation battery | INTEGRATION proofs 9/11 | selector unset → prior in-memory composition, byte-for-byte | 2B | Fable5 REQUIRED |
| **DBR-AR-2D — live proof and operator runbook** | `requires_pg` harness for proofs 1–12 over the retained standing topology; operator runbook + references-only evidence template; Smoke-C-successor zero-mutation accounting | `backend/tests/**/requires_pg/**`, `infrastructure/runbooks/**`, `docs/runtime/**` | production source changes | harness green over the standing fixture; runbook walk-through | LIVE-POSTGRES + STANDING-ENVIRONMENT (Dan-authorized runs) | teardown per runbook | 2C | Fable5 (harness); runbook prose Opus-acceptable |
| **DBR-AR-2E — production activation evidence** | Production-environment sink availability + evidence capture at the pre-deployment stage; whether durable routing audit becomes a formal gate §5 condition is decided here (§17) | evidence records; gate docs via governed amendment | everything else | evidence review; guard evolution with the decision | PRODUCTION DEPLOYMENT (blocked with the gate; depends on B5-BLK-2/3 era work) | n/a (evidence only) | 2D + deployment phase | Fable5 REQUIRED |

Each slice runs the full gate battery, keeps LF-only blobs, stays within its authorized surface, and lands only
under a GPT-authored PRD with a Dan START-GATE and independent pre-merge verification.

## 18. Open governance decisions (recorded, not resolved here)

1. **IC-002/IC-005 amendment approval (2A gate):** the closed audit-class taxonomy must be extended for the
   router-edge routing-decision events before any persistence work; the amendment text is 2A scope.
2. **Retention values:** concrete durations under the D-08 process (IC-001 default retain-all until named).
3. **Gate condition:** whether durable routing audit becomes a formal gate §5 activation condition (it is not
   one today, and this document does not add one) — decided at the DBR-AR-2E / activation review.
4. **Least-privilege writer role DDL:** the INSERT+SELECT-only role (B-7 forward proposal) — 2B scope.
5. **Tenant-facing read surface:** none exists and none is authorized; any future one needs its own amendment.
6. **Gateway class-3 durable wiring:** which slice wires the gateway emitter to the same sink (2C or a sibling).
7. **Sink-availability administrative events:** whether the Control Plane records `AuditSink*` transitions in
   the administrative audit vocabulary (events.py lockstep change).

## 19. Non-goals

This V1 does not implement a durable audit adapter; does not add a table, schema, or migration; does not apply
DDL; does not add production wiring, an API endpoint, a queue, or an outbox; does not change runtime behavior,
routing semantics, denial disclosure, authentication, or authorization; does not alter B5-BLK-4, the MVP
acceptance, any blocker or blocker count, the activation gate, or the Lovable status; and does not begin Lovable,
AI-Agent, billing, or deployment work.

## 20. Stop rails

Binding on every DBR-AR-2 slice: no runtime DDL; no threading (AT-D15T1-10); no cross-service import; no secret
value, raw DSN, token, or private key in any record, log, error, or evidence artifact; no new public disclosure
through denials; no tenant-DB audit writes; no silent fail-open for allowed routes; no production activation and
no gate-posture change without its own Dan-authorized decision; standing topology mutations only under an
explicitly authorized runbook step.

## 21. Next governed step

**Next implementation slice after DBR-AR-2B is fully merged,
post-merge verified, and target-cleaned:
DBR-AR-2C — composition and failure semantics.**

DBR-AR-2C (composition and failure semantics) is not yet authorized; it requires its own GPT PRD,
readiness review, and Dan START-GATE, following the standard loop (independent pre-merge verify → Dan human
merge → post-merge verify → target-only cleanup).
