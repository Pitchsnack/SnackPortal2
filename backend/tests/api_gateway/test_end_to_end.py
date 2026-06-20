"""End-to-end gateway flow (IC-010 §C): happy paths dispatch once, emit nothing, resolve no DB."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _gateway_doubles as D  # noqa: E402
import _h  # noqa: E402

from api_gateway.models import DatabaseDomain, DispatchCategory  # noqa: E402


def test_tenant_operation_end_to_end() -> None:
    gateway, _authn, router, audit = D.tenant_setup()
    resp = gateway.handle(D.req(method="POST", path="/tenant/deals", host="t1.snackportal.example", authorization="tok-t1"))
    assert resp.status == 200 and resp.dispatched and resp.category is DispatchCategory.TENANT_OPERATION
    assert len(router.handoffs) == 1
    ctx, decision = router.handoffs[0]
    assert ctx.active_tenant_id == "t1" and decision.domain is DatabaseDomain.TENANT and decision.target_tenant_id == "t1"
    assert audit.events == []  # a clean request emits no anomaly


def test_control_directory_read_end_to_end() -> None:
    authn = D.StubAuthenticator()
    authn.add_token("tok-ctl", principal="ops", tenant=None, role="CONTROL")
    router = D.StubRouterDispatch()
    audit = D.RecordingAuditEmitter()
    gateway = D.build_gateway(authenticator=authn, router=router, audit=audit)
    resp = gateway.handle(D.req(path="/directory/investors", authorization="tok-ctl"))
    assert resp.status == 200 and resp.category is DispatchCategory.GLOBAL_DIRECTORY_READ
    assert router.handoffs[0][1].domain is DatabaseDomain.CONTROL
    assert audit.events == []


if __name__ == "__main__":
    _h.run([test_tenant_operation_end_to_end, test_control_directory_read_end_to_end])
