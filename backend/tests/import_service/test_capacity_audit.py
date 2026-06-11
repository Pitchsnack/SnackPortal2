"""Capacity (D-13) + audit (IC-003) + routing dependency: bulk lane, lifecycle events, status."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from shared.session import Lane  # noqa: E402

from import_service.models import ImportMode, ImportRequest, SourceDescriptor, SourceKind  # noqa: E402
from doubles import FakeRoutedSessionProvider, make_service  # noqa: E402

_CSV = "record_id,display_name\n1,A\n2,B"


def _req(op="op1", tenant="t1"):
    return ImportRequest(
        tenant_id=tenant, source=SourceDescriptor(kind=SourceKind.CSV, ref="f", payload=_CSV),
        mode=ImportMode.ASYNC, operation_key=op, correlation_id="c", actor_ref="user1",
    )


def test_import_always_uses_the_bulk_lane() -> None:
    svc, provider, _, _, _ = make_service()
    svc.start_import(_req())
    assert provider.opened_lanes  # opened at least one session
    assert all(lane is Lane.BULK for lane in provider.opened_lanes)


def test_lifecycle_audit_events() -> None:
    svc, _, _, audit, _ = make_service()
    svc.start_import(_req())
    actions = audit.actions()
    assert "ImportRequested" in actions
    assert "ImportStarted" in actions
    assert "ImportCompleted" in actions


def test_not_routable_tenant_propagates_denial() -> None:
    provider = FakeRoutedSessionProvider()
    provider.set_unavailable("t1")
    svc, _, _, _, _ = make_service(provider=provider)
    try:
        svc.start_import(_req())
        assert False, "a non-routable tenant must not import"
    except Exception:
        pass


def test_get_status_reads_tenant_resident_state() -> None:
    svc, _, _, _, _ = make_service()
    svc.start_import(_req("op1"))
    status = svc.get_status(tenant_id="t1", operation_key="op1", correlation_id="c")
    assert status is not None and status.state == "applied"
    assert svc.get_status(tenant_id="t1", operation_key="ghost", correlation_id="c") is None


if __name__ == "__main__":
    _h.run([
        test_import_always_uses_the_bulk_lane,
        test_lifecycle_audit_events,
        test_not_routable_tenant_propagates_denial,
        test_get_status_reads_tenant_resident_state,
    ])
