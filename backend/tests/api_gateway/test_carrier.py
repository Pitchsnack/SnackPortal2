"""Carrier enforcement (IC-010 §E/§F): match-or-reject, prohibited stripping, CONTROL anomaly."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _gateway_doubles as D  # noqa: E402
import _h  # noqa: E402

from api_gateway.carrier import _subdomain, recognized_carriers  # noqa: E402
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


# --- IP-literal / localhost / malformed host carrier hardening (IC-005 D-33 / IC-010 §E) ---
# A host-derived carrier is a tenant DNS subdomain ONLY. A transport address (an IP literal)
# is never a tenant carrier, so it must not manufacture a phantom carrier that trips the
# len(set(carriers)) > 1 isolation gate — while genuine DNS straddles still fail closed.


def test_ipv4_literal_host_is_not_a_subdomain_carrier() -> None:
    # An IPv4 literal Host (with or without a port) asserts no host carrier; only the
    # X-Tenant-Id carrier remains, so recognized_carriers yields exactly the header value.
    assert _subdomain("127.0.0.1") is None
    assert _subdomain("127.0.0.1:5542") is None
    assert recognized_carriers(D.req(host="127.0.0.1", headers={"X-Tenant-Id": "t1"})) == ["t1"]


def test_ipv4_literal_golden_request_proceeds_not_isolation_anomaly() -> None:
    # Exact served-rehearsal G1 regression: a loopback-IP Host + matching X-Tenant-Id +
    # signed t1 claim proceeds (200, dispatched to t1) — NOT a phantom-"127" isolation_anomaly.
    gateway, _authn, router, _audit = D.tenant_setup()
    resp = gateway.handle(D.req(path="/tenant/x", host="127.0.0.1", headers={"X-Tenant-Id": "t1"}, authorization="tok-t1"))
    assert resp.status == 200 and resp.dispatched
    assert router.handoffs[0][1].target_tenant_id == "t1"


def test_ipv6_literal_host_is_not_a_subdomain_carrier() -> None:
    # Bracketed IPv6 literals (with or without a port) assert no host carrier — now
    # intentional via bracket-strip + ipaddress — and the golden request still proceeds.
    assert _subdomain("[::1]") is None
    assert _subdomain("[::1]:5542") is None
    assert _subdomain("[2001:db8::1]") is None
    gateway, _authn, router, _audit = D.tenant_setup()
    resp = gateway.handle(D.req(path="/tenant/x", host="[::1]", headers={"X-Tenant-Id": "t1"}, authorization="tok-t1"))
    assert resp.status == 200 and router.handoffs[0][1].target_tenant_id == "t1"


def test_localhost_host_is_not_a_subdomain_carrier() -> None:
    # A single-label host (localhost, with or without a port) asserts no host carrier.
    assert _subdomain("localhost") is None
    assert _subdomain("localhost:5542") is None
    gateway, _authn, router, _audit = D.tenant_setup()
    resp = gateway.handle(D.req(path="/tenant/x", host="localhost", headers={"X-Tenant-Id": "t1"}, authorization="tok-t1"))
    assert resp.status == 200 and router.handoffs[0][1].target_tenant_id == "t1"


def test_genuine_dns_subdomain_carrier_preserved() -> None:
    # Over-hardening guard: a genuine multi-label DNS host still yields its leading label
    # (port-stripped), and drives a matching-claim request to a 200 dispatched to t1.
    assert _subdomain("t1.snackportal.example") == "t1"
    assert _subdomain("t1.snackportal.example:8443") == "t1"
    gateway, _authn, router, _audit = D.tenant_setup()
    resp = gateway.handle(D.req(path="/tenant/x", host="t1.snackportal.example", authorization="tok-t1"))
    assert resp.status == 200 and resp.dispatched
    assert router.handoffs[0][1].target_tenant_id == "t1"


def test_dns_subdomain_plus_mismatched_header_still_straddles() -> None:
    # A genuine dual-carrier straddle (DNS subdomain t1 + header t2) still fails closed:
    # 403 isolation_anomaly, never dispatched, audited exactly once. (multi-carrier denial intact)
    gateway, _authn, router, audit = D.tenant_setup()
    resp = gateway.handle(D.req(path="/tenant/x", host="t1.snackportal.example", headers={"X-Tenant-Id": "t2"}, authorization="tok-t1"))
    assert resp.status == 403 and resp.public_code == "isolation_anomaly"
    assert not router.handoffs
    assert [e.action for e in audit.events] == [AuditAction.ISOLATION_ANOMALY]


def test_ipv4_literal_bare_host_uses_claim_not_phantom_carrier() -> None:
    # A bare IP Host with NO X-Tenant-Id asserts no carrier at all: the signed claim governs
    # routing (no phantom "127" fed into the IC-005 carrier-match) → 200 dispatched to t1.
    gateway, _authn, router, _audit = D.tenant_setup()
    resp = gateway.handle(D.req(path="/tenant/x", host="127.0.0.1", authorization="tok-t1"))
    assert resp.status == 200 and resp.dispatched
    assert router.handoffs[0][1].target_tenant_id == "t1"


def test_malformed_host_fails_closed_no_carrier() -> None:
    # Empty, whitespace-only, unterminated bracketed IPv6, and leading-dot hosts fail closed:
    # no manufactured tenant carrier and no exception.
    assert _subdomain("") is None
    assert _subdomain("   ") is None
    assert _subdomain("[::1") is None
    assert _subdomain(".x.y") is None


if __name__ == "__main__":
    _h.run(
        [
            test_matching_header_carrier_ok,
            test_matching_subdomain_carrier_ok,
            test_carrier_mismatch_403_and_audited,
            test_prohibited_carriers_ignored_not_honored,
            test_unrecognized_header_is_not_a_carrier,
            test_carrier_on_control_token_ignored_and_anomaly_emitted,
            test_ipv4_literal_host_is_not_a_subdomain_carrier,
            test_ipv4_literal_golden_request_proceeds_not_isolation_anomaly,
            test_ipv6_literal_host_is_not_a_subdomain_carrier,
            test_localhost_host_is_not_a_subdomain_carrier,
            test_genuine_dns_subdomain_carrier_preserved,
            test_dns_subdomain_plus_mismatched_header_still_straddles,
            test_ipv4_literal_bare_host_uses_claim_not_phantom_carrier,
            test_malformed_host_fails_closed_no_carrier,
        ]
    )
