"""Routing Context Standard (PRD-P4-R2 H / PRD-P4-E1 §19): control-vs-tenant + bootstrap."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402
from _db_doubles import (  # noqa: E402
    FakeAudit,
    FakeConnectionFactory,
    FakeRoutingRead,
    FakeSecretStore,
    make_router,
)

from database_router.models import RoutingDenied, RoutingTarget  # noqa: E402
from shared.context import RequestContext  # noqa: E402


def _wire():
    read = FakeRoutingRead()
    read.set_view("t1")
    audit = FakeAudit()
    factory = FakeConnectionFactory()
    router, _, _, _ = make_router(read=read, secret_store=FakeSecretStore(), factory=factory, audit=audit)
    return router, factory, audit


def test_tenant_request_routes_to_one_tenant_database() -> None:
    router, factory, audit = _wire()
    ctx = RequestContext(correlation_id="c", active_tenant_id="t1", principal_ref="p", role="TENANT_ADMIN")
    result = router.route(ctx)
    assert result.target is RoutingTarget.TENANT
    assert result.tenant_id == "t1"
    assert result.connection is not None
    assert factory.opens == [("t1", "1")]
    assert "Route" in audit.actions()


def test_control_request_routes_to_control_database() -> None:
    router, factory, _ = _wire()
    ctx = RequestContext(correlation_id="c", active_tenant_id=None, principal_ref="op", role="CONTROL")
    result = router.route(ctx)
    assert result.target is RoutingTarget.CONTROL
    assert result.tenant_id is None
    assert result.connection is None
    assert factory.opens == []  # CONTROL never opens a tenant database


def test_null_tenant_non_control_is_forbidden() -> None:
    router, _, _ = _wire()
    ctx = RequestContext(correlation_id="c", active_tenant_id=None, principal_ref="u", role="TENANT_AGENT")
    try:
        router.route(ctx)
        assert False, "null tenant for a tenant-scoped principal must be forbidden"
    except RoutingDenied as d:
        assert d.http_status == 403 and d.public_code == "no_active_tenant"


def test_bootstrap_phase0_never_routes_a_tenant_database() -> None:
    router, factory, _ = _wire()
    ctx = RequestContext(correlation_id="c", active_tenant_id="t1", principal_ref="sys", role="CONTROL")
    try:
        router.route(ctx, bootstrap_phase0=True)
        assert False, "tenant routing must be unavailable during Bootstrap Phase 0"
    except RoutingDenied as d:
        assert d.http_status == 503 and d.public_code == "tenant_routing_unavailable"
    assert factory.opens == []


if __name__ == "__main__":
    _h.run(
        [
            test_tenant_request_routes_to_one_tenant_database,
            test_control_request_routes_to_control_database,
            test_null_tenant_non_control_is_forbidden,
            test_bootstrap_phase0_never_routes_a_tenant_database,
        ]
    )
