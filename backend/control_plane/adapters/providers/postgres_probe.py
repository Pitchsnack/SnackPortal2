"""PostgreSQL tenant-database verification probe (Build Phase 4; Standard PRD-P4-R2 G).

Control-plane-owned, single-shot probe used by VerifyTenant / ReassociateDatabase to
check a tenant database's connectivity + observed schema version. Opens a short-lived
connection (NOT a serving pool), reads the observed schema version, and closes. It
does not import or call database_router — keeping the dependency graph acyclic.

The per-tenant credential is resolved in-memory at probe time via the SecretStore
(D-14) and never returned. The database driver import is confined to this provider
zone (Driver Containment Standard). Not exercised by the stdlib unit suite.
"""

from __future__ import annotations

from typing import Optional

import psycopg  # type: ignore  # noqa: F401  (driver import confined to this zone)

from control_plane.verification import ProbeResult, TenantDatabaseProbe
from shared.secrets import SecretRef, SecretStore

# Conventional, portable place to read the application schema version of a tenant DB.
SCHEMA_VERSION_QUERY = "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1"


class PostgresTenantProbe(TenantDatabaseProbe):
    def __init__(self, secret_store: SecretStore, *, timeout: float = 2.0) -> None:
        self._secrets = secret_store
        self._timeout = timeout

    def probe(self, association_ref: SecretRef) -> ProbeResult:
        descriptor: Optional[str] = None
        conn = None
        try:
            descriptor = self._secrets.resolve(association_ref).material  # in-memory only
            conn = psycopg.connect(descriptor, connect_timeout=int(self._timeout))
            with conn.cursor() as cur:
                cur.execute(SCHEMA_VERSION_QUERY)
                row = cur.fetchone()
            observed = str(row[0]) if row and row[0] is not None else None
            return ProbeResult(reachable=True, observed_schema_version=observed)
        except Exception:
            # Fail closed; never surface the descriptor or DB topology.
            return ProbeResult(reachable=False, observed_schema_version=None)
        finally:
            descriptor = None  # drop the resolved credential reference promptly
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
