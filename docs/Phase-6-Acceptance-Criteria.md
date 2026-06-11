# Build Phase 6 — Acceptance Criteria (Lineage Service)

**PRD:** SP2-P6-E1 · **Basis:** PRD-P6-R2 standards A–K; IC-004 (primary) + IC-002/003/005; ADRs D-22/23/24/25/08/16/17/14/02/D-30.
**Verification mode:** pure-stdlib behavior + architecture suites (Python 3.8), standalone and pytest-shaped. Live-PostgreSQL guarantees are proven by the `requires_pg` suite (binding at P6-V1).

Legend: **PASS** verified green (stdlib) · **PENDING-PG** suite delivered, executes only against a live PostgreSQL (no PG in this environment) · **N/A** out of Phase-6 scope.

---

## A. Persistence
| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-P-01 | Append-only chain: per-tenant `seq` + `prev_marker` linkage; `segment_id`/`marker_version` carried | IC-004; D-22/23/25 | `lineage_service/test_emit.test_emit_appends_a_per_tenant_chain` | **PASS** |
| AC-P-02 | Records written only via the injected `RoutedTenantSession` (no DB driver/router import) | PRD-P6-R2 D; §9 | `architecture/test_phase6_lineage_service`; `test_emit.test_emit_runs_only_on_the_provided_session` | **PASS** |
| AC-P-03 | Atomic provenance preserved: emit unchanged contract; Phase-5 write path green | IC-003/IC-004; §5 | `import_service/test_atomic_provenance` (regression) | **PASS** |
| AC-P-04 | Tenant-resident, tenant-scoped (chain never crosses tenants) | D-25; D-30 | `lineage_service/test_query.test_tenant_scoped_isolation` | **PASS** |

## B. Verification
| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-V-01 | Clean chain verifies; evidence (`VerificationReport`) produced | IC-004 D-23; §11 | `lineage_service/test_verification.test_clean_chain_verifies` | **PASS** |
| AC-V-02 | Verification is read-only, tenant-scoped, service-independent | PRD-P6-R2 E (E1-E5) | `architecture/test_phase6_lineage_service`; `test_verification` | **PASS** |
| AC-V-03 | Broken `prev_marker` linkage detected | D-23 | `test_verification.test_broken_link_detected` | **PASS** |

## C. Tamper Detection
| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-TD-01 | Mutated content → recomputed marker mismatch detected | D-23 | `test_verification.test_tamper_detected` | **PASS** |
| AC-TD-02 | Marker reproduces over canonical content; any change is detectable | D-23; PRD-P6-R2 C | `test_emit.test_marker_binds_content_tamper_evident` | **PASS** |
| AC-TD-03 | Canonicalization single-sourced (no re-implementation) | PRD-P6-R2 C (P6-OBS-3) | `test_canonical`; `architecture/test_phase6_lineage_service.test_canonicalization_is_single_source` | **PASS** |

## D. Query
| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-Q-01 | Lookup by record id and by `target_ref` | §10 (G1) | `test_query.test_get_by_id` / `test_for_record` | **PASS** |
| AC-Q-02 | Import-history lookup by `derivation_ref` | §10 (G2) | `test_query.test_for_import_filters` | **PASS** |
| AC-Q-03 | Expand-only keyset pagination by `seq` | PRD-P6-R2 D (G5) | `test_query.test_keyset_pagination` | **PASS** |
| AC-Q-04 | Reads via shared `LineageReadSession`; no `lineage_service → database_router` import | PRD-P6-R2 D; §10 | `architecture/test_phase6_lineage_service` | **PASS** |

## E. Search
| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-S-01 | Filter by event_type / operation / derivation_ref / actor_ref | §13 | `test_search.test_search_by_event_type` / `test_search_by_derivation_and_actor` | **PASS** |
| AC-S-02 | Paginated, tenant-scoped | §13 | `test_search.test_search_pagination` | **PASS** |

## F. Graph
| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-G-01 | Ancestor traversal to import root(s) | D-25; §12 | `test_graph.test_ancestors_trace_to_root` | **PASS** |
| AC-G-02 | Descendant traversal | D-25; §12 | `test_graph.test_descendants_from_root` | **PASS** |
| AC-G-03 | Node/depth bounds (truncation); read-only; tenant-scoped; no external graph DB | PRD-P6-R2 G | `test_graph.test_node_limit_truncates`; `architecture/test_phase6_lineage_service` | **PASS** |

## G. Retention
| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-R-01 | Safe default = retain-all (nothing eligible) with no D-08 values | D-24/D-08; §14 | `test_retention.test_default_retain_all` | **PASS** |
| AC-R-02 | `RetentionEvaluated` audited | D-24; §17 | `test_retention.test_default_retain_all` | **PASS** |
| AC-R-03 | Expiry / deletion / crypto-erase disabled (raise) until D-08 values | §14 | `test_retention.test_expiry_and_crypto_erase_disabled` | **PASS** |

## H. Archival
| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-AR-01 | Segment summary (first/last seq, opening/closing marker, count) derived read-only | D-24/D-25; §15 | `test_segmentation.test_current_segment_summary` | **PASS** |
| AC-AR-02 | `ArchivePrepared` audited; archive-ready summary | §15/§17 | `test_segmentation.test_prepare_archive_audits` | **PASS** |
| AC-AR-03 | Cross-segment chain continuity check | D-25 | `test_segmentation.test_verify_continuity` | **PASS** |

## I. Append-Only
| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-AO-01 | No UPDATE/DELETE API at the session vocabulary | PRD-P6-R2 A | `shared/session.py` (no update/delete verb); `architecture/test_phase6_lineage_service` | **PASS** |
| AC-AO-02 | DB-level UPDATE/DELETE/TRUNCATE rejection (trigger) | D-23 (V-OBS-1) | `requires_pg/test_pg_append_only` | **PENDING-PG** |
| AC-AO-03 | Least-privilege role cannot mutate lineage | PRD-P6-R2 A.2 | `requires_pg/test_pg_privilege` | **PENDING-PG** |

## J. Security / Disclosure
| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-SEC-01 | No DB drivers / no secret literals in lineage_service | Gov §B; §18 | `architecture/test_phase6_lineage_service` | **PASS** |
| AC-SEC-02 | Chain key by D-14 reference; never stored in lineage; `SecretValue` redacted | D-14 | `lineage_service/emit.py`; `shared/secrets.py` | **PASS** |
| AC-SEC-03 | Verification evidence non-sensitive (hashes/seq/ids; no payloads) | IC-004; §11 | `models.VerificationFinding/Report`; `test_verification` | **PASS** |
| AC-SEC-04 | Authorization (`lineage:read`/`lineage:verify`) decided by caller; service consumes RequestContext only | IC-005; §16 | `query.READ_PERMISSION` / `verification.VERIFY_PERMISSION` (declared, not enforced here) | **PASS** |

## K. Audit
| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-AU-01 | `LineageWritten` on emit (operational; ≠ lineage) | IC-002; §17 | `test_emit.test_emit_audits_lineage_written` | **PASS** |
| AC-AU-02 | `LineageVerified` / `ChainBroken` on verify | IC-002 D-23; §17 | `test_verification` (both paths) | **PASS** |
| AC-AU-03 | `RetentionEvaluated` / `ArchivePrepared` | IC-002 D-24; §17 | `test_retention` / `test_segmentation` | **PASS** |

## L. Traceability
| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-T-01 | lineage_service declares governing contracts + IMPLEMENTS_BEHAVIOR | Gov | `architecture/test_traceability` | **PASS** |
| AC-T-02 | DAG preserved (no service-to-service import; shared-leaf) | Gov DAG | `architecture/test_dependency_boundaries`; `test_phase6_lineage_service` | **PASS** |

## M. PostgreSQL Evidence (binding at P6-V1)
| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-PG-01 | Append-only UPDATE/DELETE/TRUNCATE rejection on live PG | §19 | `requires_pg/test_pg_append_only` | **PENDING-PG** |
| AC-PG-02 | `UNIQUE(seq)` fork prevention + advisory lock on live PG | §19 | `requires_pg/test_pg_chain_serialization` | **PENDING-PG** |
| AC-PG-03 | Recursive-CTE ancestor/descendant traversal on live PG | §19 | `requires_pg/test_pg_traversal` | **PENDING-PG** |
| AC-PG-04 | Least-privilege role enforcement on live PG | §19 | `requires_pg/test_pg_privilege` | **PENDING-PG** |

## N. Forward Compatibility
| ID | Description | Governing | Verification | Result |
|---|---|---|---|---|
| AC-FC-01 | AI-ready: `event_type=ai-derivation` reserved; `parent_lineage_ref` graph accommodates AI nodes (no AI built) | D-02/D-25 | `canonical`/`models` (event_type open); `graph` traversal | **PASS** |
| AC-FC-02 | `marker_version` enables non-breaking canonicalizer evolution | PRD-P6-R2 C | `test_canonical.test_unknown_marker_version_raises` | **PASS** |
| AC-FC-03 | Read API role-pluggable for portal/analytics/search/reporting consumers | §N (R1) | shared `LineageReadSession`; tenant-scoped reads | **PASS** |

---

## Out of Phase-6 scope (explicitly not implemented)
AI Gateway / agents (IC-006, D-02); analytics engine; cross-tenant queries (IC-007); synchronization; business reporting; **enabling** expiry/erasure (gated on D-08 values) — **N/A**.

## Verdict
All in-scope stdlib criteria **PASS** (48 test files green; no Phase 2–5 regressions). Build Phase 6 is **COMPLETE WITH OBSERVATIONS**: the **PENDING-PG** criteria (AC-AO-02/03, AC-PG-01..04) require a live PostgreSQL — the `requires_pg` suite is delivered and ready, but no PostgreSQL/Docker exists in this environment, so live-PG evidence is carried to **P6-V1** (per PRD-P6-R2 §K). The D-08 retention values remain a standing business/legal action; the safe default (retain-all) governs until they are named.
