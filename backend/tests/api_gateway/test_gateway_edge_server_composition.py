"""Behavioral tests for the served API Gateway Edge composition seam.

Proves ``build_gateway_edge_server_from_env`` (api_gateway/main.py): composition-gate-first (any
unset transport selector — auth / control-read / db-router — returns ``None`` WITHOUT consulting
the bind knobs, so ``build_gateway`` never receives a stub/None); a malformed transport URL raises
``ValueError`` (inherited) before any host/port parse; a valid composition passes the loopback host +
ephemeral port + exact-origin allowlist through to ``build_gateway_edge_server``; a bad
``SP2_GW_EDGE_PORT`` fails closed with ``ValueError`` BEFORE any socket is bound; the seam opens no DB
and never serves. It also proves the blessed blocking entrypoint ``serve_gateway_edge``: inactive
composition → deterministic ``RuntimeError``; active → ``serve_forever`` exactly once THEN
``server_close`` (including on exception / KeyboardInterrupt); the entrypoint spawns no thread.

Selection / pass-through / fail-closed cases monkeypatch ``build_gateway_edge_server`` (a spy) so no
real socket is bound; one real-bind smoke constructs the genuine server on ``port 0`` and immediately
closes it (construct-and-close only — never serves a request). Stdlib-only; no live PostgreSQL, no
network I/O (the transport clients are lazy). Runnable standalone:
  python tests/api_gateway/test_gateway_edge_server_composition.py
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import sys
import threading
from typing import Callable, Iterator, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from api_gateway import main as GEM  # noqa: E402
from api_gateway.adapters.providers import http_gateway_edge as HGE  # noqa: E402
from api_gateway.adapters.providers.http_gateway_edge import serve_gateway_edge  # noqa: E402
from api_gateway.main import (  # noqa: E402
    GW_AUTH_ROUTER_BASE_URL_ENV,
    GW_CONTROL_READ_BASE_URL_ENV,
    GW_DB_ROUTER_BASE_URL_ENV,
    GW_EDGE_ALLOWED_ORIGINS_ENV,
    GW_EDGE_HOST_ENV,
    GW_EDGE_PORT_ENV,
    build_gateway_edge_server_from_env,
)

_TRANSPORTS = (GW_AUTH_ROUTER_BASE_URL_ENV, GW_CONTROL_READ_BASE_URL_ENV, GW_DB_ROUTER_BASE_URL_ENV)
_BIND = (GW_EDGE_HOST_ENV, GW_EDGE_PORT_ENV, GW_EDGE_ALLOWED_ORIGINS_ENV)
_ALL = _TRANSPORTS + _BIND
_VALID = "http://127.0.0.1:1234"  # structurally valid; never connected to (lazy transport clients)


@contextlib.contextmanager
def _env(**values: Optional[str]) -> Iterator[None]:
    """Set the six edge env vars (missing key => unset for the duration); restore all afterward."""
    prior = {k: os.environ.get(k) for k in _ALL}
    try:
        for key in _ALL:
            value = values.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key in _ALL:
            if prior[key] is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior[key]


def _all_transports_valid(**overrides: Optional[str]) -> dict:
    base = {k: _VALID for k in _TRANSPORTS}
    base.update(overrides)
    return base


class _Spy:
    """Records calls to build_gateway_edge_server; returns a sentinel. ``boom=True`` asserts it is
    never invoked (so a case that must fail/return-before-construct is proven non-vacuously)."""

    def __init__(self, boom: bool = False) -> None:
        self.calls: List[Tuple[object, str, int, Tuple[str, ...]]] = []
        self.boom = boom
        self.sentinel: Tuple[object, str] = (object(), "http://sentinel:0")

    def __call__(
        self, gateway: object, *, host: str = "127.0.0.1", port: int = 0, allowed_origins: Tuple[str, ...] = ()
    ) -> Tuple[object, str]:
        self.calls.append((gateway, host, port, allowed_origins))
        if self.boom:
            raise AssertionError("build_gateway_edge_server must NOT be called in this case")
        return self.sentinel


@contextlib.contextmanager
def _patched_edge(spy: _Spy) -> Iterator[None]:
    orig = HGE.build_gateway_edge_server
    HGE.build_gateway_edge_server = spy  # type: ignore[assignment]
    try:
        yield
    finally:
        HGE.build_gateway_edge_server = orig  # type: ignore[assignment]


# --- composition-gate-first -----------------------------------------------------------------------
def test_unset_transport_returns_none_and_ignores_bind_knobs() -> None:
    spy = _Spy(boom=True)  # must never be reached
    # control-read UNSET (auth + router valid) with a deliberately INVALID port proves the bind knobs
    # are NOT consulted when the composition is incomplete (gate-first): if the port were parsed it
    # would raise ValueError; instead the seam returns None.
    env = _all_transports_valid(**{GW_CONTROL_READ_BASE_URL_ENV: None, GW_EDGE_PORT_ENV: "not-a-port"})
    with _patched_edge(spy), _env(**env):
        assert build_gateway_edge_server_from_env() is None, "an incomplete composition must return None"
    assert spy.calls == [], "gate-first: build_gateway_edge_server must not be called on an incomplete composition"


def test_all_transports_unset_returns_none() -> None:
    spy = _Spy(boom=True)
    with _patched_edge(spy), _env():
        assert build_gateway_edge_server_from_env() is None, "all transports unset must return None (serve-inert)"
    assert spy.calls == []


def test_malformed_transport_url_raises_value_error() -> None:
    spy = _Spy(boom=True)
    env = _all_transports_valid(**{GW_AUTH_ROUTER_BASE_URL_ENV: "https://127.0.0.1:8443"})
    with _patched_edge(spy), _env(**env):
        try:
            build_gateway_edge_server_from_env()
        except ValueError:
            pass
        else:
            raise AssertionError("a malformed transport URL must raise ValueError (inherited)")
    assert spy.calls == [], "a malformed transport URL must fail before build_gateway_edge_server is reached"


# --- host / port / origins pass-through -----------------------------------------------------------
def test_valid_composition_defaults_loopback_ephemeral_no_origins() -> None:
    spy = _Spy()
    with _patched_edge(spy), _env(**_all_transports_valid()):
        result = build_gateway_edge_server_from_env()
    assert len(spy.calls) == 1, "an active seam must call build_gateway_edge_server exactly once"
    _gw, host, port, origins = spy.calls[0]
    assert host == "127.0.0.1" and port == 0, "defaults must be loopback host + ephemeral port 0"
    assert origins == (), "an unset allowlist must deny every cross-origin request (empty tuple)"
    assert result is spy.sentinel, "the seam must return build_gateway_edge_server's result unchanged"


def test_custom_host_port_and_origins_passed_through() -> None:
    spy = _Spy()
    env = _all_transports_valid(
        **{GW_EDGE_HOST_ENV: "127.0.0.9", GW_EDGE_PORT_ENV: "8123", GW_EDGE_ALLOWED_ORIGINS_ENV: "https://a.example, https://b.example"}
    )
    with _patched_edge(spy), _env(**env):
        build_gateway_edge_server_from_env()
    _gw, host, port, origins = spy.calls[0]
    assert host == "127.0.0.9" and port == 8123, "explicit host/port must pass through verbatim"
    assert origins == ("https://a.example", "https://b.example"), "the exact-origin allowlist must parse comma-separated (trimmed)"


def test_blank_host_falls_back_to_loopback() -> None:
    spy = _Spy()
    with _patched_edge(spy), _env(**_all_transports_valid(**{GW_EDGE_HOST_ENV: "   "})):
        build_gateway_edge_server_from_env()
    assert spy.calls[0][1] == "127.0.0.1", "whitespace host must fall back to the loopback default"


def test_port_boundaries_accepted() -> None:
    for raw, expected in (("0", 0), ("65535", 65535), ("  42 ", 42)):
        spy = _Spy()
        with _patched_edge(spy), _env(**_all_transports_valid(**{GW_EDGE_PORT_ENV: raw})):
            build_gateway_edge_server_from_env()
        assert spy.calls[0][2] == expected, f"in-range port {raw!r} must parse to {expected}"


# --- fail-closed port -----------------------------------------------------------------------------
def test_invalid_edge_port_raises_value_error_before_construct() -> None:
    for bad in ("abc", "-1", "70000", "1.5"):
        spy = _Spy(boom=True)
        with _patched_edge(spy), _env(**_all_transports_valid(**{GW_EDGE_PORT_ENV: bad})):
            try:
                build_gateway_edge_server_from_env()
            except ValueError:
                pass
            else:
                raise AssertionError(f"invalid port {bad!r} must raise ValueError")
        assert spy.calls == [], f"invalid port {bad!r} must fail BEFORE build_gateway_edge_server (no socket bound)"


# --- inert construction (no serving) --------------------------------------------------------------
def test_seam_does_not_serve() -> None:
    served = {"n": 0}

    class _FakeServer:
        def serve_forever(self) -> None:  # pragma: no cover - must never be called
            served["n"] += 1
            raise AssertionError("the seam must not serve requests")

        def server_close(self) -> None:
            return None

    def _returns_fake(
        gateway: object, *, host: str = "127.0.0.1", port: int = 0, allowed_origins: Tuple[str, ...] = ()
    ) -> Tuple[object, str]:
        return _FakeServer(), "http://127.0.0.1:0"

    orig = HGE.build_gateway_edge_server
    HGE.build_gateway_edge_server = _returns_fake  # type: ignore[assignment]
    try:
        with _env(**_all_transports_valid()):
            result = build_gateway_edge_server_from_env()
        assert result is not None
        server, _base = result
        assert isinstance(server, _FakeServer) and served["n"] == 0, "the seam must return the server WITHOUT serving it"
    finally:
        HGE.build_gateway_edge_server = orig  # type: ignore[assignment]


def test_real_bind_smoke_constructs_and_closes() -> None:
    with _env(**_all_transports_valid()):
        result = build_gateway_edge_server_from_env()  # REAL build_gateway_edge_server -> binds an ephemeral socket
    assert result is not None, "an active seam must return a (server, base_url) tuple"
    server, base_url = result
    try:
        assert base_url.startswith("http://127.0.0.1:"), f"default bind must be internal loopback: {base_url}"
        assert hasattr(server, "server_close") and hasattr(server, "serve_forever"), "must return a real HTTPServer"
    finally:
        server.server_close()  # release the ephemeral socket; the seam never served


# --- serve entrypoint lifecycle (serve_gateway_edge) ----------------------------------------------
class _ServeProbe:
    """A fake server recording lifecycle calls in order; ``serve_effect`` raised from serve_forever."""

    def __init__(self, serve_effect: Optional[BaseException] = None) -> None:
        self.events: List[str] = []
        self._serve_effect = serve_effect

    def serve_forever(self) -> None:
        self.events.append("serve_forever")
        if self._serve_effect is not None:
            raise self._serve_effect

    def server_close(self) -> None:
        self.events.append("server_close")


@contextlib.contextmanager
def _patched_serve_seam(seam: Callable[[], Optional[Tuple[object, str]]]) -> Iterator[List[int]]:
    """Patch the composition-root attribute serve_gateway_edge's call-time import resolves; count it."""
    calls: List[int] = []

    def _counting() -> Optional[Tuple[object, str]]:
        calls.append(1)
        return seam()

    orig = GEM.build_gateway_edge_server_from_env
    GEM.build_gateway_edge_server_from_env = _counting  # type: ignore[assignment]
    try:
        yield calls
    finally:
        GEM.build_gateway_edge_server_from_env = orig  # type: ignore[assignment]


class _ServeBoom(Exception):
    """A distinct serve-time failure (never confused with the inactive RuntimeError)."""


def test_serve_inactive_seam_raises_deterministic_runtimeerror() -> None:
    messages: List[str] = []
    with _patched_serve_seam(lambda: None) as calls:
        for _ in range(2):
            try:
                serve_gateway_edge()
            except RuntimeError as exc:
                messages.append(str(exc))
            else:
                raise AssertionError("inactive composition must raise RuntimeError (fail closed)")
    assert calls == [1, 1], "the entrypoint must call the env seam exactly once per invocation"
    assert len(messages) == 2 and messages[0] == messages[1], "the inactive RuntimeError must be deterministic"


def test_serve_inactive_real_env_raises_runtimeerror() -> None:
    with _env():
        try:
            serve_gateway_edge()
        except RuntimeError:
            pass
        else:
            raise AssertionError("an unset composition must fail closed with RuntimeError")


def test_serve_active_serves_once_then_closes_after_return() -> None:
    probe = _ServeProbe()
    with _patched_serve_seam(lambda: (probe, "http://127.0.0.1:0")) as calls:
        serve_gateway_edge()
    assert calls == [1], "an active entrypoint must call the env seam exactly once"
    assert probe.events == ["serve_forever", "server_close"], f"must serve once THEN close after normal return; got {probe.events}"


def test_serve_exception_propagates_and_still_closes() -> None:
    boom = _ServeBoom("serve loop failed")
    probe = _ServeProbe(serve_effect=boom)
    with _patched_serve_seam(lambda: (probe, "http://127.0.0.1:0")):
        try:
            serve_gateway_edge()
        except _ServeBoom as exc:
            assert exc is boom, "the ORIGINAL serve exception must propagate unswallowed"
        else:
            raise AssertionError("a serve-time exception must propagate (not be swallowed)")
    assert probe.events == ["serve_forever", "server_close"], "server_close must still run when serve_forever raises"


def test_serve_keyboard_interrupt_propagates_and_still_closes() -> None:
    probe = _ServeProbe(serve_effect=KeyboardInterrupt())
    with _patched_serve_seam(lambda: (probe, "http://127.0.0.1:0")):
        try:
            serve_gateway_edge()
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("KeyboardInterrupt must propagate (orderly Ctrl+C shutdown)")
    assert probe.events == ["serve_forever", "server_close"], "server_close must still run on KeyboardInterrupt"


def test_serve_entrypoint_creates_no_thread() -> None:
    boom_calls: List[int] = []

    class _BoomThread:
        def __init__(self, *args: object, **kwargs: object) -> None:
            boom_calls.append(1)
            raise AssertionError("serve_gateway_edge must not create a thread")

    probe = _ServeProbe()
    orig_thread = threading.Thread
    threading.Thread = _BoomThread  # type: ignore[misc, assignment]
    try:
        with _patched_serve_seam(lambda: (probe, "http://127.0.0.1:0")) as calls:
            serve_gateway_edge()
        assert probe.events == ["serve_forever", "server_close"] and calls == [1]
        assert boom_calls == [], "no thread may be constructed by the entrypoint"
    finally:
        threading.Thread = orig_thread  # type: ignore[misc]


if __name__ == "__main__":
    _h.run(
        [
            test_unset_transport_returns_none_and_ignores_bind_knobs,
            test_all_transports_unset_returns_none,
            test_malformed_transport_url_raises_value_error,
            test_valid_composition_defaults_loopback_ephemeral_no_origins,
            test_custom_host_port_and_origins_passed_through,
            test_blank_host_falls_back_to_loopback,
            test_port_boundaries_accepted,
            test_invalid_edge_port_raises_value_error_before_construct,
            test_seam_does_not_serve,
            test_real_bind_smoke_constructs_and_closes,
            test_serve_inactive_seam_raises_deterministic_runtimeerror,
            test_serve_inactive_real_env_raises_runtimeerror,
            test_serve_active_serves_once_then_closes_after_return,
            test_serve_exception_propagates_and_still_closes,
            test_serve_keyboard_interrupt_propagates_and_still_closes,
            test_serve_entrypoint_creates_no_thread,
        ]
    )
