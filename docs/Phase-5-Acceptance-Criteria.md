# Build Phase 5 — Acceptance Criteria (Import Service + Phase-6 Lineage Write-Path Slice)

**PRD:** SP2-P5-E1 · **Basis:** PRD-P5-R2 standards (A–L); IC-003/IC-004/IC-002/IC-005; D-04/D-06/D-08/D-09/D-13/D-14/D-16/D-17/D-18/D-19/D-20/D-21/D-22/D-23/D-25/D-31.
**Verification mode:** pure-stdlib behavior + architecture suites (Python 3.8), standalone and pytest. `Result` cites the proving test(s). The import flow is exercised end-to-end with the **real** lineage hash-chaining emit.

Legend: **PASS** verified green · **N/A** out of Phase-5 scope.

---

## A. Import

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-IM-01 | CSV import creates tenant-owned copies + lineage | IC-003; D-18 | `import_service/test_sources.test_csv_import_creates_tenant_copy_and_lineage` | **PASS** |
| AC-IM-02 | JSON import creates tenant-owned copies | IC-003; D-18 | `test_sources.test_json_import_creates_tenant_copy` | **PASS** |
| AC-IM-03 | Global Directory import copies Global records (Global Record ≠ Tenant Record) | IC-003; D-31 | `test_sources.test_directory_import_copies_global_records` | **PASS** |
| AC-IM-04 | Import writes only via the routed session (no DB driver / no router import) | PRD-P5-R2 B | `architecture/test_phase5_import_service` | **PASS** |

## B. Lineage (write-path slice)

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-LN-01 | Per-tenant append-only chain (seq + prev_marker links) | IC-004; D-22/D-23/D-25 | `lineage_service/test_emit.test_emit_appends_a_per_tenant_chain` | **PASS** |
| AC-LN-02 | Integrity marker binds content (tamper-evident) | D-23 | `test_emit.test_marker_binds_content_tamper_evident` | **PASS** |
| AC-LN-03 | Emit runs only on the injected session (no autonomous connection) | PRD-P5-R2 D | `test_emit.test_emit_runs_only_on_the_provided_session` | **PASS** |
| AC-LN-04 | Import never hash-chains / persists lineage itself | E5 | `architecture/test_phase5_import_service` (+ chain owned by lineage_service) | **PASS** |

## C. Atomic Provenance

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-AP-01 | Data + lineage + checkpoint commit together | IC-003/IC-004; PRD-P5-R2 K | `import_service/test_atomic_provenance.test_commit_together` | **PASS** |
| AC-AP-02 | Lineage failure rolls the whole batch back (no data without provenance) | IC-004 | `test_atomic_provenance.test_rollback_together_on_lineage_failure` | **PASS** |

## D. Directory

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-DR-01 | Directory record read; unknown kind/record → consistent 404 | D-31; Gov §I | `control_plane/test_directory_read_api.test_directory_record_lookup` / `test_dispatcher_directory_routes` | **PASS** |
| AC-DR-02 | Cursor pagination (expand-only, bounded) | PRD-P5-R2 E | `test_directory_read_api.test_directory_cursor_pagination` | **PASS** |
| AC-DR-03 | Real HTTP transport (control-plane server ↔ import directory client) | PRD-P5-R2 E (R-P5-04) | `test_directory_read_api.test_directory_http_roundtrip_best_effort` | **PASS** |
| AC-DR-04 | No tenant-owned data returned (global reference only) | D-31 | read model = directory view only | **PASS** |

## E. Validation

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-VL-01 | Missing natural key rejected (structural) | D-09 | `import_service/test_validation.test_missing_natural_key_rejected` | **PASS** |
| AC-VL-02 | Unsupported type rejected | D-09 | `test_validation.test_unsupported_type_rejected` | **PASS** |
| AC-VL-03 | Control chars rejected (sanitization) | D-09 | `test_validation.test_control_chars_rejected` | **PASS** |
| AC-VL-04 | PII classification | D-09 | `test_validation.test_pii_is_classified` | **PASS** |
| AC-VL-05 | Errors are non-sensitive (no values) / safe logging | D-09; K5 | `test_validation.test_validation_error_is_non_sensitive` | **PASS** |
| AC-VL-06 | Invalid rejected, valid still committed (partial failure) | D-21 | `test_validation.test_import_rejects_invalid_but_commits_valid_records` | **PASS** |

## F. Checkpoint / Resume

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-CK-01 | Batched, tenant-resident checkpoints | D-21 | `import_service/test_checkpoint_resume` | **PASS** |
| AC-CK-02 | Crash mid-import → resume from last committed batch; no duplication; contiguous chain | D-21 | `test_checkpoint_resume.test_failure_then_resume_completes_without_duplication` | **PASS** |

## G. Idempotency

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-ID-01 | Operation-key replay → existing result (safe no-op) | D-20 | `import_service/test_idempotency.test_operation_key_replay_is_safe_no_op` | **PASS** |
| AC-ID-02 | Per-record natural-key reconciliation → no duplicate rows | D-20 | `test_idempotency.test_natural_key_reconciliation_no_duplicate_rows` | **PASS** |
| AC-ID-03 | Idempotency is tenant-scoped + tenant-resident | D-20; Gov §F | job/idem/checkpoint written via session (tenant DB) | **PASS** |

## H. Audit

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-AU-01 | Requested / Started / Completed events | IC-003 | `import_service/test_capacity_audit.test_lifecycle_audit_events` | **PASS** |
| AC-AU-02 | Resumed / Failed events | IC-003 | `test_checkpoint_resume` (resumed) / `test_atomic_provenance` (failed) | **PASS** |
| AC-AU-03 | Operational audit distinct from lineage | IC-003/IC-004 | separate sink; no lineage in audit | **PASS** |

## I. Security

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-SE-01 | Import resolves no credentials; routes via session only | D-14; D2/D3 | `architecture/test_phase5_import_service` | **PASS** |
| AC-SE-02 | No secret literals in import_service | Gov §B | `architecture/test_phase5_import_service.test_import_service_has_no_secret_literals` | **PASS** |
| AC-SE-03 | Non-routable tenant denies (fail-closed) | IC-002 | `test_capacity_audit.test_not_routable_tenant_propagates_denial` | **PASS** |
| AC-SE-04 | Source credentials by reference (D-14) — v1 sources carry none | D-14; PRD-P5-R2 J | source_ref is a reference; no creds in payload/lineage/audit | **PASS** |

## J. Traceability

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-TR-01 | import_service + lineage_service declare governing contracts; marked built | Gov | `architecture/test_traceability` | **PASS** |
| AC-TR-02 | DAG preserved: import imports no service; lineage imports no router/import | Gov DAG | `architecture/test_phase5_import_service` / `test_dependency_boundaries` | **PASS** |

## K. Capacity

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-CP-01 | Import uses the BULK lane | D-13 | `import_service/test_capacity_audit.test_import_always_uses_the_bulk_lane` | **PASS** |
| AC-CP-02 | Bulk and interactive use separate bounded pools | D-13 | `database_router/test_capacity_lane.test_bulk_and_interactive_use_separate_pools` | **PASS** |
| AC-CP-03 | Bulk saturation does not starve interactive traffic | D-13/D-16 | `test_capacity_lane.test_bulk_saturation_does_not_starve_interactive` | **PASS** |

## L. Forward Compatibility

| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-FC-01 | Lineage model AI-ready (event_type/derivation_ref/parent chain) | D-02/D-25 | `shared/lineage.LineageIntent`; emit chain | **PASS** |
| AC-FC-02 | Routed session + lineage emit reusable by Phase 6 (query/retention) and analytics | PRD-P5-R2 L | shared ports `RoutedTenantSession`/`LineageEmitPort` | **PASS** |
| AC-FC-03 | Re-import appends attributable lineage (applied vs no-op) without mutating prior | D-20/D-23 | `test_idempotency.test_natural_key_reconciliation...` (noop lineage appended) | **PASS** |

---

## Out of Phase-5 scope (explicitly not implemented)
Lineage query/search/analytics/verification/retention APIs (Build Phase 6); AI Gateway/agents (IC-006); synchronization; cross-tenant queries — **N/A**.

## Verdict
All in-scope acceptance criteria **PASS**. Build Phase 5 is **COMPLETE WITH OBSERVATIONS** (see the PRD-P5-E1 deliverables report: the PgRoutedSession provider + psycopg paths compile but are exercised only against a live PostgreSQL; the D-09 minimize/tokenize layer depends on the standing D-08 values; ruff/mypy/import-linter/gitleaks remain uninstalled/unrun).
