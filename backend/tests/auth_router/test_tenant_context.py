"""Stage 2 tenant context: carrier-match, membership, consistent denial, fail-closed."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402
import doubles as D  # noqa: E402

from auth_router.models import AuthDenied, Claims, Role  # noqa: E402
from auth_router.tenant_context import TenantContextResolver  # noqa: E402


def _claims(tenant="t1", sub="user1") -> Claims:
    return Claims(subject=sub, issuer="iss", audience="aud", tenant=tenant)


def test_member_resolves_context_with_role() -> None:
    read = D.FakeControlPlaneRead()
    read.set_tenant("t1", ready=True)
    read.add_member("user1", "t1", Role.TENANT_ADMIN)
    ctx = TenantContextResolver(read).resolve(_claims(), correlation_id="c")
    assert ctx.active_tenant_id == "t1" and ctx.role == "TENANT_ADMIN" and ctx.principal_ref == "user1"


def test_carrier_match_required() -> None:
    read = D.FakeControlPlaneRead()
    read.set_tenant("t1", ready=True)
    read.add_member("user1", "t1", Role.TENANT_AGENT)
    TenantContextResolver(read).resolve(_claims(), correlation_id="c", carrier_tenant="t1")  # match ok
    try:
        TenantContextResolver(read).resolve(_claims(), correlation_id="c", carrier_tenant="t2")
        assert False, "carrier mismatch must 403"
    except AuthDenied as e:
        assert e.http_status == 403 and e.public_code == "carrier_mismatch"


def test_unknown_and_nonmember_indistinguishable() -> None:
    read = D.FakeControlPlaneRead()
    try:
        TenantContextResolver(read).resolve(_claims(tenant="ghost"), correlation_id="c")
        assert False
    except AuthDenied as e1:
        code_unknown = e1.public_code
    read.set_tenant("t1", ready=True)  # exists, but principal is not a member
    try:
        TenantContextResolver(read).resolve(_claims(tenant="t1", sub="stranger"), correlation_id="c")
        assert False
    except AuthDenied as e2:
        code_nonmember = e2.public_code
    assert code_unknown == code_nonmember == "tenant_access_denied"


def test_member_of_not_ready_tenant() -> None:
    read = D.FakeControlPlaneRead()
    read.set_tenant("t1", ready=False, lifecycle="Verifying")
    read.add_member("user1", "t1", Role.TENANT_ADMIN)
    try:
        TenantContextResolver(read).resolve(_claims(), correlation_id="c")
        assert False
    except AuthDenied as e:
        assert e.public_code == "tenant_not_ready"


def test_fail_closed_when_control_plane_unavailable() -> None:
    read = D.FakeControlPlaneRead()
    read.set_unavailable()
    try:
        TenantContextResolver(read).resolve(_claims(), correlation_id="c")
        assert False
    except AuthDenied as e:
        assert e.http_status == 503


def test_no_tenant_claim_is_control_scope() -> None:
    ctx = TenantContextResolver(D.FakeControlPlaneRead()).resolve(_claims(tenant=None), correlation_id="c")
    assert ctx.active_tenant_id is None and ctx.role is None


if __name__ == "__main__":
    _h.run([
        test_member_resolves_context_with_role,
        test_carrier_match_required,
        test_unknown_and_nonmember_indistinguishable,
        test_member_of_not_ready_tenant,
        test_fail_closed_when_control_plane_unavailable,
        test_no_tenant_claim_is_control_scope,
    ])
