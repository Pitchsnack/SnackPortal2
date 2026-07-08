"""DB-free end-to-end gateway auth-transport smoke (07E-3c).

Wires ONLY existing components across the REAL 07E-3b HTTP transport pair: an
``InboundRequest`` enters the REAL Gateway pipeline (``build_gateway``); authentication
crosses the wire — ``HttpAuthenticator`` client → loopback single-threaded
``build_authenticate_server`` hosting the REAL ``Authenticator`` composed from the stdlib
auth_router doubles (no PyJWT, no control plane, no PostgreSQL) — and the returned 4-field
``AuthResult`` builds the gateway ``RequestContext`` through the existing exclusive path;
downstream dispatch is the recording ``StubRouterDispatch`` FAKE (resolves NO database —
the Database Router is never touched). No live PostgreSQL, no live auth provider, no
Lovable/frontend, no deployment lifecycle: the server is test-hosted on a daemon thread —
production-shaped, not default-composed. Location note: lives under ``tests/api_gateway``
(the wrapper's sanctioned alternative) because the test tree is package-imported
(``__init__.py`` throughout) and a new ``tests/integration`` package would need an
``__init__.py`` outside the authorized file surface.

Invariants preserved: Authentication ≠ Routing ≠ Authorization ≠ Database Access;
One Request → One Active Tenant → One Database; CONTROL derived from
``active_tenant_id is None`` (never a field).
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import sys
import threading
from typing import Iterator, Optional, Tuple

_HERE = pathlib.Path(__file__).resolve().parent
# Insert auth_router's test dir first, then api_gateway's LAST so it wins position 0: the shared
# ``_h``/``_gateway_doubles`` names resolve to api_gateway; ``_auth_doubles`` is unique to auth_router.
sys.path.insert(0, str(_HERE.parent / "auth_router"))
sys.path.insert(0, str(_HERE))
import _auth_doubles as D  # noqa: E402
import _gateway_doubles as G  # noqa: E402
import _h  # noqa: E402

from api_gateway.adapters.providers.http_authenticator import HttpAuthenticator  # noqa: E402
from api_gateway.main import GW_AUTH_ROUTER_BASE_URL_ENV, build_authenticator_from_env, build_gateway  # noqa: E402
from api_gateway.models import DatabaseDomain, DispatchCategory  # noqa: E402
from auth_router.adapters.providers.http_authenticate_api import build_authenticate_server  # noqa: E402
from auth_router.main import build_authenticator  # noqa: E402
from auth_router.models import Role  # noqa: E402

_ISS = "https://platform.snackportal"
_SECRET = b"07e3c-smoke-secret"


def _compose_loopback_auth_router() -> Tuple[object, str]:
    """Host the REAL auth stack in-process: doubles-composed Authenticator behind the REAL
    single-threaded loopback transport server (test-owned daemon thread; no serve lifecycle
    in production code — deployment scope)."""
    read = D.FakeControlPlaneRead()
    read.set_tenant("t1", ready=True)
    read.add_member("u1", "t1", Role.TENANT_AGENT)
    authenticator = build_authenticator(verifier=D.HmacTestVerifier(), read=read, issuers={_ISS: D.issuer_cfg(issuer=_ISS, secret=_SECRET)})
    server, base_url = build_authenticate_server(authenticator, "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, base_url


def _tenant_token(sub: str = "u1", tenant: Optional[str] = "t1") -> str:
    return D.make_hs256_jwt(D.claims(sub=sub, iss=_ISS, tenant=tenant), secret=_SECRET)


@contextlib.contextmanager
def _env(value: Optional[str]) -> Iterator[None]:
    prior = os.environ.get(GW_AUTH_ROUTER_BASE_URL_ENV)
    try:
        if value is None:
            os.environ.pop(GW_AUTH_ROUTER_BASE_URL_ENV, None)
        else:
            os.environ[GW_AUTH_ROUTER_BASE_URL_ENV] = value
        yield
    finally:
        if prior is None:
            os.environ.pop(GW_AUTH_ROUTER_BASE_URL_ENV, None)
        else:
            os.environ[GW_AUTH_ROUTER_BASE_URL_ENV] = prior


def test_smoke_success_tenant_request_via_env_selected_transport() -> None:
    server, base_url = _compose_loopback_auth_router()
    try:
        # The env-selected seam picks the REAL transport client bound to the loopback server.
        with _env(base_url):
            authenticator = build_authenticator_from_env()
        assert isinstance(authenticator, HttpAuthenticator)
        router = G.StubRouterDispatch()
        gateway = build_gateway(authenticator=authenticator, router=router)

        response = gateway.handle(
            G.req(
                "GET",
                "/tenant/deals",
                headers={"X-Tenant-Id": "t1"},
                authorization="Bearer " + _tenant_token(),
                correlation_id="smoke-cid-1",
            )
        )

        # Full chain: request → gateway → HTTP transport → real Authenticator → 4-field
        # AuthResult → RequestContext (built EXCLUSIVELY from AuthResult) → FAKED dispatch.
        assert (response.status, response.public_code, response.dispatched) == (200, "ok", True)
        assert response.category is DispatchCategory.TENANT_OPERATION
        assert len(router.handoffs) == 1, "the request must reach the FAKED dispatch exactly once"
        context, decision = router.handoffs[0]
        assert (context.correlation_id, context.principal_ref, context.active_tenant_id, context.role) == (
            "smoke-cid-1",
            "u1",
            "t1",
            "TENANT_AGENT",
        )
        assert decision.domain is DatabaseDomain.TENANT and decision.target_tenant_id == "t1"
    finally:
        server.shutdown()  # type: ignore[attr-defined]
        server.server_close()  # type: ignore[attr-defined]


def test_smoke_control_token_derives_tenantless_context() -> None:
    server, base_url = _compose_loopback_auth_router()
    try:
        router = G.StubRouterDispatch()
        gateway = build_gateway(authenticator=HttpAuthenticator(base_url), router=router)

        # A tenantless CONTROL-scope token (no tenant claim), no carrier, on a Control-domain read.
        response = gateway.handle(
            G.req("GET", "/directory/global", authorization="Bearer " + _tenant_token(sub="ctl", tenant=None), correlation_id="smoke-cid-2")
        )

        assert (response.status, response.public_code, response.dispatched) == (200, "ok", True)
        assert response.category is DispatchCategory.GLOBAL_DIRECTORY_READ
        context, decision = router.handoffs[0]
        # CONTROL is DERIVED from active_tenant_id is None across the wire — never a field.
        assert context.principal_ref == "ctl" and context.active_tenant_id is None and context.role is None
        assert decision.domain is DatabaseDomain.CONTROL and decision.target_tenant_id is None
    finally:
        server.shutdown()  # type: ignore[attr-defined]
        server.server_close()  # type: ignore[attr-defined]


def test_smoke_bad_token_maps_401_and_never_dispatches() -> None:
    server, base_url = _compose_loopback_auth_router()
    try:
        router = G.StubRouterDispatch()
        gateway = build_gateway(authenticator=HttpAuthenticator(base_url), router=router)

        response = gateway.handle(
            G.req("GET", "/tenant/deals", headers={"X-Tenant-Id": "t1"}, authorization="Bearer opaque-invalid-credential")
        )

        # The real Authenticator's denial crosses the wire as the EXISTING public code.
        assert (response.status, response.public_code) == (401, "unauthenticated")
        assert router.handoffs == [], "no dispatch on auth failure (fail closed)"
    finally:
        server.shutdown()  # type: ignore[attr-defined]
        server.server_close()  # type: ignore[attr-defined]


def test_smoke_carrier_mismatch_maps_403_and_never_dispatches() -> None:
    server, base_url = _compose_loopback_auth_router()
    try:
        router = G.StubRouterDispatch()
        gateway = build_gateway(authenticator=HttpAuthenticator(base_url), router=router)

        # Carrier asserts t2 while the signed claim is t1 → IC-005 match-or-reject across the wire.
        response = gateway.handle(G.req("GET", "/tenant/deals", headers={"X-Tenant-Id": "t2"}, authorization="Bearer " + _tenant_token()))

        assert (response.status, response.public_code) == (403, "carrier_mismatch")
        assert router.handoffs == [], "no dispatch on carrier mismatch (fail closed)"
    finally:
        server.shutdown()  # type: ignore[attr-defined]
        server.server_close()  # type: ignore[attr-defined]


if __name__ == "__main__":
    _h.run(
        [
            test_smoke_success_tenant_request_via_env_selected_transport,
            test_smoke_control_token_derives_tenantless_context,
            test_smoke_bad_token_maps_401_and_never_dispatches,
            test_smoke_carrier_mismatch_maps_403_and_never_dispatches,
        ]
    )
