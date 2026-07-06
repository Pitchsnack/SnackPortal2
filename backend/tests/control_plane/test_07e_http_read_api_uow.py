"""PRD 07E-1 — read-edge per-request unit-of-work behavioural proofs (default suite).

Exercises the REAL stdlib HTTP read edge over loopback (server-in-a-thread is a TEST-side
driver only): every GET acquires a fresh ControlStore unit of work, uses ONLY the yielded
store, and releases it BEFORE the response is written; non-GET is refused 405; unknown
records are consistent 404s (no existence leak); store/connection failures return a fixed
503 with an EMPTY body leaking no tenant/database/connection/secret detail; 404/405 pass
through unchanged and no 4xx/5xx widens to 2xx; the transport module imports no database
driver or vendor client. Self-skips only if loopback sockets are unavailable.
"""

from __future__ import annotations

import ast
import contextlib
import json
import pathlib
import sys
import threading
import urllib.error
import urllib.request
from typing import Iterator, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from control_plane.adapters.providers import http_read_api  # noqa: E402
from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.main import ControlPlane  # noqa: E402
from control_plane.ports import ControlStore  # noqa: E402
from control_plane.records import TenantLifecycleState, TenantRecord  # noqa: E402
from shared.secrets import SecretRef  # noqa: E402


def _seeded_store() -> InMemoryControlStore:
    store = InMemoryControlStore()
    store.put_tenant(
        TenantRecord(
            tenant_id="t1",
            organization_ref="org",
            lifecycle_state=TenantLifecycleState.READY,
            expected_schema_version="1",
            database_association_ref=SecretRef("tenant/t1/db", "1"),
            federation_config_ref="fed",
            created_at="t0",
            updated_at="t0",
        )
    )
    return store


class _BoomStore(InMemoryControlStore):
    """Read failure double: raises with a sensitive-looking message that must NOT leak."""

    def get_tenant(self, tenant_id: str):  # type: ignore[override]
        raise RuntimeError("connect failed: postgresql://control_user:SECRETPW@10.0.0.9:5432/control")


def _get(base: str, path: str) -> Tuple[int, bytes]:
    try:
        with urllib.request.urlopen(base + path, timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()


@contextlib.contextmanager
def _serving(cp: ControlPlane) -> Iterator[Optional[str]]:
    try:
        server, base = http_read_api.make_server(cp, "127.0.0.1", 0)
    except OSError:
        yield None  # loopback unavailable in this sandbox; checks self-skip
        return
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield base
    finally:
        server.shutdown()
        server.server_close()


def test_per_request_uow_release_before_write_on_yielded_store() -> None:
    # §8B.8/.10: the UoW store is the one the read hits, and the UoW is RELEASED before
    # the response body is serialized/written. Order proven at runtime via an event log:
    # read (on the yielded store) -> release (factory CM exit) -> serialize (json.dumps).
    events: List[str] = []
    base_store = _seeded_store()

    class _ProbeStore(InMemoryControlStore):
        def __init__(self) -> None:
            super().__init__()
            self._tenants = base_store._tenants  # share seeded state

        def get_tenant(self, tenant_id: str):  # type: ignore[override]
            events.append("read")
            return super().get_tenant(tenant_id)

    probe_store = _ProbeStore()
    cp = ControlPlane(store=probe_store)
    real_factory = cp.store_factory

    class _ProbeFactory:
        def acquire(self):  # type: ignore[no-untyped-def]
            @contextlib.contextmanager
            def _cm():  # type: ignore[no-untyped-def]
                with real_factory.acquire() as store:
                    events.append("acquire")
                    try:
                        yield store
                    finally:
                        events.append("release")

            return _cm()

    cp.store_factory = _ProbeFactory()  # type: ignore[assignment]
    real_dumps = http_read_api.json.dumps

    def _tracing_dumps(*args, **kwargs):  # type: ignore[no-untyped-def]
        events.append("serialize")
        return real_dumps(*args, **kwargs)

    http_read_api.json.dumps = _tracing_dumps  # type: ignore[assignment]
    try:
        with _serving(cp) as base:
            if base is None:
                return
            status, body = _get(base, "/tenants/t1/state")
    finally:
        http_read_api.json.dumps = real_dumps  # type: ignore[assignment]
    assert status == 200 and json.loads(body)["ready"] is True
    assert events == ["acquire", "read", "release", "serialize"], (
        f"the UoW must be acquired per request, read on the YIELDED store, and released BEFORE the response is serialized/written: {events}"
    )


def test_fresh_uow_per_request_none_at_construction() -> None:
    # §7.1/.2: no store acquired at server construction; each request = exactly one acquire.
    acquires: List[int] = []
    cp = ControlPlane(store=_seeded_store())
    real_factory = cp.store_factory

    class _CountingFactory:
        def acquire(self):  # type: ignore[no-untyped-def]
            acquires.append(1)
            return real_factory.acquire()

    cp.store_factory = _CountingFactory()  # type: ignore[assignment]
    with _serving(cp) as base:
        if base is None:
            return
        assert acquires == [], "server construction must acquire NO unit of work"
        _get(base, "/tenants/t1/state")
        _get(base, "/tenants/t1/state")
        _get(base, "/internal/routing/tenants/t1")
    assert len(acquires) == 3, f"exactly one fresh UoW per request (got {len(acquires)} for 3 requests)"


def test_non_get_refused_405_and_dispatcher_passthrough() -> None:
    # §8B.1/.6/.7: non-GET -> 405 empty body over HTTP; dispatcher 405/404 results pass
    # through unchanged; nothing widens to 2xx.
    from control_plane.read_api import ControlPlaneReadDispatcher, ControlPlaneReadService

    disp = ControlPlaneReadDispatcher(ControlPlaneReadService(_seeded_store()))
    assert disp.handle("POST", "/tenants/t1/state") == (405, {"error": "method_not_allowed"})
    cp = ControlPlane(store=_seeded_store())
    with _serving(cp) as base:
        if base is None:
            return
        for method in ("POST", "PUT", "DELETE"):
            req = urllib.request.Request(base + "/tenants/t1/state", method=method, data=b"")
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    raise AssertionError(f"{method} must not widen to 2xx (got {resp.status})")
            except urllib.error.HTTPError as err:
                assert err.code == 405, f"{method} must be refused 405 (got {err.code})"
                assert err.read() == b"", "the 405 refusal must carry an EMPTY body"


def test_unknown_records_consistent_404_no_existence_leak() -> None:
    # §8B.2/.3/.6: unknown/absent records and malformed targets fail closed to the SAME
    # consistent 404 body — no tenant-existence or shape leak, no widening to 2xx.
    cp = ControlPlane(store=_seeded_store())
    with _serving(cp) as base:
        if base is None:
            return
        bodies = set()
        for path in ("/tenants/ghost/state", "/internal/routing/tenants/ghost", "/nope", "/directory", "///"):
            status, body = _get(base, path)
            assert status == 404, f"{path} must fail closed 404 (got {status})"
            bodies.add(body)
        assert bodies == {b'{"error": "not_found"}'}, f"404s must be consistent (no leak): {bodies}"
        assert b"ghost" not in next(iter(bodies)), "the denial must not echo the probed identifier"


def test_store_failure_fixed_503_empty_body_no_leak() -> None:
    # §8B.4/.5: a store/connection failure returns a FIXED 503 with an EMPTY body; no
    # tenant, database, connection, or secret detail leaks in body or headers.
    cp = ControlPlane(store=_BoomStore())
    with _serving(cp) as base:
        if base is None:
            return
        try:
            with urllib.request.urlopen(base + "/tenants/t1/state", timeout=5) as resp:
                raise AssertionError(f"a store failure must not widen to 2xx (got {resp.status})")
        except urllib.error.HTTPError as err:
            assert err.code == 503, f"store failure must return the fixed 503 (got {err.code})"
            body = err.read()
            assert body == b"", f"the 503 body must be EMPTY (got {body!r})"
            header_blob = str(err.headers).lower()
            for needle in ("postgresql", "secretpw", "10.0.0.9", "control_user", "runtimeerror"):
                assert needle not in header_blob, f"connection detail must not leak via headers: {needle}"


def test_transport_module_imports_no_db_driver_or_vendor_client() -> None:
    # §8B.9: the transport module binds no DB driver / Supabase / PostgREST / vendor client.
    src = pathlib.Path(http_read_api.__file__).read_text(encoding="utf-8")
    banned = {"psycopg", "psycopg2", "supabase", "postgrest", "sqlalchemy", "asyncpg", "pg8000"}
    imported: set = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])
    assert not (imported & banned), f"transport must not bind a DB driver/vendor client: {imported & banned}"
    assert not any(isinstance(v, ControlStore) for v in vars(http_read_api).values()), (
        "the transport module must hold no module-global ControlStore"
    )


_TESTS = [
    test_per_request_uow_release_before_write_on_yielded_store,
    test_fresh_uow_per_request_none_at_construction,
    test_non_get_refused_405_and_dispatcher_passthrough,
    test_unknown_records_consistent_404_no_existence_leak,
    test_store_failure_fixed_503_empty_body_no_leak,
    test_transport_module_imports_no_db_driver_or_vendor_client,
]

if __name__ == "__main__":
    _h.run(_TESTS)
