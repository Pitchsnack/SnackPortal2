"""D-42 CLM Stage B — Database-Router tenant Startup EXECUTOR tests (default suite; in-memory session double).

Covers the bounded read/update executor: one routed session per operation; the sole
CLM-mutable column; no partial write; lineage_reference resolution.

The internal loopback transport edge that used to be exercised here
(``http_tenant_startup_api``, ``POST /internal/tenant/startups/*``) was DELETED with the API
Gateway — it existed only to carry a Gateway request into this service, and the public tenant
Startup edge now holds this executor in-process. Its envelope-validation and fail-closed
mapping tests went with it; the public edge's equivalent properties are proved end-to-end in
``tests/gateway_free/test_adversarial_boundary.py``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from database_router.tenant_startup_ops import TenantStartupOperations, TenantStartupRecord
from shared.session import Lane, RoutedSessionProvider, RoutedTenantSession

_TENANT = "tenant-acme"
_REF = "clm-startup-1"
_TARGET = f"{_TENANT}:startups:{_REF}"


class _MemorySession(RoutedTenantSession):
    """A dict-backed routed-session double: startups keyed by global_startup_id, lineage
    rows as a list; records begin/commit/rollback so no-partial-write is provable."""

    def __init__(self, provider: "_MemoryProvider") -> None:
        self._provider = provider
        self.begun = self.committed = self.rolled_back = self.closed = False
        self.writes: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = []

    @property
    def tenant_id(self) -> str:
        return _TENANT

    def begin(self) -> None:
        self.begun = True

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True

    def upsert(self, table: str, key: Dict[str, Any], row: Dict[str, Any]) -> bool:
        raise AssertionError("the executor never upserts (bounded single-column UPDATE only)")

    def append(self, table: str, row: Dict[str, Any]) -> None:
        raise AssertionError("the executor never appends")

    def update(self, table: str, key: Dict[str, Any], assignments: Dict[str, Any]) -> None:
        self.writes.append((table, dict(key), dict(assignments)))
        stored = self._provider.startups.get(key["global_startup_id"])
        assert stored is not None, "the executor read-first discipline guarantees a matching row"
        stored.update(assignments)

    def get(self, table: str, key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        assert table == "startups"
        row = self._provider.startups.get(key["global_startup_id"])
        return dict(row) if row is not None else None

    def latest(self, table: str, where: Dict[str, Any], order_by: str) -> Optional[Dict[str, Any]]:
        assert table == "lineage" and order_by == "seq"
        rows = [r for r in self._provider.lineage if r["target_ref"] == where["target_ref"]]
        return dict(max(rows, key=lambda r: r["seq"])) if rows else None


class _MemoryProvider(RoutedSessionProvider):
    def __init__(self) -> None:
        self.startups: Dict[str, Dict[str, Any]] = {}
        self.lineage: List[Dict[str, Any]] = []
        self.sessions: List[_MemorySession] = []
        self.opened_with: List[Tuple[str, str, Optional[str], Lane]] = []

    def open_session(
        self, *, tenant_id: str, correlation_id: str, principal_ref: Optional[str] = None, lane: Lane = Lane.BULK
    ) -> RoutedTenantSession:
        self.opened_with.append((tenant_id, correlation_id, principal_ref, lane))
        session = _MemorySession(self)
        self.sessions.append(session)
        return session


def _provider_with_row(**overrides: Any) -> _MemoryProvider:
    provider = _MemoryProvider()
    row = {
        "id": 1,
        "global_startup_id": _REF,
        "company_name": "CLM Synthetic Co",
        "short_description": "original description",
        "investment_stage": "seed",
    }
    row.update(overrides)
    provider.startups[_REF] = row
    provider.lineage.append({"seq": 1, "lineage_id": "clm-lineage-0001", "target_ref": _TARGET})
    return provider


def _args() -> Dict[str, str]:
    return {"tenant_ref": _TENANT, "startup_ref": _REF, "correlation_id": "cid-1", "actor_ref": "p1"}


# ===========================================================================
# Executor — bounded read
# ===========================================================================
def test_read_projects_the_five_bounded_fields_on_the_interactive_lane() -> None:
    provider = _provider_with_row()
    record = TenantStartupOperations(provider).read(**_args())
    assert record == TenantStartupRecord(
        record_ref=_REF,
        display_name="CLM Synthetic Co",
        short_description="original description",
        investment_stage="seed",
        lineage_reference="clm-lineage-0001",
    )
    assert provider.opened_with == [(_TENANT, "cid-1", "p1", Lane.INTERACTIVE)], "one routed session, INTERACTIVE lane"
    session = provider.sessions[0]
    assert session.begun and session.committed and session.closed and not session.rolled_back


def test_read_unknown_ref_returns_none_and_writes_nothing() -> None:
    provider = _MemoryProvider()
    assert TenantStartupOperations(provider).read(**_args()) is None
    assert provider.sessions[0].writes == []


def test_read_never_imported_record_carries_no_lineage_reference() -> None:
    provider = _provider_with_row()
    provider.lineage.clear()
    record = TenantStartupOperations(provider).read(**_args())
    assert record is not None and record.lineage_reference is None


# ===========================================================================
# Executor — bounded update (sole field; no partial write)
# ===========================================================================
def test_update_writes_exactly_the_sole_allowlisted_column_and_commits() -> None:
    provider = _provider_with_row()
    record = TenantStartupOperations(provider).update(short_description="updated text", **_args())
    assert record is not None and record.short_description == "updated text"
    session = provider.sessions[0]
    assert session.writes == [("startups", {"global_startup_id": _REF}, {"short_description": "updated text"})]
    assert session.committed and not session.rolled_back
    assert provider.startups[_REF]["company_name"] == "CLM Synthetic Co", "no other column may change"


def test_update_null_clears_and_unknown_ref_writes_nothing() -> None:
    provider = _provider_with_row()
    record = TenantStartupOperations(provider).update(short_description=None, **_args())
    assert record is not None and record.short_description is None
    absent = _MemoryProvider()
    assert TenantStartupOperations(absent).update(short_description="x", **_args()) is None
    assert absent.sessions[0].writes == [] and absent.sessions[0].rolled_back, "unknown ref: rollback, nothing written"


def test_update_over_bound_value_raises_before_any_session_is_opened() -> None:
    provider = _provider_with_row()
    raised = False
    try:
        TenantStartupOperations(provider).update(short_description="a" * 501, **_args())
    except ValueError:
        raised = True
    assert raised and provider.opened_with == [], "validation precedes any routed session (no partial write)"


# ===========================================================================
# Internal edge — envelope validation + fail-closed mapping
# ===========================================================================
