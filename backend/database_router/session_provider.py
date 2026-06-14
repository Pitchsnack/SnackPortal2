"""RoutedSessionProvider adapter (Build Phase 5 write seam + Build Phase 6 read seam).

Implements the shared `RoutedSessionProvider`/`RoutedTenantSession` (write path) over the
Build Phase 4 Database Router, and additively the Build Phase 6 read seam
`LineageReadSession`/`LineageReadSessionProvider` (PRD-P6-R2 D): registry-authoritative
routing, readiness/schema gating, per-tenant credential resolution, one tenant connection
from the requested lane. The tabular vocab (upsert/append/get/latest) and the read verbs
(page/traverse) map to **standard parameterized PostgreSQL** on the bound connection — no
provider-proprietary idioms; reads are on the INTERACTIVE lane (≠ import BULK capacity).

Consumers (import_service, lineage_service) receive sessions by injection and never import
database_router (DAG). Exercised only against a live database (the stdlib suite uses an
in-memory session double).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from shared.context import RequestContext
from shared.session import (
    Lane,
    LineageReadSession,
    LineageReadSessionProvider,
    RoutedSessionProvider,
    RoutedTenantSession,
)

from .models import RouteResult
from .ports import TenantConnection
from .router import DatabaseRouter

# Hard cap on a single provenance walk; graph.py further trims to its max_nodes.
_TRAVERSE_SAFETY_LIMIT = 100000


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _where(key: Dict[str, Any]) -> tuple[str, tuple[Any, ...]]:
    cols = list(key.keys())
    clause = " AND ".join(f"{_quote_ident(c)} = %s" for c in cols)
    params = tuple(key[c] for c in cols)
    return clause, params


class PgRoutedSession(RoutedTenantSession, LineageReadSession):
    def __init__(self, connection: TenantConnection, router: DatabaseRouter, result: RouteResult) -> None:
        self._conn = connection
        self._router = router
        self._result = result

    @property
    def tenant_id(self) -> str:
        return self._conn.tenant_id

    def begin(self) -> None:
        self._conn.begin()

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._router.release(self._result)  # return the connection to its lane's pool

    def upsert(self, table: str, key: Dict[str, Any], row: Dict[str, Any]) -> bool:
        existing = self.get(table, key)
        merged = dict(key)
        merged.update(row)
        if existing is not None and all(existing.get(k) == v for k, v in merged.items()):
            return False  # idempotent no-op (D-20)
        cols = list(merged.keys())
        placeholders = ", ".join(["%s"] * len(cols))
        col_sql = ", ".join(_quote_ident(c) for c in cols)
        conflict = ", ".join(_quote_ident(c) for c in key.keys())
        updates = ", ".join(f"{_quote_ident(c)} = EXCLUDED.{_quote_ident(c)}" for c in row.keys())
        stmt = f"INSERT INTO {_quote_ident(table)} ({col_sql}) VALUES ({placeholders}) ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
        self._conn.execute(stmt, tuple(merged[c] for c in cols))
        return True

    def append(self, table: str, row: Dict[str, Any]) -> None:
        cols = list(row.keys())
        placeholders = ", ".join(["%s"] * len(cols))
        col_sql = ", ".join(_quote_ident(c) for c in cols)
        stmt = f"INSERT INTO {_quote_ident(table)} ({col_sql}) VALUES ({placeholders})"
        self._conn.execute(stmt, tuple(row[c] for c in cols))

    def get(self, table: str, key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        clause, params = _where(key)
        rows: List[Dict[str, Any]] = self._conn.query(f"SELECT * FROM {_quote_ident(table)} WHERE {clause} LIMIT 1", params)
        return rows[0] if rows else None

    def latest(self, table: str, where: Dict[str, Any], order_by: str) -> Optional[Dict[str, Any]]:
        if where:
            clause, params = _where(where)
            sql = f"SELECT * FROM {_quote_ident(table)} WHERE {clause} ORDER BY {_quote_ident(order_by)} DESC LIMIT 1"
        else:
            params = ()
            sql = f"SELECT * FROM {_quote_ident(table)} ORDER BY {_quote_ident(order_by)} DESC LIMIT 1"
        rows: List[Dict[str, Any]] = self._conn.query(sql, params)
        return rows[0] if rows else None

    # -- LineageReadSession (Build Phase 6; read-only; standard parameterized SQL) --
    def page(
        self,
        table: str,
        where: Dict[str, Any],
        *,
        order_by: str,
        descending: bool = True,
        after: Optional[Any] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        clauses: List[str] = []
        params: List[Any] = []
        for col, val in where.items():
            clauses.append(f"{_quote_ident(col)} = %s")
            params.append(val)
        if after is not None:
            clauses.append(f"{_quote_ident(order_by)} {'<' if descending else '>'} %s")
            params.append(after)
        where_sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        direction = "DESC" if descending else "ASC"
        params.append(int(limit))
        sql = f"SELECT * FROM {_quote_ident(table)}{where_sql} ORDER BY {_quote_ident(order_by)} {direction} LIMIT %s"
        return self._conn.query(sql, tuple(params))

    def traverse(
        self,
        table: str,
        start_id: Any,
        *,
        id_col: str,
        parent_col: str,
        max_depth: int,
        descendants: bool = False,
    ) -> List[Dict[str, Any]]:
        t, idc, pc = _quote_ident(table), _quote_ident(id_col), _quote_ident(parent_col)
        if descendants:
            step = f"SELECT c.*, w._depth + 1 FROM {t} c JOIN walk w ON c.{pc} = w.{idc}"
        else:
            step = f"SELECT p.*, w._depth + 1 FROM {t} p JOIN walk w ON p.{idc} = w.{pc}"
        sql = (
            "WITH RECURSIVE walk AS ("
            f"SELECT *, 0 AS _depth FROM {t} WHERE {idc} = %s "
            f"UNION ALL {step} WHERE w._depth < %s"
            ") SELECT * FROM walk ORDER BY _depth LIMIT %s"
        )
        return self._conn.query(sql, (start_id, int(max_depth), _TRAVERSE_SAFETY_LIMIT))

    def lock_chain(self) -> None:
        # Serialize per-tenant chain-head appends (PRD-P6-R2 B); the advisory xact lock
        # auto-releases at COMMIT/ROLLBACK. UNIQUE(seq) remains the fail-closed backstop.
        self._conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"lineage_chain:{self.tenant_id}",))


class PgRoutedSessionProvider(RoutedSessionProvider, LineageReadSessionProvider):
    def __init__(self, router: DatabaseRouter) -> None:
        self._router = router

    def open_session(
        self,
        *,
        tenant_id: str,
        correlation_id: str,
        principal_ref: Optional[str] = None,
        lane: Lane = Lane.BULK,
    ) -> RoutedTenantSession:
        ctx = RequestContext(correlation_id=correlation_id, active_tenant_id=tenant_id, principal_ref=principal_ref)
        result = self._router.route(ctx, lane=lane)  # raises a canonical denial if not routable
        return PgRoutedSession(result.connection, self._router, result)  # type: ignore[arg-type]

    def open_read_session(
        self,
        *,
        tenant_id: str,
        correlation_id: str,
        principal_ref: Optional[str] = None,
    ) -> LineageReadSession:
        # Reads use the INTERACTIVE lane so lineage queries never draw on import BULK capacity (D-13).
        ctx = RequestContext(correlation_id=correlation_id, active_tenant_id=tenant_id, principal_ref=principal_ref)
        result = self._router.route(ctx, lane=Lane.INTERACTIVE)
        return PgRoutedSession(result.connection, self._router, result)  # type: ignore[arg-type]
