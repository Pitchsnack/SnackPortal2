"""PostgreSQL tenant schema applicator (D15-ARCH-SPEC-01 §8 Step 2b; PRD 07B; D-15).

Control-plane-owned. After a tenant database is provisioned (CREATE DATABASE by the
`ProvisioningOperator`) and BEFORE the verification gate runs, this applies the tenant
database's schema so the readiness probe can observe `schema_version`. It applies the EXISTING,
reviewed DDL templates — `infrastructure/db/provisioning/00[1-3]` then
`infrastructure/db/lineage/00[1-3]` — and authors NO DDL of its own.

ATOMIC + IDEMPOTENT + FAIL-CLOSED:
* all templates are applied in a SINGLE transaction; any error rolls the whole transaction back
  (NO partial schema is committed) and raises `TenantSchemaApplicationError` — the onboarding
  orchestrator then leaves the tenant not-Ready (never routable);
* every applied statement is `CREATE … IF NOT EXISTS` / `DO`-guarded role creation / `GRANT`
  / `REVOKE` / `CREATE OR REPLACE`, so a re-apply is a no-op.

CONTROLLED NON-PRODUCTION ONLY. The per-tenant credential is resolved in-memory via the
SecretStore (D-14) and never logged or returned; the database driver import is confined to this
provider zone (Driver Containment Standard). Not exercised by the stdlib unit suite.
"""

from __future__ import annotations

import pathlib
from typing import List, Optional, Sequence

import psycopg  # type: ignore  # noqa: F401  (driver import confined to this zone)

from control_plane.provisioning import TenantSchemaApplicationError, TenantSchemaApplicator
from shared.secrets import SecretRef, SecretStore

# Repo root from this module: providers -> adapters -> control_plane -> backend -> ROOT.
_DB = pathlib.Path(__file__).resolve().parents[4] / "infrastructure" / "db"


def default_tenant_schema_ddl_paths() -> List[pathlib.Path]:
    """The canonical tenant-database schema templates, in apply order (provisioning then lineage).

    These are the EXISTING reviewed DDL files; the applicator authors none of them and never
    modifies them (read-only)."""
    return [
        _DB / "provisioning" / "001_tenant_database.sql",
        _DB / "provisioning" / "002_distinctness_sentinel.sql",
        _DB / "provisioning" / "003_provisioning_role.sql",
        _DB / "lineage" / "001_lineage_schema.sql",
        _DB / "lineage" / "002_append_only.sql",
        _DB / "lineage" / "003_roles.sql",
    ]


class PostgresTenantSchemaApplicator(TenantSchemaApplicator):
    def __init__(
        self,
        secret_store: SecretStore,
        *,
        ddl_paths: Optional[Sequence[pathlib.Path]] = None,
        timeout: float = 5.0,
    ) -> None:
        self._secrets = secret_store
        self._ddl_paths = list(ddl_paths) if ddl_paths is not None else default_tenant_schema_ddl_paths()
        self._timeout = timeout

    def apply_schema(self, tenant_id: str, *, target: str, association_ref: SecretRef) -> None:
        descriptor: Optional[str] = None
        conn = None
        try:
            descriptor = self._secrets.resolve(association_ref).material  # in-memory only
            # Transaction mode (no autocommit): all templates apply within ONE transaction so a
            # failure commits no partial schema. None of the templates use a non-transactional
            # statement (no CREATE DATABASE / CREATE INDEX CONCURRENTLY / VACUUM).
            conn = psycopg.connect(descriptor, connect_timeout=int(self._timeout))
            with conn.cursor() as cur:
                for path in self._ddl_paths:
                    cur.execute(path.read_text(encoding="utf-8"))  # template bytes, never modified
            conn.commit()  # single atomic commit across all templates
        except Exception:
            if conn is not None:
                try:
                    conn.rollback()  # fail-closed: no partial schema is committed
                except Exception:
                    pass
            # Raise a non-sensitive error; never surface the descriptor or driver internals (D-14).
            raise TenantSchemaApplicationError("tenant schema application failed") from None
        finally:
            descriptor = None  # drop the resolved credential reference promptly
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
