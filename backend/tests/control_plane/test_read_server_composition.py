"""Behavioral tests for the Control-Plane read-edge server composition seam (B5-1).

Proves ``build_read_server_from_env`` (control_plane/main.py): host-gate-first (an unset / empty /
whitespace-only ``SP2_CP_READ_HOST`` returns ``None`` WITHOUT consulting the port, composing
``create_app()``, or importing/calling ``make_server``); an active host composes the production app
(``create_app()``) and passes it plus the bind host + port through to the existing ``make_server``
adapter; a bad ``SP2_CP_READ_PORT`` fails closed with ``ValueError`` BEFORE any socket is bound; the
seam opens no store/DB connection and never serves. Selection / pass-through / fail-closed cases
monkeypatch the read adapter's ``make_server`` (a spy) so no real socket is bound; one real-bind
smoke constructs the genuine server on ``port 0`` and immediately ``server.server_close()``s it
(construct-and-close only — never serves a request). Stdlib-only; DB-free (no live PostgreSQL; the
default in-memory app performs no I/O at construction); runnable standalone:
  python tests/control_plane/test_read_server_composition.py

Divergence from the router server seams (mirrored deliberately): the read-edge host itself is the
activation selector (there is no upstream client-URL selector on this server side), so a blank host
DEACTIVATES the seam (returns ``None``) rather than falling back to a default — and an active host is
used verbatim (stripped) as the bind host.
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import sys
from typing import Iterator, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from control_plane import main as cp_main  # noqa: E402
from control_plane.adapters.providers import http_read_api as HRA  # noqa: E402
from control_plane.main import (  # noqa: E402
    SP2_CP_READ_HOST,
    SP2_CP_READ_PORT,
    ControlPlane,
    build_read_server_from_env,
)

_VARS = (SP2_CP_READ_HOST, SP2_CP_READ_PORT)


@contextlib.contextmanager
def _env(host: Optional[str], port: Optional[str]) -> Iterator[None]:
    """Set the two read-edge env vars for one test (None => unset); restore both afterward."""
    prior = {k: os.environ.get(k) for k in _VARS}
    try:
        for key, value in zip(_VARS, (host, port), strict=False):
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
    """Records calls to make_server; returns a sentinel tuple. ``boom=True`` asserts it is never
    invoked (so a case that must fail/return-before-construct is proven non-vacuously)."""

    def __init__(self, boom: bool = False) -> None:
        self.calls: List[Tuple[object, str, int]] = []
        self.boom = boom
        self.sentinel: Tuple[object, str] = (object(), "http://sentinel:0")

    def __call__(self, control_plane: object, host: str = "127.0.0.1", port: int = 0) -> Tuple[object, str]:
        self.calls.append((control_plane, host, port))
        if self.boom:
            raise AssertionError("make_server must NOT be called in this case")
        return self.sentinel


@contextlib.contextmanager
def _patched_make_server(spy: _Spy) -> Iterator[None]:
    """Patch the ADAPTER-module attribute the seam's function-level ``from … import`` resolves each
    call — so no real HTTPServer/socket is constructed for the spy-based cases."""
    orig = HRA.make_server
    HRA.make_server = spy  # type: ignore[assignment]
    try:
        yield
    finally:
        HRA.make_server = orig  # type: ignore[assignment]


# --- host-gate-first --------------------------------------------------------------------------------
def test_host_unset_returns_none_and_ignores_port() -> None:
    spy = _Spy(boom=True)  # must never be reached
    # A deliberately INVALID port proves the port env is NOT consulted when the host is unset
    # (host-gate-first): if it were parsed, it would raise ValueError; instead the seam returns None.
    with _patched_make_server(spy), _env(host=None, port="not-a-port"):
        assert build_read_server_from_env() is None, "unset host selector must return None"
    assert spy.calls == [], "host-gate-first: make_server must not be called when the host is unset"


def test_host_empty_returns_none() -> None:
    spy = _Spy(boom=True)
    with _patched_make_server(spy), _env(host="", port="70000"):
        assert build_read_server_from_env() is None, "empty host selector must return None"
    assert spy.calls == [], "empty host must not reach make_server (and must not parse the port)"


def test_host_whitespace_returns_none() -> None:
    spy = _Spy(boom=True)
    with _patched_make_server(spy), _env(host="   ", port="-1"):
        assert build_read_server_from_env() is None, "whitespace-only host selector must return None"
    assert spy.calls == [], "whitespace host must not reach make_server (and must not parse the port)"


def test_inactive_host_composes_no_app_and_no_make_server() -> None:
    # §6.5: an inactive host must not call create_app() OR make_server. Arm BOTH to raise; a
    # deliberately invalid port additionally proves the port is never parsed. The seam returns None.
    spy = _Spy(boom=True)
    sentinel = "inactive-host-must-not-compose-the-app"

    def _boom_create_app() -> object:
        raise AssertionError(sentinel)

    orig_create_app = cp_main.create_app
    cp_main.create_app = _boom_create_app  # type: ignore[assignment]
    try:
        with _patched_make_server(spy), _env(host=None, port="not-a-port"):
            assert build_read_server_from_env() is None, "inactive host must return None"
        assert spy.calls == [], "inactive host must not reach make_server"
        # Non-vacuity: the create_app trap is actually armed (a real call would have been caught).
        tripped = False
        try:
            cp_main.create_app()
        except AssertionError as exc:
            tripped = sentinel in str(exc)
        assert tripped, "the create_app trap was not armed (the 'no compose' proof would be vacuous)"
    finally:
        cp_main.create_app = orig_create_app  # type: ignore[assignment]


# --- host/port pass-through -------------------------------------------------------------------------
def test_active_default_port_passes_host_and_ephemeral() -> None:
    spy = _Spy()
    with _patched_make_server(spy), _env(host="127.0.0.1", port=None):
        result = build_read_server_from_env()
    assert len(spy.calls) == 1, "an active seam must call make_server exactly once"
    control_plane, host, port = spy.calls[0]
    assert isinstance(control_plane, ControlPlane), "the seam must compose create_app() (a ControlPlane) and pass it through"
    assert host == "127.0.0.1" and port == 0, "an absent port must default to ephemeral 0; the host passes through"
    assert result is spy.sentinel, "the seam must return make_server's result unchanged"


def test_active_host_is_stripped() -> None:
    spy = _Spy()
    with _patched_make_server(spy), _env(host="  127.0.0.9  ", port=None):
        build_read_server_from_env()
    assert spy.calls[0][1] == "127.0.0.9", "the active host must be stripped before pass-through"


def test_explicit_port_passed_through() -> None:
    spy = _Spy()
    with _patched_make_server(spy), _env(host="127.0.0.1", port="8123"):
        build_read_server_from_env()
    assert spy.calls[0][2] == 8123, "an explicit port must pass through verbatim"


def test_port_boundaries_and_trim_accepted() -> None:
    for raw, expected in (("0", 0), ("65535", 65535), ("  42  ", 42)):
        spy = _Spy()
        with _patched_make_server(spy), _env(host="127.0.0.1", port=raw):
            build_read_server_from_env()
        assert spy.calls[0][2] == expected, f"in-range/trimmed port {raw!r} must parse to {expected}"


# --- fail-closed port -------------------------------------------------------------------------------
def test_invalid_port_raises_value_error_before_construct() -> None:
    for bad in ("abc", "-1", "70000", "1.5"):
        spy = _Spy(boom=True)
        with _patched_make_server(spy), _env(host="127.0.0.1", port=bad):
            try:
                build_read_server_from_env()
            except ValueError:
                pass
            else:
                raise AssertionError(f"invalid port {bad!r} must raise ValueError")
        assert spy.calls == [], f"invalid port {bad!r} must fail BEFORE make_server (no app composed, no socket bound)"


# --- factory result returned unchanged --------------------------------------------------------------
def test_factory_result_returned_unchanged() -> None:
    spy = _Spy()
    with _patched_make_server(spy), _env(host="127.0.0.1", port=None):
        result = build_read_server_from_env()
    assert result is spy.sentinel, "the seam must return exactly what make_server returns (no wrapping)"


# --- inert construction (no serving, no store/DB connection) ----------------------------------------
def test_seam_does_not_serve() -> None:
    served = {"n": 0}

    class _FakeServer:
        def serve_forever(self) -> None:  # pragma: no cover - must never be called
            served["n"] += 1
            raise AssertionError("the seam must not serve requests")

        def server_close(self) -> None:
            return None

    def _returns_fake(control_plane: object, host: str = "127.0.0.1", port: int = 0) -> Tuple[object, str]:
        return _FakeServer(), "http://127.0.0.1:0"

    orig = HRA.make_server
    HRA.make_server = _returns_fake  # type: ignore[assignment]
    try:
        with _env(host="127.0.0.1", port=None):
            result = build_read_server_from_env()
        assert result is not None
        server, _base = result
        assert isinstance(server, _FakeServer) and served["n"] == 0, "the seam must return the server WITHOUT serving it"
    finally:
        HRA.make_server = orig  # type: ignore[assignment]


def test_construction_opens_no_store_connection() -> None:
    # §6.14: control_store_unit_of_work() is the read edge's per-request store/connect path (do_GET
    # acquires a fresh unit of work through it). Composing the seam must never touch it. Arm it to
    # raise, compose a valid active seam (make_server spied so no real socket), and assert the
    # composition never trips it — then separately prove the trap is live.
    sentinel = "read-server-composition-must-not-acquire-a-store-uow"

    def _boom_uow(self: object) -> object:
        raise AssertionError(sentinel)

    orig_uow = ControlPlane.control_store_unit_of_work
    ControlPlane.control_store_unit_of_work = _boom_uow  # type: ignore[method-assign, assignment]
    spy = _Spy()
    try:
        with _patched_make_server(spy), _env(host="127.0.0.1", port=None):
            build_read_server_from_env()
        assert len(spy.calls) == 1, "the seam must compose + reach make_server without acquiring a store unit of work"
        # Non-vacuity: the trap is actually armed (a real acquisition would have been caught).
        tripped = False
        try:
            cp_main.create_app().control_store_unit_of_work()
        except AssertionError as exc:
            tripped = sentinel in str(exc)
        assert tripped, "the store-UoW trap was not armed (the inert proof would be vacuous)"
    finally:
        ControlPlane.control_store_unit_of_work = orig_uow  # type: ignore[method-assign, assignment]


# --- real-bind smoke: construct + close an ephemeral loopback server (never serves) -----------------
def test_real_bind_smoke_constructs_and_closes() -> None:
    with _env(host="127.0.0.1", port=None):
        result = build_read_server_from_env()  # REAL make_server -> binds an ephemeral socket
    assert result is not None, "an active seam must return a (server, base_url) tuple"
    server, base_url = result
    try:
        assert base_url.startswith("http://127.0.0.1:"), f"default bind must be internal loopback: {base_url}"
        assert hasattr(server, "server_close") and hasattr(server, "serve_forever"), "must return a real bound edge server"
    finally:
        server.server_close()  # release the ephemeral socket; the seam never called serve_forever


# --- create_app() unchanged -------------------------------------------------------------------------
def test_create_app_behavior_unchanged() -> None:
    # §6.16: the existing production factory still returns a ControlPlane and is unchanged by B5-1.
    app = cp_main.create_app()
    assert isinstance(app, ControlPlane), "create_app() must still return a ControlPlane (behavior unchanged)"


if __name__ == "__main__":
    _h.run(
        [
            test_host_unset_returns_none_and_ignores_port,
            test_host_empty_returns_none,
            test_host_whitespace_returns_none,
            test_inactive_host_composes_no_app_and_no_make_server,
            test_active_default_port_passes_host_and_ephemeral,
            test_active_host_is_stripped,
            test_explicit_port_passed_through,
            test_port_boundaries_and_trim_accepted,
            test_invalid_port_raises_value_error_before_construct,
            test_factory_result_returned_unchanged,
            test_seam_does_not_serve,
            test_construction_opens_no_store_connection,
            test_real_bind_smoke_constructs_and_closes,
            test_create_app_behavior_unchanged,
        ]
    )
