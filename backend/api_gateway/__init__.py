"""api_gateway — SnackPortal2 (SCAFFOLD ONLY, Build Phase 1).

Single request entry point. No business logic, no authentication/authorization
decisions, no tenant routing, no database access (IC-005; CLAUDE.md). Ingress
middleware wiring is deferred to a later authorization.
"""

from __future__ import annotations

GOVERNING_CONTRACTS = ["IC-005", "IC-001"]
BUILD_PHASE = 1
IMPLEMENTS_BEHAVIOR = False
