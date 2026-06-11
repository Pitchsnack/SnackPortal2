"""End-to-end Database Router flow: route -> transact -> release -> reuse, isolation kept."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from shared.context import RequestContext  # noqa: E402

from database_router.main import liveness  # noqa: E402
from database_router.models import RoutingTarget  # noqa: E402
from doubles import (  # noqa: E402
    FakeAudit,
    FakeConnectionFactory,
    FakeRoutingRead,
    FakeSecretStore,
    make_router,
)


def _ctx(tenant_id=None, role="TENANT_ADMIN", principal="p"):
    return RequestContext(
        correlation_id="corr", active_tenant_id=tenant_id, principal_ref=principal, role=role
    )


def test_full_router_flow() -> None:
    read = FakeRoutingRead()
    read.set_view("t1")
    read.set_view("t2")
    audit = FakeAudit()
    router, _, pool, _ = make_router(
        read=read, secret_store=FakeSecretStore(), factory=FakeConnectionFactory(), audit=audit
    )

    # Two tenants serve from physically separate, single-tenant-bound connections.
    r1 = router.route(_ctx("t1"))
    r2 = router.route(_ctx("t2"))
    assert r1.connection.tenant_id == "t1" and r2.connection.tenant_id == "t2"

    # Caller controls the transaction on the single resolved connection (IC-004-ready).
    r1.connection.begin()
    r1.connection.commit()

    router.release(r1)
    router.release(r2)

    # Reuse within the same tenant.
    r1b = router.route(_ctx("t1"))
    assert r1b.connection.tenant_id == "t1"

    # A CONTROL-scoped request resolves to the Control DB (no tenant connection).
    rc = router.route(_ctx(tenant_id=None, role="CONTROL", principal="op"))
    assert rc.target is RoutingTarget.CONTROL and rc.connection is None

    actions = audit.actions()
    assert "Route" in actions and "RouteControl" in actions
    assert liveness()["build_phase"] == "4"


if __name__ == "__main__":
    _h.run([test_full_router_flow])
