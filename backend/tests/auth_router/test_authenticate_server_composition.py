"""Behavioral tests for the Auth Router authenticate-server composition seam.

Proves ``build_authenticate_server_from_env`` (auth_router/main.py): authenticator-gate-first
(an unset ``SP2_AR_CONTROL_PLANE_READ_BASE_URL`` returns ``None`` WITHOUT consulting the bind
knobs); a malformed Slice-1 config (bad URL / invalid ``SP2_AR_ISSUERS``) raises ``ValueError``
(inherited from ``build_authenticator_from_env``); a valid active seam passes the loopback host +
ephemeral port (or the configured host/port) through to ``build_authenticate_server``; a bad
``SP2_AR_AUTHENTICATE_PORT`` fails closed with ``ValueError`` BEFORE any socket is bound; the seam
opens no DB, performs no control-plane read, verifies no token, and never serves. Selection /
pass-through / fail-closed cases monkeypatch ``build_authenticate_server`` (a spy) so no real socket
is bound; one real-bind smoke constructs the genuine server on ``port 0`` and immediately
``server.server_close()``s it (construct-and-close only — never serves a request). Stdlib-only;
DB-free, network-free (no PyJWT token, no real key material — a placeholder JWK); runnable standalone:
  python tests/auth_router/test_authenticate_server_composition.py
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import sys
from typing import Iterator, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _auth_doubles as D  # noqa: E402,F401  (shared bootstrap; kept for parity with the auth_router test suite)
import _h  # noqa: E402

from auth_router.adapters.providers import http_authenticate_api as HAA  # noqa: E402
from auth_router.adapters.providers.http_control_plane_read import HttpControlPlaneRead  # noqa: E402
from auth_router.authenticator import Authenticator  # noqa: E402
from auth_router.main import (  # noqa: E402
    SP2_AR_AUTHENTICATE_HOST,
    SP2_AR_AUTHENTICATE_PORT,
    SP2_AR_CONTROL_PLANE_READ_BASE_URL,
    SP2_AR_ISSUERS,
    build_authenticate_server_from_env,
)

_URL = "http://127.0.0.1:1234"  # structurally valid; never connected to
_ISS = "https://issuer.example"

# A structurally valid issuers config with a PLACEHOLDER public JWK (no real key material,
# no token/secret literal). The seam treats jwks as opaque, so this never touches crypto.
_PLACEHOLDER_JWK = {
    "kty": "RSA",
    "kid": "kid-placeholder",
    "use": "sig",
    "alg": "RS256",
    "n": "placeholder-public-modulus",
    "e": "AQAB",
}
_VALID_ISSUERS = json.dumps(
    {
        _ISS: {
            "issuer": _ISS,
            "audience": "snackportal2",
            "allowed_algs": ["RS256"],
            "jwks": {"kid-placeholder": dict(_PLACEHOLDER_JWK)},
            "tenant_claim": "tenant",
        }
    }
)

_VARS = (SP2_AR_CONTROL_PLANE_READ_BASE_URL, SP2_AR_ISSUERS, SP2_AR_AUTHENTICATE_HOST, SP2_AR_AUTHENTICATE_PORT)


@contextlib.contextmanager
def _env(url: Optional[str], issuers: Optional[str], host: Optional[str], port: Optional[str]) -> Iterator[None]:
    """Set the four auth/bind env vars for one test (None => unset); restore all afterward."""
    prior = {k: os.environ.get(k) for k in _VARS}
    try:
        for key, value in zip(_VARS, (url, issuers, host, port)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key in _VARS:
            if prior[key] is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior[key]


class _Spy:
    """Records calls to build_authenticate_server; returns a sentinel tuple. ``boom=True`` asserts it
    is never invoked (so a case that must fail/return-before-construct is proven non-vacuously)."""

    def __init__(self, boom: bool = False) -> None:
        self.calls: List[Tuple[object, str, int]] = []
        self.boom = boom
        self.sentinel: Tuple[object, str] = (object(), "http://sentinel:0")

    def __call__(self, authenticator: object, host: str = "127.0.0.1", port: int = 0) -> Tuple[object, str]:
        self.calls.append((authenticator, host, port))
        if self.boom:
            raise AssertionError("build_authenticate_server must NOT be called in this case")
        return self.sentinel


@contextlib.contextmanager
def _patched_factory(spy: _Spy) -> Iterator[None]:
    """Patch the ADAPTER-module attribute the seam's function-level ``from … import`` resolves each
    call — so no real HTTPServer/socket is constructed for the spy-based cases."""
    orig = HAA.build_authenticate_server
    HAA.build_authenticate_server = spy  # type: ignore[assignment]
    try:
        yield
    finally:
        HAA.build_authenticate_server = orig  # type: ignore[assignment]


# --- authenticator-gate-first -----------------------------------------------------------------------
def test_authenticator_selector_unset_returns_none_and_ignores_bind_env() -> None:
    spy = _Spy(boom=True)  # must never be reached
    # A deliberately INVALID port proves the bind env is NOT consulted when the authenticator is unset
    # (gate-first): if it were parsed, it would raise ValueError; instead the seam returns None.
    with _patched_factory(spy), _env(url=None, issuers="{ garbage not json", host="10.0.0.5", port="not-a-port"):
        assert build_authenticate_server_from_env() is None, "unset authenticator selector must return None"
    assert spy.calls == [], "gate-first: build_authenticate_server must not be called when the authenticator is unset"


def test_malformed_slice1_url_raises_value_error() -> None:
    spy = _Spy(boom=True)
    with _patched_factory(spy), _env(url="https://127.0.0.1:8443", issuers=_VALID_ISSUERS, host=None, port=None):
        try:
            build_authenticate_server_from_env()
        except ValueError:
            pass
        else:
            raise AssertionError("a malformed Slice-1 URL must raise ValueError (inherited from build_authenticator_from_env)")
    assert spy.calls == [], "a malformed Slice-1 URL must fail before build_authenticate_server is reached"


def test_invalid_slice1_issuers_raises_value_error() -> None:
    spy = _Spy(boom=True)
    with _patched_factory(spy), _env(url=_URL, issuers="{not valid json", host=None, port=None):
        try:
            build_authenticate_server_from_env()
        except ValueError:
            pass
        else:
            raise AssertionError("invalid SP2_AR_ISSUERS must raise ValueError before the factory")
    assert spy.calls == [], "invalid Slice-1 issuers must fail before build_authenticate_server is reached"


# --- host/port pass-through -------------------------------------------------------------------------
def test_valid_default_bind_passes_loopback_and_ephemeral() -> None:
    spy = _Spy()
    with _patched_factory(spy), _env(url=_URL, issuers=_VALID_ISSUERS, host=None, port=None):
        result = build_authenticate_server_from_env()
    assert len(spy.calls) == 1, "an active seam must call build_authenticate_server exactly once"
    authenticator, host, port = spy.calls[0]
    assert isinstance(authenticator, Authenticator), "the gate must pass a composed Authenticator to the factory"
    assert host == "127.0.0.1" and port == 0, "defaults must be loopback host + ephemeral port 0"
    assert result is spy.sentinel, "the seam must return build_authenticate_server's result unchanged"


def test_custom_host_and_port_passed_through() -> None:
    spy = _Spy()
    with _patched_factory(spy), _env(url=_URL, issuers=_VALID_ISSUERS, host="127.0.0.9", port="8123"):
        build_authenticate_server_from_env()
    _auth, host, port = spy.calls[0]
    assert host == "127.0.0.9" and port == 8123, "explicit host/port must pass through verbatim"


def test_blank_host_falls_back_to_loopback() -> None:
    spy = _Spy()
    with _patched_factory(spy), _env(url=_URL, issuers=_VALID_ISSUERS, host="   ", port=None):
        build_authenticate_server_from_env()
    assert spy.calls[0][1] == "127.0.0.1", "whitespace host must fall back to the loopback default"


def test_port_boundaries_accepted() -> None:
    for raw, expected in (("0", 0), ("65535", 65535), ("  42 ", 42)):
        spy = _Spy()
        with _patched_factory(spy), _env(url=_URL, issuers=_VALID_ISSUERS, host=None, port=raw):
            build_authenticate_server_from_env()
        assert spy.calls[0][2] == expected, f"in-range port {raw!r} must parse to {expected}"


# --- fail-closed port -------------------------------------------------------------------------------
def test_invalid_port_raises_value_error_before_construct() -> None:
    for bad in ("abc", "-1", "70000", "1.5"):
        spy = _Spy(boom=True)
        with _patched_factory(spy), _env(url=_URL, issuers=_VALID_ISSUERS, host=None, port=bad):
            try:
                build_authenticate_server_from_env()
            except ValueError:
                pass
            else:
                raise AssertionError(f"invalid port {bad!r} must raise ValueError")
        assert spy.calls == [], f"invalid port {bad!r} must fail BEFORE build_authenticate_server (no socket bound)"


# --- inert construction (no control-plane read / no token verify) + no serving ----------------------
def test_construction_performs_no_network_read() -> None:
    # HttpControlPlaneRead._get is the sole control-plane network path; composing the authenticator
    # (inside build_authenticator_from_env) + the server must never call it. Arm _get to raise, compose
    # a valid active seam (factory spied so no real socket), and assert composition never trips the trap.
    sentinel = "authenticate-server-composition-must-not-read-the-control-plane"

    def _boom_get(*args: object, **kwargs: object) -> object:
        raise AssertionError(sentinel)

    orig_get = HttpControlPlaneRead._get
    HttpControlPlaneRead._get = _boom_get  # type: ignore[method-assign]
    spy = _Spy()
    try:
        with _patched_factory(spy), _env(url=_URL, issuers=_VALID_ISSUERS, host=None, port=None):
            build_authenticate_server_from_env()
        assert len(spy.calls) == 1, "the seam must compose + reach build_authenticate_server without any network read"
        # Non-vacuity: the trap is actually armed (a real _get would have been caught).
        tripped = False
        try:
            HttpControlPlaneRead(_URL)._get("/federation?issuer=x")
        except AssertionError as exc:
            tripped = sentinel in str(exc)
        assert tripped, "the network-read trap was not armed (the inert proof would be vacuous)"
    finally:
        HttpControlPlaneRead._get = orig_get  # type: ignore[method-assign]


def test_seam_does_not_serve() -> None:
    served = {"n": 0}

    class _FakeServer:
        def serve_forever(self) -> None:  # pragma: no cover - must never be called
            served["n"] += 1
            raise AssertionError("the seam must not serve requests")

        def server_close(self) -> None:
            return None

    def _returns_fake(authenticator: object, host: str = "127.0.0.1", port: int = 0) -> Tuple[object, str]:
        return _FakeServer(), "http://127.0.0.1:0"

    orig = HAA.build_authenticate_server
    HAA.build_authenticate_server = _returns_fake  # type: ignore[assignment]
    try:
        with _env(url=_URL, issuers=_VALID_ISSUERS, host=None, port=None):
            result = build_authenticate_server_from_env()
        assert result is not None
        server, _base = result
        assert isinstance(server, _FakeServer) and served["n"] == 0, "the seam must return the server WITHOUT serving it"
    finally:
        HAA.build_authenticate_server = orig  # type: ignore[assignment]


# --- real-bind smoke: construct + close an ephemeral loopback server (never serves) -----------------
def test_real_bind_smoke_constructs_and_closes() -> None:
    with _env(url=_URL, issuers=_VALID_ISSUERS, host=None, port=None):
        result = build_authenticate_server_from_env()  # REAL build_authenticate_server -> binds an ephemeral socket
    assert result is not None, "an active seam must return a (server, base_url) tuple"
    server, base_url = result
    try:
        assert base_url.startswith("http://127.0.0.1:"), f"default bind must be internal loopback: {base_url}"
        assert hasattr(server, "server_close") and hasattr(server, "serve_forever"), "must return a real HTTPServer"
    finally:
        server.server_close()  # release the ephemeral socket; the seam never called serve_forever


if __name__ == "__main__":
    _h.run(
        [
            test_authenticator_selector_unset_returns_none_and_ignores_bind_env,
            test_malformed_slice1_url_raises_value_error,
            test_invalid_slice1_issuers_raises_value_error,
            test_valid_default_bind_passes_loopback_and_ephemeral,
            test_custom_host_and_port_passed_through,
            test_blank_host_falls_back_to_loopback,
            test_port_boundaries_accepted,
            test_invalid_port_raises_value_error_before_construct,
            test_construction_performs_no_network_read,
            test_seam_does_not_serve,
            test_real_bind_smoke_constructs_and_closes,
        ]
    )
