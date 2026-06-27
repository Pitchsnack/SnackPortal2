"""PRD 06 B-7C-1 — required durable audit failure / missing-table fail-closed floor (no PostgreSQL).

A default-suite (CI-enforced via the B-7C-1 full-pytest step) proof — needing no live database — that a
failed REQUIRED durable audit write (modelled as the durable `control_audit` table being absent) is
fail-closed at BOTH levels:

  • call-site (wired runtime path): TenantRegistry.register_tenant rejects the operation and leaves NO
    committed partial tenant state (audit-before-put_tenant ordering), and the exception is NOT swallowed;
  • adapter: PostgresControlStore.list_audit RAISES (never returns []) and append_audit propagates, when
    the underlying execute fails as if the table were missing.

The driver error is modelled by a locally-defined exception so this default-suite test imports NO database
driver (driver-containment clean) and needs no PostgreSQL. The B-7B failing-audit tests cover a generic
RuntimeError; this floor specifically ties the MISSING-TABLE failure mode to no-partial-state and to the
adapter's no-swallow / never-empty contract.

Pure stdlib; pytest- or standalone-run:
  python tests/control_plane/test_b7c1_required_audit_failure_floor.py
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any, List, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.adapters.providers.postgres_store import PostgresControlStore  # noqa: E402
from control_plane.audit import ControlPlaneAudit  # noqa: E402
from control_plane.records import ControlAuditRecord  # noqa: E402
from control_plane.registry import TenantRegistry  # noqa: E402
from shared.secrets import SecretRef  # noqa: E402


class _MissingTableError(Exception):
    """Stand-in for a driver UndefinedTable error (relation "control_audit" does not exist).

    Defined locally so this test imports NO database driver (driver-containment clean)."""


# --- call-site floor ------------------------------------------------------------------------------
class _MissingTableAuditStore(InMemoryControlStore):
    """A wired ControlStore whose REQUIRED audit write fails as if control_audit were absent."""

    def append_audit(self, record: ControlAuditRecord) -> None:
        raise _MissingTableError('relation "control_audit" does not exist')


def _register(reg: TenantRegistry, tid: str = "t1") -> None:
    reg.register_tenant(
        tenant_id=tid,
        organization_ref="org",
        expected_schema_version="1",
        database_association_ref=SecretRef(f"tenant/{tid}/db", "1"),
        federation_config_ref="fed",
        actor="op",
        correlation_id="c",
    )


def test_call_site_missing_table_audit_rejects_with_no_partial_state() -> None:
    store = _MissingTableAuditStore()
    reg = TenantRegistry(store, ControlPlaneAudit(store))
    raised = False
    try:
        _register(reg)
    except _MissingTableError:
        raised = True
    assert raised, "a required durable audit write failing (missing table) must reject the registration (no swallow)"
    # no partial state: the tenant was never committed (audit precedes put_tenant)
    assert store.get_tenant("t1") is None


# --- adapter floor (fake driver connection; no live DB) -------------------------------------------
_Row = Tuple[Any, ...]


class _RaisingCursor:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def __enter__(self) -> "_RaisingCursor":
        return self

    def __exit__(self, *_a: object) -> bool:
        return False

    def execute(self, *_a: object, **_k: object) -> None:
        raise self._exc

    def fetchall(self) -> List[_Row]:  # never reached (execute raises first)
        return []


class _RaisingConn:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def cursor(self) -> _RaisingCursor:
        return _RaisingCursor(self._exc)


def _pg_store_missing_table() -> PostgresControlStore:
    store = PostgresControlStore(dsn="postgresql://unused")  # lazy: __init__ opens no connection
    store._conn_cache = _RaisingConn(_MissingTableError('relation "control_audit" does not exist'))
    return store


def test_adapter_list_audit_missing_table_raises_never_returns_empty() -> None:
    store = _pg_store_missing_table()
    raised, got_empty = False, False
    try:
        got_empty = store.list_audit() == []
    except _MissingTableError:
        raised = True
    assert raised and not got_empty, "list_audit against a MISSING control_audit must RAISE, never return [] (fail-open)"


def test_adapter_append_audit_missing_table_propagates() -> None:
    store = _pg_store_missing_table()
    rec = ControlAuditRecord(
        actor="a",
        tenant_id=None,
        action="act",
        from_state=None,
        to_state=None,
        timestamp="2026-01-01T00:00:00+00:00",
        correlation_id="c",
    )
    raised = False
    try:
        store.append_audit(rec)
    except _MissingTableError:
        raised = True
    assert raised, "append_audit against a MISSING control_audit must propagate (no swallow)"


if __name__ == "__main__":
    _h.run(
        [
            test_call_site_missing_table_audit_rejects_with_no_partial_state,
            test_adapter_list_audit_missing_table_raises_never_returns_empty,
            test_adapter_append_audit_missing_table_propagates,
        ]
    )
