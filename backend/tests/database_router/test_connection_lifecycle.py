"""Connection Lifecycle Standard (PRD-P4-R2 I; D-13): create/reuse/evict/cleanup/recover."""

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


def _ctx(tenant_id):
    return RequestContext(correlation_id="c", active_tenant_id=tenant_id, principal_ref="p", role="TENANT_ADMIN")


def test_creation_is_lazy() -> None:
    read = FakeRoutingRead()
    read.set_view("t1")
    router, _, pool, _ = make_router(read=read, secret_store=FakeSecretStore(), factory=FakeConnectionFactory(), audit=FakeAudit())
    assert pool.pool_keys() == []  # nothing created until first route
    router.route(_ctx("t1"))
    assert pool.counts("t1", "1") == (0, 1)  # one in-use, none idle


def test_release_rolls_back_and_resets_then_pools() -> None:
    read = FakeRoutingRead()
    read.set_view("t1")
    router, _, pool, _ = make_router(read=read, secret_store=FakeSecretStore(), factory=FakeConnectionFactory(), audit=FakeAudit())
    r = router.route(_ctx("t1"))
    conn = r.connection
    router.release(r)
    assert conn.rolled_back >= 1 and conn.reset_count >= 1
    assert pool.counts("t1", "1") == (1, 0)  # returned to its pool, idle


def test_lru_idle_eviction() -> None:
    clock = FakeClock()
    read = FakeRoutingRead()
    read.set_view("t1")
    read.set_view("t2")
    router, _, pool, _ = make_router(
        read=read,
        secret_store=FakeSecretStore(),
        factory=FakeConnectionFactory(),
        audit=FakeAudit(),
        idle_timeout=60.0,
        clock=clock,
    )
    r1 = router.route(_ctx("t1"))
    router.release(r1)  # t1 idle at t=0
    assert pool.counts("t1", "1") == (1, 0)
    clock.advance(120.0)  # exceed idle timeout
    router.route(_ctx("t2"))  # any pool interaction triggers eviction
    assert ("t1", "1") not in pool.pool_keys()  # idle t1 connection evicted + pool dropped
    assert r1.connection.closed is True


def test_broken_idle_connection_is_replaced() -> None:
    read = FakeRoutingRead()
    read.set_view("t1")
    router, _, _, _ = make_router(read=read, secret_store=FakeSecretStore(), factory=FakeConnectionFactory(), audit=FakeAudit())
    r1 = router.route(_ctx("t1"))
    router.release(r1)
    r1.connection.break_it()  # connection goes bad while idle
    r2 = router.route(_ctx("t1"))
    assert r2.connection.id != r1.connection.id  # broken one discarded, fresh one minted
    assert r1.connection.closed is True


def test_failure_recovery_never_falls_back_to_another_tenant() -> None:
    read = FakeRoutingRead()
    read.set_view("t1")
    read.set_view("t2")
    factory = FakeConnectionFactory()
    factory.fail_for("t1")
    router, _, _, _ = make_router(read=read, secret_store=FakeSecretStore(), factory=factory, audit=FakeAudit())
    try:
        router.route(_ctx("t1"))
        assert False, "t1 connection failure must deny"
    except RoutingDenied as d:
        assert d.public_code == "connection_unavailable"
    # t2 is unaffected (per-tenant independence, D-16) and never gets a t1 connection.
    r2 = router.route(_ctx("t2"))
    assert r2.connection.tenant_id == "t2"


if __name__ == "__main__":
    _h.run(
        [
            test_creation_is_lazy,
            test_release_rolls_back_and_resets_then_pools,
            test_lru_idle_eviction,
            test_broken_idle_connection_is_replaced,
            test_failure_recovery_never_falls_back_to_another_tenant,
        ]
    )
