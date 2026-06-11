"""database_router adapters. `providers/` holds concrete backends (routing-read
transport client, tenant connection factory, tenant SecretStore, audit sink); it is
the only place a tenant-database driver may be imported (Driver Containment Standard).
"""

from __future__ import annotations
