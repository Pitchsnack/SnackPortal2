"""Separate bounded import capacity (PRD-P5-R2 G; D-13): bulk lane != interactive lane."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402
from _db_doubles import FakeAudit, FakeConnectionFactory, FakeRoutingRead, FakeSecretStore  # noqa: E402

from database_router.cache import RoutingViewCache  # noqa: E402
from database_router.models import RoutingDenied  # noqa: E402
from database_router.pool import ConnectionPoolManager  # noqa: E402
from database_router.resolver import RoutingResolver  # noqa: E402
from database_router.router import DatabaseRouter  # noqa: E402
from shared.context import RequestContext  # noqa: E402
from shared.session import Lane  # noqa: E402


def _router(*, bulk_max=2, inter_max=5):
    read = FakeRoutingRead()
    read.set_view("t1")
    resolver = RoutingResolver(read, RoutingViewCache(), supported_schema_versions=("1",))
    interactive = ConnectionPoolManager(max_per_tenant=inter_max)
    bulk = ConnectionPoolManager(max_per_tenant=bulk_max)
    router = DatabaseRouter(
        resolver=resolver,
        pool=interactive,
        secret_store=FakeSecretStore(),
        connection_factory=FakeConnectionFactory(),
        audit=FakeAudit(),
        bulk_pool=bulk,
    )
    return router, interactive, bulk


def _ctx():
    return RequestContext(correlation_id="c", active_tenant_id="t1", principal_ref="p", role="TENANT_ADMIN")


def test_bulk_and_interactive_use_separate_pools() -> None:
    router, interactive, bulk = _router()
    ri = router.route(_ctx(), lane=Lane.INTERACTIVE)
    rb = router.route(_ctx(), lane=Lane.BULK)
    assert ri.lane is Lane.INTERACTIVE and rb.lane is Lane.BULK
    assert ri.connection.id != rb.connection.id
    assert interactive.counts("t1", "1") == (0, 1)
    assert bulk.counts("t1", "1") == (0, 1)


def test_bulk_saturation_does_not_starve_interactive() -> None:
    router, _, _ = _router(bulk_max=1)
    router.route(_ctx(), lane=Lane.BULK)  # fills the (size-1) bulk pool
    try:
        router.route(_ctx(), lane=Lane.BULK)  # bulk exhausted
        assert False, "saturated bulk lane must deny, not starve"
    except RoutingDenied as d:
        assert d.public_code == "connection_unavailable"
    # Interactive traffic is unaffected by bulk saturation (D-13/D-16).
    ri = router.route(_ctx(), lane=Lane.INTERACTIVE)
    assert ri.connection.tenant_id == "t1"


if __name__ == "__main__":
    _h.run(
        [
            test_bulk_and_interactive_use_separate_pools,
            test_bulk_saturation_does_not_starve_interactive,
        ]
    )
