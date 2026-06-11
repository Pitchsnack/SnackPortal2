"""Authentication audit: success/failure/switch/carrier-mismatch; never JWT contents."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _auth_doubles as D  # noqa: E402
import _h  # noqa: E402

from auth_router.adapters.providers.in_memory_audit_sink import InMemoryAuditSink  # noqa: E402
from auth_router.main import build_authenticator  # noqa: E402
from auth_router.models import AuthDenied, Role  # noqa: E402

_ISS = "https://platform.snackportal"
_SECRET = b"audit-secret"


def _auth_with_sink():
    cfg = D.issuer_cfg(issuer=_ISS, secret=_SECRET)
    read = D.FakeControlPlaneRead()
    for t in ("t1", "t2"):
        read.set_tenant(t, ready=True)
        read.add_member("u", t, Role.TENANT_ADMIN)
    sink = InMemoryAuditSink()
    return read, sink, build_authenticator(verifier=D.HmacTestVerifier(), read=read, issuers={_ISS: cfg}, audit=sink)


def test_success_is_audited() -> None:
    _, sink, auth = _auth_with_sink()
    tok = D.make_hs256_jwt(D.claims(sub="u", iss=_ISS, tenant="t1"), secret=_SECRET)
    auth.authenticate(tok, correlation_id="c1")
    assert ("Authenticate", "success") in [(e.action, e.outcome) for e in sink.events()]


def test_failure_audited_without_jwt_or_secret() -> None:
    _, sink, auth = _auth_with_sink()
    bad = D.make_hs256_jwt(D.claims(sub="u", iss=_ISS, tenant="t1"), secret=b"WRONG-SECRET")
    try:
        auth.authenticate(bad, correlation_id="c2")
    except AuthDenied:
        pass
    events = sink.events()
    assert any(e.outcome.startswith("denied") for e in events)
    for e in events:
        blob = e.actor_ref + e.action + e.outcome + (e.target_ref or "") + e.correlation_id
        assert "WRONG-SECRET" not in blob and bad not in blob  # no secret / no raw token in audit


def test_carrier_mismatch_audited() -> None:
    _, sink, auth = _auth_with_sink()
    tok = D.make_hs256_jwt(D.claims(sub="u", iss=_ISS, tenant="t1"), secret=_SECRET)
    try:
        auth.authenticate(tok, correlation_id="c3", carrier_tenant="t2")
    except AuthDenied:
        pass
    assert any(e.action == "CarrierMismatch" for e in sink.events())


def test_tenant_switch_audited() -> None:
    _, sink, auth = _auth_with_sink()
    tok = D.make_hs256_jwt(D.claims(sub="u", iss=_ISS, tenant="t2"), secret=_SECRET)
    auth.authenticate(tok, correlation_id="c4", previous_tenant="t1")
    assert any(e.action == "TenantSwitch" for e in sink.events())


if __name__ == "__main__":
    _h.run(
        [
            test_success_is_audited,
            test_failure_audited_without_jwt_or_secret,
            test_carrier_mismatch_audited,
            test_tenant_switch_audited,
        ]
    )
