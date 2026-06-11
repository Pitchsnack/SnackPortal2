"""shared — SnackPortal2 cross-cutting library (vendor-neutral dependency leaf).

Build Phase 1: ports (interfaces) and shapes only. Pure standard library; imports
no service package and no vendor/cloud SDK. Admission to this package is governed
by the Shared Package Admission Policy (governance E): only cross-cutting concerns
consumed by >=2 services and owned by no single contract belong here.
"""
from __future__ import annotations

BUILD_PHASE = 1
IMPLEMENTS_BEHAVIOR = False
