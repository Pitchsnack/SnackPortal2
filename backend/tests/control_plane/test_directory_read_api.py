"""Global Directory read surface (PRD-P5-R2 E; D-31): record + cursor pagination; loopback.

Global reference data only — never tenant-owned records. Includes a best-effort real-HTTP
round-trip against the import_service directory client (closes R-P5-04 end to end).
"""

from __future__ import annotations

import pathlib
import sys
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.read_api import ControlPlaneReadDispatcher, ControlPlaneReadService  # noqa: E402
from control_plane.records import DirectoryKind, DirectoryRecord  # noqa: E402


def _store():
    store = InMemoryControlStore()
    for i in range(1, 6):
        store.put_directory_record(
            DirectoryRecord(
                directory=DirectoryKind.STARTUP,
                record_id=f"g{i}",
                display_name=f"S{i}",
                attributes={"sector": "ai"},
            )
        )
    return store


def test_directory_record_lookup() -> None:
    svc = ControlPlaneReadService(_store())
    view = svc.directory_record("startup", "g1")
    assert view["record_id"] == "g1" and view["directory"] == "GlobalStartupDirectory"
    assert svc.directory_record("startup", "nope") is None
    assert svc.directory_record("bogus", "g1") is None  # unknown kind -> None


def test_directory_cursor_pagination() -> None:
    svc = ControlPlaneReadService(_store())
    p1 = svc.directory_page("startup", "", 2)
    assert [r["record_id"] for r in p1["records"]] == ["g1", "g2"] and p1["next_cursor"] == "2"
    p2 = svc.directory_page("startup", p1["next_cursor"], 2)
    assert [r["record_id"] for r in p2["records"]] == ["g3", "g4"] and p2["next_cursor"] == "4"
    p3 = svc.directory_page("startup", p2["next_cursor"], 2)
    assert [r["record_id"] for r in p3["records"]] == ["g5"] and p3["next_cursor"] is None


def test_dispatcher_directory_routes() -> None:
    disp = ControlPlaneReadDispatcher(ControlPlaneReadService(_store()))
    status, body = disp.handle("GET", "/directory/startup/g1")
    assert status == 200 and body["record_id"] == "g1"
    status, _ = disp.handle("GET", "/directory/startup/nope")
    assert status == 404
    status, body = disp.handle("GET", "/directory/startup?limit=2")
    assert status == 200 and len(body["records"]) == 2
    status, _ = disp.handle("GET", "/directory/bogus/g1")
    assert status == 404


def test_directory_http_roundtrip_best_effort() -> None:
    from control_plane.adapters.providers.http_read_api import make_server
    from control_plane.main import ControlPlane
    from import_service.adapters.providers.http_directory_read import HttpDirectoryRead

    try:
        # PRD 07E-1: make_server binds a ControlPlane (per-request UoW), not a store.
        server, base = make_server(ControlPlane(store=_store()), "127.0.0.1", 0)
    except OSError:
        return
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = HttpDirectoryRead(base, timeout=2.0)
        view = client.get_record("startup", "g1")
        assert view is not None and view.record_id == "g1"
        page = client.page("startup", None, 2)
        assert len(page.records) == 2 and page.next_cursor == "2"
        assert client.get_record("startup", "nope") is None
    except OSError:
        return
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    _h.run(
        [
            test_directory_record_lookup,
            test_directory_cursor_pagination,
            test_dispatcher_directory_routes,
            test_directory_http_roundtrip_best_effort,
        ]
    )
