"""api_gateway provider adapters (stdlib / transport only).

No database driver and no vendor SDK (Supabase/Lovable/cloud) may appear here or
anywhere in api_gateway — the gateway is edge-only and needs no vendor provider zone
(IC-010 Anti-Vendor-Lock-In; enforced by tests/architecture/test_phase7_api_gateway.py).
"""

from __future__ import annotations
