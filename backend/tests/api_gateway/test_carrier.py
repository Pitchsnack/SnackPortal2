"""Carrier enforcement (IC-010 §E/§F): match-or-reject, prohibited stripping, CONTROL anomaly."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _gateway_doubles as D  # noqa: E402
import _h  # noqa: E402

from api_gateway.models import AuditAction  # noqa: E402


def test_matching_header_carrier_ok() -> None:
    gateway, _authn, router, _audit = D.tenant_setup()
    resp = gateway.handle(D.req(path="/tenant/x", headers={"X-Tenant-Id": "t1"}, authorization="tok-t1"))
    assert resp.status == 200 and resp.dispatched
    assert router.handoffs[0][1].target_tenant_id == "t1"


def test_matching_subdomain_carrier_ok() -> None:
    gateway, _authn, router, _audit = D.tenant_setup()
    resp = gateway.handle(D.req(path="/tenant/x", host="t1.snackportal.example", authorization="tok-t1"))
    assert resp.status == 200 and router.handoffs[0][1].target_tenant_id == "t1"


def test_carrier_mismatch_403_and_audited() -> None:
    gateway, _authn, router, audit = D.tenant_setup()
    resp = gateway.handle(D.req(path="/tenant/x", headers={"X-Tenant-Id": "t2"}, authorization="tok-t1"))
    assert resp.status == 403 and resp.public_code == "carrier_mismatch"
    assert not router.handoffs  # fail-closed: never dispatched
    assert [e.action for e in audit.events] == [AuditAction.CARRIER_MISMATCH]


def test_prohibited_carriers_ignored_not_honored() -> None:
    # A cookie/query tenant value that DIFFERS from the claim must NOT change routing.
    gateway, _authn, router, _audit = D.tenant_setup()
    resp = gateway.handle(
        D.req(path="/tenant/x", headers={"X-Tenant-Id": "t1"}, cookies={"tenant": "t2"}, query={"tenant": "t2"}, authorization="tok-t1")
    )
    assert resp.status == 200 and router.handoffs[0][1].target_tenant_id == "t1"


def test_unrecognized_header_is_not_a_carrier() -> None:
    gateway, _authn, router, _audit = D.tenant_setup()
    resp = gateway.handle(D.req(path="/tenant/x", headers={"X-Foo": "t2", "X-Tenant-Id": "t1"}, authorization="tok-t1"))
    assert resp.status == 200 and router.handoffs[0][1].target_tenant_id == "t1"


def test_carrier_on_control_token_ignored_and_anomaly_emitted() -> None:
    # A recognized carrier on a tenantless CONTROL token is ignored (claim-only) and MUST
    # emit the mandatory CarrierOnControlAnomaly (IC-010 §F).
    authn = D.StubAuthenticator()
    authn.add_token("tok-ctl", principal="ops", tenant=None, role="CONTROL")
    router = D.StubRouterDispatch()
    audit = D.RecordingAuditEmitter()
    gateway = D.build_gateway(authenticator=authn, router=router, audit=audit)
    resp = gateway.handle(D.req(path="/directory/startups", headers={"X-Tenant-Id": "t9"}, authorization="tok-ctl"))
    assert resp.status == 200  # carrier ignored; control-plane read proceeds
    assert [e.action for e in audit.events] == [AuditAction.CARRIER_ON_CONTROL_ANOMALY]
    assert router.handoffs[0][1].target_tenant_id is None  # CONTROL domain, no tenant


if __name__ == "__main__":
    _h.run(
        [
            test_matching_header_carrier_ok,
            test_matching_subdomain_carrier_ok,
            test_carrier_mismatch_403_and_audited,
            test_prohibited_carriers_ignored_not_honored,
            test_unrecognized_header_is_not_a_carrier,
            test_carrier_on_control_token_ignored_and_anomaly_emitted,
        ]
    )
