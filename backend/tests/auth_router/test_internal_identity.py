"""Internal identity (D-03): CONTROL/MASTER_AGENT via platform issuer, same flow."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _auth_doubles as D  # noqa: E402
import _h  # noqa: E402

from auth_router.main import build_authenticator  # noqa: E402
from auth_router.models import Role  # noqa: E402

_ISS = "https://platform.snackportal"
_SECRET = b"platform-secret"


def _auth(read):
    cfg = D.issuer_cfg(issuer=_ISS, secret=_SECRET, allowed_algs=["HS256"])
    return build_authenticator(verifier=D.HmacTestVerifier(), read=read, issuers={_ISS: cfg})


def test_control_principal_has_no_active_tenant() -> None:
    # CONTROL token carries no tenant claim -> control-plane scope, no tenant-data access.
    auth = _auth(D.FakeControlPlaneRead())
    tok = D.make_hs256_jwt(D.claims(sub="op1", iss=_ISS, tenant=None), secret=_SECRET)
    ctx = auth.authenticate(tok, correlation_id="c")
    assert ctx.principal_ref == "op1" and ctx.active_tenant_id is None and ctx.role is None


def test_master_agent_gets_exactly_one_active_tenant() -> None:
    read = D.FakeControlPlaneRead()
    read.set_tenant("t1", ready=True)
    read.add_member("ma", "t1", Role.MASTER_AGENT)
    read.set_tenant("t2", ready=True)
    read.add_member("ma", "t2", Role.MASTER_AGENT)
    auth = _auth(read)
    tok = D.make_hs256_jwt(D.claims(sub="ma", iss=_ISS, tenant="t1"), secret=_SECRET)
    ctx = auth.authenticate(tok, correlation_id="c")
    assert ctx.active_tenant_id == "t1" and ctx.role == "MASTER_AGENT"  # one active tenant despite 2 memberships


if __name__ == "__main__":
    _h.run([test_control_principal_has_no_active_tenant, test_master_agent_gets_exactly_one_active_tenant])
