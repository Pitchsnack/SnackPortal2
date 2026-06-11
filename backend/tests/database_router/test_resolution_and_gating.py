"""Readiness + schema-version gating (PRD-P4-E1 §18; IC-002/D-16/D-17) and denial mapping."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402
from _db_doubles import (  # noqa: E402
    FakeAudit,
    FakeConnectionFactory,
    FakeRoutingRead,
    FakeSecretStore,
    make_router,
)

from database_router.models import RoutingDenied  # noqa: E402
from shared.context import RequestContext  # noqa: E402


def _route(tenant_id="t1", **wire):
    read = FakeRoutingRead()
    if "view" in wire:
        wire["view"](read)
    router, _, _, _ = make_router(
        read=read,
        secret_store=FakeSecretStore(),
        factory=FakeConnectionFactory(),
        audit=FakeAudit(),
        supported=wire.get("supported", ("1",)),
    )
    ctx = RequestContext(correlation_id="c", active_tenant_id=tenant_id, principal_ref="p", role="TENANT_ADMIN")
    return router.route(ctx)


def _expect_denial(view_fn, status, code, supported=("1",)):
    try:
        _route(view=view_fn, supported=supported)
        assert False, f"expected denial {code}"
    except RoutingDenied as d:
        assert d.http_status == status, f"{code}: status {d.http_status} != {status}"
        assert d.public_code == code, f"code {d.public_code} != {code}"


def test_ready_tenant_routes() -> None:
    result = _route(view=lambda r: r.set_view("t1", lifecycle="Ready", ready=True))
    assert result.tenant_id == "t1"


def test_unknown_tenant_is_not_found() -> None:
    _expect_denial(lambda r: None, 404, "not_found")


def test_suspended_is_administratively_disabled() -> None:
    _expect_denial(lambda r: r.set_view("t1", lifecycle="Suspended", ready=False), 403, "administratively_disabled")


def test_failed_is_unavailable() -> None:
    _expect_denial(lambda r: r.set_view("t1", lifecycle="Failed", ready=False), 503, "unavailable")


def test_provisioning_is_not_ready() -> None:
    _expect_denial(lambda r: r.set_view("t1", lifecycle="Provisioning", ready=False), 503, "not_ready")


def test_decommissioned_is_not_found() -> None:
    _expect_denial(lambda r: r.set_view("t1", lifecycle="Decommissioned", ready=False), 404, "not_found")


def test_ready_state_but_not_ready_flag_denies() -> None:
    # Defense in depth: lifecycle says Ready but the derived flag is false.
    _expect_denial(lambda r: r.set_view("t1", lifecycle="Ready", ready=False), 503, "not_ready")


def test_schema_out_of_range_is_not_ready() -> None:
    _expect_denial(
        lambda r: r.set_view("t1", lifecycle="Ready", ready=True, schema="9"),
        503,
        "schema_out_of_range",
        supported=("1",),
    )


def test_control_plane_unavailable_fails_closed() -> None:
    read = FakeRoutingRead()
    read.set_view("t1")
    read.set_unavailable()
    router, _, _, _ = make_router(read=read, secret_store=FakeSecretStore(), factory=FakeConnectionFactory(), audit=FakeAudit())
    ctx = RequestContext(correlation_id="c", active_tenant_id="t1", principal_ref="p", role="TENANT_ADMIN")
    try:
        router.route(ctx)
        assert False, "must fail closed when the control plane is unavailable"
    except RoutingDenied as d:
        assert d.http_status == 503 and d.public_code == "control_plane_unavailable"


if __name__ == "__main__":
    _h.run(
        [
            test_ready_tenant_routes,
            test_unknown_tenant_is_not_found,
            test_suspended_is_administratively_disabled,
            test_failed_is_unavailable,
            test_provisioning_is_not_ready,
            test_decommissioned_is_not_found,
            test_ready_state_but_not_ready_flag_denies,
            test_schema_out_of_range_is_not_ready,
            test_control_plane_unavailable_fails_closed,
        ]
    )
