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
from database_router.pool import ConnectionPoolManager  # noqa: E402
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


# Failed-acquisition pool hygiene (D-13/D-30): a mint that fails inside acquire must not
# leave an empty reserved (tenant, version) pool key behind, must never disturb a populated
# or unrelated pool, and must re-raise the original exception unchanged.
def test_failed_secret_resolution_leaves_no_empty_pool_key() -> None:
    read = FakeRoutingRead()
    read.set_view("t1")
    secrets = FakeSecretStore()
    secrets.set_missing("tenant/t1/db")  # resolve raises before any physical open
    factory = FakeConnectionFactory()
    router, _, pool, _ = make_router(read=read, secret_store=secrets, factory=factory, audit=FakeAudit())
    try:
        router.route(_ctx("t1"))
        assert False, "missing secret must deny"
    except RoutingDenied as d:
        assert d.http_status == 503 and d.public_code == "connection_unavailable"
    assert pool.pool_keys() == []  # no phantom (t1, "1") key left behind
    assert factory.opens == []  # factory never reached (resolution failed first)


def test_failed_factory_open_leaves_no_empty_pool_key() -> None:
    read = FakeRoutingRead()
    read.set_view("t1")
    factory = FakeConnectionFactory()
    factory.fail_for("t1")  # secret resolves; the physical open raises
    router, _, pool, _ = make_router(read=read, secret_store=FakeSecretStore(), factory=factory, audit=FakeAudit())
    try:
        router.route(_ctx("t1"))
        assert False, "factory-open failure must deny"
    except RoutingDenied as d:
        assert d.http_status == 503 and d.public_code == "connection_unavailable"
    assert pool.pool_keys() == []  # failed (t1, "1") key absent; no other pool state


def test_misbound_open_leaves_no_empty_pool_key() -> None:
    read = FakeRoutingRead()
    read.set_view("t1")
    factory = FakeConnectionFactory()
    factory.misbind = True  # open() returns a wrong-tenant connection → binding guard trips
    minted: list = []
    inner_open = factory.open

    def _recording_open(tenant_id, association_version, descriptor):
        conn = inner_open(tenant_id, association_version, descriptor)
        minted.append(conn)
        return conn

    factory.open = _recording_open  # capture the misbound connection to prove it is closed
    router, _, pool, _ = make_router(read=read, secret_store=FakeSecretStore(), factory=factory, audit=FakeAudit())
    try:
        router.route(_ctx("t1"))
        assert False, "a wrong-tenant connection must be rejected"
    except RoutingDenied as d:
        assert d.http_status == 503 and d.public_code == "connection_unavailable"
    assert len(minted) == 1 and minted[0].closed is True  # misbound connection was closed
    assert pool.pool_keys() == []  # binding-guard failure leaves no phantom key


def test_failed_open_preserves_populated_same_key_pool() -> None:
    read = FakeRoutingRead()
    read.set_view("t1")
    factory = FakeConnectionFactory()
    router, _, pool, _ = make_router(read=read, secret_store=FakeSecretStore(), factory=factory, audit=FakeAudit())
    router.route(_ctx("t1"))  # a real in-use connection for (t1, "1"); NOT released
    assert pool.counts("t1", "1") == (0, 1)
    factory.fail_for("t1")  # a second mint for the SAME key now fails
    try:
        router.route(_ctx("t1"))  # in_use(1) < max(5) → reaches open_fn, which fails
        assert False, "second t1 mint must deny"
    except RoutingDenied as d:
        assert d.http_status == 503 and d.public_code == "connection_unavailable"
    assert ("t1", "1") in pool.pool_keys()  # populated pool retained, not cleaned
    assert pool.counts("t1", "1") == (0, 1)  # its live in-use connection is untouched


def test_failed_open_leaves_other_tenant_pool_untouched() -> None:
    read = FakeRoutingRead()
    read.set_view("t1")
    read.set_view("t2")
    secrets = FakeSecretStore()
    secrets.set_missing("tenant/t2/db")  # only t2's secret is unresolvable
    router, _, pool, _ = make_router(read=read, secret_store=secrets, factory=FakeConnectionFactory(), audit=FakeAudit())
    router.route(_ctx("t1"))  # populated (t1, "1") in-use pool; NOT released
    assert pool.counts("t1", "1") == (0, 1)
    try:
        router.route(_ctx("t2"))
        assert False, "t2 missing secret must deny"
    except RoutingDenied as d:
        assert d.http_status == 503 and d.public_code == "connection_unavailable"
    assert ("t1", "1") in pool.pool_keys() and pool.counts("t1", "1") == (0, 1)  # untouched
    assert ("t2", "1") not in pool.pool_keys()  # failed t2 key removed, not another key


def test_pool_acquire_propagates_open_fn_exception_and_leaves_no_key() -> None:
    pool = ConnectionPoolManager()
    sentinel = LookupError("secret unresolved")

    def open_fn():
        raise sentinel

    caught = None
    try:
        pool.acquire("t", "1", open_fn)
        assert False, "open_fn failure must propagate out of acquire"
    except LookupError as e:
        caught = e
    assert caught is sentinel  # exact instance re-raised, not wrapped or replaced
    assert pool.pool_keys() == []  # no phantom key left behind


if __name__ == "__main__":
    _h.run(
        [
            test_creation_is_lazy,
            test_release_rolls_back_and_resets_then_pools,
            test_lru_idle_eviction,
            test_broken_idle_connection_is_replaced,
            test_failure_recovery_never_falls_back_to_another_tenant,
            test_failed_secret_resolution_leaves_no_empty_pool_key,
            test_failed_factory_open_leaves_no_empty_pool_key,
            test_misbound_open_leaves_no_empty_pool_key,
            test_failed_open_preserves_populated_same_key_pool,
            test_failed_open_leaves_other_tenant_pool_untouched,
            test_pool_acquire_propagates_open_fn_exception_and_leaves_no_key,
        ]
    )
