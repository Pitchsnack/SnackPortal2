"""07E-2-X — RouteOutcome runtime seam (non-live, references-only; IC-010 §152-154).

Proves the gateway DERIVES its GatewayResponse from the Database Router's references-only
RouteOutcome (no longer a hardcoded 200/"ok"), that `category` stays gateway-owned
(RX-1 — never taken from the router), that the router still records its handoff (RX-4),
and that RouteOutcome carries only references-safe primitive fields (no body / tenant id /
DB handle / secret / payload). Non-live: the router resolves no database.
"""

from __future__ import annotations

import dataclasses
import pathlib
import sys
from typing import List, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _gateway_doubles as D  # noqa: E402
import _h  # noqa: E402

from api_gateway.models import (  # noqa: E402
    DispatchCategory,
    DispatchDecision,
    GatewayResponse,
    RouteOutcome,
)
from api_gateway.ports import RouterDispatchPort  # noqa: E402
from shared.context import RequestContext  # noqa: E402


class _OutcomeRouter(RouterDispatchPort):
    """A stub router returning a caller-supplied RouteOutcome; STILL records handoffs so a
    non-default outcome cannot silently drop the handoff regression (RX-4)."""

    def __init__(self, outcome: RouteOutcome) -> None:
        self._outcome = outcome
        self.handoffs: List[Tuple[RequestContext, DispatchDecision]] = []

    def dispatch(self, context: RequestContext, decision: DispatchDecision) -> RouteOutcome:
        self.handoffs.append((context, decision))
        return self._outcome


def _tenant_gateway_with(router: RouterDispatchPort):
    authn = D.StubAuthenticator()
    authn.add_token("tok-t1", principal="p1", tenant="t1", role="TENANT_AGENT")
    return D.build_gateway(authenticator=authn, router=router, audit=D.RecordingAuditEmitter())


def _control_gateway_with(router: RouterDispatchPort):
    authn = D.StubAuthenticator()
    authn.add_token("tok-ctl", principal="ops", tenant=None, role="CONTROL")
    return D.build_gateway(authenticator=authn, router=router, audit=D.RecordingAuditEmitter())


def test_default_stub_outcome_maps_to_existing_200_ok() -> None:
    # Regression: the default StubRouterDispatch returns RouteOutcome(200,"ok",True); the
    # gateway maps it to the exact pre-07E-2-X 200/"ok"/dispatched behavior — unchanged.
    gateway, _authn, router, _audit = D.tenant_setup()
    resp = gateway.handle(D.req(method="POST", path="/tenant/deals", authorization="tok-t1"))
    assert (resp.status, resp.public_code, resp.dispatched) == (200, "ok", True)
    assert resp.category is DispatchCategory.TENANT_OPERATION
    assert len(router.handoffs) == 1  # RX-4: handoff still recorded


def test_response_is_derived_from_route_outcome_not_hardcoded() -> None:
    # An alternate outcome proves the response is DERIVED from RouteOutcome, not synthesized.
    router = _OutcomeRouter(RouteOutcome(status=503, public_code="unavailable", dispatched=False))
    gateway = _tenant_gateway_with(router)
    resp = gateway.handle(D.req(method="POST", path="/tenant/deals", authorization="tok-t1"))
    assert (resp.status, resp.public_code, resp.dispatched) == (503, "unavailable", False)
    assert len(router.handoffs) == 1  # RX-4: handoff recorded even on a non-default outcome


def test_category_stays_gateway_owned_not_from_route_outcome() -> None:
    # RX-1: `category` is the gateway's per-request classification, never a router value.
    # The SAME alternate RouteOutcome on two different paths yields two DIFFERENT gateway
    # categories — so category cannot be coming from RouteOutcome (which carries none).
    outcome = RouteOutcome(status=503, public_code="unavailable", dispatched=False)

    tenant_resp = _tenant_gateway_with(_OutcomeRouter(outcome)).handle(D.req(method="POST", path="/tenant/deals", authorization="tok-t1"))
    assert tenant_resp.category is DispatchCategory.TENANT_OPERATION

    control_resp = _control_gateway_with(_OutcomeRouter(outcome)).handle(D.req(path="/directory/investors", authorization="tok-ctl"))
    assert control_resp.category is DispatchCategory.GLOBAL_DIRECTORY_READ


def test_route_outcome_is_references_only_primitive_fields() -> None:
    # References-only: exactly {status, public_code, dispatched}, all primitives — nothing
    # that could carry a body / tenant id / DB handle / secret / payload across the seam.
    field_names = {f.name for f in dataclasses.fields(RouteOutcome)}
    assert field_names == {"status", "public_code", "dispatched"}, field_names

    sample = RouteOutcome(status=200, public_code="ok", dispatched=True)
    assert isinstance(sample.status, int)
    assert isinstance(sample.public_code, str)
    assert isinstance(sample.dispatched, bool)

    # frozen / immutable (no post-hoc smuggling of extra state)
    raised = False
    try:
        sample.status = 500  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        raised = True
    assert raised, "RouteOutcome must be a frozen dataclass"


def test_gateway_response_carries_no_body_and_no_db_resolution() -> None:
    # No body/payload can propagate to the client: GatewayResponse has only status /
    # public_code / dispatched / category, plus the B5-BLK-6B `portal_dto` seam — the
    # single typed, catalogue-closed, defaulted-None IC-010 §V composition field (never a
    # body/payload carrier). And the gateway resolves no database — the stub router
    # records the handoff but opens nothing (non-live).
    gw_field_names = {f.name for f in dataclasses.fields(GatewayResponse)}
    assert gw_field_names == {"status", "public_code", "dispatched", "category", "portal_dto"}, gw_field_names

    gateway, _authn, router, _audit = D.tenant_setup()
    gateway.handle(D.req(method="POST", path="/tenant/deals", authorization="tok-t1"))
    ctx, _decision = router.handoffs[0]
    # The router received the context to select a DB; the gateway itself resolved none.
    assert ctx.active_tenant_id == "t1"


if __name__ == "__main__":
    _h.run(
        [
            test_default_stub_outcome_maps_to_existing_200_ok,
            test_response_is_derived_from_route_outcome_not_hardcoded,
            test_category_stays_gateway_owned_not_from_route_outcome,
            test_route_outcome_is_references_only_primitive_fields,
            test_gateway_response_carries_no_body_and_no_db_resolution,
        ]
    )
