"""In-memory routed-session doubles for lineage_service Build Phase 6 tests (stdlib).

A single `InMemorySession` implements BOTH the write seam (`RoutedTenantSession`) and the
read seam (`LineageReadSession`) over a per-tenant in-memory store, so a test can emit a
chain and then query/verify/traverse it. Providers key stores by tenant_id so cross-tenant
isolation is exercised (a session for t2 can never see t1's rows). No PostgreSQL needed; the
live-PG guarantees (privilege/trigger/advisory-lock) are covered by the requires_pg suite.
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))  # backend on path

from shared.audit import OperationalAudit, OperationalAuditEvent  # noqa: E402
from shared.context import RequestContext  # noqa: E402
from shared.secrets import SecretRef, SecretStore, SecretValue  # noqa: E402
from shared.session import (  # noqa: E402
    Lane,
    LineageReadSession,
    LineageReadSessionProvider,
    RoutedSessionProvider,
    RoutedTenantSession,
)


class _TenantStore:
    def __init__(self) -> None:
        self.tables: Dict[str, Any] = {}


class InMemorySession(RoutedTenantSession, LineageReadSession):
    def __init__(self, store: _TenantStore, tenant_id: str) -> None:
        self._store = store
        self._tenant_id = tenant_id
        self.closed = False

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    def begin(self) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...

    def close(self) -> None:
        self.closed = True

    # -- write vocab (RoutedTenantSession) -------------------------------------
    def upsert(self, table: str, key: Dict[str, Any], row: Dict[str, Any]) -> bool:
        d = self._store.tables.setdefault(table, {})
        k = frozenset(key.items())
        merged = {**key, **row}
        if d.get(k) == merged:
            return False
        d[k] = merged
        return True

    def append(self, table: str, row: Dict[str, Any]) -> None:
        self._store.tables.setdefault(table, []).append(dict(row))

    def get(self, table: str, key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        d = self._store.tables.get(table)
        if isinstance(d, dict):
            return d.get(frozenset(key.items()))
        for r in d or []:
            if all(r.get(k) == v for k, v in key.items()):
                return dict(r)
        return None

    def latest(self, table: str, where: Dict[str, Any], order_by: str) -> Optional[Dict[str, Any]]:
        cand = [r for r in self._rows(table) if all(r.get(k) == v for k, v in where.items())]
        return max(cand, key=lambda r: int(r[order_by])) if cand else None

    # -- read vocab (LineageReadSession) ---------------------------------------
    def page(self, table, where, *, order_by, descending=True, after=None, limit=100):
        rows = [r for r in self._rows(table) if all(r.get(k) == v for k, v in where.items())]
        if after is not None:
            rows = [r for r in rows if ((int(r[order_by]) < after) if descending else (int(r[order_by]) > after))]
        rows.sort(key=lambda r: int(r[order_by]), reverse=descending)
        return [dict(r) for r in rows[: int(limit)]]

    def traverse(self, table, start_id, *, id_col, parent_col, max_depth, descendants=False):
        rows = self._rows(table)
        by_id = {r[id_col]: r for r in rows}
        if start_id not in by_id:
            return []
        out: List[dict] = [dict(by_id[start_id])]
        if not descendants:
            node = by_id[start_id]
            depth = 0
            while depth < max_depth:
                parent = node.get(parent_col)
                if not parent or parent not in by_id:
                    break
                node = by_id[parent]
                out.append(dict(node))
                depth += 1
            return out
        seen = {start_id}
        current = [start_id]
        depth = 0
        while current and depth < max_depth:
            nxt = []
            for r in rows:
                if r.get(parent_col) in current and r[id_col] not in seen:
                    out.append(dict(r))
                    seen.add(r[id_col])
                    nxt.append(r[id_col])
            current = nxt
            depth += 1
        return out

    def _rows(self, table: str) -> List[dict]:
        d = self._store.tables.get(table, [])
        return list(d.values()) if isinstance(d, dict) else d


class InMemoryProvider(RoutedSessionProvider, LineageReadSessionProvider):
    """Shares one store per tenant across sessions (emit then read see the same data)."""

    def __init__(self) -> None:
        self._stores: Dict[str, _TenantStore] = {}

    def store(self, tenant_id: str) -> _TenantStore:
        return self._stores.setdefault(tenant_id, _TenantStore())

    def open_session(self, *, tenant_id, correlation_id, principal_ref=None, lane=Lane.BULK):
        return InMemorySession(self.store(tenant_id), tenant_id)

    def open_read_session(self, *, tenant_id, correlation_id, principal_ref=None):
        return InMemorySession(self.store(tenant_id), tenant_id)


class FakeKeyStore(SecretStore):
    def resolve(self, ref: SecretRef) -> SecretValue:
        return SecretValue(material="chainkey-" + ref.store_ref)

    def current_version(self, store_ref: str) -> str:
        return "1"


class RecordingAudit(OperationalAudit):
    def __init__(self) -> None:
        self.events: List[OperationalAuditEvent] = []

    def initiate(self, event: OperationalAuditEvent) -> None:
        self.events.append(event)

    def actions(self) -> List[str]:
        return [e.action for e in self.events]


def ctx(tenant: str = "t1", corr: str = "c", principal: str = "user1") -> RequestContext:
    return RequestContext(correlation_id=corr, active_tenant_id=tenant, principal_ref=principal)
