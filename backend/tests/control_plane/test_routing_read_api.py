"""Control Plane Read API (PRD-P4-R2 B): routing-view + tenant-state + membership/role.

Verifies the routing read exposes the association *reference* + expected schema
version (never credentials), tenant-state stays minimal (least disclosure), unknown
tenants get a consistent 404, and — best-effort — the real HTTP transport round-trips
against the database_router routing-read client (closes O-2).
"""

from __future__ import annotations

import pathlib
import sys
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.read_api import ControlPlaneReadDispatcher, ControlPlaneReadService  # noqa: E402
from control_plane.records import (  # noqa: E402
    MembershipRecord,
    Role,
    TenantLifecycleState,
    TenantRecord,
)
from shared.secrets import SecretRef  # noqa: E402


def _store_with_ready_tenant():
    store = InMemoryControlStore()
    store.put_tenant(
        TenantRecord(
            tenant_id="t1",
            organization_ref="org",
            lifecycle_state=TenantLifecycleState.READY,
            expected_schema_version="1",
            database_association_ref=SecretRef("tenant/t1/db", "1"),
            federation_config_ref="fed",
            created_at="t",
            updated_at="t",
        )
    )
    store.put_membership(MembershipRecord(principal_ref="u", tenant_id="t1", role=Role.TENANT_ADMIN))
    return store


def test_routing_view_exposes_reference_not_credentials() -> None:
    svc = ControlPlaneReadService(_store_with_ready_tenant())
    view = svc.routing_view("t1")
    assert view["tenant_id"] == "t1" and view["ready"] is True
    assert view["expected_schema_version"] == "1"
    assert view["database_association_ref"] == {"store_ref": "tenant/t1/db", "version": "1"}
    # No credential/secret material anywhere in the wire shape.
    assert "material" not in view and "password" not in str(view).lower()


def test_tenant_state_is_minimal_no_association() -> None:
    svc = ControlPlaneReadService(_store_with_ready_tenant())
    state = svc.tenant_state("t1")
    assert set(state.keys()) == {"tenant_id", "lifecycle_state", "ready"}
    assert "database_association_ref" not in state  # least disclosure for the auth path


def test_dispatcher_paths_and_consistent_denial() -> None:
    disp = ControlPlaneReadDispatcher(ControlPlaneReadService(_store_with_ready_tenant()))
    status, body = disp.handle("GET", "/internal/routing/tenants/t1")
    assert status == 200 and body["tenant_id"] == "t1"
    status, _ = disp.handle("GET", "/internal/routing/tenants/nope")
    assert status == 404  # unknown -> consistent 404
    status, body = disp.handle("GET", "/tenants/t1/state")
    assert status == 200 and body["ready"] is True
    status, body = disp.handle("GET", "/membership?p=u&t=t1")
    assert status == 200 and body == {"member": True}
    status, body = disp.handle("GET", "/role?p=u&t=t1")
    assert status == 200 and body == {"role": "TENANT_ADMIN"}
    status, _ = disp.handle("GET", "/role?p=ghost&t=t1")
    assert status == 404


def test_http_transport_roundtrip_best_effort() -> None:
    # Exercises the REAL stdlib HTTP server (control plane) against the urllib routing
    # client (database_router). Self-skips if sockets are unavailable in the sandbox.
    from control_plane.adapters.providers.http_read_api import make_server
    from control_plane.main import ControlPlane
    from database_router.adapters.providers.http_routing_read import HttpRoutingRead

    store = _store_with_ready_tenant()
    try:
        # PRD 07E-1: make_server binds a ControlPlane (per-request UoW), not a store.
        server, base = make_server(ControlPlane(store=store), "127.0.0.1", 0)
    except OSError:
        return  # binding unavailable; transport check skipped
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = HttpRoutingRead(base, timeout=2.0)
        view = client.get_routing_view("t1")
        assert view is not None
        assert view.tenant_id == "t1" and view.ready is True
        assert view.database_association_ref == SecretRef("tenant/t1/db", "1")
        assert view.expected_schema_version == "1"
        assert client.get_routing_view("nope") is None  # 404 -> None
    except OSError:
        return  # loopback networking blocked; transport check skipped
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    _h.run(
        [
            test_routing_view_exposes_reference_not_credentials,
            test_tenant_state_is_minimal_no_association,
            test_dispatcher_paths_and_consistent_denial,
            test_http_transport_roundtrip_best_effort,
        ]
    )
