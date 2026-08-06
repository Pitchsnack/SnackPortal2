"""PRD 07E-1A (AT-07E1-16) — production-composition smoke for the read edge (default suite).

Proves the ``make_server(create_app())`` seam: the read-edge HTTP server composed over the REAL
production app factory — ``create_app()`` (``ControlPlane``, default in-memory store, ZERO I/O at
construction) — binds a fresh loopback ephemeral port and closes cleanly. This is the exact composition
``serve_read_api()`` performs (``http_read_api.py``), which is ``# pragma: no cover`` and blocking; every
OTHER default-suite ``make_server(...)`` call injects an explicit ``store=`` (``test_directory_read_api``,
``test_routing_read_api``, ``test_07e_http_read_api_uow``), so the un-injected production-factory seam is
otherwise exercised only under the ADVISORY requires_pg live-PG harness — never in the merge gate.

Deliberately: composes via ``create_app()`` (NOT an explicit ``store=``); does NOT call the blocking
``serve_read_api()``; needs NO external PostgreSQL (the default store is in-memory). Self-skips only if
loopback sockets are unavailable in the sandbox (``OSError`` on bind), mirroring ``_serving`` in
``test_07e_http_read_api_uow.py``.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from control_plane.adapters.providers import http_read_api  # noqa: E402
from control_plane.main import create_app  # noqa: E402
from shared.adapters.providers.asgi_runtime import AsgiEdgeServer  # noqa: E402


def test_production_composition_seam_binds_and_closes_cleanly() -> None:
    # AT-07E1-16: create_app() (production factory; in-memory default; no I/O) -> make_server -> bind a
    # fresh ephemeral loopback port -> clean server_close(). No explicit store=; no serve_read_api().
    try:
        server, base_url = http_read_api.make_server(create_app(), "127.0.0.1", 0)
    except OSError:
        return  # loopback unavailable in this sandbox; self-skip (mirrors _serving's OSError guard)
    try:
        # (1) the seam actually BOUND: port=0 asks the OS for an ephemeral port; it must be non-zero.
        bound_port = server.server_address[1]
        assert bound_port != 0, f"make_server(create_app()) must bind a non-zero ephemeral port (got {bound_port})"
        assert base_url == f"http://127.0.0.1:{bound_port}", (
            f"base_url {base_url!r} must carry the bound loopback host and port {bound_port}"
        )
        # (2) read-edge runtime pin: the sanctioned shared AsgiEdgeServer exactly, never a subclass
        # or a bespoke per-service server — every edge serves through the one containment-zone runtime.
        assert type(server) is AsgiEdgeServer, (
            f"the read edge must compose the shared AsgiEdgeServer, not a subclass (got {type(server).__name__})"
        )
    finally:
        # (3) CLEAN close: releases the ephemeral port and must not raise (guards a bind/socket leak).
        server.server_close()


_TESTS = [
    test_production_composition_seam_binds_and_closes_cleanly,
]

if __name__ == "__main__":
    _h.run(_TESTS)
