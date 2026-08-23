"""Stage 4 live-PostgreSQL fixture: DSN discovery, migration application, clean skips.

**Every DSN comes from the environment.** Nothing in this file — or anywhere under it —
contains a host, a user, a password, or a database name. A DSN is read, passed to psycopg,
and never printed, logged, asserted on, or included in a failure message. :func:`redact`
exists so that a diagnostic can name *which* database was meant without disclosing how to
reach it.

The four logical databases Stage 4 requires are four **physically separate PostgreSQL
clusters**, not four databases in one. That is stronger than the contract demands and is
deliberate: a cross-tenant leak through a shared cluster (a search_path slip, a dblink, an
accidental fully-qualified name) is not merely forbidden here, it is unreachable.

    SP2_STAGE4_CONTROL_DSN    the Control database
    SP2_STAGE4_ACME_DSN       tenant ACME
    SP2_STAGE4_ZETA_DSN       tenant ZETA
    SP2_STAGE4_NOVA_DSN       tenant NOVA
    SP2_STAGE4_ADMIN_*_DSN    optional; a maintenance database on the same cluster, used
                              only to CREATE/DROP a throwaway database for the
                              fresh-database reproducibility check (§3.4)
"""

from __future__ import annotations

import importlib
import importlib.util
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlsplit, urlunsplit

#: ``backend/tests/snackportal2/requires_pg/_stage4_pg.py`` -> the repository root.
REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend"

#: The legacy DDL corpus, reused unchanged by the rebuild (``backend/migrations/README.md``).
INFRA_DB = REPO_ROOT / "infrastructure" / "db"

#: The rebuild's own migrations. Migration M-1 lives here.
REBUILD_MIGRATIONS = BACKEND_ROOT / "migrations"

ENV_CONTROL = "SP2_STAGE4_CONTROL_DSN"
ENV_TENANT = {"acme": "SP2_STAGE4_ACME_DSN", "zeta": "SP2_STAGE4_ZETA_DSN", "nova": "SP2_STAGE4_NOVA_DSN"}
ENV_ADMIN_CONTROL = "SP2_STAGE4_ADMIN_CONTROL_DSN"
ENV_ADMIN_ACME = "SP2_STAGE4_ADMIN_ACME_DSN"

TENANTS: Sequence[str] = ("acme", "zeta", "nova")

#: The M-1 filenames, named explicitly so the chain check cannot pass by simply globbing an
#: empty directory (§3.2: "M-1 MUST be included").
M1_FILES = ("016_bff_ingress_audit.sql", "017_bff_ingress_audit_append_only.sql")


def _sorted_sql(directory: Path) -> List[Path]:
    return sorted(directory.glob("*.sql"))


def control_chain() -> List[Path]:
    """The Control-database migration chain, legacy corpus first, then the rebuild's own.

    Built by globbing rather than by a hand-written list so that a migration added later is
    picked up automatically instead of being silently skipped by a stale constant.
    """
    return _sorted_sql(INFRA_DB / "control") + _sorted_sql(REBUILD_MIGRATIONS / "control")


def tenant_chain() -> List[Path]:
    """The tenant-database migration chain.

    Order matters and is not alphabetical across directories: provisioning bootstraps the
    schema-version marker the Control Plane's readiness concept reads, the tenant business
    tables come next, and lineage last because ``lineage`` and the import bookkeeping tables
    are what the Import and Lineage services read. ``deals`` has an intra-tenant foreign key
    to ``startups`` and ``investors``, so 005 must not precede 003/004 — the numeric sort
    within each directory already guarantees that.
    """
    return (
        _sorted_sql(INFRA_DB / "provisioning")
        + _sorted_sql(INFRA_DB / "tenant")
        + _sorted_sql(REBUILD_MIGRATIONS / "tenant")
        + _sorted_sql(INFRA_DB / "lineage")
    )


def dsn(name: str) -> str:
    """The configured DSN for ``control`` / ``acme`` / ``zeta`` / ``nova``, or ``""``."""
    variable = ENV_CONTROL if name == "control" else ENV_TENANT.get(name, "")
    return os.environ.get(variable, "").strip() if variable else ""


def admin_dsn(name: str) -> str:
    variable = ENV_ADMIN_CONTROL if name == "control" else ENV_ADMIN_ACME
    return os.environ.get(variable, "").strip()


def redact(value: str) -> str:
    """A DSN reduced to something safe to print: scheme and database path only.

    Used in skip messages and nowhere else. No host, no port, no user, no password.
    """
    parts = urlsplit(value)
    return urlunsplit((parts.scheme, "<redacted>", parts.path, "", ""))


def swap_database(base: str, database: str) -> str:
    """``base`` with its database path replaced — for the fresh-database check only."""
    parts = urlsplit(base)
    return urlunsplit((parts.scheme, parts.netloc, "/" + database, "", ""))


def psycopg_available() -> bool:
    return importlib.util.find_spec("psycopg") is not None


def _driver() -> Any:
    """The PostgreSQL driver, resolved at call time.

    Located through ``importlib`` rather than a static import, which is the Driver Containment
    Standard idiom the repository's existing live-PG harness (``tests/control_plane/
    requires_pg/_pg.py``) already uses: the census in
    ``tests/architecture/test_vendor_and_db_containment.py`` enumerates the *production*
    modules permitted to hold a driver, and a test harness must not appear in that list.

    This module is the **only** file under ``tests/snackportal2/requires_pg/`` that touches the
    driver at all — every test module reaches PostgreSQL through the helpers below, and
    ``test_pg_z_gates.py`` asserts that containment rather than trusting it.
    """
    return importlib.import_module("psycopg")


def database_error() -> Any:
    """The driver's base error class, for ``pytest.raises`` at the call sites.

    Returned rather than imported so the tests can say "PostgreSQL refused this" without
    reaching the driver themselves. It also makes the assertions sharper than a blind
    ``Exception`` would: a test that expects a CHECK constraint or an append-only trigger to
    fire should not pass because a typo raised ``NameError``.
    """
    return _driver().Error


def configured() -> bool:
    """True when every database Stage 4 needs is configured and the driver is importable."""
    return psycopg_available() and bool(dsn("control")) and all(dsn(tenant) for tenant in TENANTS)


SKIP_REASON = (
    "Stage 4 live-PostgreSQL fixture is not configured. Set "
    + ENV_CONTROL
    + " and "
    + ", ".join(ENV_TENANT[t] for t in TENANTS)
    + " to four disposable PostgreSQL databases, and install psycopg."
)


# --- connection and migration helpers ---------------------------------------------------


def connect(target: str, *, autocommit: bool = False) -> Any:
    """Open one connection to a configured target. The DSN never leaves this function."""
    return connect_dsn(dsn(target), autocommit=autocommit)


def connect_dsn(value: str, *, autocommit: bool = False) -> Any:
    connection = _driver().connect(value, connect_timeout=10)
    if autocommit:
        connection.autocommit = True
    return connection


def execute_outside_transaction(target_dsn: str, statement: str) -> None:
    """Run a statement PostgreSQL forbids inside a transaction block, such as CREATE DATABASE."""
    with connect_dsn(target_dsn, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(statement)


def apply_chain(target_dsn: str, files: Sequence[Path]) -> List[str]:
    """Apply a migration chain to one database, one file per transaction.

    One transaction per file, not one for the whole chain: that is how a real migration
    runner behaves, and it means a mid-chain failure names the file that failed instead of
    rolling back evidence of the files that succeeded.

    Returns the applied file names, which is what the Stage 4 report records.
    """
    applied: List[str] = []
    for path in files:
        sql = path.read_text(encoding="utf-8")
        with connect_dsn(target_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql)
        applied.append(path.name)
    return applied


def reset_database(target_dsn: str) -> None:
    """Return one database to zero, so a chain application is genuinely from scratch.

    ``DROP SCHEMA ... CASCADE`` removes tables, triggers and functions together. The
    append-only triggers guard UPDATE/DELETE/TRUNCATE, not DROP, so this is not a way to
    mutate an audit trail — it destroys the whole disposable database's schema and is only
    ever pointed at a Stage 4 fixture.
    """
    with connect_dsn(target_dsn, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DROP SCHEMA IF EXISTS public CASCADE")
            cursor.execute("DROP SCHEMA IF EXISTS dv_sentinel CASCADE")
            cursor.execute("CREATE SCHEMA public")


def table_names(target_dsn: str) -> List[str]:
    with connect_dsn(target_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            )
            return [str(row[0]) for row in cursor.fetchall()]


def column_names(target_dsn: str, table: str) -> List[str]:
    with connect_dsn(target_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s ORDER BY column_name",
                (table,),
            )
            return [str(row[0]) for row in cursor.fetchall()]


def scalar(target_dsn: str, sql: str, params: tuple = ()) -> Optional[object]:
    with connect_dsn(target_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
    return None if row is None else row[0]


def rows(target_dsn: str, sql: str, params: tuple = ()) -> List[tuple]:
    with connect_dsn(target_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return [tuple(row) for row in cursor.fetchall()]


def execute(target_dsn: str, sql: str, params: tuple = ()) -> None:
    with connect_dsn(target_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)


# --- adapter-level evidence: which database was actually connected to -------------------


class SessionWatch:
    """Counts sessions established on each Stage 4 database, from the database's own side.

    §7 asks for "adapter-level evidence to assert the selected DB without leaking DSNs".
    ``pg_stat_database.sessions`` is exactly that: PostgreSQL's own count of connections
    established, read from inside each cluster. A request that touched ACME shows a new ACME
    session; a request that was denied before routing shows none, anywhere.

    The watcher holds one long-lived connection per database and reads through it, so its own
    observation does not move the number it is observing — the alternative, opening a
    connection per reading, adds a session to every snapshot and makes "no new sessions"
    unprovable.
    """

    def __init__(self, targets: Sequence[str]) -> None:
        self._targets = list(targets)
        self._connections = {target: connect(target, autocommit=True) for target in self._targets}

    def snapshot(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for target, connection in self._connections.items():
            with connection.cursor() as cursor:
                cursor.execute("SELECT sessions FROM pg_stat_database WHERE datname = current_database()")
                row = cursor.fetchone()
            counts[target] = int(row[0]) if row else 0
        return counts

    def delta_since(self, baseline: Dict[str, int]) -> Dict[str, int]:
        current = self.snapshot()
        return {target: current[target] - baseline[target] for target in current}

    def close(self) -> None:
        for connection in self._connections.values():
            try:
                connection.close()
            except Exception:
                pass

    def __enter__(self) -> "SessionWatch":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


# --- one-time provisioning for the whole Stage 4 run ------------------------------------

_PROVISIONED = False


def provision() -> Dict[str, List[str]]:
    """Reset and migrate all four Stage 4 databases once per pytest session.

    Idempotent within a process. Every module that needs a live database calls this, so no
    module depends on having been run after another one.
    """
    global _PROVISIONED
    applied: Dict[str, List[str]] = {}
    if _PROVISIONED:
        return applied

    reset_database(dsn("control"))
    applied["control"] = apply_chain(dsn("control"), control_chain())
    for tenant in TENANTS:
        reset_database(dsn(tenant))
        applied[tenant] = apply_chain(dsn(tenant), tenant_chain())

    _PROVISIONED = True
    return applied


__all__ = [
    "BACKEND_ROOT",
    "ENV_ADMIN_ACME",
    "ENV_ADMIN_CONTROL",
    "ENV_CONTROL",
    "ENV_TENANT",
    "INFRA_DB",
    "M1_FILES",
    "REBUILD_MIGRATIONS",
    "REPO_ROOT",
    "SKIP_REASON",
    "TENANTS",
    "SessionWatch",
    "admin_dsn",
    "apply_chain",
    "column_names",
    "configured",
    "connect",
    "connect_dsn",
    "control_chain",
    "dsn",
    "execute",
    "provision",
    "psycopg_available",
    "redact",
    "reset_database",
    "rows",
    "scalar",
    "swap_database",
    "table_names",
    "tenant_chain",
]
