"""api_gateway adapters — concrete port implementations.

Transport adapters (Authenticator/Database Router over HTTP) and the no-sink audit
emitter live under ``providers``. No database driver and no vendor SDK appear here
(IC-010 §X/Anti-Vendor-Lock-In; the gateway is edge-only).
"""

from __future__ import annotations
