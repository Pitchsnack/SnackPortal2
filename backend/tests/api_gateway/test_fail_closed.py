"""Fail-closed (IC-010 §L): every failure -> Request Rejected; no fallback/default/partial."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _gateway_doubles as D  # noqa: E402
import _h  # noqa: E402

from api_gateway.models import AuditAction  # noqa: E402


def test_unauthenticated_rejected() -> None:
    gateway, _authn, router, _audit = D.tenant_setup()
    resp = gateway.handle(D.req(path="/tenant/x", authorization=None))
    assert resp.status == 401 and resp.public_code == "unauthenticated"
    assert not router.handoffs and not resp.dispatched


def test_authenticator_unavailable_fails_closed() -> None:
    gateway, authn, router, _audit = D.tenant_setup()
    authn.set_unavailable()
    resp = gateway.handle(D.req(path="/tenant/x", headers={"X-Tenant-Id": "t1"}, authorization="tok-t1"))
    assert resp.status == 503  # no fallback, no default tenant
    assert not router.handoffs


def test_unknown_route_route_denied_and_audited() -> None:
    gateway, _authn, router, audit = D.tenant_setup()
    resp = gateway.handle(D.req(path="/nope", headers={"X-Tenant-Id": "t1"}, authorization="tok-t1"))
    assert resp.status == 403 and resp.public_code == "unknown_route"
    assert not router.handoffs
    assert [e.action for e in audit.events] == [AuditAction.ROUTE_DENIED]


def test_denial_never_dispatches_or_defaults_a_tenant() -> None:
    gateway, _authn, router, _audit = D.tenant_setup()
    resp = gateway.handle(D.req(path="/tenant/x", headers={"X-Tenant-Id": "t2"}, authorization="tok-t1"))
    assert resp.status == 403 and not resp.dispatched and resp.category is None
    assert not router.handoffs


def test_consistent_denial_no_existence_leak() -> None:
    # An access-denied response carries only status + public_code (no tenant/DB identifier),
    # and is identical whether the cause is an unknown tenant or a non-member (consistent denial).
    gateway, authn, _router, _audit = D.tenant_setup()
    authn.set_deny_access()
    r1 = gateway.handle(D.req(path="/tenant/x", headers={"X-Tenant-Id": "t1"}, authorization="tok-t1"))
    r2 = gateway.handle(D.req(path="/tenant/x", headers={"X-Tenant-Id": "t1"}, authorization="tok-t1"))
    assert (r1.status, r1.public_code) == (r2.status, r2.public_code) == (403, "tenant_access_denied")


if __name__ == "__main__":
    _h.run(
        [
            test_unauthenticated_rejected,
            test_authenticator_unavailable_fails_closed,
            test_unknown_route_route_denied_and_audited,
            test_denial_never_dispatches_or_defaults_a_tenant,
            test_consistent_denial_no_existence_leak,
        ]
    )
