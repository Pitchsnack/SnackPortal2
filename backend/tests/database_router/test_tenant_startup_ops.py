"""D-42 CLM Stage B — Database-Router tenant Startup executor + internal edge tests (default suite; in-memory session double).

Covers the bounded read/update executor (one routed session per operation; the sole
CLM-mutable column; no partial write; lineage_reference resolution) and the internal
loopback transport edge (envelope validation; fail-closed 400/404/405/503 mapping).
"""

from __future__ import annotations

import json
import threading
import time
from http.client import HTTPConnection
from typing import Any, Dict, List, Optional, Tuple

from database_router.adapters.providers.http_tenant_startup_api import build_tenant_startup_server
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
class _StubOps(TenantStartupOperations):
    def __init__(self, record: Optional[TenantStartupRecord], *, raising: bool = False) -> None:
        self._record = record
        self._raising = raising
        self.calls: List[Tuple[str, Dict[str, Any]]] = []

    def read(self, **kwargs: Any) -> Optional[TenantStartupRecord]:  # type: ignore[override]
        self.calls.append(("read", kwargs))
        if self._raising:
            raise RuntimeError("routing failure (double)")
        return self._record

    def update(self, **kwargs: Any) -> Optional[TenantStartupRecord]:  # type: ignore[override]
        self.calls.append(("update", kwargs))
        if self._raising:
            raise RuntimeError("routing failure (double)")
        return self._record


def _post(base: str, path: str, body: Optional[Dict[str, Any]]) -> Tuple[int, bytes]:
    from urllib.parse import urlsplit

    parts = urlsplit(base)
    payload = json.dumps(body).encode("utf-8") if body is not None else b""
    last: Optional[BaseException] = None
    # Bounded retries: the single-threaded stdlib loopback server occasionally aborts a
    # connection under Windows (WinError 10053 and siblings, surfacing as assorted OSError
    # shapes under suite-wide socket pressure) — a test-transport artifact, not behavior.
    for attempt in range(3):
        conn = HTTPConnection(parts.hostname or "127.0.0.1", parts.port, timeout=10)
        try:
            conn.request("POST", path, body=payload, headers={"Content-Type": "application/json", "Connection": "close"})
            resp = conn.getresponse()
            return resp.status, resp.read()
        except OSError as exc:  # ConnectionAborted/Reset/RemoteDisconnected and kin
            last = exc
            time.sleep(0.05 * (attempt + 1))
        finally:
            conn.close()
    raise AssertionError(f"loopback request failed three times: {last!r}")


def _serving(ops: TenantStartupOperations):
    server, base = build_tenant_startup_server(ops)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, base


def _read_envelope(**overrides: Any) -> Dict[str, Any]:
    envelope: Dict[str, Any] = {"v": 1, "startup_ref": _REF, "target_tenant_ref": _TENANT, "correlation_id": "cid-1", "actor_ref": "p1"}
    envelope.update(overrides)
    return envelope


def test_edge_read_success_and_not_found_and_unavailable() -> None:
    record = TenantStartupRecord(
        record_ref=_REF,
        display_name="CLM Synthetic Co",
        short_description="original description",
        investment_stage="seed",
        lineage_reference="clm-lineage-0001",
    )
    for ops, expected_status, expect_record in (
        (_StubOps(record), 200, True),
        (_StubOps(None), 404, False),
        (_StubOps(record, raising=True), 503, False),
    ):
        server, thread, base = _serving(ops)
        try:
            status, raw = _post(base, "/internal/tenant/startups/read", _read_envelope())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        assert status == expected_status
        body = json.loads(raw.decode("utf-8"))
        if expect_record:
            assert set(body["record"].keys()) == {
                "record_ref",
                "display_name",
                "short_description",
                "investment_stage",
                "lineage_reference",
            }, "references + the two bounded nullable content fields only"
        else:
            assert "record" not in body, "no record content may leak on any denial"


def test_edge_rejects_malformed_envelopes_before_any_executor_call() -> None:
    ops = _StubOps(None)
    server, thread, base = _serving(ops)
    try:
        for path, bad in (
            ("/internal/tenant/startups/read", None),  # empty body
            ("/internal/tenant/startups/read", {"v": 2, **{k: v for k, v in _read_envelope().items() if k != "v"}}),
            ("/internal/tenant/startups/read", _read_envelope(extra="x")),
            ("/internal/tenant/startups/read", _read_envelope(startup_ref="")),
            ("/internal/tenant/startups/read", _read_envelope(actor_ref="postgresql://leak")),
            ("/internal/tenant/startups/update", _read_envelope()),  # update requires short_description
            ("/internal/tenant/startups/update", _read_envelope(short_description=7)),
            ("/internal/tenant/startups/update", _read_envelope(short_description="a" * 501)),
        ):
            status, raw = _post(base, path, bad)
            assert (status, json.loads(raw.decode("utf-8"))["result"]) == (400, "INVALID"), f"{path} {str(bad)[:60]}"
        assert ops.calls == [], "a malformed envelope never reaches the executor (no partial write)"
        status, _ = _post(base, "/internal/tenant/other", _read_envelope())
        assert status == 404, "wrong path: refused pre-executor"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
