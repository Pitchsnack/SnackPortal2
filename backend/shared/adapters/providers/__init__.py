"""Vendor-import containment zone — EMPTY in Build Phase 1.

This package is the ONLY location where vendor/cloud SDK imports are permitted
(governance F-1; CLAUDE.md anti-vendor-lock-in; D-14). No provider implementations
exist in Build Phase 1. Database drivers may appear only under the equivalent
`database_router/adapters/providers/**` zone.
"""
from __future__ import annotations
