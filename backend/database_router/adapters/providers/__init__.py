"""Concrete database_router providers (vendor / database-driver containment zone).

The psycopg connection factory imports a real PostgreSQL driver and is exercised
only against a live database (not by the stdlib suite). The in-memory audit sink and
env/file tenant SecretStore are pure stdlib. Any tenant-database driver import is
confined to this zone (Driver Containment Standard; PRD-P4-R2 C).
"""
from __future__ import annotations
