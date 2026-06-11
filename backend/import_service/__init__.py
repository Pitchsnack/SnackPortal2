"""import_service — SnackPortal2 Import Layer (Build Phase 5).

Global-to-tenant import-copy (IC-003): discrete one-directional copy (never sync), written
only to the single active tenant database through a shared RoutedTenantSession (no
database_router import). Each committed batch writes the tenant copy + lineage + checkpoint
in ONE transaction (atomic provenance, IC-004); lineage is emitted via the shared
LineageEmitPort (implemented by lineage_service — import never hash-chains). Hybrid
async/sync execution (D-19), operation + natural-key idempotency (D-20), batched/resumable
checkpoints (D-21), ingress validation/PII floor (D-09), pluggable source adapters
(Global Directory/CSV/JSON, D-18), separate bulk capacity (D-13). Performs no
authentication, authorization, routing, or credential resolution.
"""
from __future__ import annotations

GOVERNING_CONTRACTS = [
    "IC-003", "IC-004", "IC-002", "IC-005", "IC-001",
    "D-18", "D-19", "D-20", "D-21", "D-09", "D-08",
    "D-13", "D-16", "D-17", "D-22", "D-25", "D-31", "D-04", "D-06", "D-30", "D-14",
]
BUILD_PHASE = 5
IMPLEMENTS_BEHAVIOR = True
