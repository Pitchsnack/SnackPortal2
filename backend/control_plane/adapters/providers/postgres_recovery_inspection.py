"""PostgreSQL recovery-inspection adapter (PRD 07D-2b.2b R1-1; IC-002 Recovery & Compensation).

Control-plane-owned, READ-ONLY implementation of ``RecoveryInspectionPort`` — the ONLY new
driver-zone file of the 2b.2b slice. It serves the compensation service's content-safety
census (§7 element 4), the orphan scan's ``pg_database`` inventory (§9), and the Control-DB
identity used by the never-droppable guard:

* ``list_candidate_databases`` — ``pg_database`` names inside the tenant namespace
  (``sp2_tenant_*``), via the EXISTING provisioning-admin secret binding.
* ``database_exists`` / ``inspect_database`` — per-target existence, physical identity
  (``system_identifier`` + ``datname:oid``), and the content census via an admin connection
  swapped to the target database: data-bearing relations across all non-system schemas
  (ordinary tables COUNTED; materialized views and foreign tables SURFACED uncounted —
  AT-PMV46-1) plus a large-object presence probe (synthetic ``pg_catalog.pg_largeobject``
  entry) — so physically stored content can never hide from the bootstrap-only census.
* ``control_database_name`` — ``current_database()`` observed through the EXISTING
  control-store secret binding (the Control-DB reference), never guessed from a name.

Dual construction is NOT offered: the composition root passes ``secrets=`` + ``ref=``
bindings only (D-14 — no DSN literal ever transits this adapter's constructor). Lazy:
construction performs no I/O and resolves no secret; every operation resolves the
reference in-memory, connects short-lived, and drops the descriptor immediately (never a
retained connection or credential). FAIL-CLOSED: any error returns ``None`` — a partial
census is never treated as safe. No DDL, no writes to any database, no sentinel writes.
The driver import is confined to this provider zone (Driver Containment Standard).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import psycopg  # type: ignore  # noqa: F401  (driver import confined to this zone)

from control_plane.provisioning import DEFAULT_TENANT_DB_PREFIX
from control_plane.recovery import DatabaseInspection, RecoveryInspectionPort
from shared.secrets import SecretRef, SecretStore

SYSTEM_ID_QUERY = "SELECT system_identifier::text FROM pg_control_system()"
DB_IDENTITY_QUERY = "SELECT current_database(), (SELECT oid FROM pg_database WHERE datname = current_database())"
DB_EXISTS_QUERY = "SELECT 1 FROM pg_database WHERE datname = %s"
# Data-bearing relations across all non-system schemas (the census input; read-only catalog
# scan). AT-PMV46-1 (PR #46 pre-merge V-1): the enumeration is WIDER than ordinary tables —
# materialized views (relkind 'm') store physical rows in their own heap and foreign tables
# (relkind 'f') represent externally-backed data; both MUST surface in the census (their
# names fall outside the bootstrap set ⇒ evidence ⇒ never dropped) instead of hiding from a
# relkind='r'-only scan. Plain views ('v') hold no storage; partitioned parents ('p') are
# fail-closed already (their leaf partitions are relkind 'r' and surface as extra names).
USER_TABLES_QUERY = (
    "SELECT n.nspname, c.relname, c.relkind::text FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE c.relkind IN ('r', 'm', 'f') AND n.nspname NOT IN ('pg_catalog', 'information_schema') "
    "AND n.nspname NOT LIKE 'pg\\_%' ORDER BY n.nspname, c.relname"
)
# AT-PMV46-1: large objects live in the pg_catalog.pg_largeobject system catalog — invisible
# to any user-relation scan. Their METADATA count proves data-bearing LOs exist; a nonzero
# (or unknowable) count surfaces as a SYNTHETIC census entry whose name is outside every
# bootstrap set by construction ⇒ classified evidence (non-empty), never dropped.
LARGE_OBJECT_PROBE_QUERY = "SELECT count(*) FROM pg_largeobject_metadata"
LARGE_OBJECT_CENSUS_ENTRY = "pg_catalog.pg_largeobject"
AGENTS_CENSUS_QUERY = "SELECT count(*), count(*) FILTER (WHERE agent_kind = 'system_primary') FROM public.agents"
SCHEMA_VERSIONS_QUERY = "SELECT DISTINCT version::text FROM public.schema_version ORDER BY 1"

# Identifiers safe to interpolate double-quoted into count(*) statements. Anything else is
# reported with a row count of -1 (unknown) — the census then classifies it fail-closed.
_SAFE_CENSUS_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


class PostgresRecoveryInspection(RecoveryInspectionPort):
    def __init__(
        self,
        *,
        admin_secrets: SecretStore,
        admin_ref: SecretRef,
        control_secrets: SecretStore,
        control_ref: SecretRef,
        timeout: float = 5.0,
    ) -> None:
        # Lazy: record the reference bindings only — no connection, no secret resolution here.
        self._admin_secrets = admin_secrets
        self._admin_ref = admin_ref
        self._control_secrets = control_secrets
        self._control_ref = control_ref
        self._timeout = timeout

    # -- connection helpers (short-lived; references only; never retained) ---------------
    def _connect(self, secrets: SecretStore, ref: SecretRef, *, dbname: Optional[str] = None) -> Any:
        descriptor: Optional[str] = None
        try:
            descriptor = secrets.resolve(ref).material  # in-memory only (D-14)
            if dbname is not None:
                # Swap only the database of the resolved admin descriptor (AT-PMV46-8): the
                # compensation path passes a RECOMPUTED target and the orphan scan passes
                # pg_database-listed names — both are safe here because make_conninfo quotes
                # the value and every query this adapter runs is read-only.
                descriptor = psycopg.conninfo.make_conninfo(descriptor, dbname=dbname)
            return psycopg.connect(descriptor, connect_timeout=int(self._timeout))
        finally:
            descriptor = None  # drop the resolved credential reference promptly

    # -- RecoveryInspectionPort ----------------------------------------------------------
    def list_candidate_databases(self) -> Optional[Sequence[str]]:
        conn = None
        try:
            conn = self._connect(self._admin_secrets, self._admin_ref)
            # LIKE-escape the prefix so its underscores match literally (not as wildcards).
            pattern = DEFAULT_TENANT_DB_PREFIX.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            with conn.cursor() as cur:
                cur.execute("SELECT datname FROM pg_database WHERE datname LIKE %s ORDER BY datname", (pattern,))
                return [str(row[0]) for row in cur.fetchall()]
        except Exception:
            return None  # fail closed; never a partial inventory
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def database_exists(self, target: str) -> Optional[bool]:
        conn = None
        try:
            conn = self._connect(self._admin_secrets, self._admin_ref)
            with conn.cursor() as cur:
                cur.execute(DB_EXISTS_QUERY, (target,))
                return cur.fetchone() is not None
        except Exception:
            return None  # fail closed (could not determine)
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def inspect_database(self, target: str) -> Optional[DatabaseInspection]:
        conn = None
        try:
            conn = self._connect(self._admin_secrets, self._admin_ref, dbname=target)
            with conn.cursor() as cur:
                cur.execute(SYSTEM_ID_QUERY)
                row = cur.fetchone()
                system_identifier = str(row[0]) if row and row[0] is not None else ""

                cur.execute(DB_IDENTITY_QUERY)
                row = cur.fetchone()
                if not row or row[0] is None or str(row[0]) != target:
                    return None  # the connection must observe the intended target (fail closed)
                database_identity = f"{row[0]}:{row[1] if row[1] is not None else ''}"

                cur.execute(USER_TABLES_QUERY)
                relations: List[Tuple[str, str, str]] = [(str(r[0]), str(r[1]), str(r[2])) for r in cur.fetchall()]
                user_tables: Dict[str, int] = {}
                for schema, table, relkind in relations:
                    qualified = f"{schema}.{table}"
                    if relkind == "r" and _SAFE_CENSUS_IDENTIFIER.fullmatch(schema) and _SAFE_CENSUS_IDENTIFIER.fullmatch(table):
                        cur.execute(f'SELECT count(*) FROM "{schema}"."{table}"')  # identifiers validated above
                        count_row = cur.fetchone()
                        user_tables[qualified] = int(count_row[0]) if count_row and count_row[0] is not None else -1
                    else:
                        # AT-PMV46-1: ONLY safe-named ORDINARY tables are counted. Matviews,
                        # foreign tables, and uncountable names report -1 (unknown) — the
                        # census then fails closed: an allowed NAME carrying -1 violates its
                        # count rule (incl. a matview shadowing a bootstrap name), and any
                        # other name is outside the bootstrap set ⇒ evidence, never dropped.
                        user_tables[qualified] = -1

                # AT-PMV46-1: large-object presence probe (see LARGE_OBJECT_CENSUS_ENTRY).
                cur.execute(LARGE_OBJECT_PROBE_QUERY)
                lo_row = cur.fetchone()
                lo_count = int(lo_row[0]) if lo_row and lo_row[0] is not None else -1
                if lo_count != 0:
                    user_tables[LARGE_OBJECT_CENSUS_ENTRY] = lo_count

                agents_total = agents_primary = 0
                if "public.agents" in user_tables:
                    cur.execute(AGENTS_CENSUS_QUERY)
                    census = cur.fetchone()
                    if census is not None:
                        agents_total = int(census[0] or 0)
                        agents_primary = int(census[1] or 0)

                schema_versions: Tuple[str, ...] = ()
                if "public.schema_version" in user_tables:
                    cur.execute(SCHEMA_VERSIONS_QUERY)
                    schema_versions = tuple(str(r[0]) for r in cur.fetchall())

            return DatabaseInspection(
                database_name=target,
                system_identifier=system_identifier,
                database_identity=database_identity,
                user_tables=user_tables,
                agents_total=agents_total,
                agents_system_primary=agents_primary,
                schema_versions=schema_versions,
            )
        except Exception:
            return None  # fail closed; never a partial census
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def control_database_name(self) -> Optional[str]:
        conn = None
        try:
            conn = self._connect(self._control_secrets, self._control_ref)
            with conn.cursor() as cur:
                cur.execute("SELECT current_database()")
                row = cur.fetchone()
                return str(row[0]) if row and row[0] is not None else None
        except Exception:
            return None  # fail closed: without the Control-DB identity nothing may drop
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
