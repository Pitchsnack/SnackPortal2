"""Live-wire denial-semantics parity (B5-3) — 403 tenant_access_denied, never 503, over a REAL wire.

The narrowest REAL topology for the LW-1 proof (wrapper §8.3): a REAL control-plane read
edge (``make_server`` over a ``ControlPlane`` with an in-memory store; daemon-thread served —
the Smoke A/B hosting precedent) → the REAL ``HttpControlPlaneRead`` transport client → the
REAL ``Authenticator``/``TenantContextResolver`` denial path (stdlib HS256 doubles for the
signature stage; tokens minted at runtime — no ``eyJ`` literal), plus the REAL Auth Router
authenticate wire (``build_authenticate_server``) driven by the REAL API Gateway
``HttpAuthenticator`` client.

Proven here:
* an UNKNOWN tenant over the live wire produces a LIVE HTTP 404 from the read edge, which
  ``HttpControlPlaneRead`` maps to ``None`` → ``AuthDenied(403, "tenant_access_denied")`` —
  parity with the in-memory double, NEVER 503;
* the same denial crosses the authenticate wire as 403 — the gateway client raises the
  pinned ``forbidden()`` rejection. NOTE (documented per §8.3): the authenticate transport
  buckets granular non-carrier 403 reasons to the public code ``forbidden`` by the PINNED
  IC-010 §E/§L disclosure mapping (``http_authenticate_api._map_denied``; ``HttpAuthenticator
  ._map_error``; the Smoke A/B precedent) — ``tenant_access_denied`` is asserted at the
  Authenticator boundary where the granular code exists, and NOT-503 is asserted on BOTH legs;
* 503 remains RESERVED for real unavailability: an unreachable read edge still maps to
  ``AuthDenied(503, "control_plane_unavailable")`` (the semantics split LW-1 restores).

Mutation reasoning (wrapper §8.4 item 7): without the LW-1 404 catch, the live 404 raises
``HTTPError`` inside ``TenantContextResolver``'s sanitizing ``except`` → 503
``control_plane_unavailable`` → ``test_live_unknown_tenant_denies_403...`` fails on both legs.

Stdlib-only; DB-free; bounded daemon threads; every server closed in ``finally``; runnable
standalone:  python tests/api_gateway/test_live_wire_denial_semantics.py
"""

from __future__ import annotations

import pathlib
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Tuple

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "auth_router"))
sys.path.insert(0, str(_HERE))
import _auth_doubles as A  # noqa: E402
import _h  # noqa: E402

from api_gateway.adapters.providers.http_authenticator import HttpAuthenticator  # noqa: E402
from api_gateway.models import RequestRejected  # noqa: E402
from auth_router.adapters.providers.http_authenticate_api import build_authenticate_server  # noqa: E402
from auth_router.adapters.providers.http_control_plane_read import HttpControlPlaneRead  # noqa: E402
from auth_router.main import build_authenticator  # noqa: E402
from auth_router.models import AuthDenied  # noqa: E402
from control_plane.adapters.providers.http_read_api import make_server  # noqa: E402
from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.main import ControlPlane  # noqa: E402

_ISS = "https://platform.snackportal"
_SECRET = b"b5-3-live-wire-secret"


class _ServedEdge:
    """Host a REAL single-threaded server on a bounded test-owned daemon thread."""

    def __init__(self, server: object, base_url: str) -> None:
        self.server = server
        self.base_url = base_url

    def __enter__(self) -> "_ServedEdge":
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)  # type: ignore[attr-defined]
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.shutdown()  # type: ignore[attr-defined]
        self._thread.join(timeout=10.0)
        self.server.server_close()  # type: ignore[attr-defined]
        assert not self._thread.is_alive(), "served edge thread must terminate (bounded join)"


def _await_serving(base_url: str, probe_path: str) -> None:
    """Deadline-poll until the edge PROCESSES a request (any HTTP response counts)."""
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(base_url + probe_path, timeout=2.0).close()
            return
        except urllib.error.HTTPError:
            return  # a status response (404/405/...) proves the serve loop is processing
        except (urllib.error.URLError, OSError):
            time.sleep(0.05)
    raise AssertionError("edge did not start serving before the deadline")


def _live_read_edge() -> Tuple[object, str]:
    """The REAL control-plane read edge over an EMPTY in-memory store (every tenant unknown)."""
    return make_server(ControlPlane(store=InMemoryControlStore()), "127.0.0.1", 0)


def _refused_url() -> str:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return f"http://127.0.0.1:{port}"


def _token(tenant: str = "t-unknown") -> str:
    return A.make_hs256_jwt(A.claims(sub="u1", iss=_ISS, tenant=tenant), secret=_SECRET)


def _authenticator(read_base_url: str) -> object:
    return build_authenticator(
        verifier=A.HmacTestVerifier(),
        read=HttpControlPlaneRead(read_base_url),
        issuers={_ISS: A.issuer_cfg(issuer=_ISS, secret=_SECRET)},
    )


# --- the core parity proof: LIVE 404 -> 403 tenant_access_denied (never 503) -------------------------
def test_live_unknown_tenant_denies_403_tenant_access_denied_not_503() -> None:
    server, base_url = _live_read_edge()
    with _ServedEdge(server, base_url):
        _await_serving(base_url, "/tenants/probe/state")
        authenticator = _authenticator(base_url)
        try:
            authenticator.authenticate(_token(), correlation_id="c-lw1", carrier_tenant=None)  # type: ignore[attr-defined]
        except AuthDenied as denied:
            assert denied.http_status == 403, (
                f"a LIVE unknown-tenant 404 must deny 403, not {denied.http_status} "
                f"({denied.public_code}) — LW-1 parity with the in-memory double"
            )
            assert denied.public_code == "tenant_access_denied", (
                f"the granular denial must be tenant_access_denied (got {denied.public_code!r})"
            )
        else:
            raise AssertionError("an unknown tenant over the live wire must be DENIED")


# --- the same denial crosses the authenticate wire as 403 (gateway client mapping) -------------------
def test_live_denial_crosses_authenticate_wire_as_403_not_503() -> None:
    read_server, read_url = _live_read_edge()
    with _ServedEdge(read_server, read_url):
        _await_serving(read_url, "/tenants/probe/state")
        auth_server, auth_url = build_authenticate_server(_authenticator(read_url), "127.0.0.1", 0)
        with _ServedEdge(auth_server, auth_url):
            client = HttpAuthenticator(auth_url)
            try:
                client.authenticate("Bearer " + _token(), [], "c-lw2")
            except RequestRejected as rejected:
                assert rejected.http_status == 403, (
                    f"the live denial must cross the wire as 403, not {rejected.http_status} ({rejected.public_code})"
                )
                # The wire buckets granular non-carrier 403s to the public 'forbidden' code by the
                # PINNED IC-010 disclosure mapping (never a tenant-existence leak) — and NEVER 503.
                assert rejected.public_code == "forbidden"
            else:
                raise AssertionError("the live denial must cross the authenticate wire as a rejection")


# --- 503 stays reserved for REAL unavailability (the split LW-1 restores) ----------------------------
def test_unreachable_read_edge_still_maps_to_503_unavailable() -> None:
    authenticator = _authenticator(_refused_url())
    try:
        authenticator.authenticate(_token(), correlation_id="c-lw3", carrier_tenant=None)  # type: ignore[attr-defined]
    except AuthDenied as denied:
        assert denied.http_status == 503 and denied.public_code == "control_plane_unavailable", (
            f"a truly unreachable control plane must stay 503 control_plane_unavailable (got {denied.http_status} {denied.public_code!r})"
        )
    else:
        raise AssertionError("an unreachable control plane must fail closed")


_TESTS = [
    test_live_unknown_tenant_denies_403_tenant_access_denied_not_503,
    test_live_denial_crosses_authenticate_wire_as_403_not_503,
    test_unreachable_read_edge_still_maps_to_503_unavailable,
]

if __name__ == "__main__":
    _h.run(_TESTS)
