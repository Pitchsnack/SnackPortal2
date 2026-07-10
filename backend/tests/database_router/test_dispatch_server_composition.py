"""Behavioral tests for the Database Router dispatch-server composition seam.

Proves ``build_dispatch_server_from_env`` (database_router/main.py): router-gate-first (an
unset ``SP2_DBR_ROUTING_READ_BASE_URL`` returns ``None`` WITHOUT consulting the dispatch
knobs); a malformed routing URL raises ``ValueError`` (inherited from ``build_router_from_env``);
a valid selector passes the loopback host + ephemeral port (or the configured host/port) through
to ``build_dispatch_server``; a bad ``SP2_DBR_DISPATCH_PORT`` fails closed with ``ValueError``
BEFORE any socket is bound; the seam opens no DB connection and never serves. Selection /
pass-through / fail-closed cases monkeypatch ``build_dispatch_server`` (a spy) so no real socket
is bound; one real-bind smoke constructs the genuine server on ``port 0`` and immediately
``server.server_close()``s it (construct-and-close only — never serves a request). Stdlib-only;
DB-free (no live PostgreSQL; the driver is never imported here); runnable standalone:
  python tests/database_router/test_dispatch_server_composition.py
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Callable, Iterator, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from database_router import main as DRM  # noqa: E402
from database_router.adapters.providers import http_dispatch_api as HDA  # noqa: E402
from database_router.adapters.providers.http_dispatch_api import serve_dispatch_api  # noqa: E402
from database_router.main import (  # noqa: E402
    SP2_DBR_DISPATCH_HOST,
    SP2_DBR_DISPATCH_PORT,
    SP2_DBR_ROUTING_READ_BASE_URL,
    build_dispatch_server_from_env,
)

_VARS = (SP2_DBR_ROUTING_READ_BASE_URL, SP2_DBR_DISPATCH_HOST, SP2_DBR_DISPATCH_PORT)
_VALID_ROUTING = "http://127.0.0.1:1234"  # structurally valid; never connected to


@contextlib.contextmanager
def _env(routing: Optional[str], host: Optional[str], port: Optional[str]) -> Iterator[None]:
    """Set the three router/dispatch env vars for one test (None => unset); restore all afterward."""
    prior = {k: os.environ.get(k) for k in _VARS}
    try:
        for key, value in zip(_VARS, (routing, host, port)):
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
    """Records calls to build_dispatch_server; returns a sentinel tuple. ``boom=True`` asserts it
    is never invoked (so a case that must fail/return-before-construct is proven non-vacuously)."""

    def __init__(self, boom: bool = False) -> None:
        self.calls: List[Tuple[object, str, int]] = []
        self.boom = boom
        self.sentinel: Tuple[object, str] = (object(), "http://sentinel:0")

    def __call__(self, router: object, host: str = "127.0.0.1", port: int = 0) -> Tuple[object, str]:
        self.calls.append((router, host, port))
        if self.boom:
            raise AssertionError("build_dispatch_server must NOT be called in this case")
        return self.sentinel


@contextlib.contextmanager
def _patched_dispatch(spy: _Spy) -> Iterator[None]:
    """Patch the ADAPTER-module attribute the seam's function-level ``from … import`` resolves each
    call — so no real HTTPServer/socket is constructed for the spy-based cases."""
    orig = HDA.build_dispatch_server
    HDA.build_dispatch_server = spy  # type: ignore[assignment]
    try:
        yield
    finally:
        HDA.build_dispatch_server = orig  # type: ignore[assignment]


# --- router-gate-first ------------------------------------------------------------------------------
def test_router_selector_unset_returns_none_and_ignores_dispatch_env() -> None:
    spy = _Spy(boom=True)  # must never be reached
    # A deliberately INVALID port proves the dispatch env is NOT consulted when the router is unset
    # (router-gate-first): if it were parsed, it would raise ValueError; instead the seam returns None.
    with _patched_dispatch(spy), _env(routing=None, host="10.0.0.5", port="not-a-port"):
        assert build_dispatch_server_from_env() is None, "unset router selector must return None"
    assert spy.calls == [], "router-gate-first: build_dispatch_server must not be called when the router is unset"


def test_malformed_router_url_raises_value_error() -> None:
    spy = _Spy(boom=True)
    with _patched_dispatch(spy), _env(routing="https://127.0.0.1:8443", host=None, port=None):
        try:
            build_dispatch_server_from_env()
        except ValueError:
            pass
        else:
            raise AssertionError("a malformed routing URL must raise ValueError (inherited from build_router_from_env)")
    assert spy.calls == [], "a malformed routing URL must fail before build_dispatch_server is reached"


# --- host/port pass-through -------------------------------------------------------------------------
def test_valid_default_dispatch_passes_loopback_and_ephemeral() -> None:
    spy = _Spy()
    with _patched_dispatch(spy), _env(routing=_VALID_ROUTING, host=None, port=None):
        result = build_dispatch_server_from_env()
    assert len(spy.calls) == 1, "an active seam must call build_dispatch_server exactly once"
    _router, host, port = spy.calls[0]
    assert host == "127.0.0.1" and port == 0, "defaults must be loopback host + ephemeral port 0"
    assert result is spy.sentinel, "the seam must return build_dispatch_server's result unchanged"


def test_custom_host_and_port_passed_through() -> None:
    spy = _Spy()
    with _patched_dispatch(spy), _env(routing=_VALID_ROUTING, host="127.0.0.9", port="8123"):
        build_dispatch_server_from_env()
    _router, host, port = spy.calls[0]
    assert host == "127.0.0.9" and port == 8123, "explicit host/port must pass through verbatim"


def test_blank_host_falls_back_to_loopback() -> None:
    spy = _Spy()
    with _patched_dispatch(spy), _env(routing=_VALID_ROUTING, host="   ", port=None):
        build_dispatch_server_from_env()
    assert spy.calls[0][1] == "127.0.0.1", "whitespace host must fall back to the loopback default"


def test_port_boundaries_accepted() -> None:
    for raw, expected in (("0", 0), ("65535", 65535), ("  42 ", 42)):
        spy = _Spy()
        with _patched_dispatch(spy), _env(routing=_VALID_ROUTING, host=None, port=raw):
            build_dispatch_server_from_env()
        assert spy.calls[0][2] == expected, f"in-range port {raw!r} must parse to {expected}"


# --- fail-closed port -------------------------------------------------------------------------------
def test_invalid_port_raises_value_error_before_construct() -> None:
    for bad in ("abc", "-1", "70000", "1.5"):
        spy = _Spy(boom=True)
        with _patched_dispatch(spy), _env(routing=_VALID_ROUTING, host=None, port=bad):
            try:
                build_dispatch_server_from_env()
            except ValueError:
                pass
            else:
                raise AssertionError(f"invalid port {bad!r} must raise ValueError")
        assert spy.calls == [], f"invalid port {bad!r} must fail BEFORE build_dispatch_server (no socket bound)"


# --- inert construction (no DB open) + no serving ---------------------------------------------------
def test_construction_opens_no_db_connection() -> None:
    # Driver-independent: PsycopgConnectionFactory.open is the sole connection-opening path; composing
    # the router (inside build_router_from_env) must never call it. (Do NOT import psycopg directly —
    # the driver-containment guard forbids it; importing the factory CLASS is fine.)
    from database_router.adapters.providers.psycopg_connection import PsycopgConnectionFactory

    sentinel = "dispatch-composition-must-not-open-a-connection"

    def _boom_open(*args: object, **kwargs: object) -> object:
        raise AssertionError(sentinel)

    orig_open = PsycopgConnectionFactory.open
    PsycopgConnectionFactory.open = _boom_open  # type: ignore[method-assign, assignment]
    spy = _Spy()
    try:
        with _patched_dispatch(spy), _env(routing=_VALID_ROUTING, host=None, port=None):
            build_dispatch_server_from_env()
        assert len(spy.calls) == 1, "the seam must compose + reach build_dispatch_server without opening a DB"
        # Non-vacuity: the trap is actually armed (a real open would have been caught).
        try:
            PsycopgConnectionFactory().open("t1", "1", "unused")
        except AssertionError as exc:
            assert sentinel in str(exc), "the open-trap must raise the armed sentinel"
        else:
            raise AssertionError("the open-trap must be armed (non-vacuous)")
    finally:
        PsycopgConnectionFactory.open = orig_open  # type: ignore[method-assign, assignment]


def test_seam_does_not_serve() -> None:
    served = {"n": 0}

    class _FakeServer:
        def serve_forever(self) -> None:  # pragma: no cover - must never be called
            served["n"] += 1
            raise AssertionError("the seam must not serve requests")

        def server_close(self) -> None:
            return None

    def _returns_fake(router: object, host: str = "127.0.0.1", port: int = 0) -> Tuple[object, str]:
        return _FakeServer(), "http://127.0.0.1:0"

    orig = HDA.build_dispatch_server
    HDA.build_dispatch_server = _returns_fake  # type: ignore[assignment]
    try:
        with _env(routing=_VALID_ROUTING, host=None, port=None):
            result = build_dispatch_server_from_env()
        assert result is not None
        server, _base = result
        assert isinstance(server, _FakeServer) and served["n"] == 0, "the seam must return the server WITHOUT serving it"
    finally:
        HDA.build_dispatch_server = orig  # type: ignore[assignment]


# --- real-bind smoke: construct + close an ephemeral loopback server (never serves) -----------------
def test_real_bind_smoke_constructs_and_closes() -> None:
    with _env(routing=_VALID_ROUTING, host=None, port=None):
        result = build_dispatch_server_from_env()  # REAL build_dispatch_server -> binds an ephemeral socket
    assert result is not None, "an active seam must return a (server, base_url) tuple"
    server, base_url = result
    try:
        assert base_url.startswith("http://127.0.0.1:"), f"default bind must be internal loopback: {base_url}"
        assert hasattr(server, "server_close") and hasattr(server, "serve_forever"), "must return a real HTTPServer"
    finally:
        server.server_close()  # release the ephemeral socket; the seam never called serve_forever


# --- B5-2 serve-lifecycle entrypoint (serve_dispatch_api) -------------------------------------------
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
    """Patch the COMPOSITION-ROOT attribute (database_router.main.build_dispatch_server_from_env)
    that serve_dispatch_api's call-time function-local import resolves; count invocations."""
    calls: List[int] = []

    def _counting() -> Optional[Tuple[object, str]]:
        calls.append(1)
        return seam()

    orig = DRM.build_dispatch_server_from_env
    DRM.build_dispatch_server_from_env = _counting  # type: ignore[assignment]
    try:
        yield calls
    finally:
        DRM.build_dispatch_server_from_env = orig  # type: ignore[assignment]


class _ServeBoom(Exception):
    """A distinct serve-time failure (never confused with the inactive RuntimeError)."""


def test_serve_inactive_seam_raises_deterministic_runtimeerror() -> None:
    # Inactive composition -> deterministic RuntimeError; the seam is consulted exactly once per
    # invocation; and nothing serves (a global HTTPServer.serve_forever trap is armed throughout).
    def _no_serve(self: object, poll_interval: float = 0.5) -> None:
        raise AssertionError("nothing may serve when the composition is inactive")

    orig_serve = HDA.HTTPServer.serve_forever
    HDA.HTTPServer.serve_forever = _no_serve  # type: ignore[method-assign, assignment]
    messages: List[str] = []
    try:
        with _patched_serve_seam(lambda: None) as calls:
            for _ in range(2):
                try:
                    serve_dispatch_api()
                except RuntimeError as exc:
                    messages.append(str(exc))
                else:
                    raise AssertionError("inactive composition must raise RuntimeError (fail closed)")
        assert calls == [1, 1], "the entrypoint must call the env seam exactly once per invocation"
    finally:
        HDA.HTTPServer.serve_forever = orig_serve  # type: ignore[method-assign]
    assert len(messages) == 2 and messages[0] == messages[1], "the inactive RuntimeError must be deterministic"
    assert SP2_DBR_ROUTING_READ_BASE_URL in messages[0], "the error must name the inactive selector"


def test_serve_inactive_real_env_raises_runtimeerror() -> None:
    # End-to-end with the REAL seam: selector unset -> the entrypoint fails closed (RuntimeError).
    with _env(routing=None, host=None, port=None):
        try:
            serve_dispatch_api()
        except RuntimeError as exc:
            assert SP2_DBR_ROUTING_READ_BASE_URL in str(exc), "the fail-closed error must name the selector"
        else:
            raise AssertionError("an unset selector must fail closed with RuntimeError")


def test_serve_active_serves_once_then_closes_after_return() -> None:
    probe = _ServeProbe()  # serve_forever returns normally (post-shutdown semantics)
    with _patched_serve_seam(lambda: (probe, "http://127.0.0.1:0")) as calls:
        serve_dispatch_api()
    assert calls == [1], "an active entrypoint must call the env seam exactly once"
    assert probe.events == ["serve_forever", "server_close"], f"must serve exactly once THEN close after normal return; got {probe.events}"


def test_serve_exception_propagates_and_still_closes() -> None:
    boom = _ServeBoom("serve loop failed")
    probe = _ServeProbe(serve_effect=boom)
    with _patched_serve_seam(lambda: (probe, "http://127.0.0.1:0")):
        try:
            serve_dispatch_api()
        except _ServeBoom as exc:
            assert exc is boom, "the ORIGINAL serve exception must propagate unswallowed"
        else:
            raise AssertionError("a serve-time exception must propagate (not be swallowed)")
    assert probe.events == ["serve_forever", "server_close"], "server_close must still run when serve_forever raises"


def test_serve_keyboard_interrupt_propagates_and_still_closes() -> None:
    probe = _ServeProbe(serve_effect=KeyboardInterrupt())
    with _patched_serve_seam(lambda: (probe, "http://127.0.0.1:0")):
        try:
            serve_dispatch_api()
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("KeyboardInterrupt must propagate (orderly Ctrl+C shutdown)")
    assert probe.events == ["serve_forever", "server_close"], "server_close must still run on KeyboardInterrupt"


def test_serve_entrypoint_creates_no_thread() -> None:
    # The entrypoint serves on the CALLING thread: constructing ANY thread during its run is trapped.
    boom_calls: List[int] = []

    class _BoomThread:
        def __init__(self, *args: object, **kwargs: object) -> None:
            boom_calls.append(1)
            raise AssertionError("serve_dispatch_api must not create a thread")

    probe = _ServeProbe()
    orig_thread = threading.Thread
    threading.Thread = _BoomThread  # type: ignore[misc, assignment]
    try:
        with _patched_serve_seam(lambda: (probe, "http://127.0.0.1:0")) as calls:
            serve_dispatch_api()
        assert probe.events == ["serve_forever", "server_close"] and calls == [1]
        assert boom_calls == [], "no thread may be constructed by the entrypoint"
        # Non-vacuity: the trap is actually armed.
        tripped = False
        try:
            threading.Thread(target=lambda: None)
        except AssertionError:
            tripped = True
        assert tripped, "the thread trap was not armed (the no-thread proof would be vacuous)"
    finally:
        threading.Thread = orig_thread  # type: ignore[misc]


def test_serve_real_server_hosted_served_shutdown_joined_closed() -> None:
    # Serve-then-shutdown lifecycle over the REAL server (test-only daemon thread; bounded waits):
    # compose the genuine (server, base_url) via the REAL seam, pin the seam to return exactly that
    # tuple, host the BLOCKING entrypoint in a daemon thread, observe SERVING via an actual HTTP
    # response (GET -> 405 empty: the request was PROCESSED by the serve loop — a bare TCP connect
    # would be vacuous, the socket listens from construction), then shutdown -> serve_forever
    # returns -> the entrypoint's finally closes the socket -> bounded join -> no live thread.
    # DB-free: a GET never reaches router.route(), so no connection factory or driver is touched.
    with _env(routing=_VALID_ROUTING, host=None, port=None):
        composed = build_dispatch_server_from_env()  # REAL seam: binds an ephemeral loopback port
    assert composed is not None
    server, base_url = composed
    thread = threading.Thread(target=serve_dispatch_api, daemon=True)  # test-only hosting thread
    served = False
    try:
        with _patched_serve_seam(lambda: composed) as calls:
            thread.start()
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                try:
                    urllib.request.urlopen(base_url + "/internal/dispatch/route", timeout=2.0)
                except urllib.error.HTTPError as exc:
                    served = exc.code == 405  # GET refused by the running serve loop (request processed)
                    exc.close()
                    break
                except (urllib.error.URLError, OSError):
                    time.sleep(0.05)
            assert served, "the hosted entrypoint must process a request (405 refusal) before the deadline"
            assert calls == [1], "the hosted entrypoint must call the env seam exactly once"
    finally:
        try:
            if thread.is_alive():
                server.shutdown()  # serve_forever returns; the entrypoint's finally closes the socket
                thread.join(timeout=10.0)
        finally:
            server.server_close()  # idempotent second close (safety net if the thread never served)
    assert not thread.is_alive(), "the serve thread must terminate after shutdown (bounded join; no leak)"


if __name__ == "__main__":
    _h.run(
        [
            test_router_selector_unset_returns_none_and_ignores_dispatch_env,
            test_malformed_router_url_raises_value_error,
            test_valid_default_dispatch_passes_loopback_and_ephemeral,
            test_custom_host_and_port_passed_through,
            test_blank_host_falls_back_to_loopback,
            test_port_boundaries_accepted,
            test_invalid_port_raises_value_error_before_construct,
            test_construction_opens_no_db_connection,
            test_seam_does_not_serve,
            test_real_bind_smoke_constructs_and_closes,
            test_serve_inactive_seam_raises_deterministic_runtimeerror,
            test_serve_inactive_real_env_raises_runtimeerror,
            test_serve_active_serves_once_then_closes_after_return,
            test_serve_exception_propagates_and_still_closes,
            test_serve_keyboard_interrupt_propagates_and_still_closes,
            test_serve_entrypoint_creates_no_thread,
            test_serve_real_server_hosted_served_shutdown_joined_closed,
        ]
    )
