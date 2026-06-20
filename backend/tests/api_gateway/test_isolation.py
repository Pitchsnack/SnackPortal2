"""Isolation (IC-010 §K/§O): a straddle/fan-out attempt is rejected AND audited IsolationAnomaly."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _gateway_doubles as D  # noqa: E402
import _h  # noqa: E402

from api_gateway.dispatch import DispatchError, assert_single_database  # noqa: E402
from api_gateway.models import AuditAction, DatabaseDomain, DispatchCategory, DispatchDecision  # noqa: E402


def test_conflicting_tenant_carriers_raise_isolation_anomaly() -> None:
    # One request asserting two distinct tenants (subdomain t2 + header t1) is a straddle
    # attempt (e.g. a MASTER_AGENT fan-out) -> rejected fail-closed + IsolationAnomaly.
    gateway, _authn, router, audit = D.tenant_setup()
    resp = gateway.handle(D.req(path="/tenant/x", host="t2.snackportal.example", headers={"X-Tenant-Id": "t1"}, authorization="tok-t1"))
    assert resp.status == 403 and resp.public_code == "isolation_anomaly"
    assert not router.handoffs
    assert [e.action for e in audit.events] == [AuditAction.ISOLATION_ANOMALY]


def test_assert_single_database_rejects_tenant_without_id() -> None:
    bad = DispatchDecision(category=DispatchCategory.TENANT_OPERATION, domain=DatabaseDomain.TENANT, target_tenant_id=None)
    try:
        assert_single_database(bad)
        raise AssertionError("expected an IsolationAnomaly")
    except DispatchError as exc:
        assert exc.isolation_anomaly


def test_assert_single_database_rejects_control_with_tenant() -> None:
    bad = DispatchDecision(category=DispatchCategory.GLOBAL_DIRECTORY_READ, domain=DatabaseDomain.CONTROL, target_tenant_id="t1")
    try:
        assert_single_database(bad)
        raise AssertionError("expected an IsolationAnomaly")
    except DispatchError as exc:
        assert exc.isolation_anomaly


if __name__ == "__main__":
    _h.run(
        [
            test_conflicting_tenant_carriers_raise_isolation_anomaly,
            test_assert_single_database_rejects_tenant_without_id,
            test_assert_single_database_rejects_control_with_tenant,
        ]
    )
