"""Stdlib test doubles for import_service (no DB driver, no network).

A transactional in-memory RoutedTenantSession (snapshot-on-begin), a session provider, a
fake Directory read, an audit sink, a fake SecretStore for the lineage chain key, and
lineage-emit doubles to drive atomic-rollback / resume scenarios. The import flow is
exercised end-to-end with the REAL lineage_service hash-chaining emit.
"""
from __future__ import annotations

import copy
import pathlib
import sys
from typing import Any, Dict, List, Optional

_BACKEND = pathlib.Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from shared.audit import OperationalAudit, OperationalAuditEvent  # noqa: E402
from shared.lineage import LineageEmitPort, LineageIntent  # noqa: E402
from shared.secrets import SecretRef, SecretStore, SecretValue  # noqa: E402
from shared.session import Lane, RoutedSessionProvider, RoutedTenantSession  # noqa: E402

from import_service.main import build_import_service  # noqa: E402
from import_service.ports import (  # noqa: E402
    DirectoryPage,
    DirectoryReadPort,
    GlobalDirectoryRecordView,
)
from lineage_service.emit import LineageEmit  # noqa: E402

_KEYED = {"tenant_copy", "import_job", "import_idempotency"}


def _kf(key: Dict[str, Any]):
    return frozenset(key.items())


class FakeRoutedSession(RoutedTenantSession):
    def __init__(self, tenant_id: str, committed: dict) -> None:
        self._tenant_id = tenant_id
        self._committed = committed   # table -> {kf: row} (keyed) | [rows] (append)
        self._working: Optional[dict] = None

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    def _view(self) -> dict:
        return self._working if self._working is not None else self._committed

    def begin(self) -> None:
        self._working = copy.deepcopy(self._committed)

    def commit(self) -> None:
        if self._working is not None:
            self._committed.clear()
            self._committed.update(self._working)
            self._working = None

    def rollback(self) -> None:
        self._working = None

    def close(self) -> None:
        self._working = None

    def upsert(self, table: str, key: Dict[str, Any], row: Dict[str, Any]) -> bool:
        tbl = self._view().setdefault(table, {})
        kf = _kf(key)
        new_row = {**key, **row}
        changed = tbl.get(kf) != new_row
        tbl[kf] = new_row
        return changed

    def append(self, table: str, row: Dict[str, Any]) -> None:
        self._view().setdefault(table, []).append(dict(row))

    def get(self, table: str, key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        row = self._view().get(table, {}).get(_kf(key))
        return dict(row) if row else None

    def latest(self, table: str, where: Dict[str, Any], order_by: str) -> Optional[Dict[str, Any]]:
        rows: List[dict] = self._view().get(table, [])
        cand = [r for r in rows if all(r.get(k) == v for k, v in where.items())]
        if not cand:
            return None

        def _ord(r):
            v = r.get(order_by)
            try:
                return (1, int(v))
            except (TypeError, ValueError):
                return (0, str(v))

        return dict(max(cand, key=_ord))


class FakeRoutedSessionProvider(RoutedSessionProvider):
    def __init__(self) -> None:
        self._stores: Dict[str, dict] = {}
        self.opened_lanes: List[Lane] = []
        self.unavailable: set = set()

    def store_for(self, tenant_id: str) -> dict:
        return self._stores.setdefault(tenant_id, {})

    def set_unavailable(self, tenant_id: str) -> None:
        self.unavailable.add(tenant_id)

    def open_session(self, *, tenant_id, correlation_id, principal_ref=None, lane=Lane.BULK):
        self.opened_lanes.append(lane)
        if tenant_id in self.unavailable:
            raise RuntimeError("tenant not routable")
        return FakeRoutedSession(tenant_id, self.store_for(tenant_id))

    # -- test introspection ---------------------------------------------------
    def tenant_copy_rows(self, tenant_id: str) -> List[dict]:
        return list(self.store_for(tenant_id).get("tenant_copy", {}).values())

    def lineage_rows(self, tenant_id: str) -> List[dict]:
        return list(self.store_for(tenant_id).get("lineage", []))

    def checkpoints(self, tenant_id: str) -> List[dict]:
        return list(self.store_for(tenant_id).get("import_checkpoint", []))


class FakeDirectoryRead(DirectoryReadPort):
    def __init__(self) -> None:
        self._recs: Dict[str, List[GlobalDirectoryRecordView]] = {}

    def add(self, kind: str, record_id: str, display_name: str, **attrs) -> None:
        view = GlobalDirectoryRecordView(
            directory="GlobalStartupDirectory" if kind == "startup" else "GlobalInvestorDirectory",
            record_id=record_id, display_name=display_name,
            attributes={k: str(v) for k, v in attrs.items()},
        )
        self._recs.setdefault(kind, []).append(view)

    def get_record(self, kind, record_id):
        for r in self._recs.get(kind, []):
            if r.record_id == record_id:
                return r
        return None

    def page(self, kind, cursor, limit):
        recs = self._recs.get(kind, [])
        offset = int(cursor) if (cursor or "").isdigit() else 0
        page = recs[offset:offset + limit]
        nxt = str(offset + limit) if offset + limit < len(recs) else None
        return DirectoryPage(records=page, next_cursor=nxt)


class FakeAudit(OperationalAudit):
    def __init__(self) -> None:
        self.events: List[OperationalAuditEvent] = []

    def initiate(self, event: OperationalAuditEvent) -> None:
        self.events.append(event)

    def actions(self) -> List[str]:
        return [e.action for e in self.events]


class FakeSecretStore(SecretStore):
    def resolve(self, ref: SecretRef) -> SecretValue:
        return SecretValue(material=f"key::{ref.store_ref}@{ref.version}")

    def current_version(self, store_ref: str) -> str:
        return "1"


class RaisingLineageEmit(LineageEmitPort):
    """Always raises for the given target refs (drives atomic-rollback tests)."""

    def __init__(self, inner: LineageEmitPort, fail_targets) -> None:
        self._inner = inner
        self._fail = set(fail_targets)

    def emit(self, session, intent):
        if intent.target_ref in self._fail:
            raise RuntimeError("lineage emit failed")
        return self._inner.emit(session, intent)


class FlakyLineageEmit(LineageEmitPort):
    """Raises ONCE per target ref, then succeeds (drives resume/crash-recovery tests)."""

    def __init__(self, inner: LineageEmitPort, fail_targets) -> None:
        self._inner = inner
        self._fail = set(fail_targets)
        self._failed: set = set()

    def emit(self, session, intent):
        if intent.target_ref in self._fail and intent.target_ref not in self._failed:
            self._failed.add(intent.target_ref)
            raise RuntimeError("transient lineage emit failure")
        return self._inner.emit(session, intent)


def make_service(*, provider=None, lineage=None, audit=None, directory=None, batch_size=2):
    provider = provider or FakeRoutedSessionProvider()
    lineage = lineage or LineageEmit(FakeSecretStore())
    audit = audit or FakeAudit()
    directory = directory or FakeDirectoryRead()
    svc = build_import_service(
        session_provider=provider, lineage=lineage, directory_read=directory,
        audit=audit, batch_size=batch_size,
    )
    return svc, provider, lineage, audit, directory
