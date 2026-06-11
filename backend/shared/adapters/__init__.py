"""Adapter framework (vendor-neutral).

`interfaces` holds the generic provider/registry contracts. `providers` is the
SOLE location where vendor/cloud SDK imports are permitted (empty in Build
Phase 1). Business logic depends on ports; provider selection is config-driven via
a composition root (governance F-1 — Adapter Boundary Standard).
"""

from __future__ import annotations
