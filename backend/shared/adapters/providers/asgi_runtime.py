"""ASGI serving runtime for the FastAPI service edges (uvicorn) — vendor-containment zone.

Every SnackPortal2 HTTP edge is a FastAPI application; this module is the ONE place the
concrete ASGI server (uvicorn) is constructed, so the vendor import stays inside the
sanctioned ``adapters/providers`` containment zone (governance F-1) and every edge module
above it depends on a portable, framework-shaped lifecycle instead of on uvicorn directly.

``AsgiEdgeServer`` deliberately reproduces the exact lifecycle surface the edges were built
against — ``server_address`` / ``serve_forever()`` / ``shutdown()`` / ``server_close()`` —
so composition roots, runbooks, and the served-edge rehearsal harness keep their contract
unchanged across the migration:

* the listening socket is bound AND listening at CONSTRUCTION (never at serve time), so
  ``port=0`` yields an ephemeral port readable from ``server_address`` before anything
  serves, and a client that connects between construction and ``serve_forever()`` is queued
  rather than refused;
* ``serve_forever()`` blocks on the CALLING thread and runs the request loop exactly once;
* ``shutdown()`` is thread-safe, may be called before/without serving, and BLOCKS until the
  request loop has actually exited (the stdlib contract callers rely on);
* ``server_close()`` is idempotent and releases the socket.

Serving posture (fail closed, IC-010 §L): uvicorn's own logging is fully disabled
(``log_config=None``, ``access_log=False``) so no request line, header, token, or payload
is ever written to stderr — the migrated equivalent of the stdlib edges' silenced
``log_message``. The ``server`` response header is suppressed so the edge discloses no
runtime identity or version. ASGI lifespan is off: these edges own no startup/shutdown
event, and a lifespan error must never be able to keep a socket half-open.
"""

from __future__ import annotations

import socket
import threading
from typing import Any, Tuple

import uvicorn

__all__ = ["AsgiEdgeServer", "build_asgi_server"]

# Bounded graceful-shutdown budget: `shutdown()` must return promptly for the test/rehearsal
# lifecycles that stop an edge between assertions, never hang on a lingering keep-alive peer.
_GRACEFUL_SHUTDOWN_SECONDS = 1
# Upper bound on how long `shutdown()` waits for the serve loop to actually exit before
# returning anyway (the caller's `server_close()` then releases the socket regardless).
_SHUTDOWN_JOIN_SECONDS = 10.0
# Listen backlog for the eagerly-bound socket (the stdlib HTTPServer default).
_LISTEN_BACKLOG = 5


class AsgiEdgeServer:
    """A uvicorn-backed ASGI server exposing the stdlib server lifecycle surface.

    Construction binds and listens; it does NOT serve. ``serve_forever()`` runs the request
    loop on the calling thread until ``shutdown()`` is called (or the loop raises, which
    propagates unswallowed). Every edge in the codebase is composed through this one class.
    """

    def __init__(self, app: Any, sock: socket.socket) -> None:
        # The composed FastAPI app is exposed READ-ONLY so a caller can inspect what was actually
        # wired (the live-proof harnesses recover the composed Authenticator / DatabaseRouter from
        # the route endpoints' closures, as they previously did from the stdlib handler class).
        self.app = app
        self._sock = sock
        self._closed = False
        # server_address is read by callers immediately after construction (ephemeral ports),
        # so it is snapshotted here — never re-read from a socket that may later be closed.
        host, port = sock.getsockname()[:2]
        self.server_address: Tuple[str, int] = (host, port)
        config = uvicorn.Config(
            app,
            log_config=None,  # never install uvicorn's logging config (no request/stderr logging)
            access_log=False,  # the migrated equivalent of the stdlib edges' silenced log_message
            lifespan="off",  # these edges own no ASGI lifespan event
            server_header=False,  # disclose no runtime identity or version
            timeout_graceful_shutdown=_GRACEFUL_SHUTDOWN_SECONDS,
        )
        # The uvicorn Server object touches no event loop at construction, so it is built here
        # and kept — `shutdown()` must be able to signal an exit even before serving starts.
        self._server = uvicorn.Server(config)
        self._stopped = threading.Event()
        self._stopped.set()  # not serving yet: a shutdown() before serve_forever() must not block

    def serve_forever(self) -> None:
        """Run the request loop on the CALLING thread until ``shutdown()`` (blocking).

        Exactly one serve loop per call; no thread, daemon, subprocess, supervisor, or retry
        loop is created here. Any serve-time exception (and ``KeyboardInterrupt``) propagates
        to the caller unswallowed, exactly as the stdlib ``serve_forever`` did.
        """
        self._stopped.clear()
        try:
            self._server.run(sockets=[self._sock])
        finally:
            self._stopped.set()

    def shutdown(self) -> None:
        """Stop the request loop and BLOCK until it has exited (thread-safe, idempotent).

        Safe to call before or without ``serve_forever()``: the stopped event starts set, so
        this returns immediately when nothing is serving.
        """
        self._server.should_exit = True
        self._stopped.wait(_SHUTDOWN_JOIN_SECONDS)

    def server_close(self) -> None:
        """Release the listening socket (idempotent).

        uvicorn closes the sockets it served when the loop exits, so this may run against an
        already-closed socket; ``socket.close()`` tolerates that.
        """
        if self._closed:
            return
        self._closed = True
        self._sock.close()


def build_asgi_server(app: Any, host: str = "127.0.0.1", port: int = 0) -> Tuple[AsgiEdgeServer, str]:
    """Bind a FastAPI ``app`` to ``host:port`` and return ``(server, base_url)``.

    ``port=0`` binds an ephemeral port, which is resolved and reflected in the returned
    ``base_url`` before anything serves. The socket is bound and LISTENING on return; the
    request loop is not running (the caller owns ``serve_forever``/``shutdown``/
    ``server_close``). An unbindable host/port surfaces as ``OSError`` here — no partially
    constructed server is ever returned.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # SO_REUSEADDR matches the stdlib HTTPServer default (allow_reuse_address = 1) so an
        # edge can rebind a recently released port instead of failing on TIME_WAIT.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(_LISTEN_BACKLOG)
    except BaseException:
        sock.close()
        raise
    server = AsgiEdgeServer(app, sock)
    bound_host, bound_port = server.server_address
    return server, f"http://{bound_host}:{bound_port}"
