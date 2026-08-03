"""Production tenant ConnectionFactory over PostgreSQL (psycopg).

The ONLY tenant-database driver binding in the router. Confined to this provider
zone (Driver Containment Standard; PRD-P4-R2 C). Not exercised by the stdlib unit
suite (requires a live PostgreSQL and an installed driver); the suite uses an
in-memory fake connection factory.

The descriptor passed to `open()` is the per-tenant connection string resolved at
connect time via the SecretStore (D-14). It is used only to open the connection and
is never stored, logged, or returned. Each connection is bound to exactly one tenant
+ association version for its lifetime and is never reused across tenants (D-30).
"""

from __future__ import annotations

from typing import Any

import psycopg  # type: ignore  # noqa: F401  (driver import confined to this zone)

from database_router.ports import ConnectionFactory, TenantConnection


class PsycopgTenantConnection(TenantConnection):
    def __init__(self, conn: "psycopg.Connection", tenant_id: str, association_version: str) -> None:
        self._conn = conn
        self._tenant_id = tenant_id
        self._association_version = association_version

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    @property
    def association_version(self) -> str:
        return self._association_version

    def is_alive(self) -> bool:
        try:
            return self._conn.closed == 0
        except Exception:
            return False

    def begin(self) -> None:
        # psycopg manages transactions implicitly; an explicit BEGIN keeps multi-statement
        # data+lineage writes atomic on this single connection (IC-004; PRD-P4-R2 J).
        self._conn.execute("BEGIN")

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def reset(self) -> None:
        # Clear any session state before the connection returns to its tenant pool.
        self._conn.execute("RESET ALL")

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def execute(self, statement: str, params: tuple[object, ...] = ()) -> None:
        with self._conn.cursor() as cur:
            cur.execute(statement, params)  # standard parameterized SQL (portable)

    def query(self, statement: str, params: tuple[object, ...] = ()) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(statement, params)
            cols = [d[0] for d in cur.description] if cur.description else []
            return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]


class PsycopgConnectionFactory(ConnectionFactory):
    def open(self, tenant_id: str, association_version: str, descriptor: str) -> TenantConnection:
        conn = psycopg.connect(descriptor)  # descriptor = resolved per-tenant DSN (not retained)
        return PsycopgTenantConnection(conn, tenant_id, association_version)
