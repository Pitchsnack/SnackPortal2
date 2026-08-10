"""Env-selected composition of the two public edges — the REAL transport clients, no network.

The adversarial suite injects a fake identity provider. This file closes the remaining gap: it
composes both edges through the actual ``build_*_server_from_env`` seams, so the real
``HttpPrincipalAuthenticator`` is the one wired in, and then proves the fail-closed behaviour
that matters when it cannot be reached.

No standing service is contacted. Every base URL points at a loopback port that is deliberately
NOT listening, so "connection refused" is the transport failure under test — the fastest and
most honest way to exercise the unavailable path without touching anything that exists. Only
the ephemeral sockets these tests bind themselves are ever opened.
"""

from __future__ import annotations

import pathlib
import socket
import sys

# APPEND, never insert(0): backend/tests contains packages named after the services
# (tests/database_router/, tests/control_plane/, tests/shared/). Putting it first makes those
# EMPTY stubs win over the production packages, which silently blinds any sys.modules census.
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from gateway_free._fakes import ACME_BEARER, ACME_REF, HostedEdge, bearer, decode  # noqa: E402

import control_plane.main as cp_main  # noqa: E402
import database_router.main as dbr_main  # noqa: E402
from shared.adapters.providers.http_principal_authenticator import HttpPrincipalAuthenticator  # noqa: E402
from shared.public_edge import PublicBoundaryDenied  # noqa: E402

_ACME_TARGET = "/tenant/startups/" + ACME_REF


def _closed_port() -> int:
    """An ephemeral port that is bound, read, and released — so nothing is listening on it."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _set_common(monkeypatch, auth_port: int) -> None:
    monkeypatch.setenv(dbr_main.SP2_EDGE_AUTH_ROUTER_BASE_URL, f"http://127.0.0.1:{auth_port}")
    monkeypatch.delenv(dbr_main.SP2_EDGE_AUDIT_SINK_BASE_URL, raising=False)
    monkeypatch.setenv(dbr_main.SP2_EDGE_ALLOWED_ORIGINS, "http://localhost:5173")


def test_the_startup_edge_composes_from_env_with_the_real_auth_client(monkeypatch) -> None:
    _set_common(monkeypatch, _closed_port())
    monkeypatch.setenv(dbr_main.SP2_DBR_ROUTING_READ_BASE_URL, f"http://127.0.0.1:{_closed_port()}")

    boundary = dbr_main.build_public_boundary_from_env()
    assert boundary is not None, "a complete composition must produce a boundary"
    assert isinstance(boundary._authenticator, HttpPrincipalAuthenticator), "the REAL IC-005 transport client must be wired"

    deps = dbr_main.build_public_startup_edge_deps_from_env()
    assert deps is not None, "a complete composition must produce edge dependencies"
    _ops, _boundary, origins = deps
    assert origins == ("http://localhost:5173",), "the exact-origin allowlist comes from the environment"

    composed = dbr_main.build_public_startup_edge_server_from_env()
    assert composed is not None, "a complete composition must produce a bound server"
    server, base_url = composed
    with HostedEdge(server, base_url) as edge:
        # The Auth Router is not listening: authentication is unreachable, so the request fails
        # closed to 503 with an empty body. It never degrades into an unauthenticated success.
        status, body, headers = edge.request("GET", _ACME_TARGET, headers=bearer(ACME_BEARER))
    assert status == 503, "an unreachable Auth Router must fail the request closed"
    assert body == b"", "and disclose nothing about why"
    assert headers["cache-control"] == "no-store"
    assert headers["x-correlation-id"], "the correlation id is minted and echoed even on a failure"


def test_the_workspace_edge_composes_from_env_with_the_real_auth_client(monkeypatch) -> None:
    _set_common(monkeypatch, _closed_port())
    monkeypatch.delenv("SP2_CP_CONTROL_STORE", raising=False)

    composed = cp_main.build_public_workspace_edge_server_from_env()
    assert composed is not None, "a complete composition must produce a bound server"
    server, base_url = composed
    with HostedEdge(server, base_url) as edge:
        status, body, _headers = edge.request("GET", "/memberships", headers=bearer(ACME_BEARER))
    assert status == 503, "an unreachable Auth Router must fail the request closed"
    assert body == b""


def test_the_real_auth_client_maps_an_unreachable_router_to_unavailable() -> None:
    client = HttpPrincipalAuthenticator(f"http://127.0.0.1:{_closed_port()}", timeout=1.0)
    try:
        client.authenticate("Bearer anything", [], "corr-1")
    except PublicBoundaryDenied as denied:
        assert (denied.http_status, denied.public_code) == (503, "unavailable"), "a refused connection is 503 unavailable"
        return
    raise AssertionError("an unreachable Auth Router must raise, never return a principal")


def test_operational_routes_answer_without_the_auth_router(monkeypatch) -> None:
    # Health and readiness are deliberately unauthenticated so an operator can probe a degraded
    # edge. They must therefore disclose nothing, which the adversarial suite pins separately.
    _set_common(monkeypatch, _closed_port())
    monkeypatch.setenv(dbr_main.SP2_DBR_ROUTING_READ_BASE_URL, f"http://127.0.0.1:{_closed_port()}")
    composed = dbr_main.build_public_startup_edge_server_from_env()
    assert composed is not None
    server, base_url = composed
    with HostedEdge(server, base_url) as edge:
        for path in ("/health", "/readiness"):
            status, body, _headers = edge.request("GET", path)
            assert status == 200, f"{path} must answer even when the Auth Router is unreachable"
            rendered = str(decode(body))
            # Operational status only. The edge's own service NAME is lawful; a tenant identity,
            # a database name, a host/port, or any topology detail is not.
            for leak in ("127.0.0.1", "t-acme", "t-zeta", "5541", "5540", "postgres", "dsn"):
                assert leak not in rendered.lower(), f"readiness must not disclose {leak!r}"


def test_a_malformed_audit_selector_refuses_to_compose(monkeypatch) -> None:
    _set_common(monkeypatch, _closed_port())
    monkeypatch.setenv(dbr_main.SP2_EDGE_AUDIT_SINK_BASE_URL, "https://audit.example")
    try:
        dbr_main.build_public_boundary_from_env()
    except ValueError:
        return
    raise AssertionError("a malformed audit sink URL must raise before any socket, never fall back to in-memory")
