"""End-to-end: full authentication -> RequestContext{principal, active_tenant, role}."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _auth_doubles as D  # noqa: E402
import _h  # noqa: E402

from auth_router.main import build_authenticator, liveness  # noqa: E402
from auth_router.models import Role  # noqa: E402

_ISS = "https://platform.snackportal"
_SECRET = b"e2e-secret"


def test_full_authentication_flow() -> None:
    cfg = D.issuer_cfg(issuer=_ISS, secret=_SECRET)
    read = D.FakeControlPlaneRead()
    read.set_tenant("t1", ready=True)
    read.add_member("u1", "t1", Role.STARTUP_USER)
    auth = build_authenticator(verifier=D.HmacTestVerifier(), read=read, issuers={_ISS: cfg})

    tok = D.make_hs256_jwt(D.claims(sub="u1", iss=_ISS, tenant="t1"), secret=_SECRET)
    ctx = auth.authenticate(tok, correlation_id="cid", carrier_tenant="t1")
    assert ctx.principal_ref == "u1"
    assert ctx.active_tenant_id == "t1"
    assert ctx.role == "STARTUP_USER"
    assert liveness()["build_phase"] == "3"


if __name__ == "__main__":
    _h.run([test_full_authentication_flow])
