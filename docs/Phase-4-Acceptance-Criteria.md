# Build Phase 4 — Acceptance Criteria (Database Router & Control-Plane Production Completion)

**PRD:** SP2-P4-E1 · **Basis:** PRD-P4-R2 standards (A–M); IC-001/002/005; IC-003/004 (forward-compat); D-04/D-07/D-11/D-13/D-14/D-16/D-17/D-30.
**Verification mode:** pure-stdlib behavior + architecture suites (Python 3.8), run standalone and under pytest. `Result` cites the proving test(s).

Legend: **PASS** verified green · **N/A** out of Phase-4 scope.

---

## A. Routing

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-R-01 | A request with an active tenant routes to exactly one tenant database | IC-005; D-04 | `database_router/test_routing_determination.test_tenant_request_routes_to_one_tenant_database` | **PASS** |
| AC-R-02 | A CONTROL-scoped request (null tenant) routes to the Control DB, never a tenant DB | IC-005; D-32 | `test_routing_determination.test_control_request_routes_to_control_database` | **PASS** |
| AC-R-03 | Null active tenant for a tenant-scoped principal is denied (403) | IC-005 | `test_routing_determination.test_null_tenant_non_control_is_forbidden` | **PASS** |
| AC-R-04 | Bootstrap Phase 0 never resolves a tenant database | IC-001; D-01 | `test_routing_determination.test_bootstrap_phase0_never_routes_a_tenant_database` | **PASS** |
| AC-R-05 | Routing input is `RequestContext` only (no `auth_router`/`control_plane` import) | PRD-P4-R2 H | `architecture/test_phase4_database_router.test_database_router_imports_no_other_service` | **PASS** |

## B. Isolation

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-I-01 | Two tenants get distinct connections and distinct pools | D-30 L3 | `test_connection_isolation.test_two_tenants_get_distinct_connections_and_pools` | **PASS** |
| AC-I-02 | A connection is reused only within its own tenant | D-13 | `test_connection_isolation.test_same_tenant_reuses_its_own_connection` | **PASS** |
| AC-I-03 | A connection is never reused across tenants | D-30 | `test_connection_isolation.test_connection_never_reused_across_tenants` | **PASS** |
| AC-I-04 | Pools are keyed by (tenant_id, association_version) — version separates pools | D-13; D-11 | `test_connection_isolation.test_association_version_separates_pools` | **PASS** |
| AC-I-05 | A mis-bound (wrong-tenant) connection is rejected and closed; routing denies | D-30 | `test_connection_isolation.test_misbound_connection_is_rejected_and_closed` | **PASS** |

## C. Control Plane

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-CP-01 | Routing read exposes association **reference** + expected schema version; never credentials | PRD-P4-R2 B; D-14 | `control_plane/test_routing_read_api.test_routing_view_exposes_reference_not_credentials` | **PASS** |
| AC-CP-02 | Tenant-state read stays minimal (no association ref) — least disclosure | Governance §I | `test_routing_read_api.test_tenant_state_is_minimal_no_association` | **PASS** |
| AC-CP-03 | Unknown tenant returns a consistent 404 (no existence leak) | D-11; Governance §I | `test_routing_read_api.test_dispatcher_paths_and_consistent_denial` | **PASS** |
| AC-CP-04 | Real HTTP transport round-trips (control-plane server ↔ router client) | PRD-P4-R2 B (O-2) | `test_routing_read_api.test_http_transport_roundtrip_best_effort` | **PASS** |
| AC-CP-05 | Database Router consumes the control plane only over a transport port | PRD-P4-R2 H | `test_resolution_and_gating.test_control_plane_unavailable_fails_closed` | **PASS** |
| AC-CP-06 | PostgreSQL ControlStore provider implemented behind the port; domain stays persistence-agnostic | D-07; PRD-P4-R2 C | `control_plane/adapters/providers/postgres_store.py`; `architecture/test_phase2_control_plane` | **PASS** |

## D. Secrets

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-S-01 | Per-tenant credential resolved via SecretStore at connect time | D-14 | `test_credentials.test_credential_resolved_at_connect_time` | **PASS** |
| AC-S-02 | Pooled reuse does not re-resolve the secret (resolve only on connect) | D-14 | `test_credentials.test_credential_not_re_resolved_on_pooled_reuse` | **PASS** |
| AC-S-03 | Credentials never appear in the routing result or audit | D-14 | `test_credentials.test_credential_never_in_result_or_audit` | **PASS** |
| AC-S-04 | `SecretValue` repr is redacted | D-14 | `test_credentials.test_secret_value_repr_is_redacted` | **PASS** |
| AC-S-05 | Missing secret denies as a non-leaking `unavailable` | D-14; PRD-P4-R2 M | `test_credentials.test_missing_secret_denies_without_leak` | **PASS** |
| AC-S-06 | Tenant SecretStore is allow-listed to `tenant/*` refs (least privilege) | D-14 | `test_credentials.test_tenant_secret_store_is_allow_listed_to_tenant_refs` | **PASS** |

## E. Schema

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-SC-01 | Routing denied (not_ready) when expected schema version is out of supported range | D-17 | `test_resolution_and_gating.test_schema_out_of_range_is_not_ready` | **PASS** |
| AC-SC-02 | VerifyTenant fails a tenant whose observed schema is out of range | D-17 | `control_plane/test_lifecycle_phase4.test_verify_schema_out_of_range_marks_failed` | **PASS** |

## F. Lifecycle

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-L-01 | VerifyTenant promotes a provisioned tenant to Ready (via the verification probe) | IC-002 | `test_lifecycle_phase4.test_verify_promotes_provisioning_to_ready` | **PASS** |
| AC-L-02 | VerifyTenant marks Failed when the tenant DB is unreachable | IC-002 | `test_lifecycle_phase4.test_verify_unreachable_marks_failed` | **PASS** |
| AC-L-03 | ActivateTenant requires Verifying; rejects otherwise | IC-002 | `test_lifecycle_phase4.test_activate_requires_verifying` | **PASS** |
| AC-L-04 | ReactivateTenant restores Suspended → Verifying → Ready | IC-002 | `test_lifecycle_phase4.test_reactivate_suspended_to_ready` | **PASS** |
| AC-L-05 | ReassociateDatabase requires a version increment and re-enters Verifying | IC-002; D-11 | `test_lifecycle_phase4.test_reassociate_requires_version_increment_and_reverifies` | **PASS** |
| AC-L-06 | Verification probe is control-plane-owned; no `control_plane → database_router` edge | PRD-P4-R2 G | `architecture/test_phase4_database_router.test_control_plane_does_not_import_database_router` | **PASS** |

## G. Audit

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-A-01 | Successful and denied routes are audited (references only) | D-30 L4 | `test_routing_determination` / `test_credentials.test_missing_secret_denies_without_leak` | **PASS** |
| AC-A-02 | Cross-tenant-binding anomalies are audited without secrets | D-30 L4 | `test_connection_isolation.test_misbound_connection_is_rejected_and_closed` (+ router `IsolationAnomaly`) | **PASS** |
| AC-A-03 | Every Phase-4 lifecycle transition is audited | IC-002 | `test_lifecycle_phase4` (action assertions) | **PASS** |

## H. Schema gating / Cache

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-C-01 | Routing-view cache hit avoids re-read within TTL | D-11 | `test_cache.test_cache_hit_avoids_reread_within_ttl` | **PASS** |
| AC-C-02 | TTL expiry triggers a re-read (pull-based refresh) | D-11 | `test_cache.test_ttl_expiry_triggers_reread` | **PASS** |
| AC-C-03 | Explicit invalidation forces a re-read | D-11 | `test_cache.test_explicit_invalidation_forces_reread` | **PASS** |
| AC-C-04 | After re-association + invalidate, a Verifying tenant does not route (no stale routing) | D-11 | `test_cache.test_reassociation_then_invalidate_prevents_stale_routing` | **PASS** |

## I. Connection lifecycle

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-CL-01 | Pools are created lazily (only on first use) | D-13 | `test_connection_lifecycle.test_creation_is_lazy` | **PASS** |
| AC-CL-02 | Release rolls back, resets, and returns the connection to its own pool | D-13; D-30 | `test_connection_lifecycle.test_release_rolls_back_and_resets_then_pools` | **PASS** |
| AC-CL-03 | LRU idle eviction closes idle connections and drops empty pools | D-13 | `test_connection_lifecycle.test_lru_idle_eviction` | **PASS** |
| AC-CL-04 | A broken idle connection is discarded and replaced | D-13 | `test_connection_lifecycle.test_broken_idle_connection_is_replaced` | **PASS** |
| AC-CL-05 | A tenant's connection failure never falls back to another tenant | D-16; D-30 | `test_connection_lifecycle.test_failure_recovery_never_falls_back_to_another_tenant` | **PASS** |

## J. Security / Disclosure

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-SEC-01 | Canonical denial → HTTP mapping (404/403/503) is deliberate and consistent | PRD-P4-R2 M | `test_disclosure.test_http_status_mapping` / `test_denial_reason_codes` | **PASS** |
| AC-SEC-02 | Lifecycle → denial mapping is correct (authorized-member view) | IC-002; PRD-P4-R2 M | `test_disclosure.test_denial_for_state_mapping` | **PASS** |
| AC-SEC-03 | Denials carry no tenant id / DSN / host / credential detail | Governance §I | `test_disclosure.test_denial_carries_no_sensitive_detail` | **PASS** |
| AC-SEC-04 | No secret literals in database_router source | Governance §B (R-CI-6) | `architecture/test_phase4_database_router.test_database_router_has_no_secret_literals` | **PASS** |

## K. Traceability

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-T-01 | Every service declares governing contracts + IMPLEMENTS_BEHAVIOR; database_router now built | Governance | `architecture/test_traceability` | **PASS** |
| AC-T-02 | shared is a leaf; services remain independent (transport only) | Governance DAG | `architecture/test_dependency_boundaries` | **PASS** |

## L. Driver Containment

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-DC-01 | DB drivers appear only in `database_router/adapters/providers/**` and `control_plane/adapters/providers/**` | PRD-P4-R2 C | `architecture/test_vendor_and_db_containment.test_db_drivers_only_in_permitted_provider_zones` | **PASS** |
| AC-DC-02 | control_plane domain stays driver-free (drivers only in its provider zone) | E3/E4 | `architecture/test_phase2_control_plane` (amended) | **PASS** |
| AC-DC-03 | Vendor/cloud SDKs only under `**/adapters/providers/**` | CLAUDE.md 1–2 | `architecture/test_vendor_and_db_containment.test_vendor_imports_only_in_providers` | **PASS** |

## M. Forward Compatibility (IC-003 / IC-004)

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-FC-01 | Connection supports caller-controlled multi-statement transactions (atomic data+lineage) | IC-004; PRD-P4-R2 J | `test_end_to_end.test_full_router_flow` (begin/commit on resolved connection) | **PASS** |
| AC-FC-02 | Tenant SecretStore resolves arbitrary per-tenant refs (D-23 chain key reuse) | IC-004; D-23 | `EnvTenantSecretStore` (tenant/* allow-list) — `test_credentials.test_tenant_secret_store_is_allow_listed_to_tenant_refs` | **PASS** |
| AC-FC-03 | Pool keying admits separate bounded per-(tenant,version) capacity for heavy workloads | IC-003; D-13 | `pool.ConnectionPoolManager` (bounded `max_per_tenant`) — `test_connection_lifecycle` | **PASS** |

---

## Out of Phase-4 scope (explicitly not implemented)
Import processing (IC-003, Phase 5), lineage processing (IC-004, Phase 6), authorization/permission matrix, AI Gateway/agents (IC-006), cross-tenant queries (IC-007) — **N/A**.

## Verdict
All in-scope acceptance criteria **PASS**. Build Phase 4 is **COMPLETE WITH OBSERVATIONS** (see the PRD-P4-E1 deliverables report: live dev/CI tooling — ruff/mypy/import-linter/gitleaks — remains uninstalled and unrun; the psycopg-backed providers compile but are exercised only against a live PostgreSQL).
