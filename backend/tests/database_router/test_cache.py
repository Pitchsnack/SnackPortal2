"""Database Association Cache Standard (PRD-P4-R2 K; D-11): TTL + version + invalidation."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402
from _db_doubles import (  # noqa: E402
    FakeAudit,
    FakeClock,
    FakeConnectionFactory,
    FakeRoutingRead,
    FakeSecretStore,
    make_router,
)

from database_router.models import RoutingDenied  # noqa: E402
from shared.context import RequestContext  # noqa: E402


def _ctx(tenant_id="t1"):
    return RequestContext(correlation_id="c", active_tenant_id=tenant_id, principal_ref="p", role="TENANT_ADMIN")


def _wire(clock):
    read = FakeRoutingRead()
    read.set_view("t1")
    router, cache, _, _ = make_router(
        read=read,
        secret_store=FakeSecretStore(),
        factory=FakeConnectionFactory(),
        audit=FakeAudit(),
        ttl=15.0,
        clock=clock,
    )
    return router, read


def test_cache_hit_avoids_reread_within_ttl() -> None:
    clock = FakeClock()
    router, read = _wire(clock)
    router.route(_ctx())
    router.route(_ctx())
    assert read.calls == 1  # second route served from cache


def test_ttl_expiry_triggers_reread() -> None:
    clock = FakeClock()
    router, read = _wire(clock)
    router.route(_ctx())
    clock.advance(20.0)  # past the 15s TTL
    router.route(_ctx())
    assert read.calls == 2  # re-read after expiry (pull-based refresh)


def test_explicit_invalidation_forces_reread() -> None:
    clock = FakeClock()
    router, read = _wire(clock)
    router.route(_ctx())
    router.invalidate_tenant("t1")
    router.route(_ctx())
    assert read.calls == 2


def test_reassociation_then_invalidate_prevents_stale_routing() -> None:
    clock = FakeClock()
    router, read = _wire(clock)
    router.route(_ctx())  # cached: Ready v1
    # Re-association at the control plane: tenant goes Verifying with a new version.
    read.set_view("t1", lifecycle="Verifying", ready=False, version="2")
    router.invalidate_tenant("t1")  # push hook -> next resolve re-reads
    try:
        router.route(_ctx())
        assert False, "a re-associating (Verifying) tenant must not route"
    except RoutingDenied as d:
        assert d.public_code == "not_ready"


if __name__ == "__main__":
    _h.run(
        [
            test_cache_hit_avoids_reread_within_ttl,
            test_ttl_expiry_triggers_reread,
            test_explicit_invalidation_forces_reread,
            test_reassociation_then_invalidate_prevents_stale_routing,
        ]
    )
