"""Behavioral tests for the Control-Plane routing-audit ingest-server composition seam (DBR-AR-2C).

Proves ``build_routing_audit_server_from_env`` (control_plane/main.py): host-gate-first (an
unset / empty / whitespace-only ``SP2_CP_ROUTING_AUDIT_HOST`` returns ``None`` WITHOUT
consulting the port or the secret reference, constructing the durable store, or reaching the
ingest-server factory); an active host must be one of the three loopback hosts (the ingest
edge is internal-only) and any other value fails closed with ``ValueError`` BEFORE store
construction and socket bind; a bad ``SP2_CP_ROUTING_AUDIT_PORT`` fails closed the same way;
a blank effective ``SP2_CP_CONTROL_STORE_DSN_REF`` fails closed; the composed store is the
reference-only, lazy-connect ``PostgresRoutingAuditStore`` (``secrets=`` + ``ref=``, never a
raw descriptor value — proven by arming the store's sole connect path with a trap); and the
seam is serve-inert. Selection / fail-closed cases monkeypatch the provider modules' factory
attributes (spies) so no real socket is bound; one real-bind smoke constructs the genuine
ingest server on ``port 0`` and immediately closes it (construct-and-close only — never
serves a request, never touches a database). Stdlib-only; DB-free (no live PostgreSQL);
runnable standalone:
  python tests/control_plane/test_dbr_ar_2c_routing_audit_composition.py
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import sys
from typing import Any, Iterator, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from control_plane.adapters.providers import http_routing_audit_api as HRAA  # noqa: E402
from control_plane.adapters.providers import postgres_store as PGS  # noqa: E402
from control_plane.main import (  # noqa: E402
    CONTROL_STORE_DSN_REF_ENV,
    DEFAULT_CONTROL_STORE_DSN_REF,
    SP2_CP_ROUTING_AUDIT_HOST,
    SP2_CP_ROUTING_AUDIT_PORT,
    build_routing_audit_server_from_env,
)

_VARS = (SP2_CP_ROUTING_AUDIT_HOST, SP2_CP_ROUTING_AUDIT_PORT, CONTROL_STORE_DSN_REF_ENV)


@contextlib.contextmanager
def _env(host: Optional[str], port: Optional[str], ref: Optional[str] = None) -> Iterator[None]:
    """Set the seam's env vars for one test (None => unset); restore all afterward."""
    prior = {k: os.environ.get(k) for k in _VARS}
    try:
        for key, value in zip(_VARS, (host, port, ref)):
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


class _ServerSpy:
    """Records calls to build_routing_audit_server; returns a sentinel tuple. ``boom=True``
    asserts it is never invoked (a case that must fail/return BEFORE any socket bind)."""

    def __init__(self, boom: bool = False) -> None:
        self.calls: List[Tuple[Any, str, int]] = []
        self.boom = boom
        self.sentinel: Tuple[object, str] = (object(), "http://sentinel:0")

    def __call__(self, store: object, host: str = "127.0.0.1", port: int = 0) -> Tuple[object, str]:
        self.calls.append((store, host, port))
        if self.boom:
            raise AssertionError("build_routing_audit_server must NOT be called in this case")
        return self.sentinel


@contextlib.contextmanager
def _patched_server_factory(spy: _ServerSpy) -> Iterator[None]:
    """Patch the ADAPTER-module attribute the seam's function-level ``from … import`` resolves
    each call — so no real HTTPServer/socket is constructed for the spy-based cases."""
    orig = HRAA.build_routing_audit_server
    HRAA.build_routing_audit_server = spy  # type: ignore[assignment]
    try:
        yield
    finally:
        HRAA.build_routing_audit_server = orig  # type: ignore[assignment]


@contextlib.contextmanager
def _store_construction_trap(sentinel: str) -> Iterator[List[object]]:
    """Replace PostgresRoutingAuditStore with a booby-trapped stand-in: constructing it
    records the attempt and raises — proving fail-closed cases never reach store
    construction (and, inverted, that active cases construct exactly one store)."""
    attempts: List[object] = []
    orig = PGS.PostgresRoutingAuditStore

    class _Boom:
        def __init__(self, *args: object, **kwargs: object) -> None:
            attempts.append(kwargs)
            raise AssertionError(sentinel)

    PGS.PostgresRoutingAuditStore = _Boom  # type: ignore[assignment, misc]
    try:
        yield attempts
    finally:
        PGS.PostgresRoutingAuditStore = orig  # type: ignore[assignment, misc]


def _expect_value_error(message_probe: Optional[str] = None) -> str:
    try:
        build_routing_audit_server_from_env()
    except ValueError as exc:
        text = str(exc)
        if message_probe is not None:
            assert message_probe in text, f"expected {message_probe!r} in the bounded error, got {text!r}"
        return text
    raise AssertionError("expected ValueError (fail closed — never a silent fallback)")


# --- host-gate-first ---------------------------------------------------------------------------
def test_host_unset_returns_none_and_consults_nothing() -> None:
    spy = _ServerSpy(boom=True)
    # A deliberately INVALID port + blank ref prove neither is consulted while the host
    # selector is inactive (host-gate-first): parsing either would raise; instead → None.
    with _store_construction_trap("inactive-host-must-not-construct-a-store") as attempts:
        with _patched_server_factory(spy), _env(host=None, port="not-a-port", ref="   "):
            assert build_routing_audit_server_from_env() is None, "unset host selector must return None"
    assert spy.calls == [] and attempts == [], "host-gate-first: no store construction, no server factory call"


def test_host_empty_or_whitespace_returns_none() -> None:
    for host in ("", "   ", "\t"):
        spy = _ServerSpy(boom=True)
        with _patched_server_factory(spy), _env(host=host, port="70000"):
            assert build_routing_audit_server_from_env() is None, f"empty/whitespace host {host!r} must behave as unset"
        assert spy.calls == [], "an inactive seam must never reach the server factory"


# --- loopback-only host ------------------------------------------------------------------------
def test_non_loopback_host_fails_before_store_and_socket() -> None:
    for host in ("0.0.0.0", "192.168.1.10", "example.internal", "10.0.0.5"):
        spy = _ServerSpy(boom=True)
        with _store_construction_trap("bad-host-must-not-construct-a-store") as attempts:
            with _patched_server_factory(spy), _env(host=host, port=None):
                message = _expect_value_error(SP2_CP_ROUTING_AUDIT_HOST)
        assert spy.calls == [] and attempts == [], f"host {host!r} must fail BEFORE store construction and socket bind"
        assert host not in message, "the bounded host error must never echo the configured value"


def test_all_three_loopback_hosts_accepted() -> None:
    for host in ("127.0.0.1", "localhost", "::1"):
        spy = _ServerSpy()
        with _patched_server_factory(spy), _env(host=host, port=None):
            result = build_routing_audit_server_from_env()
        assert len(spy.calls) == 1 and spy.calls[0][1] == host, f"loopback host {host!r} must pass through"
        assert result is spy.sentinel, "the seam must return the factory result unchanged"


def test_active_host_is_stripped() -> None:
    spy = _ServerSpy()
    with _patched_server_factory(spy), _env(host="  127.0.0.1  ", port=None):
        build_routing_audit_server_from_env()
    assert spy.calls[0][1] == "127.0.0.1", "the active host must be stripped before validation/pass-through"


# --- fail-closed port --------------------------------------------------------------------------
def test_port_defaults_ephemeral_and_passes_through() -> None:
    for raw, expected in ((None, 0), ("", 0), ("   ", 0), ("0", 0), ("65535", 65535), ("  8125  ", 8125)):
        spy = _ServerSpy()
        with _patched_server_factory(spy), _env(host="127.0.0.1", port=raw):
            build_routing_audit_server_from_env()
        assert spy.calls[0][2] == expected, f"port {raw!r} must resolve to {expected}"


def test_invalid_port_fails_before_store_and_socket() -> None:
    for bad in ("abc", "-1", "65536", "1.5", "0x50"):
        spy = _ServerSpy(boom=True)
        with _store_construction_trap("bad-port-must-not-construct-a-store") as attempts:
            with _patched_server_factory(spy), _env(host="127.0.0.1", port=bad):
                _expect_value_error(SP2_CP_ROUTING_AUDIT_PORT)
        assert spy.calls == [] and attempts == [], f"invalid port {bad!r} must fail BEFORE store construction and socket bind"


# --- reference-only secret composition ----------------------------------------------------------
def test_blank_secret_ref_fails_closed_without_leak() -> None:
    spy = _ServerSpy(boom=True)
    with _store_construction_trap("blank-ref-must-not-construct-a-store") as attempts:
        with _patched_server_factory(spy), _env(host="127.0.0.1", port=None, ref="   "):
            message = _expect_value_error(CONTROL_STORE_DSN_REF_ENV)
    assert spy.calls == [] and attempts == [], "a blank secret reference must fail BEFORE store construction"
    assert "://" not in message and "password" not in message.lower(), "the bounded error must carry no descriptor material"


def test_store_composed_by_reference_only() -> None:
    spy = _ServerSpy()
    with _patched_server_factory(spy), _env(host="127.0.0.1", port=None):
        build_routing_audit_server_from_env()
    store = spy.calls[0][0]
    assert isinstance(store, PGS.PostgresRoutingAuditStore), "the seam must compose the durable 2B store adapter"
    assert store._dsn is None, "the seam must NEVER pass a raw descriptor (reference-only, D-14)"
    assert store._ref is not None and store._ref.store_ref == DEFAULT_CONTROL_STORE_DSN_REF, (
        "the default control-store secret reference must bind the store"
    )
    assert store._secrets is not None, "the widened-allow-list resolver must accompany the reference"


def test_custom_secret_ref_passes_through() -> None:
    spy = _ServerSpy()
    with _patched_server_factory(spy), _env(host="127.0.0.1", port=None, ref="control/alt-routing-audit-ref"):
        build_routing_audit_server_from_env()
    store = spy.calls[0][0]
    assert store._ref.store_ref == "control/alt-routing-audit-ref", "an explicit control-store ref must pass through stripped"


def test_store_construction_is_lazy_no_io() -> None:
    # PostgresRoutingAuditStore._open is the SOLE connect path; arm it with a trap and
    # prove the ACTIVE seam composes without any I/O — then prove the trap is live.
    sentinel = "routing-audit-composition-must-not-connect"

    def _boom_open(self: object) -> object:
        raise AssertionError(sentinel)

    orig_open = PGS.PostgresRoutingAuditStore._open
    PGS.PostgresRoutingAuditStore._open = _boom_open  # type: ignore[method-assign, assignment]
    spy = _ServerSpy()
    try:
        with _patched_server_factory(spy), _env(host="127.0.0.1", port=None):
            result = build_routing_audit_server_from_env()
        assert result is spy.sentinel and len(spy.calls) == 1, "the active seam must compose WITHOUT opening a connection"
        tripped = False
        try:
            spy.calls[0][0]._open()
        except AssertionError as exc:
            tripped = sentinel in str(exc)
        assert tripped, "the connect trap was not armed (the lazy-composition proof would be vacuous)"
    finally:
        PGS.PostgresRoutingAuditStore._open = orig_open  # type: ignore[method-assign, assignment]


# --- serve-inert + real-bind smoke --------------------------------------------------------------
def test_seam_does_not_serve() -> None:
    served = {"n": 0}

    class _FakeServer:
        def serve_forever(self) -> None:  # pragma: no cover - must never be called
            served["n"] += 1
            raise AssertionError("the seam must not serve requests")

        def server_close(self) -> None:
            return None

    def _returns_fake(store: object, host: str = "127.0.0.1", port: int = 0) -> Tuple[object, str]:
        return _FakeServer(), "http://127.0.0.1:0"

    orig = HRAA.build_routing_audit_server
    HRAA.build_routing_audit_server = _returns_fake  # type: ignore[assignment]
    try:
        with _env(host="127.0.0.1", port=None):
            result = build_routing_audit_server_from_env()
        assert result is not None
        server, _base = result
        assert isinstance(server, _FakeServer) and served["n"] == 0, "the seam must return the server WITHOUT serving it"
    finally:
        HRAA.build_routing_audit_server = orig  # type: ignore[assignment]


def test_real_bind_smoke_constructs_and_closes() -> None:
    with _env(host="127.0.0.1", port=None):
        result = build_routing_audit_server_from_env()  # REAL factory -> binds an ephemeral loopback socket
    assert result is not None, "an active seam must return a (server, base_url) tuple"
    server, base_url = result
    try:
        assert base_url.startswith("http://127.0.0.1:"), f"default bind must be internal loopback: {base_url}"
        assert hasattr(server, "server_close") and hasattr(server, "serve_forever"), "must return a real single-threaded server"
    finally:
        server.server_close()  # release the ephemeral socket; the seam never called serve_forever


if __name__ == "__main__":
    _h.run(
        [
            test_host_unset_returns_none_and_consults_nothing,
            test_host_empty_or_whitespace_returns_none,
            test_non_loopback_host_fails_before_store_and_socket,
            test_all_three_loopback_hosts_accepted,
            test_active_host_is_stripped,
            test_port_defaults_ephemeral_and_passes_through,
            test_invalid_port_fails_before_store_and_socket,
            test_blank_secret_ref_fails_closed_without_leak,
            test_store_composed_by_reference_only,
            test_custom_secret_ref_passes_through,
            test_store_construction_is_lazy_no_io,
            test_seam_does_not_serve,
            test_real_bind_smoke_constructs_and_closes,
        ]
    )
