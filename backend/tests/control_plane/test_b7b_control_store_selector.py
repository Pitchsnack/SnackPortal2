"""PRD 06 B-7B — Control-Store selector (SP2_CP_CONTROL_STORE) unit/contract guard.

The default Control-Store is in-memory and construction performs NO I/O; `postgres` selects
the durable PostgreSQL ControlStore via a SecretRef with lazy-connect (still NO I/O at
construction — the operational audit sink is one consumer of this store, not a separate
sink); any other value fails closed (ValueError). The composition root holds NO DSN literal
(the durable store is built from a secret reference only) and preserves the default
trust-anchor-only secret store for Bootstrap. Pure stdlib; pytest- or standalone-run:
  python tests/control_plane/test_b7b_control_store_selector.py
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import sys
from typing import Dict, Iterator, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.adapters.providers.postgres_store import PostgresControlStore  # noqa: E402
from control_plane.main import (  # noqa: E402
    CONTROL_STORE_DSN_REF_ENV,
    CONTROL_STORE_ENV,
    DEFAULT_CONTROL_STORE_DSN_REF,
    ControlPlane,
    create_app,
)
from shared.adapters.providers.env_reference_secret_store import DEFAULT_ALLOWED  # noqa: E402


@contextlib.contextmanager
def _env(values: Dict[str, Optional[str]]) -> Iterator[None]:
    """Temporarily set/clear env vars; restore exactly on exit (even on failure)."""
    saved = {k: os.environ.get(k) for k in values}
    try:
        for k, v in values.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


def test_default_is_in_memory() -> None:
    with _env({CONTROL_STORE_ENV: None}):
        assert isinstance(ControlPlane().store, InMemoryControlStore)


def test_explicit_in_memory_value_case_and_space_insensitive() -> None:
    with _env({CONTROL_STORE_ENV: "in_memory"}):
        assert isinstance(ControlPlane().store, InMemoryControlStore)
    with _env({CONTROL_STORE_ENV: "  IN_MEMORY  "}):
        assert isinstance(ControlPlane().store, InMemoryControlStore)


def test_postgres_value_builds_lazy_durable_store_no_io() -> None:
    with _env({CONTROL_STORE_ENV: "postgres", CONTROL_STORE_DSN_REF_ENV: None}):
        cp = ControlPlane()
        assert isinstance(cp.store, PostgresControlStore)
        # lazy-connect: NO connection opened at construction (no PostgreSQL I/O)
        assert cp.store._conn_cache is None
        # composition root holds NO DSN literal — the durable store is built from a ref only
        assert cp.store._dsn is None
        assert cp.store._ref is not None
        assert cp.store._ref.store_ref == DEFAULT_CONTROL_STORE_DSN_REF
        assert cp.store._ref.version == "1"


def test_custom_dsn_ref_env_is_honored() -> None:
    with _env({CONTROL_STORE_ENV: "postgres", CONTROL_STORE_DSN_REF_ENV: "control/custom-ref"}):
        cp = ControlPlane()
        assert isinstance(cp.store, PostgresControlStore)
        assert cp.store._ref is not None and cp.store._ref.store_ref == "control/custom-ref"


def test_invalid_selector_fails_closed() -> None:
    with _env({CONTROL_STORE_ENV: "mysql"}):
        try:
            ControlPlane()
            assert False, "an unsupported SP2_CP_CONTROL_STORE value must raise (fail closed)"
        except ValueError:
            pass


def test_explicit_store_overrides_env_and_builds_no_durable_store() -> None:
    sentinel = InMemoryControlStore()
    with _env({CONTROL_STORE_ENV: "postgres"}):
        cp = ControlPlane(store=sentinel)
        assert cp.store is sentinel  # an explicit store always wins; no durable store is built


def test_create_app_default_is_in_memory() -> None:
    with _env({CONTROL_STORE_ENV: None}):
        assert isinstance(create_app().store, InMemoryControlStore)


def test_create_app_postgres_mode_constructs_without_io_and_preserves_bootstrap_secret_store() -> None:
    with _env({CONTROL_STORE_ENV: "postgres", CONTROL_STORE_DSN_REF_ENV: None}):
        cp = create_app()  # must NOT connect (lazy); construction does no PostgreSQL I/O
        assert isinstance(cp.store, PostgresControlStore)
        assert cp.store._conn_cache is None
        # the default trust-anchor-only secret store is preserved for Bootstrap (NOT widened)
        assert cp.secret_store._allowed == DEFAULT_ALLOWED


if __name__ == "__main__":
    _h.run(
        [
            test_default_is_in_memory,
            test_explicit_in_memory_value_case_and_space_insensitive,
            test_postgres_value_builds_lazy_durable_store_no_io,
            test_custom_dsn_ref_env_is_honored,
            test_invalid_selector_fails_closed,
            test_explicit_store_overrides_env_and_builds_no_durable_store,
            test_create_app_default_is_in_memory,
            test_create_app_postgres_mode_constructs_without_io_and_preserves_bootstrap_secret_store,
        ]
    )
