"""Routed tenant session port (shared, vendor-neutral) — PRD-P5-R2 B.

The Database Router implements `RoutedSessionProvider`; consumers (import_service,
lineage_service) receive a `RoutedTenantSession` by composition-root **injection** and
never import `database_router` (DAG). A session is bound to exactly one active tenant and
one connection for a unit of work; tenant data + lineage + job-state writes commit and
roll back **together** (atomic provenance — IC-003/IC-004).

The session exposes a small, portable **tabular** vocabulary (`upsert`/`append`/`get`/
`latest`); the provider maps it to standard parameterized PostgreSQL. References only —
no credentials, payloads, or secrets appear in this port (D-14). There is no update/delete
vocabulary: lineage tables are append-only (D-23) and tenant copies mutate via `upsert`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional


class Lane(Enum):
    INTERACTIVE = "interactive"
    BULK = "bulk"  # separate bounded capacity for heavy/import workloads (D-13)


class RoutedTenantSession(ABC):
    """One tenant, one connection, caller-controlled transaction."""

    @property
    @abstractmethod
    def tenant_id(self) -> str: ...

    @abstractmethod
    def begin(self) -> None: ...

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def upsert(self, table: str, key: Dict[str, Any], row: Dict[str, Any]) -> bool:
        """Insert or update by natural key within the active transaction.

        Returns True if the stored row changed, False for an idempotent no-op (D-20).
        """

    @abstractmethod
    def append(self, table: str, row: Dict[str, Any]) -> None:
        """Append-only insert (e.g. lineage). No update/delete is exposed (D-23)."""

    @abstractmethod
    def get(self, table: str, key: Dict[str, Any]) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def latest(self, table: str, where: Dict[str, Any], order_by: str) -> Optional[Dict[str, Any]]:
        """Return the row matching `where` with the maximum `order_by` value, or None."""


class RoutedSessionProvider(ABC):
    @abstractmethod
    def open_session(
        self,
        *,
        tenant_id: str,
        correlation_id: str,
        principal_ref: Optional[str] = None,
        lane: Lane = Lane.BULK,
    ) -> RoutedTenantSession:
        """Resolve registry-authoritative routing, gate readiness + schema, resolve the
        per-tenant credential by reference, and bind one tenant connection from the
        lane's bounded pool. Raises a canonical denial (shared.errors) when not routable.
        The caller owns the transaction; `close()` returns the connection to the pool.
        """


class LineageReadSession(ABC):
    """Read-only, tenant-bound access for Build Phase 6 lineage query/verify/graph.

    Additive to the Phase-5 write seam: `RoutedTenantSession` is unchanged, so existing
    write-path implementers/doubles are untouched (PRD-P6-R2 D / P6-OBS-4). The Database
    Router implements this over a routed connection (INTERACTIVE lane); consumers
    (`lineage_service`) receive it by injection and never import `database_router` (DAG).
    Returns generic rows (`List[Dict]`); the caller maps to its own DTOs. Read-only by
    construction — no append/upsert/update/delete is exposed here.
    """

    @property
    @abstractmethod
    def tenant_id(self) -> str: ...

    @abstractmethod
    def close(self) -> None:
        """Return the underlying connection to its lane pool (read sessions are short-lived)."""

    @abstractmethod
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
        """Keyset page: rows matching `where`, ordered by `order_by`, with `order_by`
        strictly past the `after` cursor (`<` when descending, `>` when ascending),
        bounded by `limit`. Standard parameterized SQL; expand-only (D / AC-DR-02)."""

    @abstractmethod
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
        """Bounded provenance walk over `parent_col` self-references within one tenant
        (recursive CTE; no external graph DB — G). `descendants=False` climbs to ancestors;
        `True` descends to children. Depth-bounded by `max_depth` (cycle/runaway guard)."""


class LineageReadSessionProvider(ABC):
    """Opens a tenant-bound `LineageReadSession` on the INTERACTIVE lane (reads must not
    draw from the import BULK capacity — D-13). Additive sibling of `RoutedSessionProvider`
    so Phase-5 write-path providers/doubles need no change (PRD-P6-R2 D)."""

    @abstractmethod
    def open_read_session(
        self,
        *,
        tenant_id: str,
        correlation_id: str,
        principal_ref: Optional[str] = None,
    ) -> LineageReadSession:
        """Resolve registry-authoritative routing + readiness/schema gating, bind one
        tenant connection (INTERACTIVE), and return a read-only session. Raises a canonical
        denial (shared.errors) when not routable. The caller closes it via `close()`."""
