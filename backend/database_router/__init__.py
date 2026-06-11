"""database_router — SnackPortal2 Database Router (Build Phase 4).

Registry-authoritative tenant→database resolution and per-tenant connection
management (IC-005 / IC-002; D-07, D-13, D-14, D-30): consumes the authenticated
RequestContext, resolves the control-plane routing view over a transport port,
gates on readiness + schema version (D-16/D-17), resolves per-tenant credentials by
reference at connect time (D-14), and binds exactly one tenant database per request
with no cross-tenant connection reuse. Performs no authentication, authorization,
import, or lineage. This is the ONLY service permitted to access tenant databases;
database drivers may appear only under `database_router/adapters/providers/**`.
"""
from __future__ import annotations

GOVERNING_CONTRACTS = [
    "IC-005", "IC-002", "IC-001",
    "D-04", "D-07", "D-11", "D-13", "D-14", "D-16", "D-17", "D-30",
]
BUILD_PHASE = 4
IMPLEMENTS_BEHAVIOR = True
