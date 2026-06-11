"""Connection Isolation Standard (PRD-P4-R2 E; D-13/D-30): Tenant A conn != Tenant B conn."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from shared.context import RequestContext  # noqa: E402

from database_router.models import RoutingDenied  # noqa: E402
from doubles import (  # noqa: E402
    FakeAudit,
    FakeConnectionFactory,
    FakeRoutingRead,
    FakeSecretStore,
    make_router,
)


def _ctx(tenant_id):
    return RequestContext(correlation_id="c", active_tenant_id=tenant_id, principal_ref="p", role="TENANT_ADMIN")


def _wire(**kw):
    read = FakeRoutingRead()
    read.set_view("t1")
    read.set_view("t2")
    factory = FakeConnectionFactory()
    audit = FakeAudit()
    router, cache, pool, resolver = make_router(
        read=read, secret_store=FakeSecretStore(), factory=factory, audit=audit, **kw
    )
    return router, factory, pool, read


def test_two_tenants_get_distinct_connections_and_pools() -> None:
    router, factory, pool, _ = _wire()
    r1 = router.route(_ctx("t1"))
    r2 = router.route(_ctx("t2"))
    assert r1.connection.id != r2.connection.id
    assert r1.connection.tenant_id == "t1" and r2.connection.tenant_id == "t2"
    assert ("t1", "1") in pool.pool_keys() and ("t2", "1") in pool.pool_keys()


def test_same_tenant_reuses_its_own_connection() -> None:
    router, factory, _, _ = _wire()
    r1 = router.route(_ctx("t1"))
    first_id = r1.connection.id
    router.release(r1)
    r2 = router.route(_ctx("t1"))
    assert r2.connection.id == first_id          # reused
    assert factory.opens == [("t1", "1")]        # only opened once


def test_connection_never_reused_across_tenants() -> None:
    router, factory, _, _ = _wire()
    r1 = router.route(_ctx("t1"))
    router.release(r1)                            # t1 connection now idle
    r2 = router.route(_ctx("t2"))                 # must NOT borrow t1's idle connection
    assert r2.connection.tenant_id == "t2"
    assert r2.connection.id != r1.connection.id


def test_association_version_separates_pools() -> None:
    router, factory, pool, read = _wire()
    r1 = router.route(_ctx("t1"))                 # (t1, v1)
    assert r1.association_version == "1"
    # Re-association: control plane now reports a new version; push-invalidate the cache.
    read.set_view("t1", lifecycle="Ready", ready=True, version="2")
    router.invalidate_tenant("t1")
    r2 = router.route(_ctx("t1"))                 # (t1, v2) — a distinct pool/connection
    assert r2.association_version == "2"
    assert ("t1", "1") in pool.pool_keys() and ("t1", "2") in pool.pool_keys()
    assert r1.connection.id != r2.connection.id


def test_misbound_connection_is_rejected_and_closed() -> None:
    router, factory, _, _ = _wire()
    factory.misbind = True                        # factory returns a wrong-tenant connection
    try:
        router.route(_ctx("t1"))
        assert False, "a connection bound to another tenant must be rejected"
    except RoutingDenied as d:
        assert d.http_status == 503 and d.public_code == "connection_unavailable"


if __name__ == "__main__":
    _h.run([
        test_two_tenants_get_distinct_connections_and_pools,
        test_same_tenant_reuses_its_own_connection,
        test_connection_never_reused_across_tenants,
        test_association_version_separates_pools,
        test_misbound_connection_is_rejected_and_closed,
    ])
