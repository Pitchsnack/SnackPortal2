"""Dispatch taxonomy + one-request-one-DB (IC-010 §X/§Q/§K); IR-09; MASTER_AGENT fan-out."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _gateway_doubles as D  # noqa: E402
import _h  # noqa: E402

from api_gateway.dispatch import default_classifier  # noqa: E402
from api_gateway.models import DatabaseDomain, DispatchCategory  # noqa: E402


def test_taxonomy_path_to_category() -> None:
    assert default_classifier(D.req(path="/tenant/x")) is DispatchCategory.TENANT_OPERATION
    assert default_classifier(D.req(path="/directory/startups")) is DispatchCategory.GLOBAL_DIRECTORY_READ
    assert default_classifier(D.req(path="/memberships")) is DispatchCategory.MEMBERSHIPS_FOR_PRINCIPAL
    assert default_classifier(D.req(path="/import/run")) is DispatchCategory.IMPORT_INITIATION


def test_classification_is_path_only_not_carrier() -> None:
    # The dispatch decision must not vary with a client-supplied tenant/workspace value.
    a = default_classifier(D.req(path="/tenant/x", headers={"X-Tenant-Id": "t1"}, query={"tenant": "t9"}))
    b = default_classifier(D.req(path="/tenant/x", headers={"X-Tenant-Id": "t2"}, cookies={"workspace": "w"}))
    assert a is b is DispatchCategory.TENANT_OPERATION


def test_one_request_one_database() -> None:
    gateway, _authn, router, _audit = D.tenant_setup()
    gateway.handle(D.req(path="/tenant/x", headers={"X-Tenant-Id": "t1"}, authorization="tok-t1"))
    assert len(router.handoffs) == 1
    decision = router.handoffs[0][1]
    assert decision.domain is DatabaseDomain.TENANT and decision.target_tenant_id == "t1"


def test_control_read_targets_control_domain() -> None:
    authn = D.StubAuthenticator()
    authn.add_token("tok-ctl", principal="ops", tenant=None, role="CONTROL")
    router = D.StubRouterDispatch()
    gateway = D.build_gateway(authenticator=authn, router=router, audit=D.RecordingAuditEmitter())
    gateway.handle(D.req(path="/directory/startups", authorization="tok-ctl"))
    decision = router.handoffs[0][1]
    assert decision.domain is DatabaseDomain.CONTROL and decision.target_tenant_id is None


def test_tenant_op_under_control_token_denied() -> None:
    authn = D.StubAuthenticator()
    authn.add_token("tok-ctl", principal="ops", tenant=None, role="CONTROL")
    router = D.StubRouterDispatch()
    gateway = D.build_gateway(authenticator=authn, router=router, audit=D.RecordingAuditEmitter())
    resp = gateway.handle(D.req(path="/tenant/x", authorization="tok-ctl"))
    assert resp.status == 403 and resp.public_code == "tenant_context_required"
    assert not router.handoffs


def test_import_is_single_tenant_db_write() -> None:
    # IR-09: import initiation resolves to exactly one tenant DB, never a Control+tenant straddle.
    gateway, _authn, router, _audit = D.tenant_setup()
    gateway.handle(D.req(method="POST", path="/import/run", headers={"X-Tenant-Id": "t1"}, authorization="tok-t1"))
    decision = router.handoffs[0][1]
    assert decision.category is DispatchCategory.IMPORT_INITIATION
    assert decision.domain is DatabaseDomain.TENANT and decision.target_tenant_id == "t1"


def test_master_agent_request_resolves_to_single_tenant() -> None:
    # A multi-membership MASTER_AGENT request still resolves to exactly one tenant DB (IC-009 P.4).
    authn = D.StubAuthenticator()
    authn.add_token("tok-ma", principal="agent", tenant="t1", role="MASTER_AGENT")
    router = D.StubRouterDispatch()
    gateway = D.build_gateway(authenticator=authn, router=router, audit=D.RecordingAuditEmitter())
    gateway.handle(D.req(path="/tenant/x", headers={"X-Tenant-Id": "t1"}, authorization="tok-ma"))
    assert router.handoffs[0][1].target_tenant_id == "t1"


if __name__ == "__main__":
    _h.run(
        [
            test_taxonomy_path_to_category,
            test_classification_is_path_only_not_carrier,
            test_one_request_one_database,
            test_control_read_targets_control_domain,
            test_tenant_op_under_control_token_denied,
            test_import_is_single_tenant_db_write,
            test_master_agent_request_resolves_to_single_tenant,
        ]
    )
