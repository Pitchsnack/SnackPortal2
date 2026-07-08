"""Behavioral tests for the Database Router config-selectable composition seam.

Proves ``build_router_from_env`` (database_router/main.py): unset/empty/whitespace env
keeps the caller's injected composition (returns ``None``), a structurally valid internal
``http`` base URL composes a production ``DatabaseRouter`` wired to the ``HttpRoutingRead``
routing-read client bound to exactly that URL (plus the env tenant SecretStore + the
psycopg connection factory), and any malformed/off-scheme/missing-netloc value fails closed
with ``ValueError`` — never a silent fallback (the gateway SP2_GW_* / control_plane SP2_CP_*
selector posture). The construction is INERT: it opens no connection — proven non-vacuously by
arming the sole connection-opening path (``PsycopgConnectionFactory.open``) with a trap the test
would trip on. ``build_router`` direct-injection behavior stays unchanged. Stdlib-only; DB-free
(no live PostgreSQL; the driver is never imported here);
runnable standalone:  python tests/database_router/test_router_composition.py
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import sys
from typing import Callable, Iterator, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _db_doubles as D  # noqa: E402
import _h  # noqa: E402

from database_router.adapters.providers.http_routing_read import HttpRoutingRead  # noqa: E402
from database_router.main import SP2_DBR_ROUTING_READ_BASE_URL, build_router, build_router_from_env  # noqa: E402
from database_router.router import DatabaseRouter  # noqa: E402


@contextlib.contextmanager
def _env(value: Optional[str]) -> Iterator[None]:
    """Set/unset SP2_DBR_ROUTING_READ_BASE_URL for one test and always restore the prior value."""
    prior = os.environ.get(SP2_DBR_ROUTING_READ_BASE_URL)
    try:
        if value is None:
            os.environ.pop(SP2_DBR_ROUTING_READ_BASE_URL, None)
        else:
            os.environ[SP2_DBR_ROUTING_READ_BASE_URL] = value
        yield
    finally:
        if prior is None:
            os.environ.pop(SP2_DBR_ROUTING_READ_BASE_URL, None)
        else:
            os.environ[SP2_DBR_ROUTING_READ_BASE_URL] = prior


def _expect_value_error(value: str) -> None:
    with _env(value):
        try:
            build_router_from_env()
        except ValueError:
            return
        raise AssertionError(f"{value!r} must fail closed with ValueError (never a silent fallback)")


def _assert_trap_armed(thunk: Callable[[], object], sentinel: str) -> None:
    """The inert proof is non-vacuous only if the connect/open trap is actually live: calling
    it directly must raise the armed sentinel (a real composition-time open would be caught)."""
    try:
        thunk()
    except AssertionError as exc:
        assert sentinel in str(exc), "the inert-construction trap must raise the armed sentinel"
        return
    raise AssertionError("the inert-construction trap was not armed (the inert proof would be vacuous)")


# --- selection behavior -----------------------------------------------------------------------------
def test_env_unset_returns_none() -> None:
    with _env(None):
        assert build_router_from_env() is None, "unset env must preserve the caller's injected composition"


def test_env_empty_or_whitespace_returns_none() -> None:
    for value in ("", "   ", "\t"):
        with _env(value):
            assert build_router_from_env() is None, f"empty/whitespace {value!r} must behave as unset"


def test_valid_http_url_returns_database_router() -> None:
    with _env("http://127.0.0.1:1234"):
        router = build_router_from_env()
    assert isinstance(router, DatabaseRouter), "a valid internal http URL must compose a DatabaseRouter"


def test_valid_http_url_composes_expected_adapters() -> None:
    with _env("http://127.0.0.1:1234"):
        router = build_router_from_env()
    assert isinstance(router, DatabaseRouter)
    # White-box: the seam must wire the HTTP routing-read client bound to exactly the configured URL.
    read = router._resolver._read
    assert isinstance(read, HttpRoutingRead), "a valid internal http URL must select the HttpRoutingRead client"
    assert read._base == "http://127.0.0.1:1234", "the client must be bound to exactly the configured base URL"
    # It composes the existing production tenant-credential + connection adapters (by type name, so
    # the test module stays driver-independent — importing the psycopg factory class is not needed).
    assert type(router._secrets).__name__ == "EnvTenantSecretStore", "must compose the env tenant SecretStore"
    assert type(router._factory).__name__ == "PsycopgConnectionFactory", "must compose the psycopg connection factory"


# --- fail-closed configuration boundary --------------------------------------------------------------
def test_malformed_url_raises_value_error() -> None:
    for value in ("not a url", "127.0.0.1:1234", "ftp://127.0.0.1:1234", "http//missing-colon"):
        _expect_value_error(value)


def test_https_scheme_raises_value_error() -> None:
    # The seam pins scheme http: this is the INTERNAL loopback transport (TLS termination is
    # deployment scope). A configured https value must fail closed, not silently degrade.
    _expect_value_error("https://127.0.0.1:8443")


def test_missing_netloc_raises_value_error() -> None:
    for value in ("http://", "http:///internal/routing/tenants/t1", "http:relative"):
        _expect_value_error(value)


# --- inert construction: no connection opened --------------------------------------------------------
def test_construction_is_inert_no_connect() -> None:
    # Driver-independent inert proof (the driver-containment standard forbids importing psycopg outside
    # the provider zones — importing the factory CLASS is fine; its module name is not a driver prefix).
    # PsycopgConnectionFactory.open is the SOLE connection-opening path; the seam constructs the factory
    # but must never call .open() during composition. Arm .open to raise, compose a valid-but-dead URL,
    # and assert composition succeeds without ever tripping the trap.
    from database_router.adapters.providers.psycopg_connection import PsycopgConnectionFactory

    sentinel = "composition-must-not-open-a-connection"

    def _boom_open(*args: object, **kwargs: object) -> object:
        raise AssertionError(sentinel)

    orig_open = PsycopgConnectionFactory.open
    PsycopgConnectionFactory.open = _boom_open
    try:
        with _env("http://127.0.0.1:1234"):
            router = build_router_from_env()  # must compose WITHOUT opening a connection
        assert isinstance(router, DatabaseRouter), "inert composition must still return a DatabaseRouter"
        # Non-vacuity: the trap is actually armed, so a composition-time open WOULD have been caught.
        _assert_trap_armed(lambda: PsycopgConnectionFactory().open("t1", "1", "unused-descriptor"), sentinel)
    finally:
        PsycopgConnectionFactory.open = orig_open


# --- direct injection path unchanged -----------------------------------------------------------------
def test_direct_injection_build_router_unchanged() -> None:
    # The additive seam must not disturb build_router's keyword-only injection path.
    router = build_router(
        read=D.FakeRoutingRead(),
        secret_store=D.FakeSecretStore(),
        connection_factory=D.FakeConnectionFactory(),
    )
    assert isinstance(router, DatabaseRouter), "build_router direct injection must still compose a DatabaseRouter"


if __name__ == "__main__":
    _h.run(
        [
            test_env_unset_returns_none,
            test_env_empty_or_whitespace_returns_none,
            test_valid_http_url_returns_database_router,
            test_valid_http_url_composes_expected_adapters,
            test_malformed_url_raises_value_error,
            test_https_scheme_raises_value_error,
            test_missing_netloc_raises_value_error,
            test_construction_is_inert_no_connect,
            test_direct_injection_build_router_unchanged,
        ]
    )
