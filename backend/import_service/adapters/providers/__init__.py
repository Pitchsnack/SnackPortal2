"""Concrete import_service providers (source adapters + transport clients).

Pure stdlib: CSV (`csv`), JSON (`json`), Global Directory (transport via DirectoryReadPort),
and a urllib Directory read client. No database driver, no vendor SDK, no tenant writes.
"""
from __future__ import annotations
