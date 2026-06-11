"""lineage_service — SnackPortal2 (Build Phase 6 — full Lineage Service).

Tenant-resident data provenance (IC-004; D-22-D-25; D-08 retention mechanism). Owns:
- WRITE path: a minimal lineage record (D-22) appended with a per-tenant cryptographic
  hash-chain integrity marker (D-23) on the caller's RoutedTenantSession, atomic with data
  (IC-004); the keyed-hash key is a D-14 reference; marker built only via `canonical`.
- READ paths: query, search, hash-chain verification + tamper detection, and per-tenant
  provenance-graph traversal (D-25) over an injected LineageReadSession — never opening a
  database connection itself.
- Retention/archival FRAMEWORK (D-24): safe default retain-all; expiry disabled until D-08
  values; chain segmentation metadata (archival-ready). Operational audit is DISTINCT from
  lineage (IC-002). No service imports (runs on injected sessions; Standard D).
"""

from __future__ import annotations

GOVERNING_CONTRACTS = ["IC-004", "IC-002", "IC-005", "D-22", "D-23", "D-24", "D-25", "D-14"]
BUILD_PHASE = 6
IMPLEMENTS_BEHAVIOR = True
