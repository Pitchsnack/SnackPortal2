"""DB-free API Gateway Smoke B — real DatabaseRouter over DB doubles (topology smoke).

Upgrades Smoke A (07E-3d ``test_gateway_auth_and_router_transport_smoke.py``) by replacing
the hand-rolled FAKE dispatch server with a REAL ``build_dispatch_server`` hosting a REAL
``DatabaseRouter`` composed from the database_router stdlib doubles
(``_db_doubles.make_router``: ``FakeRoutingRead`` + ``FakeConnectionFactory`` +
``FakeSecretStore`` + ``FakeAudit``). It drives the full gateway pipeline across BOTH real
transports, DB-free:

    InboundRequest
      -> Gateway.handle (build_gateway with build_authenticator_from_env() +
         build_router_dispatch_from_env(), both env-selected)
      -> HttpAuthenticator -> loopback build_authenticate_server (REAL Authenticator over the
         auth_router doubles: HmacTestVerifier + FakeControlPlaneRead + issuer_cfg; no PyJWT,
         no control plane, no PostgreSQL)
      -> 4-field AuthResult -> RequestContext
      -> HttpRouterDispatch -> loopback build_dispatch_server hosting a REAL DatabaseRouter
         over DB doubles -> real route()/isolation/bind-release -> references-only RouteOutcome

Smoke B proves the gateway/auth/dispatch wire PLUS the real DatabaseRouter
routing/isolation/connection-lifecycle over doubles. It proves NOTHING about production
runnability, physical tenant-DB isolation, B5-BLK-4 closure, or Physical Multi-Database MVP
completion — every bound connection is a FAKE (this is Smoke B, not Smoke C). Invariants
preserved: Authentication != Routing != Authorization != Database Access; Global Record !=
Tenant Record; One Request -> One Active Tenant -> One Database; references only on both
wires (the gateway-computed target_tenant_id/domain never cross the dispatch wire — the
router binds solely from the signed claim). DB-free by construction: only the fake
connection factory + fake secret store are used; no psycopg, no DSN, no real PostgreSQL.

Placed under ``tests/api_gateway`` (not ``tests/integration``): the package-imported test
tree would need a ``tests/integration/__init__.py`` outside the authorized surface — the
07E-3c/3d precedent. This test crosses three services' test doubles (api_gateway seams +
auth_router ``_auth_doubles`` + database_router ``_db_doubles``); permissible because
import-linter does not analyze ``tests/``.
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import sys
import threading
from http.server import HTTPServer
from typing import Iterator, Tuple

_HERE = pathlib.Path(__file__).resolve().parent
# Put the two sibling service test dirs on sys.path for their UNIQUE double modules
# (``_auth_doubles`` -> auth_router, ``_db_doubles`` -> database_router), then api_gateway's
# own dir LAST so it wins sys.path[0] for the SHARED names (``_h``, ``_gateway_doubles``).
sys.path.insert(0, str(_HERE.parent / "auth_router"))
sys.path.insert(0, str(_HERE.parent / "database_router"))
sys.path.insert(0, str(_HERE))
import _auth_doubles as A  # noqa: E402
import _db_doubles as R  # noqa: E402
import _gateway_doubles as G  # noqa: E402
import _h  # noqa: E402

from api_gateway.main import (  # noqa: E402
    GW_AUTH_ROUTER_BASE_URL_ENV,
    GW_DB_ROUTER_BASE_URL_ENV,
    build_authenticator_from_env,
    build_gateway,
    build_router_dispatch_from_env,
)
from api_gateway.models import DispatchCategory  # noqa: E402
from auth_router.adapters.providers.http_authenticate_api import build_authenticate_server  # noqa: E402
from auth_router.main import build_authenticator  # noqa: E402
from auth_router.models import Role  # noqa: E402
from database_router.adapters.providers.http_dispatch_api import build_dispatch_server  # noqa: E402

_ISS = "https://platform.snackportal"
_SECRET = b"smoke-b-db-doubles-secret"


def _compose_loopback_auth_router() -> Tuple[HTTPServer, str]:
    """Host the REAL auth stack in-process: a doubles-composed Authenticator (HmacTestVerifier
    + FakeControlPlaneRead + issuer_cfg; no PyJWT, no control plane, no PostgreSQL) behind the
    REAL loopback auth transport server on a test-owned daemon thread. ``u1`` is a TENANT_AGENT
    of both ``t1`` and ``t2`` so the AUTH stage always issues a claim; the routing DECISION is
    made by the real DatabaseRouter on the dispatch side (the point of Smoke B)."""
    read = A.FakeControlPlaneRead()
    for tenant in ("t1", "t2"):
        read.set_tenant(tenant, ready=True)
        read.add_member("u1", tenant, Role.TENANT_AGENT)
    authenticator = build_authenticator(
        verifier=A.HmacTestVerifier(),
        read=read,
        issuers={_ISS: A.issuer_cfg(issuer=_ISS, secret=_SECRET)},
    )
    server, base_url = build_authenticate_server(authenticator, "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, base_url


def _tenant_token(tenant: str = "t1", *, sub: str = "u1") -> str:
    """A runtime-minted HS256 tenant token (no ``eyJ``-shaped literal committed)."""
    return A.make_hs256_jwt(A.claims(sub=sub, iss=_ISS, tenant=tenant), secret=_SECRET)


@contextlib.contextmanager
def _both_env(*, auth_url: str, db_router_url: str) -> Iterator[None]:
    """Set BOTH transport selectors for the two build_*_from_env() calls, always restoring
    the prior environment values afterward."""
    keys = {GW_AUTH_ROUTER_BASE_URL_ENV: auth_url, GW_DB_ROUTER_BASE_URL_ENV: db_router_url}
    prior = {k: os.environ.get(k) for k in keys}
    try:
        for k, v in keys.items():
            os.environ[k] = v
        yield
    finally:
        for k, v in prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@contextlib.contextmanager
def _smoke_topology(read: "R.FakeRoutingRead") -> Iterator[Tuple[object, object, object, object]]:
    """Compose the full Smoke B topology: REAL auth loopback server + REAL dispatch loopback
    server hosting a REAL DatabaseRouter over DB doubles, wired into the gateway through BOTH
    env-selected transport seams. Yields ``(gateway, factory, pool, audit)`` so the caller can
    prove the real router's connection lifecycle (open/release) and no-route on denial /
    auth fail-closed. Both loopback servers are shut down and closed in ``finally``."""
    auth_server, auth_url = _compose_loopback_auth_router()
    factory = R.FakeConnectionFactory()
    audit = R.FakeAudit()
    router, _cache, pool, _resolver = R.make_router(
        read=read,
        secret_store=R.FakeSecretStore(),
        factory=factory,
        audit=audit,
        supported=("1",),
    )
    dispatch_server, dispatch_url = build_dispatch_server(router, "127.0.0.1", 0)
    threading.Thread(target=dispatch_server.serve_forever, daemon=True).start()
    try:
        with _both_env(auth_url=auth_url, db_router_url=dispatch_url):
            authenticator = build_authenticator_from_env()
            router_dispatch = build_router_dispatch_from_env()
        assert authenticator is not None and router_dispatch is not None, "both seams must select real transports"
        yield build_gateway(authenticator=authenticator, router=router_dispatch), factory, pool, audit
    finally:
        auth_server.shutdown()
        auth_server.server_close()
        dispatch_server.shutdown()
        dispatch_server.server_close()


def test_smoke_success_binds_and_releases_exactly_one_connection() -> None:
    # Ready tenant t1 (lifecycle Ready, ready True, version/schema "1"). The full chain crosses
    # BOTH real wires and the REAL DatabaseRouter: auth -> 4-field AuthResult -> RequestContext
    # -> dispatch client -> real DatabaseRouter over doubles -> references-only RouteOutcome.
    read = R.FakeRoutingRead()
    read.set_view("t1")
    with _smoke_topology(read) as (gateway, factory, pool, audit):
        response = gateway.handle(
            G.req(
                "GET",
                "/tenant/deals",
                headers={"X-Tenant-Id": "t1"},
                authorization="Bearer " + _tenant_token(),
                correlation_id="smoke-b-ok",
            )
        )
    assert (response.status, response.public_code, response.dispatched) == (200, "ok", True)
    assert response.category is DispatchCategory.TENANT_OPERATION
    # The REAL DatabaseRouter opened exactly ONE fake tenant connection for (t1, assoc "1")
    # and released it back to idle before responding: one request -> one tenant -> one DB.
    assert factory.opens == [("t1", "1")], factory.opens
    assert pool.counts("t1", "1") == (1, 0), pool.counts("t1", "1")
    # The real router genuinely ran (its success audit fired) — no CONTROL shortcut.
    assert "Route" in audit.actions() and "RouteControl" not in audit.actions()


def test_smoke_unknown_tenant_maps_not_found_no_bind() -> None:
    # No routing view for t1 -> the REAL DatabaseRouter denies on resolution (not_found) and
    # binds NO connection. Auth still issues the t1 claim (auth-side membership); isolation is
    # decided by the router, not the gateway.
    read = R.FakeRoutingRead()
    with _smoke_topology(read) as (gateway, factory, pool, audit):
        response = gateway.handle(G.req("GET", "/tenant/deals", headers={"X-Tenant-Id": "t1"}, authorization="Bearer " + _tenant_token()))
    assert (response.status, response.public_code, response.dispatched) == (404, "not_found", False)
    assert factory.opens == [], factory.opens
    assert pool.counts("t1", "1") == (0, 0), pool.counts("t1", "1")
    # Dispatch WAS reached and the real router denied (no bind) — this is router-side isolation.
    assert audit.actions() == ["RouteDenied"], audit.actions()


def test_smoke_suspended_tenant_maps_administratively_disabled_no_bind() -> None:
    # Suspended tenant t2 -> administratively_disabled via the REAL DatabaseRouter; no connection
    # is bound. Token + carrier are t2 (auth succeeds); the router makes the isolation decision.
    read = R.FakeRoutingRead()
    read.set_view("t2", lifecycle="Suspended", ready=False)
    with _smoke_topology(read) as (gateway, factory, pool, audit):
        response = gateway.handle(
            G.req(
                "GET",
                "/tenant/deals",
                headers={"X-Tenant-Id": "t2"},
                authorization="Bearer " + _tenant_token("t2"),
                correlation_id="smoke-b-susp",
            )
        )
    assert (response.status, response.public_code, response.dispatched) == (403, "administratively_disabled", False)
    assert factory.opens == [], factory.opens
    assert pool.counts("t2", "1") == (0, 0), pool.counts("t2", "1")
    assert audit.actions() == ["RouteDenied"], audit.actions()


def test_smoke_bad_token_maps_401_before_dispatch_never_reaches_router() -> None:
    # A bad token fails closed at auth (401 unauthenticated) BEFORE dispatch — the real
    # DatabaseRouter is never reached (no open, no audit event).
    read = R.FakeRoutingRead()
    read.set_view("t1")
    with _smoke_topology(read) as (gateway, factory, pool, audit):
        response = gateway.handle(
            G.req("GET", "/tenant/deals", headers={"X-Tenant-Id": "t1"}, authorization="Bearer opaque-invalid-credential")
        )
    assert (response.status, response.public_code) == (401, "unauthenticated")
    assert factory.opens == [], factory.opens
    assert audit.events == [], audit.actions()


def test_smoke_carrier_mismatch_maps_403_before_dispatch_never_reaches_router() -> None:
    # Carrier asserts t2 while the signed claim is t1 -> IC-005 match-or-reject (403
    # carrier_mismatch) BEFORE dispatch — the real DatabaseRouter is never reached.
    read = R.FakeRoutingRead()
    read.set_view("t1")
    with _smoke_topology(read) as (gateway, factory, pool, audit):
        response = gateway.handle(
            G.req("GET", "/tenant/deals", headers={"X-Tenant-Id": "t2"}, authorization="Bearer " + _tenant_token("t1"))
        )
    assert (response.status, response.public_code) == (403, "carrier_mismatch")
    assert factory.opens == [], factory.opens
    assert audit.events == [], audit.actions()


if __name__ == "__main__":
    _h.run(
        [
            test_smoke_success_binds_and_releases_exactly_one_connection,
            test_smoke_unknown_tenant_maps_not_found_no_bind,
            test_smoke_suspended_tenant_maps_administratively_disabled_no_bind,
            test_smoke_bad_token_maps_401_before_dispatch_never_reaches_router,
            test_smoke_carrier_mismatch_maps_403_before_dispatch_never_reaches_router,
        ]
    )
