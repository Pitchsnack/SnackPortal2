"""Concrete ControlStore providers (vendor containment zone).

Build Phase 2 ships an in-memory provider (pure stdlib). A portable PostgreSQL
Control-DB provider is a deferred persistence-binding step; when added, any database
driver import is confined to this zone.
"""

from __future__ import annotations
