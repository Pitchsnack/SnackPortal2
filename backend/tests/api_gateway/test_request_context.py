"""RequestContext is constructed EXCLUSIVELY from AuthContext (IC-010 §G/§T / §W crit 6).

Load-bearing: active_tenant_id is the signed claim and is NEVER set from a carrier/header/
cookie/query/host value; the context carries references only (no token/PII).
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _gateway_doubles as D  # noqa: E402
import _h  # noqa: E402

from api_gateway.models import AuthResult  # noqa: E402
from api_gateway.request_context import build_request_context  # noqa: E402


def test_context_built_only_from_auth_result() -> None:
    auth = AuthResult(correlation_id="c1", principal_ref="p1", active_tenant_id="t1", role="TENANT_AGENT")
    ctx = build_request_context(auth)
    assert ctx.active_tenant_id == "t1" and ctx.principal_ref == "p1" and ctx.role == "TENANT_AGENT"
    assert ctx.correlation_id == "c1"


def test_active_tenant_id_independent_of_inbound_carriers() -> None:
    # Identical AuthContext but differing (ignored) inbound prohibited carriers => identical
    # active_tenant_id handed to the router. A query/cookie tenant cannot move the request.
    gateway, _authn, router, _audit = D.tenant_setup()
    gateway.handle(D.req(path="/tenant/x", headers={"X-Tenant-Id": "t1"}, authorization="tok-t1"))
    gateway.handle(
        D.req(path="/tenant/x", headers={"X-Tenant-Id": "t1"}, query={"tenant": "t9"}, cookies={"workspace": "w9"}, authorization="tok-t1")
    )
    assert router.handoffs[0][0].active_tenant_id == router.handoffs[1][0].active_tenant_id == "t1"


def test_context_carries_no_token_or_secret() -> None:
    gateway, _authn, router, _audit = D.tenant_setup()
    secret_bearer = "tok-t1"
    gateway.handle(D.req(path="/tenant/x", headers={"X-Tenant-Id": "t1"}, authorization=secret_bearer))
    ctx = router.handoffs[0][0]
    for value in (ctx.correlation_id, ctx.request_id, ctx.active_tenant_id, ctx.principal_ref, ctx.role):
        assert value != secret_bearer  # the bearer credential never enters the context


if __name__ == "__main__":
    _h.run(
        [
            test_context_built_only_from_auth_result,
            test_active_tenant_id_independent_of_inbound_carriers,
            test_context_carries_no_token_or_secret,
        ]
    )
