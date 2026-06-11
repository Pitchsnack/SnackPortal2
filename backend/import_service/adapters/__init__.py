"""import_service adapters. `providers/` holds concrete source adapters (Global
Directory transport, CSV, JSON), the Directory read transport client, and the audit
sink. No adapter writes tenant data directly (D-18); tenant writes go through the
caller-injected RoutedTenantSession only.
"""
from __future__ import annotations
