"""PostgreSQL tenant schema applicator (D15-ARCH-SPEC-01 §8 Step 2b; PRD 07B; PRD 07B.1; D-15).

Control-plane-owned. After a tenant database is provisioned (CREATE DATABASE by the
`ProvisioningOperator`) and BEFORE the verification gate runs, this applies the tenant
database's schema so the readiness probe can observe `schema_version`. It applies the EXISTING,
reviewed DDL templates — `infrastructure/db/provisioning/00[1-3]`, then
`infrastructure/db/lineage/00[1-3]`, then (PRD 07B.1) the seven 07C tenant business templates
`infrastructure/db/tenant/00[1-7]` in TENANT_DDL_APPLY_ORDER — and authors NO DDL of its own.
After the DDL loop and inside the SAME transaction it seeds exactly one System Primary Agent
(PRD 07B.1; the `agents` table and its constraints are owned by PRD 07C V5 §9 — the seed shape
below is the one 001_agents.sql declares it accepts verbatim).

ATOMIC + IDEMPOTENT + FAIL-CLOSED:
* all templates AND the System Primary seed are applied in a SINGLE transaction; any error rolls
  the whole transaction back (NO partial schema is committed) and raises
  `TenantSchemaApplicationError` — the onboarding orchestrator then leaves the tenant not-Ready
  (never routable);
* every applied statement is `CREATE … IF NOT EXISTS` / `DO`-guarded role creation / `GRANT`
  / `REVOKE` / `CREATE OR REPLACE` / `DROP TRIGGER IF EXISTS`+recreate, and the seed is
  `INSERT … WHERE NOT EXISTS`, so a re-apply is a no-op (exactly one System Primary remains).

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
    """The canonical tenant-database schema templates, in apply order (provisioning, lineage,
    then the 07C tenant business schema).

    These are the EXISTING reviewed DDL files; the applicator authors none of them and never
    modifies them (read-only). PRD 07B.1 appends the seven 07C tenant business files AFTER the
    six 07B bootstrap templates, sequenced by citation to 07C's machine-readable authority
    (TENANT_DDL_APPLY_ORDER in tests/architecture/test_tenant_ddl_blob_drift.py — 07C owns the
    order and the blob pins; C7 Option 2: 07B.1 asserts membership/order, it duplicates no pins).
    Order is load-bearing (FK chain: agents <- ai_agents <- entities <- ownership <- links)."""
    return [
        _DB / "provisioning" / "001_tenant_database.sql",
        _DB / "provisioning" / "002_distinctness_sentinel.sql",
        _DB / "provisioning" / "003_provisioning_role.sql",
        _DB / "lineage" / "001_lineage_schema.sql",
        _DB / "lineage" / "002_append_only.sql",
        _DB / "lineage" / "003_roles.sql",
        _DB / "tenant" / "001_agents.sql",
        _DB / "tenant" / "002_ai_agents.sql",
        _DB / "tenant" / "003_startups.sql",
        _DB / "tenant" / "004_investors.sql",
        _DB / "tenant" / "005_deals.sql",
        _DB / "tenant" / "006_ownership.sql",
        _DB / "tenant" / "007_links.sql",
    ]


# PRD 07B.1: the System Primary seed — in-applicator, in-transaction, executed after the DDL loop
# and BEFORE the single commit (never a .sql template: 07C V5 §9.3 forbids seeding in DDL). This is
# verbatim the seed shape 001_agents.sql declares it accepts (§A.3: id is GENERATED ALWAYS and is
# deliberately omitted; display_name/created_at/updated_at defaulted; control_user_id nullable).
# Idempotent via WHERE NOT EXISTS. Under a concurrent two-connection race the loser surfaces a
# unique-index violation on ux_agents_single_system_primary, which apply_schema classifies
# fail-closed as TenantSchemaApplicationError with whole-transaction rollback (07C-AT-5).
_SYSTEM_PRIMARY_SEED_SQL = (
    "INSERT INTO agents (agent_kind, agent_status, supervised_by_agent_id) "
    "SELECT 'system_primary', 'active', NULL "
    "WHERE NOT EXISTS (SELECT 1 FROM agents WHERE agent_kind = 'system_primary')"
)


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
                # PRD 07B.1: seed exactly one System Primary Agent — same transaction, after all
                # DDL, before the single commit (idempotent; fail-closed on singleton conflict).
                cur.execute(_SYSTEM_PRIMARY_SEED_SQL)
            conn.commit()  # single atomic commit across all templates + the System Primary seed
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
